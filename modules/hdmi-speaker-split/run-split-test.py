#!/usr/bin/env python3
"""Audible HDMI split test, one unattended run after the operator says ready.

Timeline (seconds from start):
  0-2   500 Hz beep through the normal Linux path (control: speaker works)
  2-    silence; HDMI hot-plug window opens, wait for 1280x720 receiver lock
  lock  DAC source switched to the DSP's I2S output (dac_i2s=1)
  +2    host plays 16 s of HDMI tone (left 1 kHz, right 2 kHz)
  end   DAC back to normal, playback stopped
Requires h713-hdmi-speaker-split loaded with armed=1.
"""
import hashlib, importlib.util, json, math, struct, subprocess, sys, time, wave
from pathlib import Path

root = Path('/home/chris/Projects/h713')
current = Path('/home/chris/.codex/worktrees/hdmi-capture-current/h713')
out = root / 'docs/hdmi-evidence/2026-10-08-speaker-split'
out.mkdir(parents=True, exist_ok=True)
ssh = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@192.168.4.1']
PARAM = '/sys/module/h713_hdmi_speaker_split/parameters'
EDID = 'edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34'
log = (out / 'run.log').open('w')
t0 = time.monotonic()

def note(msg):
    line = f'{time.monotonic() - t0:6.2f} {msg}'
    print(line, flush=True)
    log.write(line + '\n'); log.flush()

def remote(cmd, timeout=10):
    p = subprocess.run(ssh + [cmd], capture_output=True, text=True, timeout=timeout)
    note(f'$ {cmd}\n{p.stdout}{p.stderr}'.rstrip())
    return p

def status(tag):
    remote(f'echo {tag}; cat {PARAM}/status')

def snap():
    p = subprocess.run(ssh + ['python3 /root/hdmi-safe-trace/read-mips-audio-cache.py'],
                       capture_output=True, text=True, timeout=8)
    p.check_returncode()
    return json.loads(p.stdout)

# Control file: 2 s 500 Hz beep then 60 s of silence, played on the board.
control = Path('/tmp/h713-split-control.wav')
with wave.open(str(control), 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
    frames = bytearray()
    for i in range(48000 * 62):
        v = round(6500 * math.sin(2 * math.pi * 500 * i / 48000)) if i < 96000 else 0
        frames += struct.pack('<hh', v, v)
    w.writeframes(frames)
subprocess.run(['scp', '-F', '/dev/null', '-o', 'BatchMode=yes', '-q', str(control),
                'root@192.168.4.1:/tmp/'], check=True)
subprocess.run(['python3', str(current / 'tools/hdmi/make-audio-test.py'),
                '/tmp/h713-split-tone.wav', '--seconds', '16'], check=True)
spec = importlib.util.spec_from_file_location('pcm', current / 'tools/hdmi/find-hdmi-audio-pcm.py')
pcm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pcm)

status('idle')
t0 = time.monotonic()
note('START: control beep')
board_play = subprocess.Popen(ssh + ['pw-play /tmp/h713-split-control.wav'],
                              stdout=log, stderr=subprocess.STDOUT)
time.sleep(2.5)
status('after-beep')
trial_log = (out / 'hpd-trial.log').open('w')
trial = subprocess.Popen(['python3', str(current / 'tools/hdmi/run-detection-trial.py'),
                          '--seconds', '30', '--stock-io', '--probe-port-cache'],
                         stdout=trial_log, stderr=subprocess.STDOUT)
player = None
rows = []
try:
    for n in range(60):
        if trial.poll() is not None:
            raise RuntimeError('HPD trial ended before lock')
        x = snap(); port = x['ports'][0]
        rows.append({'t': time.monotonic() - t0, 'phase': 'waiting', 'port': port})
        if port['state'] == 5 and (port['hactive'], port['vactive'], port['pixel_repeat']) == (1280, 720, 0):
            break
        time.sleep(0.25)
    else:
        raise RuntimeError('receiver did not lock 720p')
    note(f'LOCK state 5 1280x720')
    connectors = [p for p in Path('/sys/class/drm').glob('card*-HDMI-A-*')
                  if (p / 'edid').exists() and hashlib.sha256((p / 'edid').read_bytes()).hexdigest() == EDID]
    if len(connectors) != 1:
        raise RuntimeError('canonical EDID not active on the host')
    device = pcm.find_pcm('H713 HDMI IN')
    note(f'host pcm {device}')
    remote(f'echo 1 > {PARAM}/dac_i2s')
    note('DAC <- DSP I2S')
    status('dac-i2s-no-tone')
    time.sleep(2)
    status('dac-i2s-no-tone+2')
    note('HDMI TONE START')
    player = subprocess.Popen(['aplay', '-D', device['pcm'], '/tmp/h713-split-tone.wav'],
                              stdout=log, stderr=subprocess.STDOUT)
    for n in range(6):
        time.sleep(2)
        status(f'tone-{n}')
        x = snap(); rows.append({'t': time.monotonic() - t0, 'phase': 'tone', 'port': x['ports'][0]})
    player.wait(timeout=20)
    note(f'HDMI TONE END rc={player.returncode}')
    status('after-tone')
finally:
    if player is not None and player.poll() is None:
        player.terminate(); player.wait(timeout=5)
    remote(f'echo 0 > {PARAM}/dac_i2s')
    note('DAC back to normal')
    remote('pkill -x pw-play')
    board_play.wait(timeout=10)
    trial.wait(timeout=60); trial_log.close()
    (out / 'receiver-cache.json').write_text(json.dumps(rows, indent=2) + '\n')
    note(f'END hpd trial rc={trial.returncode}')
    log.close()
