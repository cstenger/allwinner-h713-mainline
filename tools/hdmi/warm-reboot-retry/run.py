#!/usr/bin/env python3
"""Stages of the one-shot warm-reboot retry of the HDMI first-advert test. See RUNBOOK.md.

Each stage runs once, in order, and leaves a receipt in the run directory, so a
fresh session after the host reboot can continue. Live stages need --live. The
only board change is the single orderly poweroff; the board config is not touched.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ZERO = REPO / 'local/recovery/2026-11-01-hdmi-zero-cold-validation'
TAG = '2026-11-02-hdmi-warm-reboot-retry'  # names the run directory and the board's poweroff receipt
RUN = REPO / 'local/recovery' / TAG
PORT = '/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0'
CONNECTOR = Path('/sys/class/drm/card1-HDMI-A-1')
SSH = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@192.168.4.1']
EDID_SHA256 = 'edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34'
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
UNIT = 'h713-warm-retry-%s-%s-20261102-01.service'
SOURCES = {'capture-panel-validation.py': '957edf66a028f80edd5ca8b241d5f23240fa1e43b2bb63deee35787a5c20c73a',
           'cached-hdmi-monitor.py': '4c9f5ce510ed63dacf91245c772101b937e36da29711666f1392ed3e8c35e9c0'}
PIN_SOURCES = {'zero-control-poweroff.py': 'c289f288e16d583579669cd2d0ca7ee2247970678643d0b5507668dfc849cf7c',
               'postboot-readonly.py': 'a27eeeaf55f1d862e2ddcfd53be2eb56b2fe9a309bf1b0128d8ea509690141bc'}
# Matches boot 275f5bce: about 8 minutes off, within what the abrupt cycle's 14 passed.
MIN_OFF_SECONDS, MAX_OFF_SECONDS = 480, 1200
PREFLIGHT_MAX_AGE_SECONDS = 1800
AFTER_LOGIN_WINDOW_SECONDS = 120
LOST_POWER_BIT_REFERENCE = 0.087  # 2d8c3970 -> afe48e93, a known power loss
STAGES = ('arm-pre', 'preflight', 'poweroff', 'arm-post', 'ready', 'observe', 'collect', 'analyze', 'close')


def utc():
    return datetime.now(timezone.utc).isoformat()


def stop(message):
    sys.exit('REFUSED: ' + message)


def need(ok, message):
    if not ok:
        stop(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def literal_assignment(source, name):
    """A constant from a sealed script, without executing that script."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == name:
            return ast.literal_eval(node.value)
    raise RuntimeError(name + ' not found')


def load_pins(zero=ZERO):
    for name, digest in PIN_SOURCES.items():
        need(sha256(zero / name) == digest, 'sealed pin source changed: ' + name)
    pins = literal_assignment((zero / 'zero-control-poweroff.py').read_text(), 'PINS')
    storage = literal_assignment((zero / 'postboot-readonly.py').read_text(), 'STORAGE')
    need(len(pins['file_pins']) == 56 and len(pins['runtime_hashes']) == 5 and len(storage) >= 8, 'pin counts')
    return {'file_pins': pins['file_pins'], 'runtime_hashes': pins['runtime_hashes'], 'storage': storage,
            'dropin_sha256': pins['dropin_sha256'], 'kernel_notes_sha256': pins['kernel_notes_sha256'],
            'cid': pins['cid']}


def render(mode, pins, **extra):
    config = {**pins, 'mode': mode, 'receipt_name': TAG + '-poweroff-request.json', **extra}
    test_root = os.environ.get('H713_HRT_TEST_ROOT')
    if test_root:
        config['root'] = test_root
    return 'CONFIG = %r\n' % (config,) + (HERE / 'board_script.py').read_text()


def on_board(script, timeout=180):
    return subprocess.run(SSH + ['python3', '-'], input=script, capture_output=True, text=True, timeout=timeout)


