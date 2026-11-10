#!/usr/bin/env python3
"""Controls that distinguish fresh swapped audio from a replayed old signal."""
import importlib.util
import unittest
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location('reconnect', Path(__file__).with_name('run-alsa-reconnect-test.py'))
reconnect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconnect)


class FreshAudio(unittest.TestCase):
    def test_returned_audio_requires_new_channels_in_order(self):
        t = np.arange(48000)/48000
        tone = np.column_stack([6500*np.sin(2*np.pi*f*t) for f in (1000,2000)]).astype('<i2')
        silence = np.zeros_like(tone)
        analyze = reconnect.classify_recording
        self.assertTrue(analyze(np.concatenate([tone,silence,tone[:,::-1]]))['fresh_audio_verified'])
        self.assertFalse(analyze(np.concatenate([tone,silence,tone]))['fresh_audio_verified'])
        self.assertFalse(analyze(np.concatenate([tone,silence]))['fresh_audio_verified'])
        self.assertFalse(analyze(np.concatenate([tone[:,::-1],silence,tone]))['fresh_audio_verified'])


if __name__ == '__main__':
    unittest.main()
