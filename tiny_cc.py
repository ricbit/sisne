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

import os
import re
import sys

# Per-compile symbol table {name: (kind, addr)}, populated by compile_src()
# from the C declarations (`__addr__(N)` + kinds) and any supplied address
# map.  tiny_cc carries no project-specific symbols of its own.
SYMS = {}
PASCAL = set()  # names of callee-cleaned (pascal) functions
UCHAR_FUNCS = set()  # names of functions whose return is `unsigned char` (AL)
LONG_FUNCS = set()  # names of functions whose return is `long`/`ulong` (DX:AX)
BYTE_PARAMS = {}  # func name -> per-parameter byte-width flags (uchar params)
FAR_PARAMS = {}  # func name -> per-parameter far-pointer flags (`T far *p`)

KW = {
    'int',
    'unsigned',
    'char',
    'long',
    'void',
    'return',
    'while',
    'if',
    'else',
    'extern',
    'for',
    'register',
    'goto',
    'far',
    'do',
    'break',
    'continue',
    'switch',
    'case',
    'default',
    'pascal',
    'struct',
    'union',
}

# struct tag -> {'__size__': n, field: (offset, type)} — byte-packed layouts
# (MSC /Zp1; the DOS-era records these mirror have words at odd offsets).
# `p->field` desugars at emit_func entry into the same cast+offset AST the rest
# of the codegen already handles, so member access is byte-identical to the
# explicit `*(T far *)(p + off)` spelling.
STRUCTS = {}
# extern global name -> declared C type string (the struct tag survives here;
# SYMS keeps only the kind) — lets `->` resolve through struct-ptr GLOBALS.
GLOBTY = {}

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
            out.append(('kw' if w in KW else 'id', w))
            i = j
        elif c.isdigit():
            if c == '0' and i + 1 < n and src[i + 1] in 'xX':
                j = i + 2
                while j < n and src[j] in '0123456789abcdefABCDEF':
                    j += 1
                out.append(('num', int(src[i:j], 16)))
                i = j
            else:
                j = i
                while j < n and src[j].isdigit():
                    j += 1
                out.append(('num', int(src[i:j])))
                i = j
        elif c == "'":
            if src[i + 1] == '\\':
                m = {'n': 10, 't': 9, 'r': 13, '0': 0, '\\': 92, "'": 39}
                out.append(('num', m[src[i + 2]]))
                i += 4
            else:
                out.append(('num', ord(src[i + 1])))
                i += 3
        elif src[i : i + 3] in ('>>=', '<<='):
            out.append(('op', src[i : i + 3]))
            i += 3
        elif src[i : i + 2] in (
            '<=',
            '>=',
            '==',
            '!=',
            '||',
            '&&',
            '++',
            '--',
            '|=',
            '&=',
            '+=',
            '-=',
            '<<',
            '>>',
            '->',
        ):
            out.append(('op', src[i : i + 2]))
            i += 2
        else:
            out.append(('op', c))
            i += 1
    out.append(('end', None))
    return out


# --------- Parser ---------


class Parser:
    def __init__(self, toks):
        self.t, self.p = toks, 0

    def pk(self, o=0):
        return self.t[self.p + o]

    def eat(self):
        r = self.t[self.p]
        self.p += 1
        return r

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
    if t == 'struct':
        # `struct <tag>` — usable only through a pointer (`struct sft far *p`).
        # The type string keeps the tag (`struct:sft`) so `->` can resolve
        # member offsets; startswith('ptr_far') etc. still hold for the pointer.
        base = 'struct:' + p.exp('id')[1]
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
    if t == 'unsigned':
        if p.acc('kw', 'char'):
            base = 'uchar'
        elif p.acc('kw', 'long'):
            base = 'ulong'  # `unsigned long` → 32-bit, unsigned compares
        else:
            p.acc('kw', 'int')  # `unsigned` or `unsigned int`
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
        return 'arr_w' if (ty.startswith('ptr') or wint(ty)) else 'arr'
    if 'far' in ty and ty.startswith('ptr'):
        return 'far_var'
    if ty == 'long':
        return 'long_var'  # 32-bit scalar (low word at addr, high at +2)
    if ty == 'ulong':
        return 'ulong_var'  # 32-bit scalar, unsigned compares
    if ty in ('uchar', 'char'):
        return 'bvar'  # byte scalar global
    if ty == 'uint':
        return 'uvar'  # unsigned scalar → unsigned compares
    if ty.startswith('struct:'):
        # a struct INSTANCE at an absolute address (e.g. the SDA's embedded
        # records): build_syms expands it into one synthetic global per field.
        return ty
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


def _param_group_is_byte(grp):
    """A prototype parameter is a byte value (MSC pushes a numeric literal for it
    as `mov al,N; push ax`) when its type is a plain `char`/`unsigned char` with
    no pointer — `unsigned char count`, not `unsigned char far *fcb`."""
    return any(t == ('kw', 'char') for t in grp) and not any(
        t == ('op', '*') for t in grp
    )


def _param_group_is_far(grp):
    """A prototype parameter is a single far pointer (`T far *p`): a bare near
    address argument (`&global`, an array) passed to it is promoted to a far
    pointer.  A `T far **p` is a NEAR pointer to a far pointer (the `far` governs
    the pointee, not the parameter), so it takes the near address as-is — it must
    NOT match, or `&local_farptr` args would be wrongly pushed far."""
    return any(t == ('kw', 'far') for t in grp) and (
        sum(1 for t in grp if t == ('op', '*')) == 1
    )


def parse_extern(p):
    ty = parse_type(p)
    is_pascal = bool(p.acc('kw', 'pascal'))  # callee-cleaned (ret N) helper
    name = p.exp('id')[1]
    param_bytes = ()
    param_far = ()
    if p.acc('op', '('):
        # Collect each comma-separated parameter group (at paren depth 1) so we
        # know which parameters are byte-width — the rest of the tokens are still
        # discarded (we only need per-param widths, not names).
        groups, grp, depth = [], [], 1
        while depth:
            t = p.pk()
            if t == ('op', '('):
                depth += 1
                grp.append(p.eat())
            elif t == ('op', ')'):
                depth -= 1
                if depth == 0:
                    p.eat()
                else:
                    grp.append(p.eat())
            elif t == ('op', ',') and depth == 1:
                p.eat()
                groups.append(grp)
                grp = []
            else:
                grp.append(p.eat())
        if grp:
            groups.append(grp)
        param_bytes = tuple(_param_group_is_byte(g) for g in groups)
        param_far = tuple(_param_group_is_far(g) for g in groups)
        kind = decl_kind(ty, True, False)
    elif p.acc('op', '['):
        while not p.acc('op', ']'):
            p.eat()
        kind = decl_kind(ty, False, True)
    else:
        kind = decl_kind(ty, False, False)
    addr = parse_addr_suffix(p)
    p.exp('op', ';')
    if kind in ('far_var', 'var', 'uvar') or kind.startswith('struct:'):
        GLOBTY[name] = ty  # keep the type string (`->`/`.` needs the tag)
    return ('extern', name, kind, addr, is_pascal, ty == 'uchar', param_bytes,
            ty in ('long', 'ulong'), param_far)


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
        if nid(p.pk()):
            aname = p.eat()[1]
            args.append((ty, aname))
        p.acc('op', ',')
    addr = parse_addr_suffix(p)  # optional `__addr__(N)` on the def
    body = parse_block(p)
    far_ret = 'far' in ret_ty
    return ('func', name, args, body, addr, far_ret, ret_ty == 'uchar')


def parse_block(p):
    p.exp('op', '{')
    out = []
    while not p.acc('op', '}'):
        out.append(parse_stmt(p))
    return out


def parse_while(p, test_label=None):
    c = parse_paren(p)
    b = parse_block_or_stmt(p)
    return ('while', c, b, test_label)


def parse_stmt(p):
    t = p.pk()
    # A bare `;` is the empty statement — needed so a label can sit at the end
    # of a block (`next_handle: ;` before the closing brace).  Emits nothing.
    if t == ('op', ';'):
        p.eat()
        return ('block', [])
    # IDENT : (label declaration) — peek 2 tokens ahead
    if nid(t) and p.pk(1) == ('op', ':'):
        name = p.eat()[1]
        p.eat()  # consume the colon
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
    if t[0] == 'kw' and t[1] in ('int', 'unsigned', 'char', 'long', 'struct'):
        ty = parse_type(p)
        name = p.exp('id')[1]
        if p.acc('op', '['):  # local array: `T name[N];`
            n = int(p.exp('num')[1])
            p.exp('op', ']')
            p.exp('op', ';')
            return ('localarr', ty, name, n)
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
        c = parse_paren(p)
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
        if p.pk()[1] == ')':
            upd = None
        else:
            upd = parse_expr(p)
            if p.pk() == ('op', ','):  # comma operator in the update clause
                seq = [upd]
                while p.acc('op', ','):
                    seq.append(parse_expr(p))
                upd = ('comma', seq)
        p.exp('op', ')')
        body = parse_block_or_stmt(p)
        return ('for', init, cond, upd, body)
    if p.acc('kw', 'switch'):
        e = parse_paren(p)
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
        c = parse_paren(p)
        th = parse_block_or_stmt(p)
        el = None
        if p.acc('kw', 'else'):
            # `else if (...)` is allowed as a chain; any other else body must brace.
            el = [parse_stmt(p)] if p.pk() == ('kw', 'if') else parse_block_or_stmt(p)
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
    # Braces are required on every block body (if/else/while/for/do); a bare
    # statement is a syntax error.  (`else if` is handled in the if-parser.)
    if p.pk()[1] != '{':
        raise SyntaxError(f'block body must be braced, got {p.pk()}')
    return parse_block(p)


def parse_expr(p):
    return parse_assign(p)


def parse_assign(p):
    l = parse_or(p)
    if p.acc('op', '?'):  # ternary `cond ? a : b` (right-assoc, below assignment)
        a = parse_assign(p)
        p.exp('op', ':')
        b = parse_assign(p)
        return ('ternary', l, a, b)
    if p.acc('op', '='):
        return ('assign', l, parse_assign(p))
    for opc in ('|=', '&=', '+=', '-=', '>>=', '<<='):
        if p.acc('op', opc):
            return ('opassign', opc[:-1], l, parse_assign(p))
    return l


def _blevel(sub, kind, ops):
    """One left-associative binary-precedence level: parse `sub (op sub)*`,
    folding into ('bin'/'cmp', op, l, r) — or the 3-tuple ('or'/'and', l, r)
    for the short-circuit levels.  The whole C precedence ladder below is
    built from this one shape."""

    def f(p):
        l = sub(p)
        while p.pk()[0] == 'op' and p.pk()[1] in ops:
            op = p.eat()[1]
            r = sub(p)
            l = (kind, l, r) if kind in ('or', 'and') else (kind, op, l, r)
        return l

    return f


def uncast(r):
    """Strip no-op near casts (16-bit width) off an expr node."""
    while ncast(r) and 'far' not in r[1] and r[1] != 'long':
        r = r[2]
    return r


def parse_paren(p):
    p.exp('op', '(')
    e = parse_expr(p)
    p.exp('op', ')')
    return e


def parse_unary(p):
    if p.acc('op', '++'):
        return ('preinc', parse_unary(p))
    if p.acc('op', '--'):
        return ('predec', parse_unary(p))
    if p.acc('op', '&'):
        return ('addr', parse_unary(p))
    if p.acc('op', '*'):
        return ('deref', parse_unary(p))
    if p.acc('op', '-'):
        e = parse_unary(p)
        if num(e):
            return ('num', (-e[1]) & 0xFFFF)
        return ('neg', e)
    return parse_post(p)


parse_mul = _blevel(parse_unary, 'bin', ('*', '/', '%'))
parse_add = _blevel(parse_mul, 'bin', ('+', '-'))
parse_shift = _blevel(parse_add, 'bin', ('<<', '>>'))
parse_cmp = _blevel(parse_shift, 'cmp', ('<', '>', '<=', '>=', '==', '!='))
parse_band = _blevel(parse_cmp, 'bin', ('&',))
parse_bitor = _blevel(parse_band, 'bin', ('|',))
parse_and = _blevel(parse_bitor, 'and', ('&&',))
parse_or = _blevel(parse_and, 'or', ('||',))


def parse_post(p):
    n = parse_primary(p)
    while True:
        if p.acc('op', '['):
            i = parse_expr(p)
            p.exp('op', ']')
            n = ('idx', n, i)
        elif p.acc('op', '->'):
            n = ('arrow', n, p.exp('id')[1])
        elif p.acc('op', '.'):
            n = ('dot', n, p.exp('id')[1])
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
    if num(t):
        return ('num', t[1])
    if nid(t):
        # FP_SEG(p) / FP_OFF(p): the segment / offset word of a far pointer.
        if t[1] in ('FP_SEG', 'FP_OFF') and p.pk() == ('op', '('):
            p.eat()
            inner = parse_expr(p)
            p.exp('op', ')')
            return ('fpseg' if t[1] == 'FP_SEG' else 'fpoff', inner)
        # sizeof(type): compile-time constant (byte-packed /Zp1 layout).
        if t[1] == 'sizeof' and p.pk() == ('op', '('):
            p.eat()
            ty = parse_type(p)
            p.exp('op', ')')
            return ('num', _type_size(ty))
        return ('id', t[1])
    if t[1] == '(':
        # Could be a cast `(type) expr` or a parenthesized expr.
        if p.pk()[0] == 'kw' and p.pk()[1] in (
            'int',
            'unsigned',
            'char',
            'long',
            'void',
            'struct',
        ):
            cast_ty = parse_type(p)
            p.exp('op', ')')
            return ('cast', cast_ty, parse_unary(p))
        e = parse_expr(p)
        p.exp('op', ')')
        return e
    raise SyntaxError(f'unexpected {t}')


def _type_size(ty):
    """Byte size of a struct field type (byte-packed, MSC /Zp1)."""
    if pf(ty):
        return 4
    if ty.startswith('ptr'):
        return 2
    if wlong(ty):
        return 4
    if ty in ('char', 'uchar'):
        return 1
    if ty.startswith('struct:'):
        return STRUCTS[ty[7:]]['__size__']
    return 2  # int / uint


def parse_struct_def(p):
    """`struct <tag> { <fields> };` — record the byte-packed layout in STRUCTS.
    Fields: scalar types, far/near pointers, `char name[N]` arrays (layout
    padding), nested `struct X` by value, and anonymous `union { … };` groups
    whose members (plain fields or anonymous `struct { … };` runs) OVERLAY the
    same base offset — the classic DOS WORDREGS/BYTEREGS overlay, e.g.
    `union { unsigned int r_ax; struct { unsigned char r_al; unsigned char
    r_ah; }; };`.  A union advances the layout by its LARGEST member.  Purely a
    naming device: every member lowers to the same offset the raw byte/word
    spelling used, so member access stays byte-identical."""

    def plain_field(fields, off):
        """One `T name[N]?;` field at `off`; returns its size."""
        fty = parse_type(p)
        name = p.exp('id')[1]
        if name in fields:
            # a duplicate silently overwrites the dict entry (wrong offset for
            # every earlier use) — always a bug, even across union members.
            raise SyntaxError(f'duplicate struct field {name!r}')
        size = _type_size(fty)
        if p.acc('op', '['):  # `T name[N]` — N elements
            n = p.exp('num')[1]
            p.exp('op', ']')
            size *= n
            fty = 'arr_' + fty
        p.exp('op', ';')
        fields[name] = (off, fty)
        return size

    p.exp('kw', 'struct')
    tag = p.exp('id')[1]
    p.exp('op', '{')
    fields, off = {}, 0
    while not p.acc('op', '}'):
        if p.acc('kw', 'union'):
            p.exp('op', '{')
            maxsz = 0
            while not p.acc('op', '}'):
                if p.pk() == ('kw', 'struct') and p.pk(1) == ('op', '{'):
                    # anonymous struct member: fields laid sequentially at off
                    p.eat()
                    p.eat()
                    sub = 0
                    while not p.acc('op', '}'):
                        sub += plain_field(fields, off + sub)
                    p.exp('op', ';')
                    maxsz = max(maxsz, sub)
                else:
                    maxsz = max(maxsz, plain_field(fields, off))
            p.exp('op', ';')
            off += maxsz
            continue
        off += plain_field(fields, off)
    p.exp('op', ';')
    fields['__size__'] = off
    STRUCTS[tag] = fields


def parse(toks):
    STRUCTS.clear()
    GLOBTY.clear()
    p = Parser(toks)
    out = []
    while p.pk()[0] != 'end':
        if p.acc('kw', 'extern'):
            out.append(parse_extern(p))
        elif p.pk() == ('kw', 'struct') and p.pk(2) == ('op', '{'):
            parse_struct_def(p)  # definition, emits nothing
        else:
            out.append(parse_function(p))
    return out


def mod8(disp):
    """modrm mod bits for an optional 8-bit displacement."""
    return 0x40 if disp else 0


def d8(disp):
    """Optional disp8 emit-arg tail: (disp,) when non-zero, else empty."""
    return (disp,) if disp else ()


def pf(t):
    return t.startswith('ptr_far') and not t.startswith('ptr_ptr_far')


def s16(n):
    return n if n < 0x8000 else n - 0x10000


def i8(n):
    return -128 <= s16(n) <= 127


def sa(n):
    return SYMS[n][1]


def wint(t):
    return t in ('int', 'uint')


def wlong(t):
    return t in ('long', 'ulong')


def gsym(n, k):
    return n in SYMS and SYMS[n][0] == k


def sk(n, k):
    return SYMS[n][0] == k


def z0(e):
    return e == ('num', 0)


def ni(*a):
    raise NotImplementedError(a)


def fbyte(cg, e):
    return (cg.far_lvalue(e) or (None, None, None))[2] == 'byte'


def sd(base, reg):
    return base if reg == 'si' else base + 1


def rf(reg):
    """modrm reg-field number for a register-var's register."""
    return {'ax': 0, 'bx': 3, 'si': 6, 'di': 7}[reg]


def n12(e):
    return e[1][2]


def n11(e):
    return e[1][1]


def num(e):
    return e[0] == 'num'


def nid(e):
    return e[0] == 'id'


def nbin(e):
    return e[0] == 'bin'


def nderef(e):
    return e[0] == 'deref'


def ncast(e):
    return e[0] == 'cast'


def ncall(e):
    return e[0] == 'call'


def w16(v):
    """Little-endian byte pair of a 16-bit value — the two `db`s of
    every address/immediate word in an emit() arg list."""
    return (v & 0xFF, (v >> 8) & 0xFF)


# --------- Code generator ---------


class CG:
    def __init__(self, base, unsigned=None):
        self.base = base
        self.unsigned = unsigned or set()  # names that compare unsigned
        self.buf = bytearray()
        self.locals = {}  # name -> (positive offset from bp, type)
        self.regvars = {}  # name -> 'si'  (register-allocated locals)
        self.local_size = 0
        self._force_regvar_ax = False  # if-else routes reg-var assigns via AX
        self._force_var_ax = False  # if-else routes word-global assigns via AX
        self.labels = {}  # label -> buf offset
        self.fixups = []  # (buf_offset, label, kind)
        self.counter = 0
        # Live caches: which named local sits in which register.
        self.al = None
        self.ax = None
        self.bx = None
        self.di = None
        self.si = None  # ('gword', name) when SI holds a word global's value
        self.cl = None  # shift count still live in CL (an int amount)
        self.dx = None  # ('hi', name) high word, or ('val16', name)
        self.axdx_var = None  # name whose full 4-byte value is in AX:DX
        self.dx_alias = None  # (dest, src): while dx==('hi',dest) it's src's hi too
        self._deferred_whiles = []  # queued out-of-line while bodies
        self.cxbx_var = None  # name whose full 4-byte value is in CX:BX
        self.esbx = None  # far_var whose data ES:BX currently points at
        self._lbxdx = False  # a long accumulator that migrated to BX:DX
        self._regvar_zero = {}  # reg-var ('si'/'di') -> holds literal 0
        self.uses_di = False
        self._al_arr_store = False  # last store left its byte live in AL
        self._ax_alias = None  # (global, buf_pos) AX also holds this global
        self.uses_si = False
        self._idx_si = set()  # far_vars read once via si-indexing
        self.func_ret_lbl = None
        self.break_lbls = []  # stack of enclosing-loop break targets
        self.continue_lbls = []  # stack of enclosing-loop continue targets
        # Atoms — one tagged record per machine instruction emitted, so the
        # common-tail merge pass can compare branches semantically.
        # Each atom is a tuple (kind, head_bytes, ref) where:
        #   kind in 'raw', 'jmp_short', 'jcc', 'call'
        #   head_bytes = opcode bytes BEFORE any relocation byte
        #   ref = None / label_name (for jmp_short / jcc) / target_addr (for call)
        self.atoms = []

    def is_reg_var(self, name):
        return name in self.regvars

    def _scaled_idx_reg(self):
        """Index register for a single-use scaled far-var subscript
        (`DPB_TABLE[drive].c_dpbo`): SI normally, but DI when SI is already a
        register variable (a loop counter) — MSC's DOS_FN_39_MKDIR keeps the loop
        in SI and puts the DPB entry index in DI.  Returns ('si'|'di', mov_modrm,
        addr_rm) where mov_modrm builds `mov si/di, ax` and addr_rm the base of
        `[es:bx+si/di+disp]`."""
        if 'si' in self.regvars.values():
            return ('di', 0xF8, 0x41)  # mov di,ax ; [es:bx+di+disp]
        return ('si', 0xF0, 0x40)  # mov si,ax ; [es:bx+si+disp]

    def lty(self, e):
        """Type of the local named by an 'id' node ('' when not a local id) —
        the one test behind every is-this-a-local-of-type-T pattern."""
        if self.locid(e):
            return self.lt(e[1])
        return ''

    @staticmethod
    def gkind(e):
        """SYMS kind of the global named by an 'id' node ('' when not)."""
        if nid(e) and e[1] in SYMS:
            return SYMS[e[1]][0]
        return ''

    def byte_global_addr(self, e):
        """Address of a BYTE global operand — a `bvar` id or `arr[const]` into a
        byte array global — else None."""
        if self.gkind(e) == 'bvar':
            return sa(e[1])
        if e[0] == 'idx' and nid(e[1]) and self.gkind(e[1]) == 'arr' and num(e[2]):
            return sa(e[1][1]) + e[2][1]
        return None

    def near_global_addr(self, e):
        """Constant DS-relative address of `&global` / `&global[const]`, else None."""
        if nid(e) and e[1] in SYMS:
            return sa(e[1])
        if e[0] == 'idx' and nid(e[1]) and e[1][1] in SYMS and num(e[2]):
            return sa(e[1][1]) + e[2][1]
        return None

    def rvid(self, e):
        """True for an 'id' node naming a register-allocated (SI/DI) local."""
        return self.locid(e) and self.is_reg_var(e[1])

    def stkid(self, e):
        """True for an 'id' node naming a stack local/param (not a reg var)."""
        return self.locid(e) and not self.is_reg_var(e[1])

    def ensure_bx(self, name):
        """Make sure BX holds the value of pointer-local `name`."""
        # Two tags mean the same thing: a plain name from here, and ('nptr',
        # name) from the `*p` read path.  Both say BX already holds p, so
        # either satisfies the request (FCB_RANDOM_BLOCK_WRITE reads *count
        # and then pushes it, with only bp-relative work in between).
        if self.bx == name or self.bx == ('nptr', name):
            return
        if self.di == name:
            self.emit(0x8B, 0xDF)  # mov bx, di
            self.bx = name
            return
        disp = self.ld(name)
        self.ldbx(disp)  # mov bx, [bp-N]
        self.bx = name

    def far_lvalue(self, node):
        if ncast(node):
            node = node[2]
        """Recognize a far-pointer lvalue and return (base, disp, kind).

        kind is 'byte' or 'word'; `base` is the far-pointer holder (a `far_var`
        global or a far-pointer local/param).  Forms handled:
          BASE[disp]                          → byte at disp
          *(T far *)(BASE + disp)             → sizeof(T) at disp
          *(T far *)BASE                       → sizeof(T) at 0
        Returns None otherwise.
        """

        def is_far(n):
            if not nid(n):
                return False
            nm = n[1]
            if gsym(nm, 'far_var'):
                return True
            return nm in self.locals and pf(self.lt(nm))

        def far_base(n):
            """`n` evaluates to a far pointer — return a base descriptor for
            emit_les (a name, `('chain', inner, disp)` for a far-ptr field
            `*(T far * far *)(inner + disp)`, or `('idx', far_var, index)` for a
            table access `far_var + <index>` whose offset is recomputed each
            use), else None."""
            if is_far(n):
                return n[1]
            # *p where p is a near pointer TO a far pointer (`T far **p`): the far
            # pointer lives in near memory at [p], loaded with `mov bx,[bp+d];
            # les bx,[bx]` and reloaded on every deref (MSC /Od).
            if nderef(n) and nid(n[1]) and self.lty(n[1]).startswith('ptr_ptr_far'):
                return ('nfp', n11(n))
            # far_var + <int index> — DPB-table style entry pointer (the offset
            # is `index + [far_var]`, segment `[far_var+2]`, recomputed inline).
            if nbin(n) and n[1] == '+' and self.gfar(n[2]):
                return ('idx', n[2][1], n[3])
            # <int index> + far_ptr_local — the INT operand written FIRST, so MSC
            # evaluates it first and ADDS the pointer's offset word to it
            # (`mov bx,si; add bx,[bp+d]; mov es,[bp+d+2]`) instead of the les
            # form (PARSE_PATH_WITH_DRIVE's root terminator store).
            if (
                nbin(n)
                and n[1] == '+'
                and nid(n[3])
                and n[3][1] in self.locals
                and pf(self.lt(n[3][1]))
            ):
                return ('lidx', n[3][1], n[2])
            if nderef(n) and ncast(n[1]) and n11(n).startswith('ptr_far_ptr'):
                op = n12(n)
                if nbin(op) and op[1] == '+' and num(op[3]):
                    ib = far_base(op[2])
                    if ib:
                        return ('chain', ib, op[3][1])
                ib = far_base(op)
                if ib:
                    return ('chain', ib, 0)
            return None

        if node[0] == 'idx' and num(node[2]):
            # A far STRUCT-pointer cast with its own base offset — writing
            # `((struct dir_entry far *)(p + 1))->de_attr` lowers to
            # `(cast)(p + 1)[0Bh]`, which is the same far byte as `p[0Ch]`,
            # so fold the cast's offset into the displacement.
            base, extra = node[1], 0
            if ncast(base) and pf(base[1]):
                base, extra = self.split_disp(base[2])
            b = far_base(base)
            if b:
                return (b, node[2][1] + extra, 'byte')
        if nderef(node):
            # *p where p is a far-pointer local/param → element at offset 0
            if is_far(node[1]):
                ty = (
                    self.lt(n11(node))
                    if n11(node) in self.locals
                    else SYMS[n11(node)][0]
                )
                return (
                    n11(node),
                    0,
                    'long' if 'long' in ty else ('word' if 'int' in ty else 'byte'),
                )
            # *(T far *)(base [+ disp]) — but not a far-ptr-to-far-ptr (a base)
            if (
                ncast(node[1])
                and n11(node).startswith('ptr')
                and 'far' in n11(node)
                and not n11(node).startswith('ptr_far_ptr')
            ):
                cast_ty, operand = n11(node), n12(node)
                kind = (
                    'long'
                    if 'long' in cast_ty
                    else 'word' if 'int' in cast_ty else 'byte'
                )
                if nbin(operand) and operand[1] == '+' and num(operand[3]):
                    b = far_base(operand[2])
                    if b:
                        return (b, operand[3][1], kind)
                b = far_base(operand)
                if b:
                    return (b, 0, kind)
        return None

    def near_lvalue(self, node):
        """Recognize a near-pointer deref lvalue `*(T *)(base [+ disp])` where
        `base` is a near pointer local/param (`ptr_*`, not `ptr_far_*`).
        Returns (base_name, byte_disp, kind) with kind 'long' (4 bytes) or
        'word' (2 bytes); None otherwise."""
        if not nderef(node) or not ncast(node[1]):
            return None
        cty = n11(node)
        if cty == 'ptr_long':
            kind = 'long'
        elif cty in ('ptr_uint', 'ptr_int'):
            kind = 'word'
        else:
            return None
        operand, disp = self.split_disp(n12(node))
        if self.lty(operand).startswith('ptr_') and not pf(self.lt(operand[1])):
            return (operand[1], disp, kind)
        return None

    def far_param_subscript(self, node):
        """Recognize `far_ptr_local[int/uchar local]` — a far-pointer param/local
        subscripted by a (non-register) integer local.  Returns
        (ptr_name, index_name, index_ty) or None.  Addressed `[es:bx+si]` with the
        pointer's offset in SI (via `les si`) and the index in BX — the mirror of
        far_indexed_reg (base in BX, index in a SI/DI reg-var)."""
        if (
            node[0] == 'idx'
            and pf(self.lty(node[1]))
            and self.stkid(node[2])
            and self.lt(node[2][1]) in ('int', 'uint', 'uchar')
        ):
            return (n11(node), node[2][1], self.lt(node[2][1]))
        return None

    def _emit_far_param_index(self, ptr, idx_name, idx_ty):
        """Set up ES:SI = far pointer `ptr`, BX = index `idx_name`, for an
        `[es:bx+si]` access: `<index → BX>; les si,[bp+ptr]`."""
        d = self.ld(idx_name)
        if idx_ty == 'uchar':
            self.emit(0x8A, 0x5E, d)  # mov bl, [bp+d]
            self.emit(0x2A, 0xFF)  # sub bh, bh
        else:
            self.ldbx(d)  # mov bx, [bp+d]
        pd = self.ld(ptr)
        self.emit(0xC4, 0x76, pd)  # les si, [bp+pd]
        self.bx = self.esbx = None

    def fv_gword_idx(self, e):
        """('idx', far_var, word-global[++] [+ const]) -> (fv, g, disp, postinc)
        or None.  postinc is True for `far_var[gword++ + const]` (the index loads
        SI, then the global is bumped in memory — FIND_NEXT_CHAR_MATCH's scan)."""
        if e[0] != 'idx' or not nid(e[1]) or not self.gfar(e[1]):
            return None
        idx, disp = self.split_disp(e[2])
        if idx[0] == 'postinc' and nid(idx[1]) and self.gvw(idx[1]):
            return (n11(e), idx[1][1], disp, True)
        if nid(idx) and self.gvw(idx):
            return (n11(e), idx[1], disp, False)
        return None

    def far_indexed_reg(self, node):
        """Recognize `far_X[reg_var]` — a far pointer (a far_var global OR a
        far-pointer param/local) indexed by a register variable (SI/DI).  Returns
        (name, 'si'|'di') or None.  Element addressed `[es:bx+si/di]` after
        `les bx,[name]` (emit_les loads [addr] for a global, [bp+disp] for a
        param/local)."""
        if node[0] == 'idx' and self.rvid(node[2]):
            b = node[1]
            if nid(b):
                n = b[1]
                if (gsym(n, 'far_var')) or (n in self.locals and pf(self.lt(n))):
                    return (n, self.regvars[node[2][1]])
            # `(far_var + <index>)[reg]` — a scaled table-ENTRY byte base
            # (`DPB_TABLE[drive].c_path[si]`): emit_les rebuilds the entry
            # pointer from the `('idx', far_var, index)` recompute descriptor.
            elif nbin(b) and b[1] == '+' and self.gfar(b[2]):
                return (('idx', b[2][1], b[3]), self.regvars[node[2][1]])
        return None

    def far_reg_idx(self, node):
        """Recognize a far-pointer subscript by a register var with an optional
        `+/- const` displacement folded into `[es:bx+reg+disp]`, and an optional
        pre/post increment of the reg var.  Returns
        (name, 'si'|'di', disp, reg_name, pre, post) or None.  A bare
        `far_X[reg]` (disp 0, no inc) is left to far_indexed_reg — this only
        fires for the `far_X[reg±c]` / `far_X[++reg]` / `far_X[reg++]` shapes
        (TRIM_TRAILING_NAME_SPACES' ripple shift)."""
        if node[0] != 'idx' or not nid(node[1]):
            return None
        n = n11(node)
        if not (gsym(n, 'far_var') or (n in self.locals and pf(self.lt(n)))):
            return None
        idx = node[2]
        disp, pre, post, reg_node = 0, False, False, None
        if idx[0] == 'preinc' and self.rvid(idx[1]):
            pre, reg_node = 'inc', idx[1]
        elif idx[0] == 'predec' and self.rvid(idx[1]):
            pre, reg_node = 'dec', idx[1]
        elif idx[0] == 'postinc' and self.rvid(idx[1]):
            post, reg_node = 'inc', idx[1]
        elif nbin(idx) and idx[1] in ('+', '-') and self.rvid(idx[2]) and num(idx[3]):
            disp = idx[3][1] if idx[1] == '+' else -idx[3][1]
            reg_node = idx[2]
        else:
            return None
        return (n, self.regvars[reg_node[1]], disp & 0xFF, reg_node[1], pre, post)

    def _push_bx_word(self, disp):
        """push word [bx+disp] (disp 0 uses the no-displacement encoding)."""
        if disp:
            self.emit(0xFF, 0x77, disp)
        else:
            self.emit(0xFF, 0x37)

    def emit_les(self, base):
        """Ensure ES:BX points at `base`'s data.  A far-pointer local loads
        with `les bx, [bp+disp]`; a far_var global with `les bx, [addr]`; a
        `('chain', inner, disp)` is a far-pointer field — load `inner`, then
        `les bx, [es:bx+disp]`."""
        # ('idx', far_var, index): a table-entry pointer whose offset is
        # recomputed each use — `<index> → AX; mov bx,ax; add bx,[off]` — with the
        # segment loaded into ES only when ES doesn't already hold it (MSC keeps a
        # live segment across adjacent entry reads but reloads after a branch).
        if isinstance(base, tuple) and base[0] == 'idx':
            _, name, index = base
            off = sa(name)
            self.expr_to_ax(index)  # index → AX
            self.emit(0x8B, 0xD8)  # mov bx, ax
            self.emit(0x03, 0x1E, *w16(off))  # add bx, [off]
            if self.esbx != ('seg', name):
                self.emit(0x8E, 0x06, *w16(off + 2))  # mov es,[off+2]
            self.esbx = ('seg', name)  # ES holds far_var's segment; BX transient
            self.bx = None
            self.cxbx_var = None
            return
        # ('lidx', far_ptr_local, index): the local-pointer mirror of the table
        # split form above — the index (written first in the source sum) lands in
        # BX, the pointer's offset word is added, ES loaded from the frame.
        if isinstance(base, tuple) and base[0] == 'lidx':
            _, name, index = base
            d = self.ld(name)
            if self.rvid(index):
                self.emit(0x8B, 0xD8 | rf(self.rv(index)))  # mov bx, si/di
            else:
                self.expr_to_ax(index)  # index → AX
                self.emit(0x8B, 0xD8)  # mov bx, ax
            self.emit(0x03, 0x5E, d)  # add bx, [bp+d]
            self.emit(0x8E, 0x46, (d + 2) & 0xFF)  # mov es, [bp+d+2]
            self.esbx = name  # ES holds the pointer's segment; BX transient
            self.bx = None
            self.cxbx_var = None
            return
        if self.esbx == base and self.bx == base:
            return
        # ES:SI already points at `base` (a preceding `les si` reserved BX for an
        # array index): the segment is shared, so only the offset is copied —
        # `mov bx,si` (JOIN's two SUBST_TABLE stores and the final AL writeback).
        if getattr(self, 'essi', None) == base:
            self.emit(0x8B, 0xDE)  # mov bx, si
            self.esbx = self.bx = base
            self.cxbx_var = None
            return
        # ES still points at `base` but BX was clobbered → reload only BX, keep ES
        # (matches MSC reusing a live segment register: `mov bx,[bp+disp]`).
        if self.esbx == base and not isinstance(base, tuple) and base in self.locals:
            disp = self.ld(base)
            self.ldbx(disp)  # mov bx, [bp+disp]
            self.bx = base
            self.cxbx_var = None
            return
        if isinstance(base, tuple) and base[0] == 'chain':
            # The inner base picks its own addressing: a scaled table entry keeps
            # the table's ES:BX and indexes through SI, so the far pointer comes
            # out with `les bx,[es:bx+si+d]` and no table reload
            # (FCB_BIT15_CHECK reading DPB_TABLE[i].c_dpb at 0x8246).
            # The index register is re-materialised for the chained load even
            # though ES:BX survives — MSC re-muls per ACCESS here, because the
            # `les` about to run destroys the entry base it is reading from.
            self.si = self.di = None
            rm, dsp = self.far_rm(base[1], base[2])
            self.e26(0xC4, rm | 0x18, *dsp)  # les bx, [<inner>+disp]
            self.esbx = base
            self.bx = None
            return
        # ('nfp', name): far pointer held in near memory at pointer-local `name`.
        # MSC reloads it on every dereference (so ES:BX isn't cached afterwards) —
        # but skips the `mov bx,[bp+disp]` when BX still holds the pointer from a
        # just-emitted store `*name = …` (return_dpb_ptr's far** store then deref).
        if isinstance(base, tuple) and base[0] == 'nfp':
            if self.bx != base[1]:
                self.ldbx(self.ld(base[1]))  # mov bx, [bp+disp]
            self.emit(0xC4, 0x1F)  # les bx, [bx]
            self.esbx = self.bx = None
            self.cxbx_var = None
            return
        if base in self.locals:
            disp = self.ld(base)
            self.emit(0xC4, 0x5E, disp)  # les bx, [bp+disp]
        else:
            addr = sa(base)
            self.emit(0xC4, 0x1E, *w16(addr))  # les bx, [addr]
        self.esbx = self.bx = base
        self.cxbx_var = None

    def clob(self):
        """Forget every live register cache (call / merge-point boundary)."""
        self.al = self.ax = self.bx = self.dx = self.esbx = None
        self.essi = None
        self._bh_zero = False
        self.axdx_var = self.cxbx_var = None

    def invalidate_mem(self, name):
        """A store to local `name` invalidates any reg cached against it."""
        if self.al == name:
            self.al = None
        if self.ax == name:
            self.ax = None
        if self.bx == name:
            self.bx = None
        if self.di == name:
            self.di = None
        if self.dx in (('hi', name), ('val16', name)):
            self.dx = None
        if self.axdx_var == name:
            self.axdx_var = None
        if self.cxbx_var == name:
            self.cxbx_var = None

    def emit(self, *bs):
        """Emit one non-relocating machine instruction (args are masked to
        bytes here, so call sites pass raw disp/imm values)."""
        bs = tuple(b & 0xFF for b in bs)
        self.atoms.append(('raw', bs, None))
        self.buf.extend(bs)

    def emit_jmp_short(self, label):
        """Emit `jmp short LABEL` (2 bytes) as one atom."""
        self.atoms.append(('jmp_short', (0xEB,), label))
        self.buf.append(0xEB)
        self.fixups.append((len(self.buf), label, 'rel8'))
        self.buf.append(0)

    def emit_cc(self, cop, taken, unsigned, label):
        """jcc() + emit_jcc() in one call — every compare leaf ends here."""
        self.emit_jcc(self.jcc(cop, taken, unsigned), label)

    def emit_jcc(self, opcode, label):
        """Emit `Jcc rel8` (2 bytes) as one atom."""
        self.atoms.append(('jcc', (opcode,), label))
        self.buf.append(opcode)
        self.fixups.append((len(self.buf), label, 'rel8'))
        self.buf.append(0)

    def emit_call(self, target_addr):
        """Emit `call near ADDR` (3 bytes) as one atom; bake the disp now."""
        self.made_call = True
        self.cl = None  # a callee may clobber CL
        self.atoms.append(('call', (0xE8,), target_addr))
        call_at = len(self.buf)
        self.buf.append(0xE8)
        self.buf.extend([0, 0])
        d = target_addr - (self.base + call_at + 3)
        self.buf[call_at + 1] = d & 0xFF
        self.buf[call_at + 2] = (d >> 8) & 0xFF

    @staticmethod
    def atom_len(atom):
        kind, head, ref = atom
        if kind == 'raw':
            return len(head)
        if kind in ('jmp_short', 'jcc'):
            return len(head) + 1
        if kind == 'call':
            return len(head) + 2
        if kind == 'jmp_tbl':  # jmp word [cs:bx+TABLE] — abs16 table address
            return len(head) + 2
        if kind == 'dw_tbl':  # dense switch table: one abs16 word per entry
            return 2 * len(ref)
        raise ValueError(kind)

    # ---- snapshot / extract -----------------------------------------------
    def snapshot(self):
        """Capture full CG state so we can restore after an exploratory emit."""
        return (
            len(self.buf),
            len(self.fixups),
            len(self.atoms),
            self.al,
            self.ax,
            self.bx,
            self.di,
            self.esbx,
            dict(self.labels),
            self.dx,
            self.si,
            self.axdx_var,
            self.cxbx_var,
        )

    def restore(self, snap):
        (buf_n, fix_n, atom_n, al, ax, bx, di, esbx, labels,
         dx, si, axdx_var, cxbx_var) = snap
        del self.buf[buf_n:]
        del self.fixups[fix_n:]
        del self.atoms[atom_n:]
        self.al, self.ax, self.bx, self.di, self.esbx = al, ax, bx, di, esbx
        self.dx, self.si = dx, si
        self.axdx_var, self.cxbx_var = axdx_var, cxbx_var
        self.labels = labels

    def extract(self, snap):
        """Capture everything emitted since snap; then restore state.

        Returns (bytes_, fixups_relative, atoms, new_labels).  Fixup
        offsets and label positions are relative to the start of bytes_,
        so the chunk can be replayed elsewhere.
        """
        buf_n, fix_n, atom_n, prev_labels = snap[0], snap[1], snap[2], snap[8]
        bytes_ = bytes(self.buf[buf_n:])
        fixups_ = [(off - buf_n, lbl, kind) for off, lbl, kind in self.fixups[fix_n:]]
        atoms_ = list(self.atoms[atom_n:])
        # Capture labels created within this chunk so replay can restore them.
        new_labels = {
            n: pos - buf_n
            for n, pos in self.labels.items()
            if n not in prev_labels and pos >= buf_n
        }
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
        at_end = atom_end == len(atoms)

        def in_slice(p):
            return lo <= p < hi or (at_end and p == hi)

        return (
            bytes_[lo:hi],
            [(off - lo, l, k) for off, l, k in fixups if lo <= off < hi],
            list(atoms[atom_start:atom_end]),
            {n: p - lo for n, p in labels.items() if in_slice(p)},
        )

    def fresh(self, p):
        self.counter += 1
        return f'{p}_{self.counter}'

    def lbl_if_used(self, name):
        """Place `name` only if some emitted jump references it (loop break /
        continue labels are optional exits)."""
        if any(l == name for _, l, _ in self.fixups):
            self.lbl(name)

    def lbl(self, name):
        # All labels in this codegen are reachable as JCC targets, so the
        # register cache must be invalidated whenever we land on one.
        self.labels[name] = len(self.buf)
        self.al = self.ax = self.bx = self.di = self.dx = self.esbx = None
        self.axdx_var = self.cxbx_var = self.cl = self.si = self.essi = None
        self._bh_zero = False
        self._ah_zero = False  # AH unknown when reached from a branch
        self._regvar_zero = {}  # reg-var contents unknown at a jump target

    def fix(self, label, kind):
        self.fixups.append((len(self.buf), label, kind))
        self.buf.extend(b'\0' * {'rel8': 1, 'rel16': 2}[kind])

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
            starts.append(p)
            p += self.atom_len(a)
        pos_idx = {sp: i for i, sp in enumerate(starts)}
        pos_idx[p] = len(atoms)
        label_idx = {n: pos_idx[bp] for n, bp in self.labels.items()}

        # Jump threading (MSC's jump-to-jump peephole): a jmp/jcc whose target
        # label is itself a lone unconditional `jmp` can target that jmp's
        # destination directly.  The intermediate jmp stays (it may still be
        # reached by fall-through), so this only rewrites displacements.
        def thread(label, seen):
            idx = label_idx.get(label)
            if (
                idx is not None
                and idx < len(atoms)
                and atoms[idx][0] == 'jmp_short'
                and label not in seen
            ):
                seen.add(label)
                return thread(atoms[idx][2], seen)
            return label

        for i, a in enumerate(atoms):
            if a[0] in ('jmp_short', 'jcc'):
                tgt = thread(a[2], set())
                if tgt != a[2]:
                    atoms[i] = (a[0], a[1], tgt)
            elif a[0] == 'jmp_tbl':
                atoms[i] = (a[0], a[1], thread(a[2], set()))
            elif a[0] == 'dw_tbl':
                # A dense switch's table entries thread too — otherwise a
                # pass-through case keeps a lone `jmp` alive that MSC does not
                # emit, because its table points straight at the destination
                # (CHECK_FILE_ATTR_BITS' selectors 5,6,7,9,10 -> 4B17).
                atoms[i] = (a[0], a[1], [thread(t, set()) for t in a[2]])
        # Dead-jmp elimination (threading's companion): a `jmp` that (a) cannot
        # be reached by fall-through — the previous atom is an unconditional
        # jmp — and (b) whose label(s) no branch targets anymore after
        # threading, is dropped.  MSC never emits it: this is the structural
        # jmp-over-else of a goto-free if/else whose then-arm already exited
        # through a shared tail (dos_fn_45's error arms) — the goto-form
        # source MSC compiled jumps straight to the final target instead.
        while True:
            used = {a[2] for a in atoms if a[0] in ('jmp_short', 'jcc')}
            for a in atoms:  # switch-table refs keep their targets alive
                if a[0] == 'jmp_tbl':
                    used.add(a[2])
                elif a[0] == 'dw_tbl':
                    used.update(a[2])
            dead = None
            for i, a in enumerate(atoms):
                if (
                    i > 0
                    and a[0] == 'jmp_short'
                    # a dense switch's dw table is data — nothing falls out of
                    # it, so a jmp sitting after it is as dead as one after a
                    # jmp (CHECK_FILE_ATTR_BITS' post-switch `return 0`, whose
                    # every reference threaded into the shared block).
                    and (
                        atoms[i - 1][0] == 'jmp_short'
                        # ...and after a dw table only when the jmp lands on the
                        # EPILOGUE: `jmp ret` sitting immediately in front of the
                        # return is something MSC never emits (a switch's break
                        # just falls into it — CHECK_FILE_ATTR_BITS).  With real
                        # code after it the unreachable jmp stays, because MSC
                        # does materialise the break landing (the line editor's
                        # 0xA653 in front of its plain-key dispatch).
                        or (
                            atoms[i - 1][0] == 'dw_tbl'
                            and any(
                                n == self.func_ret_lbl
                                for n, ix in label_idx.items()
                                if ix == i + 1
                            )
                        )
                    )
                    and not any(n in used for n, idx in label_idx.items() if idx == i)
                ):
                    dead = i
                    break
            if dead is None:
                break
            del atoms[dead]
            # Labels at or past the removed atom shift down one slot; a label
            # ON it now names the following atom (same byte position).
            label_idx = {
                n: (idx if idx <= dead else idx - 1) for n, idx in label_idx.items()
            }
        # NOTE: the FALL-THROUGH merge runs FIRST.  A block that falls into the
        # shared label is not a `jmp`-ending predecessor, so it never competes
        # in the jmp/jmp pass below — and if that pass goes first it pairs two
        # jmp-ending blocks with each other instead, leaving one chained through
        # the other (DOS_FN_0F's 57h and 2 error exits, which MSC points at the
        # 0Fh block's `push ax` independently).
        # Fall-through tail merge: a `jmp L` whose preceding instructions coincide
        # with the instructions that fall THROUGH into L shares that copy — the
        # jmp lands earlier, on the shared tail, and its own duplicate copy is
        # dropped.  This is the mirror of the jmp/jmp merge for the case where one
        # predecessor reaches the tail by falling in rather than jumping (DOS_FN_42:
        # the switch default's `result = err` store jumps into the find-fcb-failure
        # arm's identical store, which falls through to the writeback).
        def content_bytes(end, floor):
            """Backward (byte, atom_idx) stream of mergeable content atoms."""
            out = []
            idx = end
            while idx > floor:
                a = atoms[idx]
                if a[0] == 'raw':
                    for b in reversed(a[1]):
                        out.append((('byte', b), idx))
                elif a[0] == 'call':
                    out.append((('call', a[2]), idx))
                elif a[0] == 'jcc':
                    # A conditional counts too, compared symbolically by
                    # (opcode, resolved target) — MSC shares a `jcc X` together
                    # with the block it falls into, and a later site reaches
                    # BOTH by jumping at the conditional
                    # (CHECK_FILE_ATTR_BITS' `if (c) return 1; return 0;`
                    # tails all entering one copy at 4B15 / 4B55).
                    out.append(((a[0], a[1], label_idx.get(a[2])), idx))
                else:
                    break
                idx -= 1
            return out

        while True:
            merged = False
            for J, a in enumerate(atoms):
                if a[0] != 'jmp_short':
                    continue
                L = label_idx.get(a[2])
                # L must be reached by fall-through from a mergeable atom.
                if L is None or L <= 0 or atoms[L - 1][0] not in (
                    'raw',
                    'call',
                    'jcc',
                ):
                    continue
                # A jmp to ITSELF is an infinite loop, not one of two
                # predecessors of a shared tail: with L == J the two candidate
                # regions below are the same span, so they match all the way to
                # the top of the function and the "merge" would delete it.
                # (MAIN_ENTRY ends in `jmp short $` after its fatal error.)
                if L == J:
                    continue
                # A (jmp side, content above the jmp) and B (fall-in side).  For a
                # backward jmp (J > L) floor A at L so it can't consume B's region;
                # a forward jmp's A and B are naturally disjoint (A < J < B).
                A = content_bytes(J - 1, (L - 1) if J > L else -1)
                B = content_bytes(L - 1, J if L > J else -1)
                m = 0
                while m < len(A) and m < len(B) and A[m][0] == B[m][0]:
                    m += 1
                while m > 0 and not (
                    (m == len(A) or A[m][1] != A[m - 1][1])
                    and (m == len(B) or B[m][1] != B[m - 1][1])
                ):
                    m -= 1
                # Count the shared run in BYTES, not items: a raw item is one
                # byte, a call three, a conditional two.  Dropping the run plus
                # this site's own jmp and inserting one jmp saves exactly that
                # many bytes, so any run of >= 2 is a win.
                def _isz(it):
                    return 3 if it[0] == 'call' else (2 if it[0] == 'jcc' else 1)

                if sum(_isz(A[k][0]) for k in range(m)) < 2:
                    continue
                sstart = B[m - 1][1]  # survivor's shared-tail start atom
                tstart = A[m - 1][1]  # truncated block's shared-tail start atom
                name = next((n for n, ix in label_idx.items() if ix == sstart), None)
                # drop the truncated copy (its shared atoms + the jmp) and point a
                # single jmp at the survivor
                del atoms[tstart : J + 1]
                atoms.insert(tstart, ('jmp_short', (0xEB,), name or '__xfall__'))
                shift = J - tstart  # atoms removed net of the inserted jmp
                if sstart > J:
                    sstart -= shift
                for n in list(label_idx):
                    if label_idx[n] > J:
                        label_idx[n] -= shift
                if name is None:
                    self.counter += 1
                    name = f'xfall_{self.counter}'
                    label_idx[name] = sstart
                    atoms[tstart] = ('jmp_short', (0xEB,), name)
                merged = True
                break
            if not merged:
                break
        # A `jcc` left sitting over a lone `jmp short` collapses to the inverted
        # `jcc` — `jz $+2; jmp T` IS `jnz T`.  This shape only appears once a
        # tail merge above has replaced a whole block with a single jmp, so the
        # pass has to run after them (PROCESS_DRIVER_REQUEST's two `status = 5`
        # stores, whose earlier copy merges into the later one at 0x61C3).
        while True:
            used = {a[2] for a in atoms if a[0] in ('jmp_short', 'jcc')}
            for a in atoms:
                if a[0] == 'jmp_tbl':
                    used.add(a[2])
                elif a[0] == 'dw_tbl':
                    used.update(a[2])
            hit = None
            for i, a in enumerate(atoms):
                if (
                    a[0] == 'jcc'
                    and i + 1 < len(atoms)
                    and atoms[i + 1][0] == 'jmp_short'
                    and label_idx.get(a[2]) == i + 2
                    # nothing may jump INTO the jmp about to be deleted
                    and not any(
                        n in used for n, ix in label_idx.items() if ix == i + 1
                    )
                ):
                    hit = i
                    break
            if hit is None:
                break
            atoms[hit] = ('jcc', (atoms[hit][1][0] ^ 1,), atoms[hit + 1][2])
            del atoms[hit + 1]
            label_idx = {
                n: (ix if ix <= hit else ix - 1) for n, ix in label_idx.items()
            }
        # MSC cross-jumping: two `jmp`-ending predecessors of one label whose
        # instruction tails coincide share a single copy — the LATER block is
        # truncated to its unique prefix plus a jmp into the survivor's tail
        # (DOS_FN_44's error funnels).  Greedy longest pair first (the 1-arg
        # LOOKUP_ERROR_MSG bodies pair with each other before either pairs
        # with the 2-arg block's shorter store+jmp tail), iterated to a fixed
        # point.  When exactly one side's tail is a whole basic block (its run
        # start is a jump target or falls right after a branch), that side
        # survives regardless of order — the other side jumps into it.
        def side_items(end, floor):
            """Backward item stream from atom `end`: raw atoms flatten to
            per-byte items (grouping-agnostic), branches/calls are symbolic
            single items.  Stops above `floor` (overlap guard) or at a
            non-mergeable atom.  items[0] is the final jmp."""
            items = []
            idx = end
            while idx > floor:
                a = atoms[idx]
                if a[0] == 'raw':
                    for b in reversed(a[1]):
                        items.append((('byte', b), idx))
                elif a[0] == 'call':
                    items.append((('call', a[2]), idx))
                elif a[0] in ('jmp_short', 'jcc'):
                    items.append(((a[0], a[1], label_idx.get(a[2])), idx))
                else:
                    break
                idx -= 1
            return items

        while True:
            preds = {}
            for i, a in enumerate(atoms):
                if a[0] == 'jmp_short':
                    preds.setdefault(label_idx.get(a[2]), []).append(i)
            target_idx = set(label_idx.values())

            def boundary(i, k):
                s = i - k + 1
                return s in target_idx or s == 0 or atoms[s - 1][0] in (
                    'jmp_short',
                    'jcc',
                )

            def atom_starts(items):
                """Item counts m at which the split falls on an atom boundary,
                mapped to the number of atoms consumed."""
                starts = {}
                for m in range(1, len(items) + 1):
                    if m == len(items) or items[m][1] != items[m - 1][1]:
                        starts[m] = None  # filled by caller via idx delta
                return starts

            best = None  # (nbytes, i, j, ki, kj)
            for ps in preds.values():
                for x in range(len(ps)):
                    for y in range(x + 1, len(ps)):
                        i, j = ps[x], ps[y]
                        A = side_items(i, -1)
                        B = side_items(j, i)  # later side must stay above i
                        m = 0
                        while m < len(A) and m < len(B) and A[m][0] == B[m][0]:
                            m += 1
                        # largest common length landing on atom boundaries on
                        # BOTH sides
                        while m > 0 and not (
                            (m == len(A) or A[m][1] != A[m - 1][1])
                            and (m == len(B) or B[m][1] != B[m - 1][1])
                        ):
                            m -= 1
                        if m == 0:
                            continue
                        ki = i - A[m - 1][1] + 1
                        kj = j - B[m - 1][1] + 1
                        if ki >= 2 and kj >= 2 and (best is None or m > best[0]):
                            best = (m, i, j, ki, kj)
            if best is None:
                break
            _, i, j, ki, kj = best
            bi, bj = boundary(i, ki), boundary(j, kj)
            # A shared tail that is PURE CONTROL FLOW — just a conditional and
            # the jmp, no instruction bytes of its own — is kept at the LATER
            # site and the earlier one jumps forward into it
            # (CHECK_FILE_ATTR_BITS' `if (c) return 1; return 0;` case tails).
            # With real content in the run MSC keeps the earlier copy.
            # Two SWITCH-TABLE case bodies that share a tail keep the LATER
            # copy, with the earlier one jumping forward into it — the opposite
            # of the general rule (the line editor's 77h/75h arms converging on
            # one `call EDIT_TEMPLATE_PROCESS`).  Elsewhere (DOS_FN_42's shared
            # error store) the earlier copy survives.
            tbl_lbls = self._switch_case_lbls

            def in_table_case(start):
                for k in range(start, -1, -1):
                    names = [n for n, ix in label_idx.items() if ix == k]
                    if names:
                        return any(n in tbl_lbls for n in names)
                return False

            both_cases = tbl_lbls and in_table_case(i - ki + 1) and in_table_case(
                j - kj + 1
            )
            _A = side_items(i, -1)  # recompute for the CHOSEN pair
            ctrl_only = all(
                _A[k][0][0] in ('jcc', 'jmp_short') for k in range(best[0])
            )
            if (bj and not bi) or ctrl_only or both_cases:
                surv, ksurv, trunc, ktrunc = j, kj, i, ki
            else:
                surv, ksurv, trunc, ktrunc = i, ki, j, kj
            spos = surv - ksurv + 1
            tstart = trunc - ktrunc + 1
            name = next((n for n, idx in label_idx.items() if idx == spos), None)
            if name is None:
                self.counter += 1
                name = f'xjmp_{self.counter}'
            # labels inside the truncated run alias into the survivor's copy
            aliases = [
                (n, idx - tstart)
                for n, idx in label_idx.items()
                if tstart <= idx <= trunc
            ]
            del atoms[tstart : trunc + 1]
            atoms.insert(tstart, ('jmp_short', (0xEB,), name))
            shift = ktrunc - 1
            if spos > trunc:
                spos -= shift
            for n in list(label_idx):
                if label_idx[n] > trunc:
                    label_idx[n] -= shift
            label_idx[name] = spos
            for n, rel in aliases:
                if n != name:
                    label_idx[n] = spos + rel

        # A `jmp` whose target is the atom immediately AFTER it is a no-op —
        # MSC falls through instead (the line editor's plain-key switch, whose
        # default lands on the very next instruction).  A label sitting on the
        # jmp keeps the same byte position once it is gone.
        while True:
            hit = None
            for i, a in enumerate(atoms):
                if a[0] != 'jmp_short':
                    continue
                tix = label_idx.get(a[2])
                if tix is not None and tix > i and not sum(
                    self.atom_len(atoms[k]) for k in range(i + 1, tix)
                ):
                    hit = i
                    break
            if hit is None:
                break
            del atoms[hit]
            label_idx = {
                n: (ix if ix <= hit else ix - 1) for n, ix in label_idx.items()
            }
        near = set()

        def alen(i):
            k = atoms[i][0]
            if k == 'jmp_short':
                return 3 if i in near else 2
            if k == 'jcc':
                return 5 if i in near else 2
            return self.atom_len(atoms[i])

        while True:
            starts, p = [], 0
            for i in range(len(atoms)):
                starts.append(p)
                p += alen(i)
            apos = starts + [p]
            changed = False
            for i, a in enumerate(atoms):
                if a[0] in ('jmp_short', 'jcc') and i not in near:
                    d = apos[label_idx[a[2]]] - (starts[i] + 2)
                    if not -128 <= d <= 127:
                        near.add(i)
                        changed = True
            if not changed:
                break
        starts, p = [], 0
        for i in range(len(atoms)):
            starts.append(p)
            p += alen(i)
        apos = starts + [p]
        self.labels = {n: apos[idx] for n, idx in label_idx.items()}
        buf = bytearray()
        for i, (kind, head, ref) in enumerate(atoms):
            if kind == 'raw':
                buf.extend(head)
            elif kind == 'jmp_tbl':
                buf.extend(head)
                buf += bytes(w16(self.base + apos[label_idx[ref]]))
            elif kind == 'dw_tbl':
                for l in ref:
                    buf += bytes(w16(self.base + apos[label_idx[l]]))
            elif kind == 'call':
                buf.append(0xE8)
                d = ref - (self.base + len(buf) + 2)
                buf += bytes(w16(d))
            elif kind == 'jmp_short':
                tgt = apos[label_idx[ref]]
                if i in near:
                    buf.append(0xE9)
                    d = tgt - (len(buf) + 2)
                    buf += bytes(w16(d))
                else:
                    buf.append(0xEB)
                    buf.append((tgt - (len(buf) + 1)) & 0xFF)
            elif kind == 'jcc':
                tgt = apos[label_idx[ref]]
                if i in near:
                    buf.append(head[0] ^ 1)
                    buf.append(0x03)  # inverted, skip jmp
                    buf.append(0xE9)
                    d = tgt - (len(buf) + 2)
                    buf += bytes(w16(d))
                else:
                    buf.append(head[0])
                    buf.append((tgt - (len(buf) + 1)) & 0xFF)
        self.buf = buf

    def jfalse(self, cond):
        d = self.fresh('done')
        self.cond_jump(cond, d, False)
        return d

    def _flush_deferred_whiles(self):
        """Place queued out-of-line while bodies (see the 'while' deferral in
        stmt): bind the body label, emit the body, and close the back edge to
        the loop test.  A trailing inner while gets its exit branch THREADED
        straight to the outer test (MSC's branch-to-branch elimination — the
        refill loop's `jna` IS the outer back edge in RENAME_FCB)."""
        while self._deferred_whiles:
            body_lbl, body, loop = self._deferred_whiles.pop(0)
            save_peek = self._peek_next
            self.lbl(body_lbl)
            last = body[-1] if body else None
            if (last and last[0] == 'while'
                    and not (num(last[1]) and last[1][1] != 0)):
                self.loop_body(body[:-1], loop, loop, peek=True)
                il = self.fresh('loop')
                self.lbl(il)
                self.cond_jump(last[1], loop, False)  # exit → outer test
                self.loop_body(last[2], loop, il)
                self.emit_jmp_short(il)
            else:
                self.loop_body(body, loop, loop, peek=True)
                self.emit_jmp_short(loop)
            self._peek_next = save_peek

    def loop_body(self, body, brk, cont, peek=False):
        """Emit a loop body inside pushed break/continue label scopes."""
        self.break_lbls.append(brk)
        self.continue_lbls.append(cont)
        if peek:
            self.emit_arms(body)
        else:
            for ss in body:
                self.stmt(ss)
        self.break_lbls.pop()
        self.continue_lbls.pop()

    def arr_off(self, e):
        """`*(T*)(local_array + const)` — the near cast+offset array read."""
        return (
            ncast(e[1])
            and 'far' not in n11(e)
            and nbin(n12(e))
            and n12(e)[1] == '+'
            and self.lty(n12(e)[2]).startswith('arr')
            and num(n12(e)[3])
        )

    def split_terms(self, addends):
        """(summed const, non-const terms) of a flattened `+` term list."""
        return (
            sum(t[1] for t in addends if num(t)) & 0xFFFF,
            [t for t in addends if not num(t)],
        )

    def split_disp(self, x):
        """Split `base + const` into (base, const); plain base gives disp 0."""
        if nbin(x) and x[1] == '+' and num(x[3]):
            return x[2], x[3][1]
        return x, 0

    def gvw(self, e):
        return self.gkind(e) in ('var', 'uvar')

    def gfar(self, e):
        return self.gkind(e) == 'far_var'

    def _gbarr(self, e):
        """Base address of the global byte array named by an 'id' node (None if
        not one) — used by the two-table indexed compare in cond_jump."""
        if nid(e) and self.gkind(e) == 'arr':
            return sa(e[1])
        return None

    def ucharty(self, e):
        return self.lty(e) == 'uchar'

    def locid(self, e):
        return nid(e) and e[1] in self.locals

    def long_opsel(self, op):
        """Zero DX and pick the add/adc vs sub/sbb opcode pair."""
        self.emit(0x2B, 0xD2)  # sub dx, dx
        return (0x01, 0x11) if op == '+' else (0x29, 0x19)

    def wptr(self, e):
        return self.locid(e) and (
            wint(self.lt(e[1])) or self.lt(e[1]).startswith('ptr')
        )

    def addr_loc(self, x):
        return x[0] == 'addr' and nid(x[1]) and n11(x) in self.locals

    def rv(self, e):
        return self.regvars[e[1]]

    def far_int_les(self, e):
        """Recompose a far-long lvalue as its low WORD, les it; disp or None."""
        fl = self.far_lvalue(('deref', ('cast', 'ptr_far_int', n12(e))))
        return self.les_fl(fl) if fl else None

    def les_fl(self, fl):
        base, disp, _ = fl
        self.emit_les(base)
        return disp

    def far_rm(self, base, disp):
        """Address `base + disp` as an ES-relative r/m, emitting whatever setup
        it needs.  A single-use scaled entry indexes `[es:bx+si/di+disp8]`; any
        other base gets `les bx` and `[es:bx(+disp8)]`.  Returns
        (modrm, disp_bytes) with the reg field ZERO — OR in `reg << 3` for a
        register operand or the `/N` extension for a group opcode.  Every
        caller still supplies its own 0x26 prefix via e26()."""
        m = self.idx_si_setup(base)
        if m is not None:
            return m, (disp & 0xFF,)
        self.emit_les(base)
        return mod8(disp) | 0x07, d8(disp)

    def idx_si_setup(self, fv):
        """Set up a single-use scaled far_var entry read: `index → SI/DI;
        les bx,[var]`, returning the `[es:bx+si/di+disp8]` r/m base.  None when
        `fv` isn't one of those (the caller falls back to bx-folded emit_les)."""
        if not (isinstance(fv, tuple) and fv[0] == 'idx' and fv in self._idx_si):
            return None
        _, name, index = fv
        reg, mov_modrm, m = self._scaled_idx_reg()  # SI, or DI if SI is a regvar
        tag = ('idxsi', name, repr(index))
        # A sibling field of the SAME entry read within one EXPRESSION keeps
        # ES:BX and the index register live — read straight from
        # [es:bx+si/di+disp].  Across statements MSC re-evaluates the index
        # (a fresh mul) but keeps ES:BX (LOOKUP_DRIVER_SLOT_FREE reading
        # s_offhi then s_offlo), so the reuse needs the index register tag too.
        if self.esbx == tag and (self.si if reg == 'si' else self.di) == tag:
            return m
        self.expr_to_ax(index)  # index → AX
        self.emit(0x8B, mov_modrm)  # mov si/di, ax
        if self.esbx == tag:
            pass  # ES:BX still address this entry — only the index moved
        elif self.esbx == ('seg', name):
            # ES already holds this table's segment (a preceding entry read) —
            # MSC reloads only the offset word, as after the drive-letter scan.
            self.emit(0x8B, 0x1E, *w16(sa(name)))  # mov bx, [var]
        else:
            self.emit(0xC4, 0x1E, *w16(sa(name)))  # les bx, [var]
        self.ax = self.al = None
        self.bx = ('fvoff', name)  # BX = the table's offset word
        self.esbx = tag
        if reg == 'si':
            self.si = tag
        else:
            self.di = tag
        return m

    def lt(self, n):
        return self.locals[n][1]

    def ldi(self, e):
        return self.ld(n11(e))

    def zaa(self):
        self.ax = self.al = None

    def zad(self):
        self.ax = self.dx = None

    def zaad(self):
        self.ax = self.al = self.dx = None

    def e26(self, *b):
        self.emit(0x26, *b)  # es-prefix emit

    def lea_ax(self, d):
        self.emit(0x8D, 0x46, d)  # lea ax, [bp+d]

    def mvax0(self, n):
        if n == 0:
            self.emit(0x33, 0xC0)  # xor ax, ax
        else:
            self.mvax(n)

    def mvax(self, a):
        self.emit(0xB8, *w16(a))  # mov ax, imm16

    def ldaxm(self, a):
        self.emit(0xA1, *w16(a))  # mov ax, [a]

    def staxm(self, a):
        self.emit(0xA3, *w16(a))  # mov [a], ax

    def ldax(self, d):
        self.emit(0x8B, 0x46, d)  # mov ax, [bp+d]

    def ldal(self, d):
        self.emit(0x8A, 0x46, d)  # mov al, [bp+d]

    def ldbx(self, d):
        self.emit(0x8B, 0x5E, d)  # mov bx, [bp+d]

    def stax(self, d):
        self.emit(0x89, 0x46, d)  # mov [bp+d], ax

    def stal(self, d):
        self.emit(0x88, 0x46, d)  # mov [bp+d], al

    def ld(self, name):
        """Stack displacement of local `name` (lvar without the type)."""
        return self.lvar(name)[0]

    def lvar(self, name):
        off, ty = self.locals[name]
        return -off & 0xFF, ty

    def _regvar_direct_ok(self, rhs):
        """True if `rhs` can be computed straight into a register var (no AX)."""
        if num(rhs):
            return True
        if self._is_rm(rhs):
            return True
        return (
            nbin(rhs) and rhs[1] == '-' and self._is_rm(rhs[2]) and self._is_rm(rhs[3])
        )

    def _regvar_branches_via_ax(self, then_stmts, else_stmts):
        """An if/else whose two arms each assign the SAME register var routes
        BOTH assignments through AX (so the shared `mov reg,ax` tail merges) when
        either arm's value is forced into AX (a far load, call, …).  Returns True
        to force the AX route; False to let each arm compute directly."""

        def reg_assign(stmts):
            if len(stmts) != 1 or stmts[0][0] != 'expr':
                return None
            e = stmts[0][1]
            if e[0] == 'assign' and self.rvid(e[1]):
                return (n11(e), e[2])
            return None

        a, b = reg_assign(then_stmts), reg_assign(else_stmts)
        if a and b and a[0] == b[0]:
            if self._regvar_direct_ok(a[1]) and self._regvar_direct_ok(b[1]):
                return False
            # A CONST arm is `mov reg,imm` either way, so there is no store-tail
            # to merge into: a far WORD load facing one still loads straight into
            # the register (DOS_FN_3B_CHDIR's `pathoff = 3` / `= cds->c_pathoffw`).
            # Two memory loads DO merge via AX (reserve_sector_for_drive).
            if num(a[1]) != num(b[1]):
                far_arm = b[1] if num(a[1]) else a[1]
                if (self.far_lvalue(far_arm) or (None, None, None))[2] == 'word':
                    return False
            return True
        return False

    # sentinel for self.ax/self.al meaning "this register currently holds 0"
    _ZERO = ('\x00zero',)

    def _zero_scalar_assign_target(self, stmt):
        """If `stmt` is `scalar = 0` to a word global, an int|uint|uchar local,
        or a far-word lvalue, return a descriptor; else None.  Used to chain
        consecutive zero stores through one `xor ax,ax` (MSC's peephole).
        Descriptors: ('g',name) ('lw',name) ('lb',name) ('fw',base,disp)."""
        if not stmt or stmt[0] != 'expr':
            return None
        e = stmt[1]
        if e[0] != 'assign' or e[2] != ('num', 0):
            return None
        lhs = e[1]
        if nid(lhs):
            n = lhs[1]
            if gsym(n, 'var'):
                return ('g', n)
            if n in self.locals and not self.is_reg_var(n):
                ty = self.lt(n)
                if wint(ty):
                    return ('lw', n)
                if ty == 'uchar':
                    return ('lb', n)
            return None
        fl = self.far_lvalue(lhs)
        if fl and fl[2] == 'word' and not isinstance(fl[0], tuple):
            return ('fw', fl[0], fl[1])
        return None

    def _branches_assign_same_var(self, then_stmts, else_stmts):
        """Both arms of an if/else are a single `t = <expr>` to the SAME word
        global or int/uint/uchar local → route both through AX so the `mov [t],ax`
        store-tail merges.  Whether the merge fires turns on how a literal 0 is
        stored:
          - word target (var global / int|uint local): a 0 arm stores as
            `mov word [t],0` (C7, not via AX), which breaks the merge — so it
            fires only when NEITHER arm is 0 (a non-zero const goes via `mov
            ax,imm`, a computed arm leaves its result in AX).
          - uchar target: a 0 arm is `xor al,al` (via AL), which ENABLES the
            merge — so it fires only when one arm IS 0 (two non-zero byte
            constants store direct).
        Matches e.g. get_sda_preserved_size (0x14 vs far-deref → merge) and
        WRITE_FCB's `SECTOR_INDEX = … : 0` (a word 0 → no merge, stores direct)."""

        def tgt(stmts):
            # The arm's LAST statement must be `t = <expr>` (earlier statements,
            # e.g. computing the value, are fine — only the trailing store merges).
            if not stmts or stmts[-1][0] != 'expr':
                return None
            e = stmts[-1][1]
            if e[0] != 'assign' or not nid(e[1]):
                return None
            n = n11(e)
            if gsym(n, 'var'):
                return (n, e[2])
            if (
                n in self.locals
                and self.lt(n) in ('int', 'uint', 'uchar')
                and not self.is_reg_var(n)
            ):
                return (n, e[2])
            return None

        a, b = tgt(then_stmts), tgt(else_stmts)
        if not a or not b or a[0] != b[0]:
            return False
        # EXACTLY ONE call-valued arm: the store tails merge only when the
        # NON-call arm also routes its value through AX/AL.  A COMPUTED non-call
        # arm does (DELETE_FCB's `drive = get_current_drive() : path[0]-1` — both
        # store `mov [drive],al`, leaving AL live), so the merge holds; a CONSTANT
        # non-call arm stores direct (`mov [t],imm`), breaking it (dos_fn_5b's
        # `result = 5 : create()`).  Two call arms still merge via AX
        # (resolve_fcb_driver's int24 pair).
        if (ncall(a[1])) != (ncall(b[1])):
            if num(b[1] if ncall(a[1]) else a[1]):
                return False
        has_zero = ('num', 0) in (a[1], b[1])
        if self.locals.get(a[0], (None, None))[1] == 'uchar':
            # uchar: merge unless BOTH arms are non-zero constants (those store
            # direct `mov byte [t],imm`).  A 0 arm (xor al,al) or a computed/AL
            # arm routes through AL, so the store tail merges.  BUT a 16-bit
            # source (a reg-var / uint id, read `mov ax,si` and truncated) paired
            # with a non-zero const does NOT merge — the const stores direct while
            # the wide arm stores AL (PARSE_FILESPEC's `namelen = si : 0x0B`).
            nzc = lambda v: num(v) and v[1] != 0
            wide = lambda v: (nid(v) and (self.is_reg_var(v[1]) or wint(self.lty(v))))
            if (nzc(a[1]) and wide(b[1])) or (nzc(b[1]) and wide(a[1])):
                return False
            # Two constant arms whose bodies are FAR APART (the else-arm has more
            # than just the store) each store direct `mov byte[t],imm` — MSC only
            # shares the `xor;…;mov[t],al` tail for adjacent single-statement arms
            # (DOS_FN_41's `flag_del = 5 : 0` around the big delete body).
            if (
                num(a[1])
                and num(b[1])
                and (len(then_stmts) > 1 or len(else_stmts) > 1)
            ):
                return False
            return not (nzc(a[1]) and nzc(b[1]))
        if not has_zero:
            return True
        # word target: a literal-0 arm stores C7 direct (not via AX); that only
        # breaks the merge when its sibling is computed (a const sibling still
        # goes via `mov ax,imm`, so both stores still merge).  For a word LOCAL,
        # both-const arms store direct in each arm (`mov word [bp+d],imm` /
        # `mov word [bp+d],0`) with no merge at all — read_back_fat_entry's
        # `headflag = 1 : 0`.
        other = b[1] if z0(a[1]) else a[1]
        return num(other) and a[0] not in self.locals

    def _is_rm(self, node):
        """True if node is a 16-bit r/m operand: a non-register local/param or a
        word `var` global (something `mov reg,[mem]` can address directly)."""
        return self.stkid(node) or self.gkind(node) == 'var'

    def _is_local_arr_read(self, e):
        """True if `e` reads `*(T *)(local_array + const)` — a plain [bp-off+const]
        memory operand that doesn't touch ES:BX."""
        return nderef(e) and self.arr_off(e)

    def _emit_rm_op(self, opcode, reg, node):
        """Emit `<op> si/di/bx, <node>` for a local/param ([bp+disp]) or var
        global ([addr]) memory operand."""
        r = rf(reg)
        if node[1] in self.locals:
            disp = self.ld(node[1])
            self.emit(opcode, 0x40 | (r << 3) | 0x06, disp)  # [bp+disp8]
        else:
            a = SYMS[node[1]][1]
            self.emit(opcode, (r << 3) | 0x06, *w16(a))  # [disp16]

    def _mem_rm(self, node):
        """Encode `node` as a memory r/m operand for an instruction whose modrm
        reg field is supplied by the caller.  Returns (prefix, modrm_base, suffix,
        is_byte) where modrm_base has reg field 0 (OR in `reg<<3` or `ext<<3`), or
        None if `node` isn't a simple scalar local / global / far lvalue.  For a
        far operand the `les` is emitted here (prefix is the 0x26 ES override).
          - local/param  → [bp+disp8]   (mod01 rm110)
          - word/byte global → [disp16] (mod00 rm110)
          - far lvalue   → [es:bx(+disp8)]"""
        if self.stkid(node):
            ty = self.lt(node[1])
            if ty in ('uchar', 'char', 'int', 'uint'):
                disp = self.ld(node[1])
                return ((), 0x46, (disp & 0xFF,), ty in ('uchar', 'char'))
            return None
        if nid(node) and node[1] in SYMS:
            k = SYMS[node[1]][0]
            if k in ('var', 'uvar', 'bvar'):
                a = SYMS[node[1]][1]
                return ((), 0x06, w16(a), k == 'bvar')
            return None
        # FP_OFF/FP_SEG(far_local) — the offset word at the far pointer's
        # [bp+disp] slot, or the segment word two bytes above it.
        if node[0] in ('fpoff', 'fpseg') and pf(self.lty(node[1])):
            disp = self.ldi(node) + (2 if node[0] == 'fpseg' else 0)
            return ((), 0x46, (disp & 0xFF,), False)
        # *(T *)(local_struct + const) — a stack struct/array member
        # (DOS_FN_44's pkt.i_status test)
        if nderef(node) and self.arr_off(node):
            d = (self.ld(n12(node)[2][1]) + n12(node)[3][1]) & 0xFF
            return ((), 0x46, (d,), 'char' in n11(node))
        far = self.far_lvalue(node)
        if far:
            base, disp, kind = far
            modrm, dbytes = self.far_rm(base, disp)
            return ((0x26,), modrm, dbytes, kind == 'byte')
        return None

    def _emit_and_test(self, operand, imm):
        """Emit `test <operand>, imm` for an `(operand & imm)` zero-test.  Returns
        True if it emitted (else the caller falls through)."""
        mm = self._mem_rm(operand)
        if not mm:
            return False
        prefix, modrm, suffix, is_byte = mm
        if is_byte:
            self.emit(*prefix, 0xF6, modrm, *suffix, imm)  # test byte,imm8
        else:
            self.emit(*prefix, 0xF7, modrm, *suffix, *w16(imm))
        return True

    def _emit_cmp_imm(self, operand, imm):
        """Emit `cmp <operand>, imm` in memory form (`cmp byte [m],imm8` /
        `cmp word [m],imm8-sx` / `cmp word [m],imm16`) via _mem_rm.  Returns True
        if it emitted (else the caller falls through to a register/cached path)."""
        mm = self._mem_rm(operand)
        if not mm:
            return False
        prefix, modrm, suffix, is_byte = mm
        modrm |= 0x38  # /7 (cmp)
        if is_byte:
            self.emit(*prefix, 0x80, modrm, *suffix, imm)
        else:
            sn = s16(imm)
            if -128 <= sn <= 127:
                self.emit(*prefix, 0x83, modrm, *suffix, imm)
            else:
                self.emit(*prefix, 0x81, modrm, *suffix, *w16(imm))
        return True

    def _emit_cmp_reg(self, operand, regvar):
        """Emit `cmp <operand>, si/di` for a WORD memory operand vs a register
        variable, via _mem_rm.  Returns False for a byte operand / non-lvalue."""
        mm = self._mem_rm(operand)
        if not mm or mm[3]:  # None or byte operand
            return False
        prefix, modrm, suffix, _ = mm
        r = rf(self.regvars[regvar])
        self.emit(*prefix, 0x39, modrm | (r << 3), *suffix)  # cmp <mem>, si/di
        return True

    def _emit_op_reg(self, operand, regvar, op):
        """Emit `add/sub <operand>, si/di` for a WORD memory operand (local,
        FP_OFF(far local), or word global) +=/-= a register var, via _mem_rm.
        Returns False for a byte operand / unsupported lvalue (e.g. long global)."""
        mm = self._mem_rm(operand)
        if not mm or mm[3]:
            return False
        prefix, modrm, suffix, _ = mm
        r = rf(self.regvars[regvar])
        opc = 0x01 if op == '+' else 0x29
        self.emit(*prefix, opc, modrm | (r << 3), *suffix)  # add/sub <mem>, si/di
        return True

    # ---- entry ----
    @staticmethod
    def _fold_scaled_index(body):
        """`base + K*(i-C) [+ D]` → `base + K*i + (D - K*C)`: MSC folds the
        constant part of a scaled subscript into the field displacement, so
        DOS_FN_29's `DPB_TABLE[drive-1].c_flags` reads `[es:bx+di-0Eh]` off a
        `mul` of `drive` itself rather than of `drive-1`."""

        def walk(n):
            if isinstance(n, list):
                return [walk(x) for x in n]
            if not isinstance(n, tuple):
                return n
            # Handle a `+` chain as a whole (before recursing) so the rewritten
            # constant merges with the field displacement in the same pass.
            if nbin(n) and n[1] == '+':
                terms = []

                def flat(x):
                    if nbin(x) and x[1] == '+':
                        flat(x[2])
                        flat(x[3])
                    elif (
                        ncast(x)
                        and pf(x[1])
                        and nbin(x[2])
                        and x[2][1] == '+'
                        and nid(x[2][2])
                        and num(x[2][3])
                    ):
                        # `(T far *)(BASE + const)` inside an address sum is a
                        # byte-level no-op — see through it so the constants can
                        # meet.  `p->b_rec[i].fld` lowers to
                        # `(sft far *)(TBL + 6) + 35h*i + 17h`, which only
                        # resolves as a far_var subscript once 6 and 17h fuse.
                        flat(x[2])
                    else:
                        terms.append(x)

                flat(n)
                delta = 0
                out = []
                for t in terms:
                    if (
                        nbin(t)
                        and t[1] == '*'
                        and num(t[2])
                        and nbin(t[3])
                        and t[3][1] == '-'
                        and num(t[3][3])
                    ):
                        delta -= t[2][1] * t[3][3][1]
                        out.append(('bin', '*', t[2], walk(t[3][2])))
                    else:
                        out.append(walk(t))
                # ...or when flattening simply brought two constants together
                if delta or len([t for t in out if num(t)]) > 1:
                    const = sum(t[1] for t in out if num(t)) + delta
                    out = [t for t in out if not num(t)]
                    if not out:  # everything collapsed into the constant
                        return ('num', const & 0xFFFF)
                    acc = out[0]
                    for t in out[1:]:
                        acc = ('bin', '+', acc, t)
                    return ('bin', '+', acc, ('num', const & 0xFFFF))
            return tuple(walk(x) for x in n)

        return walk(body)

    def _resolve_arrows(self, args, body):
        """Desugar `p->field` into the cast+offset AST the rest of the codegen
        already handles — so member access is byte-identical to the explicit
        `*(T far *)(p + off)` / `p[off]` spelling.  `p` is a struct-pointer
        parameter, local, or extern global; chains resolve through struct-ptr
        FIELDS too (`DPB_PTR->d_driver->dh_attr` lowers the inner arrow to the
        `*(T far * far *)(p + off)` form the ('chain', …) far-base handles)."""
        if not STRUCTS:
            return body
        types = {name: ty for ty, name in args}
        for n in self._nodes(body):
            if n[0] == 'local':
                types[n[2]] = n[1]

        def typestr(node):
            """Full declared type string of a struct(-pointer)-valued expression."""
            if ncast(node):
                return node[1]
            if nid(node):
                return types.get(node[1]) or GLOBTY.get(node[1], '')
            if node[0] == 'idx':
                # An element of an array MEMBER (`p->b_rec[i]`) keeps the
                # container's type string — in particular its far-ness, without
                # which the field cast below would come out near and far_lvalue
                # would not recognise the address (FIND_FREE_DRIVER_SLOT's
                # `DRIVER_TABLE->b_rec[i].s_offhi`).
                return typestr(node[1])
            if node[0] in ('arrow', 'dot'):
                pfx = 'ptr_far_' if 'far' in typestr(node[1]) else 'ptr_'
                fty = STRUCTS[tag_of(node[1])][node[2]][1]
                if fty.startswith('struct:'):
                    return pfx + fty
                # An ARRAY-of-struct member (`b_rec[]`) is reached through the
                # container's pointer, so it inherits its far-ness — without
                # this the element's field cast comes out near and far_lvalue
                # cannot resolve the address.
                if fty.startswith('arr_struct:'):
                    return pfx + fty[4:]
                return fty
            # `p[i]` — a scaled subscript of a struct-pointer table yields the
            # element (struct VALUE): drop one pointer level, keeping far-ness so
            # the access-class check sees it (`DPB_TABLE[drive].c_path[si]`).
            if node[0] == 'idx':
                t = typestr(node[1])
                if t.startswith('ptr_far_'):
                    return 'far_' + t[8:]
                if t.startswith('ptr_'):
                    return t[4:]
                return t
            # `(*p)->fld` — a dereferenced pointer-to-pointer (`T far **p`): drop
            # one pointer level, so `*p` is the inner (far) pointer whose struct
            # the arrow resolves against.
            if node[0] == 'deref':
                t = typestr(node[1])
                return t[4:] if t.startswith('ptr_') else t
            ni('member base', node)

        def tag_of(node):
            """Struct tag of a struct-pointer-valued expression (pre-lowering)."""
            ty = typestr(node)
            i = ty.find('struct:')
            if i < 0:
                raise NameError(f'not a struct pointer: {node!r} ({ty})')
            return ty[i + 7 :]

        def ptr_ty(node):
            """Outermost pointer TYPE string of a cast / id / ptr-arith / member
            expression, or None if it is not a pointer.  Used to scale explicit
            `p + n` arithmetic by sizeof(*p)."""
            if node[0] == 'cast':
                return node[1] if node[1].startswith('ptr') else None
            if nid(node):
                t = types.get(node[1]) or GLOBTY.get(node[1], '')
                return t if t.startswith('ptr') else None
            if node[0] == 'bin' and node[1] in ('+', '-'):
                return ptr_ty(node[2]) or ptr_ty(node[3])
            if node[0] in ('arrow', 'dot'):
                t = STRUCTS[tag_of(node[1])][node[2]][1]
                if t.startswith('ptr_'):
                    return ('ptr_far_' if 'far' in typestr(node[1]) else 'ptr_') + t[4:]
                return None
            # `*p` where p is `T far **` is a `T far *`, so arithmetic on it
            # scales by sizeof(T) — without this the deref yields no pointee
            # type and `*work + i` stays a raw byte offset (WRITE_DIR_ENTRY's
            # directory-entry subscript).
            if nderef(node):
                t = ptr_ty(node[1]) or ''
                return t[4:] if t.startswith('ptr_ptr_') else None
            return None

        def pointee_size(pt):
            """sizeof of the pointee named by pointer-type string `pt`."""
            inner = pt[4:]  # strip 'ptr_'
            if inner.startswith('far_'):
                inner = inner[4:]  # strip 'far_'
            return _type_size(inner)

        def scale(size, idx):
            """`size * idx` as MSC computes it — a power-of-two element size
            becomes a SHIFT (`shl dx,cl`), not a multiply.  sizeof(dir_entry)
            is 20h, so a directory-entry subscript indexes with `<< 5`
            (WRITE_DIR_ENTRY); the 51h/35h table strides keep their `mul`."""
            if size >= 2 and (size & (size - 1)) == 0:
                return ('bin', '<<', idx, ('num', size.bit_length() - 1))
            return ('bin', '*', ('num', size), idx)

        def scaled_base(pidx):
            """`p[i]` (a scaled subscript base for member access) lowers to `p + size*i`."""
            p, i = pidx[1], pidx[2]
            size = STRUCTS[tag_of(p)]['__size__']
            b = rw(p)
            # A struct-ARRAY member base (`q->b_rec`) lowers to a cast over
            # `container + off` — hoist the constant OUT of the scaled sum so
            # the far-address fold sees `container + size*i + off` (the raw
            # spelling's term order) and the member offset lands in the
            # displacement byte, as in `[es:bx+si+1Dh]` (LOOKUP_DRIVER_SLOT).
            if b[0] == 'cast' and nbin(b[2]) and b[2][1] == '+' and num(b[2][3]):
                return (
                    'bin', '+',
                    ('bin', '+', b[2][2], scale(size, rw(i))),
                    b[2][3],
                )
            return ('bin', '+', b, scale(size, rw(i)))

        def padd(e, c):
            """`e + c` with a trailing constant MERGED (never two const tails)."""
            if not c:
                return e
            if nbin(e) and e[1] == '+' and num(e[3]):
                return ('bin', '+', e[2], ('num', e[3][1] + c))
            return ('bin', '+', e, ('num', c))

        def is_base_far(n):
            return 'far' in typestr(n)

        def lower(node):
            """Fully lower one (possibly chained) `->` or `.` node."""
            base, fld = node[1], node[2]
            if (
                nid(base)
                and types.get(base[1]) is None
                and GLOBTY.get(base[1], '').startswith('struct:')
            ):
                return ('id', base[1] + '.' + fld)
            scaled = base[0] == 'idx'
            tag = tag_of(base[1]) if scaled else tag_of(base)
            off, fty = STRUCTS[tag][fld]
            pfx = 'ptr_far_' if is_base_far(base) else 'ptr_'
            lbase = scaled_base(base) if scaled else rw(base)
            if fty in ('char', 'uchar'):
                if not scaled:
                    return ('idx', lbase, ('num', off))
                cast = pfx + 'uchar'
            elif fty in ('int', 'uint', 'long', 'ulong'):
                cast = pfx + fty
            elif fty.startswith('ptr_'):
                cast = pfx + fty  # ptr field → chained ptr-to-ptr cast
            elif fty.startswith('arr_'):
                # `p->arrayfield` decays to a pointer to its first element:
                # `(elem far *)(p + off)` (NO deref) — the same AST the explicit
                # `(elem far *)p + off` byte idiom lowers to.
                addr = padd(lbase, off)
                return ('cast', pfx + fty[4:], addr)
            elif fty.startswith('struct:'):
                addr = padd(lbase, off)
                return ('cast', pfx + fty, addr)
            else:
                ni('arrow field type', fty)
            addr = padd(lbase, off)
            return ('deref', ('cast', cast, addr))

        def rw(n):
            if isinstance(n, list):
                return [rw(s) for s in n]
            if not isinstance(n, tuple):
                return n
            if n[0] in ('arrow', 'dot'):
                return lower(n)
            # Collapse a redundant pointer-over-pointer reinterpret cast
            # `(T far *)(U far *)x` → `(T far *)x`.  The `p + n` scaling above
            # re-wraps a byte cast around its sum, so `*(uint far *)((uchar far
            # *)p + off)` would otherwise nest two pointer casts; the outer
            # target cast wins and the shape matches the single-cast spelling.
            if n[0] == 'cast' and n[1].startswith('ptr'):
                inner = rw(n[2])
                if inner[0] == 'cast' and inner[1].startswith('ptr'):
                    return ('cast', n[1], inner[2])
                return ('cast', n[1], inner)
            # `p->arr[k]` — subscript of a scalar-ARRAY member: the element at
            # `p + off + sizeof(elem)*k`.  A uchar/char array lowers to the raw
            # byte-index form `(p_lowered)[off + k]` (identical to the bare
            # `p[off+k]` spelling); a wider element uses the deref-cast form.
            # (setup_drive_table's `entry->c_path[k]` CDS path bytes.)
            if (
                n[0] == 'idx'
                and n[1][0] in ('arrow', 'dot')
                and STRUCTS[tag_of(n[1][1])][n[1][2]][1].startswith('arr_')
                and not STRUCTS[tag_of(n[1][1])][n[1][2]][1].startswith('arr_struct')
            ):
                off, fty = STRUCTS[tag_of(n[1][1])][n[1][2]]
                elemty = fty[4:]  # 'arr_uchar' -> 'uchar'
                # A scaled struct-table base (`DPB_TABLE[drive].c_path`) folds to
                # `TBL + sizeof*drive` so the far-ptr build sees the raw AST.
                base = (
                    scaled_base(n[1][1]) if n[1][1][0] == 'idx' else rw(n[1][1])
                )
                far = 'far' in (typestr(n[1][1]) or '')
                if elemty in ('char', 'uchar'):
                    if num(n[2]):
                        return ('idx', base, ('num', off + n[2][1]))
                    idxe = rw(n[2])
                    return ('idx', base, ('bin', '+', ('num', off), idxe) if off else idxe)
                elemsz = _type_size(elemty)
                if num(n[2]):
                    addr = ('bin', '+', base, ('num', off + elemsz * n[2][1]))
                else:
                    sc = scale(elemsz, rw(n[2]))
                    addr = ('bin', '+', base, ('bin', '+', ('num', off), sc) if off else sc)
                return ('deref', ('cast', ('ptr_far_' if far else 'ptr_') + elemty, addr))
            # `&p->recs[i]` — address of an element of a struct-ARRAY field
            # (DOS's SFT block: records at +6 striding sizeof(record)):
            # p + sizeof(elem)*i + off, matching the raw
            # `drv + 0x35 * idx + 6` spelling's AST term order.
            if (
                n[0] == 'addr'
                and n[1][0] == 'idx'
                and n[1][1][0] in ('arrow', 'dot')
            ):
                fldnode = n[1][1]
                off, fty = STRUCTS[tag_of(fldnode[1])][fldnode[2]]
                if fty.startswith('arr_struct:'):
                    elem = STRUCTS[fty[11:]]['__size__']
                    s = (
                        'bin', '+', rw(fldnode[1]),
                        scale(elem, rw(n[1][2])),
                    )
                    return ('bin', '+', s, ('num', off)) if off else s
            # `&p[i]` on a struct pointer: the scaled element address itself.
            if (
                n[0] == 'addr'
                and n[1][0] == 'idx'
                and (nid(n[1][1]) or n[1][1][0] in ('arrow', 'dot'))
                and 'struct:' in (typestr(n[1][1]) or '')
            ):
                return scaled_base(n[1])
            # Bare `p[n]` subscript on a STRUCT pointer scales by sizeof(struct)
            # — C semantics, consistent with `p + n`.  The byte-access idiom is
            # `(unsigned char far *)p` (the far→far byte cast stripped, so the
            # codegen byte-indexes it as before).  Scalar-pointer subscripts
            # (int/long/near) are already scaled by the codegen and pass through
            # untouched; `p[i].fld` / `&p[i]` / `p->arr[k]` are handled above.
            if n[0] == 'idx' and n[1][0] not in ('arrow', 'dot'):
                pt = ptr_ty(n[1]) or ''
                pointee = pt[4:]
                if pointee.startswith('far_'):
                    pointee = pointee[4:]
                if (
                    pointee in ('uchar', 'char')
                    and n[1][0] == 'cast'
                    and n[1][1].startswith('ptr_far')
                    and ptr_ty(n[1][2])
                ):
                    return ('idx', rw(n[1][2]), rw(n[2]))  # strip byte cast
                if pointee.startswith('struct:'):
                    size = _type_size(pointee)
                    term = ('num', size * n[2][1]) if num(n[2]) else (
                        scale(size, rw(n[2])))
                    cast = ('ptr_far_' if 'far' in pt else 'ptr_') + pointee
                    return ('deref', ('cast', cast, ('bin', '+', rw(n[1]), term)))
            # Explicit pointer arithmetic `p + n` / `p - n` scales the integer
            # term by sizeof(*p) — C semantics, matching the subscript path.  A
            # byte pointee (char/uchar, sizeof 1) adds no multiply, so the raw
            # byte-offset idiom keeps an `unsigned char far *` operand and lowers
            # unchanged.  A reinterpret cast `(unsigned char far *)structptr` is
            # the size-1 signal: the far→far cast is stripped so the downstream
            # far-address lowering sees the base pointer directly — identical to
            # the pre-scaling AST (`*(T far *)(p + off)`, opassign, etc.).
            if n[0] == 'bin' and n[1] in ('+', '-'):
                lt, rt = ptr_ty(n[2]), ptr_ty(n[3])
                pnode = order = None
                if lt and not rt:
                    pnode, inode, order = n[2], n[3], 'pl'
                elif rt and not lt and n[1] == '+':
                    pnode, inode, order = n[3], n[2], 'pr'
                if pnode is not None:
                    size = pointee_size(ptr_ty(pnode))
                    castwrap = None
                    if (
                        pnode[0] == 'cast'
                        and pnode[1].startswith('ptr_far')
                        and ptr_ty(pnode[2])
                    ):
                        castwrap = pnode[1]  # lift the far→far reinterpret out
                        base = rw(pnode[2])
                    else:
                        base = rw(pnode)
                    # A nested `p + a + b` re-wraps the byte cast around the inner
                    # sum; lift it out again so ONE cast wraps the whole sum.
                    if base[0] == 'cast' and base[1].startswith('ptr_far'):
                        castwrap = base[1]
                        base = base[2]
                    if size == 1:
                        term = rw(inode)
                    elif num(inode):
                        term = ('num', size * inode[1])  # fold sizeof*const
                    else:
                        term = scale(size, rw(inode))
                    summ = ('bin', n[1], base, term) if order == 'pl' else (
                        'bin', '+', term, base)
                    # Re-wrap the reinterpret cast around the whole sum, so
                    # `(uchar far *)p + off` lowers to the `(uchar far *)(p + off)`
                    # AST the arg/assign codegen already emits byte-identically.
                    return ('cast', castwrap, summ) if castwrap else summ
            return tuple(rw(c) for c in n)

        return rw(body)

    def emit_func(self, args, body):
        body = self._resolve_arrows(args, body)
        body = self._fold_scaled_index(body)
        # A trailing bare `return;` is a semantic no-op — control falls into the
        # epilogue either way (C89 allows it even in a value-returning function,
        # documenting a fall-off that returns whatever AX/DX:AX hold, e.g.
        # get_fcb_file_size's error path).  Strip it BEFORE any body-shape
        # analysis so it can't perturb tail-position gating or return-sharing.
        while body and body[-1] == ('return', None):
            body = body[:-1]
        self.func_ret_lbl = self.fresh('func_ret')
        self.made_call = False  # any emitted call forces `mov sp,bp`
        self.return_blocks = {}  # const value -> shared `return K` block label
        self.block_labels = {}  # if-body AST repr -> shared block label
        self.dup_blocks = self._find_dup_if_blocks(body)  # bodies worth cross-jumping
        self.shared_returns = self._find_shared_returns(body)  # value reprs to share
        self.shared_ret_lbls = {}  # value repr -> placed-at-plain label
        self.shared_ret_placed = set()  # value reprs whose block was emitted
        # Functions `f` where `return f(arg)` (one arg) appears >= 2 times: the
        # `push ax; call f; add sp,2; jmp ret` tail is shared, placed at the first
        # occurrence, later ones load their arg into AX and jump to it.  Matches
        # MSC funnelling several `return lookup_error_msg(code)` through one block.
        self._shared_call_tail = self._find_shared_call_returns(body)
        self._call_tail_lbl = {}  # func name -> placed tail label

        # Shared ASSIGNMENT-call tail: `local = f(arg)` (single arg) with the same
        # target local AND function, appearing >= 2 times, share one `push arg;
        # call f; add sp,2; mov[bp-off],al` block placed at the LAST occurrence;
        # earlier ones load arg→AX and jmp forward to it, and their trailing
        # `goto <L>` is absorbed (the shared block falls through to whatever the
        # last occurrence is followed by).  dos_fn_45's two lookup_error_msg exits.
        # Walk every statement list (top level + nested branches/loops), pairing
        # each `local = f(arg)` with its next sibling.  It counts as a shareable
        # EXIT only when that sibling is a goto or a label (or nothing) — i.e. the
        # assignment is a convergent tail, not a step in normal flow (which would
        # wrongly capture invalidate_cached_fcb's loop `ch = read_fcb_path_char`).
        def _stmt_lists(stmts):
            yield stmts
            for s in stmts:
                if s[0] == 'if':
                    yield from _stmt_lists(s[2])
                    if s[3]:
                        yield from _stmt_lists(s[3])
                elif s[0] == 'while':
                    yield from _stmt_lists(s[2])
                elif s[0] == 'for':
                    yield from _stmt_lists(s[4])
                elif s[0] == 'block':
                    yield from _stmt_lists(s[1])

        _sac, _sac_bad = {}, set()
        for stmts in _stmt_lists(body):
            for i, s in enumerate(stmts):
                if (
                    s[0] == 'expr'
                    and s[1][0] == 'assign'
                    and nid(n11(s))
                    and ncall(n12(s))
                    and nid(n12(s)[1])
                    and len(n12(s)[2]) == 1
                ):
                    k = (n11(s[1]), n11(n12(s)))
                    _sac[k] = _sac.get(k, 0) + 1
                    nxt = stmts[i + 1] if i + 1 < len(stmts) else None
                    if nxt and nxt[0] not in ('goto', 'label'):
                        _sac_bad.add(k)
        self._sac_total = {
            k: v for k, v in _sac.items() if v >= 2 and k not in _sac_bad
        }
        self._sac_seen = {k: 0 for k in self._sac_total}
        self._sac_lbl = {}  # key -> shared-block label
        self._sac_suppress_goto = None  # a goto absorbed by a shared-acall jmp
        # Shared terminal-call error funnel: a void 2-arg call `OUTER(arg0, V)`
        # appearing as a terminal statement (followed by `return`, or last in its
        # arm) >= 2 times with an identical FIRST arg funnels through ONE `push
        # ax; push arg0; call OUTER` tail — V carried in AX.  The V = `INNER(code)`
        # exits further share ONE `push ax; call INNER; add sp,2` tail placed at
        # the FIRST such exit; a later one loads its code into AX and jumps in.
        # OUTER/INNER/arg0 are all DISCOVERED, not names baked into the compiler
        # (DOS_FN_4E's set_fcb_handle_or_clear(fcb, lookup_error_msg(code))).
        self._efunnel = self._find_error_funnel(body, _stmt_lists)
        self._efun_suppress = None  # a `return` absorbed by a funnel jmp/tail
        # Shared BYTE-STORE error funnel: `INNER(code); BASE[disp]=K; return`
        # exits share the INNER looktail cascade + one `les bx,[BASE]; mov byte
        # [es:bx+disp],K; jmp epilogue` settail (DELETE_FCB's LOOKUP_ERROR_MSG +
        # `fcb[0]=0xFF`).  The settail sits at the FIRST exit (its looktail falls
        # in); later exits jump back to it.  Detected below, once params/locals
        # are registered (far_lvalue needs them).
        self._bfunnel = None
        self._bfun_suppress_store = None  # a byte store folded into the settail
        self._bfun_suppress_goto = False  # skip the goto after a shared store
        # Shared MULTI-arg return-call tail: >= 2 `return f(a0, …)` (same f,
        # argc >= 2, same leftmost arg) share the final push + call + cleanup
        # + jmp-to-epilogue block; later sites push their differing args and
        # jump into it (READ_NEXT_BUFFER_CHUNK's LOAD_DRIVE).  The two arms of
        # one if/else are excluded — the atom-level mirror suffix-merge owns
        # those (FCB_RANDOM's lookup_error_msg(5,…) pair).
        _nc = {}

        def _rc(st):
            return (
                st[0] == 'return'
                and st[1]
                and ncall(st[1])
                and nid(n11(st))
                and len(n12(st)) >= 2
            )

        def _scan_nc(n):
            if isinstance(n, (list, tuple)):
                if (
                    isinstance(n, tuple)
                    and n
                    and n[0] == 'if'
                    and n[3]
                    and len(n[2]) == 1
                    and len(n[3]) == 1
                    and _rc(n[2][0])
                    and _rc(n[3][0])
                ):
                    return
                if isinstance(n, tuple) and n and n[0] == 'return' and _rc(n):
                    c = n[1]
                    k = (n11(c), len(c[2]), repr(c[2][0]))
                    _nc[k] = _nc.get(k, 0) + 1
                for c2 in n:
                    _scan_nc(c2)

        _scan_nc(body)
        self._ncall_shared = {k for k, v in _nc.items() if v >= 2}
        # Same callee and arity but a DIFFERENT leading argument still shares the
        # tail from the leftmost push onwards: every site computes its own args[0]
        # into AX and jumps to the one `push ax; call f; add sp,N; jmp ret`
        # (lookup_error_msg's four sites at 0x6190).
        _nc2 = {}
        for (nm, na, _), v in _nc.items():
            _nc2[(nm, na)] = _nc2.get((nm, na), 0) + v
        self._ncall_shared_ax = {k for k, v in _nc2.items() if v >= 2}
        self._ncall_lbls_ax = {}
        self._switch_case_lbls = set()  # every switch case body label
        self._ncall_lbls = {}  # key -> placed shared-tail label
        self._peek_next = None  # next sibling stmt (consecutive-0 chain)
        self._pascal_call = False  # inside a pascal callee's arg pushes
        self._ah_zero = False  # AH known 0 within a call's arg pushes
        # Function args go at [bp+4], [bp+6], ...  (positive offsets)
        # Stored in self.locals with positive offsets to distinguish from
        # locals (which get negative offsets via collect_locals below).
        arg_off = 4
        for ty, aname in args:
            self.locals[aname] = (-arg_off, ty)  # stored as negated so
            # far ptr and long are 4 bytes; everything else 2
            arg_off += 4 if (pf(ty) or wlong(ty)) else 2
        self.collect_locals(body)
        # A local array (address-taken stack buffer) makes MSC keep an explicit
        # `add sp,N` after the final call instead of folding it into the epilogue's
        # `mov sp,bp` — so a trailing void call must NOT tail-skip its cleanup.
        self._has_array_local = any(
            isinstance(t, str) and t.startswith('arr') for _, t in self.locals.values()
        )
        # DPB-table-style far_var entry pointers `far_var + index [+ const]`:
        # when such a far_var is read exactly ONCE in the function, MSC keeps the
        # index in SI and the base in BX (`les bx,[var]; [es:bx+si+disp]`); when
        # read several times it recomputes a bx-folded offset each time (the
        # ('idx') emit_les form).  Pick si-indexing for the single-use far_vars.
        # A far_var scaled entry read exactly ONCE (one base computation) keeps
        # the index in SI (`les bx,[var]; [es:bx+si+disp]`); read in several
        # separate expressions it recomputes a bx-folded offset each time.  Two
        # sibling fields of the SAME entry OR'd/AND'd together (`p[i].a | p[i].b`)
        # share one base, so that pair counts as ONE read (SET_FCB_DRIVE_TYPE's
        # `DPB_TABLE[out[0]].c_dpbo | .c_dpbs` stays SI, while DOS_FN_36's several
        # separate `DPB_TABLE[drive].*` reads stay bx-folded).
        def _scaled_base(x):
            if not (nderef(x) and ncast(x[1]) and 'far' in n11(x)):
                return None
            # A far-POINTER field (`DPB_TABLE[i].c_dpb`) is a ptr_far_ptr cast,
            # which far_lvalue deliberately does not claim — take its base
            # straight from the operand so it still counts toward the si/di
            # index-register decision.
            if n11(x).startswith('ptr_far_ptr'):
                operand, _ = self.split_disp(n12(x))
                if nbin(operand) and operand[1] == '+' and self.gfar(operand[2]):
                    return ('idx', operand[2][1], operand[3])
                return None
            fl = self.far_lvalue(x)
            b = fl[0] if fl else None
            return b if isinstance(b, tuple) and b[0] == 'idx' else None

        # Keyed by (var, index expression): DOS_FN_3A_RMDIR reads
        # DPB_TABLE[drive] once (SI form) and DPB_TABLE[scan_idx] twice
        # (bx-folded) in the same function.
        # Counted PER REGION, a region being a LOOP body (or the function
        # outside every loop): two reads in two SEPARATE loops each pay for
        # their own base computation and both stay si-indexed, while two reads
        # in one region share a base and go bx-folded.  DOS_FN_36 and
        # DOS_FN_3A_RMDIR need the latter, FIND_FREE_DRIVER_SLOT the former.
        _groups = {}

        def _walk_groups(node, key):
            if isinstance(node, list):
                for st in node:
                    _walk_groups(st, key)
                return
            if not isinstance(node, tuple):
                return
            if node[0] in ('for', 'while', 'do', 'dowhile'):
                key = id(node)  # a loop body is its own region
            b = _scaled_base(node)
            if b:
                _groups.setdefault(b, {})
                _groups[b][key] = _groups[b].get(key, 0) + 1
            for x in node:
                _walk_groups(x, key)

        _walk_groups(body, None)

        def _discount(b):
            """This occurrence supplies its own base — refund one from its
            busiest group."""
            g = _groups.get(b)
            if g:
                k = max(g, key=lambda k: g[k])
                g[k] -= 1

        for n in self._nodes(body):
            if n[0] == 'bin' and n[1] in ('|', '&'):
                b2, b3 = _scaled_base(n[2]), _scaled_base(n[3])
                if b2 and b2 == b3:
                    _discount(b2)  # the sibling pair is one base
            # A `far_var[i].<byte> <op> byte global` compare builds its own
            # ES:SI base (the mirrored form), so it costs no si setup here.
            if n[0] == 'cmp' and self.byte_global_addr(n[3]) is not None:
                b2 = _scaled_base(n[2])
                if b2:
                    _discount(b2)
        # Which scaled entries ride an index register at all is decided by
        # REGISTER AVAILABILITY, not use counts: with both SI and DI claimed by
        # register vars (DOS_FN_36) every scaled access is bx-folded; with an
        # index register free the si/di form is used even for repeated reads
        # (LOOKUP_DRIVER_SLOT_FREE reads s_offhi then s_offlo, recomputing the
        # index but keeping ES:BX).
        # (Register allocation runs later — at this point every reg var is
        # provisionally 'si' — so count declarations: vars land in SI then DI,
        # and two of them leave no index register free.)
        if len(self.regvars) >= 2:
            self._idx_si = set()
        else:
            self._idx_si = set(_groups)

        # Shared uchar zero-extend return tail: when >=2 returns yield a uchar
        # *value* (a uchar local or a uchar-returning call — each needs
        # `sub ah,ah`), MSC emits `sub ah,ah; jmp <epilogue>` ONCE; each such
        # return loads AL then falls into / jumps to it (GET_DRIVE_TYPE's USE_AX).
        def _is_uchar_ret_val(v):
            return v and (
                (self.ucharty(v)) or (ncall(v) and nid(v[1]) and n11(v) in UCHAR_FUNCS)
            )

        _uchar_rets = sum(
            1 for n in self._nodes(body) if n[0] == 'return' and _is_uchar_ret_val(n[1])
        )
        self._uchar_ret_val = _is_uchar_ret_val
        self._uchar_ret_share = _uchar_rets >= 2
        # When EVERY uchar-value return yields the SAME uchar local, MSC shares
        # the whole `mov al,[bp+d]; sub ah,ah; jmp epilogue` block (load
        # included): later `return ch` sites are a bare jmp, and an
        # `if (c) return ch` is a single JCC to it (CON_GETC / READ_LINE_BUFFERED).
        _ret_names = {
            n[1][1]
            for n in self._nodes(body)
            if n[0] == 'return' and _is_uchar_ret_val(n[1]) and nid(n[1])
        }
        self._uchar_ret_same = (
            _ret_names.pop()
            if self._uchar_ret_share
            and len(_ret_names) == 1
            and _uchar_rets
            == sum(
                1
                for n in self._nodes(body)
                if n[0] == 'return' and n[1] and nid(n[1]) and _is_uchar_ret_val(n[1])
            )
            else None
        )
        # Where the shared `sub ah,ah` tail lives: at the FIRST uchar-value
        # return when that return is a sole-if-arm JUMP TARGET (the block is a
        # basic block of its own — PARSE_PATH_WITH_DRIVE's
        # `if (r == 3 || r == 0) return r;`), else at the LAST one, falling
        # into the epilogue, with earlier sites jumping forward
        # (LOOKUP_DRIVER_SLOT_FREE's free-slot return mid-if-arm).
        self._useax_defer = False
        if self._uchar_ret_share and not self._uchar_ret_same:
            _first_sole = None

            def _walk_first(node, sole):
                nonlocal _first_sole
                if _first_sole is not None or not isinstance(node, (list, tuple)):
                    return
                if isinstance(node, tuple) and node and node[0] == 'return':
                    if _is_uchar_ret_val(node[1]):
                        _first_sole = sole
                    return
                if isinstance(node, tuple) and node and node[0] == 'if':
                    sole_then = len(node[2]) == 1 and node[2][0][0] == 'return'
                    for st in node[2]:
                        _walk_first(st, sole_then)
                    for st in node[3] or []:
                        _walk_first(st, False)
                    return
                for c in node:
                    _walk_first(c, sole)

            _walk_first(body, False)
            self._useax_defer = not _first_sole
        # A uchar-returning function whose EVERY `return` yields a uchar value (no
        # int/const-widened return that would force a full-word AX) returns in AL
        # only — `return found` is `mov al,[bp-d]`, no `sub ah,ah`.  A const/int
        # return sibling (get_deleted's `return 0`) re-forces the zero-extend.
        self._al_only_ret = getattr(self, '_func_ret_uchar', False) and all(
            _is_uchar_ret_val(n[1])
            for n in self._nodes(body)
            if n[0] == 'return' and n[1]
        )
        self._use_ax_lbl = None
        self._use_ax_placed = False  # same-local mode: label may pre-exist (a
        # forward `if (c) return ch` JCC) before the block itself is emitted
        # When the function has a shared uchar-return tail, MSC also defers its
        # `if (cond) return <const>` blocks to a single COLD copy just before the
        # epilogue (both `if`s jump forward to it — GET_DRIVE_TYPE's RET_FF),
        # rather than the inline-at-first-occurrence placement used otherwise
        # (find_fcb_for_drive's three `if(c) return 1`).
        # Defer `if(c) return <const>` to ONE cold tail block (placed just before
        # the epilogue) when the function also has a uchar-VALUE return AND there is
        # exactly ONE distinct const-return value — so a single shared block covers
        # it (GET_DRIVE_TYPE {0xFF}, RETRY_NETWORK_LOOP {0}).  With several distinct
        # const values (read_fcb {0,1,3}) MSC can't share one block, so they stay
        # inline; likewise with no uchar-value return (find_fcb's {1,0}).
        _const_ret_sites = [
            n11(n) for n in self._nodes(body) if n[0] == 'return' and n[1] and num(n[1])
        ]
        _const_rets = set(_const_ret_sites)
        # Deferral pays when the cold block has >= 2 JUMP SOURCES — several
        # return sites, or one sole `if (a || b) return K;` whose || arms each
        # JCC to it (GET_DRIVE_TYPE) — or when the site sits INSIDE A LOOP and
        # cannot fall out to the epilogue (RETRY_NETWORK_LOOP).  A single
        # plain-condition site in straight-line code stays inline
        # (LOOKUP_DRIVER_SLOT_FREE's `return 0xFF`).
        _cr_sources = 0
        _cr_in_loop = False

        def _scan_cr(node, in_loop):
            nonlocal _cr_sources, _cr_in_loop
            if isinstance(node, list):
                for st in node:
                    _scan_cr(st, in_loop)
                return
            if not isinstance(node, tuple) or not node:
                return
            if node[0] in ('for', 'while', 'do', 'dowhile'):
                for c in node[1:]:
                    _scan_cr(c, True)
                return
            if node[0] == 'return' and node[1] and num(node[1]):
                _cr_sources += 1
                _cr_in_loop = _cr_in_loop or in_loop
                return
            if (
                node[0] == 'if'
                and not node[3]
                and len(node[2]) == 1
                and node[2][0][0] == 'return'
                and node[2][0][1]
                and num(node[2][0][1])
                and node[1][0] == 'or'
            ):
                _cr_sources += 1  # the second || arm is one more JCC source
            for c in node[1:] if node[0] == 'if' else node:
                _scan_cr(c, in_loop)

        _scan_cr(body, False)
        self._defer_const_ret = (
            _uchar_rets >= 1
            and len(_const_rets) == 1
            and (_cr_sources >= 2 or _cr_in_loop)
        )
        self._deferred_const = {}  # value-repr -> (label, value-node)
        # Register allocation for register vars.  Without an outer loop we
        # let the first reg var live in SI, the second in DI (both
        # callee-saved).  With a loop, SI alone (matches lookup_token).
        has_loop = self._has_loop(body) or self._has_backward_goto(body)
        for i, name in enumerate(list(self.regvars)):
            # A `register unsigned char` lives in BL — the byte register MSC
            # uses to carry a table index across a loop's back edge
            # (`mov bl,x` before the head, `sub bh,bh; mov al,[bx+ARR]` at it).
            # Like the BX word var it gets NO stack slot, so it must be the
            # LAST declared local (WRITE_DIR_ENTRY's SUBST chain walk).
            if self.lt(name) == 'reg_uchar':
                if self.locals[name][0] != self.local_size:
                    ni('bl register var must be the last declared local')
                self.regvars[name] = 'bl'
                self.local_size -= 2
                continue
            if (
                not has_loop
                and i == 0
                and not self._has_deref(body)
                and not self._has_call(body)
                and not self._has_long_op(body)
                and not any(self.far_lvalue(n) for n in self._nodes(body))
            ):
                # A single reg var in a leaf function with no loop can live in
                # AX (no stack slot).  But a value live across a call, 32-bit
                # arithmetic, or a far-memory read (all clobber AX) must be in
                # callee-saved SI/DI, so those fall through to SI/DI below.
                self.regvars[name] = 'ax'
                # Reclaim the slot collect_locals reserved for it.
                self.local_size -= 2
                del self.locals[name]
            elif i == 0:
                self.regvars[name] = 'si'
                if not any(nid(n) and n[1] == name for n in self._nodes(body)):
                    # A declared-but-UNUSED register var: MSC still claims SI
                    # (push si/pop si around the body) but gives it no stack
                    # slot.  Like the BX var, it must be the LAST declared
                    # local so reclaiming its 2 bytes leaves every other
                    # bp-offset untouched (DISPATCH_FCB_OPEN's frame).
                    if self.locals[name][0] != self.local_size:
                        ni('unused si register var must be the last declared local')
                    self.local_size -= 2
            elif i == 1:
                self.regvars[name] = 'di'
            elif i == 2:
                # A third register var lands in BX — the register MSC also uses
                # as the far-pointer scratch base, so it only works when the var
                # is short-lived between `les` pairs (DOS_FN_3B_CHDIR's path
                # offset).  Unlike SI/DI, BX gets NO stack slot: the var must be
                # the LAST declared local so reclaiming its 2 bytes leaves every
                # other bp-offset untouched.
                if self.locals[name][0] != self.local_size:
                    ni('bx register var must be the last declared local')
                self.regvars[name] = 'bx'
                self.local_size -= 2
            else:
                ni('only 3 register vars supported')
        # Deferred reg-var return: when the function's LAST statement is
        # `return <reg-var>` and the same return appears elsewhere too, MSC
        # emits ONE `mov ax,si` block at the tail (falling into the epilogue)
        # and every earlier exit — plain, conditional, or a while-loop's false
        # test — jumps forward to it (CHAR_DEVICE_IO's RET block at 0x2390).
        self._regvar_ret_defer = None
        self._defer_tail_stmt = None
        self._suppress_return = None
        _last = body[-1] if body else None
        # A shared CONST `return K` whose PLAIN occurrence is the function tail:
        # MSC places the one shared block there (the natural pre-epilogue `xor
        # ax,ax` for 0) and earlier `if (cond) return K` guards JCC FORWARD to
        # it — not at the first guard.  (READ_OR_FOLLOW_FAT_CHAIN's `return 0`.)
        self._tail_shared_ret = set()
        # The function tail may be a RUN of cold return blocks — a shared
        # `return 0` followed by a goto-target `label: return 2` (DISPATCH_
        # FCB_OPEN).  Every shared-value return in that trailing run is
        # tail-placed; earlier occurrences jump FORWARD to it.
        def _in_switch(key):
            """True if const-return `key` is also returned inside a switch."""
            for n in self._nodes(body):
                if n[0] != 'switch':
                    continue
                for sub in self._nodes(list(n[2]) + [n[3] or []]):
                    if (
                        isinstance(sub, tuple)
                        and sub
                        and sub[0] == 'return'
                        and sub[1]
                        and repr(sub[1]) == key
                    ):
                        return True
            return False

        self._tail_ret_stmt_ids = set()  # the trailing-run stmts themselves
        _run = []
        for _s in reversed(body):
            if _s[0] == 'label':
                continue
            if _s[0] == 'return' and _s[1] and num(_s[1]):
                _run.append(_s)
                continue
            break
        # _tail_shared_ret steers `if (cond) return K` sites away from inline
        # placement for ANY tail return (READ_OR_FOLLOW_FAT_CHAIN).  The shared
        # block itself is anchored at the TAIL occurrence (earlier plain
        # `return K` sites jump forward to it) — DISPATCH_FCB_OPEN's cold-block
        # run, WRITE_DIR_ENTRY's single `return 0`.  The ONE exception is a
        # tail `return 0` that will collapse to `mov ax,dx`: that happens only
        # when a 32-bit `+=` immediately precedes it and leaves DX zero
        # (fcb_random_block_io's `rec->s_offset += *count; return 0;`), and
        # then the block has to stay at its first occurrence instead.
        _prev = None
        for _s in body:
            if _run and _s is _run[-1]:
                break
            _prev = _s
        _collapses = (
            len(_run) == 1
            and z0(_run[0][1])
            and _prev is not None
            and _prev[0] == 'expr'
            and _prev[1][0] == 'opassign'
            and _prev[1][1] == '+'
            and self._is_long_expr(_prev[1][2])
        )
        for _s in _run:
            if repr(_s[1]) in self.shared_returns:
                self._tail_shared_ret.add(repr(_s[1]))
                # ... unless the value is also returned from inside a SWITCH.
                # A dense jump table needs a concrete target for its
                # pass-through cases, which pins the block at the first case
                # that returns it — the later occurrences, tail included, jump
                # back (CHECK_FILE_ATTR_BITS' `return 0` at 4B17).
                if not _collapses and not _in_switch(repr(_s[1])):
                    self._tail_ret_stmt_ids.add(id(_s))
        if (
            _last
            and _last[0] == 'return'
            and _last[1]
            and nid(_last[1])
            and self.regvars.get(n11(_last)) in ('si', 'di')
        ):
            if (
                sum(
                    1
                    for n in self._nodes(body)
                    if n[0] == 'return' and n[1] == _last[1]
                )
                >= 2
            ):
                self._regvar_ret_defer = repr(_last[1])
                self._defer_tail_stmt = _last
        # Defer-to-LAST dup-if-block placement: when identical terminating
        # `if (c) { X = n; …; return K; }` blocks (>= 2) coexist with a bare
        # `if (X == n2) { return K; }` guard — one that tests the very lvalue
        # the block stores, i.e. the hand-written "skip the redundant store
        # into the return-suffix" pattern — MSC anchors the ONE cold copy at
        # the LAST occurrence: earlier occurrences jump FORWARD to it, and the
        # guard jumps into its `return K` suffix (FCB_RANDOM_BLOCK_IO's
        # fail/ret-zero block mid-CON-path).  A guard testing something else
        # (write_fcb's `if (fat_chain(…) != 0) return 1`) or a different K
        # (read_fcb's `return 0` guard vs `{…; return 1}` blocks) leaves the
        # block at the FIRST occurrence with backward jumps.
        _dup_info = {}  # body repr -> [count, body]
        _guards = []  # (K, cond) of every bare `if (cond) { return K; }`
        for n in self._nodes(body):
            if (
                n[0] == 'if'
                and len(n) >= 3
                and not n[3]
                and self._block_terminates(n[2])
            ):
                if (
                    len(n[2]) == 1
                    and n[2][0][0] == 'return'
                    and n[2][0][1]
                    and num(n[2][0][1])
                ):
                    _guards.append((n11(n[2][0]), n[1]))
                elif len(n[2]) >= 2:
                    e = _dup_info.setdefault(repr(n[2]), [0, n[2]])
                    e[0] += 1
        self._dup_last_total = {}  # body repr -> total occurrence count
        self._dup_seen = {}  # body repr -> occurrences emitted so far
        self._sret_cond_defer = set()  # const-return reprs routed to the suffix
        for _key, (_cnt, _b) in _dup_info.items():
            _bf, _bl = _b[0], _b[-1]
            if not (
                _cnt >= 2
                and _bl[0] == 'return'
                and _bl[1]
                and num(_bl[1])
                and _bf[0] == 'expr'
                and _bf[1][0] == 'assign'
            ):
                continue
            _stored = n11(_bf)  # the lvalue the block stores
            for _gk, _gc in _guards:
                if _gk == n11(_bl) and _gc[0] == 'cmp' and _gc[2] == _stored:
                    self._dup_last_total[_key] = _cnt
                    self._sret_cond_defer.add(repr(_bl[1]))
                    break
        # SI is a register var, or scratch for the table base of a far_var indexed
        # by a near value (`far_var[handle]` → les si,[tbl]; [es:bx+si]).
        self.uses_si = (
            any(r == 'si' for r in self.regvars.values())
            or self._has_far_var_near_index(body)
            or self._has_far_param_subscript(body)
            or bool(self._idx_si)
            or self._has_far_long_ptr_add(body)
            or self._has_long_long_cmp(body)
            # far_var[word-global] loads the index into SI scratch.
            or any(bool(self.fv_gword_idx(n)) for n in self._nodes(body))
            # far_var[ far_var[k] + c ] loads the inner byte into SI scratch.
            or any(
                n[0] == 'idx'
                and self.gfar(n[1])
                and n[2][0] == 'bin'
                and n[2][2][0] == 'idx'
                and nid(n[2][2][1])
                and n[2][2][1][1] == n[1][1]
                for n in self._nodes(body)
            )
            # far_local[uchar_local] puts the POINTER's offset in SI (the index
            # takes BX) — see the matching read in gen_index.
            or any(
                n[0] == 'idx'
                and self.locid(n[1])
                and pf(self.lty(n[1]))
                and self.locid(n[2])
                and self.ucharty(n[2])
                and not self.is_reg_var(n[2][1])
                for n in self._nodes(body)
            )
            # the divide-in-a-long-expression sequence spills the running
            # total's high word into SI and keeps the far pointer in DI.
            or any(self._long_div_tail(n) for n in self._nodes(body))
            # the arrD[g++] = arrS[g2++] byte copy keeps the SOURCE index in SI.
            or any(
                n[0] == 'assign'
                and n[1][0] == 'idx'
                and self.gkind(n[1][1]) == 'arr'
                and n[1][2][0] == 'postinc'
                and n[2][0] == 'idx'
                and self.gkind(n[2][1]) == 'arr'
                and n[2][2][0] in ('postinc', 'preinc')
                for n in self._nodes(body)
            )
            # local_array[uchar_local] loads the index into SI scratch.
            or any(
                n[0] == 'idx'
                and nid(n[1])
                and n11(n) in self.locals
                and str(self.lt(n11(n))).startswith('arr')
                and nid(n[2])
                and n[2][1] in self.locals
                and self.ucharty(n[2])
                and not self.is_reg_var(n[2][1])
                for n in self._nodes(body)
            )
            # ARR[g] = ARR[g +/- c] copies the shared index into SI scratch.
            or any(
                n[0] == 'assign'
                and n[1][0] == 'idx'
                and nid(n[1][1])
                and self.gkind(n[1][1]) == 'arr'
                and nid(n[1][2])
                and self.gvw(n[1][2])
                and n[2][0] == 'idx'
                and nid(n[2][1])
                and n[2][1][1] == n[1][1][1]
                and n[2][2][0] == 'bin'
                and n[2][2][1] in ('+', '-')
                and nid(n[2][2][2])
                and n[2][2][2][1] == n[1][2][1]
                for n in self._nodes(body)
            )
            # DEREF of a scaled struct-pointer subscript (`DPB_TABLE[out[0]]
            # .c_dpbo`) loads the scaled index into SI.  The bare address form
            # `&p->recs[i]` (built in AX:DX, no SI) is excluded by the deref.
            or any(self._scaled_far_deref(n) for n in self._nodes(body))
        )
        # DI may be used as a register var OR as a scratch for pointer deref
        # (the `*key == *tok` pattern in lookup_token).
        self.uses_di = (
            any(r == 'di' for r in self.regvars.values())
            # A single-use scaled far-var subscript uses DI (not SI) when SI is
            # already a register variable (MKDIR's DPB index in DI, loop in SI).
            or (bool(self._idx_si) and 'si' in self.regvars.values())
            or self._has_deref(body)
            or self._has_long_long_cmp(
                body
            )  # the far_var[si-regvar] = far_var[local] SDA copy loads the
            # table base into DI (keeping SI free), so DI must be saved.
            or any(
                n[0] == 'assign'
                and n[1][0] == 'idx'
                and self.gkind(n11(n)) == 'far_var'
                and self.rvid(n12(n))
                and n[2][0] == 'idx'
                and self.gfar(n[2][1])
                for n in self._nodes(body)
            )
            # the divide-in-a-long-expression sequence spills the running
            # total's high word into SI and keeps the far pointer in DI.
            or any(self._long_div_tail(n) for n in self._nodes(body))
            # far_local = &local_array[uchar local] zero-extends the subscript
            # through the spare index register, which is DI once SI is a
            # register var (EXEC_PROGRAM_FROM_PATH's `cur = &buf[type]`, 0x5641).
            or (
                'si' in self.regvars.values()
                and any(
                    n[0] == 'assign'
                    and pf(self.lty(n[1]))
                    and self._addr_local_arr_byte_idx(n[2])
                    for n in self._nodes(body)
                )
            )
            # ARR[reg++] = *far_local++ derefs the old offset through DI.
            or any(
                n[0] == 'assign'
                and n[1][0] == 'idx'
                and self.gkind(n11(n)) == 'arr'
                and n12(n)[0] == 'postinc'
                and nderef(n[2])
                and n[2][1][0] == 'postinc'
                for n in self._nodes(body)
            )
        )
        # Params + locals are now registered, so far_lvalue can resolve the
        # byte-store funnel's `BASE[disp]=K` exits.
        self._bfunnel = self._find_byte_funnel(body, _stmt_lists)
        self._fpseg_suppress = None  # a FP_SEG store folded into a fused far build
        self._cl_bvar0 = None  # a byte global just zeroed INTO CL (kept for a
        # following `(L & G) cmp L` — DOS_FN_41's SDA_SEARCH_ATTR)
        self.emit(0x55)  # push bp
        self.emit(0x8B, 0xEC)  # mov bp, sp
        if self.local_size:
            # a frame of 80h or more needs the imm16 form — the imm8 is SIGNED,
            # so 80h would read as -128 (DOS_FN_0F_OPEN_FCB's 128-byte frame)
            if self.local_size > 0x7F:
                self.emit(0x81, 0xEC, *w16(self.local_size))
            else:
                self.emit(0x83, 0xEC, self.local_size)
        if self.uses_di:
            self.emit(0x57)  # push di
        if self.uses_si:
            self.emit(0x56)  # push si
        for i, s in enumerate(body):
            tail = i == len(body) - 1
            self._peek_next = body[i + 1] if i + 1 < len(body) else None
            self.stmt(s, tail=tail)
        self._peek_next = None
        self._flush_deferred_whiles()  # any still-unplaced out-of-line bodies
        # Cold const-return blocks, just before the epilogue: each loads its value
        # and falls through to the epilogue (the last one); earlier ones jump to it.
        _dc = list(self._deferred_const.values())
        for j, (clbl, cval) in enumerate(_dc):
            self.lbl(clbl)
            self.expr_to_ax(cval)
            if j != len(_dc) - 1:
                self.emit_jmp_short(self.func_ret_lbl)
        # A body that CANNOT FALL THROUGH — its last instruction is an
        # unconditional jmp — and whose return label nothing references has no
        # reachable epilogue, and MSC emits none (MAIN_ENTRY ends at the
        # `jmp short $` of its fatal-error hang, with no pops and no ret).
        # Only a jmp to ITSELF counts: MSC emits the epilogue even when the last
        # instruction is an ordinary backward jmp that leaves it unreachable
        # (DOS_FN_0C, whose trailing switch arm jumps back into a shared tail).
        # An infinite self-loop is the one shape where it emits nothing at all.
        if (
            not _dc
            and self.atoms
            and self.atoms[-1][0] == 'jmp_short'
            and self.labels.get(self.atoms[-1][2]) == len(self.buf) - 2
        ):
            self.resolve()
            return
        self.lbl(self.func_ret_lbl)
        if self.uses_si:
            self.emit(0x5E)
        if self.uses_di:
            self.emit(0x5F)
        # `mov sp,bp` restores the frame.  MSC omits it only for a pure
        # straight-line leaf with no frame activity at all — no locals, no saved
        # regs, no emitted call, and no control flow (no branches/loops/gotos).
        if (
            self.local_size
            or self.uses_si
            or self.uses_di
            or self.made_call
            or self._has_branch(body)
        ):
            self.emit(0x8B, 0xE5)  # mov sp, bp
        self.emit(0x5D)  # pop bp
        self.emit(0xC3)  # ret
        self.resolve()

    def collect_locals(self, body):
        for s in body:
            if s[0] == 'localarr':
                ty, name, n = s[1], s[2], s[3]
                # A byte buffer reserved on the stack; `name` denotes its base
                # (bp-offset = element [0]).  Size is the byte count as written,
                # rounded so the base stays EVEN — MSC keeps every frame slot
                # word-aligned, so an odd-length buffer is followed by a pad byte
                # (EXEC_PROGRAM_FROM_PATH's 43h-byte path buffer at bp-54h).
                self.local_size += n + ((self.local_size + n) & 1)
                self.locals[name] = (self.local_size, 'arr_' + ty)
                continue
            if s[0] == 'local' and s[1].startswith('struct:'):
                ty, name = s[1], s[2]
                # A struct value on the stack: reserve its byte size; `name`
                # denotes the object base (array-style), so `.field`, `name`, and
                # `&name` all resolve to [bp-off] — byte-identical to the raw
                # `unsigned char name[size]` buffer it replaces.
                self.local_size += _type_size(ty)
                self.locals[name] = (self.local_size, 'arr_' + ty)
                continue
            if s[0] == 'local':
                ty, name = s[1], s[2]
                # far pointers and longs are 4 bytes; others pad to 2
                self.local_size += 4 if (pf(ty) or wlong(ty)) else 2
                self.locals[name] = (self.local_size, ty)
                if ty.startswith('reg_'):
                    # Slot stays reserved on the stack but the var actually
                    # lives in SI (only one register-var allowed for now).
                    self.regvars[name] = 'si'

    def _addr_local_arr_byte_idx(self, rhs):
        """True for `(T far *)&local_array[<uchar local>]` — the one far-pointer
        build whose subscript has to be zero-extended through an index register
        (see the matching store in gen_assign)."""
        a = rhs[2] if (ncast(rhs) and pf(rhs[1])) else rhs
        return (
            a[0] == 'addr'
            and a[1][0] == 'idx'
            and nid(a[1][1])
            and str(self.lty(a[1][1])).startswith('arr')
            and self.locid(a[1][2])
            and self.ucharty(a[1][2])
        )

    def _has_far_long_ptr_add(self, body):
        """True if the body contains a far-long opassign `*(long far*)(p+d) +=/-=
        *near_ptr` — read of the rhs pointer needs SI (ES:BX holds the far ptr)."""
        for n in self._nodes(body):
            if n[0] == 'opassign' and n[1] in ('+', '-'):
                fl, rhs = self.far_lvalue(n[2]), n[3]
                if (
                    fl
                    and fl[2] == 'long'
                    and nderef(rhs)
                    and self.lty(rhs[1]) in ('ptr_int', 'ptr_uint')
                ):
                    return True
        return False

    def _has_deref(self, node):
        # The only DI-using idiom is `*p1 == *p2` (a compare of two pointer
        # derefs, e.g. lookup_token).  A lone `*p` read or `*p = …` store uses
        # AL/BX, not DI; far derefs use ES:BX.  So only that compare counts —
        # and only in the exact shape cond_jump's DI path recognises, both
        # sides `*<pointer local>` with NO cast.  A cast inside the deref is a
        # far lvalue (`*(uint far *)(p + d)`), which never reaches DI
        # (WRITE_DIR_ENTRY's JOIN test compares two of those and MSC saves
        # only SI).
        def near_deref(x):
            return (
                nderef(x)
                and nid(x[1])
                and x[1][1] in self.locals
                and not pf(self.lt(x[1][1]))
            )

        return any(
            n[0] == 'cmp' and near_deref(n[2]) and near_deref(n[3])
            for n in self._nodes(node)
        )

    def _simple_word_rhs(self, e):
        """A word value that is a plain [bp+disp] read or a literal — it cannot
        touch ES:BX, so MSC loads the destination far pointer before it."""
        if z0(e):
            return True
        if self.stkid(e) and wint(self.lt(e[1])):
            return True
        # `<stack byte/word local> ± const`: still just a frame read plus
        # arithmetic on AX, so the `les` may be hoisted over it
        # (JOIN's `cds->c_pathoffw = idx - 1`).
        if (
            nbin(e)
            and e[1] in ('+', '-')
            and num(e[3])
            and self.stkid(e[2])
            and self.lt(e[2][1]) in ('uchar', 'char', 'int', 'uint')
        ):
            return True
        return e[0] in ('fpoff', 'fpseg') and pf(self.lty(e[1]))

    def _simple_byte_rhs(self, e):
        """True if `e` is local/global/const byte arithmetic — no call, no far
        access — so it can be computed after a `les` without clobbering ES:BX."""
        if num(e):
            return True
        # `g++` on a byte global reads and bumps memory only — no ES:BX
        # (PARSE_FILENAME_TO_FCB's `fcb->f_drvcode = WORK_FCB_DRIVE++`)
        if e[0] == 'postinc' and nid(e[1]) and self.gkind(e[1]) == 'bvar':
            return True
        # a stack struct/array byte member ([bp+d] read — DOS_FN_44's
        # regs->r_al = pkt.i_unit)
        if e[0] == 'idx' and nid(e[1]) and num(e[2]) and self.lty(e[1]).startswith('arr'):
            return True
        if nid(e):
            return self.lty(e) in ('uchar', 'int', 'uint') or self.gkind(e) in (
                'bvar',
                'var',
            )
        # A near cast to a byte reads the low byte of a local directly
        # (`(uchar)t` → mov al,[bp-off]) — safe after a `les`, whatever the
        # local's declared width.
        if ncast(e) and 'far' not in e[1]:
            if nid(e[2]) and e[2][1] in self.locals:
                return True
            return self._simple_byte_rhs(e[2])
        # ((unsigned char *)&local)[const] — a byte at a fixed offset within a
        # local (a word's low/high byte): `mov al,[bp+d]`, safe after a `les`.
        if (
            e[0] == 'idx'
            and ncast(e[1])
            and 'far' not in n11(e)
            and n12(e)[0] == 'addr'
            and nid(n12(e)[1])
            and n11(n12(e)) in self.locals
            and num(e[2])
        ):
            return True
        if nbin(e):
            return self._simple_byte_rhs(e[2]) and self._simple_byte_rhs(e[3])
        return False

    @staticmethod
    def _block_terminates(body):
        """True if the statement list always exits (no fall-through) — its last
        statement is a return/goto/break/continue."""
        return bool(body) and body[-1][0] in ('return', 'goto', 'break', 'continue')

    @staticmethod
    def _nodes(n):
        """Every (non-empty) tuple node of the AST, pre-order — the one walker
        behind all the _has_*/_count_* body scans."""
        if isinstance(n, (list, tuple)):
            if isinstance(n, tuple) and n:
                yield n
            for c in n:
                yield from CG._nodes(c)

    def _find_shared_call_returns(self, body):
        """Function names `f` where `return f(arg)` (exactly one argument) appears
        in >= 2 `return` statements.  Their `push ax; call f; add sp,2; jmp ret`
        tail is shared — placed at the first occurrence; later ones load the arg
        into AX and jump to it (MSC's FCB_OP_RAISE_ERROR_CODE for the several
        `return lookup_error_msg(code)` exits)."""
        counts = {}
        for n in self._nodes(body):
            if (
                n[0] == 'return'
                and n[1]
                and ncall(n[1])
                and nid(n11(n))
                and len(n12(n)) == 1
            ):
                nm = n11(n[1])
                counts[nm] = counts.get(nm, 0) + 1
        return {nm for nm, v in counts.items() if v >= 2}

    def _find_error_funnel(self, body, stmt_lists):
        """Detect the shared terminal-call error-funnel pattern (see emit_func).
        Returns {'outer','inner','arg0','looktail','settail','placed'} or None —
        all of outer/inner/arg0 are DISCOVERED from the body, never hard-coded
        function or variable names.  A terminal `OUTER(arg0, V)` is one whose
        next sibling is a `return`, a `goto`, a `label`, or nothing.  Fires only
        when: OUTER appears in >= 2 such statements, all with the same first-arg
        spelling; and every second arg is either a plain constant or `INNER(x)`
        for a single shared INNER, with at least one of each (both tails used)."""
        outer_hits = {}  # outer name -> list of (arg0_repr, v_node)
        for stmts in stmt_lists(body):
            for i, s in enumerate(stmts):
                if not (
                    s[0] == 'expr'
                    and ncall(s[1])
                    and nid(s[1][1])
                    and len(s[1][2]) == 2
                ):
                    continue
                nxt = stmts[i + 1] if i + 1 < len(stmts) else None
                if nxt is not None and nxt[0] not in ('return', 'goto', 'label'):
                    continue
                if nxt is not None and nxt[0] == 'return' and nxt[1]:
                    continue  # only a bare `return;` is a clean funnel exit
                call = s[1]
                outer_hits.setdefault(n11(call), []).append(
                    (repr(call[2][0]), call[2][1])
                )
        for outer, hits in outer_hits.items():
            if len(hits) < 2:
                continue
            if len({h[0] for h in hits}) != 1:  # all share the same first arg
                continue
            inners, has_plain, has_inner, ok = set(), False, False, True
            for _arg0, v in hits:
                if ncall(v) and nid(v[1]) and len(v[2]) >= 1:
                    inners.add(n11(v))
                    has_inner = True
                elif num(v):
                    has_plain = True
                else:
                    ok = False
                    break
            if ok and has_plain and has_inner and len(inners) == 1:
                return {
                    'outer': outer,
                    'inner': next(iter(inners)),
                    'arg0': hits[0][0],
                    # one shared looktail per inner ARG COUNT (1-arg + 4-arg
                    # error-code forms both feed the single settail).
                    'looktails': {},
                    'settail': None,
                    'placed': False,
                }
        return None

    def _byte_store_kc(self, stmt):
        """If `stmt` is `BASE[disp] = K` (a far BYTE store with constant K),
        return (base, disp, K); else None.  base/disp are far_lvalue's — a plain
        far-pointer name (not a computed tuple base)."""
        if not stmt or stmt[0] != 'expr':
            return None
        e = stmt[1]
        if e[0] != 'assign' or not num(e[2]):
            return None
        fl = self.far_lvalue(e[1])
        if not fl or fl[2] != 'byte' or isinstance(fl[0], tuple):
            return None
        return (fl[0], fl[1], e[2][1] & 0xFF)

    def _find_byte_funnel(self, body, stmt_lists):
        """Detect the shared BYTE-STORE error-funnel: >= 2 terminal exits of the
        form `INNER(code…); BASE[disp] = K; return` — a discarded INNER call
        (its result unused, e.g. LOOKUP_ERROR_MSG for side-effect) followed by a
        far byte store of the SAME (BASE, disp, K), each a clean funnel exit.
        The INNER calls cascade through per-arg-count looktails (as in
        _find_error_funnel), then share ONE `les bx,[BASE]; mov byte
        [es:bx+disp],K; jmp epilogue` settail placed at the FIRST exit (its
        looktail falls into it; later exits jump back).  INNER/BASE are all
        DISCOVERED (DELETE_FCB's LOOKUP_ERROR_MSG + `fcb[0] = 0xFF`)."""
        hits = {}  # (base, disp, K) -> [inner call nodes]
        extras = []  # (kind, call, kc, label) — goto-/fall-through-continuation
        for stmts in stmt_lists(body):
            for i, s in enumerate(stmts):
                if not (s[0] == 'expr' and ncall(s[1]) and nid(s[1][1])):
                    continue
                kc = self._byte_store_kc(stmts[i + 1] if i + 1 < len(stmts) else None)
                if not kc:
                    continue
                nxt = stmts[i + 2] if i + 2 < len(stmts) else None
                if nxt is not None and not (nxt[0] == 'return' and not nxt[1]):
                    # Not a clean funnel exit; record the goto-continuation and
                    # fall-into-label variants for endmode cross-jump sharing.
                    if nxt[0] == 'goto':
                        extras.append(('goto', s[1], kc, nxt[1]))
                    elif nxt[0] == 'label':
                        extras.append(('inline', s[1], kc, nxt[1]))
                    continue
                hits.setdefault(kc, []).append(s[1])
        for kc, calls in hits.items():
            if len(calls) >= 2 and len({n11(c) for c in calls}) == 1:
                bf = {
                    'inner': n11(calls[0]),
                    'store': kc,
                    'looktails': {},
                    'settail': None,
                    'placed': False,
                    'endmode': False,
                }
                # END-PLACEMENT mode: the function BODY ends with a funnel exit
                # (`INNER(code); BASE[disp]=K` as its last two statements) — MSC
                # then clusters the whole error tail at the function end, falling
                # into the epilogue, and every earlier exit jumps FORWARD into it
                # (RENAME_FCB).  Per argc, the exit emitted LAST holds the full
                # arg-push/call block; earlier ones are `mov ax,code; jmp` (and
                # trailing-args pushes) trampolines.  The current first-exit
                # placement (DELETE/CLOSE/CREATE_FCB) keeps working: none of
                # those bodies END with a funnel exit.
                tail_call = None
                if (len(body) >= 2 and body[-2][0] == 'expr'
                        and ncall(body[-2][1]) and nid(body[-2][1][1])
                        and n11(body[-2][1]) == bf['inner']
                        and self._byte_store_kc(body[-1]) == kc):
                    tail_call = body[-2][1]
                if tail_call is not None:
                    holders = {}
                    for c in calls:  # walk order == document order
                        holders[len(c[2])] = c
                    holders[len(tail_call[2])] = tail_call
                    bf['endmode'] = True
                    bf['tail_call'] = tail_call
                    bf['holders'] = holders
                    bf['store_lbl'] = None
                    bf['exit_ids'] = {id(c) for c in calls} | {id(tail_call)}
                    # Exits that continue with `goto L` share the suffix of an
                    # INLINE funnel block that falls into label L (RENAME_FCB's
                    # err523 jumping into err5's arg1-push).
                    bf['inline_blocks'] = {
                        id(c): lab
                        for k, c, ekc, lab in extras
                        if k == 'inline' and ekc == kc and n11(c) == bf['inner']
                    }
                    bf['goto_exits'] = {
                        id(c): lab
                        for k, c, ekc, lab in extras
                        if k == 'goto' and ekc == kc and n11(c) == bf['inner']
                    }
                    bf['inline_push'] = {}  # (argc, follow-label) -> share label
                return bf
        return None

    def _find_shared_returns(self, body):
        """Value reprs that appear in >= 2 `return v` statements with at least one
        *plain* return (not the sole body of an `if`).  Such a value's `return` is
        shared and placed at the plain occurrence (reached by fall-through); other
        occurrences JCC/JMP to it.  An all-conditional value (e.g. find_fcb's three
        `if(c) return 1`) is left to the constant-return merge instead."""
        total = {}
        plain = set()

        def walk(node, sole_if_body=False):
            if not isinstance(node, (list, tuple)):
                return
            if isinstance(node, tuple) and node and node[0] == 'return' and node[1]:
                k = repr(node[1])
                total[k] = total.get(k, 0) + 1
                if not sole_if_body:
                    plain.add(k)
                return
            if isinstance(node, tuple) and node and node[0] == 'if':
                walk(node[1])
                sole = len(node[2]) == 1 and node[2][0][0] == 'return'
                for s in node[2]:
                    walk(s, sole_if_body=sole)
                for s in node[3] or []:
                    walk(s)
                return
            for c in node:
                walk(c)

        walk(body)
        return {k for k in plain if total.get(k, 0) >= 2}

    def _find_dup_if_blocks(self, body):
        """Set of repr(if-body) appearing in >= 2 terminating `if (cond){body}`
        statements — the cross-jump candidates.  Only these get a shared (cold)
        block; a unique block stays a fall-through and may use live registers."""
        counts = {}
        for n in self._nodes(body):
            if (
                n[0] == 'if'
                and len(n) >= 3
                and not n[3]
                and self._block_terminates(n[2])
            ):
                k = repr(n[2])
                counts[k] = counts.get(k, 0) + 1
        return {k for k, v in counts.items() if v >= 2}

    def _has_branch(self, node):
        """True if the body has any control flow (branch/loop/goto) — i.e. it is
        not a single straight-line fall-through block."""
        return any(
            n[0]
            in ('if', 'while', 'for', 'switch', 'goto', 'label', 'break', 'continue')
            for n in self._nodes(node)
        )

    def _has_long_long_cmp(self, node):
        """True if a both-operands-computed 32-bit ordered compare appears
        (`(A>>c) <op> (B>>c)`); it parks the RHS in SI:DI, so the prologue must
        save both."""
        return any(
            n[0] == 'cmp'
            and n[1] in ('<', '>', '<=', '>=')
            and nbin(n[2])
            and n[2][1] == '>>'
            and nbin(n[3])
            and n[3][1] == '>>'
            for n in self._nodes(node)
        )

    def _has_long_op(self, node):
        """True if a 32-bit (long) bin/cast op appears (it clobbers AX:DX)."""
        return any(
            n[0] in ('bin', 'cast') and self._is_long_expr(n) for n in self._nodes(node)
        )

    def _scaled_far_deref(self, n):
        """True if `n` is a DEREF whose address is a scaled far-var subscript
        (`*(T far*)(far_var + const*idx [+ off])`) — read via `[es:bx+si]`, so
        the scaled index lives in SI.  Excludes the bare address form."""
        if n[0] != 'deref' or not ncast(n[1]):
            return False
        terms = []

        def flat(x):
            if nbin(x) and x[1] == '+':
                flat(x[2])
                flat(x[3])
            else:
                terms.append(x)

        flat(n12(n))
        return any(self.gfar(t) for t in terms) and any(
            t[0] == 'bin' and t[1] == '*' and num(t[2]) for t in terms
        )

    def _has_far_var_near_index(self, node):
        """True if a far-pointer access uses SI as a scratch index: a
        `far_var[near-int local]`, or a `*(T far*)(far_var + idx + k) >>= 1`."""
        for n in self._nodes(node):
            if n[0] == 'idx' and self.gfar(n[1]) and self.stkid(n[2]):
                return True
            if (
                n[0] == 'opassign'
                and n[1] == '>>'
                and nderef(n[2])
                and ncast(n[2][1])
                and pf(n11(n[2]))
            ):
                return True
        return False

    def _has_far_param_subscript(self, node):
        """True if a `far_ptr_local[int/uchar local]` subscript appears — it puts
        the pointer's offset in SI (via `les si`), so the prologue must save SI."""
        return any(
            n[0] == 'idx'
            and pf(self.lty(n[1]))
            and self.stkid(n[2])
            and self.lt(n[2][1]) in ('int', 'uint', 'uchar')
            for n in self._nodes(node)
        )

    @staticmethod
    def _has_loop(node):
        return any(n[0] in ('while', 'for', 'do') for n in CG._nodes(node))

    @staticmethod
    def _has_call(node):
        return any(ncall(n) for n in CG._nodes(node))

    def _has_backward_goto(self, body):
        """A goto whose target label was already seen (textually earlier) forms
        a loop — so register vars must live in callee-saved SI/DI, not AX."""
        seen = set()
        for n in self._nodes(body):
            if n[0] == 'label':
                seen.add(n[1])
            elif n[0] == 'goto' and n[1] in seen:
                return True
        return False

    def _cond_al_seed(self, cond):
        """If a loop condition is `(uchar = …) OP …`, the assigned uchar local
        ends up in AL when the condition is evaluated, so it is live in AL on
        the loop's back-edge. Return that local name (to seed the AL cache at
        the loop top), else None."""
        if cond[0] == 'cmp' and cond[2][0] == 'assign' and nid(cond[2][1]):
            v = n11(cond[2])
            if v in self.locals and self.lt(v) == 'uchar':
                return v
        return None

    def _cond_ah_zero_seed(self, cond):
        """If a loop condition compares a byte value zero-extended into AX
        (`mov al,…; sub ah,ah; cmp ax,…`), AH is left 0 on the back-edge, so a
        byte read at the body top reuses it (skips its own `sub ah,ah`) —
        PROCESS_TYPED_CHARS_UNTIL_CR's second loop reuses the `TYPED_COUNT !=
        HIST_INDEX` test's AH=0 for `HIST_BUF[HIST_INDEX]`.  The widen only
        happens when the byte is compared to a WORD (`cmp ax,[g]`); a byte
        constant RHS keeps a byte compare (`cmp al,imm8`) that leaves AH alone
        (dos_fn_09's `*p != '$'`)."""
        if cond[0] != 'cmp':
            return False
        lhs, rhs = cond[2], cond[3]
        # RHS must force a word compare (word global / word local / word expr).
        word_rhs = (
            self.gkind(rhs) == 'var'
            or (self.locid(rhs) and wint(self.lt(rhs[1])))
            or self.rvid(rhs)  # widened vs SI/DI (cmp ax,si) — RENAME's idx > si
            or rhs[0] in ('bin', 'call')
        )
        if not word_rhs:
            return False
        if self.gkind(lhs) == 'bvar' or self.ucharty(lhs):
            return True
        far = self.far_lvalue(lhs)
        if far and far[2] == 'byte':
            return True
        return lhs[0] == 'idx' and self.gkind(lhs[1]) == 'arr'

    def _cond_esbx_seed(self, cond):
        """If a loop condition dereferences a far pointer (`*p OP …`), the
        condition's `les bx,[p]` leaves ES:BX pointing at *p on the back-edge,
        so seed the ES:BX cache with that base at the loop top."""
        if cond[0] == 'cmp':
            far = self.far_lvalue(cond[2])
            if far:
                base = far[0]
                # Only a LOCAL far pointer keeps ES:BX live across the back-edge
                # (les [bp+disp] once); a global far_var reloads les [addr] each
                # use, so it must NOT be seeded.
                if isinstance(base, str) and base in self.locals and pf(self.lt(base)):
                    return base
            # far_var[gword+const] test: `les bx,[fv]` in the test leaves ES:BX
            # at the far_var, so the body's same-far_var read reuses it across
            # the back-edge (FIND_NEXT_CHAR_MATCH's INPUT_FCB_PTR scan).
            fgi = self.fv_gword_idx(cond[2])
            if fgi:
                return fgi[0]
        return None

    def _arm_ends_in_call(self, stmts):
        """True if this statement list's control flow ends in a void call on
        every path — a trailing `f(…)` statement, or a trailing if/else whose
        BOTH arms end in a call (recursively).  Used so a sibling arm's trailing
        void call tail-folds its `add sp,N` and merges into the shared tail even
        when the other arm is a nested if (dos_fn_57's error arms vs the
        get/set dispatch, both funnelling to `set_fcb_handle_or_clear`)."""
        if not stmts:
            return False
        last = stmts[-1]
        if last[0] == 'expr' and ncall(last[1]):
            return True
        if last[0] == 'if' and last[3]:
            return self._arm_ends_in_call(last[2]) and self._arm_ends_in_call(last[3])
        return False

    def _arm_tail_call_target(self, stmts):
        """(callee, argc) of the void call ending EVERY path of this statement
        list, or None.  Two arms merge into one shared tail call only when they
        end in the SAME call — different callees each keep their own `add sp,N`
        (MSC folds cleanup only into a genuinely shared falls-into-epilogue
        call: con_putc's fcb_random_block_write/con_write_char arms both keep
        theirs, while dos_fn_57's twin set_fcb_handle_or_clear arms merge)."""
        if not stmts:
            return None
        last = stmts[-1]
        if last[0] == 'expr' and ncall(last[1]) and nid(n11(last)):
            return (n11(last[1]), len(n12(last)))
        if last[0] == 'if' and last[3]:
            a = self._arm_tail_call_target(last[2])
            if a and a == self._arm_tail_call_target(last[3]):
                return a
        return None

    def _emit_call_tail_return(self, call):
        """`return f(arg)` via the shared call tail: load arg→AX (reusing AL for a
        uchar already live), then at the first occurrence emit/label the tail
        `push ax; call f; add sp,2; jmp ret`; later ones just jump to it."""
        name = n11(call)
        self.expr_to_ax(call[2][0])  # arg → AX
        if name not in self._call_tail_lbl:
            lbl = self.fresh('etail')
            self._call_tail_lbl[name] = lbl
            self.lbl(lbl)
            self.emit(0x50)  # push ax
            self.emit_call(sa(name))  # call f
            self.emit(0x83, 0xC4, 0x02)  # add sp, 2
            self.clob()
            self.emit_jmp_short(self.func_ret_lbl)  # jmp epilogue
        else:
            self.emit_jmp_short(self._call_tail_lbl[name])

    @staticmethod
    def _ncall_key(call):
        return (n11(call), len(call[2]), repr(call[2][0]) if call[2] else None)

    def _emit_ncall_return(self, call, tail):
        """`return f(a0, …)` through the shared multi-arg call tail: push the
        differing args, then fall into / jump to the one `push a0; call f;
        add sp,N; jmp ret` block (placed at the first occurrence)."""
        key = self._ncall_key(call)
        key2 = (n11(call), len(call[2]))
        if key in self._ncall_lbls:
            for a in reversed(call[2][1:]):
                self.push_arg(a)
            self.emit_jmp_short(self._ncall_lbls[key])
            return
        if key2 in self._ncall_lbls_ax:
            for a in reversed(call[2][1:]):
                self.push_arg(a)
            self.expr_to_ax(call[2][0])
            self.emit_jmp_short(self._ncall_lbls_ax[key2])
            return
        self._ncall_lbls[key] = lbl = self.fresh('ntail')
        axlbl = None
        if key2 in self._ncall_shared_ax:
            self._ncall_lbls_ax[key2] = axlbl = self.fresh('nxtail')
        self.gen_call(call, share_lbl=lbl, share_ax_lbl=axlbl)
        if not tail:
            self.emit_jmp_short(self.func_ret_lbl)

    # ---- statements ----
    def stmt(self, s, tail=False):
        match s:
            case ('local', *_) | ('localarr', *_):
                return
            case ('label', name):
                self.lbl('user_' + name)
            case ('goto', name):
                # a `goto` absorbed by a preceding shared assignment-call jmp
                # emits nothing (control already left via that jmp).
                if s is getattr(self, '_sac_suppress_goto', None):
                    self._sac_suppress_goto = None
                    return
                # a `goto` absorbed by a funnel cross-jump (the shared suffix
                # ends by falling into this goto's target — RENAME_FCB's err523).
                if self._bfun_suppress_goto:
                    self._bfun_suppress_goto = False
                    return
                self.emit_jmp_short('user_' + name)
            case ('block', stmts):
                for i, ss in enumerate(stmts):
                    self.stmt(ss, tail=tail and i == len(stmts) - 1)
            case ('expr', e):
                # A FP_SEG store folded into a preceding fused far-pointer build.
                if s is self._fpseg_suppress:
                    self._fpseg_suppress = None
                    return
                # A byte store folded into a byte-store funnel settail — skip it,
                # and mark its trailing `return;` (if any) for suppression too.
                if s is self._bfun_suppress_store:
                    self._bfun_suppress_store = None
                    if (
                        self._peek_next is not None
                        and self._peek_next[0] == 'return'
                        and not self._peek_next[1]
                    ):
                        self._efun_suppress = self._peek_next
                    return
                self.expr_stmt(e, tail=tail)
            case ('return', val):
                self._stmt_return(s, val, tail)
            case ('while', cond, body, *rest):
                self._stmt_while(cond, body, rest[0] if rest else None)
            case ('do', cond, body):
                # do { BODY } while (COND);  — labelled top, JCC-back tail, and a
                # break label right after (the natural fall-through exit).
                loop = self.fresh('loop')
                brk = self.fresh('break')
                cont = self.fresh('cont')
                self.break_lbls.append(brk)
                self.continue_lbls.append(cont)
                self.lbl(loop)
                for ss in body:
                    self.stmt(ss)
                # `continue` in a do-while lands on the CONDITION, not the loop
                # top — placed only when something jumps to it, so a loop
                # without one keeps the exact register cache noted below.
                self.lbl_if_used(cont)
                self.cond_jump(cond, loop, True)
                self.break_lbls.pop()
                self.continue_lbls.pop()
                # A break-less do-while exits ONLY by falling through the failed
                # back-edge test, so the post-test register cache is exact — keep it
                # live (MSC reuses the loop body's ES:BX in the code that follows,
                # TRIM_TRAILING_NAME_SPACES' `name[++si]='.'` after the ripple shift).
                # With a real break, the exit is a merge — clear via lbl().
                if any(l == brk for _, l, _ in self.fixups):
                    self.lbl(brk)
                return
            case ('break',):
                self.emit_jmp_short(self.break_lbls[-1])
            case ('continue',):
                self.emit_jmp_short(self.continue_lbls[-1])
            case ('switch', sw, cases, default):
                self.gen_switch(sw, cases, default)
            case ('for', init, cond, upd, fbody):
                self._stmt_for(init, cond, upd, fbody)
            case ('if', cond, then, els):
                self._stmt_if(cond, then, els, tail)
            case _:
                ni(s)

    def _stmt_return(self, s, val, tail):
        # A `return <reg-var>` already consumed by the preceding while's
        # fused exit (the loop's false test jumps straight to the shared
        # tail block, so this statement is unreachable) — emit nothing.
        if s is self._suppress_return:
            self._suppress_return = None
            return
        # A `return;` absorbed by a shared FCB error-funnel jmp/tail.
        if s is self._efun_suppress:
            self._efun_suppress = None
            return
        # `return f(arg);` whose call tail is shared (FCB_OP_RAISE_ERROR_CODE).
        if (
            val
            and ncall(val)
            and nid(val[1])
            and n11(val) in self._shared_call_tail
            and len(val[2]) == 1
        ):
            self._emit_call_tail_return(val)
            return
        # `return f(a0, …)` whose MULTI-arg tail is shared: the first site
        # emits the full call with a label before the leftmost push; later
        # sites push their differing args and jump into it.
        if (
            val
            and ncall(val)
            and nid(val[1])
            and (
                    self._ncall_key(val) in self._ncall_shared
                    or (n11(val), len(val[2])) in self._ncall_shared_ax
                )
        ):
            self._emit_ncall_return(val, tail)
            return
        # `return 0` right after a far-long add that left DX=0 (the dir-size
        # epilogue at FCB+0x15): MSC reuses it via `mov ax,dx` and falls into
        # the epilogue, rather than sharing the cold `xor ax,ax` return block.
        if tail and z0(val) and self.dx == 0:
            self.emit(0x8B, 0xC2)  # mov ax, dx
            self.ax = None
            return
        # Shared uchar zero-extend tail: load AL for this uchar-value return,
        # then route through the one `sub ah,ah; jmp epilogue` block (placed
        # at the first such return; later ones jump back to it).
        if self._uchar_ret_share and self._uchar_ret_val(val):
            # Same-local mode: the shared block includes the AL load, so a
            # later `return ch` is a bare jmp to the pre-load label.
            if self._uchar_ret_same and nid(val) and val[1] == self._uchar_ret_same:
                if self._use_ax_placed:
                    self.emit_jmp_short(self._use_ax_lbl)
                    return
                if not self._use_ax_lbl:
                    self._use_ax_lbl = self.fresh('useax')
                self._use_ax_placed = True
                self.lbl(self._use_ax_lbl)
                self.ldal(self.ldi(s))  # mov al, [bp+disp]
                self.emit(0x2A, 0xE4)  # sub ah, ah
                self.zaa()
                if not tail:
                    self.emit_jmp_short(self.func_ret_lbl)
                return
            if ncall(val):
                self.gen_call(val)  # uchar result in AL
            else:
                disp = self.ldi(s)
                self.ldal(disp)  # mov al, [bp+disp]
            if not self._use_ax_lbl:
                self._use_ax_lbl = self.fresh('useax')
            if not self._use_ax_placed and (tail or not self._useax_defer):
                self._use_ax_placed = True
                self.lbl(self._use_ax_lbl)
                self.emit(0x2A, 0xE4)  # sub ah, ah
                self.zaa()
                if not tail:
                    self.emit_jmp_short(self.func_ret_lbl)
            else:
                self.emit_jmp_short(self._use_ax_lbl)
            return
        # A plain `return v` whose value is shared: this fall-through site is
        # where the shared block lives.  Place the label here the first time
        # (then emit normally); jump to it on any later occurrence.
        if val and repr(val) in self.shared_returns:
            key = repr(val)
            lbl = self.shared_ret_lbls.setdefault(key, self.fresh('sret'))
            if key in self.shared_ret_placed:
                self.emit_jmp_short(lbl)
                return
            # Deferred reg-var return: the shared block lives at the TAIL
            # occurrence only — a non-tail plain `return si` just jumps
            # forward to it (no `mov ax,si` here).
            if key == self._regvar_ret_defer and not tail:
                self.emit_jmp_short(lbl)
                return
            # Tail-run shared const return: the block lives at the trailing-run
            # occurrence; every earlier plain `return K` jumps FORWARD to it
            # (DISPATCH_FCB_OPEN's device-record `return 0`).
            if (
                self._tail_ret_stmt_ids
                and key in self._tail_shared_ret
                and id(s) not in self._tail_ret_stmt_ids
            ):
                self.emit_jmp_short(lbl)
                return
            self.shared_ret_placed.add(key)
            self.lbl(lbl)
        if val:
            # `return f(args);` at the function end is a tail call — the
            # epilogue's `mov sp, bp` reclaims the args, so skip `add sp,N`.
            if ncast(val) and val[1] == 'uchar' and ncall(val[2]):
                # `return (uchar)f(...)` — narrow the int result to a byte and
                # zero-extend for the int return (call; add sp; sub ah,ah).
                self.gen_call(val[2], tail=tail)
                self.emit(0x2A, 0xE4)  # sub ah, ah
            elif tail and ncall(val):
                self.gen_call(val, tail=True)
            elif self._far_ptr_add_base(val):
                bn, addends = self._far_ptr_add_base(val)
                self._far_ptr_add_to_axdx(bn, addends)  # far ptr → off=AX, seg=DX
            elif self._is_long4(val):
                self.load_long_axdx(val)  # 32-bit result in DX:AX
            elif self._is_long_expr(val):
                self.gen_long(val)  # 32-bit expression → DX:AX
            elif self._al_only_ret and self._uchar_ret_val(val):
                self.expr_to_al(val)  # uchar function → AL only, no zero-extend
            else:
                self.expr_to_ax(val)
        if not tail:
            # mid-function return — jump to shared epilogue
            self.emit_jmp_short(self.func_ret_lbl)
        return

    def _stmt_while(self, cond, body, test_label):
        # while (1) → infinite loop, no condition test; exits via break.
        if num(cond) and cond[1] != 0:
            loop = self.fresh('loop')
            brk = self.fresh('break')
            self.lbl(loop)
            self.loop_body(body, brk, loop)
            self.emit_jmp_short(loop)
            self.lbl_if_used(brk)
            return
        # DEFERRED (out-of-line) while body — MSC moves a rarely-taken loop
        # body below the exit path's code: the test jumps INTO the body when
        # the condition holds, the exit falls through, and the body block is
        # dumped at the next unreachable point (RENAME_FCB's target-collision
        # pre-scan, body at 9933 between the exit path's ternary arms).
        # Gated to endmode-funnel functions with a `call() == 0` condition.
        if (
            self._bfunnel
            and self._bfunnel.get('endmode')
            and self._peek_next is not None
            and cond[0] == 'cmp'
            and cond[1] == '=='
            and ncall(cond[2])
            and z0(cond[3])
        ):
            loop = self.fresh('dwtest')
            body_lbl = self.fresh('dwbody')
            self.lbl(loop)
            self.cond_jump(cond, body_lbl, True)  # cond true → body (below)
            self._deferred_whiles.append((body_lbl, body, loop))
            return
        # MSC emits `while` as a test-at-TOP loop (no entry jump):
        #   top: if(!cond) goto exit; body; jmp top; exit:
        # The rotated (test-at-bottom, entry `jmp test`) shape belongs to
        # `for` — write a `for (; cond; )` for that. See tinycc.md.
        loop = ('user_' + test_label) if test_label else self.fresh('loop')
        # A `while` immediately followed by the function's deferred
        # `return <reg-var>`: the loop's false test jumps straight to the
        # shared tail block — no local exit label, and the (unreachable)
        # return after the loop emits nothing.  Not for the tail return
        # itself, which must still place the block.
        nxt = self._peek_next
        fused = (
            self._regvar_ret_defer
            and nxt
            and nxt is not self._defer_tail_stmt
            and nxt[0] == 'return'
            and nxt[1]
            and repr(nxt[1]) == self._regvar_ret_defer
        )
        if fused:
            exit_ = self.shared_ret_lbls.setdefault(
                self._regvar_ret_defer, self.fresh('sret')
            )
        else:
            exit_ = self.fresh('wexit')
        self.lbl(loop)
        self.cond_jump(cond, exit_, False)
        self.loop_body(body, exit_, loop)
        self.emit_jmp_short(loop)
        if fused:
            self._suppress_return = nxt
        else:
            self.lbl(exit_)
        return

    def _stmt_for(self, init, cond, upd, body):
        # for(drv=init; ; drv=upd) — no condition: a far-pointer carried in
        # DX:AX with the store hoisted to the loop *top* (the body's own
        # breaks/returns are the only exits).  init falls into the store;
        # upd recomputes DX:AX and jumps back to it.
        if (
            not cond
            and init
            and init[0] == 'assign'
            and pf(self.lty(init[1]))
            and upd
            and upd[0] == 'assign'
            and upd[1] == init[1]
        ):
            name = n11(init)
            d = self.ld(name)
            top = self.fresh('loop')
            brk = self.fresh('break')
            self.gen_long(init[2])  # init far value → DX:AX (no store)
            self.lbl(top)
            self.stax(d)  # mov [bp+d], ax
            self.emit(0x89, 0x56, d + 2)  # mov [bp+d+2], dx
            self.ax = ('fpoff', name)
            self.dx = None
            self.loop_body(body, brk, top)
            self.gen_long(upd[2])  # next far value → DX:AX (no store)
            self.emit_jmp_short(top)
            self.lbl_if_used(brk)
            return
        # Far-pointer loop variable carried in DX:AX with the store hoisted
        # to the (shared) loop test — MSC's driver-chain walk.  init/upd
        # compute the next far pointer into DX:AX *without* storing; the test
        # stores it, then compares the offset still live in AX.
        if (
            init
            and init[0] == 'assign'
            and pf(self.lty(init[1]))
            and upd
            and upd[0] == 'assign'
            and upd[1] == init[1]
            and cond
            and cond[0] == 'cmp'
            and cond[2][0] == 'fpoff'
            and cond[2][1] == init[1]
        ):
            name = n11(init)
            d = self.ld(name)
            loop = self.fresh('loop')
            test = self.fresh('test')
            brk = self.fresh('break')
            self.gen_long(init[2])  # init far value → DX:AX (no store)
            self.emit_jmp_short(test)
            self.lbl(loop)
            self.loop_body(body, brk, test)
            self.gen_long(upd[2])  # next far value → DX:AX (no store)
            self.lbl(test)
            self.stax(d)  # mov [bp+d], ax
            self.emit(0x89, 0x56, d + 2)  # mov [bp+d+2], dx
            self.ax = ('fpoff', name)
            self.dx = None
            self.cond_jump(cond, loop, True)
            self.lbl_if_used(brk)
            return
        if init:
            self.expr_stmt(init)
        # for (init; ; upd) — no condition: an infinite loop whose body exits
        # via return/break.  `upd` runs at the bottom (so loop work placed in
        # the update clause lands after the body), then `jmp` back to the top.
        if not cond:
            loop = self.fresh('loop')
            cont = self.fresh('cont')
            brk = self.fresh('break')
            # A value carried in AX ACROSS the back edge: when the body opens
            # `<word global> = X` and closes `X = <call>`, AX holds X both on
            # entry (from the store that precedes the loop) and on the back
            # edge (the call's return register), so the head's reload is dead.
            # MSC drops it — WRITE_DIR_ENTRY's FAT chain walk (7FFB).
            # The general form: the LAST body statement is `V = <call>`, so the
            # back edge arrives with AX = V (the return register).  If AX
            # already holds V on entry too, it holds V at the head on BOTH
            # paths and any reload there is dead.  V may be the word global the
            # body opens by storing, or the local feeding that store.
            seed = None
            if len(body) >= 2 and self.ax is not None:
                _l = body[-1]
                if (
                    _l[0] == 'expr'
                    and _l[1][0] == 'assign'
                    and nid(_l[1][1])
                    and ncall(_l[1][2])
                ):
                    _v = _l[1][1][1]
                    _al = self._ax_alias
                    if self.ax == _v or (_al and _al == (_v, len(self.buf))):
                        seed = _v  # AX holds V on BOTH paths into the head
            self.lbl(loop)
            if seed:
                self.ax = seed
            self.loop_body(body, brk, cont)
            self.lbl_if_used(cont)
            if upd:
                self.expr_stmt(upd)
            self.emit_jmp_short(loop)
            self.lbl_if_used(brk)
            return
        # MSC skips the entry jump-to-test only when the first iteration
        # provably runs (e.g. `i = 0; i < 18`); otherwise it rotates with a
        # `jmp test` entry (e.g. `i = nclus; DPB_PTR[4] >= i`).
        provable = (
            init
            and init[0] == 'assign'
            and num(init[2])
            and cond
            and cond[0] == 'cmp'
            and cond[2] == init[1]
            and num(cond[3])
            and (
                (cond[1] == '<' and init[2][1] < cond[3][1])
                or (cond[1] == '<=' and init[2][1] <= cond[3][1])
                or (cond[1] == '!=' and init[2][1] != cond[3][1])
                or (cond[1] == '>' and init[2][1] > cond[3][1])
                or (cond[1] == '>=' and init[2][1] >= cond[3][1])
            )
        )
        loop = self.fresh('loop')
        test = self.fresh('test')
        brk = self.fresh('break')
        cont = self.fresh('cont')
        if not provable:
            _entry_al = self.al  # AL as the init leaves it, for the test label
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
                self.bx = esbx_seed  # BX also points there (rotated cond's les)
            if self._cond_ah_zero_seed(cond):
                self._ah_zero = True  # cond's `sub ah,ah` left AH=0 on back-edge
            # `ARR[<word global>] OP num` leaves BX holding that global's value
            # (the `mov bx,[g]` its compare emitted), so the body's first read
            # of the SAME index reuses it across the back-edge — MAIN_ENTRY's
            # DEVICE= name loop tests LINE_BUF[PARSE_POS] for CR and then
            # immediately compares the same byte to a space (0x03DC).
            if (
                cond[0] == 'cmp'
                and cond[2][0] == 'idx'
                and nid(cond[2][1])
                and self.gkind(cond[2][1]) == 'arr'
                and self.gvw(cond[2][2])
                and num(cond[3])
            ):
                self.bx = ('idxvar', cond[2][2][1])
            if (
                cond[0] == 'cmp'
                and cond[2][0] == 'idx'
                and self._gbarr(cond[2][1]) is not None
                and self.locid(cond[2][2])
                and self.lt(cond[2][2][1]) in ('uchar', 'char')
                and self.locid(cond[3])
                and self.lt(cond[3][1]) in ('uchar', 'char')
            ):
                self.bx = ('idxloc', cond[2][2][1])
                self.al = cond[3][1]
                self._bh_zero = True
                self._SEEDED = True
        self.loop_body(body, brk, cont, peek=True)
        # `continue` lands on the update (then the test), per C semantics — not
        # on the test directly (which would skip the update).
        self.lbl_if_used(cont)
        if upd:
            self.expr_stmt(upd)
        if not provable:
            # A rotated loop's test has exactly two predecessors — the entry jump
            # and the body's fall-through.  When BOTH leave the same value in AL
            # the label can inherit it, which is how MSC reads the loop variable
            # back with `mov bl,al` instead of reloading its slot
            # (UNJOIN_DRIVE's chain walk at 0x7592).
            _body_al = self.al
            self.lbl(test)
            if _body_al is not None and _body_al == _entry_al:
                self.al = _body_al
        self.cond_jump(cond, loop, True)
        self.lbl_if_used(brk)
        return

    def _stmt_if(self, cond, then, els, tail):
        fn = self._efunnel
        if not els:
            match then:
                # if (cond) goto L; / break; / continue; — a single JCC.
                case [('goto', tgt)]:
                    self.cond_jump(cond, 'user_' + tgt, True)
                    return
                case [('break',)]:
                    self.cond_jump(cond, self.break_lbls[-1], True)
                    return
                case [('continue',)]:
                    self.cond_jump(cond, self.continue_lbls[-1], True)
                    return
                # if (cond) { OUTER(fcb, INNER(code)); return; } sharing the
                # funnel's already-placed error tail for the SAME code — one JCC
                # straight to the pre-load label (DOS_FN_4E's network
                # `if (status == 3)` → 683d).
                case [
                    ('expr', ('call', ('id', outer),
                              [arg0, ('call', ('id', inner), [code])])),
                    ('return', None),
                ] if (
                    fn
                    and (lt1 := fn.get('looktails', {}).get(1))
                    and outer == fn['outer']
                    and repr(arg0) == fn['arg0']
                    and inner == fn['inner']
                    and repr(code) == lt1['load_repr']
                ):
                    self.cond_jump(cond, lt1['load'], True)
                    return
                case _:
                    pass
        simple_return = not els and len(then) == 1 and then[0][0] == 'return'
        if simple_return and not then[0][1]:
            # if (cond) return;     — JCC straight to epilogue
            self.cond_jump(cond, self.func_ret_lbl, True)
            return
        # `if (cond) return <long / far-ptr>;` as the function's LAST statement:
        # skip to the epilogue on a false condition, then load the 32-bit value
        # into DX:AX and fall straight through (no `jmp epilogue`) — the general
        # path below only knows expr_to_ax (16-bit) and always jmps.
        if (
            simple_return
            and then[0][1]
            and tail
            and (
                self._is_long4(then[0][1])
                or self._is_long_expr(then[0][1])
                or self._far_ptr_add_base(then[0][1])
            )
        ):
            val = then[0][1]
            self.cond_jump(cond, self.func_ret_lbl, False)
            if self._far_ptr_add_base(val):
                bn, addends = self._far_ptr_add_base(val)
                self._far_ptr_add_to_axdx(bn, addends)
            elif self._is_long4(val):
                self.load_long_axdx(val)
            else:
                self.gen_long(val)
            return
        if simple_return and then[0][1]:
            val = then[0][1]
            # uchar-value return that shares the zero-extend tail: skip past
            # on a false condition, then let the bare-return handler place /
            # jump to the shared `sub ah,ah; jmp epilogue` (USE_AX).
            if self._uchar_ret_share and self._uchar_ret_val(val):
                # Same-local mode: the whole load+widen block is shared, so
                # `if (c) return ch` is ONE JCC to it — backward when the
                # block exists (CON_GETC), forward to the later placement
                # otherwise (READ_LINE_BUFFERED's then-arm).
                if self._uchar_ret_same and nid(val) and val[1] == self._uchar_ret_same:
                    if not self._use_ax_lbl:
                        self._use_ax_lbl = self.fresh('useax')
                    self.cond_jump(cond, self._use_ax_lbl, True)
                    return
                done = self.jfalse(cond)
                self.stmt(then[0])
                self.lbl(done)
                return
            # Shared return value.  If this is its FIRST occurrence, place the
            # block right here (cond true falls into it, cond false skips
            # past); later occurrences JCC back to it.  Matches MSC placing
            # the block at the first `return K` even when that is an
            # `if (cond) return K` (e.g. WRITE_FCB's FAT-chain error exit).
            if repr(val) in self.shared_returns:
                key = repr(val)
                # Outside a loop, MSC places the shared block at the FIRST
                # `return K` (here), with later ones jumping back.  Inside a
                # loop it instead places it at the fall-through occurrence, so
                # there this `if (cond) return K` JCCs forward to it.  A
                # deferred reg-var return always JCCs forward (block at tail).
                # A const return that is the suffix of a defer-to-last dup
                # block always JCCs forward into that block's `return K`.
                if (
                    key not in self.shared_ret_placed
                    and not self.break_lbls
                    and key != self._regvar_ret_defer
                    and key not in self._sret_cond_defer
                    and key not in self._tail_shared_ret
                ):
                    done = self.jfalse(cond)
                    self.stmt(then[0])  # places the shared block + return
                    self.lbl(done)
                    return
                lbl = self.shared_ret_lbls.setdefault(key, self.fresh('sret'))
                self.cond_jump(cond, lbl, True)
                return
            # `if (cond) return f(a0, …);` whose MULTI-arg tail is shared —
            # skip past on false, then route through the shared block.
            if (
                ncall(val)
                and nid(val[1])
                and (
                    self._ncall_key(val) in self._ncall_shared
                    or (n11(val), len(val[2])) in self._ncall_shared_ax
                )
            ):
                done = self.jfalse(cond)
                self._emit_ncall_return(val, False)
                self.lbl(done)
                return
            # `if (cond) return f(arg);` whose call tail is shared — skip past
            # on false, then load the arg into AX and fall into / jump to the
            # one `push ax; call f; add sp,2; jmp ret` block.
            if (
                ncall(val)
                and nid(val[1])
                and n11(val) in self._shared_call_tail
                and len(val[2]) == 1
            ):
                # Identical guarded exits (the two `if(net_result!=0) return
                # lookup_error_msg(net_result)`) cross-jump to one block that
                # loads the arg and jumps to the shared call tail.
                body_key = repr(then)
                if body_key in self.dup_blocks:
                    if body_key in self.block_labels:
                        self.cond_jump(cond, self.block_labels[body_key], True)
                        return
                    done = self.jfalse(cond)
                    blk = self.fresh('blk')
                    self.lbl(blk)
                    self.block_labels[body_key] = blk
                    # The guard tested `arg` into AL; it is live at every entry
                    # (fall-through and cross-jump), so the block reuses it
                    # (MSC's bare `sub ah,ah`, no reload).
                    arg = val[2][0]
                    if (
                        self.ucharty(arg)
                        and cond[0] == 'cmp'
                        and arg in (cond[2], cond[3])
                    ):
                        self.al = arg[1]
                    self.stmt(then[0])
                    self.lbl(done)
                    return
                done = self.jfalse(cond)
                self._emit_call_tail_return(val)
                self.lbl(done)
                return
            # Deferred const return: jump forward to a single cold block
            # emitted just before the epilogue (see _defer_const_ret).
            if num(val) and self._defer_const_ret:
                key = repr(val)
                if key not in self._deferred_const:
                    self._deferred_const[key] = (self.fresh('cret'), val)
                self.cond_jump(cond, self._deferred_const[key][0], True)
                return
            # Identical constant returns share one block (MSC cross-jumping):
            # a later `if (cond) return K` jumps straight to the first block.
            if num(val) and val in self.return_blocks:
                self.cond_jump(cond, self.return_blocks[val], True)
                return
            # if (cond) return EXPR; — skip past on false, load+jmp on true.
            # For a constant, label the load so later identical returns reuse it.
            done = self.jfalse(cond)
            if num(val):
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
        if (
            not els
            and self._block_terminates(then)
            and repr(then) in self.dup_blocks
        ):
            key = repr(then)
            # Defer-to-last: every occurrence but the LAST jumps forward to
            # the one cold copy; the last places it inline (Pattern A).
            if key in self._dup_last_total:
                self._dup_seen[key] = self._dup_seen.get(key, 0) + 1
                lbl = self.block_labels.setdefault(key, self.fresh('blk'))
                if self._dup_seen[key] < self._dup_last_total[key]:
                    self.cond_jump(cond, lbl, True)
                    return
                done = self.jfalse(cond)
                self.lbl(lbl)
                self.emit_arms(then)
                self.lbl(done)
                return
            if key in self.block_labels:
                self.cond_jump(cond, self.block_labels[key], True)
                return
            done = self.jfalse(cond)
            blk = self.fresh('blk')
            self.lbl(blk)
            self.block_labels[key] = blk
            self.emit_arms(then)
            self.lbl(done)
            return
        if els:
            # MSC has a single if-else layout (Pattern A): test, JCC to
            # `else` when the condition is FALSE, then-block (fall-through),
            # jmp done, else.  An OR condition is written De Morgan (as `&&`
            # with the branches swapped), so there is no separate "OR" form.
            else_lbl = self.fresh('else')
            done = self.fresh('done')
            self.cond_jump(cond, else_lbl, False)
            # When both arms assign the same reg var and one is forced
            # through AX, route both via AX so the `mov reg,ax` tail merges.
            via_ax = self._regvar_branches_via_ax(then, els)
            saved_force = self._force_regvar_ax
            self._force_regvar_ax = via_ax
            saved_var_force = self._force_var_ax
            self._force_var_ax = self._branches_assign_same_var(then, els)
            merge_tgt = n11(then[-1][1]) if self._force_var_ax else None
            # Capture each branch's atoms in isolation.  Propagate the outer
            # if's tail position to each branch's last statement so
            # tail-calls correctly skip `add sp, N`.
            snap = self.snapshot()
            # The then-arm jumps to `done`.  A trailing *void call* tail-skips
            # only when the else-arm also ends in a call — then both merge into
            # one shared call that falls through to the epilogue; otherwise the
            # standalone then-call keeps its `add sp,N` (returns / nested ifs
            # always propagate tail for their own tail-calls).
            else_last_call = self._arm_ends_in_call(els)
            # A trailing void call tail-folds its cleanup only when BOTH
            # arms end in the SAME call (they merge into one shared tail).
            then_tgt = self._arm_tail_call_target(then)
            merge_call = then_tgt and then_tgt == self._arm_tail_call_target(els)
            for i, ss in enumerate(then):
                void_call = ss[0] == 'expr' and ncall(ss[1])
                t = tail and i == len(then) - 1 and (not void_call or merge_call)
                self._peek_next = then[i + 1] if i + 1 < len(then) else None
                # At a merge (this if has an else and both arms end in a
                # call), the final shared call is reached from BOTH arms, so a
                # far-pointer held in ES:BX from within only this arm isn't
                # live on every edge.  Spill it ONLY when ES:BX holds a far
                # ptr that is a DIRECT id-argument of that call (so its push
                # would reuse ES:BX) — dos_fn_4f's `*(uint far*)fcb=0` then
                # `set_fcb_handle_or_clear(fcb, …)`.  Leave it when ES:BX
                # feeds an INNER call arg (dos_fn_68's `dispatch_fcb_open(rec)`
                # legitimately reuses es:bx=rec before pushing fcb).
                if (
                    i == len(then) - 1
                    and void_call
                    and else_last_call
                    and self.esbx in {a[1] for a in n12(ss) if nid(a)}
                ):
                    self.esbx = self.bx = None
                self.stmt(ss, tail=t)
            then_chunk = self.extract(snap)
            # else_lbl is reached via the JCC, so the else branch starts
            # with cold register caches (unlike the fall-through then).
            self.al = self.ax = self.bx = self.di = self.esbx = None
            self._ah_zero = False  # AH unknown at the else JCC target
            snap = self.snapshot()
            for i, ss in enumerate(els):
                self._peek_next = els[i + 1] if i + 1 < len(els) else None
                if (
                    i == len(els) - 1
                    and ss[0] == 'expr'
                    and ncall(ss[1])
                    and then
                    and then[-1][0] == 'expr'
                    and ncall(then[-1][1])
                    and len(els) == 1
                    and self.esbx in {a[1] for a in n12(ss) if nid(a)}
                ):
                    # Only when the else-arm IS that call: then ES:BX is
                    # whatever the condition left and must not be trusted.  If
                    # the arm did work first (INSTALL_DRIVER's `rec->s_refcnt
                    # = 1; close_sft_entry(rec)`), that work re-established
                    # ES:BX and the call pushes it from the registers.
                    self.esbx = self.bx = None  # merge tail — see then-arm
                e_void = ss[0] == 'expr' and ncall(ss[1])
                self.stmt(
                    ss,
                    tail=(
                        tail and i == len(els) - 1 and (not e_void or merge_call)
                    ),
                )
            else_chunk = self.extract(snap)
            self._force_regvar_ax = saved_force
            self._force_var_ax = saved_var_force
            then_atoms = then_chunk[2]
            else_atoms = else_chunk[2]
            # Find longest common suffix by atom equality.
            n = 0
            while (
                n < len(then_atoms)
                and n < len(else_atoms)
                and then_atoms[-1 - n] == else_atoms[-1 - n]
            ):
                n += 1
            if (
                n > 0
                and not tail
                and self._block_terminates(then)
                and self._block_terminates(els)
            ):
                # Both arms terminate via a mid-function `return` (the shared
                # suffix ends in `jmp <ret>`, not a fall into the epilogue —
                # so `not tail`), e.g. two `return lookup_error_msg(…)`.  MSC
                # lets the then-arm FALL INTO the shared tail and the else-arm
                # jump back UP to it — the mirror of the store-merge layout
                # below.  No `jmp done` from then; else_lbl sits after shared.
                # (A tail-position if/else keeps the store-merge layout, where
                # the shared tail falls into the epilogue — see get_fcb_datetime.)
                shared = self.fresh('shared')
                self.replay(*self.slice_chunk(*then_chunk, 0, len(then_atoms) - n))
                self.lbl(shared)
                self.replay(
                    *self.slice_chunk(
                        *then_chunk, len(then_atoms) - n, len(then_atoms)
                    )
                )
                self.lbl(else_lbl)
                self.replay(*self.slice_chunk(*else_chunk, 0, len(else_atoms) - n))
                self.emit_jmp_short(shared)
                self.lbl(done)
            elif n > 0:
                shared = self.fresh('shared')
                # then-unique + JMP shared
                self.replay(*self.slice_chunk(*then_chunk, 0, len(then_atoms) - n))
                self.emit_jmp_short(shared)
                # else_lbl + else-unique
                self.lbl(else_lbl)
                self.replay(*self.slice_chunk(*else_chunk, 0, len(else_atoms) - n))
                # shared block (taken from else's tail)
                self.lbl(shared)
                self.replay(
                    *self.slice_chunk(
                        *else_chunk, len(else_atoms) - n, len(else_atoms)
                    )
                )
                self.lbl(done)
                # The then-arm's own labels that fell on the shared suffix —
                # e.g. the exit label of a nested if/else (or boolean
                # materialization) whose store IS the shared tail — were
                # dropped by the then-unique slice.  The dropped suffix is
                # atom-identical to the surviving copy (that's what made it
                # shared), so alias ANY label inside it position-relative to
                # the shared block; the chunk-end label maps to `done`.
                # 3-way shared store of WRITE_FCB's extend flag and the
                # nested set_fcb tails of DOS_FN_57 rely on this.
                then_b, _, then_atom_list, then_labels = then_chunk
                boundary = sum(
                    self.atom_len(a) for a in then_atom_list[: len(then_atoms) - n]
                )
                for nm, p in then_labels.items():
                    if boundary <= p <= len(then_b):
                        self.labels[nm] = self.labels[shared] + (p - boundary)
                # the merged store tail (`mov [bp+d],ax`/`,al`) leaves the
                # target live in AX (or AL for a uchar) for a following use.
                if merge_tgt and merge_tgt in self.locals:
                    if self.lt(merge_tgt) == 'uchar':
                        self.al = merge_tgt
                    else:
                        self.ax = merge_tgt
                elif (
                    else_atoms[-1][0] == 'raw'
                    and len(else_atoms[-1][1]) == 3
                    and else_atoms[-1][1][0] == 0xA3
                ):
                    # Shared suffix ends in a word-GLOBAL store (`mov [a],ax`,
                    # A3): both paths flowed through it, so the value is in AX
                    # on either — MSC keeps it for a following compare
                    # (read_back_fat_entry's merged BUF_CHUNK store then
                    # `cmp ax,0FFFFh`).  lbl(done) cleared caches; re-tag.
                    a = n11(else_atoms[-1]) | (n12(else_atoms[-1]) << 8)
                    gname = next(
                        (
                            nm
                            for nm, v in SYMS.items()
                            if v[0] == 'var' and v[1] == a
                        ),
                        None,
                    )
                    if gname:
                        self.ax = gname
            else:
                # No common suffix — emit normally.  Skip the branch-exit
                # jump when the then-block already terminates (ends in a
                # goto/return/break): a `jmp done` after it would be dead code
                # and MSC's no-optimizer emits none.
                self.replay(*self.slice_chunk(*then_chunk, 0, len(then_atoms)))
                if not self._block_terminates(then):
                    self.emit_jmp_short(done)
                self.lbl(else_lbl)
                self.replay(*self.slice_chunk(*else_chunk, 0, len(else_atoms)))
                self.lbl(done)
        else:
            # if-no-else: Pattern A (jump past then if cond is false)
            done = self.jfalse(cond)
            self.emit_arms(then)
            self.lbl(done)
        return

    def expr_stmt(self, e, tail=False):
        # MSC re-evaluates a scaled entry INDEX at each statement (only ES:BX
        # survives) — drop any idxsi tag so the next entry read re-muls.
        if isinstance(self.si, tuple) and self.si[0] == 'idxsi':
            self.si = None
        if isinstance(self.di, tuple) and self.di[0] == 'idxsi':
            self.di = None
        if e[0] == 'comma':  # `a, b` (e.g. a for-update list)
            for sub in e[1]:
                self.expr_stmt(sub)
            return
        # A discarded comparison statement (`devbit == 0;`) — emit only the
        # compare for its flag side effect, no branch.  MSC leaves this dead
        # `cmp byte [local],imm` in DOS_FN_10 before the unconditional
        # `fcb[0x1a] |= 0x40`.
        if (
            e[0] == 'cmp'
            and nid(e[2])
            and e[2][1] in self.locals
            and self.lt(e[2][1]) == 'uchar'
            and num(e[3])
        ):
            disp = self.ld(e[2][1])
            self.emit(0x80, 0x7E, disp & 0xFF, e[3][1] & 0xFF)  # cmp byte[bp+d],imm
            return
        # Shared BYTE-STORE error funnel (see emit_func / _find_byte_funnel): a
        # discarded terminal `INNER(code…)` whose next sibling is the funnel byte
        # store routes through the shared INNER looktail (per arg count) and the
        # `les bx,[BASE]; mov byte [es:bx+disp],K; jmp epilogue` settail placed at
        # the FIRST exit — the store statement itself is then suppressed.
        bf = self._bfunnel
        if (
            bf
            and e[0] == 'call'
            and nid(e[1])
            and n11(e) == bf['inner']
            and self._byte_store_kc(self._peek_next) == bf['store']
        ):
            argc = len(e[2])
            code = e[2][0]
            if bf['endmode']:
                # Fall-into-label INLINE funnel block (err5): the call and byte
                # store emit in place (the store then falls into the label), but
                # the suffix from arg1's push is REGISTERED so a goto-
                # continuation twin can jump into it.
                if id(e) in bf['inline_blocks']:
                    argc = len(e[2])
                    for a in reversed(e[2][2:]):
                        self.push_arg(a)
                    self.expr_to_ax(e[2][1])
                    key = (argc, bf['inline_blocks'][id(e)])
                    lb = bf['inline_push'].setdefault(key, self.fresh('ipush'))
                    self.lbl(lb)
                    self.emit(0x50)  # push ax (arg1 — the converge point)
                    self.expr_to_ax(e[2][0])
                    self.emit(0x50)  # push ax (arg0)
                    self.emit_call(sa(bf['inner']))
                    self.emit(0x83, 0xC4, 2 * argc)  # add sp, N
                    self.clob()
                    return  # store NOT suppressed — emits inline next
                # `INNER(...); store; goto L` twin of an inline block falling
                # into L: push the shared trailing args, load THIS exit's arg1
                # and jump into the inline block at its arg1-push (err523).
                if id(e) in bf['goto_exits']:
                    key = (len(e[2]), bf['goto_exits'][id(e)])
                    lb = bf['inline_push'].get(key)
                    if lb is not None:
                        for a in reversed(e[2][2:]):
                            self.push_arg(a)
                        self.expr_to_ax(e[2][1])
                        self.emit_jmp_short(lb)
                        self._bfun_suppress_store = self._peek_next
                        self._bfun_suppress_goto = True
                        return
                if id(e) not in bf['exit_ids']:
                    self.gen_call(e)  # not a funnel exit — plain discarded call
                    return
                # End-placement: per-argc holder keeps the full block; everyone
                # else pushes its trailing args, loads its code and jumps to the
                # holder's `push ax` — or straight to an earlier same-code load.
                if bf['store_lbl'] is None:
                    bf['store_lbl'] = self.fresh('bstore')
                lt = bf['looktails'].get(argc)
                if lt is None:
                    lt = bf['looktails'][argc] = {
                        'push': self.fresh('bpush'),
                        'loads': {},
                    }
                code_r = repr(code)
                if e is bf['holders'].get(argc):
                    for a in reversed(e[2][1:]):
                        self.push_arg(a)  # trailing args, right-to-left
                    if code_r not in lt['loads']:
                        lt['loads'][code_r] = self.fresh('bload')
                    self.lbl(lt['loads'][code_r])
                    self.expr_to_ax(code)
                    self.lbl(lt['push'])
                    self.emit(0x50)  # push ax
                    self.emit_call(sa(bf['inner']))
                    self.emit(0x83, 0xC4, 2 * argc)  # add sp, N
                    self.clob()
                    if e is bf['tail_call']:
                        # The function-tail exit: the byte store falls straight
                        # into the epilogue.
                        self.lbl(bf['store_lbl'])
                        base, disp, K = bf['store']
                        self.emit_les(base)
                        if disp:
                            self.e26(0xC6, 0x47, disp & 0xFF, K)
                        else:
                            self.e26(0xC6, 0x07, K)
                        self.clob()
                    else:
                        self.emit_jmp_short(bf['store_lbl'])
                elif code_r in lt['loads']:
                    for a in reversed(e[2][1:]):
                        self.push_arg(a)
                    self.emit_jmp_short(lt['loads'][code_r])
                else:
                    for a in reversed(e[2][1:]):
                        self.push_arg(a)
                    lt['loads'][code_r] = self.fresh('bload')
                    self.lbl(lt['loads'][code_r])
                    self.expr_to_ax(code)
                    self.emit_jmp_short(lt['push'])
                self._bfun_suppress_store = self._peek_next
                return
            if bf['settail'] is None:
                bf['settail'] = self.fresh('bsettail')
            lt = bf['looktails'].get(argc)
            if lt is None:
                lt = bf['looktails'][argc] = {
                    'load': self.fresh('blookload'),
                    'push': self.fresh('blookpush'),
                    'load_repr': repr(code),
                }
                for a in reversed(e[2][1:]):
                    self.push_arg(a)  # trailing args, right-to-left
                if argc == 1:
                    self.lbl(lt['load'])
                self.expr_to_ax(code)
                self.lbl(lt['push'])
                self.emit(0x50)  # push ax
                self.emit_call(sa(bf['inner']))  # call INNER (result discarded)
                self.emit(0x83, 0xC4, 2 * argc)  # add sp, N
                self.clob()
                if not bf['placed']:
                    # First exit overall: the byte-store settail falls in here.
                    self.lbl(bf['settail'])
                    base, disp, K = bf['store']
                    self.emit_les(base)
                    if disp:
                        self.e26(0xC6, 0x47, disp & 0xFF, K)  # mov byte[es:bx+d],K
                    else:
                        self.e26(0xC6, 0x07, K)  # mov byte[es:bx],K
                    self.clob()
                    self.emit_jmp_short(self.func_ret_lbl)  # jmp epilogue
                    bf['placed'] = True
                else:
                    self.emit_jmp_short(bf['settail'])
            elif argc == 1 and repr(code) == lt['load_repr']:
                self.emit_jmp_short(lt['load'])  # share the code load
            else:
                for a in reversed(e[2][1:]):
                    self.push_arg(a)
                self.expr_to_ax(code)
                self.emit_jmp_short(lt['push'])
            self._bfun_suppress_store = self._peek_next
            return
        # Shared terminal-call error funnel (see emit_func / _find_error_funnel):
        # a terminal `OUTER(arg0, V)` routes V→AX and jumps through the shared
        # looktail/settail blocks rather than emitting its own copy of the call.
        fn = self._efunnel
        if (
            fn
            and e[0] == 'call'
            and nid(e[1])
            and n11(e) == fn['outer']
            and len(e[2]) == 2
            and repr(e[2][0]) == fn['arg0']
            and (self._peek_next is None or self._peek_next[0] in ('return', 'goto', 'label'))
            and not (
                self._peek_next
                and self._peek_next[0] == 'return'
                and self._peek_next[1]
            )
        ):
            arg0, v = e[2][0], e[2][1]
            if fn['settail'] is None:
                fn['settail'] = self.fresh('settail')
                fn['settail_call'] = self.fresh('setcall')
            if ncall(v) and nid(v[1]) and n11(v) == fn['inner']:
                argc = len(v[2])
                code = v[2][0]  # cdecl arg0 = the AX-carried error code
                lt = fn['looktails'].get(argc)
                if lt is None:
                    # First exit of this arg count places the shared tail.  The
                    # trailing args (arg1..) are pushed per exit; a `load` label
                    # sits before the code→AX load (so a later same-code 1-arg
                    # exit shares it), a `push` label at `push ax; call INNER`.
                    lt = fn['looktails'][argc] = {
                        'load': self.fresh('lookload'),
                        'push': self.fresh('lookpush'),
                        'load_repr': repr(code),
                    }
                    for a in reversed(v[2][1:]):
                        self.push_arg(a)  # trailing args, right-to-left
                    if argc == 1:
                        self.lbl(lt['load'])  # 1-arg: a same-code exit shares it
                    if nid(code):
                        # A VARIABLE code loads `mov al,code; sub ah,ah`, reloading
                        # from its slot (not reusing a just-pushed trailing AX).  A
                        # `zx` label sits at the `sub ah,ah` so a later variable-code
                        # exit shares it (only redoing `mov al,code`) — DOS_FN_41's
                        # lookup(status,…) / lookup(flag_del,…).
                        self.al = self.ax = None
                        self.expr_to_al(code)  # mov al, code
                        lt['zx'] = self.fresh('lookzx')
                        self.lbl(lt['zx'])
                        self.emit(0x2A, 0xE4)  # sub ah, ah
                        self._ah_zero = True
                        self.al = self.ax = None
                    else:
                        lt['zx'] = None
                        self.expr_to_ax(code)  # error code → AX (reuses a just-pushed
                        # equal trailing arg's AX, e.g. lookup(2,2,3,3))
                    self.lbl(lt['push'])
                    self.emit(0x50)  # push ax
                    self.emit_call(sa(fn['inner']))  # call INNER
                    self.emit(0x83, 0xC4, 2 * argc)  # add sp, N
                    self.clob()
                    self.emit_jmp_short(fn['settail'])
                elif argc == 1 and repr(code) == lt['load_repr']:
                    self.emit_jmp_short(lt['load'])  # share the code load
                else:
                    for a in reversed(v[2][1:]):
                        self.push_arg(a)
                    if nid(code) and lt.get('zx'):
                        # variable code: redo `mov al,code`, share the sub ah,ah
                        self.al = self.ax = None
                        self.expr_to_al(code)
                        self.emit_jmp_short(lt['zx'])
                    else:
                        if nid(code):
                            self.al = self.ax = None
                        self.expr_to_ax(code)
                        self.emit_jmp_short(lt['push'])
            else:
                # Plain (non-INNER) value.  The settail (`push ax; push arg0;
                # call OUTER`) is placed at the LAST/fall-through exit; earlier
                # plain exits jump to it with the value in AX.  A plain exit whose
                # ES:BX still holds arg0 (a preceding far store to it) pushes via
                # ES:BX and jumps past the memory-push to the shared call.
                self.expr_to_ax(v)  # value → AX (xor ax,ax for 0)
                if self._peek_next is None:
                    self.lbl(fn['settail'])
                    self.emit(0x50)  # push ax
                    self.push_arg(arg0)  # push arg0 from memory (seg; off)
                    self.lbl(fn['settail_call'])
                    self.emit_call(sa(fn['outer']))  # call OUTER
                    # Tail-skip the `add sp` only when nothing between the call and
                    # `mov sp,bp` needs a clean SP; a saved SI/DI or address-taken
                    # array forces the explicit cleanup (MKDIR's pop si/di).
                    if self.uses_si or self.uses_di or self._has_array_local:
                        nb = 2 + (4 if pf(self.lty(arg0)) else 2)
                        self.emit(0x83, 0xC4, nb)  # add sp, N
                    self.clob()
                elif nid(arg0) and self.esbx == arg0[1]:
                    self.emit(0x50)  # push ax
                    self.emit(0x06)  # push es
                    self.emit(0x53)  # push bx
                    self.emit_jmp_short(fn['settail_call'])
                else:
                    self.emit_jmp_short(fn['settail'])  # value in AX; settail pushes it
            if self._peek_next and self._peek_next[0] == 'return':
                self._efun_suppress = self._peek_next
            return
        # Shared assignment-call tail: `local = f(arg)` reached via >= 2 sites.
        if (
            e[0] == 'assign'
            and nid(e[1])
            and n11(e) in self.locals
            and ncall(e[2])
            and nid(e[2][1])
            and (n11(e), n11(e[2])) in self._sac_total
        ):
            key = (n11(e), n11(e[2]))
            self.expr_to_ax(e[2][2][0])  # arg → AX
            self._sac_seen[key] += 1
            lbl = self._sac_lbl.setdefault(key, self.fresh('sac'))
            if self._sac_seen[key] < self._sac_total[key]:
                self.emit_jmp_short(lbl)  # jmp forward to shared tail
                if self._peek_next and self._peek_next[0] == 'goto':
                    self._sac_suppress_goto = self._peek_next
            else:
                self.lbl(lbl)  # shared tail lives here
                self.emit(0x50)  # push ax
                self.emit_call(sa(n11(e[2])))  # call f
                self.emit(0x83, 0xC4, 0x02)  # add sp, 2
                self.clob()
                self.stal(self.ldi(e))  # mov [bp-off], al
            return
        if e[0] == 'assign':
            self.gen_assign(e[1], e[2])
        elif ncall(e):
            self.gen_call(e, tail=tail)
        elif e[0] == 'postinc':
            self.gen_postinc(e[1])
        elif e[0] == 'postdec':
            self.gen_postdec(e[1])
        elif e[0] == 'opassign':
            self.gen_opassign(e[1], e[2], e[3])
        else:
            self.expr_to_ax(e)

    @staticmethod
    def _flatten_sum(e):
        """Left-spine flatten of a +/- chain into [(op, term), ...], outermost
        term last."""
        terms = []
        while nbin(e) and e[1] in ('+', '-'):
            terms.append((e[1], e[3]))
            e = e[2]
        terms.append(('+', e))
        terms.reverse()
        return terms

    def _sum_has_mul(self, e):
        return any(nbin(t) and t[1] == '*' for _, t in self._flatten_sum(e))

    def _sum_to_cx(self, e):
        """Evaluate an additive chain with CX as the accumulator: the first term
        goes through AX (IMUL needs it) and is parked in CX, then each following
        term either folds straight in from memory or takes another AX trip."""
        terms = self._flatten_sum(e)
        self.expr_to_ax(terms[0][1])
        self.emit(0x8B, 0xC8)  # mov cx, ax
        for op, t in terms[1:]:
            opc = 0x03 if op == '+' else 0x2B
            if self.gkind(t) == 'var':
                self.emit(opc, 0x0E, *w16(SYMS[t[1]][1]))  # add/sub cx, [g]
            else:
                self.expr_to_ax(t)
                self.emit(opc, 0xC8)  # add/sub cx, ax
        self.ax = self.al = self.dx = None

    def _far_self_idx(self, arr, idx):
        """`far_local[*(uint far *)(far_local + d)]` — a far pointer subscripted
        by a word read through ITSELF.  Returns (name, d) or None."""
        if not (nid(arr) and arr[1] in self.locals and pf(self.lty(arr))):
            return None
        if not (nderef(idx) and ncast(idx[1]) and idx[1][1] == 'ptr_far_uint'):
            return None
        b = idx[1][2]
        if nbin(b) and b[1] == '+' and nid(b[2]) and b[2][1] == arr[1] and num(b[3]):
            return (arr[1], b[3][1])
        return None

    def _far_self_idx_base(self, name, d):
        """Emit the shared addressing: the index takes BX, the pointer's own
        offset moves to SI — `les bx,[p]; mov bx,[es:bx+d]; mov si,[p]`."""
        self.emit_les(name)
        self.e26(0x8B, mod8(d) | 0x18 | 0x07, *d8(d))  # mov bx, [es:bx+d]
        if getattr(self, 'essi', None) != name:
            self.emit(0x8B, 0x76, self.ld(name))  # mov si, [bp+p]
            self.essi = name
        self.bx = self.esbx = None

    def gen_opassign(self, op, lhs, rhs):
        # far byte lvalue += uchar local  →  the far pointer loads FIRST (an
        # immediate-free memory op can't touch AL), then the byte, then the
        # r/m8,r8 add — `les bx,[p]; mov al,[bp+d]; add [es:bx],al`
        # (RESOLVE_LOGICAL_DRIVE_LETTER splicing the hop count in at 0x52B5).
        if op in ('+', '-') and self.locid(rhs) and (
            self.lt(rhs[1]) in ('uchar', 'char')
        ):
            fl2 = self.far_lvalue(lhs)
            if fl2 and fl2[2] == 'byte':
                self.emit_les(fl2[0])
                self.ldal(self.ld(rhs[1]))  # mov al, [bp+d]
                d2 = fl2[1]
                self.e26(0x00 if op == '+' else 0x28, mod8(d2) | 0x07, *d8(d2))
                self.al = rhs[1]
                return
        # `<byte global> <op>= <byte expr>`: compute the value in AL, then fold it
        # into memory with the r/m8,r8 form — `add [373h],al`
        # (SET_INPUT_BUFFERS_AND_DESC folding the device's edit bit into EDIT_MODE).
        if self.gkind(lhs) == 'bvar' and not num(rhs) and op in ('+', '-', '|', '&'):
            self.expr_to_al(rhs)
            self.emit({'+': 0x00, '-': 0x28, '|': 0x08, '&': 0x20}[op],
                      0x06, *w16(sa(lhs[1])))
            self.al = self.ax = None
            return
        # far_ptr[reg_var] <op>= imm8 — the whole thing is one r/m instruction
        # (`les bx,[p]; or byte [es:bx+si],30h`), no load/store round trip
        # (PROCESS_DRIVER_REQUEST's hex-digit fixup loop at 0x611F).
        fir = self.far_indexed_reg(lhs)
        if fir and num(rhs) and op in ('|', '&', '+', '-', '^'):
            name, reg = fir
            if reg in ('si', 'di'):
                ext = {'+': 0, '|': 1, '&': 4, '-': 5, '^': 6}[op]
                self.emit_les(name)
                rm = 0x01 if reg == 'di' else 0x00
                self.e26(0x80, rm | (ext << 3), rhs[1] & 0xFF)
                return
        """Compound assign on a far lvalue, emitted as a read-modify-write:
        `|=`/`&=` with an immediate, or `+=` with a register value."""
        # uchar local +=/-= const → add/sub byte [bp+disp], imm8 (byte width, no AX)
        if (
            op in ('+', '-')
            and num(rhs)
            and nid(lhs)
            and self.ucharty(lhs)
            and not self.is_reg_var(lhs[1])
        ):
            disp = self.ld(lhs[1])
            opc = 0 if op == '+' else 5  # /0 add, /5 sub
            self.emit(0x80, 0x46 | (opc << 3), disp, rhs[1] & 0xFF)
            self.invalidate_mem(lhs[1])
            return
        # register var +=/-= const → add/sub si/di, imm (in-place, no AX)
        if op in ('+', '-') and self.rvid(lhs) and num(rhs):
            reg = self.rv(lhs)
            n = rhs[1] & 0xFFFF
            modrm = (sd(0xC6, reg)) if op == '+' else (sd(0xEE, reg))
            if i8(n):
                self.emit(0x83, modrm, n & 0xFF)  # add/sub reg, imm8
            else:
                self.emit(0x81, modrm, n & 0xFF, (n >> 8) & 0xFF)  # imm16
            self._regvar_zero[reg] = False
            return
        # FP_OFF(far_local) += const → add word [bp+disp], imm (advance the offset)
        if op in ('+', '-') and lhs[0] == 'fpoff' and pf(self.lty(lhs[1])) and num(rhs):
            disp = self.ldi(lhs)
            n = rhs[1]
            opc = 0 if op == '+' else 5  # /0 add, /5 sub
            if -128 <= n <= 127:
                self.emit(0x83, 0x46 | (opc << 3), disp, n)
            else:
                self.emit(0x81, 0x46 | (opc << 3), disp, *w16(n))
            # ES (the segment) is unaffected.  MSC KEEPS the stale BX when the
            # next store is an immediate (`mov word[es:bx+d],imm` addresses the
            # pre-advance entry — setup_drive_table's `entry->c_pathoffw=2` after
            # the loop bump), but RELOADS BX (`mov bx,[bp+d]`) when the next store
            # needs a register value, so it addresses the advanced entry
            # (MKDIR's '.'→'..' step, `dir_ent[0x1a]=PARENT`).
            nxt = self._peek_next
            if (
                self.bx == self.esbx
                and nxt
                and nxt[0] == 'expr'
                and nxt[1][0] == 'assign'
                and self.far_lvalue(nxt[1][1])
                and not num(nxt[1][2])
            ):
                self.bx = None
            return
        # <mem> +=/-= reg_var → add/sub <mem>, si/di  (local / FP_OFF(far local) /
        # word global, via _mem_rm — direct, no AX round-trip)
        if op in ('+', '-') and self.rvid(rhs):
            if self._emit_op_reg(lhs, rhs[1], op):
                return
            # long global += reg_var → sub ax,ax; add [g],si/di; adc [g+2],ax
            if op == '+' and self.gkind(lhs) == 'long_var':
                a = SYMS[lhs[1]][1]
                r = rf(self.rv(rhs))
                self.emit(0x2B, 0xC0)  # sub ax, ax
                self.emit(0x01, (r << 3) | 0x06, *w16(a))  # add [g],si/di
                self.emit(0x11, 0x06, *w16(a + 2))  # adc [g+2],ax
                self.zaa()
                return
        # FP_OFF(far_local) +=/-= <expr in AX>  →  add/sub [bp+disp], ax (the
        # offset word).  AX (the rhs) stays live for reuse (e.g. after IO_START
        # += xfer, MSC keeps ax = xfer for FP_OFF(buf) += xfer).
        if op in ('+', '-') and lhs[0] == 'fpoff' and pf(self.lty(lhs[1])):
            disp = self.ldi(lhs)
            self.expr_to_ax(rhs)  # rhs → ax
            self.emit(0x01 if op == '+' else 0x29, 0x46, disp)  # add/sub [bp+disp], ax
            self.al = None
            return
        # FP_SEG(far_local) +=/-= <expr in AX>  →  add/sub [bp+disp+2], ax (the
        # segment word).  Used to paragraph-normalize a far buffer in place:
        # FP_SEG(buf) += FP_OFF(buf) >> 4.
        if op in ('+', '-') and lhs[0] == 'fpseg' and pf(self.lty(lhs[1])):
            disp = self.ldi(lhs)
            self.expr_to_ax(rhs)  # rhs → ax
            self.emit(
                0x01 if op == '+' else 0x29, 0x46, disp + 2
            )  # add/sub [bp+disp+2],ax
            self.al = None
            return
        # FP_OFF/FP_SEG(far_local) &=/|= num  →  and/or word [bp+disp], imm16
        # (paragraph-normalize: FP_OFF(buf) &= 0x0F).  MSC uses the imm16 form
        # (0x81 /4 or /1) even when the constant fits in a byte.
        if (
            op in ('&', '|')
            and lhs[0] in ('fpoff', 'fpseg')
            and pf(self.lty(lhs[1]))
            and num(rhs)
        ):
            disp = self.ldi(lhs)
            if lhs[0] == 'fpseg':
                disp = (disp + 2) & 0xFF
            digit = 4 if op == '&' else 1  # AND=/4, OR=/1
            n = rhs[1]
            self.emit(0x81, 0x46 | (digit << 3), disp, *w16(n))
            return
        far = self.far_lvalue(lhs)
        # *(long far*)(base+disp) +=/-= <uint> → 32-bit far add.  ES:BX holds the
        # far pointer, so the rhs (when it is `*near_ptr`, e.g. *count) is read
        # into AX through SI — BX is busy — then zero-extended (sub dx,dx) and
        # added across both words.  DX is left 0 so a following `return 0`
        # reuses it (`mov ax,dx`).  Used for the dir-size bump at FCB+0x15.
        if far and op in ('+', '-') and far[2] == 'long':
            disp = self.les_fl(far)
            if num(rhs) and 0 <= rhs[1] <= 127:
                # small-const step: imm8 sign-extended forms —
                # `sub word [es:bx+d],1 ; sbb word [es:bx+d+2],0`
                # (DOS_FN_44's s_offset decrement)
                lo_r, hi_r = (0, 2) if op == '+' else (5, 3)  # add/adc, sub/sbb
                self.e26(0x83, mod8(disp) | (lo_r << 3) | 0x07, *d8(disp), rhs[1])
                self.e26(0x83, 0x40 | (hi_r << 3) | 0x07, disp + 2, 0x00)
                return
            if nderef(rhs) and self.lty(rhs[1]) in ('ptr_int', 'ptr_uint'):
                d = self.ldi(rhs)
                self.emit(0x8B, 0x76, d)  # mov si, [bp+d]
                self.emit(0x8B, 0x04)  # mov ax, [si]
            else:
                self.expr_to_ax(rhs)
            opc, hic = self.long_opsel(op)
            self.e26(opc, mod8(disp) | 0x07, *d8(disp))  # add/sub [es:bx+d], ax
            self.e26(hic, 0x40 | 0x57, disp + 2)  # adc/sbb [es:bx+d+2], dx
            self.ax = self.al = self.si = None
            self.dx = 0
            return
        # far_word += expr  →  eval expr to AX, then `add [es:bx+disp], ax`
        if far and op == '+' and not num(rhs):
            base, disp, kind = far
            self.expr_to_ax(rhs)
            self.emit_les(base)
            modrm = mod8(disp) | 0x07
            self.e26(0x01, modrm, *d8(disp))  # add [es:bx+d],ax
            self.zaa()
            return
        if far and num(rhs) and op in ('|', '&'):
            base, disp, kind = far
            self.emit_les(base)
            digit = {'|': 1, '&': 4}[op]  # OR=/1, AND=/4
            modrm = mod8(disp) | (digit << 3) | 0x07
            n = rhs[1]
            if kind == 'byte':
                self.e26(0x80, modrm, *d8(disp), n)
            else:
                self.e26(0x81, modrm, *d8(disp), *w16(n))
            # an immediate op on far MEMORY never touches AX — keep the caches
            # (UNJOIN_DRIVE's `cds->c_flagsh &= 0CFh` sits between the call that
            # loaded AL and the `cmp al,1` that reads it back, 0x7578)
            return
        # FP_OFF(*bufp) += expr — bufp is a near ptr to a far ptr; add to the
        # offset word it points at: mov bx,[bp+disp]; add [bx], si/di/ax
        if (
            op == '+'
            and lhs[0] == 'fpoff'
            and nderef(lhs[1])
            and self.lty(n11(lhs)).startswith('ptr_ptr_far')
        ):
            disp = self.ld(n11(lhs[1]))
            if num(rhs):
                # constant advance → `add word [bx], imm` (no AX round-trip)
                self.ldbx(disp)  # mov bx, [bp+disp]
                n = rhs[1]
                if -128 <= n <= 127:
                    self.emit(0x83, 0x07, n & 0xFF)  # add word [bx], imm8 (sign-ext)
                else:
                    self.emit(0x81, 0x07, n & 0xFF, (n >> 8) & 0xFF)  # imm16
                self.bx = None
                return
            if self.rvid(rhs):
                self.ldbx(disp)  # mov bx, [bp+disp]
                self.emit(
                    0x01, 0x37 if self.rv(rhs) == 'si' else 0x3F
                )  # add [bx], si/di
            elif self._is_rm(rhs):
                # simple memory load: load BX first, then AX
                self.ldbx(disp)  # mov bx, [bp+disp]
                self.expr_to_ax(rhs)  # mov ax, [rhs]
                self.emit(0x01, 0x07)  # add [bx], ax
            else:
                # computed addend: evaluate to AX first, then load BX
                self.expr_to_ax(rhs)
                self.ldbx(disp)  # mov bx, [bp+disp]
                self.emit(0x01, 0x07)  # add [bx], ax
            self.bx = None
            return
        # uchar_local += far byte lvalue  →  al = far byte; add [bp+disp], al
        if op == '+' and self.ucharty(lhs):
            fr = self.far_lvalue(rhs)
            if fr and fr[2] == 'byte':
                self.expr_to_al(rhs)  # mov al,[es:bx+disp] (reuse es:bx)
                d = self.ld(lhs[1])
                self.emit(0x00, 0x46, d)  # add [bp+disp], al
                self.zaa()
                return
        # word var global +=/-= SMALL CONST  →  the imm8 r/m form, no AX trip:
        # `add word [g],2` (EDIT_TEMPLATE_PROCESS charging 2 cells for a `^X`).
        if op in ('+', '-') and self.gkind(lhs) == 'var' and num(rhs) and (
            0 <= rhs[1] <= 0x7F
        ):
            self.emit(0x83, 0x06 if op == '+' else 0x2E,
                      *w16(SYMS[lhs[1]][1]), rhs[1] & 0xFF)
            return
        # word var global +=/-= expr  →  eval to AX, then `add/sub [addr], ax`
        if op in ('+', '-') and self.gkind(lhs) == 'var':
            addr = SYMS[lhs[1]][1]
            self.expr_to_ax(rhs)
            self.emit(0x01 if op == '+' else 0x29, 0x06, *w16(addr))
            self.zaa()
            return
        # var global &=/|= reg_var  →  and/or [addr], si/di
        if op in ('&', '|') and self.gkind(lhs) == 'var' and self.rvid(rhs):
            addr = SYMS[lhs[1]][1]
            r = rf(self.rv(rhs))
            opc = 0x21 if op == '&' else 0x09
            self.emit(opc, (r << 3) | 0x06, *w16(addr))  # and/or [addr],si/di
            return
        # *(uint far*)(far_var + <index> + const) >>= 1  →  compute the index into
        # SI (scratch), les bx,[tbl], shr word [es:bx+si+const], 1
        if (
            op == '>>'
            and rhs == ('num', 1)
            and nderef(lhs)
            and ncast(lhs[1])
            and pf(n11(lhs))
        ):
            terms = []

            def _ft(n):
                if nbin(n) and n[1] == '+':
                    _ft(n[2])
                    _ft(n[3])
                else:
                    terms.append(n)

            _ft(n12(lhs))
            bases = [t for t in terms if self.gfar(t)]
            const = sum(t[1] for t in terms if num(t)) & 0xFF
            varts = [t for t in terms if not (num(t) or (self.gfar(t)))]
            if len(bases) == 1 and len(varts) == 1:
                self.expr_to_ax(varts[0])  # ax = index (0x35*i)
                self.emit(0x8B, 0xF0)  # mov si, ax
                self.emit_les(bases[0][1])  # les bx, [tbl]
                self.e26(0xD1, 0x68, const)  # shr word[es:bx+si+disp],1
                self.ax = self.al = self.esbx = self.bx = None
                return
        # local long +=/-= far long lvalue  →  les; DX:AX = far long; add/adc (or
        # sub/sbb) both words into [bp+disp]/[bp+disp+2].  DOS_FN_42's SEEK_CUR/
        # SEEK_END accumulate (`pos += rec->s_offset`).
        if (
            op in ('+', '-')
            and self.stkid(lhs)
            and self.lt(lhs[1]) == 'long'
        ):
            fr = self.far_lvalue(rhs)
            if fr and fr[2] == 'long' and not isinstance(fr[0], tuple):
                rb, rd, _ = fr
                disp = self.ld(lhs[1])
                self.emit_les(rb)  # les bx, [rec]
                self.e26(0x8B, mod8(rd) | 0x07, *d8(rd))  # mov ax, es:[bx+rd]
                self.e26(0x8B, 0x57, rd + 2)  # mov dx, es:[bx+rd+2]
                # DX already holds the high word (loaded above); emit the
                # opcode pair directly rather than long_opsel (which zeroes DX)
                opc, hic = (0x01, 0x11) if op == '+' else (0x29, 0x19)
                self.emit(opc, 0x46, disp)  # add/sub [bp+disp], ax
                self.emit(hic, 0x56, disp + 2)  # adc/sbb [bp+disp+2], dx
                self.ax = self.dx = None
                return
        # local var -= far word lvalue  →  mov ax,[es:bx+d] (reuse es:bx); sub [bp+disp],ax
        if op in ('+', '-') and self.stkid(lhs):
            fr = self.far_lvalue(rhs)
            if fr and fr[2] == 'word':
                disp = self.ld(lhs[1])
                self.expr_to_ax(rhs)  # mov ax, [es:bx+d]
                opc = 0x01 if op == '+' else 0x29
                self.emit(opc, 0x46, disp)  # add/sub [bp+disp], ax
                self.ax = None
                return
        # long_var global +=/-= int/uint local  →  ax=local (reused if live); the
        # 16-bit term is zero-extended (sub dx,dx) and added to both words.
        if op in ('+', '-') and self.gkind(lhs) == 'long_var' and wint(self.lty(rhs)):
            a = SYMS[lhs[1]][1]
            self.expr_to_ax(rhs)  # ax = local (no reload if cached)
            opc, hic = self.long_opsel(op)
            self.emit(opc, 0x06, *w16(a))  # add/sub [a], ax
            self.emit(hic, 0x16, *w16(a + 2))  # adc/sbb [a+2], dx
            self.dx = None
            return
        # long_var global +=/-= <const>  →  add/sub word[lo],imm ; adc/sbb word[hi],0
        # (the const's high 16 bits are 0, so only the carry propagates upward).
        if op in ('+', '-') and self.gkind(lhs) == 'long_var' and num(rhs):
            a = SYMS[lhs[1]][1]
            n = rhs[1] & 0xFFFF
            lo_op = 0x06 if op == '+' else 0x2E  # add/sub word[disp16]
            hi_op = 0x16 if op == '+' else 0x1E  # adc/sbb word[disp16]
            if n < 128:
                self.emit(0x83, lo_op, *w16(a), n)  # add/sub word[a],imm8
            else:
                self.emit(0x81, lo_op, *w16(a), *w16(n))  # add/sub word[a],imm16
            self.emit(0x83, hi_op, *w16(a + 2), 0x00)  # adc/sbb word[a+2],0
            self.dx = None
            return
        # local var +=/-= <expr in AX>  →  rhs→ax; add/sub [bp+disp], ax.  The
        # destination is memory, so AX (the loaded rhs) stays live for a reuse by
        # the next statement (MSC keeps `ax = xfer` across `IO_START += xfer`).
        if op in ('+', '-') and self.stkid(lhs):
            disp = self.ld(lhs[1])
            self.expr_to_ax(rhs)  # rhs → ax
            self.emit(0x01 if op == '+' else 0x29, 0x46, disp)  # add/sub [bp+disp], ax
            self.al = None
            return
        # *p += expr  where p is a near int/uint pointer → mov bx,[p]; rhs→ax; add [bx],ax.
        # Reuse BX if it still holds this pointer (e.g. right after reading `*p`).
        if (
            op in ('+', '-')
            and nderef(lhs)
            and self.lty(lhs[1]) in ('ptr_int', 'ptr_uint')
        ):
            disp = self.ldi(lhs)
            if self.bx != ('nptr', n11(lhs)):
                self.ldbx(disp)  # mov bx, [bp+disp]
            self.expr_to_ax(rhs)  # rhs → ax
            self.emit(0x01 if op == '+' else 0x29, 0x07)  # add/sub [bx], ax
            self.ax = self.bx = None
            return
        # reg-var (SI/DI) +=/-= uchar  →  al=uchar; sub ah,ah; add/sub si/di,ax
        # (RENAME_FCB steps its block cursor `si += qcount`).
        if op in ('+', '-') and self.rvid(lhs) and (
                self.ucharty(rhs) or self.gkind(rhs) == 'bvar'):
            reg = self.regvars[lhs[1]]
            self.expr_to_ax(rhs)  # al = uchar; sub ah, ah
            self.emit(0x03 if op == '+' else 0x2B, sd(0xF0, reg))  # add/sub si/di, ax
            if reg == 'si':
                self.si = None
            else:
                self.di = None
            return
        # reg-var +=/-= reg-var  →  add/sub si,di in place
        # (PARSE_PATH_WITH_DRIVE's `len += namelen` after the component copy).
        if op in ('+', '-') and self.rvid(lhs) and self.rvid(rhs):
            r = rf(self.rv(lhs)) << 3 | rf(self.rv(rhs))
            self.emit(0x03 if op == '+' else 0x2B, 0xC0 | r)  # add/sub si/di,si/di
            if self.rv(lhs) == 'si':
                self.si = None
            else:
                self.di = None
            return
        # int local >>= 1  →  shr word [bp+d], 1 (FIND_FREE_DRIVER_SLOT halving
        # the running best count in place).
        if (
            op == '>>'
            and self.stkid(lhs)
            and wint(self.lt(lhs[1]))
            and num(rhs)
            and rhs[1] == 1
        ):
            self.emit(0xD1, 0x6E, self.ld(lhs[1]))  # shr word [bp+d], 1
            self.invalidate_mem(lhs[1])
            return
        ni('opassign', op, lhs, rhs)

    # ---- assignment / call / postinc ----
    def _leftmost_long_id(self, e):
        """The identifier reached by descending the left spine through
        casts and +/-/<</>> — the first sub-value that gets loaded into AX:DX.
        Used to decide whether a just-cached AX:DX pair will be reused in place."""
        if not isinstance(e, tuple):
            return None
        if nid(e):
            return e[1]
        if ncast(e):
            return self._leftmost_long_id(e[2])
        if nbin(e) and e[1] in ('+', '-', '<<', '>>'):
            return self._leftmost_long_id(e[2])
        return None

    def _is_long4(self, node):
        """True if node is a 4-byte (long or far-ptr) scalar lvalue —
        a local/param (type 'long' or 'ptr_far_*') or a long_var/far_var global."""
        if not nid(node):
            return False
        n = node[1]
        if n in self.locals:
            t = self.lt(n)
            return t == 'long' or pf(t)
        return n in SYMS and SYMS[n][0] in ('long_var', 'far_var')

    def load_long_axdx(self, node):
        """Load a 4-byte lvalue into AX (low) : DX (high)."""
        n = node[1]
        # The full 4-byte value is already live in AX:DX (e.g. right after
        # `*(long far*)p = n` — the store leaves the value in place).
        if self.axdx_var and self.axdx_var == n:
            return
        # A far pointer whose ES:BX is still cached (e.g. after `g[..]` field
        # reads) reuses it: mov ax,bx; mov dx,es — no reload from memory.  This
        # holds for a far LOCAL or param just as well as a far_var global (the
        # line editor's `INPUT_FCB_PTR = tmpl` right after reading `tmpl[1]`).
        if self.esbx == n and (
            gsym(n, 'far_var') or (n in self.locals and pf(self.lty(node)))
        ):
            self.emit(0x8B, 0xC3)  # mov ax, bx
            self.emit(0x8C, 0xC2)  # mov dx, es
            self.tag_axdx(n)
            return
        # If AX already holds this long global's low word (right after a widening
        # store `g = (unsigned)x`), keep it and load only DX (`mov dx,[a+2]`).
        if self.ax == ('low', n) and gsym(n, 'long_var'):
            a = sa(n)
            self.emit(0x8B, 0x16, *w16(a + 2))  # mov dx, [a+2]
            self.tag_axdx(n)
            return
        # If AX already holds this local's low/offset word (right after
        # `local = (long)x` or `FP_OFF(p) = …`), keep it and only load DX.
        if self.ax in (('low', n), ('fpoff', n)) and n in self.locals:
            disp = self.ld(n)
            self.emit(0x8B, 0x56, disp + 2)  # mov dx, [bp+disp+2]
            self.tag_axdx(n)
            return
        # reuse DX if it already holds this value's high word (e.g. right after
        # `n = far_fn(...)`, where intervening byte ops clobbered only AX).
        keep_dx = self.dx == ('hi', n)
        if n in self.locals:
            disp = self.ld(n)
            self.ldax(disp)  # mov ax, [bp+disp]
            if not keep_dx:
                self.emit(0x8B, 0x56, disp + 2)  # mov dx, [bp+disp+2]
        else:
            a = sa(n)
            self.ldaxm(a)  # mov ax,[a]
            if not keep_dx:
                self.emit(0x8B, 0x16, *w16(a + 2))  # mov dx,[a+2]
        self.ax = None
        self.dx = ('hi', n)
        self.axdx_var = n

    def store_axdx_long(self, node):
        """Store AX:DX into a 4-byte lvalue; leaves DX cached as its high word."""
        n = node[1]
        # A far-local-to-far-local copy (`fcb_copy = fcb`): DX holds the SOURCE's
        # high word on entry and the store makes it the dest's too — remember the
        # alias so a later push of the SOURCE still reuses `push dx` (RENAME_FCB
        # pushes `fcb` to mem_copy_far right after saving `fcb_copy = fcb`).
        prev_dx = self.dx
        if n in self.locals:
            disp = self.ld(n)
            self.stax(disp)  # mov [bp+disp], ax
            self.emit(0x89, 0x56, disp + 2)  # mov [bp+disp+2], dx
        else:
            a = sa(n)
            self.staxm(a)  # mov [a],ax
            self.emit(0x89, 0x16, *w16(a + 2))  # mov [a+2],dx
        # AX holds the low/offset word, DX the high/seg word.  Tag AX so a later
        # push of this same far pointer reuses it — but only while AX survives;
        # any AX/AL write (a sibling `mov ax,imm` call arg, a `mov al,…`) clears
        # the tag, spilling the offset back to memory while DX stays reused.
        self.ax = ('low', n)
        self.dx = ('hi', n)
        self.axdx_var = n  # AX:DX still hold this whole 4-byte value
        self.dx_alias = (
            (n, prev_dx[1])
            if isinstance(prev_dx, tuple) and prev_dx[0] == 'hi' and prev_dx[1] != n
            else None
        )  # valid only while self.dx stays ('hi', n)

    def gen_long(self, node):
        # `c ? a : b` yielding a 4-byte value: both arms materialise into AX:DX
        # and meet at a shared label, exactly like the byte ternary in
        # expr_to_al (DOS_FN_0F picking its name buffer, 0x9F83).
        if node[0] == 'ternary':
            els, end = self.fresh('tern_els'), self.fresh('tern_end')
            self.cond_jump(node[1], els, False)
            self.gen_long(node[2])
            self.emit_jmp_short(end)
            self.lbl(els)
            self.gen_long(node[3])
            self.lbl(end)
            self.ax = self.dx = self.al = None
            return
        # `&global` / a local ARRAY as a 4-byte value: the near address in AX and
        # its segment register in DX (DS for a global, SS for a frame buffer).
        if node[0] == 'addr' and self.near_global_addr(node[1]) is not None:
            self.emit(0xB8, *w16(self.near_global_addr(node[1])))  # mov ax, &g
            self.emit(0x8C, 0xDA)  # mov dx, ds
            self.ax = self.dx = None
            return
        if (
            nid(node)
            and node[1] in self.locals
            and str(self.lty(node)).startswith('arr')
        ):
            self.lea_ax(self.ld(node[1]))  # lea ax, [bp-off]
            self.emit(0x8C, 0xD2)  # mov dx, ss
            self.ax = self.dx = None
            return

        """Evaluate a 32-bit (long) expression into DX:AX."""
        if ncast(node) and wlong(node[1]):
            # (ulong)(long expr) / (long)(long expr) — a width-preserving cast
            # of an already-32-bit value is transparent; just evaluate it.
            if self._is_long_expr(node[2]):
                self.gen_long(node[2])
                return
            # (long)(int expr) — zero-extend the 16-bit value
            self.expr_to_ax(node[2])
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self.zad()
            return
        # ((long)HI << 16) | LO — assemble DX:AX from two 16-bit lvalues (high
        # word HI, low word LO): `mov ax,[LO]; mov dx,[HI]` (DOS_FN_10's fcb
        # position `((long)fcb[0x18]<<16 | fcb[0x1d])` fed to the sector math).
        if (
            nbin(node)
            and node[1] == '|'
            and nbin(node[2])
            and node[2][1] == '<<'
            and node[2][3] == ('num', 16)
            and ncast(node[2][2])
            and wlong(node[2][2][1])
            and nid(node[3])
            and node[3][1] in self.locals
        ):
            hi_n, lo_n = node[2][2][2], node[3]
            self.emit(0x8B, 0x46, self.ld(lo_n[1]) & 0xFF)  # mov ax, [bp+lo]
            self.emit(0x8B, 0x56, self.ld(hi_n[1]) & 0xFF)  # mov dx, [bp+hi]
            self.ax = self.dx = self.axdx_var = None
            return
        if nbin(node) and node[1] == '<<' and num(node[3]) and node[3][1] == 16:
            # (long)<word> << 16 is a register swap, not a shift: MSC puts the
            # word straight into DX and zeroes AX (DISPATCH_FCB_OPEN building
            # the split directory-sector number from s_dirsechi).
            inner = node[2][2] if ncast(node[2]) else node[2]
            fw = self.far_lvalue(inner)
            if fw and fw[2] == 'word':
                disp = self.les_fl(fw)
                self.e26(0x8B, mod8(disp) | 0x10 | 0x07, *d8(disp))  # mov dx,[es:bx+d]
            else:
                self.expr_to_ax(inner)
                self.emit(0x8B, 0xD0)  # mov dx, ax
            self.emit(0x2B, 0xC0)  # sub ax, ax
            self.emit(0x8B, 0xCA)  # mov cx, dx  (MSC keeps the high word live)
            self.ax = self.al = self.axdx_var = None
            return
        if nbin(node) and node[1] in ('<<', '>>'):
            # long <</>> n : DX:AX shifted by CL via the MSC helpers (__lshl /
            # __lshr pin their addresses; the convention is value=DX:AX,
            # count=CL).
            self.gen_long(node[2])  # value → DX:AX
            self._load_cl(node[3])  # count → CL
            helper = '__lshl' if node[1] == '<<' else '__lshr'
            self.emit_call(SYMS[helper][1])  # clobbers AX/BX/CX/DX/ES
            self.clob()
            return
        if ncall(node):
            self.gen_call(node)  # long-returning call → DX:AX
            return
        if ncast(node) and ncall(node[2]):
            self.gen_call(node[2])  # cast over far-pointer returning call → DX:AX
            return
        # A far-pointer retag over a computed value is a byte-level no-op.
        if ncast(node) and pf(node[1]):
            return self.gen_long(node[2])
        # <word expr> + far_ptr_local — a far pointer built from an int written
        # FIRST: the int lands in AX, the pointer's offset word is ADDED to it,
        # the segment rides in DX (DISPATCH_FCB_OPEN's dir-entry pointer
        # `(rec->s_direntx << 5) + buf`).
        if (
            nbin(node)
            and node[1] == '+'
            and nid(node[3])
            and node[3][1] in self.locals
            and pf(self.lt(node[3][1]))
        ):
            self.expr_to_ax(node[2])
            d = self.ld(node[3][1])
            self.emit(0x03, 0x46, d)  # add ax, [bp+d]
            self.emit(0x8B, 0x56, (d + 2) & 0xFF)  # mov dx, [bp+d+2]
            self.zad()
            return
        # A DIVIDE in the middle of a long expression destroys DX:AX, so MSC
        # spills the running total (low -> CX, high -> SI, each just before its
        # register dies), builds the divisor in BX, divides, and REBUILDS the
        # total in BX:DX from the remainder.  The accumulator lives in BX:DX
        # from here on — the trailing term adds into DX/BX and the far pointer
        # is reached through DI, since ES:BX no longer holds it
        # (COMPUTE_CLUSTER_INFO_FOR_FCB's data-area sector, 0x792D).
        _dt = self._long_div_tail(node)
        if _dt:
            head, dividend, bdisp, k, wdisp, base = _dt
            self.gen_long(head)  # running total -> DX:AX
            self.emit_les(base)  # les bx, [bp+base]
            self.emit(0x8B, 0xC8)  # mov cx, ax          (spill the low word)
            self.e26(0x8A, mod8(bdisp) | 0x07, *d8(bdisp))  # mov al,[es:bx+d]
            self.emit(0x2A, 0xE4)  # sub ah, ah
            self.emit(0x8B, 0xD8)  # mov bx, ax
            for _ in range(k):
                self.emit(0x43)  # inc bx               (the divisor)
            self.ldax(self.ld(dividend))  # mov ax, [bp+d]
            self.emit(0x8B, 0xF2)  # mov si, dx          (spill the high word)
            self.emit(0x8B, 0x7E, self.ld(base))  # mov di,[bp+base] (keep the ptr)
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self.emit(0xF7, 0xF3)  # div bx              (remainder -> DX)
            self.emit(0x2B, 0xDB)  # sub bx, bx          (the new high word)
            self.emit(0x03, 0xD1)  # add dx, cx
            self.emit(0x13, 0xDE)  # adc bx, si
            self.e26(0x03, 0x40 | 0x10 | 0x05, wdisp)  # add dx, [es:di+d]
            self.emit(0x83, 0xD3, 0x00)  # adc bx, 0
            self.clob()
            self._lbxdx = True
            return
        if nbin(node) and node[1] in ('+', '-'):
            self.gen_long(node[2])  # accumulate in DX:AX
            # FAR-POINTER arithmetic touches only the OFFSET — C requires no
            # carry into the segment for `far *`, and MSC emits a bare
            # `add ax,n` with no `adc dx,0` (PROCESS_DRIVER_REQUEST's
            # `base + 40h` scan bound at 0x6087).
            # ...for a far_var GLOBAL too, not just a far-pointer local
            # (FILL_DEVICE_FCB_REQUEST's `DRIVER_TABLE + 6` at 0x89C7).
            if (pf(self.lty(node[2])) or self.gkind(node[2]) == 'far_var') and num(
                node[3]
            ):
                n = node[3][1] & 0xFFFF
                self.emit(0x05 if node[1] == '+' else 0x2D, *w16(n))
                self.ax = self.axdx_var = None  # DX still holds the segment
                return
            self._long_add_term(node[1], node[3])
            return
        # a long lvalue whose value is still live in CX:BX (just stored there)
        if nid(node) and self.cxbx_var == node[1]:
            self.emit(0x8B, 0xC1)  # mov ax, cx
            self.emit(0x8B, 0xD3)  # mov dx, bx
            self.zad()
            return
        if self._is_long4(node):
            self.load_long_axdx(node)
            return
        # *bufp — bufp is a near ptr to a far ptr; load the far ptr into DX:AX
        if nderef(node) and self.lty(node[1]).startswith('ptr_ptr_far'):
            disp = self.ldi(node)
            self.ldbx(disp)  # mov bx, [bp+disp]
            self.emit(0x8B, 0x07)  # mov ax, [bx]
            self.emit(0x8B, 0x57, 0x02)  # mov dx, [bx+2]
            self.ax = self.dx = self.bx = None
            return
        # *(T far * far *)(far-ptr [+ disp]) : read the far pointer at
        # [es:bx+disp] into DX:AX (es:bx loaded/cached from the base far ptr).
        if nderef(node) and ncast(node[1]) and n11(node).startswith('ptr_far_ptr'):
            operand, disp = self.split_disp(n12(node))
            # far_var[<scaled>].<far-ptr field> — an si-indexed entry read of a
            # 4-byte field (`DPB_TABLE[i].c_dpb`): mov ax,[es:bx+si+45h];
            # mov dx,[es:bx+si+47h]  (WRITE_DIR_ENTRY climbing out of a SUBST).
            if nbin(operand) and operand[1] == '+' and self.gfar(operand[2]):
                base = ('idx', operand[2][1], operand[3])
                # both halves need an explicit disp byte, so force mod01
                modrm = self.far_rm(base, disp)[0] | 0x40
                self.e26(0x8B, modrm, disp & 0xFF)  # mov ax, [<base>+d]
                self.e26(0x8B, modrm | 0x10, (disp + 2) & 0xFF)  # mov dx, [+d+2]
                self.zad()
                return
            if pf(self.lty(operand)) or self.gfar(operand):
                self.emit_les(operand[1])
                self.e26(
                    0x8B, 0x07 if disp == 0 else 0x47, *d8(disp)
                )  # mov ax,[es:bx+d]
                self.e26(0x8B, 0x57, disp + 2)  # mov dx,[es:bx+d+2]
                self.zad()
                return
        # *(long far*)(base+d) → load the far long into DX:AX
        if (
            nderef(node)
            and ncast(node[1])
            and n11(node) in ('ptr_far_long', 'ptr_far_ulong')
        ):
            disp = self.far_int_les(node)
            if disp is not None:
                self.e26(0x8B, mod8(disp) | 0x07, *d8(disp))  # mov ax,[es:bx+d]
                self.e26(0x8B, 0x40 | 0x57, disp + 2)  # mov dx,[es:bx+d+2]
                self.zad()
                return
        # 16-bit `*near-int-ptr` in a long context → zero-extend: mov ax,[bx]; sub dx,dx
        if nderef(node) and self.lty(node[1]) in ('ptr_int', 'ptr_uint'):
            self.ensure_bx(n11(node))
            self.emit(0x8B, 0x07)  # mov ax, [bx]
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self.zad()
            return
        # 16-bit int/uint local in a long context → zero-extend: mov ax,[bp+d]; sub dx,dx
        if wint(self.lty(node)):
            d = self.ld(node[1])
            if self.ax != node[1]:  # AX may still hold it (a preceding store/test)
                self.ldax(d)  # mov ax, [bp+d]
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self.zad()
            return
        # *(uint far*)(base+d) in a long context → zero-extend: mov ax,[es:bx+d]; sub dx,dx
        if (
            nderef(node)
            and ncast(node[1])
            and n11(node) in ('ptr_far_uint', 'ptr_far_int')
        ):
            disp = self.far_int_les(node)
            if disp is not None:
                self.e26(0x8B, mod8(disp) | 0x07, *d8(disp))  # mov ax,[es:bx+d]
                self.emit(0x2B, 0xD2)  # sub dx, dx
                self.zad()
                return
        # &far_var[<scaled>].arr[const] — the address of a byte inside a table
        # entry (`&DPB_TABLE[i].c_path[3]`).  When a preceding entry read left
        # ES:BX live the assign/push paths reuse it (`add ax,bx; mov dx,es`);
        # with nothing live the offset:segment pair is built from memory here
        # (WRITE_DIR_ENTRY's SUBST walk, which reads no entry first).
        if node[0] == 'addr' and node[1][0] == 'idx':
            inner = node[1]
            s = inner[1] if z0(inner[2]) else ('bin', '+', inner[1], inner[2])
            if self.fv_axdx_sum(s):
                return
        ni('gen_long', node)

    def _long_add_term(self, op, r):
        """DX:AX +=/-= a term.  A 32-bit term adds/subtracts both words; a
        16-bit term is zero-extended (adc/sbb dx,0)."""
        opc = 0x03 if op == '+' else 0x2B
        hic = 0x13 if op == '+' else 0x1B  # adc/sbb dx, <hi>
        ext = 0xD2 if op == '+' else 0xDA  # adc dx,0 / sbb dx,0
        # 32-bit operand: add/sub both words
        if self.lty(r) == 'long':
            d = self.ld(r[1])
            self.emit(opc, 0x46, d)  # add/sub ax,[bp+d]
            self.emit(hic, 0x56, d + 2)  # adc/sbb dx,[bp+d+2]
            self.zad()
            return
        if self.gkind(r) == 'long_var':
            a = SYMS[r[1]][1]
            self.emit(opc, 0x06, *w16(a))  # add/sub ax,[a]
            self.emit(hic, 0x16, *w16(a + 2))  # adc/sbb dx,[a+2]
            self.zad()
            return
        if self.locid(r) and wint(self.lt(r[1])):
            d = self.ld(r[1])
            self.emit(opc, 0x46, d)  # add/sub ax,[bp+d]
            self.emit(0x83, ext, 0x00)  # adc/sbb dx,0 (zero-ext)
            self.zad()
            return
        if self.gvw(r):
            a = SYMS[r[1]][1]
            self.emit(opc, 0x06, *w16(a))  # add/sub ax,[a]
        elif num(r):
            n = r[1] & 0xFFFF
            self.emit(0x05 if op == '+' else 0x2D, *w16(n))
        else:
            far = self.far_lvalue(r)
            if far and far[2] == 'word':
                disp = self.les_fl(far)
                modrm = mod8(disp) | 0x07
                self.e26(opc, modrm, *d8(disp))
            elif far and far[2] == 'byte':
                disp = self.les_fl(far)
                modrm = mod8(disp) | 0x08 | 0x07  # /1 (CL), [bx+disp]
                self.e26(0x8A, modrm, *d8(disp))  # mov cl, [es:bx+disp]
                self.emit(0x2A, 0xED)  # sub ch, ch
                self.emit(0x2B, 0xDB)  # sub bx, bx
                self.emit(0x03, 0xC8 if op == '+' else 0x2B)  # add cx, ax
                self.emit(0x13, 0xDA if op == '+' else 0x1B)  # adc bx, dx
                self.zad()
                return
            else:
                ni('long term', r)
        self.emit(0x83, ext, 0x00)  # adc/sbb dx, 0
        self.zad()

    def _long_div_tail(self, node):
        """`<long> + (<uint local> % (<far byte> + K)) + <far word>` — the one
        long expression shape whose MIDDLE term needs a divide.  Both far
        lvalues must hang off the SAME far-pointer local, because the sequence
        keeps that pointer's segment in ES across the divide and reaches the
        last term through DI.  Returns (head, dividend, bdisp, K, wdisp, base)
        or None."""
        if not (nbin(node) and node[1] == '+'):
            return None
        wf = self.far_lvalue(node[3])
        inner = node[2]
        if not (wf and wf[2] == 'word' and nbin(inner) and inner[1] == '+'):
            return None
        m = inner[3]
        if not (
            nbin(m)
            and m[1] == '%'
            and self.locid(m[2])
            and wint(self.lt(m[2][1]))
        ):
            return None
        d = m[3]
        if not (nbin(d) and d[1] == '+' and num(d[3])):
            return None
        bf = self.far_lvalue(d[2])
        if not (bf and bf[2] == 'byte' and bf[0] == wf[0]):
            return None
        base = wf[0]
        if not (isinstance(base, str) and base in self.locals):
            return None
        return (inner[2], m[2][1], bf[1], d[3][1], wf[1], base)

    def _is_long_expr(self, e):
        """True if expression e evaluates to a 32-bit (long) value."""
        if ncast(e):
            return wlong(e[1])
        if nbin(e) and e[1] in ('+', '-', '<<', '|'):
            return self._is_long_expr(e[2]) or self._is_long_expr(e[3])
        if nid(e):
            n = e[1]
            if n in self.locals:
                return self.lt(n) in ('long',) or pf(self.lt(n))
            return n in SYMS and SYMS[n][0] in ('long_var', 'far_var')
        if ncall(e) and nid(e[1]) and n11(e) in SYMS:
            return SYMS[n11(e)][0] == 'far_func' or n11(e) in LONG_FUNCS
        if (
            nderef(e)
            and ncast(e[1])
            and (n11(e) == 'ptr_far_long' or n11(e).startswith('ptr_far_ptr'))
        ):
            return True  # *(long far*) / *(T far* far*)
        return False

    def _far_ptr_add_base(self, node):
        """If `node` is `far_ptr_local + <int terms>`, return (base_name, addends)."""
        if not nbin(node) or node[1] != '+':
            return None
        terms = []

        def _f(n):
            if nbin(n) and n[1] == '+':
                _f(n[2])
                _f(n[3])
            else:
                terms.append(n)

        _f(node)
        base = terms[0]
        if pf(self.lty(base)):
            return (base[1], terms[1:])
        return None

    def _far_ptr_add_to_axdx(self, base_name, addends):
        """Build `base_name + addends` as a far pointer: offset in AX, seg in DX."""
        const = sum(t[1] for t in addends if num(t)) & 0xFFFF
        varts = [t for t in addends if not num(t)]
        boff = self.ld(base_name)
        if varts:
            self.expr_to_ax(varts[0])  # ax = variable delta
            self.emit(0x03, 0x46, boff)  # add ax, [bp+base_off]
        else:
            self.ldax(boff)  # mov ax, [bp+base_off]
        self.emit(0x8B, 0x56, boff + 2)  # mov dx, [bp+base_seg]
        if const:
            self.emit(0x05, *w16(const))  # add ax, const
        self.zad()

    def _load_cl(self, node):
        """Load a shift count into CL."""
        if num(node) and self.cl == node[1]:
            return  # CL already holds it
        self.cxbx_var = None  # writes CL
        self.cl = None
        if self.gkind(node) == 'bvar':
            a = SYMS[node[1]][1]
            self.emit(0x8A, 0x0E, *w16(a))  # mov cl, [a]
            return
        if num(node):
            self.emit(0xB1, node[1])  # mov cl, imm
            self.cl = node[1]
            return
        if self.gkind(node) == 'var':
            a = SYMS[node[1]][1]
            self.emit(0x8A, 0x0E, *w16(a))  # mov cl, [a] (low byte)
            return
        far = self.far_lvalue(node)
        if far and far[2] == 'byte':
            disp = self.les_fl(far)
            modrm = mod8(disp) | 0x08 | 0x07  # /1 (CL), [bx+disp]
            self.e26(0x8A, modrm, *d8(disp))  # mov cl,[es:bx+d]
            return
        ni('shift-count', node)

    def gen_assign(self, lhs, rhs):
        # `*p = K` where p is a NEAR pointer to a byte — `mov bx,[bp+d];
        # mov byte [bx],imm` (PROCESS_PATH_LOOKUP_DRIVE's *subst flag, 0x53AF).
        if (
            nderef(lhs)
            and nid(lhs[1])
            and lhs[1][1] in self.locals
            and self.lty(lhs[1]) in ('ptr_uchar', 'ptr_char')
            and num(rhs)
        ):
            self.ldbx(self.ld(lhs[1][1]))  # mov bx, [bp+d]
            self.emit(0xC6, 0x07, rhs[1] & 0xFF)  # mov byte [bx], imm
            self.bx = ('nptr', lhs[1][1])
            return
        # `FP_OFF(g) = FP_SEG(g) = K` — both halves of one far_var take a single
        # constant, materialised ONCE in AX and stored outermost-first
        # (INIT_PSP invalidating DRIVER_TABLE at 0x1937).
        if (
            rhs[0] == 'assign'
            and lhs[0] in ('fpoff', 'fpseg')
            and rhs[1][0] in ('fpoff', 'fpseg')
            and nid(lhs[1])
            and nid(rhs[1][1])
            and lhs[1][1] == rhs[1][1][1]
            and lhs[1][1] in SYMS
            and num(rhs[2])
        ):
            a = sa(lhs[1][1])
            self.mvax0(rhs[2][1] & 0xFFFF)
            for node in (lhs, rhs[1]):  # outer target first
                self.emit(0xA3, *w16(a + (2 if node[0] == 'fpseg' else 0)))
            self.ax = None
            return
        # `FP_SEG(*p) = K` / `FP_OFF(*p) = K` where p is a NEAR pointer to a far
        # pointer — `mov bx,[bp+d]; mov word [bx+2],imm`
        # (PARSE_FILENAME_TO_FCB clearing its work pointer's segment, 0x4C6E).
        if (
            lhs[0] in ('fpoff', 'fpseg')
            and nderef(lhs[1])
            and nid(lhs[1][1])
            and lhs[1][1][1] in self.locals
            and num(rhs)
        ):
            self.ldbx(self.ld(lhs[1][1][1]))  # mov bx, [bp+d]
            d = 2 if lhs[0] == 'fpseg' else 0
            self.emit(0xC7, 0x47, d, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)
            self.bx = ('nptr', lhs[1][1][1])
            return
        # Chained assignment `a = b = … = <expr>` to word globals: evaluate the
        # value once into AX, then store it to every target left-to-right
        # (MSC's `call; mov [a],ax; mov [b],ax; …` — INIT_INPUT_CURSOR's cursor
        # row/col fan-out).
        if rhs[0] == 'assign':
            targets = [lhs]
            node = rhs
            while node[0] == 'assign':
                targets.append(node[1])
                node = node[2]
            if all(self.gkind(t) == 'var' for t in targets):
                self.expr_to_ax(node)
                for t in targets:
                    self.staxm(SYMS[t[1]][1])  # mov [t], ax
                self.ax = None
                return
            # Byte value fanned out to byte targets (uchar local / bvar global):
            # compute once into AL, store to each target INNERMOST-first — MSC
            # reuses AL from the call (`call; mov [g],al; mov [bp+d],al`,
            # GET_CWD's `drive = DIR_SEARCH_FCB.f_drvcode = get_drive_type(..)`).
            def _byte_tgt(t):
                return (self.stkid(t) and self.lty(t) == 'uchar') or self.gkind(
                    t
                ) == 'bvar'

            if all(_byte_tgt(t) for t in targets) and (
                ncall(node) or self.ucharty(node) or num(node)
            ):
                self.expr_to_al(node)
                for t in reversed(targets):
                    if self.gkind(t) == 'bvar':
                        self.emit(0xA2, *w16(SYMS[t[1]][1]))  # mov [g], al
                    else:
                        self.stal(self.ld(t[1]))  # mov [bp+d], al
                # AL survives as the OUTER (last-stored) target's value, so a
                # following `outer == k` test reuses it (`cmp al,imm`).
                self.al = targets[0][1] if self.stkid(targets[0]) else None
                return

            # MIXED widths — `<byte target> = <word target> = <const>`.  The
            # value is computed once in AX; the word target stores AX and the
            # byte target stores AL, still innermost-first
            # (`mov ax,8; mov [bp+d],ax; mov [g],al` — PROCESS_DRIVER_REQUEST's
            # `DIR_SEARCH_FCB.s_attr = mode = 8`).
            def _word_tgt(t):
                return (
                    self.stkid(t) and wint(self.lt(t[1]))
                ) or self.gkind(t) == 'var'

            if (
                num(node)
                and all(_word_tgt(t) or _byte_tgt(t) for t in targets)
                and any(_word_tgt(t) for t in targets)
                and any(_byte_tgt(t) for t in targets)
            ):
                self.expr_to_ax(node)
                for t in reversed(targets):
                    if _word_tgt(t):
                        if self.stkid(t):
                            self.stax(self.ld(t[1]))  # mov [bp+d], ax
                        else:
                            self.staxm(SYMS[t[1]][1])  # mov [g], ax
                    elif self.gkind(t) == 'bvar':
                        self.emit(0xA2, *w16(SYMS[t[1]][1]))  # mov [g], al
                    else:
                        self.stal(self.ld(t[1]))  # mov [bp+d], al
                self.ax = self.al = None
                return

            # A chain whose OUTER target is a far-pointer field: the value is
            # computed once (AL / AX / DX:AX by the field's width) and stored
            # innermost-first, each far target reloading its own ES:BX
            # (EXEC_PROGRAM_FROM_PATH fanning the redirector's record into both
            # the scratch directory entry and the caller's FCB, 0x559C).
            fl0 = self.far_lvalue(lhs)
            _gt = [self.gkind(t) in ('bvar', 'var', 'long_var') for t in targets]
            if fl0 and any(_gt) and all(
                g or self.far_lvalue(t) for g, t in zip(_gt, targets)
            ):
                kind = fl0[2]
                if kind == 'long':
                    self.gen_long(node)
                elif kind == 'word':
                    self.expr_to_ax(node)
                else:
                    self.expr_to_al(node)
                for t in reversed(targets):
                    fl = self.far_lvalue(t)
                    if fl:
                        self.emit_les(fl[0])
                        d = fl[1]
                        if kind == 'byte':
                            self.e26(0x88, mod8(d) | 0x07, *d8(d))  # [es:bx+d],al
                        else:
                            self.e26(0x89, mod8(d) | 0x07, *d8(d))  # [es:bx+d],ax
                            if kind == 'long':
                                self.e26(0x89, 0x57, (d + 2) & 0xFF)  # [+d+2],dx
                    else:
                        a = SYMS[t[1]][1]
                        if kind == 'byte':
                            self.emit(0xA2, *w16(a))  # mov [g], al
                        else:
                            self.staxm(a)  # mov [g], ax
                            if kind == 'long':
                                self.emit(0x89, 0x16, *w16((a + 2) & 0xFFFF))  # [g+2],dx
                self.ax = self.al = self.dx = None
                self.axdx_var = None
                return
        # far_var[local_dst] = far_var[local_src] — a byte copy through the SAME
        # far table: MSC loads the table offset into SI once (`les si,[tbl]`) and
        # swaps only BX between the read and the write (dos_fn_46's SDA slot copy).
        def _fv_local_idx(n):
            return (
                n[0] == 'idx'
                and self.gfar(n[1])
                and nid(n[2])
                and n[2][1] in self.locals
                and not self.is_reg_var(n[2][1])
            )

        if _fv_local_idx(lhs) and _fv_local_idx(rhs) and n11(rhs) == n11(lhs):
            tbl = sa(n11(lhs))
            self.ldbx(self.ld(rhs[2][1]))  # mov bx, [src]
            self.emit(0xC4, 0x36, *w16(tbl))  # les si, [tbl]
            self.e26(0x8A, 0x00)  # mov al, [es:bx+si]
            self.ldbx(self.ld(lhs[2][1]))  # mov bx, [dst]
            self.e26(0x88, 0x00)  # mov [es:bx+si], al
            self.al = self.ax = self.bx = self.esbx = None
            return
        # far_var[si-regvar] = far_var[local] — same table copy where the DEST index
        # is the SI reg-var (a loop index): keep SI free by loading the table base
        # into DI.  mov bx,[src]; les di,[tbl]; mov al,[es:bx+di]; mov bx,di;
        # mov [es:bx+si],al  (dos_fn_45's dup-slot copy).
        if (
            lhs[0] == 'idx'
            and self.gfar(lhs[1])
            and self.rvid(lhs[2])
            and self.regvars[lhs[2][1]] == 'si'
            and rhs[0] == 'idx'
            and nid(rhs[1])
            and n11(rhs) == n11(lhs)
            and nid(rhs[2])
            and rhs[2][1] in self.locals
            and not self.is_reg_var(rhs[2][1])
        ):
            tbl = sa(n11(lhs))
            self.ldbx(self.ld(rhs[2][1]))  # mov bx, [src]
            self.emit(0xC4, 0x3E, *w16(tbl))  # les di, [tbl]
            self.e26(0x8A, 0x01)  # mov al, [es:bx+di]
            self.emit(0x8B, 0xDF)  # mov bx, di
            self.e26(0x88, 0x00)  # mov [es:bx+si], al
            self.al = self.ax = self.bx = self.esbx = None
            return
        # Consecutive scalar zero-stores share one `xor ax,ax`: the first emits
        # it (caching 0 in AX) when the NEXT sibling statement is also a scalar
        # zero-store; the rest reuse AX/AL.  A standalone `g = 0` keeps the direct
        # `mov word/byte [g],0`.  MSC no-optimizer peephole — drives WRITE_FCB's
        # `CURRENT_CLUSTER = 0; extend_flag = 0;` (xor ax,ax; mov[g],ax; mov[b],al).
        zt = (
            self._zero_scalar_assign_target(('expr', ('assign', lhs, rhs)))
            if z0(rhs)
            else None
        )
        if zt and not self._force_var_ax:
            chaining = self.ax is self._ZERO
            # START a shared xor only for a MIXED pair — a byte store adjacent to
            # a near-word global / far-word store — where MSC loads 0 once and
            # reuses it (`xor ax,ax; mov [g],ax; mov [b],al`, WRITE_FCB's
            # CURRENT_CLUSTER+extend_flag and F18_GEOMETRY+s_relclu) — OR a
            # far-word store, which MSC always sinks through AX (`mov es:[bx],ax`).
            # A run of only byte targets ties (`xor;mov al;mov al` = 8 == two `mov
            # byte,0`) and a run of only near-word GLOBALS is larger via AX, so
            # both stay direct immediate stores: DELETE_FCB's `flag_del=0;
            # flag_e=0` (two bytes) and INIT_LINE_EDIT's two word globals.
            nxt = self._zero_scalar_assign_target(self._peek_next)
            kinds = {zt[0], nxt[0]} if nxt else set()
            start = 'fw' in kinds or ('lb' in kinds and {'g', 'fw'} & kinds)
            if not chaining and nxt and start:
                if zt[0] == 'fw':
                    # A far-word first target loads its pointer BEFORE the zero
                    # is materialised (`les bx,[bp+d]; xor ax,ax; mov es:[bx],ax`)
                    # — DOS_FN_29_PARSE_FILENAME_FCB clearing f_recsiz/f_extent.
                    self.emit_les(zt[1])
                self.emit(0x33, 0xC0)  # xor ax, ax
                self.ax = self.al = self._ZERO
                chaining = True
            if chaining:
                kind = zt[0]
                if kind == 'g':
                    a = SYMS[zt[1]][1]
                    self.staxm(a)  # mov [g], ax
                elif kind in ('lw', 'lb'):
                    disp = self.ld(zt[1])
                    self.emit(
                        0x88 if kind == 'lb' else 0x89, 0x46, disp
                    )  # mov [bp+d], al/ax
                    self.invalidate_mem(zt[1])
                else:  # 'fw' far word
                    base, d = zt[1], zt[2]
                    self.emit_les(base)
                    self.e26(
                        0x89, mod8(d) | 0x07, *((d,) if d else ())
                    )  # mov [es:bx+d], ax
                return
        # `<word global> = <word local> = <additive chain containing a multiply>`:
        # IMUL owns AX:DX, so MSC accumulates the running sum in CX and stores CX
        # to both targets (REPLAY_INPUT_HISTORY's erase-span computation).
        if (
            rhs[0] == 'assign'
            and self.gkind(lhs) == 'var'
            and self.stkid(rhs[1])
            and wint(self.lt(rhs[1][1]))
            and self._sum_has_mul(rhs[2])
        ):
            self._sum_to_cx(rhs[2])
            self.emit(0x89, 0x4E, self.ld(rhs[1][1]))  # mov [bp+d], cx
            self.emit(0x89, 0x0E, *w16(sa(lhs[1])))  # mov [g], cx
            self.zaa()
            return
        # a = b = K for byte globals: MSC materialises the constant ONCE in AL
        # and stores it innermost-first (DOS_FN_56_RENAME_FILE seeding both
        # search FCBs with the 17h attribute mask).
        if (
            rhs[0] == 'assign'
            and self.gkind(lhs) == 'bvar'
            and self.gkind(rhs[1]) == 'bvar'
        ):
            # The value is materialised in AL ONCE — a literal, or any byte
            # expression (REPLAY_INPUT_HISTORY fanning one HIST_BUF read out to
            # both CUR_CHAR and ECHO_CUR_CHAR).
            if num(rhs[2]):
                self.emit(0xB0, rhs[2][1] & 0xFF)  # mov al, imm
                self.al = rhs[2][1]
            else:
                self.expr_to_al(rhs[2])
                self.al = None
            self.emit(0xA2, *w16(sa(rhs[1][1])))  # mov [inner], al
            self.emit(0xA2, *w16(sa(lhs[1])))  # mov [outer], al
            # AL still holds the value both targets now have — tag it by the
            # INNER one, which is the target a following test reads back
            # (INIT_PSP's `PROBED_COUNT < 5` right after the pair, 0x1865).
            if not num(rhs[2]):
                self.al = rhs[1][1]
            self.ax = None
            return
        # a = b = ... = num : a chain of far-word stores of one constant.  Load the
        # value once (AX), then store to each target innermost-first (MSC's chained
        # `*p = *q = 0`, generalized to N levels).
        if rhs[0] == 'assign' and nderef(lhs) and nderef(rhs[1]):
            chain = [lhs]
            node = rhs
            while node[0] == 'assign' and nderef(node[1]):
                chain.append(node[1])
                node = node[2]
            inner = node
            fars = [self.far_lvalue(c) for c in chain]
            if all(f and f[2] == 'word' for f in fars) and (
                num(inner) or self.gkind(inner) == 'var'
            ):
                # When a `les` is needed it precedes the value load (MSC order);
                # if ES:BX is already live for this base it's a no-op.  The value
                # may be a literal or a word global read once
                # (SUBST's `cds->c_startclu = cds->c_4d = s_parent`).
                self.emit_les(fars[-1][0])
                if num(inner):
                    self.mvax0(inner[1] & 0xFFFF)
                else:
                    self.emit(0xA1, *w16(sa(inner[1])))  # mov ax, [global]
                for base, disp, _ in reversed(fars):  # innermost first
                    self.emit_les(base)
                    modrm = mod8(disp) | 0x07
                    self.e26(0x89, modrm, *d8(disp))
                self.zaa()
                return
        # int/uint local = <expr % div> : the divide leaves the remainder in DX,
        # so store DX straight to the local (no `mov ax,dx`) and keep the local
        # live in DX for a following use (e.g. `(offset << n)`).
        if self.stkid(lhs) and wint(self.lt(lhs[1])) and nbin(rhs) and rhs[1] == '%':
            self.expr_to_ax(rhs[2])  # dividend → AX
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self._emit_div_operand(rhs[3])  # div word[divisor]; rem in DX
            disp = self.ld(lhs[1])
            self.emit(0x89, 0x56, disp)  # mov [bp+disp], dx
            self.zaa()
            self.dx = ('val16', lhs[1])  # local now live in DX
            return
        # *p = long  where p is a near `long *` → store DX:AX through [p]
        if nderef(lhs) and self.lty(lhs[1]) == 'ptr_long':
            if ncall(rhs):
                self.gen_call(rhs)
            else:
                self.gen_long(rhs)
            disp = self.ldi(lhs)
            self.ldbx(disp)  # mov bx, [bp+disp]
            self.emit(0x89, 0x07)  # mov [bx], ax
            self.emit(0x89, 0x57, 0x02)  # mov [bx+2], dx
            self.bx = self.ax = self.dx = None
            return
        # *p = reg_var  where p is a near `int *`/`uint *` → store si/di through [p]
        if (
            nderef(lhs)
            and self.lty(lhs[1]) in ('ptr_int', 'ptr_uint')
            and self.rvid(rhs)
        ):
            disp = self.ldi(lhs)
            self.ldbx(disp)  # mov bx, [bp+disp]
            self.emit(0x89, 0x37 if self.rv(rhs) == 'si' else 0x3F)  # mov [bx],si/di
            self.bx = None
            return
        # *p = expr  where p is a near `int *`/`uint *` (num immediate or value→AX)
        if nderef(lhs) and self.lty(lhs[1]) in ('ptr_int', 'ptr_uint'):
            if num(rhs):
                self.ensure_bx(n11(lhs))
                self.emit(0xC7, 0x07, rhs[1], (rhs[1] >> 8))  # mov word[bx],imm
            elif rhs[0] in ('bin', 'call'):
                # the value computation may clobber BX (div/far access) → eval first
                self.expr_to_ax(rhs)
                disp = self.ldi(lhs)
                self.ldbx(disp)  # mov bx, [bp+disp]
                self.emit(0x89, 0x07)  # mov [bx], ax
            else:
                self.ensure_bx(n11(lhs))
                self.expr_to_ax(rhs)
                self.emit(0x89, 0x07)  # mov [bx], ax
            self.bx = None
            return
        # *p = far_ptr_local  where p is a near `T far **` → store the far ptr
        if (
            nderef(lhs)
            and self.lty(lhs[1]).startswith('ptr_ptr_far')
            and pf(self.lty(rhs))
        ):
            pd = self.ldi(lhs)
            self.ldbx(pd)  # mov bx, [bp+p]
            rd = self.ld(rhs[1])
            self.ldax(rd)  # mov ax, [bp+rec_off]
            self.emit(0x8B, 0x56, rd + 2)  # mov dx, [bp+rec_seg]
            self.emit(0x89, 0x07)  # mov [bx], ax
            self.emit(0x89, 0x57, 0x02)  # mov [bx+2], dx
            self.ax = self.dx = self.bx = None
            return
        # *(T far **)p = far_local + <terms>  →  build the far pointer in AX:DX
        # (offset = delta + base_off + const, segment = base_seg) and store it
        # through the near pointer p.  Unlike `rec = …` (CX:BX, kept for reuse),
        # the store-through-pointer form lands directly in AX:DX.
        if (
            nderef(lhs)
            and self.lty(lhs[1]).startswith('ptr_ptr_far')
            and nbin(rhs)
            and rhs[1] == '+'
        ):
            terms = []

            def _flat2(n):
                if nbin(n) and n[1] == '+':
                    _flat2(n[2])
                    _flat2(n[3])
                else:
                    terms.append(n)

            _flat2(rhs)
            base = terms[0]
            if pf(self.lty(base)):
                addends = terms[1:]
                const, varts = self.split_terms(addends)
                if len(varts) <= 1:
                    boff = self.ld(base[1])
                    if varts:
                        self.expr_to_ax(varts[0])  # ax = variable delta
                        self.emit(0x03, 0x46, boff)  # add ax, [bp+base_off]
                    else:
                        self.ldax(boff)  # mov ax, [bp+base_off]
                    self.emit(0x8B, 0x56, boff + 2)  # mov dx, [bp+base_seg]
                    if const:
                        self.emit(0x05, *w16(const))  # add ax, const
                    pd = self.ldi(lhs)
                    self.ldbx(pd)  # mov bx, [bp+p]
                    self.emit(0x89, 0x07)  # mov [bx], ax
                    self.emit(0x89, 0x57, 0x02)  # mov [bx+2], dx
                    self.ax = self.dx = self.bx = None
                    return
        # long_lvalue = long_lvalue - longexpr : minuend in CX:BX (MSC keeps the
        # result there so a following read reuses it), subtrahend in DX:AX.
        if (
            self._is_long4(lhs)
            and nbin(rhs)
            and rhs[1] == '-'
            and self._is_long4(rhs[2])
        ):
            self.gen_long(rhs[3])  # subtrahend → DX:AX
            m = rhs[2][1]  # minuend (a long lvalue)
            if m in self.locals:
                d = self.ld(m)
                self.emit(0x8B, 0x4E, d)  # mov cx,[bp+d]
                self.ldbx(d + 2)  # mov bx,[bp+d+2]
            else:
                a = sa(m)
                self.emit(0x8B, 0x0E, *w16(a))  # mov cx,[a]
                self.emit(0x8B, 0x1E, *w16(a + 2))  # mov bx,[a+2]
            self.emit(0x2B, 0xC8)  # sub cx, ax
            self.emit(0x1B, 0xDA)  # sbb bx, dx
            n = lhs[1]
            if n in self.locals:
                d = self.ld(n)
                self.emit(0x89, 0x4E, d)  # mov [bp+d], cx
                self.emit(0x89, 0x5E, d + 2)  # mov [bp+d+2], bx
            else:
                a = sa(n)
                self.emit(0x89, 0x0E, *w16(a))  # mov [a], cx
                self.emit(0x89, 0x1E, *w16(a + 2))  # mov [a+2], bx
            self.zad()
            self.cxbx_var = n  # CX:BX still hold this value
            return
        # long_local = (long)(16-bit expr): store the low word, then the high
        # word as an immediate 0 (C7) — and keep the low word live in AX so a
        # following `local = local + ...` reuses it (reloading only DX).
        if (
            self._is_long4(lhs)
            and nid(lhs)
            and lhs[1] in self.locals
            and ncast(rhs)
            and rhs[1] == 'long'
        ):
            disp = self.ld(lhs[1])
            self.expr_to_ax(rhs[2])
            self.stax(disp)  # mov [bp+d], ax
            self.emit(0xC7, 0x46, disp + 2, 0, 0)  # mov word [bp+d+2], 0
            self.ax = ('low', lhs[1])
            self.dx = None
            self.axdx_var = None
            return
        # *dpb_out = (far)(far_var + terms) — store a computed far pointer THROUGH a
        # near pointer to a far pointer: build off:seg in AX:DX (as for a far_local),
        # then `mov bx,[bp+dpb]; mov [bx],ax; mov [bx+2],dx`.  BX is left holding the
        # pointer so an immediately-following `les bx,[bx]` deref reuses it.
        if nderef(lhs) and self.lty(lhs[1]).startswith('ptr_ptr_far'):
            r = rhs[2] if (ncast(rhs) and 'far' in rhs[1]) else rhs
            if nbin(r) and r[1] == '+' and self.fv_axdx_sum(r):
                self.ensure_bx(n11(lhs))  # mov bx,[bp+dpb]
                self.emit(0x89, 0x07)  # mov [bx],ax
                self.emit(0x89, 0x57, 0x02)  # mov [bx+2],dx
                self.zad()
                return
            # *<near ptr to far> = <far local>: the POINTER is loaded first,
            # then the value's two words (WRITE_DIR_ENTRY publishing the newly
            # allocated dir sector back through its `work` out-param).
            if self.stkid(r) and pf(self.lt(r[1])):
                self.ensure_bx(n11(lhs))  # mov bx, [bp+work]
                d = self.ld(r[1])
                self.ldax(d)  # mov ax, [bp+d]
                self.emit(0x8B, 0x56, (d + 2) & 0xFF)  # mov dx, [bp+d+2]
                self.emit(0x89, 0x07)  # mov [bx], ax
                self.emit(0x89, 0x57, 0x02)  # mov [bx+2], dx
                self.zad()
                return
            # *<near ptr to far> = &global — the DS-relative build, pointer
            # first, then the address immediate and DS itself
            # (EXEC_PROGRAM_FROM_PATH publishing the scratch dir entry, 0x5616).
            ga = self.near_global_addr(r[1]) if r[0] == 'addr' else None
            if ga is not None:
                self.ensure_bx(n11(lhs))  # mov bx, [bp+d]
                self.mvax(ga)  # mov ax, &g
                self.emit(0x89, 0x07)  # mov [bx], ax
                self.emit(0x8C, 0x5F, 0x02)  # mov [bx+2], ds
                self.ax = None
                return
            # *<near ptr to far> = <far-returning call> — the call comes first
            # (it clobbers BX), then the pointer is reloaded and DX:AX stored
            # (EXEC_PROGRAM_FROM_PATH handing back its directory entry, 0x56D9).
            if ncall(r):
                self.gen_call(r)  # far result → DX:AX
                self.ensure_bx(n11(lhs))  # mov bx, [bp+d]
                self.emit(0x89, 0x07)  # mov [bx], ax
                self.emit(0x89, 0x57, 0x02)  # mov [bx+2], dx
                self.zad()
                return
        # far_local = far_var_global + <int terms> : offset = sum(terms) + [g],
        # segment = [g+2], built in AX:DX (MSC: <var term>; add ax,[g]; mov
        # dx,[g+2]; [add ax,const]; store both).  Handles a single trailing const
        # too (`far_var + idx*k + c`).
        if pf(self.lty(lhs)) and nbin(rhs) and rhs[1] == '+':
            if self.fv_axdx_sum(rhs):
                # Tag AX:DX as the stored far pointer so an immediately following
                # push of it reuses the registers (`push dx; push ax`) instead of
                # reloading — DOS_FN_10's `sft = DRIVER_TABLE + 0x35*fcb[0x1d] + 6`
                # passed straight to int2f_network_1087.
                self.store_axdx_long(lhs)
                return
        # far_local = far_local + <16-bit offset> : pointer arithmetic — copy the
        # segment, add the offset delta to the offset word.  MSC emits:
        #   mov ax,<var-delta>; mov cx,[base_off]; mov bx,[base_seg];
        #   add cx,ax [; add cx,k]; mov [dst_off],cx; mov [dst_seg],bx
        if pf(self.lty(lhs)) and nbin(rhs) and rhs[1] == '+':
            terms = []

            def _flat(n):
                if nbin(n) and n[1] == '+':
                    _flat(n[2])
                    _flat(n[3])
                else:
                    terms.append(n)

            _flat(rhs)
            base = terms[0]
            if pf(self.lty(base)):
                addends = terms[1:]
                const, varts = self.split_terms(addends)
                # A SCALED variable term (`&p->rec[i]`, i*sizeof) builds the
                # pointer in AX:DX rather than CX:BX: the `mul` already lands in
                # AX, so MSC adds the base offset there and takes the segment in
                # DX (INSTALL_FIRST_DRIVER's `&chain->b_rec[rem]`).
                if (
                    len(varts) == 1
                    and nbin(varts[0])
                    and varts[0][1] == '*'
                    # ...but only when the index is a MEMORY local: a register-var
                    # index (`mul si`) keeps MSC on the CX:BX form
                    # (find_free_file_handle's identical `&drv->b_rec[si]`).
                    and not any(self.rvid(t) for t in varts[0][2:4])
                ):
                    self.expr_to_ax(varts[0])  # mov ax,K; mul word [bp+i]
                    boff = self.ld(base[1])
                    self.emit(0x03, 0x46, boff)  # add ax, [bp+base_off]
                    self.emit(0x8B, 0x56, boff + 2)  # mov dx, [bp+base_seg]
                    if const:
                        self.emit(0x05, *w16(const))  # add ax, const
                    doff = self.ld(lhs[1])
                    self.emit(0x89, 0x46, doff)  # mov [bp+dst_off], ax
                    self.emit(0x89, 0x56, doff + 2)  # mov [bp+dst_seg], dx
                    self.ax = self.al = self.dx = None
                    self.cxbx_var = None
                    # DX:AX still hold the pointer just stored — a following
                    # push of it goes straight from the registers
                    # (DISPATCH_FCB_OPEN's COMPARE_FCB_NAME argument).
                    self.axdx_var = lhs[1]
                    return
                if len(varts) <= 1:
                    if varts:
                        self.expr_to_ax(varts[0])  # ax = variable delta
                    boff = self.ld(base[1])
                    self.emit(0x8B, 0x4E, boff)  # mov cx, [bp+base_off]
                    self.ldbx(boff + 2)  # mov bx, [bp+base_seg]
                    if varts:
                        self.emit(0x03, 0xC8)  # add cx, ax
                    if const:
                        if const < 128:
                            self.emit(0x83, 0xC1, const)  # add cx, imm8
                        else:
                            self.emit(0x81, 0xC1, *w16(const))
                    doff = self.ld(lhs[1])
                    self.emit(0x89, 0x4E, doff)  # mov [bp+dst_off], cx
                    self.emit(0x89, 0x5E, doff + 2)  # mov [bp+dst_seg], bx
                    self.ax = self.bx = self.dx = None
                    self.axdx_var = self.cxbx_var = None
                    return
        # far_local = &far_var[i].<field> with ES:BX still holding the table
        # base from a preceding entry read: recompute the scaled index, add the
        # live base offset, take the segment from ES (DOS_FN_3A_RMDIR's
        # `alias_path = &DPB_TABLE[scan_idx].c_path[3]`).
        if pf(self.lty(lhs)) and rhs[0] == 'addr':
            fl = self.far_lvalue(rhs[1])
            if (
                fl
                and isinstance(fl[0], tuple)
                and fl[0][0] == 'idx'
                and self.bx == ('fvoff', fl[0][1])
            ):
                _, name, index = fl[0]
                self.expr_to_ax(index)  # scaled index → AX
                self.emit(0x03, 0xC3)  # add ax, bx
                self.emit(0x8C, 0xC2)  # mov dx, es
                if fl[1]:
                    self.emit(0x05, *w16(fl[1]))  # add ax, field disp
                doff = self.ld(lhs[1])
                self.emit(0x89, 0x46, doff)  # mov [bp+off], ax
                self.emit(0x89, 0x56, doff + 2)  # mov [bp+seg], dx
                self.ax = self.al = self.dx = None
                return
        # far_local = &global / &global[const]  →  a DS-relative far pointer:
        # mov ax,&g+k; mov [bp+off],ax; mov [bp+seg],ds  (DOS_FN_3A_RMDIR's
        # `path_copy = &SDA_SCRATCH_BUF[3]`).
        if pf(self.lty(lhs)) and rhs[0] == 'addr':
            ga = self.near_global_addr(rhs[1])
            if ga is not None:
                doff = self.ld(lhs[1])
                self.emit(0xB8, *w16(ga))  # mov ax, &g+k
                self.emit(0x89, 0x46, doff)  # mov [bp+off], ax
                self.emit(0x8C, 0x5E, doff + 2)  # mov [bp+seg], ds
                self.ax = None
                return
        # far GLOBAL = &global / a near array  →  the same DS-relative build, but
        # both halves land in absolute memory (the line editor pointing
        # INPUT_FCB_PTR at the recall template at 0x1320).
        if self.gkind(lhs) == 'far_var':
            ga = None
            if nid(rhs) and self.gkind(rhs) == 'arr':
                ga = sa(rhs[1])
            elif rhs[0] == 'addr':
                ga = self.near_global_addr(rhs[1])
            if ga is not None:
                a = sa(lhs[1])
                self.emit(0xB8, *w16(ga))  # mov ax, &g
                self.emit(0xA3, *w16(a))  # mov [p], ax
                self.emit(0x8C, 0x1E, *w16((a + 2) & 0xFFFF))  # mov [p+2], ds
                self.ax = None
                return
        # far_local = <local array>  →  an SS-relative far pointer:
        # lea ax,[bp-off]; mov [bp+off],ax; mov [bp+seg],ss (OPEN_FILE
        # retargeting its path at the APPEND scratch buffer, 0x665D).
        if pf(self.lty(lhs)):
            arr = rhs[2] if ncast(rhs) and pf(rhs[1]) else rhs
            if nid(arr) and self.lty(arr).startswith('arr'):
                doff = self.ld(lhs[1])
                self.lea_ax(self.ld(arr[1]))  # lea ax, [bp-off]
                self.emit(0x89, 0x46, doff)  # mov [bp+off], ax
                self.emit(0x8C, 0x56, doff + 2)  # mov [bp+seg], ss
                self.ax = None
                return
        # *far_local++ = <byte>  —  the pointer is loaded, its OFFSET word bumped
        # in memory, and the store then goes through the OLD ES:BX (the bumped
        # register form has no addressing mode once the pointer has moved)
        # (GET_ASSIGN_PATH_FOR_DRIVE writing the copied path out, 0x76DD).
        if (
            nderef(lhs)
            and lhs[1][0] == 'postinc'
            and self.locid(lhs[1][1])
            and pf(self.lty(lhs[1][1]))
        ):
            name = lhs[1][1][1]
            self.expr_to_al(rhs)
            self.emit_les(name)  # les bx, [bp+d]
            self.emit(0xFF, 0x46, self.ld(name))  # inc word [bp+d]
            self.e26(0x88, 0x07)  # mov [es:bx], al
            self.esbx = self.bx = None  # the pointer moved out from under ES:BX
            return
        # arr[<word global>++] = <byte const> — the same index capture, with an
        # immediate store (the NUL and LF terminators MAIN_ENTRY writes after a
        # DEVICE= name and its arguments, 0x0406 / 0x0443).
        if (
            lhs[0] == 'idx'
            and nid(lhs[1])
            and self.gkind(lhs[1]) == 'arr'
            and lhs[2][0] == 'postinc'
            and self.gvw(lhs[2][1])
            and num(rhs)
        ):
            g = SYMS[lhs[2][1][1]][1]
            self.emit(0x8B, 0x1E, *w16(g))  # mov bx, [g]
            self.emit(0xFF, 0x06, *w16(g))  # inc word [g]
            self.emit(
                0xC6, 0x87, *w16(SYMS[lhs[1][1]][1]), rhs[1]
            )  # mov byte [bx+ARR], imm8
            self.bx = None
            return
        # arrD[<word global>++] = arrS[<word global>++ / ++<word global>] — a
        # byte copy between two near array globals, each index in its own
        # register: the DESTINATION index is captured in BX and its global
        # bumped, then the SOURCE index in SI (bumped after the capture for a
        # post-inc, before it for a pre-inc), then one load/store through the
        # two bases (MAIN_ENTRY's DEVICE= name/args and SHELL= copy loops,
        # 0x03E3 / 0x0420 / 0x0461).
        if (
            lhs[0] == 'idx'
            and nid(lhs[1])
            and self.gkind(lhs[1]) == 'arr'
            and lhs[2][0] == 'postinc'
            and self.gvw(lhs[2][1])
            and rhs[0] == 'idx'
            and nid(rhs[1])
            and self.gkind(rhs[1]) == 'arr'
            and rhs[2][0] in ('postinc', 'preinc')
            and self.gvw(rhs[2][1])
        ):
            gd = SYMS[lhs[2][1][1]][1]
            gs = SYMS[rhs[2][1][1]][1]
            self.emit(0x8B, 0x1E, *w16(gd))  # mov bx, [gd]
            self.emit(0xFF, 0x06, *w16(gd))  # inc word [gd]
            if rhs[2][0] == 'preinc':
                self.emit(0xFF, 0x06, *w16(gs))  # inc word [gs]
                self.emit(0x8B, 0x36, *w16(gs))  # mov si, [gs]
            else:
                self.emit(0x8B, 0x36, *w16(gs))  # mov si, [gs]
                self.emit(0xFF, 0x06, *w16(gs))  # inc word [gs]
            self.emit(0x8A, 0x84, *w16(SYMS[rhs[1][1]][1]))  # mov al,[si+ARRS]
            self.emit(0x88, 0x87, *w16(SYMS[lhs[1][1]][1]))  # mov [bx+ARRD],al
            self.bx = self.al = self.ax = None
            return
        # word_array_global[<word global>++] = <word expr>  —  the index is
        # captured in BX and the global bumped BEFORE it is scaled, so the store
        # uses the OLD index: mov bx,[g]; inc word [g]; shl bx,1; <value→AX>;
        # mov [bx+ARR],ax  (MAIN_ENTRY appending a DEVICE= path offset, 0x03C9).
        if (
            lhs[0] == 'idx'
            and nid(lhs[1])
            and self.gkind(lhs[1]) == 'arr_w'
            and lhs[2][0] == 'postinc'
            and self.gvw(lhs[2][1])
        ):
            g = SYMS[lhs[2][1][1]][1]
            self.emit(0x8B, 0x1E, *w16(g))  # mov bx, [g]
            self.emit(0xFF, 0x06, *w16(g))  # inc word [g]
            self.emit(0xD1, 0xE3)  # shl bx, 1
            self.expr_to_ax(rhs)
            self.emit(0x89, 0x87, *w16(SYMS[lhs[1][1]][1]))  # mov [bx+ARR], ax
            self.bx = self.ax = None
            return
        # far_local = &local_array[<index>]  →  the same SS-relative build with
        # the ELEMENT address in AX.  A constant or a register-var index folds
        # into the lea's displacement (`lea ax,[bp+si-53h]`); a byte local has
        # to be zero-extended into the spare index register first
        # (EXEC_PROGRAM_FROM_PATH walking its path buffer at 0x54DF / 0x5648).
        if pf(self.lty(lhs)):
            a = rhs[2] if ncast(rhs) and pf(rhs[1]) else rhs
            if (
                a[0] == 'addr'
                and a[1][0] == 'idx'
                and nid(a[1][1])
                and str(self.lty(a[1][1])).startswith('arr')
            ):
                arr, idx = a[1][1], a[1][2]
                off, doff = self.ld(arr[1]), self.ld(lhs[1])
                base, k = idx, 0
                if nbin(idx) and idx[1] == '+' and num(idx[3]):
                    base, k = idx[2], idx[3][1]
                if num(idx):
                    self.lea_ax((off + idx[1]) & 0xFF)  # lea ax, [bp+off+k]
                elif self.rvid(base):
                    # lea ax, [bp+si/di+off+k]
                    self.emit(0x8D, sd(0x42, self.rv(base)), (off + k) & 0xFF)
                elif self.locid(base) and self.ucharty(base) and k == 0:
                    r = 'di' if 'si' in self.regvars.values() else 'si'
                    # the mov's REG field is 110/111, not the +1 of an r/m base
                    self.emit(0x8B, 0x76 if r == 'si' else 0x7E, self.ld(base[1]))
                    self.emit(0x81, sd(0xE6, r), 0xFF, 0x00)  # and si/di, 0FFh
                    self.emit(0x8D, sd(0x42, r), off & 0xFF)  # lea ax,[bp+si/di+off]
                else:
                    ni('gen_assign &local_arr[i]', idx)
                self.emit(0x89, 0x46, doff)  # mov [bp+off], ax
                self.emit(0x8C, 0x56, doff + 2)  # mov [bp+seg], ss
                self.ax = None
                return
        # long global = 0 : one `xor ax,ax` feeds both word stores (high then
        # low), no DX (DOS_FN_23's `DOS_DATETIME = 0` on the network-device path).
        if self.gkind(lhs) == 'long_var' and z0(rhs):
            a = SYMS[lhs[1]][1]
            self.emit(0x33, 0xC0)  # xor ax, ax
            self.emit(0xA3, *w16(a + 2))  # mov [a+2], ax  (high word)
            self.emit(0xA3, *w16(a))  # mov [a], ax  (low word)
            self.ax = self.al = self._ZERO
            self.dx = self.bx = None
            self.axdx_var = self.cxbx_var = None
            return
        # Widening store: long global = (unsigned)<16-bit expr>.  MSC stores the
        # 16-bit value to the low word and an IMMEDIATE 0 to the high word (a
        # `mov word[hi],0`, NOT `sub dx,dx`), and keeps the low word live in AX
        # (tagged) so a following read of the same global reloads only DX.  The
        # position setup in DOS_FN_24/14/15's `DOS_DATETIME = (unsigned)*(uint
        # far*)(rec+0Ch)`.
        if self.gkind(lhs) == 'long_var' and ncast(rhs) and rhs[1] == 'uint':
            self.expr_to_ax(rhs[2])
            a = SYMS[lhs[1]][1]
            self.staxm(a)  # mov [a], ax
            self.emit(0xC7, 0x06, *w16(a + 2), 0x00, 0x00)  # mov word[a+2], 0
            self.ax = ('low', lhs[1])
            self.dx = self.bx = None
            self.axdx_var = self.cxbx_var = None
            return
        # long global = <long expr> + (uchar)<far byte>: MSC widens the byte into
        # BX:CX (BX=0, CX=byte), adds the long value (DX:AX), and stores BX:CX —
        # a distinct register target from the DX:AX `_long_add_term`.  DOS_FN_24's
        # `DOS_DATETIME = (DOS_DATETIME << 7) + (uchar)*(rec+0x20)`.
        if (
            self.gkind(lhs) == 'long_var'
            and nbin(rhs)
            and rhs[1] == '+'
            and self._is_long_expr(rhs[2])
            and (
                (ncast(rhs[3]) and rhs[3][1] == 'uchar')
                or (self.far_lvalue(rhs[3]) and self.far_lvalue(rhs[3])[2] == 'byte')
            )
        ):
            far = self.far_lvalue(rhs[3][2]) if ncast(rhs[3]) else self.far_lvalue(rhs[3])
            if far and far[2] == 'byte':
                self.gen_long(rhs[2])  # long expr → DX:AX
                disp = self.les_fl(far)
                self.e26(0x8A, mod8(disp) | 0x0F, *d8(disp))  # mov cl,[es:bx+d]
                self.emit(0x2A, 0xED)  # sub ch,ch
                self.emit(0x2B, 0xDB)  # sub bx,bx
                self.emit(0x03, 0xC8)  # add cx,ax
                self.emit(0x13, 0xDA)  # adc bx,dx
                a = SYMS[lhs[1]][1]
                self.emit(0x89, 0x0E, *w16(a))  # mov [a],cx
                self.emit(0x89, 0x1E, *w16(a + 2))  # mov [a+2],bx
                self.ax = self.dx = self.bx = self.cl = None
                self.axdx_var = self.cxbx_var = None
                return
        # far_local = *<near ptr to far> + ((a % b) << k) — WRITE_DIR_ENTRY's
        # dir-entry pointer.  The offset term is a DIV REMAINDER, so it is
        # already sitting in DX; MSC keeps the whole build there and puts the
        # segment in CX rather than using the usual AX:DX pair.
        _r = rhs[2] if (ncast(rhs) and pf(rhs[1])) else rhs
        if (
            self.stkid(lhs)
            and pf(self.lt(lhs[1]))
            and nbin(_r)
            and _r[1] == '+'
            and nderef(_r[2])
            and nid(_r[2][1])
            and self.lty(_r[2][1]).startswith('ptr_ptr_far')
            and nbin(_r[3])
            and _r[3][1] == '<<'
            and num(_r[3][3])
            and nbin(_r[3][2])
            and _r[3][2][1] == '%'
        ):
            rhs = _r
            q = rhs[3][2]
            self.expr_to_ax(q[2])  # mov ax, <a>
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self._emit_div_operand(q[3])  # div word [<b>]   → DX = a % b
            k = rhs[3][3][1]
            if k == 1:
                self.emit(0xD1, 0xE2)  # shl dx, 1
            else:
                self.emit(0xB1, k)  # mov cl, k
                self.emit(0xD3, 0xE2)  # shl dx, cl
            self.ldbx(self.ld(rhs[2][1][1]))  # mov bx, [bp+work]
            self.emit(0x03, 0x17)  # add dx, [bx]
            self.emit(0x8B, 0x4F, 0x02)  # mov cx, [bx+2]
            d = self.ld(lhs[1])
            self.emit(0x89, 0x56, d)  # mov [bp+d], dx
            self.emit(0x89, 0x4E, (d + 2) & 0xFF)  # mov [bp+d+2], cx
            self.zaad()
            self.bx = self.cl = None
            self.axdx_var = self.cxbx_var = None
            return
        # 4-byte (long / far-ptr) scalar assignment: copy through AX:DX.
        if self._is_long4(lhs):
            if ncall(rhs):
                self.gen_call(rhs)  # 32-bit result in AX:DX
            elif self._is_long4(rhs):
                self.load_long_axdx(rhs)
            else:
                self.gen_long(rhs)  # general long expression
            self.store_axdx_long(lhs)
            return
        # Byte scalar global:  BVAR = expr
        if self.gkind(lhs) == 'bvar':
            a = SYMS[lhs[1]][1]
            if num(rhs):
                # `G = 0` immediately before `(L & G) <cmp> L`: MSC zeroes CL
                # once and reuses it for both the store and the `and al,cl`
                # (DOS_FN_41's `SDA_SEARCH_ATTR = 0; if ((attr_check &
                # SDA_SEARCH_ATTR) != attr_check)`).
                nxt = self._peek_next
                if (
                    rhs[1] == 0
                    and nxt
                    and nxt[0] == 'if'
                    and nxt[1][0] == 'cmp'
                    and nbin(nxt[1][2])
                    and nxt[1][2][1] == '&'
                    and nid(nxt[1][2][3])
                    and nxt[1][2][3][1] == lhs[1]
                ):
                    self.emit(0x32, 0xC9)  # xor cl, cl
                    self.emit(0x88, 0x0E, *w16(a))  # mov [a], cl
                    self._cl_bvar0 = lhs[1]
                    return
                self.emit(0xC6, 0x06, *w16(a), rhs[1])  # mov byte [a], imm
                return
            self.expr_to_al(rhs)
            self.emit(0xA2, *w16(a))  # mov [a], al
            # AL still holds the stored value: tag it as the far-byte rhs (so a
            # following use of THAT byte reuses AL) when rhs is a far-byte
            # lvalue, else as the byte-global itself (so a following `if (g cmp
            # c)` reuses AL — echo_input_char's CR test).
            # ...and when the rhs is a byte LOCAL, keep the tag on the LOCAL:
            # AL genuinely holds both, and it is the local that gets read again
            # (the line editor's `key` right after `ECHO_CUR_CHAR = key`).
            if fbyte(self, rhs):
                self.al = ('rhs', rhs)
            elif self.locid(rhs) and self.lt(rhs[1]) in ('uchar', 'char'):
                self.al = rhs[1]
            else:
                self.al = lhs[1]
            return
        # Fused far-pointer construction for a far-pointer LOCAL: the pair
        # `FP_OFF(p) = <expr>; FP_SEG(p) = FP_SEG(q)` computes the offset in AX
        # and the segment in DX (interleaved `mov dx,[seg]` BEFORE the stores),
        # then stores both — MSC's shape for DOS_FN_10's `dir_ent` from the
        # sector far pointer.  The FP_SEG store is then suppressed.
        if lhs[0] == 'fpoff' and nid(lhs[1]) and lhs[1][1] in self.locals \
                and pf(self.lty(lhs[1])):
            nxt = self._peek_next
            # The segment source may be another far local's FP_SEG, or a plain
            # word local holding the segment (PROCESS_DRIVER_REQUEST unpacks
            # the request's offset/segment words into two ints first).
            dseg = None
            if (
                nxt
                and nxt[0] == 'expr'
                and nxt[1][0] == 'assign'
                and nxt[1][1][0] == 'fpseg'
                and nid(nxt[1][1][1])
                and n11(nxt[1][1]) == n11(lhs)
            ):
                _src = nxt[1][2]
                if (
                    _src[0] == 'fpseg'
                    and nid(_src[1])
                    and _src[1][1] in self.locals
                    and pf(self.lty(_src[1]))
                ):
                    dseg = self.ld(_src[1][1]) + 2
                elif self.stkid(_src) and wint(self.lt(_src[1])):
                    dseg = self.ld(_src[1])
            if dseg is not None:
                d = self.ld(lhs[1][1])
                self.expr_to_ax(rhs)  # offset → AX
                self.emit(0x8B, 0x56, dseg & 0xFF)  # mov dx, [bp+seg]
                self.stax(d)  # mov [bp+d], ax
                self.emit(0x89, 0x56, (d + 2) & 0xFF)  # mov [bp+d+2], dx
                self.ax = self.dx = self.axdx_var = None
                self._fpseg_suppress = nxt
                return
        # FP_SEG(p) / FP_OFF(p) = expr — write the segment / offset word of a
        # far pointer (offset word at base, segment at +2).
        if lhs[0] in ('fpseg', 'fpoff') and nid(lhs[1]):
            name = n11(lhs)
            # far_var global: store to [addr] / [addr+2]
            if gsym(name, 'far_var'):
                addr = sa(name) + (2 if lhs[0] == 'fpseg' else 0)
                if num(rhs):
                    self.emit(
                        0xC7, 0x06, *w16(addr), rhs[1], (rhs[1] >> 8)
                    )  # mov word[addr],imm
                else:
                    self.expr_to_ax(rhs)
                    self.staxm(addr)  # mov [addr],ax
                    self.ax = None
                self.axdx_var = None
                return
            disp = self.ld(name)
            if lhs[0] == 'fpseg':
                disp = (disp + 2) & 0xFF
            if num(rhs):
                self.emit(
                    0xC7, 0x46, disp, rhs[1], (rhs[1] >> 8)
                )  # mov word [bp+disp], imm
            else:
                self.expr_to_ax(rhs)
                self.stax(disp)  # mov [bp+disp], ax
                # AX still holds the offset/segment word, so a following push of
                # this far pointer can reuse it (push ax) instead of re-reading.
                self.ax = (
                    ('fpoff', n11(lhs)) if lhs[0] == 'fpoff' else ('fpseg', n11(lhs))
                )
            if self.esbx == n11(lhs):
                self.esbx = None
            return
        # FP_SEG/FP_OFF of a far-pointer MEMBER of a local struct
        # (`FP_OFF(pkt.i_ptr) = …`, desugared to fpoff(*(T far * *)(pkt+off))):
        # a plain word store at the member's offset (+2 for the segment half).
        if (
            lhs[0] in ('fpoff', 'fpseg')
            and nderef(lhs[1])
            and ncast(lhs[1][1])
            and n11(lhs[1]).startswith('ptr_ptr_far')
        ):
            base = n12(lhs[1])
            if lhs[0] == 'fpseg':
                if nbin(base) and base[1] == '+' and num(base[3]):
                    base = ('bin', '+', base[2], ('num', base[3][1] + 2))
                else:
                    base = ('bin', '+', base, ('num', 2))
            lhs = ('deref', ('cast', 'ptr_uint', base))
        # A far-pointer FIELD as the store target (`p->c_dpb = <far value>`,
        # desugared to `*(T far * far *)(p + off) = …`): a 4-byte far store —
        # identical handling to a far `long` lvalue.  (far_lvalue deliberately
        # excludes ptr_far_ptr casts because on the READ side they are chain
        # bases; as a store TARGET the retyped form is exact.)
        if nderef(lhs) and ncast(lhs[1]) and n11(lhs).startswith('ptr_far_ptr'):
            alt = ('deref', ('cast', 'ptr_far_ulong', n12(lhs)))
            if self.far_lvalue(alt):
                lhs = alt
        # Far-pointer store:  *(T far *)(FAR_VAR + disp) = expr
        far = self.far_lvalue(lhs)
        if far:
            fv, disp, kind = far
            modrm = mod8(disp) | 0x07
            if kind == 'long':
                # *(long far*)(p+d) = long value  →  les; DX:AX = value; store both.
                # A call rhs runs first (it clobbers ES:BX, so the les reloads after).
                rfar = self.far_lvalue(rhs)
                if ncall(rhs):
                    self.gen_call(rhs)
                    self.emit_les(fv)
                elif rfar and rfar[2] == 'long' and not isinstance(rfar[0], tuple):
                    # far-long rhs from a DIFFERENT far pointer: read it into DX:AX
                    # FIRST (its `les` would else clobber the dest's ES:BX), then
                    # load the dest.  `*(long far*)(fcb+d)=*(long far*)(src+e)`.
                    rb, rd, _ = rfar
                    self.emit_les(rb)
                    self.e26(0x8B, mod8(rd) | 0x07, *d8(rd))  # mov ax,es:[bx+rd]
                    self.e26(0x8B, 0x57, rd + 2)  # mov dx,es:[bx+rd+2]
                    self.emit_les(fv)
                elif nderef(rhs) and ncast(rhs[1]) and n11(rhs).startswith(
                    'ptr_far_ptr'
                ):
                    # A far-POINTER field as the source (`fcb->s_dpb =
                    # DPB_TABLE[i].c_dpb`): build it in DX:AX first — its own
                    # scaled `les` would otherwise clobber the dest's ES:BX.
                    self.gen_long(rhs)
                    self.emit_les(fv)
                elif z0(rhs):
                    # `<far long> = 0` — one `xor ax,ax` feeds both halves, and
                    # MSC writes the HIGH word first (the same shape as the
                    # long-global zero store in #788).
                    self.emit_les(fv)
                    self.emit(0x33, 0xC0)  # xor ax, ax
                    self.e26(0x89, 0x47, (disp + 2) & 0xFF)  # [es:bx+d+2],ax
                    self.e26(0x89, modrm, *d8(disp))  # [es:bx+d],ax
                    self.zaad()
                    self.axdx_var = None
                    return
                elif not self._is_long_expr(rhs):
                    # Widening store `<far long> = <16-bit expr>`: the value is
                    # computed into AX FIRST (it may need its own `les`), then
                    # the destination is loaded and the HIGH word takes an
                    # IMMEDIATE 0 — not a `sub dx,dx` (COMPUTE_CLUSTER_INFO_FOR_FCB
                    # writing the root directory's sector at 0x791F).
                    self.expr_to_ax(rhs)
                    self.emit_les(fv)
                    self.e26(0x89, modrm, *d8(disp))  # [es:bx+d],ax
                    self.e26(0xC7, 0x47, (disp + 2) & 0xFF, 0x00, 0x00)  # [+d+2],0
                    self.zaad()
                    self.axdx_var = None
                    return
                elif not nid(rhs):
                    # A computed 32-bit value: build it FIRST (it needs the
                    # registers and may `les` its own operands), then load the
                    # destination.
                    self.gen_long(rhs)
                    if self._lbxdx:
                        # ...unless a divide pushed the accumulator into BX:DX —
                        # BX is the high word now, so the destination pointer
                        # goes to ES:SI instead.
                        self._lbxdx = False
                        self.emit(0xC4, 0x76, self.ld(fv))  # les si, [bp+d]
                        self.e26(
                            0x89, mod8(disp) | 0x14, *d8(disp)
                        )  # mov [es:si+d], dx
                        self.e26(0x89, 0x5C, (disp + 2) & 0xFF)  # [es:si+d+2], bx
                        self.zaad()
                        self.axdx_var = None
                        return
                    self.emit_les(fv)
                else:
                    self.emit_les(fv)
                    self.load_long_axdx(rhs)
                self.e26(0x89, modrm, *d8(disp))  # [es:bx+d],ax
                self.e26(0x89, 0x57, disp + 2)  # [es:bx+d+2],dx
                self.zaad()
                # the stored value is still in AX:DX — a following `return v` reuses it
                self.axdx_var = rhs[1] if nid(rhs) else None
                return
            if num(rhs):
                # store immediate: mov byte/word [<rm>], imm — a scaled table
                # entry addresses through SI like the reads do, rather than
                # folding the entry offset into BX (FCB_BIT15_CHECK invalidating
                # DPB_TABLE[i].c_startclu at 0x825D).
                rm, dsp = self.far_rm(fv, disp)
                if kind == 'word':
                    self.e26(0xC7, rm, *dsp, rhs[1], (rhs[1] >> 8))
                else:
                    self.e26(0xC6, rm, *dsp, rhs[1])
                # the immediate store and `les` touch only ES:BX, so AX/AL survive
                return
            if kind == 'word' and self.rvid(rhs):
                # far word = register var → store SI/DI straight (no AX round-trip)
                self.emit_les(fv)
                r = rf(self.rv(rhs))
                self.e26(
                    0x89, mod8(disp) | (r << 3) | 0x07, *d8(disp)
                )  # mov [es:bx+d], si/di
                return
            if kind == 'word' and self._simple_word_rhs(rhs):
                m = self.idx_si_setup(fv)
                if m is not None:
                    # si-indexed single-use entry: the base setup uses AX, so it
                    # has to precede the value load either way.
                    self.expr_to_ax(rhs)
                    self.e26(0x89, m, disp)  # mov [es:bx+si/di+d], ax
                    self.al = None
                    return
                # far word store of a *simple* value (a stack word, an
                # FP_OFF/FP_SEG slot, or a literal): like the byte case, MSC
                # loads the far pointer FIRST and then materialises the value —
                # it cannot touch ES:BX.
                self.emit_les(fv)
                self.expr_to_ax(rhs)
                self.e26(0x89, modrm, *d8(disp))  # mov [es:bx+d], ax
                self.al = None  # AL is the low half of the value just loaded
                return
            if kind == 'byte' and nbin(rhs) and rhs[1] == '%':
                # `<far byte> = <expr> % <divisor>` — the divide leaves the
                # remainder in DX, so MSC loads the destination and stores DL
                # straight out instead of routing it through AL
                # (COMPUTE_CLUSTER_INFO_FOR_FCB's intra-sector offset, 0x796F).
                self.expr_to_ax(rhs[2])
                self.emit(0x2B, 0xD2)  # sub dx, dx
                self._emit_div_operand(rhs[3])
                self.emit_les(fv)
                self.e26(0x88, modrm | 0x10, *d8(disp))  # mov [es:bx+d], dl
                self.zaad()
                return
            if kind == 'byte' and self._simple_byte_rhs(rhs):
                # far byte store with a *simple* value (local/const arithmetic that
                # can't touch ES:BX): MSC loads the far pointer first, then computes
                # the byte directly in AL (no zero-extend).  A value needing a call
                # or far access stays value-first (below) so it doesn't lose ES:BX.
                self.emit_les(fv)
                self.expr_to_al(rhs)
                self.e26(0x88, modrm, *d8(disp))
                # `mov es:[bx],al` leaves AL holding the stored value — keep it
                # tagged by a simple local/byte-global source so a following use
                # reuses AL (just `sub ah,ah`, no reload) — COPY_PROMPT_TEMPLATE's
                # `P[1] = CNT; f(CNT + 1)`.
                self.al = (
                    rhs[1]
                    if (self.locid(rhs) or self.gkind(rhs) == 'bvar')
                    else None
                )
                self.ax = None
                return
            # A near cast of a local (`(uint)t` → mov ax,[bp-off]) is likewise a
            # plain [bp+disp] read that can't touch ES:BX.
            near_cast_local = (
                ncast(rhs)
                and 'far' not in rhs[1]
                and nid(rhs[2])
                and rhs[2][1] in self.locals
            )
            # `((unsigned int *)&long_local)[k]` — a word half of a long local:
            # a frame read (or a DX reuse) that can't touch ES:BX, so les-first.
            long_half = (
                rhs[0] == 'idx'
                and ncast(rhs[1])
                and rhs[1][1] == 'ptr_uint'
                and rhs[1][2][0] == 'addr'
                and nid(rhs[1][2][1])
                and rhs[1][2][1][1] in self.locals
                and self.lt(rhs[1][2][1][1]) == 'long'
                and num(rhs[2])
            )
            # FP_OFF/FP_SEG(global far pointer) is a plain absolute-word load
            # (mov ax,[g] / [g+2]) that can't touch ES:BX, so les-first — matching
            # a direct component-global read (SDA_DTA_OFF / SDA_DTA_SEG).
            fpseg_gfar = rhs[0] in ('fpoff', 'fpseg') and self.gfar(rhs[1])
            # A byte store needs only AL (no zero-extend); a word store needs AX.
            load = self.expr_to_al if kind == 'byte' else self.expr_to_ax
            if (
                self._is_rm(rhs)
                or self._is_local_arr_read(rhs)
                or near_cast_local
                or long_half
                or fpseg_gfar
            ):
                # a simple memory rhs (e.g. a global or a stack-buffer word) doesn't
                # touch ES:BX, so MSC loads the far pointer first, then the value.
                self.emit_les(fv)
                load(rhs)
            else:
                load(rhs)
                self.emit_les(fv)
            if kind == 'word':
                self.e26(0x89, modrm, *d8(disp))
            else:
                self.e26(0x88, modrm, *d8(disp))
            # The store doesn't touch AX; keep it tagged by the source id so a
            # following store of the SAME value reuses it (ES:BX is likewise still
            # live) — MSC's `*(int far*)(p+1B)=F34; *(int far*)(p+0B)=F34; …`.
            self.ax = (
                rhs[1] if (kind == 'word' and nid(rhs) and self.ax == rhs[1]) else None
            )
            # A BYTE store leaves the value in AL — tag it by the far lvalue so
            # passing that same field on reuses it (FCB_BIT15_CHECK handing
            # fcb->f_drvcode to GET_DPB_BY_DRIVE_INDEX at 0x82C6).  A word store
            # leaves only the low half there, so AL is dead.
            self.al = ('farb', repr(lhs)) if kind == 'byte' else None
            return
        # far_var[reg] = <byte expr>  →  al=expr; les bx,[addr]; mov es:[bx+idx],al
        # far_X[reg±const] / far_X[++reg] / far_X[reg++] = byte  —  the ripple
        # shift in TRIM_TRAILING_NAME_SPACES.  A far read rhs of the SAME pointer
        # (name[di+1]=name[di]) reuses the ES:BX that the read just loaded; a
        # pre-increment bumps the reg AFTER the rhs read but BEFORE the store
        # address, matching MSC's `les; mov al,[es:bx+di]; inc si; mov [es:bx+si],al`.
        fri = self.far_reg_idx(lhs)
        if fri:
            name, reg, disp, regname, pre, post = fri
            base_rm = 0x00 if reg == 'si' else 0x01
            modrm = (0x40 | base_rm) if disp else base_rm
            dbytes = (disp,) if disp else ()
            incop = sd(0x4E if 'dec' in (pre, post) else 0x46, reg)  # inc/dec si/di
            # Post-increment of a far index: the store uses the OLD index but the
            # reg must advance, so MSC captures it in CX and adds it to the base
            # (`mov cx,di; inc di; add bx,cx; mov [es:bx],al`) rather than
            # addressing `[es:bx+reg]` after the reg moved (GET_CWD's
            # `dest[di++] = path[si]` copy).
            if post and not disp:
                if num(rhs):
                    self.emit_les(name)
                elif self._simple_byte_rhs(rhs):
                    self.emit_les(name)
                    self.expr_to_al(rhs)
                else:
                    self.expr_to_al(rhs)
                    self.emit_les(name)
                # The old index is captured in CX when AL carries the value; a
                # CONSTANT store leaves AX free, so MSC captures it there
                # (PARSE_PATH_WITH_DRIVE's `out[len++] = '\\'`).
                cap = 0xC6 if num(rhs) else 0xCE  # mov ax/cx, si|di
                self.emit(0x8B, sd(cap, reg))
                self.emit(incop)  # inc si/di
                self.emit(0x03, 0xD8 if num(rhs) else 0xD9)  # add bx, ax/cx
                if num(rhs):
                    self.e26(0xC6, 0x07, rhs[1])  # mov byte [es:bx], imm
                else:
                    self.e26(0x88, 0x07)  # mov [es:bx], al
                self.bx = self.cxbx_var = None
                if reg == 'si':
                    self.si = None
                else:
                    self.di = None
                self.zaa()
                return
            if num(rhs):
                self.emit_les(name)
                if pre:
                    self.emit(incop)
                self.e26(0xC6, modrm, *dbytes, rhs[1])  # mov byte[es:bx+reg+d],imm
            elif self._simple_byte_rhs(rhs):
                self.emit_les(name)
                if pre:
                    self.emit(incop)
                self.expr_to_al(rhs)
                self.e26(0x88, modrm, *dbytes)  # mov [es:bx+reg+d],al
            else:
                self.expr_to_al(rhs)
                if pre:
                    self.emit(incop)
                self.emit_les(name)  # cached when rhs read the same far ptr
                self.e26(0x88, modrm, *dbytes)
            if post:
                self.emit(incop)
            if pre or post:  # the reg-var's value changed
                if reg == 'si':
                    self.si = None
                else:
                    self.di = None
            self.zaa()
            return
        fi = self.far_indexed_reg(lhs)
        if fi:
            name, reg = fi
            if reg == 'bx':
                # A BX reg var IS the index, so the far pointer's OFFSET is
                # loaded into DI instead of BX: `les di,[bp+d]; mov byte
                # [es:bx+di], imm` (DOS_FN_3B_CHDIR's path NUL terminator).
                if not num(rhs):
                    ni('bx-indexed far store', lhs, rhs)
                self.emit(0xC4, 0x7E, self.ld(name))  # les di, [bp+d]
                self.e26(0xC6, 0x01, rhs[1])  # mov byte [es:bx+di], imm
                self.bx = self.esbx = None
                return
            rm = 0x01 if reg == 'di' else 0x00
            if num(rhs):
                self.store_byte_imm(name, rm, rhs[1])
                return
            if self._simple_byte_rhs(rhs):
                # a local/const byte can't clobber ES:BX → MSC loads `les` first
                self.emit_les(name)
                self.expr_to_al(rhs)
            else:
                self.expr_to_al(rhs)
                self.emit_les(name)
            self.e26(0x88, rm)  # mov es:[bx+idx],al
            self.zaa()
            return
        # Byte-array stores indexed by a register var.
        if lhs[0] == 'idx' and self.gkind(lhs[1]) == 'arr':
            arr_addr = sa(n11(lhs))
            idx = lhs[2]
            # ARR[reg++] = *far_local++  —  the fused copy step of a
            # `while (*p) SCRATCH[si++] = *p++;` loop (COPY_DPB_AND_LOOKUP).
            # MSC reserves BX for the pending store (index postinc FIRST), bumps
            # the far pointer's OFFSET word in memory, and derefs the OLD offset
            # through DI reusing the ES the loop condition's `les` left live:
            #   mov bx,si; inc si; mov di,[bp+d]; inc word[bp+d];
            #   mov al,[es:di]; mov [bx+ARR],al
            if (
                idx[0] == 'postinc'
                and nid(idx[1])
                and self.is_reg_var(n11(idx))
                and nderef(rhs)
                and rhs[1][0] == 'postinc'
                and nid(rhs[1][1])
                and pf(self.lty(rhs[1][1]))
                and self.esbx == rhs[1][1][1]  # ES holds the far ptr's segment
            ):
                reg = self.regvars[n11(idx)]
                d = self.ld(rhs[1][1][1])
                self.emit(0x8B, sd(0xDE, reg))  # mov bx, si/di
                self.emit(sd(0x46, reg))  # inc si/di
                self.emit(0x8B, 0x7E, d)  # mov di, [bp+d]  (old offset)
                self.emit(0xFF, 0x46, d)  # inc word [bp+d]
                self.e26(0x8A, 0x05)  # mov al, [es:di]
                self.emit(0x88, 0x87, *w16(arr_addr))  # mov [bx+ARR], al
                self.bx = self.di = self.al = None
                if reg == 'si':
                    self.si = None
                return
            # ARR[reg++] = imm  →  mov bx,reg; inc reg; mov byte [bx+ARR],imm
            # (direct C6 store, no AL — COPY_DPB_AND_LOOKUP's trailing '\').
            if (
                idx[0] == 'postinc'
                and nid(idx[1])
                and self.is_reg_var(n11(idx))
                and num(rhs)
            ):
                reg = self.regvars[n11(idx)]
                self.emit(0x8B, sd(0xDE, reg))  # mov bx, si/di
                self.emit(sd(0x46, reg))  # inc si/di
                self.emit(0xC6, 0x87, *w16(arr_addr), rhs[1])
                self.bx = None
                if reg == 'si':
                    self.si = None
                return
            # ARR[reg++] = expr  →  al = expr; mov bx,reg; inc reg; mov [bx+ARR],al
            if idx[0] == 'postinc' and nid(idx[1]) and self.is_reg_var(n11(idx)):
                reg = self.regvars[n11(idx)]
                self.expr_to_al(rhs)
                self.emit(0x8B, sd(0xDE, reg))  # mov bx, si/di
                self.emit(sd(0x46, reg))  # inc si/di
                self.emit(0x88, 0x87, *w16(arr_addr))
                self.bx = self.al = None
                return
            # ARR[local_byte++] = ARR2[ARR3[reg]]  →  the VALUE first (its own BX
            # subscript zeroes BH), then the index — which reuses BH=0:
            #   mov bl,[reg+ARR3]; sub bh,bh; mov al,[bx+ARR2];
            #   mov bl,[bp+d]; inc byte[bp+d]; mov [bx+ARR],al
            # (RENAME_FCB's `QCHAR_TABLE[idx++] = MATCH_NAME_11EA[QPOS_TABLE[si]]`.)
            if (idx[0] == 'postinc' and nid(idx[1])
                    and self.stkid(idx[1]) and self.ucharty(idx[1])
                    and rhs[0] == 'idx' and self.gkind(rhs[1]) == 'arr'
                    and rhs[2][0] == 'idx' and self.gkind(rhs[2][1]) == 'arr'
                    and self.rvid(rhs[2][2])):
                d = self.ld(idx[1][1])
                inner_base = sa(rhs[2][1][1])
                outer_base = sa(rhs[1][1])
                r_reg = self.regvars[rhs[2][2][1]]
                self.emit(0x8A, 0x9C if r_reg == 'si' else 0x9D, *w16(inner_base))
                self.emit(0x2A, 0xFF)  # sub bh, bh
                self.emit(0x8A, 0x87, *w16(outer_base))  # mov al, [bx+ARR2]
                self.emit(0x8A, 0x5E, d)  # mov bl, [bp+d]
                self.emit(0xFE, 0x46, d)  # inc byte [bp+d]  (BH still 0)
                self.emit(0x88, 0x87, *w16(arr_addr))  # mov [bx+ARR], al
                self.bx = self.al = None
                return
            # ARR[local_byte++] = expr  →  index materialised BEFORE the value:
            #   mov bl,[bp+d]; inc byte[bp+d]; sub bh,bh; al=expr; mov [bx+ARR],al
            # (RENAME_FCB's `QPOS_TABLE[qcount++] = si` — a stack uchar counter, not
            # a register var, so the post-increment lands on memory.)
            if (idx[0] == 'postinc' and nid(idx[1])
                    and self.stkid(idx[1]) and self.ucharty(idx[1])):
                d = self.ld(idx[1][1])
                self.emit(0x8A, 0x5E, d)  # mov bl, [bp+d]
                self.emit(0xFE, 0x46, d)  # inc byte [bp+d]
                self.emit(0x2A, 0xFF)  # sub bh, bh
                self.expr_to_al(rhs)
                self.emit(0x88, 0x87, *w16(arr_addr))  # mov [bx+ARR], al
                self.bx = self.al = None
                return
            # ARR[reg] = imm  →  mov byte [reg+ARR], imm — but reuse a live AL that
            # already holds the constant (a preceding same-const store materialised
            # it: PARSE_FILESPEC's `fcb[si]=0x20; NAME_BUF[si]=0x20`).
            if nid(idx) and self.is_reg_var(idx[1]) and num(rhs):
                reg = self.rv(idx)
                modrm = sd(0x84, reg)  # [si/di + disp16]
                if self.al == rhs[1]:
                    self.emit(0x88, modrm, *w16(arr_addr))  # mov [reg+ARR], al
                else:
                    self.emit(0xC6, modrm, *w16(arr_addr), rhs[1])
                return
            # ARR[reg] = <byte expr>  →  al = expr; mov [reg+ARR], al
            if nid(idx) and self.is_reg_var(idx[1]):
                reg = self.rv(idx)
                self.expr_to_al(rhs)
                modrm = sd(0x84, reg)  # [si/di + disp16]
                self.emit(0x88, modrm, *w16(arr_addr))
                # AL still holds the stored byte — tag it so a following
                # `ARR[reg] == K` compares `cmp al,K` directly (RENAME_FCB's
                # `NAME_SCRATCH[si] = DIR_SEARCH_NAME[si]` then `== '?'`).
                self.al = ('gidx', arr_addr, reg)
                return
            # ARR[word-global] = <byte>  →  mov bx,[g]; al = expr; mov [bx+ARR], al
            if nid(idx) and self.gvw(idx) and (
                self.gkind(rhs) == 'bvar' or num(rhs) or self.ucharty(rhs)
            ):
                key = ('idxvar', idx[1])
                if self.bx != key:
                    self.emit(0x8B, 0x1E, *w16(sa(idx[1])))  # mov bx, [g]
                    self.bx = key
                if num(rhs):
                    self.emit(0xC6, 0x87, *w16(arr_addr), rhs[1])  # mov byte[bx+ARR],imm
                    return
                self.expr_to_al(rhs)  # al = byte (bvar/uchar — no BX use)
                self.emit(0x88, 0x87, *w16(arr_addr))  # mov [bx+ARR], al
                self.al = None  # bx stays cached as ('idxvar', idx)
                return
            # ARR[g] = ARR[g +/- c]  (same word-global index, const-offset src):
            #   mov bx,[g]; mov si,bx; mov al,[si+ARR+c]; mov [bx+ARR],al
            # MSC keeps the lvalue index in BX (reserved for the pending store)
            # and copies it to SI for the source subscript, folding +/-c into the
            # array-base displacement (buffer memmove, e.g. DELETE_CHAR).
            if (nid(idx) and self.gvw(idx) and rhs[0] == 'idx'
                    and nid(rhs[1]) and rhs[1][1] == lhs[1][1]
                    and rhs[2][0] == 'bin' and rhs[2][1] in ('+', '-')
                    and nid(rhs[2][2]) and rhs[2][2][1] == idx[1]
                    and num(rhs[2][3])):
                c = rhs[2][3][1] if rhs[2][1] == '+' else -rhs[2][3][1]
                self.emit(0x8B, 0x1E, *w16(sa(idx[1])))  # mov bx,[g]
                self.emit(0x8B, 0xF3)  # mov si,bx
                self.emit(0x8A, 0x84, *w16((arr_addr + c) & 0xFFFF))  # al=[si+ARR+c]
                self.emit(0x88, 0x87, *w16(arr_addr))  # mov [bx+ARR],al
                self.bx = ('idxvar', idx[1])
                self.si = self.al = None
                return
            # ARR[const] = <byte imm>  →  mov byte [ARR+const], imm
            if num(idx) and num(rhs):
                self.emit(0xC6, 0x06, *w16((arr_addr + idx[1]) & 0xFFFF), rhs[1])
                return
            # ARR[const] = <byte expr>  →  <expr → AL>; mov [ARR+const], al
            # (the 3-byte accumulator moffs store, as for a plain byte global —
            # COPY_DPB_ENTRY_TO_SDA re-lettering the staged path's drive).
            if num(idx):
                self.expr_to_al(rhs)
                self.emit(0xA2, *w16((arr_addr + idx[1]) & 0xFFFF))
                self.al = None
                return
            # Chained ?-fill: WORK[QPOS[r]] = QCHAR[idx++] = SRC[QPOS[r]] — one
            # matched wildcard char written to both the new-name FCB and the QCHAR
            # log (RENAME_FCB 9A57).  Load once through the QPOS[r] subscript,
            # store to QCHAR[idx++] and WORK[QPOS[r]] reusing AL and BH=0.
            # The destination may be a struct global's array member, which
            # lowers to BASE[k + i] (WORK_FCB's f_name is WORK_FCB[1 + i]);
            # fold that leading constant into the base for this rule only.
            _didx, _dbase = idx, arr_addr
            if nbin(_didx) and _didx[1] == '+' and num(_didx[2]):
                _dbase = (_dbase + _didx[2][1]) & 0xFFFF
                _didx = _didx[3]
            if (_didx[0] == 'idx' and self.gkind(_didx[1]) == 'arr'
                    and self.rvid(_didx[2])
                    and rhs[0] == 'assign'
                    and rhs[1][0] == 'idx' and self.gkind(rhs[1][1]) == 'arr'
                    and rhs[1][2][0] == 'postinc' and self.stkid(rhs[1][2][1])
                    and self.ucharty(rhs[1][2][1])
                    and rhs[2][0] == 'idx' and self.gkind(rhs[2][1]) == 'arr'
                    and rhs[2][2] == _didx):
                qpos_base = sa(_didx[1][1])
                r_reg = self.regvars[_didx[2][1]]
                qchar_base = sa(rhs[1][1][1])
                idx_disp = self.ld(rhs[1][2][1][1])
                src_base = sa(rhs[2][1][1])
                qmod = 0x9C if r_reg == 'si' else 0x9D
                self.emit(0x8A, qmod, *w16(qpos_base))  # mov bl,[si+QPOS]
                self.emit(0x2A, 0xFF)  # sub bh,bh
                self.emit(0x8A, 0x87, *w16(src_base))  # mov al,[bx+SRC]
                self.emit(0x8A, 0x5E, idx_disp)  # mov bl,[bp+idx]
                self.emit(0xFE, 0x46, idx_disp)  # inc byte [bp+idx]
                self.emit(0x88, 0x87, *w16(qchar_base))  # mov [bx+QCHAR],al
                self.emit(0x8A, qmod, *w16(qpos_base))  # mov bl,[si+QPOS]
                self.emit(0x88, 0x87, *w16(_dbase))  # mov [bx+WORK],al
                self.bx = self.al = None
                return
            # ARR[reg + const] = ARR[reg1 + reg2] — the source's TWO-register
            # subscript has no 8086 addressing mode, so the SECOND term is
            # copied into BX and the first stays the index register; the
            # destination keeps its own register with the constant folded into
            # the array base (COPY_DPB_ENTRY_TO_SDA's substituted-root shift).
            if (
                nbin(idx)
                and idx[1] == '+'
                and self.rvid(idx[2])
                and num(idx[3])
                and rhs[0] == 'idx'
                and nid(rhs[1])
                and rhs[1][1] == lhs[1][1]
                and nbin(rhs[2])
                and rhs[2][1] == '+'
                and self.rvid(rhs[2][2])
                and self.rvid(rhs[2][3])
            ):
                keep = self.rv(rhs[2][2])  # stays as the index register
                self.emit(0x8B, 0xD8 | rf(self.rv(rhs[2][3])))  # mov bx, si/di
                # mov al,[bx+si/di+ARR]
                self.emit(0x8A, 0x80 | (0 if keep == 'si' else 1), *w16(arr_addr))
                d = (arr_addr + idx[3][1]) & 0xFFFF
                rm = 0x84 | (0 if self.rv(idx[2]) == 'si' else 1)
                self.emit(0x88, rm, *w16(d))  # mov [si/di+ARR+const], al
                self.bx = self.al = None
                self._al_arr_store = True  # value live in AL for an assign-cond
                return
            # arr[<far byte> ± const] = <far byte> : BX is spoken for by the
            # zero-extended index, so the VALUE is fetched through ES:SI —
            # `mov bl,[es:bx+d]; sub bh,bh; les si,[q]; mov al,[es:si+e];
            # mov [bx+ARR±c],al` (JOIN swapping the two SUBST_TABLE entries).
            if nbin(idx) and idx[1] in ('+', '-') and num(idx[3]):
                _il = self.far_lvalue(idx[2])
                _vl = self.far_lvalue(rhs)
                if _il and _il[2] == 'byte' and _vl and _vl[2] == 'byte':
                    c = idx[3][1] if idx[1] == '+' else -idx[3][1]
                    self.emit_les(_il[0])
                    self.e26(0x8A, mod8(_il[1]) | 0x18 | 0x07, *d8(_il[1]))
                    self.emit(0x2A, 0xFF)  # sub bh, bh
                    self.emit(0xC4, 0x76, self.ld(_vl[0]))  # les si, [bp+q]
                    self.essi = _vl[0]
                    self.e26(0x8A, mod8(_vl[1]) | 0x04, *d8(_vl[1]))  # mov al,[es:si+e]
                    self.emit(0x88, 0x87, *w16((arr_addr + c) & 0xFFFF))
                    self.bx = self.si = self.esbx = self.al = None
                    return
            # arr[<far byte>] = <uchar local> : the index zero-extends into BX
            # and the value comes straight from the frame
            # (JOIN's `SUBST_TABLE[regs->r_bl] = idx`).
            _il = self.far_lvalue(idx)
            if _il and _il[2] == 'byte' and self.locid(rhs) and (
                self.lt(rhs[1]) in ('uchar', 'char')
            ):
                self.emit_les(_il[0])
                self.e26(0x8A, mod8(_il[1]) | 0x18 | 0x07, *d8(_il[1]))
                self.emit(0x2A, 0xFF)  # sub bh, bh
                self.ldal(self.ld(rhs[1]))  # mov al, [bp+d]
                self.emit(0x88, 0x87, *w16(arr_addr))  # mov [bx+ARR], al
                self.esbx, self.bx = _il[0], None
                return
            # arr[<uchar local> ± const] = 0 : widening the index already put a
            # zero in BH, so MSC stores THAT rather than materialising another
            # (SUBST clearing the 11-byte FCB name area).
            _i = None
            if nbin(idx) and idx[1] == '+' and num(rhs) and rhs[1] == 0:
                if num(idx[2]) and self.locid(idx[3]):
                    _i, _k = idx[3], idx[2][1]
                elif num(idx[3]) and self.locid(idx[2]):
                    _i, _k = idx[2], idx[3][1]
            if _i is not None and self.lt(_i[1]) in ('uchar', 'char'):
                self.emit(0x8A, 0x5E, self.ld(_i[1]))  # mov bl, [bp+d]
                self.emit(0x2A, 0xFF)  # sub bh, bh
                self.emit(0x88, 0xBF, *w16((arr_addr + _k) & 0xFFFF))
                self.bx = None
                self._bh_zero = True
                return
            # arr[<int local/param>] = <byte const> : index straight into BX and
            # store the immediate — `mov bx,[bp+d]; mov byte [bx+ARR],imm`
            # (EDIT_TEMPLATE_PROCESS terminating the line with CR).  BX keeps the
            # index so a following `= <that local>` reuses it.
            if self.locid(idx) and wint(self.lt(idx[1])) and num(rhs):
                self.ldbx(self.ld(idx[1]))  # mov bx, [bp+d]
                self.emit(0xC6, 0x87, *w16(arr_addr), rhs[1] & 0xFF)
                self.bx = ('idxloc', idx[1])
                return
            # arr[A] = arr2[B] with BX already holding the widened A (from the
            # compare that ended the search): the SOURCE index goes to SI as a
            # word masked to a byte, and the store reuses BX —
            # `mov si,[bp+B]; and si,0FFh; mov al,[si+ARR2]; mov [bx+ARR],al`
            # (UNJOIN_DRIVE unlinking the SUBST chain at 0x759F).
            if (
                self.locid(idx)
                and self.bx == ('idxloc', idx[1])
                and rhs[0] == 'idx'
                and self._gbarr(rhs[1]) is not None
                and self.locid(rhs[2])
                and self.lt(rhs[2][1]) in ('uchar', 'char')
            ):
                self.emit(0x8B, 0x76, self.ld(rhs[2][1]))  # mov si, [bp+B]
                self.emit(0x81, 0xE6, 0xFF, 0x00)  # and si, 0FFh
                self.emit(0x8A, 0x84, *w16(self._gbarr(rhs[1])))  # mov al,[si+ARR2]
                self.emit(0x88, 0x87, *w16(arr_addr))  # mov [bx+ARR], al
                self.si = self.al = None
                return
            # arr[<uchar local>] = <byte const> : widen the index into BX and
            # store the immediate; BH is already zero when a preceding widen
            # left it so (UNJOIN_DRIVE clearing its own slot at 0x75AE).
            if self.locid(idx) and self.lt(idx[1]) in ('uchar', 'char') and num(rhs):
                self.emit(0x8A, 0x5E, self.ld(idx[1]))  # mov bl, [bp+d]
                if not getattr(self, '_bh_zero', False):
                    self.emit(0x2A, 0xFF)  # sub bh, bh
                    self._bh_zero = True
                self.emit(0xC6, 0x87, *w16(arr_addr), rhs[1] & 0xFF)
                self.bx = ('idxloc', idx[1])
                return
            ni('arr-store', lhs, rhs)
        # far_local[*(uint far *)(far_local + d)] = <byte> : same reversed
        # addressing as the read (SET_FCB truncating the CDS path at c_pathoffw
        # and putting the displaced byte back).
        if lhs[0] == 'idx':
            fsi = self._far_self_idx(lhs[1], lhs[2])
            if fsi:
                if num(rhs):
                    self._far_self_idx_base(*fsi)
                    self.e26(0xC6, 0x00, rhs[1] & 0xFF)  # mov byte [es:bx+si], imm
                else:
                    self._far_self_idx_base(*fsi)
                    self.expr_to_al(rhs)
                    self.e26(0x88, 0x00)  # mov [es:bx+si], al
                self.bx = self.esbx = None
                return
        # far_ptr_local[reg] = expr (byte) → les bx,[bp+d]; mov byte[es:bx+si/di],al/imm
        if lhs[0] == 'idx' and pf(self.lty(lhs[1])) and self.rvid(lhs[2]):
            rm = sd(0x00, self.regvars[lhs[2][1]])  # [bx+si]/[bx+di]
            if num(rhs):
                if self.store_byte_imm(n11(lhs), rm, rhs[1]):
                    return
            else:
                self.expr_to_al(rhs)
                self.emit_les(n11(lhs))
                self.e26(0x88, rm)  # mov [es:bx+idx],al
            self.zaa()
            return
        # far_var[near-int local] = num  →  mov bx,[idx]; les si,[tbl]; mov byte[es:bx+si],imm
        if lhs[0] == 'idx' and self.gfar(lhs[1]) and self.stkid(lhs[2]) and num(rhs):
            idisp = self.ld(lhs[2][1])
            self.ldbx(idisp)  # mov bx, [bp+idx]
            addr = sa(n11(lhs))
            self.emit(0xC4, 0x36, *w16(addr))  # les si, [tbl]
            self.e26(0xC6, 0x00, rhs[1])  # mov byte [es:bx+si], imm
            self.bx = self.esbx = None
            return
        # local_array[reg var] = <byte expr>  →  al = expr; mov [bp+si/di+off], al
        # (DOS_FN_29_PARSE_FILENAME_FCB filling the 8.3 name buffer).
        if lhs[0] == 'idx' and self.lty(lhs[1]).startswith('arr') and self.rvid(lhs[2]):
            disp = self.ld(lhs[1][1])
            self.expr_to_al(rhs)
            self.emit(0x88, sd(0x42, self.rv(lhs[2])), disp)  # mov [bp+si/di+off],al
            self.zaa()
            return
        # local_array[const] = byte  →  mov byte [bp-off+const], imm/al
        if lhs[0] == 'idx' and self.lty(lhs[1]).startswith('arr') and num(lhs[2]):
            disp = self.ldi(lhs)
            d = (disp + lhs[2][1]) & 0xFF
            if num(rhs):
                self.emit(0xC6, 0x46, d, rhs[1])  # mov byte [bp+d], imm
            else:
                self.expr_to_al(rhs)
                self.stal(d)  # mov [bp+d], al
            self.zaa()
            return
        # *(T *)(local_array + const) = expr  →  word/long store at [bp-off+const]
        if (
            nderef(lhs)
            and ncast(lhs[1])
            and 'far' not in n11(lhs)
            and nbin(n12(lhs))
            and n12(lhs)[1] == '+'
            and self.lty(n12(lhs)[2]).startswith('arr')
            and num(n12(lhs)[3])
        ):
            disp = self.ld(n12(lhs)[2][1])
            d = (disp + n12(lhs)[3][1]) & 0xFF
            if 'long' in n11(lhs):
                self.load_long_axdx(rhs)  # rhs → DX:AX
                self.stax(d)  # mov [bp+d], ax
                self.emit(0x89, 0x56, d + 2)  # mov [bp+d+2], dx
            elif num(rhs):
                # word member = imm → mov word [bp+d], imm (AX untouched;
                # DOS_FN_44's pkt.i_status = 0)
                self.emit(0xC7, 0x46, d, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)
                return
            else:
                self.expr_to_ax(rhs)
                self.stax(d)  # mov [bp+d], ax
            self.zaa()
            return
        # ((T *)&local)[const] = value  →  store into the local's frame slot at a
        # fixed element offset.  Byte elements (`(uchar*)&t`) clear a long's high
        # byte; WORD elements (`(uint*)&pos`) set a long's low/high word.
        if (
            lhs[0] == 'idx'
            and ncast(lhs[1])
            and 'far' not in n11(lhs)
            and self.addr_loc(n12(lhs))
            and num(lhs[2])
        ):
            word = 'int' in n11(lhs)  # ptr_int / ptr_uint
            d = (self.ld(n11(n12(lhs))) + lhs[2][1] * (2 if word else 1)) & 0xFF
            if num(rhs) and word:
                self.emit(0xC7, 0x46, d, rhs[1] & 0xFF, (rhs[1] >> 8) & 0xFF)
            elif num(rhs):
                self.emit(0xC6, 0x46, d, rhs[1])  # mov byte [bp+d], imm
            elif word:
                self.expr_to_ax(rhs)
                self.stax(d)  # mov [bp+d], ax
            else:
                self.expr_to_al(rhs)
                self.stal(d)  # mov [bp+d], al
            self.zaa()
            self.invalidate_mem(n11(n12(lhs)))  # the local's value changed
            return
        # *(T *)&local = expr  →  store to the local's slot at offset 0 (e.g. set a
        # long's low word, leaving the high word as-is).
        if (
            nderef(lhs)
            and ncast(lhs[1])
            and 'far' not in n11(lhs)
            and self.addr_loc(n12(lhs))
        ):
            disp = self.ld(n11(n12(lhs)))
            word = 'int' in n11(lhs)
            if num(rhs):
                if word:
                    self.emit(0xC7, 0x46, disp, rhs[1], (rhs[1] >> 8))
                else:
                    self.emit(0xC6, 0x46, disp, rhs[1])
            else:
                self.expr_to_ax(rhs)
                self.stax(disp)
            self.zaa()
            self.invalidate_mem(n11(n12(lhs)))
            return
        # far_ptr[<uchar local>] = <byte>: the index has to be zero-extended
        # through BX (`mov bl,[bp+d]; sub bh,bh`), so the BASE takes ES:SI and
        # the store is `mov [es:bx+si],al` — the mirror of the usual bx-base
        # form (JOIN copying the path into its CDS entry).
        if (
            lhs[0] == 'idx'
            and nid(lhs[1])
            and lhs[1][1] in self.locals
            and pf(self.lty(lhs[1]))
            and nid(lhs[2])
            and lhs[2][1] in self.locals
            and self.lt(lhs[2][1]) in ('uchar', 'char')
            and not self.is_reg_var(lhs[2][1])
        ):
            self.expr_to_al(rhs)
            self.emit(0x8A, 0x5E, self.ld(lhs[2][1]))  # mov bl, [bp+idx]
            self.emit(0x2A, 0xFF)  # sub bh, bh
            self.emit(0xC4, 0x76, self.ld(lhs[1][1]))  # les si, [bp+base]
            self.essi = lhs[1][1]
            self.e26(0x88, 0x00)  # mov [es:bx+si], al
            self.bx = self.si = self.esbx = None
            return
        if not nid(lhs):
            ni('gen_assign', lhs, rhs)
        name = lhs[1]
        if name in self.locals:
            # Register-allocated local (SI, DI or BX)
            if self.is_reg_var(name):
                reg = self.regvars[name]
                # A BL byte register var takes a BYTE move — `mov bl,[bp+d]`
                # for a uchar local, `mov bl,imm8` for a constant.  BH is left
                # alone; each use re-zeroes it (`sub bh,bh`) before indexing.
                if reg == 'bl':
                    if num(rhs):
                        self.emit(0xB3, rhs[1])  # mov bl, imm8
                    elif self.stkid(rhs) and self.ucharty(rhs):
                        self.emit(0x8A, 0x5E, self.ld(rhs[1]))  # mov bl,[bp+d]
                    elif self.gkind(rhs) == 'bvar':
                        self.emit(0x8A, 0x1E, *w16(sa(rhs[1])))  # mov bl,[g]
                    else:
                        self.expr_to_al(rhs)
                        self.emit(0x8A, 0xD8)  # mov bl, al
                    self.bx = None
                    return
                if num(rhs) and rhs[1] == 0:
                    self.emit(0x33, 0xC0 | (rf(reg) << 3) | rf(reg))  # xor r, r
                elif num(rhs):
                    self.emit(0xB8 | rf(reg), rhs[1], (rhs[1] >> 8))  # mov r, imm
                elif self.rvid(rhs):
                    dst, src = rf(reg), rf(self.rv(rhs))
                    self.emit(0x8B, 0xC0 | (dst << 3) | src)  # mov si/di, si/di
                elif not self._force_regvar_ax and self._is_rm(rhs):
                    self._emit_rm_op(0x8B, reg, rhs)  # mov si/di, <load>
                elif (
                    not self._force_regvar_ax
                    and nbin(rhs)
                    and rhs[1] == '-'
                    and self._is_rm(rhs[2])
                    and self._is_rm(rhs[3])
                ):
                    self._emit_rm_op(0x8B, reg, rhs[2])  # mov si/di, a
                    self._emit_rm_op(0x2B, reg, rhs[3])  # sub si/di, b
                elif (
                    not self._force_regvar_ax
                    and (self.far_lvalue(rhs) or (None, None, None))[2] == 'word'
                ):
                    # reg = far word → load straight into SI/DI (no AX round-trip)
                    base, fdisp, _ = self.far_lvalue(rhs)
                    self.emit_les(base)
                    self.e26(
                        0x8B,
                        mod8(fdisp) | (rf(reg) << 3) | 0x07,
                        *d8(fdisp),
                    )  # mov si/di/bx,[es:bx+d]
                    if reg == 'bx':
                        # A BX reg var overwrites the `les` base it just read
                        # through — the next far access must reload ES:BX.
                        self.bx = self.esbx = None
                elif (
                    not self._force_regvar_ax
                    and (self.far_lvalue(rhs) or (None, None, None))[2] == 'byte'
                ):
                    # reg = far byte → zero-extend into SI/DI: mov al,[es:bx+d];
                    # sub ah,ah; mov si/di,ax
                    self.expr_to_al(rhs)
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                    self.emit(0x8B, 0xC0 | (rf(reg) << 3))  # mov si/di/bx, ax
                    self.zaa()
                elif not self._force_regvar_ax and nbin(rhs) and rhs[1] in ('+', '-'):
                    # reg = <chain of +/- terms> : first term → SI, then add/sub
                    # SI, term in place (MSC keeps the accumulator in SI).
                    terms = []

                    def _flatpm(n):
                        if nbin(n) and n[1] in ('+', '-'):
                            _flatpm(n[2])
                            terms.append((n[1], n[3]))
                        else:
                            terms.append(('+', n))

                    _flatpm(rhs)
                    self.expr_to_ax(terms[0][1])  # first term → AX
                    self.emit(0x8B, 0xF0 if reg == 'si' else 0xF8)  # mov si/di, ax
                    rb = sd(0xF6, reg)  # si/di r/m field
                    for op, t in terms[1:]:
                        opc = 0x03 if op == '+' else 0x2B  # add/sub
                        if num(t):
                            n = t[1] & 0xFFFF
                            self.emit(
                                (0x83 if i8(n) else 0x81),
                                (sd(0xC6, reg)) if op == '+' else (sd(0xEE, reg)),
                                n,
                                *(() if i8(n) else ((n >> 8),)),
                            )
                        elif self.gvw(t):
                            a = SYMS[t[1]][1]
                            self.emit(
                                opc, 0x36 if reg == 'si' else 0x3E, *w16(a)
                            )  # add/sub si,[addr]
                        elif self.locid(t) and not self.is_reg_var(t[1]):
                            d = self.ld(t[1])
                            self.emit(
                                opc, 0x76 if reg == 'si' else 0x7E, d
                            )  # add/sub si,[bp+d]
                        else:
                            ni('regvar term', t)
                else:
                    # reg = expr : evaluate to AX then `mov reg, ax`
                    self.expr_to_ax(rhs)
                    self.emit(0x8B, 0xC0 | (rf(reg) << 3))  # mov si/di/bx, ax
                # track whether this reg-var now holds a literal 0 (so a following
                # `mem == 0` can reuse it as `cmp [mem], si/di`, like MSC)
                self._regvar_zero[reg] = num(rhs) and rhs[1] == 0
                return
            disp, ty = self.lvar(name)
            if ty == 'uchar':
                if num(rhs):
                    if self._force_var_ax:
                        # if/else merge: materialize in AL so the `mov [bp+d],al`
                        # store tail merges across the arms (xor al,al / mov al,imm)
                        if rhs[1] & 0xFF == 0:
                            self.emit(0x32, 0xC0)  # xor al, al
                        else:
                            self.emit(0xB0, rhs[1])  # mov al, imm
                        self.stal(disp)  # mov [bp+d], al
                        self.al = None
                        return
                    if rhs[1] == 0 and getattr(self, '_bh_zero', False):
                        # BH is already zero from a preceding index widen, so MSC
                        # stores THAT rather than an immediate — one byte shorter
                        # (UNJOIN_DRIVE restarting its scan counter at 0x75B6).
                        self.emit(0x88, 0x7E, disp)  # mov [bp+d], bh
                    else:
                        self.emit(0xC6, 0x46, disp, rhs[1])  # mov byte[bp+d],imm
                    if self.al == name:  # AL untouched; only this local's tag dies
                        self.al = None
                    return
                self.expr_to_al(rhs)
                self.stal(disp)
                # AL still holds the stored value.  Normally tag it by the local
                # so a following use of the local reuses AL.  But when the local
                # is mutated by the very next statement (`drive--`), AL no longer
                # matches the local — so if the source was a far byte, tag AL by
                # that source instead, so a later test of the SAME far byte reuses
                # it (`drive = fcb[6]; drive--; if (fcb[6] == 0) …` → `or al,al`).
                fr = self.far_lvalue(rhs)
                nxt = self._peek_next
                mutated_next = (
                    nxt
                    and nxt[0] == 'expr'
                    and nxt[1][0] in ('postinc', 'postdec')
                    and n11(nxt) == ('id', name)
                )
                if fr and fr[2] == 'byte' and mutated_next:
                    self.al = ('rhs', rhs)
                else:
                    self.al = name
            else:
                if num(rhs) and self._force_var_ax:
                    # if/else merge: route via AX so the `mov [bp+d],ax` tail merges
                    n = rhs[1] & 0xFFFF
                    self.mvax0(n)
                    self.stax(disp)  # mov [bp+d], ax
                elif num(rhs):
                    n = rhs[1] & 0xFFFF
                    self.emit(0xC7, 0x46, disp, *w16(n))
                    self.ax = None
                elif self.rvid(rhs):
                    self.emit(
                        0x89, 0x76 if self.rv(rhs) == 'si' else 0x7E, disp
                    )  # mov [bp+d], si/di
                else:
                    self.expr_to_ax(rhs)
                    self.stax(disp)
                    self.ax = name
                self.invalidate_mem(name)
                self.ax = name
            return
        if gsym(name, 'var'):
            addr = sa(name)
            # extern = reg_var  →  mov [addr], si/di  (direct, no AX round-trip)
            if self.locid(rhs) and self.is_reg_var(rhs[1]):
                modrm = 0x36 if self.rv(rhs) == 'si' else 0x3E
                self.emit(0x89, modrm, *w16(addr))
                return
            # extern = const  →  mov word [addr], imm16  (or, inside an if/else
            # whose other arm assigns the same global, materialize in AX so the
            # `mov [addr],ax` store merges: mov ax,imm / xor ax,ax; mov [addr],ax)
            if num(rhs):
                n = rhs[1] & 0xFFFF
                if self._force_var_ax:
                    self.mvax0(n)
                    self.staxm(addr)  # mov [addr], ax
                    self.ax = None
                    return
                self.emit(0xC7, 0x06, *w16(addr), *w16(n))
                return
            # extern = expr % divisor → div, then store the remainder (DX) direct
            if nbin(rhs) and rhs[1] == '%':
                self.expr_to_ax(rhs[2])
                self.emit(0x2B, 0xD2)  # sub dx, dx
                self._emit_div_operand(rhs[3])
                self.emit(0x89, 0x16, *w16(addr))  # mov [addr], dx
                self.zad()
                return
            self.expr_to_ax(rhs)
            self.staxm(addr)  # mov [addr], ax
            # AX holds the stored value.  When the source was a simple readable
            # id, keep AX tagged by that source (MSC tracks the loaded operand,
            # not the destination) so a following store of the SAME source reuses
            # it — e.g. `WRITE_RESULT = F34; *(int far*)(driver+1B) = F34; …`.
            self.ax = rhs[1] if (nid(rhs) and self.ax == rhs[1]) else name
            # AX equals this GLOBAL's value too, whatever name it is tagged
            # under.  Recorded with the buffer position so the alias is only
            # honoured while nothing further has been emitted (see the loop
            # back-edge seed in _stmt_for).
            self._ax_alias = (name, len(self.buf))
            return
        if gsym(name, 'far_var'):
            addr = sa(name)
            # A far pointer is set from a far-returning call: DX:AX → off:seg.
            # Split-store the low word (AX) then the high word (DX).
            self.gen_call(rhs)
            self.staxm(addr)  # mov [addr], ax
            self.emit(0x89, 0x16, *w16(addr + 2))  # mov [addr+2], dx
            self.ax = None
            return
        raise NameError(name)

    def gen_call(self, e, tail=False, cleanup=True, share_lbl=None,
                 share_ax_lbl=None):
        target = e[1]
        args = e[2]
        if not nid(target) or SYMS[target[1]][0] not in ('func', 'far_func'):
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
            return (
                nderef(x) and self.lty(x[1]) in ('ptr_int', 'ptr_uint')
            ) or self.near_lvalue(x)

        for idx, a in enumerate(args):
            a2 = a[2] if (ncast(a) and a[1] == 'long') else a
            fl = self.far_lvalue(a2)
            if fl and fl[2] == 'word' and not isinstance(fl[0], tuple):
                # Preload ES:BX only when the far-word arg is pushed early (not the
                # first C arg / last pushed — MSC loads les inline there) and no
                # earlier-pushed arg clobbers BX.
                if idx > 0 and not any(_clobbers_bx(x) for x in args[idx + 1 :]):
                    self.emit_les(fl[0])
                break
        # Enter the arg list trusting the tracked AH state: an ES:BX preload
        # (les) doesn't touch AH, so a known-0 AH (e.g. seeded on a loop
        # back-edge) is still live for the first byte arg's widen.
        pbytes = BYTE_PARAMS.get(target[1], ())
        pfar = FAR_PARAMS.get(target[1], ())
        for i in range(len(args) - 1, -1, -1):
            a = args[i]
            far_param = i < len(pfar) and pfar[i]
            # Shared multi-arg call tail: the label lands before the leftmost
            # arg's push (lbl() clears the caches, so the push emits cold —
            # correct for every jump-in site as well as this fall-through).
            # Decide the leftmost arg's AX reuse BEFORE any label clears the
            # cache: the value it reuses comes from args[1], which every jump-in
            # site pushes too, so the fact survives the join.
            ax_live = (
                share_ax_lbl is not None
                and i == 0
                and num(a)
                and self.ax == ('imm', a[1] & 0xFFFF)
            )
            if share_lbl and a is args[0]:
                self.lbl(share_lbl)
            if share_ax_lbl and i == 0:
                # The leftmost arg is where the wider shared tail begins: its
                # VALUE differs per site, its push does not.  A repeated literal
                # still reuses the live AX, so the two 2s of
                # `lookup_error_msg(2, 2, 3, 8)` become `mov ax,2; push ax; push ax`.
                if ax_live:
                    pass
                elif num(a):
                    self.mvax0(a[1] & 0xFFFF)
                else:
                    self.expr_to_ax(a)
                self.lbl(share_ax_lbl)
                self.emit(0x50)  # push ax
                self.ax = None
                self._ah_zero = False
                nbytes += 2
                continue
            self.push_arg(a, byte_param=(i < len(pbytes) and pbytes[i]),
                          arg0=(i == 0), far_param=far_param)
            # far pointers and longs (local/param or far_var global) are 4 bytes
            far_arg = (
                (
                    pf(self.lty(a))
                    or self.lty(a) in ('long', 'ulong')
                    or self.gkind(a) in ('far_var', 'long_var')
                )
                or (ncall(a) and self.gkind(a[1]) == 'far_func')
                or (nderef(a) and self.lty(a[1]).startswith('ptr_ptr_far'))
                or (a[0] in ('bin', 'cast') and self._is_long_expr(a))
                or (ncast(a) and pf(a[1]))
                or (nderef(a) and ncast(a[1]) and 'ptr_far_ptr_far' in n11(a))
                or (nderef(a) and (self.near_lvalue(a) or (None,))[-1] == 'long')
                # far pointer + const: `(unsigned char far *)fcb + 1`
                or (
                    nbin(a)
                    and a[1] == '+'
                    and (
                        (ncast(a[2]) and pf(a[2][1]))
                        or pf(self.lty(a[2]))
                    )
                )
                # a bare near address promoted to far by a `far *` param
                or (far_param and self._promotable_near_addr(a))
            )
            nbytes += 4 if far_arg else 2
        self.emit_call(addr)
        # cdecl: caller cleans args.  Pascal callees clean their own (ret N);
        # cleanup=False defers to a shared site (switch).  A tail call can skip
        # `add sp` only when the epilogue's `mov sp,bp` reclaims the args with
        # nothing in between — but a `pop si/di` (saved reg) must see clean SP,
        # so don't skip when the function saves SI/DI, nor when the frame holds an
        # address-taken local array (MSC keeps the explicit cleanup then).
        tail_skip = tail and not (
            self.uses_si or self.uses_di or self._has_array_local
        )
        if args and not tail_skip and cleanup and target[1] not in PASCAL:
            self.emit(0x83, 0xC4, nbytes)
        # A near call clobbers AX/BX/DX/ES (caller-saved); SI/DI are preserved.
        self.clob()
        # AH is unknown after a call (its result / a trailing uchar-arg push may
        # have left it non-zero) — don't let a stale `_ah_zero=True` leak to a
        # later zero-extend outside the arg list.
        self._ah_zero = False
        return nbytes

    @staticmethod
    def _switch_case_call(body):
        """A switch case body must be a single function call (+ optional
        break) — the DOS sub-dispatch shape. Return its call expr."""
        stmts = [s for s in body if s[0] != 'break']
        if len(stmts) == 1 and stmts[0][0] == 'expr' and ncall(stmts[0][1]):
            return stmts[0][1]
        ni('switch case must be a single call')

    def gen_switch_table(self, val, cases, default):
        """MSC dense-table switch (DOS_FN_44_IOCTL): widen the value to AX,
        bounds-check, `add ax,ax; xchg ax,bx; jmp word [cs:bx+TBL]`, case bodies
        in source order, then the dw table (absolute case addresses; missing
        values -> after-switch).  `break` jumps past the table; an empty case
        body falls through to the next case (both values share one table target).

        A WIDE value set is PARTITIONED the way MSC does it rather than tabled
        whole (SET_INPUT_BUFFERS_AND_DESC's edit keys span 43h..0C8h): values
        are clustered while the gaps stay small, a contiguous run at the top of
        the cluster that shares one target is peeled off into a range compare,
        and whatever is left over becomes a `cmp/je` ladder placed AFTER the
        table.  Bodies stay in source order throughout; only the ladder is
        emitted in ascending value order."""
        if default:
            ni('table switch default body')
        if any(not num(k) for k, _ in cases):
            ni('table switch non-constant case')
        self.expr_to_ax(val)
        brk = self.fresh('swbrk')
        tbl = self.fresh('swtbl')

        # Case labels up front (the dispatch code references them), following the
        # same fall-through rule as before: an empty body shares the next label.
        case_lbl, bodies, pending = {}, [], []
        for k, body in cases:
            pending.append(k[1])
            if not body:
                continue
            cl = self.fresh('case')
            for v in pending:
                case_lbl[v] = cl
            pending = []
            bodies.append((cl, body))
        self._switch_case_lbls.update(case_lbl.values())

        sv = sorted(case_lbl)
        # A range dense enough overall (at least one case per 3 slots) is tabled
        # WHOLE, gaps and all — the F-key switch spans 3Bh..53h with a 16-slot
        # hole and MSC still tables it.  Only a sparse spread gets partitioned,
        # and then the cluster grows while the gaps stay small.
        if sv[-1] - sv[0] + 1 <= 3 * len(sv):
            cluster, sparse = sv, []
        else:
            end = 0
            for i in range(1, len(sv)):
                if sv[i] - sv[i - 1] > 4:  # more than 3 dead slots — split here
                    break
                end = i
            cluster, sparse = sv[: end + 1], sv[end + 1 :]
        bound = cluster[-1]
        peels = []
        while len(cluster) > 2:
            tgt = case_lbl[cluster[-1]]
            j = len(cluster) - 1
            while (
                j > 0
                and case_lbl[cluster[j - 1]] == tgt
                and cluster[j - 1] == cluster[j] - 1
            ):
                j -= 1
            # Peel only when it PAYS: the range compare costs 5 bytes, each
            # table slot it removes saves 2.  CHECK_FILE_ATTR_BITS' top run
            # (9,10 sharing the return-0 block) frees 2 slots and must stay in
            # the table; the edit keys' 4Fh/50h frees 3 and comes out.
            if len(cluster) - j < 2 or 2 * (cluster[-1] - cluster[j - 1]) <= 5:
                break
            peels.append((cluster[j], tgt))
            cluster = cluster[:j]
        lo, hi = cluster[0], cluster[-1]

        if sparse:
            sparse_lbl = self.fresh('swsparse')
            l1 = self.fresh('swlo')
            self.emit(0x3D, *w16(bound))  # cmp ax, cluster top
            self.emit_jcc(0x76, l1)  # jbe
            self.emit_jmp_short(sparse_lbl)  # jmp ladder
            self.lbl(l1)
        for runlo, tgt in peels:
            self.emit(0x3D, *w16(runlo))  # cmp ax, run base
            self.emit_jcc(0x73, tgt)  # jnb body
        if lo == 0 and not sparse and not peels:
            self.emit(0x3D, *w16(hi))  # cmp ax, maxcase
            self.emit_jcc(0x77, brk)  # ja after-switch (default)
        else:
            if lo:
                self.emit(0x2D, *w16(lo))  # sub ax, lo
            self.emit(0x3D, *w16(hi - lo))  # cmp ax, span
            jt = self.fresh('swjt')
            self.emit_jcc(0x76, jt)  # jbe table jump
            self.emit_jmp_short(brk)  # jmp after-switch (default)
            self.lbl(jt)
        self.emit(0x03, 0xC0)  # add ax, ax
        self.emit(0x93)  # xchg ax, bx
        self.atoms.append(('jmp_tbl', (0x2E, 0xFF, 0xA7), tbl))
        self.buf.extend((0x2E, 0xFF, 0xA7, 0, 0))
        self.clob()
        self.bx = None

        self.break_lbls.append(brk)
        for cl, body in bodies:
            self.lbl(cl)
            for st in body:
                self.stmt(st)
        self.break_lbls.pop()
        targets = [case_lbl.get(v, brk) for v in range(lo, hi + 1)]
        self.lbl(tbl)
        self.atoms.append(('dw_tbl', (), targets))
        self.buf.extend(bytes(2 * len(targets)))
        if sparse:
            self.lbl(sparse_lbl)
            for v in sparse:  # the ladder alone is ordered by VALUE, not source
                self.emit(0x3D, *w16(v))
                self.emit_jcc(0x74, case_lbl[v])  # jz body
            self.emit_jmp_short(brk)
        self.lbl(brk)

    @staticmethod
    def _all_call_cases(cases):
        """True if every case body is a single call (+ optional break) — the
        MSC sub-dispatch shape handled by the shared-cleanup form."""
        for _, body in cases:
            stmts = [s for s in body if s[0] != 'break']
            if not (len(stmts) == 1 and stmts[0][0] == 'expr' and ncall(stmts[0][1])):
                return False
        return True

    def gen_switch_general(self, val, cases, default):
        """General MSC switch (DOS_FN_42): eval the value to AX, a `cmp ax,K /
        je Ck` chain in source order (K==0 uses `or ax,ax`), then the default
        body as the chain fall-through, then the case bodies in source order,
        then the break target.  Each body ends in its own `break` (jmp brk); an
        empty case threads its je straight to brk (jump-threading + dead-jmp
        elim).  Shared body tails (the accumulate arms, the error stores) are
        left to resolve()'s cross-jumping."""
        self.expr_to_ax(val)
        brk = self.fresh('swbrk')
        caselbls = [self.fresh('case') for _ in cases]
        for (k, _), cl in zip(cases, caselbls):
            if k[1] == 0:
                self.emit(0x0B, 0xC0)  # or ax, ax
            else:
                self.emit(0x3D, *w16(k[1]))  # cmp ax, imm16
            self.emit_jcc(0x74, cl)  # je case
        self.break_lbls.append(brk)
        # default body falls through the chain; a missing/empty default just
        # jumps to break
        if default:
            for st in default:
                self.stmt(st)
            if not self._block_terminates(default):
                self.emit_jmp_short(brk)
        else:
            self.emit_jmp_short(brk)
        for (k, body), cl in zip(cases, caselbls):
            self.lbl(cl)
            for st in body:
                self.stmt(st)
            if not self._block_terminates(body):
                self.emit_jmp_short(brk)
        self.break_lbls.pop()
        self.lbl(brk)

    def gen_switch(self, val, cases, default):
        """MSC sub-dispatch: eval the value to AX, emit a `cmp ax,K / je case`
        chain + default jump, then the case bodies. Each case is a single call;
        they share one `add sp,N` cleanup and exit jump (MSC's tail-merge).
        A dense many-case switch (>= 8 case labels) uses the jump-table form;
        a switch with a default body or non-call cases uses the general form."""
        if len(cases) >= 8:
            return self.gen_switch_table(val, cases, default)
        if default or not self._all_call_cases(cases):
            return self.gen_switch_general(val, cases, default)
        self.expr_to_ax(val)
        brk = self.fresh('swbrk')
        caselbls = [self.fresh('case') for _ in cases]
        for (k, _), cl in zip(cases, caselbls):
            kv = k[1]
            self.emit(0x3D, *w16(kv))  # cmp ax, imm16
            self.emit_jcc(0x74, cl)  # je case
        self.emit_jmp_short(brk)  # default → break
        shared = self.fresh('swshared')
        shared_done = False
        self.break_lbls.append(brk)
        for (k, body), cl in zip(cases, caselbls):
            self.lbl(cl)
            nbytes = self.gen_call(self._switch_case_call(body), cleanup=False)
            if not shared_done:
                self.lbl(shared)  # cases converge here
                if nbytes:
                    self.emit(0x83, 0xC4, nbytes)  # add sp, N (shared)
                self.emit_jmp_short(brk)
                shared_done = True
            else:
                self.emit_jmp_short(shared)
        self.break_lbls.pop()
        self.lbl(brk)

    def _promotable_near_addr(self, a):
        """A near address with a known segment — `&global` / `&local`, or a
        global/local array name (which decays to its address) — promotable to a
        far pointer when the callee parameter is `far *`.  The `(T far *)<addr>`
        cast the promotion delegates to picks the right segment: DS for a global
        (push ds), SS for a local buffer / `&local` (push ss)."""
        if a[0] == 'addr' and nid(a[1]):
            n = a[1][1]
            return (
                n in SYMS and SYMS[n][0] in ('arr', 'arr_w', 'var', 'uvar', 'bvar')
            ) or n in self.locals
        # &local_array[const] — an interior address of a stack buffer
        if a[0] == 'addr' and a[1][0] == 'idx' and nid(a[1][1]) and num(a[1][2]):
            return self.lty(a[1][1]).startswith('arr')
        if nid(a):
            n = a[1]
            return (n in SYMS and SYMS[n][0] in ('arr', 'arr_w')) or (
                n in self.locals and (self.lty(a) or '').startswith('arr')
            )
        return False

    def push_arg(self, e, byte_param=False, arg0=False, far_param=False):
        # A far byte still live in AL from the store that just wrote it: only the
        # zero-extend is needed (FCB_BIT15_CHECK at 0x82C6).
        if byte_param and getattr(self, 'al', None) == ('farb', repr(e)):
            self.emit(0x2A, 0xE4)  # sub ah, ah
            self.emit(0x50)  # push ax
            self.ax = None
            self._ah_zero = True
            return
        # A NEAR pointer local still live in BX (a preceding `*p` deref loaded it
        # there) is pushed straight from the register — `push bx`
        # (INIT_PSP handing `para` on to COMPUTE_MCB_SLOT_COUNT at 0x188F).
        if nid(e) and self.bx == ('nptr', e[1]):
            self.emit(0x53)  # push bx
            self._ah_zero = False
            return
        # A word global whose value is still live in AX — the store that put it
        # there was the previous statement — pushes straight from the register
        # (EDIT_TEMPLATE_PROCESS handing KEY_TYPED_DISPATCH the column it just
        # computed).
        if nid(e) and self.gkind(e) == 'var' and self.ax == e[1]:
            self.emit(0x50)  # push ax
            self._ah_zero = False
            return
        # A far-pointer local whose ES:BX is STILL LIVE (a store through it
        # just happened) is pushed straight from the registers — `push es;
        # push bx` — not re-read from its frame slot (INSTALL_DRIVER handing
        # `rec` to CLOSE_SFT_ENTRY right after setting its refcount).
        if self.locid(e) and pf(self.lty(e)) and self.bx == e[1]:
            # ... from DX:BX while DX still holds the segment the address
            # computation left there, else from ES:BX after a fresh `les`.
            if self.esbx == e[1]:
                self.emit(0x06)  # push es
                self.emit(0x53)  # push bx
                return
        # A bare near address (`&global`/`&local` or an array name) handed to a
        # `far *` parameter: promote it to a far pointer — identical to the
        # explicit `(T far *)<addr>` cast, so the cast is not needed at the call.
        if far_param and self._promotable_near_addr(e):
            return self.push_arg(('cast', 'ptr_far_uchar', e))
        # A numeric literal filling a `unsigned char` parameter of a *pascal*
        # helper: MSC narrows it to a byte in AL and pushes the word (garbage AH)
        # — `mov al,N; push ax` (SHR_FAR_BUF_BY_CL's count).  cdecl callees keep
        # the int-promoted `mov ax,N` even for a uchar param.
        if byte_param and num(e) and self._pascal_call:
            self.emit(0xB0, e[1] & 0xFF)  # mov al, imm8
            self.emit(0x50)  # push ax
            self.al = None
            self._ah_zero = False
            return
        # FP_SEG/FP_OFF(far_var) arg where the word is still live in a register:
        # MSC pushes it straight (`push dx`/`push bx`) rather than re-reading
        # memory — after `far_var = <far ptr>` leaves DX = its seg (`('hi',name)`)
        # and a following `les bx,[far_var]` leaves BX = its offset.
        if e[0] in ('fpseg', 'fpoff') and self.gfar(e[1]):
            name = n11(e)
            if e[0] == 'fpseg' and self.dx == ('hi', name):
                self.emit(0x52)  # push dx
                return
            if e[0] == 'fpoff' and self.bx == name and self.esbx == name:
                self.emit(0x53)  # push bx
                return
            # neither half cached: push the word straight from memory —
            # `push word [g+2]` / `push word [g]` (DOS_FN_44's DRIVER_VEC args)
            addr = SYMS[name][1] + (2 if e[0] == 'fpseg' else 0)
            self.emit(0xFF, 0x36, *w16(addr))
            return
        # FP_SEG/FP_OFF(far_local/param) as an arg → push the seg/off word from
        # the frame (`push word [bp+d+2]` / `push word [bp+d]`) — BUILD_DRIVER_
        # REQUEST forwarding its `driver` far-pointer param to the packet call.
        match e:
            case ('fpseg' | 'fpoff' as half, ('id', pname) as pnode) if (
                pname in self.locals and pf(self.lty(pnode))
            ):
                disp = self.ld(pname) + (2 if half == 'fpseg' else 0)
                self.emit(0xFF, 0x76, disp & 0xFF)  # push word [bp+d]
                return
        # (unsigned char)<call> as an arg: narrow the int result to a byte —
        # `sub ah,ah; push ax` (MSC zero-extends the low byte of the returned AX).
        if ncast(e) and e[1] == 'uchar' and ncall(e[2]):
            self.gen_call(e[2])
            self.push_al0()
            return
        # A near (non-`far`, non-`long`) cast is a byte-level no-op at 16-bit
        # width — unwrap it so the idx/var fast-paths below still apply.  `long`
        # is NOT a no-op (it widens to 4 bytes), handled just below.
        if ncast(e) and not pf(e[1]) and e[1] != 'long':
            return self.push_arg(e[2])
        # (T far *)<far-typed value> is a byte-level no-op (retagging one far
        # pointer as another — `(struct fcb far *)regs`): unwrap and push the
        # inner 4-byte value directly.
        if (
            ncast(e)
            and e[1].startswith('ptr_far_')
            and nid(e[2])
            and self.lty(e[2]).startswith('ptr_far_')
        ):
            # A RETAG of a far local is a far VALUE, so it goes out in the
            # value registers the address computation left — `push dx; push bx`
            # (segment in DX, offset in BX after the `les`).  The un-cast
            # pointer below instead pushes ES:BX.  INSTALL_DRIVER passes the
            # same `rec` both ways, one line apart, and MSC picks differently.
            if self.dx == ('hi', e[2][1]) and self.bx == e[2][1]:
                self.emit(0x52)  # push dx
                self.emit(0x53)  # push bx
                return
            return self.push_arg(e[2])
        # (T far *)&local_buffer[const] → SS:&buf[k]: lea ax,[bp-off+k]; push ss;
        # push ax (DOS_FN_29_PARSE_FILENAME_FCB handing over the 3-byte extension).
        match e:
            case ('cast', ty, ('addr', ('idx', ('id', buf) as bnode, ('num', k)))) if (
                pf(ty) and self.lty(bnode).startswith('arr')
            ):
                self.lea_ax((self.ld(buf) + k) & 0xFF)  # lea ax, [bp-off+k]
                self.push_seg_ax(0x16)
                return
        # (T far *)local_buffer → far pointer SS:&buf[0]: lea ax,[bp-off]; push ss;
        # push ax  (a stack buffer passed by far pointer to a driver/helper).
        if ncast(e) and pf(e[1]) and self.lty(e[2]).startswith('arr'):
            disp = self.ld(e[2][1])
            self.lea_ax(disp)  # lea ax, [bp-off]
            self.push_seg_ax(0x16)
            return
        # (T far *)&local_scalar → far pointer SS:&local: lea ax,[bp-off]; push ss;
        # push ax  (a stack out-param handed to a helper — compute_cluster's cluster).
        match e:
            case ('cast', ty, ('addr', ('id', vname))) if (
                pf(ty) and vname in self.locals
            ):
                self.lea_ax(self.ld(vname))  # lea ax, [bp-off]
                self.push_seg_ax(0x16)
                return
        # (T far *)<ds-global>  →  a DS-relative far pointer: mov ax,&g; push ds;
        # push ax.  Covers `(far*)arr`, `(far*)&g`, and `(far*)&arr[expr]`.
        if ncast(e) and 'far' in e[1]:
            inner = e[2]
            gaddr = None
            if (
                nid(inner)
                and inner[1] in SYMS
                and SYMS[inner[1]][0] in ('arr', 'arr_w', 'var', 'uvar', 'bvar')
            ):
                gaddr = SYMS[inner[1]][1]
            elif inner[0] == 'addr' and nid(inner[1]) and n11(inner) in SYMS:
                gaddr = sa(n11(inner))
            if gaddr is not None:
                self.mvax(gaddr)  # mov ax, &g
                self.push_seg_ax(0x1E)
                return
            # (far)(far_ptr + const) reusing a live ES:BX (a preceding les left
            # ES:BX = the far param OR far_var global): mov ax,bx; mov dx,es;
            # add ax,const; push both (COPY_PROMPT_TEMPLATE's INPUT_FCB_PTR + 2).
            match e[2]:
                # ES:BX already points at this pointer (a preceding les) — reuse
                # the registers: mov ax,bx; mov dx,es; add ax,const
                # (COPY_PROMPT_TEMPLATE's INPUT_FCB_PTR + 2).
                case ('bin', '+', ('id', pname) as pnode, ('num', delta)) if (
                    (pf(self.lty(pnode)) or self.gfar(pnode)) and self.esbx == pname
                ):
                    self.emit(0x8B, 0xC3)  # mov ax, bx
                    self.emit(0x8C, 0xC2)  # mov dx, es
                    n = delta & 0xFFFF
                    if n == 1:  # MSC uses inc for +1 (DOS_FN_10's fcb+1)
                        self.emit(0x40)  # inc ax
                    else:
                        self.emit(0x05, *w16(n))  # add ax, const
                    self.push_dxax()
                    return
                # ES:BX NOT live — read the pointer from its frame slot instead
                # (DOS_FN_4E's `(far)(rec+0x26)` after a call spilled ES:BX).
                # A zero const skips the `add`.
                case ('bin', '+', ('id', pname), ('num', delta)) if (
                    pname in self.locals and pf(self.lt(pname))
                ):
                    off = self.ld(pname)
                    self.emit(0x8B, 0x46, off)  # mov ax, [bp+off]
                    self.emit(0x8B, 0x56, off + 2)  # mov dx, [bp+off+2]
                    if delta == 1:
                        self.emit(0x40)  # inc ax  (DELETE_FCB's `path + 1`)
                    elif delta:
                        self.emit(0x05, *w16(delta & 0xFFFF))  # add ax, const
                    self.push_dxax()
                    return
            # (far)(far_var + <scaled term>) — a table-ENTRY address as an arg
            # (`&DPB_TABLE[drive]` lowers to DPB_TABLE + 0x51*drive): build
            # offset:segment in AX:DX via fv_axdx_sum, push both
            # (COPY_DPB_AND_LOOKUP's mem_copy_far src).  Gated on a `*` term so
            # the plain far_var+const shapes keep their existing paths.
            if (
                nbin(e[2])
                and e[2][1] == '+'
                and any(nbin(t) and t[1] == '*' for t in (e[2][2], e[2][3]))
                and self.fv_axdx_sum(e[2])
            ):
                self.push_dxax()
                return
            # (far*)&arr[expr]  →  expr→AX; add ax,&arr; push ds; push ax
            if (
                inner[0] == 'addr'
                and inner[1][0] == 'idx'
                and nid(n11(inner))
                and n11(inner[1]) in SYMS
            ):
                a = sa(n11(inner[1]))
                self.expr_to_ax(n12(inner))  # index → AX
                self.emit(0x05, *w16(a))  # add ax, &arr
                self.push_seg_ax(0x1E)
                return
        # far_ptr_local + reg_var as a far arg: offset word to AX (then += reg),
        # segment to DX — read from ES instead of the frame when ES still holds
        # this pointer's segment from a preceding les (PARSE_PATH_WITH_DRIVE's
        # mem_copy_far dst right after the `out[len++] = '\\'` store).
        match e:
            case ('bin', '+', ('id', pname), ('id', _) as reg) if (
                pname in self.locals and pf(self.lt(pname)) and self.rvid(reg)
            ):
                off = self.ld(pname)
                self.ldax(off)  # mov ax, [bp+off]
                if self.esbx == pname:
                    self.emit(0x8C, 0xC2)  # mov dx, es
                else:
                    self.emit(0x8B, 0x56, (off + 2) & 0xFF)  # mov dx, [bp+off+2]
                self.emit(0x03, sd(0xC6, self.rv(reg)))  # add ax, si/di
                self.push_dxax()
                self.zad()
                return
        # Immediate arg → `mov ax,imm; push ax` (the 8086 has no push-imm).  Reuse
        # AX when it already holds this immediate so consecutive equal args share
        # one load — MSC's `mov ax,3; push ax; push ax` for lookup_error_msg(…,3,3).
        if num(e) and not self._pascal_call:
            n = e[1] & 0xFFFF
            if self.ax != ('imm', n):
                self.mvax0(n)
                self.ax = ('imm', n)
            self.emit(0x50)  # push ax
            self._ah_zero = False  # MSC re-zero-extends a following byte arg
            return
        # `0` to a pascal helper zeroes AX with `sub ax,ax` (not `xor`)
        if z0(e) and self._pascal_call:
            self.emit(0x2B, 0xC0)  # sub ax, ax
            self.emit(0x50)  # push ax
            self.ax = None
            self._ah_zero = True
            return
        # *bufp where bufp is a near pointer to a far pointer: push the far
        # pointer it points to (seg word, then off word).
        if nderef(e) and self.lty(e[1]).startswith('ptr_ptr_far'):
            disp = self.ldi(e)
            self.ldbx(disp)  # mov bx, [bp+disp]
            self.emit(0xFF, 0x77, 0x02)  # push word [bx+2]
            self.emit(0xFF, 0x37)  # push word [bx]
            self.bx = None
            return
        # *(T far * far *)(far_ptr + const) — a far pointer stored in far memory:
        # les the base, then push its seg word [es:bx+d+2] and off word [es:bx+d].
        if nderef(e) and ncast(e[1]) and 'ptr_far_ptr_far' in n11(e):
            fl = self.far_lvalue(('deref', ('cast', 'ptr_far_uint', n12(e))))
            if fl:
                disp = self.les_fl(fl)
                self.e26(0xFF, 0x77, disp + 2)  # push word[es:bx+d+2]
                if disp:
                    self.e26(0xFF, 0x77, disp)  # push word[es:bx+d]
                else:
                    self.e26(0xFF, 0x37)  # push word[es:bx]
                self.bx = self.esbx = None
                self._ah_zero = False
                return
        # *p where p is a near `int *`/`uint *` → mov bx,[bp+disp]; push word [bx]
        if nderef(e) and self.lty(e[1]) in ('ptr_int', 'ptr_uint'):
            self.ensure_bx(n11(e))
            self.emit(0xFF, 0x37)  # push word [bx]
            return
        # near-pointer deref arg: *(long*)(p+d) pushes [bx+d+2] then [bx+d];
        # *(uint*)(p+d) pushes [bx+d].  BX is loaded once via ensure_bx and
        # reused across the call's arg pushes (matches MSC's single `mov bx`).
        nl = self.near_lvalue(e)
        if nl:
            base, disp, kind = nl
            self.ensure_bx(base)
            if kind == 'long':
                self._push_bx_word(disp + 2)  # high word
            self._push_bx_word(disp)  # low word / the word
            return
        # local-struct word member arg: push word [bp+d] straight
        # (DOS_FN_44's lookup_default_error(pkt.i_status, 2))
        if nderef(e) and self.arr_off(e) and 'char' not in n11(e):
            d = (self.ld(n12(e)[2][1]) + n12(e)[3][1]) & 0xFF
            self.emit(0xFF, 0x76, d)  # push word [bp+d]
            return
        # (long)(16-bit lvalue) arg: zero-extend in place — push 0 (high word),
        # then push the value's memory word directly (low).  Matches MSC widening
        # a 16-bit value to a long argument without routing it through AX.
        if ncast(e) and e[1] == 'long':
            inner = e[2]
            fl = self.far_lvalue(inner)
            lo = None
            if fl and fl[2] == 'word' and not isinstance(fl[0], tuple):
                self.emit_les(fl[0])
                m = (0x40 if fl[1] else 0x00) | 0x30 | 0x07
                lo = (0x26, 0xFF, m) + ((fl[1] & 0xFF,) if fl[1] else ())
            elif wint(self.lty(inner)):
                d = self.ld(inner[1])
                lo = (0xFF, 0x76, d & 0xFF)
            elif self.gvw(inner):
                a = SYMS[inner[1]][1]
                lo = (0xFF, 0x36, *w16(a))
            if lo:
                # MSC zeroes the high word with `sub ax,ax` here, not `xor` —
                # same as the `(long)0` argument path just below.
                self.emit(0x2B, 0xC0)  # sub ax, ax (high = 0)
                self.emit(0x50)  # push ax
                self.emit(*lo)  # push word [low]
                self.ax = None
                self.axdx_var = None  # AX clobbered; AX:DX no longer a pair
                self._ah_zero = True  # AX (hence AH) was just zeroed
                return
            # (long)0 argument: one zeroed AX pushed twice (high then low) —
            # `sub ax,ax; push ax; push ax` (invalidate_cached_fcb's 0L).  MSC
            # still re-zeroes AH for a following byte arg, so _ah_zero stays off.
            if num(inner) and inner[1] == 0:
                self.emit(0x2B, 0xC0)  # sub ax, ax
                self.emit(0x50)  # push ax (high)
                self.emit(0x50)  # push ax (low)
                self.ax = None
                self.axdx_var = None
                self._ah_zero = False
                return
        # a long-valued expression (not a simple id, handled below): push DX:AX
        # far-pointer param + const → push the far pointer with its OFFSET advanced
        # (segment unchanged): mov ax,[bp+off]; mov dx,[bp+off+2]; inc/add ax; push
        # dx; push ax  (`fcb + 1` as a far arg — NOT a 32-bit add).  A byte-no-op
        # far cast of the base is unwrapped (`(unsigned char far *)fcb + 1`).
        _fp_base = e[2] if nbin(e) and e[1] == '+' else None
        if _fp_base is not None and ncast(_fp_base) and pf(_fp_base[1]) \
                and nid(_fp_base[2]) and pf(self.lty(_fp_base[2])):
            _fp_base = _fp_base[2]
        if (
            nbin(e)
            and e[1] == '+'
            and _fp_base is not None
            and nid(_fp_base)
            and _fp_base[1] in self.locals
            and pf(self.lty(_fp_base))
            and num(e[3])
        ):
            disp = self.ld(_fp_base[1])
            self.ldax(disp)  # mov ax,[bp+off]
            self.emit(0x8B, 0x56, disp + 2)  # mov dx,[bp+off+2]
            n = e[3][1] & 0xFFFF
            if n == 1:
                self.emit(0x40)  # inc ax
            else:
                self.emit(0x05, *w16(n))  # add ax, n
            self.push_dxax()
            return
        if e[0] in ('bin', 'cast') and self._is_long_expr(e):
            self.gen_long(e)
            self.push_dxax()
            return
        # far-pointer-returning call as an argument: push DX:AX (seg then off)
        if ncall(e) and self.gkind(e[1]) == 'far_func':
            self.gen_call(e)
            self.emit(0x52)  # push dx (seg)
            self.emit(0x50)  # push ax (off)
            self._ah_zero = False
            return
        if self.gkind(e) == 'var':
            addr = SYMS[e[1]][1]
            self.emit(0xFF, 0x36, *w16(addr))
            return
        # local_array[idx] byte arg → zero-extend the byte and push (mov al via
        # gen_index; sub ah,ah; push ax) — `is_path_delimiter(buf[i])`.
        match e:
            case ('idx', ('id', arr), _) if (
                arr in self.locals and str(self.lt(arr)).startswith('arr')
            ):
                self.gen_index(e)  # al = buf[idx]
                self.push_al()
                return
        # far word lvalue → push word [es:bx+disp]
        _fw = self.far_lvalue(e)
        if _fw and _fw[2] == 'word':
            modrm, dbytes = self.far_rm(_fw[0], _fw[1])
            self.e26(0xFF, modrm | 0x30, *dbytes)  # /6 (push) word [es:bx…]
            return
        # far LONG lvalue → push its two words straight from memory, high then low
        # (`push word[es:bx+d+2]; push word[es:bx+d]`) — DOS_FN_23's file-size arg
        # to the divmod32 record-count division.
        if _fw and _fw[2] == 'long':
            disp = self.les_fl(_fw)
            self.e26(0xFF, mod8(disp + 2) | 0x30 | 0x07, *d8(disp + 2))  # push hi
            self.e26(0xFF, mod8(disp) | 0x30 | 0x07, *d8(disp))  # push lo
            return
        # far byte arg → zero-extend and push; reuse AL when it still holds this
        # value (e.g. `g = fcb[d]; f(fcb[d])`): skip the re-read.
        if _fw and _fw[2] == 'byte':
            if self.al != ('rhs', e):
                disp = self.les_fl(_fw)
                self.e26(0x8A, mod8(disp) | 0x07, *d8(disp))  # mov al,[es:bx+d]
            self.push_al()
            return
        # byte scalar global (uchar) → zero-extend to a word and push.  Skip the
        # `sub ah,ah` when a prior zero-extend in this arg list already cleared AH.
        if self.gkind(e) == 'bvar':
            addr = SYMS[e[1]][1]
            self.emit(0xA0, *w16(addr))  # mov al, [a]
            self.push_al()
            return
        # far-pointer global: push seg word then off word, or reuse AX:DX if
        # they still hold this value (e.g. right after `g = far_fn(...)`).
        if self.gkind(e) in ('far_var', 'long_var'):
            addr = SYMS[e[1]][1]
            if self.axdx_var == e[1]:
                self.emit(0x52)  # push dx (seg/hi)
                self.emit(0x50)  # push ax (off/lo)
            else:
                self.emit(0xFF, 0x36, *w16(addr + 2))
                self.emit(0xFF, 0x36, *w16(addr))
            return
        if self.rvid(e):
            self.emit(sd(0x56, self.rv(e)))  # push si/di
            return
        if self.locid(e):
            disp, ty = self.lvar(e[1])
            if ty == 'long' or pf(ty):
                # reuse AX:DX only while BOTH still hold this 4-byte local
                # (`self.ax == ('low', e[1])`): right after `g = far_fn(…)` the
                # push is immediate.  An intervening `mov ax,imm` (a sibling call
                # arg) clears the AX tag, so the granular path below reuses only
                # DX (seg) and reads the offset from the slot — dos_fn_4f's
                # `rec = SDA_DTA; mem_copy_far(rec, (far)&G, 0x2B)`.
                if self.axdx_var == e[1] and self.ax == ('low', e[1]):
                    self.emit(0x52)  # push dx
                    self.emit(0x50)  # push ax
                    return
            if ty in ('long', 'ulong'):
                # high word: reuse DX if still cached, else from memory
                if self.dx == ('hi', e[1]):
                    self.emit(0x52)  # push dx (hi)
                else:
                    self.emit(0xFF, 0x76, disp + 2)  # push [bp+disp+2] (hi)
                self.emit(0xFF, 0x76, disp)  # push [bp+disp] (lo)
                return
            if pf(ty):
                # far pointer: push segment word then offset word. Reuse ES for
                # the segment when it still points here, and AX for the offset.
                if self.esbx == e[1]:
                    self.emit(0x06)  # push es (segment, still live)
                elif self.ax == ('fpseg', e[1]):
                    self.emit(0x50)  # push ax (segment, still live)
                elif self.dx == ('hi', e[1]) or (
                    self.dx_alias
                    and self.dx == ('hi', self.dx_alias[0])
                    and self.dx_alias[1] == e[1]
                ):
                    self.emit(0x52)  # push dx (segment, still live)
                else:
                    self.emit(0xFF, 0x76, disp + 2)  # push [bp+disp+2] (seg)
                if self.bx == e[1]:
                    self.emit(0x53)  # push bx (offset, still live)
                    self.ax = None
                    return
                if self.ax == ('fpoff', e[1]):
                    self.emit(0x50)  # push ax (offset)
                else:
                    self.emit(0xFF, 0x76, disp)  # push [bp+disp] (off)
                self.ax = None
                return
            if ty == 'uchar':
                # default argument promotion: zero-extend byte to word.  Reuse AX
                # if it already holds the zero-extended value, else AL if it holds
                # the byte, else load from the frame.
                if self.ax == ('zx', e[1]):
                    self.emit(0x50)  # push ax (zero-extended, live)
                    self.zaa()
                    self._ah_zero = True
                    return
                if self.al != e[1]:
                    self.ldal(disp)  # mov al, [bp+disp] (AH untouched)
                    # The LEFTMOST arg (pushed last) is where a cross-jumped
                    # shared call tail converges — MSC re-zero-extends AH there
                    # (join semantics), so drop a straight-line known-0 AH.  A
                    # mid-list byte arg keeps AH=0 from the prior widened push
                    # (INVOKE_DOS_ERROR_PROMPT's `mode` after `unit`).
                    if arg0:
                        self._ah_zero = False
                self.push_al()
                return
            # int/uint local: reuse AX when it still holds this value (MSC keeps a
            # just-computed value in AX and pushes it directly), else from memory.
            if self.ax == e[1]:
                self.emit(0x50)  # push ax
                self._ah_zero = False
                return
            self.emit(0xFF, 0x76, disp)
            return
        # Direct push of arr_w[local_var] — saves the AX round-trip.
        if (
            e[0] == 'idx'
            and self.gkind(e[1]) == 'arr_w'
            and nid(e[2])
            and e[2][1] in self.locals
        ):
            addr = sa(n11(e))
            idx_disp = self.ld(e[2][1])
            self.ldbx(idx_disp)  # mov bx, [bp+disp]
            self.emit(0xD1, 0xE3)  # shl bx, 1
            self.emit(0xFF, 0xB7, *w16(addr))  # push word [bx+addr]
            self.bx = None
            return
        self.expr_to_ax(e)
        if byte_param and ncall(e):
            # A call result filling a `unsigned char` parameter: MSC narrows AX
            # to its low byte by clearing AH, then pushes the word
            # (`get_drive_type(uppercase_and_check_drive(&path))`, 0x600A).
            self.emit(0x2A, 0xE4)  # sub ah, ah
            self.emit(0x50)
            self.ax = None
            self._ah_zero = True
            return
        self.emit(0x50)
        self.ax = None
        self._ah_zero = False

    def gen_postinc(self, lvalue):
        # (*p)++ where p is a near `int *`/`uint *` → mov bx,[p]; inc word [bx]
        if nderef(lvalue) and self.lty(lvalue[1]) in ('ptr_int', 'ptr_uint'):
            self.ensure_bx(n11(lvalue))
            self.emit(0xFF, 0x07)  # inc word [bx]
            return
        # (*(T far *)(p+d))++ → les bx,[p]; inc word/byte [es:bx+d]
        far = self.far_lvalue(lvalue)
        if far:
            base, disp, kind = far
            self.emit_les(base)
            self.e26(0xFE if kind == 'byte' else 0xFF, mod8(disp) | 0x07, *d8(disp))
            return
        # FP_OFF(far_local)++ → inc word [bp+disp] (the offset word in place —
        # DOS_FN_29_PARSE_FILENAME_FCB walking the spec cursor).
        if lvalue[0] in ('fpoff', 'fpseg') and pf(self.lty(lvalue[1])):
            disp = self.ldi(lvalue) + (2 if lvalue[0] == 'fpseg' else 0)
            self.emit(0xFF, 0x46, disp & 0xFF)  # inc word [bp+disp]
            return
        if not nid(lvalue):
            raise NotImplementedError
        name = lvalue[1]
        if name in self.locals:
            if self.is_reg_var(name):
                self.emit(sd(0x46, self.regvars[name]))  # inc si/di
                self._regvar_zero[self.regvars[name]] = False
                return
            disp, ty = self.lvar(name)
            if ty == 'long':
                self.emit(0x83, 0x46, disp, 0x01)  # add word[bp+d],1
                self.emit(0x83, 0x56, disp + 2, 0x00)  # adc word[bp+d+2],0
            elif ty in ('uchar', 'char'):
                self.emit(0xFE, 0x46, disp)  # inc byte [bp+d]
            else:
                self.emit(0xFF, 0x46, disp)  # inc word [bp+d]
            self.invalidate_mem(name)
            if self.esbx == name:  # far ptr offset changed
                self.esbx = None
            return
        if gsym(name, 'var'):
            addr = sa(name)
            self.emit(0xFF, 0x06, *w16(addr))  # inc word [addr]
            # A BX cached as this var's index is now stale (value changed).
            if self.bx == ('idxvar', name):
                self.bx = None
            return
        if gsym(name, 'long_var'):
            addr = sa(name)
            self.emit(0x83, 0x06, *w16(addr), 0x01)  # add word[addr],1
            self.emit(0x83, 0x16, *w16(addr + 2), 0x00)  # adc word[addr+2],0
            return
        if gsym(name, 'bvar'):
            self.emit(0xFE, 0x06, *w16(sa(name)))  # inc byte [addr]
            self.al = None
            return
        raise NameError(name)

    def gen_postdec(self, lvalue):
        # Far-pointer field decrement:  (*(int far *)(FAR_VAR + disp))--
        far = self.far_lvalue(lvalue)
        if far:
            fv, disp, kind = far
            self.emit_les(fv)
            modrm = mod8(disp) | 0x08 | 0x07  # /1 [bx(+disp8)]
            self.e26(0xFF, modrm, *d8(disp))
            return
        if not nid(lvalue):
            raise NotImplementedError
        name = lvalue[1]
        if name in self.locals and self.is_reg_var(name):
            self.emit(sd(0x4E, self.regvars[name]))  # dec si/di
            return
        if name in self.locals:
            disp = self.ld(name)
            if self.lt(name) in ('uchar', 'char'):
                self.emit(0xFE, 0x4E, disp)  # dec byte [bp+disp]
            else:
                self.emit(0xFF, 0x4E, disp)  # dec word [bp+disp]
            self.invalidate_mem(name)
            return
        if gsym(name, 'var'):
            addr = sa(name)
            self.emit(0xFF, 0x0E, *w16(addr))  # dec word [addr]
            return
        if gsym(name, 'bvar'):
            addr = sa(name)
            self.emit(0xFE, 0x0E, *w16(addr))  # dec byte [addr]
            return
        raise NameError(name)

    # ---- expressions ----
    def expr_to_ax(self, e):
        # FP_SEG of a far pointer whose high word is STILL LIVE in DX from the
        # store that just wrote it — `mov ax,dx`, no reload
        # (FILL_DEVICE_FCB_REQUEST copying the device header's segment, 0x8B08).
        if e[0] == 'fpseg' and nid(e[1]) and self.dx == ('hi', e[1][1]):
            self.emit(0x8B, 0xC2)  # mov ax, dx
            self.ax = None
            return
        # A local still live in BX because it was just used as an array index
        # (`HIST_BUF[template] = 0Dh`) is fetched with `mov ax,bx`.
        if nid(e) and self.bx == ('idxloc', e[1]):
            self.emit(0x8B, 0xC3)  # mov ax, bx
            self.ax = e[1]
            return
        # A far byte already zero-extended into AX by a preceding compare on the
        # SAME lvalue is reused rather than re-read (EDIT_TEMPLATE_PROCESS
        # clamping ECHO_CURSOR to the value it just compared).
        if getattr(self, 'ax', None) == ('zxfar', repr(e)):
            return
        # A local still live in DX (right after `local = expr % div`) is fetched
        # with `mov ax, dx` instead of a reload from its stack slot.
        if nid(e) and self.dx == ('val16', e[1]):
            self.emit(0x8B, 0xC2)  # mov ax, dx
            self.ax = e[1]
            return
        # A word global still live in SI (loaded as an index by a preceding
        # fv_gword_idx compare on the same fall-through) → `mov ax,si` instead of
        # reloading (FIND_PREV_CHAR_MATCH's `ECHO_CURSOR = SCAN_POS`).
        if nid(e) and self.si == ('gword', e[1]):
            self.emit(0x8B, 0xC6)  # mov ax, si
            self.ax = None
            return
        # The high/low word of a long local via `((unsigned int *)&L)[k]`.  When
        # the long is still live in AX:DX (just stored), the HIGH word reuses DX
        # (`mov ax,dx`); otherwise (and for the low word) reload the word from the
        # frame.  DOS_FN_42 returns the new seek position in DX:AX this way.
        if (
            e[0] == 'idx'
            and ncast(e[1])
            and e[1][1] == 'ptr_uint'
            and e[1][2][0] == 'addr'
            and nid(e[1][2][1])
            and e[1][2][1][1] in self.locals
            and self.lt(e[1][2][1][1]) == 'long'
            and num(e[2])
        ):
            L, k = e[1][2][1][1], e[2][1]
            if k == 1 and self.axdx_var == L:
                self.emit(0x8B, 0xC2)  # mov ax, dx (high word still live)
            else:
                self.emit(0x8B, 0x46, (self.ld(L) + 2 * k) & 0xFF)  # mov ax,[bp+d]
            self.ax = self.axdx_var = None
            return
        # Evaluating overwrites AX — but a call pushes its args (which may reuse
        # AX:DX) before clobbering, so defer the clear to gen_call in that case.
        # Also keep the AX:DX pair when this expression's leftmost long leaf IS
        # the cached value: it will be reused in place (MSC keeps a just-stored
        # long live, e.g. `EOF_ANCHOR = …; SECTOR_INDEX = ((EOF_ANCHOR-1)>>n)+1`).
        if not ncall(e) and self._leftmost_long_id(e) != self.axdx_var:
            self.axdx_var = None
        op = e[0]
        if op == 'ternary':
            # `cond ? a : b` in a word context: both arms materialise into AX,
            # meeting at a shared label (MSC's branch-merged `mov ax,…`).
            els, end = self.fresh('tern_els'), self.fresh('tern_end')
            self.cond_jump(e[1], els, False)  # if !cond → else
            self.expr_to_ax(e[2])
            self.emit_jmp_short(end)
            self.lbl(els)
            self.expr_to_ax(e[3])
            self.lbl(end)
            self.ax = None
            return
        if op == 'cast' and 'far' not in e[1]:
            # (unsigned char)<call> in a word context: narrow the returned AX
            # to its low byte — `sub ah,ah` (DOS_FN_44's fcb_random_block_io
            # result).  Other near casts are byte-level no-ops.
            if e[1] == 'uchar' and ncall(e[2]):
                self.gen_call(e[2])
                self.zaa()
                self.emit(0x2A, 0xE4)  # sub ah, ah
                self._ah_zero = True
                return
            return self.expr_to_ax(e[2])
        # *(T *)(local_array + const) → word at [bp-off+const]  (byte zero-extends)
        if op == 'deref' and self.arr_off(e):
            disp = self.ld(n12(e)[2][1])
            d = (disp + n12(e)[3][1]) & 0xFF
            if 'char' in n11(e):
                self.ldal(d)  # mov al, [bp+d]
                self.emit(0x2A, 0xE4)  # sub ah, ah
            else:
                self.ldax(d)  # mov ax, [bp+d]
            self.zaa()
            return
        far = self.far_lvalue(e)
        if far:
            fv, disp, kind = far
            # The byte may still be live in AL from a preceding `g = <this far
            # byte>` — just zero-extend it in place (no les/reload), so
            # `g = fcb[1]; f(fcb[1] + 1)` reuses AL (COPY_PROMPT_TEMPLATE).
            if kind == 'byte' and self.al == ('rhs', e):
                self.emit(0x2A, 0xE4)  # sub ah, ah
                self.zaa()
                self._ah_zero = True
                return
            # si-indexed single-use far_var entry: `index → SI; les bx,[var];
            # [es:bx+si+disp]` (vs the bx-folded ('idx') emit_les for multi-use).
            modrm, dbytes = self.far_rm(fv, disp)
            if kind == 'word':
                self.e26(0x8B, modrm, *dbytes)
            else:
                self.e26(0x8A, modrm, *dbytes)
                # zero-extend byte → int; elide `sub ah,ah` when AH is already
                # known 0 (e.g. a preceding `x = far_byte` just cleared it —
                # dos_fn_46's `src = fcb[2]; dst = fcb[4]`).
                if not self._ah_zero:
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                self._ah_zero = True
            self.zaa()
            return
        if op == 'num':
            n = e[1] & 0xFFFF
            # AX already holds this immediate (a just-pushed equal arg) → reuse it,
            # matching push_arg's `('imm', n)` tag (lookup(2,2,3,3)'s code push).
            if self.ax == ('imm', n) and n != 0:
                return
            if e[1] == 0:
                if self.dx == 0:
                    self.emit(0x8B, 0xC2)  # mov ax, dx (DX already 0)
                else:
                    self.emit(0x33, 0xC0)  # xor ax, ax
                self.ax = None
            else:
                self.emit(0xB8, e[1], (e[1] >> 8))
                self.ax = ('imm', n)
            return
        if op == 'call':
            self.gen_call(e)
            # a uchar return is in AL with garbage AH — zero-extend for int context
            if nid(e[1]) and n11(e) in UCHAR_FUNCS:
                self.emit(0x2A, 0xE4)  # sub ah, ah
                self.zaa()
            return
        if op == 'id':
            name = e[1]
            if name in self.locals:
                if self.is_reg_var(name):
                    self.emit(0x8B, sd(0xC6, self.regvars[name]))  # mov ax,si/di
                    self.ax = None
                    return
                if self.ax == name:
                    return
                disp = self.ld(name)
                if self.lt(name) == 'uchar':
                    if self.al != name:
                        self.ldal(disp)  # mov al, [bp+d]
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                    self.al = name
                    self.ax = None
                    return
                self.ldax(disp)
                self.ax = name
                return
            if name in SYMS:
                kind = SYMS[name][0]
                addr = sa(name)
                if kind == 'var':
                    if self.ax == name:  # AX still holds it (just assigned/compared)
                        return
                    self.ldaxm(addr)
                    self.ax = name
                    return
                if kind in ('arr', 'arr_w'):
                    # array name → address-as-constant (decay to pointer)
                    self.mvax(addr)
                    self.ax = None
                    return
        if op == 'addr':
            # &global → its address as a constant (decay to pointer)
            inner = e[1]
            if nid(inner) and inner[1] in SYMS:
                a = SYMS[inner[1]][1]
                self.mvax(a)  # mov ax, &global
                self.ax = None
                return
            # &local / &param → lea ax, [bp+disp]
            if self.locid(inner):
                disp = self.ld(inner[1])
                self.lea_ax(disp)  # lea ax, [bp+disp]
                self.ax = None
                return
            ni('addr', e)
        if op == 'neg':
            self.expr_to_ax(e[1])
            self.emit(0xF7, 0xD8)  # neg ax
            self.ax = None
            return
        if op == 'bin':
            return self.gen_bin(e[1], e[2], e[3])
        if op == 'idx':
            self.gen_index(e)
            # A byte-array element loads into AL; zero-extend to AX for an
            # int-context value (e.g. `return LINE_BUF[i];`).  Elide `sub ah,ah`
            # when AH is already known 0 (reused across a loop back-edge).
            if self.gkind(e[1]) == 'arr':
                if not self._ah_zero:
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                self._ah_zero = True
            return
        # FP_OFF/FP_SEG of a far-pointer local → its offset/segment word.  Reuse
        # AX when it still holds this offset (just assigned), else load from mem.
        if op in ('fpoff', 'fpseg') and pf(self.lty(e[1])):
            name = n11(e)
            if op == 'fpoff' and self.ax == ('fpoff', name):
                return
            disp = self.ld(name)
            if op == 'fpseg':
                disp = (disp + 2) & 0xFF
            self.ldax(disp)  # mov ax, [bp+disp]
            self.ax = ('fpoff', name) if op == 'fpoff' else None
            return
        # FP_OFF/FP_SEG of a far_var global → its offset/segment word in memory
        if op in ('fpoff', 'fpseg') and self.gfar(e[1]):
            a = sa(n11(e)) + (2 if op == 'fpseg' else 0)
            self.ldaxm(a)  # mov ax, [a]
            self.ax = None
            return
        # long global in a 16-bit context → its low word: mov ax, [addr]
        if self.gkind(e) == 'long_var':
            a = SYMS[e[1]][1]
            self.ldaxm(a)  # mov ax, [a]
            self.ax = None
            return
        # *p where p is a near int/uint pointer local → mov bx,[bp+d]; mov ax,[bx].
        # Cache BX (key ('nptr',p)) so a following `*p += ...` reuses it (no reload).
        if op == 'deref' and self.lty(e[1]) in ('ptr_int', 'ptr_uint'):
            disp = self.ldi(e)
            self.ldbx(disp)  # mov bx, [bp+disp]
            self.emit(0x8B, 0x07)  # mov ax, [bx]
            self.ax = None
            self.bx = ('nptr', n11(e))
            return
        # byte global in an int context → mov al,[addr]; sub ah,ah (zero-extend).
        # Cache it in AX (key ('bv',name)) so an immediately-following reuse — e.g.
        # `if (x < G) y = G;` where the compare just loaded G — skips the reload.
        if self.gkind(e) == 'bvar':
            if self.ax == ('bv', e[1]):
                return
            # the byte is still live in AL (a preceding `g = CNT` / far store of
            # CNT) — just zero-extend it, no reload (`P[1] = CNT; f(CNT + 1)`).
            if self.al == e[1]:
                if not self._ah_zero:
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                self._ah_zero = True
                self.al = None
                self.ax = ('bv', e[1])
                return
            a = SYMS[e[1]][1]
            self.emit(0xA0, *w16(a))  # mov al, [a]
            # zero-extend byte → int; elide `sub ah,ah` when AH is already known 0
            # (a preceding widen left it cleared, e.g. across a loop-exit test —
            # FLUSH_INPUT_TYPED reuses the loop condition's AH=0).
            if not self._ah_zero:
                self.emit(0x2A, 0xE4)  # sub ah, ah
            self._ah_zero = True
            self.al = None
            self.ax = ('bv', e[1])
            return
        ni(e)

    def expr_to_al(self, e):
        if not ncall(e):  # see expr_to_ax: defer for calls
            self.axdx_var = None
            # an AL write invalidates a full-AX offset/low-word tag
            if isinstance(self.ax, tuple) and self.ax[0] in ('low', 'fpoff'):
                self.ax = None
        op = e[0]
        # `g++` as a VALUE for a byte global: read it, bump it in memory, and the
        # OLD value stays in AL — `mov al,[g]; inc byte [g]`
        # (PARSE_FILENAME_TO_FCB's `fcb->f_drvcode = WORK_FCB_DRIVE++`, 0x4C9A).
        if e[0] == 'postinc' and nid(e[1]) and self.gkind(e[1]) == 'bvar':
            a = sa(e[1][1])
            self.emit(0xA0, *w16(a))  # mov al, [g]
            self.emit(0xFE, 0x06, *w16(a))  # inc byte [g]
            self.al = self.ax = None
            return
        # *far_local++ : the `les` captures the OLD pointer, the offset word is
        # bumped in memory, and the deref then reads through the stale BX
        # (`les bx,[p]; inc word [p]; mov al,[es:bx]` — JOIN's path-copy loop).
        if (
            nderef(e)
            and e[1][0] == 'postinc'
            and nid(e[1][1])
            and e[1][1][1] in self.locals
            and pf(self.lty(e[1][1]))
        ):
            name = e[1][1][1]
            self.emit_les(name)
            self.emit(0xFF, 0x46, self.ld(name))  # inc word [bp+off]
            self.e26(0x8A, 0x07)  # mov al, [es:bx]
            self.invalidate_mem(name)
            self.esbx = self.bx = None
            self.al = self.ax = None
            return
        if op == 'ternary':
            # `cond ? a : b` in a byte context: both arms materialise into AL,
            # meeting at a shared label — MSC's `mov al,A / jmp / mov al,B`
            # merged store (INVOKE_DOS_ERROR_PROMPT's `mode = attr&80 ? FF : 5`).
            els, end = self.fresh('tern_els'), self.fresh('tern_end')
            self.cond_jump(e[1], els, False)  # if !cond → else
            self.expr_to_al(e[2])
            self.emit_jmp_short(end)
            # Unreachable point: MSC dumps pending out-of-line loop bodies here,
            # BETWEEN the ternary's arms (RENAME_FCB's pre-scan body at 9933).
            self._flush_deferred_whiles()
            self.lbl(els)
            self.expr_to_al(e[3])
            self.lbl(end)
            self.al = None
            return
        if op == 'cast' and 'far' not in e[1]:
            return self.expr_to_al(e[2])
        if op == 'call':
            self.gen_call(e)  # result byte lands in AL (low of AX)
            return
        fir = self.far_indexed_reg(e)
        if fir:
            name, reg = fir
            self.emit_les(name)
            self.e26(0x8A, sd(0x00, reg))  # mov al,[es:bx+si/di]
            self.al = None
            return
        far = self.far_lvalue(e)
        if far:
            disp = self.les_fl(far)
            modrm = mod8(disp) | 0x07  # al, [bx(+disp8)]
            self.e26(0x8A, modrm, *d8(disp))
            self.al = None
            return
        if op == 'id' and self.is_reg_var(e[1]):
            # a reg-var read as a byte → `mov ax,si/di` (can't `mov al,reg`), the
            # low byte is then AL (PARSE_FILESPEC's `namelen = si`).
            self.emit(0x8B, sd(0xC6, self.rv(e)))  # mov ax, si/di
            self.zaa()
            return
        if op == 'id' and e[1] in self.locals:
            if self.al == e[1]:
                return
            disp = self.ld(e[1])
            self.ldal(disp)
            self.al = e[1]
            return
        if op == 'idx':
            return self.gen_index(e)
        if op == 'num':
            if e[1] & 0xFF == 0:
                self.emit(0x32, 0xC0)  # xor al, al (byte 0 value; DOS_FN_16's
                # `(...) ? 1 : 0` else-arm)
            else:
                self.emit(0xB0, e[1] & 0xFF)  # mov al, imm
            self.al = None
            return
        # uchar_local - imm  →  (load al), sub al, imm8
        if (
            op == 'bin'
            and e[1] == '-'
            and num(e[3])
            and nid(e[2])
            and e[2][1] in self.locals
        ):
            self.expr_to_al(e[2])
            self.emit(0x2C, e[3][1])  # sub al, imm8
            self.al = None
            return
        # <byte local> |/&/^ imm  →  (load al), or/and/xor al, imm8 (byte context:
        # a word local's low byte is loaded, GET_SET_ATTRS' `attr | 0x10`).
        if (
            op == 'bin'
            and e[1] in ('|', '&', '^')
            and num(e[3])
            and nid(e[2])
            and e[2][1] in self.locals
        ):
            self.expr_to_al(e[2])
            self.emit({'|': 0x0C, '&': 0x24, '^': 0x34}[e[1]], e[3][1] & 0xFF)
            self.al = None
            return
        # const - uchar_local  →  mov al,const; sub al,[bp+disp]  (`3 - result`)
        if (
            op == 'bin'
            and e[1] == '-'
            and num(e[2])
            and nid(e[3])
            and e[3][1] in self.locals
        ):
            self.emit(0xB0, e[2][1] & 0xFF)  # mov al, const
            self.emit(0x2A, 0x46, self.ld(e[3][1]))  # sub al, [bp+disp]
            self.al = None
            return
        # byte AND: <byte expr> & imm  →  (al = expr); and al, imm8
        if op == 'bin' and e[1] == '&' and num(e[3]):
            self.expr_to_al(e[2])
            self.emit(0x24, e[3][1])  # and al, imm8
            self.al = None
            return
        # byte <op> uchar_local  →  (al = lhs); <op> al, [bp+disp]  (`attr & mask`)
        if (
            op == 'bin'
            and e[1] in ('&', '|', '^', '+', '-')
            and nid(e[3])
            and e[3][1] in self.locals
            and self.ucharty(e[3])
        ):
            self.expr_to_al(e[2])
            opc = {'&': 0x22, '|': 0x0A, '^': 0x32, '+': 0x02, '-': 0x2A}[e[1]]
            self.emit(opc, 0x46, self.ld(e[3][1]))  # <op> al, [bp+disp]
            self.al = None
            return
        # uchar_local + reg_var  →  mov al,[local]; mov cx,si/di; add al,cl
        if op == 'bin' and e[1] == '+' and self.stkid(e[2]) and self.rvid(e[3]):
            self.expr_to_al(e[2])  # mov al, [local]
            reg = self.regvars[e[3][1]]
            self.emit(0x8B, sd(0xCE, reg))  # mov cx, si/di
            self.emit(0x02, 0xC1)  # add al, cl
            self.al = None
            return
        # uchar local <op> const → byte arithmetic in AL (no zero-extend):
        # mov al,[bp+disp]; add/sub/and/or/xor al, imm8
        # (also covers far byte <op> const: `drive = *(uchar far*)(entry) - 0x41`)
        if (
            op == 'bin'
            and e[1] in ('+', '-', '&', '|', '^')
            and num(e[3])
            and (
                self.ucharty(e[2])
                or self.gkind(e[2]) == 'bvar'
                or fbyte(self, e[2])
                or (ncall(e[2]) and nid(e[2][1]) and n11(e[2]) in UCHAR_FUNCS)
            )
        ):
            if self.ucharty(e[2]):
                if self.al != e[2][1]:
                    self.ldal(self.ld(e[2][1]))  # mov al,[bp+disp]
            elif self.gkind(e[2]) == 'bvar':
                self.emit(0xA0, *w16(SYMS[e[2][1]][1]))  # mov al, [addr]
            elif ncall(e[2]):
                self.gen_call(e[2])  # uchar call → result byte in AL (DOS_FN_16's
                # `fcb[0] = get_drive_type(fcb[0]) + 1`)
            else:
                self.expr_to_al(e[2])  # mov al, [es:bx+d]
            if e[1] in ('+', '-') and e[3][1] == 1:
                # byte ± 1: MSC uses inc/dec al (DOS_FN_44's d_unit + 1)
                self.emit(0xFE, 0xC0 if e[1] == '+' else 0xC8)  # inc/dec al
            else:
                opc = {'+': 0x04, '-': 0x2C, '&': 0x24, '|': 0x0C, '^': 0x34}[e[1]]
                self.emit(opc, e[3][1])  # <op> al, imm8
            self.al = None
            return
        # <byte const> - <global>  —  a subtraction whose result is only a byte
        # narrows the WHOLE expression: `mov al,imm; sub al,[g]`, reading just
        # the global's low half (MAIN_ENTRY's `CFG_FCBS_PER_FILE =
        # 0x0F - MAIN_LOOP_INDEX` at 0x051C, whose word-destination twin at
        # 0x0312 keeps the AX form).
        if (
            op == 'bin'
            and e[1] == '-'
            and num(e[2])
            and nid(e[3])
            and self.gkind(e[3]) in ('var', 'uvar', 'bvar')
        ):
            self.emit(0xB0, e[2][1] & 0xFF)  # mov al, imm8
            self.emit(0x2A, 0x06, *w16(SYMS[e[3][1]][1]))  # sub al, [g]
            self.al = None
            return
        # other binary ops: evaluate to AX (AL holds the low byte we want)
        if op == 'bin':
            self.gen_bin(e[1], e[2], e[3])
            return
        # byte global → mov al, [addr]
        if self.gkind(e) == 'bvar':
            a = SYMS[e[1]][1]
            self.emit(0xA0, *w16(a))  # mov al, [a]
            self.al = None
            return
        # WORD global narrowed to a byte — the low half is at the same address,
        # so MSC just reads AL from it (MAIN_ENTRY mirroring SYS_LAST_DRIVE into
        # its byte copy at 0x064D).
        if self.gkind(e) in ('var', 'uvar'):
            self.emit(0xA0, *w16(SYMS[e[1]][1]))  # mov al, [a]
            self.al = None
            return
        ni(e)

    def gen_index(self, e):
        arr = e[1]
        idx = e[2]
        # far_var[word-global (+const)]  →  mov si,[g]; les bx,[fv];
        # mov al,[es:bx+si+disp]  (echo_input_char's typed-buffer read).
        fgi = self.fv_gword_idx(e)
        if fgi:
            fv, g, disp, pinc = fgi
            self.emit(0x8B, 0x36, *w16(sa(g)))  # mov si, [g]
            if pinc:
                self.emit(0xFF, 0x06, *w16(sa(g)))  # inc word [g]
            self.emit_les(fv)  # les bx, [fv]
            self.e26(0x8A, 0x40 | mod8(disp), *d8(disp))  # mov al,[es:bx+si+disp]
            self.zaa()
            return
        # local_array[uchar_local]  →  mov si,[bp+idx]; and si,0FFh;
        # mov al,[bp+si+arr_off]  (a stack buffer indexed by a byte loop counter).
        if (
            nid(arr)
            and arr[1] in self.locals
            and str(self.lt(arr[1])).startswith('arr')
            and nid(idx)
            and idx[1] in self.locals
            and self.ucharty(idx)
            and not self.is_reg_var(idx[1])
        ):
            self.emit(0x8B, 0x76, self.ld(idx[1]))  # mov si, [bp+idx]
            self.emit(0x81, 0xE6, 0xFF, 0x00)  # and si, 0x00FF
            self.emit(0x8A, 0x42, self.ld(arr[1]))  # mov al, [bp+si+arr_off]
            self.zaa()
            return
        # local_array[const]  →  mov al, [bp+arr_off+const]
        if (
            nid(arr)
            and arr[1] in self.locals
            and str(self.lt(arr[1])).startswith('arr')
            and num(idx)
        ):
            self.ldal((self.ld(arr[1]) + idx[1]) & 0xFF)  # mov al,[bp+d]
            self.zaa()
            return
        # ((unsigned char *)&local)[const]  →  mov al, [bp+disp+const]  (a byte at a
        # fixed offset within a local, e.g. a long's high byte).
        if (
            ncast(arr)
            and 'far' not in arr[1]
            and arr[1].startswith('ptr')
            and arr[2][0] == 'addr'
            and nid(arr[2][1])
            and n11(arr[2]) in self.locals
            and num(idx)
        ):
            disp = self.ld(n11(arr[2]))
            self.ldal((disp + idx[1]))  # mov al, [bp+d]
            self.zaa()
            return
        # far_local[uchar local]  →  the INDEX takes BX (zero-extended through
        # BL/BH, not a word load) and the POINTER's offset goes to SI, so the
        # read is `mov bl,[bp+i]; sub bh,bh; les si,[bp+p]; mov al,[es:bx+si]`
        # (GET_ASSIGN_PATH_FOR_DRIVE copying the CDS path out, 0x76CF).
        if (
            self.locid(arr)
            and pf(self.lty(arr))
            and self.locid(idx)
            and self.ucharty(idx)
            and not self.is_reg_var(idx[1])
        ):
            self.emit(0x8A, 0x5E, self.ld(idx[1]))  # mov bl, [bp+i]
            self.emit(0x2A, 0xFF)  # sub bh, bh
            self.emit(0xC4, 0x76, self.ld(arr[1]))  # les si, [bp+p]
            self.e26(0x8A, 0x00)  # mov al, [es:bx+si]
            self.bx = self.essi = None
            self._bh_zero = True
            self.zaa()
            return
        fsi = self._far_self_idx(arr, idx)
        if fsi:
            self._far_self_idx_base(*fsi)
            self.e26(0x8A, 0x00)  # mov al, [es:bx+si]
            self.zaa()
            return
        if not nid(arr) or arr[1] not in SYMS:
            ni('gen_index', arr, idx)
        arr_kind, arr_addr = SYMS[arr[1]][:2]
        # Word-element array of pointers (e.g. KEYWORD_PTR_TABLE)
        if arr_kind == 'arr_w':
            if self.locid(idx) and self.is_reg_var(idx[1]):
                # MSC pattern: mov bx, si; shl bx, 1; mov ax, [bx+addr]
                self.emit(0x8B, 0xDE)  # mov bx, si
                self.emit(0xD1, 0xE3)  # shl bx, 1
                self.emit(0x8B, 0x87, *w16(arr_addr))  # mov ax, [bx+addr]
                self.bx = None
                self.ax = None
                return
            if self.gvw(idx):
                # indexed by a WORD GLOBAL: mov bx,[g]; shl bx,1; mov ax,[bx+ARR]
                self.emit(0x8B, 0x1E, *w16(SYMS[idx[1]][1]))  # mov bx, [g]
                self.emit(0xD1, 0xE3)  # shl bx, 1
                self.emit(0x8B, 0x87, *w16(arr_addr))  # mov ax, [bx+addr]
                self.bx = self.ax = None
                return
            ni('arr_w with non-reg idx')
        # Far-pointer global indexed by a near value: les si,[tbl]; al=[es:bx+si]
        if arr_kind == 'far_var':
            # Indexed by a REGISTER var: the table's offset goes in BX and the
            # index stays in SI/DI (`les bx,[tbl]; mov al,[es:bx+si]`) — the
            # mirror of the near-value form below, which needs SI for the table
            # (INSTALL_DRIVER reading the job file table by handle).
            if self.rvid(idx):
                self.emit_les(arr[1])
                self.e26(0x8A, 0x01 if self.rv(idx) == 'di' else 0x00)
                self.emit(0x2A, 0xE4)  # sub ah, ah (zero-extend)
                self.zaa()
                return
            if self.locid(idx) and not self.is_reg_var(idx[1]):
                disp = self.ld(idx[1])
                self.ldbx(disp)  # mov bx, [bp+idx]
            elif self.gkind(idx) == 'var':
                ia = SYMS[idx[1]][1]
                self.emit(0x8B, 0x1E, *w16(ia))  # mov bx, [addr]
            else:
                ni(idx)
            self.emit(0xC4, 0x36, *w16(arr_addr))  # les si,[tbl]
            self.e26(0x8A, 0x00)  # mov al, [es:bx+si]
            self.emit(0x2A, 0xE4)  # sub ah, ah (zero-extend)
            self.al = self.ax = self.bx = self.esbx = None
            return
        if arr_kind != 'arr':
            ni(arr_kind)
        # Byte-element array (e.g. LINE_BUF)
        if num(idx):  # arr[const] → mov al,[addr+c]
            a = (arr_addr + idx[1]) & 0xFFFF
            self.emit(0xA0, *w16(a))  # mov al, [addr+const]
            self.al = self.ax = None  # caller zero-extends (expr_to_ax)
            return
        # arr[gword ± const] → mov bx,[g]; mov al,[bx + (ARR±const)]  (the const
        # folds into the array-base displacement — HANDLE_INSERT_MODE reads
        # HIST_BUF[HIST_INDEX - 1] as `[bx + HIST_BUF-1]`).
        if (idx[0] == 'bin' and idx[1] in ('+', '-')
                and self.gkind(idx[2]) == 'var' and num(idx[3])):
            g = idx[2][1]
            c = idx[3][1] if idx[1] == '+' else -idx[3][1]
            key = ('idxvar', g)
            if self.bx != key:
                self.emit(0x8B, 0x1E, *w16(SYMS[g][1]))  # mov bx, [g]
                self.bx = key
            self.emit(0x8A, 0x87, *w16((arr_addr + c) & 0xFFFF))  # mov al,[bx+ARR±c]
            self.zaa()
            self.bx = key  # bx survives the AL load
            return
        # arr[<far byte> ± const] → mov bl,[es:bx+d]; sub bh,bh;
        # mov al,[bx + (ARR±const)] — the index is a byte read through a far
        # pointer, so it lands in BL and the const folds into the array base
        # (JOIN reads SUBST_TABLE[cds->c_drvletter - 'A'] as [bx+SUBST_TABLE-41h]).
        if idx[0] == 'bin' and idx[1] in ('+', '-') and num(idx[3]):
            _fl = self.far_lvalue(idx[2])
            if _fl and _fl[2] == 'byte':
                c = idx[3][1] if idx[1] == '+' else -idx[3][1]
                self.emit_les(_fl[0])
                self.e26(0x8A, mod8(_fl[1]) | 0x18 | 0x07, *d8(_fl[1]))  # mov bl,[es:bx+d]
                self.emit(0x2A, 0xFF)  # sub bh, bh
                self.emit(0x8A, 0x87, *w16((arr_addr + c) & 0xFFFF))  # mov al,[bx+ARR±c]
                self.esbx, self.bx = _fl[0], None
                self.zaa()
                return
        # arr[reg var ± const] → mov al, [si/di + (ARR±const)]  (the const folds
        # into the base displacement).  A struct-member array indexed by a reg
        # var normalizes to base[member_off + idx], e.g. DIR_SEARCH_FCB.f_name[si]
        # → DIR_SEARCH_FCB[1 + si]; the '+' form is commutative.
        if idx[0] == 'bin' and idx[1] in ('+', '-'):
            if idx[1] == '+' and num(idx[2]) and self.rvid(idx[3]):
                self.emit(0x8A, sd(0x84, self.rv(idx[3])),
                          *w16((arr_addr + idx[2][1]) & 0xFFFF))
                self.zaa()
                return
            if self.rvid(idx[2]) and num(idx[3]):
                c = idx[3][1] if idx[1] == '+' else -idx[3][1]
                self.emit(0x8A, sd(0x84, self.rv(idx[2])),
                          *w16((arr_addr + c) & 0xFFFF))
                self.zaa()
                return
        # arr[BL reg var] → sub bh,bh; mov al,[bx + ARR].  BL carries only the
        # low byte across the loop's back edge, so BH is re-zeroed at each use
        # (WRITE_DIR_ENTRY's SUBST chain walk).
        if self.rvid(idx) and self.rv(idx) == 'bl':
            self.emit(0x2A, 0xFF)  # sub bh, bh
            self.emit(0x8A, 0x87, *w16(arr_addr))  # mov al, [bx + ARR]
            self.bx = None
            self.zaa()
            return
        # arr[reg var] → mov al, [si/di + ARR]  (the index lives in SI/DI)
        if self.rvid(idx):
            self.emit(0x8A, sd(0x84, self.rv(idx)), *w16(arr_addr))
            self.zaa()
            return
        if self.locid(idx):
            # BX may already hold this index, widened by a preceding compare —
            # a rotated loop's condition seeds it across the back edge, so the
            # body's read needs no reload (UNJOIN_DRIVE's chain walk, 0x758B).
            if self.bx == ('idxloc', idx[1]):
                pass
            else:
                disp = self.ld(idx[1])
                self.ldbx(disp)  # mov bx, [bp-N]
                self.bx = None
        elif self.gkind(idx) == 'var':
            key = ('idxvar', idx[1])
            if self.bx != key:
                self.emit(0x8B, 0x1E, *w16(SYMS[idx[1]][1]))  # mov bx, [addr]
                self.bx = key
            self.emit(0x8A, 0x87, *w16(arr_addr))  # mov al, [bx+ARR]
            self.zaa(); self.bx = key  # bx survives the AL load
            return
        else:
            ni(idx)
        # Load the byte from base+bx
        self.emit(0x8A, 0x87, *w16(arr_addr))
        self.zaa()

    def gen_bin(self, op, lhs, rhs):
        if op == '*':
            # far word * *near-int-ptr  →  mov ax,[es:bx+d]; mov bx,[bp+p]; mul word[bx]
            fl = self.far_lvalue(lhs)
            if (
                fl
                and fl[2] == 'word'
                and nderef(rhs)
                and self.lty(rhs[1]) in ('ptr_int', 'ptr_uint')
            ):
                self.expr_to_ax(lhs)  # mov ax, [es:bx+d]
                disp = self.ldi(rhs)
                self.ldbx(disp)  # mov bx, [bp+p]
                self.emit(0xF7, 0x27)  # mul word [bx]
                self.ax = self.al = self.dx = self.bx = None
                return
            # far word * int/uint local  →  mov ax,[es:bx+d]; mul word [bp+p]
            if fl and fl[2] == 'word' and wint(self.lty(rhs)):
                self.expr_to_ax(lhs)  # mov ax, [es:bx+d]
                disp = self.ld(rhs[1])
                uns = self.lt(rhs[1]) == 'uint'
                self.emit(0xF7, 0x66 if uns else 0x6E, disp)  # mul/imul word [bp+p]
                self.ax = self.al = self.dx = self.bx = None
                return
            # MSC pattern: mov ax, <const> ; imul word [<var>]
            const, other = (
                (rhs, lhs) if num(rhs) else (lhs, rhs) if num(lhs) else (None, None)
            )
            if const and self.rvid(other):
                self.emit(0xB8, const[1], (const[1] >> 8))  # mov ax, const
                self.emit(0xF7, 0xE6 if self.rv(other) == 'si' else 0xE7)  # mul si/di
                self.zaad()
                return
            # byte const * uchar local → 8-bit `mov al,const; mul byte [bp-N]`
            # (result in AX); used for the DPB-entry offset `0x51 * drive`.
            if const and 0 <= const[1] <= 0xFF and self.ucharty(other):
                self.emit(0xB0, const[1])  # mov al, const
                disp = self.ld(other[1])
                self.emit(0xF6, 0x66, disp)  # mul byte [bp-N]
                self.zaad()
                return
            if const and self.locid(other):
                self.emit(0xB8, const[1], (const[1] >> 8))
                disp = self.ld(other[1])
                uns = self.lt(other[1]) in ('uint', 'uchar', 'reg_uint', 'reg_uchar')
                self.emit(0xF7, 0x66 if uns else 0x6E, disp)  # mul/imul word [bp-N]
                self.zaa()
                return
            # var-global * var-global  →  mov ax,[g1]; imul word [g2]
            if self.gkind(lhs) == 'var' and self.gkind(rhs) == 'var':
                self.ldaxm(SYMS[lhs[1]][1])  # mov ax, [g1]
                uns = lhs[1] in self.unsigned or rhs[1] in self.unsigned
                self.emit(0xF7, 0x26 if uns else 0x2E, *w16(SYMS[rhs[1]][1]))
                self.zaad()
                return
            # var-global * reg-var  →  mov ax,[g]; mul si/di
            for g_side, r_side in ((lhs, rhs), (rhs, lhs)):
                if self.gkind(g_side) == 'var' and self.rvid(r_side):
                    a = SYMS[g_side[1]][1]
                    self.ldaxm(a)  # mov ax, [g]
                    self.emit(
                        0xF7, 0xE6 if self.rv(r_side) == 'si' else 0xE7
                    )  # mul si/di
                    self.zaad()
                    return
            # const * byte-global → mov al,const; mul byte[g]  (8-bit multiply → AX)
            for c, g in ((lhs, rhs), (rhs, lhs)):
                if num(c) and self.gkind(g) == 'bvar':
                    a = SYMS[g[1]][1]
                    self.emit(0xB0, c[1])  # mov al, const
                    self.emit(0xF6, 0x26, *w16(a))  # mul byte [g]
                    self.zaad()
                    return
            # const * far-byte → mov al,const; les bx; mul byte[es:bx+disp] (→ AX)
            for c, fb in ((lhs, rhs), (rhs, lhs)):
                if num(c) and 0 <= c[1] <= 0xFF:
                    fl = self.far_lvalue(fb)
                    if fl and fl[2] == 'byte':
                        bse, disp, _ = fl
                        self.emit(0xB0, c[1])  # mov al, const
                        self.emit_les(bse)
                        modrm = mod8(disp) | 0x20 | 0x07  # /4 (mul),[bx+d]
                        self.e26(0xF6, modrm, *d8(disp))
                        self.zaad()
                        return
            ni('*', lhs, rhs)
        # register var +/- const → `lea ax,[si/di ± disp]` (MSC computes a small
        # offset of a register variable with LEA, not mov+add/dec).
        if op in ('+', '-') and self.rvid(lhs) and num(rhs):
            d = (rhs[1] if op == '+' else -rhs[1]) & 0xFFFF
            rm = 4 if self.rv(lhs) == 'si' else 5  # [si] / [di]
            sdisp = s16(d)
            if -128 <= sdisp <= 127:
                self.emit(0x8D, 0x40 | rm, d)  # lea ax,[reg+disp8]
            else:
                self.emit(0x8D, 0x80 | rm, *w16(d))  # disp16
            self.zaa()
            return
        if op == '+':
            # far byte + far byte (same far base) → mov al,[es:bx+d1];sub ah,ah;
            # mov cl,[es:bx+d2];sub ch,ch; add ax,cx
            fl1, fl2 = self.far_lvalue(lhs), self.far_lvalue(rhs)
            if fl1 and fl2 and fl1[2] == 'byte' and fl2[2] == 'byte':
                self.emit_les(fl1[0])
                m1 = (0x40 if fl1[1] else 0x00) | 0x07
                self.e26(0x8A, m1, *((fl1[1],) if fl1[1] else ()))  # mov al,[es:bx+d1]
                self.emit(0x2A, 0xE4)  # sub ah, ah
                self.emit_les(fl2[0])
                m2 = (0x40 if fl2[1] else 0x00) | 0x08 | 0x07
                self.e26(0x8A, m2, *((fl2[1],) if fl2[1] else ()))  # mov cl,[es:bx+d2]
                self.add_cx_tail()
                return
            # Special: reg_var + small_const  →  lea ax, [si/di + disp8]
            if self.rvid(lhs) and num(rhs) and 0 <= rhs[1] <= 127:
                rm = sd(0x44, self.rv(lhs))
                self.emit(0x8D, rm, rhs[1])  # lea ax, [si/di+disp8]
                self.zaa()
                return
            # Special: reg_var + reg_var  →  mov ax,<lhs>; add ax,<rhs>
            # (PARSE_PATH_WITH_DRIVE's `len + namelen` buffer-limit check).
            if self.rvid(lhs) and self.rvid(rhs):
                self.emit(0x8B, sd(0xC6, self.rv(lhs)))  # mov ax, si/di
                self.emit(0x03, sd(0xC6, self.rv(rhs)))  # add ax, si/di
                self.zaa()
                return
            # Special: var + array_const  (or symmetric):
            # load the non-array side into AX, then `add ax, imm16` for the
            # array address.  Matches `mov ax,[X]; add ax, LINE_BUF_addr`.
            for v_side, c_side in ((lhs, rhs), (rhs, lhs)):
                if self.gkind(c_side) in ('arr', 'arr_w'):
                    self.expr_to_ax(v_side)
                    addr = SYMS[c_side[1]][1]
                    self.emit(0x05, *w16(addr))
                    self.ax = None
                    return
            self.expr_to_ax(lhs)
            if self.locid(rhs) and self.lt(rhs[1]) == 'uchar':
                disp = self.ld(rhs[1])
                self.emit(0x8A, 0x4E, disp)  # mov cl, [bp-N]
                self.add_cx_tail()
                return
            # <expr> + word local/param  →  add ax, [bp+disp] straight from the
            # frame (COMPUTE_CLUSTER_INFO_FOR_FCB's `dpb->d_firstdir + idx`).
            if self.locid(rhs) and wint(self.lt(rhs[1])):
                self.emit(0x03, 0x46, self.ld(rhs[1]) & 0xFF)  # add ax, [bp+d]
                self.zaa()
                return
            # <expr> + word var global  →  eval lhs to AX; add ax, [g]
            if self.gkind(rhs) == 'var':
                a = SYMS[rhs[1]][1]
                self.emit(0x03, 0x06, *w16(a))  # add ax, [g]
                self.zaa()
                return
            # <expr> + FP_OFF/FP_SEG(far ptr) → add ax, the far pointer's
            # offset/segment word.  A far_var global: `add ax,[g]` (DOS_FN_10's
            # `0x35*fcb[0x1d] + FP_OFF(DRIVER_TABLE) + 6`); a far-pointer local:
            # `add ax,[bp+disp]` (DOS_FN_10's `(fcb[0x1f]<<5) + FP_OFF(sector)`).
            if rhs[0] in ('fpoff', 'fpseg') and self.gfar(rhs[1]):
                a = SYMS[n11(rhs)][1] + (2 if rhs[0] == 'fpseg' else 0)
                self.emit(0x03, 0x06, *w16(a))  # add ax, [g]
                self.zaa()
                return
            if (
                rhs[0] in ('fpoff', 'fpseg')
                and nid(rhs[1])
                and rhs[1][1] in self.locals
                and pf(self.lty(rhs[1]))
            ):
                disp = self.ld(rhs[1][1]) + (2 if rhs[0] == 'fpseg' else 0)
                self.emit(0x03, 0x46, disp & 0xFF)  # add ax, [bp+disp]
                self.zaa()
                return
            if num(rhs):
                if rhs[1] in (1, 2):  # MSC uses inc for + 1 / + 2
                    for _ in range(rhs[1]):
                        self.emit(0x40)  # inc ax
                else:
                    n = rhs[1] & 0xFFFF
                    self.emit(0x05, *w16(n))  # add ax, imm16
                self.zaa()
                return
            ni('+', lhs, rhs)
        if op == '-':
            self.expr_to_ax(lhs)
            r = uncast(rhs)
            if num(r):
                if r[1] in (1, 2):  # MSC uses dec for - 1 / - 2
                    for _ in range(r[1]):
                        self.emit(0x48)  # dec ax
                else:
                    n = r[1] & 0xFFFF
                    self.emit(0x2D, *w16(n))
                self.zaa()
                return
            # ax -= <16-bit mem>: a word/long/unsigned global, or an int/uint local
            if self.gkind(r) in ('var', 'long_var'):
                a = SYMS[r[1]][1]
                self.emit(0x2B, 0x06, *w16(a))  # sub ax, [a]
                self.zaa()
                return
            if wint(self.lty(r)):
                d = self.ld(r[1])
                self.emit(0x2B, 0x46, d)  # sub ax, [bp+d]
                self.zaa()
                return
            # ax -= far word lvalue: sub ax, [es:bx+disp]
            fr = self.far_lvalue(r)
            if fr and fr[2] == 'word':
                disp = self.les_fl(fr)
                modrm = mod8(disp) | 0x06  # /0 (ax)? no — sub r,r/m
                self.e26(0x2B, mod8(disp) | 0x07, *d8(disp))  # sub ax, [es:bx+disp]
                self.zaa()
                return
            ni('-', lhs, rhs)
        if op == '<<':
            # 16-bit variable shift: shl ax, cl
            self.expr_to_ax(lhs)
            self._load_cl(rhs)
            self.emit(0xD3, 0xE0)  # shl ax, cl
            self.zaa()
            return
        if op == '&':
            r = uncast(rhs)
            # us, so MSC skips the `sub ah,ah` zero-extend.
            if num(r) and 0 <= r[1] <= 0xFF:
                fl = self.far_lvalue(lhs)
                byte_local = (
                    nid(lhs)
                    and lhs[1] in self.locals
                    and self.lt(lhs[1]) in ('uchar', 'char')
                )
                if (fl and fl[2] == 'byte') or byte_local:
                    self.expr_to_al(lhs)
                    self.emit(0x25, r[1], 0x00)  # and ax, imm16
                    self.zaa()
                    return
            # 16-bit AND: eval lhs to AX, then `and ax, <rhs>`
            self.expr_to_ax(lhs)
            if self.gkind(r) in ('var', 'long_var'):
                a = SYMS[r[1]][1]
                self.emit(0x23, 0x06, *w16(a))  # and ax, [a]
            elif num(r) and r[1] & 0xFF == 0xFF and r[1] <= 0xFFFF:
                # all-ones low byte: MSC masks just AH (`& 0xEFFF` →
                # `and ah,0xEF` — DOS_FN_44's dh_attr mask)
                self.emit(0x80, 0xE4, (r[1] >> 8) & 0xFF)  # and ah, imm8
            elif num(r):
                self.emit(0x25, r[1], (r[1] >> 8))  # and ax, imm16
            else:
                ni('&', lhs, rhs)
            self.zaa()
            return
        if op in ('/', '%'):
            # unsigned 16-bit divide: ax = lhs; sub dx,dx; div word[divisor].
            # Quotient lands in AX, remainder in DX; `%` moves DX->AX.
            self.expr_to_ax(lhs)
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self._emit_div_operand(rhs)
            if op == '%':
                self.emit(0x8B, 0xC2)  # mov ax, dx
            self.zaad()
            return
        if (
            op == '>>'
            and num(rhs)
            and not self._is_long_expr(lhs)
            and not self._is_long4(lhs)
        ):
            # 16-bit unsigned shift: mov cl,amt; shr ax,cl  (shr ax,1 for amt==1)
            self.expr_to_ax(lhs)
            if (
                lhs[0] == 'idx'
                and lhs[1][0] == 'cast'
                and lhs[1][1] in ('ptr_uchar', 'ptr_char')
            ):
                # A byte read through a char* cast only fills AL; C promotes it
                # to int before shifting, so AH has to be cleared or the high
                # half shifts in garbage (`(uchar)date1[1] >> 4`, 0x60D9).
                self.emit(0x2A, 0xE4)  # sub ah, ah
            amt = rhs[1]
            if amt == 1:
                self.emit(0xD1, 0xE8)  # shr ax, 1
            else:
                self._load_cl(rhs)  # mov cl, amt (reused if live)
                self.emit(0xD3, 0xE8)  # shr ax, cl
            self.zaa()
            return
        if op == '>>' and num(rhs):
            # long >> const : evaluate to DX:AX.  MSC special-cases >>8 (byte
            # shuffle) and >>16 (word move); other counts use the SHR helper
            # (DX:AX >> CL, address pinned by __lshr).  Callers in a 16/8-bit
            # context (a cast) take AX / AL.
            self.load_long_axdx(lhs)  # ax=lo, dx=hi
            amt = rhs[1]
            if amt == 8:
                self.emit(0x8A, 0xC4)  # mov al, ah
                self.emit(0x8A, 0xE2)  # mov ah, dl
                self.emit(0x8A, 0xD6)  # mov dl, dh
                self.emit(0x2A, 0xF6)  # sub dh, dh
                self.zaad()
            elif amt == 16:
                self.emit(0x8B, 0xC2)  # mov ax, dx
                self.emit(0x2B, 0xD2)  # sub dx, dx
                self.zaad()
            else:
                self.emit(0xB1, amt)  # mov cl, amt
                self.emit_call(SYMS['__lshr'][1])  # clobbers AX/BX/CX/DX/ES
                self.clob()
            return
        if op == '>>':
            # long >> variable : DX:AX = lhs; load CL; call the SHR helper
            self.gen_long(lhs)
            self._load_cl(rhs)
            self.emit_call(SYMS['__lshr'][1])
            self.clob()
            return
        if op == '|':
            # `*(T far*)(p+a) | *(T far*)(p+b)` over ONE far base (same ES:BX):
            # load the first word, OR the second straight from [es:bx+b].
            fl, fr = self.far_lvalue(lhs), self.far_lvalue(rhs)
            if fl and fr and fl[2] == 'word' and fr[2] == 'word' and fl[0] == fr[0]:
                self.expr_to_ax(lhs)  # ax = [es:bx(+si)+a]
                rdisp = fr[1]
                if (
                    isinstance(fl[0], tuple)
                    and fl[0][0] == 'idx'
                    and fl[0] in self._idx_si
                ):
                    # si-indexed scaled base: OR the sibling field from
                    # [es:bx+si/di+b] (SET_FCB's DPB_TABLE[out[0]].c_dpbo|.c_dpbs;
                    # DI when SI is a reg-var, MKDIR's loop counter).
                    _, _, m = self._scaled_idx_reg()
                    self.e26(0x0B, m, rdisp)  # or ax,[es:bx+si/di+b]
                else:
                    self.e26(
                        0x0B, mod8(rdisp) | 0x07, *((rdisp,) if rdisp else ())
                    )  # or ax,[es:bx+b]
                self.zaa()
                return
        ni(op)

    def _emit_div_operand(self, rhs):
        """Emit `div word [<rhs>]` for a word global or local divisor."""
        if self.gkind(rhs) == 'var':
            a = SYMS[rhs[1]][1]
            self.emit(0xF7, 0x36, *w16(a))  # div word [addr]
        elif self.locid(rhs):
            d = self.ld(rhs[1])
            self.emit(0xF7, 0x76, d)  # div word [bp+d]
        else:
            fr = self.far_lvalue(rhs)
            if fr and fr[2] == 'word':
                disp = self.les_fl(fr)
                modrm = mod8(disp) | 0x30 | 0x07  # /6 (div), [bx+disp]
                self.e26(0xF7, modrm, *d8(disp))  # div word[es:bx+d]
                return
            ni('div-operand', rhs)

    # ---- conditional jumps ----
    def cond_jump(self, cond, label, taken):
        if cond[0] == 'or':
            if taken:
                self.cond_jump(cond[1], label, True)
                self.cond_jump(cond[2], label, True)
            else:
                skip = self.fresh('skip')
                self.cond_jump(cond[1], skip, True)
                self.cond_jump(cond[2], label, False)
                self.lbl(skip)
            return
        if cond[0] == 'and':
            if taken:
                # (a && b) true → only branch when BOTH are true:
                # if (!a) skip; if (b) goto label; skip:
                skip = self.fresh('skip')
                self.cond_jump(cond[1], skip, False)
                self.cond_jump(cond[2], label, True)
                self.lbl(skip)
            else:
                # NOT (a && b) → either arm false suffices:
                # if (!a) goto label; if (!b) goto label
                self.cond_jump(cond[1], label, False)
                self.cond_jump(cond[2], label, False)
            return
        if cond[0] != 'cmp':
            ni(cond)
        cop, lhs, rhs = cond[1], cond[2], cond[3]
        # An explicit `(unsigned)` cast on either side makes the whole comparison
        # unsigned (MSC picks jnc/ja over jnl/jg) — unwrap it so the operand
        # patterns below still match (the line editor's
        # `TEMPLATE_LEN >= (unsigned)ECHO_CURSOR`).
        # ...and an `(int)` cast is the mirror: it forces the SIGNED jcc even when
        # the other operand is unsigned (EDIT_TEMPLATE_PROCESS walking the
        # history with `(int)HIST_SCAN_IDX + 1 <= (int)HIST_INDEX`).
        self._force_uns = self._force_sign = False
        for _side in ('lhs', 'rhs'):
            _v = lhs if _side == 'lhs' else rhs
            if ncast(_v) and _v[1] == 'int' and nid(_v[2]):
                self._force_sign = True
                if _side == 'lhs':
                    lhs = _v[2]
                else:
                    rhs = _v[2]
                continue
            # ...only over a bare NAME: a cast wrapping a call is load-bearing
            # for WIDTH (con_getc's `(unsigned int)check_con_busy(...) != 0`
            # tests AX, not AL) and must not be unwrapped.
            if ncast(_v) and _v[1] in ('uint', 'uchar') and nid(_v[2]):
                self._force_uns = True
                if _side == 'lhs':
                    lhs = _v[2]
                else:
                    rhs = _v[2]
        # `++regvar <op> num` — the bump belongs to the CONDITION, so it is
        # emitted before the compare and the compare then reads the register
        # itself (EXEC_PROGRAM_FROM_PATH's `++status < 0x43` scan bound at
        # 0x54D0).
        if lhs[0] in ('preinc', 'predec') and self.rvid(lhs[1]) and num(rhs):
            _r = self.rv(lhs[1])
            self.emit(sd(0x4E if lhs[0] == 'predec' else 0x46, _r))  # inc/dec si/di
            self._regvar_zero[_r] = False
            if _r == 'si':
                self.si = None
            else:
                self.di = None
            lhs = lhs[1]
        # `A[B[di]] == C[di+si]` — two byte tables compared, the right side a
        # two-register sum index (RENAME_FCB's wildcard collision check).  MSC
        # evaluates the RHS first into AL via `mov bx,di; mov al,[bx+si+C]`, then
        # loads the LHS subscript `mov bl,[di+B]; sub bh,bh` and compares the
        # arr[<uchar local>] <cmp> <byte const> : same addressing as the
        # local-vs-local form below, with the constant as the immediate —
        # `mov bl,al; sub bh,bh; cmp byte [bx+ARR],imm`
        # (RESOLVE_LOGICAL_DRIVE_LETTER testing the SUBST chain head at 0x5223).
        if (
            lhs[0] == 'idx'
            and self._gbarr(lhs[1]) is not None
            and self.locid(lhs[2])
            and self.lt(lhs[2][1]) in ('uchar', 'char')
            and num(rhs)
        ):
            if self.al == lhs[2][1]:
                self.emit(0x8A, 0xD8)  # mov bl, al
            else:
                self.emit(0x8A, 0x5E, self.ld(lhs[2][1]))  # mov bl, [bp+i]
            self.emit(0x2A, 0xFF)  # sub bh, bh
            self.emit(0x80, 0xBF, *w16(self._gbarr(lhs[1])), rhs[1] & 0xFF)
            self.bx = ('idxloc', lhs[2][1])
            self._bh_zero = True
            self.emit_cc(cop, taken, True, label)
            return
        # arr[<uchar local>] <cmp> <uchar local> : the index zero-extends into BX
        # (reusing AL when it already holds it) and the right operand goes to AL,
        # so the compare reads memory against the register —
        # `mov bl,..; sub bh,bh; mov al,[bp+r]; cmp [bx+ARR],al`
        # (UNJOIN_DRIVE walking the SUBST_TABLE chain at 0x7592).
        if (
            lhs[0] == 'idx'
            and self._gbarr(lhs[1]) is not None
            and self.locid(lhs[2])
            and self.lt(lhs[2][1]) in ('uchar', 'char')
            and self.locid(rhs)
            and self.lt(rhs[1]) in ('uchar', 'char')
        ):
            if self.al == lhs[2][1]:
                self.emit(0x8A, 0xD8)  # mov bl, al
            else:
                self.emit(0x8A, 0x5E, self.ld(lhs[2][1]))  # mov bl, [bp+i]
            self.emit(0x2A, 0xFF)  # sub bh, bh
            self.ldal(self.ld(rhs[1]))  # mov al, [bp+r]
            self.emit(0x38, 0x87, *w16(self._gbarr(lhs[1])))  # cmp [bx+ARR], al
            self.bx = ('idxloc', lhs[2][1])  # BX still holds the widened index
            self.al = rhs[1]
            self._bh_zero = True
            self.emit_cc(cop, taken, True, label)
            return
        # memory operand `cmp [bx+A],al`.
        if (
            cop in ('==', '!=')
            and lhs[0] == 'idx' and self._gbarr(lhs[1]) is not None
            and lhs[2][0] == 'idx' and self._gbarr(lhs[2][1]) is not None
            and self.rvid(lhs[2][2])
            and rhs[0] == 'idx' and self._gbarr(rhs[1]) is not None
            and rhs[2][0] == 'bin' and rhs[2][1] == '+'
            and self.rvid(rhs[2][2]) and self.rvid(rhs[2][3])
        ):
            a_base = self._gbarr(lhs[1])
            b_base = self._gbarr(lhs[2][1])
            c_base = self._gbarr(rhs[1])
            di_reg = self.regvars[rhs[2][2][1]]  # left of + → BX
            si_reg = self.regvars[rhs[2][3][1]]  # right of + → index reg
            q_reg = self.regvars[lhs[2][2][1]]   # B[q_reg]
            self.emit(0x8B, sd(0xDE, di_reg))    # mov bx, di
            self.emit(0x8A, 0x80 if si_reg == 'si' else 0x81, *w16(c_base))  # al=[bx+si+C]
            self.emit(0x8A, 0x9C if q_reg == 'si' else 0x9D, *w16(b_base))   # bl=[di+B]
            self.emit(0x2A, 0xFF)                # sub bh, bh
            self.emit(0x38, 0x87, *w16(a_base))  # cmp [bx+A], al
            self.bx = self.al = None
            self.emit_cc(cop, taken, True, label)
            return
        # `(L & G) ==/!= L` where G is a byte global just zeroed into CL and L is
        # a uchar local still live in AL — reuse both: `and al,cl; cmp al,[L]`
        # (DOS_FN_41's `(attr_check & SDA_SEARCH_ATTR) != attr_check`).
        if (
            cop in ('==', '!=')
            and nbin(lhs)
            and lhs[1] == '&'
            and nid(lhs[3])
            and self._cl_bvar0 is not None
            and lhs[3][1] == self._cl_bvar0
            and nid(lhs[2])
            and nid(rhs)
            and lhs[2] == rhs
            and self.al == rhs[1]
        ):
            self._cl_bvar0 = None
            self.emit(0x22, 0xC1)  # and al, cl
            self.emit(0x3A, 0x46, self.ld(rhs[1]) & 0xFF)  # cmp al, [bp+L]
            self.emit_cc(cop, taken, rhs[1] in self.unsigned, label)
            return
        # `K - uchar_local ==/!= uchar_local` : MSC evaluates the subtraction as
        # (uchar - K) then negates, and widens the rhs through CX —
        #   mov al,[L]; sub ah,ah; sub ax,K; neg ax; mov cl,[R]; sub ch,ch;
        #   cmp ax,cx  (RENAME_FCB's QCHAR_TABLE-full test `0xC7-qcount == idx`).
        if (
            cop in ('==', '!=')
            and nbin(lhs)
            and lhs[1] == '-'
            and num(lhs[2])
            and self.ucharty(lhs[3])
            and self.ucharty(rhs)
        ):
            self.ldal(self.ld(lhs[3][1]))  # mov al, [bp+L]
            self.emit(0x2A, 0xE4)  # sub ah, ah
            self.emit(0x2D, *w16(lhs[2][1]))  # sub ax, K
            self.emit(0xF7, 0xD8)  # neg ax
            self.emit(0x8A, 0x4E, self.ld(rhs[1]))  # mov cl, [bp+R]
            self.emit(0x2A, 0xED)  # sub ch, ch
            self.emit(0x3B, 0xC1)  # cmp ax, cx
            self.al = self.ax = self.cl = None
            self.emit_cc(cop, taken, False, label)
            return
        # `expr <cmp> ++word_global` : the pre-increment mutates memory before
        # the compare re-reads it — evaluate the LHS to AX, emit `inc word [g]`,
        # then `cmp ax,[g]` against the now-incremented value (echo_or_buffer_char
        # steps the echo column and tests it against the terminal width).
        if rhs[0] == 'preinc' and self.gvw(rhs[1]):
            g = rhs[1][1]
            addr = SYMS[g][1]
            self.expr_to_ax(lhs)
            self.emit(0xFF, 0x06, *w16(addr))  # inc word [g]
            if self.bx == ('idxvar', g):
                self.bx = None
            self.emit(0x3B, 0x06, *w16(addr))  # cmp ax, [g]
            self.ax = None
            self.emit_cc(cop, taken, self.is_uchar_cmp(lhs, rhs[1]), label)
            return
        # (word_global | word_global) <cmp> 0  →  mov ax,[g1]; or ax,[g2]; jcc
        # (the OR sets ZF directly, no `cmp` — `SEED_CLUSTER | SEED_HANDLE`).
        if (
            nbin(lhs)
            and lhs[1] == '|'
            and z0(rhs)
            and self.gvw(lhs[2])
            and self.gvw(lhs[3])
        ):
            self.ldaxm(SYMS[lhs[2][1]][1])  # mov ax, [g1]
            self.emit(0x0B, 0x06, *w16(SYMS[lhs[3][1]][1]))  # or ax, [g2]
            self.ax = None
            self.emit_cc(cop, taken, True, label)
            return
        # local_array[const] <op> imm  →  cmp byte [bp+off+const], imm8 (direct
        # memory compare, `buf[0] == 0x20`).
        if (
            lhs[0] == 'idx'
            and nid(lhs[1])
            and n11(lhs) in self.locals
            and str(self.lt(n11(lhs))).startswith('arr')
            and num(lhs[2])
            and num(rhs)
        ):
            disp = (self.ldi(lhs) + lhs[2][1]) & 0xFF
            self.emit(0x80, 0x7E, disp, rhs[1] & 0xFF)  # cmp byte [bp+d], imm8
            self.emit_cc(cop, taken, True, label)  # unsigned (uchar)
            return
        # <uchar local> <op> 0 with BH still holding a zero from a just-widened
        # array index: MSC compares against the REGISTER, saving the immediate
        # byte — `cmp [bp+d],bh` (SUBST testing the drive right after clearing
        # the FCB name area).
        if (
            getattr(self, '_bh_zero', False)
            and self.locid(lhs)
            and self.lt(lhs[1]) in ('uchar', 'char')
            and num(rhs)
            and rhs[1] == 0
        ):
            self.emit(0x38, 0x7E, self.ld(lhs[1]))  # cmp [bp+d], bh
            self.emit_cc(cop, taken, True, label)
            return
        # <byte expr> <op> uchar_local  →  (al = expr); cmp al,[bp+disp]; jcc
        # (`(attr & mask) != attr`).
        if (
            nbin(lhs)
            and nid(rhs)
            and rhs[1] in self.locals
            and self.ucharty(rhs)
            and not self.is_reg_var(rhs[1])
        ):
            self.expr_to_al(lhs)
            self.emit(0x3A, 0x46, self.ld(rhs[1]))  # cmp al, [bp+disp]
            self.al = None
            self.emit_cc(cop, taken, True, label)  # unsigned (uchar)
            return
        # far byte already live in AL from a prior `local = fcb[d]` store — test
        # AL directly (`or al,al` / `cmp al,imm`) instead of re-reading it
        # (e.g. `drive = fcb[6]; drive--; if (fcb[6] == 0) …`).
        if num(rhs) and self.al == ('rhs', lhs) and fbyte(self, lhs):
            self.cmp_al_imm(rhs[1])
            self.emit_cc(cop, taken, False, label)
            return
        # (A | B) == 0 / != 0 : evaluating the OR already sets ZF, so branch on it
        # directly instead of appending a redundant `or ax,ax`.
        if cop in ('==', '!=') and z0(rhs) and nbin(lhs) and lhs[1] == '|':
            self.expr_to_ax(lhs)
            self.emit_cc(cop, taken, False, label)
            return
        # far_var[word-global (+const)] <op> imm8 → index→SI scratch; les bx;
        # cmp byte [es:bx+si+disp], imm8  (echo_input_loop's CR test on the
        # typed buffer: `INPUT_FCB_PTR[ECHO_CURSOR + 2] != 0x0D`).
        fgi = self.fv_gword_idx(lhs)
        if fgi and num(rhs):
            fv, g, disp, pinc = fgi
            self.emit(0x8B, 0x36, *w16(sa(g)))  # mov si, [g]
            if pinc:
                self.emit(0xFF, 0x06, *w16(sa(g)))  # inc word [g]
            self.emit_les(fv)  # les bx, [fv]
            self.e26(0x80, 0x38 | mod8(disp), *d8(disp), rhs[1])
            self.emit_cc(cop, taken, True, label)
            return
        # far_var[gword+const] <op> byte-global : mov si,[g]; les bx,[fv];
        # mov al,[bvar]; cmp [es:bx+si+disp],al (ES:BX reused across the loop
        # back-edge from the test — FIND_NEXT_CHAR_MATCH's key compare).
        if fgi and self.gkind(rhs) == 'bvar':
            fv, g, disp, pinc = fgi
            self.emit(0x8B, 0x36, *w16(sa(g)))  # mov si, [g]
            if pinc:
                self.emit(0xFF, 0x06, *w16(sa(g)))  # inc word [g]
            self.emit_les(fv)  # les bx, [fv] (no-op if ES:BX already the base)
            self.emit(0xA0, *w16(sa(rhs[1])))  # mov al, [bvar]
            self.e26(0x38, 0x00 | mod8(disp), *d8(disp))  # cmp [es:bx+si+disp],al
            # SI still holds the (un-bumped) index global — a following read of it
            # on the fall-through reuses `mov ax,si` (FIND_PREV_CHAR_MATCH).
            self.si = None if pinc else ('gword', g)
            self.al = None
            self.emit_cc(cop, taken, True, label)
            return

        # far_ptr[local] <op> const → index→BX; les si,[ptr]; cmp byte[es:bx+si],imm
        if num(rhs):
            fps = self.far_param_subscript(lhs)
            if fps:
                self._emit_far_param_index(*fps)
                self.e26(0x80, 0x38, rhs[1])  # cmp byte[es:bx+si],imm8
                self.emit_cc(cop, taken, True, label)
                return
        # FP_OFF/FP_SEG(far_var) <op> X — a word at [addr]/[addr+2]: cmp word[a],X
        if lhs[0] in ('fpoff', 'fpseg') and self.gfar(lhs[1]):
            a = sa(n11(lhs)) + (2 if lhs[0] == 'fpseg' else 0)
            if num(rhs):
                n = rhs[1]
                if i8(n):
                    self.emit(0x83, 0x3E, *w16(a), n)
                else:
                    self.emit(0x81, 0x3E, *w16(a), *w16(n))
                self.emit_cc(cop, taken, True, label)
                return
            if self.gvw(rhs):
                self.expr_to_ax(rhs)  # mov ax, [g]
                self.emit(0x39, 0x06, *w16(a))  # cmp [a], ax
                self.emit_cc(cop, taken, True, label)
                return
        # FP_OFF/FP_SEG(far_local) <op> num — direct cmp word [bp+d(+2)], imm
        # (COPY_DPB_AND_LOOKUP's did-the-resolver-return-the-scratch test).
        # Defers to the register-reuse paths when AX:DX still holds the far
        # pointer's value (find_fcb_for_drive's loop-carried `cmp ax,0xffff`).
        if (
            lhs[0] in ('fpoff', 'fpseg')
            and pf(self.lty(lhs[1]))
            and num(rhs)
            and self.axdx_var != lhs[1][1]
            and self.ax not in (('low', lhs[1][1]), (lhs[0], lhs[1][1]))
            and self.dx != ('hi', lhs[1][1])
            and self._emit_cmp_imm(lhs, rhs[1])
        ):
            self.emit_cc(cop, taken, True, label)
            return
        # *(long far*)(base+d) == 0 / != 0  →  mov ax,[es:bx+d]; or ax,[es:bx+d+2]; jz/jnz
        if (
            cop in ('==', '!=')
            and z0(rhs)
            and nderef(lhs)
            and ncast(lhs[1])
            and n11(lhs) == 'ptr_far_long'
        ):
            disp = self.far_int_les(lhs)
            if disp is not None:
                self.e26(0x8B, mod8(disp) | 0x07, *d8(disp))  # mov ax,[es:bx+d]
                self.e26(0x0B, 0x40 | 0x07, disp + 2)  # or ax,[es:bx+d+2]
                self.emit_cc(cop, taken, False, label)
                return
        # (global++) <op> X  →  mov ax,[g]; inc word[g]; cmp ax, X
        if lhs[0] == 'postinc' and self.gkind(lhs[1]) == 'var':
            g = sa(n11(lhs))
            self.ldaxm(g)  # mov ax, [g]
            self.emit(0xFF, 0x06, *w16(g))  # inc word [g]
            self.ax = None
            if self.gkind(rhs) == 'var':
                a = SYMS[rhs[1]][1]
                self.emit(0x3B, 0x06, *w16(a))  # cmp ax, [a]
            elif num(rhs):
                self.cmp_ax_imm(rhs[1])
            else:
                ni('postinc-cmp', rhs)
            self.emit_cc(cop, taken, self.is_uchar_cmp(lhs[1], rhs), label)
            return
        # (local++ / local--) <op> num  →  mov ax,[bp+d]; inc/dec word[bp+d];
        # cmp ax, num  (the comparison uses the pre-inc/dec value)
        if lhs[0] in ('postinc', 'postdec') and self.stkid(lhs[1]) and num(rhs):
            d = self.ldi(lhs)
            self.ldax(d)  # mov ax, [bp+d]
            self.emit(
                0xFF, 0x46 if lhs[0] == 'postinc' else 0x4E, d
            )  # inc/dec word [bp+d]
            self.ax = None
            self.cmp_ax_imm(rhs[1])
            self.emit_cc(cop, taken, self.is_uchar_cmp(lhs[1], rhs), label)
            return
        # long-returning call == 0 / != 0 — the helper leaves DX:AX, so OR both
        # words (`or ax,dx`) — DOS_FN_23's `divmod32_bin(size,recsize) != 0`.
        if z0(rhs) and ncall(lhs) and nid(lhs[1]) and n11(lhs) in LONG_FUNCS:
            self.gen_long(lhs)
            self.emit(0x0B, 0xC2)  # or ax, dx
            self.emit_cc(cop, taken, False, label)
            return
        # long == 0 / != 0 — OR both words (or `or ax,dx` if it's freshly in regs)
        if z0(rhs) and nid(lhs) and self._is_long4(lhs):
            n = lhs[1]
            if self.axdx_var == n:
                self.emit(0x0B, 0xC2)  # or ax, dx
            elif n in self.locals:
                d = self.ld(n)
                self.ldax(d)  # mov ax,[bp+d]
                self.emit(0x0B, 0x46, d + 2)  # or ax,[bp+d+2]
            else:
                a = sa(n)
                self.ldaxm(a)  # mov ax,[a]
                self.emit(0x0B, 0x06, *w16(a + 2))  # or ax,[a+2]
            self.emit_cc(cop, taken, False, label)
            return
        # long == / != long lvalue — evaluate lhs to DX:AX, then split-compare
        # the two words against a long global / local.
        if cop in ('==', '!=') and (
            self.gkind(rhs) == 'long_var' or self.lty(rhs) == 'long'
        ):
            self.gen_long(lhs)  # lhs → DX:AX
            if rhs[1] in self.locals:
                d = self.ld(rhs[1])
                hi = (0x3B, 0x56, (d + 2) & 0xFF)  # cmp dx,[bp+d+2]
                lo = (0x3B, 0x46, d & 0xFF)  # cmp ax,[bp+d]
            else:
                a = SYMS[rhs[1]][1]
                hi = (0x3B, 0x16, *w16(a + 2))  # cmp dx,[a+2]
                lo = (0x3B, 0x06, *w16(a))  # cmp ax,[a]
            jump_when_equal = (cop == '==') == taken
            if jump_when_equal:
                skip = self.fresh('skip')
                self.emit(*hi)
                self.emit_jcc(0x75, skip)  # jnz skip (hi differs)
                self.emit(*lo)
                self.emit_jcc(0x74, label)  # jz label (lo equal)
                self.lbl(skip)
            else:
                self.emit(*hi)
                self.emit_jcc(0x75, label)  # jnz label
                self.emit(*lo)
                self.emit_jcc(0x75, label)  # jnz label
            return
        # ordered long compare where BOTH operands are computed long exprs
        # (neither is a memory lvalue): `(A >> c) >= (B >> c)`.  MSC evaluates
        # the RHS first into DX:AX, parks it in CX:SI (then DI:SI), evaluates the
        # LHS into DX:AX with the CX→DI shuffle injected after the second `les`,
        # and split-compares DX:AX against SI:DI.  Recognized for the file-extend
        # decision in WRITE_FCB_WITH_NETWORK; tightly shaped so it can't fire for
        # the simpler one-operand-in-memory compares handled below.
        if (
            cop in ('<', '>', '<=', '>=')
            and nbin(lhs)
            and lhs[1] == '>>'
            and nbin(rhs)
            and rhs[1] == '>>'
        ):
            r_cl = self.far_lvalue(rhs[3])
            l_cl = self.far_lvalue(lhs[3])
            l_val = lhs[2]
            if (
                ncast(l_val)
                and wlong(l_val[1])
                and nbin(l_val[2])
                and l_val[2][1] == '-'
            ):
                deref = self.far_lvalue(l_val[2][2])
            else:
                deref = None
            if r_cl and r_cl[2] == 'byte' and l_cl and l_cl[2] == 'byte' and deref:
                # RHS = B >> c  →  DX:AX
                self.gen_long(rhs[2])  # B → DX:AX
                self._load_cl(rhs[3])  # les; mov cl,[es:bx+c]
                self.emit_call(SYMS['__lshr'][1])
                self.clob()
                # Interleave: start LHS deref, park RHS in CX:SI, finish deref,
                # set up the second shift count with the CX→DI shuffle.
                self.emit_les(deref[0])  # les bx, [P]
                self.emit(0x8B, 0xC8)  # mov cx, ax  (RHS lo)
                self.emit(0x8B, 0xF2)  # mov si, dx  (RHS hi)
                dd = deref[1]
                self.e26(
                    0x8B, mod8(dd) | 0x07, *((dd,) if dd else ())
                )  # mov ax,[es:bx+d]
                self.e26(0x8B, 0x40 | 0x57, dd + 2)  # mov dx,[es:bx+d+2]
                self.emit_les(l_cl[0])  # les bx, [L]
                self.emit(0x8B, 0xF9)  # mov di, cx  (RHS lo)
                ck = l_cl[1]
                self.e26(
                    0x8A, mod8(ck) | 0x08 | 0x07, *((ck,) if ck else ())
                )  # mov cl,[es:bx+c]
                self.emit(0x2D, 0x01, 0x00)  # sub ax, 1
                self.emit(0x83, 0xDA, 0x00)  # sbb dx, 0
                self.emit_call(SYMS['__lshr'][1])  # LHS → DX:AX
                self.clob()
                self.cl = None
                # split compare DX:AX (LHS) vs SI:DI (RHS, si=hi, di=lo)
                self._ord_split_cmp(
                    cop, taken, label, (0x3B, 0xD6), (0x3B, 0xC7)
                )  # cmp dx,si / cmp ax,di
                return
        # far-long deref  <ordered>  long lvalue:  the deref is the memory
        # operand and the lvalue goes to DX:AX.  MSC loads ES:BX for the deref
        # first, then the lvalue, and split-compares [es:bx+d] vs DX:AX with the
        # greater-test (ja) emitted before the below-test (jb) — the operand
        # orientation that the `< EOF_ANCHOR` range check in WRITE_FCB uses.
        if (
            cop in ('<', '>', '<=', '>=')
            and nderef(lhs)
            and ncast(lhs[1])
            and n11(lhs) in ('ptr_far_long', 'ptr_far_ulong')
            and (self.gkind(rhs) == 'long_var' or self.lty(rhs) == 'long')
        ):
            disp = self.far_int_les(lhs)
            if disp is not None:  # les bx, [base]
                self.gen_long(('id', rhs[1]))  # rhs → DX:AX
                hi = (
                    0x26,
                    0x39,
                    0x40 | (0x02 << 3) | 0x07,
                    (disp + 2) & 0xFF,
                )  # cmp [es:bx+d+2],dx
                lo = (
                    0x26,
                    0x39,
                    mod8(disp) | 0x07,
                    *d8(disp & 0xFF),
                )  # cmp [es:bx+d],ax
                self._ord_split_cmp(cop, taken, label, hi, lo, ja_first=True)
                return

        # ordered long compare (unsigned long): high/low split with the jb/ja
        # two-level jump.  One operand goes to DX:AX (a computed long expr, or —
        # when both are simple long lvalues — the RHS); the other is compared
        # from memory.  (DX:AX-reuse to skip the reload is added separately.)
        def _long_lval(n):
            # A far pointer is a 4-byte lvalue too, and comparing two of them
            # is the same word-by-word job (PROCESS_DRIVER_REQUEST's scan
            # bound `base + 40h > path`).
            return (
                self.gkind(n) in ('long_var', 'far_var')
                or self.lty(n) == 'long'
                or pf(self.lty(n))
            )

        # ordered long expr <op> ((long)HI << 16 | LO) — the RHS is a 32-bit value
        # assembled from two 16-bit lvalues (high word HI, low word LO), compared
        # word-by-word against the DX:AX result of the LHS (DOS_FN_10's sector
        # range check `... > ((long)fcb[0x18]<<16 | fcb[0x1d])`).
        def _hilo_pair(n):
            if (
                nbin(n)
                and n[1] == '|'
                and nbin(n[2])
                and n[2][1] == '<<'
                and n[2][3] == ('num', 16)
                and ncast(n[2][2])
                and wlong(n[2][2][1])
            ):
                return (n[2][2][2], n[3])  # (HI, LO)
            return None

        def _shift_pair(n):
            """`X >> S` as (X, S), else None — the both-computed compare shape."""
            return (n[2], n[3]) if nbin(n) and n[1] == '>>' else None

        pair = _hilo_pair(rhs)
        if cop in ('<', '>', '<=', '>=') and self._is_long_expr(lhs) and pair:
            hi_n, lo_n = pair
            self.gen_long(lhs)  # LHS → DX:AX
            d_hi, d_lo = self.ld(hi_n[1]), self.ld(lo_n[1])
            hi = (0x3B, 0x56, d_hi & 0xFF)  # cmp dx, [bp+hi]
            lo = (0x3B, 0x46, d_lo & 0xFF)  # cmp ax, [bp+lo]
            self._ord_split_cmp(cop, taken, label, hi, lo, ja_first=True)
            return

        # Two 4-byte lvalues compared for EQUALITY: the right side goes to DX:AX
        # and the left is tested a half at a time from memory, SEGMENT FIRST —
        # `cmp [seg],dx; jnz ne; cmp [off],ax; jz eq`
        # (FILL_DEVICE_FCB_REQUEST matching the redirector's record, 0x89DD).
        if cop in ('==', '!=') and _long_lval(lhs) and _long_lval(rhs):
            if self.axdx_var != rhs[1]:
                self.gen_long(('id', rhs[1]))  # rhs → DX:AX
            memn = lhs[1]
            if memn in self.locals:
                d = self.ld(memn)
                hi = (0x39, 0x56, (d + 2) & 0xFF)
                lo = (0x39, 0x46, d & 0xFF)
            else:
                a = sa(memn)
                hi = (0x39, 0x16, *w16(a + 2))
                lo = (0x39, 0x06, *w16(a))
            if (cop == '==') == bool(taken):  # branch when the halves MATCH
                ne = self.fresh('cmpne')
                self.emit(*hi)
                self.emit_jcc(0x75, ne)  # jnz — a differing half decides it
                self.emit(*lo)
                self.emit_jcc(0x74, label)  # jz
                self.lbl(ne)
            else:  # branch when EITHER half differs
                self.emit(*hi)
                self.emit_jcc(0x75, label)
                self.emit(*lo)
                self.emit_jcc(0x75, label)
            return
        if cop in ('<', '>', '<=', '>=') and (
            (_long_lval(lhs) and _long_lval(rhs))
            or (
                _long_lval(rhs)
                and lhs[0] in ('bin', 'cast')
                and self._is_long_expr(lhs)
            )
        ):
            if not self.is_uchar_cmp(lhs, rhs):
                ni('signed long ordered cmp', cond)
            if _long_lval(lhs) and _long_lval(rhs):
                if self.axdx_var != rhs[1]:  # reuse DX:AX if it still holds rhs
                    self.gen_long(('id', rhs[1]))  # rhs → DX:AX
                memn, opc = lhs[1], 0x39  # cmp [mem], dxreg
            else:
                self.gen_long(lhs)  # lhs expr → DX:AX
                memn, opc = rhs[1], 0x3B  # cmp dxreg, [mem]
            if memn in self.locals:
                d = self.ld(memn)
                hi = (opc, 0x56, (d + 2) & 0xFF)
                lo = (opc, 0x46, d & 0xFF)
            else:
                a = sa(memn)
                hi = (opc, 0x16, *w16(a + 2))
                lo = (opc, 0x06, *w16(a))
            self._ord_split_cmp(cop, taken, label, hi, lo)
            return
        # BOTH sides computed 32-bit ordered compare, `(A >> S) <ord> (B >> S)`.
        # Neither side can stay in memory, so MSC evaluates the RIGHT side into
        # DX:AX and spills it — but LAZILY, each half moving only just before
        # the instruction that would overwrite it, which interleaves the saves
        # into the left side's own code:
        #     <B >> S>            ; RHS in DX:AX
        #     les bx,[A]          ; harmless, emitted first
        #     mov cx,ax / mov si,dx   ; spill, just before AX/DX are reloaded
        #     mov ax,[es:bx+d] / mov dx,[es:bx+d+2]
        #     les bx,[S]          ; harmless
        #     mov di,cx           ; low migrates CX->DI, just before CL dies
        #     mov cl,[es:bx+d]    ; ... to the shift count
        #     <A's own arithmetic> ; MSC does every memory read before it
        #     call __lshr
        #     cmp dx,si / cmp ax,di
        # (FCB_RANDOM_BLOCK_WRITE's extend test at 0x301E.)
        if cop in ('<', '>', '<=', '>=') and _shift_pair(lhs) and _shift_pair(rhs):
            (la, ls), (rb, rs) = _shift_pair(lhs), _shift_pair(rhs)
            lval, ldelta = (la[2], la[3][1]) if nbin(la) and la[1] == '-' else (la, 0)
            lf = self.far_lvalue(lval)
            if ls == rs and lf and lf[2] == 'long':
                if not self.is_uchar_cmp(lhs, rhs):
                    ni('signed long ordered cmp', cond)
                self.gen_long(('bin', '>>', rb, rs))  # RHS → DX:AX
                self.emit_les(lf[0])  # les bx,[A]
                self.emit(0x8B, 0xC8)  # mov cx, ax   (spill low)
                self.emit(0x8B, 0xF2)  # mov si, dx   (spill high)
                d = lf[1]
                self.e26(0x8B, mod8(d) | 0x07, *d8(d))  # mov ax,[es:bx+d]
                self.e26(0x8B, 0x57, (d + 2) & 0xFF)  # mov dx,[es:bx+d+2]
                cf = self.far_lvalue(ls)
                if not (cf and cf[2] == 'byte'):
                    ni('shift-count', ls)
                self.emit_les(cf[0])  # les bx,[S]
                self.emit(0x8B, 0xF9)  # mov di, cx   (low migrates before CL dies)
                cd = cf[1]
                self.e26(0x8A, mod8(cd) | 0x08 | 0x07, *d8(cd))  # mov cl,[es:bx+d]
                if ldelta:
                    self.emit(0x2D, *w16(ldelta))  # sub ax, delta
                    self.emit(0x83, 0xDA, 0x00)  # sbb dx, 0
                self.emit_call(SYMS['__lshr'][1])
                self.clob()
                self.si = self.di = None
                self._ord_split_cmp(
                    cop, taken, label, (0x3B, 0xD6), (0x3B, 0xC7)
                )
                return
        # (long >> 16) <op> const — the high word lives in DX, so MSC emits no
        # shift; just test DX (reused if it already holds x's high word, e.g.
        # right after `x = f()`).
        if nbin(lhs) and lhs[1] == '>>' and lhs[3] == ('num', 16) and num(rhs):
            x = lhs[2]
            if not (self.dx == ('hi', x[1]) if nid(x) else False):
                self.load_long_axdx(x)  # mov dx, x_high (also reloads ax)
            if rhs[1] == 0:
                self.emit(0x0B, 0xD2)  # or dx, dx
            else:
                self.emit(0x81, 0xFA, rhs[1], (rhs[1] >> 8))  # cmp dx,imm
            self.emit_cc(cop, taken, False, label)
            return
        # (operand & imm) == 0 / != 0  →  `test <operand>, imm; jcc`  (no AND/cmp),
        # for a far lvalue / uchar|int|uint local / word global.
        if (
            nbin(lhs)
            and lhs[1] == '&'
            and num(lhs[3])
            and z0(rhs)
            and self._emit_and_test(lhs[2], lhs[3][1])
        ):
            self.emit_cc(cop, taken, False, label)
            return
        # Assignment in the condition, e.g. (ch = read_byte()) != 0x0D — emit
        # the assignment (leaving the value in AL/AX), then compare the target.
        if lhs[0] == 'assign':
            target = lhs[1]
            self._al_arr_store = False
            self.gen_assign(target, lhs[2])
            # A far/array byte store leaves the value in AL with no named cache;
            # compare AL directly instead of re-reading through the pointer.
            far = self.far_lvalue(target)
            if num(rhs) and (self._al_arr_store or (far and far[2] == 'byte')):
                self.cmp_al_imm(rhs[1])  # or al,al / cmp al,imm8
                self._al_arr_store = False
                self.emit_cc(cop, taken, True, label)
                return
            lhs = target
        # Special: byte-array indexed by a CONST <op> num → cmp byte[addr+c], imm
        if lhs[0] == 'idx' and self.gkind(lhs[1]) == 'arr' and num(lhs[2]) and num(rhs):
            a = (sa(n11(lhs)) + lhs[2][1]) & 0xFFFF
            self.emit(0x80, 0x3E, *w16(a), rhs[1])  # cmp byte[a],imm8
            self.emit_cc(cop, taken, False, label)
            return
        # Special: byte-array indexed by a UCHAR LOCAL <op> num — the index
        # widens through BL/BH (not a word load), so the compare stays a byte:
        #   mov bl,[bp+d]; sub bh,bh; cmp byte [bx+ARR], imm8
        # (WRITE_DIR_ENTRY's `SUBST_TABLE[drive] != 0FFh` guard).
        if (
            lhs[0] == 'idx'
            and nid(lhs[1])
            and self.gkind(lhs[1]) == 'arr'
            and self.stkid(lhs[2])
            and self.ucharty(lhs[2])
            and num(rhs)
        ):
            self.emit(0x8A, 0x5E, self.ld(lhs[2][1]))  # mov bl, [bp+d]
            self.emit(0x2A, 0xFF)  # sub bh, bh
            self.emit(0x80, 0xBF, *w16(sa(n11(lhs))), rhs[1])  # cmp byte[bx+ARR],imm
            self.bx = None
            self.emit_cc(cop, taken, True, label)
            return
        # byte-array indexed by a REG VAR (± const, folded into the array-base
        # displacement) <op> num  →  cmp byte [si/di + ARR±c], imm8 — direct
        # memory compare, no AL load (COPY_DPB_AND_LOOKUP's `SCRATCH[si] != 0`
        # length scan and `SCRATCH[si-1] != 0x5C` backslash test).
        if lhs[0] == 'idx' and self.gkind(lhs[1]) == 'arr' and num(rhs):
            # AL already holds this element's value (a store just left it
            # tagged): compare the register, not memory — `cmp al, imm8`.
            if (self.rvid(lhs[2])
                    and self.al == ('gidx', sa(n11(lhs)),
                                    self.regvars[lhs[2][1]])):
                self.cmp_al_imm(rhs[1])
                self.emit_cc(cop, taken, False, label)
                return
            idx, c = lhs[2], None
            if self.rvid(idx):
                c = 0
            elif (nbin(idx) and idx[1] in ('+', '-') and self.rvid(idx[2])
                  and num(idx[3])):
                c = idx[3][1] if idx[1] == '+' else -idx[3][1]
            if c is not None:
                reg = self.regvars[(idx if nid(idx) else idx[2])[1]]
                a = (sa(n11(lhs)) + c) & 0xFFFF
                self.emit(0x80, sd(0xBC, reg), *w16(a), rhs[1])  # cmp byte[reg+ARR±c],imm
                self.emit_cc(cop, taken, False, label)
                return
        # The same two shapes for a LOCAL byte array: a constant subscript folds
        # into the frame displacement, a register-var subscript rides the
        # [bp+si/di] base — either way a direct memory compare with no AL load
        # (EXEC_PROGRAM_FROM_PATH's path-buffer scans at 0x54CA / 0x5517).
        if (
            lhs[0] == 'idx'
            and nid(lhs[1])
            and str(self.lty(lhs[1])).startswith('arr')
            and num(rhs)
        ):
            off, idx, c = self.ld(n11(lhs)), lhs[2], None
            if num(idx):
                # cmp byte [bp+off+k], imm8
                self.emit(0x80, 0x7E, (off + idx[1]) & 0xFF, rhs[1])
                self.emit_cc(cop, taken, False, label)
                return
            if self.rvid(idx):
                c = 0
            elif (nbin(idx) and idx[1] in ('+', '-') and self.rvid(idx[2])
                  and num(idx[3])):
                c = idx[3][1] if idx[1] == '+' else -idx[3][1]
            if c is not None:
                reg = self.regvars[(idx if nid(idx) else idx[2])[1]]
                # cmp byte [bp+si/di+off±c], imm8
                self.emit(0x80, sd(0x7A, reg), (off + c) & 0xFF, rhs[1])
                self.emit_cc(cop, taken, False, label)
                return
        # Special: byte-array indexed by an extern var <op> num, e.g.
        # LINE_BUF[PARSE_POS] == 0x20  →  mov bx,[var] (cached); cmp byte
        # [bx+ARR], imm.  The BX load is shared across compares on the same
        # index (e.g. the two arms of an || condition).
        if (
            lhs[0] == 'idx'
            and self.gkind(lhs[1]) == 'arr'
            and self.gkind(lhs[2]) == 'var'
            and num(rhs)
        ):
            arr_addr = sa(n11(lhs))
            vaddr = SYMS[lhs[2][1]][1]
            key = ('idxvar', lhs[2][1])
            if self.bx != key:
                self.emit(0x8B, 0x1E, *w16(vaddr))
                self.bx = key
            self.emit(0x80, 0xBF, *w16(arr_addr), rhs[1])  # cmp byte [bx+ARR], imm8
            self.emit_cc(cop, taken, False, label)
            return
        # word global <op> const  →  cmp word [addr], imm  (no AX load)
        # var global <op> num — reuse AX when it still holds the global (just
        # assigned, e.g. `g = f(); if (g == X)`): cmp ax, num.  MSC always takes
        # the ACCUMULATOR form `3D iw` here, never the sign-extended `83 F8 ib`
        # (same 3 bytes) — CON_PUTC_OR_FCB1's tab-stop `if (COL >= 50h)`.
        if self.gkind(lhs) == 'var' and num(rhs) and self.ax == lhs[1]:
            n = rhs[1]
            if n == 0:
                self.emit(0x0B, 0xC0)  # or ax, ax
            else:
                self.emit(0x3D, *w16(n))  # cmp ax, imm16
            self.emit_cc(cop, taken, lhs[1] in self.unsigned, label)
            return
        if self.gkind(lhs) == 'var' and num(rhs):
            a = SYMS[lhs[1]][1]
            n = rhs[1]
            # `word_global == 0` while a reg-var still holds 0 → MSC reuses it:
            # `cmp [addr], si/di` (a byte shorter than the immediate form).
            zreg = next((r for r in ('si', 'di') if self._regvar_zero.get(r)), None)
            if n == 0 and zreg:
                self.emit(0x39, (0x36 if zreg == 'si' else 0x3E), *w16(a))
                self.emit_cc(cop, taken, lhs[1] in self.unsigned, label)
                return
            self._emit_cmp_imm(lhs, n)  # cmp word [addr], imm
            self.emit_cc(cop, taken, lhs[1] in self.unsigned, label)
            return
        # far_X[reg] <op> far_Y[reg] (same reg index) → load RHS byte to AL, then
        # `cmp [es:bx+si/di], al` over the LHS base (a[si] == b[si]).
        firl = self.far_indexed_reg(lhs)
        if firl and self.far_indexed_reg(rhs):
            self.expr_to_al(rhs)  # al = far_Y[reg]
            self.emit_les(firl[0])
            self.e26(0x38, 0x00 if firl[1] == 'si' else 0x01)  # cmp [es:bx+si/di],al
            self.emit_cc(cop, taken, True, label)
            return
        # far_X[reg] <op> const → les bx; cmp byte [es:bx+si/di], imm8
        if firl and num(rhs):
            self.emit_les(firl[0])
            self.e26(0x80, 0x38 if firl[1] == 'si' else 0x39, rhs[1])
            self.emit_cc(cop, taken, True, label)
            return
        # far byte <op> <int local/param>  →  zero-extend the byte into AX and
        # compare against the frame slot: `les bx,[p]; mov al,[es:bx+d];
        # sub ah,ah; cmp ax,[bp+n]` (EDIT_TEMPLATE_PROCESS clamping ECHO_CURSOR
        # to the template's own length).
        _fb = self.far_lvalue(lhs)
        if _fb and _fb[2] == 'byte' and self.locid(rhs) and wint(self.lt(rhs[1])):
            self.expr_to_ax(lhs)
            self.emit(0x3B, 0x46, self.ld(rhs[1]))  # cmp ax, [bp+n]
            # a far BYTE arrives zero-extended, so the compare is unsigned; the
            # value stays live in AX for a following store of the same lvalue
            self.ax = ('zxfar', repr(lhs))
            self.emit_cc(cop, taken, True, label)
            return
        # <uchar call> <op> <uchar local>  →  the result stays in AL and the
        # frame slot is the memory operand: `call f; cmp al,[bp+d]`
        # (UNJOIN_DRIVE testing GET_DRIVE_COUNT against its drive at 0x7637).
        if (
            ncall(lhs)
            and nid(lhs[1])
            and n11(lhs) in UCHAR_FUNCS
            and self.locid(rhs)
            and self.lt(rhs[1]) in ('uchar', 'char')
        ):
            self.gen_call(lhs)
            self.emit(0x3A, 0x46, self.ld(rhs[1]))  # cmp al, [bp+d]
            self.al = self.ax = None
            self.emit_cc(cop, taken, True, label)
            return
        # far byte <op> <uchar call>  →  the CALL runs first (its result stays in
        # AL) and only then the `les`, because the callee clobbers ES:BX —
        # `call f; les bx,[p]; cmp [es:bx+d],al` (JOIN's
        # `regs->r_bl == get_current_drive()`).
        _fl = self.far_lvalue(lhs)
        if (
            _fl
            and _fl[2] == 'byte'
            and ncall(rhs)
            and nid(rhs[1])
            and n11(rhs) in UCHAR_FUNCS
        ):
            self.gen_call(rhs)
            self.emit_les(_fl[0])
            self.e26(0x38, mod8(_fl[1]) | 0x07, *d8(_fl[1]))  # cmp [es:bx+d], al
            self.al = self.ax = None
            self.emit_cc(cop, taken, True, label)
            return
        # far byte <op> uchar local  →  les bx; mov al,[local]; cmp [es:bx+d],al
        # far_var[ far_var[k] + c ] == imm : a far subscript indexed by a byte
        # read from the SAME far pointer — `mov si,[es:bx+k]; and si,0FFh;
        # cmp byte[es:bx+si+c],imm` (ES:BX reused from a preceding compare on the
        # same far ptr).  INIT_INPUT_CURSOR's `INPUT_FCB_PTR[INPUT_FCB_PTR[1]+2]`.
        if (lhs[0] == 'idx' and self.gfar(lhs[1]) and num(rhs)
                and lhs[2][0] == 'bin' and lhs[2][1] == '+' and num(lhs[2][3])
                and lhs[2][2][0] == 'idx' and nid(lhs[2][2][1])
                and lhs[2][2][1][1] == lhs[1][1] and num(lhs[2][2][2])):
            k, c = lhs[2][2][2][1], lhs[2][3][1]
            self.emit_les(lhs[1][1])
            self.e26(0x8B, mod8(k) | 0x30 | 0x07, *d8(k))  # mov si,[es:bx+k]
            self.emit(0x81, 0xE6, 0xFF, 0x00)  # and si, 0FFh
            self.e26(0x80, mod8(c) | 0x38, *d8(c), rhs[1])  # cmp byte[es:bx+si+c],imm
            self.si = None
            self.emit_cc(cop, taken, True, label)
            return
        fl = self.far_lvalue(lhs)
        if fl and fl[2] == 'byte' and self.ucharty(rhs):
            disp = self.les_fl(fl)
            self.expr_to_al(rhs)
            modrm = mod8(disp) | 0x07
            self.e26(0x38, modrm, *d8(disp))  # cmp [es:bx+d],al
            self.emit_cc(cop, taken, True, label)  # unsigned
            return
        # far_var[<scaled>].<byte> <op> <far byte> : the LHS is a table entry, so
        # building its base needs AX — MSC evaluates the RIGHT side first and
        # parks it in CX, then uses the MIRRORED addressing (scaled index in BX,
        # table pointer in ES:SI):
        #   les bx,[p]; mov al,[es:bx+e]; mov cx,ax; mov al,K; mul byte[i];
        #   mov bx,ax; les si,[var]; cmp [es:bx+si+d],cl
        # (UNJOIN_DRIVE matching each CDS entry's drive letter, 0x75BB.)  This
        # has to precede the plain far-byte-vs-far-byte case below, which would
        # otherwise claim it and emit the bx-folded form.
        frb = self.far_lvalue(rhs)
        if (
            fl
            and fl[2] == 'byte'
            and frb
            and frb[2] == 'byte'
            and isinstance(fl[0], tuple)
            and fl[0][0] == 'idx'
        ):
            _, tname, index = fl[0]
            disp = fl[1]
            self.expr_to_al(rhs)  # the far byte → AL
            self.emit(0x8B, 0xC8)  # mov cx, ax
            self.expr_to_ax(index)  # scaled index → AX
            self.emit(0x8B, 0xD8)  # mov bx, ax
            self.emit(0xC4, 0x36, *w16(sa(tname)))  # les si, [var]
            self.e26(0x38, mod8(disp) | 0x08, *d8(disp))  # cmp [es:bx+si+d], cl
            self.ax = self.al = self.bx = self.si = None
            self.esbx = ('seg', tname)
            self.emit_cc(cop, taken, True, label)  # unsigned
            return
        # far byte <op> far byte : the rhs byte may still be live in AL (source
        # reuse from a preceding `g = rhs`) — load it only if not, then compare
        # the lhs far byte to it (both share ES:BX when off the same far ptr).
        fr2 = self.far_lvalue(rhs)
        if fl and fl[2] == 'byte' and fr2 and fr2[2] == 'byte':
            if self.al != ('rhs', rhs):
                d2 = self.les_fl(fr2)
                self.e26(0x8A, mod8(d2) | 0x07, *d8(d2))  # mov al,[es:bx+d2]
            disp = self.les_fl(fl)
            self.e26(0x38, mod8(disp) | 0x07, *d8(disp))  # cmp [es:bx+d],al
            self.emit_cc(cop, taken, True, label)  # unsigned
            return
        # Special: far-pointer field <op> num  →  les bx + cmp [es:bx+disp], imm
        far = self.far_lvalue(lhs)
        if far and num(rhs):
            fv, disp, kind = far
            modrm, dbytes = self.far_rm(fv, disp)
            modrm |= 0x38  # /7 (cmp)
            n = rhs[1]
            if kind == 'byte':
                self.e26(0x80, modrm, *dbytes, n)  # cmp byte [es:bx…], imm8
            elif i8(n):
                self.e26(0x83, modrm, *dbytes, n)  # cmp word [es:bx…], imm8 sx
            else:
                self.e26(0x81, modrm, *dbytes, *w16(n))  # cmp word [es:bx…], imm16
            self.emit_cc(cop, taken, self.far_uns(lhs), label)
            return
        # Special: far-pointer word field <op> memory var  →  les bx; mov
        # ax,[var]; cmp [es:bx+disp], ax   (e.g. drv->count > idx).  Register
        # vars have their own direct `cmp [es:bx+disp], si/di` path; an
        # si-indexed entry keeps the scaled form (LOOKUP_DRIVER_SLOT_FREE's
        # age scan).
        if far and far[2] == 'word' and (self.stkid(rhs) or self.gvw(rhs)):
            fv, disp, _ = far
            modrm, dbytes = self.far_rm(fv, disp)
            self.expr_to_ax(rhs)  # mov ax, [var]
            self.e26(0x39, modrm, *dbytes)  # cmp [es:bx…], ax
            self.emit_cc(cop, taken, self.far_uns(lhs), label)
            return
        # Special: *p1 == *p2  (or with == direction flipped — same result)
        if (
            cop == '=='
            and nderef(lhs)
            and nderef(rhs)
            and nid(lhs[1])
            and nid(rhs[1])
            and n11(lhs) in self.locals
            and n11(rhs) in self.locals
        ):
            # MSC pattern: rhs ptr → BX, lhs ptr → DI; mov al,[di]; cmp [bx],al
            rdisp = self.ldi(rhs)
            self.ldbx(rdisp)  # mov bx, [bp-N]
            self.bx = n11(rhs)
            ldisp = self.ldi(lhs)
            self.emit(0x8B, 0x7E, ldisp)  # mov di, [bp-N]
            self.di = n11(lhs)
            self.emit(0x8A, 0x05)  # mov al, [di]
            self.al = None
            self.emit(0x38, 0x07)  # cmp [bx], al
            self.emit_cc(cop, taken, False, label)
            return
        # (a % b) == 0 / != 0  →  div; or dx,dx; jz/jnz  (remainder stays in DX)
        if cop in ('==', '!=') and z0(rhs) and nbin(lhs) and lhs[1] == '%':
            self.expr_to_ax(lhs[2])
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self._emit_div_operand(lhs[3])
            self.emit(0x0B, 0xD2)  # or dx, dx
            self.emit_cc(cop, taken, False, label)
            return
        # Special: *ptr <op> num — byte for a char ptr, word for an int/uint ptr
        if (
            cop in ('==', '!=')
            and nderef(lhs)
            and nid(lhs[1])
            and n11(lhs) in self.locals
            and num(rhs)
        ):
            ty = self.lt(n11(lhs))
            self.ensure_bx(n11(lhs))
            if ty in ('ptr_int', 'ptr_uint'):
                n = rhs[1]
                if -128 <= n <= 127:
                    self.emit(0x83, 0x3F, n)  # cmp word [bx], imm8 sx
                else:
                    self.emit(0x81, 0x3F, *w16(n))  # cmp word [bx], imm16
            else:
                self.emit(0x80, 0x3F, rhs[1])  # cmp byte [bx], imm8
            self.emit_cc(cop, taken, False, label)
            return
        # Special: *near-int-ptr <op> int-local  →  (ax=rhs); mov bx,[p]; cmp [bx],ax
        if (
            nderef(lhs)
            and self.lty(lhs[1]) in ('ptr_int', 'ptr_uint')
            and self.stkid(rhs)
        ):
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.ensure_bx(n11(lhs))  # mov bx,[p] first
            self.expr_to_ax(rhs)  # then ax = rhs (reused if cached)
            self.emit(0x39, 0x07)  # cmp [bx], ax
            self.emit_cc(cop, taken, unsigned, label)
            return
        # Special: byte global (uchar) <op> num  →  cmp byte [addr], imm8
        if self.gkind(lhs) == 'bvar' and num(rhs):
            if self.al == lhs[1]:  # value still live in AL from a prior store
                self.cmp_al_imm(rhs[1])
            else:
                self.emit(0x80, 0x3E, *w16(SYMS[lhs[1]][1]), rhs[1])
            self.emit_cc(cop, taken, True, label)
            return
        # Special: far_var[reg] <op> num  →  les bx,[addr]; cmp byte es:[bx+idx],imm8
        fi = self.far_indexed_reg(lhs)
        if fi and num(rhs):
            name, reg = fi
            self.emit_les(name)
            rm = 0x01 if reg == 'di' else 0x00  # [bx+di] / [bx+si]
            self.e26(0x80, 0x38 | rm, rhs[1])  # cmp byte es:[bx+idx],imm8
            self.emit_cc(cop, taken, True, label)
            return
        # far_X[reg±const] / far_X[--reg] <op> num — the reg±const displacement
        # folds into the addressing mode (`les bx,[p]; cmp byte [es:bx+si-1],imm`);
        # a pre-inc/dec bumps the reg between the les and the compare
        # (PARSE_PATH_WITH_DRIVE's trailing-slash checks and ".." trim loop).
        fri = self.far_reg_idx(lhs)
        if fri and num(rhs) and not fri[5]:  # post-inc compare: no MSC exemplar
            name, reg, disp, regname, pre, _ = fri
            self.emit_les(name)
            if pre:
                self.emit(sd(0x4E if pre == 'dec' else 0x46, reg))  # inc/dec si/di
                if reg == 'si':
                    self.si = None
                else:
                    self.di = None
            base_rm = 0x00 if reg == 'si' else 0x01
            modrm = ((0x40 | base_rm) if disp else base_rm) | 0x38  # /7 (cmp)
            self.e26(0x80, modrm, *((disp,) if disp else ()), rhs[1])
            self.emit_cc(cop, taken, True, label)
            return
        # Special: byte global <op> byte global  →  the RIGHT one goes to AL and
        # the left stays in memory: `mov al,[g2]; cmp [g1],al`
        # (DOS_FN_56_RENAME_FILE's source/destination drive-code check).
        # <uchar local> <op> <byte global> : the global goes to AL and the frame
        # slot stays as the memory operand — `mov al,[g]; cmp [bp+d],al`
        # (INIT_PSP's drive loop against INSTALLED_COUNT at 0x1908).
        gb0 = self.byte_global_addr(rhs)
        if (
            gb0 is not None
            and self.locid(lhs)
            and self.lt(lhs[1]) in ('uchar', 'char')
        ):
            if self.al != rhs[1]:
                self.emit(0xA0, *w16(gb0))  # mov al, [g]
                self.al = rhs[1]
            self.emit(0x38, 0x46, self.ld(lhs[1]))  # cmp [bp+d], al
            self.emit_cc(cop, taken, True, label)  # unsigned
            return
        g1, g2 = self.byte_global_addr(lhs), self.byte_global_addr(rhs)
        if g1 is not None and g2 is not None:
            if self.al != rhs[1]:
                self.emit(0xA0, *w16(g2))  # mov al, [g2]
                self.al = rhs[1]
            self.emit(0x38, 0x06, *w16(g1))  # cmp [g1], al
            self.emit_cc(cop, taken, True, label)
            return
        # Special: far byte lvalue <op> global_array[reg var]  →  the array byte
        # goes to AL and the far side stays in memory:
        #   les bx,[ptr]; mov al,[si+ARR]; cmp [es:bx+d],al
        # (DOS_FN_29_PARSE_FILENAME_FCB's separator scan).
        fa = self.far_lvalue(lhs)
        if (
            fa
            and fa[2] == 'byte'
            and rhs[0] == 'idx'
            and nid(rhs[1])
            and self.gkind(rhs[1]) == 'arr'
            and self.rvid(rhs[2])
        ):
            disp = fa[1]
            self.emit_les(fa[0])
            self.emit(0x8A, sd(0x84, self.rv(rhs[2])), *w16(sa(rhs[1][1])))
            self.e26(0x38, mod8(disp) | 0x07, *d8(disp))  # cmp [es:bx+d], al
            self.ax = self.al = None
            self.emit_cc(cop, taken, True, label)
            return
        # Special: far_var[i].<byte> <op> byte global  →  the scaled index goes
        # in BX and the table pointer in ES:SI (the MIRROR of the usual
        # si-indexed read) so the global can stay in AL:
        #   mov al,K; mul byte[i]; mov bx,ax; les si,[var]; mov al,[g];
        #   cmp [es:bx+si+d],al   (DOS_FN_3A_RMDIR's CDS drive-letter scan).
        fb = self.far_lvalue(lhs)
        gb = self.byte_global_addr(rhs)
        if fb and fb[2] == 'byte' and gb is not None and \
                isinstance(fb[0], tuple) and fb[0][0] == 'idx':
            _, name, index = fb[0]
            disp = fb[1]
            self.expr_to_ax(index)  # scaled index → AX
            self.emit(0x8B, 0xD8)  # mov bx, ax
            self.emit(0xC4, 0x36, *w16(sa(name)))  # les si, [var]
            self.emit(0xA0, *w16(gb))  # mov al, [g]
            self.e26(0x38, mod8(disp), *d8(disp))  # cmp [es:bx+si+d], al
            self.ax = self.al = self.bx = self.si = None
            self.esbx = ('seg', name)  # ES still holds the table's segment
            self.emit_cc(cop, taken, True, label)
            return
        # Special: far_var[<scaled>].<word> <op> <far word lvalue> — building the
        # scaled base needs AX (mov al,K; mul), so MSC evaluates the RIGHT side
        # first and parks it in CX:
        #   mov ax,[es:bx+0Fh]; mov cx,ax; mov al,51h; mul ..; les bx,[414h];
        #   cmp [es:bx+si-4],cx        (WRITE_DIR_ENTRY's JOIN parent test)
        fl2, fr2 = self.far_lvalue(lhs), self.far_lvalue(rhs)
        if (
            fl2
            and fl2[2] == 'word'
            and isinstance(fl2[0], tuple)
            and fl2[0][0] == 'idx'
            and fr2
            and fr2[2] == 'word'
        ):
            self.expr_to_ax(rhs)  # mov ax, [es:bx+d]
            self.emit(0x8B, 0xC8)  # mov cx, ax
            modrm, dbytes = self.far_rm(fl2[0], fl2[1])
            self.e26(0x39, modrm | 0x08, *dbytes)  # cmp [es:bx…], cx
            self.cl = None
            self.emit_cc(cop, taken, self.far_uns(lhs), label)
            return
        # Special: reg_var <op> word memory — there is no `cmp reg,mem` that
        # keeps the operand order, so MSC compares the MEMORY operand against
        # the register and SWAPS the test (`si < COUNT` becomes
        # `cmp [COUNT],si` + jna for the false branch).  INSTALL_DRIVER's SFT
        # sweep.
        if self.rvid(lhs) and (
            self.gvw(rhs) or (self.stkid(rhs) and wint(self.lt(rhs[1])))
        ):
            if self._emit_cmp_reg(rhs, lhs[1]):
                swap = {'<': '>', '>': '<', '<=': '>=', '>=': '<='}
                self.emit_cc(
                    swap.get(cop, cop), taken, self.is_uchar_cmp(lhs, rhs), label
                )
                return
        # Special: far word lvalue / int local <op> reg_var → cmp <mem>, si/di
        fw = self.far_lvalue(lhs)
        if (
            fw and fw[2] == 'word' or self.stkid(lhs) and wint(self.lt(lhs[1]))
        ) and self.rvid(rhs):
            self._emit_cmp_reg(lhs, rhs[1])  # cmp es:[bx+d]/[bp+d], si/di
            self.emit_cc(cop, taken, self.is_uchar_cmp(lhs, rhs), label)
            return
        # Special: reg-var (SI/DI) <op> num
        if self.rvid(lhs) and num(rhs):
            reg = self.rv(lhs)
            n = rhs[1] & 0xFFFF
            if rhs[1] == 0:
                self.emit(0x0B, 0xF6 if reg == 'si' else 0xFF)  # or si,si / or di,di
            else:
                rb = sd(0xFE, reg)
                if -128 <= rhs[1] <= 127:
                    self.emit(0x83, rb, n)  # cmp si/di, imm8 sx
                else:
                    self.emit(0x81, rb, *w16(n))
            self.emit_cc(cop, taken, self.is_uchar_cmp(lhs, rhs), label)
            return
        # Special: uchar local/param <op> reg_var → al=local; sub ah,ah; cmp ax,si/di
        # (the byte widens to AX, so it can't use the `cmp [bp+disp],si/di` form).
        if self.ucharty(lhs) and self.rvid(rhs):
            self.expr_to_ax(lhs)  # mov al,[bp+d]; sub ah,ah
            self.emit(0x3B, sd(0xC6, self.rv(rhs)))  # cmp ax,si/di
            self.emit_cc(cop, taken, True, label)  # unsigned (uchar)
            return
        # Special: <computed expr> <op> uchar GLOBAL → lhs→AX; widen the byte
        # global through CX (`mov cl,[g]; sub ch,ch`); cmp ax,cx.  Unsigned —
        # echo_input_loop's `TYPED_COUNT + 1 >= TYPED_LIMIT` buffer check.
        if self.gkind(rhs) == 'bvar' and lhs[0] in ('bin', 'call', 'cast'):
            self.expr_to_ax(lhs)
            self.emit(0x8A, 0x0E, *w16(sa(rhs[1])))  # mov cl, [g]
            self.emit(0x2A, 0xED)  # sub ch, ch
            self.emit(0x3B, 0xC1)  # cmp ax, cx
            self.cl = None
            self.emit_cc(cop, taken, True, label)
            return

        # Special: <computed expr> <op> reg_var  →  eval lhs to AX; cmp ax, si/di
        # (only for genuine expressions — simple id operands have their own paths)
        if self.rvid(rhs) and not (
            nid(lhs) and (lhs[1] in self.locals or lhs[1] in SYMS)
        ):
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.expr_to_ax(lhs)
            self.emit(0x3B, sd(0xC6, self.rv(rhs)))  # cmp ax,si/di
            self.emit_cc(cop, taken, unsigned, label)
            return
        # Special: extern int var <op> reg_var  →  cmp [addr], si/di
        if self.gkind(lhs) == 'var' and self.rvid(rhs):
            addr = SYMS[lhs[1]][1]
            modrm = 0x36 if self.rv(rhs) == 'si' else 0x3E
            self.emit(0x39, modrm, *w16(addr))  # cmp [addr], si/di
            self.emit_cc(cop, taken, self.is_uchar_cmp(lhs, rhs), label)
            return
        # Special: extern int var <op> expr  →  mov ax, expr; cmp [addr], ax
        if self.gkind(lhs) == 'var':
            addr = SYMS[lhs[1]][1]
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.expr_to_ax(rhs)
            self.emit(0x39, 0x06, *w16(addr))  # cmp [addr], ax
            self.emit_cc(cop, taken, unsigned, label)
            return
        # Special: <computed expr> / byte-global <op> word var global  →  eval
        # lhs to AX (a bvar zero-extends: mov al,[g]; sub ah,ah); cmp ax,[g].
        if self.gkind(rhs) == 'var' and (not nid(lhs) or self.gkind(lhs) == 'bvar'):
            a = SYMS[rhs[1]][1]
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.expr_to_ax(lhs)
            self.emit(0x3B, 0x06, *w16(a))  # cmp ax, [g]
            self.emit_cc(cop, taken, unsigned, label)
            return
        # uchar local <op> word local/global : zero-extend AL→AX, then cmp ax,[rhs]
        # uchar local <op> uchar local: MSC holds the RIGHT operand in AL and
        # compares memory against the register — `mov al,[bp+r]; cmp [bp+l],al`
        # — with no zero-extend, reusing AL when the byte is already there (the
        # store a preceding `x = <uchar call>` just made).  DOS_FN_3A_RMDIR's
        # `dot_path == dot_alias`, both at the fall-in and at the loop head.
        if self.ucharty(lhs) and self.ucharty(rhs):
            if self.al != rhs[1]:
                self.ldal(self.ld(rhs[1]))  # mov al, [bp+r]
                self.al = rhs[1]
            self.emit(0x38, 0x46, self.ld(lhs[1]))  # cmp [bp+l], al
            self.emit_cc(cop, taken, self.is_uchar_cmp(lhs, rhs), label)
            return
        if self.ucharty(lhs) and not num(rhs):
            unsigned = self.is_uchar_cmp(lhs, rhs)
            disp = self.ld(lhs[1])
            if self.al != lhs[1]:  # a preceding store may have left it in AL
                self.ldal(disp)  # mov al, [bp+disp]
            self.emit(0x2A, 0xE4)  # sub ah, ah
            if self.rvid(rhs):
                self.emit(0x3B, sd(0xC6, self.rv(rhs)))  # cmp ax, si/di
            elif self.locid(rhs):
                rd = self.ld(rhs[1])
                self.emit(0x3B, 0x46, rd)  # cmp ax, [bp+rd]
            elif self.gkind(rhs) == 'var':
                a = SYMS[rhs[1]][1]
                self.emit(0x3B, 0x06, *w16(a))  # cmp ax, [g]
            else:
                ni(cond)
            self.emit_cc(cop, taken, unsigned, label)
            # AL holds the byte, AX its zero-extension — a following use of this
            # uchar (e.g. passing it as an arg) can reuse AX (push ax).
            self.al = lhs[1]
            self.ax = ('zx', lhs[1])
            return
        unsigned = self.is_uchar_cmp(lhs, rhs)
        # uchar <op> const : cmp al, imm8 (when AL has it) or mem-form.  A zero
        # compare with AH known 0 (a loop test's `sub ah,ah` on the back-edge)
        # reuses the register: `cmp [bp+d],ah` — 1 byte shorter than the imm
        # form (RENAME_FCB's `match != 0` at the collision-loop body top).
        if self.ucharty(lhs) and num(rhs):
            if not (0 <= rhs[1] <= 0xFF):
                # A const OUTSIDE uchar range (`best == -1`): int promotion is
                # observable, so MSC widens the byte and compares the full word
                # — faithfully always-false for -1 (LOOKUP_DRIVER_SLOT_FREE's
                # original-source bug).
                self.expr_to_ax(lhs)  # mov al,[bp+d]; sub ah,ah
                self.cmp_ax_imm(rhs[1] & 0xFFFF)  # cmp ax, imm16
            elif self.al == lhs[1]:
                self.cmp_al_imm(rhs[1])
            elif rhs[1] == 0 and self._ah_zero:
                self.emit(0x38, 0x66, self.ld(lhs[1]))  # cmp [bp+d], ah
            else:
                self._emit_cmp_imm(lhs, rhs[1])  # cmp byte [bp-N], imm8
        # int-var <op> small const : cmp word [bp+disp], imm8 sign-extended.
        # Skip when AX already holds this local — the general case reuses it
        # (`or ax,ax` / `cmp ax,imm`), matching MSC right after `var = expr`.
        elif (
            self.wptr(lhs) and num(rhs) and -128 <= rhs[1] <= 127 and self.ax != lhs[1]
        ):
            self._emit_cmp_imm(lhs, rhs[1])  # cmp word [bp+disp], imm8 sx
        # int/ptr-var <op> int/ptr-expr : load expr to AX, cmp [bp-N], ax.  Skip
        # when AX already holds this local and rhs is a constant — the general
        # case below reuses AX directly (cmp ax, imm).
        elif self.wptr(lhs) and not (self.ax == lhs[1] and num(rhs)):
            self.expr_to_ax(rhs)
            disp = self.ld(lhs[1])
            self.emit(0x39, 0x46, disp)  # cmp [bp-N], ax
        # (unsigned int)<uchar call> <op> const : an explicit word cast forces
        # the FULL-AX accumulator compare with NO zero-extend — the declaration
        # carries the function's true byte return, the cast reproduces a caller
        # that was compiled against a word-returning prototype (DOS_FN_23's
        # `(unsigned int)parse_filename_to_fcb(...) != 1` → `cmp ax,1`).
        elif (
            num(rhs)
            and ncast(lhs)
            and lhs[1] in ('int', 'uint')
            and ncall(lhs[2])
            and nid(lhs[2][1])
            and n11(lhs[2]) in UCHAR_FUNCS
        ):
            self.gen_call(lhs[2])
            if rhs[1] == 0:
                self.emit(0x0B, 0xC0)  # or ax, ax
            else:
                self.emit(0x3D, *w16(rhs[1] & 0xFFFF))  # cmp ax, imm16
            self.emit_cc(cop, taken, True, label)
            return
        # uchar-returning call <op> const : the result is a byte in AL — test AL
        elif num(rhs) and ncall(lhs) and nid(lhs[1]) and n11(lhs) in UCHAR_FUNCS:
            self.gen_call(lhs)
            self.cmp_al_imm(rhs[1])
            self.emit_cc(cop, taken, True, label)
            return
        # general expr (e.g. a call result) <op> const : eval to AX, then test
        elif num(rhs):
            self.expr_to_ax(lhs)
            if rhs[1] == 0:
                self.emit(0x0B, 0xC0)  # or ax, ax
            elif rhs[1] == 0xFFFF and cop in ('==', '!=') and ncall(lhs):
                # call() == / != 0xFFFF : the result is a dead temp, so MSC
                # tests -1 with `inc ax` (ZF iff AX was 0FFFFh) instead of the
                # 3-byte `cmp ax,0FFFFh` (find_fcb_logical_limit's driver test).
                self.emit(0x40)  # inc ax
                self.ax = None
            elif ncall(lhs) and cop in ('==', '!='):
                # call() ==/!= small imm : the result is a dead temp in the
                # accumulator, so MSC uses the `cmp ax,imm16` accumulator form
                # (3D, same 3 bytes) rather than `83 F8 ib` (DOS_FN_23's
                # `parse_filename_to_fcb(...) != 1`).
                self.emit(0x3D, *w16(rhs[1] & 0xFFFF))  # cmp ax, imm16
            else:
                # accumulator form only — `83 F8 ib` never occurs in the ROM
                self.emit(0x3D, *w16(rhs[1]))  # cmp ax, imm16
        # general expr (bin/call/cast) <op> int/uint local : eval lhs to AX, then
        # `cmp ax, [bp+disp]`.  E.g. `(SECTOR_INDEX - CURRENT_CLUSTER) > len` — the
        # FAT chain-length limit test in read_back_fat_entry.
        elif (
            nid(rhs)
            and rhs[1] in self.locals
            and wint(self.lt(rhs[1]))
            and lhs[0] in ('bin', 'call', 'cast')
        ):
            self.expr_to_ax(lhs)
            disp = self.ld(rhs[1])
            self.emit(0x3B, 0x46, disp)  # cmp ax, [bp+disp]
        else:
            ni(cond)
        self.emit_cc(cop, taken, unsigned, label)

    def is_uchar_cmp(self, lhs, rhs):
        """True if either operand is unsigned (drives unsigned JCC selection)."""
        if getattr(self, '_force_sign', False):
            return False
        if getattr(self, '_force_uns', False):
            return True
        for side in (lhs, rhs):
            # arithmetic over unsigned operands stays unsigned, and a shift
            # keeps the signedness of the value being shifted — so recurse
            # (PARSE_PATH_WITH_DRIVE's `len + namelen > 0x41`, and
            # FCB_RANDOM_BLOCK_WRITE's `(x >> s) >= (IO_START >> s)`, where
            # the unsigned RHS makes the whole comparison unsigned).
            if nbin(side) and side[1] in ('+', '-', '>>', '<<'):
                if self.is_uchar_cmp(side[2], side[3]):
                    return True
                continue
            if not nid(side):
                continue
            n = side[1]
            if n in self.locals and (
                self.lt(n) in ('uchar', 'uint', 'reg_uint', 'reg_uchar')
                # a far pointer compares UNSIGNED (MSC emits jc/ja)
                or pf(self.lt(n))
            ):
                return True
            if n in self.unsigned:
                return True
        return False

    def _ord_split_cmp(self, cop, taken, label, hi, lo, ja_first=False):
        """High/low split of an unsigned 32-bit ordered compare: emit `hi`
        (the high-word cmp bytes), branch jb/ja per the (op, taken) table,
        then `lo` + the low-word finisher.  `ja_first` selects the [es:bx]
        orientation that tests ja before jb."""
        TBL = {
            ('>', True): ('skip', 'label', 0x77),
            ('>', False): ('label', 'skip', 0x76),
            ('>=', True): ('skip', 'label', 0x73),
            ('>=', False): ('label', 'skip', 0x72),
            ('<', True): ('label', 'skip', 0x72),
            ('<', False): ('skip', 'label', 0x73),
            ('<=', True): ('label', 'skip', 0x76),
            ('<=', False): ('skip', 'label', 0x77),
        }
        jb_tgt, ja_tgt, lo_op = TBL[(cop, taken)]
        skip = self.fresh('lcmp')
        tgt = {'label': label, 'skip': skip}
        self.emit(*hi)
        first, second = (
            ((0x77, ja_tgt), (0x72, jb_tgt))
            if ja_first
            else ((0x72, jb_tgt), (0x77, ja_tgt))
        )
        self.emit_jcc(first[0], tgt[first[1]])
        self.emit_jcc(second[0], tgt[second[1]])
        self.emit(*lo)
        self.emit_jcc(lo_op, label)
        self.lbl(skip)

    def far_uns(self, lhs):
        """Unsigned-compare flag for a far lvalue's declared cast type."""
        if nderef(lhs) and ncast(lhs[1]):
            return 'uint' in n11(lhs) or 'uchar' in n11(lhs)
        # BASE[idx]: the far pointer's declared element type (`unsigned char far
        # *rec` → rec[0] is an unsigned byte, GET_SET_ATTRS' `rec[0] > 1`).
        if lhs[0] == 'idx' and nid(lhs[1]) and pf(self.lty(lhs[1])):
            ty = self.lty(lhs[1])
            if 'uchar' in ty or 'uint' in ty:
                return True
            # struct-typed far pointer: `p->field` lowers to BASE[off] — the
            # sign comes from the FIELD at that offset (rec->r_al is an
            # unsigned byte, GET_SET_ATTRS' `rec->r_al > 1`).
            if ty.startswith('ptr_far_struct:') and num(lhs[2]):
                tag, off = ty.split(':', 1)[1], lhs[2][1]
                return any(
                    isinstance(v, tuple) and v[0] == off
                    and v[1] in ('uchar', 'uint', 'ulong')
                    for v in STRUCTS.get(tag, {}).values()
                )
        return False

    def push_seg_ax(self, seg_op):
        """push ss/ds (0x16/0x1E) then AX — the far-pointer arg tail."""
        self.emit(seg_op)
        self.emit(0x50)  # push ax
        self.ax = None
        self._ah_zero = False

    def tag_axdx(self, n):
        """DX:AX now holds long/far `n` (low untagged, hi tagged)."""
        self.ax = None
        self.dx = ('hi', n)
        self.axdx_var = n

    def store_byte_imm(self, base, rm, v):
        """`<far base>[reg idx] = imm8`, les first.  When the NEXT statement
        stores the SAME constant, materialise it once in AL so the sibling
        store reuses it (PARSE_FILESPEC's init loop); returns True then."""
        nxt = self._peek_next
        share = (
            nxt
            and nxt[0] == 'expr'
            and nxt[1][0] == 'assign'
            and n12(nxt) == ('num', v)
        )
        self.emit_les(base)
        if share:
            if self.al != v:
                self.emit(0xB0, v & 0xFF)  # mov al, imm
            self.e26(0x88, rm)  # mov es:[bx+idx], al
            self.al = v
            self.ax = None
            return True
        self.e26(0xC6, rm, v)  # mov byte es:[bx+idx], imm8
        return False

    def fv_axdx_sum(self, rhs):
        """Flatten `far_var + <terms>` and build offset:segment in AX:DX (var
        term to AX; add ax,[g] — else mov ax,[g] — mov dx,[g+2]; add ax,const).
        Emits nothing and returns False when the head isn't a far_var."""
        terms = []

        def _flat(n):
            if nbin(n) and n[1] == '+':
                _flat(n[2])
                _flat(n[3])
            else:
                terms.append(n)

        _flat(rhs)
        if self.gkind(terms[0]) != 'far_var':
            return False
        g = SYMS[terms[0][1]][1]
        rest = terms[1:]
        const, varts = self.split_terms(rest)
        name = terms[0][1]
        live = self.bx == ('fvoff', name) and (
            self.esbx in (name, ('seg', name))
            or (isinstance(self.esbx, tuple) and self.esbx[:2] == ('idxsi', name))
        )
        if varts:
            self.expr_to_ax(varts[0])  # var term → AX
            if live:
                # ES:BX still carry this table's segment:offset from a
                # preceding entry read — reuse them (LOOKUP_DRIVER_SLOT_FREE's
                # free-slot pointer right after the refcount test).
                self.emit(0x03, 0xC3)  # add ax, bx
                self.emit(0x8C, 0xC2)  # mov dx, es
            else:
                self.emit(0x03, 0x06, *w16(g))  # add ax, [g]
                self.emit(0x8B, 0x16, *w16(g + 2))  # mov dx, [g+2]
        else:
            self.ldaxm(g)  # mov ax, [g]
            self.emit(0x8B, 0x16, *w16(g + 2))  # mov dx, [g+2]
        if const:
            self.emit(0x05, *w16(const))  # add ax, const
        return True

    def add_cx_tail(self):
        self.emit(0x2A, 0xED)  # sub ch, ch
        self.emit(0x03, 0xC1)  # add ax, cx
        self.zaa()

    def push_al0(self):
        self.emit(0x2A, 0xE4)  # sub ah, ah
        self.emit(0x50)  # push ax
        self.zaa()
        self._ah_zero = True

    def push_al(self):
        """Widen the byte in AL and push it (shared arg-push tail)."""
        if not self._ah_zero:
            self.emit(0x2A, 0xE4)  # sub ah, ah
        self.emit(0x50)  # push ax
        self.zaa()
        self._ah_zero = True

    def push_dxax(self):
        """Push the long in DX:AX (hi then lo — shared arg-push tail)."""
        self.emit(0x52)  # push dx
        self.emit(0x50)  # push ax
        self.zad()
        self._ah_zero = False

    def emit_arms(self, stmts):
        """Emit a statement list, feeding each statement its successor via
        _peek_next (the lookahead several fusions key on)."""
        for i, ss in enumerate(stmts):
            self._peek_next = stmts[i + 1] if i + 1 < len(stmts) else None
            self.stmt(ss)

    def cmp_al_imm(self, n):
        if n == 0:
            self.emit(0x0A, 0xC0)  # or al, al
        else:
            self.emit(0x3C, n)  # cmp al, imm8

    def cmp_ax_imm(self, n):
        # MSC always uses the accumulator form `3D iw` (same length as the
        # sign-extended `83 F8 ib`); `83 F8` never occurs in the ROM.
        if n == 0:
            self.emit(0x0B, 0xC0)  # or ax, ax
        else:
            self.emit(0x3D, *w16(n))  # cmp ax, imm16

    def jcc(self, op, taken, unsigned):
        # Jcc opcode ^ 1 is the inverted condition, so only the taken tables
        # are stored; not-taken jumps are the XOR.
        t = (
            {'<': 0x72, '>': 0x77, '<=': 0x76, '>=': 0x73, '==': 0x74, '!=': 0x75}
            if unsigned
            else {'<': 0x7C, '>': 0x7F, '<=': 0x7E, '>=': 0x7D, '==': 0x74, '!=': 0x75}
        )[op]
        return t if taken else t ^ 1


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
    long_funcs = set()
    byte_params = {}
    far_params = {}
    for d in decls:
        if d[0] == 'extern':
            _, name, kind, addr, is_pascal, ret_uchar, param_bytes = d[:7]
            ret_long = len(d) > 7 and d[7]
            param_far = d[8] if len(d) > 8 else ()
            if addr is None:
                addr = addr_map.get(name)
            if addr is None:
                continue
            if kind.startswith('struct:'):
                # A struct INSTANCE at an absolute address: register the base
                # (kind 'arr', so `&NAME` / `(far *)&NAME` yield the address)
                # plus one synthetic global per field at addr+off, named
                # `NAME.field` — the desugar rewrites `NAME.field` to that id,
                # so every access is a plain DS-relative global (byte-exact,
                # no pointer indirection).  GLOBTY carries ptr-field types so
                # chained `NAME.ptrfield->x` still lowers.
                syms[name] = ('arr', addr)
                for fld, v in STRUCTS[kind[7:]].items():
                    if fld == '__size__':
                        continue
                    off, fty = v
                    if fty.startswith('arr_'):
                        fk = decl_kind(fty[4:], False, True)
                    else:
                        fk = decl_kind(fty, False, False)
                    mangled = name + '.' + fld
                    if fk == 'uvar':
                        fk = 'var'
                        unsigned.add(mangled)
                    if fk == 'ulong_var':
                        fk = 'long_var'
                        unsigned.add(mangled)
                    syms[mangled] = (fk, addr + off)
                    GLOBTY[mangled] = fty
                continue
            if kind in ('func', 'far_func'):
                # last prototype wins: a per-function `extern int f()` override
                # after the header's `extern unsigned char f()` restores the
                # word-return test (read_line_buffered vs char_device_io).
                if ret_uchar:
                    uchar_funcs.add(name)
                else:
                    uchar_funcs.discard(name)
                if ret_long:
                    long_funcs.add(name)  # returns DX:AX (divmod32/divmod32_bin)
                else:
                    long_funcs.discard(name)
            if kind in ('func', 'far_func') and any(param_bytes):
                byte_params[name] = param_bytes
            if kind in ('func', 'far_func') and any(param_far):
                far_params[name] = param_far
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
    return syms, unsigned, pascal, uchar_funcs, byte_params, long_funcs, far_params


def compile_src(src, addr_map=None):
    """Compile every defined function in `src` that has a resolvable address.

    Addresses and kinds come from the C itself (`__addr__(N)` and the
    declarations); `addr_map` (a {name: address} dict, e.g. supplied by the
    build) fills in / overrides addresses not pinned in the C.  tiny_cc has no
    project-specific symbol table of its own.

    Returns dict name -> (base_addr, bytes).
    """
    global SYMS, PASCAL, UCHAR_FUNCS, BYTE_PARAMS, LONG_FUNCS, FAR_PARAMS
    decls = parse(lex(src))
    syms, unsigned, pascal, uchar_funcs, byte_params, long_funcs, far_params = build_syms(
        decls, addr_map or {}
    )
    saved, saved_p, saved_u, saved_b = SYMS, PASCAL, UCHAR_FUNCS, BYTE_PARAMS
    saved_l, saved_f = LONG_FUNCS, FAR_PARAMS
    SYMS = syms
    PASCAL = pascal
    UCHAR_FUNCS = uchar_funcs
    BYTE_PARAMS = byte_params
    LONG_FUNCS = long_funcs
    FAR_PARAMS = far_params
    try:
        out = {}
        for d in decls:
            if d[0] != 'func':
                continue
            name, args, body = d[1], d[2], d[3]
            if name not in SYMS or SYMS[name][0] not in ('func', 'far_func'):
                continue
            base = sa(name)
            cg = CG(base, unsigned)
            cg._func_ret_uchar = len(d) > 6 and d[6]
            cg.emit_func(args, body)
            out[name] = (base, bytes(cg.buf))
        return out
    finally:
        SYMS = saved
        PASCAL = saved_p
        UCHAR_FUNCS = saved_u
        BYTE_PARAMS = saved_b
        LONG_FUNCS = saved_l
        FAR_PARAMS = saved_f


def dump(bs, base):
    for i in range(0, len(bs), 16):
        chunk = bs[i : i + 16]
        print(f'{base + i:04X}: ' + ' '.join(f'{b:02X}' for b in chunk))


def _shared_compiled_headers(cfile):
    """A `compiled/<name>.c` holds only its own function; the shared extern decls
    live once in the sibling `*.rev` `[compiled_headers]` section (the build
    prepends them before tiny_cc).  Find that .rev and return its header lines so
    the standalone CLI compiles the same source the build does.  Empty if none."""
    d = os.path.dirname(os.path.abspath(cfile))
    # compiled/ lives next to the .rev; also try the parent (compiled/wip/).
    for cand in (os.path.dirname(d), os.path.dirname(os.path.dirname(d))):
        for fn in sorted(os.listdir(cand)) if os.path.isdir(cand) else []:
            if not fn.endswith('.rev'):
                continue
            lines, grab = [], False
            for ln in (
                open(os.path.join(cand, fn), encoding='utf-8').read().splitlines()
            ):
                s = ln.strip()
                if s == '[compiled_headers]':
                    grab = True
                    continue
                if grab and s.startswith('[') and s.endswith(']'):
                    break
                if grab:
                    lines.append(ln)
            if lines:
                return '\n'.join(lines) + '\n'
    return ''


def main():
    if len(sys.argv) < 2:
        print('usage: tiny_cc.py FILE.c [--rom ROM]', file=sys.stderr)
        sys.exit(1)
    src = open(sys.argv[1]).read()
    # A bare compiled/<name>.c omits the shared externs — prepend them so the CLI
    # compiles what the build does (duplicate externs are tolerated).
    if '__addr__' in src:
        src = _shared_compiled_headers(sys.argv[1]) + src
    results = compile_src(src)  # addresses come from __addr__ in the C
    rom = None
    if '--rom' in sys.argv:
        rom = open(sys.argv[sys.argv.index('--rom') + 1], 'rb').read()
    exit_code = 0
    for name, (base, bs) in results.items():
        print(f'; --- {name} @ 0x{base:04X}  ({len(bs)} bytes) ---')
        dump(bs, base)
        if rom is not None:
            exp = rom[base : base + len(bs)]
            n = sum(1 for x, y in zip(bs, exp) if x == y)
            ok = bs == exp
            print(
                f'  {n}/{len(bs)} bytes match'
                + ('  — perfect' if ok else '  — DIVERGENCE')
            )
            if not ok:
                for i, (x, y) in enumerate(zip(bs, exp)):
                    if x != y:
                        print(
                            f'  first divergence @ {base + i:04X}: '
                            f'got {x:02X}, expected {y:02X}'
                        )
                        break
                exit_code = 2
        print()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
