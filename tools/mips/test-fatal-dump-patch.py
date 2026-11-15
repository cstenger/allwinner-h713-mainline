#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Host test for fatal-dump-patch.py state checks and save-area decoding."""
import argparse, importlib.util, struct
from pathlib import Path

spec = importlib.util.spec_from_file_location('fdp', Path(__file__).with_name('fatal-dump-patch.py'))
fdp = importlib.util.module_from_spec(spec); spec.loader.exec_module(fdp)


class Fake:
    def __init__(self, image):
        self.w = {}
        for a, _ in fdp.GUARDS: self.w[a] = image.u32(a)
        for a, old, _ in fdp.SITES: self.w[a] = image.u32(a)
    def u32(self, a): return self.w.get(a, 0)
    def put(self, a, v): self.w[a] = v


def refused(mem):
    try: fdp.state(mem)
    except SystemExit: return True
    return False


def main():
    p = argparse.ArgumentParser(); p.add_argument('--image', required=True); a = p.parse_args()
    img = fdp.Image(a.image)
    m = Fake(img)
    assert fdp.state(m) == 'original'
    for addr, old, new in fdp.SITES: m.put(addr, new)
    assert fdp.state(m) == 'patched'
    m.put(fdp.SITES[0][0], fdp.SITES[0][1])
    assert refused(m), 'mixed sites must refuse'
    m.put(fdp.SITES[0][0], 0x12345678)
    assert refused(m), 'foreign word must refuse'
    m = Fake(img); m.put(fdp.GUARDS[0][0], 0)
    assert refused(m), 'guard mismatch must refuse'
    # Decoder: magic, EPC, Cause DBE with BD set, BadVAddr in the patched slot.
    m = Fake(img)
    for off, v in ((0, 0x63726173), (4, 0x68726567), (0x80, 0x10007c03),
                   (0x84, 0x80000000 | (7 << 2) | 0x400), (0x88, 0x8b123e04), (0x94, 0x4e302a90)):
        m.put(fdp.SAVE + off, v)
    d = fdp.decode(m)
    assert d['decoded']['magic_ok'] and d['decoded']['exccode'] == 'DBE'
    assert d['decoded']['branch_delay'] and d['epc'] == '0x8b123e04' and d['badvaddr'] == '0x4e302a90'
    assert d['decoded']['status_exl_erl_ie'] == [1, 0, 1]
    print('PASS original/patched/mixed/foreign/guard states and save-area decode')


if __name__ == '__main__':
    main()