class Run:
    def __init__(self, root):
        self.root = Path(root)

    def receipt(self, stage):
        return self.root / ('STAGE-%s.json' % stage)

    def done(self, stage):
        return self.receipt(stage).exists()

    def load(self, stage):
        return json.loads(self.receipt(stage).read_text())

    def begin(self, stage):
        index = STAGES.index(stage)
        need(not self.done(stage), stage + ' already ran; stages are single-use')
        if index:
            need(self.done(STAGES[index - 1]), 'run %s first' % STAGES[index - 1])

    def finish(self, stage, value):
        value = {'stage': stage, 'finished_utc': utc(), **value}
        with self.receipt(stage).open('x') as f:
            json.dump(value, f, sort_keys=True, indent=2)
            f.write('\n')
        print(json.dumps({k: v for k, v in value.items() if not isinstance(v, (dict, list))}, indent=2))
        return value


def host_boot():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def cached_hdmi():
    edid = (CONNECTOR / 'edid').read_bytes()
    return {'status': (CONNECTOR / 'status').read_text().strip(), 'enabled': (CONNECTOR / 'enabled').read_text().strip(),
            'edid_bytes': len(edid), 'edid_sha256': hashlib.sha256(edid).hexdigest()}


def start_unit(run, name, argv):
    log = run.root / (name + '.process.log')
    unit = name_unit(name)
    subprocess.run(['systemd-run', '--user', '--unit=' + unit, '--property=Restart=no', '--property=TimeoutStopSec=10',
                    '--property=UMask=0077', '--property=StandardOutput=append:%s' % log,
                    '--property=StandardError=append:%s' % log, *argv], check=True, timeout=20, capture_output=True)
    return unit


def name_unit(name):
    kind, phase = name.split('-')
    return UNIT % (phase, kind)


def unit_props(unit):
    p = subprocess.run(['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID',
                        '-p', 'Restart'], capture_output=True, text=True, check=True, timeout=5)
    return dict(line.split('=', 1) for line in p.stdout.splitlines())


def start_recorders(run, phase):
    python = ['/usr/bin/python3', '-B']
    start_unit(run, 'uart-' + phase, [*python, str(REPO / 'tools/serial/capture-panel-validation.py'),
                                      '--port', PORT, '--output', str(run.root / ('uart-' + phase))])
    start_unit(run, 'hdmi-' + phase, [*python, str(HERE / 'cached-hdmi-monitor.py'), str(run.root / ('hdmi-' + phase))])
    # Kernel uevents only: a read-only netlink listener; udevadm prints its own monotonic stamp.
    start_unit(run, 'uevent-' + phase, ['/usr/bin/stdbuf', '-oL', '/usr/bin/udevadm', 'monitor', '--kernel',
                                        '--subsystem-match=drm', '--property'])


def verify_recorders(run, phase, wait=8):
    deadline = time.monotonic() + wait
    while True:
        try:
            return check_recorders(run, phase)
        except (OSError, AssertionError, ValueError, KeyError, subprocess.SubprocessError) as error:
            if time.monotonic() >= deadline:
                stop('recorders not healthy: %r' % (error,))
            time.sleep(.5)


def check_recorders(run, phase):
    props = {}
    for kind in ('uart', 'hdmi', 'uevent'):
        props[kind] = unit_props(name_unit(kind + '-' + phase))
        assert props[kind]['ActiveState'] == 'active' and props[kind]['SubState'] == 'running'
        assert props[kind]['Restart'] == 'no'
    port = str(Path(PORT).resolve(strict=True))
    owners = subprocess.run(['fuser', port], capture_output=True, text=True, timeout=5).stdout.split()
    assert owners == [props['uart']['MainPID']], 'UART owners %r' % owners
    stamped = (run.root / ('uart-' + phase) / 'serial-timestamped.log').read_text(errors='replace')
    assert 'OPEN ' + PORT in stamped and 'CAPTURE STOP' not in stamped
    latest = json.loads((run.root / ('hdmi-' + phase) / 'latest.json').read_text())
    assert latest['snapshot']['ok'] and latest['phase'] != 'stop'
    assert time.monotonic_ns() - latest['host_monotonic_ns'] < 10_000_000_000
    return {'units': props, 'cached_hdmi': latest['snapshot']}


