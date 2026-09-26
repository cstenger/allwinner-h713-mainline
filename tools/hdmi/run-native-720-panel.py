#!/usr/bin/env python3
"""Show a camera-gated native 720p marker and video on the projector panel."""

import argparse
import hashlib
import json
import re
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
PROBE = Path("/tmp/h713-scp-probe-720/h713-scp-probe.ko")
PATTERN = Path("/tmp/h713-motion-pattern-1280x720.mkv")
DEFAULT_VIDEO = Path("/home/chris/Projects/h713/local/"
                     "Madame Leota Complete Audio Loop - 720.mp4")
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5"]
KERNEL_RELEASE = "6.18.38"


def run(argv, timeout=30, check=True):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1200:]} {result.stderr[-1200:]}")
    return result


def remote(command, timeout=30, check=True):
    return run(SSH + [command], timeout, check)


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def connector_state():
    return ((CONNECTOR / "status").read_text().strip(),
            (CONNECTOR / "enabled").read_text().strip())


def primary_fb(state):
    match = re.search(r"(?ms)^plane\[\d+\]: plane-0\n(.*?)(?=^plane\[|^crtc\[|\Z)",
                      state)
    fb = re.search(r"(?m)^\s*fb=(\d+)$", match.group(1)) if match else None
    if not fb:
        raise RuntimeError("KMS primary-plane framebuffer was not reported")
    return int(fb.group(1))


