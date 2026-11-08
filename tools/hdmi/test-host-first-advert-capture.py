#!/usr/bin/env python3
"""The host capture turns debug on only while recording and always restores it."""
import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('host-first-advert-capture.sh')


class Capture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.sys = self.root / 'sys'
        for p, v in (('module/nvidia_modeset/parameters/debug', '0'),
                     ('module/drm/parameters/debug', '0x0'),
                     ('class/drm/card1-HDMI-A-1/status', 'disconnected'),
                     ('class/drm/card1-DP-2/status', 'connected')):
            (self.sys / p).parent.mkdir(parents=True, exist_ok=True)
            (self.sys / p).write_text(v + '\n')
        bin_ = self.root / 'bin'
        bin_.mkdir()
        # Fake recorders that note the debug state they started under and stay alive.
        for name in ('journalctl', 'udevadm'):
            (bin_ / name).write_text('#!/bin/sh\necho "%s started nvkms=$(cat %s)"\nexec sleep 60\n'
                                     % (name, self.sys / 'module/nvidia_modeset/parameters/debug'))
            (bin_ / name).chmod(0o755)
        self.out = self.root / 'out'
        self.env = dict(os.environ, SYS=str(self.sys), ALLOW_NONROOT='1', MAX_SECONDS='20',
                        PATH=f'{bin_}:{os.environ["PATH"]}')

    def debug(self):
        return ((self.sys / 'module/nvidia_modeset/parameters/debug').read_text().strip(),
                (self.sys / 'module/drm/parameters/debug').read_text().strip())

    def start(self, **env):
        p = subprocess.Popen(['bash', str(SCRIPT), str(self.out)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             env=dict(self.env, **env), start_new_session=True)
        for _ in range(100):
            if self.debug() == ('1', '0x6'):
                return p
            time.sleep(0.05)
        p.kill()
        self.fail('debug never switched on: ' + p.communicate()[0])

    def test_mark_quit_restores_and_records(self):
        p = self.start()
        (self.sys / 'class/drm/card1-HDMI-A-1/status').write_text('connected\n')
        time.sleep(0.4)
        out, _ = p.communicate('\nboard on\nq\n', timeout=10)
        self.assertEqual(p.returncode, 0, out)
        self.assertEqual(self.debug(), ('0', '0x0'))
        events = (self.out / 'events.log').read_text()
        for word in ('DEBUG ON nvidia_modeset.debug=1 drm.debug=0x6', 'MARK\n', 'MARK board on',
                     'STOP (q)', 'RESTORED nvidia_modeset.debug=0 drm.debug=0x0'):
            self.assertIn(word, events)
        conn = (self.out / 'connector.log').read_text().splitlines()
        self.assertTrue(conn[0].endswith('card1-HDMI-A-1=disconnected'), conn)
        self.assertTrue(conn[-1].endswith('card1-HDMI-A-1=connected'), conn)
        self.assertNotIn('DP-2', ''.join(conn))
        ctx = (self.out / 'context.txt').read_text()
        self.assertIn('old nvidia_modeset.debug=0 drm.debug=0x0', ctx)
        self.assertIn('journalctl started nvkms=0', (self.out / 'journal.log').read_text())

    def test_terminate_and_timeout_both_restore(self):
        p = self.start()
        os.killpg(p.pid, signal.SIGTERM)
        p.communicate(timeout=10)
        self.assertEqual(self.debug(), ('0', '0x0'))
        self.assertIn('RESTORED', (self.out / 'events.log').read_text())
        (self.out / 'events.log').unlink()
        p = self.start(MAX_SECONDS='1')
        p.communicate(timeout=10)
        self.assertEqual(self.debug(), ('0', '0x0'))
        self.assertIn('STOP (timeout 1 s)', (self.out / 'events.log').read_text())

    def test_previous_nonzero_values_are_restored_not_zeroed(self):
        (self.sys / 'module/drm/parameters/debug').write_text('0x100\n')
        p = self.start()
        p.communicate('q\n', timeout=10)
        self.assertEqual(self.debug(), ('0', '0x100'))

    def test_refuses_without_root(self):
        env = dict(self.env)
        env.pop('ALLOW_NONROOT')
        if os.geteuid() == 0:
            self.skipTest('running as root')
        r = subprocess.run(['bash', str(SCRIPT), str(self.out)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.debug(), ('0', '0x0'))


if __name__ == '__main__':
    unittest.main()
