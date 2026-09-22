#!/usr/bin/env python3
"""Read the flashed U-Boot mips-stability witness; run on the H713 board.

Install instrumentation only through `h713_disp mips-stability 0x34` at U-Boot.
This reader verifies all 34 code words before reading the fixed uncached
mailbox. It performs no writes, firmware release, or receiver MMIO.
Stage beside mips-shell.py. --watch is bounded to 30 seconds.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import time

PATCHED_WORDS = (
    (0x4b100300, 0x26730001),
    (0x4b100304, 0x3c1aae34),
    (0x4b100308, 0xaf531000),
    (0x4b10030c, 0x0ac412e1),
    (0x4b100310, 0xac532cc0),
    (0x4b104b7c, 0x0ac400c0),
    (0x4b100320, 0x3c1aae34),
    (0x4b100324, 0x401b6000),
    (0x4b100328, 0xaf5b1008),
    (0x4b10032c, 0x401b6800),
    (0x4b100330, 0xaf5b100c),
    (0x4b100334, 0x401b7000),
    (0x4b100338, 0xaf5b1010),
    (0x4b10033c, 0x401b4000),
    (0x4b100340, 0xaf5b1014),
    (0x4b100344, 0x341b0001),
    (0x4b100348, 0xaf5b1004),
    (0x4b10034c, 0x0ac56f4a),
    (0x4b100350, 0x00000000),
    (0x4b101180, 0x0ac400c8),
    (0x4b100360, 0x3c1aae34),
    (0x4b100364, 0x401b6000),
    (0x4b100368, 0xaf5b1008),
    (0x4b10036c, 0x401b6800),
    (0x4b100370, 0xaf5b100c),
    (0x4b100374, 0x401bf000),
    (0x4b100378, 0xaf5b1010),
    (0x4b10037c, 0x401b4000),
    (0x4b100380, 0xaf5b1014),
    (0x4b100384, 0x341b0002),
    (0x4b100388, 0xaf5b1004),
    (0x4b10038c, 0x0ac56f79),
    (0x4b100390, 0x00000000),
    (0x4b101100, 0x0ac400d8),
)
MAILBOX = 0x4e341000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch', type=float, default=0)
    parser.add_argument('--irq-frame', action='store_true',
                        help='read bounded DRAM IRQ frame/table; cached MIPS data may be stale')
    args = parser.parse_args()
    if not 0 <= args.watch <= 30:
        parser.error('--watch must be between 0 and 30 seconds')
    spec = importlib.util.spec_from_file_location(
        'mips_shell', Path(__file__).with_name('mips-shell.py'))
    shell = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shell)
    mem = shell.Mem()  # Existing aligned word reader; put32/write are not used.
    for address, expected in PATCHED_WORDS:
        actual = mem.u32(address)
        if actual != expected:
            raise SystemExit(f'Witness patch mismatch at {address:#x}: '
                             f'{actual:#010x} != {expected:#010x}; '
                             'refusing to interpret mailbox')
    print(json.dumps({'verified_patch_words': len(PATCHED_WORDS),
                      'mailbox': f'{MAILBOX:08x}'}), flush=True)
    if args.irq_frame:
        pointer = mem.u32(0x4b252c98)
        context = {'irq_nesting_dram': mem.u32(0x4b22cce8),
                   'frame_pointer_dram': f'{pointer:08x}',
                   'cached_mips_data_may_be_stale': True}
        if 0x8b100000 <= pointer <= 0x8d961000 - 0xa0 and not pointer & 3:
            physical = pointer - 0x40000000
            names = {'v0': 0x04, 'v1': 0x08, 'a0': 0x0c, 'a1': 0x10,
                     'a2': 0x14, 'a3': 0x18, 's0': 0x3c, 's1': 0x40,
                     's2': 0x44, 's3': 0x48, 'ra': 0x78, 'epc': 0x7c,
                     'status': 0x90, 'cause': 0x94}
            context['frame'] = {name: f'{mem.u32(physical + offset):08x}'
                                for name, offset in names.items()}
            context['frame_words'] = [f'{mem.u32(physical + i * 4):08x}'
                                      for i in range(40)]
        else:
            context['frame'] = 'unavailable: pointer outside reserved RAM or unaligned'
        context['irq_map'] = [mem.u32(0x4b272674 + i * 4) for i in range(64)]
        context['irq_callbacks'] = [f'{mem.u32(0x4b272770 + i * 4):08x}'
                                    for i in range(64)]
        print(json.dumps(context), flush=True)
    start = time.monotonic()
    previous = None
    while True:
        words = tuple(mem.u32(MAILBOX + i * 4) for i in range(6))
        elapsed = time.monotonic() - start
        if words != previous or elapsed >= args.watch:
            tick, exception, status, cause, epc, badvaddr = words
            print(json.dumps({'seconds': round(elapsed, 3), 'tick': tick,
                              'exception': exception, 'status': f'{status:08x}',
                              'cause': f'{cause:08x}', 'epc': f'{epc:08x}',
                              'badvaddr': f'{badvaddr:08x}',
                              'exc_code': (cause >> 2) & 31,
                              'branch_delay': bool(cause & (1 << 31))}), flush=True)
            previous = words
        if elapsed >= args.watch:
            break
        time.sleep(min(0.1, args.watch - elapsed))


if __name__ == '__main__':
    main()
