#!/usr/bin/env python3
"""
tiny_cc.py — a minimal 16-bit C compiler that produces byte-exact MS C 3.x
(no-optimizer) codegen for the small leaf functions we reconstruct.

It is a pure compiler: it carries no project-specific symbol table. Symbol
addresses come from the C itself via `__addr__(N)` on a declaration (and an
optional {name: address} map passed to compile_src by the build); a symbol's
signedness comes from its C type (`unsigned`). It implements only the C
constructs and x86 encodings the targets actually need.

Usage:
  python3 tiny_cc.py FILE.c              # hex dump of each compiled function
  python3 tiny_cc.py FILE.c --rom ROM    # also diff each function vs ROM bytes

Subset of C handled:
  - `int` / `unsigned [int]` / `unsigned char` locals; `void` return type
  - `extern int X; extern unsigned char X[N]; extern void f(int);`
  - assignment `=`, postinc `var++`; `arr[reg++] = expr`, `arr[reg] = imm`
  - `while (cond)`  AND  `while (1)` (constant-true → infinite loop)
  - assignment in a condition: `while ((ch = f()) != X)` — the read byte is
    kept live in AL into the loop top; a label on a `while` names its test
  - `do { } while (cond)`,  `break` / `continue`  (incl. `if (cond) break;`)
  - `for (init; cond; upd)`  and  `goto` / labels
  - `switch` over single-call cases (MSC sub-dispatch, shared cleanup)
  - `long` (32-bit) move-only: DX:AX return ABI, long/far locals/params/
    globals copied as word pairs, high word via `x >> 16`, byte globals, `&global`
  - `long` arithmetic in DX:AX: `(long)int` zero-extend, `+ uint` (add/adc),
    `<<` via the MSC shift helper (DX:AX<<CL; address pinned by `__lshl`),
    `x - 1/2`→dec
  - far-pointer structs: nested far-deref `*(T far* far*)(p+d)` (chained les),
    far word store/test-imm, far_var globals incl. FP_OFF/SEG and AX:DX reuse,
    binary `&`, far-returning call as an argument
  - branch relaxation: jmp/jcc widen to near (jcc → inverted-short + near-jmp)
    when out of rel8 range, iterated to a fixed point (MSC's short/near choice)
  - `if (cond)`     AND  `if (cond) else`
  - `return EXPR;`  AND  `return;`
  - operators: `*  +  -  <  >  ||` and `[]` index, `()` call
  - decimal / hex / char literals
  - special case `if (cond) return;` → JCC straight to the shared epilogue

Codegen rules (matched to MS C 3.x no-optimizer output):
  - Locals: each padded to 2 bytes, allocated in declaration order with
    the first-declared closest to BP (smallest offset)
  - `while`: if cond is constant-true → labelled top + JMP-back tail (no
    initial JMP); otherwise initial JMP forward to a test at the bottom
    and a JCC-back to the top
  - `if-else`: ELSE block first, then JMP done, then THEN block, then done
    (so the OR's `||` arms naturally JCC down to the THEN block)
  - `if` (no else): cond_jump(false-branch → done); THEN block; done
  - `if (cond) return;`: cond_jump(true-branch → func_ret_lbl) — no inline
    epilogue
  - Shared function epilogue at func_ret_lbl emitted once at end of func;
    `return EXPR;` at the function's natural end just leaves AX set and
    falls through into it
  - AL/AX register cache: tracks which named local is currently in AL/AX,
    invalidated at every label (any JCC target) so the codegen falls back
    to mem-form `cmp byte [bp-N], imm8` at label-entries
"""

import re
import sys

# Per-compile symbol table {name: (kind, addr)}, populated by compile_src()
# from the C declarations (`__addr__(N)` + kinds) and any supplied address
# map.  tiny_cc carries no project-specific symbols of its own.
SYMS = {}
PASCAL = set()        # names of callee-cleaned (pascal) functions
UCHAR_FUNCS = set()   # names of functions whose return is `unsigned char` (AL)

KW = {'int','unsigned','char','long','void','return','while','if','else','extern',
      'for','register','goto','far','do','break','continue',
      'switch','case','default','pascal'}


# --------- Lexer ---------

def lex(src):
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    src = re.sub(r'//[^\n]*', ' ', src)
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
        elif c.isalpha() or c == '_':
            j = i
            while j < n and (src[j].isalnum() or src[j] == '_'):
                j += 1
            w = src[i:j]
            out.append(('kw' if w in KW else 'id', w)); i = j
        elif c.isdigit():
            if c == '0' and i + 1 < n and src[i + 1] in 'xX':
                j = i + 2
                while j < n and src[j] in '0123456789abcdefABCDEF':
                    j += 1
                out.append(('num', int(src[i:j], 16))); i = j
            else:
                j = i
                while j < n and src[j].isdigit():
                    j += 1
                out.append(('num', int(src[i:j]))); i = j
        elif c == "'":
            if src[i + 1] == '\\':
                m = {'n':10,'t':9,'r':13,'0':0,'\\':92,"'":39}
                out.append(('num', m[src[i + 2]])); i += 4
            else:
                out.append(('num', ord(src[i + 1]))); i += 3
        elif src[i:i + 3] in ('>>=', '<<='):
            out.append(('op', src[i:i + 3])); i += 3
        elif src[i:i + 2] in ('<=','>=','==','!=','||','&&','++','--','|=','&=',
                              '+=','-=','<<','>>'):
            out.append(('op', src[i:i + 2])); i += 2
        else:
            out.append(('op', c)); i += 1
    out.append(('end', None))
    return out


# --------- Parser ---------

class Parser:
    def __init__(self, toks): self.t, self.p = toks, 0
    def pk(self, o=0): return self.t[self.p + o]
    def eat(self):
        r = self.t[self.p]; self.p += 1; return r
    def acc(self, k, v=None):
        t = self.pk()
        if t[0] == k and (v is None or t[1] == v):
            return self.eat()
        return None
    def exp(self, k, v=None):
        r = self.acc(k, v)
        if not r:
            raise SyntaxError(f'expected {k}/{v}, got {self.pk()}')
        return r


def parse_type(p):
    t = p.eat()[1]
    if t == 'unsigned':
        if p.acc('kw', 'char'):
            base = 'uchar'
        elif p.acc('kw', 'long'):
            base = 'ulong'              # `unsigned long` → 32-bit, unsigned compares
        else:
            p.acc('kw', 'int')          # `unsigned` or `unsigned int`
            base = 'uint'
    else:
        base = t
    # `far`/`*` chain — each `*` makes a pointer, `far` before it a far pointer
    # (so `T far * far *` is a far pointer to a far pointer).
    pending_far = False
    while True:
        if p.acc('kw', 'far'):
            pending_far = True
        elif p.acc('op', '*'):
            base = ('ptr_far_' if pending_far else 'ptr_') + base
            pending_far = False
        else:
            break
    return base


def decl_kind(ty, is_func, is_arr):
    """Derive a SYMS kind from a C declaration's type string + shape.

    ty is the parse_type() result (e.g. 'int', 'ptr_far_uchar', 'ptr_uchar').
    """
    if is_func:
        return 'far_func' if 'far' in ty else 'func'
    if is_arr:
        # 2-byte elements (pointer or int) → arr_w; byte elements → arr.
        return 'arr_w' if (ty.startswith('ptr') or ty in ('int', 'uint')) else 'arr'
    if 'far' in ty and ty.startswith('ptr'):
        return 'far_var'
    if ty == 'long':
        return 'long_var'      # 32-bit scalar (low word at addr, high at +2)
    if ty == 'ulong':
        return 'ulong_var'     # 32-bit scalar, unsigned compares
    if ty in ('uchar', 'char'):
        return 'bvar'          # byte scalar global
    if ty == 'uint':
        return 'uvar'          # unsigned scalar → unsigned compares
    return 'var'


def parse_addr_suffix(p):
    """Optional `__addr__(N)` after a declarator — pins the symbol's address
    in the C itself (used for memory-mapped globals not in the symbol map).
    Returns the int address or None."""
    if p.pk() == ('id', '__addr__'):
        p.eat()
        p.exp('op', '(')
        addr = p.eat()[1]
        p.exp('op', ')')
        return addr
    return None


def parse_extern(p):
    ty = parse_type(p)
    is_pascal = bool(p.acc('kw', 'pascal'))   # callee-cleaned (ret N) helper
    name = p.exp('id')[1]
    if p.acc('op', '('):
        while not p.acc('op', ')'):
            p.eat()
        kind = decl_kind(ty, True, False)
    elif p.acc('op', '['):
        while not p.acc('op', ']'):
            p.eat()
        kind = decl_kind(ty, False, True)
    else:
        kind = decl_kind(ty, False, False)
    addr = parse_addr_suffix(p)
    p.exp('op', ';')
    return ('extern', name, kind, addr, is_pascal, ty == 'uchar')


def parse_function(p):
    ret_ty = parse_type(p)
    name = p.exp('id')[1]
    p.exp('op', '(')
    args = []
    while not p.acc('op', ')'):
        if p.pk() == ('kw', 'void'):
            p.eat()
            continue
        ty = parse_type(p)
        if p.pk()[0] == 'id':
            aname = p.eat()[1]
            args.append((ty, aname))
        p.acc('op', ',')
    addr = parse_addr_suffix(p)             # optional `__addr__(N)` on the def
    body = parse_block(p)
    far_ret = 'far' in ret_ty
    return ('func', name, args, body, addr, far_ret)


def parse_block(p):
    p.exp('op', '{')
    out = []
    while not p.acc('op', '}'):
        out.append(parse_stmt(p))
    return out


def parse_while(p, test_label=None):
    p.exp('op', '(')
    c = parse_expr(p)
    p.exp('op', ')')
    b = parse_block_or_stmt(p)
    return ('while', c, b, test_label)


def parse_stmt(p):
    t = p.pk()
    # IDENT : (label declaration) — peek 2 tokens ahead
    if t[0] == 'id' and p.pk(1) == ('op', ':'):
        name = p.eat()[1]
        p.eat()    # consume the colon
        # A label directly on a `while` names the loop's CONDITION test (the
        # loop is entered there), so `goto name` re-runs the test.
        if p.acc('kw', 'while'):
            return parse_while(p, test_label=name)
        return ('label', name)
    if p.acc('kw', 'goto'):
        name = p.exp('id')[1]
        p.exp('op', ';')
        return ('goto', name)
    if p.acc('kw', 'continue'):
        p.exp('op', ';')
        return ('continue',)
    if t[0] == 'kw' and t[1] in ('int','unsigned','char','long'):
        ty = parse_type(p)
        name = p.exp('id')[1]
        p.exp('op', ';')
        return ('local', ty, name)
    if p.acc('kw', 'register'):
        ty = parse_type(p)
        name = p.exp('id')[1]
        p.exp('op', ';')
        return ('local', 'reg_' + ty, name)
    if p.acc('kw', 'return'):
        e = parse_expr(p) if p.pk()[1] != ';' else None
        p.exp('op', ';')
        return ('return', e)
    if p.acc('kw', 'while'):
        return parse_while(p)
    if p.acc('kw', 'do'):
        body = parse_block_or_stmt(p)
        p.exp('kw', 'while')
        p.exp('op', '(')
        c = parse_expr(p)
        p.exp('op', ')')
        p.exp('op', ';')
        return ('do', c, body)
    if p.acc('kw', 'break'):
        p.exp('op', ';')
        return ('break',)
    if p.acc('kw', 'for'):
        p.exp('op', '(')
        init = parse_expr(p) if p.pk()[1] != ';' else None
        p.exp('op', ';')
        cond = parse_expr(p) if p.pk()[1] != ';' else None
        p.exp('op', ';')
        upd  = parse_expr(p) if p.pk()[1] != ')' else None
        p.exp('op', ')')
        body = parse_block_or_stmt(p)
        return ('for', init, cond, upd, body)
    if p.acc('kw', 'switch'):
        p.exp('op', '(')
        e = parse_expr(p)
        p.exp('op', ')')
        p.exp('op', '{')
        cases = []
        default = None
        while not p.acc('op', '}'):
            if p.acc('kw', 'case'):
                k = parse_expr(p)
                p.exp('op', ':')
                cases.append((k, _parse_case_body(p)))
            elif p.acc('kw', 'default'):
                p.exp('op', ':')
                default = _parse_case_body(p)
            else:
                raise SyntaxError('expected case/default in switch')
        return ('switch', e, cases, default)
    if p.acc('kw', 'if'):
        p.exp('op', '(')
        c = parse_expr(p)
        p.exp('op', ')')
        th = parse_block_or_stmt(p)
        el = parse_block_or_stmt(p) if p.acc('kw', 'else') else None
        return ('if', c, th, el)
    if t[1] == '{':
        return ('block', parse_block(p))
    e = parse_expr(p)
    p.exp('op', ';')
    return ('expr', e)


def _parse_case_body(p):
    """Statements of one switch case, up to the next case/default/`}`."""
    body = []
    while p.pk() not in (('kw', 'case'), ('kw', 'default'), ('op', '}')):
        body.append(parse_stmt(p))
    return body


def parse_block_or_stmt(p):
    return parse_block(p) if p.pk()[1] == '{' else [parse_stmt(p)]


def parse_expr(p):     return parse_assign(p)
def parse_assign(p):
    l = parse_or(p)
    if p.acc('op', '='):
        return ('assign', l, parse_assign(p))
    for opc in ('|=', '&=', '+=', '-=', '>>=', '<<='):
        if p.acc('op', opc):
            return ('opassign', opc[:-1], l, parse_assign(p))
    return l

def parse_or(p):
    l = parse_and(p)
    while p.acc('op', '||'):
        l = ('or', l, parse_and(p))
    return l

def parse_and(p):
    l = parse_band(p)
    while p.acc('op', '&&'):
        l = ('and', l, parse_band(p))
    return l

def parse_band(p):
    l = parse_cmp(p)
    while p.pk() == ('op', '&'):
        p.eat()
        l = ('bin', '&', l, parse_cmp(p))
    return l

def parse_cmp(p):
    l = parse_shift(p)
    while p.pk()[0] == 'op' and p.pk()[1] in ('<','>','<=','>=','==','!='):
        op = p.eat()[1]
        l = ('cmp', op, l, parse_shift(p))
    return l

def parse_shift(p):
    l = parse_add(p)
    while p.pk()[0] == 'op' and p.pk()[1] in ('<<','>>'):
        op = p.eat()[1]
        l = ('bin', op, l, parse_add(p))
    return l

def parse_add(p):
    l = parse_mul(p)
    while p.pk()[0] == 'op' and p.pk()[1] in ('+','-'):
        op = p.eat()[1]
        l = ('bin', op, l, parse_mul(p))
    return l

def parse_mul(p):
    l = parse_unary(p)
    while p.pk()[0] == 'op' and p.pk()[1] in ('*','/','%'):
        op = p.eat()[1]
        l = ('bin', op, l, parse_unary(p))
    return l

def parse_unary(p):
    if p.acc('op', '&'):
        return ('addr', parse_unary(p))
    if p.acc('op', '*'):
        return ('deref', parse_unary(p))
    if p.acc('op', '-'):
        e = parse_unary(p)
        if e[0] == 'num':
            return ('num', (-e[1]) & 0xFFFF)
        return ('neg', e)
    return parse_post(p)

def parse_post(p):
    n = parse_primary(p)
    while True:
        if p.acc('op', '['):
            i = parse_expr(p)
            p.exp('op', ']')
            n = ('idx', n, i)
        elif p.acc('op', '('):
            args = []
            while not p.acc('op', ')'):
                args.append(parse_expr(p))
                p.acc('op', ',')
            n = ('call', n, args)
        elif p.acc('op', '++'):
            n = ('postinc', n)
        elif p.acc('op', '--'):
            n = ('postdec', n)
        else:
            break
    return n

def parse_primary(p):
    t = p.eat()
    if t[0] == 'num': return ('num', t[1])
    if t[0] == 'id':
        # FP_SEG(p) / FP_OFF(p): the segment / offset word of a far pointer.
        if t[1] in ('FP_SEG', 'FP_OFF') and p.pk() == ('op', '('):
            p.eat()
            inner = parse_expr(p)
            p.exp('op', ')')
            return ('fpseg' if t[1] == 'FP_SEG' else 'fpoff', inner)
        return ('id', t[1])
    if t[1] == '(':
        # Could be a cast `(type) expr` or a parenthesized expr.
        if p.pk()[0] == 'kw' and p.pk()[1] in ('int','unsigned','char','long','void'):
            cast_ty = parse_type(p)
            p.exp('op', ')')
            return ('cast', cast_ty, parse_unary(p))
        e = parse_expr(p)
        p.exp('op', ')')
        return e
    raise SyntaxError(f'unexpected {t}')


def parse(toks):
    p = Parser(toks)
    out = []
    while p.pk()[0] != 'end':
        if p.acc('kw', 'extern'):
            out.append(parse_extern(p))
        else:
            out.append(parse_function(p))
    return out


# --------- Code generator ---------

