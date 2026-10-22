#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import subprocess
import unittest
import copy
import tempfile

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
old=load('retention_tests',HERE/'test-dsp-retention.py');old.ASSETS=HERE/'dsp-minimum'
a=load('minimum_analysis',HERE/'analyze-dsp-minimum.py')
h=load('minimum_helper',HERE/'dsp-minimum.py')
runner=load('minimum_runner',HERE.parent/'serial/run-dsp-minimum-boot.py')

class Native(old.Native):
    test_actual_observer_normal_inherited_and_zero_responses=None
    test_actual_observer_faults_do_not_retry_or_patch=None
    test_actual_hold_predicate_refuses_off_busy_cold_live_or_half_gated=None
    def test_no_observer_or_steps_without_both_optins(self):
        for mode in ('missing-flag','missing-level'):
            subprocess.run([str(self.path/'observer'),mode,'1'],check=True)
    def test_each_fixed_level_and_minimum_threshold(self):
        for level in ('1','2','3'):
            for mode in ('normal','zero','needs-2','needs-3'):
                with self.subTest(level=level,mode=mode):subprocess.run([str(self.path/'observer'),mode,level],check=True)
    def test_phase_distinguishes_busy_from_sent_done_timeout_and_skips(self):
        for mode in ('busy-timeout','done-timeout','device1-timeout'):
            subprocess.run([str(self.path/'observer'),mode,'3'],check=True)
    def test_inherited_owners_power_or_lock_failure_do_not_issue_requests(self):
        for mode in ('inherited','resource-denied','lock-mismatch','power-loss'):
            subprocess.run([str(self.path/'observer'),mode,'1'],check=True)

class Evidence(unittest.TestCase):
    def record(self,level=1):
        r=old.good_record();r['baseline']['boot_id']='cold-'+str(level);r['warm_boot_id']='warm-'+str(level)
        r['state'].update(schema='h713-dsp-minimum-v1',step=58,level=level,setup_mask=(1<<level)-1,
            ctl_before=0,cfg_before=0,phase=[5,5],sent=[1,1],
            setup_readback=[0x700,0x001a5e00 if level>=2 else 0xffffffff,0x011a5e00 if level>=3 else 0xffffffff],
            demod_before=1,display_reset_before=0,tvcap_reset_before=0,route_writes=0,routes_before=[1]*7,tv_before=[0]*15,pairs=[{'outcome':[1,1],'raw':[0,0]}])
        r['arm_proof']={'verified':True,'arm':'one-logo','level':level,'cold_boot_id':r['baseline']['boot_id'],
                        'warm_boot_id':r['warm_boot_id'],'fit_sha256':'same-fit'}
        return r
    def timeout(self,r):
        r['state'].update(timeout=1,phase=[4,6],sent=[1,0],pairs=[{'outcome':[2,3],'raw':[0xffffffff,0xffffffff]}]);return r
    def test_completed_zero_is_access_success_not_retention(self):
        result=a.analyze(self.record());self.assertTrue(result['completed_access']);self.assertFalse(result['patch_retained'])
    def test_phase_required_to_classify_failure(self):
        r=self.timeout(self.record());self.assertEqual(a.analyze(r)['classification'],'command_sent_done_timeout')
        r['state'].update(phase=[1,6],sent=[0,0]);self.assertEqual(a.analyze(r)['classification'],'initial_busy_timeout')
        r['state']['sent']=[1,0];self.assertEqual(a.analyze(r)['classification'],'inconclusive')
    def test_minimum_requires_distinct_matched_trials_and_resolved_lower_levels(self):
        low=self.timeout(self.record(1));high=self.record(2)
        self.assertEqual(a.compare([low,high])['lowest_completed_stock_prefix'],2)
        low['state'].update(phase=[1,6],sent=[0,0]);self.assertIsNone(a.compare([low,high])['lowest_completed_stock_prefix'])
        self.assertEqual(a.compare([self.record(1),high])['lowest_completed_stock_prefix'],1)
        high['arm_proof']['fit_sha256']='different';self.assertIsNone(a.compare([self.record(1),high])['lowest_completed_stock_prefix'])
    def test_wrong_level_or_unknown_completion_never_becomes_success(self):
        for field,value in [('step',57),('claimed',1),('failed',1),('hold',0),('phase',[5,4]),('sent',[1,0]),('setup_mask',0)]:
            r=self.record();r['state'][field]=value;self.assertFalse(a.analyze(r)['completed_access'])
        r=self.record();r['arm_proof']['level']=2;self.assertFalse(a.analyze(r)['completed_access'])
    def test_setup_context_mismatch_does_not_establish_minimum(self):
        low=self.timeout(self.record(1));high=self.record(2)
        high['state']['demod_before']=0
        self.assertIsNone(a.compare([low,high])['lowest_completed_stock_prefix'])
    def test_58_steps_and_no_setup_after_request(self):
        self.assertEqual(len(h.STEPS),58);self.assertEqual(h.STEPS[54:58],['device0-version','device1-version','release-stock-lock','final-check'])
        self.assertEqual(h.STAGES[50],'setup-ready')

class Loader(unittest.TestCase):
    def test_level_and_logo_proof_cannot_be_omitted_or_switched(self):
        import json
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);b=p/'baseline';b.write_text(json.dumps(old.good_record()['baseline']))
            c=p/'catch';c.write_bytes(b'U-Boot SPL test\r\nH713 RESET v1 stage=proper_preboot gp6=48444d49 gp7=00000000 mips_status=00000000\r\n=> ')
            l=p/'logo';l.write_bytes(b'H713 RESET v1 stage=post_logo gp6=48444d49 mips_status=00000000\r\nH713_DSP_MINIMUM_LOGO_OK\r\n=> ')
            for level in (1,2,3):
                self.assertEqual(runner.arm_proof('one-logo','one-reviewed-warm-logo',b,c,l,level)['level'],level)
            for level in (None,0,4):
                with self.assertRaises(ValueError):runner.arm_proof('one-logo','one-reviewed-warm-logo',b,c,l,level)
            with self.assertRaises(ValueError):runner.arm_proof('no-logo','no-warm-logo-executed',b,c,None,1)
            l.write_bytes(l.read_bytes()*2)
            with self.assertRaises(ValueError):runner.arm_proof('one-logo','one-reviewed-warm-logo',b,c,l,1)

if __name__=='__main__':unittest.main()
