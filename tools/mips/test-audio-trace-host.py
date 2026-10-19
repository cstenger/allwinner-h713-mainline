#!/usr/bin/env python3
"""Offline image guards, profile identity and mocked device-reader lifecycle."""
import contextlib
import hashlib
import importlib.util
import io
import json
import mmap
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(filename):
    spec = importlib.util.spec_from_file_location('subject', HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fit(payload):
    def node(name):
        raw = struct.pack('>I', 1) + name + b'\0'
        return raw + bytes(-len(raw) % 4)
    tree = node(b'') + node(b'images') + node(b'uboot')
    tree += struct.pack('>III', 3, len(payload), 0)
    offset = 56 + len(tree)
    tree += payload + bytes(-len(payload) % 4)
    tree += struct.pack('>4I', 2, 2, 2, 9)
    names = b'data\0'
    total = 56 + len(tree) + len(names)
    header = struct.pack('>10I', 0xD00DFEED, total, 56, 56 + len(tree),
                         40, 17, 16, 0, len(names), len(tree))
    return header + bytes(16) + tree + names, offset


def fixture(trace, adjacent=b''):
    firmware = bytearray(0x90000)
    for address, expected, _ in trace.monitor_records():
        struct.pack_into('<I', firmware, address - 0x4B100000, expected)
    uboot, _ = fit(bytes(32) + adjacent + trace.cap.encode(trace.cap.CAPTURE_RECORDS) + bytes(32))
    uboot += bytes(-len(uboot) % 512)
    trace.FW_SHA = hashlib.sha256(firmware).hexdigest()
    trace.UBOOT_SHA = hashlib.sha256(uboot).hexdigest()
    trace.UBOOT_PADDED_SIZE = len(uboot)
    return uboot, bytes(firmware)


class Images(unittest.TestCase):
    def setUp(self):
        self.trace = load('make-audio-monitor-trace.py')

    def test_fit_bounds_and_structure(self):
        good, offset = fit(b'uboot')
        self.assertEqual(self.trace.fit_uboot_region(good), (offset, 5))
        bad = [b'', good[:39], good[:-1]]
        for field, value in [(0, 0), (1, 39), (2, 57), (3, 40), (5, 16),
                             (8, len(good)), (9, len(good))]:
            item = bytearray(good)
            struct.pack_into('>I', item, field * 4, value)
            bad.append(item)
        for where, value in [(56, 2), (56, 3), (56, 42),
                             (offset - 8, len(good)), (offset - 4, 999),
                             (len(good) - 9, 4)]:
            item = bytearray(good)
            struct.pack_into('>I', item, where, value)
            bad.append(item)
        # Unterminated node name, and an early end with nodes still open.
        item = bytearray(good)
        item[60:] = b'x' * (len(item) - 60)
        bad.append(item)
        item = bytearray(good)
        struct.pack_into('>I', item, 64, 9)
        bad.append(item)
        for item in bad:
            with self.subTest(image=bytes(item).hex()), self.assertRaises(ValueError):
                self.trace.fit_uboot_region(item)

    def test_pins_and_prefix_scope(self):
        uboot, fw = fixture(self.trace)
        expected = self.trace.prepare(uboot, fw)
        self.assertEqual(self.trace.prepare(uboot + self.trace.cap.encode(self.trace.cap.CAPTURE_RECORDS), fw), expected)
        for image, firmware in [(uboot[:-1], fw), (b'x' + uboot[1:], fw), (uboot, fw[:-1])]:
            with self.assertRaises(ValueError):
                self.trace.prepare(image, firmware)

    def test_table_ownership(self):
        adjacent = self.trace.cap.encode([self.trace.monitor_records()[0]])
        uboot, fw = fixture(self.trace, adjacent)
        with self.assertRaisesRegex(ValueError, 'already appears'):
            self.trace.prepare(uboot, fw)

    def test_pristine_words_and_census(self):
        uboot, fw = fixture(self.trace)
        damaged = bytearray(fw)
        damaged[0x4C0] = 1
        self.trace.FW_SHA = hashlib.sha256(damaged).hexdigest()
        with self.assertRaisesRegex(ValueError, 'firmware site mismatch'):
            self.trace.prepare(uboot, damaged)
        self.trace.FW_SHA = hashlib.sha256(fw).hexdigest()
        with patch.object(self.trace, 'monitor_records', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'size or relocation'):
                self.trace.prepare(uboot, fw)

    def test_duplicate_or_missing_table(self):
        uboot, fw = fixture(self.trace)
        table = self.trace.cap.encode(self.trace.cap.CAPTURE_RECORDS)
        for payload in (table + table, bytes(len(table))):
            image, _ = fit(payload)
            self.trace.UBOOT_PADDED_SIZE = len(image)
            self.trace.UBOOT_SHA = hashlib.sha256(image).hexdigest()
            with self.assertRaisesRegex(ValueError, 'unique capture'):
                self.trace.prepare(image, fw)

    def test_all_candidate_modes_and_historical_profiles(self):
        for filename, evidence in [
            ('make-audio-monitor-trace.py', '2026-10-07-audio-monitor-trace'),
            ('make-audio-regr-trace.py', '2026-10-07-pll-readback'),
            ('make-audio-dispatch-trace.py', '2026-10-07-audio-dispatch'),
            ('make-audio-pll-retry.py', '2026-10-07-audio-pll-retry'),
            ('make-audio-pll-init.py', '2026-10-07-pll-initialization')]:
            module = load(filename)
            trace = getattr(module, 'monitor', module)
            historical = json.loads((ROOT / 'docs/hdmi-evidence' / evidence / 'audio-monitor-profile.json').read_text())
            self.assertEqual([list(r) for r in trace.monitor_records()], historical['records'])
            self.assertEqual(trace.FIELDS, historical['fields'])
            uboot, fw = fixture(trace)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'uboot').write_bytes(uboot)
                (root/'fw').write_bytes(fw)
                args = ['generator', str(root/'uboot'), str(root/'fw'), str(root/'out'), '--candidate']
                with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
                    trace.main()
                    with self.assertRaises(FileExistsError):
                        trace.main()
                result = root/'out'
                candidate = (result/'uboot-audio-monitor.bin').read_bytes()
                manifest = json.loads((result/'candidate-manifest.json').read_text())
                self.assertEqual((result/'uboot-before.bin').read_bytes(), uboot)
                self.assertEqual(len(candidate), len(uboot))
                changed = [i for i, (a, b) in enumerate(zip(uboot, candidate)) if a != b]
                self.assertEqual(len(changed), manifest['changed_bytes'])
                self.assertTrue(all(manifest['table_offset'] <= i < manifest['table_offset'] + 672 for i in changed))
                self.assertEqual(hashlib.sha256(candidate).hexdigest(), manifest['candidate_sha256'])
                # Invalid input must not create an output directory.
                (root/'fw').write_bytes(b'wrong')
                args[3] = str(root/'invalid')
                with patch.object(sys, 'argv', args), self.assertRaises(ValueError):
                    trace.main()
                self.assertFalse((root/'invalid').exists())


