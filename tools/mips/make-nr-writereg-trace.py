#!/usr/bin/env python3
"""Generate (and self-test) the NRWinNode::WriteReg entry trace for display.bin.

Design: docs/hdmi-panel-source-design-2026-10-23.md section 10.8.  The
question is which dirty mask the firmware passes to NRWinNode::WriteReg
(0x8b1a48cc, NR vtable slot 4) when an HDMI source locks.  Only a mask with
bit 0x800 runs the AFBD source-0 frame programmer (0x8b1a4538).

Hook: the two prologue instructions at 0x8b1a48d0/48d4
(lui v0,0x8b20 ; addiu v0,v0,0x7024) become  j CAVE ; nop.  The cave counts
the call, records $a1 and the NR node's m_afbd_source_mode (this+0x60), keeps
a 16-entry ring, re-executes the two displaced instructions and jumps back to
0x8b1a48d8.  It uses only t0, t1, t8 and t9, which are dead at this point of
the prologue ($a0/$a1 are read, never written; $sp is already adjusted).

The trace page base is loaded as `lui t8, 0xad98` (kseg1 0xad980000 = ARM
0x4d980000) rather than the installer's relocatable 0xae34 form, and every
store offset is >= 0x100, so h713_mips_apply_comm_trace()'s relocation counts
(lui 0xae34 bases, stores at <= 0x90) are unchanged.  That function memsets
the whole page before installing, so all slots below start at zero.

Trace page layout (offsets from 0x4d980000):
    +0x100  calls
    +0x104  last mask
    +0x108  OR of every mask
    +0x10c  calls whose mask has 0x800
    +0x110  last mask seen while this+0x60 == 1 (HDMI / capture mode)
    +0x114  calls while this+0x60 == 1
    +0x118  ring index (free-running)
    +0x120  ring[16] of {mask, this+0x60}, 8 bytes each (to +0x19f)

    make-nr-writereg-trace.py --c-rows      # rows for h713_mips_comm_trace_patches
    make-nr-writereg-trace.py --self-test   # encoding + emulation checks
"""
import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "local/mips-display/board-b-mips/display.bin"
BASE = 0x8B100000            # MIPS VA of display.bin offset 0
ARM_DELTA = 0x40000000       # kseg0 0x8b... -> ARM 0x4b...

HOOK = 0x8B1A48D0
HOOK_ORIG = (0x3C028B20, 0x24427024)   # lui v0,0x8b20 ; addiu v0,v0,0x7024
RESUME = 0x8B1A48D8
CAVE = 0x8B100C40            # zero run 0x4b100c10..0x4b100fff, unused by comm trace
TRACE_HI = 0xAD98

R = dict(zero=0, v0=2, a0=4, a1=5, t0=8, t1=9, t8=24, t9=25)


def i_type(op, rs, rt, imm):
    return (op << 26) | (R[rs] << 21) | (R[rt] << 16) | (imm & 0xFFFF)


def r_type(rs, rt, rd, sa, funct):
    return (R[rs] << 21) | (R[rt] << 16) | (R[rd] << 11) | (sa << 6) | funct


lui = lambda rt, imm: i_type(0x0F, "zero", rt, imm)
lw = lambda rt, off, base: i_type(0x23, base, rt, off)
sw = lambda rt, off, base: i_type(0x2B, base, rt, off)
addiu = lambda rt, rs, imm: i_type(0x09, rs, rt, imm)
andi = lambda rt, rs, imm: i_type(0x0C, rs, rt, imm)
or_ = lambda rd, rs, rt: r_type(rs, rt, rd, 0, 0x25)
addu = lambda rd, rs, rt: r_type(rs, rt, rd, 0, 0x21)
sll = lambda rd, rt, sa: r_type("zero", rt, rd, sa, 0x00)
NOP = 0


def j(target):
    return (0x02 << 26) | ((target >> 2) & 0x3FFFFFF)