def stop_recorders(phase):
    for kind in ('uart', 'hdmi', 'uevent'):
        subprocess.run(['systemctl', '--user', 'stop', name_unit(kind + '-' + phase)], timeout=20, check=False)


def monitor_transitions(path):
    """(utc seconds, monotonic ns, status, enabled, edid sha) at every recorded change."""
    previous, out = None, []
    for line in Path(path).read_text().splitlines():
        e = json.loads(line)
        s = e['snapshot']
        if not s or not s.get('ok'):
            continue
        key = (s['status'], s['enabled'], s['edid_sha256'])
        if key != previous:
            out.append((datetime.fromisoformat(e['host_utc']).timestamp(), e['host_monotonic_ns'], *key))
            previous = key
    return out


def uart_lines(path):
    out = []
    for line in Path(path).read_text(errors='replace').splitlines():
        m = re.match(r'(\d{4}-\S+) (.*)$', line)
        if m:
            out.append((datetime.fromisoformat(m.group(1)).timestamp(), m.group(2)))
    return out


def uart_summary(path):
    lines = uart_lines(path)
    spl = [t for t, s in lines if 'U-Boot SPL' in s]
    power_down = [t for t, s in lines if 'reboot: Power down' in s]
    login = [t for t, s in lines if ' login: ' in s or ' login:' in s]
    return {'spl': spl, 'power_down': power_down, 'login': login,
            'disconnects': sum('DISCONNECTED' in s or 'OPEN FAILED' in s for _, s in lines)}


def kernel_zero(path):
    """Host UTC of kernel uptime zero, from the last boot's stamped console lines."""
    lines = uart_lines(path)
    spl = max((i for i, (_, s) in enumerate(lines) if 'U-Boot SPL' in s), default=0)
    offsets = [t - float(m.group(1)) for t, s in lines[spl:]
               for m in [re.search(r'\[ *(\d+\.\d+)\] [^\[]*$', s)] if m and float(m.group(1)) > 2.5]
    return min(offsets) if offsets else None


def kernel_time(log, pattern):
    m = re.search(r'\[ *(\d+\.\d+)\] [^\n]*' + pattern, log)
    return float(m.group(1)) if m else None


def bank_comparison(s0_hex, s1_hex):
    a, b = bytes.fromhex(s0_hex)[0x4780:0x4a80], bytes.fromhex(s1_hex)[0x4780:0x4a80]
    bits = sum(bin(x ^ y).count('1') for x, y in zip(a, b))
    fraction = bits / (len(a) * 8)
    verdict = 'RETAINED' if bits == 0 else ('LOST' if fraction >= .01 else 'PARTIAL')
    return {'bytes': len(a), 'differing_bits': bits, 'fraction': round(fraction, 4), 'edid_ram': verdict}


def uevents(path, phase_label):
    text = Path(path).read_text(errors='replace') if Path(path).exists() else ''
    events = re.findall(r'^KERNEL\[(\d+\.\d+)\] (\w+)\s+(\S+)', text, re.M)
    hotplug = [float(t) for t, _, _ in events]
    return {'phase': phase_label, 'drm_events': len(events), 'hotplug_properties': text.count('HOTPLUG=1'),
            'first_monotonic': hotplug[0] if hotplug else None, 'last_monotonic': hotplug[-1] if hotplug else None}


def timing(events_path, uart_path, kernel_log):
    zero = kernel_zero(uart_path)
    ready = kernel_time(kernel_log, r'h713-hdmi-signal: EDID and HPD ready')
    lock = kernel_time(kernel_log, r'h713-hdmi-v4l2: signal locked')
    result = {'kernel_uptime_zero_utc': zero, 'ready_uptime': ready, 'lock_uptime': lock,
              'ready_to_lock': round(lock - ready, 3) if lock and ready else None, 'ready_to_connected': None}
    connected = [t for t, _, status, *_ in monitor_transitions(events_path)
                 if status == 'connected' and zero and t > zero]
    if connected and ready:
        result['ready_to_connected'] = round(connected[0] - zero - ready, 3)
    return result