class DeviceReader(unittest.TestCase):
    def setUp(self):
        self.reader = load('read-audio-monitor-trace.py')
        self.maps = []
        self.open = patch.object(self.reader.os, 'open', return_value=99).start()
        self.close = patch.object(self.reader.os, 'close').start()
        self.addCleanup(patch.stopall)
        real_mmap = mmap.mmap

        def fake_map(fd, length, flags, prot, *, offset):
            self.assertEqual((fd, length, flags, prot), (99, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE))
            page = real_mmap(-1, length)
            self.maps.append(page)
            values = {a: (0x3C18AD98 if w == 0x3C18AE34 else w)
                      for a, _, w in self.reader.trace.monitor_records()}
            values.update({self.reader.BASE + off: 0 for off in self.reader.trace.FIELDS.values()})
            values.update({self.reader.BASE+4: 0x434F4D4D, self.reader.BASE+0x80: 0x43414E31,
                           self.reader.BASE+0xFFC: 0x43414E31})
            for address, value in values.items():
                if address & ~0xFFF == offset:
                    struct.pack_into('<I', page, address-offset, value)
            return page
        patch.object(self.reader.mmap, 'mmap', side_effect=fake_map).start()

    def test_profiles_verify_and_close(self):
        for generator in ['make-audio-monitor-trace.py', 'make-audio-regr-trace.py', 'make-audio-dispatch-trace.py']:
            module = load(generator)
            self.reader.trace = getattr(module, 'monitor', module)
            with self.reader.Reader() as device:
                self.reader.verify(device)
                snapshot = self.reader.snapshot(device)
                self.assertFalse(snapshot['monitor_count_changed_during_read'])
                self.assertTrue(set(self.reader.trace.FIELDS) <= snapshot.keys())
                with self.assertRaises(ValueError):
                    device.word(0x06880000)
                with self.assertRaises(ValueError):
                    device.word(self.reader.BASE + 0x101)
            self.assertTrue(all(m.closed for m in self.maps))
            device.close()
            with self.assertRaisesRegex(ValueError, 'closed'):
                device.word(self.reader.BASE+4)
        self.assertEqual(self.close.call_count, 3)

    def test_verify_failure_cleanup(self):
        with self.assertRaisesRegex(ValueError, 'instruction mismatch'):
            with self.reader.Reader() as device:
                # Every instrumented page is verified; corrupt the first instruction.
                address = self.reader.trace.monitor_records()[0][0]
                device.word(address)
                struct.pack_into('<I', device.pages[address & ~0xFFF], address & 0xFFF, 0xFFFFFFFF)
                self.reader.verify(device)
        self.assertTrue(all(m.closed for m in self.maps))
        self.close.assert_called_once_with(99)

    def test_magic_and_canary_guards(self):
        for offset, message in [(4, 'magic absent'), (0x80, 'canary mismatch'), (0xFFC, 'canary mismatch')]:
            with self.assertRaisesRegex(ValueError, message):
                with self.reader.Reader() as device:
                    device.word(self.reader.BASE+offset)
                    struct.pack_into('<I', device.pages[self.reader.BASE], offset, 0)
                    self.reader.verify(device)
            self.assertTrue(all(m.closed for m in self.maps))

    def test_allowlist_rejects_before_mapping(self):
        with self.reader.Reader() as device:
            for address in [0x06880000, self.reader.BASE+0x101, self.reader.BASE+0x120]:
                with self.assertRaises(ValueError):
                    device.word(address)
            self.assertEqual(self.maps, [])

    def test_cli_exception_closes_verified_reader(self):
        with patch.object(sys, 'argv', ['reader']), patch.object(self.reader, 'snapshot', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.reader.main()
        self.assertTrue(all(m.closed for m in self.maps))
        self.close.assert_called_once_with(99)

    def test_mmap_failure_cleanup(self):
        with patch.object(self.reader.mmap, 'mmap', side_effect=OSError('mapping denied')):
            with self.assertRaises(OSError):
                with self.reader.Reader() as device:
                    device.word(self.reader.BASE+4)
        self.close.assert_called_once_with(99)

    def test_cli_validation_before_device_open(self):
        for options in [['--watch', 'nan'], ['--watch', '61'], ['--interval', '0'], ['--watch', 'inf']]:
            with patch.object(sys, 'argv', ['reader'] + options), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.reader.main()
        self.open.assert_not_called()

    def test_functional_verifiers_close_and_publish_no_fields(self):
        for mode in ('retry', 'init'):
            verifier = load(f'verify-audio-pll-{mode}.py')
            self.reader.trace = verifier.reader.trace
            self.assertEqual(self.reader.trace.FIELDS, {})
            with patch.object(sys, 'argv', ['verify']), contextlib.redirect_stdout(io.StringIO()) as output:
                verifier.main()
            self.assertIn(f'PLL_{mode.upper()}_PROFILE_VERIFIED', output.getvalue())
            self.assertTrue(all(m.closed for m in self.maps))
        self.assertEqual(self.close.call_count, 2)

    def test_functional_verifier_failure_cleanup(self):
        for mode in ('retry', 'init'):
            verifier = load(f'verify-audio-pll-{mode}.py')
            with patch.object(sys, 'argv', ['verify']), patch.object(verifier.reader, 'verify', side_effect=ValueError('wrong profile')):
                with self.assertRaisesRegex(ValueError, 'wrong profile'):
                    verifier.main()
        self.assertEqual(self.close.call_count, 2)

    def test_functional_verifier_help_before_device_open(self):
        for mode in ('retry', 'init'):
            verifier = load(f'verify-audio-pll-{mode}.py')
            with patch.object(sys, 'argv', ['verify', '--help']), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    verifier.main()
            self.assertEqual(result.exception.code, 0)
        self.open.assert_not_called()

    def test_snapshot_detects_count_change(self):
        class Changing:
            count = 0
            def word(self, address):
                if address == self_reader.BASE + 0x100:
                    self.count += 1
                    return self.count
                return 0
        self_reader = self.reader
        self.assertTrue(self.reader.snapshot(Changing())['monitor_count_changed_during_read'])


class OfflinePLLModel(unittest.TestCase):
    def test_import_does_not_read_private_input_and_pin_cannot_be_skipped(self):
        path = HERE.parent / 'stock/decode-mips-audio-pll.py'
        spec = importlib.util.spec_from_file_location('model', path)
        model = importlib.util.module_from_spec(spec)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('unexpected input read')):
            spec.loader.exec_module(model)
        with patch.object(model, 'Uc', side_effect=AssertionError('emulation before pin check')):
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                model.run(b'wrong firmware', 0x8B13BCB8)

    def test_model_rejects_wrong_init_branch(self):
        path = HERE.parent / 'stock/decode-mips-audio-pll.py'
        spec = importlib.util.spec_from_file_location('model', path)
        model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model)
        firmware = bytes(0x3C62C)
        with patch.object(model, 'FW_SHA', hashlib.sha256(firmware).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'branch mismatch'):
                model.run(firmware, 0x8B13C524, initialize_zero=True)


class WithdrawnInstaller(unittest.TestCase):
    def test_withdrawn_installer(self):
        result = subprocess.run([sys.executable, str(HERE/'install-audio-monitor-trace.py'),
                                 '/nonexistent/profile', '--port', '/nonexistent/serial'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('withdrawn', result.stderr)
        self.assertIn('no device opened', result.stderr)


if __name__ == '__main__':
    unittest.main()
