#!/usr/bin/env python3
"""Convert annotate.py's MASM-flavor x86 output into JWasm-acceptable form.

The X86Decoder's `syntax="masm"` mode already emits most of what JWasm wants
(`es:[..]`, `word ptr [..]`, `dword ptr [..]`, MASM-style segment overrides),
but JWasm rejects two things:

1. Short/near jumps with numeric targets — `jbe short 66h`. JWasm wants
   labels, period: `jbe short LOC_0066`. We synthesise one `LOC_XXXX:`
   label per distinct jump/call target by scanning the `;#XXXX:` byte
   markers the decoder leaves on every line, then rewrite the operands.

2. `imm16 NN` qualifiers, if any leak through from FASM-style output —
   `sub ax, imm16 20h` becomes `db 2Dh, 20h, 0`. Includes the
   ADD/OR/ADC/SBB/AND/SUB/XOR/CMP family.

Usage: nasm_to_jwasm.py <input.asm> <output.asm>
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiny_cc


# AX-imm16 opcode (bit 7..3 selects the op, bit 0 selects AX vs AL).
AX_IMM16_OPCODES = {
    'add': 0x05, 'or':  0x0D, 'adc': 0x15, 'sbb': 0x1D,
    'and': 0x25, 'sub': 0x2D, 'xor': 0x35, 'cmp': 0x3D,
}

# String ops accept rep/repe/repne. Anything else with that prefix is bogus
# decoding (a stray F0/F2/F3 in data being interpreted as code), so JWasm
# rejects it — we convert those lines back to raw `db` bytes.
STRING_OPS = {
    'movsb', 'movsw', 'cmpsb', 'cmpsw',
    'stosb', 'stosw', 'lodsb', 'lodsw',
    'scasb', 'scasw',
}

# Trailing-marker regex used by several passes to recover raw bytes.
RAW_BYTES_RE = re.compile(
    r'^(\s*).*;#([0-9A-Fa-f]+):\s*((?:[0-9A-Fa-f]{2}\s+)*[0-9A-Fa-f]{2})\s*(.*)$'
)


def expand_compiled(lines):
    """Expand annotate.py's [compiled] marker blocks into `db` bytes by
    compiling the inline C with tiny_cc.

    A block looks like:
        ;@compiled NAME ADDR SIZE
        <c source line>
        ...
        ;@endcompiled
    Everything between ;@compiled and ;@endcompiled that is not a ;@ marker
    line is the (indented) C body. The whole block is replaced with `db`
    lines carrying `;#ADDR: bytes` markers (16 bytes/line) so the downstream
    passes and the bit-perfect build treat it like any other data."""
    out = []
    i = 0
    n = len(lines)
    header_lines = []   # shared C extern decls prepended to every block
    while i < n:
        line = lines[i]
        # Shared header block (emitted once at the top): collect its C lines and
        # drop it — it produces no bytes, only declarations for tiny_cc.
        if re.match(r'^\s*;@compiled_headers\s*$', line):
            i += 1
            while i < n and not re.match(r'^\s*;@endcompiled_headers\s*$', lines[i]):
                if not lines[i].strip().startswith(';@'):
                    header_lines.append(lines[i])
                i += 1
            i += 1  # skip ;@endcompiled_headers
            continue
        m = re.match(r'^\s*;@compiled\s+(\S+)\s+([0-9A-Fa-f]+)\s+(\d+)\s*$', line)
        if not m:
            out.append(line)
            i += 1
            continue
        name = m.group(1)
        addr = int(m.group(2), 16)
        size = int(m.group(3))
        # The function's own address comes from the header; every extern pins
        # its own address with __addr__(N) in the C.
        addr_map = {name: addr}
        c_lines = []
        i += 1
        while i < n and not re.match(r'^\s*;@endcompiled\s*$', lines[i]):
            l = lines[i]
            if l.strip().startswith(';@'):
                pass  # marker line — ignored
            else:
                c_lines.append(l)  # C body line (tiny_cc ignores indentation)
            i += 1
        i += 1  # skip ;@endcompiled

        # Prepend the shared header decls so the block holds only its function.
        c_src = "\n".join(header_lines + c_lines)
        result = tiny_cc.compile_src(c_src, addr_map)
        if name not in result:
            print(f"Error: tiny_cc did not produce function '{name}' from the "
                  f"[compiled] block at {addr:04X}", file=sys.stderr)
            sys.exit(1)
        _, code = result[name]
        # Sanity check the declared size; the final bit-perfect md5 on the
        # assembled ROM is what actually verifies the bytes.
        if len(code) != size:
            print(f"Error: compiled '{name}' is {len(code)} bytes, expected "
                  f"{size} (declared at {addr:04X})", file=sys.stderr)
            sys.exit(1)

        out.append(f"        ; compiled: {name} ({size} bytes)")
        for off in range(0, len(code), 16):
            chunk = code[off:off + 16]
            hexparts = []
            for b in chunk:
                t = f"{b:02X}h"
                if not t[0].isdigit():
                    t = "0" + t
                hexparts.append(t)
            raw = " ".join(f"{b:02X}" for b in chunk)
            db = f"        db      {', '.join(hexparts)}"
            pad = " " * max(1, 63 - len(db))
            out.append(f"{db}{pad};#{addr + off:04X}: {raw}")
    return out


def line_to_db(line, note=""):
    """Rewrite `line` as a raw `db NN, NN, ...` using its trailing
    `;#XXXX: bytes` marker. Returns None if the line lacks a marker."""
    rm = RAW_BYTES_RE.match(line)
    if not rm:
        return None
    indent = rm.group(1)
    addr = rm.group(2)
    bytes_str = rm.group(3).strip()
    bs = [b for b in bytes_str.split() if len(b) == 2]
    hexparts = []
    for b in bs:
        s = f"{b}h"
        if not s[0].isdigit():
            s = "0" + s
        hexparts.append(s)
    tail = f"  ({note})" if note else ""
    return (f"{indent}db      {', '.join(hexparts)}"
            f"    ;#{addr}: {bytes_str}{tail}")


def _extract_marker_bytes(line):
    """Pull the byte sequence out of a `;#XXXX: bytes` marker. Returns
    a list of int bytes, or None if the line has no marker."""
    rm = RAW_BYTES_RE.match(line)
    if not rm:
        return None
    return [int(b, 16) for b in rm.group(3).split() if len(b) == 2]


# Opcodes that take a ModR/M byte. Used to compute the displacement
# location in `would_canonicalise`. This is the 8086 subset (no LEA/etc.
# need special handling — they all take ModR/M).
_MODRM_OPS = (
    set(range(0x00, 0x04)) | set(range(0x08, 0x0C))
    | set(range(0x10, 0x14)) | set(range(0x18, 0x1C))
    | set(range(0x20, 0x24)) | set(range(0x28, 0x2C))
    | set(range(0x30, 0x34)) | set(range(0x38, 0x3C))
    | {0x62, 0x63}                  # bound (not 8086), arpl (286+)
    | set(range(0x80, 0x90))        # GRP1, TEST, XCHG, MOV r,rm
    | {0x8C, 0x8D, 0x8E, 0x8F}      # MOV sreg, LEA, MOV sreg, POP rm
    | {0xC0, 0xC1, 0xC4, 0xC5, 0xC6, 0xC7}  # shift-imm (186+), LES/LDS, MOV
    | set(range(0xD0, 0xD4))        # GRP2 shift
    | set(range(0xD8, 0xE0))        # FPU escapes
    | {0xF6, 0xF7, 0xFE, 0xFF}      # GRP3, GRP4, GRP5
)


def _modrm_extra_len(bytes_, modrm_pos):
    """Length of the ModR/M byte + displacement. modrm_pos is the
    offset of the ModR/M byte in `bytes_`."""
    if modrm_pos >= len(bytes_):
        return 0
    mod = (bytes_[modrm_pos] >> 6) & 3
    rm = bytes_[modrm_pos] & 7
    if mod == 3:
        return 1
    if mod == 0 and rm == 6:
        return 3   # ModR/M + disp16
    if mod == 0:
        return 1
    if mod == 1:
        return 2   # ModR/M + disp8
    return 3       # mod=2: ModR/M + disp16


def _default_seg(modrm):
    """Default segment ('ds'/'ss'/None) for the addressing mode encoded
    in this ModR/M byte. None when mod=3 (register, no segment)."""
    mod = (modrm >> 6) & 3
    rm = modrm & 7
    if mod == 3:
        return None
    if rm in (2, 3):                  # [bp+si], [bp+di]
        return 'ss'
    if rm == 6 and mod != 0:          # [bp+disp]
        return 'ss'
    return 'ds'


# Arith opcode bytes for GRP1 (ADD/OR/ADC/SBB/AND/SUB/XOR/CMP). The
# *non*-AX-imm forms (00..3D excluding 04/05/0C/0D/14/15/1C/1D/...) split
# on d-bit (bit 1) and w-bit (bit 0).
_ARITH_NONIMM_OPS = {
    0x00, 0x01, 0x02, 0x03,           # ADD
    0x08, 0x09, 0x0A, 0x0B,           # OR
    0x10, 0x11, 0x12, 0x13,           # ADC
    0x18, 0x19, 0x1A, 0x1B,           # SBB
    0x20, 0x21, 0x22, 0x23,           # AND
    0x28, 0x29, 0x2A, 0x2B,           # SUB
    0x30, 0x31, 0x32, 0x33,           # XOR
    0x38, 0x39, 0x3A, 0x3B,           # CMP
}


def would_canonicalise(bytes_):
    """Return True if JWasm would not round-trip these instruction bytes
    given the clean mnemonic annotate.py emits.

    Covers every case where JWasm picks a different (usually shorter)
    encoding for an equivalent mnemonic, plus a few cases where the bytes
    decode to a mnemonic JWasm rejects outright (lds reg-reg, aad imm,
    direct far jump with numeric seg:off). The detector is byte-pattern
    based — no full disassembly needed."""
    if not bytes_:
        return False
    # Step past prefixes; remember whether we saw a seg override.
    i = 0
    seg = None
    while i < len(bytes_) and bytes_[i] in (0x26, 0x2E, 0x36, 0x3E,
                                            0xF0, 0xF2, 0xF3):
        if bytes_[i] == 0x26:
            seg = 'es'
        elif bytes_[i] == 0x2E:
            seg = 'cs'
        elif bytes_[i] == 0x36:
            seg = 'ss'
        elif bytes_[i] == 0x3E:
            seg = 'ds'
        i += 1
    if i >= len(bytes_):
        return False
    op = bytes_[i]

    # Reg-reg arith with d=0 → JWasm always picks d=1.
    if op in _ARITH_NONIMM_OPS and (op & 2) == 0:
        if i + 1 < len(bytes_) and (bytes_[i + 1] & 0xC0) == 0xC0:
            return True

    # 0x82 is an undocumented alias for 0x80; JWasm canonicalises.
    if op == 0x82:
        return True

    # AX-imm16 (0x05, 0x0D, ...) where imm fits sign-extended imm8.
    # JWasm canonicalises to the 0x83 sign-extended form (same length,
    # different bytes).
    if op in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
        if i + 2 < len(bytes_):
            imm = bytes_[i + 1] | (bytes_[i + 2] << 8)
            if imm <= 0x7F or imm >= 0xFF80:
                return True

    # 0x81 imm16 fitting sign-extended imm8 → JWasm shrinks to 0x83 form.
    if op == 0x81:
        extra = _modrm_extra_len(bytes_, i + 1)
        imm_pos = i + 1 + extra
        if imm_pos + 1 < len(bytes_):
            imm = bytes_[imm_pos] | (bytes_[imm_pos + 1] << 8)
            if imm <= 0x7F or imm >= 0xFF80:
                return True

    # XCHG r/m, r with mod=3 (reg-reg). JWasm may canonicalise to either
    # the opposite ModR/M ordering (commutative) or to the 1-byte
    # `xchg ax, r16` form when AX is involved.
    if op in (0x86, 0x87):
        if i + 1 < len(bytes_) and (bytes_[i + 1] & 0xC0) == 0xC0:
            return True

    # MOV r/m, r with mod=3 (d=0 reg-reg). JWasm picks the d=1 form
    # (0x8A/0x8B) and emits a different ModR/M byte.
    if op in (0x88, 0x89):
        if i + 1 < len(bytes_) and (bytes_[i + 1] & 0xC0) == 0xC0:
            return True

    # TEST r/m, r with mod=3 (reg-reg).  TEST is commutative, so JWasm is free
    # to swap reg and r/m and emit the mirrored ModR/M byte — `test ax, bx` at
    # 85 D8 comes back as 85 C3 (COMMAND.COM 31E1h).
    if op in (0x84, 0x85):
        if i + 1 < len(bytes_) and (bytes_[i + 1] & 0xC0) == 0xC0:
            return True

    # MOV r/m, Sreg with reg field >= 4 (undocumented alias for reg 0..3).
    if op in (0x8C, 0x8E):
        if i + 1 < len(bytes_) and ((bytes_[i + 1] >> 3) & 7) >= 4:
            return True

    # Direct far CALL / JMP ptr16:16 — JWasm wants a labelled FAR target.
    if op in (0x9A, 0xEA):
        return True

    # LDS / LES with register r/m — invalid; JWasm rejects.
    if op in (0xC4, 0xC5):
        if i + 1 < len(bytes_) and (bytes_[i + 1] & 0xC0) == 0xC0:
            return True

    # MOV r/m, imm with register r/m — JWasm uses shorter B0..BF form.
    if op in (0xC6, 0xC7):
        if i + 1 < len(bytes_) and (bytes_[i + 1] & 0xC0) == 0xC0:
            return True

    # AAM / AAD with operand != 0Ah — JWasm rejects.
    if op in (0xD4, 0xD5):
        if i + 1 < len(bytes_) and bytes_[i + 1] != 0x0A:
            return True

    # GRP2 shift with sub-field = 6 (undocumented SHL alias).
    if 0xD0 <= op <= 0xD3:
        if i + 1 < len(bytes_) and ((bytes_[i + 1] >> 3) & 7) == 6:
            return True

    # Non-canonical displacement and redundant seg override — both flagged
    # for ops that take ModR/M.
    if op in _MODRM_OPS and i + 1 < len(bytes_):
        modrm = bytes_[i + 1]
        mod = (modrm >> 6) & 3
        rm = modrm & 7
        # Redundant seg override matching the addressing default.
        if seg is not None and _default_seg(modrm) == seg:
            return True
        if mod == 1 and rm != 6 and i + 2 < len(bytes_):
            if bytes_[i + 2] == 0:               # disp8=0 → JWasm uses mod=0
                return True
        elif mod == 2 and rm != 6 and i + 3 < len(bytes_):
            disp = bytes_[i + 2] | (bytes_[i + 3] << 8)
            if disp == 0:                        # disp16=0 → mod=0
                return True
            if disp <= 0x7F or disp >= 0xFF80:   # fits disp8 → mod=1
                return True
    # Seg override on an instruction that takes no ModR/M memory operand
    # (mov reg, imm; push/pop reg; ret; …) is dropped by JWasm.
    elif seg is not None and op not in _MODRM_OPS:
        return True

    return False


BYTE_REGS = {'al', 'bl', 'cl', 'dl', 'ah', 'bh', 'ch', 'dh'}
WORD_REGS = {'ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp',
             'es', 'cs', 'ss', 'ds'}  # segment registers — word-sized


def _operand_size(operands):
    """If any comma-separated operand is a sized register, return
    'byte'/'word'. Returns None if the size can't be deduced."""
    for op in operands:
        tok = op.strip().lower()
        if tok in BYTE_REGS:
            return 'byte'
        if tok in WORD_REGS:
            return 'word'
    return None


