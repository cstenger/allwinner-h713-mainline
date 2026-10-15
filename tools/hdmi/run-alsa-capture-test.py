#!/usr/bin/env python3
"""Test the prepared H713 ALSA capture driver at all three HDMI input rates.

Does not load/unload modules or change the DSP graph. Requires the guarded
receiver/DSP setup and h713-hdmi-audio already prepared by the operator.
"""
import argparse
import importlib.util
import json
import shlex
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rate_test", HERE / "run-audio-rate-test.py")
rate_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rate_test)
SSH = rate_test.SSH[:]
SSH[1:1] = ["-o", "StrictHostKeyChecking=yes"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=5"]


def remote(command, path):
    p = subprocess.run(SSH + [command], capture_output=True, timeout=8)
    path.write_bytes(p.stdout + p.stderr)
    if p.returncode:
        raise RuntimeError(f"board command failed; see {path}")
    return p.stdout.decode()


def read_counters(path):
    text = remote("set -e; for name in period_active period_bytes period_notifications period_xruns; do "
                  "printf '%s ' \"$name\"; cat /sys/module/h713_hdmi_audio/parameters/\"$name\"; done", path)
    return {name: int(value) for name, value in (line.split() for line in text.splitlines())}


def analyze_wave(path, seconds=16):
    with wave.open(str(path)) as stream:
        if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth(), stream.getnframes()) != (48000, 2, 2, seconds*48000):
            raise RuntimeError("unexpected recording format or frame count")
        # Capture starts about one second before source playback; use settled
        # sections and the last second, after the tone has ended.
        tone = []
        for second in range(4, seconds - 7, 2):
            stream.setpos(second * 48000)
            item = rate_test.analysis.analyze(stream.readframes(16384))
            item["recording_second"] = second
            tone.append(item)
        stream.setpos((seconds - 1) * 48000)
        silence = stream.readframes(48000)
        silent = not any(silence)
    return {"tone_windows": tone, "final_second_all_zero": silent,
            "pass": silent and all(t["tone_pass"] and t["capture_rate_hz"] == 48000 for t in tone)}


PERSISTENT_SIGNAL = ("set -e; P=/sys/module/h713_hdmi_signal/parameters; "
                     "test \"$(cat $P/ready)\" = Y; test \"$(cat $P/failed)\" = N; "
                     "test -d /sys/module/h713_ddc_pins; test ! -d /sys/module/h713_scp_probe; "
                     "systemctl is-active h713-hdmi-signal.service; ")


