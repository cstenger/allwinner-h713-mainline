#!/usr/bin/env python3
"""Check HDMI audio capture end to end through the production PipeWire source.

This PC plays the standard 1 kHz (left) / 2 kHz (right) tone over HDMI at each
input rate; the board records its HDMI PipeWire source (fixed 48 kHz S16
stereo) with pw-record while the speaker route keeps running, muted. Every
1-second window inside the tone must pass audio-rate-analysis (tone purity,
level, inferred 48 kHz capture rate) and a window after the tone must be
silent. The production rootfs has no arecord, which run-alsa-capture-test.py
needs.

Board access uses the production known_hosts. Restores the speaker sink's
volume and mute state in all cases. Writes RESULT.json in a new directory.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KNOWN_HOSTS = ROOT/'local/recovery/2026-11-03-production-install-03/known_hosts'
SSH = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'UserKnownHostsFile='+str(KNOWN_HOSTS), '-o', 'ConnectTimeout=5', 'root@192.168.4.1']
SCP = ['scp', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'UserKnownHostsFile='+str(KNOWN_HOSTS)]
AS_MEDIA = 'runuser -u media -- env XDG_RUNTIME_DIR=/run/user/1000 '
SOURCE = 'alsa_input._sys_devices_h713-hdmi-audio-dma_sound_card1.stereo-fallback'
SINK = '@DEFAULT_AUDIO_SINK@'
TONE_SECONDS, RECORD_SECONDS = 10, 16


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


rate_test = load('rate_test', HERE/'run-audio-rate-test.py')
analysis = load('analysis', HERE/'audio-rate-analysis.py')


def board(command, timeout=30):
    p = subprocess.run(SSH+[command], capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('board command failed: '+command+'\n'+p.stdout+p.stderr)
    return p.stdout


def analyse(path):
    with wave.open(str(path)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (48000, 2, 2):
            raise RuntimeError('unexpected recording format')
        frames = w.readframes(w.getnframes())
    second = 48000*4
    # Find the tone onset: the first second whose RMS clears the silence floor.
    def window(start):
        return frames[start:start+65536]
    onset = next((s for s in range(0, len(frames)-65536, second//4)
                  if not analysis.analyze(window(s))['silence_pass']), None)
    if onset is None:
        return {'pass': False, 'error': 'no tone found in the recording'}
    tone = [analysis.analyze(window(onset+second*k)) for k in range(1, TONE_SECONDS-2)]
    after = onset + second*(TONE_SECONDS+1)
    silence = analysis.analyze(window(after)) if after+65536 <= len(frames) else None
    ok = (all(t['tone_pass'] and t['capture_rate_hz'] == 48000 for t in tone)
          and silence is not None and silence['silence_pass'])
    return {'pass': ok, 'onset_second': onset/second, 'tone_windows': len(tone),
            'tone_fail': [i for i, t in enumerate(tone) if not (t['tone_pass'] and t['capture_rate_hz'] == 48000)],
            'tone_rms': [[round(c['rms']) for c in t['channels']] for t in tone],
            'silence_pass': bool(silence and silence['silence_pass'])}


def trial(out, rate):
    out.mkdir()
    rate_test.make_wave(out/'tone.wav', rate, tone_seconds=TONE_SECONDS)
    card, device, _ = rate_test.find_pcm()
    remote = '/tmp/h713-tone-%d.wav' % rate
    rec = subprocess.Popen(SSH+[AS_MEDIA+'timeout -s INT %ds pw-record --target %s --rate 48000 --channels 2 '
                                '--format s16 %s' % (RECORD_SECONDS, SOURCE, remote)],
                           stdout=(out/'record.log').open('w'), stderr=subprocess.STDOUT)
    time.sleep(1.5)
    play = subprocess.run(['aplay', '--disable-resample', '-D', 'hw:%d,%d' % (card, device), str(out/'tone.wav')],
                          capture_output=True, text=True, timeout=TONE_SECONDS+10)
    (out/'play.log').write_text(play.stdout+play.stderr)
    rec.wait(timeout=RECORD_SECONDS+15)
    subprocess.run(SCP+['root@192.168.4.1:'+remote, str(out/'capture.wav')], check=True,
                   capture_output=True, timeout=30)
    board('rm -f '+remote)
    result = {'input_rate_hz': rate, 'aplay_rc': play.returncode, **analyse(out/'capture.wav')}
    result['pass'] = result['pass'] and play.returncode == 0
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('output', type=Path, help='new evidence directory')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    pre = board('cat /proc/sys/kernel/random/boot_id; P=/sys/module/h713_hdmi_audio/parameters; '
                'cat $P/graph_ready $P/dsp_failed; dmesg | grep "DSP patch verified" | tail -1; '
                + AS_MEDIA+'wpctl get-volume '+SINK)
    (a.output/'preflight.txt').write_text(pre)
    lines = pre.splitlines()
    if lines[1:3] != ['Y', 'N']:
        raise SystemExit('audio driver not ready (graph_ready/dsp_failed): '+' '.join(lines[1:3]))
    volume = re.search(r'Volume: ([0-9.]+)', pre).group(1)
    muted = '[MUTED]' in pre
    results = []
    try:
        board(AS_MEDIA+'wpctl set-mute '+SINK+' 1')
        for i, rate in enumerate((48000, 32000, 44100), 1):
            print('tone check at', rate, 'Hz', flush=True)
            results.append(trial(a.output/('%d-%d' % (i, rate)), rate))
    finally:
        board(AS_MEDIA+'wpctl set-volume '+SINK+' '+volume+'; '+AS_MEDIA+'wpctl set-mute '+SINK+' '+('1' if muted else '0'))
    summary = {'boot_id': lines[0], 'pass': all(r['pass'] for r in results),
               'trials': [{k: r[k] for k in ('input_rate_hz', 'pass', 'tone_fail', 'silence_pass') if k in r}
                          for r in results]}
    (a.output/'RESULT.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
