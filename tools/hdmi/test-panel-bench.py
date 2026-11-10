#!/usr/bin/env python3
"""Offline receiver bench state/CLI controls; never load modules or use hardware."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

base = load('session_tests', 'test-hdmi-session.py')
bench = load('bench', 'bench-receiver-only.py')
m = base.m


class Board(base.FakeBoard):
    def __init__(self):
        super().__init__()
        self.files[m.HANDOFF] = struct.pack('>III', 0x48444d49, 0, 123)
        self.active = False
        self.missing_top_restore = False
        self.truncate_log = False
        self.invalid_clock = False

    def run(self, argv, check=True, timeout=15):
        if argv[:2] == ['systemctl', 'show']:
            return SimpleNamespace(stdout='active' if self.active else 'inactive', returncode=0)
        if argv[0] == 'insmod' and argv[1].endswith('h713-tvfe-bench.ko'):
            self.modules.add('h713_tvfe_bench')
            with_top = 'audio_top=1' in argv
            self.param('h713_tvfe_bench', 'audio_top', 'Y' if with_top else 'N')
            self.param(m.OWNER, 'clients', 1)
            self.log += 'production TVFE hold applied\n'
            if with_top:
                self.log += 'audio-top (top_ctl=700 top_cfg=1)\n'
            return SimpleNamespace(stdout='', returncode=0)
        if argv == ['rmmod', 'h713_tvfe_bench']:
            with_top = self.read(m.BASE + 'h713_tvfe_bench/parameters/audio_top') == 'Y'
            self.modules.remove('h713_tvfe_bench')
            self.param(m.OWNER, 'clients', 0)
            if self.truncate_log:
                self.log = 'wrapped\n'
            self.log += '15 clock words and bus verified\n'
            if with_top and not self.missing_top_restore:
                self.log += 'restored audio-top\nrestored audio-IHB clock\n'
            return SimpleNamespace(stdout='', returncode=0)
        result = super().run(argv, check, timeout)
        if argv[0] == 'insmod' and argv[1].endswith('h713-hdmi-receiver.ko') and self.invalid_clock:
            self.param(m.OWNER, 'clock_count', 5)
        if argv[0] == 'insmod' and argv[1].endswith('h713-hdmi-audio.ko'):
            self.param(m.AUDIO, 'manage_dsp', 'N')
            self.param(m.AUDIO, 'graph_ready', 'N')
        if argv == ['rmmod', m.AUDIO]:
            self.log += 'restored SPDI1\nrestored Audio Bridge output stream 0\nrestored audio-top\nrestored audio-IHB clock\n'
        return result


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.b = Board()
        self.s = bench.receiver_class(m)(self.b, '/bundle', True)

    def test_receiver_only_and_once_per_boot_latch(self):
        self.assertEqual(self.s.start()['phase'], 'receiver-only')
        self.assertFalse(self.s.loaded(m.AUDIO))
        self.assertTrue(self.s.prior()['restore_verified'])
        with self.assertRaises(RuntimeError):
            self.s.start()

    def test_normal_service_or_competing_owner_refuses_before_writes(self):
        self.b.active = True
        with self.assertRaises(RuntimeError):
            self.s.start()
        self.assertFalse(self.b.writes or self.b.modules)
        self.b.active = False
        self.b.modules.add('h713_hdmi_dsp_probe')
        with self.assertRaises(RuntimeError):
            self.s.start()
        self.assertFalse(self.b.writes)

    def test_invalid_clock_stage_latches_attempt_and_stops(self):
        self.b.invalid_clock = True
        with self.assertRaisesRegex(RuntimeError, 'clock stage'):
            self.s.start()
        self.assertEqual(self.s.prior()['phase'], 'attempted')
        self.assertFalse(self.b.writes)

    def test_tvfe_restore_uses_current_parameters_not_old_logs(self):
        self.b.log += 'unrelated old audio-top (top_ctl=700)\n'
        self.s.tvfe_only = True
        self.s.start()
        with self.assertRaises(RuntimeError):
            self.s.park()
        self.assertTrue(self.s.stop_tvfe()['tvfe_restored'])
        self.assertTrue(self.s.prior()['restore_verified'])

    def test_missing_top_restore_or_wrapped_log_never_authorizes_parking(self):
        for failure in ('missing_top_restore', 'truncate_log'):
            with self.subTest(failure=failure):
                self.setUp()
                self.s.tvfe_only = self.s.audio_top = True
                self.s.start()
                setattr(self.b, failure, True)
                with self.assertRaises(RuntimeError):
                    self.s.stop_tvfe()
                self.assertEqual(self.s.prior()['phase'], 'ready')
                with self.assertRaises(RuntimeError):
                    self.s.park()

    def test_unmanaged_audio_stop_preserves_wireplumber_and_requires_ownership(self):
        self.s.audio_no_dsp = True
        self.s.start()
        self.s.stop_audio()
        self.assertTrue(self.s.prior()['restore_verified'])
        self.assertTrue(self.b.wp)
        self.setUp()
        self.b.modules.add(m.AUDIO)
        with self.assertRaisesRegex(RuntimeError, 'owned'):
            self.s.stop_audio()

    def test_open_pcm_retains_audio_and_restores_wireplumber(self):
        self.s.audio_no_dsp = True
        self.s.start()
        self.b.files[m.PCM] = 'state: RUNNING'
        with self.assertRaisesRegex(RuntimeError, 'capture is open'):
            self.s.stop_audio()
        self.assertTrue(self.b.wp)
        self.assertTrue(self.s.loaded(m.AUDIO))

    def test_invalid_cli_options_do_not_import_target_bundle(self):
        for args in (['start'], ['start', '--armed', '--expected-boot', 'boot1', '--keep-audio-top'],
                     ['start', '--armed', '--expected-boot', 'boot1', '--audio-top', '--top-ctl', '1']):
            with self.subTest(args=args), mock.patch.object(bench, 'load_session') as loader, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                bench.main(args)
            loader.assert_not_called()

    def test_status_does_not_create_state_or_take_mutating_lock(self):
        with mock.patch.object(bench, 'load_session', return_value=m), \
                mock.patch.object(m, 'Board', return_value=self.b), \
                mock.patch.object(bench.Path, 'mkdir') as mkdir, \
                mock.patch('builtins.open') as opened, contextlib.redirect_stdout(io.StringIO()):
            bench.main(['status'])
        mkdir.assert_not_called()
        opened.assert_not_called()
        self.assertFalse(self.b.commands or self.b.writes or self.b.modules)

    def test_wrong_boot_id_does_not_touch_state_or_modules(self):
        with mock.patch.object(bench, 'load_session', return_value=m), \
                mock.patch.object(m, 'Board', return_value=self.b), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            bench.main(['start', '--armed', '--expected-boot', 'other-boot'])
        self.assertFalse(self.b.commands or self.b.writes or self.b.modules)


if __name__ == '__main__':
    unittest.main()