def _translate_syntax(code):
    """NASM-style → JWasm/MASM-style operand syntax (one line, sans the
    trailing `;#…` marker)."""
    # `0xNN` → `0NNh` — JWasm doesn't accept C-style hex.
    def hex_repl(m):
        h = m.group(1)
        prefix = '0' if h[0].isalpha() else ''
        return f'{prefix}{h}h'
    code = re.sub(r'\b0x([0-9A-Fa-f]+)\b', hex_repl, code)
    # Move `seg:` inside brackets to outside: `[es:NN]` → `es:[NN]`.
    code = re.sub(r'\[([cdes]s):([^\]]+)\]', r'\1:[\2]', code)
    # NASM size keyword → MASM `size ptr`. Only on a memory operand.
    code = re.sub(r'\b(byte|word|dword)\s+(?=(?:[cdes]s:)?\[)',
                  r'\1 ptr ', code)
    # `call/jmp near LBL` → `call/jmp near ptr LBL`. Don't touch `near`
    # when it's already followed by `ptr`.
    code = re.sub(r'\b(call|jmp)\s+near\b(?!\s+ptr\b)',
                  r'\1 near ptr', code)
    # `int3` → `int 3` (JWasm parses int3 as an identifier, not the op).
    code = re.sub(r'\bint3\b', 'int 3', code)
    # `rep` with cmps/scas means REPE/REPZ; JWasm enforces the distinction.
    code = re.sub(
        r'\brep\s+(cmpsb|cmpsw|scasb|scasw)\b', r'repe \1', code)
    # `times N db V` → `db N dup (V)` (MASM/JWasm syntax).
    code = re.sub(r'\btimes\s+(\S+)\s+db\s+(.+?)(?=\s*$|\s+;)',
                  r'db \1 dup (\2)', code)
    # FF /3 and /5 with memory: NASM emits `call/jmp far word [..]` or
    # `call/jmp far [..]`; JWasm wants `call/jmp dword ptr [..]` (no
    # `far`, the size *is* dword for a 16:16 far pointer).
    code = re.sub(r'\b(call|jmp)\s+far\s+word\s+ptr\s+',
                  r'\1 dword ptr ', code)
    code = re.sub(r'\b(call|jmp)\s+far\s+(?=(?:[cdes]s:)?\[)',
                  r'\1 dword ptr ', code)
    # 0xC4/0xC5 LDS/LES: operand is a 32-bit far pointer in memory.
    # NASM may render the size as `word`; JWasm wants `dword ptr`.
    code = re.sub(r'\b(lds|les)\s+([a-z]+),\s+word\s+ptr\s+',
                  r'\1 \2, dword ptr ', code)
    # Bare `[disp]` (no register, no seg) requires a segment override in
    # JWasm — otherwise the brackets parse as an expression, not memory.
    def add_ds(m):
        inner = m.group(1)
        # Has a register? Leave alone — defaults are fine.
        if re.search(r'\b(?:bx|si|di|bp|sp)\b', inner):
            return m.group(0)
        return f'ds:[{inner}]'
    code = re.sub(r'(?<![cdes]s:)(?<!\w)\[([^\[\]]+)\]', add_ds, code)
    # JWasm refuses to infer the size of a bracketed memory operand from
    # a code-label inside the brackets — even when the sibling operand is
    # a sized register. Splice `byte ptr` / `word ptr` in front of bare
    # brackets when the sibling operand fixes the size.
    head = re.match(r'^(\s*\S+\s+)(.*)$', code)
    if head:
        operands_part = head.group(2)
        operands = [o.strip() for o in operands_part.split(',')]
        if len(operands) >= 2:
            size = _operand_size(operands)
            if size:
                def add_size(m):
                    preceding = m.string[max(0, m.start() - 12):m.start()]
                    if re.search(r'\b(byte|word|dword)\s+ptr\s*$', preceding):
                        return m.group(0)
                    return f'{size} ptr {m.group(0)}'
                code = re.sub(r'(?:[cdes]s:)?\[[^\[\]]+\]', add_size, code)
    # LDS / LES: source is a 32-bit far pointer; force `dword ptr` over
    # whatever sibling-size inference produced above.
    code = re.sub(r'\b(lds|les)(\s+[a-z]+,\s*)(?:byte|word)\s+ptr\s+',
                  r'\1\2dword ptr ', code)
    return code


