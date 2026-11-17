#!/usr/bin/env python3
"""Record the projector speaker while driving board events; flag clicks/pops.

RUNS ON THE HOST. Needs a microphone on a USB interface (default hw:2,0
input 1, the Scarlett 2i2) placed by the speaker, and ssh to the board.

    pop-capture.py run   PLAN.json OUT_DIR    record + drive events + analyse
    pop-capture.py score OUT_DIR              re-analyse a finished run

A plan is a list of steps, each {"name", "cmd", "settle"}: `cmd` runs on
the board (as root) and the step then waits `settle` seconds before the next.
"cmd": null with a settle is a quiet reference stretch.

Timing: one ssh session runs a monitor on the board. It runs each step,
logs its start/end on the board's CLOCK_MONOTONIC, and polls the external
amplifier line (PL2, "allwinner,pa" in /sys/kernel/debug/gpio) and the DAPM
Speaker widget every 2 ms, logging every change. Host<->board clock offset
is the minimum-RTT ping through the same session. The recording's start is
taken when arecord is launched (tens of ms of uncertainty; windows are wider).

Detection: a click is broadband and abrupt, the fan is stationary. Score =
peak |first difference| in each 1 ms block, divided by the median block over
the whole recording. Each step's window gets its maximum score; the quiet
reference windows say what the room alone reaches. The positive control (a
loud tone cut without a fade) must score far above the quiet reference, or the
run proves nothing.
"""
import json
import os
import subprocess
import sys
import threading
import time
import wave

import numpy as np

SSH = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes',
       '-o', 'StrictHostKeyChecking=yes',
       '-o', 'UserKnownHostsFile=' + os.path.join(
           os.path.dirname(os.path.abspath(__file__)), '..', '..', 'local',
           'recovery', '2026-11-03-production-install-03', 'known_hosts'),
       '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=3',
       '-o', 'ServerAliveCountMax=3', 'root@192.168.4.1']
DEVICE = os.environ.get('POP_DEVICE', 'hw:2,0')
MIC_CHANNEL = int(os.environ.get('POP_CHANNEL', '0'))
RATE = 48000
HP_HZ = float(os.environ.get('POP_HP_HZ', '6000'))
BASE_MS = 150
FLAG = float(os.environ.get('POP_FLAG', '3.5'))  # controls: quiet <= 2.6, clicks >= 4

MONITOR = r'''
import os, subprocess, sys, threading, time
os.environ.setdefault("PIPEWIRE_RUNTIME_DIR", "/run/user/1000")
SPK = "/sys/kernel/debug/asoc/H713 Audio Codec/dapm/Speaker"
out_lock = threading.Lock()
def emit(*f):
    with out_lock:
        sys.stdout.write(" ".join(str(x) for x in f) + "\n"); sys.stdout.flush()
def pa():
    with open("/sys/kernel/debug/gpio") as g:
        for line in g:
            if "allwinner,pa" in line:
                return "hi" if " out hi" in line else "lo"
    return "?"
def spk():
    try:
        with open(SPK) as f:
            return f.readline().split(":")[1].split()[0]
    except OSError:
        return "?"
PCM = "/proc/asound/card0/pcm0p/sub0/status"
def pcm():
    try:
        with open(PCM) as f:
            l = f.readline().split()
        return l[1] if len(l) > 1 else l[0]
    except OSError:
        return "?"
stop = False
def poll():
    last = None
    while not stop:
        cur = (pa(), spk(), pcm())
        if cur != last:
            emit("state", time.monotonic(), *cur); last = cur
        time.sleep(0.002)
threading.Thread(target=poll, daemon=True).start()
for line in sys.stdin:
    line = line.rstrip("\n")
    if line == "ping":
        emit("pong", time.monotonic())
    elif line.startswith("run "):
        name, cmd = line[4:].split(" ", 1)
        emit("start", time.monotonic(), name)
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        emit("end", time.monotonic(), name, r.returncode,
             (r.stdout + r.stderr).strip().replace("\n", " | ")[:300])
    elif line == "quit":
        break
stop = True
emit("bye", time.monotonic())
'''