def classify(detected, edid_ok, control_ok, bank):
    """The conclusion this run allows. Never more than the design supports."""
    if not control_ok:
        return 'INVALID: a matched condition did not hold; this run decides nothing'
    if detected and edid_ok:
        return ('DETECTED after one warm host reboot and no host poweroff: a strict first-advert rule is refuted, and '
                'this did not reproduce the failure of the run with a full host poweroff (4a945796). '
                'One run each, so the poweroff is a candidate, not a cause. '
                'Next test: a full host poweroff alone, same conditions.')
    if detected:
        return 'INVALID: connected with an unexpected EDID'
    tail = {'RETAINED': 'EDID RAM kept power, which points away from rail discharge and toward host state.',
            'LOST': 'EDID RAM lost power, so host state and rail discharge remain unseparated.',
            'PARTIAL': 'EDID RAM partly decayed; rail state is ambiguous.'}[bank['edid_ram']]
    return ('NOT DETECTED after one warm host reboot and no host poweroff: a full host poweroff is not needed to '
            'reproduce the failure under the 0 ms bench, about the same off time and an orderly shutdown. ' + tail +
            ' Preserve this state: no reseat, HPD pulse, service restart or reboot without a new decision.')


def stage_arm_pre(run, args):
    pins = load_pins()
    host = cached_hdmi()
    need(host['status'] == 'connected', 'host does not show the projector connected')
    run.root.mkdir(exist_ok=True)
    start_recorders(run, 'pre')
    run.finish('arm-pre', {'host_boot_id': host_boot(), 'recorders': verify_recorders(run, 'pre'), 'pins': len(pins['file_pins'])})


def stage_preflight(run, args):
    verify_recorders(run, 'pre')
    p = on_board(render('preflight', load_pins()))
    need(p.returncode == 0, 'board preflight failed:\n' + p.stderr[-2000:])
    result = json.loads(p.stdout)
    (run.root / 'S0.json').write_text(json.dumps(result, sort_keys=True))
    host = cached_hdmi()
    need(host['status'] == 'connected' and host['edid_sha256'] == EDID_SHA256, 'host EDID is not the expected one')
    run.finish('preflight', {'board_boot_id': result['boot_id'], 'signal': result['signal'], 'host_hdmi': host,
                             'bank_backup_sha256': result['sram']['bank_backup_sha256'],
                             'ext4_kernel_lines': result['ext4_kernel_lines'], 'monotonic_s': time.monotonic()})


def stage_poweroff(run, args):
    pre = run.load('preflight')
    need(pre['host_hdmi'] and host_boot() == run.load('arm-pre')['host_boot_id'], 'host rebooted too early')
    need(time.monotonic() - pre['monotonic_s'] < PREFLIGHT_MAX_AGE_SECONDS, 'preflight is stale')
    verify_recorders(run, 'pre')
    script = render('poweroff', load_pins(), expected_boot=pre['board_boot_id'],
                    s0_bank_sha256=pre['bank_backup_sha256'])
    intent = run.root / 'POWEROFF-INTENT.json'
    need(not intent.exists(), 'a poweroff was already attempted; inspect it, do not retry blindly')
    intent.write_text(json.dumps({'utc': utc(), 'board_boot_id': pre['board_boot_id']}) + '\n')
    try:
        p = on_board(script, 60)
        dispatch = {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr[-2000:]}
    except subprocess.TimeoutExpired as error:  # ssh can outlive the board; keep what it printed
        output = error.stdout or b''
        dispatch = {'returncode': None, 'stderr': 'ssh timeout',
                    'stdout': output.decode(errors='replace') if isinstance(output, bytes) else output}
    issued = 'ISSUING_ONE_ORDINARY_SYSTEMCTL_POWEROFF' in dispatch['stdout']
    need(issued, 'poweroff not dispatched; board untouched past its gates:\n' + dispatch['stderr'])
    deadline = time.monotonic() + args.wait
    uart = run.root / 'uart-pre/serial-timestamped.log'
    host = cached_hdmi()
    while time.monotonic() < deadline:
        host = cached_hdmi()
        if uart_summary(uart)['power_down'] and host['status'] == 'disconnected':
            break
        time.sleep(1)
    summary = uart_summary(uart)
    need(summary['power_down'], 'no Power down on UART; do not remove power or reboot the host yet')
    need(host['status'] == 'disconnected', 'host never showed disconnected')
    time.sleep(2)  # let the recorders log the final transition
    stop_recorders('pre')
    run.finish('poweroff', {'dispatch': dispatch, 'power_down_utc': summary['power_down'][-1], 'host_hdmi': host,
                            'host_boot_id': host_boot(), 'recorders_stopped': True,
                            'next': 'Remove board supply, leave all cables, then run: systemctl reboot'})


