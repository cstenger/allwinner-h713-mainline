#!/usr/bin/env python3
"""Prepare a cold-start AudioMonitor overlay with RTT register-read output.

Host artifacts only. Uses the exact-image and table guards of the monitor
generator. Never patch a running MIPS core. The normal regr read is unchanged;
only its successful-read printf tail call switches from UART4 to RTT.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "monitor", Path(__file__).with_name("make-audio-monitor-trace.py"))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
original_records = monitor.monitor_records


def monitor_records():
    old = original_records()
    # Drop the redundant audio-object pointer witness to free one record.
    words = [w for _, _, w in old[:27]]
    del words[13]
    words[13] = monitor.branch(monitor.CAVE + 13 * 4, monitor.CAVE + 17 * 4)
    words[20] = monitor.branch(monitor.CAVE + 20 * 4, monitor.CAVE + 24 * 4)
    records = [(monitor.CAVE - 0x40000000 + i * 4, 0, w)
               for i, w in enumerate(words)]
    records += [(0x4B13A2F4, 0x10620009, monitor.jump(monitor.CAVE)),
                (0x4B180128, monitor.jump(0x8B15B304), monitor.jump(0x8B15B348))]
    records += [(monitor.CAVE - 0x40000000 + (26 + i) * 4, 0, 0x3C18AE34)
                for i in range(7)]
    records += [(monitor.CAVE - 0x40000000 + (33 + i) * 4, 0, 0xAF00006C)
                for i in range(7)]
    return records


monitor.monitor_records = monitor_records
monitor.FIELDS = {k: v for k, v in monitor.FIELDS.items() if k != "audio_object"}

if __name__ == "__main__":
    monitor.main()
