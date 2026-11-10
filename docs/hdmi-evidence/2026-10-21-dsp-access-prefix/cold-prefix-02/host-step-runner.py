#!/usr/bin/env python3
"""Run ONE prefix helper action on the board and verify it. No loop, no retry.

usage: prefix_one.py load
       prefix_one.py step N NAME
Exit 0 only when the helper acknowledged and the UART carries the markers.
"""
import json, subprocess, sys, time
from pathlib import Path

BASE = Path('/home/chris/Projects/h713/build/hdmi-dsp-access-audit-2026-10-21/cold-prefix-02')
BOOT = '36c40861-5bd6-4d21-875a-fce2fc1811b9'
BUNDLE = '/root/hdmi-dsp-access-audit-2026-10-21-v2'
SSH = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@192.168.4.1']

action = sys.argv[1]
cmd = ['python3', BUNDLE + '/dsp-access-audit.py', action, '--bundle', BUNDLE, '--expected-boot', BOOT]
if action == 'step':
    n, name = int(sys.argv[2]), sys.argv[3]
    cmd += ['--expected-step', str(n), '--operation', name]
    out = BASE / f'step-{n:02d}.txt'
    markers = [f'h713-dsp-access-audit: {t} step={n} operation={name}' for t in ('BEGIN', 'DONE')]
elif action == 'load':
    n, out = 0, BASE / 'load.txt'
    markers = ['h713-dsp-access-audit: INIT software validation only; no MMIO',
               'h713-dsp-access-audit: INIT DONE completed=0; waiting for one explicit step']
else:
    sys.exit('load or step only')
if out.exists():
    sys.exit(f'{out} exists: this action was already attempted; no retry')

uart = BASE / 'bench-uart.log'
before = uart.read_text(errors='replace')
with out.open('x') as stream:
    stream.write(json.dumps({'host_event': 'sending', 'argv': cmd, 'host_time': time.time()}) + '\n')
    stream.flush()
    try:
        r = subprocess.run(SSH + [' '.join(cmd)], stdout=stream, stderr=subprocess.STDOUT, timeout=90)
        code = r.returncode
    except subprocess.TimeoutExpired:
        code = 'timeout'
    stream.write(json.dumps({'host_event': 'returned', 'code': code, 'host_time': time.time()}) + '\n')
time.sleep(1.5)
new = uart.read_text(errors='replace')[len(before):]

text = out.read_text()
ack = None
if code == 0:
    start = text.rfind('{\n  "event": "acknowledged"')
    try:
        ack = json.JSONDecoder().raw_decode(text, start)[0]['result'] if start >= 0 else None
    except Exception:
        ack = None
problems = []
if code != 0: problems.append(f'helper exit {code}')
if ack is None: problems.append('no acknowledgment')
elif ack['completed'] != n or ack['attempted'] != n or ack['failed'] != 'N' or ack['released'] != 'N':
    problems.append(f'unexpected ack {ack}')
for marker in markers:
    if new.count(marker) != 1: problems.append(f'UART marker missing/duplicated: {marker}')
for bad in ('FAIL', 'Internal error', 'SError', 'Unable to handle', 'Call trace', 'rcu:', 'watchdog'):
    if bad in new: problems.append(f'UART contains {bad!r}')
print('UART:', new.strip() or '(nothing new)')
if problems:
    print('STOP:', '; '.join(problems)); sys.exit(1)
print(f'PASS {action} n={n} value=0x{ack["last_value"]:08x} next={ack["next_operation"]}')
