#!/usr/bin/env python3
"""Read-only observation of a new matched-test boot; never changes the board."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import time

spec = importlib.util.spec_from_file_location('qualification', Path(__file__).with_name('startup-qualification.py'))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

REMOTE = q.REMOTE + r'''
ready_by=time.monotonic()+45
while True:
    start=snapshot()
    if start['services'].get('h713-hdmi-video.service',{}).get('ActiveState')=='active' and 'not_ready' not in start:break
    if time.monotonic()>ready_by:raise RuntimeError('video/counters not ready')
    time.sleep(1)
version=read('/sys/module/h713_hdmi_v4l2/version')
if version!='reject-trace-v1':raise RuntimeError('diagnostic module is not loaded')
start=snapshot()
video_start=int(start['services']['h713-hdmi-video.service']['ActiveEnterTimestampMonotonic'])/1e6
if video_start<=0:raise RuntimeError('video is not ready')
deadline=video_start+WINDOW
if start['uptime']>=deadline:raise RuntimeError('missed the matched observation deadline')
print(json.dumps(dict(kind='window',module_version=version,video_ready=video_start,deadline=deadline,window_seconds=WINDOW)),flush=True)
while True:
    row=snapshot()
    print(json.dumps(dict(kind='sample',data=row)),flush=True)
    if row['uptime']>=deadline:break
    time.sleep(min(5,max(0,deadline-row['uptime'])))
final=gather(PREVIOUS)
final['kernel_journal']=command(['journalctl','-k','-b','-o','short-monotonic','--no-pager'])
print(json.dumps(dict(kind='final',data=final)),flush=True)
'''


def assess(records, arm):
    window = next(r for r in records if r['kind'] == 'window')
    rows = [r['data'] for r in records if r['kind'] == 'sample']
    final = next(r['data'] for r in records if r['kind'] == 'final')
    expected = set(q.UNITS)
    if arm == 'original':
        expected.remove('h713-hdmi-prepare.service')
    issues = []
    identity = None
    for row in rows:
        services = row['services']
        active = {n: services[n] for n in expected}
        if identity is None:
            identity = (row['boot_id'], active)
        elif (row['boot_id'], active) != identity:
            issues.append('service/boot identity changed')
        for name, service in active.items():
            if any(service.get(k) != v for k, v in dict(ActiveState='active', Result='success', NRestarts='0').items()):
                issues.append('service failure: ' + name)
        for name in ('xruns', 'bad_guard', 'invalid_pair'):
            if row.get('errors', {}).get(name) != 0:
                issues.append('hard error: ' + name)
        if row.get('signal') != 'locked 1280x720':
            issues.append('source lock changed')
        for key in ('capture_pcm', 'playback_pcm'):
            if 'state: RUNNING' not in row.get(key, ''):
                issues.append('PCM not running: ' + key)
    if not rows or not (window['deadline'] <= rows[-1]['uptime'] <= window['deadline'] + 2):
        issues.append('observation deadline missed')
    journal = final['kernel_journal']
    if 'pair stream polls=' in journal or 'signal holding' in journal:
        issues.append('stream restarted/source interrupted during boot')
    if final.get('readvertised') != 0:
        issues.append('HPD re-advertisement')
    # A short HPD pulse or the HPD-only diagnostic is still a second advertisement.
    if final.get('hpd_pulses') or final.get('hpd_cycles'):
        issues.append('HPD pulse re-advertisement')
    elapsed = rows[-1]['uptime']-rows[0]['uptime']
    fps = (rows[-1]['frames']-rows[0]['frames'])/elapsed if elapsed > 0 else 0
    if fps < 50:
        issues.append('sampled frame rate below 50 fps')
    return dict(status='VALID matched observation' if not issues else 'INVALID matched observation',
                arm=arm, boot_id=final['boot_id'], issues=sorted(set(issues)),
                video_ready=window['video_ready'], window_end=window['deadline'],
                window_seconds=window.get('window_seconds', 300.0),
                stream_qualification='full' if window.get('window_seconds', 300.0) >= 300 else 'quick development check only',
                first_live_sample=rows[0]['uptime'], last_live_sample=rows[-1]['uptime'],
                fps=fps, rejected_at_window_end=rows[-1]['errors']['rejected'],
                readvertised=final.get('readvertised'), hpd_pulses=final.get('hpd_pulses'),
                hpd_cycles=final.get('hpd_cycles'),
                trace_lines=[line for line in journal.splitlines() if 'h713-hdmi-v4l2: reject=' in line],
                strict_zero_rejection_qualification='not evaluated or waived by this experiment')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-boot', required=True)
    parser.add_argument('--arm', choices=('original', 'optimized'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--module-version', default='reject-trace-v1', help='expected loaded diagnostic module version')
    parser.add_argument('--window-seconds', type=float, default=300,
                        help='stream observation after video start; below 300 is a quick development check, not qualification')
    parser.add_argument('--with-radio', action='store_true', help='also require parallel AIC owner, hotspot and BT to remain active')
    args = parser.parse_args()
    remote = REMOTE
    if args.with_radio:
        radio = ['h713-aic8800-modules.service', 'h713-hotspot.service', 'h713-bt-attach.service',
                 'systemd-modules-load.service']
        q.UNITS.extend(radio)
        remote = q.REMOTE+'\nUNITS += '+repr(radio)+'\n'+REMOTE[len(q.REMOTE):]
    remote = remote.replace("version!='reject-trace-v1'", 'version!='+repr(args.module_version))
    if not 10 <= args.window_seconds <= 3600:
        raise SystemExit('window must be 10..3600 s')
    marker = "ready_by=time.monotonic()+45"
    if remote.count(marker) != 1:
        raise SystemExit('observer template changed; refusing to inject the window')
    remote = remote.replace(marker, 'WINDOW=' + repr(float(args.window_seconds)) + '\n' + marker)
    args.output.mkdir(parents=True, exist_ok=False)
    # Source-host history affects the first HDMI advertisement. Capture it
    # before waiting, including when a later source reboot interrupts the host.
    host_context = dict(utc=datetime.now(timezone.utc).isoformat(),
                        host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                        host_uptime_seconds=float(Path('/proc/uptime').read_text().split()[0]),
                        previous_board_boot=args.previous_boot, arm=args.arm,
                        radio_checks=args.with_radio)
    (args.output/'host-context.json').write_text(json.dumps(host_context, indent=2)+'\n')
    until = time.monotonic()+1800
    while time.monotonic() < until:
        probe = subprocess.run(q.SSH+['cat /proc/sys/kernel/random/boot_id'], capture_output=True, text=True, timeout=15)
        boot = probe.stdout.strip()
        if probe.returncode == 0 and boot and boot != args.previous_boot:
            print('New boot: '+boot, flush=True)
            break
        time.sleep(5)
    else:
        raise RuntimeError('no new boot within 30 minutes')
    with (args.output/'observations.jsonl').open('w') as out, (args.output/'observer.stderr').open('w') as err:
        code = 'PREVIOUS='+repr(args.previous_boot)+'\n'+remote
        run = subprocess.run(q.SSH+['python3 -u -'], input=code, text=True, stdout=out, stderr=err, timeout=420)
    if run.returncode:
        raise RuntimeError('remote observation failed; raw evidence retained')
    records = [json.loads(line) for line in (args.output/'observations.jsonl').read_text().splitlines()]
    result = assess(records, args.arm)
    if args.with_radio:
        final = next(r['data'] for r in records if r['kind'] == 'final')
        result['radio_services'] = {name: final['services'][name] for name in radio}
        def seconds(name, key):
            return int(final['services'][name][key])/1e6
        owner = 'h713-aic8800-modules.service'
        prepare = 'h713-hdmi-prepare.service'
        # A oneshot with several ExecStart commands overwrites ExecMainStart
        # for each command. Unit activation bounds cover the complete sequence.
        result['radio_prepare_overlap_seconds'] = max(0, min(seconds(owner, 'ActiveEnterTimestampMonotonic'),
             seconds(prepare, 'ActiveEnterTimestampMonotonic'))-max(seconds(owner, 'InactiveExitTimestampMonotonic'),
             seconds(prepare, 'InactiveExitTimestampMonotonic')))
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
