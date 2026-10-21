#!/usr/bin/env python3
"""Exercise acknowledgment loss, stage ordering and prefix isolation offline."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('dsp-access-audit.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Fake:
    def __init__(self):
        self.files = {'/proc/sys/kernel/random/boot_id': b'boot-a\n',
                      '/proc/device-tree/chosen/h713,dsp-observation-v1': bytes.fromhex('44535031'),
                      '/bundle/' + m.KO: b'module', m.GUARD: b'guard',
                      '/bundle/dsp-access-audit.py': b'helper'}
        for node in ('display@5600000', 'cpu-comm@3003000'):
            self.files['/proc/device-tree/soc/' + node + '/status'] = b'disabled\0'
        self.files['/bundle/manifest.json'] = json.dumps({
            'schema': m.SCHEMA, 'kernel_release': '6.18.38',
            'module_sha256': hashlib.sha256(b'module').hexdigest(),
            'guard_sha256': hashlib.sha256(b'guard').hexdigest(),
            'helper_sha256': hashlib.sha256(b'helper').hexdigest()}).encode()
        self.calls, self.writes, self.saved = [], [], []
        self.fail = None
        self.active = 'inactive'
        self.release = '6.18.38'

    def note(self, *args, **kwargs):pass
    def read(self, path):return self.files[path]
    def exists(self, path):return path in self.files
    def save(self, value):
        self.saved.append(value.copy())
        self.files[m.STATE] = json.dumps(value).encode()
    def params(self, **values):
        for key, value in values.items():self.files[m.PARAM + key] = (str(value) + '\n').encode()

    def run(self, argv):
        self.calls.append(argv)
        if argv[0] == 'systemctl':return self.active + '\n'
        if argv[0] == 'uname':return self.release + '\n'
        if argv[0] == 'modinfo':return '6.18.38 SMP\n'
        if argv[0] == 'insmod':
            assert self.saved[-1]['phase'] == 'loading'
            if self.fail == 'load':raise subprocess.TimeoutExpired(argv, 30)
            self.files['/sys/module/' + m.MODULE] = b''
            self.params(failed='N', released='N', prefix_complete='N', completed=0,
                        attempted=0, last_value=0, next_operation=m.STEPS[0])
        elif argv[0] == 'rmmod':self.files.pop('/sys/module/' + m.MODULE)
        return ''

    def write(self, path, value):
        self.writes.append((path, value))
        if path == m.PARAM + 'advance':
            assert self.saved[-1]['phase'] == 'executing'
            if self.fail == 'step':
                self.params(failed='Y')
                raise OSError('step failed')
            n = int(value)
            self.params(completed=n, attempted=n, last_value=0,
                        prefix_complete='Y' if n == len(m.STEPS) else 'N',
                        next_operation=m.STEPS[n] if n < len(m.STEPS) else 'prefix-end')
            if self.fail == 'lost-ack':self.files['/proc/sys/kernel/random/boot_id'] = b'other'
        elif path == m.PARAM + 'release_prefix':
            assert self.saved[-1]['phase'] == 'releasing'
            if self.fail == 'release':raise OSError('release uncertain')
            self.params(released='Y')
        else:raise AssertionError('Unexpected operation')


class AuditBoundary(unittest.TestCase):
    def setUp(self):
        self.b = Fake()
        self.a = m.Audit(self.b, '/bundle', 'boot-a')

    def test_load_no_steps_and_persist_before_insmod(self):
        self.assertEqual(self.a.load()['completed'], 0)
        self.assertEqual(self.b.writes, [])
        self.assertEqual([s['phase'] for s in self.b.saved], ['loading', 'paused'])

    def test_refusal_before_load(self):
        cases = {
            'boot': ('/proc/sys/kernel/random/boot_id', b'other'),
            'handoff': ('/proc/device-tree/chosen/h713,hdmi-boot-v1', b'old'),
            'marker': ('/proc/device-tree/chosen/h713,dsp-observation-v1', b'bad'),
            'node': ('/proc/device-tree/soc/display@5600000/status', b'okay\0'),
            'device': ('/dev/cpu_comm_fd', b''),
            'owner': ('/sys/module/h713_hdmi_dsp_observe', b''),
            'legacy-attempt': ('/run/h713-dsp-observe/state.json', b'{}'),
            'guard': (m.GUARD, b'old'),
            'module': ('/bundle/' + m.KO, b'other'),
            'helper': ('/bundle/dsp-access-audit.py', b'other'),
        }
        for label, (path, value) in cases.items():
            with self.subTest(label=label):
                self.setUp()
                self.b.files[path] = value
                with self.assertRaises(RuntimeError):self.a.load()
                self.assertFalse(any(c[0] == 'insmod' for c in self.b.calls))
                self.assertEqual(self.b.writes, [])
        for attribute, value in (('active', 'failed'), ('release', 'other')):
            self.setUp()
            setattr(self.b, attribute, value)
            with self.assertRaises(RuntimeError):self.a.load()
            self.assertFalse(any(c[0] == 'insmod' for c in self.b.calls))

    def test_no_skip_repeat_or_name_mismatch(self):
        self.a.load()
        for step, name in ((0, m.STEPS[0]), (2, m.STEPS[1]), (1, 'other')):
            with self.assertRaises(RuntimeError):self.a.step(step, name)
        self.assertEqual(self.b.writes, [])
        self.a.step(1, m.STEPS[0])
        with self.assertRaises(RuntimeError):self.a.step(1, m.STEPS[0])
        self.assertEqual(len(self.b.writes), 1)

    def test_kernel_cursor_or_next_operation_mismatch_refuses_access(self):
        for fields in ({'attempted': 1}, {'completed': 1},
                       {'next_operation': 'unexpected'}, {'failed': 'Y'},
                       {'prefix_complete': 'Y'}, {'released': 'Y'}):
            with self.subTest(fields=fields):
                self.setUp()
                self.a.load()
                self.b.params(**fields)
                with self.assertRaises(RuntimeError):self.a.step(1, m.STEPS[0])
                with self.assertRaises(RuntimeError):self.a.release()
                self.assertEqual(self.b.writes, [])

    def test_all_33_steps_end_without_power_or_dsp_continuation(self):
        self.a.load()
        for n, name in enumerate(m.STEPS, 1):
            before = len(self.b.writes)
            result = self.a.step(n, name)
            self.assertEqual(len(self.b.writes), before + 1)
            self.assertEqual(result['completed'], n)
        self.assertEqual(result['next_operation'], 'prefix-end')
        self.assertEqual(result['prefix_complete'], 'Y')
        with self.assertRaises(RuntimeError):self.a.step(34, 'resume-domain')
        self.assertEqual(len(self.b.writes), 33)
        self.assertFalse(hasattr(self.a, 'versions'))

    def test_failed_load_or_step_blocks_retry_and_release(self):
        for failure in ('load', 'step'):
            with self.subTest(failure=failure):
                self.setUp()
                if failure == 'step':self.a.load()
                self.b.fail = failure
                with self.assertRaises((OSError, subprocess.TimeoutExpired)):
                    self.a.load() if failure == 'load' else self.a.step(1, m.STEPS[0])
                count = len(self.b.writes)
                for action in (self.a.load, self.a.release, lambda:self.a.step(1, m.STEPS[0])):
                    with self.assertRaises(RuntimeError):action()
                self.assertEqual(len(self.b.writes), count)

    def test_missing_ack_not_retried_even_if_kernel_completed(self):
        self.a.load()
        self.b.fail = 'lost-ack'
        with self.assertRaises(RuntimeError):self.a.step(1, m.STEPS[0])
        self.b.files['/proc/sys/kernel/random/boot_id'] = b'boot-a'
        with self.assertRaises(RuntimeError):self.a.step(1, m.STEPS[0])
        with self.assertRaises(RuntimeError):self.a.release()
        self.assertEqual(len(self.b.writes), 1)
        self.assertEqual(self.a.status()['state']['phase'], 'executing')

    def test_partial_healthy_release_and_no_reload(self):
        self.a.load()
        self.a.step(1, m.STEPS[0])
        self.a.release()
        self.assertEqual(self.b.writes[-1], (m.PARAM + 'release_prefix', b'1\n'))
        self.assertEqual(self.b.calls[-1][0], 'rmmod')
        with self.assertRaises(RuntimeError):self.a.load()

    def test_uncertain_release_does_not_unload_or_retry(self):
        self.a.load()
        self.b.fail = 'release'
        with self.assertRaises(OSError):self.a.release()
        with self.assertRaises(RuntimeError):self.a.release()
        self.assertFalse(any(c[0] == 'rmmod' for c in self.b.calls))

    def test_python_kernel_step_protocol_matches(self):
        source = (Path(__file__).resolve().parents[2] / 'modules/hdmi-dsp-access-audit/h713-hdmi-dsp-access-audit.c').read_text()
        plan = source.split('static const struct audit_step steps[] = {', 1)[1].split('\n};', 1)[0]
        names = []
        for line in plan.splitlines():
            if line.startswith('#'):continue
            for item in re.finditer(r'\{\s*[A-Z_]+, \d+, "([^"]+)"\s*\}|CLOCK_STEP\(\d+, "([^"]+)"\)', line):
                names.append(item.group(1) or 'get-clock-' + item.group(2))
        self.assertEqual(tuple(names), m.STEPS)


if __name__ == '__main__':unittest.main()
