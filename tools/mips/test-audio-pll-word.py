#!/usr/bin/env python3
"""Execute both patched stock epilogues; verify MMIO width, lanes and ABI."""
import argparse
import hashlib
import importlib.util
import struct
import random
import json
from pathlib import Path
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.mips_const import UC_CPU_MIPS32_24KC, UC_MIPS_REG_0, UC_MIPS_REG_PC
spec = importlib.util.spec_from_file_location('word', Path(__file__).with_name('make-audio-pll-word.py'))
word = importlib.util.module_from_spec(spec)
spec.loader.exec_module(word)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path, help='private board-B display.bin')
    args = parser.parse_args()
    fw = args.firmware.read_bytes()
    if hashlib.sha256(fw).hexdigest() != word.monitor.FW_SHA:
        raise ValueError('firmware SHA256 does not match board-B image')
    shim = word.build_shim()
    rng = random.Random(713)
    cases = 0
    for masked in (False, True):
        for addr in [0xbb880000 + i for i in range(32)] + [0xbb87ffff, 0xbb890001, 0xbb840003]:
            for _ in range(8):
                u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
                u.ctl_set_cpu_model(UC_CPU_MIPS32_24KC)
                u.mem_map(0xb100000, len(fw) + 0xfff & ~0xfff)
                u.mem_write(0xb100000, fw)
                for a, expected, new in word.records(shim):
                    u.mem_write(a & 0x1fffffff, struct.pack('<I', new))
                u.mem_map(0x100000, 0x10000)
                u.mem_map(0x1b840000, 0x60000)
                aligned = addr & ~3
                initial = rng.getrandbits(32)
                value = rng.getrandbits(32)
                u.mem_write(aligned & 0x1fffffff, struct.pack('<I', initial))
                stop = 0x8010f000
                sp = 0x80108000
                v0 = rng.getrandbits(32)
                saved = [rng.getrandbits(32) for _ in range(3)]
                layout = [saved[0], saved[1], saved[2], stop] if masked else [saved[0], saved[1], stop]
                u.mem_write((sp & 0x1fffffff) + (16 if masked else 20), struct.pack('<' + 'I' * len(layout), *layout))
                for r, v in [(4, addr), (17, value), (29, sp), (2, v0)]:
                    u.reg_write(UC_MIPS_REG_0 + r, v)
                writes = []
                reads = []

                def memwrite(u, access, a, size, v, data):
                    writes.append((a & 0x1fffffff, size, v))

                def memread(u, access, a, size, v, data):
                    reads.append((a & 0x1fffffff, size))

                def code(u, a, size, data):
                    if a == stop:
                        u.emu_stop()
                u.hook_add(UC_HOOK_MEM_WRITE, memwrite)
                u.hook_add(UC_HOOK_MEM_READ, memread)
                u.hook_add(UC_HOOK_CODE, code)
                u.emu_start(0x8b18042c if masked else 0x8b1803c4, 0, count=100)
                target = 0xbb880000 <= addr < 0xbb880014 and (not 0xbb880008 <= addr < 0xbb88000c)
                lane = addr & 3
                expected = initial & ~(255 << 8 * lane) | (value & 255) << 8 * lane
                assert struct.unpack('<I', u.mem_read(aligned & 0x1fffffff, 4))[0] == expected
                assert len(writes) == 1 and writes[0][:2] == ((aligned if target else addr) & 0x1fffffff, 4 if target else 1), writes
                mmio_reads = [x for x in reads if x[0] >= 0x1b840000]
                assert mmio_reads == ([(aligned & 0x1fffffff, 4)] if target else []), mmio_reads
                assert u.reg_read(UC_MIPS_REG_PC) == stop
                for r, v in [(16, saved[0]), (17, saved[1]), (29, sp + 32), (31, stop), (2, v0)] + ([(18, saved[2])] if masked else []):
                    assert u.reg_read(UC_MIPS_REG_0 + r) == v, (r, masked)
                cases += 1
    print(json.dumps(dict(cases=cases, result='PASS', coverage='both stock epilogues, lane preservation, bounded word access, original byte fallback, callee registers, stack, v0 and ra')))


if __name__ == '__main__':
    main()
