#!/usr/bin/env python3
"""Exercise actual service state machine with simulated IO, never hardware."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('session',Path(__file__).with_name('h713-hdmi-session.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PATCH=b'Q'*2896
m.PATCH_SHA=hashlib.sha256(PATCH).hexdigest()


class FakeBoard:
    def __init__(self):
        self.files={m.BOOT_ID:'boot1\n',m.FW_PATH:'\n',m.PCM:'closed\n','/bundle/cold-boot-proof.json':json.dumps({'boot_id':'boot1','cold_boot_confirmed':True,'parked_status_before_launch':0,'source3_verified':True})}
        self.events=[];self.modules=set();self.commands=[];self.writes=[];self.log='baseline\n'
        self.wp=True;self.fail_audio=False;self.fail_remove=False;self.bad_restore=False
        self.fail_park=False;self.fail_release=False;self.bad_trace=False;self.bad_patch=False;self.bad_ipc=False;self.mips_live=True
    def exists(self,p):return p in self.files or p.removeprefix(m.BASE) in self.modules
    def read(self,p):return self.files[p]
    def binary(self,p):return b'bad' if self.bad_patch else PATCH
    def write(self,p,text):
        self.events.append(('write',p));self.writes.append((p,text));self.files[p]=text
        if p.endswith('/park_for_shutdown'):
            self.mips_live=self.fail_park
            self.param(m.OWNER,'parked','N' if self.fail_park else 'Y')
            self.param(m.OWNER,'park_failed','Y' if self.fail_park else 'N')
        if p.endswith('/release_when_parked'):
            if self.fail_release:raise RuntimeError('release refused')
            self.param(m.OWNER,'firmware_pin','N');self.param(m.OWNER,'edid_ready','N')
        if p.endswith('/clock_count') and text.strip()=='4':self.files[m.BASE+m.OWNER+'/parameters/edid_ready']='Y'
    def state(self,value):self.files[m.STATE]=json.dumps(value)
    def param(self,module,name,value):self.files[m.BASE+module+'/parameters/'+name]=str(value)
    def run(self,argv,check=True,timeout=15):
        self.events.append(('run',argv));self.commands.append(argv);out='';rc=0
        if argv[0]=='uname':out='6.18.38\n'
        elif argv[0]=='modinfo':out='6.18.38 SMP mod_unload aarch64\n'
        elif '--status' in argv:out='MIPS core      ALIVE' if self.mips_live else 'MIPS core      parked'
        elif '--source-only' in argv:out=json.dumps({'guards':'bad' if self.bad_trace else '43414e31/43414e31','source3_transition_complete':1,'source3_worker_new':'00000003'})
        elif '--cmd' in argv:out='missing' if self.bad_ipc else 'VS:/$'
        elif argv[0]=='insmod':
            if argv[1].endswith('h713-hdmi-receiver.ko'):
                self.modules.add(m.OWNER)
                for k,v in [('init_error',0),('clock_count',0),('clients',0),('firmware_pin','Y'),('edid_ready','N')]:self.param(m.OWNER,k,v)
                for domain in ('tvfe','tvcap'):self.files['/sys/devices/h713-hdmi-'+domain+'/power/runtime_status']='active'
            else:
                if self.fail_audio:raise RuntimeError('simulated DSP load timeout')
                self.modules.add(m.AUDIO);self.param(m.OWNER,'clients',1)
                for k,v in [('graph_ready','Y'),('dsp_failed','N'),('manage_dsp','Y'),('manage_tvfe','Y'),('require_receiver_owner','Y')]:self.param(m.AUDIO,k,v)
        elif argv[0]=='runuser':
            action=argv[-2]
            if action=='is-active':rc=0 if self.wp else 3
            elif action=='stop':self.wp=False
            elif action=='start':self.wp=True
        elif argv[0]=='dmesg':out=self.log
        elif argv[0]=='rmmod':
            if argv==['rmmod',m.OWNER]:
                self.modules.remove(m.OWNER)
                return SimpleNamespace(stdout='',stderr='',returncode=0)
            assert argv==['rmmod',m.AUDIO],argv
            if self.fail_remove:raise RuntimeError('in use')
            self.modules.remove(m.AUDIO);self.param(m.OWNER,'clients',0)
            if not self.bad_restore:
                self.log+=''.join(f'DSP restore {i:04x}=0000 verified\n' for i in range(22))
                self.log+='managed DSP graph restored 22 words\n15 clock words and bus verified\n'
        else:raise AssertionError(argv)
        return SimpleNamespace(stdout=out,stderr='',returncode=rc)


class Lifecycle(unittest.TestCase):
    def setUp(self):self.b=FakeBoard();self.s=m.Session(self.b,'/bundle')
    def test_start_idempotence_stop_and_warm_retry(self):
        self.assertFalse(self.s.start()['already_ready'])
        self.assertEqual(self.b.read(m.FW_PATH),'\n')
        commands=len(self.b.commands);writes=len(self.b.writes)
        self.assertTrue(self.s.start()['already_ready'])
        self.assertEqual((len(self.b.commands),len(self.b.writes)),(commands,writes))
        self.assertTrue(self.s.stop()['receiver_retained']);self.assertTrue(self.b.wp)
        self.assertIn(m.OWNER,self.b.modules);self.assertNotIn(m.AUDIO,self.b.modules)
        self.assertTrue(self.s.prior()['restore_verified'])
        self.assertTrue(self.s.stop()['already_stopped'])
        self.assertTrue(self.s.prior()['restore_verified'])
        commands=len(self.b.commands)
        with self.assertRaisesRegex(RuntimeError,'cold boot'):self.s.start()
        self.assertEqual(len(self.b.commands),commands)
    def test_park_requires_verified_stop_and_capability(self):
        self.s.start()
        with self.assertRaisesRegex(RuntimeError,'verified managed audio stop'):self.s.park()
        self.s.stop();self.b.param(m.OWNER,'shutdown_ready','N')
        commands=len(self.b.commands);writes=len(self.b.writes)
        with self.assertRaisesRegex(RuntimeError,'parking-capable'):self.s.park()
        self.assertEqual((len(self.b.commands),len(self.b.writes)),(commands,writes))
        self.b.param(m.OWNER,'shutdown_ready','Y');self.b.param(m.OWNER,'clients',1)
        with self.assertRaisesRegex(RuntimeError,'client count'):self.s.park()
        self.assertEqual(len(self.b.writes),writes)

    def test_terminal_parking_removes_owner_only_after_verified_reset(self):
        self.s.start();self.s.stop();self.b.param(m.OWNER,'shutdown_ready','Y')
        result=self.s.park()
        self.assertTrue(result['receiver_removed']);self.assertNotIn(m.OWNER,self.b.modules)
        self.assertEqual(self.s.prior()['phase'],'parked')
        self.s.stop();self.assertEqual(self.s.prior()['phase'],'parked')
        with self.assertRaisesRegex(RuntimeError,'cold boot'):self.s.start()
    def test_terminal_failure_latches_and_retains_receiver(self):
        for release_failure in (False,True):
            self.setUp();self.s.start();self.s.stop();self.b.param(m.OWNER,'shutdown_ready','Y')
            self.b.fail_release=release_failure;self.b.fail_park=not release_failure
            with self.assertRaises(RuntimeError):self.s.park()
            self.assertIn(m.OWNER,self.b.modules);self.assertEqual(self.s.prior()['phase'],'parking_failed')
            if not release_failure:
                self.assertFalse(any(p.endswith('/release_when_parked') for p,_ in self.b.writes))
            writes=len(self.b.writes)
            self.s.stop()
            self.assertEqual(self.s.prior()['phase'],'parking_failed')
            with self.assertRaises(RuntimeError):self.s.park()
            self.assertEqual(len(self.b.writes),writes)

    def test_shutdown_restores_audio_before_parking_and_is_idempotent(self):
        self.s.start();self.b.param(m.OWNER,'shutdown_ready','Y')
        result=self.s.shutdown()
        self.assertEqual(result['audio_stop']['dsp_restored_words'],22)
        events=self.b.events
        removed=events.index(('run',['rmmod',m.AUDIO]))
        parked=events.index(('write',m.BASE+m.OWNER+'/parameters/park_for_shutdown'))
        released=events.index(('write',m.BASE+m.OWNER+'/parameters/release_when_parked'))
        unloaded=events.index(('run',['rmmod',m.OWNER]))
        self.assertTrue(removed < parked < released < unloaded)
        count=len(events)
        self.assertTrue(self.s.shutdown()['already_parked'])
        self.assertEqual(len(events),count)
    def test_shutdown_busy_or_capture_only_never_stops_or_parks(self):
        self.s.start();self.b.param(m.OWNER,'shutdown_ready','N')
        before=len(self.b.events)
        with self.assertRaisesRegex(RuntimeError,'parking-capable'):self.s.shutdown()
        self.assertEqual(len(self.b.events),before)
        self.b.param(m.OWNER,'shutdown_ready','Y');self.b.files[m.PCM]='state: RUNNING'
        with self.assertRaisesRegex(RuntimeError,'capture is open'):self.s.shutdown()
        self.assertEqual(len(self.b.events),before)
    def test_shutdown_failures_never_continue_or_retry_terminal_operations(self):
        for failure in ('fail_remove','bad_restore','fail_park','fail_release'):
            self.setUp();self.s.start();self.b.param(m.OWNER,'shutdown_ready','Y')
            setattr(self.b,failure,True)
            with self.assertRaises(RuntimeError):self.s.shutdown()
            self.assertIn(m.OWNER,self.b.modules)
            if failure in ('fail_remove','bad_restore'):
                self.assertFalse(any(p.endswith('/park_for_shutdown') for p,_ in self.b.writes))
            else:
                count=len(self.b.events)
                with self.assertRaisesRegex(RuntimeError,'cold boot'):self.s.shutdown()
                self.assertEqual(len(self.b.events),count)

    def test_busy_stop_preserves_client_and_services(self):
        self.s.start();self.b.files[m.PCM]='state: RUNNING\n'
        commands=len(self.b.commands)
        with self.assertRaisesRegex(RuntimeError,'capture is open'):self.s.stop()
        self.assertEqual(len(self.b.commands),commands);self.assertTrue(self.b.wp)
        self.assertEqual(self.s.prior()['phase'],'ready')
    def test_failed_setup_latches_and_restores_original_firmware_path(self):
        self.b.files[m.FW_PATH]='/existing\n';self.b.fail_audio=True
        with self.assertRaises(RuntimeError):self.s.start()
        self.assertEqual(self.b.read(m.FW_PATH),'/existing\n')
        self.assertIn(m.OWNER,self.b.modules);self.assertEqual(self.s.prior()['phase'],'failed')
        commands=len(self.b.commands)
        with self.assertRaisesRegex(RuntimeError,'cold boot'):self.s.start()
        self.assertEqual(len(self.b.commands),commands)
    def test_bad_preflight_never_mutates_hardware(self):
        for name in ('bad_patch','bad_trace'):
            self.setUp();setattr(self.b,name,True)
            with self.assertRaises(RuntimeError):self.s.start()
            self.assertFalse(self.b.modules);self.assertFalse(self.b.writes)
        self.setUp();self.b.mips_live=False
        with self.assertRaises(RuntimeError):self.s.start()
        self.assertFalse(self.b.modules);self.assertFalse(self.b.writes)
    def test_stop_failure_restores_wireplumber_and_preserves_retry_state(self):
        self.s.start();self.b.fail_remove=True
        with self.assertRaises(RuntimeError):self.s.stop()
        self.assertTrue(self.b.wp);self.assertIn(m.AUDIO,self.b.modules)
        self.assertEqual(self.s.prior()['phase'],'ready')
    def test_restore_proof_failure_still_forbids_reinit(self):
        self.s.start();self.b.bad_restore=True
        with self.assertRaisesRegex(RuntimeError,'verification missing'):self.s.stop()
        self.assertTrue(self.b.wp);self.assertEqual(self.s.prior()['phase'],'stopped')
        self.assertIsNot(self.s.prior().get('restore_verified'),True)
        with self.assertRaisesRegex(RuntimeError,'cold boot'):self.s.start()
    def test_inactive_wireplumber_stays_inactive(self):
        self.s.start();self.b.wp=False;self.s.stop();self.assertFalse(self.b.wp)
    def test_warm_linux_boot_cannot_reuse_old_cold_proof(self):
        self.b.files[m.BOOT_ID]='boot2\n';self.s=m.Session(self.b,'/bundle')
        with self.assertRaisesRegex(RuntimeError,'proof'):self.s.start()
        self.assertFalse(self.b.modules);self.assertFalse(self.b.commands)
    def test_unowned_healthy_audio_cannot_be_adopted_or_removed(self):
        self.s.start();del self.b.files[m.STATE];commands=len(self.b.commands)
        with self.assertRaisesRegex(RuntimeError,'ownership'):self.s.start()
        with self.assertRaisesRegex(RuntimeError,'owned'):self.s.stop()
        self.assertEqual(len(self.b.commands),commands)
    def test_latched_dsp_failure_blocks_stop_commands(self):
        self.s.start();self.b.param(m.AUDIO,'dsp_failed','Y');commands=len(self.b.commands)
        with self.assertRaises(RuntimeError):self.s.stop()
        self.assertEqual(len(self.b.commands),commands)
    def test_ipc_failure_retains_partial_holds(self):
        self.b.bad_ipc=True
        with self.assertRaises(RuntimeError):self.s.start()
        self.assertIn(m.OWNER,self.b.modules);self.assertEqual(self.s.prior()['phase'],'failed')
        self.assertFalse(any(c[0]=='rmmod' for c in self.b.commands))


if __name__=='__main__':unittest.main()
