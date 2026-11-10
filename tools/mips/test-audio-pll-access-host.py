#!/usr/bin/env python3
"""Offline second-table guards, reproducible shim builds and profile trust.

Uses synthetic images and mocked device I/O; no private firmware is required.
Build tests require clang, ld.lld and pyelftools.
"""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import importlib.util

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(filename):
    spec = importlib.util.spec_from_file_location('subject', HERE/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = load('test-audio-trace-host.py')


def synthetic(word, shim):
    firmware = bytearray(0x90000)
    for address, expected, _ in word.init.records() + word.records(shim):
        struct.pack_into('<I', firmware, address-0x4B100000, expected)
    payload = bytearray(0x95000)
    _, dataoff = helpers.fit(b'')
    base = 601380
    table = word.cap.encode(word.cap.CAPTURE_RECORDS)
    payload[base-dataoff:base-dataoff+len(table)] = table
    old = sum((word.cap.progress_group(0x4B104000+i*32, marker, 0,
                                      0x4B108000+i*4, 0, 0)
               for i, marker in enumerate(word.MARKERS)), [])
    payload[word.START-dataoff:word.START-dataoff+864] = word.cap.encode(old)
    image, _ = helpers.fit(payload)
    image += bytes(-len(image) % 512)
    word.monitor.UBOOT_PADDED_SIZE = len(image)
    word.monitor.UBOOT_SHA = hashlib.sha256(image).hexdigest()
    word.monitor.FW_SHA = hashlib.sha256(firmware).hexdigest()
    return image, bytes(firmware)


class Images(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        word = load('make-audio-pll-word.py')
        byte = load('make-audio-pll-byte-read.py')
        cls.shims = {'word': word.build_shim(), 'byte-read': byte.word.build_shim(
            'audio-pll-byte-read.S', byte.SHIM_SIZE, byte.SHIM_SHA)}

    def setUp(self):
        self.word = load('make-audio-pll-word.py')
        self.shim = self.shims['word']
        self.image, self.firmware = synthetic(self.word, self.shim)

    def repin(self, image):
        self.word.monitor.UBOOT_SHA = hashlib.sha256(image).hexdigest()
        return bytes(image)

    def test_second_table_boundaries_and_suffix(self):
        candidate, profile = self.word.prepare(self.image, self.firmware, self.shim)
        offset = profile['fit_table_offset']
        changed = [i for i, (a, b) in enumerate(zip(self.image, candidate)) if a != b]
        self.assertEqual(len(candidate), len(self.image))
        self.assertTrue(changed)
        self.assertTrue(all(offset <= i < offset+672 or self.word.START <= i < self.word.START+864 for i in changed))
        self.assertEqual(self.word.prepare(self.image+b'ignored readback suffix', self.firmware, self.shim), (candidate, profile))
        self.assertEqual(self.word.cap.census(profile['records']), (16, 16))

    def test_marker_and_hook_preimages(self):
        for relative in (12, 4*16+12, 5*16+8):
            image = bytearray(self.image)
            image[self.word.START+relative] ^= 1
            with self.assertRaisesRegex(ValueError, 'preimage mismatch'):
                self.word.prepare(self.repin(image), self.firmware, self.shim)

    def test_ownership_and_pristine_cave(self):
        image = bytearray(self.image)
        word = self.word
        image[word.TABLE_LO:word.TABLE_LO+16] = word.cap.encode([word.records(self.shim)[0]])
        with self.assertRaisesRegex(ValueError, 'already owned'):
            word.prepare(self.repin(image), self.firmware, self.shim)
        firmware = bytearray(self.firmware)
        firmware[word.CAVE-0x8B100000] = 1
        word.monitor.UBOOT_SHA = hashlib.sha256(self.image).hexdigest()
        word.monitor.FW_SHA = hashlib.sha256(firmware).hexdigest()
        with self.assertRaisesRegex(ValueError, 'firmware site mismatch'):
            word.prepare(self.image, firmware, self.shim)

    def test_second_table_bounds_and_record_census(self):
        with patch.object(self.word, 'TABLE_HI', len(self.image)+16):
            with self.assertRaisesRegex(ValueError, 'outside U-Boot data'):
                self.word.prepare(self.image, self.firmware, self.shim)
        records = self.word.records(self.shim)
        for altered in (records[:-1], [records[0]]+records[:-1],
                        [(a, e, 0 if w == 0x3C1AAE34 else w) for a, e, w in records]):
            with patch.object(self.word, 'records', return_value=altered):
                with self.assertRaisesRegex(ValueError, 'size, uniqueness or relocation'):
                    self.word.prepare(self.image, self.firmware, self.shim)

    def test_shim_pins(self):
        for shim in (self.shim[:-4], b'\0'*len(self.shim), self.shims['byte-read']):
            with self.assertRaisesRegex(ValueError, 'length/SHA256'):
                self.word.records(shim)

    def test_historical_profiles_and_wrong_mode(self):
        for mode, directory in [('word', 'word-access'), ('byte-read', 'byte-read')]:
            module = load(f'make-audio-pll-{mode}.py')
            word = getattr(module, 'word', module)
            profile = json.loads((ROOT/f'docs/hdmi-evidence/2026-10-07-pll-{directory}/audio-monitor-profile.json').read_text())
            records = word.validated_records(profile, module.SHIM_SIZE, module.SHIM_SHA)
            self.assertEqual([list(r) for r in records], profile['records'])
            self.assertEqual(word.records(self.shims[mode]), records[42:])
            for change in ('address', 'word', 'hash', 'fields', 'duplicate', 'negative'):
                bad = copy.deepcopy(profile)
                if change == 'address': bad['records'][0][0] = 0x06880000
                elif change == 'word': bad['records'][42][2] ^= 1
                elif change == 'hash': bad['firmware_sha256'] = 'wrong'
                elif change == 'fields': bad['fields'] = {'unexpected': 0x120}
                elif change == 'duplicate': bad['records'][-1] = bad['records'][0]
                else: bad['records'][0][2] = -1
                with self.assertRaises(ValueError):
                    word.validated_records(bad, module.SHIM_SIZE, module.SHIM_SHA)
            if mode == 'byte-read':
                with self.assertRaises(ValueError):
                    self.word.validated_records(profile)

    def test_cli_outputs_and_reuse_refusal(self):
        for mode in ('word', 'byte-read'):
            module = load(f'make-audio-pll-{mode}.py')
            word = getattr(module, 'word', module)
            image, firmware = synthetic(word, self.shims[mode])
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root/'uboot').write_bytes(image)
                (root/'fw').write_bytes(firmware)
                argv = ['generator', str(root/'uboot'), str(root/'fw'), str(root/'out')]
                with patch.object(sys, 'argv', argv), patch.object(word, 'build_shim', return_value=self.shims[mode]), contextlib.redirect_stdout(io.StringIO()):
                    module.main()
                    with self.assertRaises(FileExistsError): module.main()
                    (root/'fw').write_bytes(b'wrong')
                    argv[-1] = str(root/'invalid')
                    with self.assertRaisesRegex(ValueError, 'SHA256'): module.main()
                self.assertFalse((root/'invalid').exists())
                manifest = json.loads((root/'out/candidate-manifest.json').read_text())
                self.assertFalse(manifest['storage_modified'])
                self.assertEqual(manifest['records'], 96)
                self.assertEqual((root/'out/uboot-before.bin').read_bytes(), image)


class ProfileCLI(unittest.TestCase):
    def test_bad_profile_and_help_never_open_device(self):
        for mode in ('word', 'byte-read'):
            module = load(f'verify-audio-pll-{mode}.py')
            reader = getattr(module, 'verifier', module).reader
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary)/'profile.json'
                for bad in ([], {}, {'records': [[0x06880000, 0, 0]]}):
                    path.write_text(json.dumps(bad))
                    with patch.object(sys, 'argv', ['verify', str(path)]), patch.object(reader.os, 'open') as opened:
                        with self.assertRaises(ValueError): module.main()
                        opened.assert_not_called()
                with patch.object(sys, 'argv', ['verify', '--help']), patch.object(reader.os, 'open') as opened, contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as result: module.main()
                    self.assertEqual(result.exception.code, 0)
                    opened.assert_not_called()

    def test_verified_profile_cleanup_and_k0_relocation(self):
        # Initialize only the reusable harness, keeping this suite's test count
        # separate from the earlier monitor/retry test suite.
        for mode, directory in [('word', 'word-access'), ('byte-read', 'byte-read')]:
            harness = helpers.DeviceReader()
            harness.setUp()
            try:
                module = load(f'verify-audio-pll-{mode}.py')
                verifier = getattr(module, 'verifier', module)
                profile_path = ROOT/f'docs/hdmi-evidence/2026-10-07-pll-{directory}/audio-monitor-profile.json'
                profile = json.loads(profile_path.read_text())
                from types import SimpleNamespace
                harness.reader.trace = SimpleNamespace(monitor_records=lambda: profile['records'], FIELDS={})
                with patch.object(sys, 'argv', ['verify', str(profile_path)]), contextlib.redirect_stdout(io.StringIO()) as output:
                    module.main()
                self.assertIn('96 records', output.getvalue())
                self.assertTrue(all(m.closed for m in harness.maps))
                harness.close.assert_called_once_with(99)
                # A valid file with mismatched installed code must still close
                # the mapped page and descriptor on verification failure.
                bad_records = copy.deepcopy(profile['records'])
                bad_records[0][2] ^= 1
                harness.reader.trace = SimpleNamespace(monitor_records=lambda: bad_records, FIELDS={})
                harness.close.reset_mock()
                with patch.object(sys, 'argv', ['verify', str(profile_path)]):
                    with self.assertRaisesRegex(ValueError, 'instruction mismatch'):
                        module.main()
                self.assertTrue(all(m.closed for m in harness.maps))
                harness.close.assert_called_once_with(99)
            finally:
                harness.doCleanups()


if __name__ == '__main__':
    unittest.main()