def rewrite_syntax(lines):
    """Translate every code line from NASM-style to JWasm-acceptable
    syntax. Leaves the `;#…` byte-marker comment alone."""
    out = []
    for line in lines:
        if ';#' in line:
            code, _, rest = line.partition(';#')
            out.append(_translate_syntax(code) + ';#' + rest)
        else:
            out.append(_translate_syntax(line))
    return out


def rewrite_canonicalised(lines):
    """For each line whose byte marker shows a non-canonical encoding
    JWasm would reshape on re-emit, replace the line with raw `db` bytes
    to preserve the ROM exactly."""
    out = []
    for line in lines:
        bs = _extract_marker_bytes(line)
        if bs and would_canonicalise(bs):
            db = line_to_db(line)
            if db:
                out.append(db)
                continue
        out.append(line)
    return out


def collect_addresses_and_targets(lines):
    """Walk every line; return (code_addrs, jump_targets).

    `code_addrs` is the set of every offset that appears in a `;#XXXX:`
    marker (the address of an emitted instruction or db).

    `jump_targets` is the set of every numeric value that appears as the
    operand of a short/near jump or call.
    """
    code_addrs = set()
    jump_targets = set()
    marker_re = re.compile(r';#([0-9A-Fa-f]{4})[: ]')
    # NOTE: trailing `(?!:)` rejects the seg portion of `jmp far seg:off`.
    target_re = re.compile(
        r'\b(?:j[a-z]+|call|jmp|loop[a-z]*|jcxz)\s+'
        r'(?:short\s+|near\s+ptr\s+|near\s+)?'
        r'(?:0)?([0-9A-Fa-f]+)h\b(?!:)'
    )
    for line in lines:
        m = marker_re.search(line)
        if m:
            code_addrs.add(int(m.group(1), 16))
        # Strip the trailing ;#... comment before scanning for jump operands
        code_part = line.split(';#')[0]
        for tm in target_re.finditer(code_part):
            jump_targets.add(int(tm.group(1), 16))
    return code_addrs, jump_targets


