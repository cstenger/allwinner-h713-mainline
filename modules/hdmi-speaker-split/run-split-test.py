#!/usr/bin/env python3
"""Audible HDMI split test, one unattended run after the operator says ready.

Timeline (seconds from start):
  0-2   500 Hz beep through the normal Linux path (control: speaker works)
  2-    silence; HDMI hot-plug window opens, wait for 1280x720 receiver lock
  lock  DAC source switched to the DSP's I2S output (dac_i2s=1)
  +2    host plays 16 s of HDMI tone (left 1 kHz, right 2 kHz)
  end   DAC back to normal, playback stopped
Requires h713-hdmi-speaker-split loaded with armed=1 lock_window_ready=1.
The operator must authorize this audible bench trial before running it.
"""
import argparse, hashlib, importlib.util, json, math, struct, subprocess, time, uuid, wave
from pathlib import Path

root = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output', type=Path, required=True, help='new evidence directory; existing directories are refused')
args = ap.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
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
    p.check_returncode()
    return p

def status(tag):
    remote(f'echo {tag}; cat {PARAM}/status')

def snap():
    p = subprocess.run(ssh + ['python3 /root/hdmi-safe-trace/read-mips-audio-cache.py'],
                       capture_output=True, text=True, timeout=8)
    p.check_returncode()
    return json.loads(p.stdout)

board_play = trial = player = trial_log = None
rows = []
cleanup_errors = []
dac_switched = False
remote_control = None
try:
    remote(f'test "$(cat {PARAM}/armed)" = Y && '
           f'test "$(cat {PARAM}/lock_window_ready)" = Y')
    # Control file: 2 s 500 Hz beep then 60 s of silence, played on the board.
    control = out / f'h713-split-control-{uuid.uuid4().hex}.wav'
    remote_control = '/tmp/' + control.name
    tone = out / 'tone.wav'
    with wave.open(str(control), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
        frames = bytearray()
        for i in range(48000 * 62):
            v = round(6500 * math.sin(2 * math.pi * 500 * i / 48000)) if i < 96000 else 0
            frames += struct.pack('<hh', v, v)
        w.writeframes(frames)
    subprocess.run(['scp', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-q', str(control),
                    'root@192.168.4.1:/tmp/'], check=True, timeout=30)
    subprocess.run(['python3', str(root / 'tools/hdmi/make-audio-test.py'),
                    str(tone), '--seconds', '16'], check=True)
    spec = importlib.util.spec_from_file_location('pcm', root / 'tools/hdmi/find-hdmi-audio-pcm.py')
    pcm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pcm)

    status('idle')
    t0 = time.monotonic()
    note('START: control beep')
    board_play = subprocess.Popen(ssh + [f'exec pw-play {remote_control}'],
                                  stdout=log, stderr=subprocess.STDOUT)
    time.sleep(2.5)
    if board_play.poll() is not None:
        raise RuntimeError('board control playback ended before the trial')
    status('after-beep')
    trial_log = (out / 'hpd-trial.log').open('w')
    trial = subprocess.Popen(['python3', str(root / 'tools/hdmi/run-detection-trial.py'),
                              '--seconds', '30', '--stock-io', '--probe-port-cache'],
                             stdout=trial_log, stderr=subprocess.STDOUT)
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
    if board_play.poll() is not None:
        raise RuntimeError('board playback ended before DAC switch')
    dac_switched = True
    remote(f'echo 1 > {PARAM}/dac_i2s')
    note('DAC <- DSP I2S')
    status('dac-i2s-no-tone')
    time.sleep(2)
    status('dac-i2s-no-tone+2')
    note('HDMI TONE START')
    player = subprocess.Popen(['aplay', '-D', device['pcm'], str(tone)],
                              stdout=log, stderr=subprocess.STDOUT)
    for n in range(6):
        time.sleep(2)
        if board_play.poll() is not None:
            raise RuntimeError('board playback ended during the tone')
        status(f'tone-{n}')
        x = snap(); rows.append({'t': time.monotonic() - t0, 'phase': 'tone', 'port': x['ports'][0]})
    player.wait(timeout=20)
    note(f'HDMI TONE END rc={player.returncode}')
    if player.returncode:
        raise RuntimeError('HDMI tone playback failed')
    status('after-tone')
finally:
    # Each cleanup runs even when an earlier one fails; preserve evidence.
    def cleanup(label, action):
        try:
            action()
        except Exception as exc:
            cleanup_errors.append(f'{label}: {exc}')
            note(f'CLEANUP FAILED {label}: {exc}')

    def stop(process):
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)

    cleanup('host playback', lambda: stop(player))
    if dac_switched:
        cleanup('DAC source restore', lambda: remote(f'echo 0 > {PARAM}/dac_i2s'))
    if board_play is not None:
        pattern = 'pw-play ' + remote_control.replace('.', '[.]')
        cleanup('board playback', lambda: remote(f"pkill -fx '{pattern}' || test $? -eq 1"))
        cleanup('board SSH process', lambda: stop(board_play))
    if remote_control is not None:
        cleanup('board control file', lambda: remote(f'rm -f -- {remote_control}'))
    # The trial allows 30 s plus 60 s grace and SSH teardown. Do not kill
    # its owner process while it may still be restoring HPD/DDC state.
    if trial is not None:
        cleanup('HPD trial restore', lambda: trial.wait(timeout=120))
        note(f'END hpd trial rc={trial.returncode}')
        if trial.returncode:
            cleanup_errors.append(f'HPD trial rc={trial.returncode}')
    if trial_log is not None:
        trial_log.close()
    (out / 'receiver-cache.json').write_text(json.dumps(rows, indent=2) + '\n')
    (out / 'cleanup.json').write_text(json.dumps(cleanup_errors, indent=2) + '\n')
    log.close()
if cleanup_errors:
    raise RuntimeError('Cleanup incomplete: ' + '; '.join(cleanup_errors))
