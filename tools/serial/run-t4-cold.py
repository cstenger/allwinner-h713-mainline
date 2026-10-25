#!/usr/bin/env python3
"""T4: from a caught COLD U-Boot prompt, source the RAM-only T4 startup script once.

docs/hdmi-panel-source-design-2026-10-23.md section 10.12.  The operator
cold-powers the board with serial unplugged, then plugs the adapter in
right away; the replug interrupts the 5 s autoboot (docs/hdmi-normal-startup).
This tool then:

  1. requires a `=>` prompt, and a cold census: MIPS status 0x0306101c == 0,
     RTC GP6 0x07090118 == 0 (md.l reads only; GP7 is not touched);
  2. YMODEMs build/hdmi-t4-2026-10-23/t4-cold.scr to 0x52000000 (the sender
     verifies the RAM CRC), checking the file against the manifest first;
  3. sends `source 0x52000000` exactly once -- no retry -- and records UART
     until the kernel banner and the startup handoff echo, or a timeout.

    run-t4-cold.py --output docs/hdmi-evidence/.../t4-run [--port /dev/ttyUSB0]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from console import drain, open_port, write_slow  # noqa: E402

PREPARED = ROOT / "build/hdmi-t4-2026-10-23"
CENSUS = {0x0306101C: 0, 0x07090118: 0}  # MIPS status, GP6; GP7 is never touched


def md(fd, raw, addr):
    write_slow(fd, b"md.l 0x%08x 1\n" % addr)
    out = drain(fd, 0.8, echo=False)
    raw.write(out)
    m = re.search(rb"%08x:\s+([0-9a-f]{8})" % addr, out)
    if not m:
        raise RuntimeError(f"md.l 0x{addr:08x}: no value in reply")
    return int(m.group(1), 16)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--timeout", type=float, default=240)
    ap.add_argument("--prepared", type=Path, default=PREPARED,
                    help="directory with t4-cold.scr + manifest.json (default: the T4 build)")
    a = ap.parse_args()
    out = a.output
    out.mkdir(parents=True, exist_ok=True)
    if (out / "source-attempted").exists():
        raise SystemExit("a source was already attempted for this run; no retry")
    man = json.loads((a.prepared / "manifest.json").read_text())
    scr = a.prepared / "t4-cold.scr"
    if hashlib.sha256(scr.read_bytes()).hexdigest() != man["cold_script_sha256"]:
        raise SystemExit("t4-cold.scr does not match the manifest")

    fd = open_port(a.port)
    try:
        with (out / "uart-prompt.log").open("ab", buffering=0) as raw:
            write_slow(fd, b"\n")
            first = drain(fd, 1.0, echo=False)
            raw.write(first)
            if not re.search(rb"=>\s*$", first):
                raise SystemExit("no U-Boot prompt; nothing sent (did the replug stop autoboot?)")
            census = {f"{k:#010x}": md(fd, raw, k) for k in CENSUS}
            (out / "census.json").write_text(json.dumps(census, indent=1) + "\n")
            bad = {k: v for k, v in census.items() if v != CENSUS[int(k, 16)]}
            if bad:
                raise SystemExit(f"not a cold prompt: {bad}; nothing sent")
    finally:
        os.close(fd)

    t = subprocess.run([sys.executable, str(HERE / "ymodem-send.py"), str(scr), "0x52000000", "--port", a.port],
                       capture_output=True, text=True, timeout=90)
    (out / "script-transfer.log").write_text(t.stdout + t.stderr)
    if t.returncode:
        raise SystemExit("YMODEM/CRC failed; nothing sourced (see script-transfer.log)")

    fd = open_port(a.port)
    try:
        with (out / "uart-t4-boot.log").open("xb", buffering=0) as raw:
            write_slow(fd, b"\n")
            pre = drain(fd, 1.0, echo=False)
            raw.write(pre)
            if not re.search(rb"=>\s*$", pre):
                raise SystemExit("prompt lost after transfer; nothing sourced")
            (out / "source-attempted").write_text(time.strftime("%Y-%m-%dT%H:%M:%S%z") + " one source; no retry\n")
            write_slow(fd, b"source 0x52000000\n")
            seen, buf, end = set(), b"", time.time() + a.timeout
            marks = {b"startup handoff verified": "handoff", b"Booting Linux": "kernel", b"login:": "login"}
            while time.time() < end and "login" not in seen:
                chunk = drain(fd, 0.5, echo=False)
                raw.write(chunk)
                buf = (buf + chunk)[-65536:]
                for k, v in marks.items():
                    if k in buf:
                        seen.add(v)
                if re.search(rb"=>\s*$", chunk) and "kernel" not in seen and time.time() > end - a.timeout + 20:
                    break
            print(json.dumps({"seen": sorted(seen)}))
            (out / "uart-summary.json").write_text(json.dumps({"seen": sorted(seen)}) + "\n")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
