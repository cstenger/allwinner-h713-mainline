#!/usr/bin/env python3
"""Run one bounded motion-pattern trial with MIPS IRQ/ring correlation."""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
PATTERN = Path("/tmp/h713-motion-pattern.mkv")
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5", "root@192.168.4.1"]


def run(argv, timeout=30):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1000:]} {result.stderr[-1000:]}")
    return result.stdout


def main():
    output = Path("/tmp") / ("h713-cap-irq-trial-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
               str(PATTERN)]).strip(), flush=True)
    print(run([sys.executable, str(HERE / "prepare-source3.py"),
               "--postboot-only"], timeout=60).strip(), flush=True)
    before = run(SSH + ["python3 /root/hdmi-cap-trace/read-comm-trace.py "
                        "--source-only"])
    (output / "trace-before.json").write_text(before)

    trial = player = None
    try:
        with (output / "signal-trial.log").open("w") as log:
            trial = subprocess.Popen(
                [sys.executable, str(HERE / "run-detection-trial.py"),
                 "--seconds", "24"], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 18
            while time.monotonic() < deadline:
                if trial.poll() is not None:
                    raise RuntimeError("signal trial ended before HDMI enabled")
                if ((CONNECTOR / "status").read_text().strip() == "connected" and
                        (CONNECTOR / "enabled").read_text().strip() == "enabled"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("GPU HDMI output did not enable")

            with (output / "mpv.log").open("w") as log:
                player = subprocess.Popen(
                    ["mpv", "--no-config", "--no-audio", "--vo=gpu",
                     "--gpu-context=wayland", "--loop-file=inf", "--fullscreen",
                     "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
                     "--no-input-default-bindings", str(PATTERN)],
                    stdout=log, stderr=subprocess.STDOUT)
                time.sleep(2)
                if player.poll() is not None:
                    raise RuntimeError("mpv exited before sampling")
                trace = run(SSH + [
                    "python3 /root/hdmi-cap-trace/read-cap-ring-trace.py "
                    "--seconds 8 --interval 0.003"], timeout=20)
                (output / "cap-ring.jsonl").write_text(trace)
                player.terminate()
                player.wait(timeout=5)
                player = None
            trial.wait(timeout=40)
            if trial.returncode:
                raise RuntimeError("signal trial failed")
        after = run(SSH + ["python3 /root/hdmi-cap-trace/read-comm-trace.py "
                           "--source-only"])
        (output / "trace-after.json").write_text(after)
        samples = [json.loads(line) for line in trace.splitlines()]
        print(json.dumps({"samples": len(samples) - 1,
                          "before": json.loads(before),
                          "after": json.loads(after)}), flush=True)
    finally:
        if player is not None and player.poll() is None:
            player.terminate()
            try:
                player.wait(timeout=5)
            except subprocess.TimeoutExpired:
                player.kill()
        if trial is not None and trial.poll() is None:
            trial.wait(timeout=40)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