def rewrite_numeric_jumps(lines, valid_targets):
    """Replace `short NNh` / `near ptr NNh` operands with synthetic
    `LOC_XXXX` labels.

    For jump targets that aren't on an instruction boundary in the
    disassembly (i.e., the disassembler picked a different decoding
    than the original SISNE source), fall back to raw `db` bytes
    pulled from the trailing `;#XXXX: bytes` marker. JWasm will accept
    those at face value; we lose the symbolic jump but keep the build
    bit-perfect."""
    out = []
    jump_re = re.compile(
        r'(\b(?:j[a-z]+|call|jmp|loop[a-z]*|jcxz)\s+'
        r'(?:short\s+|near\s+ptr\s+|near\s+)?)'
        r'(?:0)?([0-9A-Fa-f]+)h\b(?!:)'
    )

    def label_sub(m):
        prefix = m.group(1)
        val = int(m.group(2), 16)
        if val in valid_targets:
            return f"{prefix}LOC_{val:04X}"
        return None  # signal "couldn't resolve"

    for line in lines:
        if ';#' not in line:
            out.append(line)
            continue
        code_part, _, rest = line.partition(';#')
        # Find jump targets, try to label them.
        unresolvable = False
        def try_sub(m):
            nonlocal unresolvable
            replacement = label_sub(m)
            if replacement is None:
                unresolvable = True
                return m.group(0)
            return replacement
        new_code = jump_re.sub(try_sub, code_part)
        if unresolvable:
            db = line_to_db(
                line, f"unresolvable jump target: {code_part.strip()}")
            if db:
                out.append(db)
                continue
        out.append(new_code + ';#' + rest)
    return out


