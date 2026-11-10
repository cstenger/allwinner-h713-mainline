#!/usr/bin/env python3
"""Verify cold-installed PLL init code and canaries with aligned DRAM reads."""
import argparse
import importlib.util
from pathlib import Path
import sys


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load('reader', 'read-audio-monitor-trace.py')
reader.trace = load('retry', 'make-audio-pll-init.py').monitor

def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    with reader.Reader() as device:
        reader.verify(device)
    print('PLL_INIT_PROFILE_VERIFIED: 42 instructions, magic, both canaries')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f'PLL_INIT_VERIFY_ERROR: {error}')
