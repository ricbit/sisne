# tiny_cc control-flow layout rules

How `tiny_cc.py` lays out `if` / `while` / `for` / `do`-`while` in x86 — i.e.
**where the condition test and the loop body end up** in the emitted bytes.
These rules exist to reproduce MS C 3.x (no-optimizer) codegen byte-for-byte,
so they are not arbitrary: each matches what MSC actually emitted in SISNE.SIS.

Two passes shape the final bytes after these layouts are chosen:

- **Branch relaxation** — every `jmp`/`jcc` starts as a short rel8 and is
  widened to a near (rel16) form only when its target is out of ±127 range,
  iterated to a fixed point. A widened `jcc` becomes
  `inverted-jcc short over a near jmp`. So a forward branch to far code shows
  up as `jcc short .skip / jmp near target`.
- **Jump threading** — a `jmp`/`jcc` whose target label is itself a lone
  unconditional `jmp` is retargeted to that jmp's destination (the
  intermediate jmp stays if something still falls into it). This is what lets
  a structured loop with a second entry collapse to the binary's direct jumps.

Throughout, "the condition" is emitted by `cond_jump(cond, label, taken)`,
which produces the compare **and** a conditional jump to `label`
(`taken=True` → jump when the condition holds; `False` → jump when it fails).

---

## `if`

### Single-statement fast paths (no `else`)
`if (cond) goto L;` / `break;` / `continue;` / `return;` / `return EXPR;`
emit just **one** conditional jump — the condition's JCC targets the label /
loop-break / loop-continue / function epilogue directly (`taken=True`). No
body block is laid out. (`return EXPR` is the exception: it skips past on
false, then loads AX and jumps to the epilogue.)

### `if (cond) { then }` — no `else` → **Pattern A**
```
        <cond>            ; jcc done   when cond is FALSE
        <then>
done:
```
Condition at the **top**; body (`then`) **falls through** right after it; a
false condition jumps **past** the body. Body is inline, directly below the
test.

### `if (cond) { then } else { else }` — one layout for all conditions
```
        <cond>            ; jcc else_lbl   when cond is FALSE
        <then>
        jmp done
else_lbl:
        <else>
done:
```
`then` is always the fall-through (top), `else` is below it — regardless of
whether the condition is simple, `&&`, or `||`. A longest-common-suffix
**tail-merge** may fold identical trailing instructions of the two branches
into one shared block.

> **There is no separate "OR" if-else layout.** An `if (A || B) { X } else { Y }`
> is written by the programmer in its **De Morgan** form
> `if (!A && !B) { Y } else { X }` — i.e. negate the condition to `&&` and swap
> the branches — which is the same Pattern A above and emits identical bytes.
> Example (atoi_decimal): `if (ch < '0' || ch > '9') { error; } else { acc; }`
> is the binary's `if (ch >= '0' && ch <= '9') { acc; } else { error; }`.
>
> Consequence: `then` is always physically first. If the binary needs a block
> placed *below* its alternative (e.g. a loop body below its exit code), no
> `if/else` arrangement produces it — that requires a `goto`.

### Cross-jumped `if` blocks — first- vs last-occurrence placement

Identical terminating `if (c) { body }` blocks (>= 2 occurrences) share ONE
cold copy. Default: the copy is placed inline at the **first** occurrence and
later ones JCC **back** to it (read_fcb_with_network's three
`{ *count = 0; return 1; }`).

