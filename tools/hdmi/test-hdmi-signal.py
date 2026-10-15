#!/usr/bin/env python3
"""Check service ownership and failure retention without hardware IO."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('signal_owner',Path(__file__).with_name('h713-hdmi-signal.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Signal(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        for name in ('MODULE','DDC','PCM','OWNED'):setattr(m,name,root/name)
        (m.MODULE/'parameters').mkdir(parents=True);m.DDC.mkdir();m.PCM.write_text('closed\n');m.OWNED.write_text('owned')
        self.events=[];self.bad_restore=False;self.failed=False
    def param(self,name):
        stopped=(m.MODULE/'parameters/stop').exists()
        return {'failed':'Y' if self.failed else 'N','ready':'N' if stopped else 'Y','restored':'Y' if stopped and not self.bad_restore else 'N'}[name]
    def command(self,args):
        self.events.append(args)
        if args==['rmmod','h713_hdmi_signal']:shutil.rmtree(m.MODULE)
        elif args==['rmmod','h713_ddc_pins']:shutil.rmtree(m.DDC)
        else:raise AssertionError(args)
    def action(self,action):
        with patch('sys.argv',['signal',action]),patch.object(m,'param',self.param),patch.object(m,'run',self.command):m.main()
    def test_ordered_stop_requires_restoration_before_releasing_ddc(self):
        self.action('stop')
        self.assertEqual(self.events,[['rmmod','h713_hdmi_signal'],['rmmod','h713_ddc_pins']])
        self.assertFalse(m.OWNED.exists())
        self.action('stop') # already stopped is harmless
    def test_busy_failed_or_foreign_resources_never_receive_stop(self):
        for failure in ('busy','failed','foreign'):
            with self.subTest(failure=failure):
                self.setUp()
                if failure=='busy':m.PCM.write_text('state: RUNNING')
                elif failure=='failed':self.failed=True
                else:m.OWNED.unlink()
                with self.assertRaises(RuntimeError):self.action('stop')
                self.assertFalse((m.MODULE/'parameters/stop').exists())
                self.assertTrue(m.DDC.exists());self.assertEqual(self.events,[])
    def test_failed_restore_retains_both_modules_and_ownership(self):
        self.bad_restore=True
        with self.assertRaisesRegex(RuntimeError,'restoration incomplete'):self.action('stop')
        self.assertTrue(m.MODULE.exists() and m.DDC.exists() and m.OWNED.exists())
        self.assertEqual(self.events,[])
    def test_start_rejects_foreign_signal_module(self):
        m.OWNED.unlink()
        with self.assertRaisesRegex(RuntimeError,'not owned'):self.action('start')
        self.assertEqual(self.events,[])

if __name__=='__main__':unittest.main()
