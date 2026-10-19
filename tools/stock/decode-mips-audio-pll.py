#!/usr/bin/env python3
"""Offline stock MIPS PLL execution; simulated byte helpers never touch hardware.

Requires Unicorn and an explicit, identity-pinned private firmware input.
Reads default to zero. A poll reaching the instruction bound is incomplete,
not a hardware failure; full Init returning does not prove physical PLL lock.
The collapse/word-write switches model hypotheses, not measured bus behavior.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_CPU_MIPS32_24KC, UC_MIPS_REG_0, UC_MIPS_REG_PC

FW_SHA = '4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce'


def run(firmware, entry, initial=0, initialize_zero=False,
        collapse_byte_writes=False, word_write_shim=False):
    if hashlib.sha256(firmware).hexdigest() != FW_SHA:
        raise ValueError('firmware SHA256 does not match board-B image')
    emulator = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    emulator.ctl_set_cpu_model(UC_CPU_MIPS32_24KC)
    emulator.mem_map(0x0B100000, (len(firmware) + 4095) & ~4095)
    emulator.mem_write(0x0B100000, firmware)
    if initialize_zero:
        if struct.unpack_from('<I', firmware, 0x3C628)[0] != 0x06000017:
            raise ValueError('stock Init-selection branch mismatch')
        emulator.mem_write(0x0B13C628, struct.pack('<I', 0x1A000017))
    emulator.mem_map(0x100000, 0x100000)
    emulator.mem_map(0x0D000000, 0x10000)
    argument, stop, stack = 0x8D000000, 0x801F0000, 0x80180000
    emulator.mem_write(argument & 0x1FFFFFFF, struct.pack('<7I', 74250, 6144, 48000, 0, 0, 0, 0))
    for index, value in [(4, 0x06880000), (5, argument), (29, stack), (31, stop)]:
        emulator.reg_write(UC_MIPS_REG_0 + index, value)
    registers = {0x0688000C + i: (initial >> (8*i)) & 255 for i in range(4)}
    events, visited, logs = [], {}, []

    def reg(index):
        return emulator.reg_read(UC_MIPS_REG_0 + index)

    def ret(value=0):
        emulator.reg_write(UC_MIPS_REG_0 + 2, value)
        emulator.reg_write(UC_MIPS_REG_PC, reg(31))

    def check(address):
        if not 0x06880000 <= address < 0x0688001C:
            raise ValueError(f'helper address outside modeled PLL bank: {address:#x}')

    def store(address, value):
        if (word_write_shim and 0x06880000 <= address < 0x06880014
                and not 0x06880008 <= address < 0x0688000C):
            registers[address] = value & 255
        elif collapse_byte_writes:
            aligned = address & ~3
            for lane in range(4):
                registers[aligned + lane] = 0
            registers[aligned] = value & 255
        else:
            registers[address] = value & 255

    def hook(emulator, address, size, data):
        visited[address] = visited.get(address, 0) + 1
        if address == stop:
            emulator.emu_stop()
        elif address == 0x8B150948:
            logs.append(hex(reg(7)))
            ret()
        elif address == 0x8B180340:
            target = reg(4)
            check(target)
            ret(registers.get(target, 0))
        elif address in (0x8B180394, 0x8B1803DC):
            target = reg(4)
            check(target)
            value = (reg(5) & 255 if address == 0x8B180394 else
                     (registers.get(target, 0) & ~reg(5)) | (reg(6) & reg(5)))
            events.append(dict(addr=f'{target:08x}', value=value))
            store(target, value)
            ret()

    emulator.hook_add(UC_HOOK_CODE, hook)
    emulator.emu_start(entry, 0, count=200000)
    words = {f'{address:08x}': sum(registers.get(address+i, 0) << (8*i) for i in range(4))
             for address in range(0x06880000, 0x0688001C, 4)}
    return dict(entry=f'{entry:08x}', initial_control_word=initial,
                initialize_zero=initialize_zero, collapse_byte_writes=collapse_byte_writes,
                word_write_shim=word_write_shim,
                returned=emulator.reg_read(UC_MIPS_REG_PC) == stop, result=reg(2),
                events=events, words=words, max_visits=max(visited.values()),
                instructions=sum(visited.values()), log_functions=logs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path, help='private board-B display.bin')
    args = parser.parse_args()
    firmware = args.firmware.read_bytes()
    results = [run(firmware, 0x8B13BCB8), run(firmware, 0x8B13C000),
               run(firmware, 0x8B13C524, initialize_zero=True),
               run(firmware, 0x8B13C524, initialize_zero=True, collapse_byte_writes=True)]
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f'PLL_MODEL_ERROR: {error}')
