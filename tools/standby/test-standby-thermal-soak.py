#!/usr/bin/env python3
"""The standby soak always wakes through h713-standby, and aborts hot."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('soak', Path(__file__).with_name('standby-thermal-soak.py'))
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Board:
    """Fake sysfs plus an h713-standby that flips the lamp like the real one."""
    def __init__(self, root, temp_at=lambda t: 55.0, state='off', enter_rc=0):
        self.root, self.temp_at, self.state, self.enter_rc = root, temp_at, state, enter_rc
        self.now, self.calls = 0.0, []
        for zone, kind in (('thermal_zone0', 'cpu-thermal'), ('thermal_zone1', 'gpu-thermal')):
            (root/'class/thermal'/zone).mkdir(parents=True)
            (root/'class/thermal'/zone/'type').write_text(kind)
        policy = root/'devices/system/cpu/cpufreq/policy0';policy.mkdir(parents=True)
        (policy/'scaling_cur_freq').write_text('1008000');(policy/'scaling_max_freq').write_text('1296000')
        (root/'class/backlight/lamp').mkdir(parents=True)
        self.lamp('0' if state == 'off' else '4')
        self.write_temps()
    def lamp(self, value): (self.root/'class/backlight/lamp/bl_power').write_text(value)
    def write_temps(self):
        for zone in ('thermal_zone0', 'thermal_zone1'):
            (self.root/'class/thermal'/zone/'temp').write_text(str(int(self.temp_at(self.now) * 1000)))
    def clock(self): return self.now
    def sleep(self, seconds): self.now += seconds;self.write_temps()
    def run(self, argv, **kw):
        arg = argv[1];self.calls.append(arg)
        if arg == '':
            return SimpleNamespace(returncode=0, stdout=self.state + '\n', stderr='')
        if arg == 'on':
            if self.enter_rc == 0:
                self.state = 'on';self.lamp('4')
            return SimpleNamespace(returncode=self.enter_rc, stdout='', stderr='')
        self.state = 'off';self.lamp('0')
        return SimpleNamespace(returncode=0, stdout='', stderr='')


class Soak(unittest.TestCase):
    def go(self, board, seconds=60, abort=70.0):
        out = io.StringIO()
        rc = m.soak(seconds, out, abort, 10, root=board.root, standby='h713-standby',
                    clock=board.clock, sleep=board.sleep, run=board.run)
        return rc, [json.loads(line) for line in out.getvalue().splitlines()]
    def board(self, **kw):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return Board(Path(temp.name), **kw)
    def test_completes_then_wakes_through_the_standby_tool(self):
        b = self.board();rc, rows = self.go(b)
        self.assertEqual(rc, 0)
        self.assertEqual(b.calls, ['', 'on', 'off'])
        self.assertEqual([r['kind'] for r in rows][-1], 'woke')
        self.assertEqual(len([r for r in rows if r['kind'] == 'sample']), 6)
    def test_hot_zone_aborts_and_still_wakes(self):
        b = self.board(temp_at=lambda t: 55.0 + t / 2)       # reaches 70 C at 30 s
        rc, rows = self.go(b, seconds=3600)
        self.assertEqual(rc, 2)
        self.assertIn('abort', [r['kind'] for r in rows])
        self.assertEqual(b.calls[-1], 'off');self.assertEqual(rows[-1]['kind'], 'woke')
        self.assertLessEqual(rows[-1]['elapsed'], 40)
    def test_refuses_unless_starting_awake(self):
        b = self.board(state='on');rc, rows = self.go(b)
        self.assertEqual(rc, 1);self.assertEqual(b.calls, [''])
        self.assertEqual(rows[0]['kind'], 'refused')
    def test_failed_entry_tries_to_wake_and_fails_the_run(self):
        b = self.board(enter_rc=1);rc, rows = self.go(b)
        self.assertEqual(rc, 1);self.assertEqual(b.calls, ['', 'on', 'off'])
        self.assertEqual(rows[-1]['kind'], 'enter_failed')
    def test_peak_is_reported_on_wake(self):
        b = self.board(temp_at=lambda t: 55.0 + (t % 30) / 10)
        rc, rows = self.go(b, seconds=90)
        self.assertEqual(rc, 0);self.assertAlmostEqual(rows[-1]['peak']['cpu-thermal'], 57.0)


if __name__ == '__main__': unittest.main()
