#!/usr/bin/env python3
"""Exercise the kernel FIT + startup script transaction on fake roots."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import struct
import zlib
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kfit', HERE/'install-kernel-fit.py')
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def sha(b): return hashlib.sha256(b).hexdigest()


OLD = {'h713-kernel.fit': b'old fit'*100, 'h713-hdmi.cmd': b'old cmd', 'h713-hdmi.scr': b'old scr'}
NEW = {'h713-kernel.fit': b'new fit'*90, 'h713-hdmi.cmd': b'new cmd', 'h713-hdmi.scr': b'new scr'}


class KernelFit(unittest.TestCase):
    def with_cedrus(self):
        p = self.root/m.CEDRUS;p.parent.mkdir(parents=True);p.write_bytes(b'old cedrus')
        (self.bundle/'sunxi-cedrus.ko').write_bytes(b'new cedrus')
        self.manifest['files']['sunxi-cedrus.ko'] = sha(b'new cedrus')
        self.manifest['baseline']['sunxi-cedrus.ko'] = sha(b'old cedrus')
        self.manifest['checks']['cedrus_module_reproduced'] = True
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))

    def test_cedrus_is_paired_and_rolls_back(self):
        self.with_cedrus();before = self.files()
        self.assertEqual(self.run_()['state'], 'baseline');self.assertEqual(self.files(), before)
        r = self.run_(True)
        self.assertEqual((self.root/m.CEDRUS).read_bytes(), b'new cedrus')
        self.run_(True, rollback=Path(r['backup']))
        self.assertEqual((self.root/m.CEDRUS).read_bytes(), b'old cedrus')

    def test_cedrus_failure_restores_fit_script_and_module(self):
        self.with_cedrus();before = self.files();real = os.replace
        def fail(src, dst):
            if str(dst).endswith(m.FAT+'/h713-hdmi.scr') and str(src).endswith(m.SUFFIX):
                raise OSError('injected script activation failure')
            return real(src, dst)
        with patch.object(m.os, 'replace', fail), self.assertRaises(OSError): self.run_(True)
        self.assertEqual({k:v for k,v in self.files().items() if not k.startswith(m.STATE)}, before)

    def test_cedrus_drift_or_unchecked_baseline_refused(self):
        self.with_cedrus();(self.root/m.CEDRUS).write_bytes(b'foreign')
        before = self.files()
        with self.assertRaisesRegex(RuntimeError, 'copies disagree'): self.run_(True)
        self.assertEqual(self.files(), before)
        (self.root/m.CEDRUS).write_bytes(b'old cedrus')
        self.manifest['checks']['cedrus_module_reproduced'] = False
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(RuntimeError, 'Cedrus baseline checks'): self.run_(True)

    def with_cpu_comm(self):
        p = self.root/m.CPU_COMM;p.parent.mkdir(parents=True);p.write_bytes(b'old cpu_comm')
        (self.bundle/'hy310-cpu-comm.ko').write_bytes(b'new cpu_comm')
        self.manifest['files']['hy310-cpu-comm.ko'] = sha(b'new cpu_comm')
        self.manifest['baseline']['hy310-cpu-comm.ko'] = sha(b'old cpu_comm')
        self.manifest['checks']['cpu_comm_module_reproduced'] = True
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))

    def test_cpu_comm_is_paired_and_rolls_back(self):
        self.with_cpu_comm();before = self.files()
        self.assertEqual(self.run_()['state'], 'baseline');self.assertEqual(self.files(), before)
        r = self.run_(True)
        self.assertEqual((self.root/m.CPU_COMM).read_bytes(), b'new cpu_comm')
        self.run_(True, rollback=Path(r['backup']))
        self.assertEqual((self.root/m.CPU_COMM).read_bytes(), b'old cpu_comm')

    def test_cpu_comm_failure_restores_fit_script_and_module(self):
        self.with_cpu_comm();before = self.files();real = os.replace
        def fail(src, dst):
            if str(dst).endswith(m.FAT+'/h713-hdmi.scr') and str(src).endswith(m.SUFFIX):
                raise OSError('injected script activation failure')
            return real(src, dst)
        with patch.object(m.os, 'replace', fail), self.assertRaises(OSError): self.run_(True)
        self.assertEqual({k:v for k,v in self.files().items() if not k.startswith(m.STATE)}, before)

    def test_cpu_comm_drift_or_unchecked_baseline_refused(self):
        self.with_cpu_comm();(self.root/m.CPU_COMM).write_bytes(b'foreign')
        before = self.files()
        with self.assertRaisesRegex(RuntimeError, 'copies disagree'): self.run_(True)
        self.assertEqual(self.files(), before)
        (self.root/m.CPU_COMM).write_bytes(b'old cpu_comm')
        self.manifest['checks']['cpu_comm_module_reproduced'] = False
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(RuntimeError, 'CPU_COMM baseline checks'): self.run_(True)

    def module_only(self):
        """CPU_COMM-only bundle pinned to the installed (OLD) FIT and script."""
        p = self.root/m.CPU_COMM;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(b'old cpu_comm')
        for n in NEW: (self.bundle/n).unlink(missing_ok=True)
        (self.bundle/'hy310-cpu-comm.ko').write_bytes(b'new cpu_comm')
        self.manifest.update(scope='modules', files={'hy310-cpu-comm.ko': sha(b'new cpu_comm')},
                             baseline={**{n: sha(d) for n, d in OLD.items()},
                                       'hy310-cpu-comm.ko': sha(b'old cpu_comm')},
                             checks={'module_symvers_equal': True, 'kernel_release_equal': True,
                                     'config_diff': [], 'dtb_change': 'none', 'fit_unchanged': True,
                                     'script_unchanged': True, 'cpu_comm_module_reproduced': True})
        self.write_manifest()

    def test_module_only_writes_only_the_module_and_rolls_back(self):
        self.module_only();before = self.files();real = os.replace;renamed = []
        r = self.run_();self.assertEqual(r['state'], 'baseline');self.assertEqual(list(r['would']), [m.CPU_COMM])
        def record(src, dst):
            renamed.append(str(Path(dst).relative_to(self.root)));return real(src, dst)
        with patch.object(m.os, 'replace', record): r = self.run_(True)
        self.assertEqual(renamed, [m.CPU_COMM]);self.assertEqual(r['state'], 'candidate')
        changed = {k for k, v in self.files().items() if not k.startswith(m.STATE) and before.get(k) != v}
        self.assertEqual(changed, {m.CPU_COMM})
        self.assertEqual((self.root/m.CPU_COMM).read_bytes(), b'new cpu_comm')
        with self.assertRaisesRegex(RuntimeError, 'expected baseline'): self.run_(True)
        self.run_(True, rollback=Path(r['backup']))
        self.assertEqual({k: v for k, v in self.files().items() if not k.startswith(m.STATE)}, before)

    def test_module_only_refuses_unpinned_kernel_or_script(self):
        self.module_only()
        cases = [(m.FAT+'/h713-kernel.fit', NEW['h713-kernel.fit']), (m.FAT+'/h713-hdmi.scr', b'other'),
                 (m.BUNDLES[1]+'/h713-hdmi.cmd', b'other')]
        for rel, data in cases:
            with self.subTest(rel=rel):
                p = self.root/rel;old = p.read_bytes();p.write_bytes(data)
                if p.parent.name != 'boot':
                    s = self.root/m.BUNDLES[1]/'SHA256SUMS';olds = s.read_bytes()
                    s.write_bytes(m.new_sums(olds, {p.name: sha(data)}))
                before = self.files()
                with self.assertRaisesRegex(RuntimeError, 'not the pinned'): self.run_(True)
                self.assertEqual(self.files(), before);p.write_bytes(old)
                if p.parent.name != 'boot': s.write_bytes(olds)
        (self.root/m.CPU_COMM).write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'module copies disagree'): self.run_(True)

    def test_module_only_manifest_must_be_narrow(self):
        for edit, message in (
                (lambda: self.manifest['files'].update({'h713-kernel.fit': sha(OLD['h713-kernel.fit'])}),
                 'only modules'),
                (lambda: self.manifest['checks'].update(fit_unchanged=False), 'more than modules'),
                (lambda: self.manifest['checks'].update(config_diff=['CONFIG_X']), 'more than modules'),
                (lambda: self.manifest['checks'].update(dtb_change='pio-spi-54-60-only'), 'more than modules'),
                (lambda: self.manifest['baseline'].pop('h713-hdmi.scr'), 'pins missing'),
                (lambda: self.manifest['baseline'].update({'hy310-cpu-comm.ko': sha(b'new cpu_comm')}),
                 'equals baseline'),
                (lambda: self.manifest.update(scope='everything'), 'unknown bundle scope'),
                (lambda: self.manifest['checks'].update(cpu_comm_module_reproduced=False), 'CPU_COMM baseline')):
            with self.subTest(message=message):
                self.module_only();edit()
                if 'h713-kernel.fit' in self.manifest['files']:
                    (self.bundle/'h713-kernel.fit').write_bytes(OLD['h713-kernel.fit'])
                self.write_manifest()
                with self.assertRaisesRegex(RuntimeError, message): self.run_(True)

    def test_module_only_failure_restores_module(self):
        self.module_only();before = self.files()
        def fail(src, dst): raise OSError('injected module rename failure')
        with patch.object(m.os, 'replace', fail), self.assertRaises(OSError): self.run_(True)
        self.assertEqual({k: v for k, v in self.files().items() if not k.startswith(m.STATE)}, before)
        backup = next((self.root/m.STATE).glob(m.PREFIX+'*'))
        self.assertTrue((backup/'RESTORED').exists())

    def slub_bundle(self):
        cmd = m.SLUB_PREFIX+OLD['h713-hdmi.cmd']
        payload = struct.pack('>2I', len(cmd), 0)+cmd
        header = struct.pack('>7I4B32s', 0x27051956, 0, 0, len(payload),
                             0, 0, zlib.crc32(payload), 5, 22, 6, 0, b'test')
        header = header[:4]+struct.pack('>I', zlib.crc32(header))+header[8:]
        files = {'h713-kernel.fit': OLD['h713-kernel.fit'],
                 'h713-hdmi.cmd': cmd, 'h713-hdmi.scr': header+payload}
        for name, data in files.items(): (self.bundle/name).write_bytes(data)
        self.manifest['files'] = {n: sha(v) for n,v in files.items()}
        self.manifest['checks']['config_diff'] = []
        self.manifest['diagnostic_bootargs'] = ['slub_debug=FZPU', 'oops=panic']
        self.write_manifest()

    def write_manifest(self):
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))

    def test_slub_script_only_install_and_exact_rollback(self):
        self.slub_bundle();before=self.files()
        r=self.run_(True)
        self.assertEqual((self.root/m.FAT/'h713-kernel.fit').read_bytes(), OLD['h713-kernel.fit'])
        self.assertTrue((self.root/m.BUNDLES[0]/'h713-hdmi.cmd').read_bytes().startswith(m.SLUB_PREFIX))
        self.run_(True, rollback=Path(r['backup']))
        self.assertEqual({k:v for k,v in self.files().items() if not k.startswith(m.STATE)}, before)

    def test_slub_diagnostic_rejects_kernel_module_and_config_changes(self):
        self.slub_bundle()
        for key in ('h713-kernel.fit','hy310-cpu-comm.ko','sunxi-cedrus.ko'):
            with self.subTest(key=key):
                (self.bundle/key).write_bytes(b'changed')
                self.manifest['files'][key]=sha(b'changed');self.write_manifest()
                with self.assertRaisesRegex(RuntimeError,'diagnostic changes kernel/module'): self.run_(True)
                self.slub_bundle()
                self.manifest['files'].pop(key,None) if key!='h713-kernel.fit' else None
                self.write_manifest()
        self.slub_bundle();self.manifest['checks']['config_diff']=['CONFIG_X'];self.write_manifest()
        with self.assertRaisesRegex(RuntimeError,'diagnostic changes configuration'): self.run_(True)

    def test_slub_diagnostic_rejects_command_or_script_drift(self):
        self.slub_bundle()
        cmd=(self.bundle/'h713-hdmi.cmd').read_bytes()+b'unsafe'
        (self.bundle/'h713-hdmi.cmd').write_bytes(cmd)
        self.manifest['files']['h713-hdmi.cmd']=sha(cmd);self.write_manifest()
        with self.assertRaisesRegex(RuntimeError,'only prepend'): self.run_(True)
        self.slub_bundle();scr=(self.bundle/'h713-hdmi.scr').read_bytes()+b'junk'
        (self.bundle/'h713-hdmi.scr').write_bytes(scr)
        self.manifest['files']['h713-hdmi.scr']=sha(scr);self.write_manifest()
        with self.assertRaisesRegex(RuntimeError,'script header'): self.run_(True)
        self.slub_bundle();self.manifest['diagnostic_bootargs']=['other'];self.write_manifest()
        with self.assertRaisesRegex(RuntimeError,'unsupported diagnostic'): self.run_(True)

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
