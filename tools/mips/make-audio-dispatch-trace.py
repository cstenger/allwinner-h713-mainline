#!/usr/bin/env python3
"""Prepare a cold-start diagnostic with N/Fs latched only at PLL dispatch.

Host artifacts only. Retains the RTT regr output overlay and exact-image
42-record/table guards. Never patch running MIPS code.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'regr', Path(__file__).with_name('make-audio-regr-trace.py'))
regr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regr)
monitor = regr.monitor
original_records = regr.monitor_records


def monitor_records():
    records = original_records()
    words = [w for _, _, w in records[:26]]
    # Equal status skips both the dispatch counter and N/Fs publication.
    # Monitor/status fields still update on every call. Register/stack
    # restoration and the original comparison's return paths stay identical.
    words = (words[:9] +
             [monitor.branch(monitor.CAVE + 9*4, monitor.CAVE + 17*4),
              words[14], words[15], words[16]] + words[9:13] + words[17:])
    return [(monitor.CAVE - 0x40000000 + i*4, 0, w)
            for i, w in enumerate(words)] + records[26:]


monitor.monitor_records = monitor_records
monitor.FIELDS = {('dispatch_n' if k == 'n' else
                   'dispatch_sample_rate_hz' if k == 'sample_rate_hz' else k): v
                  for k, v in monitor.FIELDS.items()}

if __name__ == '__main__':
    monitor.main()
