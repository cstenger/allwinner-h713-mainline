#!/usr/bin/env python3
"""Compare H713 HDMI audio status during silence and deterministic GPU LPCM."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path('/home/chris/.codex/worktrees/hdmi-capture-current/h713/tools/hdmi')
ROOT = HERE.parents[1]
DEFAULT_MODULE = ROOT / "modules/hdmi-audio-probe/h713-hdmi-audio-probe.ko"
DEFAULT_EDID_PROBE = Path("/tmp/h713-hdmi-complete-edid-probe/h713-scp-probe.ko")
CANONICAL_EDID_SHA256 = "edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34"
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5"]


def run(argv, timeout=30, check=True):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1000:]} {result.stderr[-1000:]}")
    return result


def remote(command, timeout=20):
    return run(SSH + [command], timeout).stdout


def snapshot(sequence):
    remote(f"echo {sequence} > /sys/module/h713_hdmi_audio_probe/parameters/snapshot")
    data = subprocess.run(SSH + ['python3 /tmp/h713-read-aligned-elog.py'], capture_output=True, timeout=15, check=True).stdout
    Path(f'/tmp/h713-bridge-monitor-elog-{sequence}.bin').write_bytes(data)
    Path(f'/tmp/h713-bridge-monitor-cache-{sequence}.json').write_text(remote('python3 /root/hdmi-safe-trace/read-audio-monitor-trace.py'))



def source_connector():
    for connector in Path("/sys/class/drm").glob("card*-HDMI-A-*"):
        try:
            edid = (connector / "edid").read_bytes()
        except OSError:
            continue
        if edid and hashlib.sha256(edid).hexdigest() == CANONICAL_EDID_SHA256:
            return connector
    return None


def receiver_lock():
    result = remote("python3 /root/hdmi-safe-trace/read-mips-port-cache.py")
    state = json.loads(result)
    return next((port for port in state["ports"]
                 if port["port_id"] == 1), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, default=DEFAULT_MODULE)
    parser.add_argument("--tvfe-hold-module", type=Path,
                        help="stock-order TVFE hold required for audio-register writes")
    parser.add_argument("--edid-probe", type=Path, default=DEFAULT_EDID_PROBE,
                        help="canonical-EDID SCP probe built for the running kernel")
    parser.add_argument("--seconds", type=float, default=8.0,
                        help="tone duration (default: 8 seconds)")
    parser.add_argument("--init-audio-top", action="store_true",
                        help="apply only the reversible stock audio-top clock sequence")
    parser.add_argument("--stock-audio-ihb", action="store_true",
                        help="temporarily apply the stock audio-IHB mux/divider word")
    parser.add_argument("--activate-spdi1", action="store_true",
                        help="temporarily apply the stock 48-kHz LPCM SPDI1 activation")
    parser.add_argument("--open-spdi1", action="store_true",
                        help="apply the stock SPDI1 IRQ open sequence with an owned handler")
    parser.add_argument("--configure-audbrg", action="store_true",
                        help="configure stock Audio Bridge output stream 0 with private DMA")
    parser.add_argument("--audbrg-stage", type=int, choices=range(1, 5), default=1,
                        help="last Audio Bridge setup phase to apply (default: 1)")
    parser.add_argument("--reuse-loaded-modules", action="store_true",
                        help="verify and reuse an already-loaded guarded TVFE hold and audio probe")
    args = parser.parse_args()
    if not args.module.is_file():
        parser.error(f"module not found: {args.module}")
    register_writes = (args.init_audio_top or args.stock_audio_ihb or
                       args.activate_spdi1 or args.open_spdi1 or
                       args.configure_audbrg)
    if args.open_spdi1 and not args.activate_spdi1:
        parser.error("--open-spdi1 requires --activate-spdi1")
    if args.configure_audbrg and not args.open_spdi1:
        parser.error("--configure-audbrg requires --open-spdi1")
    if register_writes and args.tvfe_hold_module is None:
        parser.error("audio-register writes require --tvfe-hold-module")
    if (args.tvfe_hold_module is not None and
            not args.tvfe_hold_module.is_file()):
        parser.error(f"TVFE hold module not found: {args.tvfe_hold_module}")
    if not args.edid_probe.is_file():
        parser.error(f"canonical EDID probe not found: {args.edid_probe}")
    if not 2 <= args.seconds <= 15:
        parser.error("--seconds must be between 2 and 15")
    if source_connector() is not None:
        raise RuntimeError("canonical H713 EDID is already active before the bounded trial")

    output = Path("/tmp") / ("h713-hdmi-audio-status-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    wav = output / "stereo-1khz-2khz.wav"
    print(run([sys.executable, str(HERE / "make-audio-test.py"), str(wav),
               "--seconds", str(args.seconds)]).stdout.strip(), flush=True)
    print(run([sys.executable, str(HERE / "prepare-source3.py"),
               "--postboot-only"], timeout=100).stdout.strip(), flush=True)

    module_sha = hashlib.sha256(args.module.read_bytes()).hexdigest()
    tvfe_sha = (hashlib.sha256(args.tvfe_hold_module.read_bytes()).hexdigest()
                if args.tvfe_hold_module else None)
    probe_sha = hashlib.sha256(args.edid_probe.read_bytes()).hexdigest()
    staged = [str(args.module), str(args.edid_probe)]
    if args.tvfe_hold_module:
        staged.append(str(args.tvfe_hold_module))
    run(SCP + staged + ["root@192.168.4.1:/tmp/"])
    tvfe_preflight = ""
    if args.reuse_loaded_modules:
        tvfe_preflight = (
            "test -d /sys/module/h713_hdmi_tvfe_hold; "
            "test \"$(cat /sys/module/h713_hdmi_tvfe_hold/parameters/armed)\" = Y; "
            "test \"$(cat /sys/module/h713_hdmi_tvfe_hold/parameters/live_source3)\" = Y; "
            "test \"$(cat /sys/module/h713_hdmi_tvfe_hold/parameters/receiver_powered)\" = Y; ")
    elif args.tvfe_hold_module:
        tvfe_preflight = (
            "test ! -d /sys/module/h713_hdmi_tvfe_hold; "
            "test \"$(sha256sum /tmp/h713-hdmi-tvfe-hold.ko | cut -d' ' -f1)\" = "
            f"{tvfe_sha}; set -- $(modinfo -F vermagic "
            "/tmp/h713-hdmi-tvfe-hold.ko); "
            "test \"$1\" = \"$(uname -r)\"; "
            "insmod /tmp/h713-hdmi-tvfe-hold.ko armed=1 live_source3=1 "
            "receiver_powered=1; "
            "timeout 5s python3 -u /root/mips-shell.py --cmd 'help win' "
            "| grep -q 'VS:/'; ")
    if args.reuse_loaded_modules:
        audio_preflight = (
            "test -d /sys/module/h713_hdmi_audio_probe; "
            "test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/armed)\" = Y; "
            "test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/live_source3)\" = Y; "
            "test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/receiver_powered)\" = Y; "
            f"test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/init_audio_top)\" = "
            f"{'Y' if args.init_audio_top else 'N'}; "
            f"test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/stock_audio_ihb)\" = "
            f"{'Y' if args.stock_audio_ihb else 'N'}; "
            f"test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/activate_spdi1)\" = "
            f"{'Y' if args.activate_spdi1 else 'N'}; "
            f"test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/open_spdi1)\" = "
            f"{'Y' if args.open_spdi1 else 'N'}; "
            f"test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/configure_audbrg)\" = "
            f"{'Y' if args.configure_audbrg else 'N'}; "
            f"test \"$(cat /sys/module/h713_hdmi_audio_probe/parameters/audbrg_stage)\" = "
            f"{args.audbrg_stage}; ")
    else:
        audio_preflight = (
            "test ! -d /sys/module/h713_hdmi_audio_probe; "
            "insmod /tmp/h713-hdmi-audio-probe.ko armed=1 live_source3=1 "
            f"receiver_powered=1 init_audio_top={int(args.init_audio_top)} "
            f"stock_audio_ihb={int(args.stock_audio_ihb)} "
            f"activate_spdi1={int(args.activate_spdi1)} "
            f"open_spdi1={int(args.open_spdi1)} "
            f"configure_audbrg={int(args.configure_audbrg)} "
            f"audbrg_stage={args.audbrg_stage} snapshot=1")
    preflight = remote(
        "set -e; "
        "test -d /sys/module/h713_hdmi_power; "
        "test \"$(cat /sys/devices/h713-hdmi-tvfe/power/runtime_status)\" = active; "
        "test \"$(cat /sys/devices/h713-hdmi-tvcap/power/runtime_status)\" = active; "
        "test \"$(sha256sum /tmp/h713-hdmi-audio-probe.ko | cut -d' ' -f1)\" = "
        f"{module_sha}; set -- $(modinfo -F vermagic /tmp/h713-hdmi-audio-probe.ko); "
        "test \"$1\" = \"$(uname -r)\"; "
        "test \"$(sha256sum /tmp/h713-scp-probe.ko | cut -d' ' -f1)\" = "
        f"{probe_sha}; set -- $(modinfo -F vermagic /tmp/h713-scp-probe.ko); "
        "test \"$1\" = \"$(uname -r)\"; "
        "python3 -u /root/mips-shell.py --status | grep -q 'MIPS core      ALIVE'; "
        f"{tvfe_preflight}{audio_preflight}")
    (output / "probe-load.log").write_text(preflight)

    detector_log = (output / "detection.log").open("w")
    detector = subprocess.Popen(
        [sys.executable, str(HERE / "run-detection-trial.py"), "--seconds", "30",
         "--probe-port-cache", "--stock-io"], stdout=detector_log, stderr=subprocess.STDOUT)
    player = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if detector.poll() is not None:
                raise RuntimeError("bounded EDID/HPD trial ended before audio playback")
            connector = source_connector()
            if (connector is not None and
                    (connector / "status").read_text().strip() == "connected" and
                    (connector / "enabled").read_text().strip() == "enabled"):
                result = run([sys.executable, str(HERE / "find-hdmi-audio-pcm.py")],
                             check=False)
                if result.returncode == 0:
                    pcm = json.loads(result.stdout)
                    receiver = receiver_lock()
                    if (receiver is not None and
                            (receiver["state"], receiver["hactive"],
                         receiver["vactive"], receiver["pixel_repeat"]) ==
                            (5, 1280, 720, 0)):
                        break
            time.sleep(0.2)
        else:
            raise RuntimeError("source HDMI output/ELD did not become ready")

        (output / "pcm.json").write_text(json.dumps(pcm, indent=2) + "\n")
        (output / "receiver-lock.json").write_text(
            json.dumps(receiver, indent=2) + "\n")
        (output / "connector.txt").write_text(connector.name + "\n")
        (output / "eld.txt").write_text(Path(pcm["eld"]).read_text())
        snapshot(2)
        with (output / "aplay.log").open("w") as player_log:
            player = subprocess.Popen(
                ["aplay", "-q", "-D", pcm["pcm"], str(wav)],
                stdout=player_log, stderr=subprocess.STDOUT)
            time.sleep(1.0)
            if player.poll() is not None:
                raise RuntimeError("aplay exited before the first active snapshot")
            snapshot(3)
            time.sleep(min(2.0, args.seconds / 2))
            if player.poll() is not None:
                raise RuntimeError("aplay exited before the second active snapshot")
            snapshot(4)
            player.wait(timeout=args.seconds + 5)
            if player.returncode:
                raise RuntimeError("aplay failed; inspect aplay.log")
            player = None
        snapshot(5)
        detector.wait(timeout=45)
        if detector.returncode:
            raise RuntimeError("bounded EDID/HPD trial failed; inspect detection.log")
        detector_log.flush()
        mips = remote("timeout 5s python3 -u /root/mips-shell.py --cmd 'help win'")
        (output / "mips-after.log").write_text(mips)
        if "VS:/" not in mips:
            raise RuntimeError("MIPS liveness check failed after audio snapshots")
        evidence = remote("dmesg | grep 'h713-hdmi-audio-probe' | tail -20")
        (output / "probe-dmesg.log").write_text(evidence)
        print(evidence.strip(), flush=True)
        print(json.dumps({"logs": str(output), "pcm": pcm["pcm"],
                          "receiver": receiver,
                          "module_sha256": module_sha,
                          "tvfe_hold_sha256": tvfe_sha,
                          "edid_probe_sha256": probe_sha,
                          "init_audio_top": args.init_audio_top,
                          "stock_audio_ihb": args.stock_audio_ihb,
                          "activate_spdi1": args.activate_spdi1,
                          "open_spdi1": args.open_spdi1,
                          "configure_audbrg": args.configure_audbrg,
                          "audbrg_stage": args.audbrg_stage,
                          "reused_loaded_modules": args.reuse_loaded_modules,
                          "tvfe_hold_left_loaded": bool(args.tvfe_hold_module),
                          "probe_left_loaded": True}), flush=True)
        return output
    finally:
        if player is not None and player.poll() is None:
            player.terminate()
            try:
                player.wait(timeout=3)
            except subprocess.TimeoutExpired:
                player.kill()
        if detector.poll() is None:
            try:
                detector.wait(timeout=45)
            except subprocess.TimeoutExpired:
                detector.kill()
        detector_log.close()
        # Deliberately retain the status probe so post-trial state remains
        # inspectable. Its optional IRQs and DMA are released on rmmod; a cold
        # power cycle remains the normal receiver-experiment teardown.


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
