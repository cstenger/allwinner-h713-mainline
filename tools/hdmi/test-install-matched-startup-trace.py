#!/usr/bin/env python3
"""Exercise arm switching, refusal, and partial-write rollback on fake roots."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('switcher', Path(__file__).with_name('install-matched-startup-trace.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Switch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'root'
        self.package = Path(self.tmp.name) / 'package'
        self.state = self.root / m.io.STATE
        self.state.mkdir(parents=True)
        self.files = {}
        for arm, content in (('baseline', b'base'), ('original', b'old'), ('optimized', b'new')):
            files = {'usr/lib/h713-hdmi/script': content,
                     'usr/lib/h713-hdmi/prepare': None if arm == 'original' else b'prepare',
                     'usr/lib/h713-hdmi-video/module': b'base-ko' if arm == 'baseline' else b'trace-ko'}
            for bundle in ('h713-hdmi', 'h713-hdmi-video'):
                prefix = 'usr/lib/' + bundle + '/'
                files[prefix+'SHA256SUMS'] = ''.join(m.sha(v)+'  '+n[len(prefix):]+'\n' for n, v in files.copy().items() if n.startswith(prefix) and v is not None).encode()
            self.files[arm] = files
            for n, v in files.items():
                if v is not None:
                    p = self.package / arm / n
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(v)
        raw = (json.dumps({a: {n: m.sha(v) for n, v in f.items()} for a, f in self.files.items()})+'\n').encode()
        (self.package / 'pins.json').write_bytes(raw)
        for n, v in self.files['baseline'].items():
            p = self.root / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(v)
        for target, value in (('PINS', m.sha(raw)), ('identity', lambda *a: None), ('read', self.read)):
            context = patch.object(m, target, value)
            context.start()
            self.addCleanup(context.stop)

    @staticmethod
    def read(root, name):
        p = m.io.path(root, name)
        return p.read_bytes() if p.exists() else None

    def switch(self, arm, apply=True):
        return m.switch(self.root, self.package, 'boot', arm, apply)

    def assert_arm(self, arm):
        self.assertEqual({n: self.read(self.root, n) for n in self.files[arm]}, self.files[arm])

    def test_preview_and_both_directions(self):
        self.assertFalse(self.switch('original', False)['applied'])
        self.assert_arm('baseline')
        for arm in ('original', 'optimized', 'original'):
            self.assertTrue(self.switch(arm)['applied'])
            self.assert_arm(arm)
        self.assertFalse(self.switch('original')['applied'])

    def test_partial_write_rolls_back(self):
        atomic = m.io.atomic
        failed = False
        def fail_after_write(*args):
            nonlocal failed
            atomic(*args)
            if not failed:
                failed = True
                raise RuntimeError('injected write failure')
        with patch.object(m.io, 'atomic', fail_after_write):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.switch('original')
        self.assert_arm('baseline')
        self.assertFalse(list(self.state.glob('*/INCOMPLETE')))
        self.assertTrue(list(self.state.glob('*/ROLLED_BACK')))

    def test_alien_file_and_payload_refused(self):
        p = self.root / 'usr/lib/h713-hdmi/script'
        p.write_bytes(b'alien')
        with self.assertRaisesRegex(RuntimeError, 'recognized'):
            self.switch('original')
        p.write_bytes(b'base')
        (self.package / 'original/usr/lib/h713-hdmi/script').write_bytes(b'alien')
        with self.assertRaisesRegex(RuntimeError, 'payload'):
            self.switch('original')
        self.assert_arm('baseline')


if __name__ == '__main__':
    unittest.main()
