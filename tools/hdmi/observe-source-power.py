#!/usr/bin/env python3
"""Observe board-B HDMI power candidates and copied callbacks; never issue RPCs.

Run on the board. Only reserved MIPS DRAM is mapped, read-only. No MMIO,
ioctl, callback registration, HPD request, firmware write or service action.
Candidate bytes are experimental, not a validated power-present API.
"""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import select
import struct
import time

LOW, HIGH, DELTA = 0x8B100000, 0x8BF41000, 0x40000000
ROOT = 0x8BAC1A70
# Filled from the exact board-B display.bin by the companion static audit.
CODE_PINS = {'five_volt_reader': {'address': 2333339632, 'bytes': 72, 'sha256': '8c6db6ea9f87533624f19d3ec5168d262277589f6faa4bb153a2ce267e525b29'}, 'port_poll': {'address': 2333316140, 'bytes': 112, 'sha256': '99ebb59e3cb349e0f12b98192b28d2186f3707b0fe54f90abc7834b31c62c950'}, 'power_change': {'address': 2333303416, 'bytes': 64, 'sha256': '8c829eea8071f168d6064ed6d4ce99f734dedf3770073470553b5d584a3a4d7f'}, 'callback_marshaller': {'address': 2333122716, 'bytes': 68, 'sha256': '4cb0502b3721416fa9252209acaed63225fad1deeb514b75a3611f8b107e0c0b'}}


class Memory:
    def __init__(self):
        self.fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
        self.pages = {}

    def word(self, address):
        if address & 3 or not LOW <= address <= HIGH - 4:
            raise ValueError('outside aligned MIPS DRAM: %#x' % address)
        phys = address - DELTA
        page = phys & ~4095
        if page not in self.pages:
            self.pages[page] = mmap.mmap(self.fd, 4096, flags=mmap.MAP_SHARED,
                                         prot=mmap.PROT_READ, offset=page)
        return struct.unpack_from('<I', self.pages[page], phys - page)[0]

    def byte(self, address):
        return (self.word(address & ~3) >> ((address & 3) * 8)) & 255

    def close(self):
        for page in self.pages.values():
            page.close()
        os.close(self.fd)


def need(value, message):
    if not value:
        raise ValueError(message)


def snapshot(mem):
    manager = mem.word(ROOT)
    need(mem.word(manager) == 0x8B201D24, 'manager identity mismatch')
    hdmi = mem.word(manager + 0x18)
    need(mem.word(hdmi) == 0x8B1F5390, 'receiver identity mismatch')
    ports = []
    for index in range(3):
        port = mem.word(hdmi + 0xEC + 4 * index)
        need(port != 0, 'port absent')
        need(mem.byte(port + 0x51B) == index + 1, 'port identity mismatch')
        need(mem.word(port + 0x520) == 0x06840000, 'port link identity mismatch')
        context = mem.word(port + 0x544)
        ports.append(dict(port=index + 1, object=hex(port),
                          polling_enabled=mem.byte(port + 0x51A),
                          power_candidate=mem.byte(port + 0x532),
                          processed_power_candidate=mem.byte(context + 0xE),
                          state=mem.word(port + 0xC0)))
    return dict(ports=ports, bsp_callback=hex(mem.word(0x8B22F05C)),
                hal_callback=hex(mem.word(0x8B2728B4)),
                signal=Path('/sys/devices/platform/h713-hdmi-ring/signal').read_text().strip(),
                retries=Path('/sys/module/h713_hdmi_signal/parameters/readvertised').read_text().strip())


def emit(kind, **values):
    print(json.dumps(dict(kind=kind, monotonic=time.monotonic(), **values)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=0,
                        help='0: one snapshot; otherwise observe up to 1800 seconds')
    args = parser.parse_args()
    need(0 <= args.seconds <= 1800, 'duration outside 0..1800 seconds')
    mem = Memory()
    callback_fd = None
    try:
        need(bool(CODE_PINS), 'missing exact firmware code pins')
        for name, pin in CODE_PINS.items():
            raw = b''.join(struct.pack('<I', mem.word(pin['address'] + off))
                           for off in range(0, pin['bytes'], 4))
            need(hashlib.sha256(raw).hexdigest() == pin['sha256'],
                 'firmware code mismatch: ' + name)
        emit('identity', boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             code_pins=CODE_PINS, candidate_semantics='unvalidated source-power cache')
        first = snapshot(mem)
        emit('sample', **first)
        if not args.seconds:
            return
        # Open creates a private copy queue. No routine is installed or changed.
        callback_fd = os.open('/dev/cpu_comm', os.O_RDONLY | os.O_NONBLOCK)
        emit('armed', callback_mode='passive copied messages; no registration')
        end, heartbeat, previous = time.monotonic() + args.seconds, time.monotonic(), first
        while time.monotonic() < end:
            readable, _, _ = select.select([callback_fd], [], [],
                                          min(.2, max(0, end - time.monotonic())))
            if readable:
                try:
                    raw = os.read(callback_fd, 104)
                except BlockingIOError:
                    continue
                need(len(raw) == 104, 'unexpected CPU_COMM message size')
                emit('callback_copy', raw_hex=raw.hex(), words=struct.unpack('<26I', raw))
            current = snapshot(mem)
            now = time.monotonic()
            if current != previous or now - heartbeat >= 5:
                emit('sample', **current)
                previous, heartbeat = current, now
        emit('complete', **snapshot(mem))
    finally:
        if callback_fd is not None:
            os.close(callback_fd)
        mem.close()


if __name__ == '__main__':
    main()
