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
GST_RUNNER = HERE / "gst-native-720-panel.c"
PROBE = ROOT / "build/scp-probe-1280-720/h713-scp-probe.ko"
# The tested module defaults to the conservative 640x480/full-verification
# configuration.  Native 720p is selected only by the explicit insmod options
# below, so the same pinned binary is also the deterministic fallback.
FALLBACK = MODULE
PATTERN = Path("/tmp/h713-motion-pattern-1280x720.mkv")
DEFAULT_VIDEO = Path("/home/chris/Projects/h713/local/"
                     "Madame Leota Complete Audio Loop - 720.mp4")
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5"]
KERNEL_RELEASE = "6.18.38"
EDID_SHA256 = "1bf44b2172fb4e512d8a575c58f2abbcfd96d2f2902bea5b8a7a323248fb9013"
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


def require_native_source(timeout=4):
    edid = (CONNECTOR / "edid").read_bytes()
    modes = (CONNECTOR / "modes").read_text().splitlines()
    digest = hashlib.sha256(edid).hexdigest()
    if digest != EDID_SHA256 or "1280x720" not in modes:
        raise RuntimeError("source did not read the pinned 1280x720 EDID")
    deadline = time.monotonic() + timeout
    port = None
    while time.monotonic() < deadline:
        state = json.loads(remote(
            "python3 /root/hdmi-safe-trace/read-mips-port-cache.py").stdout)
        port = next((item for item in state["ports"]
                     if item["port_id"] == 1), None)
        if port and (port["state"], port["hactive"], port["vactive"],
                     port["pixel_repeat"]) == (5, 1280, 720, 0):
            return digest, port
        time.sleep(0.2)
    raise RuntimeError(f"receiver did not lock to native 1280x720: {port}")