def run_trial(out, rate, index, recorder_command="arecord", stall_reader=False, seconds=16, persistent_signal=False):
    out.mkdir()
    rate_test.make_wave(out / "tone.wav", rate, tone_seconds=seconds - 6)
    result = {"input_rate_hz": rate, "capture_seconds": seconds, "pass": False}
    helper = recorder = player = None
    remote_path = f"/tmp/h713-alsa-capture-{index}.wav"
    try:
        counters_before = read_counters(out / "counters-before.txt")
        with (out / "signal.log").open("w") as signal_log, (out / "capture.log").open("w") as capture_log, (out / "playback.log").open("w") as play_log:
            if persistent_signal:
                # The normal-startup service already owns EDID/HPD; starting
                # the bounded helper would compete with it.
                remote(PERSISTENT_SIGNAL + "grep . /sys/module/h713_hdmi_signal/parameters/ready /sys/module/h713_hdmi_signal/parameters/failed /sys/module/h713_hdmi_signal/parameters/restored", out / "signal-before.txt")
            else:
                helper = subprocess.Popen([sys.executable, str(HERE / "run-detection-trial.py"), "--seconds", str(seconds + 14), "--stock-io"], stdout=signal_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 10
            while True:
                if helper is not None and helper.poll() is not None:
                    raise RuntimeError("signal helper ended before ELD")
                try:
                    card, device, eld = rate_test.find_pcm()
                    break
                except RuntimeError:
                    if time.monotonic() > deadline:
                        raise RuntimeError("HDMI ELD acquisition timed out")
                    time.sleep(.2)
            (out / "eld.txt").write_text(eld.read_text())
            recorder = subprocess.Popen(SSH + [
                f"timeout -k 3s -s INT {seconds + 6}s " + shlex.quote(recorder_command) + " -v -D hw:H713HDMI,0 -t wav -f S16_LE "
                f"-r 48000 -c 2 --period-size=256 --buffer-size=16384 -d {seconds} " + shlex.quote(remote_path)],
                stdout=capture_log, stderr=subprocess.STDOUT)
            time.sleep(.7)
            status = remote("cat /proc/asound/H713HDMI/pcm0c/sub0/status; cat /proc/asound/H713HDMI/pcm0c/sub0/hw_params", out / "capture-start.txt")
            if "state: RUNNING" not in status:
                raise RuntimeError("capture did not enter RUNNING")
            rate_test.check_hw_params(status, 48000)
            player = subprocess.Popen(["aplay", "--disable-resample", "-v", "-D", f"hw:{card},{device}", str(out / "tone.wav")], stdout=play_log, stderr=subprocess.STDOUT)
            time.sleep(.3)
            params = Path(f"/proc/asound/card{card}/pcm{device}p/sub0/hw_params").read_text()
            (out / "host-hw-params.txt").write_text(params)
            rate_test.check_hw_params(params, rate)
            if stall_reader:
                # Stop only this PCM's positively identified reader. The board
                # resumes it in finally even if the host SSH connection fails.
                time.sleep(2)
                script = """import os, signal, time
from pathlib import Path
status = Path('/proc/asound/H713HDMI/pcm0c/sub0/status')
text = status.read_text()
assert 'state: RUNNING' in text, text
pid = int(next(line.split(':', 1)[1] for line in text.splitlines() if line.startswith('owner_pid')))
assert Path(f'/proc/{pid}/comm').read_text().strip() == 'arecord'
os.kill(pid, signal.SIGSTOP)
try:
    time.sleep(1)
    text = status.read_text()
    print(text, flush=True)
    assert 'state: XRUN' in text, text
finally:
    os.kill(pid, signal.SIGCONT)
"""
                remote("python3 -c " + shlex.quote(script), out / "stalled-reader.txt")
                time.sleep(.5)
                resumed = remote("cat /proc/asound/H713HDMI/pcm0c/sub0/status", out / "reader-resumed.txt")
                if "state: RUNNING" not in resumed:
                    raise RuntimeError("reader did not recover to RUNNING after XRUN")
            result["playback_returncode"] = player.wait(timeout=seconds + 2)
            result["capture_returncode"] = recorder.wait(timeout=10)
            result["signal_returncode"] = helper.wait(timeout=seconds + 75) if helper else 0
        subprocess.run(SCP + [f"root@192.168.4.1:{remote_path}", str(out / "capture.wav")], check=True, capture_output=True, timeout=15)
        result["analysis"] = analyze_wave(out / "capture.wav", seconds)
        log = (out / "capture.log").read_text().lower()
        result["expected_reader_overrun"] = stall_reader
        result["pass"] = (result["analysis"]["pass"] and (("overrun" in log) == stall_reader)
                          and all(result[k] == 0 for k in ("playback_returncode", "capture_returncode", "signal_returncode")))
        remote((PERSISTENT_SIGNAL if persistent_signal else "set -e; test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins; ") + "cat /proc/asound/H713HDMI/pcm0c/sub0/status; dmesg | tail -20", out / "after.txt")
        counters_after = read_counters(out / "counters-after.txt")
        result["counter_delta"] = {name: counters_after[name] - value
                                   for name, value in counters_before.items()}
        deltas = result["counter_delta"]
        result["pass"] = result["pass"] and deltas["period_xruns"] == 0 and all(
            deltas[name] > 0 for name in ("period_active", "period_bytes", "period_notifications"))
        if "closed" not in (out / "after.txt").read_text():
            result["pass"] = False
    except Exception as error:
        result.update({"pass": False, "error": str(error)})
    finally:
        for process in (player, recorder):
            if process is not None and process.poll() is None:
                # Remote arecord has its own duration and INT/KILL deadline.
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        if helper is not None and helper.poll() is None:
            try:
                result["signal_returncode"] = helper.wait(timeout=seconds + 75)
            except subprocess.TimeoutExpired:
                result["cleanup_error"] = "signal helper did not finish; inspect before retry"
                result["pass"] = False
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new evidence directory")
    parser.add_argument("--recorder", default="arecord", help="board recorder executable, optionally staged in /tmp")
    parser.add_argument("--stall-reader", action="store_true", help="48 kHz only: stop the reader for one second, require XRUN and successful same-open recovery")
    parser.add_argument("--persistent-signal", action="store_true",
                        help="use the running h713-hdmi-signal.service instead of the bounded SCP helper")
    parser.add_argument("--seconds", type=int, choices=range(16, 121), default=16,
                        help="capture duration per rate, 16–120 seconds (default: 16)")
    args = parser.parse_args()
    if args.stall_reader and args.seconds != 16:
        parser.error("--stall-reader requires the default 16-second capture")
    args.output.mkdir(parents=True, exist_ok=False)
    remote((PERSISTENT_SIGNAL if args.persistent_signal else "") + "set -e; test -d /sys/module/h713_hdmi_audio; "
           "test \"$(cat /sys/module/h713_hdmi_audio/parameters/graph_ready)\" = Y; "
           "if test -f /sys/module/h713_hdmi_audio/parameters/manage_dsp && "
           "test \"$(cat /sys/module/h713_hdmi_audio/parameters/manage_dsp)\" = Y; then "
           "test \"$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)\" = N; "
           "test ! -d /sys/module/h713_hdmi_dsp_probe; else "
           "test \"$(cat /sys/module/h713_hdmi_dsp_probe/parameters/stock_graph)\" = Y; "
           "test \"$(cat /sys/module/h713_hdmi_dsp_probe/parameters/graph_chain)\" = Y; fi; "
           "command -v " + shlex.quote(args.recorder) + "; cat /proc/asound/cards", args.output / "preflight.txt")
    trials = []
    rates = (48000,) if args.stall_reader else (48000, 32000, 44100)
    for index, rate in enumerate(rates, 1):
        print(f"ALSA capture test: {rate} Hz HDMI input", flush=True)
        result = run_trial(args.output / f"{index}-{rate}", rate, index, args.recorder, args.stall_reader, args.seconds,
                           args.persistent_signal)
        trials.append(result)
        print(json.dumps({"input_rate_hz": rate, "pass": result["pass"], "error": result.get("error")}), flush=True)
        if not result["pass"]:
            break
    passed = len(trials) == len(rates) and all(t["pass"] for t in trials)
    (args.output / "summary.json").write_text(json.dumps({"pass": passed, "trials": trials}, indent=2) + "\n")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
