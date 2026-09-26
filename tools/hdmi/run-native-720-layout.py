#!/usr/bin/env python3
"""Capture read-only 720p ring samples while a deterministic source is active.

This does not route HDMI capture to the projector panel. It temporarily offers
the 720p trial EDID, plays the marker pattern on the source HDMI connector, and
reads completed ring pairs through /dev/mem on the target.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATTERN = Path("/tmp/h713-motion-pattern-1280x720.mkv")
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5"]
FRAME = 2 * 1280 * 720


def run(argv, timeout=30):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1000:]} {result.stderr[-1000:]}")
    return result.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe-module", type=Path,
                    default=Path("/tmp/h713-scp-probe-720/h713-scp-probe.ko"))
    ap.add_argument("--frames", type=int, choices=range(1, 9), default=3)
    args = ap.parse_args()
    if not args.probe_module.is_file():
        ap.error(f"720p SCP probe module not found: {args.probe_module}")

    output = Path("/tmp") / ("h713-native-720-layout-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
               str(PATTERN), "--width", "1280", "--height", "720"],
              timeout=120).strip(), flush=True)
    run(SCP + [str(args.probe_module),
               "root@192.168.4.1:/tmp/h713-scp-probe.ko"])
    run(SCP + [str(HERE / "read-coherent-frame.py"),
               "root@192.168.4.1:/tmp/read-coherent-frame-720.py"])

    trial = None
    player = None
    try:
        with (output / "trial.log").open("w") as log:
            trial = subprocess.Popen(
                [sys.executable, str(HERE / "run-detection-trial.py"),
                 "--seconds", "30", "--probe-port-cache", "--probe-afbd-pair"],
                stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if trial.poll() is not None:
                    raise RuntimeError("720p detection trial ended before output enabled")
                if ((CONNECTOR / "status").read_text().strip() == "connected" and
                        (CONNECTOR / "enabled").read_text().strip() == "enabled"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("source GPU did not enable the 720p output")

            with (output / "mpv.log").open("w") as player_log:
                player = subprocess.Popen(
                    ["mpv", "--no-config", "--no-audio", "--vo=gpu",
                     "--gpu-context=wayland", "--loop-file=inf", "--fullscreen",
                     "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
                     "--no-input-default-bindings", str(PATTERN)],
                    stdout=player_log, stderr=subprocess.STDOUT)
                time.sleep(2)
                if player.poll() is not None:
                    raise RuntimeError("mpv exited before the DRAM read")
                command = ("python3 /tmp/read-coherent-frame-720.py --width 1280 "
                           f"--height 720 --copies 1 --timeout 12 --count {args.frames}")
                capture = subprocess.run(SSH + [command], capture_output=True,
                                         timeout=18)
                (output / "coherent.log").write_bytes(capture.stderr)
                if capture.returncode or len(capture.stdout) != args.frames * FRAME:
                    raise RuntimeError("720p ring read failed; inspect coherent.log")
                raw = output / "capture.nv16"
                raw.write_bytes(capture.stdout)
                metadata = [json.loads(line) for line in
                            capture.stderr.decode().splitlines()]
                (output / "coherent.json").write_text(
                    json.dumps(metadata, indent=2) + "\n")
                for index in range(args.frames):
                    frame = output / f"frame-{index + 1:02d}.nv16"
                    png = output / f"frame-{index + 1:02d}.png"
                    frame.write_bytes(capture.stdout[index * FRAME:(index + 1) * FRAME])
                    run([sys.executable, str(HERE / "nv16-to-png.py"),
                         str(frame), str(png), "--width", "1280", "--height", "720"],
                        timeout=30)
                analysis = run(
                    [sys.executable, str(HERE / "analyze-motion-stream.py"),
                     str(raw), "--width", "1280", "--height", "720"], timeout=30)
                (output / "analysis.json").write_text(analysis)
                result = json.loads(analysis)
                print(json.dumps({key: result[key] for key in
                                  ("frames", "patterned_frames", "band_mismatches",
                                   "stripe_mismatches", "first_ids")}), flush=True)
                if (result["patterned_frames"] != args.frames or
                        result["band_mismatches"] or result["stripe_mismatches"]):
                    raise RuntimeError("720p marker integrity check failed")
                player.terminate()
                player.wait(timeout=5)
                player = None
            trial.wait(timeout=50)
            if trial.returncode:
                raise RuntimeError("720p detection trial failed; inspect trial.log")
        return output
    finally:
        if player is not None and player.poll() is None:
            player.terminate()
            try:
                player.wait(timeout=5)
            except subprocess.TimeoutExpired:
                player.kill()
        if trial is not None and trial.poll() is None:
            trial.wait(timeout=50)
        try:
            print(run([sys.executable, str(HERE / "prepare-source3.py"),
                       "--postboot-only"], timeout=90).strip(), flush=True)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"WARNING: standard probe restore failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
