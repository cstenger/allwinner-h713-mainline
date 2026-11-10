#!/usr/bin/env python3
"""Verify a reviewed 96-record cold-installed PLL profile using DRAM loads only.

The profile is explicit and its full record list must match trusted generators
and a hash-pinned shim before /dev/mem is opened. No receiver MMIO is read.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load('reader', 'read-audio-monitor-trace.py')
word = load('word', 'make-audio-pll-word.py')


def main(generator=word, size=word.SHIM_SIZE, sha=word.SHIM_SHA, label='WORD'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path, help='matching generated audio-monitor-profile.json')
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    if not isinstance(profile, dict):
        raise ValueError('profile must be a JSON object')
    records = generator.validated_records(profile, size, sha)
    reader.trace = SimpleNamespace(monitor_records=lambda: records, FIELDS={})
    with reader.Reader() as device:
        reader.verify(device)
    print(f'PLL_{label}_PROFILE_VERIFIED: 96 records, magic, both canaries')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f'PLL_WORD_VERIFY_ERROR: {error}')
