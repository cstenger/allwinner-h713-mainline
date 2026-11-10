#!/usr/bin/env python3
"""Show, interrupt, and recover HDMI capture on the projector panel.

This is an operator-recorded test. It deliberately disables the source GPU's
HDMI output while V4L2 and DRM playback are active, requires the capture stream
to fail closed and the console framebuffer to return, then re-enables the same
source mode and requires a fresh preview to complete. It will not run without
the explicit --camera-ready acknowledgement.
"""

import argparse
import json
import re
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
KERNEL_VERSION = "#1 SMP Thu Sep 24 01:45:24 PDT 2026"


def run(argv, timeout=30, check=True):
    result = subprocess.run(argv, text=True, capture_output=True,
                            timeout=timeout)
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


def wait_connector(expected, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if connector_state() == expected:
            return
        time.sleep(0.1)
    raise RuntimeError(f"connector did not reach {expected}: {connector_state()}")


def primary_fb(state):
    match = re.search(r"(?ms)^plane\[\d+\]: plane-0\n(.*?)(?=^plane\[|^crtc\[|\Z)",
                      state)
    fb = re.search(r"(?m)^\s*fb=(\d+)$", match.group(1)) if match else None
    if not fb:
        raise RuntimeError("KMS primary-plane framebuffer was not reported")
    return int(fb.group(1))


def wait_primary_fb(expected, equal, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = remote("cat /sys/kernel/debug/dri/0/state").stdout
        value = primary_fb(state)
        if (value == expected) == equal:
            return value, state
        time.sleep(0.2)
    relation = "equal" if equal else "differ from"
    raise RuntimeError(f"primary framebuffer did not {relation} {expected}")


def start_source(log):
    return subprocess.Popen(
        ["mpv", "--no-config", "--no-audio", "--vo=gpu",
         "--gpu-context=wayland", "--loop-file=inf", "--fullscreen",
         "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
         "--no-input-default-bindings", str(PATTERN)],
        stdout=log, stderr=subprocess.STDOUT)


def start_preview(stamp, phase, frames):
    ffmpeg_log = f"/tmp/{stamp}-{phase}-ffmpeg.log"
    mpv_log = f"/tmp/{stamp}-{phase}-mpv.log"
    dd_log = f"/tmp/{stamp}-{phase}-dd.log"
    command = (
        "timeout -s INT 25s bash -o pipefail -c '"
        f"dd if=/dev/video1 bs=614400 count={frames} iflag=fullblock "
        f"status=none 2>{dd_log} | "
        "ffmpeg -nostdin -hide_banner -loglevel info "
        "-f rawvideo -pixel_format nv16 -video_size 640x480 -framerate 60 -i - "
        f"-fps_mode passthrough -frames:v {frames} "
        "-vf scale=960:720:flags=fast_bilinear,pad=1280:720:160:0:black,format=bgr0 "
        "-pix_fmt bgr0 -f rawvideo - "
        f"2>{ffmpeg_log} | /usr/local/bin/mpv --no-config --no-audio "
        f"--no-terminal --log-file={mpv_log} --vo=drm --drm-device=/dev/dri/card0 "
        "--demuxer=rawvideo --demuxer-rawvideo-w=1280 "
        "--demuxer-rawvideo-h=720 --demuxer-rawvideo-fps=20 "
        "--demuxer-rawvideo-mp-format=bgr0 -'")
    return subprocess.Popen(SSH + [command], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True), {
                                "ffmpeg": ffmpeg_log,
                                "mpv": mpv_log,
                                "dd": dd_log,
                            }


def collect_target_logs(output, phase, paths):
    for kind, path in paths.items():
        result = remote(f"cat {path}", check=False)
        (output / f"{phase}-{kind}.log").write_text(
            result.stdout + result.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-ready", action="store_true",
                        help="confirm the operator is already recording all five phases")
    args = parser.parse_args()
    if not args.camera_ready:
        parser.error("stop and obtain operator confirmation before using --camera-ready")

    output = Path("/tmp") / ("h713-panel-signal-recovery-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    if remote("uname -v").stdout.strip() != KERNEL_VERSION:
        raise RuntimeError("projector kernel differs from the validated module")
    if connector_state() != ("disconnected", "disabled"):
        raise RuntimeError("GPU test connector is not disconnected and disabled")
    if not PATTERN.is_file():
        print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
                   str(PATTERN)], timeout=40).stdout.strip(), flush=True)
    print(run([sys.executable, str(HERE / "prepare-source3.py")],
              timeout=150).stdout.strip(), flush=True)
    remote("set -e; test -e /sys/module/h713_hdmi_v4l2/parameters/phase_from_hash; "
           "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/verify_full)\" = N; "
           "test \"$(cat /sys/class/video4linux/video1/name)\" = "
           "\"H713 HDMI1 ring capture\"; test -f /sys/kernel/debug/dri/0/state; "
           "test -x /usr/local/bin/mpv; command -v ffmpeg >/dev/null")

    kms_before = remote("cat /sys/kernel/debug/dri/0/state").stdout
    fb_before = primary_fb(kms_before)
    (output / "kms-before.log").write_text(kms_before)
    dmesg_start = int(remote("dmesg | wc -l").stdout.strip())
    trial = source = preview = None
    source_log = None
    interrupted_paths = recovered_paths = None
    try:
        trial_log = (output / "signal-trial.log").open("w")
        trial = subprocess.Popen(
            [sys.executable, str(HERE / "run-detection-trial.py"),
             "--seconds", "30"], stdout=trial_log, stderr=subprocess.STDOUT)
        wait_connector(("connected", "enabled"), 15)

        source_log = (output / "source-before.log").open("w")
        source = start_source(source_log)
        time.sleep(2)
        if source.poll() is not None:
            raise RuntimeError("initial source player exited early")
        preview, interrupted_paths = start_preview(output.name, "interrupted", 600)
        fb_video_a, kms_video_a = wait_primary_fb(fb_before, False, 8)
        (output / "kms-video-before-loss.log").write_text(kms_video_a)
        time.sleep(3)

        stop(source)
        source = None
        source_log.close()
        source_log = None
        run(["cosmic-randr", "disable", "HDMI-A-1"])
        wait_connector(("connected", "disabled"), 5)
        out, err = preview.communicate(timeout=10)
        (output / "interrupted-preview-ssh.log").write_text(out + err)
        interrupted_exit = preview.returncode
        preview = None
        collect_target_logs(output, "interrupted", interrupted_paths)
        interrupted_dd = (output / "interrupted-dd.log").read_text()
        if interrupted_exit == 0 or "Input/output error" not in interrupted_dd:
            raise RuntimeError("signal loss did not fail the active V4L2 stream closed")
        fb_loss, kms_loss = wait_primary_fb(fb_before, True, 8)
        (output / "kms-signal-loss.log").write_text(kms_loss)

        run(["cosmic-randr", "enable", "HDMI-A-1"])
        wait_connector(("connected", "enabled"), 8)
        source_log = (output / "source-recovered.log").open("w")
        source = start_source(source_log)
        time.sleep(2)
        if source.poll() is not None:
            raise RuntimeError("recovered source player exited early")
        preview, recovered_paths = start_preview(output.name, "recovered", 120)
        fb_video_b, kms_video_b = wait_primary_fb(fb_before, False, 8)
        (output / "kms-video-recovered.log").write_text(kms_video_b)
        out, err = preview.communicate(timeout=20)
        (output / "recovered-preview-ssh.log").write_text(out + err)
        recovered_exit = preview.returncode
        preview = None
        collect_target_logs(output, "recovered", recovered_paths)
        if recovered_exit:
            raise RuntimeError(f"recovered panel preview exited {recovered_exit}")
        recovered_ffmpeg = (output / "recovered-ffmpeg.log").read_text()
        if not re.search(r"frame=\s*120\b", recovered_ffmpeg):
            raise RuntimeError("recovered conversion did not produce 120 frames")

        stop(source)
        source = None
        source_log.close()
        source_log = None
        trial.wait(timeout=35)
        trial_log.close()
        if trial.returncode:
            raise RuntimeError("bounded signal trial failed")
        wait_connector(("disconnected", "disabled"), 8)
        fb_after, kms_after = wait_primary_fb(fb_before, True, 8)
        (output / "kms-after.log").write_text(kms_after)
        dmesg = remote(
            f"dmesg | tail -n +{dmesg_start + 1} | "
            "grep -E 'h713-hdmi-v4l2: (stream|learned completion phase)'",
            check=False).stdout
        (output / "driver.log").write_text(dmesg)
        result = {
            "camera_ready": True,
            "interrupted_preview_exit": interrupted_exit,
            "recovered_preview_exit": recovered_exit,
            "primary_fb_before": fb_before,
            "primary_fb_video_before_loss": fb_video_a,
            "primary_fb_signal_loss": fb_loss,
            "primary_fb_video_recovered": fb_video_b,
            "primary_fb_after": fb_after,
            "source_restored": True,
        }
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    finally:
        stop(source)
        if source_log is not None:
            source_log.close()
        if preview is not None and preview.poll() is None:
            stop(preview)
        if trial is not None and trial.poll() is None:
            trial.wait(timeout=40)
        if connector_state()[0] == "connected" and connector_state()[1] != "enabled":
            run(["cosmic-randr", "enable", "HDMI-A-1"], check=False)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