def cave_words():
    """Cave program; branches are resolved against their own addresses."""
    prog = []
    labels = {}

    def emit(word):
        prog.append(word)

    def label(name):
        labels[name] = CAVE + 4 * len(prog)

    def branch(op, rs, rt, name):
        prog.append(("br", op, rs, rt, name, CAVE + 4 * len(prog)))

    emit(lui("t8", TRACE_HI))
    emit(lw("t9", 0x100, "t8")); emit(addiu("t9", "t9", 1)); emit(sw("t9", 0x100, "t8"))
    emit(sw("a1", 0x104, "t8"))
    emit(lw("t9", 0x108, "t8")); emit(or_("t9", "t9", "a1")); emit(sw("t9", 0x108, "t8"))
    emit(andi("t9", "a1", 0x800))
    branch(0x04, "t9", "zero", "no800"); emit(NOP)            # beq t9,zero
    emit(lw("t9", 0x10C, "t8")); emit(addiu("t9", "t9", 1)); emit(sw("t9", 0x10C, "t8"))
    label("no800")
    emit(lw("t0", 0x60, "a0"))                                 # m_afbd_source_mode
    emit(addiu("t1", "t0", -1))
    branch(0x05, "t1", "zero", "notcap"); emit(NOP)           # bne t1,zero
    emit(sw("a1", 0x110, "t8"))
    emit(lw("t9", 0x114, "t8")); emit(addiu("t9", "t9", 1)); emit(sw("t9", 0x114, "t8"))
    label("notcap")
    emit(lw("t9", 0x118, "t8"))
    emit(andi("t1", "t9", 0xF)); emit(sll("t1", "t1", 3)); emit(addu("t1", "t1", "t8"))
    emit(sw("a1", 0x120, "t1")); emit(sw("t0", 0x124, "t1"))
    emit(addiu("t9", "t9", 1)); emit(sw("t9", 0x118, "t8"))
    emit(HOOK_ORIG[0]); emit(HOOK_ORIG[1])                     # displaced prologue
    emit(j(RESUME)); emit(NOP)

    out = []
    for w in prog:
        if isinstance(w, tuple):
            _, op, rs, rt, name, pc = w
            off = (labels[name] - (pc + 4)) >> 2
            w = i_type(op, rs, rt, off)
        out.append(w)
    return out


def patch_rows():
    """(ARM address, expected, replacement): cave first, hook last, as the
    existing table orders each trampoline before the jump into it."""
    arm = lambda va: va - ARM_DELTA
    rows = [(arm(CAVE + 4 * i), 0, w) for i, w in enumerate(cave_words())]
    rows.append((arm(HOOK), HOOK_ORIG[0], j(CAVE)))
    rows.append((arm(HOOK + 4), HOOK_ORIG[1], NOP))
    return rows


def c_rows():
    from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    lines = ["\t/* NRWinNode::WriteReg entry -> record dirty mask/source mode (+0x100..). */"]
    for addr, exp, rep in patch_rows():
        va = addr + ARM_DELTA
        ins = next(md.disasm(struct.pack("<I", rep), va), None)
        text = f"{ins.mnemonic} {ins.op_str}".strip() if ins else "?"
        lines.append(f"\t{{ 0x{addr:08x}, 0x{exp:08x}, 0x{rep:08x} }}, /* {text} */")
    return "\n".join(lines)


def emulate(image, patched, mask, mode):
    """Run 0x8b1a48cc..0x8b1a48d8 under unicorn; return (regs, trace page, stack)."""
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_SP,
                                    UC_MIPS_REG_RA, UC_MIPS_REG_PC, UC_MIPS_REG_V0,
                                    UC_MIPS_REG_S0, UC_MIPS_REG_S1)
    img = bytearray(image)
    if patched:
        for addr, exp, rep in patch_rows():
            off = addr + ARM_DELTA - BASE
            assert struct.unpack_from("<I", img, off)[0] == exp, f"{addr:#x} not pristine"
            struct.pack_into("<I", img, off, rep)
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    phys = lambda va: va & 0x1FFFFFFF
    size = (len(img) + 0xFFFF) & ~0xFFFF
    uc.mem_map(phys(BASE), size)
    uc.mem_write(phys(BASE), bytes(img))
    trace = 0xAD980000
    uc.mem_map(phys(trace), 0x1000)
    node = 0x8C000000
    uc.mem_map(phys(node), 0x1000)
    uc.mem_write(phys(node) + 0x60, struct.pack("<I", mode))
    stack = 0x8C100000
    uc.mem_map(phys(stack) - 0x10000, 0x20000)
    uc.reg_write(UC_MIPS_REG_A0, node)
    uc.reg_write(UC_MIPS_REG_A1, mask)
    uc.reg_write(UC_MIPS_REG_SP, stack)
    uc.reg_write(UC_MIPS_REG_RA, 0x8B1A0000)
    uc.reg_write(UC_MIPS_REG_S0, 0x11111111)
    uc.reg_write(UC_MIPS_REG_S1, 0x22222222)
    uc.emu_start(0x8B1A48CC, RESUME, count=200)
    regs = {n: uc.reg_read(r) for n, r in [("pc", UC_MIPS_REG_PC), ("sp", UC_MIPS_REG_SP),
            ("v0", UC_MIPS_REG_V0), ("a0", UC_MIPS_REG_A0), ("a1", UC_MIPS_REG_A1),
            ("ra", UC_MIPS_REG_RA), ("s0", UC_MIPS_REG_S0), ("s1", UC_MIPS_REG_S1)]}
    page = bytes(uc.mem_read(phys(trace), 0x1000))
    stk = bytes(uc.mem_read(phys(stack) - 0x100, 0x200))
    return regs, page, stk, uc


