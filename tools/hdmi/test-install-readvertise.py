#!/usr/bin/env python3
"""Drive install-readvertise.sh against a synthetic installed generation."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('install-readvertise.sh')
UNIT = 'h713-hdmi-readvertise.service'
OTHER = ['h713-hdmi-receiver.ko', 'h713-hdmi-signal.py', 'h713-hdmi.scr', 'firmware/h713/hdmi-audio-dsp.bin']


def sums(root, names):
    (root / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256((root / n).read_bytes()).hexdigest() + '  ' + n + '\n' for n in sorted(names)))


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


class Install(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        t = Path(tmp.name)
        self.bundle, self.install, self.state, self.sys, self.units = (t / n for n in ('bundle', 'install', 'state', 'sys', 'units'))
        for d in (self.bundle, self.install, self.state, self.sys, self.units):
            d.mkdir()
        for name in OTHER:
            (self.install / name).parent.mkdir(parents=True, exist_ok=True)
            (self.install / name).write_text('same ' + name)
        self.old = b'old signal module'
        (self.install / 'h713-hdmi-signal.ko').write_bytes(self.old)
        sums(self.install, OTHER + ['h713-hdmi-signal.ko'])
        self.dropins = self.units / 'h713-hdmi-signal.service.d'
        self.dropins.mkdir()
        for d in ('90-start-delay.conf', '95-readvertise-bench.conf', '10-keep.conf'):
            (self.dropins / d).write_text(d)
        (self.units / UNIT).write_text('bench unit')
        for name, text in (('h713-hdmi-signal.ko', 'new signal module'), ('h713-hdmi-readvertise.py', 'service'), (UNIT, 'unit')):
            (self.bundle / name).write_text(text)
        shutil.copy(SCRIPT, self.bundle / 'install-readvertise.sh')
        sums(self.bundle, ['h713-hdmi-signal.ko', 'h713-hdmi-readvertise.py', UNIT, 'install-readvertise.sh'])
        self.pin(self.old)
        self.stub = t / 'systemctl'
        self.stub.write_text(f'#!/bin/sh\necho "$*" >> {t}/systemctl.log\n')
        self.stub.chmod(0o755)

    def pin(self, data):
        text = SCRIPT.read_text()
        old = next(line for line in text.splitlines() if line.startswith('PREVIOUS='))
        (self.bundle / 'install-readvertise.sh').write_text(text.replace(old, 'PREVIOUS=' + hashlib.sha256(data).hexdigest()))
        sums(self.bundle, ['h713-hdmi-signal.ko', 'h713-hdmi-readvertise.py', UNIT, 'install-readvertise.sh'])

    def run_install(self):
        env = {'PATH': '/usr/bin:/bin', 'H713_HDMI_INSTALL': str(self.install), 'H713_HDMI_STATE': str(self.state),
               'H713_HDMI_SYSMODULE': str(self.sys), 'H713_SYSTEMD_UNITS': str(self.units),
               'H713_SYSTEMCTL': str(self.stub)}
        return subprocess.run(['sh', str(self.bundle / 'install-readvertise.sh')], env=env, capture_output=True, text=True)

    def assert_refused(self, reason):
        before = tree(self.install), tree(self.units)
        r = self.run_install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(reason, r.stderr)
        self.assertIn('nothing changed', r.stderr)
        self.assertEqual((tree(self.install), tree(self.units)), before)
        self.assertEqual(list(self.state.iterdir()), [])

    def test_installs_scope_retires_dropins_keeps_backup_and_is_idempotent(self):
        others = {n: (self.install / n).read_bytes() for n in OTHER}
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ('h713-hdmi-signal.ko', 'h713-hdmi-readvertise.py', UNIT):
            self.assertEqual((self.install / name).read_bytes(), (self.bundle / name).read_bytes())
        self.assertEqual((self.units / UNIT).read_text(), 'unit')
        self.assertEqual({n: (self.install / n).read_bytes() for n in OTHER}, others)
        self.assertEqual(sorted(p.name for p in self.dropins.iterdir()), ['10-keep.conf'])
        check = subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=self.install, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(len((self.install / 'SHA256SUMS').read_text().splitlines()), len(OTHER) + 3)
        backup, = self.state.iterdir()
        self.assertEqual((backup / 'h713-hdmi-signal.ko').read_bytes(), self.old)
        self.assertEqual((backup / ('unit.' + UNIT)).read_text(), 'bench unit')
        self.assertEqual(sorted(p.name for p in backup.iterdir() if p.name.startswith('dropin.')),
                         ['dropin.90-start-delay.conf', 'dropin.95-readvertise-bench.conf'])
        log = (self.state.parent / 'systemctl.log').read_text().splitlines()
        self.assertEqual(log, ['daemon-reload', 'enable ' + UNIT])
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('already current', r.stdout)
        self.assertEqual(len(list(self.state.iterdir())), 1)

    def test_refuses_an_unknown_signal_module(self):
        self.pin(b'some other module')
        self.assert_refused('not the pinned predecessor')

    def test_refuses_a_generation_that_fails_its_checksums(self):
        (self.install / 'h713-hdmi-receiver.ko').write_text('tampered')
        self.assert_refused('fails its own checksums')

    def test_refuses_a_failed_loaded_owner(self):
        params = self.sys / 'h713_hdmi_signal/parameters'
        params.mkdir(parents=True)
        (params / 'failed').write_text('Y\n')
        self.assert_refused('loaded signal owner has failed')

    def test_refuses_a_corrupt_bundle(self):
        (self.bundle / 'h713-hdmi-readvertise.py').write_text('corrupt')
        self.assert_refused('bundle checksum mismatch')

    def test_completes_an_interrupted_run(self):
        shutil.copy(self.bundle / 'h713-hdmi-signal.ko', self.install / 'h713-hdmi-signal.ko')  # replaced, sums not yet
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        check = subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=self.install, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == '__main__':
    unittest.main()
