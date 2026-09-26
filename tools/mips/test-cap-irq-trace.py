#!/usr/bin/env python3
"""Emulate the VIncap trace trampoline and compare it with stock execution."""

import importlib.util
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN
from unicorn import UC_MODE_MIPS32
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "cap_patch", HERE / "make-cap-irq-trace-uboot.py")
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)

HOOK = 0x8B1863A4
STOP = 0x8B1863AC
TRACE_PHYS = 0x0D980000
STACK = 0x80110000


def pack(word):
    return struct.pack("<I", word)


def run(mask, patched):
    emu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    emu.mem_map(0x0B100000, 0x200000)
    emu.mem_map(TRACE_PHYS, 0x1000)
    emu.mem_map(0x00100000, 0x20000)
    emu.mem_map(0x1B940000, 0x1000)
    # The stock instruction pair replaced/retained by the guarded hook.
    emu.mem_write(HOOK & 0x1FFFFFFF, pack(0x8C470008))
    emu.mem_write((HOOK + 4) & 0x1FFFFFFF, pack(0x00091827))
    if patched:
        for address, _expected, word in PATCH.CAPTURE_RECORDS[:29]:
            runtime = address + 0x40000000
            # The existing installer relocates the trace page to reserved DRAM.
            if word == 0x3C18AE34:
                word = 0x3C18AD98
            emu.mem_write(runtime & 0x1FFFFFFF, pack(word))

    for register in range(1, 32):
        emu.reg_write(UC_MIPS_REG_0 + register, 0x100100 + register * 16)
    emu.reg_write(UC_MIPS_REG_0 + 2, 0xBB940000)  # v0
    emu.reg_write(UC_MIPS_REG_0 + 9, mask)        # t1
    emu.reg_write(UC_MIPS_REG_0 + 29, STACK)      # sp
    emu.mem_write(0x1B940008, pack(0xA5A55A5A))
    emu.mem_write(TRACE_PHYS + 0x84,
                  struct.pack("<4I", 100, 200, 300, 400))
    emu.hook_add(
        UC_HOOK_CODE,
        lambda uc, address, _size, _data:
            uc.emu_stop() if address == STOP else None)
    emu.emu_start(HOOK, 0, count=100)
    if emu.reg_read(UC_MIPS_REG_PC) != STOP:
        raise AssertionError(f"did not return to decoder for mask {mask:#x}")
    registers = [emu.reg_read(UC_MIPS_REG_0 + r) for r in range(32)]
    counters = struct.unpack("<4I", emu.mem_read(TRACE_PHYS + 0x84, 16))
    return registers, counters


def main():
    for mask in range(8):
        stock_registers, _ = run(mask, False)
        traced_registers, counters = run(mask, True)
        if traced_registers != stock_registers:
            changed = [i for i, pair in enumerate(
                       zip(stock_registers, traced_registers))
                       if pair[0] != pair[1]]
            raise AssertionError(f"GPR mismatch for mask {mask:#x}: {changed}")
        expected = (101, 200 + bool(mask & 1), 300 + bool(mask & 2),
                    400 + bool(mask & 4))
        if counters != expected:
            raise AssertionError(
                f"counter mismatch for mask {mask:#x}: {counters} != {expected}")
    print("PASS: all 8 VIncap masks; GPRs and stack pointer preserved; "
          "event counters exact")


if __name__ == "__main__":
    main()
