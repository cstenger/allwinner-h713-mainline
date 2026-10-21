#!/usr/bin/env python3
"""One explicit staged-access step per invocation; never run a stage loop.

A failed/uncertain operation consumes this boot. No AudioTop/DSP access,
reset or reboot. Crossing a stage boundary needs a read-only `snapshot`
and then `--stage-ack <stage>`. From step 41 on, the only supported end is
an orderly poweroff with the module loaded; `release` is refused.
This helper must be staged with the guard and a pinned manifest.
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
SCHEMA = 'h713-dsp-access-ext-v1'
PPU_NODE = '/proc/device-tree/soc/power-controller@7001014/'
# INIT/BEGIN/DONE are pr_notice (level 5); the console prints levels strictly
# below its threshold, and the rootfs default is 5 (warnings only).
CONSOLE_MIN = 6
COMPETITORS = ('h713_hdmi_receiver', 'h713_hdmi_audio', 'h713_hdmi_signal',
               'h713_ddc_pins', 'h713_scp_probe', 'h713_hdmi_dsp_probe',
               'h713_tvfe_bench', 'h713_hdmi_power', 'h713_hdmi_tvfe_hold',
               'h713_edid_clock', 'h713_hdmi_dsp_observe')
CLOCKS = ('pll-video0', 'pll-adc', 'bus-tvcap', 'bus-cap-300m', 'vincap-dma',
          'tvfe-1296m', 'bus-hdmi-audio', 'hdmi-audio', 'audio-cpu', 'audio-umac',
          'audio-ihb', 'pll-video2', 'deint', 'panel', 'svp-dtl', 'afbd', 'bus-disp')
STEPS = (
    'claim-dsp-port', 'claim-lock-window', 'claim-audiotop', 'claim-scp-reset',
    'map-mips-status', 'map-scp-reset', 'map-tv-ccu', 'map-display-ccu',
    'read-mips-stopped', 'read-scp-stopped', 'read-demod-bus', 'read-display-bus',
    'get-display-reset', 'read-display-reset', 'get-demod-reset', 'read-demod-reset',
    *('get-clock-' + c for c in CLOCKS),
    'map-ppu-status', 'read-ppu-tvfe-status', 'read-ppu-tvcap-status',
    'get-tvcap-reset', 'read-tvcap-reset', 'census-clock-enabled', 'read-tv-ccu-words',
    'attach-tvfe', 'resume-tvfe', 'attach-tvcap', 'resume-tvcap',
    'recheck-stopped-after-power',
    'deassert-tvcap-reset-if-asserted',
    *('enable-clock-' + c for c in CLOCKS[2:6]),
    'deassert-demod-reset',
    *('enable-clock-' + c for c in CLOCKS[0:2]),
    *('write-tv-word-' + w for w in ('d10', 'd20', 'd24', 'd28', 'd2c', 'd30', 'd34',
                                     'd38', 'd40', 'd48', 'd4c', 'd50', 'd58', 'd5c', 'd60')),
    'set-demod-bus-gate',
    *('enable-clock-' + c for c in CLOCKS[6:11]),
    *('enable-clock-' + c for c in CLOCKS[11:17]),
    'deassert-display-reset-if-asserted',
    'final-recheck')
PREFIX_STEPS = 33
LAST_READ_ONLY_STEP = 40
# Completing the step on the left ends the named stage. The next step needs
# a snapshot taken at that cursor plus --stage-ack <name>.
STAGES = {33: 'prefix', 40: 'census', 45: 'power', 53: 'receiver',
          69: 'tvfe-words', 74: 'audio', 81: 'display'}
SNAPSHOTS = ('/sys/kernel/debug/clk/clk_summary', '/sys/kernel/debug/pm_genpd/pm_genpd_summary')


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
        try:
            Path(path).write_bytes(value)
        except OSError as error:
            self.note('write-failed', path=path, errno=error.errno, error=str(error))
            raise
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


def next_name(n):
    return STEPS[n] if n < len(STEPS) else 'extension-end'


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
        if (not self.b.exists('/proc/device-tree/chosen/h713,dsp-observation-v2') or
                self.b.read('/proc/device-tree/chosen/h713,dsp-observation-v2') != bytes.fromhex('44535032')):
            raise RuntimeError('Not a boot-v4 maintenance boot (v2 marker missing)')
        if self.b.exists(PPU_NODE + 'allwinner,keep-tvcap-on'):
            raise RuntimeError('TVCAP retention flag present; genpd TVCAP state would not reflect hardware')
        for node in ('display@5600000', 'cpu-comm@3003000'):
            if self.b.read('/proc/device-tree/soc/' + node + '/status') != b'disabled\0':
                raise RuntimeError('Competing DT node is not disabled: ' + node)
        printk = self.b.read('/proc/sys/kernel/printk').split()
        if not printk or not printk[0].isdigit() or int(printk[0]) < CONSOLE_MIN:
            raise RuntimeError('Console threshold hides UART BEGIN/DONE markers; run dmesg -n 7 first')
        # panic=5 on the cmdline would warm-reboot past the shutdown guard.
        if self.b.read('/proc/sys/kernel/panic').strip() != b'0':
            raise RuntimeError('Panic would auto-reboot; run sysctl kernel.panic=0 first')
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

    def snapshot_kernel(self):
        result = {name: self.b.read(PARAM + name).decode().strip() for name in
                  ('failed', 'released', 'prefix_complete', 'extension_available',
                   'extension_complete', 'completed', 'attempted', 'next_operation',
                   'last_value')}
        for key in ('completed', 'attempted', 'last_value'):
            result[key] = int(result[key])
        if not 0 <= result['completed'] <= len(STEPS):raise RuntimeError('Invalid kernel cursor')
        return result

    def expect(self, result, n):
        return (result['failed'] == 'N' and result['released'] == 'N' and
                result['extension_available'] == 'Y' and
                result['completed'] == n and result['attempted'] == n and
                result['next_operation'] == next_name(n) and
                result['prefix_complete'] == ('Y' if n >= PREFIX_STEPS else 'N') and
                result['extension_complete'] == ('Y' if n == len(STEPS) else 'N'))

    def paused(self):
        state = self.prior() or {}
        if (state.get('boot_id') != self.expected or state.get('schema') != SCHEMA or
                state.get('phase') != 'paused'):
            raise RuntimeError('No acknowledged paused stage; no retry/reload')
        result = self.snapshot_kernel()
        if not self.expect(result, state['completed']):
            raise RuntimeError('Uncertain kernel state; stop and cold power off')
        return state, result

    def load(self):
        self.preflight()
        if self.prior() or self.b.exists('/sys/module/' + MODULE):
            raise RuntimeError('Already attempted; no reload')
        self.save('loading', 0)
        self.b.run(['insmod', self.bundle + '/' + KO, 'armed=1'])
        self.boot()
        result = self.snapshot_kernel()
        if not self.expect(result, 0):
            raise RuntimeError('Load acknowledgment failed; no retry')
        self.save('paused', 0)
        return result

    def step(self, expected_step, operation, stage_ack=None):
        self.preflight()
        state, before = self.paused()
        n = before['completed']
        if (expected_step != n + 1 or not 1 <= expected_step <= len(STEPS) or
                operation != STEPS[expected_step - 1]):
            raise RuntimeError('Stale, skipped, terminal or mismatched step; no access')
        if n in STAGES:
            if stage_ack != STAGES[n] or state.get('snapshot_at') != n:
                raise RuntimeError('Stage boundary: take a snapshot, review it, then pass --stage-ack '
                                   + STAGES[n] + '; no access')
        elif stage_ack is not None:
            raise RuntimeError('No stage boundary here; --stage-ack refused')
        self.save('executing', n, attempted=expected_step, operation=operation)
        self.b.write(PARAM + 'advance', (str(expected_step) + '\n').encode())
        self.boot()
        result = self.snapshot_kernel()
        if not self.expect(result, expected_step):
            raise RuntimeError('Stage acknowledgment failed; no retry or cleanup')
        if expected_step == LAST_READ_ONLY_STEP:
            result['tv_words'] = self.b.read(PARAM + 'tv_words').decode().strip()
            result['tvcap_reset_before'] = int(self.b.read(PARAM + 'tvcap_reset_before'))
        self.save('paused', expected_step)
        return result

    def snapshot(self):
        """Read-only clock/genpd census at a stage boundary; records the cursor."""
        self.preflight()
        state, result = self.paused()
        n = result['completed']
        if n not in STAGES:raise RuntimeError('Snapshots are taken at stage boundaries only')
        captured = {path: self.b.read(path).decode(errors='replace') for path in SNAPSHOTS}
        self.save('paused', n, snapshot_at=n)
        return {'stage_complete': STAGES[n], 'kernel': result, 'snapshots': captured}

    def status(self):
        self.boot()
        return {'state': self.prior(), 'kernel': self.snapshot_kernel()}

    def release(self):
        self.preflight()
        state, result = self.paused()
        if result['completed'] > LAST_READ_ONLY_STEP:
            raise RuntimeError('Hardware state changed (step > 40): no software restore; '
                               'orderly poweroff with the module loaded is the only end')
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
    parser.add_argument('action', choices=('load', 'step', 'snapshot', 'status', 'release'))
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-boot', required=True)
    parser.add_argument('--expected-step', type=int)
    parser.add_argument('--operation')
    parser.add_argument('--stage-ack')
    args = parser.parse_args()
    if args.action == 'step' and (args.expected_step is None or args.operation is None):
        parser.error('step requires --expected-step and --operation; there is no automatic loop')
    if args.action != 'step' and (args.expected_step is not None or args.operation is not None
                                  or args.stage_ack is not None):
        parser.error('step arguments apply only to step')
    lock = Path(STATE).parent / 'lock'
    lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        audit = Audit(Backend(), args.bundle, args.expected_boot)
        if args.action == 'step':
            result = audit.step(args.expected_step, args.operation, args.stage_ack)
        else:
            result = getattr(audit, args.action)()
        print(json.dumps({'event': 'acknowledged', 'result': result}, indent=2), flush=True)


if __name__ == '__main__':main()
