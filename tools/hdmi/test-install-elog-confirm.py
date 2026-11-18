#!/usr/bin/env python3
"""Exercise the elog-confirmation transaction and partial-write recovery on fake roots."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer', HERE/'install-elog-confirm.py')
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def payload(digest):
    """The frozen copy of a pinned installer payload (test-payloads/<sha256>)."""
    data = (HERE/'test-payloads'/digest).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, digest
    return data


class Install(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)/'root';self.bundle = Path(temp.name)/'bundle'
        for name in (m.io.BACKEND, m.io.STATE, 'usr/lib/systemd/system-shutdown', 'proc/device-tree',
                     'proc/sys/kernel/random', m.SYSTEMD + '/multi-user.target.wants'):
            (self.root/name).mkdir(parents=True, exist_ok=True)
        (self.root/'proc/device-tree/model').write_text('HY200 QZ713DF_A1 (Allwinner H713)\0')
        (self.root/'proc/sys/kernel/random/boot_id').write_text('B1')
        self.addCleanup(patch.stopall)
        old_shell, old_unit = b'original shell', b'original unit'
        patch.object(m, 'OLD_SHELL', m.sha(old_shell)).start()
        patch.object(m, 'OLD_UNIT', m.sha(old_unit)).start()
        patch.object(m, 'FILES', ((m.io.BACKEND + '/' + m.SHELL, m.sha(old_shell), m.NEW_SHELL),
                                  (m.io.BACKEND + '/' + m.UNIT, m.sha(old_unit), m.NEW_UNIT),
                                  (m.SYSTEMD + '/' + m.UNIT, m.sha(old_unit), m.NEW_UNIT))).start()
        real_metadata = m.io.metadata
        def attrs(path):
            result = real_metadata(path);result.update(uid=0, gid=0);return result
        patch.object(m.io, 'metadata', attrs).start()
        for rel, data in ((m.io.BACKEND + '/' + m.SHELL, old_shell), (m.io.BACKEND + '/' + m.UNIT, old_unit),
                          (m.SYSTEMD + '/' + m.UNIT, old_unit)):
            p = self.root/rel;p.write_bytes(data);p.chmod(0o644)
        (self.root/m.WANTS).symlink_to('../' + m.UNIT)
        (self.root/m.io.BACKEND/'unchanged.ko').write_bytes(b'unchanged module')
        sums = (m.sha(old_shell) + '  ./' + m.SHELL + '\n' + m.sha(b'unchanged module') + '  ./unchanged.ko\n'
                + m.sha(old_unit) + '  ./' + m.UNIT + '\n')
        (self.root/m.MANIFEST).write_text(sums);(self.root/m.MANIFEST).chmod(0o644)
        self.before = m.current(self.root);self.manifest = m.sha(self.before[3])
        for name, digest in ((m.SHELL, m.NEW_SHELL), (m.UNIT, m.NEW_UNIT)):
            p = self.bundle/m.io.BACKEND/name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(payload(digest))
    def run_install(self, apply=False): return m.install(self.root, self.bundle, 'B1', self.manifest, apply)
    def files(self):
        return {str(p.relative_to(self.root)): (os.readlink(p) if p.is_symlink() else p.read_bytes())
                for p in self.root.rglob('*') if p.is_file() or p.is_symlink()}
    def test_preview_then_install_and_exact_rollback(self):
        before = self.files();self.assertEqual(self.run_install()['phase'], 'would-install')
        self.assertEqual(self.files(), before)
        result = self.run_install(True);backup = Path(result['backup'])
        now = m.current(self.root)
        self.assertEqual([m.sha(d) for d in now[:3]], [m.NEW_SHELL, m.NEW_UNIT, m.NEW_UNIT])
        sums = now[3].decode()
        self.assertIn(m.NEW_SHELL + '  ./' + m.SHELL, sums);self.assertIn(m.NEW_UNIT + '  ./' + m.UNIT, sums)
        m.io.verify_generation(self.root, now[3])
        self.assertTrue((backup/'COMMITTED').exists());self.assertFalse((backup/'INCOMPLETE').exists())
        self.assertEqual(os.readlink(self.root/m.WANTS), '../' + m.UNIT)
        m.rollback(self.root, backup, 'B1', True)
        self.assertEqual(m.current(self.root), self.before)
    def test_foreign_files_payload_manifest_link_or_boot_refused_before_writes(self):
        cases = {'shell': self.root/m.io.BACKEND/m.SHELL, 'unit': self.root/m.SYSTEMD/m.UNIT,
                 'payload': self.bundle/m.io.BACKEND/m.UNIT, 'manifest': self.root/m.MANIFEST,
                 'boot': self.root/'proc/sys/kernel/random/boot_id'}
        for key, path in cases.items():
            with self.subTest(key=key):
                old = path.read_bytes();path.write_bytes(b'foreign');before = self.files()
                with self.assertRaises(RuntimeError): self.run_install(True)
                self.assertEqual(self.files(), before);path.write_bytes(old)
        link = self.root/m.WANTS;link.unlink();before = self.files()
        with self.assertRaises(RuntimeError): self.run_install(True)
        self.assertEqual(self.files(), before)
    def test_partial_write_is_latched_and_rollback_restores_everything(self):
        original = m.io.atomic;calls = []
        def fail_third(*args):
            calls.append(args[0])
            if len(calls) == 3: raise OSError('injected third-write failure')
            return original(*args)
        with patch.object(m.io, 'atomic', fail_third), self.assertRaises(OSError): self.run_install(True)
        backup = next((self.root/m.io.STATE).glob(m.PREFIX + '*'))
        self.assertTrue((backup/'INCOMPLETE').exists())
        with self.assertRaisesRegex(RuntimeError, 'incomplete'): self.run_install(True)
        m.rollback(self.root, backup, 'B1', True)
        self.assertEqual(m.current(self.root), self.before)
        self.assertFalse((backup/'INCOMPLETE').exists())


class Payload(unittest.TestCase):
    def test_payloads_are_this_trees_shell_and_unit(self):
        shell = (HERE.parent/'mips/mips-shell.py').read_bytes()
        unit = (HERE/'h713-mips-elog-level.service').read_bytes()
        self.assertEqual((m.sha(shell), m.sha(unit)), (m.NEW_SHELL, m.NEW_UNIT))
        self.assertIn(b'def confirm_elog_level', shell)
        self.assertIn(b'Type=exec', unit);self.assertNotIn(b'Type=oneshot', unit)


if __name__ == '__main__': unittest.main()
