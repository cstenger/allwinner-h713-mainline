#!/usr/bin/env python3
"""Host-only input validation tests and deliberate fault checks."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

SOURCE = Path(__file__).with_name('check-uboot-migration-inputs.py')
spec = importlib.util.spec_from_file_location('migration', sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != '--mutations' else SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def environment(body):
    payload = body.ljust(65532, b'\0')
    return struct.pack('<I', zlib.crc32(payload)) + payload


class Inputs(unittest.TestCase):
    def test_valid_environment(self):
        self.assertEqual(m.check_environment(environment(b'a=one\0b=two\0\0'), {'a': 'one'}), 2)

    def test_crc_failure(self):
        bad = bytearray(environment(b'a=one\0\0'))
        bad[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC'):
            m.check_environment(bad, {})

    def test_policy_failure(self):
        with self.assertRaisesRegex(ValueError, 'policy'):
            m.check_environment(environment(b'bootcmd=wrong\0\0'), {'bootcmd': 'guarded'})

    def test_duplicate_failure(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            m.check_environment(environment(b'a=one\0a=two\0\0'), {})

    def test_identity_failure(self):
        digest = hashlib.sha256(b'ab').hexdigest()
        m.check_blob(b'ab', 2, digest)
        with self.assertRaisesRegex(ValueError, 'size'):
            m.check_blob(b'ab', 3, digest)
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            m.check_blob(b'cd', 2, digest)

    def test_proper_header(self):
        data = struct.pack('>II', 0xd00dfeed, 960817).ljust(1877 * 512, b'\0')
        old = m.PROPER_HASH
        try:
            m.PROPER_HASH = hashlib.sha256(data).hexdigest()
            m.check_proper(data)
            bad = bytearray(data)
            bad[0] ^= 1
            m.PROPER_HASH = hashlib.sha256(bad).hexdigest()
            with self.assertRaisesRegex(ValueError, 'header'):
                m.check_proper(bad)
        finally:
            m.PROPER_HASH = old

    def test_observed_address(self):
        self.assertEqual(m.legacy_lba(7818182656), 0x32ec00)


def mutations():
    original = SOURCE.read_text()
    variants = {
        'environment count lost': ('return len(values)', 'return 0'),
        'CRC unchecked': ("struct.unpack('<I', data[:4])[0] == zlib.crc32(data[4:])", 'True'),
        'policy unchecked': ('values.get(key.encode()) == value.encode()', 'True'),
        'duplicates accepted': ('key and key not in values', 'key'),
        'size unchecked': ('len(data) == size', 'True'),
        'hash unchecked': ('hashlib.sha256(data).hexdigest() == digest', 'True'),
        'FIT header unchecked': ('magic == 0xd00dfeed and size == 960817', 'True'),
        'address truncation omitted': ('((capacity + narrowed) & 0xffffffff) // 512', '(capacity + narrowed) // 512'),
    }
    with tempfile.TemporaryDirectory() as directory:
        for name, (before, after) in variants.items():
            assert original.count(before) == 1, name
            candidate = Path(directory) / 'mutant.py'
            candidate.write_text(original.replace(before, after))
            result = subprocess.run([sys.executable, __file__, str(candidate)], capture_output=True)
            assert result.returncode != 0 and b'FAILED' in result.stderr, name
            print('CAUGHT:', name)
    print('PASS all 8 deliberate faults caught')


if __name__ == '__main__':
    if '--mutations' in sys.argv:
        mutations()
    else:
        unittest.main(argv=[sys.argv[0]])
