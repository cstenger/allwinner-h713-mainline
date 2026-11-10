#!/usr/bin/env python3
"""Bounded rate sweep using the already prepared, proven graph-chain DMA path."""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("analysis", HERE / "audio-rate-analysis.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
       "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=1", "root@192.168.4.1"]
CAPTURE = "/sys/devices/h713-hdmi-audbrg-dma/capture"


def make_wave(path, rate, tone_seconds=10):
    t = np.arange(rate * tone_seconds) / rate
    tone = np.column_stack([np.rint(6500 * np.sin(2*np.pi*f*t)) for f in (1000, 2000)])
    samples = np.vstack([tone, np.zeros((rate * 4, 2))]).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(samples.tobytes())


def remote(command, output):
    result = subprocess.run(SSH + [command], capture_output=True, timeout=8)
    output.write_bytes(result.stdout)
    output.with_suffix(output.suffix + ".stderr").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(f"remote command failed ({result.returncode}); see {output}")
    return result.stdout


def find_pcm():
    # Use the same HDA ELD group mapping as the successful capture recipe.
    matches = []
    for path in sorted(Path("/proc/asound").glob("card*/eld#*")):
        fields = dict(line.split(None, 1) for line in path.read_text().splitlines()
                      if len(line.split(None, 1)) == 2)
        if any(fields.get(k) != v for k, v in
               (("monitor_present", "1"), ("eld_valid", "1"), ("monitor_name", "H713 HDMI IN"))):
            continue
        group = int(path.name.rsplit(".", 1)[1]) // 4
        devices = sorted(int(p.name[3:-1]) for p in path.parent.glob("pcm*p"))
        if group < len(devices):
            matches.append((int(path.parent.name[4:]), devices[group], path))
    if len(matches) != 1:
        raise RuntimeError("expected exactly one valid H713 HDMI IN ELD")
    return matches[0]


def check_hw_params(text, rate):
    for name, value in (("format", "S16_LE"), ("channels", "2"), ("rate", str(rate))):
        if not re.search(rf"^{name}: {value}(?:\s|$)", text, re.M):
            raise RuntimeError(f"host hardware did not negotiate {name}={value}")


def parse_timing(data):
    lines = data.decode().splitlines()
    uptime = float(lines[0].split()[0])
    rows = [line for line in lines if line.rstrip().endswith("h713-hdmi-audbrg-probe")]
    if len(rows) != 1:
        raise RuntimeError("expected exactly one bridge IRQ counter")
    counters = []
    for word in rows[0].split(":", 1)[1].split():
        if not word.isdigit():
            break
        counters.append(int(word))
    if not counters:
        raise RuntimeError("bridge IRQ counters missing")
    return {"uptime_seconds": uptime, "bridge_irqs": sum(counters)}


def wait_until(start, seconds, player, trial):
    while time.monotonic() < start + seconds:
        if player.poll() is not None or trial.poll() is not None:
            raise RuntimeError("playback or signal window ended early")
        time.sleep(.05)


