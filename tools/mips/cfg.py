#!/usr/bin/env python3
"""Recover the true extent of a function in the H713 MIPS display firmware.

The firmware is built with out-of-line basic-block placement: a function's
blocks are *not* a contiguous address range, and unrelated functions sit
between them.  Two earlier passes over this image mis-attributed code because
they assumed "next function start" bounded the previous function -- notably
around `0x8b1a4810`, which sits 0x2d8 bytes past an unrelated `jr $ra`.

So work from control flow instead of from addresses:

    cfg.py FIRMWARE 8b1a4538              # blocks, calls, exits
    cfg.py FIRMWARE 8b1a4538 --contains 8b1a4810
    cfg.py FIRMWARE 8b1a4538 --listing    # full disassembly, in block order

A block ends at the first control transfer; MIPS delay slots mean the
instruction *after* the transfer still executes and belongs to the block.
Indirect jumps (`jr` on anything but `$ra`) terminate a block and are reported,
because a jump table we have not resolved is a hole in the recovered CFG and
should be visible rather than silently closed.
"""
import argparse
import bisect
import struct
import sys

from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs

BASE = 0x8B100000


def load(path):
    with open(path, "rb") as handle:
        return handle.read()


def word(image, va):
    return struct.unpack_from("<I", image, va - BASE)[0]


def parse_address(text):
    value = int(text, 16)
    return value if value >= BASE else value + BASE


class Transfer:
    """What an instruction does to control flow."""

    def __init__(self, kind, target=None, register=None):
        self.kind = kind          # 'branch' | 'jump' | 'call' | 'return' | 'indirect'
        self.target = target
        self.register = register


def classify(image, va):
    """Decode one instruction's control-flow effect, or None if it is straight-line."""
    insn = word(image, va)
    op = insn >> 26
    rs = (insn >> 21) & 0x1F
    rt = (insn >> 16) & 0x1F
    imm = insn & 0xFFFF
    offset = ((imm - 0x10000) if imm & 0x8000 else imm) << 2
    fallthrough = va + 8 + offset      # branches are relative to the delay slot

    if op == 0:
        funct = insn & 0x3F
        if funct == 0x08:              # jr
            if rs == 31:
                return Transfer("return")
            return Transfer("indirect", register=rs)
        if funct == 0x09:              # jalr
            return Transfer("call", register=rs)
        return None
    if op in (2, 3):                   # j / jal
        target = (va & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)
        return Transfer("jump" if op == 2 else "call", target=target)
    if op == 1:                        # REGIMM: bltz/bgez and their -al forms
        if rt in (0x10, 0x11):         # bltzal / bgezal
            return Transfer("call", target=fallthrough)
        if rt in (0x01, 0x11) and rs == 0:     # bgez $zero -- always taken
            return Transfer("jump", target=fallthrough)
        return Transfer("branch", target=fallthrough)
    if op in (4, 5, 6, 7, 20, 21, 22, 23):   # beq/bne/blez/bgtz and likely forms
        # `b label` assembles as `beq $zero, $zero`, and `blez $zero` is also
        # always taken.  Treating those as conditional pushes a fall-through
        # that never executes, which walks straight into the next function --
        # exactly how the 0x8b1a4538 / 0x8b1a48cc pair first read as one.
        unconditional = (op in (4, 20) and rs == 0 and rt == 0) or \
                        (op in (6, 22) and rs == 0)
        kind = "jump" if unconditional else "branch"
        return Transfer(kind, target=fallthrough)
    return None


def walk(image, entry):
    """Recursive descent from `entry`; returns (blocks, calls, indirects)."""
    limit = BASE + len(image)
    blocks = {}                        # start VA -> end VA (exclusive)
    calls = {}                         # target -> set of call sites
    indirects = []                     # (VA, register)
    pending = [entry]
    seen = set()

    while pending:
        start = pending.pop()
        if start in seen or not (BASE <= start < limit):
            continue
        seen.add(start)
        va = start
        while va < limit:
            transfer = classify(image, va)
            if transfer is None:
                va += 4
                continue
            delay = va + 4             # the delay slot belongs to this block
            if transfer.kind == "call":
                if transfer.target is not None:
                    calls.setdefault(transfer.target, set()).add(va)
                else:
                    indirects.append((va, f"jalr ${transfer.register}"))
                va += 8                # a call returns; keep decoding
                continue
            end = delay + 4
            blocks[start] = end
            if transfer.kind == "branch":
                pending.append(transfer.target)
                pending.append(end)    # not-taken path
            elif transfer.kind == "jump":
                pending.append(transfer.target)
            elif transfer.kind == "indirect":
                indirects.append((va, f"jr ${transfer.register}"))
            break
        else:
            blocks[start] = limit

    return merge(blocks), calls, indirects


def merge(blocks):
    """Coalesce blocks that abut or overlap into maximal ranges."""
    ranges = []
    for start in sorted(blocks):
        end = blocks[start]
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    return [tuple(r) for r in ranges]


def contains(ranges, va):
    starts = [r[0] for r in ranges]
    index = bisect.bisect_right(starts, va) - 1
    return index >= 0 and va < ranges[index][1]


def listing(image, ranges):
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    for start, end in ranges:
        print(f"; --- {start:#x} .. {end:#x} ---")
        for insn in md.disasm(image[start - BASE:end - BASE], start):
            print(f"0x{insn.address:08x}  {insn.mnemonic:8s} {insn.op_str}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("firmware")
    parser.add_argument("entry")
    parser.add_argument("--contains", help="report whether this VA is reachable code")
    parser.add_argument("--listing", action="store_true")
    args = parser.parse_args()

    image = load(args.firmware)
    entry = parse_address(args.entry)
    ranges, calls, indirects = walk(image, entry)

    total = sum(end - start for start, end in ranges) // 4
    print(f"entry {entry:#x}: {len(ranges)} block range(s), {total} instructions")
    for start, end in ranges:
        print(f"  {start:#010x} .. {end:#010x}  ({(end - start) // 4} insns)")

    if calls:
        print("calls:")
        for target in sorted(calls):
            sites = " ".join(f"{s:#x}" for s in sorted(calls[target]))
            print(f"  {target:#010x}  from {sites}")
    if indirects:
        print("unresolved transfers (CFG holes):")
        for va, what in indirects:
            print(f"  {va:#010x}  {what}")

    if args.contains:
        va = parse_address(args.contains)
        print(f"contains {va:#x}: {contains(ranges, va)}")
    if args.listing:
        listing(image, ranges)


if __name__ == "__main__":
    main()
