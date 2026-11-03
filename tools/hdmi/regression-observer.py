#!/usr/bin/env python3
"""Observe HDMI through source interruptions; no hardware control or service restart."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time

UNITS = ['h713-hdmi-'+name+'.service' for name in
         ('capture', 'signal', 'ring', 'speaker', 'video', 'health-ack', 'readvertise')]
ERRORS = {
    'rejected': '/sys/module/h713_hdmi_v4l2/parameters/frames_rejected',
    'xruns': '/sys/module/h713_hdmi_audio/parameters/period_xruns',
    'bad_guard': '/sys/module/h713_hdmi_v4l2/parameters/sig_bad_guard',
    'afbd_invalid': '/sys/module/h713_hdmi_v4l2/parameters/afbd_invalid',
}


def read(path):
    return Path(path).read_text().strip()


def snapshot():
    boot = read('/proc/sys/kernel/random/boot_id')
    raw = subprocess.run(['systemctl', 'show', *UNITS, '-p', 'Id', '-p', 'ActiveState',
                          '-p', 'NRestarts', '-p', 'ExecMainStartTimestampMonotonic'],
                         check=True, capture_output=True, text=True, timeout=10).stdout
    services = {}
    for record in raw.strip().split('\n\n'):
        item = dict(line.split('=', 1) for line in record.splitlines() if '=' in line)
        services[item.pop('Id')] = item
    result = dict(boot_id=boot, uptime=float(read('/proc/uptime').split()[0]),
                  signal=read('/sys/devices/platform/h713-hdmi-ring/signal'), services=services,
                  errors={key: int(read(path)) for key, path in ERRORS.items()},
                  frames=int(read('/sys/module/h713_hdmi_v4l2/parameters/frames_produced')),
                  readvertised=int(read('/sys/module/h713_hdmi_signal/parameters/readvertised')),
                  owner_ready=read('/sys/module/h713_hdmi_signal/parameters/ready'),
                  owner_failed=read('/sys/module/h713_hdmi_signal/parameters/failed'))
    if read('/proc/sys/kernel/random/boot_id') != boot:
        raise ValueError('board reboot during snapshot')
    return result


def healthy(samples):
    if not samples:
        raise ValueError('no samples')
    baseline = samples[0]
    previous = None
    for row in samples:
        if row.get('boot_id') != baseline['boot_id']:
            raise ValueError('board boot changed')
        if row.get('errors') != {key: 0 for key in ERRORS}:
            raise ValueError('capture error or missing error evidence')
        if row.get('owner_ready') != 'Y' or row.get('owner_failed') != 'N':
            raise ValueError('signal owner unhealthy')
        if set(row.get('services', {})) != set(UNITS):
            raise ValueError('missing service evidence')
        for name, unit in row['services'].items():
            if unit.get('NRestarts') != '0':
                raise ValueError('automatic service restart')
            if name != 'h713-hdmi-video.service':
                if unit.get('ActiveState') != 'active':
                    raise ValueError('HDMI owner service inactive')
                if unit.get('ExecMainStartTimestampMonotonic') != baseline['services'][name]['ExecMainStartTimestampMonotonic']:
                    raise ValueError('HDMI owner service replaced')
        if previous and (row['uptime'] <= previous['uptime'] or row['uptime'] - previous['uptime'] > 12):
            raise ValueError('non-monotonic or incomplete observation')
        previous = row
    return baseline


def analyze(samples, mode, seconds=7200):
    baseline = healthy(samples)
    if baseline['signal'] != 'locked 1280x720' or samples[-1]['signal'] != 'locked 1280x720':
        raise ValueError('locked baseline and final state required')
    if samples[-1]['services']['h713-hdmi-video.service']['ActiveState'] != 'active':
        raise ValueError('video did not return')
    if mode == 'soak':
        if samples[-1]['uptime'] - baseline['uptime'] < seconds:
            raise ValueError('session too short')
        if any(row['signal'] != 'locked 1280x720' for row in samples):
            raise ValueError('source interrupted during session')
        if samples[-1]['frames'] - baseline['frames'] < 50 * (samples[-1]['uptime'] - baseline['uptime']):
            raise ValueError('capture did not sustain 50 fps')
    else:
        losses = [i for i, row in enumerate(samples) if row['signal'] == 'none']
        if not losses:
            raise ValueError('source loss not observed')
        last_loss = losses[-1]
        if not any(row['signal'] == 'locked 1280x720' for row in samples[last_loss+1:]):
            raise ValueError('source did not recover')
        stable = [row for row in samples[last_loss+1:] if row['signal'] == 'locked 1280x720']
        if len(stable) < 2 or stable[-1]['uptime'] - stable[0]['uptime'] < 10 or stable[-1]['frames'] <= stable[0]['frames']:
            raise ValueError('insufficient recovered video evidence')
    return dict(result='PASS',mode=mode,boot_id=baseline['boot_id'],samples=len(samples),
                seconds=samples[-1]['uptime']-baseline['uptime'],final_signal=samples[-1]['signal'],
                errors=samples[-1]['errors'],board_rebooted=False)


def watch(output, expected_boot, hours):
    if not 0 < hours <= 8:
        raise ValueError('observation must be bounded to at most eight hours')
    stop = False
    def halt(*unused):
        nonlocal stop
        stop = True
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, halt)
    end = time.monotonic() + hours * 3600
    with output.open('x', buffering=1) as log:
        while not stop and time.monotonic() < end:
            row = snapshot()
            if row['boot_id'] != expected_boot:
                raise ValueError('wrong board boot')
            log.write(json.dumps(row, sort_keys=True)+'\n')
            time.sleep(5)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['snapshot','watch','recovery','soak'])
    p.add_argument('--output', type=Path)
    p.add_argument('--expected-boot')
    p.add_argument('--hours', type=float, default=4)
    p.add_argument('--input', type=Path)
    p.add_argument('--start', type=float, default=0)
    p.add_argument('--end', type=float, default=float('inf'))
    p.add_argument('--seconds', type=float, default=7200)
    a = p.parse_args()
    if a.mode == 'snapshot':
        print(json.dumps(snapshot(), indent=2))
    elif a.mode == 'watch':
        if not a.output or not a.expected_boot:
            p.error('watch requires --output and --expected-boot')
        watch(a.output, a.expected_boot, a.hours)
    else:
        if not a.input:
            p.error('analysis requires --input')
        rows = [json.loads(line) for line in a.input.read_text().splitlines()]
        print(json.dumps(analyze([r for r in rows if a.start <= r['uptime'] <= a.end],a.mode,a.seconds),indent=2))
