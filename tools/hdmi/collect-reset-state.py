#!/usr/bin/env python3
"""Collect Linux-visible HDMI reset evidence as JSON; never authorize recovery.

No MMIO, firmware RPC, module load, service mutation, or reset is performed.
Run on the target, redirecting stdout to the evidence collector. --root reads
an offline filesystem fixture and disables commands; it is not a remote root.
Missing state is recorded, never interpreted as fresh/reset hardware.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


MODULE_PARAMS = {
    'h713_hdmi_receiver': (
        'armed', 'live_source3', 'clients', 'init_error', 'firmware_pin',
        'clock_count', 'edid_ready', 'shutdown_ready', 'parked', 'park_failed'),
    'h713_hdmi_audio': ('dsp_failed', 'manage_dsp', 'manage_tvfe',
                        'period_xruns', 'period_irq_seen', 'period_irq_status'),
    'h713_hdmi_signal': ('ready', 'failed', 'restored', 'recovery'),
    'h713_ddc_pins': (),
    'h713_scp_probe': (),
    'h713_hdmi_v4l2': (),
}
UNITS = ('h713-hdmi-capture.service', 'h713-hdmi-signal.service',
         'h713-hdmi-speaker.service')
LIMIT = 65536


def read_file(root, path, binary=False):
    try:
        with (root / path.lstrip('/')).open('rb') as stream:
            data = stream.read(LIMIT + 1)
        return {'value': data[:LIMIT].hex() if binary else
                data[:LIMIT].decode('utf-8', errors='replace'),
                'truncated': len(data) > LIMIT}
    except OSError as error:
        return {'error': str(error)}


def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=15,
                                check=False)
        return {'argv': argv, 'returncode': result.returncode,
                'stdout': result.stdout[:LIMIT].decode(errors='replace'),
                'stderr': result.stderr[:LIMIT].decode(errors='replace'),
                'truncated': max(len(result.stdout), len(result.stderr)) > LIMIT}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'argv': argv, 'error': str(error)}


def collect(root, files_only=False):
    result = {'schema': 1, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Linux-visible, non-atomic snapshot; not reset proof',
              'hardware_reset_state': 'unknown', 'files': {}, 'modules': {}}
    paths = (
        '/proc/sys/kernel/random/boot_id', '/proc/uptime', '/proc/version',
        '/proc/cmdline', '/proc/modules', '/proc/asound/cards',
        '/proc/asound/H713HDMI/pcm0c/sub0/status',
        '/run/h713-hdmi-session/state.json',
        '/sys/devices/h713-hdmi-tvfe/power/runtime_status',
        '/sys/devices/h713-hdmi-tvcap/power/runtime_status',
    )
    for path in paths:
        result['files'][path] = read_file(root, path)
    handoff = '/proc/device-tree/chosen/h713,hdmi-boot-v1'
    result['files'][handoff] = read_file(root, handoff, binary=True)
    for name, params in MODULE_PARAMS.items():
        base = root / 'sys/module' / name
        try:
            base.stat()
            present = True
        except FileNotFoundError:
            present = False
        except OSError as error:
            result['modules'][name] = {'error': str(error)}
            continue
        result['modules'][name] = {'present': present, 'parameters': {
            param: read_file(root, f'/sys/module/{name}/parameters/{param}')
            for param in params} if present else {}}
    if not files_only and root.resolve() == Path('/'):
        result['commands'] = [command(argv) for argv in (
            ['systemctl', 'show', '--no-pager',
             '--property=ActiveState,SubState,Result,ConditionResult,ExecMainStatus,NRestarts',
             *UNITS],
            ['journalctl', '-b', '--no-pager', '-n', '250',
             '-u', UNITS[0], '-u', UNITS[1], '-u', UNITS[2]],
            ['journalctl', '-b', '-1', '--no-pager', '-n', '250',
             '-u', UNITS[0], '-u', UNITS[1], '-u', UNITS[2]],
            ['dmesg', '--color=never'],
        )]
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/'))
    parser.add_argument('--files-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(collect(args.root, args.files_only), indent=2))


if __name__ == '__main__':
    main()
