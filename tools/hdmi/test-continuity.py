#!/usr/bin/env python3
"""Offline controls for the capture continuity screen; no device access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

import numpy as np

SCRIPT = Path(__file__).with_name('check-continuity.py')
spec = importlib.util.spec_from_file_location('continuity', SCRIPT)
continuity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(continuity)


class Continuity(unittest.TestCase):
    def test_clean_drift_step_and_gap_controls(self):
        t = np.arange(6 * 48000)
        clean = 6500 * np.sin(2 * np.pi * 1000 * t / 48000)
        self.assertLess(continuity.measure(clean, 1000)['max_residual_phase_step_rad'], .001)
        drift = 6500 * np.sin(2 * np.pi * 1000.1 * t / 48000)
        self.assertLess(continuity.measure(drift, 1000)['max_residual_phase_step_rad'], .001)
        broken = clean.copy()
        broken[144000:] = 6500 * np.sin(2 * np.pi * 1000 * (t[144000:] + 256) / 48000)
        self.assertGreater(continuity.measure(broken, 1000)['max_residual_phase_step_rad'], 1)
        gap = clean.copy()
        gap[144000:144960] = 0
        self.assertEqual(continuity.measure(gap, 1000)['min_relative_amplitude'], 0)

    def test_undefined_metrics_are_errors(self):
        for samples in (np.zeros(1920), np.zeros(960), np.zeros(1921),
                        np.full(1920, np.nan), np.full((1920, 2), 1)):
            with self.subTest(shape=samples.shape), self.assertRaises(ValueError):
                continuity.measure(samples, 1000)

    def write_wave(self, path, *, rate=48000, seconds=9, silent=False, channels=2, width=2):
        t = np.arange(seconds * rate) / rate
        samples = np.column_stack([6500 * np.sin(2 * np.pi * f * t) for f in (1000, 2000)])
        if silent:
            samples[:] = 0
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(samples.astype('<i2').tobytes())

    def run_cli(self, *arguments):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return continuity.main(list(map(str, arguments)))

    def test_explicit_inputs_keep_distinct_trials_and_produce_finite_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            paths = [root / name / 'capture.wav' for name in ('a', 'b')]
            for path in paths:
                path.parent.mkdir()
                self.write_wave(path)
            output = root / 'report.json'
            self.assertEqual(self.run_cli(*paths, '--output', output), 0)
            data = json.loads(output.read_text())
            self.assertEqual(set(data['trials']), {str(path.resolve()) for path in paths})
            for trial in data['trials'].values():
                for channel in trial:
                    self.assertLess(channel['max_residual_phase_step_rad'], .001)
                    self.assertGreater(channel['min_relative_amplitude'], .999)

    def test_bad_recordings_fail_without_a_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            capture, report = root / 'capture.wav', root / 'report.json'
            for settings in ({'rate': 32000}, {'seconds': 8}, {'channels': 1},
                             {'width': 1}, {'silent': True}):
                with self.subTest(settings=settings):
                    self.write_wave(capture, **settings)
                    self.assertEqual(self.run_cli(capture, '--output', report), 1)
                    self.assertFalse(report.exists())
            self.write_wave(capture)
            capture.write_bytes(capture.read_bytes()[:44 + 4 * 48000 * 4])
            self.assertEqual(self.run_cli(capture, '--output', report), 1)
            self.assertFalse(report.exists())
            self.assertEqual(self.run_cli(root / 'missing.wav', '--output', report), 1)
            self.assertFalse(report.exists())

    def test_cli_rejects_empty_duplicate_and_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            capture, report = root / 'capture.wav', root / 'report.json'
            self.write_wave(capture)
            for arguments in (('--output', report), (capture, capture, '--output', report),
                              (capture, '--output', capture)):
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as exc:
                    self.run_cli(*arguments)
                self.assertEqual(exc.exception.code, 2)
            report.write_text('preserve me')
            with self.assertRaises(SystemExit):
                self.run_cli(capture, '--output', report)
            self.assertEqual(report.read_text(), 'preserve me')

    def test_cli_errors_survive_python_optimization(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            capture, report = root / 'capture.wav', root / 'report.json'
            self.write_wave(capture, seconds=8)
            result = subprocess.run([sys.executable, '-O', str(SCRIPT), str(capture),
                                     '--output', str(report)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(report.exists())


if __name__ == '__main__':
    unittest.main()
