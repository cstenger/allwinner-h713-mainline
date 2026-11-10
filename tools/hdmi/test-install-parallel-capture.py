#!/usr/bin/env python3
"""Exercise exact unit update/rollback and partial installation; no services."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('installer',HERE/'install-parallel-capture.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def payload(digest):
    """The frozen copy of a pinned installer payload (test-payloads/<sha256>)."""
    data=(HERE/'test-payloads'/digest).read_bytes()
    assert hashlib.sha256(data).hexdigest()==digest,digest
    return data

class Install(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'root';self.bundle=Path(temp.name)/'bundle'
        for relative in (m.BACKEND,m.io.STATE,'usr/lib/systemd/system-shutdown','proc/device-tree',
                         'proc/sys/kernel/random','etc/systemd/system'):
            (self.root/relative).mkdir(parents=True,exist_ok=True)
        (self.root/'proc/device-tree/model').write_text('HY200 QZ713DF_A1 (Allwinner H713)\0')
        (self.root/'proc/sys/kernel/random/boot_id').write_text('B1')
        metadata=m.io.metadata
        def attrs(path):
            result=metadata(path);result.update(uid=0,gid=0);return result
        self.patch=patch.object(m.io,'metadata',attrs);self.patch.start();self.addCleanup(self.patch.stop)
        capture=payload(m.CAPTURE_NEW)
        old=capture.replace(b'Requires=h713-hdmi-prepare.service\n',b'').replace(b' user@1000.service h713-hdmi-prepare.service',b' user@1000.service')
        self.assertEqual(m.sha(old),m.CAPTURE_OLD)
        for name in m.TARGETS[2:4]:
            (self.root/name).write_bytes(old);(self.root/name).chmod(0o644)
        for name in ('mips-shell.py','h713-hdmi-session.py'):
            path=self.root/m.BACKEND/name;path.write_bytes(payload(m.SCRIPTS[name]));path.chmod(0o644)
            self.assertEqual(m.sha(path.read_bytes()),m.SCRIPTS[name])
        (self.root/m.BACKEND/'unchanged.ko').write_bytes(b'unchanged')
        lines=[]
        for path in sorted((self.root/m.BACKEND).iterdir()):
            lines.append(m.sha(path.read_bytes())+'  ./'+path.name+'\n')
        (self.root/m.TARGETS[4]).write_text(''.join(lines));(self.root/m.TARGETS[4]).chmod(0o644)
        self.manifest=m.sha((self.root/m.TARGETS[4]).read_bytes())
        for name in m.TARGETS[:4]:
            path=self.bundle/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(payload(m.PREPARE_NEW if 'prepare' in name else m.CAPTURE_NEW))
        self.before=m.current(self.root)
    def install(self,apply=False):return m.install(self.root,self.bundle,'B1',self.manifest,apply)
    def files(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def test_preview_exact_install_rollback_and_new_units_not_enabled(self):
        before=self.files();self.assertEqual(self.install()['phase'],'would-install');self.assertEqual(self.files(),before)
        result=self.install(True);backup=Path(result['backup'])
        self.assertEqual(list(map(m.sha,m.current(self.root)[:4])),[m.PREPARE_NEW]*2+[m.CAPTURE_NEW]*2)
        self.assertFalse((self.root/'etc/systemd/system/multi-user.target.wants/h713-hdmi-prepare.service').exists())
        installed=self.files();self.assertEqual(m.rollback(self.root,backup,'B1')['phase'],'would-rollback')
        self.assertEqual(self.files(),installed)
        m.rollback(self.root,backup,'B1',True);self.assertEqual(m.current(self.root),self.before)
        m.rollback(self.root,backup,'B1',True);self.assertEqual(m.current(self.root),self.before)
    def test_every_partial_write_boundary_can_rollback_without_touching_scripts(self):
        original=m.atomic
        for stop in range(1,6):
            calls=[]
            def fail(*args):
                calls.append(args[0])
                if len(calls)==stop:raise OSError('injected write failure')
                return original(*args)
            with patch.object(m,'atomic',fail),self.assertRaises(OSError):self.install(True)
            backup=next((self.root/m.io.STATE).glob(m.PREFIX+'*/INCOMPLETE')).parent
            with self.assertRaisesRegex(RuntimeError,'incomplete'):self.install(True)
            m.rollback(self.root,backup,'B1',True);self.assertEqual(m.current(self.root),self.before)
            for name,digest in m.SCRIPTS.items():self.assertEqual(m.sha((self.root/m.BACKEND/name).read_bytes()),digest)
    def test_identity_unit_payload_and_dropin_drift_rejected_before_write(self):
        for name in ('proc/sys/kernel/random/boot_id',m.BACKEND+'/mips-shell.py',m.TARGETS[2],m.TARGETS[4],m.TARGETS[0]):
            path=self.root/name;old=path.read_bytes() if path.exists() else None;path.write_bytes(b'foreign')
            before=self.files()
            with self.subTest(name=name),self.assertRaises(RuntimeError):self.install(True)
            self.assertEqual(self.files(),before)
            if old is None:path.unlink()
            else:path.write_bytes(old)
        path=self.root/'etc/systemd/system/h713-hdmi-capture.service.d';path.mkdir()
        with self.assertRaisesRegex(RuntimeError,'drop-in'):self.install(True)
        path.rmdir()
        path=self.bundle/m.TARGETS[0];path.write_bytes(b'foreign')
        before=self.files()
        with self.assertRaisesRegex(RuntimeError,'payload'):self.install(True)
        self.assertEqual(self.files(),before)
    def test_existing_unit_symlink_or_foreign_rollback_target_refused(self):
        path=self.root/m.TARGETS[0];path.symlink_to(self.root/m.TARGETS[2])
        with self.assertRaises(RuntimeError):self.install(True)
        path.unlink();result=self.install(True);backup=Path(result['backup'])
        (self.root/m.TARGETS[0]).write_bytes(b'foreign')
        before=self.files()
        with self.assertRaisesRegex(RuntimeError,'foreign'):m.rollback(self.root,backup,'B1',True)
        self.assertEqual(self.files(),before)


if __name__=='__main__':unittest.main()
