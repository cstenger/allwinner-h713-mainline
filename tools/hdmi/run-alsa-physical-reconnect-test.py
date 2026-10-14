#!/usr/bin/env python3
"""Keep capture open across an operator-controlled physical HDMI unplug/replug.

Watch stdout for unplug/reconnect requests; unplug has a 70-second deadline and return has 20 seconds.
HPD stays asserted for one bounded 150-second window. No module/DSP setup.
"""
import argparse
import importlib.util
import json
import shutil
import shlex
import subprocess
import sys
import time
import wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('transition', HERE/'run-alsa-rate-transition-test.py')
transition = importlib.util.module_from_spec(spec); spec.loader.exec_module(transition)
capture = transition.capture
spec = importlib.util.spec_from_file_location('reconnect', HERE/'run-alsa-reconnect-test.py')
reconnect = importlib.util.module_from_spec(spec); spec.loader.exec_module(reconnect)
CONNECTOR = Path('/sys/class/drm/card1-HDMI-A-1/status')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--recorder', default='arecord')
    args = parser.parse_args()
    out = args.output; out.mkdir(parents=True, exist_ok=False)
    capture.remote('set -e; test "$(cat /sys/module/h713_hdmi_audio/parameters/graph_ready)" = Y; '
                   'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
                   'test "$(cat /proc/asound/H713HDMI/pcm0c/sub0/status)" = closed', out/'preflight.txt')
    reader = helper = player = None
    logs = []; result = {'pass': False}
    remote_path = '/tmp/h713-alsa-physical-reconnect.wav'
    def status(name):
        return transition.parse_status(capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status', out/name))
    def wait_eld(seconds):
        deadline = time.monotonic()+seconds
        while True:
            if helper.poll() is not None: raise RuntimeError('signal helper ended before ELD')
            try: return capture.rate_test.find_pcm()
            except RuntimeError:
                if time.monotonic() >= deadline: raise RuntimeError('audio ELD timeout')
                time.sleep(.2)
    try:
        before = capture.read_counters(out/'counters-before.txt')
        log = (out/'signal.log').open('w'); logs.append(log)
        helper = subprocess.Popen([sys.executable, str(HERE/'run-detection-trial.py'), '--seconds', '150', '--stock-io'], stdout=log, stderr=subprocess.STDOUT)
        card, device, eld = wait_eld(10)
        (out/'eld-before.txt').write_text(eld.read_text())
        log = (out/'capture.log').open('w'); logs.append(log)
        reader = subprocess.Popen(capture.SSH+['timeout -k 3s -s INT 128s '+shlex.quote(args.recorder)+
            ' -v -D hw:H713HDMI,0 -t wav -f S16_LE -r 48000 -c 2 --period-size=256 --buffer-size=16384 -d 120 '+remote_path], stdout=log, stderr=subprocess.STDOUT)
        time.sleep(.7)
        owner = status('capture-start.txt')['owner_pid']
        for phase in range(2):
            t = np.arange(6*48000)/48000
            frequencies = (1000,2000) if phase == 0 else (2000,1000)
            data = np.column_stack([6500*np.sin(2*np.pi*f*t) for f in frequencies]).astype('<i2')
            tone = out/f'tone-{phase}.wav'
            with wave.open(str(tone),'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(48000); wav.writeframes(data.tobytes())
            log = (out/f'playback-{phase}.log').open('w'); logs.append(log)
            player = subprocess.Popen(['aplay','--disable-resample','-v','-D',f'hw:{card},{device}',str(tone)], stdout=log, stderr=subprocess.STDOUT)
            time.sleep(1)
            params = Path(f'/proc/asound/card{card}/pcm{device}p/sub0/hw_params').read_text()
            capture.rate_test.check_hw_params(params,48000)
            (out/f'host-hw-params-{phase}.txt').write_text(params)
            if status(f'capture-active-{phase}.txt')['owner_pid'] != owner: raise RuntimeError('capture owner changed')
            if player.wait(timeout=9) != 0: raise RuntimeError('playback failed')
            if phase == 0:
                print(json.dumps({'event':'unplug_now','deadline_seconds':70}),flush=True)
                deadline = time.monotonic()+70
                while CONNECTOR.read_text().strip() != 'disconnected':
                    if reader.poll() is not None: raise RuntimeError('capture ended before unplug')
                    if time.monotonic() >= deadline: raise RuntimeError('physical unplug deadline expired')
                    time.sleep(.2)
                time.sleep(2)
                lost = status('capture-cable-removed.txt')
                if lost['owner_pid'] != owner: raise RuntimeError('capture owner changed during loss')
                result['physical_disconnect_observed'] = True
                print(json.dumps({'event':'reconnect_now','deadline_seconds':20}),flush=True)
                returned_card, returned_device, eld = wait_eld(20)
                if (returned_card,returned_device) != (card,device): raise RuntimeError('source PCM identity changed')
                (out/'eld-returned.txt').write_text(eld.read_text())
                result['physical_return_observed'] = True
        result['same_owner_pid'] = owner
        result['capture_returncode'] = reader.wait(timeout=120)
        result['signal_returncode'] = helper.wait(timeout=215)
        if result['capture_returncode'] != 0 or result['signal_returncode'] != 0: raise RuntimeError('capture or signal helper failed')
        subprocess.run(capture.SCP+[f'root@192.168.4.1:{remote_path}',str(out/'capture.wav')],check=True,capture_output=True,timeout=20)
        with wave.open(str(out/'capture.wav')) as wav:
            if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getnframes()) != (48000,2,2,120*48000): raise RuntimeError('unexpected output format or frames')
            data = np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').reshape(-1,2)
        result.update(reconnect.classify_recording(data))
        result['final_second_all_zero'] = not np.any(data[-48000:])
        after = capture.read_counters(out/'counters-after.txt')
        result['counter_delta'] = {k:after[k]-v for k,v in before.items()}
        capture.remote('set -e; test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins; '
                       'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
                       'cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/'after.txt')
        result['pass'] = (result['fresh_audio_verified'] and result['final_second_all_zero']
                          and result['counter_delta']['period_xruns'] == 0
                          and all(result['counter_delta'][k] > 0 for k in ('period_active','period_bytes','period_notifications'))
                          and (out/'after.txt').read_text().strip() == 'closed'
                          and 'overrun' not in (out/'capture.log').read_text().lower())
    except Exception as error:
        result['error'] = str(error)
    finally:
        for process in (player,reader):
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        if helper is not None and helper.poll() is None:
            try: helper.wait(timeout=215)
            except subprocess.TimeoutExpired: result.update({'pass':False,'cleanup_error':'helper did not finish; inspect retained holds'})
        for log in logs: log.close()
        try:
            deadline = time.monotonic()+130
            while True:
                state = capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/'final-status.txt')
                if state.strip() == 'closed': break
                if time.monotonic() >= deadline: raise RuntimeError('remote reader did not close')
                time.sleep(1)
        except Exception as error: result.update({'pass':False,'cleanup_error':str(error)})
        lines = (out/'signal.log').read_text().splitlines() if (out/'signal.log').exists() else []
        if lines and lines[0].startswith('Logs: '):
            src=Path(lines[0].removeprefix('Logs: '))
            if src.exists(): shutil.copytree(src,out/'signal-evidence')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':result['pass'],'error':result.get('error')}),flush=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
