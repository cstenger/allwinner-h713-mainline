#!/usr/bin/env python3
"""Read only the fixed, already established reserved DRAM elog ring.

Mode byte can be stale across the MIPS/ARM cache boundary. This explicitly
reads the same bounded 0x19000-byte region even when that byte reports zero;
no writes to device memory and no claim that an active logging mode exists.
"""
import runpy
from pathlib import Path
m=runpy.run_path('/root/hdmi-safe-trace/read-elog-ring.py')
mem=m['Words']()
Path('/tmp/h713-known-ring.bin').write_bytes(mem.read(0x4b272d9c,0x19000))
