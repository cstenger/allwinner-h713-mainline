#!/usr/bin/env python3
"""Check service ownership and failure retention without hardware IO."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import subprocess

spec=importlib.util.spec_from_file_location('signal_owner',Path(__file__).with_name('h713-hdmi-signal.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Signal(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        for name in ('MODULE','DDC','PCM','OWNED','ATTEMPTED','PROBE','GRAPH'):setattr(m,name,root/name)
        m.GRAPH.write_text('Y\n')
        (m.MODULE/'parameters').mkdir(parents=True);m.DDC.mkdir();m.PCM.write_text('closed\n');m.OWNED.write_text('owned');m.ATTEMPTED.write_text('attempted')
        self.events=[];self.bad_restore=False;self.failed=False;self.init='ready';self.ddc_rmmod_fails=False
    def param(self,name):
        stopped=(m.MODULE/'parameters/stop').exists()
        return {'failed':'Y' if self.failed else 'N','ready':'N' if stopped else 'Y','restored':'Y' if stopped and not self.bad_restore else 'N'}[name]
    def command(self,args):
        self.events.append(args)
        if args==['rmmod','h713_hdmi_signal']:shutil.rmtree(m.MODULE)
        elif args==['rmmod','h713_ddc_pins']:
            if self.ddc_rmmod_fails:raise subprocess.CalledProcessError(1,args)
            shutil.rmtree(m.DDC)
        elif args[0]=='insmod' and args[1].endswith('h713-ddc-pins.ko'):
            self.assertTrue(m.ATTEMPTED.exists()) # latched before the first hold
            m.DDC.mkdir()
        elif args[0]=='insmod' and args[1].endswith('h713-hdmi-signal.ko'):
            # Ownership must be recorded before SCP can be released.
            self.assertTrue(m.OWNED.exists() and m.DDC.exists())
            if self.init=='refused':raise subprocess.CalledProcessError(1,args)
            if self.init=='refused_loaded':
                (m.MODULE/'parameters').mkdir(parents=True);raise subprocess.CalledProcessError(1,args)
            (m.MODULE/'parameters').mkdir(parents=True);self.failed=self.init=='failed'
        else:raise AssertionError(args)
    def action(self,action,*extra):
        with patch('sys.argv',['signal',action,*extra]),patch.object(m,'param',self.param),patch.object(m,'run',self.command):m.main()
    def test_ordered_stop_requires_restoration_before_releasing_ddc(self):
        self.action('stop')
        self.assertEqual(self.events,[['rmmod','h713_hdmi_signal'],['rmmod','h713_ddc_pins']])
        self.assertFalse(m.OWNED.exists() or m.ATTEMPTED.exists())
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
    def fresh(self):
        shutil.rmtree(m.MODULE);shutil.rmtree(m.DDC);m.OWNED.unlink();m.ATTEMPTED.unlink()
    def test_start_claims_ddc_then_releases_scp(self):
        self.fresh();self.action('start')
        self.assertEqual([e[1].rsplit('/',1)[1] for e in self.events],['h713-ddc-pins.ko','h713-hdmi-signal.ko'])
        self.assertTrue(m.OWNED.exists());self.events=[]
        self.action('start') # already ready is harmless
        self.assertEqual(self.events,[])
    def test_start_loads_modules_from_the_named_bundle(self):
        self.fresh();self.action('start','--bundle','/tmp/candidate')
        self.assertEqual([e[1] for e in self.events],['/tmp/candidate/h713-ddc-pins.ko','/tmp/candidate/h713-hdmi-signal.ko'])
        self.fresh();self.events=[];self.action('start')
        self.assertEqual([e[1] for e in self.events],['/usr/lib/h713-hdmi/h713-ddc-pins.ko','/usr/lib/h713-hdmi/h713-hdmi-signal.ko'])
    def test_start_failure_after_scp_release_retains_everything(self):
        self.fresh();self.init='failed'
        with self.assertRaisesRegex(RuntimeError,'holds retained'):self.action('start')
        self.assertTrue(m.MODULE.exists() and m.DDC.exists() and m.OWNED.exists())
        for action in ('start','stop'):
            with self.subTest(action=action),self.assertRaisesRegex(RuntimeError,'cold cycle'):self.action(action)
        self.assertFalse((m.MODULE/'parameters/stop').exists())
        self.assertEqual(len(self.events),2) # no rmmod, no second insmod
    def test_refused_insmod_releases_ddc_so_the_backend_can_park(self):
        # M1: a clean pre-launch failure leaves no HDMI signal hold behind.
        self.fresh();self.init='refused'
        with self.assertRaisesRegex(RuntimeError,'nothing retained'):self.action('start')
        self.assertEqual([e[:2] for e in self.events][-1],['rmmod','h713_ddc_pins'])
        self.assertFalse(m.MODULE.exists() or m.DDC.exists() or m.OWNED.exists())
        self.assertTrue(m.ATTEMPTED.exists());self.events=[]
        with self.assertRaisesRegex(RuntimeError,'already attempted'):self.action('start')
        self.action('stop') # nothing left: the unit's stop is a no-op
        self.assertEqual(self.events,[])
    def test_refused_insmod_keeps_ownership_when_ddc_release_fails(self):
        self.fresh();self.init='refused';self.ddc_rmmod_fails=True
        with self.assertRaisesRegex(RuntimeError,'DDC retained'):self.action('start')
        self.assertTrue(m.DDC.exists() and m.OWNED.exists() and m.ATTEMPTED.exists())
    def test_failed_insmod_with_the_module_loaded_retains_every_hold(self):
        self.fresh();self.init='refused_loaded'
        with self.assertRaisesRegex(RuntimeError,'module loaded; holds retained'):self.action('start')
        self.assertTrue(m.MODULE.exists() and m.DDC.exists() and m.OWNED.exists())
        self.assertNotIn(['rmmod','h713_ddc_pins'],self.events)
    def test_start_after_a_complete_stop_is_allowed(self):
        self.action('stop');self.events=[]
        self.action('start')
        self.assertEqual(len(self.events),2);self.assertTrue(m.OWNED.exists() and m.ATTEMPTED.exists())
    def test_start_refuses_competing_helpers_and_unready_backend(self):
        for case in ('ddc','probe','graph'):
            with self.subTest(case=case):
                self.setUp();self.fresh()
                if case=='ddc':m.DDC.mkdir()
                elif case=='probe':m.PROBE.mkdir()
                else:m.GRAPH.write_text('N\n')
                with self.assertRaises(RuntimeError):self.action('start')
                self.assertEqual(self.events,[]);self.assertFalse(m.OWNED.exists())
    def test_refused_stop_write_retains_ddc_and_ownership(self):
        (m.MODULE/'parameters/stop').mkdir() # write raises OSError
        with self.assertRaisesRegex(RuntimeError,'stop refused.*holds retained'):self.action('stop')
        self.assertTrue(m.MODULE.exists() and m.DDC.exists() and m.OWNED.exists())
        self.assertEqual(self.events,[])
    def test_stop_after_signal_unloaded_releases_remaining_ddc(self):
        shutil.rmtree(m.MODULE);self.action('stop')
        self.assertEqual(self.events,[['rmmod','h713_ddc_pins']]);self.assertFalse(m.OWNED.exists())

if __name__=='__main__':unittest.main()