class CG:
    def __init__(self, base, unsigned=None):
        self.base   = base
        self.unsigned = unsigned or set()  # names that compare unsigned
        self.buf    = bytearray()
        self.locals = {}                  # name -> (positive offset from bp, type)
        self.regvars = {}                 # name -> 'si'  (register-allocated locals)
        self.local_size  = 0
        self._force_regvar_ax = False     # if-else routes reg-var assigns via AX
        self._force_var_ax = False        # if-else routes word-global assigns via AX
        self.labels      = {}             # label -> buf offset
        self.fixups      = []             # (buf_offset, label, kind)
        self.counter     = 0
        # Live caches: which named local sits in which register.
        self.al = None
        self.ax = None
        self.bx = None
        self.di = None
        self.cl = None                    # shift count still live in CL (an int amount)
        self.dx = None                    # ('hi', name) high word, or ('val16', name)
        self.axdx_var = None              # name whose full 4-byte value is in AX:DX
        self.cxbx_var = None              # name whose full 4-byte value is in CX:BX
        self.esbx = None                  # far_var whose data ES:BX currently points at
        self.uses_di = False
        self.uses_si = False
        self.func_ret_lbl = None
        self.break_lbls = []              # stack of enclosing-loop break targets
        self.continue_lbls = []           # stack of enclosing-loop continue targets
        # Atoms — one tagged record per machine instruction emitted, so the
        # common-tail merge pass can compare branches semantically.
        # Each atom is a tuple (kind, head_bytes, ref) where:
        #   kind in 'raw', 'jmp_short', 'jcc', 'call'
        #   head_bytes = opcode bytes BEFORE any relocation byte
        #   ref = None / label_name (for jmp_short / jcc) / target_addr (for call)
        self.atoms = []

    def is_reg_var(self, name):
        return name in self.regvars

    def ensure_bx(self, name):
        """Make sure BX holds the value of pointer-local `name`."""
        if self.bx == name:
            return
        if self.di == name:
            self.emit(0x8B, 0xDF)                     # mov bx, di
            self.bx = name
            return
        disp, _ = self.lvar(name)
        self.emit(0x8B, 0x5E, disp)                   # mov bx, [bp-N]
        self.bx = name

    def far_lvalue(self, node):
        """Recognize a far-pointer lvalue and return (base, disp, kind).

        kind is 'byte' or 'word'; `base` is the far-pointer holder (a `far_var`
        global or a far-pointer local/param).  Forms handled:
          BASE[disp]                          → byte at disp
          *(T far *)(BASE + disp)             → sizeof(T) at disp
          *(T far *)BASE                       → sizeof(T) at 0
        Returns None otherwise.
        """
        def is_far(n):
            if n[0] != 'id':
                return False
            nm = n[1]
            if nm in SYMS and SYMS[nm][0] == 'far_var':
                return True
            return (nm in self.locals
                    and self.locals[nm][1].startswith('ptr_far'))

        def far_base(n):
            """`n` evaluates to a far pointer — return a base descriptor for
            emit_les (a name, or `('chain', inner, disp)` for a far-ptr field
            `*(T far * far *)(inner + disp)`), else None."""
            if is_far(n):
                return n[1]
            if (n[0] == 'deref' and n[1][0] == 'cast'
                    and n[1][1].startswith('ptr_far_ptr')):
                op = n[1][2]
                if op[0] == 'bin' and op[1] == '+' and op[3][0] == 'num':
                    ib = far_base(op[2])
                    if ib is not None:
                        return ('chain', ib, op[3][1])
                ib = far_base(op)
                if ib is not None:
                    return ('chain', ib, 0)
            return None

        if node[0] == 'idx' and node[2][0] == 'num':
            b = far_base(node[1])
            if b is not None:
                return (b, node[2][1], 'byte')
        if node[0] == 'deref':
            # *p where p is a far-pointer local/param → element at offset 0
            if is_far(node[1]):
                ty = self.locals[node[1][1]][1] if node[1][1] in self.locals \
                    else SYMS[node[1][1]][0]
                return (node[1][1], 0, 'word' if 'int' in ty else 'byte')
            # *(T far *)(base [+ disp]) — but not a far-ptr-to-far-ptr (a base)
            if (node[1][0] == 'cast' and node[1][1].startswith('ptr')
                    and 'far' in node[1][1]
                    and not node[1][1].startswith('ptr_far_ptr')):
                cast_ty, operand = node[1][1], node[1][2]
                kind = ('long' if 'long' in cast_ty
                        else 'word' if 'int' in cast_ty else 'byte')
                if operand[0] == 'bin' and operand[1] == '+' \
                        and operand[3][0] == 'num':
                    b = far_base(operand[2])
                    if b is not None:
                        return (b, operand[3][1], kind)
                b = far_base(operand)
                if b is not None:
                    return (b, 0, kind)
        return None

    def near_lvalue(self, node):
        """Recognize a near-pointer deref lvalue `*(T *)(base [+ disp])` where
        `base` is a near pointer local/param (`ptr_*`, not `ptr_far_*`).
        Returns (base_name, byte_disp, kind) with kind 'long' (4 bytes) or
        'word' (2 bytes); None otherwise."""
        if node[0] != 'deref' or node[1][0] != 'cast':
            return None
        cty = node[1][1]
        if cty == 'ptr_long':
            kind = 'long'
        elif cty in ('ptr_uint', 'ptr_int'):
            kind = 'word'
        else:
            return None
        operand, disp = node[1][2], 0
        if operand[0] == 'bin' and operand[1] == '+' and operand[3][0] == 'num':
            disp, operand = operand[3][1], operand[2]
        if (operand[0] == 'id' and operand[1] in self.locals
                and self.locals[operand[1]][1].startswith('ptr_')
                and not self.locals[operand[1]][1].startswith('ptr_far')):
            return (operand[1], disp, kind)
        return None

    def far_indexed_reg(self, node):
        """Recognize `far_var[reg_var]` — a far-pointer global indexed by a
        register variable (SI/DI).  Returns (far_var_name, 'si'|'di') or None.
        The element is addressed `[es:bx+si/di]` after `les bx,[addr]`."""
        if (node[0] == 'idx'
                and node[1][0] == 'id' and node[1][1] in SYMS
                and SYMS[node[1][1]][0] == 'far_var'
                and node[2][0] == 'id' and node[2][1] in self.locals
                and self.is_reg_var(node[2][1])):
            return (node[1][1], self.regvars[node[2][1]])
        return None

    def _push_bx_word(self, disp):
        """push word [bx+disp] (disp 0 uses the no-displacement encoding)."""
        if disp:
            self.emit(0xFF, 0x77, disp & 0xFF)
        else:
            self.emit(0xFF, 0x37)

    def emit_les(self, base):
        """Ensure ES:BX points at `base`'s data.  A far-pointer local loads
        with `les bx, [bp+disp]`; a far_var global with `les bx, [addr]`; a
        `('chain', inner, disp)` is a far-pointer field — load `inner`, then
        `les bx, [es:bx+disp]`."""
        if self.esbx == base and self.bx == base:
            return
        # ES still points at `base` but BX was clobbered → reload only BX, keep ES
        # (matches MSC reusing a live segment register: `mov bx,[bp+disp]`).
        if (self.esbx == base and not isinstance(base, tuple)
                and base in self.locals):
            disp, _ = self.lvar(base)
            self.emit(0x8B, 0x5E, disp)                          # mov bx, [bp+disp]
            self.bx = base
            self.cxbx_var = None
            return
        if isinstance(base, tuple) and base[0] == 'chain':
            self.emit_les(base[1])
            self.emit(0x26, 0xC4, 0x5F, base[2] & 0xFF)         # les bx,[es:bx+disp]
            self.esbx = base
            self.bx = None
            return
        if base in self.locals:
            disp, _ = self.lvar(base)
            self.emit(0xC4, 0x5E, disp)                          # les bx, [bp+disp]
        else:
            addr = SYMS[base][1]
            self.emit(0xC4, 0x1E, addr & 0xFF, (addr >> 8) & 0xFF)  # les bx, [addr]
        self.esbx = self.bx = base
        self.cxbx_var = None

    def invalidate_mem(self, name):
        """A store to local `name` invalidates any reg cached against it."""
        if self.al == name: self.al = None
        if self.ax == name: self.ax = None
        if self.bx == name: self.bx = None
        if self.di == name: self.di = None
        if self.dx in (('hi', name), ('val16', name)): self.dx = None
        if self.axdx_var == name: self.axdx_var = None
        if self.cxbx_var == name: self.cxbx_var = None

    def emit(self, *bs):
        """Emit one non-relocating machine instruction."""
        self.atoms.append(('raw', tuple(bs), None))
        self.buf.extend(bs)

    def emit_jmp_short(self, label):
        """Emit `jmp short LABEL` (2 bytes) as one atom."""
        self.atoms.append(('jmp_short', (0xEB,), label))
        self.buf.append(0xEB)
        self.fixups.append((len(self.buf), label, 'rel8'))
        self.buf.append(0)

    def emit_jcc(self, opcode, label):
        """Emit `Jcc rel8` (2 bytes) as one atom."""
        self.atoms.append(('jcc', (opcode,), label))
        self.buf.append(opcode)
        self.fixups.append((len(self.buf), label, 'rel8'))
        self.buf.append(0)

    def emit_call(self, target_addr):
        """Emit `call near ADDR` (3 bytes) as one atom; bake the disp now."""
        self.made_call = True
        self.cl = None                    # a callee may clobber CL
        self.atoms.append(('call', (0xE8,), target_addr))
        call_at = len(self.buf)
        self.buf.append(0xE8)
        self.buf.extend([0, 0])
        d = target_addr - (self.base + call_at + 3)
        self.buf[call_at + 1] = d & 0xFF
        self.buf[call_at + 2] = (d >> 8) & 0xFF

    @staticmethod
    def atom_len(atom):
        kind, head, _ = atom
        if kind == 'raw': return len(head)
        if kind in ('jmp_short', 'jcc'): return len(head) + 1
        if kind == 'call': return len(head) + 2
        raise ValueError(kind)

    # ---- snapshot / extract -----------------------------------------------
    def snapshot(self):
        """Capture full CG state so we can restore after an exploratory emit."""
        return (len(self.buf), len(self.fixups), len(self.atoms),
                self.al, self.ax, self.bx, self.di, self.esbx, dict(self.labels))

    def restore(self, snap):
        buf_n, fix_n, atom_n, al, ax, bx, di, esbx, labels = snap
        del self.buf[buf_n:]
        del self.fixups[fix_n:]
        del self.atoms[atom_n:]
        self.al, self.ax, self.bx, self.di, self.esbx = al, ax, bx, di, esbx
        self.labels = labels

    def extract(self, snap):
        """Capture everything emitted since snap; then restore state.

        Returns (bytes_, fixups_relative, atoms, new_labels).  Fixup
        offsets and label positions are relative to the start of bytes_,
        so the chunk can be replayed elsewhere.
        """
        buf_n, fix_n, atom_n, _, _, _, _, _, prev_labels = snap
        bytes_  = bytes(self.buf[buf_n:])
        fixups_ = [(off - buf_n, lbl, kind)
                   for off, lbl, kind in self.fixups[fix_n:]]
        atoms_  = list(self.atoms[atom_n:])
        # Capture labels created within this chunk so replay can restore them.
        new_labels = {n: pos - buf_n for n, pos in self.labels.items()
                      if n not in prev_labels and pos >= buf_n}
        self.restore(snap)
        return bytes_, fixups_, atoms_, new_labels

    def replay(self, bytes_, fixups_relative, atoms, new_labels=None):
        """Re-emit a captured chunk at the current buf position.

        bytes_/fixups_relative/atoms/new_labels must already be sliced to
        the chunk being emitted.  Fixup offsets and label positions are
        relative to the start of bytes_.
        """
        base = len(self.buf)
        self.buf.extend(bytes_)
        for fix_off, lbl, kind in fixups_relative:
            self.fixups.append((base + fix_off, lbl, kind))
        if new_labels:
            for name, rel_pos in new_labels.items():
                self.labels[name] = base + rel_pos
        # Walk atoms to recompute call disps at their new positions
        pos = base
        for atom in atoms:
            kind, _, ref = atom
            if kind == 'call':
                d = ref - (self.base + pos + 3)
                self.buf[pos + 1] = d & 0xFF
                self.buf[pos + 2] = (d >> 8) & 0xFF
            pos += self.atom_len(atom)
        self.atoms.extend(atoms)

    def slice_chunk(self, bytes_, fixups, atoms, labels, atom_start, atom_end):
        """Slice a captured chunk to the given atom-index range.

        Returns (sliced_bytes, sliced_fixups, sliced_atoms, sliced_labels)
        with offsets re-based so the chunk starts at byte 0.
        """
        # Compute byte boundaries from atom indices.
        lo = sum(self.atom_len(a) for a in atoms[:atom_start])
        hi = lo + sum(self.atom_len(a) for a in atoms[atom_start:atom_end])
        # A label at p == hi sits one past the slice's last byte (a forward
        # target at the block's end, e.g. a nested if's `done`). Keep it only
        # for the final slice, where it maps to the position right after the
        # replayed bytes.
        at_end = (atom_end == len(atoms))
        def in_slice(p):
            return lo <= p < hi or (at_end and p == hi)
        return (bytes_[lo:hi],
                [(off - lo, l, k) for off, l, k in fixups if lo <= off < hi],
                list(atoms[atom_start:atom_end]),
                {n: p - lo for n, p in labels.items() if in_slice(p)})

    def fresh(self, p):
        self.counter += 1
        return f'{p}_{self.counter}'

    def lbl(self, name):
        # All labels in this codegen are reachable as JCC targets, so the
        # register cache must be invalidated whenever we land on one.
        self.labels[name] = len(self.buf)
        self.al = self.ax = self.bx = self.di = self.dx = self.esbx = None
        self.axdx_var = self.cxbx_var = self.cl = None

    def fix(self, label, kind):
        self.fixups.append((len(self.buf), label, kind))
        self.buf.extend(b'\0' * {'rel8':1,'rel16':2}[kind])

    def resolve(self):
        """Rebuild the buffer from the atom list with branch relaxation: each
        jmp/jcc starts `short` (rel8) and is widened to `near` only when its
        target is out of rel8 range — iterated to a fixed point (MSC's choice).
        A widened jcc becomes `inverted-jcc short +3 / jmp near` (e.g. a far
        `if(==X) return` → `jnz short .skip; jmp near ret`)."""
        atoms = self.atoms
        # Each label sits on an atom boundary; map it to that atom index.
        starts, p = [], 0
        for a in atoms:
            starts.append(p); p += self.atom_len(a)
        pos_idx = {sp: i for i, sp in enumerate(starts)}
        pos_idx[p] = len(atoms)
        label_idx = {n: pos_idx[bp] for n, bp in self.labels.items()}

        # Jump threading (MSC's jump-to-jump peephole): a jmp/jcc whose target
        # label is itself a lone unconditional `jmp` can target that jmp's
        # destination directly.  The intermediate jmp stays (it may still be
        # reached by fall-through), so this only rewrites displacements.
        def thread(label, seen):
            idx = label_idx.get(label)
            if (idx is not None and idx < len(atoms)
                    and atoms[idx][0] == 'jmp_short' and label not in seen):
                seen.add(label)
                return thread(atoms[idx][2], seen)
            return label
        for i, a in enumerate(atoms):
            if a[0] in ('jmp_short', 'jcc'):
                tgt = thread(a[2], set())
                if tgt != a[2]:
                    atoms[i] = (a[0], a[1], tgt)

        near = set()

        def alen(i):
            k = atoms[i][0]
            if k == 'jmp_short': return 3 if i in near else 2
            if k == 'jcc':       return 5 if i in near else 2
            return self.atom_len(atoms[i])

        while True:
            starts, p = [], 0
            for i in range(len(atoms)):
                starts.append(p); p += alen(i)
            apos = starts + [p]
            changed = False
            for i, a in enumerate(atoms):
                if a[0] in ('jmp_short', 'jcc') and i not in near:
                    d = apos[label_idx[a[2]]] - (starts[i] + 2)
                    if not -128 <= d <= 127:
                        near.add(i); changed = True
            if not changed:
                break

        starts, p = [], 0
        for i in range(len(atoms)):
            starts.append(p); p += alen(i)
        apos = starts + [p]
        self.labels = {n: apos[idx] for n, idx in label_idx.items()}
        buf = bytearray()
        for i, (kind, head, ref) in enumerate(atoms):
            if kind == 'raw':
                buf.extend(head)
            elif kind == 'call':
                buf.append(0xE8)
                d = ref - (self.base + len(buf) + 2)
                buf += bytes((d & 0xFF, (d >> 8) & 0xFF))
            elif kind == 'jmp_short':
                tgt = apos[label_idx[ref]]
                if i in near:
                    buf.append(0xE9); d = tgt - (len(buf) + 2)
                    buf += bytes((d & 0xFF, (d >> 8) & 0xFF))
                else:
                    buf.append(0xEB); buf.append((tgt - (len(buf) + 1)) & 0xFF)
            elif kind == 'jcc':
                tgt = apos[label_idx[ref]]
                if i in near:
                    buf.append(head[0] ^ 1); buf.append(0x03)   # inverted, skip jmp
                    buf.append(0xE9); d = tgt - (len(buf) + 2)
                    buf += bytes((d & 0xFF, (d >> 8) & 0xFF))
                else:
                    buf.append(head[0]); buf.append((tgt - (len(buf) + 1)) & 0xFF)
        self.buf = buf

    def lvar(self, name):
        off, ty = self.locals[name]
        return -off & 0xFF, ty

    def _regvar_direct_ok(self, rhs):
        """True if `rhs` can be computed straight into a register var (no AX)."""
        if rhs[0] == 'num':
            return True
        if self._is_rm(rhs):
            return True
        return (rhs[0] == 'bin' and rhs[1] == '-'
                and self._is_rm(rhs[2]) and self._is_rm(rhs[3]))

    def _regvar_branches_via_ax(self, then_stmts, else_stmts):
        """An if/else whose two arms each assign the SAME register var routes
        BOTH assignments through AX (so the shared `mov reg,ax` tail merges) when
        either arm's value is forced into AX (a far load, call, …).  Returns True
        to force the AX route; False to let each arm compute directly."""
        def reg_assign(stmts):
            if len(stmts) != 1 or stmts[0][0] != 'expr':
                return None
            e = stmts[0][1]
            if (e[0] == 'assign' and e[1][0] == 'id'
                    and e[1][1] in self.locals and self.is_reg_var(e[1][1])):
                return (e[1][1], e[2])
            return None
        a, b = reg_assign(then_stmts), reg_assign(else_stmts)
        if a and b and a[0] == b[0]:
            return not (self._regvar_direct_ok(a[1]) and self._regvar_direct_ok(b[1]))
        return False

    def _branches_assign_same_var(self, then_stmts, else_stmts):
        """Both arms of an if/else are a single `t = <expr>` to the SAME word
        global or int/uint local → route both through AX so the `mov [t],ax`
        store-tail merges."""
        def tgt(stmts):
            if len(stmts) != 1 or stmts[0][0] != 'expr':
                return None
            e = stmts[0][1]
            if e[0] != 'assign' or e[1][0] != 'id':
                return None
            n = e[1][1]
            if n in SYMS and SYMS[n][0] == 'var':
                return n
            if (n in self.locals and self.locals[n][1] in ('int', 'uint')
                    and not self.is_reg_var(n)):
                return n
            return None
        a, b = tgt(then_stmts), tgt(else_stmts)
        return a is not None and a == b

    def _is_rm(self, node):
        """True if node is a 16-bit r/m operand: a non-register local/param or a
        word `var` global (something `mov reg,[mem]` can address directly)."""
        return (node[0] == 'id'
                and ((node[1] in self.locals and not self.is_reg_var(node[1]))
                     or (node[1] in SYMS and SYMS[node[1]][0] == 'var')))

    def _emit_rm_op(self, opcode, reg, node):
        """Emit `<op> si/di, <node>` for a local/param ([bp+disp]) or var global
        ([addr]) memory operand."""
        rf = 6 if reg == 'si' else 7
        if node[1] in self.locals:
            disp, _ = self.lvar(node[1])
            self.emit(opcode, 0x40 | (rf << 3) | 0x06, disp & 0xFF)   # [bp+disp8]
        else:
            a = SYMS[node[1]][1]
            self.emit(opcode, (rf << 3) | 0x06, a & 0xFF, (a >> 8) & 0xFF)  # [disp16]

    # ---- entry ----
    def emit_func(self, args, body):
        self.func_ret_lbl = self.fresh('func_ret')
        self.made_call = False                # any emitted call forces `mov sp,bp`
        self.return_blocks = {}               # const value -> shared `return K` block label
        self.block_labels = {}                # if-body AST repr -> shared block label
        self.dup_blocks = self._find_dup_if_blocks(body)  # bodies worth cross-jumping
        # Function args go at [bp+4], [bp+6], ...  (positive offsets)
        # Stored in self.locals with positive offsets to distinguish from
        # locals (which get negative offsets via collect_locals below).
        arg_off = 4
        for ty, aname in args:
            self.locals[aname] = (-arg_off, ty)   # stored as negated so
            # far ptr and long are 4 bytes; everything else 2
            arg_off += 4 if (ty.startswith('ptr_far') or ty == 'long') else 2
        self.collect_locals(body)
        # Register allocation for register vars.  Without an outer loop we
        # let the first reg var live in SI, the second in DI (both
        # callee-saved).  With a loop, SI alone (matches lookup_token).
        has_loop = self._has_loop(body) or self._has_backward_goto(body)
        for i, name in enumerate(list(self.regvars)):
            if (not has_loop and i == 0 and not self._has_deref(body)
                    and not self._has_call(body)
                    and not self._has_long_op(body)):
                # A single reg var in a leaf function with no loop can live in
                # AX (no stack slot).  But a value live across a call or 32-bit
                # arithmetic (both clobber AX) must be in callee-saved SI/DI, so
                # those fall through to the SI/DI allocation below.
                self.regvars[name] = 'ax'
                # Reclaim the slot collect_locals reserved for it.
                self.local_size -= 2
                del self.locals[name]
            elif i == 0:
                self.regvars[name] = 'si'
            elif i == 1:
                self.regvars[name] = 'di'
            else:
                raise NotImplementedError('only 2 register vars supported')
        # SI is a register var, or scratch for the table base of a far_var indexed
        # by a near value (`far_var[handle]` → les si,[tbl]; [es:bx+si]).
        self.uses_si = (any(r == 'si' for r in self.regvars.values())
                        or self._has_far_var_near_index(body))
        # DI may be used as a register var OR as a scratch for pointer deref
        # (the `*key == *tok` pattern in lookup_token).
        self.uses_di = (any(r == 'di' for r in self.regvars.values())
                        or self._has_deref(body))
        self.emit(0x55)                       # push bp
        self.emit(0x8B, 0xEC)                 # mov bp, sp
        if self.local_size:
            self.emit(0x83, 0xEC, self.local_size)
        if self.uses_di: self.emit(0x57)      # push di
        if self.uses_si: self.emit(0x56)      # push si
        for i, s in enumerate(body):
            tail = (i == len(body) - 1)
            self.stmt(s, tail=tail)
        self.lbl(self.func_ret_lbl)
        if self.uses_si: self.emit(0x5E)
        if self.uses_di: self.emit(0x5F)
        # `mov sp,bp` restores the frame.  MSC omits it only for a pure
        # straight-line leaf with no frame activity at all — no locals, no saved
        # regs, no emitted call, and no control flow (no branches/loops/gotos).
        if (self.local_size or self.uses_si or self.uses_di
                or self.made_call or self._has_branch(body)):
            self.emit(0x8B, 0xE5)             # mov sp, bp
        self.emit(0x5D, 0xC3)                 # pop bp; ret
        self.resolve()

    def collect_locals(self, body):
        for s in body:
            if s[0] == 'local':
                ty, name = s[1], s[2]
                # far pointers and longs are 4 bytes; others pad to 2
                self.local_size += 4 if (ty.startswith('ptr_far')
                                         or ty == 'long') else 2
                self.locals[name] = (self.local_size, ty)
                if ty.startswith('reg_'):
                    # Slot stays reserved on the stack but the var actually
                    # lives in SI (only one register-var allowed for now).
                    self.regvars[name] = 'si'

    def _has_deref(self, node):
        # The only DI-using idiom is `*p1 == *p2` (a compare of two pointer
        # derefs, e.g. lookup_token).  A lone `*p` read or `*p = …` store uses
        # AL/BX, not DI; far derefs use ES:BX.  So only that compare counts.
        if isinstance(node, (list, tuple)):
            if (isinstance(node, tuple) and node and node[0] == 'cmp'
                    and node[2][0] == 'deref' and node[3][0] == 'deref'):
                return True
            return any(self._has_deref(c) for c in node)
        return False

    @staticmethod
    def _block_terminates(body):
        """True if the statement list always exits (no fall-through) — its last
        statement is a return/goto/break/continue."""
        return bool(body) and body[-1][0] in (
            'return', 'goto', 'break', 'continue')

    def _find_dup_if_blocks(self, body):
        """Set of repr(if-body) appearing in >= 2 terminating `if (cond){body}`
        statements — the cross-jump candidates.  Only these get a shared (cold)
        block; a unique block stays a fall-through and may use live registers."""
        counts = {}
        def walk(node):
            if isinstance(node, (list, tuple)):
                if (isinstance(node, tuple) and len(node) >= 3 and node[0] == 'if'
                        and not node[3] and self._block_terminates(node[2])):
                    k = repr(node[2])
                    counts[k] = counts.get(k, 0) + 1
                for c in node:
                    walk(c)
        walk(body)
        return {k for k, v in counts.items() if v >= 2}

    def _has_branch(self, node):
        """True if the body has any control flow (branch/loop/goto) — i.e. it is
        not a single straight-line fall-through block."""
        if isinstance(node, (list, tuple)):
            if (isinstance(node, tuple) and node and node[0] in
                    ('if', 'while', 'for', 'switch', 'goto', 'label', 'break',
                     'continue')):
                return True
            return any(self._has_branch(c) for c in node)
        return False

    def _has_long_op(self, node):
        """True if a 32-bit (long) bin/cast op appears (it clobbers AX:DX)."""
        if isinstance(node, (list, tuple)):
            if (isinstance(node, tuple) and node and node[0] in ('bin', 'cast')
                    and self._is_long_expr(node)):
                return True
            return any(self._has_long_op(c) for c in node)
        return False

    def _has_far_var_near_index(self, node):
        """True if a far-pointer access uses SI as a scratch index: a
        `far_var[near-int local]`, or a `*(T far*)(far_var + idx + k) >>= 1`."""
        if isinstance(node, (list, tuple)):
            if (isinstance(node, tuple) and node and node[0] == 'idx'
                    and node[1][0] == 'id' and node[1][1] in SYMS
                    and SYMS[node[1][1]][0] == 'far_var'
                    and node[2][0] == 'id' and node[2][1] in self.locals
                    and not self.is_reg_var(node[2][1])):
                return True
            if (isinstance(node, tuple) and node and node[0] == 'opassign'
                    and node[1] == '>>' and node[2][0] == 'deref'
                    and node[2][1][0] == 'cast'
                    and node[2][1][1].startswith('ptr_far')):
                return True
            return any(self._has_far_var_near_index(c) for c in node)
        return False

    @staticmethod
    def _has_loop(node):
        if isinstance(node, (list, tuple)):
            if isinstance(node, tuple) and node and node[0] in ('while', 'for', 'do'):
                return True
            return any(CG._has_loop(c) for c in node)
        return False

    @staticmethod
    def _lg_seq(node, out):
        if isinstance(node, (list, tuple)):
            if isinstance(node, tuple) and node and node[0] in ('label', 'goto'):
                out.append((node[0], node[1]))
            for c in node:
                CG._lg_seq(c, out)

    @staticmethod
    def _has_call(node):
        if isinstance(node, (list, tuple)):
            if isinstance(node, tuple) and node and node[0] == 'call':
                return True
            return any(CG._has_call(c) for c in node)
        return False

    def _has_backward_goto(self, body):
        """A goto whose target label was already seen (textually earlier) forms
        a loop — so register vars must live in callee-saved SI/DI, not AX."""
        seq = []
        self._lg_seq(body, seq)
        seen = set()
        for kind, name in seq:
            if kind == 'label':
                seen.add(name)
            elif kind == 'goto' and name in seen:
                return True
        return False

    def _cond_al_seed(self, cond):
        """If a loop condition is `(uchar = …) OP …`, the assigned uchar local
        ends up in AL when the condition is evaluated, so it is live in AL on
        the loop's back-edge. Return that local name (to seed the AL cache at
        the loop top), else None."""
        if cond[0] == 'cmp' and cond[2][0] == 'assign' \
                and cond[2][1][0] == 'id':
            v = cond[2][1][1]
            if v in self.locals and self.locals[v][1] == 'uchar':
                return v
        return None

    def _cond_esbx_seed(self, cond):
        """If a loop condition dereferences a far pointer (`*p OP …`), the
        condition's `les bx,[p]` leaves ES:BX pointing at *p on the back-edge,
        so seed the ES:BX cache with that base at the loop top."""
        if cond[0] == 'cmp':
            far = self.far_lvalue(cond[2])
            if far is not None:
                base = far[0]
                # Only a LOCAL far pointer keeps ES:BX live across the back-edge
                # (les [bp+disp] once); a global far_var reloads les [addr] each
                # use, so it must NOT be seeded.
                if (isinstance(base, str) and base in self.locals
                        and self.locals[base][1].startswith('ptr_far')):
                    return base
        return None

    # ---- statements ----
    def stmt(self, s, tail=False):
        op = s[0]
        if op == 'local': return
        if op == 'label':
            self.lbl('user_' + s[1])
            return
        if op == 'goto':
            self.emit_jmp_short('user_' + s[1])
            return
        if op == 'block':
            for i, ss in enumerate(s[1]):
                last = tail and (i == len(s[1]) - 1)
                self.stmt(ss, tail=last)
            return
        if op == 'expr':
            self.expr_stmt(s[1], tail=tail)
            return
        if op == 'return':
            if s[1] is not None:
                # `return f(args);` at the function end is a tail call — the
                # epilogue's `mov sp, bp` reclaims the args, so skip `add sp,N`.
                if tail and s[1][0] == 'call':
                    self.gen_call(s[1], tail=True)
                elif self._far_ptr_add_base(s[1]) is not None:
                    bn, addends = self._far_ptr_add_base(s[1])
                    self._far_ptr_add_to_axdx(bn, addends)   # far ptr → off=AX, seg=DX
                elif self._is_long4(s[1]):
                    self.load_long_axdx(s[1])    # 32-bit result in DX:AX
                elif self._is_long_expr(s[1]):
                    self.gen_long(s[1])          # 32-bit expression → DX:AX
                else:
                    self.expr_to_ax(s[1])
            if not tail:
                # mid-function return — jump to shared epilogue
                self.emit_jmp_short(self.func_ret_lbl)
            return
        if op == 'while':
            cond, body = s[1], s[2]
            test_label = s[3] if len(s) > 3 else None
            # while (1) → infinite loop, no condition test; exits via break.
            if cond[0] == 'num' and cond[1] != 0:
                loop = self.fresh('loop')
                brk = self.fresh('break')
                self.lbl(loop)
                self.break_lbls.append(brk)
                self.continue_lbls.append(loop)
                for ss in body: self.stmt(ss)
                self.break_lbls.pop()
                self.continue_lbls.pop()
                self.emit_jmp_short(loop)
                if any(l == brk for _, l, _ in self.fixups):
                    self.lbl(brk)
                return
            # MSC emits `while` as a test-at-TOP loop (no entry jump):
            #   top: if(!cond) goto exit; body; jmp top; exit:
            # The rotated (test-at-bottom, entry `jmp test`) shape belongs to
            # `for` — write a `for (; cond; )` for that. See tinycc.md.
            loop = ('user_' + test_label) if test_label else self.fresh('loop')
            exit_ = self.fresh('wexit')
            self.lbl(loop)
            self.break_lbls.append(exit_)
            self.continue_lbls.append(loop)
            self.cond_jump(cond, exit_, False)
            for ss in body: self.stmt(ss)
            self.break_lbls.pop()
            self.continue_lbls.pop()
            self.emit_jmp_short(loop)
            self.lbl(exit_)
            return
        if op == 'do':
            # do { BODY } while (COND);  — labelled top, JCC-back tail, and a
            # break label right after (the natural fall-through exit).
            cond, body = s[1], s[2]
            loop = self.fresh('loop')
            brk  = self.fresh('break')
            self.break_lbls.append(brk)
            self.lbl(loop)
            for ss in body: self.stmt(ss)
            self.cond_jump(cond, loop, True)
            self.break_lbls.pop()
            self.lbl(brk)
            return
        if op == 'break':
            self.emit_jmp_short(self.break_lbls[-1])
            return
        if op == 'continue':
            self.emit_jmp_short(self.continue_lbls[-1])
            return
        if op == 'switch':
            self.gen_switch(s[1], s[2], s[3])
            return
        if op == 'for':
            init, cond, upd, body = s[1], s[2], s[3], s[4]
            # for(drv=init; ; drv=upd) — no condition: a far-pointer carried in
            # DX:AX with the store hoisted to the loop *top* (the body's own
            # breaks/returns are the only exits).  init falls into the store;
            # upd recomputes DX:AX and jumps back to it.
            if (cond is None and init and init[0] == 'assign'
                    and init[1][0] == 'id' and init[1][1] in self.locals
                    and self.locals[init[1][1]][1].startswith('ptr_far')
                    and upd and upd[0] == 'assign' and upd[1] == init[1]):
                name = init[1][1]
                d, _ = self.lvar(name)
                top = self.fresh('loop'); brk = self.fresh('break')
                self.gen_long(init[2])               # init far value → DX:AX (no store)
                self.lbl(top)
                self.emit(0x89, 0x46, d & 0xFF)          # mov [bp+d], ax
                self.emit(0x89, 0x56, (d + 2) & 0xFF)    # mov [bp+d+2], dx
                self.ax = ('fpoff', name); self.dx = None
                self.break_lbls.append(brk); self.continue_lbls.append(top)
                for ss in body: self.stmt(ss)
                self.break_lbls.pop(); self.continue_lbls.pop()
                self.gen_long(upd[2])                # next far value → DX:AX (no store)
                self.emit_jmp_short(top)
                if any(l == brk for _, l, _ in self.fixups):
                    self.lbl(brk)
                return
            # Far-pointer loop variable carried in DX:AX with the store hoisted
            # to the (shared) loop test — MSC's driver-chain walk.  init/upd
            # compute the next far pointer into DX:AX *without* storing; the test
            # stores it, then compares the offset still live in AX.
            if (init and init[0] == 'assign' and init[1][0] == 'id'
                    and init[1][1] in self.locals
                    and self.locals[init[1][1]][1].startswith('ptr_far')
                    and upd and upd[0] == 'assign' and upd[1] == init[1]
                    and cond and cond[0] == 'cmp' and cond[2][0] == 'fpoff'
                    and cond[2][1] == init[1]):
                name = init[1][1]
                d, _ = self.lvar(name)
                loop = self.fresh('loop'); test = self.fresh('test')
                brk = self.fresh('break')
                self.gen_long(init[2])               # init far value → DX:AX (no store)
                self.emit_jmp_short(test)
                self.lbl(loop)
                self.break_lbls.append(brk); self.continue_lbls.append(test)
                for ss in body: self.stmt(ss)
                self.break_lbls.pop(); self.continue_lbls.pop()
                self.gen_long(upd[2])                # next far value → DX:AX (no store)
                self.lbl(test)
                self.emit(0x89, 0x46, d & 0xFF)          # mov [bp+d], ax
                self.emit(0x89, 0x56, (d + 2) & 0xFF)    # mov [bp+d+2], dx
                self.ax = ('fpoff', name); self.dx = None
                self.cond_jump(cond, loop, True)
                if any(l == brk for _, l, _ in self.fixups):
                    self.lbl(brk)
                return
            if init: self.expr_stmt(init)
            # MSC skips the entry jump-to-test only when the first iteration
            # provably runs (e.g. `i = 0; i < 18`); otherwise it rotates with a
            # `jmp test` entry (e.g. `i = nclus; DPB_PTR[4] >= i`).
            provable = (init and init[0] == 'assign' and init[2][0] == 'num'
                        and cond and cond[0] == 'cmp' and cond[2] == init[1]
                        and cond[3][0] == 'num'
                        and ((cond[1] == '<'  and init[2][1] <  cond[3][1])
                             or (cond[1] == '<=' and init[2][1] <= cond[3][1])
                             or (cond[1] == '!=' and init[2][1] != cond[3][1])))
            loop = self.fresh('loop')
            test = self.fresh('test')
            brk  = self.fresh('break')
            if not provable:
                self.emit_jmp_short(test)
            self.lbl(loop)
            # On the back-edge the rotated condition left a value live in a
            # register (a uchar assign in AL, a far-deref's ES:BX) — seed the
            # cache at the loop top so the body's first use doesn't reload.
            if not provable:
                seed = self._cond_al_seed(cond)
                if seed:
                    self.al = seed
                esbx_seed = self._cond_esbx_seed(cond)
                if esbx_seed:
                    self.esbx = esbx_seed
                    self.bx = esbx_seed       # BX also points there (rotated cond's les)
            self.break_lbls.append(brk)
            self.continue_lbls.append(test)
            for ss in body: self.stmt(ss)
            self.break_lbls.pop()
            self.continue_lbls.pop()
            if upd: self.expr_stmt(upd)
            if not provable:
                self.lbl(test)
            self.cond_jump(cond, loop, True)
            if any(l == brk for _, l, _ in self.fixups):
                self.lbl(brk)
            return
        if op == 'if':
            # if (cond) goto L;  — single JCC to the user label (cond true)
            if (not s[3] and len(s[2]) == 1 and s[2][0][0] == 'goto'):
                self.cond_jump(s[1], 'user_' + s[2][0][1], True)
                return
            # if (cond) break;  — single JCC to the enclosing loop's break label
            if (not s[3] and len(s[2]) == 1 and s[2][0][0] == 'break'):
                self.cond_jump(s[1], self.break_lbls[-1], True)
                return
            # if (cond) continue;  — single JCC to the loop's continue label
            if (not s[3] and len(s[2]) == 1 and s[2][0][0] == 'continue'):
                self.cond_jump(s[1], self.continue_lbls[-1], True)
                return
            simple_return = (
                not s[3] and len(s[2]) == 1
                and s[2][0][0] == 'return')
            if simple_return and s[2][0][1] is None:
                # if (cond) return;     — JCC straight to epilogue
                self.cond_jump(s[1], self.func_ret_lbl, True)
                return
            if simple_return and s[2][0][1] is not None:
                val = s[2][0][1]
                # Identical constant returns share one block (MSC cross-jumping):
                # a later `if (cond) return K` jumps straight to the first block.
                if val[0] == 'num' and val in self.return_blocks:
                    self.cond_jump(s[1], self.return_blocks[val], True)
                    return
                # if (cond) return EXPR; — skip past on false, load+jmp on true.
                # For a constant, label the load so later identical returns reuse it.
                done = self.fresh('done')
                self.cond_jump(s[1], done, False)
                if val[0] == 'num':
                    blk = self.fresh('ret')
                    self.lbl(blk)
                    self.return_blocks[val] = blk
                self.expr_to_ax(val)
                self.emit_jmp_short(self.func_ret_lbl)
                self.lbl(done)
                return
            # Block cross-jumping: `if (cond) { ...; return/goto/break }` whose whole
            # body matches an earlier such `if` shares one copy — the later one JCCs
            # straight to that block.  Only for a *terminating* body (it cannot fall
            # through, so reusing it can't change what runs after the original `if`).
            if (not s[3] and self._block_terminates(s[2])
                    and repr(s[2]) in self.dup_blocks):
                key = repr(s[2])
                if key in self.block_labels:
                    self.cond_jump(s[1], self.block_labels[key], True)
                    return
                done = self.fresh('done')
                self.cond_jump(s[1], done, False)
                blk = self.fresh('blk')
                self.lbl(blk)
                self.block_labels[key] = blk
                for ss in s[2]:
                    self.stmt(ss)
                self.lbl(done)
                return
            if s[3]:
                # MSC has a single if-else layout (Pattern A): test, JCC to
                # `else` when the condition is FALSE, then-block (fall-through),
                # jmp done, else.  An OR condition is written De Morgan (as `&&`
                # with the branches swapped), so there is no separate "OR" form.
                else_lbl = self.fresh('else')
                done     = self.fresh('done')
                self.cond_jump(s[1], else_lbl, False)
                # When both arms assign the same reg var and one is forced
                # through AX, route both via AX so the `mov reg,ax` tail merges.
                via_ax = self._regvar_branches_via_ax(s[2], s[3])
                saved_force = self._force_regvar_ax
                self._force_regvar_ax = via_ax
                saved_var_force = self._force_var_ax
                self._force_var_ax = self._branches_assign_same_var(s[2], s[3])
                merge_tgt = (s[2][0][1][1][1] if self._force_var_ax else None)
                # Capture each branch's atoms in isolation.  Propagate the outer
                # if's tail position to each branch's last statement so
                # tail-calls correctly skip `add sp, N`.
                snap = self.snapshot()
                # The then-arm jumps to `done`.  A trailing *void call* tail-skips
                # only when the else-arm also ends in a call — then both merge into
                # one shared call that falls through to the epilogue; otherwise the
                # standalone then-call keeps its `add sp,N` (returns / nested ifs
                # always propagate tail for their own tail-calls).
                else_last_call = (s[3] and s[3][-1][0] == 'expr'
                                  and s[3][-1][1][0] == 'call')
                for i, ss in enumerate(s[2]):
                    void_call = ss[0] == 'expr' and ss[1][0] == 'call'
                    t = tail and i == len(s[2]) - 1 and (not void_call or else_last_call)
                    self.stmt(ss, tail=t)
                then_chunk = self.extract(snap)
                # else_lbl is reached via the JCC, so the else branch starts
                # with cold register caches (unlike the fall-through then).
                self.al = self.ax = self.bx = self.di = self.esbx = None
                snap = self.snapshot()
                for i, ss in enumerate(s[3]):
                    self.stmt(ss, tail=tail and i == len(s[3]) - 1)
                else_chunk = self.extract(snap)
                self._force_regvar_ax = saved_force
                self._force_var_ax = saved_var_force
                then_atoms = then_chunk[2]
                else_atoms = else_chunk[2]
                # Find longest common suffix by atom equality.
                n = 0
                while (n < len(then_atoms) and n < len(else_atoms)
                       and then_atoms[-1 - n] == else_atoms[-1 - n]):
                    n += 1
                if n > 0:
                    shared = self.fresh('shared')
                    # then-unique + JMP shared
                    self.replay(*self.slice_chunk(*then_chunk,
                                                   0, len(then_atoms) - n))
                    self.emit_jmp_short(shared)
                    # else_lbl + else-unique
                    self.lbl(else_lbl)
                    self.replay(*self.slice_chunk(*else_chunk,
                                                   0, len(else_atoms) - n))
                    # shared block (taken from else's tail)
                    self.lbl(shared)
                    self.replay(*self.slice_chunk(*else_chunk,
                                                   len(else_atoms) - n,
                                                   len(else_atoms)))
                    self.lbl(done)
                    # the merged store tail (`mov [bp+d],ax`) leaves the target in
                    # AX — a local target stays live for a following `return t`.
                    if merge_tgt and merge_tgt in self.locals:
                        self.ax = merge_tgt
                else:
                    # No common suffix — emit normally.
                    self.replay(*self.slice_chunk(*then_chunk,
                                                   0, len(then_atoms)))
                    self.emit_jmp_short(done)
                    self.lbl(else_lbl)
                    self.replay(*self.slice_chunk(*else_chunk,
                                                   0, len(else_atoms)))
                    self.lbl(done)
            else:
                # if-no-else: Pattern A (jump past then if cond is false)
                done = self.fresh('done')
                self.cond_jump(s[1], done, False)
                for ss in s[2]: self.stmt(ss)
                self.lbl(done)
            return
        raise NotImplementedError(s)

    def expr_stmt(self, e, tail=False):
        if e[0] == 'assign':
            self.gen_assign(e[1], e[2])
        elif e[0] == 'call':
            self.gen_call(e, tail=tail)
        elif e[0] == 'postinc':
            self.gen_postinc(e[1])
        elif e[0] == 'postdec':
            self.gen_postdec(e[1])
        elif e[0] == 'opassign':
            self.gen_opassign(e[1], e[2], e[3])
        else:
            self.expr_to_ax(e)

    def gen_opassign(self, op, lhs, rhs):
        """Compound assign on a far lvalue, emitted as a read-modify-write:
        `|=`/`&=` with an immediate, or `+=` with a register value."""
        # local/param (or FP_OFF of a far ptr) +=/-= reg_var → add/sub [bp+disp],si/di
        if (op in ('+', '-') and rhs[0] == 'id' and rhs[1] in self.locals
                and self.is_reg_var(rhs[1])):
            tgt = None
            if lhs[0] == 'id' and lhs[1] in self.locals and not self.is_reg_var(lhs[1]):
                tgt = lhs[1]
            elif (lhs[0] == 'fpoff' and lhs[1][0] == 'id'
                  and lhs[1][1] in self.locals):
                tgt = lhs[1][1]
            if tgt is not None:
                disp, _ = self.lvar(tgt)
                rf = 6 if self.regvars[rhs[1]] == 'si' else 7
                opc = 0x01 if op == '+' else 0x29
                self.emit(opc, 0x40 | (rf << 3) | 0x06, disp & 0xFF)  # add/sub [bp+disp],si/di
                return
            # long global += reg_var → sub ax,ax; add [g],si/di; adc [g+2],ax
            if (op == '+' and lhs[0] == 'id' and lhs[1] in SYMS
                    and SYMS[lhs[1]][0] == 'long_var'):
                a = SYMS[lhs[1]][1]
                rf = 6 if self.regvars[rhs[1]] == 'si' else 7
                self.emit(0x2B, 0xC0)                                 # sub ax, ax
                self.emit(0x01, (rf << 3) | 0x06, a & 0xFF, (a >> 8) & 0xFF)    # add [g],si/di
                self.emit(0x11, 0x06, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)    # adc [g+2],ax
                self.ax = self.al = None
                return
        far = self.far_lvalue(lhs)
        # far_word += expr  →  eval expr to AX, then `add [es:bx+disp], ax`
        if far is not None and op == '+' and rhs[0] != 'num':
            base, disp, kind = far
            self.expr_to_ax(rhs)
            self.emit_les(base)
            modrm = (0x40 if disp else 0x00) | 0x07
            self.emit(0x26, 0x01, modrm, *((disp & 0xFF,) if disp else ()))  # add [es:bx+d],ax
            self.ax = self.al = None
            return
        if far is not None and rhs[0] == 'num':
            base, disp, kind = far
            self.emit_les(base)
            digit = {'|': 1, '&': 4}[op]                  # OR=/1, AND=/4
            modrm = (0x40 if disp else 0x00) | (digit << 3) | 0x07
            n = rhs[1]
            if kind == 'byte':
                self.emit(0x26, 0x80, modrm, *((disp & 0xFF,) if disp else ()),
                          n & 0xFF)
            else:
                self.emit(0x26, 0x81, modrm, *((disp & 0xFF,) if disp else ()),
                          n & 0xFF, (n >> 8) & 0xFF)
            self.ax = self.al = None
            return
        # FP_OFF(*bufp) += expr — bufp is a near ptr to a far ptr; add to the
        # offset word it points at: mov bx,[bp+disp]; add [bx], si/di/ax
        if (op == '+' and lhs[0] == 'fpoff' and lhs[1][0] == 'deref'
                and lhs[1][1][0] == 'id' and lhs[1][1][1] in self.locals
                and self.locals[lhs[1][1][1]][1].startswith('ptr_ptr_far')):
            disp, _ = self.lvar(lhs[1][1][1])
            if (rhs[0] == 'id' and rhs[1] in self.locals
                    and self.is_reg_var(rhs[1])):
                self.emit(0x8B, 0x5E, disp & 0xFF)           # mov bx, [bp+disp]
                self.emit(0x01, 0x37 if self.regvars[rhs[1]] == 'si' else 0x3F)  # add [bx], si/di
            elif self._is_rm(rhs):
                # simple memory load: load BX first, then AX
                self.emit(0x8B, 0x5E, disp & 0xFF)           # mov bx, [bp+disp]
                self.expr_to_ax(rhs)                         # mov ax, [rhs]
                self.emit(0x01, 0x07)                        # add [bx], ax
            else:
                # computed addend: evaluate to AX first, then load BX
                self.expr_to_ax(rhs)
                self.emit(0x8B, 0x5E, disp & 0xFF)           # mov bx, [bp+disp]
                self.emit(0x01, 0x07)                        # add [bx], ax
            self.bx = None
            return
        # uchar_local += far byte lvalue  →  al = far byte; add [bp+disp], al
        if (op == '+' and lhs[0] == 'id' and lhs[1] in self.locals
                and self.locals[lhs[1]][1] == 'uchar'):
            fr = self.far_lvalue(rhs)
            if fr is not None and fr[2] == 'byte':
                self.expr_to_al(rhs)                    # mov al,[es:bx+disp] (reuse es:bx)
                d, _ = self.lvar(lhs[1])
                self.emit(0x00, 0x46, d & 0xFF)         # add [bp+disp], al
                self.al = self.ax = None
                return
        # word var global += expr  →  eval to AX, then `add [addr], ax`
        if (op == '+' and lhs[0] == 'id' and lhs[1] in SYMS
                and SYMS[lhs[1]][0] == 'var'):
            addr = SYMS[lhs[1]][1]
            self.expr_to_ax(rhs)
            self.emit(0x01, 0x06, addr & 0xFF, (addr >> 8) & 0xFF)  # add [addr], ax
            self.ax = self.al = None
            return
        # var global &=/|= reg_var  →  and/or [addr], si/di
        if (op in ('&', '|') and lhs[0] == 'id' and lhs[1] in SYMS
                and SYMS[lhs[1]][0] == 'var'
                and rhs[0] == 'id' and rhs[1] in self.locals
                and self.is_reg_var(rhs[1])):
            addr = SYMS[lhs[1]][1]
            rf = 6 if self.regvars[rhs[1]] == 'si' else 7
            opc = 0x21 if op == '&' else 0x09
            self.emit(opc, (rf << 3) | 0x06, addr & 0xFF, (addr >> 8) & 0xFF)  # and/or [addr],si/di
            return
        # *(uint far*)(far_var + <index> + const) >>= 1  →  compute the index into
        # SI (scratch), les bx,[tbl], shr word [es:bx+si+const], 1
        if (op == '>>' and rhs == ('num', 1) and lhs[0] == 'deref'
                and lhs[1][0] == 'cast' and lhs[1][1].startswith('ptr_far')):
            terms = []
            def _ft(n):
                if n[0] == 'bin' and n[1] == '+':
                    _ft(n[2]); _ft(n[3])
                else:
                    terms.append(n)
            _ft(lhs[1][2])
            bases = [t for t in terms if t[0] == 'id' and t[1] in SYMS
                     and SYMS[t[1]][0] == 'far_var']
            const = sum(t[1] for t in terms if t[0] == 'num') & 0xFF
            varts = [t for t in terms if not (t[0] == 'num'
                     or (t[0] == 'id' and t[1] in SYMS and SYMS[t[1]][0] == 'far_var'))]
            if len(bases) == 1 and len(varts) == 1:
                self.expr_to_ax(varts[0])                      # ax = index (0x35*i)
                self.emit(0x8B, 0xF0)                          # mov si, ax
                self.emit_les(bases[0][1])                     # les bx, [tbl]
                self.emit(0x26, 0xD1, 0x68, const)             # shr word[es:bx+si+disp],1
                self.ax = self.al = self.esbx = self.bx = None
                return
        # local var -= far word lvalue  →  mov ax,[es:bx+d] (reuse es:bx); sub [bp+disp],ax
        if (op in ('+', '-') and lhs[0] == 'id' and lhs[1] in self.locals
                and not self.is_reg_var(lhs[1])):
            fr = self.far_lvalue(rhs)
            if fr is not None and fr[2] == 'word':
                disp, _ = self.lvar(lhs[1])
                self.expr_to_ax(rhs)                       # mov ax, [es:bx+d]
                opc = 0x01 if op == '+' else 0x29
                self.emit(opc, 0x46, disp & 0xFF)          # add/sub [bp+disp], ax
                self.ax = None
                return
        raise NotImplementedError(('opassign', op, lhs, rhs))

    # ---- assignment / call / postinc ----
    def _is_long4(self, node):
        """True if node is a 4-byte (long or far-ptr) scalar lvalue —
        a local/param (type 'long' or 'ptr_far_*') or a long_var/far_var global."""
        if node[0] != 'id':
            return False
        n = node[1]
        if n in self.locals:
            t = self.locals[n][1]
            return t == 'long' or t.startswith('ptr_far')
        return n in SYMS and SYMS[n][0] in ('long_var', 'far_var')

    def load_long_axdx(self, node):
        """Load a 4-byte lvalue into AX (low) : DX (high)."""
        n = node[1]
        # The full 4-byte value is already live in AX:DX (e.g. right after
        # `*(long far*)p = n` — the store leaves the value in place).
        if self.axdx_var is not None and self.axdx_var == n:
            return
        # A far_var whose ES:BX is still cached (e.g. after `g[..]` field reads)
        # reuses it: mov ax,bx; mov dx,es — no reload from memory.
        if (n in SYMS and SYMS[n][0] == 'far_var' and self.esbx == n):
            self.emit(0x8B, 0xC3)                          # mov ax, bx
            self.emit(0x8C, 0xC2)                          # mov dx, es
            self.ax = None
            self.dx = ('hi', n)
            self.axdx_var = n
            return
        # If AX already holds this local's low/offset word (right after
        # `local = (long)x` or `FP_OFF(p) = …`), keep it and only load DX.
        if self.ax in (('low', n), ('fpoff', n)) and n in self.locals:
            disp, _ = self.lvar(n)
            self.emit(0x8B, 0x56, (disp + 2) & 0xFF)        # mov dx, [bp+disp+2]
            self.ax = None
            self.dx = ('hi', n)
            self.axdx_var = n
            return
        # reuse DX if it already holds this value's high word (e.g. right after
        # `n = far_fn(...)`, where intervening byte ops clobbered only AX).
        keep_dx = self.dx == ('hi', n)
        if n in self.locals:
            disp, _ = self.lvar(n)
            self.emit(0x8B, 0x46, disp & 0xFF)              # mov ax, [bp+disp]
            if not keep_dx:
                self.emit(0x8B, 0x56, (disp + 2) & 0xFF)    # mov dx, [bp+disp+2]
        else:
            a = SYMS[n][1]
            self.emit(0xA1, a & 0xFF, (a >> 8) & 0xFF)                  # mov ax,[a]
            if not keep_dx:
                self.emit(0x8B, 0x16, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)  # mov dx,[a+2]
        self.ax = None
        self.dx = ('hi', n)
        self.axdx_var = n

    def store_axdx_long(self, node):
        """Store AX:DX into a 4-byte lvalue; leaves DX cached as its high word."""
        n = node[1]
        if n in self.locals:
            disp, _ = self.lvar(n)
            self.emit(0x89, 0x46, disp & 0xFF)              # mov [bp+disp], ax
            self.emit(0x89, 0x56, (disp + 2) & 0xFF)        # mov [bp+disp+2], dx
        else:
            a = SYMS[n][1]
            self.emit(0xA3, a & 0xFF, (a >> 8) & 0xFF)                  # mov [a],ax
            self.emit(0x89, 0x16, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)  # mov [a+2],dx
        self.ax = None
        self.dx = ('hi', n)
        self.axdx_var = n          # AX:DX still hold this whole 4-byte value

    def gen_long(self, node):
        """Evaluate a 32-bit (long) expression into DX:AX."""
        if node[0] == 'cast' and node[1] == 'long':
            # (long)(int expr) — zero-extend the 16-bit value
            self.expr_to_ax(node[2])
            self.emit(0x2B, 0xD2)                       # sub dx, dx
            self.ax = self.dx = None
            return
        if node[0] == 'bin' and node[1] == '<<':
            # long << n : DX:AX <<= CL, via the MSC shift helper (__lshl pins
            # its address; the register convention is value=DX:AX, count=CL).
            self.gen_long(node[2])                      # value → DX:AX
            self._load_cl(node[3])                      # count → CL
            self.emit_call(SYMS['__lshl'][1])           # clobbers AX/BX/CX/DX/ES
            self.al = self.ax = self.bx = self.dx = self.esbx = None
            self.axdx_var = self.cxbx_var = None
            return
        if node[0] == 'call':
            self.gen_call(node)                         # long-returning call → DX:AX
            return
        if node[0] == 'bin' and node[1] in ('+', '-'):
            self.gen_long(node[2])                      # accumulate in DX:AX
            self._long_add_term(node[1], node[3])
            return
        # a long lvalue whose value is still live in CX:BX (just stored there)
        if node[0] == 'id' and self.cxbx_var == node[1]:
            self.emit(0x8B, 0xC1)                       # mov ax, cx
            self.emit(0x8B, 0xD3)                       # mov dx, bx
            self.ax = self.dx = None
            return
        if self._is_long4(node):
            self.load_long_axdx(node)
            return
        # *bufp — bufp is a near ptr to a far ptr; load the far ptr into DX:AX
        if (node[0] == 'deref' and node[1][0] == 'id'
                and node[1][1] in self.locals
                and self.locals[node[1][1]][1].startswith('ptr_ptr_far')):
            disp, _ = self.lvar(node[1][1])
            self.emit(0x8B, 0x5E, disp & 0xFF)          # mov bx, [bp+disp]
            self.emit(0x8B, 0x07)                       # mov ax, [bx]
            self.emit(0x8B, 0x57, 0x02)                 # mov dx, [bx+2]
            self.ax = self.dx = self.bx = None
            return
        # *(T far * far *)(far-ptr [+ disp]) : read the far pointer at
        # [es:bx+disp] into DX:AX (es:bx loaded/cached from the base far ptr).
        if (node[0] == 'deref' and node[1][0] == 'cast'
                and node[1][1].startswith('ptr_far_ptr')):
            operand, disp = node[1][2], 0
            if operand[0] == 'bin' and operand[1] == '+' and operand[3][0] == 'num':
                disp, operand = operand[3][1], operand[2]
            if (operand[0] == 'id'
                    and ((operand[1] in self.locals
                          and self.locals[operand[1]][1].startswith('ptr_far'))
                         or (operand[1] in SYMS and SYMS[operand[1]][0] == 'far_var'))):
                self.emit_les(operand[1])
                self.emit(0x26, 0x8B, 0x07 if disp == 0 else 0x47,
                          *((disp & 0xFF,) if disp else ()))     # mov ax,[es:bx+d]
                self.emit(0x26, 0x8B, 0x57, (disp + 2) & 0xFF)   # mov dx,[es:bx+d+2]
                self.ax = self.dx = None
                return
        # *(long far*)(base+d) → load the far long into DX:AX
        if (node[0] == 'deref' and node[1][0] == 'cast'
                and node[1][1] == 'ptr_far_long'):
            fl = self.far_lvalue(('deref', ('cast', 'ptr_far_int', node[1][2])))
            if fl is not None:
                base, disp, _ = fl
                self.emit_les(base)
                self.emit(0x26, 0x8B, (0x40 if disp else 0x00) | 0x07,
                          *((disp & 0xFF,) if disp else ()))            # mov ax,[es:bx+d]
                self.emit(0x26, 0x8B, 0x40 | 0x57, (disp + 2) & 0xFF)   # mov dx,[es:bx+d+2]
                self.ax = self.dx = None
                return
        # 16-bit `*near-int-ptr` in a long context → zero-extend: mov ax,[bx]; sub dx,dx
        if (node[0] == 'deref' and node[1][0] == 'id' and node[1][1] in self.locals
                and self.locals[node[1][1]][1] in ('ptr_int', 'ptr_uint')):
            self.ensure_bx(node[1][1])
            self.emit(0x8B, 0x07)                       # mov ax, [bx]
            self.emit(0x2B, 0xD2)                       # sub dx, dx
            self.ax = self.dx = None
            return
        # 16-bit int/uint local in a long context → zero-extend: mov ax,[bp+d]; sub dx,dx
        if (node[0] == 'id' and node[1] in self.locals
                and self.locals[node[1]][1] in ('int', 'uint')):
            d, _ = self.lvar(node[1])
            self.emit(0x8B, 0x46, d & 0xFF)             # mov ax, [bp+d]
            self.emit(0x2B, 0xD2)                       # sub dx, dx
            self.ax = self.dx = None
            return
        raise NotImplementedError(('gen_long', node))

    def _long_add_term(self, op, r):
        """DX:AX +=/-= a term.  A 32-bit term adds/subtracts both words; a
        16-bit term is zero-extended (adc/sbb dx,0)."""
        opc = 0x03 if op == '+' else 0x2B
        hic = 0x13 if op == '+' else 0x1B            # adc/sbb dx, <hi>
        ext = 0xD2 if op == '+' else 0xDA            # adc dx,0 / sbb dx,0
        # 32-bit operand: add/sub both words
        if r[0] == 'id' and r[1] in self.locals and self.locals[r[1]][1] == 'long':
            d, _ = self.lvar(r[1])
            self.emit(opc, 0x46, d & 0xFF)                         # add/sub ax,[bp+d]
            self.emit(hic, 0x56, (d + 2) & 0xFF)                   # adc/sbb dx,[bp+d+2]
            self.ax = self.dx = None
            return
        if r[0] == 'id' and r[1] in SYMS and SYMS[r[1]][0] == 'long_var':
            a = SYMS[r[1]][1]
            self.emit(opc, 0x06, a & 0xFF, (a >> 8) & 0xFF)              # add/sub ax,[a]
            self.emit(hic, 0x16, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)  # adc/sbb dx,[a+2]
            self.ax = self.dx = None
            return
        if r[0] == 'id' and r[1] in self.locals \
                and self.locals[r[1]][1] in ('int', 'uint'):
            d, _ = self.lvar(r[1])
            self.emit(opc, 0x46, d & 0xFF)                         # add/sub ax,[bp+d]
            self.emit(0x83, ext, 0x00)                             # adc/sbb dx,0 (zero-ext)
            self.ax = self.dx = None
            return
        if r[0] == 'id' and r[1] in SYMS and SYMS[r[1]][0] in ('var', 'uvar'):
            a = SYMS[r[1]][1]
            self.emit(opc, 0x06, a & 0xFF, (a >> 8) & 0xFF)        # add/sub ax,[a]
        elif r[0] == 'num':
            n = r[1] & 0xFFFF
            self.emit(0x05 if op == '+' else 0x2D, n & 0xFF, (n >> 8) & 0xFF)
        else:
            far = self.far_lvalue(r)
            if far is not None and far[2] == 'word':
                base, disp, _ = far
                self.emit_les(base)
                modrm = (0x40 if disp else 0x00) | 0x07
                self.emit(0x26, opc, modrm, *((disp & 0xFF,) if disp else ()))
            else:
                raise NotImplementedError(('long term', r))
        self.emit(0x83, ext, 0x00)                                 # adc/sbb dx, 0
        self.ax = self.dx = None

    def _is_long_expr(self, e):
        """True if expression e evaluates to a 32-bit (long) value."""
        if e[0] == 'cast':
            return e[1] == 'long'
        if e[0] == 'bin' and e[1] in ('+', '-', '<<'):
            return self._is_long_expr(e[2]) or self._is_long_expr(e[3])
        if e[0] == 'id':
            n = e[1]
            if n in self.locals:
                return self.locals[n][1] in ('long',) \
                    or self.locals[n][1].startswith('ptr_far')
            return n in SYMS and SYMS[n][0] in ('long_var', 'far_var')
        if e[0] == 'call' and e[1][0] == 'id' and e[1][1] in SYMS:
            return SYMS[e[1][1]][0] == 'far_func'
        if (e[0] == 'deref' and e[1][0] == 'cast'
                and (e[1][1] == 'ptr_far_long'
                     or e[1][1].startswith('ptr_far_ptr'))):
            return True                                  # *(long far*) / *(T far* far*)
        return False

    def _far_ptr_add_base(self, node):
        """If `node` is `far_ptr_local + <int terms>`, return (base_name, addends)."""
        if node[0] != 'bin' or node[1] != '+':
            return None
        terms = []
        def _f(n):
            if n[0] == 'bin' and n[1] == '+':
                _f(n[2]); _f(n[3])
            else:
                terms.append(n)
        _f(node)
        base = terms[0]
        if (base[0] == 'id' and base[1] in self.locals
                and self.locals[base[1]][1].startswith('ptr_far')):
            return (base[1], terms[1:])
        return None

    def _far_ptr_add_to_axdx(self, base_name, addends):
        """Build `base_name + addends` as a far pointer: offset in AX, seg in DX."""
        const = sum(t[1] for t in addends if t[0] == 'num') & 0xFFFF
        varts = [t for t in addends if t[0] != 'num']
        boff, _ = self.lvar(base_name)
        if varts:
            self.expr_to_ax(varts[0])                # ax = variable delta
            self.emit(0x03, 0x46, boff & 0xFF)       # add ax, [bp+base_off]
        else:
            self.emit(0x8B, 0x46, boff & 0xFF)       # mov ax, [bp+base_off]
        self.emit(0x8B, 0x56, (boff + 2) & 0xFF)     # mov dx, [bp+base_seg]
        if const:
            self.emit(0x05, const & 0xFF, (const >> 8) & 0xFF)  # add ax, const
        self.ax = self.dx = None

    def _load_cl(self, node):
        """Load a shift count into CL."""
        if node[0] == 'num' and self.cl == node[1]:
            return                                                 # CL already holds it
        self.cxbx_var = None                                       # writes CL
        self.cl = None
        if node[0] == 'id' and node[1] in SYMS and SYMS[node[1]][0] == 'bvar':
            a = SYMS[node[1]][1]
            self.emit(0x8A, 0x0E, a & 0xFF, (a >> 8) & 0xFF)       # mov cl, [a]
            return
        if node[0] == 'num':
            self.emit(0xB1, node[1] & 0xFF)                        # mov cl, imm
            self.cl = node[1]
            return
        if node[0] == 'id' and node[1] in SYMS and SYMS[node[1]][0] == 'var':
            a = SYMS[node[1]][1]
            self.emit(0x8A, 0x0E, a & 0xFF, (a >> 8) & 0xFF)       # mov cl, [a] (low byte)
            return
        far = self.far_lvalue(node)
        if far is not None and far[2] == 'byte':
            base, disp, _ = far
            self.emit_les(base)
            modrm = (0x40 if disp else 0x00) | 0x08 | 0x07         # /1 (CL), [bx+disp]
            self.emit(0x26, 0x8A, modrm, *((disp & 0xFF,) if disp else ()))  # mov cl,[es:bx+d]
            return
        raise NotImplementedError(('shift-count', node))

    def gen_assign(self, lhs, rhs):
        # a = (b = num) for two far-word stores — load the value once, store to the
        # inner target then the outer, reusing AX (MSC's chained `*p = *q = 0`).
        if (rhs[0] == 'assign' and lhs[0] == 'deref' and rhs[1][0] == 'deref'):
            fa, fb = self.far_lvalue(lhs), self.far_lvalue(rhs[1])
            inner = rhs[2]
            if (fa is not None and fb is not None and fa[2] == 'word' == fb[2]
                    and inner[0] == 'num'):
                n = inner[1] & 0xFFFF
                if n == 0:
                    self.emit(0x33, 0xC0)                       # xor ax, ax
                else:
                    self.emit(0xB8, n & 0xFF, (n >> 8) & 0xFF)  # mov ax, imm
                for base, disp in ((fb[0], fb[1]), (fa[0], fa[1])):
                    self.emit_les(base)
                    modrm = (0x40 if disp else 0x00) | 0x07
                    self.emit(0x26, 0x89, modrm, *((disp & 0xFF,) if disp else ()))
                self.ax = self.al = None
                return
        # int/uint local = <expr % div> : the divide leaves the remainder in DX,
        # so store DX straight to the local (no `mov ax,dx`) and keep the local
        # live in DX for a following use (e.g. `(offset << n)`).
        if (lhs[0] == 'id' and lhs[1] in self.locals
                and not self.is_reg_var(lhs[1])
                and self.locals[lhs[1]][1] in ('int', 'uint')
                and rhs[0] == 'bin' and rhs[1] == '%'):
            self.expr_to_ax(rhs[2])                  # dividend → AX
            self.emit(0x2B, 0xD2)                    # sub dx, dx
            self._emit_div_operand(rhs[3])           # div word[divisor]; rem in DX
            disp, _ = self.lvar(lhs[1])
            self.emit(0x89, 0x56, disp & 0xFF)       # mov [bp+disp], dx
            self.ax = self.al = None
            self.dx = ('val16', lhs[1])              # local now live in DX
            return
        # *p = long  where p is a near `long *` → store DX:AX through [p]
        if (lhs[0] == 'deref' and lhs[1][0] == 'id'
                and lhs[1][1] in self.locals
                and self.locals[lhs[1][1]][1] == 'ptr_long'):
            if rhs[0] == 'call':
                self.gen_call(rhs)
            else:
                self.gen_long(rhs)
            disp, _ = self.lvar(lhs[1][1])
            self.emit(0x8B, 0x5E, disp & 0xFF)        # mov bx, [bp+disp]
            self.emit(0x89, 0x07)                      # mov [bx], ax
            self.emit(0x89, 0x57, 0x02)                # mov [bx+2], dx
            self.bx = self.ax = self.dx = None
            return
        # *p = reg_var  where p is a near `int *`/`uint *` → store si/di through [p]
        if (lhs[0] == 'deref' and lhs[1][0] == 'id' and lhs[1][1] in self.locals
                and self.locals[lhs[1][1]][1] in ('ptr_int', 'ptr_uint')
                and rhs[0] == 'id' and rhs[1] in self.locals
                and self.is_reg_var(rhs[1])):
            disp, _ = self.lvar(lhs[1][1])
            self.emit(0x8B, 0x5E, disp & 0xFF)         # mov bx, [bp+disp]
            self.emit(0x89, 0x37 if self.regvars[rhs[1]] == 'si' else 0x3F)  # mov [bx],si/di
            self.bx = None
            return
        # *p = expr  where p is a near `int *`/`uint *` (num immediate or value→AX)
        if (lhs[0] == 'deref' and lhs[1][0] == 'id' and lhs[1][1] in self.locals
                and self.locals[lhs[1][1]][1] in ('ptr_int', 'ptr_uint')):
            if rhs[0] == 'num':
                self.ensure_bx(lhs[1][1])
                self.emit(0xC7, 0x07, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)  # mov word[bx],imm
            elif rhs[0] in ('bin', 'call'):
                # the value computation may clobber BX (div/far access) → eval first
                self.expr_to_ax(rhs)
                disp, _ = self.lvar(lhs[1][1])
                self.emit(0x8B, 0x5E, disp & 0xFF)     # mov bx, [bp+disp]
                self.emit(0x89, 0x07)                  # mov [bx], ax
            else:
                self.ensure_bx(lhs[1][1])
                self.expr_to_ax(rhs)
                self.emit(0x89, 0x07)                  # mov [bx], ax
            self.bx = None
            return
        # *p = far_ptr_local  where p is a near `T far **` → store the far ptr
        if (lhs[0] == 'deref' and lhs[1][0] == 'id' and lhs[1][1] in self.locals
                and self.locals[lhs[1][1]][1].startswith('ptr_ptr_far')
                and rhs[0] == 'id' and rhs[1] in self.locals
                and self.locals[rhs[1]][1].startswith('ptr_far')):
            pd, _ = self.lvar(lhs[1][1])
            self.emit(0x8B, 0x5E, pd & 0xFF)           # mov bx, [bp+p]
            rd, _ = self.lvar(rhs[1])
            self.emit(0x8B, 0x46, rd & 0xFF)           # mov ax, [bp+rec_off]
            self.emit(0x8B, 0x56, (rd + 2) & 0xFF)     # mov dx, [bp+rec_seg]
            self.emit(0x89, 0x07)                      # mov [bx], ax
            self.emit(0x89, 0x57, 0x02)                # mov [bx+2], dx
            self.ax = self.dx = self.bx = None
            return
        # *(T far **)p = far_local + <terms>  →  build the far pointer in AX:DX
        # (offset = delta + base_off + const, segment = base_seg) and store it
        # through the near pointer p.  Unlike `rec = …` (CX:BX, kept for reuse),
        # the store-through-pointer form lands directly in AX:DX.
        if (lhs[0] == 'deref' and lhs[1][0] == 'id' and lhs[1][1] in self.locals
                and self.locals[lhs[1][1]][1].startswith('ptr_ptr_far')
                and rhs[0] == 'bin' and rhs[1] == '+'):
            terms = []
            def _flat2(n):
                if n[0] == 'bin' and n[1] == '+':
                    _flat2(n[2]); _flat2(n[3])
                else:
                    terms.append(n)
            _flat2(rhs)
            base = terms[0]
            if (base[0] == 'id' and base[1] in self.locals
                    and self.locals[base[1]][1].startswith('ptr_far')):
                addends = terms[1:]
                const = sum(t[1] for t in addends if t[0] == 'num') & 0xFFFF
                varts = [t for t in addends if t[0] != 'num']
                if len(varts) <= 1:
                    boff, _ = self.lvar(base[1])
                    if varts:
                        self.expr_to_ax(varts[0])              # ax = variable delta
                        self.emit(0x03, 0x46, boff & 0xFF)     # add ax, [bp+base_off]
                    else:
                        self.emit(0x8B, 0x46, boff & 0xFF)     # mov ax, [bp+base_off]
                    self.emit(0x8B, 0x56, (boff + 2) & 0xFF)   # mov dx, [bp+base_seg]
                    if const:
                        self.emit(0x05, const & 0xFF, (const >> 8) & 0xFF)  # add ax, const
                    pd, _ = self.lvar(lhs[1][1])
                    self.emit(0x8B, 0x5E, pd & 0xFF)           # mov bx, [bp+p]
                    self.emit(0x89, 0x07)                      # mov [bx], ax
                    self.emit(0x89, 0x57, 0x02)                # mov [bx+2], dx
                    self.ax = self.dx = self.bx = None
                    return
        # long_lvalue = long_lvalue - longexpr : minuend in CX:BX (MSC keeps the
        # result there so a following read reuses it), subtrahend in DX:AX.
        if (self._is_long4(lhs) and rhs[0] == 'bin' and rhs[1] == '-'
                and self._is_long4(rhs[2])):
            self.gen_long(rhs[3])                  # subtrahend → DX:AX
            m = rhs[2][1]                          # minuend (a long lvalue)
            if m in self.locals:
                d, _ = self.lvar(m)
                self.emit(0x8B, 0x4E, d & 0xFF)            # mov cx,[bp+d]
                self.emit(0x8B, 0x5E, (d + 2) & 0xFF)      # mov bx,[bp+d+2]
            else:
                a = SYMS[m][1]
                self.emit(0x8B, 0x0E, a & 0xFF, (a >> 8) & 0xFF)              # mov cx,[a]
                self.emit(0x8B, 0x1E, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)  # mov bx,[a+2]
            self.emit(0x2B, 0xC8)                  # sub cx, ax
            self.emit(0x1B, 0xDA)                  # sbb bx, dx
            n = lhs[1]
            if n in self.locals:
                d, _ = self.lvar(n)
                self.emit(0x89, 0x4E, d & 0xFF)            # mov [bp+d], cx
                self.emit(0x89, 0x5E, (d + 2) & 0xFF)      # mov [bp+d+2], bx
            else:
                a = SYMS[n][1]
                self.emit(0x89, 0x0E, a & 0xFF, (a >> 8) & 0xFF)             # mov [a], cx
                self.emit(0x89, 0x1E, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF) # mov [a+2], bx
            self.ax = self.dx = None
            self.cxbx_var = n                      # CX:BX still hold this value
            return
        # long_local = (long)(16-bit expr): store the low word, then the high
        # word as an immediate 0 (C7) — and keep the low word live in AX so a
        # following `local = local + ...` reuses it (reloading only DX).
        if (self._is_long4(lhs) and lhs[0] == 'id' and lhs[1] in self.locals
                and rhs[0] == 'cast' and rhs[1] == 'long'):
            disp, _ = self.lvar(lhs[1])
            self.expr_to_ax(rhs[2])
            self.emit(0x89, 0x46, disp & 0xFF)               # mov [bp+d], ax
            self.emit(0xC7, 0x46, (disp + 2) & 0xFF, 0, 0)   # mov word [bp+d+2], 0
            self.ax = ('low', lhs[1])
            self.dx = None
            self.axdx_var = None
            return
        # far_local = far_local + <16-bit offset> : pointer arithmetic — copy the
        # segment, add the offset delta to the offset word.  MSC emits:
        #   mov ax,<var-delta>; mov cx,[base_off]; mov bx,[base_seg];
        #   add cx,ax [; add cx,k]; mov [dst_off],cx; mov [dst_seg],bx
        if (lhs[0] == 'id' and lhs[1] in self.locals
                and self.locals[lhs[1]][1].startswith('ptr_far')
                and rhs[0] == 'bin' and rhs[1] == '+'):
            terms = []
            def _flat(n):
                if n[0] == 'bin' and n[1] == '+':
                    _flat(n[2]); _flat(n[3])
                else:
                    terms.append(n)
            _flat(rhs)
            base = terms[0]
            if (base[0] == 'id' and base[1] in self.locals
                    and self.locals[base[1]][1].startswith('ptr_far')):
                addends = terms[1:]
                const = sum(t[1] for t in addends if t[0] == 'num') & 0xFFFF
                varts = [t for t in addends if t[0] != 'num']
                if len(varts) <= 1:
                    if varts:
                        self.expr_to_ax(varts[0])              # ax = variable delta
                    boff, _ = self.lvar(base[1])
                    self.emit(0x8B, 0x4E, boff & 0xFF)             # mov cx, [bp+base_off]
                    self.emit(0x8B, 0x5E, (boff + 2) & 0xFF)       # mov bx, [bp+base_seg]
                    if varts:
                        self.emit(0x03, 0xC8)                      # add cx, ax
                    if const:
                        if const < 128:
                            self.emit(0x83, 0xC1, const)           # add cx, imm8
                        else:
                            self.emit(0x81, 0xC1, const & 0xFF, (const >> 8) & 0xFF)
                    doff, _ = self.lvar(lhs[1])
                    self.emit(0x89, 0x4E, doff & 0xFF)             # mov [bp+dst_off], cx
                    self.emit(0x89, 0x5E, (doff + 2) & 0xFF)       # mov [bp+dst_seg], bx
                    self.ax = self.bx = self.dx = None
                    self.axdx_var = self.cxbx_var = None
                    return
        # 4-byte (long / far-ptr) scalar assignment: copy through AX:DX.
        if self._is_long4(lhs):
            if rhs[0] == 'call':
                self.gen_call(rhs)                # 32-bit result in AX:DX
            elif self._is_long4(rhs):
                self.load_long_axdx(rhs)
            else:
                self.gen_long(rhs)                # general long expression
            self.store_axdx_long(lhs)
            return
        # Byte scalar global:  BVAR = expr
        if lhs[0] == 'id' and lhs[1] in SYMS and SYMS[lhs[1]][0] == 'bvar':
            a = SYMS[lhs[1]][1]
            if rhs[0] == 'num':
                self.emit(0xC6, 0x06, a & 0xFF, (a >> 8) & 0xFF,
                          rhs[1] & 0xFF)                    # mov byte [a], imm
                return
            self.expr_to_al(rhs)
            self.emit(0xA2, a & 0xFF, (a >> 8) & 0xFF)      # mov [a], al
            self.al = ('rhs', rhs)                          # AL still holds rhs's value
            return
        # FP_SEG(p) / FP_OFF(p) = expr — write the segment / offset word of a
        # far pointer (offset word at base, segment at +2).
        if lhs[0] in ('fpseg', 'fpoff') and lhs[1][0] == 'id':
            name = lhs[1][1]
            # far_var global: store to [addr] / [addr+2]
            if name in SYMS and SYMS[name][0] == 'far_var':
                addr = SYMS[name][1] + (2 if lhs[0] == 'fpseg' else 0)
                if rhs[0] == 'num':
                    self.emit(0xC7, 0x06, addr & 0xFF, (addr >> 8) & 0xFF,
                              rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)  # mov word[addr],imm
                else:
                    self.expr_to_ax(rhs)
                    self.emit(0xA3, addr & 0xFF, (addr >> 8) & 0xFF)  # mov [addr],ax
                    self.ax = None
                self.axdx_var = None
                return
            disp, _ = self.lvar(name)
            if lhs[0] == 'fpseg':
                disp = (disp + 2) & 0xFF
            self.expr_to_ax(rhs)
            self.emit(0x89, 0x46, disp)               # mov [bp+disp], ax
            # Note that AX still holds the offset word, so a following push of
            # this far pointer can reuse it (push ax) instead of re-reading.
            self.ax = ('fpoff', lhs[1][1]) if lhs[0] == 'fpoff' else None
            if self.esbx == lhs[1][1]:
                self.esbx = None
            return
        # Far-pointer store:  *(T far *)(FAR_VAR + disp) = expr
        far = self.far_lvalue(lhs)
        if far is not None:
            fv, disp, kind = far
            modrm = (0x40 if disp else 0x00) | 0x07
            if kind == 'long':
                # *(long far*)(p+d) = long value  →  les; DX:AX = value; store both
                self.emit_les(fv)
                self.load_long_axdx(rhs)
                self.emit(0x26, 0x89, modrm, *((disp & 0xFF,) if disp else ()))  # [es:bx+d],ax
                self.emit(0x26, 0x89, 0x57, (disp + 2) & 0xFF)                  # [es:bx+d+2],dx
                self.ax = self.al = self.dx = None
                # the stored value is still in AX:DX — a following `return v` reuses it
                self.axdx_var = rhs[1] if rhs[0] == 'id' else None
                return
            if rhs[0] == 'num':
                # store immediate: mov byte/word [es:bx+disp], imm
                self.emit_les(fv)
                if kind == 'word':
                    self.emit(0x26, 0xC7, modrm, *((disp & 0xFF,) if disp else ()),
                              rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)
                else:
                    self.emit(0x26, 0xC6, modrm, *((disp & 0xFF,) if disp else ()),
                              rhs[1] & 0xFF)
                self.ax = self.al = None
                return
            if self._is_rm(rhs):
                # a simple memory rhs (e.g. a global) doesn't touch ES:BX, so MSC
                # loads the far pointer first, then the value.
                self.emit_les(fv)
                self.expr_to_ax(rhs)
            else:
                self.expr_to_ax(rhs)
                self.emit_les(fv)
            if kind == 'word':
                self.emit(0x26, 0x89, modrm, *((disp & 0xFF,) if disp else ()))
            else:
                self.emit(0x26, 0x88, modrm, *((disp & 0xFF,) if disp else ()))
            self.ax = self.al = None
            return
        # far_var[reg] = <byte expr>  →  al=expr; les bx,[addr]; mov es:[bx+idx],al
        fi = self.far_indexed_reg(lhs)
        if fi is not None:
            name, reg = fi
            self.expr_to_al(rhs)
            self.emit_les(name)
            self.emit(0x26, 0x88, 0x01 if reg == 'di' else 0x00)  # mov es:[bx+idx],al
            self.al = self.ax = None
            return
        # Byte-array stores indexed by a register var.
        if (lhs[0] == 'idx' and lhs[1][0] == 'id' and lhs[1][1] in SYMS
                and SYMS[lhs[1][1]][0] == 'arr'):
            arr_addr = SYMS[lhs[1][1]][1]
            idx = lhs[2]
            # ARR[reg++] = expr  →  al = expr; mov bx,reg; inc reg; mov [bx+ARR],al
            if (idx[0] == 'postinc' and idx[1][0] == 'id'
                    and self.is_reg_var(idx[1][1])):
                reg = self.regvars[idx[1][1]]
                self.expr_to_al(rhs)
                self.emit(0x8B, 0xDE if reg == 'si' else 0xDF)   # mov bx, si/di
                self.emit(0x46 if reg == 'si' else 0x47)         # inc si/di
                self.emit(0x88, 0x87, arr_addr & 0xFF, (arr_addr >> 8) & 0xFF)
                self.bx = self.al = None
                return
            # ARR[reg] = imm  →  mov byte [reg+ARR], imm
            if (idx[0] == 'id' and self.is_reg_var(idx[1])
                    and rhs[0] == 'num'):
                reg = self.regvars[idx[1]]
                modrm = 0x84 if reg == 'si' else 0x85            # [si/di + disp16]
                self.emit(0xC6, modrm, arr_addr & 0xFF,
                          (arr_addr >> 8) & 0xFF, rhs[1] & 0xFF)
                return
            raise NotImplementedError(('arr-store', lhs, rhs))
        # far_ptr_local[reg] = expr (byte) → les bx,[bp+d]; mov byte[es:bx+si/di],al/imm
        if (lhs[0] == 'idx' and lhs[1][0] == 'id' and lhs[1][1] in self.locals
                and self.locals[lhs[1][1]][1].startswith('ptr_far')
                and lhs[2][0] == 'id' and lhs[2][1] in self.locals
                and self.is_reg_var(lhs[2][1])):
            rm = 0x00 if self.regvars[lhs[2][1]] == 'si' else 0x01   # [bx+si]/[bx+di]
            if rhs[0] == 'num':
                self.emit_les(lhs[1][1])
                self.emit(0x26, 0xC6, rm, rhs[1] & 0xFF)            # mov byte[es:bx+idx],imm
            else:
                self.expr_to_al(rhs)
                self.emit_les(lhs[1][1])
                self.emit(0x26, 0x88, rm)                           # mov [es:bx+idx],al
            self.al = self.ax = None
            return
        # far_var[near-int local] = num  →  mov bx,[idx]; les si,[tbl]; mov byte[es:bx+si],imm
        if (lhs[0] == 'idx' and lhs[1][0] == 'id' and lhs[1][1] in SYMS
                and SYMS[lhs[1][1]][0] == 'far_var'
                and lhs[2][0] == 'id' and lhs[2][1] in self.locals
                and not self.is_reg_var(lhs[2][1]) and rhs[0] == 'num'):
            idisp, _ = self.lvar(lhs[2][1])
            self.emit(0x8B, 0x5E, idisp & 0xFF)                # mov bx, [bp+idx]
            addr = SYMS[lhs[1][1]][1]
            self.emit(0xC4, 0x36, addr & 0xFF, (addr >> 8) & 0xFF)  # les si, [tbl]
            self.emit(0x26, 0xC6, 0x00, rhs[1] & 0xFF)         # mov byte [es:bx+si], imm
            self.bx = self.esbx = None
            return
        # ((unsigned char *)&local)[const] = byte  →  byte store into the local's
        # frame slot at a fixed offset (e.g. clearing a long's high byte).
        if (lhs[0] == 'idx' and lhs[1][0] == 'cast' and 'far' not in lhs[1][1]
                and lhs[1][2][0] == 'addr' and lhs[1][2][1][0] == 'id'
                and lhs[1][2][1][1] in self.locals and lhs[2][0] == 'num'):
            disp, _ = self.lvar(lhs[1][2][1][1])
            d = (disp + lhs[2][1]) & 0xFF
            if rhs[0] == 'num':
                self.emit(0xC6, 0x46, d, rhs[1] & 0xFF)   # mov byte [bp+d], imm
            else:
                self.expr_to_al(rhs)
                self.emit(0x88, 0x46, d)                  # mov [bp+d], al
            self.al = None
            self.invalidate_mem(lhs[1][2][1][1])          # the local's value changed
            return
        if lhs[0] != 'id': raise NotImplementedError
        name = lhs[1]
        if name in self.locals:
            # Register-allocated local (currently only SI)
            if self.is_reg_var(name):
                reg = self.regvars[name]
                if rhs[0] == 'num' and rhs[1] == 0 and reg == 'si':
                    self.emit(0x33, 0xF6)                  # xor si, si
                elif rhs[0] == 'num' and rhs[1] == 0 and reg == 'di':
                    self.emit(0x33, 0xFF)                  # xor di, di
                elif rhs[0] == 'num' and reg == 'si':
                    self.emit(0xBE, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)
                elif rhs[0] == 'num' and reg == 'di':
                    self.emit(0xBF, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)
                elif (rhs[0] == 'id' and rhs[1] in self.locals
                      and self.is_reg_var(rhs[1])):
                    dst = 6 if reg == 'si' else 7
                    src = 6 if self.regvars[rhs[1]] == 'si' else 7
                    self.emit(0x8B, 0xC0 | (dst << 3) | src)   # mov si/di, si/di
                elif not self._force_regvar_ax and self._is_rm(rhs):
                    self._emit_rm_op(0x8B, reg, rhs)        # mov si/di, <load>
                elif (not self._force_regvar_ax
                      and rhs[0] == 'bin' and rhs[1] == '-'
                      and self._is_rm(rhs[2]) and self._is_rm(rhs[3])):
                    self._emit_rm_op(0x8B, reg, rhs[2])     # mov si/di, a
                    self._emit_rm_op(0x2B, reg, rhs[3])     # sub si/di, b
                else:
                    # reg = expr : evaluate to AX then `mov reg, ax`
                    self.expr_to_ax(rhs)
                    self.emit(0x8B, 0xF0 if reg == 'si' else 0xF8)  # mov si/di, ax
                return
            disp, ty = self.lvar(name)
            if ty == 'uchar':
                if rhs[0] == 'num':
                    self.emit(0xC6, 0x46, disp, rhs[1] & 0xFF)  # mov byte[bp+d],imm
                    self.al = None
                    return
                self.expr_to_al(rhs)
                self.emit(0x88, 0x46, disp)
                self.al = name
            else:
                if rhs[0] == 'num' and self._force_var_ax:
                    # if/else merge: route via AX so the `mov [bp+d],ax` tail merges
                    n = rhs[1] & 0xFFFF
                    if n == 0:
                        self.emit(0x33, 0xC0)                       # xor ax, ax
                    else:
                        self.emit(0xB8, n & 0xFF, (n >> 8) & 0xFF)  # mov ax, imm
                    self.emit(0x89, 0x46, disp)                     # mov [bp+d], ax
                elif rhs[0] == 'num':
                    n = rhs[1] & 0xFFFF
                    self.emit(0xC7, 0x46, disp, n & 0xFF, (n >> 8) & 0xFF)
                    self.ax = None
                elif (rhs[0] == 'id' and rhs[1] in self.locals
                      and self.is_reg_var(rhs[1])):
                    self.emit(0x89, 0x76 if self.regvars[rhs[1]] == 'si' else 0x7E,
                              disp)                          # mov [bp+d], si/di
                else:
                    self.expr_to_ax(rhs)
                    self.emit(0x89, 0x46, disp)
                    self.ax = name
                self.invalidate_mem(name)
                self.ax = name
            return
        if name in SYMS and SYMS[name][0] == 'var':
            addr = SYMS[name][1]
            # extern = reg_var  →  mov [addr], si/di  (direct, no AX round-trip)
            if rhs[0] == 'id' and rhs[1] in self.locals \
               and self.is_reg_var(rhs[1]):
                modrm = 0x36 if self.regvars[rhs[1]] == 'si' else 0x3E
                self.emit(0x89, modrm, addr & 0xFF, (addr >> 8) & 0xFF)
                return
            # extern = const  →  mov word [addr], imm16  (or, inside an if/else
            # whose other arm assigns the same global, materialize in AX so the
            # `mov [addr],ax` store merges: mov ax,imm / xor ax,ax; mov [addr],ax)
            if rhs[0] == 'num':
                n = rhs[1] & 0xFFFF
                if self._force_var_ax:
                    if n == 0:
                        self.emit(0x33, 0xC0)                     # xor ax, ax
                    else:
                        self.emit(0xB8, n & 0xFF, (n >> 8) & 0xFF)  # mov ax, imm
                    self.emit(0xA3, addr & 0xFF, (addr >> 8) & 0xFF)  # mov [addr], ax
                    self.ax = None
                    return
                self.emit(0xC7, 0x06, addr & 0xFF, (addr >> 8) & 0xFF,
                          n & 0xFF, (n >> 8) & 0xFF)
                return
            # extern = expr % divisor → div, then store the remainder (DX) direct
            if rhs[0] == 'bin' and rhs[1] == '%':
                self.expr_to_ax(rhs[2])
                self.emit(0x2B, 0xD2)                 # sub dx, dx
                self._emit_div_operand(rhs[3])
                self.emit(0x89, 0x16, addr & 0xFF, (addr >> 8) & 0xFF)  # mov [addr], dx
                self.ax = self.dx = None
                return
            self.expr_to_ax(rhs)
            self.emit(0xA3, addr & 0xFF, (addr >> 8) & 0xFF)   # mov [addr], ax
            self.ax = name                                     # AX still holds [addr]
            return
        if name in SYMS and SYMS[name][0] == 'far_var':
            addr = SYMS[name][1]
            # A far pointer is set from a far-returning call: DX:AX → off:seg.
            # Split-store the low word (AX) then the high word (DX).
            self.gen_call(rhs)
            self.emit(0xA3, addr & 0xFF, (addr >> 8) & 0xFF)        # mov [addr], ax
            self.emit(0x89, 0x16, (addr + 2) & 0xFF, ((addr + 2) >> 8) & 0xFF)  # mov [addr+2], dx
            self.ax = None
            return
        raise NameError(name)

    def gen_call(self, e, tail=False, cleanup=True):
        target = e[1]; args = e[2]
        if target[0] != 'id' or SYMS[target[1]][0] not in ('func', 'far_func'):
            raise NotImplementedError
        addr = SYMS[target[1]][1]
        # MSC zeroes a `0` argument with `sub ax,ax` for the pascal long
        # helpers (vs `xor ax,ax` for cdecl calls).
        self._pascal_call = target[1] in PASCAL
        nbytes = 0
        # MSC pre-loads ES:BX before the arg pushes when an arg is a far *word*
        # read (`push word[es:bx+d]`), incl. one widened via (long); a far *byte*
        # arg loads les inline instead.
        def _clobbers_bx(x):
            return ((x[0] == 'deref' and x[1][0] == 'id' and x[1][1] in self.locals
                     and self.locals[x[1][1]][1] in ('ptr_int', 'ptr_uint'))
                    or self.near_lvalue(x) is not None)
        for idx, a in enumerate(args):
            a2 = a[2] if (a[0] == 'cast' and a[1] == 'long') else a
            fl = self.far_lvalue(a2)
            if fl is not None and fl[2] == 'word' and not isinstance(fl[0], tuple):
                # Preload ES:BX only when the far-word arg is pushed early (not the
                # first C arg / last pushed — MSC loads les inline there) and no
                # earlier-pushed arg clobbers BX.
                if idx > 0 and not any(_clobbers_bx(x) for x in args[idx + 1:]):
                    self.emit_les(fl[0])
                break
        for a in reversed(args):
            self.push_arg(a)
            # far pointers and longs (local/param or far_var global) are 4 bytes
            far_arg = ((a[0] == 'id'
                        and ((a[1] in self.locals
                              and (self.locals[a[1]][1].startswith('ptr_far')
                                   or self.locals[a[1]][1] == 'long'))
                             or (a[1] in SYMS and SYMS[a[1]][0] in
                                 ('far_var', 'long_var'))))
                       or (a[0] == 'call' and a[1][0] == 'id'
                           and a[1][1] in SYMS and SYMS[a[1][1]][0] == 'far_func')
                       or (a[0] == 'deref' and a[1][0] == 'id'
                           and a[1][1] in self.locals
                           and self.locals[a[1][1]][1].startswith('ptr_ptr_far'))
                       or (a[0] in ('bin', 'cast') and self._is_long_expr(a))
                       or (a[0] == 'deref' and (self.near_lvalue(a) or (None,))[-1] == 'long'))
            nbytes += 4 if far_arg else 2
        self.emit_call(addr)
        # cdecl: caller cleans args.  Pascal callees clean their own (ret N);
        # cleanup=False defers to a shared site (switch).  A tail call can skip
        # `add sp` only when the epilogue's `mov sp,bp` reclaims the args with
        # nothing in between — but a `pop si/di` (saved reg) must see clean SP,
        # so don't skip when the function saves SI/DI.
        tail_skip = tail and not (self.uses_si or self.uses_di)
        if args and not tail_skip and cleanup and target[1] not in PASCAL:
            self.emit(0x83, 0xC4, nbytes)
        # A near call clobbers AX/BX/DX/ES (caller-saved); SI/DI are preserved.
        self.al = self.ax = self.bx = self.dx = self.esbx = None
        self.axdx_var = self.cxbx_var = None
        return nbytes

    @staticmethod
    def _switch_case_call(body):
        """A switch case body must be a single function call (+ optional
        break) — the DOS sub-dispatch shape. Return its call expr."""
        stmts = [s for s in body if s[0] != 'break']
        if len(stmts) == 1 and stmts[0][0] == 'expr' and stmts[0][1][0] == 'call':
            return stmts[0][1]
        raise NotImplementedError('switch case must be a single call')

    def gen_switch(self, val, cases, default):
        """MSC sub-dispatch: eval the value to AX, emit a `cmp ax,K / je case`
        chain + default jump, then the case bodies. Each case is a single call;
        they share one `add sp,N` cleanup and exit jump (MSC's tail-merge)."""
        if default:
            raise NotImplementedError('switch default body')
        self.expr_to_ax(val)
        brk = self.fresh('swbrk')
        caselbls = [self.fresh('case') for _ in cases]
        for (k, _), cl in zip(cases, caselbls):
            kv = k[1]
            self.emit(0x3D, kv & 0xFF, (kv >> 8) & 0xFF)   # cmp ax, imm16
            self.emit_jcc(0x74, cl)                        # je case
        self.emit_jmp_short(brk)                           # default → break
        shared = self.fresh('swshared')
        shared_done = False
        self.break_lbls.append(brk)
        for (k, body), cl in zip(cases, caselbls):
            self.lbl(cl)
            nbytes = self.gen_call(self._switch_case_call(body), cleanup=False)
            if not shared_done:
                self.lbl(shared)                           # cases converge here
                if nbytes:
                    self.emit(0x83, 0xC4, nbytes)          # add sp, N (shared)
                self.emit_jmp_short(brk)
                shared_done = True
            else:
                self.emit_jmp_short(shared)
        self.break_lbls.pop()
        self.lbl(brk)

    def push_arg(self, e):
        # A near (non-`far`, non-`long`) cast is a byte-level no-op at 16-bit
        # width — unwrap it so the idx/var fast-paths below still apply.  `long`
        # is NOT a no-op (it widens to 4 bytes), handled just below.
        if e[0] == 'cast' and 'far' not in e[1] and e[1] != 'long':
            return self.push_arg(e[2])
        # `0` to a pascal helper zeroes AX with `sub ax,ax` (not `xor`)
        if e == ('num', 0) and getattr(self, '_pascal_call', False):
            self.emit(0x2B, 0xC0)                              # sub ax, ax
            self.emit(0x50)                                    # push ax
            self.ax = None
            return
        # *bufp where bufp is a near pointer to a far pointer: push the far
        # pointer it points to (seg word, then off word).
        if (e[0] == 'deref' and e[1][0] == 'id' and e[1][1] in self.locals
                and self.locals[e[1][1]][1].startswith('ptr_ptr_far')):
            disp, _ = self.lvar(e[1][1])
            self.emit(0x8B, 0x5E, disp & 0xFF)                # mov bx, [bp+disp]
            self.emit(0xFF, 0x77, 0x02)                       # push word [bx+2]
            self.emit(0xFF, 0x37)                             # push word [bx]
            self.bx = None
            return
        # *p where p is a near `int *`/`uint *` → mov bx,[bp+disp]; push word [bx]
        if (e[0] == 'deref' and e[1][0] == 'id' and e[1][1] in self.locals
                and self.locals[e[1][1]][1] in ('ptr_int', 'ptr_uint')):
            self.ensure_bx(e[1][1])
            self.emit(0xFF, 0x37)                             # push word [bx]
            return
        # near-pointer deref arg: *(long*)(p+d) pushes [bx+d+2] then [bx+d];
        # *(uint*)(p+d) pushes [bx+d].  BX is loaded once via ensure_bx and
        # reused across the call's arg pushes (matches MSC's single `mov bx`).
        nl = self.near_lvalue(e)
        if nl is not None:
            base, disp, kind = nl
            self.ensure_bx(base)
            if kind == 'long':
                self._push_bx_word(disp + 2)                  # high word
            self._push_bx_word(disp)                          # low word / the word
            return
        # (long)(16-bit lvalue) arg: zero-extend in place — push 0 (high word),
        # then push the value's memory word directly (low).  Matches MSC widening
        # a 16-bit value to a long argument without routing it through AX.
        if e[0] == 'cast' and e[1] == 'long':
            inner = e[2]
            fl = self.far_lvalue(inner)
            lo = None
            if fl is not None and fl[2] == 'word' and not isinstance(fl[0], tuple):
                self.emit_les(fl[0])
                m = (0x40 if fl[1] else 0x00) | 0x30 | 0x07
                lo = (0x26, 0xFF, m) + ((fl[1] & 0xFF,) if fl[1] else ())
            elif (inner[0] == 'id' and inner[1] in self.locals
                  and self.locals[inner[1]][1] in ('int', 'uint')):
                d, _ = self.lvar(inner[1])
                lo = (0xFF, 0x76, d & 0xFF)
            elif (inner[0] == 'id' and inner[1] in SYMS
                  and SYMS[inner[1]][0] in ('var', 'uvar')):
                a = SYMS[inner[1]][1]
                lo = (0xFF, 0x36, a & 0xFF, (a >> 8) & 0xFF)
            if lo is not None:
                self.emit(0x2B if getattr(self, '_pascal_call', False) else 0x33,
                          0xC0)                                 # sub/xor ax, ax (high=0)
                self.emit(0x50)                                 # push ax
                self.emit(*lo)                                  # push word [low]
                self.ax = None
                self.axdx_var = None    # AX clobbered; AX:DX no longer a pair
                return
        # a long-valued expression (not a simple id, handled below): push DX:AX
        if e[0] in ('bin', 'cast') and self._is_long_expr(e):
            self.gen_long(e)
            self.emit(0x52)                                    # push dx
            self.emit(0x50)                                    # push ax
            self.ax = self.dx = None
            return
        # far-pointer-returning call as an argument: push DX:AX (seg then off)
        if (e[0] == 'call' and e[1][0] == 'id' and e[1][1] in SYMS
                and SYMS[e[1][1]][0] == 'far_func'):
            self.gen_call(e)
            self.emit(0x52)                                   # push dx (seg)
            self.emit(0x50)                                   # push ax (off)
            return
        if e[0] == 'id' and e[1] in SYMS and SYMS[e[1]][0] == 'var':
            addr = SYMS[e[1]][1]
            self.emit(0xFF, 0x36, addr & 0xFF, (addr >> 8) & 0xFF)
            return
        # far word lvalue → push word [es:bx+disp]
        _fw = self.far_lvalue(e)
        if _fw is not None and _fw[2] == 'word':
            base, disp, _ = _fw
            self.emit_les(base)
            modrm = (0x40 if disp else 0x00) | 0x30 | 0x07   # /6 (push), [bx+disp]
            self.emit(0x26, 0xFF, modrm, *((disp & 0xFF,) if disp else ()))
            return
        # far byte arg → zero-extend and push; reuse AL when it still holds this
        # value (e.g. `g = fcb[d]; f(fcb[d])`): skip the re-read.
        if _fw is not None and _fw[2] == 'byte':
            if self.al != ('rhs', e):
                base, disp, _ = _fw
                self.emit_les(base)
                self.emit(0x26, 0x8A, (0x40 if disp else 0x00) | 0x07,
                          *((disp & 0xFF,) if disp else ()))   # mov al,[es:bx+d]
            self.emit(0x2A, 0xE4)                              # sub ah, ah
            self.emit(0x50)                                    # push ax
            self.al = self.ax = None
            return
        # byte scalar global (uchar) → zero-extend to a word and push
        if e[0] == 'id' and e[1] in SYMS and SYMS[e[1]][0] == 'bvar':
            addr = SYMS[e[1]][1]
            self.emit(0xA0, addr & 0xFF, (addr >> 8) & 0xFF)   # mov al, [a]
            self.emit(0x2A, 0xE4)                              # sub ah, ah
            self.emit(0x50)                                    # push ax
            self.al = self.ax = None
            return
        # far-pointer global: push seg word then off word, or reuse AX:DX if
        # they still hold this value (e.g. right after `g = far_fn(...)`).
        if e[0] == 'id' and e[1] in SYMS and SYMS[e[1]][0] == 'far_var':
            addr = SYMS[e[1]][1]
            if self.axdx_var == e[1]:
                self.emit(0x52)                                   # push dx (seg)
                self.emit(0x50)                                   # push ax (off)
            else:
                self.emit(0xFF, 0x36, (addr + 2) & 0xFF, ((addr + 2) >> 8) & 0xFF)
                self.emit(0xFF, 0x36, addr & 0xFF, (addr >> 8) & 0xFF)
            return
        # long global: push high word then low word
        if e[0] == 'id' and e[1] in SYMS and SYMS[e[1]][0] == 'long_var':
            addr = SYMS[e[1]][1]
            if self.axdx_var == e[1]:
                self.emit(0x52)                                   # push dx (hi)
                self.emit(0x50)                                   # push ax (lo)
            else:
                self.emit(0xFF, 0x36, (addr + 2) & 0xFF, ((addr + 2) >> 8) & 0xFF)
                self.emit(0xFF, 0x36, addr & 0xFF, (addr >> 8) & 0xFF)
            return
        if e[0] == 'id' and e[1] in self.locals and self.is_reg_var(e[1]):
            self.emit(0x56 if self.regvars[e[1]] == 'si' else 0x57)  # push si/di
            return
        if e[0] == 'id' and e[1] in self.locals:
            disp, ty = self.lvar(e[1])
            if ty == 'long' or ty.startswith('ptr_far'):
                # reuse AX:DX if they still hold this 4-byte local
                if self.axdx_var == e[1]:
                    self.emit(0x52)                       # push dx
                    self.emit(0x50)                       # push ax
                    return
            if ty == 'long':
                # high word: reuse DX if still cached, else from memory
                if self.dx == ('hi', e[1]):
                    self.emit(0x52)                       # push dx (hi)
                else:
                    self.emit(0xFF, 0x76, (disp + 2) & 0xFF)  # push [bp+disp+2] (hi)
                self.emit(0xFF, 0x76, disp & 0xFF)         # push [bp+disp] (lo)
                return
            if ty.startswith('ptr_far'):
                # far pointer: push segment word then offset word. Reuse ES for
                # the segment when it still points here, and AX for the offset.
                if self.esbx == e[1]:
                    self.emit(0x06)                       # push es (segment, still live)
                else:
                    self.emit(0xFF, 0x76, (disp + 2) & 0xFF)  # push [bp+disp+2] (seg)
                if self.bx == e[1]:
                    self.emit(0x53)                       # push bx (offset, still live)
                    self.ax = None
                    return
                if self.ax == ('fpoff', e[1]):
                    self.emit(0x50)                        # push ax (offset)
                else:
                    self.emit(0xFF, 0x76, disp & 0xFF)     # push [bp+disp] (off)
                self.ax = None
                return
            if ty == 'uchar':
                # default argument promotion: zero-extend byte to word; reuse AL
                # if it already holds this local.
                if self.al != e[1]:
                    self.emit(0x8A, 0x46, disp)      # mov al, [bp+disp]
                self.emit(0x2A, 0xE4)                 # sub ah, ah
                self.emit(0x50)                       # push ax
                self.al = self.ax = None
                return
            self.emit(0xFF, 0x76, disp)
            return
        # Direct push of arr_w[local_var] — saves the AX round-trip.
        if (e[0] == 'idx'
                and e[1][0] == 'id' and e[1][1] in SYMS
                and SYMS[e[1][1]][0] == 'arr_w'
                and e[2][0] == 'id' and e[2][1] in self.locals):
            addr = SYMS[e[1][1]][1]
            idx_disp, _ = self.lvar(e[2][1])
            self.emit(0x8B, 0x5E, idx_disp)                       # mov bx, [bp+disp]
            self.emit(0xD1, 0xE3)                                 # shl bx, 1
            self.emit(0xFF, 0xB7,
                      addr & 0xFF, (addr >> 8) & 0xFF)            # push word [bx+addr]
            self.bx = None
            return
        self.expr_to_ax(e)
        self.emit(0x50)
        self.ax = None

    def gen_postinc(self, lvalue):
        # (*p)++ where p is a near `int *`/`uint *` → mov bx,[p]; inc word [bx]
        if (lvalue[0] == 'deref' and lvalue[1][0] == 'id'
                and lvalue[1][1] in self.locals
                and self.locals[lvalue[1][1]][1] in ('ptr_int', 'ptr_uint')):
            self.ensure_bx(lvalue[1][1])
            self.emit(0xFF, 0x07)                          # inc word [bx]
            return
        if lvalue[0] != 'id': raise NotImplementedError
        name = lvalue[1]
        if name in self.locals:
            if self.is_reg_var(name):
                self.emit(0x46 if self.regvars[name] == 'si' else 0x47)  # inc si/di
                return
            disp, ty = self.lvar(name)
            if ty == 'long':
                self.emit(0x83, 0x46, disp & 0xFF, 0x01)        # add word[bp+d],1
                self.emit(0x83, 0x56, (disp + 2) & 0xFF, 0x00)  # adc word[bp+d+2],0
            elif ty in ('uchar', 'char'):
                self.emit(0xFE, 0x46, disp & 0xFF)              # inc byte [bp+d]
            else:
                self.emit(0xFF, 0x46, disp & 0xFF)              # inc word [bp+d]
            self.invalidate_mem(name)
            if self.esbx == name:                      # far ptr offset changed
                self.esbx = None
            return
        if name in SYMS and SYMS[name][0] == 'var':
            addr = SYMS[name][1]
            self.emit(0xFF, 0x06, addr & 0xFF, (addr >> 8) & 0xFF)  # inc word [addr]
            # A BX cached as this var's index is now stale (value changed).
            if self.bx == ('idxvar', name):
                self.bx = None
            return
        if name in SYMS and SYMS[name][0] == 'long_var':
            addr = SYMS[name][1]
            self.emit(0x83, 0x06, addr & 0xFF, (addr >> 8) & 0xFF, 0x01)        # add word[addr],1
            self.emit(0x83, 0x16, (addr + 2) & 0xFF, ((addr + 2) >> 8) & 0xFF, 0x00)  # adc word[addr+2],0
            return
        raise NameError(name)

    def gen_postdec(self, lvalue):
        # Far-pointer field decrement:  (*(int far *)(FAR_VAR + disp))--
        far = self.far_lvalue(lvalue)
        if far is not None:
            fv, disp, kind = far
            self.emit_les(fv)
            modrm = (0x40 if disp else 0x00) | 0x08 | 0x07          # /1 [bx(+disp8)]
            self.emit(0x26, 0xFF, modrm, *((disp & 0xFF,) if disp else ()))
            return
        if lvalue[0] != 'id': raise NotImplementedError
        name = lvalue[1]
        if name in self.locals and self.is_reg_var(name):
            self.emit(0x4E if self.regvars[name] == 'si' else 0x4F)  # dec si/di
            return
        if name in self.locals:
            disp, _ = self.lvar(name)
            self.emit(0xFF, 0x4E, disp & 0xFF)                     # dec word [bp+disp]
            self.invalidate_mem(name)
            return
        if name in SYMS and SYMS[name][0] == 'var':
            addr = SYMS[name][1]
            self.emit(0xFF, 0x0E, addr & 0xFF, (addr >> 8) & 0xFF)  # dec word [addr]
            return
        raise NameError(name)

    # ---- expressions ----
    def expr_to_ax(self, e):
        # A local still live in DX (right after `local = expr % div`) is fetched
        # with `mov ax, dx` instead of a reload from its stack slot.
        if e[0] == 'id' and self.dx == ('val16', e[1]):
            self.emit(0x8B, 0xC2)                            # mov ax, dx
            self.ax = e[1]
            return
        # Evaluating overwrites AX — but a call pushes its args (which may reuse
        # AX:DX) before clobbering, so defer the clear to gen_call in that case.
        if e[0] != 'call':
            self.axdx_var = None
        op = e[0]
        if op == 'cast' and 'far' not in e[1]:
            return self.expr_to_ax(e[2])
        far = self.far_lvalue(e)
        if far is not None:
            fv, disp, kind = far
            self.emit_les(fv)
            modrm = (0x40 if disp else 0x00) | 0x07          # ax, [bx(+disp8)]
            if kind == 'word':
                self.emit(0x26, 0x8B, modrm, *((disp & 0xFF,) if disp else ()))
            else:
                self.emit(0x26, 0x8A, modrm, *((disp & 0xFF,) if disp else ()))
                self.emit(0x2A, 0xE4)                 # sub ah, ah (byte → int)
            self.ax = self.al = None
            return
        if op == 'num':
            if e[1] == 0:
                self.emit(0x33, 0xC0)                 # xor ax, ax
            else:
                self.emit(0xB8, e[1] & 0xFF, (e[1] >> 8) & 0xFF)
            self.ax = None
            return
        if op == 'call':
            self.gen_call(e)
            return
        if op == 'id':
            name = e[1]
            if name in self.locals:
                if self.is_reg_var(name):
                    self.emit(0x8B, 0xC6 if self.regvars[name] == 'si' else 0xC7)  # mov ax,si/di
                    self.ax = None
                    return
                if self.ax == name:
                    return
                disp, _ = self.lvar(name)
                if self.locals[name][1] == 'uchar':
                    self.emit(0x8A, 0x46, disp & 0xFF)    # mov al, [bp+d]
                    self.emit(0x2A, 0xE4)                 # sub ah, ah
                    self.al = name
                    self.ax = None
                    return
                self.emit(0x8B, 0x46, disp)
                self.ax = name
                return
            if name in SYMS:
                kind = SYMS[name][0]
                addr = SYMS[name][1]
                if kind == 'var':
                    if self.ax == name:           # AX still holds it (just assigned/compared)
                        return
                    self.emit(0xA1, addr & 0xFF, (addr >> 8) & 0xFF)
                    self.ax = name
                    return
                if kind in ('arr', 'arr_w'):
                    # array name → address-as-constant (decay to pointer)
                    self.emit(0xB8, addr & 0xFF, (addr >> 8) & 0xFF)
                    self.ax = None
                    return
        if op == 'addr':
            # &global → its address as a constant (decay to pointer)
            inner = e[1]
            if inner[0] == 'id' and inner[1] in SYMS:
                a = SYMS[inner[1]][1]
                self.emit(0xB8, a & 0xFF, (a >> 8) & 0xFF)   # mov ax, &global
                self.ax = None
                return
            # &local / &param → lea ax, [bp+disp]
            if inner[0] == 'id' and inner[1] in self.locals:
                disp, _ = self.lvar(inner[1])
                self.emit(0x8D, 0x46, disp & 0xFF)           # lea ax, [bp+disp]
                self.ax = None
                return
            raise NotImplementedError(('addr', e))
        if op == 'neg':
            self.expr_to_ax(e[1])
            self.emit(0xF7, 0xD8)                          # neg ax
            self.ax = None
            return
        if op == 'bin': return self.gen_bin(e[1], e[2], e[3])
        if op == 'idx':
            self.gen_index(e)
            # A byte-array element loads into AL; zero-extend to AX for an
            # int-context value (e.g. `return LINE_BUF[i];`).
            if (e[1][0] == 'id' and e[1][1] in SYMS
                    and SYMS[e[1][1]][0] == 'arr'):
                self.emit(0x2A, 0xE4)                  # sub ah, ah
            return
        # FP_OFF/FP_SEG of a far-pointer local → its offset/segment word.  Reuse
        # AX when it still holds this offset (just assigned), else load from mem.
        if (op in ('fpoff', 'fpseg') and e[1][0] == 'id'
                and e[1][1] in self.locals
                and self.locals[e[1][1]][1].startswith('ptr_far')):
            name = e[1][1]
            if op == 'fpoff' and self.ax == ('fpoff', name):
                return
            disp, _ = self.lvar(name)
            if op == 'fpseg':
                disp = (disp + 2) & 0xFF
            self.emit(0x8B, 0x46, disp & 0xFF)         # mov ax, [bp+disp]
            self.ax = ('fpoff', name) if op == 'fpoff' else None
            return
        # long global in a 16-bit context → its low word: mov ax, [addr]
        if op == 'id' and e[1] in SYMS and SYMS[e[1]][0] == 'long_var':
            a = SYMS[e[1]][1]
            self.emit(0xA1, a & 0xFF, (a >> 8) & 0xFF)   # mov ax, [a]
            self.ax = None
            return
        raise NotImplementedError(e)

    def expr_to_al(self, e):
        if e[0] != 'call':            # see expr_to_ax: defer for calls
            self.axdx_var = None
        op = e[0]
        if op == 'cast' and 'far' not in e[1]:
            return self.expr_to_al(e[2])
        if op == 'call':
            self.gen_call(e)             # result byte lands in AL (low of AX)
            return
        far = self.far_lvalue(e)
        if far is not None:
            base, disp, _ = far
            self.emit_les(base)
            modrm = (0x40 if disp else 0x00) | 0x07          # al, [bx(+disp8)]
            self.emit(0x26, 0x8A, modrm, *((disp & 0xFF,) if disp else ()))
            self.al = None
            return
        if op == 'id' and e[1] in self.locals:
            if self.al == e[1]:
                return
            disp, _ = self.lvar(e[1])
            self.emit(0x8A, 0x46, disp)
            self.al = e[1]
            return
        if op == 'idx':
            return self.gen_index(e)
        if op == 'num':
            self.emit(0xB0, e[1] & 0xFF)
            self.al = None
            return
        # uchar_local - imm  →  (load al), sub al, imm8
        if op == 'bin' and e[1] == '-' and e[3][0] == 'num' \
                and e[2][0] == 'id' and e[2][1] in self.locals:
            self.expr_to_al(e[2])
            self.emit(0x2C, e[3][1] & 0xFF)        # sub al, imm8
            self.al = None
            return
        # byte AND: <byte expr> & imm  →  (al = expr); and al, imm8
        if op == 'bin' and e[1] == '&' and e[3][0] == 'num':
            self.expr_to_al(e[2])
            self.emit(0x24, e[3][1] & 0xFF)        # and al, imm8
            self.al = None
            return
        # uchar_local + reg_var  →  mov al,[local]; mov cx,si/di; add al,cl
        if (op == 'bin' and e[1] == '+'
                and e[2][0] == 'id' and e[2][1] in self.locals
                and not self.is_reg_var(e[2][1])
                and e[3][0] == 'id' and e[3][1] in self.locals
                and self.is_reg_var(e[3][1])):
            self.expr_to_al(e[2])                            # mov al, [local]
            reg = self.regvars[e[3][1]]
            self.emit(0x8B, 0xCE if reg == 'si' else 0xCF)   # mov cx, si/di
            self.emit(0x02, 0xC1)                            # add al, cl
            self.al = None
            return
        # other binary ops: evaluate to AX (AL holds the low byte we want)
        if op == 'bin':
            self.gen_bin(e[1], e[2], e[3])
            return
        raise NotImplementedError(e)

    def gen_index(self, e):
        arr = e[1]; idx = e[2]
        # ((unsigned char *)&local)[const]  →  mov al, [bp+disp+const]  (a byte at a
        # fixed offset within a local, e.g. a long's high byte).
        if (arr[0] == 'cast' and 'far' not in arr[1] and arr[1].startswith('ptr')
                and arr[2][0] == 'addr' and arr[2][1][0] == 'id'
                and arr[2][1][1] in self.locals and idx[0] == 'num'):
            disp, _ = self.lvar(arr[2][1][1])
            self.emit(0x8A, 0x46, (disp + idx[1]) & 0xFF)       # mov al, [bp+d]
            self.al = self.ax = None
            return
        if arr[0] != 'id' or arr[1] not in SYMS:
            raise NotImplementedError
        arr_kind, arr_addr = SYMS[arr[1]][:2]
        # Word-element array of pointers (e.g. KEYWORD_PTR_TABLE)
        if arr_kind == 'arr_w':
            if idx[0] == 'id' and idx[1] in self.locals \
               and self.is_reg_var(idx[1]):
                # MSC pattern: mov bx, si; shl bx, 1; mov ax, [bx+addr]
                self.emit(0x8B, 0xDE)                                  # mov bx, si
                self.emit(0xD1, 0xE3)                                  # shl bx, 1
                self.emit(0x8B, 0x87,
                          arr_addr & 0xFF, (arr_addr >> 8) & 0xFF)     # mov ax, [bx+addr]
                self.bx = None
                self.ax = None
                return
            raise NotImplementedError('arr_w with non-reg idx')
        # Far-pointer global indexed by a near value: les si,[tbl]; al=[es:bx+si]
        if arr_kind == 'far_var':
            if idx[0] == 'id' and idx[1] in self.locals \
               and not self.is_reg_var(idx[1]):
                disp, _ = self.lvar(idx[1])
                self.emit(0x8B, 0x5E, disp & 0xFF)              # mov bx, [bp+idx]
            elif idx[0] == 'id' and idx[1] in SYMS and SYMS[idx[1]][0] == 'var':
                ia = SYMS[idx[1]][1]
                self.emit(0x8B, 0x1E, ia & 0xFF, (ia >> 8) & 0xFF)  # mov bx, [addr]
            else:
                raise NotImplementedError(idx)
            self.emit(0xC4, 0x36, arr_addr & 0xFF, (arr_addr >> 8) & 0xFF)  # les si,[tbl]
            self.emit(0x26, 0x8A, 0x00)                         # mov al, [es:bx+si]
            self.emit(0x2A, 0xE4)                               # sub ah, ah (zero-extend)
            self.al = self.ax = self.bx = self.esbx = None
            return
        if arr_kind != 'arr':
            raise NotImplementedError(arr_kind)
        # Byte-element array (e.g. LINE_BUF)
        if idx[0] == 'id' and idx[1] in self.locals:
            disp, _ = self.lvar(idx[1])
            self.emit(0x8B, 0x5E, disp)              # mov bx, [bp-N]
            self.bx = None
        elif idx[0] == 'id' and idx[1] in SYMS and SYMS[idx[1]][0] == 'var':
            iaddr = SYMS[idx[1]][1]
            self.emit(0x8B, 0x1E, iaddr & 0xFF, (iaddr >> 8) & 0xFF)  # mov bx, [addr]
            self.bx = None
        else:
            raise NotImplementedError(idx)
        # Load the byte from base+bx
        self.emit(0x8A, 0x87, arr_addr & 0xFF, (arr_addr >> 8) & 0xFF)
        self.al = self.ax = None

    def gen_bin(self, op, lhs, rhs):
        if op == '*':
            # far word * *near-int-ptr  →  mov ax,[es:bx+d]; mov bx,[bp+p]; mul word[bx]
            fl = self.far_lvalue(lhs)
            if (fl is not None and fl[2] == 'word'
                    and rhs[0] == 'deref' and rhs[1][0] == 'id'
                    and rhs[1][1] in self.locals
                    and self.locals[rhs[1][1]][1] in ('ptr_int', 'ptr_uint')):
                self.expr_to_ax(lhs)                       # mov ax, [es:bx+d]
                disp, _ = self.lvar(rhs[1][1])
                self.emit(0x8B, 0x5E, disp & 0xFF)         # mov bx, [bp+p]
                self.emit(0xF7, 0x27)                      # mul word [bx]
                self.ax = self.al = self.dx = self.bx = None
                return
            # MSC pattern: mov ax, <const> ; imul word [<var>]
            const, other = (rhs, lhs) if rhs[0] == 'num' else \
                           (lhs, rhs) if lhs[0] == 'num' else (None, None)
            if (const is not None and other[0] == 'id'
                    and other[1] in self.locals and self.is_reg_var(other[1])):
                self.emit(0xB8, const[1] & 0xFF, (const[1] >> 8) & 0xFF)  # mov ax, const
                self.emit(0xF7, 0xE6 if self.regvars[other[1]] == 'si'
                          else 0xE7)                    # mul si/di
                self.ax = self.al = self.dx = None
                return
            if const is not None and other[0] == 'id' and other[1] in self.locals:
                self.emit(0xB8, const[1] & 0xFF, (const[1] >> 8) & 0xFF)
                disp, _ = self.lvar(other[1])
                uns = self.locals[other[1]][1] in ('uint', 'uchar',
                                                   'reg_uint', 'reg_uchar')
                self.emit(0xF7, 0x66 if uns else 0x6E, disp)  # mul/imul word [bp-N]
                self.ax = self.al = None
                return
            # var-global * reg-var  →  mov ax,[g]; mul si/di
            for g_side, r_side in ((lhs, rhs), (rhs, lhs)):
                if (g_side[0] == 'id' and g_side[1] in SYMS
                        and SYMS[g_side[1]][0] == 'var'
                        and r_side[0] == 'id' and r_side[1] in self.locals
                        and self.is_reg_var(r_side[1])):
                    a = SYMS[g_side[1]][1]
                    self.emit(0xA1, a & 0xFF, (a >> 8) & 0xFF)   # mov ax, [g]
                    self.emit(0xF7, 0xE6 if self.regvars[r_side[1]] == 'si'
                              else 0xE7)                          # mul si/di
                    self.ax = self.al = self.dx = None
                    return
            raise NotImplementedError(('*', lhs, rhs))
        if op == '+':
            # far byte + far byte (same far base) → mov al,[es:bx+d1];sub ah,ah;
            # mov cl,[es:bx+d2];sub ch,ch; add ax,cx
            fl1, fl2 = self.far_lvalue(lhs), self.far_lvalue(rhs)
            if fl1 and fl2 and fl1[2] == 'byte' and fl2[2] == 'byte':
                self.emit_les(fl1[0])
                m1 = (0x40 if fl1[1] else 0x00) | 0x07
                self.emit(0x26, 0x8A, m1, *((fl1[1] & 0xFF,) if fl1[1] else ()))  # mov al,[es:bx+d1]
                self.emit(0x2A, 0xE4)                                # sub ah, ah
                self.emit_les(fl2[0])
                m2 = (0x40 if fl2[1] else 0x00) | 0x08 | 0x07
                self.emit(0x26, 0x8A, m2, *((fl2[1] & 0xFF,) if fl2[1] else ()))  # mov cl,[es:bx+d2]
                self.emit(0x2A, 0xED)                                # sub ch, ch
                self.emit(0x03, 0xC1)                                # add ax, cx
                self.ax = self.al = None
                return
            # Special: reg_var + small_const  →  lea ax, [si/di + disp8]
            if (lhs[0] == 'id' and lhs[1] in self.locals
                    and self.is_reg_var(lhs[1])
                    and rhs[0] == 'num' and 0 <= rhs[1] <= 127):
                rm = 0x44 if self.regvars[lhs[1]] == 'si' else 0x45
                self.emit(0x8D, rm, rhs[1] & 0xFF)         # lea ax, [si/di+disp8]
                self.ax = self.al = None
                return
            # Special: var + array_const  (or symmetric):
            # load the non-array side into AX, then `add ax, imm16` for the
            # array address.  Matches `mov ax,[X]; add ax, LINE_BUF_addr`.
            for v_side, c_side in ((lhs, rhs), (rhs, lhs)):
                if (c_side[0] == 'id' and c_side[1] in SYMS
                        and SYMS[c_side[1]][0] in ('arr', 'arr_w')):
                    self.expr_to_ax(v_side)
                    addr = SYMS[c_side[1]][1]
                    self.emit(0x05, addr & 0xFF, (addr >> 8) & 0xFF)
                    self.ax = None
                    return
            self.expr_to_ax(lhs)
            if rhs[0] == 'id' and rhs[1] in self.locals \
               and self.locals[rhs[1]][1] == 'uchar':
                disp, _ = self.lvar(rhs[1])
                self.emit(0x8A, 0x4E, disp)             # mov cl, [bp-N]
                self.emit(0x2A, 0xED)                   # sub ch, ch
                self.emit(0x03, 0xC1)                   # add ax, cx
                self.ax = self.al = None
                return
            # <expr> + word var global  →  eval lhs to AX; add ax, [g]
            if rhs[0] == 'id' and rhs[1] in SYMS and SYMS[rhs[1]][0] == 'var':
                a = SYMS[rhs[1]][1]
                self.emit(0x03, 0x06, a & 0xFF, (a >> 8) & 0xFF)  # add ax, [g]
                self.ax = self.al = None
                return
            if rhs[0] == 'num':
                if rhs[1] in (1, 2):           # MSC uses inc for + 1 / + 2
                    for _ in range(rhs[1]):
                        self.emit(0x40)        # inc ax
                else:
                    n = rhs[1] & 0xFFFF
                    self.emit(0x05, n & 0xFF, (n >> 8) & 0xFF)  # add ax, imm16
                self.ax = self.al = None
                return
            raise NotImplementedError(('+', lhs, rhs))
        if op == '-':
            self.expr_to_ax(lhs)
            r = rhs
            while r[0] == 'cast' and 'far' not in r[1] and r[1] != 'long':
                r = r[2]                       # a near cast is a no-op at 16-bit width
            if r[0] == 'num':
                if r[1] in (1, 2):             # MSC uses dec for - 1 / - 2
                    for _ in range(r[1]):
                        self.emit(0x48)        # dec ax
                else:
                    n = r[1] & 0xFFFF
                    self.emit(0x2D, n & 0xFF, (n >> 8) & 0xFF)
                self.ax = self.al = None
                return
            # ax -= <16-bit mem>: a word/long/unsigned global, or an int/uint local
            if r[0] == 'id' and r[1] in SYMS and SYMS[r[1]][0] in ('var', 'long_var'):
                a = SYMS[r[1]][1]
                self.emit(0x2B, 0x06, a & 0xFF, (a >> 8) & 0xFF)    # sub ax, [a]
                self.ax = self.al = None
                return
            if (r[0] == 'id' and r[1] in self.locals
                    and self.locals[r[1]][1] in ('int', 'uint')):
                d, _ = self.lvar(r[1])
                self.emit(0x2B, 0x46, d & 0xFF)                     # sub ax, [bp+d]
                self.ax = self.al = None
                return
            # ax -= far word lvalue: sub ax, [es:bx+disp]
            fr = self.far_lvalue(r)
            if fr is not None and fr[2] == 'word':
                base, disp, _ = fr
                self.emit_les(base)
                modrm = (0x40 if disp else 0x00) | 0x06           # /0 (ax)? no — sub r,r/m
                self.emit(0x26, 0x2B, (0x40 if disp else 0x00) | 0x07,
                          *((disp & 0xFF,) if disp else ()))        # sub ax, [es:bx+disp]
                self.ax = self.al = None
                return
            raise NotImplementedError(('-', lhs, rhs))
        if op == '<<':
            # 16-bit variable shift: shl ax, cl
            self.expr_to_ax(lhs)
            self._load_cl(rhs)
            self.emit(0xD3, 0xE0)                   # shl ax, cl
            self.ax = self.al = None
            return
        if op == '&':
            # 16-bit AND: eval lhs to AX, then `and ax, <rhs>`
            self.expr_to_ax(lhs)
            r = rhs
            while r[0] == 'cast' and 'far' not in r[1] and r[1] != 'long':
                r = r[2]
            if r[0] == 'id' and r[1] in SYMS and SYMS[r[1]][0] in ('var', 'long_var'):
                a = SYMS[r[1]][1]
                self.emit(0x23, 0x06, a & 0xFF, (a >> 8) & 0xFF)   # and ax, [a]
            elif r[0] == 'num':
                self.emit(0x25, r[1] & 0xFF, (r[1] >> 8) & 0xFF)   # and ax, imm16
            else:
                raise NotImplementedError(('&', lhs, rhs))
            self.ax = self.al = None
            return
        if op in ('/', '%'):
            # unsigned 16-bit divide: ax = lhs; sub dx,dx; div word[divisor].
            # Quotient lands in AX, remainder in DX; `%` moves DX->AX.
            self.expr_to_ax(lhs)
            self.emit(0x2B, 0xD2)                   # sub dx, dx
            self._emit_div_operand(rhs)
            if op == '%':
                self.emit(0x8B, 0xC2)               # mov ax, dx
            self.ax = self.al = self.dx = None
            return
        if (op == '>>' and rhs[0] == 'num'
                and not self._is_long_expr(lhs) and not self._is_long4(lhs)):
            # 16-bit unsigned shift: mov cl,amt; shr ax,cl  (shr ax,1 for amt==1)
            self.expr_to_ax(lhs)
            amt = rhs[1]
            if amt == 1:
                self.emit(0xD1, 0xE8)               # shr ax, 1
            else:
                self._load_cl(rhs)                  # mov cl, amt (reused if live)
                self.emit(0xD3, 0xE8)               # shr ax, cl
            self.ax = self.al = None
            return
        if op == '>>' and rhs[0] == 'num':
            # long >> const : evaluate to DX:AX.  MSC special-cases >>8 (byte
            # shuffle) and >>16 (word move); other counts use the SHR helper
            # (DX:AX >> CL, address pinned by __lshr).  Callers in a 16/8-bit
            # context (a cast) take AX / AL.
            self.load_long_axdx(lhs)                # ax=lo, dx=hi
            amt = rhs[1]
            if amt == 8:
                self.emit(0x8A, 0xC4)               # mov al, ah
                self.emit(0x8A, 0xE2)               # mov ah, dl
                self.emit(0x8A, 0xD6)               # mov dl, dh
                self.emit(0x2A, 0xF6)               # sub dh, dh
                self.ax = self.al = self.dx = None
            elif amt == 16:
                self.emit(0x8B, 0xC2)               # mov ax, dx
                self.emit(0x2B, 0xD2)               # sub dx, dx
                self.ax = self.al = self.dx = None
            else:
                self.emit(0xB1, amt & 0xFF)         # mov cl, amt
                self.emit_call(SYMS['__lshr'][1])   # clobbers AX/BX/CX/DX/ES
                self.al = self.ax = self.bx = self.dx = self.esbx = None
                self.axdx_var = self.cxbx_var = None
            return
        if op == '>>':
            # long >> variable : DX:AX = lhs; load CL; call the SHR helper
            self.gen_long(lhs)
            self._load_cl(rhs)
            self.emit_call(SYMS['__lshr'][1])
            self.al = self.ax = self.bx = self.dx = self.esbx = None
            self.axdx_var = self.cxbx_var = None
            return
        raise NotImplementedError(op)

    def _emit_div_operand(self, rhs):
        """Emit `div word [<rhs>]` for a word global or local divisor."""
        if rhs[0] == 'id' and rhs[1] in SYMS and SYMS[rhs[1]][0] == 'var':
            a = SYMS[rhs[1]][1]
            self.emit(0xF7, 0x36, a & 0xFF, (a >> 8) & 0xFF)   # div word [addr]
        elif rhs[0] == 'id' and rhs[1] in self.locals:
            d, _ = self.lvar(rhs[1])
            self.emit(0xF7, 0x76, d & 0xFF)                    # div word [bp+d]
        else:
            fr = self.far_lvalue(rhs)
            if fr is not None and fr[2] == 'word':
                base, disp, _ = fr
                self.emit_les(base)
                modrm = (0x40 if disp else 0x00) | 0x30 | 0x07     # /6 (div), [bx+disp]
                self.emit(0x26, 0xF7, modrm, *((disp & 0xFF,) if disp else ()))  # div word[es:bx+d]
                return
            raise NotImplementedError(('div-operand', rhs))

    # ---- conditional jumps ----
    def cond_jump(self, cond, label, taken):
        if cond[0] == 'or':
            if taken:
                self.cond_jump(cond[1], label, True)
                self.cond_jump(cond[2], label, True)
            else:
                skip = self.fresh('skip')
                self.cond_jump(cond[1], skip,  True)
                self.cond_jump(cond[2], label, False)
                self.lbl(skip)
            return
        if cond[0] == 'and':
            if taken:
                # (a && b) true → only branch when BOTH are true:
                # if (!a) skip; if (b) goto label; skip:
                skip = self.fresh('skip')
                self.cond_jump(cond[1], skip,  False)
                self.cond_jump(cond[2], label, True)
                self.lbl(skip)
            else:
                # NOT (a && b) → either arm false suffices:
                # if (!a) goto label; if (!b) goto label
                self.cond_jump(cond[1], label, False)
                self.cond_jump(cond[2], label, False)
            return

        if cond[0] != 'cmp':
            raise NotImplementedError(cond)

        cop, lhs, rhs = cond[1], cond[2], cond[3]

        # FP_OFF/FP_SEG(far_var) <op> X — a word at [addr]/[addr+2]: cmp word[a],X
        if (lhs[0] in ('fpoff', 'fpseg') and lhs[1][0] == 'id'
                and lhs[1][1] in SYMS and SYMS[lhs[1][1]][0] == 'far_var'):
            a = SYMS[lhs[1][1]][1] + (2 if lhs[0] == 'fpseg' else 0)
            if rhs[0] == 'num':
                n = rhs[1]
                sn = n if n < 0x8000 else n - 0x10000
                if -128 <= sn <= 127:
                    self.emit(0x83, 0x3E, a & 0xFF, (a >> 8) & 0xFF, n & 0xFF)
                else:
                    self.emit(0x81, 0x3E, a & 0xFF, (a >> 8) & 0xFF,
                              n & 0xFF, (n >> 8) & 0xFF)
                self.emit_jcc(self.jcc(cop, taken, True), label)
                return
            if (rhs[0] == 'id' and rhs[1] in SYMS
                    and SYMS[rhs[1]][0] in ('var', 'uvar')):
                self.expr_to_ax(rhs)                                # mov ax, [g]
                self.emit(0x39, 0x06, a & 0xFF, (a >> 8) & 0xFF)    # cmp [a], ax
                self.emit_jcc(self.jcc(cop, taken, True), label)
                return

        # *(long far*)(base+d) == 0 / != 0  →  mov ax,[es:bx+d]; or ax,[es:bx+d+2]; jz/jnz
        if (cop in ('==', '!=') and rhs == ('num', 0) and lhs[0] == 'deref'
                and lhs[1][0] == 'cast' and lhs[1][1] == 'ptr_far_long'):
            fl = self.far_lvalue(('deref', ('cast', 'ptr_far_int', lhs[1][2])))
            if fl is not None:
                base, disp, _ = fl
                self.emit_les(base)
                self.emit(0x26, 0x8B, (0x40 if disp else 0x00) | 0x07,
                          *((disp & 0xFF,) if disp else ()))            # mov ax,[es:bx+d]
                self.emit(0x26, 0x0B, 0x40 | 0x07, (disp + 2) & 0xFF)   # or ax,[es:bx+d+2]
                self.emit_jcc(self.jcc(cop, taken, False), label)
                return

        # (global++) <op> X  →  mov ax,[g]; inc word[g]; cmp ax, X
        if (lhs[0] == 'postinc' and lhs[1][0] == 'id' and lhs[1][1] in SYMS
                and SYMS[lhs[1][1]][0] == 'var'):
            g = SYMS[lhs[1][1]][1]
            self.emit(0xA1, g & 0xFF, (g >> 8) & 0xFF)          # mov ax, [g]
            self.emit(0xFF, 0x06, g & 0xFF, (g >> 8) & 0xFF)    # inc word [g]
            self.ax = None
            if rhs[0] == 'id' and rhs[1] in SYMS and SYMS[rhs[1]][0] == 'var':
                a = SYMS[rhs[1]][1]
                self.emit(0x3B, 0x06, a & 0xFF, (a >> 8) & 0xFF)  # cmp ax, [a]
            elif rhs[0] == 'num':
                n = rhs[1]
                sn = n if n < 0x8000 else n - 0x10000
                if n == 0:
                    self.emit(0x0B, 0xC0)                       # or ax, ax
                elif -128 <= sn <= 127:
                    self.emit(0x83, 0xF8, n & 0xFF)             # cmp ax, imm8
                else:
                    self.emit(0x3D, n & 0xFF, (n >> 8) & 0xFF)  # cmp ax, imm16
            else:
                raise NotImplementedError(('postinc-cmp', rhs))
            self.emit_jcc(self.jcc(cop, taken, self.is_uchar_cmp(lhs[1], rhs)),
                          label)
            return

        # (local++ / local--) <op> num  →  mov ax,[bp+d]; inc/dec word[bp+d];
        # cmp ax, num  (the comparison uses the pre-inc/dec value)
        if (lhs[0] in ('postinc', 'postdec') and lhs[1][0] == 'id'
                and lhs[1][1] in self.locals and not self.is_reg_var(lhs[1][1])
                and rhs[0] == 'num'):
            d, _ = self.lvar(lhs[1][1])
            self.emit(0x8B, 0x46, d & 0xFF)                     # mov ax, [bp+d]
            self.emit(0xFF, 0x46 if lhs[0] == 'postinc' else 0x4E, d & 0xFF)  # inc/dec word [bp+d]
            self.ax = None
            n = rhs[1]
            sn = n if n < 0x8000 else n - 0x10000
            if n == 0:
                self.emit(0x0B, 0xC0)                           # or ax, ax
            elif -128 <= sn <= 127:
                self.emit(0x83, 0xF8, n & 0xFF)                 # cmp ax, imm8
            else:
                self.emit(0x3D, n & 0xFF, (n >> 8) & 0xFF)      # cmp ax, imm16
            self.emit_jcc(self.jcc(cop, taken, self.is_uchar_cmp(lhs[1], rhs)),
                          label)
            return

        # long == 0 / != 0 — OR both words (or `or ax,dx` if it's freshly in regs)
        if rhs == ('num', 0) and lhs[0] == 'id' and self._is_long4(lhs):
            n = lhs[1]
            if self.axdx_var == n:
                self.emit(0x0B, 0xC2)                          # or ax, dx
            elif n in self.locals:
                d, _ = self.lvar(n)
                self.emit(0x8B, 0x46, d & 0xFF)                # mov ax,[bp+d]
                self.emit(0x0B, 0x46, (d + 2) & 0xFF)          # or ax,[bp+d+2]
            else:
                a = SYMS[n][1]
                self.emit(0xA1, a & 0xFF, (a >> 8) & 0xFF)                  # mov ax,[a]
                self.emit(0x0B, 0x06, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)  # or ax,[a+2]
            self.emit_jcc(self.jcc(cop, taken, False), label)
            return

        # long == / != long lvalue — evaluate lhs to DX:AX, then split-compare
        # the two words against a long global / local.
        if (cop in ('==', '!=') and rhs[0] == 'id'
                and ((rhs[1] in SYMS and SYMS[rhs[1]][0] == 'long_var')
                     or (rhs[1] in self.locals
                         and self.locals[rhs[1]][1] == 'long'))):
            self.gen_long(lhs)                                  # lhs → DX:AX
            if rhs[1] in self.locals:
                d, _ = self.lvar(rhs[1])
                hi = (0x3B, 0x56, (d + 2) & 0xFF)              # cmp dx,[bp+d+2]
                lo = (0x3B, 0x46, d & 0xFF)                    # cmp ax,[bp+d]
            else:
                a = SYMS[rhs[1]][1]
                hi = (0x3B, 0x16, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)  # cmp dx,[a+2]
                lo = (0x3B, 0x06, a & 0xFF, (a >> 8) & 0xFF)             # cmp ax,[a]
            jump_when_equal = (cop == '==') == taken
            if jump_when_equal:
                skip = self.fresh('skip')
                self.emit(*hi); self.emit_jcc(0x75, skip)     # jnz skip (hi differs)
                self.emit(*lo); self.emit_jcc(0x74, label)    # jz label (lo equal)
                self.lbl(skip)
            else:
                self.emit(*hi); self.emit_jcc(0x75, label)    # jnz label
                self.emit(*lo); self.emit_jcc(0x75, label)    # jnz label
            return

        # ordered long compare (unsigned long): high/low split with the jb/ja
        # two-level jump.  One operand goes to DX:AX (a computed long expr, or —
        # when both are simple long lvalues — the RHS); the other is compared
        # from memory.  (DX:AX-reuse to skip the reload is added separately.)
        def _long_lval(n):
            return (n[0] == 'id'
                    and ((n[1] in SYMS and SYMS[n[1]][0] == 'long_var')
                         or (n[1] in self.locals and self.locals[n[1]][1] == 'long')))
        if (cop in ('<', '>', '<=', '>=')
                and ((_long_lval(lhs) and _long_lval(rhs))
                     or (_long_lval(rhs) and lhs[0] in ('bin', 'cast')
                         and self._is_long_expr(lhs)))):
            if not self.is_uchar_cmp(lhs, rhs):
                raise NotImplementedError(('signed long ordered cmp', cond))
            if _long_lval(lhs) and _long_lval(rhs):
                if self.axdx_var != rhs[1]:            # reuse DX:AX if it still holds rhs
                    self.gen_long(('id', rhs[1]))      # rhs → DX:AX
                memn, opc = lhs[1], 0x39               # cmp [mem], dxreg
            else:
                self.gen_long(lhs)                     # lhs expr → DX:AX
                memn, opc = rhs[1], 0x3B               # cmp dxreg, [mem]
            if memn in self.locals:
                d, _ = self.lvar(memn)
                hi = (opc, 0x56, (d + 2) & 0xFF); lo = (opc, 0x46, d & 0xFF)
            else:
                a = SYMS[memn][1]
                hi = (opc, 0x16, (a + 2) & 0xFF, ((a + 2) >> 8) & 0xFF)
                lo = (opc, 0x06, a & 0xFF, (a >> 8) & 0xFF)
            TBL = {('>', True): ('skip', 'label', 0x77), ('>', False): ('label', 'skip', 0x76),
                   ('>=', True): ('skip', 'label', 0x73), ('>=', False): ('label', 'skip', 0x72),
                   ('<', True): ('label', 'skip', 0x72), ('<', False): ('skip', 'label', 0x73),
                   ('<=', True): ('label', 'skip', 0x76), ('<=', False): ('skip', 'label', 0x77)}
            jb_tgt, ja_tgt, lo_op = TBL[(cop, taken)]
            skip = self.fresh('lcmp')
            tgt = {'label': label, 'skip': skip}
            self.emit(*hi)
            self.emit_jcc(0x72, tgt[jb_tgt])           # jb
            self.emit_jcc(0x77, tgt[ja_tgt])           # ja (jnbe)
            self.emit(*lo)
            self.emit_jcc(lo_op, label)
            self.lbl(skip)
            return

        # (long >> 16) <op> const — the high word lives in DX, so MSC emits no
        # shift; just test DX (reused if it already holds x's high word, e.g.
        # right after `x = f()`).
        if (lhs[0] == 'bin' and lhs[1] == '>>' and lhs[3] == ('num', 16)
                and rhs[0] == 'num'):
            x = lhs[2]
            if not (self.dx == ('hi', x[1]) if x[0] == 'id' else False):
                self.load_long_axdx(x)            # mov dx, x_high (also reloads ax)
            if rhs[1] == 0:
                self.emit(0x0B, 0xD2)             # or dx, dx
            else:
                self.emit(0x81, 0xFA, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)  # cmp dx,imm
            self.emit_jcc(self.jcc(cop, taken, False), label)
            return

        # (far_mem & imm) == 0 / != 0  →  `test [mem], imm` (no AND/compare)
        if (lhs[0] == 'bin' and lhs[1] == '&' and lhs[3][0] == 'num'
                and rhs == ('num', 0)):
            far = self.far_lvalue(lhs[2])
            if far is not None:
                base, disp, kind = far
                self.emit_les(base)
                modrm = (0x40 if disp else 0x00) | 0x07     # /0, [bx+disp]
                imm = lhs[3][1]
                if kind == 'word':
                    self.emit(0x26, 0xF7, modrm, *((disp & 0xFF,) if disp else ()),
                              imm & 0xFF, (imm >> 8) & 0xFF)
                else:
                    self.emit(0x26, 0xF6, modrm, *((disp & 0xFF,) if disp else ()),
                              imm & 0xFF)
                self.emit_jcc(self.jcc(cop, taken, False), label)
                return

        # Assignment in the condition, e.g. (ch = read_byte()) != 0x0D — emit
        # the assignment (leaving the value in AL/AX), then compare the target.
        if lhs[0] == 'assign':
            target = lhs[1]
            self.gen_assign(target, lhs[2])
            # A far/array byte store leaves the value in AL with no named cache;
            # compare AL directly instead of re-reading through the pointer.
            far = self.far_lvalue(target)
            if rhs[0] == 'num' and far is not None and far[2] == 'byte':
                self.emit(0x3C, rhs[1] & 0xFF)             # cmp al, imm8
                self.emit_jcc(self.jcc(cop, taken, True), label)
                return
            lhs = target

        # Special: byte-array indexed by an extern var <op> num, e.g.
        # LINE_BUF[PARSE_POS] == 0x20  →  mov bx,[var] (cached); cmp byte
        # [bx+ARR], imm.  The BX load is shared across compares on the same
        # index (e.g. the two arms of an || condition).
        if (lhs[0] == 'idx' and lhs[1][0] == 'id' and lhs[1][1] in SYMS
                and SYMS[lhs[1][1]][0] == 'arr'
                and lhs[2][0] == 'id' and lhs[2][1] in SYMS
                and SYMS[lhs[2][1]][0] == 'var' and rhs[0] == 'num'):
            arr_addr = SYMS[lhs[1][1]][1]
            vaddr = SYMS[lhs[2][1]][1]
            key = ('idxvar', lhs[2][1])
            if self.bx != key:
                self.emit(0x8B, 0x1E, vaddr & 0xFF, (vaddr >> 8) & 0xFF)
                self.bx = key
            self.emit(0x80, 0xBF, arr_addr & 0xFF, (arr_addr >> 8) & 0xFF,
                      rhs[1] & 0xFF)                       # cmp byte [bx+ARR], imm8
            self.emit_jcc(self.jcc(cop, taken, False), label)
            return

        # word global <op> const  →  cmp word [addr], imm  (no AX load)
        # var global <op> num — reuse AX when it still holds the global (just
        # assigned, e.g. `g = f(); if (g == X)`): cmp ax, num
        if (lhs[0] == 'id' and lhs[1] in SYMS and SYMS[lhs[1]][0] == 'var'
                and rhs[0] == 'num' and self.ax == lhs[1]):
            n = rhs[1]
            if n == 0:
                self.emit(0x0B, 0xC0)                       # or ax, ax
            elif -128 <= n <= 127:
                self.emit(0x83, 0xF8, n & 0xFF)             # cmp ax, imm8
            else:
                self.emit(0x3D, n & 0xFF, (n >> 8) & 0xFF)  # cmp ax, imm16
            self.emit_jcc(self.jcc(cop, taken, lhs[1] in self.unsigned), label)
            return

        if (lhs[0] == 'id' and lhs[1] in SYMS and SYMS[lhs[1]][0] == 'var'
                and rhs[0] == 'num'):
            a = SYMS[lhs[1]][1]
            n = rhs[1]
            sn = n if n < 0x8000 else n - 0x10000
            if -128 <= sn <= 127:
                self.emit(0x83, 0x3E, a & 0xFF, (a >> 8) & 0xFF, n & 0xFF)
            else:
                self.emit(0x81, 0x3E, a & 0xFF, (a >> 8) & 0xFF,
                          n & 0xFF, (n >> 8) & 0xFF)
            self.emit_jcc(self.jcc(cop, taken, lhs[1] in self.unsigned), label)
            return

        # far byte <op> uchar local  →  les bx; mov al,[local]; cmp [es:bx+d],al
        fl = self.far_lvalue(lhs)
        if (fl is not None and fl[2] == 'byte' and rhs[0] == 'id'
                and rhs[1] in self.locals and self.locals[rhs[1]][1] == 'uchar'):
            base, disp, _ = fl
            self.emit_les(base)
            self.expr_to_al(rhs)
            modrm = (0x40 if disp else 0x00) | 0x07
            self.emit(0x26, 0x38, modrm, *((disp & 0xFF,) if disp else ()))  # cmp [es:bx+d],al
            self.emit_jcc(self.jcc(cop, taken, True), label)        # unsigned
            return

        # Special: far-pointer field <op> num  →  les bx + cmp [es:bx+disp], imm
        far = self.far_lvalue(lhs)
        if far is not None and rhs[0] == 'num':
            fv, disp, kind = far
            self.emit_les(fv)
            modrm = 0x40 | 0x38 | 0x07 if disp else 0x38 | 0x07   # /7 [bx(+disp8)]
            n = rhs[1]
            if kind == 'byte':
                self.emit(0x26, 0x80, modrm, *( (disp & 0xFF,) if disp else () ),
                          n & 0xFF)                                # cmp byte [es:bx+d], imm8
            elif -128 <= (n if n < 0x8000 else n - 0x10000) <= 127:
                self.emit(0x26, 0x83, modrm, *( (disp & 0xFF,) if disp else () ),
                          n & 0xFF)                                # cmp word [es:bx+d], imm8 sx
            else:
                self.emit(0x26, 0x81, modrm, *( (disp & 0xFF,) if disp else () ),
                          n & 0xFF, (n >> 8) & 0xFF)               # cmp word [es:bx+d], imm16
            unsigned = (lhs[0] == 'deref' and lhs[1][0] == 'cast'
                        and ('uint' in lhs[1][1] or 'uchar' in lhs[1][1]))
            self.emit_jcc(self.jcc(cop, taken, unsigned), label)
            return

        # Special: far-pointer word field <op> memory var  →  les bx; mov
        # ax,[var]; cmp [es:bx+disp], ax   (e.g. drv->count > idx).  Register
        # vars have their own direct `cmp [es:bx+disp], si/di` path.
        if (far is not None and far[2] == 'word' and rhs[0] == 'id'
                and ((rhs[1] in self.locals and not self.is_reg_var(rhs[1]))
                     or (rhs[1] in SYMS and SYMS[rhs[1]][0] in ('var', 'uvar')))):
            fv, disp, _ = far
            self.emit_les(fv)
            self.expr_to_ax(rhs)                                # mov ax, [var]
            modrm = (0x40 | 0x07) if disp else 0x07            # [bx(+disp8)], reg=ax
            self.emit(0x26, 0x39, modrm, *((disp & 0xFF,) if disp else ()))  # cmp [es:bx+d],ax
            unsigned = (lhs[0] == 'deref' and lhs[1][0] == 'cast'
                        and ('uint' in lhs[1][1] or 'uchar' in lhs[1][1]))
            self.emit_jcc(self.jcc(cop, taken, unsigned), label)
            return

        # Special: *p1 == *p2  (or with == direction flipped — same result)
        if (cop == '==' and lhs[0] == 'deref' and rhs[0] == 'deref'
                and lhs[1][0] == 'id' and rhs[1][0] == 'id'
                and lhs[1][1] in self.locals and rhs[1][1] in self.locals):
            # MSC pattern: rhs ptr → BX, lhs ptr → DI; mov al,[di]; cmp [bx],al
            rdisp, _ = self.lvar(rhs[1][1])
            self.emit(0x8B, 0x5E, rdisp)                   # mov bx, [bp-N]
            self.bx = rhs[1][1]
            ldisp, _ = self.lvar(lhs[1][1])
            self.emit(0x8B, 0x7E, ldisp)                   # mov di, [bp-N]
            self.di = lhs[1][1]
            self.emit(0x8A, 0x05)                          # mov al, [di]
            self.al = None
            self.emit(0x38, 0x07)                          # cmp [bx], al
            self.emit_jcc(self.jcc(cop, taken, False), label)
            return

        # *(long far*)(base+d) == 0 / != 0  →  mov ax,[es:bx+d]; or ax,[es:bx+d+2]; jz/jnz
        if (cop in ('==', '!=') and rhs == ('num', 0) and lhs[0] == 'deref'
                and lhs[1][0] == 'cast' and lhs[1][1] == 'ptr_far_long'):
            fl = self.far_lvalue(('deref', ('cast', 'ptr_far_int', lhs[1][2])))
            if fl is not None:
                base, disp, _ = fl
                self.emit_les(base)
                self.emit(0x26, 0x8B, (0x40 if disp else 0x00) | 0x07,
                          *((disp & 0xFF,) if disp else ()))            # mov ax,[es:bx+d]
                self.emit(0x26, 0x0B, 0x40 | 0x07, (disp + 2) & 0xFF)   # or ax,[es:bx+d+2]
                self.emit_jcc(self.jcc(cop, taken, False), label)
                return

        # (a % b) == 0 / != 0  →  div; or dx,dx; jz/jnz  (remainder stays in DX)
        if (cop in ('==', '!=') and rhs == ('num', 0)
                and lhs[0] == 'bin' and lhs[1] == '%'):
            self.expr_to_ax(lhs[2])
            self.emit(0x2B, 0xD2)                                       # sub dx, dx
            self._emit_div_operand(lhs[3])
            self.emit(0x0B, 0xD2)                                       # or dx, dx
            self.emit_jcc(self.jcc(cop, taken, False), label)
            return

        # Special: *ptr <op> num — byte for a char ptr, word for an int/uint ptr
        if (cop in ('==', '!=') and lhs[0] == 'deref'
                and lhs[1][0] == 'id' and lhs[1][1] in self.locals
                and rhs[0] == 'num'):
            ty = self.locals[lhs[1][1]][1]
            self.ensure_bx(lhs[1][1])
            if ty in ('ptr_int', 'ptr_uint'):
                n = rhs[1]
                if -128 <= n <= 127:
                    self.emit(0x83, 0x3F, n & 0xFF)        # cmp word [bx], imm8 sx
                else:
                    self.emit(0x81, 0x3F, n & 0xFF, (n >> 8) & 0xFF)  # cmp word [bx], imm16
            else:
                self.emit(0x80, 0x3F, rhs[1] & 0xFF)       # cmp byte [bx], imm8
            self.emit_jcc(self.jcc(cop, taken, False), label)
            return

        # Special: *near-int-ptr <op> int-local  →  (ax=rhs); mov bx,[p]; cmp [bx],ax
        if (lhs[0] == 'deref' and lhs[1][0] == 'id' and lhs[1][1] in self.locals
                and self.locals[lhs[1][1]][1] in ('ptr_int', 'ptr_uint')
                and rhs[0] == 'id' and rhs[1] in self.locals
                and not self.is_reg_var(rhs[1])):
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.ensure_bx(lhs[1][1])                       # mov bx,[p] first
            self.expr_to_ax(rhs)                            # then ax = rhs (reused if cached)
            self.emit(0x39, 0x07)                          # cmp [bx], ax
            self.emit_jcc(self.jcc(cop, taken, unsigned), label)
            return

        # Special: byte global (uchar) <op> num  →  cmp byte [addr], imm8
        if (lhs[0] == 'id' and lhs[1] in SYMS and SYMS[lhs[1]][0] == 'bvar'
                and rhs[0] == 'num'):
            addr = SYMS[lhs[1]][1]
            self.emit(0x80, 0x3E, addr & 0xFF, (addr >> 8) & 0xFF, rhs[1] & 0xFF)
            self.emit_jcc(self.jcc(cop, taken, True), label)
            return

        # Special: far_var[reg] <op> num  →  les bx,[addr]; cmp byte es:[bx+idx],imm8
        fi = self.far_indexed_reg(lhs)
        if fi is not None and rhs[0] == 'num':
            name, reg = fi
            self.emit_les(name)
            rm = 0x01 if reg == 'di' else 0x00            # [bx+di] / [bx+si]
            self.emit(0x26, 0x80, 0x38 | rm, rhs[1] & 0xFF)  # cmp byte es:[bx+idx],imm8
            self.emit_jcc(self.jcc(cop, taken, True), label)
            return

        # Special: far word lvalue <op> reg_var → les bx; cmp es:[bx+disp],si/di
        fw = self.far_lvalue(lhs)
        if (fw is not None and fw[2] == 'word'
                and rhs[0] == 'id' and rhs[1] in self.locals
                and self.is_reg_var(rhs[1])):
            base, disp, _ = fw
            self.emit_les(base)
            rf = 6 if self.regvars[rhs[1]] == 'si' else 7
            modrm = (0x40 if disp else 0x00) | (rf << 3) | 0x07   # es:[bx+disp8]
            self.emit(0x26, 0x39, modrm, *((disp & 0xFF,) if disp else ()))  # cmp es:[bx+d],si/di
            self.emit_jcc(self.jcc(cop, taken, self.is_uchar_cmp(lhs, rhs)), label)
            return

        # Special: reg-var (SI/DI) <op> num
        if (lhs[0] == 'id' and lhs[1] in self.locals
                and self.is_reg_var(lhs[1]) and rhs[0] == 'num'):
            reg = self.regvars[lhs[1]]
            n = rhs[1] & 0xFFFF
            if rhs[1] == 0:
                self.emit(0x0B, 0xF6 if reg == 'si' else 0xFF)  # or si,si / or di,di
            else:
                rb = 0xFE if reg == 'si' else 0xFF
                if -128 <= rhs[1] <= 127:
                    self.emit(0x83, rb, n & 0xFF)          # cmp si/di, imm8 sx
                else:
                    self.emit(0x81, rb, n & 0xFF, (n >> 8) & 0xFF)
            self.emit_jcc(self.jcc(cop, taken, self.is_uchar_cmp(lhs, rhs)), label)
            return

        # Special: int/uint local <op> reg_var  →  cmp [bp+disp], si/di
        if (lhs[0] == 'id' and lhs[1] in self.locals and not self.is_reg_var(lhs[1])
                and self.locals[lhs[1]][1] in ('int', 'uint')
                and rhs[0] == 'id' and rhs[1] in self.locals
                and self.is_reg_var(rhs[1])):
            disp, _ = self.lvar(lhs[1])
            modrm = 0x76 if self.regvars[rhs[1]] == 'si' else 0x7E   # [bp+disp],si/di
            self.emit(0x39, modrm, disp & 0xFF)                      # cmp [bp+disp], si/di
            self.emit_jcc(self.jcc(cop, taken, self.is_uchar_cmp(lhs, rhs)), label)
            return

        # Special: <computed expr> <op> reg_var  →  eval lhs to AX; cmp ax, si/di
        # (only for genuine expressions — simple id operands have their own paths)
        if (rhs[0] == 'id' and rhs[1] in self.locals and self.is_reg_var(rhs[1])
                and not (lhs[0] == 'id' and (lhs[1] in self.locals or lhs[1] in SYMS))):
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.expr_to_ax(lhs)
            self.emit(0x3B, 0xC6 if self.regvars[rhs[1]] == 'si' else 0xC7)  # cmp ax,si/di
            self.emit_jcc(self.jcc(cop, taken, unsigned), label)
            return

        # Special: extern int var <op> reg_var  →  cmp [addr], si/di
        if (lhs[0] == 'id' and lhs[1] in SYMS and SYMS[lhs[1]][0] == 'var'
                and rhs[0] == 'id' and rhs[1] in self.locals
                and self.is_reg_var(rhs[1])):
            addr = SYMS[lhs[1]][1]
            modrm = 0x36 if self.regvars[rhs[1]] == 'si' else 0x3E
            self.emit(0x39, modrm, addr & 0xFF, (addr >> 8) & 0xFF)  # cmp [addr], si/di
            self.emit_jcc(self.jcc(cop, taken, self.is_uchar_cmp(lhs, rhs)), label)
            return

        # Special: extern int var <op> expr  →  mov ax, expr; cmp [addr], ax
        if (lhs[0] == 'id' and lhs[1] in SYMS and SYMS[lhs[1]][0] == 'var'):
            addr = SYMS[lhs[1]][1]
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.expr_to_ax(rhs)
            self.emit(0x39, 0x06, addr & 0xFF, (addr >> 8) & 0xFF)   # cmp [addr], ax
            self.emit_jcc(self.jcc(cop, taken, unsigned), label)
            return

        # Special: <computed expr> <op> word var global  →  eval lhs to AX;
        # cmp ax,[g].  (A simple id lhs uses its own var/local path below.)
        if (rhs[0] == 'id' and rhs[1] in SYMS and SYMS[rhs[1]][0] == 'var'
                and lhs[0] != 'id'):
            a = SYMS[rhs[1]][1]
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.expr_to_ax(lhs)
            self.emit(0x3B, 0x06, a & 0xFF, (a >> 8) & 0xFF)   # cmp ax, [g]
            self.emit_jcc(self.jcc(cop, taken, unsigned), label)
            return

        unsigned = self.is_uchar_cmp(lhs, rhs)

        # uchar <op> const : cmp al, imm8 (when AL has it) or mem-form
        if (lhs[0] == 'id' and lhs[1] in self.locals
                and self.locals[lhs[1]][1] == 'uchar'
                and rhs[0] == 'num'):
            if self.al == lhs[1]:
                self.emit(0x3C, rhs[1] & 0xFF)                  # cmp al, imm8
            else:
                disp, _ = self.lvar(lhs[1])
                self.emit(0x80, 0x7E, disp, rhs[1] & 0xFF)      # cmp byte [bp-N], imm8

        # int-var <op> small const : cmp word [bp+disp], imm8 sign-extended
        elif (lhs[0] == 'id' and lhs[1] in self.locals
              and (self.locals[lhs[1]][1] in ('int', 'uint')
                   or self.locals[lhs[1]][1].startswith('ptr'))
              and rhs[0] == 'num' and -128 <= rhs[1] <= 127):
            disp, _ = self.lvar(lhs[1])
            self.emit(0x83, 0x7E, disp, rhs[1] & 0xFF)          # cmp word [bp+disp], imm8 sx

        # int/ptr-var <op> int/ptr-expr : load expr to AX, cmp [bp-N], ax.  Skip
        # when AX already holds this local and rhs is a constant — the general
        # case below reuses AX directly (cmp ax, imm).
        elif (lhs[0] == 'id' and lhs[1] in self.locals
              and (self.locals[lhs[1]][1] in ('int', 'uint')
                   or self.locals[lhs[1]][1].startswith('ptr'))
              and not (self.ax == lhs[1] and rhs[0] == 'num')):
            self.expr_to_ax(rhs)
            disp, _ = self.lvar(lhs[1])
            self.emit(0x39, 0x46, disp)                         # cmp [bp-N], ax

        # uchar-returning call <op> const : the result is a byte in AL — test AL
        elif (rhs[0] == 'num' and lhs[0] == 'call' and lhs[1][0] == 'id'
              and lhs[1][1] in UCHAR_FUNCS):
            self.gen_call(lhs)
            if rhs[1] == 0:
                self.emit(0x0A, 0xC0)                           # or al, al
            else:
                self.emit(0x3C, rhs[1] & 0xFF)                  # cmp al, imm8
            self.emit_jcc(self.jcc(cop, taken, True), label)
            return
        # general expr (e.g. a call result) <op> const : eval to AX, then test
        elif rhs[0] == 'num':
            self.expr_to_ax(lhs)
            if rhs[1] == 0:
                self.emit(0x0B, 0xC0)                           # or ax, ax
            elif -128 <= rhs[1] <= 127:
                self.emit(0x83, 0xF8, rhs[1] & 0xFF)            # cmp ax, imm8 sx
            else:
                self.emit(0x3D, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)  # cmp ax, imm16

        else:
            raise NotImplementedError(cond)

        self.emit_jcc(self.jcc(cop, taken, unsigned), label)

    def is_uchar_cmp(self, lhs, rhs):
        """True if either operand is unsigned (drives unsigned JCC selection)."""
        for side in (lhs, rhs):
            if side[0] != 'id':
                continue
            n = side[1]
            if n in self.locals and self.locals[n][1] in (
                    'uchar', 'uint', 'reg_uint', 'reg_uchar'):
                return True
            if n in self.unsigned:
                return True
        return False

    def jcc(self, op, taken, unsigned):
        true_signed   = {'<':0x7C,'>':0x7F,'<=':0x7E,'>=':0x7D,'==':0x74,'!=':0x75}
        true_unsigned = {'<':0x72,'>':0x77,'<=':0x76,'>=':0x73,'==':0x74,'!=':0x75}
        false_signed   = {'<':0x7D,'>':0x7E,'<=':0x7F,'>=':0x7C,'==':0x75,'!=':0x74}
        false_unsigned = {'<':0x73,'>':0x76,'<=':0x77,'>=':0x72,'==':0x75,'!=':0x74}
        if taken:
            return (true_unsigned if unsigned else true_signed)[op]
        return (false_unsigned if unsigned else false_signed)[op]