def rewrite_invalid_prefixes(lines):
    """Detect prefix-instruction combos JWasm rejects (e.g. `lock xlatb`,
    `repne jo`, `rep mov`) and fall back to raw `db`.

    These come from the decoder interpreting a stray F0/F2/F3 in a data
    region as a prefix on the following byte. JWasm enforces that lock
    only attaches to certain memory-write ops and rep*/repe*/repne*/repz*
    only attaches to string ops. The bytes themselves are correct — they
    just shouldn't have been decoded as instructions in the first place,
    which is a separate annotation problem to fix later in the rev."""
    prefix_re = re.compile(
        r'^\s*(lock|rep|repe|repne|repz|repnz)\s+(\S+)', re.IGNORECASE)
    out = []
    for line in lines:
        m = prefix_re.match(line)
        if m:
            prefix = m.group(1).lower()
            mnem = m.group(2).lower()
            bad = False
            if prefix == 'lock':
                bad = True  # be conservative — most lock combos are bogus
            elif mnem not in STRING_OPS:
                bad = True
            if bad:
                db = line_to_db(line, f"invalid prefix combo: {prefix} {mnem}")
                if db:
                    out.append(db)
                    continue
        out.append(line)
    return out


def insert_synthetic_labels(lines, target_addrs):
    """Prepend a `LOC_XXXX:` label line before every code line whose
    `;#XXXX:` marker matches one of the wanted targets. Skips targets
    that already have a label at the same offset (those get a duplicate
    label, which JWasm tolerates)."""
    marker_re = re.compile(r';#([0-9A-Fa-f]{4})[: ]')
    out = []
    for line in lines:
        m = marker_re.search(line)
        if m:
            addr = int(m.group(1), 16)
            if addr in target_addrs:
                out.append(f"LOC_{addr:04X}:")
        out.append(line)
    return out