**Defer-to-last** variant: when the shared body is `{ X = n; …; return K; }`
and a bare guard `if (X == n2) { return K; }` exists — one that **tests the
very lvalue the block stores** (the hand-written "skip the redundant store
into the return-suffix" pattern) — the copy is anchored at the **last**
occurrence instead: earlier occurrences jump **forward** to it, and the guard
jumps **into** its `return K` suffix (past the store). This is
FCB_RANDOM_BLOCK_IO's fail/ret-zero block, placed mid-CON-path:

```
        cmp word [bx], 0    ; if (*count == 0)  — the guard
        jnz +3 / jmp RZ     ;   → forward, INTO the block's return
        …
        jmp FZ              ; earlier { *count = 0; return 0; } sites
        …
        cmp word [bp-0Eh], 0 ; the LAST occurrence (CON path)
        jnz skip
FZ:     mov word [bx], 0    ; *count = 0
RZ:     xor ax, ax          ; return 0
        jmp epilogue
skip:   …
```

A guard testing something else (write_fcb's `if (fat_chain(…) != 0) return 1`)
or returning a different K (read_fcb's `return 0` guard vs `{…; return 1}`
blocks) keeps the default first-occurrence placement.

---

## `while`

### `while (1) { … }` — infinite
```
loop:
        <body>
        jmp loop
```
No condition. The only way out is `break` (→ a break label placed after the
loop, emitted only if a `break` actually targets it).

### `while (cond) { … }` → **always test-at-TOP** (no entry jump)
```
loop:
        <cond>            ; jcc exit   when cond is FALSE (no entry jump)
        <body>
        jmp loop
exit:
```
Condition at the **top**, body below it, `jmp loop` back-edge at the bottom.
The function/preceding code **falls straight into the test** — no entry jump,
regardless of whether the condition is simple or compound (`||`/`&&`). A label
written on the `while` names the **top/test** (so `goto thatlabel` re-runs the
condition). `break` → `exit`, `continue` → `loop` (the top).

> **`while` is for test-at-top loops only.** A test-at-bottom (rotated) loop —
> body first, condition and back-edge at the bottom, with an entry `jmp test`
> — is what **`for`** produces. If you have a simple-condition loop that MSC
> rotated, write it as `for (; cond; )` (optionally with init/update), **not**
> `while (cond)`. Every simple-`while` in the codebase was converted this way
> (atoi_decimal, dos_fn_09, invalidate_cached_fcb, lookup_token,
> read_line_to_buffer).

### Deferred reg-var return — `return si` exits share the tail block

When the function's **last** statement is `return <reg-var>` (SI/DI) and the
same `return` appears in **>= 2** places, the one shared `mov ax,si` block is
emitted **at the tail**, falling into the epilogue; every earlier exit reaches
it with a jump instead of loading AX locally:

- a plain mid-function `return si;` → `jmp RET` (no `mov ax,si` at the site);
- `if (cond) return si;` → a single JCC to RET (relaxation rewrites it to
  `jcc +3; jmp RET` when out of short range);
- a `while (cond) { … }` **immediately followed by** `return si;` fuses: the
  loop's false test jumps straight to RET, and the (unreachable) `return`
  after the loop emits nothing.

```
top:    cmp [bp+6], si    ; while (count > si)
        ja  body
        jmp RET           ; loop exit IS the return
body:   …
        jmp top
        …                 ; other paths: jcc/jmp RET
RET:    mov ax, si        ; the tail `return si` (falls into the epilogue)
```

This is CHAR_DEVICE_IO's layout (RET at 0x2390). Before this idiom every exit
needed an explicit `goto ret`; now they are all structured `return si`. The
placement differs from the ordinary shared-return rule (block at the first
plain occurrence) — the reg-var gate defers it to the tail.

---

## `for (init; cond; upd) { … }` — the rotated/test-at-bottom loop

```
        <init>
      [ jmp test ]        ; entry jump — only when NOT "provable"
loop:
        <body>
        <upd>
        test:
        <cond>            ; jcc loop   when cond is TRUE (taken)
```
`init` first; then body+update; condition tested at the **bottom**; back-edge
is the condition's JCC. `for (; cond; )` (empty init/update) is therefore the
exact equivalent of a rotated `while` — body on top, test at the bottom.

The **entry `jmp test`** is emitted unless the first iteration *provably*
runs — i.e. `init` is `var = CONST`, `cond` compares that same `var` against a
constant, and the initial value already satisfies it (`<`, `<=`, `!=`):

- `for (i = 0; i < 18; i++)` → **provable** → no entry jump (falls straight
  into the body). *(lookup_token)*
- `for (i = nclus; DPB_PTR[4] >= i; i++)` → not provable → **entry `jmp
  test`** (rotated). *(invalidate_cached_fcb)*
- `for (; *p != '$'; p++)` → empty init → not provable → rotated. *(dos_fn_09)*

This mirrors MSC: it skips the entry jump only when it can see the loop must
execute at least once.

**Back-edge register seeding.** On a rotated `for`'s back-edge the condition
has just left a value live in a register, so the cache is seeded at the loop
top so the body's first use doesn't reload:
- a uchar assign in the condition (`(ch = read_byte()) != 0x0D`) leaves `ch`
  in **AL** → seed AL. *(read_line_to_buffer)*
- a **local** far-pointer deref (`*p != '$'`) leaves **ES:BX** = `p` → seed
  ES:BX. *(dos_fn_09)*  A **global** far_var deref (`DPB_PTR[4] >= i`) is
  **not** seeded — MSC reloads `les [addr]` each use. *(invalidate inner `for`s)*
Seeding applies only to the non-provable (rotated) form, where the bottom test
runs before the body on every entry.

---

## `do { … } while (cond);`

```
loop:
        <body>
        <cond>            ; jcc loop   when cond is TRUE (taken)
brk:
```
Body **first** (top, always runs once), condition at the **bottom**, back-edge
is the JCC. The break label is placed at the natural fall-through exit.

---

## Summary table

| Construct                         | Condition | Body          | Entry jump |
|-----------------------------------|-----------|---------------|------------|
| `if (c) {then}`                   | top       | below (inline)| —          |
| `if (c) {then} else {else}` (any cond) | top  | then first, else below | — (write `\|\|` as De Morgan `&&`) |
| `while (1)`                       | —         | top           | —          |
| `while (c)` (any cond)            | **top**   | below         | **none**   |
| `for`, provable 1st iteration     | bottom    | top           | none       |
| `for`, not provable (incl. `for(;c;)`) | bottom | top         | `jmp test` |
| `do … while (c)`                  | bottom    | top           | —          |

**Choosing the loop construct:**
- Need **test-at-top** (condition checked before the first iteration, no entry
  jump)? → **`while`**.
- Need **test-at-bottom / rotated** (body emitted first, entry `jmp test`)? →
  **`for`** — `for (; cond; )` for a bare rotated loop, or with init/update.
- A `for` with a provably-true first iteration (`for (i=0; i<N; i++)`) drops
  the entry jump.

### What no construct can do
Every loop body is emitted **adjacent to its condition** (inline). If the
target binary places a loop **body at the bottom**, reached by a *forward*
jump from the in-loop test, with early-exit code physically in between
(e.g. `read_path_chars`: `if (CURSOR <= COUNT) goto body; … 0xFFFF; return;
body: …`), that layout is **not reachable** from `while`/`for`/`do` — it needs
an explicit `goto body`. Keep the goto for exactly that case; everything else
(early-exit branching, single-entry loops) folds into the structured forms
above.
