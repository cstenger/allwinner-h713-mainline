#!/usr/bin/env python3
"""Read the guarded, uncached audio monitor mailbox; no device-memory writes.

Run on the board after the matching cold-start diagnostic and source-3 startup.
The counter flag is not a seqlock or an atomicity guarantee.
Snapshots are best-effort: counters and last-observed fields can update while
ARM reads them. Dispatch counts witness the monitor's status-change branch,
not successful PLL lock or completion of SetAPLL.
"""
import argparse
import ctypes
import importlib.util
import json
import mmap
import os
from pathlib import Path
import sys
import time

spec = importlib.util.spec_from_file_location(
    "audio_trace", Path(__file__).with_name("make-audio-monitor-trace.py"))
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)
BASE = 0x4D980000


class Reader:
    def __init__(self):
        # Writable mmap is required by ctypes.from_buffer, but only aligned
        # loads are exposed. Never issue a byte-slicing memcpy on Device RAM.
        self.pages = {}
        self.allowed = {a for a, _, _ in trace.monitor_records()}
        self.allowed |= {BASE + o for o in trace.FIELDS.values()}
        self.allowed |= {BASE + 4, BASE + 0x80, BASE + 0xFFC}
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)

    def close(self):
        try:
            while self.pages:
                _, mapping = self.pages.popitem()
                mapping.close()
        finally:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def word(self, address):
        if self.fd is None:
            raise ValueError("reader is closed")
        if address not in self.allowed or address & 3:
            raise ValueError("read outside explicit firmware/mailbox allowlist")
        page = address & ~0xFFF
        if page not in self.pages:
            mapping = mmap.mmap(self.fd, 0x1000, mmap.MAP_SHARED,
                                mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
            self.pages[page] = mapping
        # A temporary scalar performs one aligned word load and releases its
        # exported buffer immediately, allowing mmap.close() during cleanup.
        return ctypes.c_uint32.from_buffer(self.pages[page], address - page).value


def verify(reader):
    for address, _, word in trace.monitor_records():
        if word == 0x3C18AE34:
            word = 0x3C18AD98
        if reader.word(address) != word:
            raise ValueError(f"audio trace instruction mismatch at {address:#x}")
    if reader.word(BASE + 4) != 0x434F4D4D:
        raise ValueError("CPU_COMM trace magic absent")
    if any(reader.word(BASE + o) != 0x43414E31 for o in (0x80, 0xFFC)):
        raise ValueError("trace page canary mismatch")


def snapshot(reader):
    before = reader.word(BASE + trace.FIELDS["monitor_calls"])
    result = {name: reader.word(BASE + offset) for name, offset in trace.FIELDS.items()}
    after = reader.word(BASE + trace.FIELDS["monitor_calls"])
    result["monitor_count_changed_during_read"] = before != after
    result["host_monotonic"] = time.monotonic()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", type=float, default=0)
    parser.add_argument("--interval", type=float, default=0.25)
    args = parser.parse_args()
    if not 0 <= args.watch <= 60 or not 0.02 <= args.interval <= 1:
        parser.error("watch must be 0..60 seconds and interval 0.02..1")
    with Reader() as reader:
        verify(reader)
        deadline = time.monotonic() + args.watch
        while True:
            print(json.dumps(snapshot(reader), sort_keys=True), flush=True)
            if time.monotonic() >= deadline:
                break
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"AUDIO_MONITOR_TRACE_ERROR: {error}")
