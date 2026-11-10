#!/usr/bin/env python3
"""Offline serial-interrupt and pinned logo-free DT/command checks."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/serial'))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
catch=load('catch',ROOT/'tools/serial/catch-cold-uboot.py')
boot=load('boot',ROOT/'tools/hdmi/prepare-dsp-observe-boot.py')


class Capture(unittest.TestCase):
 def test_interrupt_requires_fresh_spl_and_is_sent_once(self):
  s=catch.Catch();self.assertIsNone(s.feed(b'Linux text\n'))
  self.assertIsNone(s.feed(b'U-Boot SP'));self.assertIsNone(s.feed(b'L 2026\n'))
  self.assertIsNone(s.feed(b'Hit any key to stop auto'))
  self.assertEqual(s.feed(b'boot: 5'),'space')
  self.assertIsNone(s.feed(b'Hit any key to stop autoboot: 4'))
  self.assertEqual(s.feed(b'\r\n=> '),'done')
 def test_lost_autoboot_window_and_repeated_boot_fail(self):
  for text in (b'U-Boot SPL x\nH713 RESET v1 stage=pre_workspace',b'U-Boot SPL x\nU-Boot SPL y\n'):
   with self.subTest(text=text):
    with self.assertRaises(RuntimeError):catch.Catch().feed(text)


class Artifact(unittest.TestCase):
 def test_wrong_fit_refused_before_output_creation(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'bad.fit').write_bytes(b'not the pinned image')
   with self.assertRaises(ValueError):boot.prepare(p/'bad.fit',Path('/no/dumpimage'),p/'out')
   self.assertFalse((p/'out').exists())


if __name__=='__main__':unittest.main()