def restore_console():
    return remote("echo 0 > /sys/class/graphics/fb0/blank; "
                  "test \"$(cat /sys/class/graphics/fb0/blank)\" = 0", check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ready = ap.add_mutually_exclusive_group()
    ready.add_argument("--camera-ready", action="store_true",
                       help="confirm recording includes console, marker, video, console")
    ready.add_argument("--operator-ready", action="store_true",
                       help="confirm the operator is watching; no optical evidence retained")
    ap.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    args = ap.parse_args()
    if not (args.camera_ready or args.operator_ready):
        ap.error("stop and obtain operator confirmation before the visible run")
    for path in (MODULE, FALLBACK, PROBE, args.video):
        if not path.is_file():
            ap.error(f"required file not found: {path}")
    if connector_state() != ("disconnected", "disabled"):
        raise RuntimeError("GPU test connector is not disconnected and disabled")
    if remote("uname -r").stdout.strip() != KERNEL_RELEASE:
        raise RuntimeError("projector kernel release differs from the validated module")
    if not PATTERN.is_file():
        print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
                   str(PATTERN), "--width", "1280", "--height", "720"],
                  timeout=120).stdout.strip(), flush=True)

    output = Path("/tmp") / ("h713-native-720-panel-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    module_sha = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    (output / "module-sha256.txt").write_text(module_sha + "\n")
    run(SCP + [str(PROBE), "root@192.168.4.1:/tmp/h713-scp-probe.ko"])
    run(SCP + [str(MODULE), "root@192.168.4.1:/tmp/h713-hdmi-v4l2-720.ko"])
    run(SCP + [str(FALLBACK), "root@192.168.4.1:/tmp/h713-hdmi-v4l2.ko"])
    try:
        remote("set -e; if test -d /sys/module/h713_hdmi_v4l2; then "
               "rmmod h713_hdmi_v4l2; fi; "
               f"test \"$(sha256sum /tmp/h713-hdmi-v4l2-720.ko | cut -d' ' -f1)\" = {module_sha}; "
               "insmod /tmp/h713-hdmi-v4l2-720.ko width=1280 height=720 verify_full=0; "
               "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/width)\" = 1280; "
               "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/height)\" = 720; "
               "test -f /sys/kernel/debug/dri/0/state; test -x /usr/local/bin/mpv; "
               "command -v ffmpeg >/dev/null")
    except (RuntimeError, subprocess.TimeoutExpired):
        remote("if test -d /sys/module/h713_hdmi_v4l2; then "
               "rmmod h713_hdmi_v4l2; fi; "
               "insmod /tmp/h713-hdmi-v4l2.ko verify_full=1", check=False)
        raise

    kms_before = remote("cat /sys/kernel/debug/dri/0/state").stdout
    fb_before = primary_fb(kms_before)
    (output / "kms-before.log").write_text(kms_before)
    stamp = output.name
    ffmpeg_log = f"/tmp/{stamp}-ffmpeg.log"
    mpv_log = f"/tmp/{stamp}-mpv.log"
    dd_log = f"/tmp/{stamp}-dd.log"
    target = (
        "timeout -s INT 25s bash -o pipefail -c '"
        f"dd if=/dev/video1 bs=1843200 count=240 iflag=fullblock status=none 2>{dd_log} | "
        "ffmpeg -nostdin -hide_banner -loglevel info -f rawvideo "
        "-pixel_format nv16 -video_size 1280x720 -framerate 60 -i - "
        "-fps_mode passthrough -frames:v 240 -vf format=bgr0 -pix_fmt bgr0 "
        f"-f rawvideo - 2>{ffmpeg_log} | /usr/local/bin/mpv --no-config "
        f"--no-audio --no-terminal --log-file={mpv_log} --vo=drm "
        "--drm-device=/dev/dri/card0 --demuxer=rawvideo "
        "--demuxer-rawvideo-w=1280 --demuxer-rawvideo-h=720 "
        "--demuxer-rawvideo-fps=20 --demuxer-rawvideo-mp-format=bgr0 -'")

    trial = source = preview = None
    try:
        with (output / "trial.log").open("w") as trial_log:
            trial = subprocess.Popen(
                [sys.executable, str(HERE / "run-detection-trial.py"),
                 "--seconds", "30", "--probe-port-cache"],
                stdout=trial_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if connector_state() == ("connected", "enabled"):
                    break
                if trial.poll() is not None:
                    raise RuntimeError("720p signal trial ended before output enabled")
                time.sleep(0.1)
            else:
                raise RuntimeError("source GPU did not enable 720p")

            with (output / "source-mpv.log").open("w") as source_log:
                source = subprocess.Popen(
                    ["mpv", "--no-config", "--no-audio", "--vo=gpu",
                     "--gpu-context=wayland", "--fullscreen",
                     "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
                     "--no-input-default-bindings", str(PATTERN), str(args.video)],
                    stdout=source_log, stderr=subprocess.STDOUT)
                time.sleep(1)
                if source.poll() is not None:
                    raise RuntimeError("source playlist exited early")
                preview = subprocess.Popen(SSH + [target], stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True)
                time.sleep(2)
                if preview.poll() is not None:
                    raise RuntimeError("native panel preview exited early")
                kms_during = remote("cat /sys/kernel/debug/dri/0/state").stdout
                (output / "kms-during.log").write_text(kms_during)
                out, err = preview.communicate(timeout=25)
                (output / "preview-ssh.log").write_text(out + err)
                if preview.returncode:
                    raise RuntimeError(f"native panel preview exited {preview.returncode}")
                preview = None
                stop(source)
                source = None
            trial.wait(timeout=45)
            if trial.returncode:
                raise RuntimeError("720p signal trial failed")

        ffmpeg_text = remote(f"cat {ffmpeg_log}").stdout
        (output / "target-ffmpeg.log").write_text(ffmpeg_text)
        (output / "target-mpv.log").write_text(remote(f"cat {mpv_log}").stdout)
        (output / "target-dd.log").write_text(remote(f"cat {dd_log}", check=False).stdout)
        if not re.search(r"frame=\s*240\b", ffmpeg_text):
            raise RuntimeError("native conversion did not produce all 240 frames")
        kms_after = remote("cat /sys/kernel/debug/dri/0/state").stdout
        fb_during = primary_fb(kms_during)
        fb_after = primary_fb(kms_after)
        (output / "kms-after.log").write_text(kms_after)
        if fb_during == fb_before or fb_after != fb_before:
            raise RuntimeError("KMS primary framebuffer did not switch and restore")
        telemetry = remote(
            "dmesg | grep 'h713-hdmi-v4l2' | tail -8; "
            "grep -H . /sys/module/h713_hdmi_v4l2/parameters/{frames_produced,"
            "frames_delivered,frames_overwritten,frames_rejected}").stdout
        (output / "driver-telemetry.txt").write_text(telemetry)
        result = {"camera_ready": args.camera_ready,
                  "operator_observation_only": args.operator_ready,
                  "frames": 240, "display_fps": 20,
                  "primary_fb_before": fb_before,
                  "primary_fb_during": fb_during,
                  "primary_fb_after": fb_after,
                  "source_restored": connector_state() ==
                  ("disconnected", "disabled")}
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    finally:
        stop(source)
        if preview is not None and preview.poll() is None:
            stop(preview)
        console = restore_console()
        if console.returncode:
            print("WARNING: framebuffer console unblank failed", file=sys.stderr)
        if trial is not None and trial.poll() is None:
            trial.wait(timeout=45)
        restore = remote(
            "set -e; if test -d /sys/module/h713_hdmi_v4l2; then "
            "rmmod h713_hdmi_v4l2; fi; "
            "insmod /tmp/h713-hdmi-v4l2.ko verify_full=1", check=False)
        (output / "restore.log").write_text(
            restore.stdout + restore.stderr + f"exit={restore.returncode}\n")
        if restore.returncode:
            print("WARNING: fallback V4L2 module restore failed", file=sys.stderr)
        run([sys.executable, str(HERE / "prepare-source3.py"),
             "--postboot-only"], timeout=90, check=False)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
