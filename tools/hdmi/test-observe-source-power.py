#!/usr/bin/env python3
"""Offline safety checks for the experimental DRAM-only observer."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('observer', Path(__file__).with_name('observe-source-power.py'))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class ObserverTests(unittest.TestCase):
    def test_rejects_mmio_unaligned_and_outside_dram_before_mapping(self):
        mem = observer.Memory.__new__(observer.Memory)
        mem.pages = {}
        for address in (0x0684037A, 0x07091000, observer.LOW - 4,
                        observer.HIGH, observer.LOW + 1, 0):
            with self.subTest(address=hex(address)), self.assertRaises(ValueError):
                mem.word(address)
        self.assertEqual(mem.pages, {})

    def test_firmware_pin_ranges_are_inside_dram_and_nonempty(self):
        self.assertEqual(len(observer.CODE_PINS), 4)
        for pin in observer.CODE_PINS.values():
            self.assertGreaterEqual(pin['address'], observer.LOW)
            self.assertLessEqual(pin['address'] + pin['bytes'], observer.HIGH)
            self.assertEqual(pin['address'] % 4, 0)
            self.assertEqual(pin['bytes'] % 4, 0)
            self.assertEqual(len(pin['sha256']), 64)

    def test_missing_manager_stops_pointer_chase(self):
        class FakeMemory:
            def word(self, address):
                if address == observer.ROOT:
                    return observer.LOW
                if address == observer.LOW:
                    return 0
                raise AssertionError('followed unexpected pointer')
        with self.assertRaisesRegex(ValueError, 'manager identity'):
            observer.snapshot(FakeMemory())


if __name__ == '__main__':
    unittest.main()
