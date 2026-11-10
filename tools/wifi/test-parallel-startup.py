#!/usr/bin/env python3
"""Exercise actual payload ordering and every partial installation boundary."""
import importlib.util
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('builder', Path(__file__).with_name('build-parallel-startup.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
m = b.m


class Parallel(unittest.TestCase):
    def test_owner_and_clients_preserve_dependencies_and_shutdown(self):
        data = b.payloads()
        self.assertFalse(any(line.strip().startswith(b'aic8800_') for line in data[0].splitlines()))
        for module in m.MODULES:
            self.assertIn(('blacklist '+module+'\n').encode(), data[3])
        owner = data[4].decode()
        self.assertEqual([line for line in owner.splitlines() if line.startswith('ExecStart=')],
                         ['ExecStart=/usr/sbin/modprobe '+n for n in m.MODULES]+['ExecStart=/usr/bin/test -d /sys/class/net/wlan0'])
        self.assertNotIn('ExecStop=', owner)
        self.assertNotIn('DefaultDependencies=no', owner)
        for client in data[1:3]:
            self.assertIn(b'After=systemd-modules-load.service h713-aic8800-modules.service\n', client)
            self.assertIn(b'Requires=h713-aic8800-modules.service\n', client)
        self.assertIn(b'TimeoutStopSec=10s', data[2])
        self.assertIn(b'Restart=on-failure', data[1])
        # No path back from HDMI to the new radio owner was introduced.
        for name in ('h713-hdmi-prepare.service', 'h713-hdmi-capture-startup.service'):
            self.assertNotIn(m.OWNER, (b.ROOT/'tools/hdmi'/name).read_text())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base/'root'
        self.package = base/'package'
        self.before = b.payloads()[:3]
        self.before[0] = b'\n'.join(x.encode() for x in m.MODULES)+b'\n'
        for i in (1, 2):
            self.before[i] = self.before[i].replace(b'After=systemd-modules-load.service h713-aic8800-modules.service', b'After=systemd-modules-load.service').replace(b'Requires=h713-aic8800-modules.service\n', b'')
        archive = base/'before.tar'
        import io
        with tarfile.open(archive, 'w') as t:
            for n, data in zip(m.TARGETS, self.before):
                info = tarfile.TarInfo(n)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        self.manifest = b.build(archive, self.package)
        for n in m.TARGETS:
            (self.root/n).parent.mkdir(parents=True, exist_ok=True)
        for n, data in zip(m.TARGETS, self.before):
            (self.root/n).write_bytes(data)
            (self.root/n).chmod(0o644)
        (self.root/m.io.STATE).mkdir(parents=True)
        metadata = m.io.metadata
        patcher = patch.object(m.io, 'metadata', lambda p: dict(metadata(p), uid=0, gid=0))
        patcher.start()
        self.addCleanup(patcher.stop)
        original = m.entry
        def entry(root, name):
            p = m.path(root, name)
            return dict(symlink=os.readlink(p)) if p.is_symlink() else original(root, name)
        for name, value in (('entry', entry), ('identity', lambda *args: None)):
            patcher = patch.object(m, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def current(self):
        return [m.entry(self.root, n) for n in m.TARGETS]

    def test_preview_install_and_explicit_rollback(self):
        before = self.current()
        self.assertFalse(m.install(self.root, self.package, 'boot', self.manifest)['applied'])
        self.assertEqual(self.current(), before)
        receipt = m.install(self.root, self.package, 'boot', self.manifest, True)
        self.assertEqual(self.current(), json.loads((self.package/'manifest.json').read_text())['after'])
        m.restore(self.root, Path(receipt['backup']), 'boot', self.manifest)
        self.assertEqual(self.current(), before)

    def test_failure_after_each_write_restores_all_originals(self):
        before = self.current()
        for boundary in range(1, 7):
            count = 0
            original = m.put
            def failing(*args):
                nonlocal count
                original(*args)
                count += 1
                if count == boundary:
                    raise OSError('injected post-write failure')
            with patch.object(m, 'put', failing), self.assertRaisesRegex(OSError, 'injected'):
                m.install(self.root, self.package, 'boot', self.manifest, True)
            self.assertEqual(self.current(), before)
            self.assertFalse(list((self.root/m.io.STATE).glob('*/INCOMPLETE')))

    def test_foreign_baseline_or_payload_refused(self):
        (self.root/m.TARGETS[0]).write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'baseline'):
            m.install(self.root, self.package, 'boot', self.manifest, True)
        (self.root/m.TARGETS[0]).write_bytes(self.before[0])
        (self.package/m.TARGETS[3]).write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'payload'):
            m.install(self.root, self.package, 'boot', self.manifest, True)


if __name__ == '__main__':
    unittest.main()