def rewrite_imm16_qualifiers(lines):
    """Convert `<mnem> ax, imm16 NN` and `<mnem> al, imm16 NN` into raw
    `db` of the AX-imm16 form opcode. Leaves the trailing byte-marker
    comment alone."""
    pat = re.compile(
        r'^(\s*)([a-z]+)\s+(a[xl]),\s*imm16\s+([0-9A-Fa-f]+)h(.*)$',
        re.IGNORECASE,
    )
    out = []
    for line in lines:
        m = pat.match(line)
        if not m:
            out.append(line)
            continue
        indent, mnem, reg, imm_hex, tail = m.groups()
        mnem_lc = mnem.lower()
        if mnem_lc not in AX_IMM16_OPCODES:
            out.append(line)
            continue
        op = AX_IMM16_OPCODES[mnem_lc]
        imm = int(imm_hex, 16)
        if reg.lower() == 'al':
            # 8-bit form: opcode is +1 less (the imm8 form), 2 bytes
            new = (f"{indent}db      {op-1:#04X}h, "
                   f"{imm & 0xFF:#04X}h{tail}")
        else:
            # 16-bit form: 3 bytes
            new = (f"{indent}db      {op:#04X}h, "
                   f"{imm & 0xFF:#04X}h, "
                   f"{(imm >> 8) & 0xFF:#04X}h{tail}")
        out.append(new)
    return out