# --------- Driver ---------


def build_syms(decls, addr_map):
    """Build the per-compile symbol table from the parsed declarations.

    Returns (syms, unsigned):
      syms     – {name: (kind, addr)}; kinds come from the C declarations,
                 addresses from `__addr__(N)` in the C (preferred) or the
                 supplied `addr_map`.  Names with no address are skipped.
      unsigned – set of names whose comparisons are unsigned (declared
                 `unsigned`/`unsigned int`).
    """
    syms = {}
    unsigned = set()
    pascal = set()
    uchar_funcs = set()
    for d in decls:
        if d[0] == 'extern':
            _, name, kind, addr, is_pascal, ret_uchar = d
            if addr is None:
                addr = addr_map.get(name)
            if addr is None:
                continue
            if ret_uchar and kind in ('func', 'far_func'):
                uchar_funcs.add(name)
            if kind == 'uvar':
                kind = 'var'
                unsigned.add(name)
            if kind == 'ulong_var':
                kind = 'long_var'
                unsigned.add(name)
            syms[name] = (kind, addr)
            if is_pascal:
                pascal.add(name)
        elif d[0] == 'func':
            name, addr, far_ret = d[1], d[4], d[5]
            if addr is None:
                addr = addr_map.get(name)
            if addr is not None:
                syms[name] = ('far_func' if far_ret else 'func', addr)
    return syms, unsigned, pascal, uchar_funcs


