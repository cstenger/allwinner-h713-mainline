#!/usr/bin/env python3
"""Exercise the stage-1 transaction and partial-write recovery on fake roots."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('installer',HERE/'install-ipc-completion.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Install(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'root';self.bundle=Path(temp.name)/'bundle'
        for name in (m.io.BACKEND,m.io.STATE,'usr/lib/systemd/system-shutdown','proc/device-tree',
                     'proc/sys/kernel/random','etc/systemd/system'):
            (self.root/name).mkdir(parents=True,exist_ok=True)
        (self.root/'proc/device-tree/model').write_text('HY200 QZ713DF_A1 (Allwinner H713)\0')
        (self.root/'proc/sys/kernel/random/boot_id').write_text('B1')
        unit=self.root/'etc/systemd/system/h713-hdmi-capture.service';unit.write_bytes(b'accepted capture unit')
        self.addCleanup(patch.stopall)
        patch.object(m,'UNIT_SHA',m.sha(unit.read_bytes())).start()
        old=(b'original shell',b'original session')
        patch.object(m,'OLD',tuple(map(m.sha,old))).start()
        real_metadata=m.io.metadata
        def attrs(path):
            result=real_metadata(path);result.update(uid=0,gid=0);return result
        patch.object(m.io,'metadata',attrs).start()
        lines=[]
        for name,data in zip(m.NAMES[:2],old):
            path=m.target(self.root,name);path.write_bytes(data);path.chmod(0o644)
            lines.append(m.sha(data)+'  ./'+name+'\n')
        m.target(self.root,'unchanged.ko').write_bytes(b'unchanged module')
        lines.append(m.sha(b'unchanged module')+'  ./unchanged.ko\n')
        m.target(self.root,'SHA256SUMS').write_text(''.join(lines));m.target(self.root,'SHA256SUMS').chmod(0o644)
        self.before=[m.target(self.root,name).read_bytes() for name in m.NAMES]
        self.manifest=m.sha(self.before[2])
        for name,source in zip(m.NAMES[:2],(HERE.parent/'mips/mips-shell.py',HERE/'h713-hdmi-session.py')):
            path=self.bundle/m.io.BACKEND/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source.read_bytes())
    def run_install(self,apply=False):return m.install(self.root,self.bundle,'B1',self.manifest,apply)
    def files(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def test_preview_then_install_and_exact_rollback(self):
        before=self.files();self.assertEqual(self.run_install()['phase'],'would-install');self.assertEqual(self.files(),before)
        result=self.run_install(True);backup=Path(result['backup'])
        self.assertEqual(tuple(map(m.sha,m.current(self.root)[:2])),m.NEW)
        self.assertTrue((backup/'COMMITTED').exists());self.assertFalse((backup/'INCOMPLETE').exists())
        preview=self.files();self.assertEqual(m.rollback(self.root,backup,'B1')['phase'],'would-rollback')
        self.assertEqual(self.files(),preview)
        m.rollback(self.root,backup,'B1',True)
        self.assertEqual(m.current(self.root),self.before)
        self.assertEqual(m.target(self.root,'unchanged.ko').read_bytes(),b'unchanged module')
    def test_foreign_file_payload_manifest_unit_or_boot_refused_before_writes(self):
        for key in ('file','payload','manifest','unit','boot','parallel'):
            with self.subTest(key=key):
                if key=='file':path=m.target(self.root,m.NAMES[0])
                elif key=='payload':path=self.bundle/m.io.BACKEND/m.NAMES[0]
                elif key=='manifest':path=m.target(self.root,'SHA256SUMS')
                elif key=='unit':path=self.root/'etc/systemd/system/h713-hdmi-capture.service'
                elif key=='boot':path=self.root/'proc/sys/kernel/random/boot_id'
                else:path=self.root/'etc/systemd/system/h713-hdmi-prepare.service'
                old=path.read_bytes() if path.exists() else None;path.write_bytes(b'foreign')
                before=self.files()
                with self.assertRaises(RuntimeError):self.run_install(True)
                self.assertEqual(self.files(),before)
                if old is None:path.unlink()
                else:path.write_bytes(old)
    def test_partial_write_is_latched_and_rollback_restores_all_three_files(self):
        original=m.io.atomic;calls=[]
        def fail_second(*args):
            calls.append(args[0])
            if len(calls)==2:raise OSError('injected second-write failure')
            return original(*args)
        with patch.object(m.io,'atomic',fail_second),self.assertRaises(OSError):self.run_install(True)
        backup=next((self.root/m.io.STATE).glob(m.PREFIX+'*'))
        self.assertTrue((backup/'INCOMPLETE').exists())
        with self.assertRaisesRegex(RuntimeError,'incomplete'):self.run_install(True)
        m.rollback(self.root,backup,'B1',True)
        self.assertEqual(m.current(self.root),self.before)
        self.assertFalse((backup/'INCOMPLETE').exists())
    def test_symlink_bad_mode_and_unrelated_backend_drift_refused(self):
        path=m.target(self.root,m.NAMES[0]);old=path.read_bytes()
        actual=self.root/'actual';actual.write_bytes(old);path.unlink();path.symlink_to(actual)
        with self.assertRaises(RuntimeError):self.run_install(True)
        path.unlink();path.write_bytes(old);path.chmod(0o755)
        with self.assertRaises(RuntimeError):self.run_install(True)
        path.chmod(0o644);m.target(self.root,'unchanged.ko').write_bytes(b'drift')
        with self.assertRaises(RuntimeError):self.run_install(True)


if __name__=='__main__':unittest.main()
