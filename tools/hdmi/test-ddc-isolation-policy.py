#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('retry', Path(__file__).with_name('h713-hdmi-readvertise.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Power:
    def __init__(self, value): self.value, self.closed = value, False
    def read(self): return self.value
    def close(self): self.closed = True


class Isolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.params = root / 'parameters'
        self.params.mkdir()
        self.signal = root / 'signal'
        self.signal.write_text('none')
        (root / 'version').write_text('ddc-hpd-isolation-v1')
        for name, value in {'ready':'Y','failed':'N','readvertised':'0','readvertise':'',
                            'ddc_cycles':'0','ddc_cycle':''}.items():
            (self.params / name).write_text(value)
        self.time = 0
        self.requests = []
        self.result = 'locked 1280x720'
        self.changed = False
        self.power = Power(None)
        original = Path.write_text
        def write(path, data, *args, **kwargs):
            if path == self.params / 'ddc_cycle':
                self.requests.append(data)
                self.time += 2.1
                original(self.params / 'ddc_cycles', '1')
                original(self.signal, self.result)
            return original(path, data, *args, **kwargs)
        for p in (patch.object(m, 'PARAMS', self.params), patch.object(m, 'SIGNAL', self.signal),
                  patch.object(Path, 'write_text', write)):
            p.start()
            self.addCleanup(p.stop)

    def sleep(self, seconds):
        self.time += seconds
        if self.changed and self.time > 1:
            self.signal.write_text('acquiring 0x0')

    def run_diag(self):
        m.isolate_initial_ddc(self.power, lambda:self.time, self.sleep)

    def test_unknown_cold_power_can_run_once_without_hpd_request(self):
        self.run_diag()
        self.assertEqual(self.requests, ['2000\n'])
        self.assertEqual((self.params / 'readvertised').read_text(), '0')

    def test_active_absent_and_changing_source_are_not_disturbed(self):
        for state in ['locked 1280x720','holding 1280x720','acquiring 0x0','unsupported 0x0']:
            self.signal.write_text(state)
            self.run_diag()
        self.signal.write_text('none')
        self.power.value = False
        self.run_diag()
        self.power.value = None
        self.changed = True
        self.run_diag()
        self.assertFalse(self.requests)

    def test_no_lock_returns_to_normal_fallback_without_extra_ddc_action(self):
        self.result = 'none'
        self.run_diag()
        self.assertEqual(self.requests, ['2000\n'])
        self.assertGreaterEqual(self.time, 10)
        self.assertLess(self.time, 10.5)

    def test_owner_failure_or_previous_retry_skips_diagnostic(self):
        (self.params / 'failed').write_text('Y')
        self.run_diag()
        (self.params / 'failed').write_text('N')
        (self.params / 'readvertised').write_text('1')
        self.run_diag()
        self.assertFalse(self.requests)

    def test_candidate_main_runs_diagnostic_then_normal_policy_and_closes(self):
        with patch.object(m, 'DIAGNOSTIC_DDC_ONLY', True):
            self.assertEqual(m.main(lambda:self.time, self.sleep, polls=0, power=self.power), 0)
        self.assertEqual(self.requests, ['2000\n'])
        self.assertTrue(self.power.closed)

    def test_wrong_module_fails_closed_and_releases_control_fd(self):
        (self.params.parent / 'version').write_text('wrong-version')
        with patch.object(m, 'DIAGNOSTIC_DDC_ONLY', True):
            with self.assertRaisesRegex(RuntimeError, 'version missing'):
                m.main(lambda:self.time, self.sleep, polls=0, power=self.power)
        self.assertTrue(self.power.closed)
        self.assertFalse(self.requests)


if __name__ == '__main__': unittest.main()