def run(plan_path, out):
    plan = json.load(open(plan_path))
    os.makedirs(out, exist_ok=True)
    wav = os.path.join(out, 'mic.wav')
    log = open(os.path.join(out, 'board.log'), 'w')

    # ssh joins its arguments into one remote shell line, so ship the
    # monitor as a file rather than as `python3 -c`.
    subprocess.run(SSH + ['mkdir -p /var/tmp/pop && cat > /var/tmp/pop/monitor.py'],
                   input=MONITOR, text=True, check=True)
    mon = subprocess.Popen(SSH + ['python3', '-u', '/var/tmp/pop/monitor.py'],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           text=True, bufsize=1)
    lines = []
    cond = threading.Condition()

    def reader():
        for line in mon.stdout:
            log.write(line); log.flush()
            with cond:
                lines.append(line.split()); cond.notify_all()
    threading.Thread(target=reader, daemon=True).start()

    def send(s):
        mon.stdin.write(s + '\n'); mon.stdin.flush()

    def wait_for(pred, timeout=120):
        end = time.monotonic() + timeout
        with cond:
            while True:
                for f in lines:
                    if pred(f):
                        return f
                left = end - time.monotonic()
                if left <= 0:
                    raise TimeoutError('board monitor timed out')
                cond.wait(left)

    # Clock offset: board_mono - host_mono, from the minimum-RTT ping.
    best = None
    for _ in range(20):
        with cond:
            n = len(lines)
        t0 = time.monotonic(); send('ping')
        f = wait_for(lambda f, n=n: f[0] == 'pong' and lines.index(f) >= n)
        t1 = time.monotonic()
        rtt = t1 - t0
        if best is None or rtt < best[0]:
            best = (rtt, float(f[1]) - (t0 + t1) / 2)
        time.sleep(0.05)
    rtt, offset = best

    rec_t0 = time.monotonic()
    rec = subprocess.Popen(['arecord', '-q', '-D', DEVICE, '-c', '2',
                            '-f', 'S32_LE', '-r', str(RATE), wav])
    time.sleep(1.0)
    try:
        for i, step in enumerate(plan):
            name = '%02d-%s' % (i, step['name'])
            if step.get('cmd'):
                send('run %s %s' % (name, step['cmd']))
                wait_for(lambda f, name=name: f[0] == 'end' and f[2] == name)
            else:
                send('run %s true' % name)
                wait_for(lambda f, name=name: f[0] == 'end' and f[2] == name)
            time.sleep(step.get('settle', 2))
    finally:
        time.sleep(1.0)
        rec.terminate(); rec.wait()
        send('quit')
        try:
            mon.wait(timeout=10)
        except subprocess.TimeoutExpired:
            mon.kill()
    json.dump({'rec_host_t0': rec_t0, 'offset': offset, 'rtt': rtt,
               'plan': plan}, open(os.path.join(out, 'meta.json'), 'w'),
              indent=1)
    score(out)


def load_mic(path):
    with wave.open(path) as w:
        raw = w.readframes(w.getnframes())
        ch = w.getnchannels()
    x = np.frombuffer(raw, dtype='<i4').reshape(-1, ch)[:, MIC_CHANNEL]
    return x.astype(np.float64) / 2**31