# The .asm may spell a target's accented letters in Unicode — `"n\u00e3o"` is
# far easier to read than `"n", 84h, "o"`.  JWasm has no idea what a code page
# is, so the letters are turned back into their bytes here, on the way out.
# Keep in step with CODEPAGES in annotate.py.
CODEPAGE_BYTES = {
    "\u00c7": 0x80, "\u00e9": 0x82, "\u00e2": 0x83, "\u00e3": 0x84,
    "\u00e7": 0x87, "\u00c3": 0x8E, "\u00c9": 0x90, "\u00e1": 0xA0,
    "\u00ed": 0xA1, "\u00f3": 0xA2, "\u00fa": 0xA3,
    "\u00ab": 0xAE, "\u00bb": 0xAF,
    # The sign-on screen's line-drawing and block cells.
    "\u2502": 0xB3, "\u2524": 0xB4, "\u2510": 0xBF, "\u2514": 0xC0,
    "\u2534": 0xC1, "\u252c": 0xC2, "\u251c": 0xC3, "\u2500": 0xC4,
    "\u253c": 0xC5, "\u2518": 0xD9, "\u250c": 0xDA, "\u2588": 0xDB,
}


def encode_codepage(lines):
    """Rewrite `db "n\u00e3o"` as `db "n", 84h, "o"`.

    Only string literals are touched, and only characters the map knows; a
    stray non-ASCII byte anywhere else is left alone so it surfaces as an
    assembler error rather than being silently mangled.
    """
    def fix_literal(m):
        body = m.group(1)
        if all(ch in CODEPAGE_BYTES or ord(ch) < 0x80 for ch in body) and \
                any(ch in CODEPAGE_BYTES for ch in body):
            parts, run = [], ""
            for ch in body:
                if ch in CODEPAGE_BYTES:
                    if run:
                        parts.append('"%s"' % run); run = ""
                    parts.append("0%02Xh" % CODEPAGE_BYTES[ch])
                else:
                    run += ch
            if run:
                parts.append('"%s"' % run)
            return ", ".join(parts)
        return m.group(0)

    out = []
    for line in lines:
        if any(ch in CODEPAGE_BYTES for ch in line):
            line = re.sub(r'"([^"]*)"', fix_literal, line)
        out.append(line)
    return out


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.asm> <output.asm>", file=sys.stderr)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    with open(src) as f:
        text = f.read()
    lines = text.split('\n')

    # 0) Expand [compiled] C blocks into db bytes via tiny_cc (before any
    #    other pass, so downstream sees ordinary data lines + byte markers).
    lines = expand_compiled(lines)

    # 1) NASM-style syntax → JWasm/MASM (size ptr, ds:, near ptr, dup,
    #    int 3, repe cmps, etc.). Pure textual translation.
    lines = rewrite_syntax(lines)

    # 1b) Accented letters in string literals → their code-page bytes.
    lines = encode_codepage(lines)

    # 1a) imm16 qualifier (FASM-only leftover) → db
    lines = rewrite_imm16_qualifiers(lines)

    # 1b) Bogus prefix-instruction combos → db
    lines = rewrite_invalid_prefixes(lines)

    # 1c) Bytes that JWasm would re-encode differently → db, so the
    #     ROM survives unchanged through the assemble step.
    lines = rewrite_canonicalised(lines)

    # 2) Collect jump targets and code addresses
    code_addrs, jump_targets = collect_addresses_and_targets(lines)
    # Only synthesise labels for targets that actually correspond to an
    # emitted code address; foreign targets stay numeric (and will fail
    # JWasm — but those are bugs in the rev to fix).
    targets_with_code = jump_targets & code_addrs

    # 3) Insert LOC_XXXX labels
    lines = insert_synthetic_labels(lines, targets_with_code)

    # 4) Rewrite jump operands to use LOC_XXXX
    lines = rewrite_numeric_jumps(lines, targets_with_code)

    with open(dst, 'w') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    main()
