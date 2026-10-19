#!/usr/bin/env python3
"""Build a cold-only byte-packed PLL read diagnostic; stock stores retained.

Host artifacts only. Reads exactly four scalar PLL addresses using four LBU
loads; other addresses retain the stock LW. No new MMIO stores are added.
"""
import importlib.util
from pathlib import Path
import struct

spec = importlib.util.spec_from_file_location('word', Path(__file__).with_name('make-audio-pll-word.py'))
word = importlib.util.module_from_spec(spec)
spec.loader.exec_module(word)
SHIM_SIZE = 100
SHIM_SHA = 'bd0d6a5be034e63165836ab19e3c41dea75a59499f57665c4bb1b6c714ff0c6d'


def records(shim):
    word.check_shim(shim, SHIM_SIZE, SHIM_SHA)
    code = list(struct.unpack('<25I', shim))
    code += [0x3C1AAE34]*9 + [0xAF400000]*9 + [0]*10
    return [(word.CAVE-0x40000000+i*4, 0, value) for i, value in enumerate(code)] + [
        (0x4B180114, 0x8C460000, word.monitor.jump(word.CAVE))]


word.records = records


def main():
    word.main('audio-pll-byte-read.S', SHIM_SIZE, SHIM_SHA,
              scope='byte read diagnostic; stock PLL writes unchanged; init/retry retained')


if __name__ == '__main__':
    main()