def score(out):
    meta = json.load(open(os.path.join(out, 'meta.json')))
    x = load_mic(os.path.join(out, 'mic.wav'))
    rms_db = 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)
    # Keep only HP_HZ and up: a click is broadband, test tones and most fan
    # energy are not. Then 1 ms RMS blocks, scored against the median of the
    # preceding BASE_MS (skipping the last 5 ms), so any steady sound --
    # fan, a held tone -- scores ~1 and only onsets stand out.
    spec = np.fft.rfft(x)
    spec[:int(HP_HZ * len(x) / RATE)] = 0
    h = np.fft.irfft(spec, len(x))
    blk = RATE // 1000
    n = len(h) // blk
    env = np.sqrt((h[:n * blk].reshape(n, blk) ** 2).mean(axis=1))
    med = float(np.median(env))
    pad = np.full(BASE_MS + 5, med)
    win = np.lib.stride_tricks.sliding_window_view(
        np.concatenate([pad, env, pad]), BASE_MS)
    before = np.median(win[:n], axis=1)                 # env[i-155:i-5]
    after = np.median(win[BASE_MS + 10:BASE_MS + 10 + n], axis=1)  # env[i+5:i+155]
    # A click is short: it must stand above BOTH sides. A sound that starts
    # and keeps going (a tone, the fan spinning up) raises the after side.
    sc = env / np.maximum(np.maximum(before, after), med * 0.5)

    def to_rec(board_t):
        # board -> host -> seconds into the recording
        return board_t - meta['offset'] - meta['rec_host_t0']

    starts, ends, states = {}, {}, []
    for line in open(os.path.join(out, 'board.log')):
        f = line.split()
        if f[0] == 'start':
            starts[f[2]] = to_rec(float(f[1]))
        elif f[0] == 'end':
            ends[f[2]] = (to_rec(float(f[1])), f[3], ' '.join(f[4:]))
        elif f[0] == 'state':
            states.append((to_rec(float(f[1])), f[2], f[3], f[4] if len(f) > 4 else '-'))

    names = sorted(starts)
    rows = []
    for i, name in enumerate(names):
        a = starts[name] - 0.3
        b = starts[names[i + 1]] - 0.3 if i + 1 < len(names) else n / 1000
        ia, ib = max(0, int(a * 1000)), min(n, int(b * 1000))
        w = sc[ia:ib]
        k = int(np.argmax(w)) if len(w) else 0
        top = float(w[k]) if len(w) else 0.0
        over = int(np.sum(w > FLAG)) if len(w) else 0
        seg = x[ia * blk:ib * blk]
        lvl = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12) if len(seg) else 0
        hlv = 20 * np.log10(np.sqrt(np.mean(env[ia:ib] ** 2)) + 1e-12) if ib > ia else 0
        rows.append({'step': name, 'from_s': round(a, 3), 'to_s': round(b, 3),
                     'max_score': round(top, 1),
                     'at_s': round((ia + k) / 1000, 3),
                     'blocks_over_flag': over,
                     'rms_dbfs': round(lvl, 1), 'hiband_dbfs': round(hlv, 1),
                     'rc': ends.get(name, (0, '?', ''))[1],
                     'out': ends.get(name, (0, '', ''))[2][:120]})
    edges = [{'t_s': round(t, 3), 'pa': p, 'speaker': s, 'pcm': c} for t, p, s, c in states]
    # Top transients anywhere, with the nearest PA/Speaker edge.
    order = np.argsort(sc)[::-1]
    peaks = []
    for k in order:
        if len(peaks) >= 15:
            break
        if any(abs(k - p['ms']) < 200 for p in peaks):
            continue
        t = k / 1000
        near = min(states, key=lambda s: abs(s[0] - t)) if states else None
        peaks.append({'ms': int(k), 't_s': round(t, 3),
                      'score': round(float(sc[k]), 1),
                      'nearest_edge': None if near is None else
                      {'dt_ms': round((t - near[0]) * 1000), 'pa': near[1],
                       'speaker': near[2], 'pcm': near[3]}})
    result = {'median_block': med, 'rms_dbfs': round(rms_db, 1),
              'clock_rtt_ms': round(meta['rtt'] * 1000, 1),
              'steps': rows, 'edges': edges, 'top_peaks': peaks}
    json.dump(result, open(os.path.join(out, 'score.json'), 'w'), indent=1)
    print('room RMS %.1f dBFS, clock RTT %.1f ms' % (rms_db, meta['rtt'] * 1e3))
    print('flag threshold %.1f' % FLAG)
    print('%-28s %6s %8s %5s %7s %7s  %s' % ('step', 'max', 'at_s', 'flag', 'rms', 'hiband', 'rc'))
    for r in rows:
        print('%-28s %6.1f %8.3f %5d %7.1f %7.1f  %s %s' % (r['step'], r['max_score'],
              r['at_s'], r['blocks_over_flag'], r['rms_dbfs'], r['hiband_dbfs'],
              r['rc'], r['out'][:40]))
    print('PA/Speaker edges:')
    for e in edges:
        print('  %8.3f  pa=%s speaker=%s pcm=%s' % (e['t_s'], e['pa'], e['speaker'], e['pcm']))


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'run':
        run(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 3 and sys.argv[1] == 'score':
        score(sys.argv[2])
    else:
        sys.exit(__doc__)
