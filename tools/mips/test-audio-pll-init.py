#!/usr/bin/env python3
"""Execute the generated init branch and retry return paths, including delays.

Requires Unicorn; no private firmware or board access is needed.
"""
import importlib.util
from pathlib import Path
import random
import struct

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_CPU_MIPS32_24KC, UC_MIPS_REG_0, UC_MIPS_REG_PC


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    init = load('init', 'make-audio-pll-init.py')
    retry_test = load('retry_test', 'test-audio-pll-retry.py')
    retry_test.main(init.monitor, padding_word=25)
    records = {a: (old, new) for a, old, new in init.records()}
    original, replacement = records[0x4B13C628]
    assert (original, replacement) == (0x06000017, 0x1A000017)
    rng = random.Random(713)
    controls = [0, 1, 0x60180000, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF]
    controls += [rng.getrandbits(32) for _ in range(100)]
    for word in controls:
        for patched in (False, True):
            emulator = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
            emulator.ctl_set_cpu_model(UC_CPU_MIPS32_24KC)
            emulator.mem_map(0x0B13C000, 0x1000)
            emulator.mem_map(0x100000, 0x1000)
            # Execute the actual generated replacement and the stock delay slot.
            opcode = replacement if patched else original
            emulator.mem_write(0x0B13C628, struct.pack('<II', opcode, 0xAFA70018))
            regs = [0] + [rng.getrandbits(32) for _ in range(31)]
            regs[16], regs[29] = word, 0x80100000
            for index, value in enumerate(regs):
                emulator.reg_write(UC_MIPS_REG_0 + index, value)
            stops = (0x8B13C630, 0x8B13C688)

            def stop(emulator, address, size, data):
                if address in stops:
                    emulator.emu_stop()

            emulator.hook_add(UC_HOOK_CODE, stop)
            emulator.emu_start(0x8B13C628, 0, count=6)
            expected = stops[1] if word & 0x80000000 or (patched and word == 0) else stops[0]
            assert emulator.reg_read(UC_MIPS_REG_PC) == expected
            assert [emulator.reg_read(UC_MIPS_REG_0+i) for i in range(32)] == regs
            assert struct.unpack('<I', emulator.mem_read(0x100018, 4))[0] == regs[7]
    print(f'PASS: {len(controls)*2} generated/stock init branch paths; only zero changes selection; registers and delay-slot store preserved')


if __name__ == '__main__':
    main()
