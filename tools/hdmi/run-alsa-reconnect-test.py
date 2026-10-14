#!/usr/bin/env python3
"""Bounded HPD/source loss and return with the same ALSA capture open.

Requires the verified receiver/DSP graph, like run-alsa-capture-test.py.
Uses two saved/restored signal windows, not physical cable removal.
"""
import argparse
import importlib.util
import json
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


def classify_recording(data):
    normal, swapped = [], []
    for offset in range(0, len(data)-16384+1, 16384):
        block = data[offset:offset+16384]
        for samples, matches in ((block, normal), (block[:, ::-1].copy(), swapped)):
            analysis = capture.rate_test.analysis.analyze(samples.tobytes())
            if analysis['tone_pass'] and analysis['capture_rate_hz'] == 48000:
                matches.append(offset/48000)
    return {'normal_tone_windows_s': normal,
            'returned_swapped_tone_windows_s': swapped,
            'fresh_audio_verified': bool(normal and swapped and max(normal) < min(swapped))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--recorder', default='arecord')
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    capture.remote('set -e; test "$(cat /sys/module/h713_hdmi_audio/parameters/graph_ready)" = Y; '
                   'if test -f /sys/module/h713_hdmi_audio/parameters/manage_dsp && '
                   'test "$(cat /sys/module/h713_hdmi_audio/parameters/manage_dsp)" = Y; then '
                   'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
                   'test ! -d /sys/module/h713_hdmi_dsp_probe; else '
                   'test "$(cat /sys/module/h713_hdmi_dsp_probe/parameters/stock_graph)" = Y; fi; '
                   'test "$(cat /proc/asound/H713HDMI/pcm0c/sub0/status)" = closed; '
                   'cat /proc/asound/H713HDMI/pcm0c/sub0/status', out/'preflight.txt')
    reader = helper = player = None
    logs = []
    result = {'pass': False}
    remote_wave = '/tmp/h713-alsa-reconnect.wav'
    try:
        owners = []
        for phase in range(2):
            with (out/f'signal-{phase}.log').open('w') as signal_log:
                helper = subprocess.Popen([sys.executable, str(HERE/'run-detection-trial.py'), '--seconds', '12', '--stock-io'], stdout=signal_log, stderr=subprocess.STDOUT)
                deadline = time.monotonic()+10
                while True:
                    if helper.poll() is not None:
                        raise RuntimeError('signal helper ended before ELD')
                    try:
                        card, device, eld = capture.rate_test.find_pcm()
                        break
                    except RuntimeError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('ELD timeout')
                        time.sleep(.2)
                (out/f'eld-{phase}.txt').write_text(eld.read_text())
                if reader is None:
                    log = (out/'capture.log').open('w'); logs.append(log)
                    reader = subprocess.Popen(capture.SSH + ['timeout -s INT 38s '+shlex.quote(args.recorder)+
                        ' -v -D hw:H713HDMI,0 -t wav -f S16_LE -r 48000 -c 2 --period-size=256 --buffer-size=16384 '+remote_wave], stdout=log, stderr=subprocess.STDOUT)
                # Fresh audio has swapped channels after reconnection.
                t = np.arange(5*48000)/48000
                frequencies = (1000,2000) if phase == 0 else (2000,1000)
                samples = np.column_stack([6500*np.sin(2*np.pi*f*t) for f in frequencies]).astype('<i2')
                path = out/f'tone-{phase}.wav'
                with wave.open(str(path),'wb') as wav:
                    wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(48000)
                    wav.writeframes(samples.tobytes())
                log = (out/f'playback-{phase}.log').open('w'); logs.append(log)
                player = subprocess.Popen(['aplay','--disable-resample','-v','-D',f'hw:{card},{device}',str(path)], stdout=log, stderr=subprocess.STDOUT)
                time.sleep(1)
                params = Path(f'/proc/asound/card{card}/pcm{device}p/sub0/hw_params').read_text()
                capture.rate_test.check_hw_params(params,48000)
                (out/f'host-hw-params-{phase}.txt').write_text(params)
                status = capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/f'capture-active-{phase}.txt')
                assert 'state: RUNNING' in status, status
                owners.append(next(line.split(':',1)[1].strip() for line in status.splitlines() if line.startswith('owner_pid')))
                assert player.wait(timeout=8) == 0
                assert helper.wait(timeout=20) == 0
            assert Path('/sys/class/drm/card1-HDMI-A-1/status').read_text().strip() == 'disconnected'
            capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/f'capture-disconnected-{phase}.txt')
            if phase == 0:
                assert reader.poll() is None, 'capture exited on signal loss'
                time.sleep(3)
        assert owners[0] == owners[1], 'capture owner changed'
        result['capture_returncode'] = reader.wait(timeout=15)
        assert result['capture_returncode'] in (0,124), 'unexpected capture failure'
        subprocess.run(capture.SCP+[f'root@192.168.4.1:{remote_wave}',str(out/'capture.wav')],check=True,capture_output=True,timeout=15)
        with wave.open(str(out/'capture.wav'),'rb') as wav:
            assert (wav.getframerate(),wav.getnchannels(),wav.getsampwidth()) == (48000,2,2)
            data = np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').reshape(-1,2)
        result.update(classify_recording(data), same_owner_pid=owners[0], frames=len(data))
        assert result['fresh_audio_verified'], 'fresh post-reconnect audio not verified'
        capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status; dmesg | tail -25',out/'after.txt')
        assert (out/'after.txt').read_text().startswith('closed'), 'capture not closed'
        result['pass'] = True
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
            try: helper.wait(timeout=30)
            except subprocess.TimeoutExpired: result['cleanup_error'] = 'signal helper did not finish'
        for log in logs: log.close()
        # SSH termination alone does not prove the remote reader has exited.
        # Its independent 38-second timeout is the final bound on error paths.
        try:
            deadline = time.monotonic()+40
            while True:
                status = capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status', out/'final-status.txt')
                if status.strip() == 'closed':
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('remote capture did not close')
                time.sleep(1)
        except Exception as error:
            result['cleanup_error'] = str(error)
            result['pass'] = False
        for path in out.glob('signal-*.log'):
            first = path.read_text().splitlines()[0]
            if first.startswith('Logs: '):
                src = Path(first.removeprefix('Logs: '))
                if src.exists(): shutil.copytree(src,out/(path.stem+'-evidence'))
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
