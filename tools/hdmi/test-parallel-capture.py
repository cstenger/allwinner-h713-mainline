#!/usr/bin/env python3
"""Check real unit ordering, including shutdown, without starting services."""
import configparser
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCES = {'h713-hdmi-capture.service': 'h713-hdmi-capture-startup.service',
           **{f'h713-hdmi-{name}.service': f'h713-hdmi-{name}.service'
              for name in ('prepare', 'signal', 'ring', 'video', 'speaker')}}


def read_units():
    units = {}
    for name, source in SOURCES.items():
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.read_string((HERE/source).read_text())
        units[name] = config
    return units


def predecessors(units, name):
    return units[name]['Unit'].get('After', '').split()


class Ordering(unittest.TestCase):
    def test_parallel_start_preserves_lifecycle_and_signal_gates(self):
        units = read_units()
        def ancestors(name, path=()):
            if name in path: raise AssertionError('ordering cycle: '+str((*path, name)))
            result = set(predecessors(units, name)) if name in units else set()
            for parent in list(result): result |= ancestors(parent, (*path, name))
            return result
        prepare = 'h713-hdmi-prepare.service'
        capture = 'h713-hdmi-capture.service'
        self.assertNotIn('user@1000.service', ancestors(prepare))
        self.assertIn('systemd-modules-load.service', ancestors(prepare))
        # These startup edges reverse at stop: consumers before capture,
        # capture before user-session teardown and the inert prepare unit.
        self.assertIn('user@1000.service', ancestors(capture))
        self.assertIn(prepare, units[capture]['Unit']['Requires'].split())
        self.assertIn(prepare, ancestors(capture))
        for consumer in ('signal', 'ring', 'video', 'speaker'):
            self.assertIn(capture, ancestors(f'h713-hdmi-{consumer}.service'))
        self.assertIn('user@1000.service', ancestors('h713-hdmi-speaker.service'))
        self.assertIn('shutdown --bundle', units[capture]['Service']['ExecStop'])
        self.assertNotIn('ExecStop', units[prepare]['Service'])
        self.assertEqual(units[prepare]['Unit']['ConditionPathExists'],
                         units[capture]['Unit']['ConditionPathExists'])
        # prepare does the one guarded start; capture's start is a no-op
        # (prepare already verified and saved "ready"), it owns teardown.
        self.assertIn('session.py start --bundle', units[prepare]['Service']['ExecStart'])
        self.assertIn('--boot-handoff', units[prepare]['Service']['ExecStart'])
        self.assertEqual(units[capture]['Service']['ExecStart'], '/usr/bin/true')
        self.assertNotIn('Install', units[prepare])

    @unittest.skipUnless(shutil.which('systemd-analyze'), 'systemd-analyze required')
    def test_native_systemd_verification_of_combined_units(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); units = root/'etc/systemd/system'; units.mkdir(parents=True)
            for name, source in SOURCES.items():
                (units/name).write_bytes((HERE/source).read_bytes())
            for target in ('sysinit', 'basic', 'shutdown', 'multi-user'):
                (units/f'{target}.target').write_text('[Unit]\nDescription=Offline target\n')
            for name in ('user@1000.service', 'systemd-modules-load.service'):
                (units/name).write_text('[Service]\nExecStart=/usr/bin/python3\n')
            for binary in ('usr/bin/python3', 'usr/bin/true', 'usr/bin/gst-launch-1.0', 'sbin/insmod', 'sbin/rmmod',
                           'usr/lib/h713-hdmi-speaker/enable-mixer.sh'):
                path = root/binary;path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# never executed: offline unit verification fixture\n');path.chmod(0o755)
            result = subprocess.run(['systemd-analyze', f'--root={root}', '--generators=no',
                                     '--man=no', 'verify', *SOURCES],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__': unittest.main()
