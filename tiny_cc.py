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
BYTE_PARAMS = {}  # func name -> per-parameter byte-width flags (uchar params)

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


def parse_extern(p):
    ty = parse_type(p)
    is_pascal = bool(p.acc('kw', 'pascal'))  # callee-cleaned (ret N) helper
    name = p.exp('id')[1]
    param_bytes = ()
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
        kind = decl_kind(ty, True, False)
    elif p.acc('op', '['):
        while not p.acc('op', ']'):
            p.eat()
        kind = decl_kind(ty, False, True)
    else:
        kind = decl_kind(ty, False, False)
    addr = parse_addr_suffix(p)
    p.exp('op', ';')
    if kind in ('far_var', 'var', 'uvar'):
        GLOBTY[name] = ty  # keep the type string (`->` needs the tag)
    return ('extern', name, kind, addr, is_pascal, ty == 'uchar', param_bytes)


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
        return ('id', t[1])
    if t[1] == '(':
        # Could be a cast `(type) expr` or a parenthesized expr.
        if p.pk()[0] == 'kw' and p.pk()[1] in (
            'int',
            'unsigned',
            'char',
            'long',
            'void',
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
    padding), nested `struct X` by value."""
    p.exp('kw', 'struct')
    tag = p.exp('id')[1]
    p.exp('op', '{')
    fields, off = {}, 0
    while not p.acc('op', '}'):
        fty = parse_type(p)
        name = p.exp('id')[1]
        size = _type_size(fty)
        if p.acc('op', '['):  # `T name[N]` — N elements
            n = p.exp('num')[1]
            p.exp('op', ']')
            size *= n
            fty = 'arr_' + fty
        p.exp('op', ';')
        fields[name] = (off, fty)
        off += size
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
    return t.startswith('ptr_far')


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
        self.cl = None  # shift count still live in CL (an int amount)
        self.dx = None  # ('hi', name) high word, or ('val16', name)
        self.axdx_var = None  # name whose full 4-byte value is in AX:DX
        self.cxbx_var = None  # name whose full 4-byte value is in CX:BX
        self.esbx = None  # far_var whose data ES:BX currently points at
        self._regvar_zero = {}  # reg-var ('si'/'di') -> holds literal 0
        self.uses_di = False
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

    def rvid(self, e):
        """True for an 'id' node naming a register-allocated (SI/DI) local."""
        return self.locid(e) and self.is_reg_var(e[1])

    def stkid(self, e):
        """True for an 'id' node naming a stack local/param (not a reg var)."""
        return self.locid(e) and not self.is_reg_var(e[1])

    def ensure_bx(self, name):
        """Make sure BX holds the value of pointer-local `name`."""
        if self.bx == name:
            return
        if self.di == name:
            self.emit(0x8B, 0xDF)  # mov bx, di
            self.bx = name
            return
        disp = self.ld(name)
        self.ldbx(disp)  # mov bx, [bp-N]
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
            b = far_base(node[1])
            if b:
                return (b, node[2][1], 'byte')
        if nderef(node):
            # *p where p is a far-pointer local/param → element at offset 0
            if is_far(node[1]):
                ty = (
                    self.lt(n11(node))
                    if n11(node) in self.locals
                    else SYMS[n11(node)][0]
                )
                return (n11(node), 0, 'word' if 'int' in ty else 'byte')
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

    def far_indexed_reg(self, node):
        """Recognize `far_X[reg_var]` — a far pointer (a far_var global OR a
        far-pointer param/local) indexed by a register variable (SI/DI).  Returns
        (name, 'si'|'di') or None.  Element addressed `[es:bx+si/di]` after
        `les bx,[name]` (emit_les loads [addr] for a global, [bp+disp] for a
        param/local)."""
        if node[0] == 'idx' and nid(node[1]) and self.rvid(node[2]):
            n = n11(node)
            if (gsym(n, 'far_var')) or (n in self.locals and pf(self.lt(n))):
                return (n, self.regvars[node[2][1]])
        return None

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
        if self.esbx == base and self.bx == base:
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
            self.emit_les(base[1])
            self.e26(0xC4, 0x5F, base[2])  # les bx,[es:bx+disp]
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
        kind, head, _ = atom
        if kind == 'raw':
            return len(head)
        if kind in ('jmp_short', 'jcc'):
            return len(head) + 1
        if kind == 'call':
            return len(head) + 2
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
        )

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
        self.axdx_var = self.cxbx_var = self.cl = None
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
        # Dead-jmp elimination (threading's companion): a `jmp` that (a) cannot
        # be reached by fall-through — the previous atom is an unconditional
        # jmp — and (b) whose label(s) no branch targets anymore after
        # threading, is dropped.  MSC never emits it: this is the structural
        # jmp-over-else of a goto-free if/else whose then-arm already exited
        # through a shared tail (dos_fn_45's error arms) — the goto-form
        # source MSC compiled jumps straight to the final target instead.
        while True:
            used = {a[2] for a in atoms if a[0] in ('jmp_short', 'jcc')}
            dead = None
            for i, a in enumerate(atoms):
                if (
                    i > 0
                    and a[0] == 'jmp_short'
                    and atoms[i - 1][0] == 'jmp_short'
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
            return not (self._regvar_direct_ok(a[1]) and self._regvar_direct_ok(b[1]))
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
        # EXACTLY ONE call-valued arm breaks the merge: MSC materialises the call
        # result to the variable's home and stores the sibling const direct — both
        # to memory, re-read at the use (dos_fn_5b's `result = 5 : create()`).  Two
        # call arms still merge via AX (resolve_fcb_driver's int24 pair).
        if (ncall(a[1])) != (ncall(b[1])):
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
        """Emit `<op> si/di, <node>` for a local/param ([bp+disp]) or var global
        ([addr]) memory operand."""
        rf = 6 if reg == 'si' else 7
        if node[1] in self.locals:
            disp = self.ld(node[1])
            self.emit(opcode, 0x40 | (rf << 3) | 0x06, disp)  # [bp+disp8]
        else:
            a = SYMS[node[1]][1]
            self.emit(opcode, (rf << 3) | 0x06, *w16(a))  # [disp16]

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
        # FP_OFF(far_local) — the offset word at the far pointer's [bp+disp] slot.
        if node[0] == 'fpoff' and pf(self.lty(node[1])):
            disp = self.ldi(node)
            return ((), 0x46, (disp & 0xFF,), False)
        far = self.far_lvalue(node)
        if far:
            base, disp, kind = far
            self.emit_les(base)
            return (
                (0x26,),
                mod8(disp) | 0x07,
                (disp & 0xFF,) if disp else (),
                kind == 'byte',
            )
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
        rf = 6 if self.regvars[regvar] == 'si' else 7
        self.emit(*prefix, 0x39, modrm | (rf << 3), *suffix)  # cmp <mem>, si/di
        return True

    def _emit_op_reg(self, operand, regvar, op):
        """Emit `add/sub <operand>, si/di` for a WORD memory operand (local,
        FP_OFF(far local), or word global) +=/-= a register var, via _mem_rm.
        Returns False for a byte operand / unsupported lvalue (e.g. long global)."""
        mm = self._mem_rm(operand)
        if not mm or mm[3]:
            return False
        prefix, modrm, suffix, _ = mm
        rf = 6 if self.regvars[regvar] == 'si' else 7
        opc = 0x01 if op == '+' else 0x29
        self.emit(*prefix, opc, modrm | (rf << 3), *suffix)  # add/sub <mem>, si/di
        return True

    # ---- entry ----
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
            if nid(node):
                return types.get(node[1]) or GLOBTY.get(node[1], '')
            if node[0] in ('arrow', 'dot'):
                return STRUCTS[tag_of(node[1])][node[2]][1]
            ni('member base', node)

        def tag_of(node):
            """Struct tag of a struct-pointer-valued expression (pre-lowering)."""
            ty = typestr(node)
            i = ty.find('struct:')
            if i < 0:
                raise NameError(f'not a struct pointer: {node!r} ({ty})')
            return ty[i + 7 :]

        def lower(node):
            """Fully lower one (possibly chained) `->` or `.` node.  The cast keeps
            the base's memory class: a NEAR struct pointer (`ptr_struct:…`) or a
            near struct value (`struct:…`, whose array-style local decays to its
            address) lowers to `*(T *)(p + off)` / `p[off]`; a FAR one
            (`ptr_far_struct:…`) to `*(T far *)(p + off)` — so member access stays
            byte-identical to the explicit cast the codegen already emits."""
            base, fld = node[1], node[2]
            off, fty = STRUCTS[tag_of(base)][fld]
            pfx = 'ptr_far_' if 'far' in typestr(base) else 'ptr_'
            lbase = rw(base)
            if fty in ('char', 'uchar'):
                return ('idx', lbase, ('num', off))
            if fty in ('int', 'uint', 'long', 'ulong'):
                cast = pfx + fty
            elif fty.startswith('ptr_'):
                cast = pfx + fty  # ptr field → chained ptr-to-ptr cast
            else:
                ni('arrow field type', fty)
            addr = ('bin', '+', lbase, ('num', off)) if off else lbase
            return ('deref', ('cast', cast, addr))

        def rw(n):
            if isinstance(n, list):
                return [rw(s) for s in n]
            if not isinstance(n, tuple):
                return n
            if n[0] in ('arrow', 'dot'):
                return lower(n)
            return tuple(rw(c) for c in n)

        return rw(body)

    def emit_func(self, args, body):
        body = self._resolve_arrows(args, body)
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
        _idx_counts = {}
        for n in self._nodes(body):
            if nderef(n) and ncast(n[1]) and 'far' in n11(n):
                inner = n12(n)
                if nbin(inner) and inner[1] == '+' and num(inner[3]):
                    inner = inner[2]  # strip trailing +const
                if (
                    nbin(inner)
                    and inner[1] == '+'
                    and self.gfar(inner[2])
                    and not num(inner[3])
                ):
                    nm = inner[2][1]
                    _idx_counts[nm] = _idx_counts.get(nm, 0) + 1
        self._idx_si = {k for k, v in _idx_counts.items() if v == 1}

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
        _const_rets = {
            n11(n) for n in self._nodes(body) if n[0] == 'return' and n[1] and num(n[1])
        }
        self._defer_const_ret = _uchar_rets >= 1 and len(_const_rets) == 1
        self._deferred_const = {}  # value-repr -> (label, value-node)
        # Register allocation for register vars.  Without an outer loop we
        # let the first reg var live in SI, the second in DI (both
        # callee-saved).  With a loop, SI alone (matches lookup_token).
        has_loop = self._has_loop(body) or self._has_backward_goto(body)
        for i, name in enumerate(list(self.regvars)):
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
            elif i == 1:
                self.regvars[name] = 'di'
            else:
                ni('only 2 register vars supported')
        # Deferred reg-var return: when the function's LAST statement is
        # `return <reg-var>` and the same return appears elsewhere too, MSC
        # emits ONE `mov ax,si` block at the tail (falling into the epilogue)
        # and every earlier exit — plain, conditional, or a while-loop's false
        # test — jumps forward to it (CHAR_DEVICE_IO's RET block at 0x2390).
        self._regvar_ret_defer = None
        self._defer_tail_stmt = None
        self._suppress_return = None
        _last = body[-1] if body else None
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
        )
        # DI may be used as a register var OR as a scratch for pointer deref
        # (the `*key == *tok` pattern in lookup_token).
        self.uses_di = (
            any(r == 'di' for r in self.regvars.values())
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
        )
        self.emit(0x55)  # push bp
        self.emit(0x8B, 0xEC)  # mov bp, sp
        if self.local_size:
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
        # Cold const-return blocks, just before the epilogue: each loads its value
        # and falls through to the epilogue (the last one); earlier ones jump to it.
        _dc = list(self._deferred_const.values())
        for j, (clbl, cval) in enumerate(_dc):
            self.lbl(clbl)
            self.expr_to_ax(cval)
            if j != len(_dc) - 1:
                self.emit_jmp_short(self.func_ret_lbl)
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
        self.emit(0x5D, 0xC3)  # pop bp; ret
        self.resolve()

    def collect_locals(self, body):
        for s in body:
            if s[0] == 'localarr':
                ty, name, n = s[1], s[2], s[3]
                # A byte buffer reserved on the stack; `name` denotes its base
                # (bp-offset = element [0]).  Size is the byte count as written.
                self.local_size += n
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
        # AL/BX, not DI; far derefs use ES:BX.  So only that compare counts.
        return any(
            n[0] == 'cmp' and nderef(n[2]) and nderef(n[3]) for n in self._nodes(node)
        )

    def _simple_byte_rhs(self, e):
        """True if `e` is local/global/const byte arithmetic — no call, no far
        access — so it can be computed after a `les` without clobbering ES:BX."""
        if num(e):
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
        if key in self._ncall_lbls:
            for a in reversed(call[2][1:]):
                self.push_arg(a)
            self.emit_jmp_short(self._ncall_lbls[key])
            return
        self._ncall_lbls[key] = lbl = self.fresh('ntail')
        self.gen_call(call, share_lbl=lbl)
        if not tail:
            self.emit_jmp_short(self.func_ret_lbl)

    # ---- statements ----
    def stmt(self, s, tail=False):
        op = s[0]
        if op in ('local', 'localarr'):
            return
        if op == 'label':
            self.lbl('user_' + s[1])
            return
        if op == 'goto':
            # a `goto` absorbed by a preceding shared assignment-call jmp emits
            # nothing (control already left via the jmp to the shared block).
            if s is getattr(self, '_sac_suppress_goto', None):
                self._sac_suppress_goto = None
                return
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
            # A `return <reg-var>` already consumed by the preceding while's
            # fused exit (the loop's false test jumps straight to the shared
            # tail block, so this statement is unreachable) — emit nothing.
            if s is self._suppress_return:
                self._suppress_return = None
                return
            # `return f(arg);` whose call tail is shared (FCB_OP_RAISE_ERROR_CODE).
            if (
                s[1]
                and ncall(s[1])
                and nid(n11(s))
                and n11(s[1]) in self._shared_call_tail
                and len(n12(s)) == 1
            ):
                self._emit_call_tail_return(s[1])
                return
            # `return f(a0, …)` whose MULTI-arg tail is shared: the first site
            # emits the full call with a label before the leftmost push; later
            # sites push their differing args and jump into it.
            if (
                s[1]
                and ncall(s[1])
                and nid(n11(s))
                and self._ncall_key(s[1]) in self._ncall_shared
            ):
                self._emit_ncall_return(s[1], tail)
                return
            # `return 0` right after a far-long add that left DX=0 (the dir-size
            # epilogue at FCB+0x15): MSC reuses it via `mov ax,dx` and falls into
            # the epilogue, rather than sharing the cold `xor ax,ax` return block.
            if tail and z0(s[1]) and self.dx == 0:
                self.emit(0x8B, 0xC2)  # mov ax, dx
                self.ax = None
                return
            # Shared uchar zero-extend tail: load AL for this uchar-value return,
            # then route through the one `sub ah,ah; jmp epilogue` block (placed
            # at the first such return; later ones jump back to it).
            if self._uchar_ret_share and self._uchar_ret_val(s[1]):
                if ncall(s[1]):
                    self.gen_call(s[1])  # uchar result in AL
                else:
                    disp = self.ldi(s)
                    self.ldal(disp)  # mov al, [bp+disp]
                if not self._use_ax_lbl:
                    self._use_ax_lbl = self.fresh('useax')
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
            if s[1] and repr(s[1]) in self.shared_returns:
                key = repr(s[1])
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
                self.shared_ret_placed.add(key)
                self.lbl(lbl)
            if s[1]:
                # `return f(args);` at the function end is a tail call — the
                # epilogue's `mov sp, bp` reclaims the args, so skip `add sp,N`.
                if ncast(s[1]) and n11(s) == 'uchar' and ncall(n12(s)):
                    # `return (uchar)f(...)` — narrow the int result to a byte and
                    # zero-extend for the int return (call; add sp; sub ah,ah).
                    self.gen_call(n12(s), tail=tail)
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                elif tail and ncall(s[1]):
                    self.gen_call(s[1], tail=True)
                elif self._far_ptr_add_base(s[1]):
                    bn, addends = self._far_ptr_add_base(s[1])
                    self._far_ptr_add_to_axdx(bn, addends)  # far ptr → off=AX, seg=DX
                elif self._is_long4(s[1]):
                    self.load_long_axdx(s[1])  # 32-bit result in DX:AX
                elif self._is_long_expr(s[1]):
                    self.gen_long(s[1])  # 32-bit expression → DX:AX
                elif self._al_only_ret and self._uchar_ret_val(s[1]):
                    self.expr_to_al(s[1])  # uchar function → AL only, no zero-extend
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
            if num(cond) and cond[1] != 0:
                loop = self.fresh('loop')
                brk = self.fresh('break')
                self.lbl(loop)
                self.loop_body(body, brk, loop)
                self.emit_jmp_short(loop)
                self.lbl_if_used(brk)
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
        if op == 'do':
            # do { BODY } while (COND);  — labelled top, JCC-back tail, and a
            # break label right after (the natural fall-through exit).
            cond, body = s[1], s[2]
            loop = self.fresh('loop')
            brk = self.fresh('break')
            self.break_lbls.append(brk)
            self.lbl(loop)
            for ss in body:
                self.stmt(ss)
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
                self.lbl(loop)
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
                )
            )
            loop = self.fresh('loop')
            test = self.fresh('test')
            brk = self.fresh('break')
            cont = self.fresh('cont')
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
                    self.bx = esbx_seed  # BX also points there (rotated cond's les)
            self.loop_body(body, brk, cont, peek=True)
            # `continue` lands on the update (then the test), per C semantics — not
            # on the test directly (which would skip the update).
            self.lbl_if_used(cont)
            if upd:
                self.expr_stmt(upd)
            if not provable:
                self.lbl(test)
            self.cond_jump(cond, loop, True)
            self.lbl_if_used(brk)
            return
        if op == 'if':
            # if (cond) goto L;  — single JCC to the user label (cond true)
            if not s[3] and len(s[2]) == 1 and s[2][0][0] == 'goto':
                self.cond_jump(s[1], 'user_' + s[2][0][1], True)
                return
            # if (cond) break;  — single JCC to the enclosing loop's break label
            if not s[3] and len(s[2]) == 1 and s[2][0][0] == 'break':
                self.cond_jump(s[1], self.break_lbls[-1], True)
                return
            # if (cond) continue;  — single JCC to the loop's continue label
            if not s[3] and len(s[2]) == 1 and s[2][0][0] == 'continue':
                self.cond_jump(s[1], self.continue_lbls[-1], True)
                return
            simple_return = not s[3] and len(s[2]) == 1 and s[2][0][0] == 'return'
            if simple_return and not s[2][0][1]:
                # if (cond) return;     — JCC straight to epilogue
                self.cond_jump(s[1], self.func_ret_lbl, True)
                return
            # `if (cond) return <long / far-ptr>;` as the function's LAST statement:
            # skip to the epilogue on a false condition, then load the 32-bit value
            # into DX:AX and fall straight through (no `jmp epilogue`) — the general
            # path below only knows expr_to_ax (16-bit) and always jmps.
            if (
                simple_return
                and s[2][0][1]
                and tail
                and (
                    self._is_long4(s[2][0][1])
                    or self._is_long_expr(s[2][0][1])
                    or self._far_ptr_add_base(s[2][0][1])
                )
            ):
                val = s[2][0][1]
                self.cond_jump(s[1], self.func_ret_lbl, False)
                if self._far_ptr_add_base(val):
                    bn, addends = self._far_ptr_add_base(val)
                    self._far_ptr_add_to_axdx(bn, addends)
                elif self._is_long4(val):
                    self.load_long_axdx(val)
                else:
                    self.gen_long(val)
                return
            if simple_return and s[2][0][1]:
                val = s[2][0][1]
                # uchar-value return that shares the zero-extend tail: skip past
                # on a false condition, then let the bare-return handler place /
                # jump to the shared `sub ah,ah; jmp epilogue` (USE_AX).
                if self._uchar_ret_share and self._uchar_ret_val(val):
                    done = self.jfalse(s[1])
                    self.stmt(s[2][0])
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
                    ):
                        done = self.jfalse(s[1])
                        self.stmt(s[2][0])  # places the shared block + return
                        self.lbl(done)
                        return
                    lbl = self.shared_ret_lbls.setdefault(key, self.fresh('sret'))
                    self.cond_jump(s[1], lbl, True)
                    return
                # `if (cond) return f(a0, …);` whose MULTI-arg tail is shared —
                # skip past on false, then route through the shared block.
                if (
                    ncall(val)
                    and nid(val[1])
                    and self._ncall_key(val) in self._ncall_shared
                ):
                    done = self.jfalse(s[1])
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
                    body_key = repr(s[2])
                    if body_key in self.dup_blocks:
                        if body_key in self.block_labels:
                            self.cond_jump(s[1], self.block_labels[body_key], True)
                            return
                        done = self.jfalse(s[1])
                        blk = self.fresh('blk')
                        self.lbl(blk)
                        self.block_labels[body_key] = blk
                        # The guard tested `arg` into AL; it is live at every entry
                        # (fall-through and cross-jump), so the block reuses it
                        # (MSC's bare `sub ah,ah`, no reload).
                        arg = val[2][0]
                        if (
                            self.ucharty(arg)
                            and s[1][0] == 'cmp'
                            and arg in (n12(s), s[1][3])
                        ):
                            self.al = arg[1]
                        self.stmt(s[2][0])
                        self.lbl(done)
                        return
                    done = self.jfalse(s[1])
                    self._emit_call_tail_return(val)
                    self.lbl(done)
                    return
                # Deferred const return: jump forward to a single cold block
                # emitted just before the epilogue (see _defer_const_ret).
                if num(val) and self._defer_const_ret:
                    key = repr(val)
                    if key not in self._deferred_const:
                        self._deferred_const[key] = (self.fresh('cret'), val)
                    self.cond_jump(s[1], self._deferred_const[key][0], True)
                    return
                # Identical constant returns share one block (MSC cross-jumping):
                # a later `if (cond) return K` jumps straight to the first block.
                if num(val) and val in self.return_blocks:
                    self.cond_jump(s[1], self.return_blocks[val], True)
                    return
                # if (cond) return EXPR; — skip past on false, load+jmp on true.
                # For a constant, label the load so later identical returns reuse it.
                done = self.jfalse(s[1])
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
                not s[3]
                and self._block_terminates(s[2])
                and repr(s[2]) in self.dup_blocks
            ):
                key = repr(s[2])
                # Defer-to-last: every occurrence but the LAST jumps forward to
                # the one cold copy; the last places it inline (Pattern A).
                if key in self._dup_last_total:
                    self._dup_seen[key] = self._dup_seen.get(key, 0) + 1
                    lbl = self.block_labels.setdefault(key, self.fresh('blk'))
                    if self._dup_seen[key] < self._dup_last_total[key]:
                        self.cond_jump(s[1], lbl, True)
                        return
                    done = self.jfalse(s[1])
                    self.lbl(lbl)
                    self.emit_arms(s[2])
                    self.lbl(done)
                    return
                if key in self.block_labels:
                    self.cond_jump(s[1], self.block_labels[key], True)
                    return
                done = self.jfalse(s[1])
                blk = self.fresh('blk')
                self.lbl(blk)
                self.block_labels[key] = blk
                self.emit_arms(s[2])
                self.lbl(done)
                return
            if s[3]:
                # MSC has a single if-else layout (Pattern A): test, JCC to
                # `else` when the condition is FALSE, then-block (fall-through),
                # jmp done, else.  An OR condition is written De Morgan (as `&&`
                # with the branches swapped), so there is no separate "OR" form.
                else_lbl = self.fresh('else')
                done = self.fresh('done')
                self.cond_jump(s[1], else_lbl, False)
                # When both arms assign the same reg var and one is forced
                # through AX, route both via AX so the `mov reg,ax` tail merges.
                via_ax = self._regvar_branches_via_ax(s[2], s[3])
                saved_force = self._force_regvar_ax
                self._force_regvar_ax = via_ax
                saved_var_force = self._force_var_ax
                self._force_var_ax = self._branches_assign_same_var(s[2], s[3])
                merge_tgt = n11(s[2][-1][1]) if self._force_var_ax else None
                # Capture each branch's atoms in isolation.  Propagate the outer
                # if's tail position to each branch's last statement so
                # tail-calls correctly skip `add sp, N`.
                snap = self.snapshot()
                # The then-arm jumps to `done`.  A trailing *void call* tail-skips
                # only when the else-arm also ends in a call — then both merge into
                # one shared call that falls through to the epilogue; otherwise the
                # standalone then-call keeps its `add sp,N` (returns / nested ifs
                # always propagate tail for their own tail-calls).
                else_last_call = self._arm_ends_in_call(s[3])
                # A trailing void call tail-folds its cleanup only when BOTH
                # arms end in the SAME call (they merge into one shared tail).
                then_tgt = self._arm_tail_call_target(s[2])
                merge_call = then_tgt and then_tgt == self._arm_tail_call_target(s[3])
                for i, ss in enumerate(s[2]):
                    void_call = ss[0] == 'expr' and ncall(ss[1])
                    t = tail and i == len(s[2]) - 1 and (not void_call or merge_call)
                    self._peek_next = s[2][i + 1] if i + 1 < len(s[2]) else None
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
                        i == len(s[2]) - 1
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
                snap = self.snapshot()
                for i, ss in enumerate(s[3]):
                    self._peek_next = s[3][i + 1] if i + 1 < len(s[3]) else None
                    if (
                        i == len(s[3]) - 1
                        and ss[0] == 'expr'
                        and ncall(ss[1])
                        and s[2]
                        and s[2][-1][0] == 'expr'
                        and ncall(s[2][-1][1])
                        and self.esbx in {a[1] for a in n12(ss) if nid(a)}
                    ):
                        self.esbx = self.bx = None  # merge tail — see then-arm
                    e_void = ss[0] == 'expr' and ncall(ss[1])
                    self.stmt(
                        ss,
                        tail=(
                            tail and i == len(s[3]) - 1 and (not e_void or merge_call)
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
                    and self._block_terminates(s[2])
                    and self._block_terminates(s[3])
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
                    # dropped by the then-unique slice.  Alias them to the shared
                    # block (boundary) / done (chunk end) so their references
                    # (the `jmp` from a nested true-arm) resolve to the one
                    # surviving copy.  3-way shared store of WRITE_FCB's extend
                    # flag relies on this.
                    then_b, _, then_atom_list, then_labels = then_chunk
                    boundary = sum(
                        self.atom_len(a) for a in then_atom_list[: len(then_atoms) - n]
                    )
                    for nm, p in then_labels.items():
                        if p == boundary:
                            self.labels[nm] = self.labels[shared]
                        elif p == len(then_b):
                            self.labels[nm] = self.labels[done]
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
                    if not self._block_terminates(s[2]):
                        self.emit_jmp_short(done)
                    self.lbl(else_lbl)
                    self.replay(*self.slice_chunk(*else_chunk, 0, len(else_atoms)))
                    self.lbl(done)
            else:
                # if-no-else: Pattern A (jump past then if cond is false)
                done = self.jfalse(s[1])
                self.emit_arms(s[2])
                self.lbl(done)
            return
        ni(s)

    def expr_stmt(self, e, tail=False):
        if e[0] == 'comma':  # `a, b` (e.g. a for-update list)
            for sub in e[1]:
                self.expr_stmt(sub)
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

    def gen_opassign(self, op, lhs, rhs):
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
            # ES:BX (if loaded from this pointer) is unaffected — it still holds the
            # old offset; MSC reuses it for further field stores this iteration and
            # only reloads on the next `les`.  AX is untouched.
            return
        # <mem> +=/-= reg_var → add/sub <mem>, si/di  (local / FP_OFF(far local) /
        # word global, via _mem_rm — direct, no AX round-trip)
        if op in ('+', '-') and self.rvid(rhs):
            if self._emit_op_reg(lhs, rhs[1], op):
                return
            # long global += reg_var → sub ax,ax; add [g],si/di; adc [g+2],ax
            if op == '+' and self.gkind(lhs) == 'long_var':
                a = SYMS[lhs[1]][1]
                rf = 6 if self.rv(rhs) == 'si' else 7
                self.emit(0x2B, 0xC0)  # sub ax, ax
                self.emit(0x01, (rf << 3) | 0x06, *w16(a))  # add [g],si/di
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
            self.zaa()
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
            rf = 6 if self.rv(rhs) == 'si' else 7
            opc = 0x21 if op == '&' else 0x09
            self.emit(opc, (rf << 3) | 0x06, *w16(addr))  # and/or [addr],si/di
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
        # A far_var whose ES:BX is still cached (e.g. after `g[..]` field reads)
        # reuses it: mov ax,bx; mov dx,es — no reload from memory.
        if gsym(n, 'far_var') and self.esbx == n:
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

    def gen_long(self, node):
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
        if nbin(node) and node[1] == '<<':
            # long << n : DX:AX <<= CL, via the MSC shift helper (__lshl pins
            # its address; the register convention is value=DX:AX, count=CL).
            self.gen_long(node[2])  # value → DX:AX
            self._load_cl(node[3])  # count → CL
            self.emit_call(SYMS['__lshl'][1])  # clobbers AX/BX/CX/DX/ES
            self.clob()
            return
        if ncall(node):
            self.gen_call(node)  # long-returning call → DX:AX
            return
        if nbin(node) and node[1] in ('+', '-'):
            self.gen_long(node[2])  # accumulate in DX:AX
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
            self.ldax(d)  # mov ax, [bp+d]
            self.emit(0x2B, 0xD2)  # sub dx, dx
            self.zad()
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
            else:
                ni('long term', r)
        self.emit(0x83, ext, 0x00)  # adc/sbb dx, 0
        self.zad()

    def _is_long_expr(self, e):
        """True if expression e evaluates to a 32-bit (long) value."""
        if ncast(e):
            return wlong(e[1])
        if nbin(e) and e[1] in ('+', '-', '<<'):
            return self._is_long_expr(e[2]) or self._is_long_expr(e[3])
        if nid(e):
            n = e[1]
            if n in self.locals:
                return self.lt(n) in ('long',) or pf(self.lt(n))
            return n in SYMS and SYMS[n][0] in ('long_var', 'far_var')
        if ncall(e) and nid(e[1]) and n11(e) in SYMS:
            return SYMS[n11(e)][0] == 'far_func'
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
            if not chaining and self._zero_scalar_assign_target(self._peek_next):
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
            if num(inner) and all(f and f[2] == 'word' for f in fars):
                n = inner[1] & 0xFFFF
                # When a `les` is needed it precedes the constant load (MSC order);
                # if ES:BX is already live for this base it's a no-op.
                self.emit_les(fars[-1][0])
                self.mvax0(n)
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
        # far_local = far_var_global + <int terms> : offset = sum(terms) + [g],
        # segment = [g+2], built in AX:DX (MSC: <var term>; add ax,[g]; mov
        # dx,[g+2]; [add ax,const]; store both).  Handles a single trailing const
        # too (`far_var + idx*k + c`).
        if pf(self.lty(lhs)) and nbin(rhs) and rhs[1] == '+':
            if self.fv_axdx_sum(rhs):
                d = self.ld(lhs[1])
                self.stax(d)  # mov [bp+d], ax
                self.emit(0x89, 0x56, d + 2)  # mov [bp+d+2], dx
                self.zad()
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
            and ncast(rhs[3])
            and rhs[3][1] == 'uchar'
        ):
            far = self.far_lvalue(rhs[3][2])
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
                self.emit(0xC6, 0x06, *w16(a), rhs[1])  # mov byte [a], imm
                return
            self.expr_to_al(rhs)
            self.emit(0xA2, *w16(a))  # mov [a], al
            self.al = ('rhs', rhs)  # AL still holds rhs's value
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
                # store immediate: mov byte/word [es:bx+disp], imm
                self.emit_les(fv)
                if kind == 'word':
                    self.e26(0xC7, modrm, *d8(disp), rhs[1], (rhs[1] >> 8))
                else:
                    self.e26(0xC6, modrm, *d8(disp), rhs[1])
                # the immediate store and `les` touch only ES:BX, so AX/AL survive
                return
            if kind == 'word' and self.rvid(rhs):
                # far word = register var → store SI/DI straight (no AX round-trip)
                self.emit_les(fv)
                rf = 6 if self.rv(rhs) == 'si' else 7
                self.e26(
                    0x89, mod8(disp) | (rf << 3) | 0x07, *d8(disp)
                )  # mov [es:bx+d], si/di
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
                # tagged by a simple local source so a following `return result`
                # reuses AL (just `sub ah,ah`, no reload).
                self.al = rhs[1] if (self.locid(rhs)) else None
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
            # A byte store needs only AL (no zero-extend); a word store needs AX.
            load = self.expr_to_al if kind == 'byte' else self.expr_to_ax
            if self._is_rm(rhs) or self._is_local_arr_read(rhs) or near_cast_local:
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
            self.al = None
            return
        # far_var[reg] = <byte expr>  →  al=expr; les bx,[addr]; mov es:[bx+idx],al
        fi = self.far_indexed_reg(lhs)
        if fi:
            name, reg = fi
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
            # ARR[reg++] = expr  →  al = expr; mov bx,reg; inc reg; mov [bx+ARR],al
            if idx[0] == 'postinc' and nid(idx[1]) and self.is_reg_var(n11(idx)):
                reg = self.regvars[n11(idx)]
                self.expr_to_al(rhs)
                self.emit(0x8B, sd(0xDE, reg))  # mov bx, si/di
                self.emit(sd(0x46, reg))  # inc si/di
                self.emit(0x88, 0x87, *w16(arr_addr))
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
                self.al = None
                return
            ni('arr-store', lhs, rhs)
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
        if not nid(lhs):
            raise NotImplementedError
        name = lhs[1]
        if name in self.locals:
            # Register-allocated local (currently only SI)
            if self.is_reg_var(name):
                reg = self.regvars[name]
                if num(rhs) and rhs[1] == 0 and reg == 'si':
                    self.emit(0x33, 0xF6)  # xor si, si
                elif num(rhs) and rhs[1] == 0 and reg == 'di':
                    self.emit(0x33, 0xFF)  # xor di, di
                elif num(rhs) and reg == 'si':
                    self.emit(0xBE, rhs[1], (rhs[1] >> 8))
                elif num(rhs) and reg == 'di':
                    self.emit(0xBF, rhs[1], (rhs[1] >> 8))
                elif self.rvid(rhs):
                    dst = 6 if reg == 'si' else 7
                    src = 6 if self.rv(rhs) == 'si' else 7
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
                    rf = 6 if reg == 'si' else 7
                    self.e26(
                        0x8B,
                        mod8(fdisp) | (rf << 3) | 0x07,
                        *((fdisp,) if fdisp else ()),
                    )  # mov si/di,[es:bx+d]
                elif (
                    not self._force_regvar_ax
                    and (self.far_lvalue(rhs) or (None, None, None))[2] == 'byte'
                ):
                    # reg = far byte → zero-extend into SI/DI: mov al,[es:bx+d];
                    # sub ah,ah; mov si/di,ax
                    self.expr_to_al(rhs)
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                    self.emit(0x8B, 0xF0 if reg == 'si' else 0xF8)  # mov si/di, ax
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
                    self.emit(0x8B, 0xF0 if reg == 'si' else 0xF8)  # mov si/di, ax
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
                    self.emit(0xC6, 0x46, disp, rhs[1])  # mov byte[bp+d],imm
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

    def gen_call(self, e, tail=False, cleanup=True, share_lbl=None):
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
        self._ah_zero = False  # AH unknown entering the arg list
        pbytes = BYTE_PARAMS.get(target[1], ())
        for i in range(len(args) - 1, -1, -1):
            a = args[i]
            # Shared multi-arg call tail: the label lands before the leftmost
            # arg's push (lbl() clears the caches, so the push emits cold —
            # correct for every jump-in site as well as this fall-through).
            if share_lbl and a is args[0]:
                self.lbl(share_lbl)
            self.push_arg(a, byte_param=(i < len(pbytes) and pbytes[i]))
            # far pointers and longs (local/param or far_var global) are 4 bytes
            far_arg = (
                (
                    pf(self.lty(a))
                    or self.lty(a) == 'long'
                    or self.gkind(a) in ('far_var', 'long_var')
                )
                or (ncall(a) and self.gkind(a[1]) == 'far_func')
                or (nderef(a) and self.lty(a[1]).startswith('ptr_ptr_far'))
                or (a[0] in ('bin', 'cast') and self._is_long_expr(a))
                or (ncast(a) and pf(a[1]))
                or (nderef(a) and ncast(a[1]) and 'ptr_far_ptr_far' in n11(a))
                or (nderef(a) and (self.near_lvalue(a) or (None,))[-1] == 'long')
            )
            nbytes += 4 if far_arg else 2
        self.emit_call(addr)
        # cdecl: caller cleans args.  Pascal callees clean their own (ret N);
        # cleanup=False defers to a shared site (switch).  A tail call can skip
        # `add sp` only when the epilogue's `mov sp,bp` reclaims the args with
        # nothing in between — but a `pop si/di` (saved reg) must see clean SP,
        # so don't skip when the function saves SI/DI, nor when the frame holds an
        # address-taken local array (MSC keeps the explicit cleanup then).
        tail_skip = tail and not (self.uses_si or self.uses_di or self._has_array_local)
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

    def gen_switch(self, val, cases, default):
        """MSC sub-dispatch: eval the value to AX, emit a `cmp ax,K / je case`
        chain + default jump, then the case bodies. Each case is a single call;
        they share one `add sp,N` cleanup and exit jump (MSC's tail-merge)."""
        if default:
            ni('switch default body')
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

    def push_arg(self, e, byte_param=False):
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
        # (unsigned char)<call> as an arg: narrow the int result to a byte —
        # `sub ah,ah; push ax` (MSC zero-extends the low byte of the returned AX).
        if ncast(e) and e[1] == 'uchar' and ncall(e[2]):
            self.gen_call(e[2])
            self.push_al0()
            return
        # A near (non-`far`, non-`long`) cast is a byte-level no-op at 16-bit
        # width — unwrap it so the idx/var fast-paths below still apply.  `long`
        # is NOT a no-op (it widens to 4 bytes), handled just below.
        if ncast(e) and 'far' not in e[1] and e[1] != 'long':
            return self.push_arg(e[2])
        # (T far *)local_buffer → far pointer SS:&buf[0]: lea ax,[bp-off]; push ss;
        # push ax  (a stack buffer passed by far pointer to a driver/helper).
        if ncast(e) and 'far' in e[1] and self.lty(e[2]).startswith('arr'):
            disp = self.ld(e[2][1])
            self.lea_ax(disp)  # lea ax, [bp-off]
            self.push_seg_ax(0x16)
            return
        # (T far *)&local_scalar → far pointer SS:&local: lea ax,[bp-off]; push ss;
        # push ax  (a stack out-param handed to a helper — compute_cluster's cluster).
        if (
            ncast(e)
            and 'far' in e[1]
            and e[2][0] == 'addr'
            and nid(e[2][1])
            and n11(e[2]) in self.locals
        ):
            self.lea_ax(self.ld(n11(e[2])))  # lea ax, [bp-off]
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
            # (far)(far_param + const) reusing a live ES:BX (the fall-through arm
            # kept ES:BX = the param): mov ax,bx; mov dx,es; add ax,const; push both.
            if (
                nbin(e[2])
                and e[2][1] == '+'
                and nid(e[2][2])
                and pf(self.lty(e[2][2]))
                and num(e[2][3])
                and self.esbx == e[2][2][1]
            ):
                self.emit(0x8B, 0xC3)  # mov ax, bx
                self.emit(0x8C, 0xC2)  # mov dx, es
                self.emit(0x05, *w16(e[2][3][1] & 0xFFFF))  # add ax, const
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
                self.emit(
                    0x2B if self._pascal_call else 0x33, 0xC0
                )  # sub/xor ax, ax (high=0)
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
        # dx; push ax  (`fcb + 1` as a far arg — NOT a 32-bit add).
        if nbin(e) and e[1] == '+' and nid(e[2]) and pf(self.lty(e[2])) and num(e[3]):
            disp = self.ld(e[2][1])
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
        if (
            e[0] == 'idx'
            and nid(e[1])
            and n11(e) in self.locals
            and str(self.lt(n11(e))).startswith('arr')
        ):
            self.gen_index(e)  # al = buf[idx]
            self.push_al()
            return
        # far word lvalue → push word [es:bx+disp]
        _fw = self.far_lvalue(e)
        if _fw and _fw[2] == 'word':
            disp = self.les_fl(_fw)
            modrm = mod8(disp) | 0x30 | 0x07  # /6 (push), [bx+disp]
            self.e26(0xFF, modrm, *d8(disp))
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
            if ty == 'long':
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
                elif self.dx == ('hi', e[1]):
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
                    self.ldal(disp)  # mov al, [bp+disp]
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
        # A local still live in DX (right after `local = expr % div`) is fetched
        # with `mov ax, dx` instead of a reload from its stack slot.
        if nid(e) and self.dx == ('val16', e[1]):
            self.emit(0x8B, 0xC2)  # mov ax, dx
            self.ax = e[1]
            return
        # Evaluating overwrites AX — but a call pushes its args (which may reuse
        # AX:DX) before clobbering, so defer the clear to gen_call in that case.
        # Also keep the AX:DX pair when this expression's leftmost long leaf IS
        # the cached value: it will be reused in place (MSC keeps a just-stored
        # long live, e.g. `EOF_ANCHOR = …; SECTOR_INDEX = ((EOF_ANCHOR-1)>>n)+1`).
        if not ncall(e) and self._leftmost_long_id(e) != self.axdx_var:
            self.axdx_var = None
        op = e[0]
        if op == 'cast' and 'far' not in e[1]:
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
            # si-indexed single-use far_var entry: `index → SI; les bx,[var];
            # [es:bx+si+disp]` (vs the bx-folded ('idx') emit_les for multi-use).
            if isinstance(fv, tuple) and fv[0] == 'idx' and fv[1] in self._idx_si:
                _, name, index = fv
                self.expr_to_ax(index)  # index → AX
                self.emit(0x8B, 0xF0)  # mov si, ax
                off = sa(name)
                self.emit(0xC4, 0x1E, *w16(off))  # les bx,[off]
                m = 0x40 | 0x00  # [es:bx+si+disp8]
                if kind == 'word':
                    self.e26(0x8B, m, disp)  # mov ax,[es:bx+si+d]
                else:
                    self.e26(0x8A, m, disp)  # mov al,[es:bx+si+d]
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                self.ax = self.al = self.bx = self.esbx = None
                return
            self.emit_les(fv)
            modrm = mod8(disp) | 0x07  # ax, [bx(+disp8)]
            if kind == 'word':
                self.e26(0x8B, modrm, *d8(disp))
            else:
                self.e26(0x8A, modrm, *d8(disp))
                # zero-extend byte → int; elide `sub ah,ah` when AH is already
                # known 0 (e.g. a preceding `x = far_byte` just cleared it —
                # dos_fn_46's `src = fcb[2]; dst = fcb[4]`).
                if not self._ah_zero:
                    self.emit(0x2A, 0xE4)  # sub ah, ah
                self._ah_zero = True
            self.zaa()
            return
        if op == 'num':
            if e[1] == 0:
                if self.dx == 0:
                    self.emit(0x8B, 0xC2)  # mov ax, dx (DX already 0)
                else:
                    self.emit(0x33, 0xC0)  # xor ax, ax
            else:
                self.emit(0xB8, e[1], (e[1] >> 8))
            self.ax = None
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
            # int-context value (e.g. `return LINE_BUF[i];`).
            if self.gkind(e[1]) == 'arr':
                self.emit(0x2A, 0xE4)  # sub ah, ah
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
            a = SYMS[e[1]][1]
            self.emit(0xA0, *w16(a))  # mov al, [a]
            self.emit(0x2A, 0xE4)  # sub ah, ah
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
            self.emit(0xB0, e[1])
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
            and (self.ucharty(e[2]) or fbyte(self, e[2]))
        ):
            if self.ucharty(e[2]):
                if self.al != e[2][1]:
                    self.ldal(self.ld(e[2][1]))  # mov al,[bp+disp]
            else:
                self.expr_to_al(e[2])  # mov al, [es:bx+d]
            opc = {'+': 0x04, '-': 0x2C, '&': 0x24, '|': 0x0C, '^': 0x34}[e[1]]
            self.emit(opc, e[3][1])  # <op> al, imm8
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
        ni(e)

    def gen_index(self, e):
        arr = e[1]
        idx = e[2]
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
        if not nid(arr) or arr[1] not in SYMS:
            raise NotImplementedError
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
            ni('arr_w with non-reg idx')
        # Far-pointer global indexed by a near value: les si,[tbl]; al=[es:bx+si]
        if arr_kind == 'far_var':
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
        if self.locid(idx):
            disp = self.ld(idx[1])
            self.ldbx(disp)  # mov bx, [bp-N]
            self.bx = None
        elif self.gkind(idx) == 'var':
            iaddr = SYMS[idx[1]][1]
            self.emit(0x8B, 0x1E, *w16(iaddr))  # mov bx, [addr]
            self.bx = None
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
            sd = s16(d)
            if -128 <= sd <= 127:
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
            # <expr> + word var global  →  eval lhs to AX; add ax, [g]
            if self.gkind(rhs) == 'var':
                a = SYMS[rhs[1]][1]
                self.emit(0x03, 0x06, *w16(a))  # add ax, [g]
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
                if fl and fl[2] == 'byte':
                    self.expr_to_al(lhs)
                    self.emit(0x25, r[1], 0x00)  # and ax, imm16
                    self.zaa()
                    return
            # 16-bit AND: eval lhs to AX, then `and ax, <rhs>`
            self.expr_to_ax(lhs)
            if self.gkind(r) in ('var', 'long_var'):
                a = SYMS[r[1]][1]
                self.emit(0x23, 0x06, *w16(a))  # and ax, [a]
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
                self.expr_to_ax(lhs)  # ax = [es:bx+a]
                rdisp = fr[1]
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
            return self.gkind(n) == 'long_var' or self.lty(n) == 'long'

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
            self.gen_assign(target, lhs[2])
            # A far/array byte store leaves the value in AL with no named cache;
            # compare AL directly instead of re-reading through the pointer.
            far = self.far_lvalue(target)
            if num(rhs) and far and far[2] == 'byte':
                self.emit(0x3C, rhs[1])  # cmp al, imm8
                self.emit_cc(cop, taken, True, label)
                return
            lhs = target
        # Special: byte-array indexed by a CONST <op> num → cmp byte[addr+c], imm
        if lhs[0] == 'idx' and self.gkind(lhs[1]) == 'arr' and num(lhs[2]) and num(rhs):
            a = (sa(n11(lhs)) + lhs[2][1]) & 0xFFFF
            self.emit(0x80, 0x3E, *w16(a), rhs[1])  # cmp byte[a],imm8
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
        # assigned, e.g. `g = f(); if (g == X)`): cmp ax, num
        if self.gkind(lhs) == 'var' and num(rhs) and self.ax == lhs[1]:
            n = rhs[1]
            if n == 0:
                self.emit(0x0B, 0xC0)  # or ax, ax
            elif -128 <= n <= 127:
                self.emit(0x83, 0xF8, n)  # cmp ax, imm8
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
        # far byte <op> uchar local  →  les bx; mov al,[local]; cmp [es:bx+d],al
        fl = self.far_lvalue(lhs)
        if fl and fl[2] == 'byte' and self.ucharty(rhs):
            disp = self.les_fl(fl)
            self.expr_to_al(rhs)
            modrm = mod8(disp) | 0x07
            self.e26(0x38, modrm, *d8(disp))  # cmp [es:bx+d],al
            self.emit_cc(cop, taken, True, label)  # unsigned
            return
        # Special: far-pointer field <op> num  →  les bx + cmp [es:bx+disp], imm
        far = self.far_lvalue(lhs)
        if far and num(rhs):
            fv, disp, kind = far
            self.emit_les(fv)
            modrm = 0x40 | 0x38 | 0x07 if disp else 0x38 | 0x07  # /7 [bx(+disp8)]
            n = rhs[1]
            if kind == 'byte':
                self.e26(0x80, modrm, *d8(disp), n)  # cmp byte [es:bx+d], imm8
            elif i8(n):
                self.e26(0x83, modrm, *d8(disp), n)  # cmp word [es:bx+d], imm8 sx
            else:
                self.e26(0x81, modrm, *d8(disp), *w16(n))  # cmp word [es:bx+d], imm16
            self.emit_cc(cop, taken, self.far_uns(lhs), label)
            return
        # Special: far-pointer word field <op> memory var  →  les bx; mov
        # ax,[var]; cmp [es:bx+disp], ax   (e.g. drv->count > idx).  Register
        # vars have their own direct `cmp [es:bx+disp], si/di` path.
        if far and far[2] == 'word' and (self.stkid(rhs) or self.gvw(rhs)):
            fv, disp, _ = far
            self.emit_les(fv)
            self.expr_to_ax(rhs)  # mov ax, [var]
            modrm = (0x40 | 0x07) if disp else 0x07  # [bx(+disp8)], reg=ax
            self.e26(0x39, modrm, *d8(disp))  # cmp [es:bx+d],ax
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
            addr = SYMS[lhs[1]][1]
            self.emit(0x80, 0x3E, *w16(addr), rhs[1])
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
        # Special: <computed expr> <op> word var global  →  eval lhs to AX;
        # cmp ax,[g].  (A simple id lhs uses its own var/local path below.)
        if self.gkind(rhs) == 'var' and not nid(lhs):
            a = SYMS[rhs[1]][1]
            unsigned = self.is_uchar_cmp(lhs, rhs)
            self.expr_to_ax(lhs)
            self.emit(0x3B, 0x06, *w16(a))  # cmp ax, [g]
            self.emit_cc(cop, taken, unsigned, label)
            return
        # uchar local <op> word local/global : zero-extend AL→AX, then cmp ax,[rhs]
        if self.ucharty(lhs) and not num(rhs):
            unsigned = self.is_uchar_cmp(lhs, rhs)
            disp = self.ld(lhs[1])
            self.ldal(disp)  # mov al, [bp+disp]
            self.emit(0x2A, 0xE4)  # sub ah, ah
            if self.locid(rhs):
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
        # uchar <op> const : cmp al, imm8 (when AL has it) or mem-form
        if self.ucharty(lhs) and num(rhs):
            if self.al == lhs[1]:
                self.cmp_al_imm(rhs[1])
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
            elif -128 <= rhs[1] <= 127:
                self.emit(0x83, 0xF8, rhs[1])  # cmp ax, imm8 sx
            else:
                self.emit(0x3D, rhs[1], (rhs[1] >> 8))  # cmp ax, imm16
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
        for side in (lhs, rhs):
            if not nid(side):
                continue
            n = side[1]
            if n in self.locals and self.lt(n) in (
                'uchar',
                'uint',
                'reg_uint',
                'reg_uchar',
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
        return (
            nderef(lhs)
            and ncast(lhs[1])
            and ('uint' in n11(lhs) or 'uchar' in n11(lhs))
        )

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
        if varts:
            self.expr_to_ax(varts[0])  # var term → AX
            self.emit(0x03, 0x06, *w16(g))  # add ax, [g]
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
        if n == 0:
            self.emit(0x0B, 0xC0)  # or ax, ax
        elif i8(n):
            self.emit(0x83, 0xF8, n)  # cmp ax, imm8 sx
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
    byte_params = {}
    for d in decls:
        if d[0] == 'extern':
            _, name, kind, addr, is_pascal, ret_uchar, param_bytes = d
            if addr is None:
                addr = addr_map.get(name)
            if addr is None:
                continue
            if ret_uchar and kind in ('func', 'far_func'):
                uchar_funcs.add(name)
            if kind in ('func', 'far_func') and any(param_bytes):
                byte_params[name] = param_bytes
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
    return syms, unsigned, pascal, uchar_funcs, byte_params


def compile_src(src, addr_map=None):
    """Compile every defined function in `src` that has a resolvable address.

    Addresses and kinds come from the C itself (`__addr__(N)` and the
    declarations); `addr_map` (a {name: address} dict, e.g. supplied by the
    build) fills in / overrides addresses not pinned in the C.  tiny_cc has no
    project-specific symbol table of its own.

    Returns dict name -> (base_addr, bytes).
    """
    global SYMS, PASCAL, UCHAR_FUNCS, BYTE_PARAMS
    decls = parse(lex(src))
    syms, unsigned, pascal, uchar_funcs, byte_params = build_syms(decls, addr_map or {})
    saved, saved_p, saved_u, saved_b = SYMS, PASCAL, UCHAR_FUNCS, BYTE_PARAMS
    SYMS = syms
    PASCAL = pascal
    UCHAR_FUNCS = uchar_funcs
    BYTE_PARAMS = byte_params
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
