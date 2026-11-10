#!/usr/bin/env python3
"""Offline fixtures only; no board paths are read or written by these tests."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import build
import hdmi_delay_bench as h


class Delay(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.boot = 'b6849123-0398-4736-b06f-cfe25b19e593'
        self.put(h.BOOT, self.boot)
        self.put(h.STATE, json.dumps({'boot_id': self.boot, 'phase': 'ready'}))
        for module, params in h.PARAMS.items():
            for name, value in params.items():
                self.put(f'/sys/module/{module}/parameters/{name}', value)
        for domain in ('tvfe', 'tvcap'):
            self.put(f'/sys/devices/h713-hdmi-{domain}/power/runtime_status', 'active')
        path = self.put('/usr/lib/h713-hdmi/fixture.ko', 'unchanged module')
        info = path.stat()
        self.manifest = {'schema': 'h713-start-delay-v1', 'excluded_boot_id': h.EXCLUDED_BOOT,
            'bundle': '/usr/lib/h713-hdmi', 'file_pins': { '/usr/lib/h713-hdmi/fixture.ko': {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': info.st_size,
                'mode': info.st_mode & 0o7777, 'uid': info.st_uid, 'gid': info.st_gid}}}
        self.manifest_path = self.root/'manifest.json'
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.digest = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        self.now = 10_000_000_000
        self.logs, self.commands, self.sleeps = [], [], []
        self.sleep_hook = None
        self.emit_hook = None
        candidate = build.transform(build.BASE.read_text(), self.digest)
        namespace = {'__name__': 'candidate_test', '__file__': str(self.root/'candidate.py')}
        exec(compile(candidate, namespace['__file__'], 'exec'), namespace)
        self.m = argparse.Namespace(**namespace)
        # main's function globals, not Namespace attributes, own constants.
        self.g = namespace
        for name in ('MODULE', 'DDC', 'PROBE', 'OWNED', 'ATTEMPTED', 'GRAPH'):
            self.g[name] = self.path(str(namespace[name]))

    def path(self, name):
        return self.root/name.lstrip('/')

    def put(self, name, value):
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.assertFalse(self.g['OWNED'].exists() or self.g['ATTEMPTED'].exists())
        self.assertEqual(self.commands, [])
        self.now += round(seconds*1_000_000_000)
        if self.sleep_hook:
            self.sleep_hook()

    def emit(self, value):
        self.logs.append(value)
        if self.emit_hook:
            self.emit_hook()

    def bench(self, delay=2000, **kwargs):
        return h.Bench(self.manifest_path, self.digest, delay, root=self.root,
                       clock=lambda:self.now, sleep=self.sleep, emit=self.emit, **kwargs)

    def command(self, argv):
        self.assertTrue(self.g['OWNED'].exists() and self.g['ATTEMPTED'].exists())
        self.commands.append((self.now, argv))

    def action(self, *args):
        original = h.Bench
        def factory(manifest, digest, delay):
            return original(manifest, digest, delay, root=self.root,
                            clock=lambda:self.now, sleep=self.sleep, emit=self.emit)
        self.g['run'] = self.command
        self.g['param'] = lambda name: {'ready':'Y', 'failed':'N', 'restored':'N'}[name]
        with patch.object(h, 'Bench', side_effect=factory), \
             patch.object(sys, 'argv', ['candidate', *args]), contextlib.redirect_stdout(io.StringIO()):
            self.g['main']()

    def start(self, delay=2000, *extra):
        self.action('start', '--bench-delay-ms', str(delay), '--bench-manifest',
                    str(self.manifest_path), *extra)

    def test_delayed_wrapper_orders_wait_markers_ddc_and_scp(self):
        self.start()
        self.assertEqual([x[1][1].rsplit('/',1)[-1] for x in self.commands],
                         ['h713-ddc-pins.ko', 'h713-hdmi-signal.ko'])
        self.assertGreaterEqual(self.commands[0][0], 12_000_000_000)
        self.assertEqual(self.commands[1][1][2:], ['armed=1'])
        self.assertEqual(self.logs[-1]['elapsed_ns'], 2_000_000_000)

    def test_zero_control_has_same_checks_logs_and_commands_without_sleep(self):
        self.start(0)
        self.assertEqual(self.sleeps, [])
        self.assertEqual(self.commands[0][0], 10_000_000_000)
        self.assertEqual([v['phase'] for v in self.logs], ['delay-start','delay-complete'])

    def test_short_sleeps_do_not_shorten_wait(self):
        def short(seconds):
            self.now += min(250_000_000, round(seconds*1e9))
        bench = self.bench()
        bench.sleep = short
        bench.wait()
        self.assertGreaterEqual(self.logs[-1]['elapsed_ns'], 2_000_000_000)

    def test_interrupted_sleep_aborts_before_holds(self):
        def interrupt():
            raise InterruptedError('interrupted')
        self.sleep_hook = interrupt
        with self.assertRaises(InterruptedError):self.start()
        self.assertEqual(self.commands, [])
        self.assertFalse(self.g['OWNED'].exists() or self.g['ATTEMPTED'].exists())

    def test_current_failed_boot_refuses_before_any_delay_or_holds(self):
        self.put(h.BOOT, h.EXCLUDED_BOOT)
        with self.assertRaisesRegex(RuntimeError, 'excluded'):self.start()
        self.assertEqual(self.sleeps+self.commands+self.logs, [])

    def test_owners_diagnostics_and_latches_refuse(self):
        for name in h.ABSENT:
            with self.subTest(path=name):
                path=self.put(name, 'present')
                with self.assertRaisesRegex(RuntimeError, 'present'):self.start()
                path.unlink()
        self.assertEqual(self.commands+self.sleeps, [])

    def test_every_readiness_gate_refuses(self):
        for module, params in h.PARAMS.items():
            for name, value in params.items():
                with self.subTest(module=module, param=name):
                    path = self.put(f'/sys/module/{module}/parameters/{name}', 'bad')
                    with self.assertRaisesRegex(RuntimeError, 'readiness'):self.start()
                    path.write_text(value)
        self.assertEqual(self.commands+self.sleeps, [])

    def test_session_must_be_ready_and_current(self):
        for state in ({'phase':'starting','boot_id':self.boot}, {'phase':'ready','boot_id':h.EXCLUDED_BOOT}):
            self.put(h.STATE,json.dumps(state))
            with self.assertRaisesRegex(RuntimeError, 'session'):self.start()
        self.assertEqual(self.commands+self.sleeps, [])

    def test_inactive_receiver_domain_refuses(self):
        self.put('/sys/devices/h713-hdmi-tvfe/power/runtime_status','suspended')
        with self.assertRaisesRegex(RuntimeError,'inactive'):self.start()
        self.assertEqual(self.commands+self.sleeps, [])

    def test_pin_content_and_metadata_refuse(self):
        path=self.path('/usr/lib/h713-hdmi/fixture.ko')
        path.write_text('CHANGED!! module') # same length, content mismatch
        with self.assertRaisesRegex(RuntimeError,'pin content'):self.start()
        path.write_text('unchanged module');path.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError,'pin metadata'):self.start()
        self.assertEqual(self.commands+self.sleeps, [])

    def test_missing_pin_refuses(self):
        self.path('/usr/lib/h713-hdmi/fixture.ko').unlink()
        with self.assertRaises(FileNotFoundError):self.start()
        self.assertEqual(self.commands+self.sleeps, [])

    def test_symlink_pin_refuses(self):
        path=self.path('/usr/lib/h713-hdmi/fixture.ko');path.unlink()
        path.symlink_to(self.manifest_path)
        with self.assertRaisesRegex(RuntimeError,'not regular'):self.start()

    def test_manifest_tamper_refuses(self):
        self.manifest_path.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'manifest hash'):self.start()
        self.assertEqual(self.commands+self.sleeps, [])

    def test_post_delay_boot_graph_pin_owner_drift_refuse_before_holds(self):
        for drift in ('boot','graph','pin','owner'):
            with self.subTest(drift=drift):
                self.setUp()
                def change():
                    if drift=='boot':self.put(h.BOOT,h.EXCLUDED_BOOT)
                    elif drift=='graph':self.g['GRAPH'].write_text('N')
                    elif drift=='pin':self.put('/usr/lib/h713-hdmi/fixture.ko','bad')
                    else:self.put('/sys/module/h713_scp_sampler_v2','present')
                self.sleep_hook=change
                with self.assertRaises(RuntimeError):self.start()
                self.assertEqual(self.commands,[])
                self.assertFalse(self.g['OWNED'].exists() or self.g['ATTEMPTED'].exists())

    def test_backwards_clock_refuses(self):
        self.sleep_hook=lambda:setattr(self,'now',0)
        with self.assertRaisesRegex(RuntimeError,'backwards'):self.start()
        self.assertEqual(self.commands,[])

    def test_logging_failure_refuses_before_holds(self):
        for phase in ('delay-start','delay-complete'):
            with self.subTest(phase=phase):
                self.setUp()
                def fail():
                    if self.logs[-1]['phase']==phase:raise BrokenPipeError('log failed')
                self.emit_hook=fail
                with self.assertRaises(BrokenPipeError):self.start()
                self.assertEqual(self.commands,[])
                self.assertFalse(self.g['OWNED'].exists())

    def test_invalid_cli_and_fault_arguments_refuse(self):
        for extra in (('--signal-arg','fault=2'),('--bundle','/tmp/other')):
            with self.assertRaises(RuntimeError):self.start(2000,*extra)
        for delay in (-1,1,1999,2001):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):self.start(delay)
        with self.assertRaisesRegex(RuntimeError,'both bench options'):
            self.action('start','--bench-delay-ms','2000')
        with self.assertRaisesRegex(RuntimeError,'both bench options'):
            self.action('start','--bench-manifest',str(self.manifest_path))
        with self.assertRaisesRegex(RuntimeError,'only allowed on start'):
            self.action('stop','--bench-delay-ms','2000','--bench-manifest',str(self.manifest_path))
        self.assertEqual(self.commands+self.sleeps,[])

    def test_invalid_boot_id_refuses(self):
        self.put(h.BOOT,'not-a-boot-id')
        with self.assertRaises(ValueError):self.start()

    def test_second_start_retains_existing_latches_and_refuses(self):
        self.start();count=len(self.commands)
        with self.assertRaisesRegex(RuntimeError,'present'):self.start()
        self.assertEqual(len(self.commands),count)
        self.assertTrue(self.g['OWNED'].exists() and self.g['ATTEMPTED'].exists())

    def test_ddc_claim_failure_retains_attempt_markers(self):
        def oracle(argv):
            self.assertTrue(self.g['OWNED'].exists() and self.g['ATTEMPTED'].exists())
            self.commands.append((self.now,argv))
            raise subprocess.CalledProcessError(1,argv)
        self.command=oracle
        with self.assertRaises(subprocess.CalledProcessError):self.start()
        self.assertTrue(self.g['OWNED'].exists() and self.g['ATTEMPTED'].exists())
        with self.assertRaises(RuntimeError):self.start()
        self.assertEqual(len(self.commands),1)

    def test_pre_scp_refusal_releases_only_ddc_and_retains_attempt(self):
        def command(argv):
            self.commands.append((self.now,argv))
            if argv[0]=='insmod' and argv[1].endswith('h713-ddc-pins.ko'):
                self.g['DDC'].mkdir(parents=True)
            elif argv[0]=='insmod':raise subprocess.CalledProcessError(1,argv)
            elif argv==['rmmod','h713_ddc_pins']:shutil.rmtree(self.g['DDC'])
            else:self.fail(str(argv))
        self.command=command
        with self.assertRaisesRegex(RuntimeError,'nothing retained'):self.start()
        self.assertFalse(self.g['DDC'].exists() or self.g['OWNED'].exists())
        self.assertTrue(self.g['ATTEMPTED'].exists())

    def test_ambiguous_loaded_signal_refusal_retains_all_holds(self):
        def command(argv):
            self.commands.append((self.now,argv))
            if argv[1].endswith('h713-ddc-pins.ko'):self.g['DDC'].mkdir(parents=True)
            else:
                self.g['MODULE'].mkdir(parents=True)
                raise subprocess.CalledProcessError(1,argv)
        self.command=command
        with self.assertRaisesRegex(RuntimeError,'holds retained'):self.start()
        self.assertTrue(all(self.g[n].exists() for n in ('DDC','MODULE','OWNED','ATTEMPTED')))
        self.assertEqual(len(self.commands),2)

    def test_original_ast_and_stop_are_preserved(self):
        source=build.BASE.read_text()
        self.assertTrue(build.verify_ast(source,build.transform(source,self.digest))['stop_branch_unchanged'])
        with self.assertRaisesRegex(RuntimeError,'outside approved hooks'):
            build.verify_ast(source,build.transform(source,self.digest).replace("'armed=1'","'armed=0'"))

    def test_real_monotonic_two_second_wait_offline(self):
        bench=h.Bench(self.manifest_path,self.digest,2000,root=self.root,emit=self.emit)
        start=time.monotonic_ns();bench.wait();elapsed=time.monotonic_ns()-start
        self.assertGreaterEqual(elapsed,2_000_000_000)
        self.assertGreaterEqual(self.logs[-1]['elapsed_ns'],2_000_000_000)


if __name__=='__main__':unittest.main(verbosity=2)
