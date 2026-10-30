#!/usr/bin/env python3
"""Offline fake-root guard synchronization, failure recovery and scope checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import fcntl
import os
import subprocess
import sys
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE/file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


u = load('guard_sync', 'sync-shutdown-guard.py')
b = load('guard_builder', 'build-guard-sync.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sums(directory):
    return ''.join(sha(p.read_bytes())+'  '+str(p.relative_to(directory))+'\n'
                   for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS').encode()


def tree(directory):
    return {str(p.relative_to(directory)): ('link', str(p.readlink())) if p.is_symlink() else
            (p.stat().st_mode & 0o7777, p.stat().st_uid, p.stat().st_gid, p.read_bytes() if p.is_file() else None)
            for p in sorted(directory.rglob('*'))}


class Sync(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.root, self.bundle = self.work/'target', self.work/'bundle'
        self.backend = self.root/u.BACKEND
        self.state = self.root/u.STATE
        self.hook = self.root/u.TARGETS[1]
        for p in (self.backend, self.state, self.hook.parent, self.bundle, self.root/'proc/device-tree'):
            p.mkdir(parents=True, exist_ok=True)
        (self.root/'proc/device-tree/model').write_text('HY200 QZ713DF_A1 (Allwinner H713)\0')
        audit = json.loads((ROOT/'docs/production-audit/2026-10-28/board-inventory.json').read_text())
        self.old = audit['files']['/usr/lib/h713-hdmi/h713-hdmi-hold-guard']['text'].encode()
        self.new = (HERE/u.GUARD).read_bytes()
        self.assertEqual(sha(self.old), u.OLD)
        self.assertEqual(sha(self.new), u.NEW)
        for p in (self.backend/u.GUARD, self.hook):
            p.write_bytes(self.old)
            p.chmod(0o755)
        for relative in ('h713-hdmi-receiver.ko', 'h713-hdmi-audio.ko', 'h713-hdmi.cmd',
                         'h713-hdmi.scr', 'h713-hdmi-session.py', 'firmware/h713/dsp.bin'):
            p = self.backend/relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('unchanged fixture: '+relative).encode())
        (self.hook.parent/'h713-off').write_text('unchanged lamp hook')
        old_sums = sums(self.backend)
        (self.backend/'SHA256SUMS').write_bytes(old_sums)
        (self.backend/'SHA256SUMS').chmod(0o644)
        self.before = [p.read_bytes() for p in [self.root/t for t in u.TARGETS]]
        (self.bundle/u.GUARD).write_bytes(self.new)
        shutil.copyfile(HERE/'sync-shutdown-guard.py', self.bundle/'sync-shutdown-guard.py')
        (self.bundle/'manifest.json').write_text(json.dumps({
            'schema': 'h713-shutdown-guard-sync-v1', 'before_guard': u.OLD, 'after_guard': u.NEW,
            'before_manifest': sha(old_sums), 'after_manifest': sha(old_sums.replace(u.OLD.encode(), u.NEW.encode()))}))
        (self.bundle/'SHA256SUMS').write_bytes(sums(self.bundle))

    def install(self, dry_run=False):
        return u.install(self.root, self.bundle, dry_run=dry_run)

    def assert_refused(self):
        before = tree(self.root)
        with self.assertRaises((RuntimeError, OSError, ValueError)):
            self.install()
        self.assertEqual(tree(self.root), before)

    def test_preview_is_read_only_and_scope_exact(self):
        before = tree(self.root)
        result = self.install(dry_run=True)
        self.assertEqual(result['phase'], 'would-install')
        self.assertEqual(result['targets'], list(u.TARGETS))
        self.assertEqual(tree(self.root), before)

    def test_install_changes_only_scope_preserves_modes_and_backup(self):
        before = tree(self.root)
        result = self.install()
        self.assertEqual(result['phase'], 'installed')
        backup = Path(result['backup'])
        for i, relative in enumerate(u.TARGETS):
            self.assertEqual((backup/str(i)).read_bytes(), self.before[i])
            self.assertEqual((self.root/relative).stat().st_mode & 0o777, (0o755,0o755,0o644)[i])
        after = tree(self.root)
        for name, item in before.items():
            if name not in u.TARGETS:
                self.assertEqual(after[name], item, name)
        self.assertEqual(self.hook.read_bytes(), self.new)
        self.assertTrue((backup/'COMMITTED').exists())
        self.assertFalse((backup/'INCOMPLETE').exists())
        u.verify_generation(self.root, (self.backend/'SHA256SUMS').read_bytes())
        self.assertEqual((self.backend/'SHA256SUMS').read_bytes(), self.before[2].replace(u.OLD.encode(), u.NEW.encode()))

    def test_repeat_install_is_noop(self):
        self.install()
        before = tree(self.root)
        self.assertEqual(self.install()['phase'], 'already-current')
        self.assertEqual(tree(self.root), before)

    def test_bad_inputs_refused_without_target_writes(self):
        scenarios = ('other-file', 'candidate', 'hook', 'model', 'permissions', 'symlink', 'manifest')
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                if scenario == 'other-file':
                    p=self.backend/'h713-hdmi-receiver.ko';old=p.read_bytes();p.write_bytes(b'foreign')
                elif scenario == 'candidate':
                    p=self.bundle/u.GUARD;old=p.read_bytes();p.write_bytes(b'corrupt candidate')
                elif scenario == 'hook':
                    p=self.hook;old=p.read_bytes();p.write_bytes(b'foreign hook')
                elif scenario == 'model':
                    p=self.root/'proc/device-tree/model';old=p.read_bytes();p.write_bytes(b'HY200 QZ713_V2')
                elif scenario == 'permissions':
                    p=self.hook;p.chmod(0o644)
                elif scenario == 'symlink':
                    p=self.hook;p.unlink();p.symlink_to(self.backend/u.GUARD)
                else:
                    p=self.backend/'SHA256SUMS';old=p.read_bytes();p.write_bytes(old+b'corrupt\n')
                self.assert_refused()
                if scenario == 'permissions':p.chmod(0o755)
                elif scenario == 'symlink':p.unlink();p.write_bytes(self.old);p.chmod(0o755)
                else:p.write_bytes(old)

    def test_incomplete_update_recoverable_at_each_cut(self):
        for cut in (1,2,3):
            with self.subTest(cut=cut):
                real = u.atomic
                count = 0
                def interrupted(*args):
                    nonlocal count
                    real(*args)
                    count += 1
                    if count == cut:raise OSError('simulated power loss')
                with mock.patch.object(u, 'atomic', interrupted):
                    with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                        self.install()
                backup, = [p for p in self.state.iterdir() if p.is_dir()]
                self.assertTrue((backup/'INCOMPLETE').exists())
                self.assert_refused()
                before = tree(self.root)
                self.assertEqual(u.rollback(self.root, backup)['phase'], 'would-rollback')
                self.assertEqual(tree(self.root), before)
                u.rollback(self.root, backup, dry_run=False)
                for i, relative in enumerate(u.TARGETS):
                    self.assertEqual((self.root/relative).read_bytes(), self.before[i])
                self.assertFalse((backup/'INCOMPLETE').exists())
                shutil.rmtree(backup)

    def test_committed_rollback_and_idempotence(self):
        backup = Path(self.install()['backup'])
        result = u.rollback(self.root, backup, dry_run=False)
        self.assertEqual(result['phase'], 'rolled-back')
        for i, relative in enumerate(u.TARGETS):self.assertEqual((self.root/relative).read_bytes(), self.before[i])
        before = tree(self.root)
        u.rollback(self.root, backup, dry_run=False)
        self.assertEqual(tree(self.root), before)

    def test_rollback_refuses_corrupt_backup_foreign_target_or_other_file(self):
        backup = Path(self.install()['backup'])
        for p in (backup/'0', self.hook, self.backend/'h713-hdmi-audio.ko'):
            with self.subTest(path=p):
                original=p.read_bytes();p.write_bytes(b'foreign')
                before=tree(self.root)
                with self.assertRaises(RuntimeError):u.rollback(self.root, backup, dry_run=False)
                self.assertEqual(tree(self.root),before)
                p.write_bytes(original)

    def test_paths_and_manifest_table_fail_closed(self):
        with self.assertRaises(RuntimeError):u.table(b'0'*64+b'  ../escape\n')
        with self.assertRaises(RuntimeError):u.table(b'0'*64+b'  a\n'+b'1'*64+b'  a\n')
        with self.assertRaises(RuntimeError):u.rollback(self.root,self.work/'guard-sync-foreign',dry_run=False)
        victim=self.root/'usr/lib';moved=self.root/'usr/lib-original';victim.rename(moved);victim.symlink_to(moved)
        self.assert_refused()

    def test_mutation_during_write_is_refused(self):
        real=u.atomic
        def changed(p,data,attrs,expected):
            if p==self.hook:p.write_bytes(b'concurrent edit')
            return real(p,data,attrs,expected)
        with mock.patch.object(u,'atomic',changed):
            with self.assertRaisesRegex(RuntimeError,'target changed'):
                self.install()
        self.assertEqual(self.hook.read_bytes(),b'concurrent edit')

    def test_builder_pins_audit_and_candidate_without_mutating_sources(self):
        out=self.work/'real-package'
        result=b.build(out)
        self.assertEqual(u.package(out),result)
        self.assertEqual(result['before_manifest'],'5c57391a0b4e7acde446bf4e2b52319aeca8314693f183095abc08ae960a6631')
        with self.assertRaises(FileExistsError):b.build(out)
        with mock.patch.object(b,'NEW','0'*64):
            with self.assertRaisesRegex(RuntimeError,'candidate guard differs'):b.build(self.work/'wrong-guard')

    def test_directory_lock_refuses_overlapping_update(self):
        fd=os.open(self.state,os.O_RDONLY|os.O_DIRECTORY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assert_refused()
        finally:os.close(fd)

    def test_cli_defaults_to_read_only_preview(self):
        before=tree(self.root)
        r=subprocess.run([sys.executable,str(HERE/'sync-shutdown-guard.py'),
                          '--root',str(self.root),'--bundle',str(self.bundle)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue(json.loads(r.stdout)['dry_run'])
        self.assertEqual(tree(self.root),before)


if __name__ == '__main__':
    unittest.main()
