#!/usr/bin/env python3
"""Read HDMI audio fields already cached by MIPS; never access receiver MMIO.

Worker state begins eight bytes into the port object.
The board-B event 0x3000 worker calls Get_N_CTS and GetFs with worker_state+0x78 (port+0x80).
The audio worker uses that same structure for SetAPLL and compares +0x30/34
against the current N/sample rate. Keep unknown fields as raw words.

ARM reads DRAM without participating in the MIPS D-cache coherency domain.
These fields can therefore be stale. Zero history does not prove SetAPLL was
not executed; correlate positive firmware elog records before concluding.
"""
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location(
    "port_cache", Path(__file__).with_name("read-mips-port-cache.py"))
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


def snapshot():
    mem = cache.ReadOnlyMem()
    result = cache.snapshot(mem)
    if result.get("hdmi"):
        hdmi = int(result["hdmi"], 16)
        active = mem.mips_word(hdmi + 0xe8)
        if active:
            cache.checked_phys(active, 0x534)
        result["active_port_object"] = f"{active:08x}"
    for port in result.get("ports", []):
        if not port.get("object"):
            continue
        addr = int(port["object"], 16) + 8
        cache.checked_phys(addr, 0x52c)
        if mem.mips_word(addr + 0x518) != 0x06840000:
            raise ValueError("unexpected receiver base in audio worker state")
        port["audio"] = {
            "cts": mem.mips_word(addr + 0x78),
            "n": mem.mips_word(addr + 0x7c),
            "sample_rate_hz": mem.mips_word(addr + 0x80),
            "infoframe_rate_code": mem.mips_word(addr + 0x84),
            "status_byte": mem.mips_byte(addr + 0x88),
            "active_port_gate": mem.mips_byte(addr - 8 + 0x531),
            "monitor_counter": mem.mips_word(addr + 0xb4),
            "pll_last_n": mem.mips_word(addr + 0xa8),
            "pll_last_sample_rate_hz": mem.mips_word(addr + 0xac),
            "pll_register_base": f"{mem.mips_word(addr + 0xb0):08x}",
            "receiver_register_base": f"{mem.mips_word(addr + 0x518):08x}",
            "raw_words_78_b4": [f"{mem.mips_word(addr + off):08x}"
                                 for off in range(0x78, 0xb8, 4)],
        }
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(snapshot(), sort_keys=True))
    except (OSError, ValueError) as exc:
        sys.exit(f"MIPS_AUDIO_CACHE_ERROR: {exc}")