def stage_arm_post(run, args):
    off = run.load('poweroff')
    need(args.supply_removed, 'confirm with --supply-removed once the operator has removed board power')
    now_boot = host_boot()
    need(now_boot != off['host_boot_id'], 'the host has not rebooted since the poweroff')
    boots = subprocess.run(['journalctl', '--list-boots', '--no-pager', '-o', 'json'], capture_output=True, text=True,
                           check=True, timeout=20).stdout
    listed = [b['boot_id'] for b in json.loads(boots)]
    need(listed[-2:] == [off['host_boot_id'].replace('-', ''), now_boot.replace('-', '')],
         'expected exactly one host reboot since the poweroff')
    ended = subprocess.run(['journalctl', '-b', off['host_boot_id'].replace('-', ''), '--no-pager', '-o', 'short-iso'],
                           capture_output=True, text=True, check=True, timeout=30).stdout
    need('reboot requested from' in ended and 'poweroff requested from' not in ended,
         'the previous host boot did not end in a requested reboot; this run tests a warm reboot only')
    journal = subprocess.run(['journalctl', '-b', '--no-pager', '-o', 'short-iso'], capture_output=True, text=True,
                             check=True, timeout=30).stdout
    need('s-monitors: HDMI connected' not in journal, 'this host boot already saw a connect; not a first advert')
    host = cached_hdmi()
    need(host['status'] == 'disconnected' and host['edid_bytes'] == 0, 'host is not disconnected with empty EDID')
    start_recorders(run, 'post')
    recorders = verify_recorders(run, 'post')
    summary = uart_summary(run.root / 'uart-post/serial-timestamped.log')
    need(not summary['spl'], 'board already started; this run is invalid')
    run.finish('arm-post', {'host_boot_id': now_boot, 'host_hdmi': host, 'recorders': recorders,
                            'operator_confirmed_supply_removed': True, 'host_path': 'one requested reboot, no poweroff',
                            'earliest_power_on_utc': off['power_down_utc'] + MIN_OFF_SECONDS})


def stage_ready(run, args):
    off = run.load('poweroff')
    elapsed = time.time() - off['power_down_utc']
    need(elapsed >= MIN_OFF_SECONDS, 'wait %d s more to match the off time' % (MIN_OFF_SECONDS - elapsed))
    need(elapsed <= MAX_OFF_SECONDS, 'off for %d s; over %d s, so the match is lost. Stop and decide.' % (elapsed, MAX_OFF_SECONDS))
    recorders = verify_recorders(run, 'post')
    need(cached_hdmi()['status'] == 'disconnected', 'host no longer shows disconnected')
    need(not uart_summary(run.root / 'uart-post/serial-timestamped.log')['spl'], 'board already started; invalid')
    latest = off['power_down_utc'] + MAX_OFF_SECONDS
    run.finish('ready', {'off_seconds_so_far': round(elapsed), 'recorders': recorders, 'power_on_by_utc': latest,
                         'power_on_by_local': datetime.fromtimestamp(latest).astimezone().strftime('%H:%M:%S %Z'),
                         'next': 'Operator: power on once. Touch no cable, host setting or U-Boot prompt.'})


