#!/usr/bin/env python3
"""Read guarded MIPS HDMI/audio DRAM through stock Android's read-only tool.

Run on the host. Verify stock firmware identity before interpreting fields.
Uses the existing pointer/vptr/port guards, never receiver MMIO. MIPS D-cache
can make these ARM observations stale; this does not establish PLL execution.
"""
import importlib.util
import json
from pathlib import Path
import subprocess

path = Path(__file__).parents[1] / "hdmi" / "read-mips-audio-cache.py"
spec = importlib.util.spec_from_file_location("audio", path)
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


class AdbMem:
    def word(self, address):
        if address & 3 or not 0x4B100000 <= address <= 0x4D960FFC:
            raise ValueError(f"outside aligned MIPS DRAM: {address:#x}")
        reply = subprocess.check_output([
            "adb", "shell", "/data/local/tmp/cap/hidtvreg-read",
            f"{address:08x}", "1"], text=True, timeout=5).split()
        if len(reply) != 2 or int(reply[0], 16) != address:
            raise ValueError("invalid register reader reply")
        return int(reply[1], 16)

    def mips_word(self, address):
        return self.word(audio.cache.checked_phys(address))

    def mips_byte(self, address):
        return (self.mips_word(address & ~3) >> ((address & 3) * 8)) & 255

    def mips_halfword(self, address):
        if address & 1:
            raise ValueError("unaligned halfword")
        return (self.mips_word(address & ~3) >> ((address & 2) * 8)) & 65535


if __name__ == "__main__":
    audio.cache.ReadOnlyMem = AdbMem
    print(json.dumps(audio.snapshot(), sort_keys=True))
