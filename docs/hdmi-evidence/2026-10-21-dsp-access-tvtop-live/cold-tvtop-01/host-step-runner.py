#!/usr/bin/env python3
"""Run ONE extension helper action on the board and verify it. No loop, no retry.

usage: ext_one.py load
       ext_one.py step N NAME [STAGE_ACK]
       ext_one.py snapshot N        (N = completed cursor at the boundary)
Exit 0 only when the helper acknowledged and the UART carries the markers.
"""
import json, subprocess, sys, time
from pathlib import Path

BASE = Path('/home/chris/Projects/h713/build/hdmi-dsp-access-tvtop-2026-10-21/cold-tvtop-01')
BOOT = '046a1262-cc72-4d5e-b505-f174b90eccb6'
BUNDLE = '/root/hdmi-dsp-access-tvtop-2026-10-21'
SSH = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@192.168.4.1']

action = sys.argv[1]
cmd = ['python3', BUNDLE + '/dsp-access-audit.py', action, '--bundle', BUNDLE, '--expected-boot', BOOT]
markers = []
if action == 'step':
    n, name = int(sys.argv[2]), sys.argv[3]
    cmd += ['--expected-step', str(n), '--operation', name]
    if len(sys.argv) > 4:cmd += ['--stage-ack', sys.argv[4]]
    out = BASE / f'step-{n:02d}.txt'
    markers = [f'h713-dsp-access-audit: {t} step={n} operation={name}' for t in ('BEGIN', 'DONE')]
elif action == 'load':
    n, out = 0, BASE / 'load.txt'
    markers = ['h713-dsp-access-audit: INIT software validation only; no MMIO',
               'h713-dsp-access-audit: INIT DONE completed=0 extension=1; waiting for one explicit step']
elif action == 'snapshot':
    n = int(sys.argv[2])
    out = BASE / f'snapshot-after-{n:02d}.txt'
else:
    sys.exit('load, step or snapshot only')
if out.exists():
    sys.exit(f'{out} exists: this action was already attempted; no retry')

uart = BASE / 'bench-uart.log'
before = uart.read_text(errors='replace')
with out.open('x') as stream:
    stream.write(json.dumps({'host_event': 'sending', 'argv': cmd, 'host_time': time.time()}) + '\n')
    stream.flush()
    try:
        r = subprocess.run(SSH + [' '.join(cmd)], stdout=stream, stderr=subprocess.STDOUT, timeout=120)
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
kernel = ack.get('kernel', ack) if ack else None
if kernel and (kernel['completed'] != n or kernel['attempted'] != n or kernel['failed'] != 'N'
               or kernel['released'] != 'N'):
    problems.append(f'unexpected ack {kernel}')
for marker in markers:
    if new.count(marker) != 1: problems.append(f'UART marker missing/duplicated: {marker}')
for bad in ('FAIL', 'Internal error', 'SError', 'Unable to handle', 'Call trace', 'rcu:', 'watchdog', 'BUG'):
    if bad in new: problems.append(f'UART contains {bad!r}')
print('UART:', new.strip() or '(nothing new)')
if problems:
    print('STOP:', '; '.join(problems)); sys.exit(1)
if action == 'snapshot':
    print(f'PASS snapshot at {n}: stage {ack["stage_complete"]} complete')
    for path, body in ack['snapshots'].items():
        (BASE / f'snapshot-after-{n:02d}-{Path(path).name}.txt').write_text(body)
else:
    op = ' OP-DONE' if f'OP-DONE step={n}\n' in new or new.rstrip().endswith(f'OP-DONE step={n}') else ''
    extra = {k: kernel[k] for k in ('tv_words', 'tvcap_reset_before', 'audiotop_ctl', 'audiotop_cfg', 'tvfe_ctl', 'dsp_status', 'lock_peer', 'lock_own', 'tvtop_cold', 'tvtop_set') if k in kernel}
    print(f'PASS {action} n={n} value=0x{kernel["last_value"]:08x} next={kernel["next_operation"]}{op} {extra or ""}')