def stage_observe(run, args):
    """Host-only and passive: decides detection without contacting the board."""
    uart, events = run.root / 'uart-post/serial-timestamped.log', run.root / 'hdmi-post/events.jsonl'
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        summary = uart_summary(uart)
        done_at = summary['login'][-1] + AFTER_LOGIN_WINDOW_SECONDS if summary['login'] else None
        connected = [t for t, _, status, *_ in monitor_transitions(events) if status == 'connected']
        if connected or (done_at and time.time() >= done_at):
            break
        time.sleep(1)
    else:
        stop('no boot and no detection before the wait ended; rerun observe, nothing was recorded')
    time.sleep(3)
    host = cached_hdmi()
    run.finish('observe', {'detected': bool(connected), 'first_connected_utc': connected[0] if connected else None,
                           'host_hdmi': host, 'uart': summary, 'contacted_board': False})


def stage_collect(run, args):
    pre = run.load('preflight')
    script = render('collect', load_pins(), previous_boot=pre['board_boot_id'])
    p = None
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:  # the host's Wi-Fi link to the board comes up by itself
        p = on_board(script)
        if p.returncode != 255:
            break
        time.sleep(5)
    need(p is not None and p.returncode == 0, 'read-only collection failed:\n' + (p.stderr[-2000:] if p else 'not attempted'))
    result = json.loads(p.stdout)
    (run.root / 'S1.json').write_text(json.dumps(result, sort_keys=True))
    run.finish('collect', {'board_boot_id': result['boot_id'], 'signal': result['signal'],
                           'pin_failures': result['pin_failures'], 'runtime_failures': result['runtime_failures']})


def host_journal():
    p = subprocess.run(['journalctl', '-b', '--no-pager', '-o', 'short-iso'], capture_output=True, text=True, timeout=30)
    return [line for line in p.stdout.splitlines() if 's-monitors: HDMI' in line]


def stage_analyze(run, args):
    s0, s1 = (json.loads((run.root / name).read_text()) for name in ('S0.json', 'S1.json'))
    observe, off = run.load('observe'), run.load('poweroff')
    uart = run.root / 'uart-post/serial-timestamped.log'
    summary = uart_summary(uart)
    bank = bank_comparison(s0['sram']['sram_hex'], s1['sram']['sram_hex'])
    loaded = s1['loaded_commands']
    journal = s1['signal_journal_json']['stdout']
    delay_records = re.findall(r'\\"delay_ms\\": (\d+)', journal)
    off_seconds = summary['spl'][0] - off['power_down_utc'] if summary['spl'] else None
    checks = {
        'one_spl': len(summary['spl']) == 1,
        'uart_continuous': summary['disconnects'] == 0,
        'off_time_matched': off_seconds is not None and MIN_OFF_SECONDS <= off_seconds <= MAX_OFF_SECONDS,
        'host_warm_reboot_only': run.load('arm-post')['host_path'] == 'one requested reboot, no poweroff',
        'same_host_boot_since_arming': host_boot() == run.load('arm-post')['host_boot_id'],
        'zero_ms_loaded': '--bench-delay-ms=0 ' in loaded,
        'zero_ms_ran_once': delay_records in (['0', '0'],),
        'pins_unchanged': not s1['pin_failures'] and not s1['runtime_failures'],
        'storage_unchanged': all(s1['storage_checks'].values()),
        'identity': s1['cid_matches'] and s1['kernel_notes_match'],
        'sram_payload_same': (s0['sram']['sram_hex'][2 * 0x4680:2 * 0x4780] == s1['sram']['sram_hex'][2 * 0x4680:2 * 0x4780]),
        'owner_healthy': (s1['parameters']['h713_hdmi_signal.ready'], s1['parameters']['h713_hdmi_signal.failed']) == ('Y', 'N'),
        'prior_stop_restored': 'ownership restored' in s1['previous_boot_signal_journal']['stdout'],
    }
    control = {k: v for k, v in checks.items() if k != 'prior_stop_restored'}
    edid_ok = observe['host_hdmi']['edid_sha256'] == EDID_SHA256
    conclusion = classify(observe['detected'], edid_ok, all(control.values()), bank)
    late = [t for t, _, status, *_ in monitor_transitions(run.root / 'hdmi-post/events.jsonl') if status == 'connected']
    control_uevents = uevents(run.root / 'uevent-pre.process.log', 'poweroff control')
    test_uevents = uevents(run.root / 'uevent-post.process.log', 'first advert')
    limits = ['One run; no failure rate.', 'UART stayed wired: this is not a fully cold start.',
              'A warm host reboot may or may not drop GPU +5 V and USB power.']
    if not checks['prior_stop_restored']:
        limits.append('The orderly restore is not in the board journal, so EDID RAM comparison is weaker.')
    if late and not observe['detected']:
        limits.append('The host connected only after the observation window closed; treat this as a slow detection, not a clean miss.')
    if control_uevents['drm_events'] == 0:
        limits.append('The uevent recorder saw nothing at poweroff, so a null uevent result means nothing.')
    if bank['edid_ram'] != 'RETAINED':
        limits.append('Non-identical EDID RAM could also come from a reset clearing it, not only power loss. '
                      'Reference for known power loss: %.1f%% of bits.' % (100 * LOST_POWER_BIT_REFERENCE))
    run.finish('analyze', {
        'conclusion': conclusion, 'detected': observe['detected'], 'checks': checks, 'edid_bank_comparison': bank,
        'timing': timing(run.root / 'hdmi-post/events.jsonl', uart, s1['kernel_all']),
        'board_off_seconds': off_seconds, 'signal': s1['signal'], 'uevents': [control_uevents, test_uevents],
        'host_journal_hdmi_lines': host_journal(), 'limits': limits, 'board_boot_id': s1['boot_id'],
    })


