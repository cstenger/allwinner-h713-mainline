#!/usr/bin/env python3
"""One explicit read-only prefix step per invocation; never run a stage loop.

A failed/uncertain operation consumes this boot. No DSP request, reset or boot.
This helper must be staged with the new guard and a pinned manifest.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

MODULE = 'h713_hdmi_dsp_access_audit'
KO = 'h713-hdmi-dsp-access-audit.ko'
PARAM = '/sys/module/' + MODULE + '/parameters/'
STATE = '/run/h713-dsp-access-audit/state.json'
GUARD = '/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard'
SCHEMA = 'h713-dsp-access-prefix-v1'
COMPETITORS = ('h713_hdmi_receiver', 'h713_hdmi_audio', 'h713_hdmi_signal',
               'h713_ddc_pins', 'h713_scp_probe', 'h713_hdmi_dsp_probe',
               'h713_tvfe_bench', 'h713_hdmi_power', 'h713_hdmi_tvfe_hold',
               'h713_edid_clock', 'h713_hdmi_dsp_observe')
STEPS = (
    'claim-dsp-port', 'claim-lock-window', 'claim-audiotop', 'claim-scp-reset',
    'map-mips-status', 'map-scp-reset', 'map-tv-ccu', 'map-display-ccu',
    'read-mips-stopped', 'read-scp-stopped', 'read-demod-bus', 'read-display-bus',
    'get-display-reset', 'read-display-reset', 'get-demod-reset', 'read-demod-reset',
    'get-clock-pll-video0', 'get-clock-pll-adc', 'get-clock-bus-tvcap',
    'get-clock-bus-cap-300m', 'get-clock-vincap-dma', 'get-clock-tvfe-1296m',
    'get-clock-bus-hdmi-audio', 'get-clock-hdmi-audio', 'get-clock-audio-cpu',
    'get-clock-audio-umac', 'get-clock-audio-ihb', 'get-clock-pll-video2',
    'get-clock-deint', 'get-clock-panel', 'get-clock-svp-dtl', 'get-clock-afbd',
    'get-clock-bus-disp')


class Backend:
    def note(self, event, **values):
        print(json.dumps({'event': event, 'monotonic_ns': time.monotonic_ns(), **values}), flush=True)

    def read(self, path):
        self.note('before-read', path=path)
        result = Path(path).read_bytes()
        self.note('after-read', path=path)
        return result

    def exists(self, path):
        self.note('before-exists', path=path)
        result = Path(path).exists()
        self.note('after-exists', path=path, exists=result)
        return result

    def write(self, path, value):
        self.note('before-write', path=path, value=value.decode().strip())
        Path(path).write_bytes(value)
        self.note('after-write', path=path)

    def run(self, argv):
        self.note('before-command', argv=argv)
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True)
        except subprocess.CalledProcessError as error:
            self.note('command-failed', argv=argv, code=error.returncode, stdout=error.stdout, stderr=error.stderr)
            raise
        except subprocess.TimeoutExpired:
            self.note('command-timeout', argv=argv, uncertain=True)
            raise
        self.note('after-command', argv=argv)
        return result.stdout

    def save(self, value):
        self.note('before-state-save', **value)
        path = Path(STATE)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = path.with_suffix('.new')
        with temp.open('w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        self.note('state-saved', **value)


class Audit:
    def __init__(self, backend, bundle, boot):
        self.b, self.bundle, self.expected = backend, str(bundle), boot

    def boot(self):
        if self.b.read('/proc/sys/kernel/random/boot_id').decode().strip() != self.expected:
            raise RuntimeError('Unexpected boot ID; no action')

    def prior(self):
        return json.loads(self.b.read(STATE)) if self.b.exists(STATE) else None

    def save(self, phase, completed, **fields):
        self.b.save({'boot_id': self.expected, 'schema': SCHEMA, 'phase': phase,
                     'completed': completed, **fields})

    def preflight(self):
        self.boot()
        if self.b.exists('/run/h713-dsp-observe/state.json'):
            raise RuntimeError('Legacy observation attempted this boot; require fresh cold boot')
        if self.b.exists('/proc/device-tree/chosen/h713,hdmi-boot-v1'):
            raise RuntimeError('HDMI handoff exists')
        if self.b.read('/proc/device-tree/chosen/h713,dsp-observation-v1') != bytes.fromhex('44535031'):
            raise RuntimeError('Missing observation marker')
        for node in ('display@5600000', 'cpu-comm@3003000'):
            if self.b.read('/proc/device-tree/soc/' + node + '/status') != b'disabled\0':
                raise RuntimeError('Competing DT node is not disabled: ' + node)
        if self.b.exists('/dev/cpu_comm_fd'):raise RuntimeError('CPU_COMM device exists')
        for name in COMPETITORS:
            if self.b.exists('/sys/module/' + name):raise RuntimeError('Competing owner: ' + name)
        for unit in ('capture', 'signal', 'speaker'):
            active = self.b.run(['systemctl', 'show', 'h713-hdmi-' + unit + '.service',
                                 '-p', 'ActiveState', '--value']).strip()
            if active != 'inactive':raise RuntimeError('HDMI unit is not inactive: ' + unit)
        manifest = json.loads(self.b.read(self.bundle + '/manifest.json'))
        if manifest['schema'] != SCHEMA:raise RuntimeError('Wrong bundle schema')
        for path, digest in (
                (self.bundle + '/' + KO, manifest['module_sha256']),
                (GUARD, manifest['guard_sha256']),
                (self.bundle + '/dsp-access-audit.py', manifest['helper_sha256'])):
            if hashlib.sha256(self.b.read(path)).hexdigest() != digest:
                raise RuntimeError('Pinned file mismatch: ' + path)
        release = self.b.run(['uname', '-r']).strip()
        vermagic = self.b.run(['modinfo', '-F', 'vermagic', self.bundle + '/' + KO]).split()[0]
        if release != manifest['kernel_release'] or vermagic != release:
            raise RuntimeError('Kernel ABI mismatch')
        self.boot()

    def snapshot(self):
        result = {name: self.b.read(PARAM + name).decode().strip() for name in
                  ('failed', 'released', 'prefix_complete', 'completed', 'attempted',
                   'next_operation', 'last_value')}
        result['completed'] = int(result['completed'])
        result['attempted'] = int(result['attempted'])
        result['last_value'] = int(result['last_value'])
        n = result['completed']
        if not 0 <= n <= len(STEPS):raise RuntimeError('Invalid kernel cursor')
        return result

    def paused(self):
        state = self.prior() or {}
        if (state.get('boot_id') != self.expected or state.get('schema') != SCHEMA or
                state.get('phase') != 'paused'):
            raise RuntimeError('No acknowledged paused stage; no retry/reload')
        result = self.snapshot()
        n = state['completed']
        next_name = STEPS[n] if n < len(STEPS) else 'prefix-end'
        if (result['failed'] != 'N' or result['released'] != 'N' or
                result['completed'] != n or result['attempted'] != n or
                result['next_operation'] != next_name or
                result['prefix_complete'] != ('Y' if n == len(STEPS) else 'N')):
            raise RuntimeError('Uncertain kernel state; stop and cold power off')
        return result

    def load(self):
        self.preflight()
        if self.prior() or self.b.exists('/sys/module/' + MODULE):
            raise RuntimeError('Already attempted; no reload')
        self.save('loading', 0)
        self.b.run(['insmod', self.bundle + '/' + KO, 'armed=1'])
        self.boot()
        result = self.snapshot()
        if (result['completed'] != 0 or result['attempted'] != 0 or result['failed'] != 'N' or
                result['released'] != 'N' or result['prefix_complete'] != 'N' or
                result['next_operation'] != STEPS[0]):
            raise RuntimeError('Load acknowledgment failed; no retry')
        self.save('paused', 0)
        return result

    def step(self, expected_step, operation):
        self.preflight()
        before = self.paused()
        if (expected_step != before['completed'] + 1 or not 1 <= expected_step <= len(STEPS) or
                operation != STEPS[expected_step - 1]):
            raise RuntimeError('Stale, skipped, terminal or mismatched step; no access')
        self.save('executing', before['completed'], attempted=expected_step, operation=operation)
        self.b.write(PARAM + 'advance', (str(expected_step) + '\n').encode())
        self.boot()
        result = self.snapshot()
        if (result['failed'] != 'N' or result['released'] != 'N' or
                result['completed'] != expected_step or result['attempted'] != expected_step or
                result['next_operation'] != (STEPS[expected_step] if expected_step < len(STEPS) else 'prefix-end') or
                result['prefix_complete'] != ('Y' if expected_step == len(STEPS) else 'N')):
            raise RuntimeError('Stage acknowledgment failed; no retry or cleanup')
        self.save('paused', expected_step)
        return result

    def status(self):
        self.boot()
        return {'state': self.prior(), 'kernel': self.snapshot()}

    def release(self):
        self.preflight()
        result = self.paused()
        self.save('releasing', result['completed'])
        self.b.write(PARAM + 'release_prefix', b'1\n')
        self.boot()
        if self.b.read(PARAM + 'released').strip() != b'Y':
            raise RuntimeError('Release not acknowledged; retain module, cold power off')
        self.b.run(['rmmod', MODULE])
        self.save('released', result['completed'])
        return {'phase': 'released', 'fresh_cold_boot_required_before_any_other_experiment': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('load', 'step', 'status', 'release'))
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-boot', required=True)
    parser.add_argument('--expected-step', type=int)
    parser.add_argument('--operation')
    args = parser.parse_args()
    if args.action == 'step' and (args.expected_step is None or args.operation is None):
        parser.error('step requires --expected-step and --operation; there is no automatic loop')
    if args.action != 'step' and (args.expected_step is not None or args.operation is not None):
        parser.error('step arguments apply only to step')
    lock = Path(STATE).parent / 'lock'
    lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        audit = Audit(Backend(), args.bundle, args.expected_boot)
        result = audit.step(args.expected_step, args.operation) if args.action == 'step' else getattr(audit, args.action)()
        print(json.dumps({'event': 'acknowledged', 'result': result}, indent=2), flush=True)


if __name__ == '__main__':main()
