#!/usr/bin/env python3
"""Offline discriminator checks for the HDMI rate sweep."""
import importlib.util
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("runner", HERE / "run-audio-rate-test.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def ring(rate, swapped=False):
    t = np.arange(16384) / rate
    frequencies = (2000, 1000) if swapped else (1000, 2000)
    return np.column_stack([6500*np.sin(2*np.pi*f*t) for f in frequencies]).astype("<i2")


class RateTest(unittest.TestCase):
    def test_capture_rate_discriminator_including_ring_seam(self):
        for rate in runner.analysis.RATES:
            for seam in (False, True):
                x = ring(rate)
                if seam:
                    x[7000:] = ring(rate)[3000:12384]
                result = runner.analysis.analyze(x.tobytes())
                self.assertTrue(result["tone_pass"], (rate, seam, result))
                self.assertEqual(result["capture_rate_hz"], rate)

    def test_negative_controls(self):
        rng = np.random.default_rng(713)
        for x in (np.zeros((16384, 2), dtype="<i2"),
                  np.full((16384, 2), 2000, dtype="<i2"),
                  rng.integers(-6500, 6500, (16384, 2), dtype="<i2"),
                  ring(48000, swapped=True), ring(96000),
                  (ring(48000) * .1).astype("<i2")):
            self.assertFalse(runner.analysis.analyze(x.tobytes())["tone_pass"])
        self.assertTrue(runner.analysis.analyze(bytes(65536))["silence_pass"])
        self.assertFalse(runner.analysis.analyze(ring(48000).tobytes())["silence_pass"])
        with self.assertRaises(ValueError):
            runner.analysis.analyze(bytes(1024))

    def test_host_rate_mismatch_is_rejected(self):
        text = "format: S16_LE\nchannels: 2\nrate: 48000 (48000/1)\n"
        runner.check_hw_params(text, 48000)
        for rate in (32000, 44100):
            with self.assertRaises(RuntimeError):
                runner.check_hw_params(text, rate)

    def test_irq_timing_requires_bridge_row(self):
        data = b"123.45 600.00\n336: 100 20 0 0 GICv2 147 Level h713-hdmi-audbrg-probe\n"
        self.assertEqual(runner.parse_timing(data), {"uptime_seconds": 123.45, "bridge_irqs": 120})
        with self.assertRaises(RuntimeError):
            runner.parse_timing(b"123.45 600.00\n335: 0 0 GICv2 145 Level other\n")

    def test_generated_waves_have_exact_rates_and_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            for rate in runner.analysis.RATES:
                path = Path(directory) / f"{rate}.wav"
                runner.make_wave(path, rate)
                with wave.open(str(path)) as stream:
                    self.assertEqual((stream.getframerate(), stream.getnchannels(), stream.getsampwidth()),
                                     (rate, 2, 2))
                    self.assertEqual(stream.getnframes(), 14*rate)
                    tone = stream.readframes(16384)
                    self.assertEqual(runner.analysis.analyze(tone)["capture_rate_hz"], rate)
                    stream.setpos(10*rate)
                    self.assertEqual(stream.readframes(4*rate), bytes(4*rate*4))


if __name__ == "__main__":
    unittest.main()
