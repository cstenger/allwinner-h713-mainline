#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('initial_installer', Path(__file__).with_name('install-ddc-isolation.py'))
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
m = wrapper.transaction


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root, self.package = [Path(self.tmp.name) / n for n in ('root', 'package')]
        self.old, self.new = {}, {}
        for files, prefix in ((self.old, b'old'), (self.new, b'new')):
            for name in m.TARGETS[:-1]:
                files[name] = prefix + name.encode()
            files[m.TARGETS[-1]] = ''.join(m.sha(files[name])+'  ./'+Path(name).name+'\n'
                for name in m.TARGETS[:-1]).encode()
        for root, files in ((self.root, self.old), (self.package, self.new)):
            for name, data in files.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                p.chmod(0o644)
        video = self.root / 'usr/lib/h713-hdmi-video/SHA256SUMS'
        video.parent.mkdir(parents=True)
        (video.parent / 'untouched.ko').write_bytes(b'untouched')
        video.write_text(m.sha(b'untouched')+'  ./untouched.ko\n')
        video.chmod(0o644)
        for name, value in {'proc/device-tree/model': 'HY200 QZ713DF_A1 (Allwinner H713)\0',
                            'proc/sys/kernel/random/boot_id': 'boot',
                            'sys/block/mmcblk0/device/cid': '15010038475446345208604bbe691991'}.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value)
        (self.root / m.io.STATE).mkdir(parents=True)
        (self.root / 'usr/lib/systemd/system-shutdown').mkdir(parents=True)
        raw = json.dumps(dict(before={n:m.sha(v) for n,v in self.old.items()},
                              after={n:m.sha(v) for n,v in self.new.items()})).encode()
        (self.package / 'manifest.json').write_bytes(raw)
        self.pin = m.sha(raw)
        p = patch.object(m, 'ATTRS', dict(mode=0o644, uid=os.geteuid(), gid=os.getegid()))
        p.start()
        self.addCleanup(p.stop)

    def install(self, apply=True, rollback=None):
        return m.install(self.root, self.package, 'boot', self.pin, apply, rollback)

    def assert_files(self, expected):
        self.assertEqual({n:(self.root/n).read_bytes() for n in m.TARGETS}, expected)

    def test_preview_install_and_explicit_rollback(self):
        self.assertFalse(self.install(False)['applied'])
        self.assert_files(self.old)
        result = self.install()
        self.assertIn('ddc-isolation-', result['backup'])
        self.assert_files(self.new)
        self.install(rollback=Path(result['backup']))
        self.assert_files(self.old)

    def test_each_post_write_failure_restores_exact_predecessor(self):
        original = m.io.atomic
        for boundary in (1, 2, 3):
            count = 0
            def fail(*args):
                nonlocal count
                original(*args)
                count += 1
                if count == boundary:
                    raise RuntimeError('injected failure')
            with self.subTest(boundary=boundary), patch.object(m.io, 'atomic', fail):
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    self.install()
            self.assert_files(self.old)
            self.assertFalse(list((self.root/m.io.STATE).glob('*/INCOMPLETE')))

    def test_changed_package_or_predecessor_refused(self):
        (self.package/m.TARGETS[0]).write_bytes(b'alien')
        with self.assertRaisesRegex(RuntimeError, 'payload'):
            self.install()
        self.assert_files(self.old)
        (self.root/m.TARGETS[0]).write_bytes(b'alien')
        with self.assertRaisesRegex(RuntimeError, 'generation'):
            self.install()


if __name__ == '__main__':
    unittest.main()
