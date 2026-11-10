#!/usr/bin/env python3
"""Read guarded DRAM with N/Fs latched at the status-change dispatch."""
import importlib.util
from pathlib import Path
import sys


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load("reader", "read-audio-monitor-trace.py")
reader.trace = load("regr_trace", "make-audio-dispatch-trace.py").monitor

if __name__ == "__main__":
    try:
        reader.main()
    except (OSError, ValueError) as error:
        sys.exit(f"AUDIO_DISPATCH_TRACE_ERROR: {error}")