def self_test(uboot_src=None):
    from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs
    image = IMAGE.read_bytes()
    fails = []
    # 1. every site pristine, cave inside the free zero run, no overlap with the
    #    existing comm-trace table.
    import re
    src = Path(uboot_src or ROOT / "external/u-boot/arch/arm/mach-sunxi/h713_mips.c").read_text()
    t0 = src.index("h713_mips_comm_trace_patches[] = {")
    table = src[t0:src.index("};", t0)]
    used = {int(a, 16) for a in re.findall(r"\{\s*(0x4b1[0-9a-f]{5})\s*,", table)}
    for addr, exp, rep in patch_rows():
        word = struct.unpack_from("<I", image, addr + ARM_DELTA - BASE)[0]
        if word != exp:
            fails.append(f"{addr:#x}: image {word:#x} != expected {exp:#x}")
        if addr in used:
            fails.append(f"{addr:#x} already in h713_mips_comm_trace_patches")
    last = max(a for a, _, _ in patch_rows() if a < 0x4B101000)
    if not (0x4B100C10 <= CAVE - ARM_DELTA and last < 0x4B101000):
        fails.append("cave outside the free run")
    # 2. the installer's relocation counts are untouched.
    for _, _, w in patch_rows():
        op, reg, imm = w >> 26, (w >> 16) & 0x1F, w & 0xFFFF
        if op == 0x0F and reg in (24, 26) and imm == 0xAE34:
            fails.append("cave uses the relocatable 0xae34 base")
        if op == 0x2B and ((w >> 21) & 0x1F) in (24, 26) and imm <= 0x90:
            fails.append(f"cave store {w:#x} would be relocated/counted")
    # 3. encoder round trip through capstone.
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    for addr, _, w in patch_rows():
        if next(md.disasm(struct.pack("<I", w), addr + ARM_DELTA), None) is None:
            fails.append(f"{addr:#x}: {w:#x} does not decode")
    # 4. emulation: patched prologue ends in the same state as the original,
    #    and the trace slots say what was passed.
    for mask, mode in [(0x7E06, 1), (0x0400, 1), (0x0800, 2), (0xFFFFFFFF, 2), (0x6000, 0)]:
        r0, _, s0, _ = emulate(image, False, mask, mode)
        r1, page, s1, _ = emulate(image, True, mask, mode)
        # unicorn reports the stop PC at a block boundary before `until`, which
        # differs between the two runs; every other register must match, and
        # the displaced lui/addiu must have produced the stock v0.
        r0.pop("pc"); r1.pop("pc")
        if r0 != r1:
            fails.append(f"mask {mask:#x}: registers differ {r0} vs {r1}")
        if r1["v0"] != 0x8B207024:
            fails.append(f"mask {mask:#x}: v0 {r1['v0']:#x} after the displaced prologue")
        if s0 != s1:
            fails.append(f"mask {mask:#x}: stack differs")
        get = lambda o: struct.unpack_from("<I", page, o)[0]
        want = {0x100: 1, 0x104: mask, 0x108: mask, 0x10C: int(bool(mask & 0x800)),
                0x110: mask if mode == 1 else 0, 0x114: int(mode == 1), 0x118: 1,
                0x120: mask, 0x124: mode}
        for o, v in want.items():
            if get(o) != v:
                fails.append(f"mask {mask:#x} mode {mode}: +{o:#x} = {get(o):#x}, want {v:#x}")
        if any(page[:0x100]) or any(page[0x1A0:]):
            fails.append("cave wrote outside +0x100..+0x19f")
    # 5. ring wrap and accumulation over 20 calls on one page.
    from unicorn.mips_const import UC_MIPS_REG_A1, UC_MIPS_REG_SP, UC_MIPS_REG_A0
    _, _, _, uc = emulate(image, True, 1, 1)
    for n in range(2, 21):
        uc.reg_write(UC_MIPS_REG_A1, n << 4)
        uc.reg_write(UC_MIPS_REG_SP, 0x8C100000)
        uc.emu_start(0x8B1A48CC, RESUME, count=200)
    page = bytes(uc.mem_read(0x0D980000, 0x200))
    get = lambda o: struct.unpack_from("<I", page, o)[0]
    if get(0x100) != 20 or get(0x118) != 20:
        fails.append(f"20 calls: count {get(0x100)} index {get(0x118)}")
    if get(0x120 + 8 * (19 % 16)) != (20 << 4):
        fails.append("ring slot of call 20 wrong")
    for f in fails:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else "passed",
          f"({len(patch_rows())} patch words, cave {CAVE:#x}..{CAVE + 4 * len(cave_words()) - 4:#x})")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--c-rows", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--uboot-src", help="h713_mips.c whose comm-trace table must not overlap "
                    "(default: the external/u-boot checkout)")
    a = ap.parse_args()
    if a.self_test:
        return self_test(a.uboot_src)
    print(c_rows())
    return 0


if __name__ == "__main__":
    sys.exit(main())
