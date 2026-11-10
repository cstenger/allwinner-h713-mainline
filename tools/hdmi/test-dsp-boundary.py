#!/usr/bin/env python3
"""Execute the actual boundary observer with stage-specific failures and loss."""
import importlib.util
import copy
import json
from pathlib import Path
import subprocess
import unittest
import tempfile

HERE = Path(__file__).resolve().parent

def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

old = load('retention_tests', HERE / 'test-dsp-retention.py')
old.ASSETS = HERE / 'dsp-boundary'
analyzer = load('boundary_analysis', HERE / 'analyze-dsp-boundary.py')
helper = load('boundary_helper', HERE / 'dsp-boundary.py')
runner = load('boundary_runner', HERE.parent / 'serial/run-dsp-boundary-boot.py')

class Native(old.Native):
    # Reuse only the compiler fixture, then exercise boundary semantics.
    test_actual_observer_normal_inherited_and_zero_responses = None
    test_actual_observer_faults_do_not_retry_or_patch = None
    test_actual_hold_predicate_refuses_off_busy_cold_live_or_half_gated = None
    def test_before_and_after_each_write_and_inherited_noops(self):
        for mode in ('normal','inherited','zero','loss-control','loss-config','loss-latch'):
            with self.subTest(mode=mode):subprocess.run([str(self.path/'observer'),mode],check=True)
    def test_timeout_cannot_reach_audiotop_or_another_pair(self):
        for mode in ('done-timeout','busy-timeout','late-timeout'):
            with self.subTest(mode=mode):subprocess.run([str(self.path/'observer'),mode],check=True)
    def test_lock_power_resource_gate_failures_prevent_requests(self):
        for mode in ('lock-mismatch','power-loss','resource-denied','closed-gate','violated'):
            with self.subTest(mode=mode):subprocess.run([str(self.path/'observer'),mode],check=True)

class Evidence(unittest.TestCase):
    def record(self):
        r=old.good_record();s=r['state'];s.update(schema='h713-dsp-boundary-v1',step=73,
            pairs=[{'outcome':[1,1],'raw':[1,1]} for i in range(4)])
        return r
    def test_transition_identifies_each_intervention(self):
        for i,name in enumerate(('control','config','latch'),1):
            r=self.record()
            for pair in r['state']['pairs'][i:]:pair['raw']=[0,0]
            self.assertEqual(analyzer.analyze(r)['first_observed_change'],name)
    def test_zero_before_setup_does_not_become_reset_erasure(self):
        r=self.record()
        for pair in r['state']['pairs']:pair['raw']=[0,0]
        self.assertEqual(analyzer.analyze(r)['classification'],'zero_before_audiotop_writes')
        self.assertEqual(analyzer.analyze(r)['direct_reset_ram_erasure'],'not measured')
    def test_bad_context_and_unreleased_pair_inconclusive(self):
        for field,value in [('failed',1),('timeout',1),('hold',0),('violated',1),('claimed',1),('step',54)]:
            r=self.record();r['state'][field]=value
            self.assertIsNone(analyzer.analyze(r)['pairs'][0])
    def test_missing_response_metadata_remains_inconclusive(self):
        for change in ('missing-pairs', 'missing-raw', 'missing-outcome'):
            r=self.record()
            if change=='missing-pairs':del r['state']['pairs']
            elif change=='missing-raw':del r['state']['pairs'][0]['raw']
            else:del r['state']['pairs'][0]['outcome']
            self.assertIsNone(analyzer.analyze(r)['pairs'][0])
    def test_stage_and_timeout_gates(self):
        self.assertEqual(len(helper.STEPS),73)
        self.assertEqual(helper.STAGES[51],'exploratory-pre-at-status')
        self.assertEqual(helper.STEPS[55],'audiotop-control-if-needed')
        self.assertEqual(helper.STEPS[61],'audiotop-config-if-needed')
        self.assertEqual(helper.STEPS[67],'audiotop-latch-if-needed')
    def test_comparison_requires_arm_and_distinct_cold_cycles(self):
        a,b=self.record(),self.record()
        self.assertEqual(analyzer.compare(a,b)['classification'],'inconclusive')
        a['arm_proof']={'verified':True,'arm':'no-logo','cold_boot_id':'cold','warm_boot_id':'warm','fit_sha256':'test-fit'}
        b['arm_proof']={'verified':True,'arm':'one-logo','cold_boot_id':'cold','warm_boot_id':'warm','fit_sha256':'test-fit'}
        self.assertEqual(analyzer.compare(a,b)['classification'],'inconclusive')
        b['baseline']['boot_id']='cold-b';b['warm_boot_id']='warm-b'
        b['arm_proof'].update(cold_boot_id='cold-b',warm_boot_id='warm-b')
        b['state']['pairs'][0]['raw']=[0,0]
        self.assertEqual(analyzer.compare(a,b)['classification'],'logo_path_difference_requires_replication')

class Loader(unittest.TestCase):
    def fixture(self, p):
        baseline=p/'baseline.json';baseline.write_text(json.dumps(old.good_record()['baseline']))
        catch=p/'catch.log';catch.write_bytes(b'U-Boot SPL test\r\nH713 RESET v1 stage=proper_preboot gp6=48444d49 gp7=00000000 mips_status=00000000\r\n=> ')
        logo=p/'logo.log';logo.write_bytes(b'H713 RESET v1 stage=post_logo gp6=48444d49 mips_status=00000000\r\nH713_DSP_BOUNDARY_LOGO_OK\r\n=> ')
        return baseline,catch,logo
    def test_arm_checks_refuse_missing_duplicate_logo_or_wrong_ack(self):
        with tempfile.TemporaryDirectory() as t:
            b,c,l=self.fixture(Path(t))
            self.assertEqual(runner.arm_proof('no-logo','no-warm-logo-executed',b,c)['arm'],'no-logo')
            self.assertEqual(runner.arm_proof('one-logo','one-reviewed-warm-logo',b,c,l)['arm'],'one-logo')
            for arm,ack,logo in [('no-logo','no-warm-logo-executed',l),('one-logo','one-reviewed-warm-logo',None),('no-logo','one-reviewed-warm-logo',None)]:
                with self.assertRaises(ValueError):runner.arm_proof(arm,ack,b,c,logo)
            l.write_bytes(l.read_bytes()+l.read_bytes())
            with self.assertRaises(ValueError):runner.arm_proof('one-logo','one-reviewed-warm-logo',b,c,l)
    def test_cold_latch_or_two_resets_refused_before_uart(self):
        with tempfile.TemporaryDirectory() as t:
            b,c,l=self.fixture(Path(t))
            original=c.read_bytes()
            for raw in (original.replace(b'gp6=48444d49',b'gp6=00000000'),original+original):
                c.write_bytes(raw)
                with self.assertRaises(ValueError):runner.arm_proof('no-logo','no-warm-logo-executed',b,c)

if __name__=='__main__':unittest.main()
