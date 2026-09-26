#!/usr/bin/env python3
"""Run a bounded, receiver-only 1280x720 V4L2 marker capture."""

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
MODULE = ROOT / "modules/hdmi-v4l2/h713-hdmi-v4l2.ko"
FALLBACK = Path("/tmp/h713-v4l2-restore.qIXYPX/modules/hdmi-v4l2/"
                "h713-hdmi-v4l2.ko")
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
    ap.add_argument("--frames", type=int, choices=range(1, 121), default=30)
    ap.add_argument("--sparse-verify", action="store_true")
    args = ap.parse_args()
    for path in (args.probe_module, MODULE, FALLBACK):
        if not path.is_file():
            ap.error(f"required module not found: {path}")

    output = Path("/tmp") / ("h713-native-720-v4l2-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
               str(PATTERN), "--width", "1280", "--height", "720"],
              timeout=120).strip(), flush=True)
    module_sha = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    (output / "module-sha256.txt").write_text(module_sha + "\n")
    run(SCP + [str(args.probe_module),
               "root@192.168.4.1:/tmp/h713-scp-probe.ko"])
    run(SCP + [str(MODULE), "root@192.168.4.1:/tmp/h713-hdmi-v4l2-720.ko"])
    run(SCP + [str(FALLBACK), "root@192.168.4.1:/tmp/h713-hdmi-v4l2.ko"])
    verify = 0 if args.sparse_verify else 1
    trial = None
    player = None
    remote_raw = f"/tmp/{output.name}.nv16"
    try:
        setup = run(SSH + [
            "set -e; if test -d /sys/module/h713_hdmi_v4l2; then "
            "rmmod h713_hdmi_v4l2; fi; "
            f"test \"$(sha256sum /tmp/h713-hdmi-v4l2-720.ko | cut -d' ' -f1)\" = {module_sha}; "
            "insmod /tmp/h713-hdmi-v4l2-720.ko width=1280 height=720 "
            f"verify_full={verify}; v4l2-ctl -d /dev/video1 --all; "
            "v4l2-ctl -d /dev/video1 --list-formats-ext"])
        (output / "v4l2-capability.txt").write_text(setup)
        with (output / "trial.log").open("w") as log:
            trial = subprocess.Popen(
                [sys.executable, str(HERE / "run-detection-trial.py"),
                 "--seconds", "30", "--probe-port-cache"],
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
                    raise RuntimeError("mpv exited before V4L2 capture")
                command = ("timeout -s KILL 20s ffmpeg -nostdin -y -hide_banner "
                           "-loglevel info -f v4l2 -input_format nv16 "
                           "-video_size 1280x720 -i /dev/video1 -fps_mode passthrough "
                           f"-frames:v {args.frames} -pix_fmt nv16 -f rawvideo {remote_raw}")
                capture = subprocess.run(SSH + [command], text=True,
                                         capture_output=True, timeout=25)
                (output / "ffmpeg.log").write_text(capture.stdout + capture.stderr)
                if capture.returncode:
                    raise RuntimeError("720p V4L2 capture failed; inspect ffmpeg.log")
                player.terminate()
                player.wait(timeout=5)
                player = None
            trial.wait(timeout=50)
            if trial.returncode:
                raise RuntimeError("720p detection trial failed; inspect trial.log")

        raw = output / "capture.nv16"
        run(SCP + [f"root@192.168.4.1:{remote_raw}", str(raw)], timeout=60)
        if raw.stat().st_size != args.frames * FRAME:
            raise RuntimeError(f"capture size is {raw.stat().st_size}, expected "
                               f"{args.frames * FRAME}")
        analysis = run([sys.executable, str(HERE / "analyze-motion-stream.py"),
                        str(raw), "--width", "1280", "--height", "720"], timeout=30)
        (output / "analysis.json").write_text(analysis)
        result = json.loads(analysis)
        telemetry = run(SSH + [
            "dmesg | grep 'h713-hdmi-v4l2' | tail -8; "
            "grep -H . /sys/module/h713_hdmi_v4l2/parameters/{frames_produced,"
            "frames_delivered,frames_overwritten,frames_rejected,width,height,verify_full}"])
        (output / "driver-telemetry.txt").write_text(telemetry)
        print(json.dumps({key: result[key] for key in
                          ("frames", "patterned_frames", "band_mismatches",
                           "stripe_mismatches", "sequential_steps",
                           "duplicate_steps", "skipped_steps")}), flush=True)
        if (result["patterned_frames"] != args.frames or
                result["band_mismatches"] or result["stripe_mismatches"]):
            raise RuntimeError("720p V4L2 marker integrity check failed")
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
        restore = subprocess.run(SSH + [
            "set -e; if test -d /sys/module/h713_hdmi_v4l2; then "
            "rmmod h713_hdmi_v4l2; fi; "
            "insmod /tmp/h713-hdmi-v4l2.ko verify_full=1"],
            text=True, capture_output=True, timeout=20)
        (output / "restore.log").write_text(restore.stdout + restore.stderr)
        try:
            print(run([sys.executable, str(HERE / "prepare-source3.py"),
                       "--postboot-only"], timeout=90).strip(), flush=True)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"WARNING: standard probe restore failed: {exc}", file=sys.stderr)
        if restore.returncode:
            print("WARNING: standard V4L2 module restore failed", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
