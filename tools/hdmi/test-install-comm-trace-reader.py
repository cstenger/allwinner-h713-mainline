#!/usr/bin/env python3
"""Exercise install-comm-trace-reader.py on fake roots (no board access)."""
import hashlib, importlib.util, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer', HERE / 'install-comm-trace-reader.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sha = lambda b: hashlib.sha256(b).hexdigest()
OLD = (HERE / 'test-payloads' / m.OLD_READER).read_bytes()
NEW = (HERE.parent / 'mips/read-comm-trace.py').read_bytes()


class Reader(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root = Path(t.name) / 'root'; self.bundle = Path(t.name) / 'bundle'
        for d in (m.io.BACKEND, m.io.STATE, 'usr/lib/systemd/system-shutdown', 'proc/device-tree',
                  'proc/sys/kernel/random'):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        (self.root / 'proc/device-tree/model').write_text('HY200 QZ713DF_A1 (Allwinner H713)\0')
        (self.root / 'proc/sys/kernel/random/boot_id').write_text('B1')
        be = self.root / m.io.BACKEND
        (be / 'read-comm-trace.py').write_bytes(OLD)
        (be / 'h713-hdmi-session.py').write_bytes(b'session')
        self.manifest = ('%s  ./h713-hdmi-session.py\n%s  ./read-comm-trace.py\n' % (sha(b'session'), sha(OLD))).encode()
        (be / 'SHA256SUMS').write_bytes(self.manifest)
        (self.bundle / m.io.BACKEND).mkdir(parents=True)
        (self.bundle / m.io.BACKEND / 'read-comm-trace.py').write_bytes(NEW)
        self.p = patch.object(m, 'OLD_MANIFEST', sha(self.manifest)); self.p.start(); self.addCleanup(self.p.stop)
        self.q = patch.object(m.io, 'metadata', lambda p: {'mode': 0o644, 'uid': 0, 'gid': 0})
        self.q.start(); self.addCleanup(self.q.stop)

    def test_install_and_exact_rollback(self):
        self.assertEqual(sha(NEW), m.NEW_READER)
        self.assertEqual(m.install(self.root, self.bundle, 'B1')['phase'], 'would-install')
        r = m.install(self.root, self.bundle, 'B1', apply=True)
        be = self.root / m.io.BACKEND
        self.assertEqual(sha((be / 'read-comm-trace.py').read_bytes()), m.NEW_READER)
        m.io.verify_generation(self.root, (be / 'SHA256SUMS').read_bytes())
        self.assertIn(m.NEW_READER + '  ./read-comm-trace.py', (be / 'SHA256SUMS').read_text())
        backup = Path(r['backup'])
        self.assertTrue((backup / 'COMMITTED').exists() and not (backup / 'INCOMPLETE').exists())
        m.rollback(self.root, backup, 'B1', apply=True)
        self.assertEqual((be / 'read-comm-trace.py').read_bytes(), OLD)
        self.assertEqual((be / 'SHA256SUMS').read_bytes(), self.manifest)

    def test_refusals(self):
        be = self.root / m.io.BACKEND
        (self.bundle / m.io.BACKEND / 'read-comm-trace.py').write_bytes(NEW + b'#')
        with self.assertRaisesRegex(RuntimeError, 'payload checksum'): m.install(self.root, self.bundle, 'B1')
        (self.bundle / m.io.BACKEND / 'read-comm-trace.py').write_bytes(NEW)
        with self.assertRaisesRegex(RuntimeError, 'boot ID'): m.install(self.root, self.bundle, 'B2')
        (be / 'read-comm-trace.py').write_bytes(OLD + b'#')
        with self.assertRaisesRegex(RuntimeError, 'unexpected installed'): m.install(self.root, self.bundle, 'B1')
        (be / 'read-comm-trace.py').write_bytes(OLD)
        r = m.install(self.root, self.bundle, 'B1', apply=True)
        (be / 'h713-hdmi-session.py').write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'unrelated backend'): m.rollback(self.root, Path(r['backup']), 'B1')


if __name__ == '__main__':
    unittest.main()
