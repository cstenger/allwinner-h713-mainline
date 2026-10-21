#!/usr/bin/env python3
"""Logo-free DSP bench: prepare access separately from one-shot version reads.

Run on the board. No boot/reset, firmware launch, patch load or graph write.
A failed operation consumes this boot. Inspect or power off; never retry.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess

MODULE = 'h713_hdmi_dsp_observe'
PARAM = '/sys/module/' + MODULE + '/parameters/'
GUARD = '/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard'
STATE = '/run/h713-dsp-observe/state.json'
COMPETITORS = ('h713_hdmi_receiver', 'h713_hdmi_audio', 'h713_hdmi_signal',
               'h713_ddc_pins', 'h713_scp_probe', 'h713_hdmi_dsp_probe',
               'h713_tvfe_bench', 'h713_hdmi_power', 'h713_hdmi_tvfe_hold',
               'h713_edid_clock')


class Backend:
    def read(self, path):return Path(path).read_bytes()
    def exists(self, path):return Path(path).exists()
    def write(self, path, value):Path(path).write_bytes(value)
    def save(self, value):
        path = Path(STATE)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')
    def run(self, argv):
        return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True).stdout


class Observation:
    def __init__(self, backend, bundle, expected_boot):
        self.b, self.bundle, self.expected = backend, str(bundle), expected_boot

    def boot(self):
        actual = self.b.read('/proc/sys/kernel/random/boot_id').decode().strip()
        if actual != self.expected:raise RuntimeError('Unexpected boot; no action')
        return actual

    def prior(self):
        return json.loads(self.b.read(STATE)) if self.b.exists(STATE) else None

    def save(self, phase):self.b.save({'boot_id': self.expected, 'phase': phase, 'cold_boot_required': True})
    def param(self, name):return self.b.read(PARAM + name).decode().strip()

    def prepare(self):
        self.boot()
        if self.prior() or self.b.exists('/sys/module/' + MODULE):
            raise RuntimeError('Observation already attempted; no reload/retry')
        if self.b.exists('/proc/device-tree/chosen/h713,hdmi-boot-v1'):
            raise RuntimeError('HDMI handoff present; requires logo-free boot')
        if self.b.read('/proc/device-tree/chosen/h713,dsp-observation-v1') != bytes.fromhex('44535031'):
            raise RuntimeError('Missing observation boot marker')
        for node in ('display@5600000', 'cpu-comm@3003000'):
            if self.b.read('/proc/device-tree/soc/' + node + '/status') != b'disabled\0':
                raise RuntimeError('Competing hardware probe not disabled: ' + node)
        if self.b.exists('/dev/cpu_comm_fd'):
            raise RuntimeError('CPU_COMM device exists on observation boot')
        for name in COMPETITORS:
            if self.b.exists('/sys/module/' + name):raise RuntimeError('Competing owner: ' + name)
        for unit in ('capture', 'signal', 'speaker'):
            state = self.b.run(['systemctl', 'show', 'h713-hdmi-' + unit + '.service', '-p', 'ActiveState', '--value']).strip()
            if state != 'inactive':raise RuntimeError('HDMI service active or failed: ' + unit)
        manifest = json.loads(self.b.read(self.bundle + '/manifest.json'))
        for path, digest in ((self.bundle + '/h713-hdmi-dsp-observe.ko', manifest['module_sha256']),
                             (GUARD, manifest['guard_sha256'])):
            if hashlib.sha256(self.b.read(path)).hexdigest() != digest:
                raise RuntimeError('Pinned file mismatch: ' + path)
        release = self.b.run(['uname', '-r']).strip()
        vermagic = self.b.run(['modinfo', '-F', 'vermagic', self.bundle + '/h713-hdmi-dsp-observe.ko']).split()[0]
        if release != manifest['kernel_release'] or vermagic != release:
            raise RuntimeError('Kernel/module ABI mismatch')
        self.boot()
        self.save('attempted')
        self.b.run(['insmod', self.bundle + '/h713-hdmi-dsp-observe.ko', 'armed=1'])
        if self.param('failed') != 'N' or self.param('ready') != 'Y' or self.param('attempted') != 'N':
            raise RuntimeError('Access setup failed; retain holds and cold power off')
        self.save('prepared')
        return {'phase': 'prepared', 'DSP_commands_issued': 0}

    def versions(self):
        self.boot()
        prior = self.prior() or {}
        if prior.get('boot_id') != self.expected or prior.get('phase') != 'prepared':
            raise RuntimeError('No fresh prepared observation')
        if self.param('failed') != 'N' or self.param('ready') != 'Y' or self.param('attempted') != 'N':
            raise RuntimeError('Observation not eligible; no retry')
        self.save('reading')
        self.b.write(PARAM + 'probe_versions', b'1\n')
        if self.param('failed') != 'N' or self.param('attempted') != 'Y':
            raise RuntimeError('DSP read failed; retain holds and cold power off')
        result = {'phase': 'observed', 'version0_raw': int(self.param('version0')),
                  'version1_raw': int(self.param('version1')),
                  'scope': 'after controlled access setup; not pristine reset-entry state'}
        self.save('observed')
        return result

    def restore(self):
        self.boot()
        prior = self.prior() or {}
        if prior.get('boot_id') != self.expected or prior.get('phase') not in ('prepared', 'observed'):
            raise RuntimeError('No successful setup/observation to restore')
        if self.param('failed') != 'N':raise RuntimeError('Failure latch set; cold power off')
        self.save('restoring')
        self.b.write(PARAM + 'restore', b'1\n')
        if self.param('failed') != 'N' or self.param('released') != 'Y':
            raise RuntimeError('Restore failed; cold power off')
        self.b.run(['rmmod', MODULE])
        self.save('restored')
        return {'phase': 'restored', 'cold_boot_required': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'versions', 'restore'))
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--expected-boot', required=True)
    args = parser.parse_args()
    lock = Path(STATE).parent / 'lock'
    lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = getattr(Observation(Backend(), args.bundle, args.expected_boot), args.action)()
        print(json.dumps(result, indent=2))


if __name__ == '__main__':main()
