#!/usr/bin/env python3
"""Run one bounded HDMI1 motion-pattern capture on the connected GPU."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULE = ROOT / "build/hdmi-v4l2/h713-hdmi-v4l2.ko"
PATTERN = Path("/tmp/h713-motion-pattern.mkv")
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5"]
EXPECTED_KERNEL_VERSION = "#1 SMP Thu Sep 24 01:45:24 PDT 2026"


def run(argv, timeout=30):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1000:]} {result.stderr[-1000:]}")
    return result.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("sparse", "full"), default="sparse")
    ap.add_argument("--frames", type=int, default=120)
    args = ap.parse_args()
    if not 1 <= args.frames <= 120:
        ap.error("--frames must be 1–120")
    output = Path("/tmp") / ("h713-motion-trial-" +
                            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    if not MODULE.is_file():
        raise RuntimeError(f"build the matching module first: {MODULE}")
    if run(SSH + ["uname -v"]).strip() != EXPECTED_KERNEL_VERSION:
        raise RuntimeError("the running projector kernel does not match the module")
    print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
               str(PATTERN)]).strip(), flush=True)
    print(run([sys.executable, str(HERE / "prepare-source3.py")],
              timeout=150).strip(), flush=True)
    digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    run(SCP + [str(MODULE), "root@192.168.4.1:/tmp/h713-hdmi-v4l2.ko"])
    run(SSH + ["set -e; "
               f"test \"$(sha256sum /tmp/h713-hdmi-v4l2.ko | cut -d' ' -f1)\" = {digest}; "
               "if test -d /sys/module/h713_hdmi_v4l2; then rmmod h713_hdmi_v4l2; fi; "
               "insmod /tmp/h713-hdmi-v4l2.ko verify_full=1"])

    (output / "irq-idle-a.log").write_text(run(SSH + ["cat /proc/interrupts"]))
    time.sleep(2)
    (output / "irq-idle-b.log").write_text(run(SSH + ["cat /proc/interrupts"]))

    remote_file = f"/tmp/{output.name}-{args.mode}.nv16"
    player = None
    trial = None
    try:
        if args.mode == "sparse":
            run(SSH + ["rmmod h713_hdmi_v4l2 && "
                       "insmod /tmp/h713-hdmi-v4l2.ko verify_full=0"])
        print(f"Module ready: {args.mode} verification", flush=True)
        with (output / "trial.log").open("w") as trial_log:
            trial = subprocess.Popen(
                [sys.executable, str(HERE / "run-detection-trial.py"),
                 "--seconds", "30"], stdout=trial_log,
                stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if trial.poll() is not None:
                    raise RuntimeError("HDMI signal trial ended before output enabled")
                if ((CONNECTOR / "status").read_text().strip() == "connected" and
                        (CONNECTOR / "enabled").read_text().strip() == "enabled"):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("GPU HDMI output did not enable")
            (output / "host-displays.log").write_text(
                run(["cosmic-randr", "list"], timeout=10))
            with (output / "mpv.log").open("w") as player_log:
                player = subprocess.Popen(
                    ["mpv", "--no-config", "--no-audio", "--vo=gpu",
                     "--gpu-context=wayland", "--loop-file=inf", "--fullscreen",
                     "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
                     "--no-input-default-bindings", str(PATTERN)],
                    stdout=player_log, stderr=subprocess.STDOUT)
                time.sleep(2)
                if player.poll() is not None:
                    raise RuntimeError("mpv exited before capture; inspect mpv.log")
                (output / "irq-video-a.log").write_text(
                    run(SSH + ["cat /proc/interrupts"]))
                command = ("timeout -s KILL 12s ffmpeg -nostdin -y "
                           "-hide_banner -loglevel info -f v4l2 "
                           "-input_format nv16 -video_size 640x480 "
                           "-i /dev/video1 -fps_mode passthrough "
                           f"-frames:v {args.frames} -pix_fmt nv16 "
                           f"-f rawvideo {remote_file}")
                capture = subprocess.run(SSH + [command], text=True,
                                         capture_output=True, timeout=20)
                (output / "ffmpeg.log").write_text(
                    capture.stdout + capture.stderr)
                if capture.returncode:
                    raise RuntimeError("FFmpeg capture failed; inspect ffmpeg.log")
                (output / "irq-video-b.log").write_text(
                    run(SSH + ["cat /proc/interrupts"]))
                print("Captured motion stream", flush=True)
                player.terminate()
                player.wait(timeout=5)
                player = None
            trial.wait(timeout=50)
            if trial.returncode:
                raise RuntimeError("HDMI signal trial failed; inspect trial.log")
        raw = output / "capture.nv16"
        run(SCP + [f"root@192.168.4.1:{remote_file}", str(raw)], timeout=50)
        analysis = run([sys.executable, str(HERE / "analyze-motion-stream.py"),
                        str(raw)], timeout=20)
        (output / "analysis.json").write_text(analysis)
        result = json.loads(analysis)
        print(json.dumps({key: result[key] for key in (
            "frames", "patterned_frames", "band_mismatches",
            "stripe_mismatches", "sequential_steps", "duplicate_steps",
            "skipped_steps")}), flush=True)
        if result["patterned_frames"] < args.frames // 2:
            raise RuntimeError("moving pattern did not occupy the HDMI output")
        if result["band_mismatches"] or result["stripe_mismatches"]:
            raise RuntimeError("captured motion frames have inconsistent markers")
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
        if args.mode == "sparse" and (trial is None or trial.poll() is not None):
            restored = subprocess.run(
                SSH + ["rmmod h713_hdmi_v4l2 && "
                       "insmod /tmp/h713-hdmi-v4l2.ko verify_full=1"],
                text=True, capture_output=True, timeout=20)
            (output / "restore.log").write_text(
                restored.stdout + restored.stderr)
            if restored.returncode:
                print("Could not restore full verification; inspect restore.log",
                      file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