def display_error_count():
    pattern = ("sun50i-iommu.*(Page fault|cannot remap)|"
               "atomic commit.*fail|RGB quiesce vblank timed out|"
               "timed out draining retired framebuffers")
    result = remote(f"dmesg | grep -E -c '{pattern}' || true").stdout.strip()
    return int(result or "0")


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
    for path in (MODULE, GST_RUNNER, PROBE, args.video):
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
    runner_sha = hashlib.sha256(GST_RUNNER.read_bytes()).hexdigest()
    probe_sha = hashlib.sha256(PROBE.read_bytes()).hexdigest()
    (output / "module-sha256.txt").write_text(module_sha + "\n")
    (output / "runner-sha256.txt").write_text(runner_sha + "\n")
    (output / "probe-sha256.txt").write_text(probe_sha + "\n")
    run(SCP + [str(PROBE), "root@192.168.4.1:/tmp/h713-scp-probe.ko"])
    run(SCP + [str(MODULE), "root@192.168.4.1:/tmp/h713-hdmi-v4l2-720.ko"])
    run(SCP + [str(FALLBACK), "root@192.168.4.1:/tmp/h713-hdmi-v4l2.ko"])
    run(SCP + [str(GST_RUNNER),
               "root@192.168.4.1:/tmp/h713-gst-native-720-panel.c"])
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
               "test -f /tmp/h713-scp-probe.ko; "
               "set -- $(modinfo -F vermagic /tmp/h713-scp-probe.ko); "
               "test \"$1\" = \"$(uname -r)\"; "
               "test -f /sys/kernel/debug/dri/0/state; "
               "command -v gst-launch-1.0 >/dev/null; "
               "gst-inspect-1.0 kmssink >/dev/null; "
               f"test \"$(sha256sum /tmp/h713-gst-native-720-panel.c | cut -d' ' -f1)\" = {runner_sha}; "
               "cc -O2 -Wall -Wextra -Werror "
               "-o /tmp/h713-gst-native-720-panel "
               "/tmp/h713-gst-native-720-panel.c "
               "$(pkg-config --cflags --libs gstreamer-1.0)")
    except (RuntimeError, subprocess.TimeoutExpired):
        remote("if test -d /sys/module/h713_hdmi_v4l2; then "
               "rmmod h713_hdmi_v4l2; fi; "
               "insmod /tmp/h713-hdmi-v4l2.ko verify_full=1", check=False)
        raise

    kms_before = remote("cat /sys/kernel/debug/dri/0/state").stdout
    fb_before = primary_fb(kms_before)
    errors_before = display_error_count()
    if plane_state(kms_before, "video-0") != ("(null)", 0):
        raise RuntimeError("KMS NV12 overlay was already active before the test")
    (output / "kms-before.log").write_text(kms_before)
    target = ("timeout -s INT 15s /tmp/h713-gst-native-720-panel "
              f"{PANEL_FRAMES}")

    # This is intentionally the first projector-visible action.  Leave enough
    # time for the camera to record the known-good console before video starts.
    console = restore_console()
    if console.returncode:
        raise RuntimeError("framebuffer console unblank failed")
    time.sleep(2)

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

            edid_sha, receiver = require_native_source()

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
        summaries = [line for line in gst_text.splitlines()
                     if line.startswith("{")]
        if not summaries:
            raise RuntimeError("GStreamer runner did not report its counters")
        pipeline = json.loads(summaries[-1])
        (output / "pipeline-summary.json").write_text(
            json.dumps(pipeline, indent=2) + "\n")
        for name in ("requested_frames", "source_buffers", "sink_buffers",
                     "rendered"):
            if pipeline.get(name) != PANEL_FRAMES:
                raise RuntimeError(f"pipeline counter {name} did not reach "
                                   f"{PANEL_FRAMES}")
        for name in ("dropped", "pts_mismatches", "unmatched_buffers"):
            if pipeline.get(name) != 0:
                raise RuntimeError(f"pipeline counter {name} was nonzero")
        elapsed_s = pipeline["elapsed_seconds"]
        measured_fps = PANEL_FRAMES / elapsed_s
        if measured_fps < 55:
            raise RuntimeError(f"NV12 panel path ran at only {measured_fps:.2f} fps")
        kms_after = wait_overlay_released(fb_before)
        errors_after = display_error_count()
        fb_during = primary_fb(kms_during)
        fb_after = primary_fb(kms_after)
        (output / "kms-after.log").write_text(kms_after)
        if fb_during != fb_before or fb_after != fb_before:
            raise RuntimeError("KMS primary framebuffer changed during overlay playback")
        if errors_after != errors_before:
            raise RuntimeError("panel run introduced an IOMMU or DRM cleanup error")
        telemetry = remote(
            "dmesg | grep 'h713-hdmi-v4l2' | tail -8; "
            "grep -H . /sys/module/h713_hdmi_v4l2/parameters/{frames_produced,"
            "frames_delivered,frames_overwritten,frames_rejected}").stdout
        (output / "driver-telemetry.txt").write_text(telemetry)
        counters = validate_capture_telemetry(capture_telemetry(telemetry))
        result = {"camera_ready": args.camera_ready,
                  "operator_observation_only": args.operator_ready,
                  "pipeline_frames": PANEL_FRAMES,
                  "pipeline_rendered": pipeline["rendered"],
                  "pipeline_dropped": pipeline["dropped"],
                  "source_edid_sha256": edid_sha,
                  "receiver_hactive": receiver["hactive"],
                  "receiver_vactive": receiver["vactive"],
                  "conversion_mean_us": pipeline["conversion_mean_us"],
                  "conversion_max_us": pipeline["conversion_max_us"],
                  "nominal_display_fps": PANEL_FPS,
                  "measured_fps": round(measured_fps, 2),
                  "driver_produced": counters["frames_produced"],
                  "driver_delivered": counters["frames_delivered"],
                  "driver_overwritten_total": counters["frames_overwritten"],
                  "driver_rejected": counters["frames_rejected"],
                  "driver_unstable": counters["unstable"],
                  "driver_events_beyond_pipeline":
                  counters["events_beyond_pipeline"],
                  "display_errors_before": errors_before,
                  "display_errors_after": errors_after,
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
