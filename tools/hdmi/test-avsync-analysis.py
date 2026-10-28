#!/usr/bin/env python3
"""Test calibration sign/quality gates against independent synthetic event logs."""
import importlib.util
from pathlib import Path
import types
import unittest

HERE=Path(__file__).resolve().parent
SOURCE=(HERE/'analyze-avsync.py').read_text()

def load(source=SOURCE):
    m=types.ModuleType('analysis');m.__file__=str(HERE/'analyze-avsync.py')
    exec(compile(source,m.__file__,'exec'),m.__dict__);return m

M=load()

def log(offset=0, drift=0):
    rows=['flashes 20, beeps 20']
    for i in range(20):
        t=1000+i*1.1;d=offset+drift*(t-1000)/60
        rows.append(f'PAIR_CSV,{t:.9f},{t+d/1000:.9f},{d:.6f}')
    return '\n'.join(rows)

class Tests(unittest.TestCase):
    def test_audio_early_requires_positive_delay(self):
        r=M.analyze(log(-40));self.assertAlmostEqual(r['audio_timing_correction_sec'],.04)
        self.assertIsNone(r['electronic_only_candidate_delay_sec'])
    def test_audio_late_reduces_existing_delay(self):
        r=M.analyze(log(50),.1);self.assertAlmostEqual(r['electronic_only_candidate_delay_sec'],.05)
    def test_spread_and_drift_preserve_direction(self):
        r=M.analyze(log(-40,6));self.assertAlmostEqual(r['within_window_slope_ms_per_min'],6,places=5)
        self.assertAlmostEqual(r['offset_ms']['p95']-r['offset_ms']['p05'],1.881,places=5)
    def test_bad_clock_or_pairing_is_refused(self):
        for bad in (log().replace('1000.000000000','nan',1),log().replace('PAIR_CSV,1001.100000000','PAIR_CSV,1000.000000000',1)):
            with self.assertRaises(ValueError):M.analyze(bad)
    def test_timestamp_disagreement_is_refused(self):
        with self.assertRaises(ValueError):M.analyze(log().replace(',0.000000',',20.000000',1))
    def test_low_match_coverage_is_refused(self):
        with self.assertRaises(ValueError):M.analyze(log().replace('flashes 20, beeps 20','flashes 40, beeps 40'))
    def test_short_window_is_refused(self):
        s=log();rows=s.splitlines();s='\n'.join([rows[0]]+[f'PAIR_CSV,{1000+i*.1:.9f},{1000+i*.1:.9f},0' for i in range(20)])
        with self.assertRaises(ValueError):M.analyze(s)
    def test_unavailable_negative_delay_is_not_silently_claimed(self):
        r=M.analyze(log(50),0);self.assertTrue(r['candidate_outside_supported_range']);self.assertIsNone(r['electronic_only_candidate_delay_sec'])
        with self.assertRaises(ValueError):M.analyze(log(),float('nan'))

if __name__=='__main__':
    def run(module,name=None):
        global M
        M=module;r=unittest.TestResult()
        suite=unittest.TestSuite([Tests(name)]) if name else unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
        suite.run(r);return r
    r=run(load())
    for _,detail in r.errors+r.failures:print(detail)
    assert r.wasSuccessful();print('PASS',r.testsRun,'analysis tests')
    mutations=[
      ('test_audio_early_requires_positive_delay',"'audio_timing_correction_sec': -median/1000","'audio_timing_correction_sec': median/1000"),
      ('test_audio_late_reduces_existing_delay','requested = current_delay-median/1000','requested = -median/1000'),
      ('test_spread_and_drift_preserve_direction','slope*60','-slope*60'),
      ('test_bad_clock_or_pairing_is_refused','if not all(math.isfinite(v) for v in (flash, beep, offset)):','if False:'),
      ('test_timestamp_disagreement_is_refused','if abs((beep-flash)*1000-offset) > .002:','if False:'),
      ('test_low_match_coverage_is_refused','len(pairs)/max(nf, nb) < .8','False'),
      ('test_short_window_is_refused',"if pairs[-1][0]-pairs[0][0] < 8:",'if False:'),
      ('test_unavailable_negative_delay_is_not_silently_claimed',"'candidate_outside_supported_range': not 0 <= requested <= .5","'candidate_outside_supported_range': False")]
    for test,old,new in mutations:
        assert old in SOURCE
        assert not run(load(SOURCE.replace(old,new)),test).wasSuccessful(),test+' mutant survived'
        print('CAUGHT',test)