def compile_src(src, addr_map=None):
    """Compile every defined function in `src` that has a resolvable address.

    Addresses and kinds come from the C itself (`__addr__(N)` and the
    declarations); `addr_map` (a {name: address} dict, e.g. supplied by the
    build) fills in / overrides addresses not pinned in the C.  tiny_cc has no
    project-specific symbol table of its own.

    Returns dict name -> (base_addr, bytes).
    """
    global SYMS, PASCAL, UCHAR_FUNCS
    decls = parse(lex(src))
    syms, unsigned, pascal, uchar_funcs = build_syms(decls, addr_map or {})
    saved, saved_p, saved_u = SYMS, PASCAL, UCHAR_FUNCS
    SYMS = syms
    PASCAL = pascal
    UCHAR_FUNCS = uchar_funcs
    try:
        out = {}
        for d in decls:
            if d[0] != 'func':
                continue
            name, args, body = d[1], d[2], d[3]
            if name not in SYMS or SYMS[name][0] not in ('func', 'far_func'):
                continue
            base = SYMS[name][1]
            cg = CG(base, unsigned)
            cg.emit_func(args, body)
            out[name] = (base, bytes(cg.buf))
        return out
    finally:
        SYMS = saved
        PASCAL = saved_p
        UCHAR_FUNCS = saved_u


