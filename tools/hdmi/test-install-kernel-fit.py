#!/usr/bin/env python3
"""Exercise the kernel FIT + startup script transaction on fake roots."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kfit', HERE/'install-kernel-fit.py')
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def sha(b): return hashlib.sha256(b).hexdigest()


OLD = {'h713-kernel.fit': b'old fit'*100, 'h713-hdmi.cmd': b'old cmd', 'h713-hdmi.scr': b'old scr'}
NEW = {'h713-kernel.fit': b'new fit'*90, 'h713-hdmi.cmd': b'new cmd', 'h713-hdmi.scr': b'new scr'}


class KernelFit(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)/'root';self.bundle = Path(temp.name)/'bundle'
        for d in (m.STATE, m.FAT, *m.BUNDLES, 'proc/device-tree', 'proc/sys/kernel/random'):
            (self.root/d).mkdir(parents=True, exist_ok=True)
        (self.root/'proc/device-tree/model').write_text(m.MODEL+'\0')
        (self.root/'proc/sys/kernel/random/boot_id').write_text('B1\n')
        for b in m.BUNDLES:
            for n in m.SCRIPT_NAMES: (self.root/b/n).write_bytes(OLD[n])
            (self.root/b/'other.ko').write_bytes(b'unrelated')
            (self.root/b/'SHA256SUMS').write_text(''.join(sha(OLD[n])+'  ./'+n+'\n' for n in m.SCRIPT_NAMES)
                                                  +sha(b'unrelated')+'  ./other.ko\n')
        (self.root/m.FAT/'h713-kernel.fit').write_bytes(OLD['h713-kernel.fit'])
        (self.root/m.FAT/'h713-hdmi.scr').write_bytes(OLD['h713-hdmi.scr'])
        (self.root/m.FAT/'bootlogo.bmp').write_bytes(b'logo')
        self.bundle.mkdir()
        for n, d in NEW.items(): (self.bundle/n).write_bytes(d)
        manifest = dict(schema=m.SCHEMA, files={n: sha(d) for n, d in NEW.items()},
                        baseline={n: sha(d) for n, d in OLD.items()},
                        checks={'module_symvers_equal': True, 'kernel_release_equal': True,
                                'config_diff': ['CONFIG_LEGACY_PTYS', 'CONFIG_LEGACY_PTY_COUNT']})
        (self.bundle/'manifest.json').write_text(json.dumps(manifest))
        self.manifest = manifest

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def run_(self, apply=False, rollback=None, boot='B1'):
        return m.run(self.root, self.bundle, boot, apply, rollback)

    def test_preview_install_and_exact_rollback(self):
        before = self.files()
        r = self.run_();self.assertEqual(r['state'], 'baseline');self.assertEqual(self.files(), before)
        r = self.run_(True);self.assertEqual(r['state'], 'candidate')
        self.assertEqual((self.root/m.FAT/'h713-kernel.fit').read_bytes(), NEW['h713-kernel.fit'])
        self.assertEqual((self.root/m.FAT/'h713-hdmi.scr').read_bytes(), NEW['h713-hdmi.scr'])
        for b in m.BUNDLES:
            sums = m.sums((self.root/b/'SHA256SUMS').read_bytes())
            self.assertEqual(sums['h713-hdmi.cmd'], sha(NEW['h713-hdmi.cmd']))
            self.assertEqual(sums['other.ko'], sha(b'unrelated'))
        self.assertEqual(m.state(self.root, self.manifest), 'candidate')
        with self.assertRaisesRegex(RuntimeError, 'expected baseline'): self.run_(True)
        backup = Path(r['backup'])
        self.assertTrue((backup/'COMMITTED').exists());self.assertFalse((backup/'INCOMPLETE').exists())
        mid = self.files();self.run_(rollback=backup);self.assertEqual(self.files(), mid)
        self.run_(True, rollback=backup)
        after = {k: v for k, v in self.files().items() if not k.startswith(m.STATE)}
        self.assertEqual(after, {k: v for k, v in before.items() if not k.startswith(m.STATE)})

    def test_disagreeing_or_foreign_copies_refused_before_writes(self):
        cases = [(m.BUNDLES[1]+'/h713-hdmi.scr', NEW['h713-hdmi.scr']),   # one copy already new
                 (m.FAT+'/h713-kernel.fit', b'foreign fit'),
                 (m.FAT+'/h713-hdmi.scr', NEW['h713-hdmi.scr']),          # half-installed pair
                 (m.BUNDLES[0]+'/other.ko', b'drift')]
        for rel, data in cases:
            with self.subTest(rel=rel):
                p = self.root/rel;old = p.read_bytes();p.write_bytes(data)
                before = self.files()
                with self.assertRaises(RuntimeError): self.run_(True)
                self.assertEqual(self.files(), before);p.write_bytes(old)

    def test_state_refuses_every_mixed_pair(self):
        for rel in (m.FAT+'/h713-kernel.fit', m.FAT+'/h713-hdmi.scr', m.BUNDLES[0]+'/h713-hdmi.cmd'):
            with self.subTest(rel=rel):
                p = self.root/rel;old = p.read_bytes();p.write_bytes(NEW[p.name])
                if p.parent.name != 'boot':   # keep that bundle's own manifest consistent
                    s = self.root/m.BUNDLES[0]/'SHA256SUMS';olds = s.read_bytes()
                    s.write_bytes(m.new_sums(olds, {p.name: sha(NEW[p.name])}))
                with self.assertRaisesRegex(RuntimeError, 'disagree'): m.state(self.root, self.manifest)
                p.write_bytes(old)
                if p.parent.name != 'boot': s.write_bytes(olds)

    def test_wrong_boot_board_or_bundle_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'boot changed'): self.run_(True, boot='B2')
        (self.bundle/'h713-kernel.fit').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'bundle file mismatch'): self.run_(True)

    def test_unchecked_bundle_refused(self):
        self.manifest['checks']['module_symvers_equal'] = False
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(RuntimeError, 'bundle checks'): self.run_(True)

    def test_failure_between_fat_renames_restores_everything(self):
        before = self.files();real = os.replace;calls = []
        def fail_script(src, dst):
            if str(dst).endswith(m.FAT+'/h713-hdmi.scr') and str(src).endswith(m.SUFFIX):
                calls.append(dst);raise OSError('injected: power lost before script rename')
            return real(src, dst)
        with patch.object(m.os, 'replace', fail_script), self.assertRaisesRegex(OSError, 'injected'):
            self.run_(True)
        self.assertEqual(len(calls), 1)
        after = {k: v for k, v in self.files().items() if not k.startswith(m.STATE)}
        self.assertEqual(after, before)
        backup = next((self.root/m.STATE).glob(m.PREFIX+'*'))
        self.assertTrue((backup/'RESTORED').exists());self.assertFalse((backup/'INCOMPLETE').exists())
        self.assertEqual(self.run_()['state'], 'baseline')

    def test_fit_is_activated_before_script(self):
        real = os.replace;order = []
        def record(src, dst):
            if str(src).endswith(m.SUFFIX): order.append(Path(dst).name)
            return real(src, dst)
        with patch.object(m.os, 'replace', record): self.run_(True)
        fat = [n for n in order if n in ('h713-kernel.fit', 'h713-hdmi.scr')]
        self.assertEqual(fat[-2:], ['h713-kernel.fit', 'h713-hdmi.scr'])

    def test_rollback_needs_committed_backup_in_state(self):
        r = self.run_(True);backup = Path(r['backup'])
        (backup/'COMMITTED').unlink()
        with self.assertRaisesRegex(RuntimeError, 'not a committed'): self.run_(True, rollback=backup)
        (backup/'COMMITTED').write_bytes(b'verified\n')
        with self.assertRaisesRegex(RuntimeError, 'invalid backup'): self.run_(True, rollback=self.root/'tmp')

    def test_leftover_staged_file_refused(self):
        (self.root/m.FAT/('h713-kernel.fit'+m.SUFFIX)).write_bytes(b'x')
        with self.assertRaisesRegex(RuntimeError, 'staged file left'): self.run_(True)


if __name__ == '__main__':
    unittest.main()
