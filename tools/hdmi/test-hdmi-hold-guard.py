#!/usr/bin/env python3
"""Run the systemd-shutdown hold guard against fake module state."""
from pathlib import Path
import subprocess
import tempfile
import unittest

GUARD=Path(__file__).with_name('h713-hdmi-hold-guard')
HOLDS=['h713_hdmi_signal','h713_ddc_pins','h713_scp_probe','h713_hdmi_audio','h713_hdmi_receiver']


class Guard(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);t=Path(tmp.name)
        self.sys,self.calls=t/'sys',t/'calls';self.sys.mkdir()
        for name in ('lamp-off','poweroff'):
            (t/name).write_text(f'#!/bin/sh\necho "{name} $*" >> {self.calls}\n');(t/name).chmod(0o755)
        (self.sys/'sun50i_h713_afbd').mkdir()  # unrelated modules never count
        self.env={'PATH':'/usr/bin:/bin','H713_GUARD_SYSMODULE':str(self.sys),
                  'H713_GUARD_LAMP_OFF':str(t/'lamp-off'),'H713_GUARD_POWEROFF':str(t/'poweroff')}

    def guard(self,verb):
        self.calls.unlink(missing_ok=True)
        r=subprocess.run(['sh',str(GUARD),verb],env=self.env,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        return [line.strip() for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_clean_teardown_leaves_every_verb_alone(self):
        for verb in ('poweroff','halt','reboot','kexec'):
            with self.subTest(verb=verb):self.assertEqual(self.guard(verb),[])

    def test_retained_holds_turn_reboot_and_kexec_into_lamp_off_poweroff(self):
        for module in HOLDS:
            for verb in ('reboot','kexec'):
                with self.subTest(module=module,verb=verb):
                    (self.sys/module).mkdir(exist_ok=True)
                    self.assertEqual(self.guard(verb),['lamp-off poweroff','poweroff'])
                    (self.sys/module).rmdir()

    def test_retained_holds_never_alter_poweroff_or_halt(self):
        for module in HOLDS:(self.sys/module).mkdir()
        for verb in ('poweroff','halt'):
            with self.subTest(verb=verb):self.assertEqual(self.guard(verb),[])


if __name__=='__main__':unittest.main()
