#!/usr/bin/env python3
"""Exercise install-elog-level.py on fake roots (no board access)."""
import hashlib, importlib.util, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer', HERE / 'install-elog-level.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sha = lambda b: hashlib.sha256(b).hexdigest()
OLD = (HERE / 'test-payloads' / m.OLD_SHELL).read_bytes()
# Frozen copies of this installer's pinned payloads: the tree's mips-shell.py and
# unit have moved on since (2026-11-18 elog confirmation), this transaction has not.
NEW = (HERE / 'test-payloads' / m.NEW_SHELL).read_bytes()
UNIT = (HERE / 'test-payloads' / m.NEW_UNIT).read_bytes()


class ElogInstall(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root = Path(t.name) / 'root'; self.bundle = Path(t.name) / 'bundle'
        for d in (m.io.BACKEND, m.io.STATE, 'usr/lib/systemd/system-shutdown', 'proc/device-tree',
                  'proc/sys/kernel/random', m.SYSTEMD + '/multi-user.target.wants'):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        (self.root / 'proc/device-tree/model').write_text('HY200 QZ713DF_A1 (Allwinner H713)\0')
        (self.root / 'proc/sys/kernel/random/boot_id').write_text('B1')
        be = self.root / m.io.BACKEND
        (be / 'mips-shell.py').write_bytes(OLD); (be / 'other.py').write_bytes(b'other')
        self.manifest = ('%s  ./mips-shell.py\n%s  ./other.py\n' % (sha(OLD), sha(b'other'))).encode()
        (be / 'SHA256SUMS').write_bytes(self.manifest)
        (self.bundle / m.io.BACKEND).mkdir(parents=True)
        (self.bundle / m.io.BACKEND / 'mips-shell.py').write_bytes(NEW)
        (self.bundle / m.io.BACKEND / m.UNIT).write_bytes(UNIT)
        for p in (patch.object(m, 'OLD_MANIFEST', sha(self.manifest)),
                  patch.object(m.io, 'metadata', lambda p: dict(m.ATTRS))):
            p.start(); self.addCleanup(p.stop)

    def snapshot(self):
        out = {}
        for p in sorted(self.root.rglob('*')):
            rel = str(p.relative_to(self.root))
            if rel.startswith(m.io.STATE) or rel.startswith('proc'): continue
            out[rel] = ('link', os.readlink(p)) if p.is_symlink() else (p.read_bytes() if p.is_file() else 'dir')
        return out

    def test_install_matches_release_layout_and_rolls_back_exactly(self):
        self.assertEqual((sha(NEW), sha(UNIT)), (m.NEW_SHELL, m.NEW_UNIT))
        original = self.snapshot()
        self.assertEqual(m.install(self.root, self.bundle, 'B1')['phase'], 'would-install')
        self.assertEqual(self.snapshot(), original)
        r = m.install(self.root, self.bundle, 'B1', apply=True)
        be = self.root / m.io.BACKEND; units = self.root / m.SYSTEMD
        self.assertEqual((be / 'mips-shell.py').read_bytes(), NEW)
        self.assertEqual((be / m.UNIT).read_bytes(), UNIT)
        self.assertEqual((units / m.UNIT).read_bytes(), UNIT)
        self.assertEqual(os.readlink(self.root / m.WANTS), '../' + m.UNIT)
        sums = (be / 'SHA256SUMS').read_text()
        self.assertIn(m.NEW_SHELL + '  ./mips-shell.py', sums)
        self.assertTrue(sums.endswith(m.NEW_UNIT + '  ./' + m.UNIT + '\n'))
        m.io.verify_generation(self.root, (be / 'SHA256SUMS').read_bytes())
        self.assertTrue((Path(r['backup']) / 'COMMITTED').exists())
        m.rollback(self.root, Path(r['backup']), 'B1', apply=True)
        self.assertEqual(self.snapshot(), original)

    def test_refusals(self):
        be = self.root / m.io.BACKEND
        (self.bundle / m.io.BACKEND / 'mips-shell.py').write_bytes(NEW + b'#')
        with self.assertRaisesRegex(RuntimeError, 'payload checksum'): m.install(self.root, self.bundle, 'B1')
        (self.bundle / m.io.BACKEND / 'mips-shell.py').write_bytes(NEW)
        with self.assertRaisesRegex(RuntimeError, 'boot ID'): m.install(self.root, self.bundle, 'B2')
        (be / 'mips-shell.py').write_bytes(OLD + b'#')
        with self.assertRaisesRegex(RuntimeError, 'unexpected installed'): m.install(self.root, self.bundle, 'B1')
        (be / 'mips-shell.py').write_bytes(OLD)
        (self.root / m.SYSTEMD / m.UNIT).write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'target exists'): m.install(self.root, self.bundle, 'B1')
        (self.root / m.SYSTEMD / m.UNIT).unlink()
        r = m.install(self.root, self.bundle, 'B1', apply=True)
        (be / 'other.py').write_bytes(b'changed')
        os.unlink(self.root / m.WANTS); os.symlink('/elsewhere', self.root / m.WANTS)
        with self.assertRaisesRegex(RuntimeError, 'foreign wants link'): m.rollback(self.root, Path(r['backup']), 'B1')


if __name__ == '__main__':
    unittest.main()
