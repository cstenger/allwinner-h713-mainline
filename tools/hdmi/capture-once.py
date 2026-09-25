#!/usr/bin/env python3
"""Prepare a cold-booted board and save one HDMI color snapshot.

This combines the guarded source-3 setup with a bounded SCP/EDID signal
window. It retries one clean GPU-detection miss by default, never a failed
hardware trial. The output path is printed when a color PNG was captured.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script, *args, timeout):
    p = subprocess.run([sys.executable, str(HERE / script), *args],
                       text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{script} exited {p.returncode}:\n{p.stdout[-1800:]}\n{p.stderr[-1800:]}")
    return p.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--attempts", type=int, choices=(1, 2), default=2,
                    help="maximum bounded HPD windows (default: 2)")
    ap.add_argument("--seconds", type=int, choices=range(10, 31), default=12,
                    help="HPD hold per attempt, 10..30 seconds (default: 12)")
    args = ap.parse_args()
    print(run("prepare-source3.py", timeout=150).strip(), flush=True)
    for attempt in range(1, args.attempts + 1):
        out = run("run-detection-trial.py", "--seconds", str(args.seconds),
                  "--dump-nv16", timeout=args.seconds + 45)
        match = re.search(r"^Logs: (.+)$", out, re.MULTILINE)
        if not match:
            raise RuntimeError("trial returned without an output directory")
        png = Path(match.group(1)) / "candidate-nv16.png"
        if png.is_file():
            print(f"HDMI color snapshot: {png}", flush=True)
            return
        print(f"Attempt {attempt}: GPU did not enable output; SCP trial restored cleanly", flush=True)
    raise RuntimeError("GPU did not connect in the bounded attempts; board remains prepared")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        sys.exit(str(e))
