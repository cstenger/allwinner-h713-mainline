#!/usr/bin/env python3
"""Verify source-rate changes with one fixed-format ALSA capture kept open.

The HPD/EDID window stays asserted while host playback changes 48->32->44.1
->48 kHz. Alternating channel signatures distinguish new audio from old data.
Does not load modules or initialize DSP; requires the prepared managed driver.
"""
import argparse
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('capture', HERE/'run-alsa-capture-test.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
RATES = (48000, 32000, 44100, 48000)
SECONDS = 48


def parse_status(text):
    fields = {name.strip(): value.strip() for name, value in
              (line.split(':', 1) for line in text.splitlines() if ':' in line)}
    if fields.get('state', '').strip() != 'RUNNING':
        raise RuntimeError('capture is not RUNNING: '+text)
    return {name: int(fields[name]) for name in ('owner_pid', 'hw_ptr')}


def analyze_wave(path, phases):
    with wave.open(str(path)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) != (48000, 2, 2, SECONDS*48000):
            raise RuntimeError('unexpected output format/frame count')
        checks = []
        for phase in phases:
            windows = []
            for offset in (48000, 96000):
                frame = phase['sample_frame'] + offset
                wav.setpos(frame)
                samples = np.frombuffer(wav.readframes(16384), dtype='<i2').reshape(-1, 2)
                if phase['swapped']:
                    samples = samples[:, ::-1].copy()
                item = capture.rate_test.analysis.analyze(samples.tobytes())
                item['recording_frame'] = frame
                windows.append(item)
            checks.append({'input_rate_hz': phase['input_rate_hz'], 'swapped': phase['swapped'],
                           'windows': windows, 'pass': all(w['tone_pass'] and w['capture_rate_hz'] == 48000 for w in windows)})
        wav.setpos((SECONDS-1)*48000)
        silent = not any(wav.readframes(48000))
    return {'phases': checks, 'final_second_all_zero': silent,
            'pass': len(checks) == len(RATES) and all(p['pass'] for p in checks) and silent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--recorder', default='arecord')
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    capture.remote('set -e; test "$(cat /sys/module/h713_hdmi_audio/parameters/graph_ready)" = Y; '
                   'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
                   'test "$(cat /proc/asound/H713HDMI/pcm0c/sub0/status)" = closed; '
                   'test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins', out/'preflight.txt')
    helper = reader = player = None
    result = {'pass': False, 'phases': []}
    remote_path = '/tmp/h713-alsa-rate-transition.wav'
    logs = []
    try:
        before = capture.read_counters(out/'counters-before.txt')
        log = (out/'signal.log').open('w'); logs.append(log)
        helper = subprocess.Popen([sys.executable, str(HERE/'run-detection-trial.py'), '--seconds', '70', '--stock-io'], stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+10
        while True:
            if helper.poll() is not None:
                raise RuntimeError('signal helper ended before audio ELD')
            try:
                card, device, eld = capture.rate_test.find_pcm()
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('audio ELD timeout')
                time.sleep(.2)
        (out/'eld.txt').write_text(eld.read_text())
        log = (out/'capture.log').open('w'); logs.append(log)
        reader = subprocess.Popen(capture.SSH + [
            'timeout -k 3s -s INT 56s '+shlex.quote(args.recorder)+
            ' -v -D hw:H713HDMI,0 -t wav -f S16_LE -r 48000 -c 2 '
            '--period-size=256 --buffer-size=16384 -d 48 '+remote_path], stdout=log, stderr=subprocess.STDOUT)
        time.sleep(.7)
        initial = parse_status(capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status', out/'capture-start.txt'))
        for index, rate in enumerate(RATES):
            if reader.poll() is not None or helper.poll() is not None:
                raise RuntimeError('capture or signal helper ended before transition')
            t = np.arange(8*rate)/rate
            swapped = bool(index % 2)
            frequencies = (2000, 1000) if swapped else (1000, 2000)
            samples = np.column_stack([6500*np.sin(2*np.pi*f*t) for f in frequencies]).astype('<i2')
            path = out/f'tone-{index}-{rate}.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(rate)
                wav.writeframes(samples.tobytes())
            log = (out/f'playback-{index}.log').open('w'); logs.append(log)
            player = subprocess.Popen(['aplay', '--disable-resample', '-v', '-D', f'hw:{card},{device}', str(path)], stdout=log, stderr=subprocess.STDOUT)
            time.sleep(1)
            params = Path(f'/proc/asound/card{card}/pcm{device}p/sub0/hw_params').read_text()
            capture.rate_test.check_hw_params(params, rate)
            (out/f'host-hw-params-{index}.txt').write_text(params)
            status = parse_status(capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status; '
                'cat /proc/asound/H713HDMI/pcm0c/sub0/hw_params', out/f'capture-phase-{index}.txt'))
            if status['owner_pid'] != initial['owner_pid']:
                raise RuntimeError('capture owner changed during source-rate transition')
            capture.rate_test.check_hw_params((out/f'capture-phase-{index}.txt').read_text(), 48000)
            phase = {'input_rate_hz': rate, 'swapped': swapped, 'sample_frame': status['hw_ptr'], 'owner_pid': status['owner_pid']}
            result['phases'].append(phase)
            if player.wait(timeout=10) != 0:
                raise RuntimeError('source playback failed')
            gap = parse_status(capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status', out/f'capture-gap-{index}.txt'))
            if gap['owner_pid'] != initial['owner_pid']:
                raise RuntimeError('capture owner changed between source formats')
            print(json.dumps({'phase': index, 'input_rate_hz': rate, 'same_owner_pid': initial['owner_pid']}), flush=True)
            time.sleep(.5)
        result['capture_returncode'] = reader.wait(timeout=20)
        result['signal_returncode'] = helper.wait(timeout=135)
        if result['capture_returncode'] != 0 or result['signal_returncode'] != 0:
            raise RuntimeError('recording or signal helper failed')
        subprocess.run(capture.SCP+[f'root@192.168.4.1:{remote_path}', str(out/'capture.wav')], check=True, capture_output=True, timeout=15)
        result['analysis'] = analyze_wave(out/'capture.wav', result['phases'])
        after = capture.read_counters(out/'counters-after.txt')
        result['counter_delta'] = {k: after[k]-v for k,v in before.items()}
        capture.remote('set -e; test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins; '
                       'cat /proc/asound/H713HDMI/pcm0c/sub0/status; '
                       'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N', out/'after.txt')
        result['pass'] = (result['analysis']['pass'] and result['counter_delta']['period_xruns'] == 0
                          and all(result['counter_delta'][k] > 0 for k in ('period_active', 'period_bytes', 'period_notifications'))
                          and (out/'after.txt').read_text().strip() == 'closed'
                          and 'overrun' not in (out/'capture.log').read_text().lower())
    except Exception as error:
        result['error'] = str(error)
    finally:
        for process in (player, reader):
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)
        if helper is not None and helper.poll() is None:
            try: helper.wait(timeout=135)
            except subprocess.TimeoutExpired:
                result['cleanup_error'] = 'signal helper did not finish; inspect retained holds'
                result['pass'] = False
        for log in logs: log.close()
        try:
            deadline = time.monotonic()+60
            while True:
                state = capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status', out/'final-status.txt')
                if state.strip() == 'closed': break
                if time.monotonic() >= deadline: raise RuntimeError('remote reader did not close')
                time.sleep(1)
        except Exception as error:
            result.update({'pass': False, 'cleanup_error': str(error)})
        lines = (out/'signal.log').read_text().splitlines() if (out/'signal.log').exists() else []
        if lines and lines[0].startswith('Logs: '):
            src = Path(lines[0].removeprefix('Logs: '))
            if src.exists(): shutil.copytree(src, out/'signal-evidence')
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'pass': result['pass'], 'error': result.get('error')}), flush=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
