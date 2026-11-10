#!/usr/bin/env python3
"""Host-only exact-environment and fault/rollback checks."""
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

spec = importlib.util.spec_from_file_location('countdown', Path(__file__).with_name('autoboot-countdown.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def blob(body):
    data = body.ljust(m.SIZE-4, b'\xff')
    return struct.pack('<I', zlib.crc32(data))+data


class Countdown(unittest.TestCase):
    def setUp(self):
        self.before = blob(b'bootcmd=run guarded\0bootdelay=5\0preboot=hold recovery\0serial#=fixture\0\0')
        pin = patch.object(m, 'BEFORE', m.sha(self.before))
        pin.start()
        self.addCleanup(pin.stop)

    def test_exact_one_payload_byte_and_crc_only(self):
        after = m.candidate(self.before)
        self.assertEqual(len(after), m.SIZE)
        values = m.parse(after)
        self.assertEqual(values.pop(b'bootdelay'), b'0')
        old = m.parse(self.before)
        old.pop(b'bootdelay')
        self.assertEqual(values, old)
        differences = [i for i in range(m.SIZE) if self.before[i] != after[i]]
        self.assertEqual(len([i for i in differences if i >= 4]), 1)
        self.assertEqual(after[-100:], self.before[-100:])

    def test_wrong_preimage_crc_duplicate_or_delay_refused(self):
        bad = bytearray(self.before)
        bad[-1] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'CRC'):
            m.candidate(bytes(bad))
        for body in (b'bootdelay=5\0bootdelay=5\0\0', b'bootdelay=2\0\0'):
            data = blob(body)
            with patch.object(m, 'BEFORE', m.sha(data)):
                with self.assertRaises(RuntimeError):
                    m.candidate(data)
        with self.assertRaisesRegex(RuntimeError, 'unrecognized'):
            m.candidate(blob(b'bootdelay=5\0other=changed\0\0'))

    def exercise(self, fault=None):
        after = m.candidate(self.before)
        with tempfile.TemporaryDirectory() as directory, patch.object(m, 'OFFSET', 4096):
            root = Path(directory)
            disk = root/'disk'
            image = b'L'*4096+self.before+b'R'*4096
            disk.write_bytes(image)
            fd = os.open(disk, os.O_RDWR)
            self.addCleanup(os.close, fd)
            count = 0
            real_write = os.pwrite
            def write_once(descriptor, data, offset):
                nonlocal count
                count += 1
                if count == 1 and fault == 'short':
                    return real_write(descriptor, data[:100], offset)
                if count == 1 and fault == 'readback':
                    real_write(descriptor, bytes([data[0]^1])+data[1:], offset)
                    return len(data)
                return real_write(descriptor, data, offset)
            def context():
                self.assertEqual(os.pread(fd, 4096, 0), b'L'*4096)
                self.assertEqual(os.pread(fd, 4096, 4096+m.SIZE), b'R'*4096)
            with patch.object(m.os, 'pwrite', write_once):
                if fault:
                    with self.assertRaises(RuntimeError):
                        m.transaction(fd, self.before, after, root/'backup', context)
                    self.assertEqual(disk.read_bytes(), image)
                    self.assertTrue((root/'backup/ROLLED_BACK').exists())
                else:
                    m.transaction(fd, self.before, after, root/'backup', context)
                    self.assertEqual(os.pread(fd, m.SIZE, 4096), after)
                    self.assertTrue((root/'backup/COMMITTED').exists())
                    m.transaction(fd, after, self.before, root/'rollback', context)
                    self.assertEqual(disk.read_bytes(), image)
            self.assertFalse((root/'backup/INCOMPLETE').exists())
            self.assertEqual((root/'backup/environment-before.bin').read_bytes(), self.before)

    def test_write_and_explicit_rollback(self):
        self.exercise()

    def test_short_write_restores_original(self):
        self.exercise('short')

    def test_readback_failure_restores_original(self):
        self.exercise('readback')


if __name__ == '__main__':
    unittest.main()
