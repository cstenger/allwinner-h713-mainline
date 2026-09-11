#!/usr/bin/env python3
"""Map every MMIO access in the image by tracking lui-loaded bases across offsets.

block-survey.py counts lui SITES, which undercounts a block reached through one
lui and many displacements -- that is how 0x05180000 read as "1 site" and sat
unexamined for months.

THE CORRECTNESS TRAP, hit 2026-09-10. A tracker that records "register r holds
base B" must INVALIDATE r the moment anything else defines it. The first version
of this tool did not, so after

    lui  $s0, 0xba1c        # some unrelated constant
    ...
    move $s0, $a0           # $s0 is now a C++ object pointer
    sw   $t3, 0x6c($s0)     # a struct field store

it reported a write to 0x051c006c that does not exist. That false positive was
briefly believed, and it is exactly the kind of error that costs a board run.

So: every instruction's destination register is cleared unless the instruction
is one of the two forms that legitimately propagate a base (lui, or addiu from
an already-tracked base). Calls clobber the o32 caller-saved set.

    block-map.py FIRMWARE                 # per-block register counts
    block-map.py FIRMWARE 0x05180000      # every access in one block
"""
import struct, sys

BASE = 0x8B100000
APERTURE = 0xB5000000          # MIPS address = ARM physical + this

LOADS  = {0x20, 0x21, 0x23, 0x24, 0x25}
STORES = {0x28, 0x29, 0x2B}
# o32 caller-saved: at, v0-v1, a0-a3, t0-t9, ra
CLOBBERED_BY_CALL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25, 31}


def defined_register(w):
    """Which register does this instruction write? None if it writes no GPR."""
    op = w >> 26
    rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    if op == 0x00:                                  # SPECIAL
        funct = w & 0x3F
        if funct in (0x08, 0x09):                   # jr, jalr
            return rd if funct == 0x09 else None
        if funct in (0x18, 0x19, 0x1A, 0x1B):       # mult/multu/div/divu -> hi/lo
            return None
        return rd
    if op == 0x1C:                                  # SPECIAL2 (mul, madd...)
        return rd if (w & 0x3F) == 0x02 else rd
    if op == 0x1F:                                  # SPECIAL3 (ins, ext)
        return rt
    if op in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F):
        return rt                                   # addi..lui
    if op in LOADS:
        return rt
    if op == 0x01:                                  # REGIMM: bltzal/bgezal link
        return 31 if ((w >> 16) & 0x1E) == 0x10 else None
    return None


def scan(image):
    n = len(image) // 4
    words = struct.unpack("<%dI" % n, image[: n * 4])
    base = {}
    hits = {}
    for i, w in enumerate(words):
        va = BASE + i * 4
        op = w >> 26
        rs, rt = (w >> 21) & 31, (w >> 16) & 31
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm

        # Record the access BEFORE applying this instruction's own definition,
        # so `lw $v0, 0x20($v0)` is still attributed to the old base.
        if op in LOADS | STORES and rs in base:
            full = base[rs] + simm
            if 0xBA000000 <= full < 0xBB000000:
                arm = full - APERTURE
                hits.setdefault(arm & 0xFFFF0000, {}).setdefault(arm, set()).add(
                    "w" if op in STORES else "r"
                )

        if op == 3 or (op == 0 and (w & 0x3F) == 0x09):      # jal / jalr
            for r in CLOBBERED_BY_CALL:
                base.pop(r, None)
            continue

        dst = defined_register(w)
        if dst is None or dst == 0:
            continue
        if op == 0x0F:                                       # lui
            base[dst] = imm << 16
        elif op == 0x09 and rs in base:                      # addiu from a base
            base[dst] = base[rs] + simm
        else:
            base.pop(dst, None)                              # anything else kills it
    return hits


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else (
        "/home/chris/Projects/h713/local/mips-display/board-b-mips/display.bin"
    )
    want = int(sys.argv[2], 16) if len(sys.argv) > 2 else None
    hits = scan(open(path, "rb").read())
    for blk in sorted(hits):
        regs = hits[blk]
        written = sum(1 for a in regs if "w" in regs[a])
        print(f"=== {blk:#010x}   {len(regs)} distinct registers, {written} written")
    if want is not None:
        print(f"\n--- {want:#010x} ---")
        for a in sorted(hits.get(want, {})):
            print(f"   {a:#010x}  {'/'.join(sorted(hits[want][a]))}")


if __name__ == "__main__":
    main()
