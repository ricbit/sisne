# SISNE reconstruction — buildable, self-verifying source

Byte-exact reconstruction of the SCOPUS SISNE system (8086) — SISNE Plus
V3.30 R05, disk 1 dated 21.12.90.  Each `<game>.asm` is annotated assembly;
functions reverse-engineered to C live inline in
`;@compiled NAME ADDR SIZE` .. `;@endcompiled` regions.

`nasm_to_jwasm.py` (using `tiny_cc.py`, a minimal 16-bit C compiler that
reproduces MS C 3.x no-optimizer codegen) compiles those C regions back into
`db` bytes and emits JWasm-syntax assembly; JWasm assembles it to a flat
binary, which is then compared against the bundled reference ROM.

Message text is written with its accented letters (`"Trilha n\u00e3o
encontrada"`); nasm_to_jwasm.py converts them to the system's code-page
bytes before JWasm sees them, since JWasm has no notion of a code page.

See `tinycc.md` for the C-to-x86 codegen rules tiny_cc follows.

## Build

    make            # build every .bin and verify each == its .rom
    make build      # build only
    make clean

A correct build ends with `all bit-perfect`; any divergence prints
`<game>: MISMATCH` and `BUILD BROKEN` and fails.

Needs `python3` and [JWasm](https://github.com/Baron-von-Riedesel/JWasm) on PATH
(override with `make JWASM=/path/to/jwasm`).

## Files
- `boot.asm`, `init.asm`, `sisne_sis.asm`, `command_com.asm` — annotated source.
  `sisne_sis` is the system itself; `command_com` is its command interpreter.
- `boot.rom`, `init.rom`, `sisne_sis.rom`, `command_com.rom` — original
  reference images, extracted from the distribution disk (build target).
- `nasm_to_jwasm.py`, `tiny_cc.py` — the C-aware preprocessor and 16-bit C compiler.
- `tinycc.md` — tiny_cc codegen rules.
