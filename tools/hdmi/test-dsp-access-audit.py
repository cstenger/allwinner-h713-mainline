#!/usr/bin/env python3
"""Exercise acknowledgment loss, stage ordering, stage gates and isolation offline."""
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


def name_after(n):
    return m.STEPS[n] if n < len(m.STEPS) else 'extension-end'


class Fake:
    def __init__(self):
        self.files = {'/proc/sys/kernel/random/boot_id': b'boot-a\n',
                      '/proc/device-tree/chosen/h713,dsp-observation-v1': bytes.fromhex('44535031'),
                      '/proc/device-tree/chosen/h713,dsp-observation-v2': bytes.fromhex('44535032'),
                      '/bundle/' + m.KO: b'module', m.GUARD: b'guard',
                      '/bundle/dsp-access-audit.py': b'helper',
                      '/proc/sys/kernel/printk': b'7\t4\t1\t7\n',
                      '/proc/sys/kernel/panic': b'0\n'}
        for path in m.SNAPSHOTS:self.files[path] = b'snapshot text\n'
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
        self.extension = 'Y'

    def note(self, *args, **kwargs):pass
    def read(self, path):return self.files[path]
    def exists(self, path):return path in self.files
    def save(self, value):
        self.saved.append(value.copy())
        self.files[m.STATE] = json.dumps(value).encode()
    def params(self, **values):
        for key, value in values.items():self.files[m.PARAM + key] = (str(value) + '\n').encode()
    def cursor(self, n):
        self.params(completed=n, attempted=n, last_value=0,
                    prefix_complete='Y' if n >= m.PREFIX_STEPS else 'N',
                    extension_complete='Y' if n == len(m.STEPS) else 'N',
                    next_operation=name_after(n))

    def run(self, argv):
        self.calls.append(argv)
        if argv[0] == 'systemctl':return self.active + '\n'
        if argv[0] == 'uname':return self.release + '\n'
        if argv[0] == 'modinfo':return '6.18.38 SMP\n'
        if argv[0] == 'insmod':
            assert self.saved[-1]['phase'] == 'loading'
            if self.fail == 'load':raise subprocess.TimeoutExpired(argv, 30)
            self.files['/sys/module/' + m.MODULE] = b''
            self.params(failed='N', released='N', extension_available=self.extension,
                        tv_words='0,0,0,0,0,0,0,0,0,0,0,0,0,0,0', tvcap_reset_before=4294967295)
            self.cursor(0)
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
            self.cursor(n)
            if n == 38:self.params(tvcap_reset_before=1)
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

    def run_to(self, target):
        """Advance step by step, taking a snapshot and stage-ack at each boundary."""
        n = self.a.paused()[1]['completed']
        while n < target:
            ack = None
            if n in m.STAGES:
                self.a.snapshot()
                ack = m.STAGES[n]
            self.a.step(n + 1, m.STEPS[n], ack)
            n += 1

    def test_load_no_steps_and_persist_before_insmod(self):
        self.assertEqual(self.a.load()['completed'], 0)
        self.assertEqual(self.b.writes, [])
        self.assertEqual([s['phase'] for s in self.b.saved], ['loading', 'paused'])

    def test_refusal_before_load(self):
        cases = {
            'boot': ('/proc/sys/kernel/random/boot_id', b'other'),
            'handoff': ('/proc/device-tree/chosen/h713,hdmi-boot-v1', b'old'),
            'marker': ('/proc/device-tree/chosen/h713,dsp-observation-v1', b'bad'),
            'marker-v2': ('/proc/device-tree/chosen/h713,dsp-observation-v2', b'bad'),
            'keep-tvcap-on': (m.PPU_NODE + 'allwinner,keep-tvcap-on', b''),
            'node': ('/proc/device-tree/soc/display@5600000/status', b'okay\0'),
            'device': ('/dev/cpu_comm_fd', b''),
            'owner': ('/sys/module/h713_hdmi_dsp_observe', b''),
            'legacy-attempt': ('/run/h713-dsp-observe/state.json', b'{}'),
            'guard': (m.GUARD, b'old'),
            'module': ('/bundle/' + m.KO, b'other'),
            'helper': ('/bundle/dsp-access-audit.py', b'other'),
            'console-default': ('/proc/sys/kernel/printk', b'5\t4\t1\t7\n'),
            'console-garbled': ('/proc/sys/kernel/printk', b''),
            'panic-reboot': ('/proc/sys/kernel/panic', b'5\n'),
        }
        for label, (path, value) in cases.items():
            with self.subTest(label=label):
                self.setUp()
                self.b.files[path] = value
                with self.assertRaises(RuntimeError):self.a.load()
                self.assertFalse(any(c[0] == 'insmod' for c in self.b.calls))
                self.assertEqual(self.b.writes, [])
        with self.subTest(label='boot-v3 (no v2 marker)'):
            self.setUp()
            del self.b.files['/proc/device-tree/chosen/h713,dsp-observation-v2']
            with self.assertRaises(RuntimeError):self.a.load()
            self.assertFalse(any(c[0] == 'insmod' for c in self.b.calls))
        for attribute, value in (('active', 'failed'), ('release', 'other')):
            self.setUp()
            setattr(self.b, attribute, value)
            with self.assertRaises(RuntimeError):self.a.load()
            self.assertFalse(any(c[0] == 'insmod' for c in self.b.calls))

    def test_kernel_without_extension_is_refused_at_load(self):
        self.b.extension = 'N'
        with self.assertRaises(RuntimeError):self.a.load()
        self.assertEqual(self.b.writes, [])

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
                       {'prefix_complete': 'Y'}, {'released': 'Y'},
                       {'extension_available': 'N'}, {'extension_complete': 'Y'}):
            with self.subTest(fields=fields):
                self.setUp()
                self.a.load()
                self.b.params(**fields)
                with self.assertRaises(RuntimeError):self.a.step(1, m.STEPS[0])
                with self.assertRaises(RuntimeError):self.a.release()
                self.assertEqual(self.b.writes, [])

    def test_every_stage_boundary_needs_snapshot_and_exact_ack(self):
        self.a.load()
        for boundary, stage in m.STAGES.items():
            with self.subTest(stage=stage):
                self.run_to(boundary)
                nxt = m.STEPS[boundary]
                writes = len(self.b.writes)
                with self.assertRaises(RuntimeError):self.a.step(boundary + 1, nxt)
                with self.assertRaises(RuntimeError):self.a.step(boundary + 1, nxt, stage)  # no snapshot
                self.a.snapshot()
                with self.assertRaises(RuntimeError):self.a.step(boundary + 1, nxt, 'wrong')
                self.assertEqual(len(self.b.writes), writes)
                self.a.step(boundary + 1, nxt, stage)
                self.assertEqual(len(self.b.writes), writes + 1)

    def test_stage_ack_refused_away_from_boundary_and_snapshot_only_at_boundary(self):
        self.a.load()
        with self.assertRaises(RuntimeError):self.a.step(1, m.STEPS[0], 'prefix')
        with self.assertRaises(RuntimeError):self.a.snapshot()
        self.assertEqual(self.b.writes, [])

    def test_snapshot_is_cleared_by_the_next_step(self):
        self.a.load()
        self.run_to(m.PREFIX_STEPS)
        self.a.snapshot()
        self.a.step(34, m.STEPS[33], 'prefix')
        self.run_to(39)
        self.assertNotIn('snapshot_at', self.b.saved[-1])

    def test_all_82_steps_end_without_audiotop_or_release(self):
        self.a.load()
        self.run_to(len(m.STEPS))
        result = self.a.paused()[1]
        self.assertEqual(result['next_operation'], 'extension-end')
        self.assertEqual(result['extension_complete'], 'Y')
        self.assertEqual(len([w for w in self.b.writes if w[0].endswith('advance')]), 82)
        with self.assertRaises(RuntimeError):self.a.step(83, 'map-audiotop')
        with self.assertRaises(RuntimeError):self.a.release()
        self.assertFalse(any('audiotop' in s or 'dsp-port' in s for s in m.STEPS[33:]))
        self.assertFalse(hasattr(self.a, 'versions'))

    def test_census_results_recorded_at_last_read_only_step(self):
        self.a.load()
        self.run_to(m.LAST_READ_ONLY_STEP - 1)
        result = self.a.step(40, m.STEPS[39])
        self.assertEqual(result['tvcap_reset_before'], 1)
        self.assertEqual(len(result['tv_words'].split(',')), 15)

    def test_release_allowed_through_census_refused_after_first_state_change(self):
        self.a.load()
        self.run_to(m.LAST_READ_ONLY_STEP)
        self.a.release()
        self.assertEqual(self.b.calls[-1][0], 'rmmod')
        self.setUp()
        self.a.load()
        self.run_to(m.LAST_READ_ONLY_STEP + 1)
        with self.assertRaises(RuntimeError):self.a.release()
        self.assertFalse(any(w[0].endswith('release_prefix') for w in self.b.writes))

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

    def test_uncertain_release_does_not_unload_or_retry(self):
        self.a.load()
        self.b.fail = 'release'
        with self.assertRaises(OSError):self.a.release()
        with self.assertRaises(RuntimeError):self.a.release()
        self.assertFalse(any(c[0] == 'rmmod' for c in self.b.calls))

    def test_python_kernel_step_protocol_matches(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / 'modules/hdmi-dsp-access-audit/h713-hdmi-dsp-access-audit.c').read_text()
        plan = source.split('static const struct audit_step steps[] = {', 1)[1].split('\n};', 1)[0]
        names = []
        pattern = (r'\{\s*[A-Z_]+, \d+, "([^"]+)"\s*\}|CLOCK_STEP\(\d+, "([^"]+)"\)'
                   r'|ENABLE_STEP\(\d+, "([^"]+)"\)|TV_WORD_STEP\(\d+, "([^"]+)"\)')
        for line in plan.splitlines():
            if line.lstrip().startswith(('#', '/*')):continue
            for item in re.finditer(pattern, line):
                names.append(item.group(1) or (item.group(2) and 'get-clock-' + item.group(2))
                             or (item.group(3) and 'enable-clock-' + item.group(3))
                             or 'write-tv-word-' + item.group(4))
        self.assertEqual(tuple(names), m.STEPS)
        self.assertEqual(len(names), 82)
        # Stage boundaries and the release limit match the C constants.
        self.assertIn('#define PREFIX_STEPS %d' % m.PREFIX_STEPS, source)
        self.assertIn('#define LAST_READ_ONLY_STEP %d' % m.LAST_READ_ONLY_STEP, source)
        # ENABLE_STEP clock indices name the same clocks as the C clock table.
        for idx, name in re.findall(r'ENABLE_STEP\((\d+), "([^"]+)"\)', plan):
            self.assertEqual(m.CLOCKS[int(idx)], name)
        for idx, name in re.findall(r'CLOCK_STEP\((\d+), "([^"]+)"\)', plan):
            self.assertEqual(m.CLOCKS[int(idx)], name)

    def test_tv_word_steps_match_c_offsets(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / 'modules/hdmi-dsp-access-audit/h713-hdmi-dsp-access-audit.c').read_text()
        offsets = source.split('static const u16 tv_offsets[] = {', 1)[1].split('};', 1)[0]
        regs = ['d%02x' % (0x10 + int(x, 16)) for x in re.findall(r'0x([0-9a-f]+)', offsets)]
        self.assertEqual(['write-tv-word-' + r for r in regs],
                         [s for s in m.STEPS if s.startswith('write-tv-word-')])


if __name__ == '__main__':unittest.main()
