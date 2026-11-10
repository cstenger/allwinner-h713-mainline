#!/usr/bin/env python3
"""Prepare the projector and save a bounded NV16 stream from /dev/video1.

This uses the verified source-3 setup, stages the exact-kernel removable V4L2
bridge, and runs one bounded EDID/HPD window. It does not flash the kernel or
leave HPD asserted after capture.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULE = ROOT / "build/hdmi-v4l2/h713-hdmi-v4l2.ko"
EXPECTED_KERNEL_VERSION = "#1 SMP Thu Sep 24 01:45:24 PDT 2026"
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5"]


def run(argv, timeout):
    p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{argv[0]} exited {p.returncode}:\n"
                           f"{p.stdout[-1200:]}\n{p.stderr[-1200:]}")
    return p.stdout


def remote(command):
    return run(SSH + [command], 20)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frames", type=int, default=30,
                    help="frames to save, 1–120 (default: 30)")
    ap.add_argument("--seconds", type=int, default=20,
                    help="bounded HDMI signal window, 10–30 s (default: 20)")
    ap.add_argument("--sparse-verify", action="store_true",
                    help="experimental faster copy with sparse stability checks only")
    args = ap.parse_args()
    if not 1 <= args.frames <= 120 or not 10 <= args.seconds <= 30:
        ap.error("frames must be 1–120 and seconds must be 10–30")

    if not MODULE.is_file():
        raise RuntimeError(f"build the matching module first: {MODULE}")
    boot = remote("uname -v")
    if boot.strip() != EXPECTED_KERNEL_VERSION:
        raise RuntimeError(f"module build does not match the running kernel: {boot.strip()}")
    print(run([sys.executable, str(HERE / "prepare-source3.py")], 150).strip(),
          flush=True)

    digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    verify_full = int(not args.sparse_verify)
    run(SCP + [str(MODULE), "root@192.168.4.1:/tmp/h713-hdmi-v4l2.ko"], 30)
    remote("set -e; "
           f"test \"$(sha256sum /tmp/h713-hdmi-v4l2.ko | cut -d' ' -f1)\" = {digest}; "
           "if test -d /sys/module/h713_hdmi_v4l2; then rmmod h713_hdmi_v4l2; fi; "
           f"insmod /tmp/h713-hdmi-v4l2.ko verify_full={verify_full}; "
           "test \"$(cat /sys/class/video4linux/video1/name)\" = "
           "\"H713 HDMI1 ring capture\"")
    print("V4L2 HDMI capture ready at /dev/video1 "
          f"(verification: {'sparse' if args.sparse_verify else 'full'})", flush=True)

    for attempt in range(2):
        p = subprocess.run([sys.executable, str(HERE / "run-detection-trial.py"),
                            "--seconds", str(args.seconds),
                            "--v4l2-frames", str(args.frames)],
                           text=True, capture_output=True,
                           timeout=args.seconds + 100)
        match = re.search(r"^Logs: (.+)$", p.stdout, re.MULTILINE)
        if not match:
            raise RuntimeError(f"trial returned without logs:\n{p.stdout[-1200:]}\n{p.stderr[-1200:]}")
        output = Path(match.group(1))
        if p.returncode == 0 and (output / "v4l2.nv16").is_file():
            summary = json.loads((output / "v4l2-summary.json").read_text())[0]
            print(f"NV16 stream: {output / 'v4l2.nv16'}", flush=True)
            print(f"Frames: {summary['frames']} ({summary['unique_crc32']} distinct)", flush=True)
            print(f"Last-frame preview: {output / f'v4l2-frame-{args.frames:03d}.png'}", flush=True)
            return
        if attempt == 0 and '"v4l2_error": "GPU never enabled output"' in p.stdout:
            print("GPU detection missed; retrying one clean bounded window", flush=True)
            continue
        raise RuntimeError(f"V4L2 trial failed:\n{p.stdout[-1600:]}\n{p.stderr[-1200:]}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        sys.exit(str(e))
