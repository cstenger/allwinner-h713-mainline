#!/usr/bin/env python3
"""Verify PLL byte-reader hook access widths and fallback without any stores."""
import argparse
import hashlib
import importlib.util
import struct
import random
import json
from pathlib import Path
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.mips_const import UC_CPU_MIPS32_24KC, UC_MIPS_REG_0, UC_MIPS_REG_PC, UC_MIPS_REG_2, UC_MIPS_REG_5, UC_MIPS_REG_6
s = importlib.util.spec_from_file_location('byte', Path(__file__).with_name('make-audio-pll-byte-read.py'))
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path, help='private board-B display.bin')
    args = parser.parse_args()
    fw = args.firmware.read_bytes()
    if hashlib.sha256(fw).hexdigest() != m.word.monitor.FW_SHA:
        raise ValueError('firmware SHA256 does not match board-B image')
    shim = m.word.build_shim('audio-pll-byte-read.S', m.SHIM_SIZE, m.SHIM_SHA)
    rng = random.Random(713)
    cases = 0
    for addr in [0xbb880000 + i for i in range(0, 32, 4)] + [0xbb840000, 0xbb890000, 0xbb87fffc]:
        for _ in range(24):
            u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
            u.ctl_set_cpu_model(UC_CPU_MIPS32_24KC)
            u.mem_map(0xb100000, len(fw) + 0xfff & ~0xfff)
            u.mem_write(0xb100000, fw)
            for a, e, w in m.records(shim):
                u.mem_write(a & 0x1fffffff, struct.pack('<I', w))
            u.mem_map(0x1b840000, 0x60000)
            u.mem_map(0x100000, 0x10000)
            value = rng.getrandbits(32)
            a1 = rng.getrandbits(32)
            u.mem_write(addr & 0x1fffffff, struct.pack('<I', value))
            u.mem_write(0x108010, struct.pack('<I', a1))
            for reg, v in [(2, addr), (29, 0x80108000)]:
                u.reg_write(UC_MIPS_REG_0 + reg, v)
            reads = []
            writes = []

            def read(u, access, a, size, v, data):
                if a & 0x1fffffff >= 0x1b840000:
                    reads.append((a & 0x1fffffff, size))

            def write(u, access, a, size, v, data):
                writes.append((a, size))

            def code(u, a, size, data):
                if a == 0x8b18011c:
                    u.emu_stop()
            u.hook_add(UC_HOOK_MEM_READ, read)
            u.hook_add(UC_HOOK_MEM_WRITE, write)
            u.hook_add(UC_HOOK_CODE, code)
            u.emu_start(0x8b180114, 0, count=100)
            target = addr in (0xbb880000, 0xbb880004, 0xbb88000c, 0xbb880010)
            expected_reads = [(addr + i & 0x1fffffff, 1) for i in range(4)] if target else [(addr & 0x1fffffff, 4)]
            assert reads == expected_reads, reads
            assert not writes and u.reg_read(UC_MIPS_REG_PC) == 0x8b18011c
            assert u.reg_read(UC_MIPS_REG_6) == value and u.reg_read(UC_MIPS_REG_5) == a1 and (u.reg_read(UC_MIPS_REG_2) == addr)
            cases += 1
    print(json.dumps(dict(cases=cases, result='PASS', coverage='exact four scalar PLL addresses, four LBU widths, stock LW fallback, hook delay-slot a1 load, no stores')))


if __name__ == '__main__':
    main()
