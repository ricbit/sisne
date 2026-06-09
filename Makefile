# Build the SISNE reconstruction binaries from the annotated .asm sources and
# verify each is bit-perfect against the bundled reference ROM.
#
# Pipeline per game:  <game>.asm  --nasm_to_jwasm.py-->  <game>.p.asm  --jwasm-->  <game>.bin
# nasm_to_jwasm.py imports tiny_cc.py to compile the C embedded in the
# ;@compiled .. ;@endcompiled regions back into `db` bytes (see tinycc.md).
#
# Requires: python3, and JWasm (https://github.com/Baron-von-Riedesel/JWasm).
#
#   make            build all .bin, then verify each matches its .rom
#   make build      build only (no comparison)
#   make clean      remove generated .p.asm and .bin

PYTHON ?= python3
JWASM  ?= jwasm

GAMES := boot init sisne_sis
BINS  := $(addsuffix .bin,$(GAMES))

all: verify

build: $(BINS)

%.p.asm: %.asm tiny_cc.py nasm_to_jwasm.py
	$(PYTHON) nasm_to_jwasm.py $< $@

%.bin: %.p.asm
	$(JWASM) -nologo -bin -Fo=$@ $<

# Bit-perfect check against the bundled reference ROMs. Fails loudly if a build
# diverges from the original image.
verify: $(BINS)
	@ok=1; for g in $(GAMES); do \
	  if cmp -s $$g.bin $$g.rom; then echo "  $$g: bit-perfect"; \
	  else echo "  $$g: MISMATCH against $$g.rom" >&2; ok=0; fi; \
	done; \
	if [ $$ok -ne 1 ]; then echo "BUILD BROKEN" >&2; exit 1; fi; \
	echo "all bit-perfect"

clean:
	rm -f $(BINS) $(addsuffix .p.asm,$(GAMES))

.PHONY: all build verify clean
