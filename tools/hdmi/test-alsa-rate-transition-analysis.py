#!/usr/bin/env python3
"""Reject stale/missing audio after source-rate changes on an open capture."""
import importlib.util
import tempfile
import unittest
import wave
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location('transition', Path(__file__).with_name('run-alsa-rate-transition-test.py'))
transition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transition)


class Transition(unittest.TestCase):
    def test_each_phase_requires_its_fresh_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'capture.wav'
            data = np.zeros((48*48000, 2), dtype='<i2')
            t = np.arange(8*48000)/48000
            tone = np.column_stack([6500*np.sin(2*np.pi*f*t) for f in (1000,2000)]).astype('<i2')
            phases = []
            for index, rate in enumerate(transition.RATES):
                start = (2+index*9)*48000
                data[start:start+len(tone)] = tone[:, ::-1] if index % 2 else tone
                phases.append({'input_rate_hz': rate, 'swapped': bool(index%2), 'sample_frame': start+48000})

            def check(samples):
                with wave.open(str(path), 'wb') as wav:
                    wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(48000)
                    wav.writeframes(samples.tobytes())
                return transition.analyze_wave(path, phases)['pass']

            self.assertTrue(check(data))
            for index in range(4):
                start = (2+index*9)*48000
                missing = data.copy()
                missing[start:start+len(tone)] = 0
                self.assertFalse(check(missing))
                stale = data.copy()
                stale[start:start+len(tone)] = stale[start:start+len(tone), ::-1]
                self.assertFalse(check(stale))
            dirty = data.copy(); dirty[-1, 0] = 1
            self.assertFalse(check(dirty))
            with self.assertRaises(RuntimeError): check(data[:-1])

    def test_same_open_status_requires_running(self):
        self.assertEqual(transition.parse_status('state: RUNNING\nowner_pid   : 123\nhw_ptr      : 48000'), {'owner_pid': 123, 'hw_ptr': 48000})
        for state in ('closed', 'state: XRUN\nowner_pid: 123\nhw_ptr: 48000'):
            with self.assertRaises(RuntimeError): transition.parse_status(state)


if __name__ == '__main__':
    unittest.main()
