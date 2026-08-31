#!/usr/bin/env python3
"""Survey which display blocks the H713 MIPS firmware actually addresses.

    block-survey.py FIRMWARE
    block-survey.py FIRMWARE --sites 0xba00     # list every site for one block

Answers a question that three sessions of register permutation could not: of the
display blocks we know about, which ones does the firmware's own code touch, and
how much of its code touches each. That is not the same as which blocks carry
per-frame traffic -- see the caveat at the bottom -- but it is decisive in the
negative direction, and the negative is what has been expensive here.

METHOD

The firmware reaches peripherals through an aperture documented in
mips-firmware-address-map: MIPS address = ARM physical + 0xB5000000, so ARM
0x05600000 (AFBD) is MIPS 0xBA600000. Every earlier search of this image for
display registers came up empty because it searched for the ARM form.

MMIO addresses in this image are formed as `lui $rt, 0xbaXX` followed by a
load/store at a 16-bit displacement, so counting `lui` immediates in the
0xba00..0xbaff range enumerates the blocks the code can reach. The encoding is
fixed: lui is opcode 0x0F with rs = 0, which in little-endian file order is
[imm_lo, imm_hi, 0x0<rt>, 0x3C].

WHY THE ZEROES ARE TRUSTWORTHY

This project has a standing rule that a scan answering "none" must be shown
capable of answering "one" -- an earlier cross-reference scan reported zero
stores to a global because it only tracked lui-formed bases, and that near-miss
would have supported a confident and wrong conclusion.

This scan clears that bar in the same run it reports: it finds eight populated
blocks including AFBD, whose writes to 0x05600010 are independently confirmed on
hardware. A block reading zero here is therefore not addressed by any
lui-formed reference in the image.

The residual gap is narrow and worth stating: an address materialised some other
way -- loaded whole from a data word, or computed from a base register held
across a call -- would not be counted. Nothing in this firmware's observed MMIO
idiom does that, but "zero lui sites" is the precise claim, not "provably never
accessed".

CAVEAT ON RANKING

Site counts measure how much *code* addresses a block, not how much traffic it
carries at runtime. AFBD is the block proven to move per frame on hardware, and
it does not top this table. Read the ranking as where the firmware's logic
lives, not where the pixels flow.
"""

import argparse
import collections
import pathlib
import sys

# Same base as disasm.py, and the same reason for centralising it: a helper
# carrying 0x8b101000 once described unrelated code as the CPU_COMM adapter.
BASE = 0x8B100000

# ARM physical + this = MIPS virtual (KSEG1 uncached). Derived from the
# firmware's own byte/halfword/word accessors; see mips-firmware-address-map.
ARM_TO_MIPS = 0xB5000000

APERTURE_LO, APERTURE_HI = 0xBA00, 0xBAFF

# Only blocks confirmed by an independent source: the live register captures,
# the U-Boot bring-up tables, or the stock-driver disassembly. Deliberately not
# a guess list -- an unlabelled row means "we have never characterised this",
# which is exactly the finding worth surfacing.
KNOWN_BLOCKS = {
    0x05000000: "composition page (firmware-owned; carries the content taps)",
    0x05140000: "display route",
    0x051c0000: "LVDS PHY",
    0x05200000: "VBlender-ish",
    0x05240000: "GE2D core (ARM-side OSD device)",
    0x0525c000: "mixer",
    0x05280000: "window registers",
    0x05600000: "AFBD (proven per-frame on hardware)",
    0x05700000: "TVTOP",
    0x05880000: "TCON",
    0x058c0000: "PLL",
}


def lui_sites(image):
    """-> {immediate: [virtual address of each lui, ...]} within the aperture."""
    sites = collections.defaultdict(list)
    for i in range(0, len(image) - 3, 4):
        # lui: opcode 0x0F (top 6 bits of the last byte = 0b001111) and rs = 0.
        if image[i + 3] != 0x3C or (image[i + 2] & 0xE0) != 0x00:
            continue
        imm = image[i] | (image[i + 1] << 8)
        if APERTURE_LO <= imm <= APERTURE_HI:
            sites[imm].append(BASE + i)
    return sites


def arm_of(imm):
    return (imm << 16) - ARM_TO_MIPS


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="raw firmware, e.g. display.bin")
    ap.add_argument("--sites", help="list every site for one 0xbaXX immediate")
    args = ap.parse_args()

    image = pathlib.Path(args.image).read_bytes()
    sites = lui_sites(image)

    if not sites:
        print("no aperture references found at all -- wrong image, or the "
              "base/aperture constants are wrong. Refusing to report zeroes "
              "from a scan that found nothing.", file=sys.stderr)
        return 1

    if args.sites:
        imm = int(args.sites, 16)
        found = sites.get(imm, [])
        print(f"lui 0x{imm:04x}  (ARM 0x{arm_of(imm):08x}): {len(found)} sites")
        for va in found:
            print(f"  0x{va:08x}")
        return 0

    print(f"{'MIPS':>7}  {'ARM phys':>10}  {'sites':>5}   block")
    for imm in sorted(sites, key=lambda k: -len(sites[k])):
        arm = arm_of(imm)
        label = KNOWN_BLOCKS.get(arm, "** not characterised **")
        print(f"  0x{imm:04x}  0x{arm:08x}  {len(sites[imm]):>5}   {label}")

    print(f"\ntotal aperture lui sites: {sum(len(v) for v in sites.values())}")

    absent = [(a, n) for a, n in sorted(KNOWN_BLOCKS.items())
              if not any(arm_of(i) == a for i in sites)]
    if absent:
        print(f"\nknown blocks with ZERO lui sites ({len(absent)}) -- the "
              f"scan found {len(sites)} populated blocks in the same pass, "
              "so it demonstrably can detect one:")
        for arm, label in absent:
            print(f"  0x{arm:08x}   {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
