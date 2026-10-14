#!/usr/bin/env python3
"""Offline controls for the ALSA recording acceptance test."""
import importlib.util
import tempfile
import unittest
import wave
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location("test_runner", Path(__file__).with_name("run-alsa-capture-test.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CaptureAnalysis(unittest.TestCase):
    def test_tones_silence_channels_and_frame_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.wav"
            t = np.arange(10*48000) / 48000
            tones = np.column_stack([6500*np.sin(2*np.pi*f*t) for f in (1000, 2000)]).astype("<i2")
            good = np.zeros((16*48000, 2), dtype="<i2")
            good[48000:11*48000] = tones

            def write(samples):
                with wave.open(str(path), "wb") as out:
                    out.setnchannels(2)
                    out.setsampwidth(2)
                    out.setframerate(48000)
                    out.writeframes(samples.astype("<i2").tobytes())

            write(good)
            self.assertTrue(runner.analyze_wave(path)["pass"])
            write(np.zeros_like(good))
            self.assertFalse(runner.analyze_wave(path)["pass"])
            write(good[:, ::-1])
            self.assertFalse(runner.analyze_wave(path)["pass"])
            contaminated = good.copy()
            contaminated[-1, 0] = 1
            write(contaminated)
            self.assertFalse(runner.analyze_wave(path)["pass"])
            write(good[:-1])
            with self.assertRaises(RuntimeError):
                runner.analyze_wave(path)

    def test_extended_recording_checks_middle_and_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.wav"
            seconds = 32
            samples = np.zeros((seconds * 48000, 2), dtype="<i2")
            t = np.arange((seconds - 6) * 48000) / 48000
            samples[48000:(seconds - 5) * 48000] = np.column_stack(
                [6500 * np.sin(2 * np.pi * f * t) for f in (1000, 2000)])

            def check(data):
                with wave.open(str(path), "wb") as out:
                    out.setnchannels(2)
                    out.setsampwidth(2)
                    out.setframerate(48000)
                    out.writeframes(data.astype("<i2").tobytes())
                return runner.analyze_wave(path, seconds)["pass"]

            self.assertTrue(check(samples))
            for second in (16, 24):
                broken = samples.copy()
                broken[second * 48000:(second + 1) * 48000] = 0
                self.assertFalse(check(broken))
            samples[-1, 0] = 1
            self.assertFalse(check(samples))


if __name__ == "__main__":
    unittest.main()
