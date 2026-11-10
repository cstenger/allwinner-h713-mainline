#!/usr/bin/env python3
"""Controls for marker drift, missing/replayed markers and frame integrity."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('endurance',Path(__file__).with_name('audio-endurance-analysis.py'))
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)


class Endurance(unittest.TestCase):
    def test_measured_drift_and_damaged_capture(self):
        seconds=90;rate=analysis.RATE
        t=np.arange(seconds*rate)/rate
        normal=np.column_stack([6500*np.sin(2*np.pi*f*t) for f in (1000,2000)]).astype('<i2')
        normal[-3*rate:]=0
        positions=analysis.marker_frames(seconds)
        drift=125e-6;delay=1.1*rate
        good=normal.copy()
        for index,source in enumerate(positions):
            frame=round(delay+source*(1+drift))
            template=analysis.marker(index)
            warped=np.interp(np.arange(round(len(template)*(1+drift)))/(1+drift),np.arange(len(template)),template).astype('<i2')
            good[frame:frame+len(warped),0]=warped
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'capture.raw'
            def check(data):
                path.write_bytes(data.astype('<i2').tobytes())
                return analysis.analyze_raw(path,seconds)
            result=check(good)
            self.assertTrue(result['pass'],result)
            self.assertAlmostEqual(result['source_relative_drift_ppm'],125,delta=1)
            stale=good.copy();frame=round(delay+positions[1]*(1+drift))
            stale[frame:frame+analysis.MARKER_FRAMES,0]=analysis.marker(0)
            self.assertFalse(check(stale)['pass'])
            missing=good.copy();missing[frame:frame+analysis.MARKER_FRAMES,0]=0
            self.assertFalse(check(missing)['pass'])
            shifted=good.copy();frame=round(delay+positions[2]*(1+drift))
            shifted[frame:frame+analysis.MARKER_FRAMES+300,0]=0
            shifted[frame+300:frame+300+analysis.MARKER_FRAMES,0]=analysis.marker(2)
            self.assertFalse(check(shifted)['pass'])
            dirty=good.copy();dirty[-1,0]=1
            self.assertFalse(check(dirty)['pass'])
            with self.assertRaises(RuntimeError):check(good[:-1])

    def test_board_clock_cadence(self):
        samples=[{'before_raw':100+i*30-.0001,'after_raw':100+i*30+.0001,'hw_ptr':int(i*30*48000*1.000075)} for i in range(5)]
        result=analysis.analyze_clock(samples)
        self.assertAlmostEqual(result['capture_vs_board_raw_ppm'],75,delta=.1)


if __name__=='__main__':unittest.main()
