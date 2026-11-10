#!/usr/bin/env python3
"""Read-only before/after state for the approved guard synchronization."""
from pathlib import Path
import hashlib
import json
import stat
import subprocess

paths = set()
for directory in ('/usr/lib/h713-hdmi', '/usr/lib/h713-hdmi-health',
                  '/usr/lib/h713-hdmi-video', '/usr/lib/h713-hdmi-speaker'):
    paths.update(p for p in Path(directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
paths.update(Path(p) for p in (
    '/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard',
    '/usr/lib/systemd/system-shutdown/h713-off',
    '/etc/default/h713-hdmi-speaker',
    '/var/lib/h713-hdmi-startup/kernel.sha256',
    '/usr/local/bin/h713-play', '/usr/local/bin/gst-plane-play'))
paths.update(Path('/etc/systemd/system').glob('h713-hdmi-*.service'))
files = {}
for p in sorted(paths):
    s = p.stat()
    files[str(p)] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                     'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid, 'gid': s.st_gid,
                     'bytes': s.st_size}
checks = []
for p in paths:
    if p.name != 'SHA256SUMS':
        continue
    entries = []
    for line in p.read_text().splitlines():
        expected, name = line.split('  ', 1)
        actual = files[str(p.parent / name)]['sha256']
        entries.append({'path': str(p.parent/name), 'expected': expected, 'actual': actual,
                        'matches': expected == actual})
    checks.append({'path': str(p), 'checks': entries, 'all_match': all(e['matches'] for e in entries)})
services = ['h713-hdmi-'+name+'.service' for name in ('capture','signal','speaker','ring','video','health-ack')]
p = subprocess.run(['systemctl','show',*services,'-p','Id','-p','ActiveState','-p','SubState',
                    '-p','NRestarts','-p','ExecMainStartTimestampMonotonic'],
                   text=True,capture_output=True,check=True,timeout=12)
states = {}
for block in p.stdout.strip().split('\n\n'):
    fields = dict(line.split('=',1) for line in block.splitlines() if '=' in line)
    states[fields['Id']] = fields
runtime = {}
for name in ('/sys/module/h713_hdmi_audio/parameters/period_xruns',
             '/sys/module/h713_hdmi_v4l2/parameters/frames_rejected',
             '/sys/module/h713_hdmi_v4l2/parameters/allow_480p',
             '/sys/devices/platform/h713-hdmi-ring/signal'):
    try:runtime[name] = Path(name).read_text().strip()
    except OSError as error:runtime[name] = {'error': str(error)}
print(json.dumps({'model': Path('/proc/device-tree/model').read_text().strip('\0\n'),
                  'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  'files': files, 'bundle_checks': checks, 'services': states,
                  'runtime': runtime},indent=2))
