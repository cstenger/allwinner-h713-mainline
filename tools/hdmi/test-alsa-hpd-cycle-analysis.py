#!/usr/bin/env python3
"""Reject stale per-cycle markers, wrong channel audio and incomplete capture."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('cycles',Path(__file__).with_name('run-alsa-hpd-cycle-test.py'))
cycles=importlib.util.module_from_spec(spec);spec.loader.exec_module(cycles)


class Recovery(unittest.TestCase):
    def test_fresh_unique_markers_and_channels(self):
        rate=48000;seconds=40
        good=np.zeros((seconds*rate,2),dtype='<i2');phases=[]
        t=np.arange(6*rate)/rate
        for index,start in enumerate((2,12,22)):
            frequencies=(2000,1000) if index%2 else (1000,2000)
            data=np.column_stack([6500*np.sin(2*np.pi*f*t) for f in frequencies]).astype('<i2')
            data[2*rate:2*rate+16384,0]=cycles.marker_analysis.marker(index)
            good[start*rate:(start+6)*rate]=data
            phases.append({'index':index,'sample_frame':(start+1)*rate,'swapped':bool(index%2)})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'capture.raw'
            def check(data):
                path.write_bytes(data.astype('<i2').tobytes())
                return cycles.analyze_raw(path,seconds,phases,3)['pass']
            self.assertTrue(check(good))
            stale=good.copy();stale[14*rate:14*rate+16384,0]=cycles.marker_analysis.marker(0)
            self.assertFalse(check(stale))
            missing=good.copy();missing[22*rate:28*rate]=0
            self.assertFalse(check(missing))
            wrong=good.copy();wrong[15*rate:16*rate]=wrong[15*rate:16*rate,::-1]
            self.assertFalse(check(wrong))
            dirty=good.copy();dirty[-1,0]=1
            self.assertFalse(check(dirty))
            with self.assertRaises(RuntimeError):check(good[:-1])


if __name__=='__main__':unittest.main()