def dump(bs, base):
    for i in range(0, len(bs), 16):
        chunk = bs[i:i + 16]
        print(f'{base + i:04X}: ' + ' '.join(f'{b:02X}' for b in chunk))


def main():
    if len(sys.argv) < 2:
        print('usage: tiny_cc.py FILE.c [--rom ROM]', file=sys.stderr)
        sys.exit(1)
    src = open(sys.argv[1]).read()
    results = compile_src(src)        # addresses come from __addr__ in the C
    rom = None
    if '--rom' in sys.argv:
        rom = open(sys.argv[sys.argv.index('--rom') + 1], 'rb').read()
    exit_code = 0
    for name, (base, bs) in results.items():
        print(f'; --- {name} @ 0x{base:04X}  ({len(bs)} bytes) ---')
        dump(bs, base)
        if rom is not None:
            exp = rom[base:base + len(bs)]
            n = sum(1 for x, y in zip(bs, exp) if x == y)
            ok = (bs == exp)
            print(f'  {n}/{len(bs)} bytes match'
                  + ('  — perfect' if ok else '  — DIVERGENCE'))
            if not ok:
                for i, (x, y) in enumerate(zip(bs, exp)):
                    if x != y:
                        print(f'  first divergence @ {base + i:04X}: '
                              f'got {x:02X}, expected {y:02X}')
                        break
                exit_code = 2
        print()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
