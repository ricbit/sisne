# SISNE reconstruction — buildable, self-verifying source

Byte-exact reconstruction of the 1983 SCOPUS SISNE system (8086). Each
`<game>.asm` is annotated assembly; functions reverse-engineered to C live
inline in `;@compiled NAME ADDR SIZE` .. `;@endcompiled` regions.

`nasm_to_jwasm.py` (using `tiny_cc.py`, a minimal 16-bit C compiler that
reproduces MS C 3.x no-optimizer codegen) compiles those C regions back into
`db` bytes and emits JWasm-syntax assembly; JWasm assembles it to a flat
binary, which is then compared against the bundled reference ROM.

See `tinycc.md` for the C-to-x86 codegen rules tiny_cc follows.

## Build

    make            # build boot/init/sisne_sis .bin and verify each == its .rom
    make build      # build only
    make clean

A correct build ends with `all bit-perfect`; any divergence prints
`<game>: MISMATCH` and `BUILD BROKEN` and fails.

Needs `python3` and [JWasm](https://github.com/Baron-von-Riedesel/JWasm) on PATH
(override with `make JWASM=/path/to/jwasm`).

## Files
- `boot.asm`, `init.asm`, `sisne_sis.asm` — annotated reconstruction source.
- `boot.rom`, `init.rom`, `sisne_sis.rom` — original reference images (build target).
- `nasm_to_jwasm.py`, `tiny_cc.py` — the C-aware preprocessor and 16-bit C compiler.
- `tinycc.md` — tiny_cc codegen rules.