def run_rate(out, rate):
    out.mkdir()
    make_wave(out / "tone.wav", rate)
    trial = player = None
    result = {"input_rate_hz": rate, "tone_snapshots": []}
    try:
        with (out / "signal.log").open("w") as slog, (out / "playback.log").open("w") as plog:
            trial = subprocess.Popen([sys.executable, str(HERE / "run-detection-trial.py"),
                                      "--seconds", "30", "--stock-io"], stdout=slog, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 12
            while True:
                if trial.poll() is not None:
                    raise RuntimeError("signal helper ended before ELD acquisition")
                try:
                    card, device, eld = find_pcm()
                    break
                except RuntimeError:
                    if time.monotonic() > deadline:
                        raise RuntimeError("ELD acquisition timed out; check HDMI1 cable")
                    time.sleep(.2)
            (out / "eld.txt").write_text(eld.read_text())
            result["pcm"] = f"hw:{card},{device}"
            start = time.monotonic()
            player = subprocess.Popen(["aplay", "--disable-resample", "-v", "-D", result["pcm"],
                                       str(out / "tone.wav")], stdout=plog, stderr=subprocess.STDOUT)
            params = Path(f"/proc/asound/card{card}/pcm{device}p/sub0/hw_params")
            for _ in range(40):
                if player.poll() is not None:
                    raise RuntimeError("aplay exited before hardware negotiation")
                text = params.read_text()
                if "rate:" in text:
                    break
                time.sleep(.05)
            else:
                raise RuntimeError("host hardware parameters did not become available")
            (out / "hw-params.txt").write_text(text)
            check_hw_params(text, rate)
            for index, seconds in enumerate((2, 4, 6), 1):
                wait_until(start, seconds, player, trial)
                timing = parse_timing(remote("cat /proc/uptime /proc/interrupts", out / f"timing-{index}.txt"))
                before = time.monotonic() - start
                data = remote(f"cat {CAPTURE}", out / f"tone-{index}.bin")
                after = time.monotonic() - start
                if before < 1 or after > 9 or player.poll() is not None or trial.poll() is not None:
                    raise RuntimeError("snapshot was outside the settled tone window")
                item = analysis.analyze(data)
                item["read_window_seconds"] = [before, after]
                item["timing"] = timing
                result["tone_snapshots"].append(item)
            # Send digital silence while the HDMI PCM remains open, so stale ring
            # contents cannot be mistaken for a successful post-tone control.
            wait_until(start, 12, player, trial)
            data = remote(f"cat {CAPTURE}", out / "silence.bin")
            if time.monotonic() - start > 13.5 or player.poll() is not None or trial.poll() is not None:
                raise RuntimeError("silence snapshot was outside the active PCM window")
            result["silence"] = analysis.analyze(data)
            result["silence_timing"] = parse_timing(remote("cat /proc/uptime /proc/interrupts", out / "timing-silence.txt"))
            result["playback_returncode"] = player.wait(timeout=6)
            result["signal_returncode"] = trial.wait(timeout=45)
            remote("test ! -d /sys/module/h713_scp_probe && test ! -d /sys/module/h713_ddc_pins",
                   out / "signal-cleanup-check.txt")
            rates = {item["capture_rate_hz"] for item in result["tone_snapshots"]}
            timings = [item["timing"] for item in result["tone_snapshots"]] + [result["silence_timing"]]
            result["bridge_irq_hz"] = [
                (b["bridge_irqs"] - a["bridge_irqs"]) / (b["uptime_seconds"] - a["uptime_seconds"])
                for a, b in zip(timings, timings[1:])]
            result["pass"] = (all(item["tone_pass"] for item in result["tone_snapshots"])
                              and len(rates) == 1 and result["silence"]["silence_pass"]
                              and rates.issubset({rate, 48000})
                              and all(value > 0 for value in result["bridge_irq_hz"])
                              and result["playback_returncode"] == result["signal_returncode"] == 0)
            result["capture_rate_hz"] = next(iter(rates)) if len(rates) == 1 else None
    except Exception as error:
        result.update({"pass": False, "error": str(error)})
    finally:
        if player is not None and player.poll() is None:
            player.terminate()
            try:
                player.wait(timeout=3)
            except subprocess.TimeoutExpired:
                player.kill()
                player.wait(timeout=3)
        # Let the bounded HPD helper complete its restoration, even on failure.
        if trial is not None and trial.poll() is None:
            try:
                result["signal_returncode"] = trial.wait(timeout=45)
            except subprocess.TimeoutExpired:
                result.update({"pass": False, "cleanup_error": "signal helper did not finish; inspect board before retry"})
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new evidence directory (must not exist)")
    parser.add_argument("--generate-only", action="store_true", help="create WAVs without board/host audio access")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.generate_only:
        for rate in analysis.RATES:
            make_wave(args.output / f"tone-{rate}.wav", rate)
        return
    results = []
    try:
        remote("set -e; test \"$(cat /sys/module/h713_hdmi_dsp_probe/parameters/graph_chain)\" = Y; "
               "test \"$(cat /sys/module/h713_hdmi_dsp_probe/parameters/stock_graph)\" = Y; "
               "test \"$(cat /sys/module/h713_hdmi_bridge_trial/parameters/audbrg_stage)\" = 4; "
               f"test -r {CAPTURE}; uname -a", args.output / "preflight.txt")
        for index, rate in enumerate((48000, 32000, 44100, 48000)):
            print(f"Testing {rate} Hz input", flush=True)
            result = run_rate(args.output / f"{index+1}-{rate}", rate)
            results.append(result)
            print(json.dumps({k: result.get(k) for k in ("input_rate_hz", "capture_rate_hz", "pass", "error")}), flush=True)
            if not result["pass"]:
                break
    except Exception as error:
        results.append({"pass": False, "error": str(error)})
    passed = len(results) == 4 and all(r["pass"] for r in results)
    if passed:
        baseline = np.mean([[c["rms"] for c in item["channels"]]
                            for item in results[0]["tone_snapshots"]], axis=0)
        for result in results:
            level = np.mean([[c["rms"] for c in item["channels"]]
                             for item in result["tone_snapshots"]], axis=0)
            result["amplitude_ratio_to_control"] = (level / baseline).tolist()
            result["level_matches_control"] = bool(np.all(abs(level / baseline - 1) < .15))
            result["pass"] = result["pass"] and result["level_matches_control"]
        for index, result in enumerate(results):
            path = args.output / f"{index+1}-{result['input_rate_hz']}" / "result.json"
            path.write_text(json.dumps(result, indent=2) + "\n")
        passed = all(r["level_matches_control"] for r in results)
    summary = {"pass": passed, "trials": results,
               "rate_measurement": "inferred from known tone cycles per DMA sample; not a continuous frame-count measurement"}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
