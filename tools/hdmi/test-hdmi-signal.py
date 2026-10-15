#!/usr/bin/env python3
"""Check service ownership and failure retention without hardware IO."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import errno
import signal

spec=importlib.util.spec_from_file_location('signal_owner',Path(__file__).with_name('h713-hdmi-signal.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Signal(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        for name in ('MODULE','DDC','OWNED','ATTEMPTED','PROBE','GRAPH','NO_RECLAIM'):setattr(m,name,root/name)
        m.GRAPH.write_text('Y\n')
        (m.MODULE/'parameters').mkdir(parents=True);m.DDC.mkdir();m.OWNED.write_text('owned');m.ATTEMPTED.write_text('attempted')
        self.events=[];self.bad_restore=False;self.failed=False;self.init='ready';self.ddc_rmmod_fails=False
        self.ddc_release=True # current helper; False models one without the parameter
        if self.ddc_release:(m.DDC/'parameters').mkdir();(m.DDC/'parameters/release').write_text('')
        # Capture device model: consumers hold it (pids) or something we
        # cannot see holds it (foreign_busy); graph_ready N gives EAGAIN.
        self.pids=[];self.foreign_busy=False;self.not_ready=False;self.ignores_term=set()
        self.shutdown=False;self.kills=[];self.holding=None;self.clock=0.0
        self.recover='refused' # an init failure the module will not undo
        self.opens=0
    def open_capture(self,dev):
        self.assertFalse((m.MODULE/'parameters/stop').is_file()) # held before the stop is written
        if self.not_ready:raise OSError(errno.EAGAIN,'Resource temporarily unavailable')
        if self.pids or self.foreign_busy:raise OSError(errno.EBUSY,'Device or resource busy')
        self.holding=True;self.opens+=1;return 99
    def close_capture(self,fd):
        self.assertEqual(fd,99);self.assertTrue(self.holding)
        self.assertTrue((m.MODULE/'parameters/stop').exists()) # released after the stop
        self.holding=False
    def kill(self,pid,sig):
        self.kills.append((pid,sig))
        if not (sig==signal.SIGTERM and pid in self.ignores_term) and pid in self.pids:self.pids.remove(pid)
    def sleep(self,seconds):self.clock+=seconds
    def param(self,name):
        stopped=(m.MODULE/'parameters/stop').is_file()
        failed=self.failed and not (stopped and self.recover in ('2','3'))
        ready='N' if stopped or self.failed else 'Y'
        return {'failed':'Y' if failed else 'N','ready':ready,'restored':'Y' if stopped and not self.bad_restore else 'N',
                'recovery':self.recover if stopped and self.recover in ('2','3') else '0'}[name]
    def command(self,args):
        self.events.append(args)
        if args==['rmmod','h713_hdmi_signal']:shutil.rmtree(m.MODULE)
        elif args==['rmmod','h713_ddc_pins']:
            if self.ddc_rmmod_fails:raise subprocess.CalledProcessError(1,args)
            # A pinned helper refuses rmmod until a verified release.
            release=m.DDC/'parameters/release'
            if release.exists():self.assertEqual(release.read_text(),'1\n')
            shutil.rmtree(m.DDC)
        elif args[0]=='insmod' and args[1].endswith('h713-ddc-pins.ko'):
            self.assertTrue(m.ATTEMPTED.exists()) # latched before the first hold
            m.DDC.mkdir();(m.DDC/'parameters').mkdir();(m.DDC/'parameters/release').write_text('')
        elif args[0]=='insmod' and args[1].endswith('h713-hdmi-signal.ko'):
            # Ownership must be recorded before SCP can be released.
            self.assertTrue(m.OWNED.exists() and m.DDC.exists())
            if self.init=='refused':raise subprocess.CalledProcessError(1,args)
            if self.init=='refused_loaded':
                (m.MODULE/'parameters').mkdir(parents=True);raise subprocess.CalledProcessError(1,args)
            (m.MODULE/'parameters').mkdir(parents=True);self.failed=self.init=='failed'
            if self.failed and self.recover=='refused':(m.MODULE/'parameters/stop').mkdir() # module refuses: EPERM
        else:raise AssertionError(args)
    def action(self,action,*extra):
        with patch('sys.argv',['signal',action,*extra]),patch.object(m,'param',self.param),patch.object(m,'run',self.command),\
             patch.object(m,'capture_device',lambda:Path('/dev/snd/pcmC1D0c')),patch.object(m,'open_capture',self.open_capture),\
             patch.object(m,'close_capture',self.close_capture),patch.object(m,'holders',lambda dev:list(self.pids)),\
             patch.object(m,'kill',self.kill),patch.object(m,'shutting_down',lambda:self.shutdown),\
             patch.object(m.time,'sleep',self.sleep),patch.object(m.time,'monotonic',lambda:self.clock):m.main()
    def test_ordered_stop_requires_restoration_before_releasing_ddc(self):
        self.action('stop')
        self.assertEqual(self.events,[['rmmod','h713_hdmi_signal'],['rmmod','h713_ddc_pins']])
        self.assertFalse(m.OWNED.exists() or m.ATTEMPTED.exists())
        self.action('stop') # already stopped is harmless
    def test_busy_failed_or_foreign_resources_never_receive_stop(self):
        for failure in ('busy','failed','foreign'):
            with self.subTest(failure=failure):
                self.setUp()
                if failure=='busy':self.pids=[4242]
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
    def test_init_failure_from_a_proven_state_is_undone_and_releases_everything(self):
        for state in ('2','3'):
            with self.subTest(state=state):
                self.setUp();self.fresh();self.init='failed';self.recover=state
                with self.assertRaisesRegex(RuntimeError,f'undone from proven state {state}, nothing retained'):self.action('start')
                self.assertEqual([e[0]+' '+e[1].rsplit('/',1)[-1] for e in self.events],
                                 ['insmod h713-ddc-pins.ko','insmod h713-hdmi-signal.ko','rmmod h713_hdmi_signal','rmmod h713_ddc_pins'])
                self.assertFalse(m.MODULE.exists() or m.DDC.exists() or m.OWNED.exists())
                self.assertTrue(m.ATTEMPTED.exists());self.assertEqual(self.opens,1);self.assertFalse(self.holding)
                self.events=[]
                with self.assertRaisesRegex(RuntimeError,'already attempted'):self.action('start')
    def test_bench_signal_args_reach_the_insmod(self):
        self.fresh();self.action('start','--signal-arg','fault=2')
        self.assertEqual(self.events[1][2:],['armed=1','fault=2'])
        self.fresh();self.events=[];self.action('start')
        self.assertEqual(self.events[1][2:],['armed=1'])
    def test_init_failure_recovery_waits_for_no_capture(self):
        self.fresh();self.init='failed';self.recover='3';self.pids=[4242]
        with self.assertRaisesRegex(RuntimeError,'capture is open'):self.action('start')
        self.assertTrue(m.MODULE.exists() and m.DDC.exists() and m.OWNED.exists());self.assertEqual(self.kills,[])
    def test_start_failure_after_scp_release_retains_everything(self):
        self.fresh();self.init='failed'
        with self.assertRaisesRegex(RuntimeError,'not provably recoverable.*holds retained'):self.action('start')
        self.assertTrue(m.MODULE.exists() and m.DDC.exists() and m.OWNED.exists())
        for action in ('start','stop'):
            with self.subTest(action=action),self.assertRaisesRegex(RuntimeError,'cold cycle'):self.action(action)
        self.assertFalse((m.MODULE/'parameters/stop').is_file()) # attempted, refused by the module
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
    def test_stop_releases_ddc_pins_before_removing_the_helper(self):
        self.action('stop')
        self.assertEqual(self.events[-1],['rmmod','h713_ddc_pins']);self.assertFalse(m.DDC.exists())
    def test_failed_ddc_pin_restore_keeps_the_helper_and_ownership(self):
        (m.DDC/'parameters/release').unlink();(m.DDC/'parameters/release').mkdir() # write raises OSError, as -EIO would
        with self.assertRaisesRegex(RuntimeError,'DDC pin restore failed.*DDC retained'):self.action('stop')
        self.assertNotIn(['rmmod','h713_ddc_pins'],self.events)
        self.assertTrue(m.DDC.exists() and m.OWNED.exists() and m.ATTEMPTED.exists())
        self.assertFalse(m.MODULE.exists()) # the signal owner itself was restored first
    def test_helper_without_release_parameter_is_removed_directly(self):
        shutil.rmtree(m.DDC/'parameters') # helper loaded before the release change
        self.action('stop')
        self.assertEqual(self.events[-1],['rmmod','h713_ddc_pins']);self.assertFalse(m.DDC.exists())
    def test_stop_holds_the_capture_device_across_restoration(self):
        self.action('stop')
        self.assertEqual(self.opens,1);self.assertFalse(self.holding) # taken before the stop, released after it
        self.assertEqual(self.events,[['rmmod','h713_hdmi_signal'],['rmmod','h713_ddc_pins']])
    def test_hold_is_released_when_restoration_is_incomplete(self):
        self.bad_restore=True
        with self.assertRaisesRegex(RuntimeError,'restoration incomplete'):self.action('stop')
        self.assertFalse(self.holding)
    def test_running_system_never_kills_consumers(self):
        self.pids=[4242]
        with self.assertRaisesRegex(RuntimeError,'capture is open'):self.action('stop')
        self.assertEqual(self.kills,[]);self.assertFalse((m.MODULE/'parameters/stop').exists())
    def test_shutdown_closes_consumers_then_restores(self):
        self.shutdown=True;self.pids=[4242,4343]
        self.action('stop')
        self.assertEqual(self.kills,[(4242,signal.SIGTERM),(4343,signal.SIGTERM)])
        self.assertEqual(self.events[0],['rmmod','h713_hdmi_signal'])
    def test_shutdown_escalates_to_sigkill_after_the_grace(self):
        self.shutdown=True;self.pids=[4242];self.ignores_term={4242}
        self.action('stop')
        self.assertEqual(self.kills,[(4242,signal.SIGTERM),(4242,signal.SIGKILL)])
        self.assertGreaterEqual(self.clock,5)
    def test_bench_no_reclaim_keeps_consumers_and_refuses(self):
        self.shutdown=True;self.pids=[4242];m.NO_RECLAIM.write_text('')
        with self.assertRaisesRegex(RuntimeError,'capture is open'):self.action('stop')
        self.assertEqual(self.kills,[])
    def test_failed_owner_never_reclaims_consumers(self):
        self.shutdown=True;self.pids=[4242];self.failed=True
        with self.assertRaisesRegex(RuntimeError,'owner failed'):self.action('stop')
        self.assertEqual(self.kills,[])
    def test_an_open_by_an_unseen_holder_still_refuses(self):
        self.shutdown=True;self.foreign_busy=True # e.g. a holder we could not read
        with self.assertRaisesRegex(RuntimeError,'capture is open'):self.action('stop')
        self.assertFalse((m.MODULE/'parameters/stop').exists())
    def test_graph_not_ready_means_nobody_can_capture(self):
        self.not_ready=True
        self.action('stop');self.assertIsNone(self.holding)
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
