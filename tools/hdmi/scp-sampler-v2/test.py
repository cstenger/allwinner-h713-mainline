#!/usr/bin/env python3
"""Exercise emitted monitor + actual C transaction/owner code on fake SRAM."""
import argparse
import base64
import contextlib
import ctypes as C
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--packet',type=Path,required=True)
P.add_argument('--mutations',action='store_true')
P.add_argument('--fail-fast',action='store_true',help='stop a mutated run after its first behavioral failure')
A=P.parse_args()
spec=importlib.util.spec_from_file_location('model',Path(__file__).with_name('model.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('capture',Path(__file__).with_name('capture.py'))
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
spec=importlib.util.spec_from_file_location('remote_test',Path(__file__).with_name('remote_test.py'))
remote_test=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote_test)


def compile_native(packet,output):
    for name in ['core.h','owner.h','generated.h']:shutil.copyfile(packet/name,output/name)
    (output/'wrapper.c').write_text(m.WRAPPER)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC','-pthread',
                    '-o',str(output/'native.so'),str(output/'wrapper.c')],check=True,capture_output=True)
    return output/'native.so'


class Tests(unittest.TestCase):
    library=None
    def make(self,**kw):
        cpu=m.CPU(A.packet,**kw);tx=m.Transaction(self.library,cpu)
        self.addCleanup(tx.cleanup)
        return cpu,tx

    def verify(self,cpu,tx):
        self.assertEqual(tx.receipt.phase,8)
        self.assertEqual(cpu.reads,cpu.m['read_registers'])
        self.assertEqual(list(tx.receipt.values),[cpu.peripheral[a] for a in cpu.reads])
        self.assertEqual(cpu.arm_read(0x4404),0x84830010)
        self.assertEqual(cpu.arm_read(0x4410),0x15000000)
        self.assertEqual(cpu.arm_read(0x4414),0)
        self.assertEqual(cpu.arm_read(0x4418),0x15000000)
        self.assertFalse(cpu.stop_delegated)
        self.assertEqual(cpu.last_return_context,cpu.context)
        self.assertEqual(tx.lib.held_lock(),1)
        self.assertEqual(tx.lib.owner_refs(),2)
        self.assertEqual(tx.lib.object_refs(),1)
        self.assertEqual(tx.lib.bool_reads(),3)
        self.assertEqual(tx.receipt.original_r13,cpu.context[13])
        self.assertEqual(tx.receipt.bootstrap_sr&0x17e,0)
        allowed=set(range(0x4f80,0x5000))|set(range(0x4414,0x441c))
        for f in cpu.m['fragments']:allowed.update(range(f['offset'],f['offset']+f['bytes']))
        self.assertTrue(all(i in allowed for i,(x,y) in enumerate(zip(cpu.before,cpu.mem)) if x!=y))
        self.assertTrue(all(0x4f80<=addr<0x5000 for addr,_ in cpu.stores))

    def test_01_nominal(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);self.verify(cpu,tx)

    def test_02_all_loop_phases_and_contexts(self):
        for phase in range(4):
            for seed in range(16):
                cpu=m.CPU(A.packet,seed=seed,phase=phase);tx=m.Transaction(self.library,cpu)
                try:self.assertEqual(tx.run(),0);self.verify(cpu,tx)
                finally:tx.cleanup()

    def test_03_delayed_reordered_store_visibility(self):
        for phase in range(4):
            for seed in range(8):
                cpu=m.CPU(A.packet,seed=seed,phase=phase,store_delay=17);tx=m.Transaction(self.library,cpu)
                try:self.assertEqual(tx.run(),0);self.verify(cpu,tx)
                finally:tx.cleanup()

    def test_04_fast_core_slow_observer(self):
        cpu,tx=self.make();tx.steps_per_io=23
        self.assertEqual(tx.run(),0);self.verify(cpu,tx)

    def test_05_slow_core(self):
        cpu,tx=self.make();tx.steps_per_io=0
        self.assertEqual(tx.run(),0);self.verify(cpu,tx)

    def test_06_done_before_return_is_rejected(self):
        cpu,tx=self.make();cpu.freeze_at_done=True
        self.assertEqual(tx.run(),1);self.assertEqual(tx.receipt.phase,10)
        self.assertNotIn(7,tx.phases);self.assertEqual(tx.lib.held_lock(),1)
        self.assertEqual(len(cpu.reads),14)

    def test_07_stale_return_marker_is_not_accepted(self):
        cpu,tx=self.make()
        def phase(n):
            if n==6:cpu.disabled=True;cpu.arm_write(0x4ff0,cpu.m['post_challenge'])
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertNotIn(7,tx.phases)

    def test_08_stale_hook_never_arms_sample(self):
        cpu,tx=self.make();cpu.stale_hook=True
        self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])
        self.assertNotIn((0x4f80,1),tx.writes)

    def test_09_missing_echo_never_arms_sample(self):
        cpu,tx=self.make();cpu.suppress_echo=True
        self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])
        self.assertNotIn((0x4f80,1),tx.writes)

    def test_10_sticky_hook_remains_safe_after_unhook(self):
        cpu,tx=self.make();cpu.sticky_hook=True
        self.assertEqual(tx.run(),0);self.verify(cpu,tx)
        entries=cpu.entry_count;cpu.advance(3000)
        self.assertGreater(cpu.entry_count,entries)
        self.assertEqual(len(cpu.reads),14)
        # The resident code was never removed and the request is consumed.
        self.assertEqual(cpu.arm_read(0x4f80),0)

    def test_11_every_stalled_load_is_retained(self):
        for index in range(14):
            cpu=m.CPU(A.packet);cpu.stall_at=index;tx=m.Transaction(self.library,cpu)
            try:
                self.assertEqual(tx.run(),1);self.assertTrue(cpu.stalled)
                self.assertEqual(tx.lib.held_lock(),1);self.assertNotIn(7,tx.phases)
                self.assertEqual(cpu.reads,cpu.m['read_registers'][:index])
                self.assertEqual(cpu.arm_read(0x4404),cpu.m['hook'])
            finally:tx.cleanup()

    def test_12_every_unsafe_SR_bit_refuses_reads(self):
        for bit in [1,2,3,4,5,6,8]:
            cpu=m.CPU(A.packet,sr=0x8081|(1<<bit));tx=m.Transaction(self.library,cpu)
            try:
                self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])
                self.assertEqual(tx.receipt.reason,21)
                self.assertFalse(cpu.saw_hook)
                self.assertNotIn(13,tx.phases)
            finally:tx.cleanup()

    def test_13_user_mode_refused(self):
        cpu,tx=self.make(sr=0x8080);self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])

    def test_14_bad_context_refused(self):
        for register in [3,10,11]:
            cpu=m.CPU(A.packet);tx=m.Transaction(self.library,cpu)
            def corrupt(off,value):
                if off==0x4404 and value==cpu.m['hook']:cpu.reg[register]^=0x100
            tx.before_write=corrupt
            try:self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])
            finally:tx.cleanup()

    def test_15_monitor_r0_guard_never_samples(self):
        cpu,tx=self.make();cpu.on_entry=lambda:cpu.reg.__setitem__(0,4)
        self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])

    def test_16_one_shot_latch_rejects_replay(self):
        cpu,tx=self.make();cpu.sticky_hook=True
        self.assertEqual(tx.run(),0)
        cpu.arm_write(0x4f80,1);cpu.advance(1000)
        self.assertEqual(len(cpu.reads),14);self.assertEqual(cpu.arm_read(0x4f94),1)

    def test_17_unknown_request_refused(self):
        cpu,tx=self.make()
        tx.before_write=lambda off,value:2 if off==0x4f80 and value==1 else None
        self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])

    def test_18_preimage_drift_is_clean_refusal(self):
        cpu,tx=self.make();cpu.arm_write(0x100,cpu.arm_read(0x100)^1)
        self.assertEqual(tx.run(),-1);self.assertEqual(tx.writes,[])
        self.assertEqual(tx.lib.held_lock(),0)

    def test_19_pending_stop_before_capture_refused(self):
        cpu,tx=self.make();cpu.arm_write(0x4f10,1)
        self.assertEqual(tx.run(),-1);self.assertEqual(tx.writes,[])

    def test_20_owner_absent(self):
        cpu,tx=self.make();self.assertEqual(tx.run(absent=1),-1)
        self.assertEqual(tx.writes,[]);self.assertEqual(tx.lib.object_refs(),1)

    def test_21_owner_unload_race(self):
        cpu,tx=self.make();self.assertEqual(tx.run(race=1),-1)
        self.assertEqual(tx.writes,[]);self.assertEqual(tx.lib.object_refs(),1)
        self.assertEqual(tx.lib.owner_refs(),1)

    def test_22_owner_not_ready(self):
        cpu,tx=self.make();self.assertEqual(tx.run(ready=0),-1)
        self.assertEqual(tx.writes,[]);self.assertEqual(tx.lib.held_lock(),0)

    def test_23_stop_stays_blocked_after_success(self):
        cpu,tx=self.make();thread=None
        def phase(n):
            nonlocal thread
            if n==2:
                thread=threading.Thread(target=tx.lib.competing_stop);thread.start()
                time.sleep(.01)
                self.assertEqual(tx.lib.stops(),0)
        tx.on_phase=phase
        self.assertEqual(tx.run(),0);self.assertTrue(thread.is_alive())
        self.assertEqual(tx.lib.stops(),0)
        # Explicit future end of preservation is the only unlock path.
        self.assertEqual(tx.lib.release_guard(C.byref(tx.io),C.byref(tx.receipt)),0)
        tx.lib.explicit_success_release();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertEqual(tx.lib.stops(),1)

    def test_24_stop_stays_blocked_on_stall(self):
        cpu,tx=self.make();cpu.stall_at=0;thread=None
        def phase(n):
            nonlocal thread
            if n==2:thread=threading.Thread(target=tx.lib.competing_stop);thread.start()
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertTrue(thread.is_alive())
        self.assertEqual(tx.lib.stops(),0)
        # Test-harness mutex cleanup, not an available production FROZEN action.
        tx.cleanup();thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_25_original_stop_delegation_after_later_release(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0)
        self.assertEqual(tx.lib.release_guard(C.byref(tx.io),C.byref(tx.receipt)),0)
        tx.lib.explicit_success_release()
        cpu.arm_write(0x4f10,1);cpu.advance(200)
        self.assertTrue(cpu.stop_delegated)

    def test_26_all_host_write_failures_retained(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);count=tx.write_count
        tx.cleanup()
        # Each write position of the actual successful transaction is faulted.
        for index in range(1,count+1):
            cpu2=m.CPU(A.packet);tx2=m.Transaction(self.library,cpu2);tx2.fail_write=index
            try:
                self.assertEqual(tx2.run(),1,(index,count))
                self.assertEqual(tx2.lib.held_lock(),1)
                self.assertEqual(tx2.write_count,index)
            finally:tx2.cleanup()

    def test_27_outside_corruption_after_capture_is_retained(self):
        cpu,tx=self.make()
        def phase(n):
            if n==7:cpu.arm_write(0x200,cpu.arm_read(0x200)^1)
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertEqual(tx.receipt.reason,10)

    def test_28_exception_marker_aborts_without_cleanup(self):
        cpu,tx=self.make()
        def phase(n):
            if n==5:cpu.arm_write(0x4f0c,4)
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertNotIn(7,tx.phases)

    def test_29_idle_error_marker_cannot_be_ignored(self):
        cpu,tx=self.make()
        def phase(n):
            if n==4:cpu.arm_write(0x4f94,1)
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])

    def test_30_forged_entry_marker_still_needs_fresh_return(self):
        cpu,tx=self.make()
        def phase(n):
            if n==3:
                cpu.disabled=True;cpu.arm_write(0x4f84,cpu.m['nonce']);cpu.arm_write(0x4f88,0x8081)
                for off,v in [(0x4fd8,0x4f00),(0x4fe4,0x48444d49),(0x4fe8,0x07090000)]:cpu.arm_write(off,v)
                cpu.arm_write(0x4ff0,cpu.m['initial_challenge'])
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertEqual(cpu.reads,[])

    def test_31_release_refuses_pending_stop(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0)
        cpu.arm_write(0x4f10,1)
        self.assertEqual(tx.lib.release_guard(C.byref(tx.io),C.byref(tx.receipt)),1)
        self.assertEqual(tx.lib.held_lock(),1);cpu.advance(200)
        self.assertTrue(cpu.guard_parked);self.assertFalse(cpu.stop_delegated)

    def test_32_ARM_rechecks_unsafe_entry_frame(self):
        cpu,tx=self.make()
        def phase(n):
            if n==3:
                cpu.disabled=True;cpu.arm_write(0x4f84,cpu.m['nonce']);cpu.arm_write(0x4f88,0x8091)
                for off,v in [(0x4fd8,0x4f00),(0x4fe4,0x48444d49),(0x4fe8,0x07090000)]:cpu.arm_write(off,v)
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertEqual(tx.receipt.reason,7)
        self.assertNotIn(4,tx.phases)

    def event(self,cpu,tx):
        return dict(boot_id=cpu.m['identity']['boot_id'],status=8,reason=0,no_release_performed=True,
            owner_stop_held=True,bootstrap_sr=tx.receipt.bootstrap_sr,original_r13=tx.receipt.original_r13,
            result=' '.join(str(n) for n in [cpu.m['nonce'],8,0,tx.receipt.sr,*tx.receipt.values]),
            after_sram=base64.b64encode(cpu.mem).decode())

    def test_33_post_capture_frame_and_bytes(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0)
        self.assertTrue(capture.verify_finished(A.packet,cpu.m,self.event(cpu,tx))['owner_stop_held'])

    def test_34_post_capture_wrong_boot_refused(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);e=self.event(cpu,tx);e['boot_id']='wrong'
        with self.assertRaises(ValueError):capture.verify_finished(A.packet,cpu.m,e)

    def test_35_post_capture_release_refused(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);e=self.event(cpu,tx);e['owner_stop_held']=False
        with self.assertRaises(ValueError):capture.verify_finished(A.packet,cpu.m,e)

    def test_36_post_capture_frame_mismatch_refused(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);e=self.event(cpu,tx);e['result']+=' 1'
        with self.assertRaises(ValueError):capture.verify_finished(A.packet,cpu.m,e)

    def test_37_post_capture_guard_mismatch_refused(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);cpu.arm_write(0x4414,1)
        with self.assertRaises(ValueError):capture.verify_finished(A.packet,cpu.m,self.event(cpu,tx))

    def test_38_post_capture_code_mismatch_refused(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);cpu.arm_write(0x4ac0,1)
        with self.assertRaises(ValueError):capture.verify_finished(A.packet,cpu.m,self.event(cpu,tx))

    def test_39_post_capture_outside_corruption_refused(self):
        cpu,tx=self.make();self.assertEqual(tx.run(),0);cpu.arm_write(0x100,cpu.arm_read(0x100)^1)
        with self.assertRaises(ValueError):capture.verify_finished(A.packet,cpu.m,self.event(cpu,tx))

    def test_40_default_driver_is_offline(self):
        manifest=json.loads((A.packet/'manifest.json').read_text())
        with mock.patch.object(capture,'load_packet',return_value=(manifest,{})), \
             mock.patch.object(capture,'host_bad_state',side_effect=AssertionError('hardware path')), \
             mock.patch.object(capture.subprocess,'Popen',side_effect=AssertionError('network path')), \
             mock.patch('sys.argv',['capture.py','--packet',str(A.packet)]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            capture.main()
        self.assertFalse(json.loads(output.getvalue())['hardware_opened'])

    def test_41_explicit_release_write_failures_keep_lock(self):
        for fault in [1,2]:
            cpu=m.CPU(A.packet);tx=m.Transaction(self.library,cpu)
            try:
                self.assertEqual(tx.run(),0);tx.fail_write=tx.write_count+fault
                self.assertEqual(tx.lib.release_guard(C.byref(tx.io),C.byref(tx.receipt)),1)
                self.assertEqual(tx.lib.held_lock(),1)
            finally:tx.cleanup()

    def test_42_bad_context_return_parks_at_guard(self):
        cpu,tx=self.make()
        def phase(n):
            if n==5:
                target=next(off for off in cpu.allowed_pc if cpu.arm_read(off)==0x84604fd8)
                cpu.arm_write(target,0x15000000)
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertTrue(cpu.guard_parked)
        self.assertIn(cpu.pc,[0x4414,0x4418])
        self.assertFalse(cpu.stop_delegated);self.assertNotIn(7,tx.phases)

    def test_43_unexpected_stop_parks_without_HPD_path(self):
        cpu,tx=self.make()
        def phase(n):
            if n==5:cpu.arm_write(0x4f10,1)
        tx.on_phase=phase
        self.assertEqual(tx.run(),1);self.assertTrue(cpu.guard_parked)
        self.assertIn(cpu.pc,[0x4414,0x4418])
        self.assertFalse(cpu.stop_delegated)

    def test_44_bootstrap_stale_slot_never_jumps_to_scratch(self):
        cpu,tx=self.make();cpu.stale_boot_slot=True
        self.assertEqual(tx.run(),1);self.assertFalse(cpu.saw_hook)
        self.assertEqual(cpu.reads,[]);self.assertNotIn(13,tx.phases)

    def test_45_bootstrap_canary_and_sentinel_collisions(self):
        for value in [0xa55a3cc3,0x5aa5c33c,0xa5a50000,0x5a5a0000,0,0xffffffff]:
            cpu=m.CPU(A.packet);cpu.reg[13]=value;cpu.context[13]=value;tx=m.Transaction(self.library,cpu)
            try:self.assertEqual(tx.run(),0);self.verify(cpu,tx)
            finally:tx.cleanup()

    def test_46_bootstrap_mixed_old_new_instruction_views(self):
        for phase in range(4):
            for seed in range(8):
                cpu=m.CPU(A.packet,phase=phase,seed=seed,store_delay=17);cpu.bootstrap_fetch_mix=True
                tx=m.Transaction(self.library,cpu)
                try:self.assertEqual(tx.run(),0);self.verify(cpu,tx)
                finally:tx.cleanup()

    def test_47_carry_overflow_context_preserved(self):
        cpu,tx=self.make(sr=0x8c81);self.assertEqual(tx.run(),0);self.verify(cpu,tx)
        self.assertEqual(tx.receipt.bootstrap_sr,0x8c81);self.assertEqual(tx.receipt.sr,0x8c81)

    def test_48_stale_psync_cannot_release_park_to_scratch(self):
        cpu,tx=self.make();cpu.stale_sync=True
        self.assertEqual(tx.run(),1);self.assertFalse(cpu.monitor_entered)
        release=((0x4ac0-0x4414)//4)&0x3ffffff
        self.assertNotIn((0x4414,release),tx.writes)
        self.assertEqual(cpu.reads,[])

    def run_peer(self,stall=None):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);peer=remote_test.Peer(capture,m,self.library,A.packet,root,stall)
            output=root/'capture'
            try:
                with mock.patch.object(capture,'load_packet',return_value=(peer.manifest,dict(file_pins=peer.pins))), \
                     mock.patch.object(capture,'host_bad_state',return_value=None), \
                     mock.patch.object(capture.subprocess,'Popen',side_effect=peer.popen), \
                     mock.patch('sys.argv',['capture.py','--packet',str(peer.client_packet),'--output',str(output),'--execute-approved']), \
                     contextlib.redirect_stdout(io.StringIO()):
                    if stall is None:capture.main()
                    else:
                        with self.assertRaises(ValueError):capture.main()
                self.assertEqual(peer.errors,[])
                self.assertEqual(len(peer.commands),1)
                self.assertEqual(len(peer.param_writes),1)
                self.assertTrue(peer.param_writes[0][0].endswith('/capture'))
                self.assertTrue(peer.device_reads)
                self.assertEqual(peer.tx.lib.held_lock(),1)
                self.assertEqual((output/'before-sram.bin').read_bytes(),peer.cpu.before)
                self.assertTrue((output/'CAPTURE-INTENT.json').exists())
                event=json.loads((output/'REMOTE-RESULT.json').read_text())
                self.assertTrue(event['owner_stop_held']);self.assertTrue(event['no_release_performed'])
                self.assertEqual(event['status'],8 if stall is None else 10)
                self.assertEqual((output/'RESULT.json').exists(),stall is None)
            finally:peer.close()

    def test_49_full_driver_and_peer_protocol(self):self.run_peer()
    def test_50_full_driver_retains_frozen_failure(self):self.run_peer(stall=4)


def mutations(packet):
    changes=[
      ('skip entry proof','if(scps_until(io,r,SCPS_OUT+4,SCPS_NONCE)) goto fail;','/* mutation */'),
      ('skip post-return proof','if(scps_return(io,r,SCPS_POST_CHALLENGE)) goto fail;','/* mutation */'),
      ('accept stale return','if(scps_put(io,r,SCPS_OUT+112,0,0)) return -1;','/* mutation */'),
      ('release owner on success','if(ret<0) kernel_param_unlock(owner);','if(ret<=0) kernel_param_unlock(owner);'),
      ('release owner on ambiguity','if(ret<0) kernel_param_unlock(owner);','kernel_param_unlock(owner);'),
      ('ignore owner ready','if(!scps_owner_bool(owner,"ready",1)', 'if(0'),
      ('ignore preimage','if(io->read(io->context,off)!=scps_baseline[off/4]) { r->reason=6;',
                         'if(0) { r->reason=6;'),
      ('ignore write failure','if (io->write(io->context,off,value))','if (io->write(io->context,off,value) && 0)'),
      ('ignore SR','if((r->sr&0x17e) || !(r->sr&1) ||','if(0 ||'),
      ('ignore exceptions','return io->read(io->context,0x4f0c) || io->read(io->context,0x4f18) ||','return 0 ||'),
      ('ignore bootstrap cache state','if((observed&0x17e) || !(observed&1))','if(0)'),
      ('skip pre-entry pipeline witness','if(scps_until(io,r,SCPS_OUT+4,SCPS_MARKER)) goto fail;','/* mutation */'),
      ('accept failed module pin','!try_module_get(owner)','(!try_module_get(owner) && 0)'),
    ]
    with tempfile.TemporaryDirectory() as td:
        base=Path(td)
        for index,item in enumerate(changes):
            label,old,new,*which=item;p=base/str(index);p.mkdir()
            for name in ['core.h','owner.h','generated.h','manifest.json','baseline-sram.bin','fragment-a.bin','fragment-b.bin']:
                shutil.copyfile(packet/name,p/name)
            target=p/('owner.h' if 'owner' in old else 'core.h');s=target.read_text()
            if which:
                parts=s.split(old);assert len(parts)==3;s=old.join(parts[:2])+new+parts[2]
            else:
                assert s.count(old)==1,(label,s.count(old));s=s.replace(old,new)
            target.write_text(s)
            result=subprocess.run(['python3',str(Path(__file__).resolve()),'--packet',str(p),'--fail-fast'],capture_output=True)
            if result.returncode==0:raise AssertionError('SURVIVED '+label)
            if b'FAIL:' not in result.stderr and b'ERROR: test_' not in result.stderr:
                raise AssertionError('not a behavioral kill '+label+'\n'+result.stderr.decode()[-1000:])
            print('CAUGHT '+label,flush=True)
    print(f'PASS all {len(changes)} transaction/owner mutations caught')


if __name__=='__main__':
    if A.mutations:mutations(A.packet.resolve())
    else:
        with tempfile.TemporaryDirectory() as td:
            Tests.library=compile_native(A.packet.resolve(),Path(td))
            result=unittest.TextTestRunner(verbosity=2,failfast=A.fail_fast).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
            raise SystemExit(not result.wasSuccessful())
