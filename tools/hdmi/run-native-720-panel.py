#!/usr/bin/env python3
"""Show camera-gated native 720p capture through the projector NV12 plane."""

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
PANEL_FRAMES = 360
PANEL_FPS = 60
TAIL_FRAME_BUDGET = 8


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
    return plane_state(state, "plane-0")[1]


def plane_state(state, name):
    match = re.search(rf"(?ms)^plane\[\d+\]: {re.escape(name)}\n"
                      r"(.*?)(?=^plane\[|^crtc\[|\Z)", state)
    crtc = re.search(r"(?m)^\s*crtc=(.+)$", match.group(1)) if match else None
    fb = re.search(r"(?m)^\s*fb=(\d+)$", match.group(1)) if match else None
    if not crtc or not fb:
        raise RuntimeError(f"KMS {name} state was not reported")
    return crtc.group(1), int(fb.group(1))


def wait_overlay_released(primary, timeout=5):
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = remote("cat /sys/kernel/debug/dri/0/state").stdout
        if (plane_state(last, "plane-0") == ("crtc-0", primary) and
                plane_state(last, "video-0") == ("(null)", 0)):
            return last
        time.sleep(0.1)
    raise RuntimeError("NV12 overlay did not retire and restore the console plane")


def capture_telemetry(text):
    values = {}
    for name in ("frames_produced", "frames_delivered",
                 "frames_overwritten", "frames_rejected"):
        match = re.search(rf"/{name}:(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"capture telemetry omitted {name}")
        values[name] = int(match.group(1))

    stream_lines = re.findall(r"(?m)^.*h713-hdmi-v4l2: stream .*$", text)
    unstable = (re.search(r"\bunstable=(\d+)\b", stream_lines[-1])
                if stream_lines else None)
    if not unstable:
        raise RuntimeError("capture telemetry omitted the final unstable count")
    values["unstable"] = int(unstable.group(1))
    return values


def validate_capture_telemetry(values):
    produced = values["frames_produced"]
    delivered = values["frames_delivered"]
    overwritten = values["frames_overwritten"]
    rejected = values["frames_rejected"]
    if values["unstable"] or rejected:
        raise RuntimeError("capture rejected or observed an unstable frame")
    if delivered < PANEL_FRAMES:
        raise RuntimeError("capture delivered fewer than the requested frames")
    if produced != delivered + overwritten + rejected:
        raise RuntimeError("capture frame accounting does not close")
    events_beyond_pipeline = produced - PANEL_FRAMES
    if events_beyond_pipeline < 0 or events_beyond_pipeline > TAIL_FRAME_BUDGET:
        raise RuntimeError("capture shutdown tail exceeded its frame budget")
    values["events_beyond_pipeline"] = events_beyond_pipeline
    return values


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
               "insmod /tmp/h713-hdmi-v4l2-720.ko width=1280 height=720 "
               "verify_full=0 source_cached=1 use_vmalloc=1; "
               "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/width)\" = 1280; "
               "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/height)\" = 720; "
               "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/source_cached)\" = Y; "
               "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/use_vmalloc)\" = Y; "
               "test -f /sys/kernel/debug/dri/0/state; "
               "command -v gst-launch-1.0 >/dev/null; "
               "gst-inspect-1.0 kmssink >/dev/null")
    except (RuntimeError, subprocess.TimeoutExpired):
        remote("if test -d /sys/module/h713_hdmi_v4l2; then "
               "rmmod h713_hdmi_v4l2; fi; "
               "insmod /tmp/h713-hdmi-v4l2.ko verify_full=1", check=False)
        raise

    kms_before = remote("cat /sys/kernel/debug/dri/0/state").stdout
    fb_before = primary_fb(kms_before)
    if plane_state(kms_before, "video-0") != ("(null)", 0):
        raise RuntimeError("KMS NV12 overlay was already active before the test")
    (output / "kms-before.log").write_text(kms_before)
    target = (
        "timeout -s INT 15s gst-launch-1.0 -e "
        f"v4l2src device=/dev/video1 num-buffers={PANEL_FRAMES} io-mode=mmap "
        "! video/x-raw,format=NV16,width=1280,height=720,framerate=60/1 "
        "! videoconvert n-threads=4 "
        "! video/x-raw,format=NV12 "
        "! kmssink driver-name=sun50i-h713-afbd sync=false skip-vsync=true")

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
                video_crtc, video_fb = plane_state(kms_during, "video-0")
                if video_crtc != "crtc-0" or not video_fb:
                    raise RuntimeError("KMS NV12 overlay did not become active")
                out, err = preview.communicate(timeout=20)
                (output / "preview-ssh.log").write_text(out + err)
                if preview.returncode:
                    raise RuntimeError(f"native panel preview exited {preview.returncode}")
                preview = None
                stop(source)
                source = None
            trial.wait(timeout=45)
            if trial.returncode:
                raise RuntimeError("720p signal trial failed")

        gst_text = (output / "preview-ssh.log").read_text()
        elapsed = re.search(r"Execution ended after (\d+):(\d+):(\d+)\.(\d+)",
                            gst_text)
        if "Got EOS" not in gst_text or not elapsed:
            raise RuntimeError("GStreamer did not report a bounded EOS completion")
        elapsed_s = (int(elapsed.group(1)) * 3600 + int(elapsed.group(2)) * 60 +
                     int(elapsed.group(3)) + float("0." + elapsed.group(4)))
        measured_fps = PANEL_FRAMES / elapsed_s
        if measured_fps < 55:
            raise RuntimeError(f"NV12 panel path ran at only {measured_fps:.2f} fps")
        kms_after = wait_overlay_released(fb_before)
        fb_during = primary_fb(kms_during)
        fb_after = primary_fb(kms_after)
        (output / "kms-after.log").write_text(kms_after)
        if fb_during != fb_before or fb_after != fb_before:
            raise RuntimeError("KMS primary framebuffer changed during overlay playback")
        telemetry = remote(
            "dmesg | grep 'h713-hdmi-v4l2' | tail -8; "
            "grep -H . /sys/module/h713_hdmi_v4l2/parameters/{frames_produced,"
            "frames_delivered,frames_overwritten,frames_rejected}").stdout
        (output / "driver-telemetry.txt").write_text(telemetry)
        counters = validate_capture_telemetry(capture_telemetry(telemetry))
        result = {"camera_ready": args.camera_ready,
                  "operator_observation_only": args.operator_ready,
                  "pipeline_frames": PANEL_FRAMES,
                  "nominal_display_fps": PANEL_FPS,
                  "measured_fps": round(measured_fps, 2),
                  "driver_produced": counters["frames_produced"],
                  "driver_delivered": counters["frames_delivered"],
                  "driver_overwritten_total": counters["frames_overwritten"],
                  "driver_rejected": counters["frames_rejected"],
                  "driver_unstable": counters["unstable"],
                  "driver_events_beyond_pipeline":
                  counters["events_beyond_pipeline"],
                  "primary_fb_before": fb_before,
                  "primary_fb_during": fb_during,
                  "primary_fb_after": fb_after,
                  "video_fb_during": video_fb,
                  "source_restored": connector_state() ==
                  ("disconnected", "disabled")}
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    finally:
        stop(source)
        if preview is not None and preview.poll() is None:
            stop(preview)
            remote("pkill -INT -x gst-launch-1.0 || true", check=False)
        try:
            wait_overlay_released(fb_before)
        except (RuntimeError, subprocess.TimeoutExpired):
            print("WARNING: NV12 overlay release was not confirmed", file=sys.stderr)
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
