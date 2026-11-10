#!/usr/bin/env python3
"""Run standby lifecycle regressions against a private sysfs/service model."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_name('h713-standby').read_text()


class Standby(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / 'run'
        self.lamp = self.root / 'lamp'
        self.policy = self.root / 'policy'
        self.bin = self.root / 'bin'
        for p in (self.lamp, self.policy, self.bin):
            p.mkdir()
        (self.lamp / 'bl_power').write_text('0\n')
        (self.policy / 'scaling_max_freq').write_text('1296000\n')
        (self.policy / 'cpuinfo_min_freq').write_text('480000\n')
        for name, body in {'pkill': 'exit 1', 'pgrep': 'exit 1', 'logger': 'exit 0'}.items():
            self.command(name, body)
        self.helper = self.bin / 'ramp'
        self.command('ramp', f'printf "0\\n" > "{self.lamp}/bl_power"')
        source = SOURCE.replace('RUN=/run/h713-standby', f'RUN={self.run}')
        source = source.replace('LAMP=/sys/class/backlight/lamp', f'LAMP={self.lamp}')
        source = source.replace('POLICY=/sys/devices/system/cpu/cpufreq/policy0', f'POLICY={self.policy}')
        source = source.replace('LAMP_RAMP=/usr/local/bin/h713-lamp-ramp', f'LAMP_RAMP={self.helper}')
        self.script = self.root / 'standby'
        self.script.write_text(source)

    def command(self, name, body):
        p = self.bin / name
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)

    def invoke(self, command, expected=0):
        result = subprocess.run(['sh', str(self.script), command], capture_output=True,
                                text=True, env={**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH']})
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_toggle_restores_original_cpu_limit_and_lamp(self):
        self.invoke('toggle')
        self.assertEqual((self.lamp / 'bl_power').read_text().strip(), '4')
        self.assertEqual((self.policy / 'scaling_max_freq').read_text().strip(), '480000')
        self.invoke('on')  # repeated enter must not overwrite the saved limit
        self.invoke('toggle')
        self.assertEqual((self.run / 'state').read_text().strip(), 'off')
        self.assertEqual((self.lamp / 'bl_power').read_text().strip(), '0')
        self.assertEqual((self.policy / 'scaling_max_freq').read_text().strip(), '1296000')

    def test_failed_ramp_retains_standby_and_cpu_cap(self):
        self.invoke('on')
        self.command('ramp', 'exit 1')
        self.invoke('off', 1)
        self.assertEqual((self.run / 'state').read_text().strip(), 'on')
        self.assertEqual((self.lamp / 'bl_power').read_text().strip(), '4')
        self.assertEqual((self.policy / 'scaling_max_freq').read_text().strip(), '480000')

    def test_missing_helper_refuses_entry_before_switching_lamp(self):
        self.helper.unlink()
        self.invoke('on', 1)
        self.assertEqual((self.lamp / 'bl_power').read_text().strip(), '0')
        self.assertFalse((self.run / 'state').exists())


if __name__ == '__main__':
    unittest.main()
