#!/usr/bin/env python3
"""Soak the product's light standby and log how hot the SoC gets.

Uses the real product path, not raw PB5 writes: `h713-standby on` (players
stopped, lamp and fan off via the lamp backlight, CPU capped at its lowest
OPP; HDMI capture keeps running) and `h713-standby off` to wake (the bounded
lamp ramp; an abrupt PB5 edge can reset the board). Every INTERVAL seconds it
logs both thermal zones, CPU frequency, load, HDMI frames and lamp state as
JSON lines. It wakes at the end of SECONDS, on SIGTERM/SIGINT, or at once if
any zone reaches ABORT_C (default 70 C, under the 75 C passive trip).

  usage: standby-thermal-soak.py SECONDS OUTFILE [--abort-c C] [--interval S]

Runs on the board as root, detached (systemd-run), so host loss is harmless.
Exit 0: completed the soak, woke cleanly. 2: aborted on temperature, woke.
1: could not enter or could not wake (the log says which).
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

SYS = Path('/sys')
STANDBY = '/usr/local/bin/h713-standby'


def read(path, default=None):
    try:
        return path.read_text().strip()
    except OSError:
        return default


def sample(root, clock):
    zones = sorted(p for p in (root/'class/thermal').glob('thermal_zone*'))
    temps = {read(z/'type', z.name): int(read(z/'temp', '0')) / 1000 for z in zones}
    policy = root/'devices/system/cpu/cpufreq/policy0'
    frames = read(root/'module/h713_hdmi_v4l2/parameters/frames_produced')
    return {'t': round(clock(), 1), 'temps': temps,
            'cur_khz': int(read(policy/'scaling_cur_freq', '0')),
            'max_khz': int(read(policy/'scaling_max_freq', '0')),
            'load1': float(read(Path('/proc/loadavg'), '0').split()[0]) if root == SYS else 0.0,
            'frames': int(frames) if frames and frames.isdigit() else None,
            'signal': read(root/'devices/platform/h713-hdmi-ring/signal'),
            'bl_power': read(root/'class/backlight/lamp/bl_power')}


def soak(seconds, out, abort_c=70.0, interval=10.0, *, root=SYS, standby=STANDBY,
         clock=time.monotonic, sleep=time.sleep, run=subprocess.run):
    stop = {'signal': None}
    def halt(signum, frame): stop['signal'] = signum
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, halt)
    start = clock()
    def log(kind, **data):
        out.write(json.dumps({'kind': kind, 'elapsed': round(clock() - start, 1), **data}) + '\n')
        out.flush()
    def standby_cmd(arg):
        p = run([standby, arg], capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout + p.stderr).strip()
    rc, text = standby_cmd('')
    if text != 'off':
        log('refused', reason='not starting from a woken state', state=text)
        return 1
    log('baseline', **sample(root, clock))
    rc, text = standby_cmd('on')
    entered = sample(root, clock)
    if rc != 0 or entered['bl_power'] != '4':
        log('enter_failed', rc=rc, output=text, **entered)
        standby_cmd('off')
        return 1
    log('entered', output=text, **entered)
    result, peak = 0, {}
    try:
        while clock() - start < seconds:
            if stop['signal'] is not None:
                log('stopped', signal=stop['signal'])
                break
            row = sample(root, clock)
            for zone, value in row['temps'].items():
                peak[zone] = max(peak.get(zone, value), value)
            log('sample', **row)
            if any(value >= abort_c for value in row['temps'].values()):
                log('abort', reason=f'a zone reached {abort_c} C', **row)
                result = 2
                break
            sleep(interval)
    finally:
        rc, text = standby_cmd('off')
        woke = sample(root, clock)
        ok = rc == 0 and woke['bl_power'] == '0'
        log('woke' if ok else 'wake_failed', rc=rc, output=text, peak=peak, **woke)
    return result if ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('seconds', type=float)
    parser.add_argument('outfile', type=Path)
    parser.add_argument('--abort-c', type=float, default=70.0)
    parser.add_argument('--interval', type=float, default=10.0)
    args = parser.parse_args()
    if not 0 < args.seconds <= 4 * 3600 or not 40 <= args.abort_c <= 74 or not 1 <= args.interval <= 60:
        parser.error('seconds 0..14400, abort 40..74 C, interval 1..60 s')
    with args.outfile.open('x') as out:
        sys.exit(soak(args.seconds, out, args.abort_c, args.interval))


if __name__ == '__main__':
    main()
