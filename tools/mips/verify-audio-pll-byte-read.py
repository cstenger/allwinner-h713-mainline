#!/usr/bin/env python3
"""Verify the explicit cold-installed byte-read profile with guarded DRAM loads."""
import importlib.util
from pathlib import Path
import sys


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = load('verifier', 'verify-audio-pll-word.py')
byte = load('byte', 'make-audio-pll-byte-read.py')


def main():
    verifier.main(byte.word, byte.SHIM_SIZE, byte.SHIM_SHA, label='BYTE')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f'PLL_BYTE_VERIFY_ERROR: {error}')