def stage_close(run, args):
    stop_recorders('post')
    time.sleep(1)
    for phase in ('pre', 'post'):
        need('CAPTURE STOP' in (run.root / ('uart-' + phase) / 'serial-timestamped.log').read_text(errors='replace'),
             'UART %s capture has no clean stop' % phase)
    value = run.finish('close', {'board_action': False, 'note': 'Board left exactly as it is, including any failed state.'})
    lines = ['%s  %s' % (sha256(p), p.relative_to(run.root)) for p in sorted(run.root.rglob('*'))
             if p.is_file() and p.name != 'SHA256SUMS']
    (run.root / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    with tarfile.open(str(run.root) + '.tar.gz', 'x:gz') as tar:
        tar.add(run.root, arcname=run.root.name)
    return value


LIVE = {'arm-pre', 'preflight', 'poweroff', 'arm-post', 'ready', 'observe', 'collect', 'close'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('check', *STAGES))
    parser.add_argument('--live', action='store_true', help='required for any stage that touches recorders or the board')
    parser.add_argument('--supply-removed', action='store_true', help='arm-post: the operator removed board power')
    parser.add_argument('--wait', type=int, default=300, help='seconds to wait in poweroff, observe or collect')
    parser.add_argument('--run-dir', type=Path, default=RUN)
    args = parser.parse_args()
    for name, digest in SOURCES.items():
        source = (HERE / name) if name == 'cached-hdmi-monitor.py' else (REPO / 'tools/serial' / name)
        need(sha256(source) == digest, 'recorder source changed: ' + name)
    if args.stage == 'check':
        pins = load_pins()
        for mode, extra in (('preflight', {}), ('poweroff', {'expected_boot': 'x', 's0_bank_sha256': 'x'}),
                            ('collect', {'previous_boot': 'x'})):
            compile(render(mode, pins, **extra), mode, 'exec')
        print(json.dumps({'status': 'PACKET_CHECK_PASS', 'file_pins': len(pins['file_pins']),
                          'runtime_hashes': len(pins['runtime_hashes']), 'storage_regions': len(pins['storage']),
                          'contacted_board': False}, indent=2))
        return
    need(args.stage not in LIVE or args.live, args.stage + ' is live; pass --live once it is authorized')
    run = Run(args.run_dir)
    if args.stage != 'arm-pre':
        need(args.run_dir.is_dir(), 'run arm-pre first')
    run.begin(args.stage) if args.run_dir.is_dir() else None
    globals()['stage_' + args.stage.replace('-', '_')](run, args)


if __name__ == '__main__':
    main()
