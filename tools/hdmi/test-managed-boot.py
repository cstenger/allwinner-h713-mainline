#!/usr/bin/env python3
"""Guard the actual cold-boot sequence using fixture command responses."""
import importlib.util
import unittest
import tempfile
import json
from pathlib import Path
spec=importlib.util.spec_from_file_location('boot',Path(__file__).with_name('boot-managed-audio.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class FakeSerial:
    def __init__(self,override=None):self.commands=[];self.override=override or {}
    def call(self,command,timeout=20):
        self.commands.append(command)
        if command in self.override:return self.override[command]
        fixed={'version':'U-Boot 2026.07-rc5\n=> ','md.l 0x0306101c 1':'0306101c: 00000000\n=> ',
            'h713_disp mips-comm-trace 0x34':'firmware identity accepted\nfirmware readiness proven by MIPS READY\napplication readiness proven\n=> ',
            'h713_disp commdev':'chan=0000 pid=8b8f275c foo <== LIVE\n=> ',
            'h713_disp commcall eaf13de5 chan=0 pid=8b8f275c 3':'MIPS sender completed RETURN\nRETURN_ACK publication consumed\n=> ',
            'h713_disp commtrace':'transition-complete=1 worker-new=00000003\n=> ',
            'fatload mmc 1:2 0x50000000 h713-kernel.fit':'7789216 bytes read\n=> ',
            'printenv hdmi_trial_fdt_size':'hdmi_trial_fdt_size=8319\n=> ',
            'printenv hdmi_trial_fdt':'hdmi_trial_fdt=50001000\n=> ',
            'fdt print /soc/audio-bridge@203042c interrupts':'<0x00000000 0x00000073 0x00000004 0x00000000 0x00000071 0x00000004>\n=> ',
            'bootm 0x50000000 - 0x4f000000':'Linux version 6.18.38'}
        return fixed.get(command,'=> ')


class Boot(unittest.TestCase):
    def test_exact_sequence_has_one_launch_and_ram_only_irq_fix(self):
        serial=FakeSerial();markers=[];result=m.boot(serial,lambda:markers.append(len(serial.commands)))
        self.assertTrue(result['source3_verified']);self.assertEqual(markers,[2])
        self.assertEqual(serial.commands.count('h713_disp mips-comm-trace 0x34'),1)
        self.assertFalse(any('saveenv' in c or 'reset' in c or 'mmc write' in c for c in serial.commands))
    def test_alive_core_rejected_before_launch(self):
        serial=FakeSerial({'md.l 0x0306101c 1':'0306101c: 00000001'})
        with self.assertRaises(RuntimeError):m.boot(serial,lambda:self.fail('attempt marker should not be written'))
        self.assertEqual(len(serial.commands),2)
    def test_bad_guards_do_not_continue_to_boot(self):
        cases={'h713_disp commdev':'chan=0000 pid=00000000 <== LIVE',
               'h713_disp commtrace':'transition-complete=0 worker-new=00000003',
               'fatload mmc 1:2 0x50000000 h713-kernel.fit':'10 bytes read',
               'printenv hdmi_trial_fdt_size':'hdmi_trial_fdt_size=1000',
               'printenv hdmi_trial_fdt':'hdmi_trial_fdt=4f000000'}
        for command,text in cases.items():
            serial=FakeSerial({command:text})
            with self.assertRaises(RuntimeError):m.boot(serial,lambda:None)
            self.assertEqual(serial.commands[-1],command)
            self.assertNotIn('bootm 0x50000000 - 0x4f000000',serial.commands)
    def test_size_guard_resume_never_launches_or_repeats_source_call(self):
        with tempfile.TemporaryDirectory() as directory:
            prior=Path(directory)
            original=FakeSerial()
            m.boot(original,lambda:None)
            for i,command in enumerate(original.commands[:10],1):
                (prior/f'{i:02d}-serial.log').write_text(original.call(command))
            (prior/'mips-launch-attempted').write_text('attempted')
            (prior/'result.json').write_text(json.dumps({'pass':False,'error':'unexpected FIT FDT size'}))
            current=FakeSerial({'md.l 0x0306101c 1':'0306101c: 00000001'})
            result=m.resume(current,prior)
            self.assertEqual(result['fdt_bytes'],33561)
            self.assertFalse(any('mips-comm-trace' in c or 'commcall' in c for c in current.commands))
            changed=FakeSerial({'md.l 0x0306101c 1':'0306101c: 00000001','h713_disp commdev':'chan=0000 pid=8b111111 <== LIVE'})
            with self.assertRaises(RuntimeError):m.resume(changed,prior)
            self.assertFalse(any('fatload' in c for c in changed.commands))

    def test_opt_in_parking_consumer_is_checked_before_linux(self):
        responses={
          'printenv hdmi_shutdown_ccu':'hdmi_shutdown_ccu=4',
          'fdt print /soc/hdmi-mips-shutdown resets':'<0x00000004 0x00000001 0x00000004 0x00000002 0x00000004 0x00000003>',
          'fdt print /soc/hdmi-mips-shutdown clocks':'<0x00000004 0x00000013 0x00000004 0x00000014>'}
        serial=FakeSerial(responses)
        result=m.boot(serial,lambda:None,park_capable=True)
        self.assertTrue(result['park_capable'])
        self.assertEqual(serial.commands.count('h713_disp mips-comm-trace 0x34'),1)
        self.assertTrue(any('fdt mknode /soc hdmi-mips-shutdown'==c for c in serial.commands))
        responses['fdt print /soc/hdmi-mips-shutdown resets']='wrong reset lines'
        serial=FakeSerial(responses)
        with self.assertRaises(RuntimeError):m.boot(serial,lambda:None,park_capable=True)
        self.assertNotIn('bootm 0x50000000 - 0x4f000000',serial.commands)

    def test_shutdown_dropin_is_installed_only_for_parking_boots(self):
        for enabled in (False,True):
            commands=[]
            def remote(command,name,**kwargs):commands.append((command,name))
            m.configure_service(remote,enabled)
            setup=commands[0][0]
            if enabled:
                self.assertIn('mkdir -p /run/systemd/system/h713-hdmi-capture.service.d',setup)
                self.assertIn('cp '+m.BASE+'/h713-hdmi-capture-shutdown.conf',setup)
            else:self.assertTrue(setup.startswith('test ! -e '))
            final=commands[-1][0]
            self.assertLess(final.index('systemd-analyze verify'),final.index('systemctl start'))
            self.assertNotIn('/etc/',setup+final)

    def test_ambiguous_channel_rejected(self):
        with self.assertRaises(RuntimeError):m.live_pid('chan=0000 pid=8b111111 <== LIVE\nchan=0000 pid=8b222222 <== LIVE')


if __name__=='__main__':unittest.main()
