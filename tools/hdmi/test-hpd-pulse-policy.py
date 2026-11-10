#!/usr/bin/env python3
"""One re-advertise mechanism: spec HPD pulses on a bounded schedule."""
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('retry', Path(__file__).with_name('h713-hdmi-readvertise.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Power:
    def __init__(self, value): self.value, self.closed = value, False
    def read(self): return self.value
    def wait(self, seconds, sleep): sleep(seconds)
    def close(self): self.closed = True


class Pulse(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.params, self.signal = root / 'parameters', root / 'signal'
        self.params.mkdir()
        for name, value in {'ready': 'Y', 'failed': 'N', 'readvertised': '0', 'readvertise': '',
                            'hpd_pulses': '0', 'hpd_pulse': ''}.items():
            (self.params / name).write_text(value)
        self.signal.write_text('none')
        self.time, self.pulses, self.readvertises = 0.0, [], []
        self.respond = True        # a source that connects ~1.4 s after a pulse
        self.script = {}           # time -> signal text
        self.power_script = {}     # time -> power value
        self.refuse = False
        self.power = Power(None)
        self.pending = None
        original = Path.write_text

        def write(path, data, *a, **k):
            if path == self.params / 'hpd_pulse':
                if self.refuse:
                    raise PermissionError(1, 'Operation not permitted')
                self.pulses.append((round(self.time, 2), data))
                self.time += 0.15
                if self.respond:
                    self.pending = self.time + 1.4
                return len(data)
            if path == self.params / 'readvertise':
                self.readvertises.append(round(self.time, 2))
                return len(data)
            return original(path, data, *a, **k)
        for p in (patch.object(m, 'PARAMS', self.params), patch.object(m, 'SIGNAL', self.signal),
                  patch.object(Path, 'write_text', write)):
            p.start()
            self.addCleanup(p.stop)

    def sleep(self, seconds):
        before = self.time
        self.time += seconds
        for t, text in self.script.items():
            if before < t <= self.time:
                self.signal.write_text(text)
        for t, value in self.power_script.items():
            if before < t <= self.time:
                self.power.value = value
        if self.pending is not None and self.time >= self.pending:
            self.signal.write_text('locked 1280x720')
            self.pending = None

    def run_for(self, seconds):
        with redirect_stdout(io.StringIO()):
            return m.main(lambda: self.time, self.sleep, polls=int(seconds / m.PULSE_POLL), power=self.power)

    def test_fresh_silent_source_gets_one_short_pulse_after_two_seconds(self):
        self.run_for(60)
        self.assertEqual(len(self.pulses), 1)
        self.assertGreaterEqual(self.pulses[0][0], m.PULSE_FIRST)
        self.assertLess(self.pulses[0][0], m.PULSE_FIRST + m.PULSE_POLL + 0.01)
        self.assertEqual(self.pulses[0][1], f'{m.PULSE_MS}\n')
        self.assertEqual(self.readvertises, [])
        self.assertTrue(self.power.closed)

    def test_source_that_honours_the_first_advert_is_never_pulsed(self):
        self.script = {1.4: 'locked 1280x720'}
        self.run_for(400)
        self.assertEqual(self.pulses, [])

    def test_unanswered_pulses_follow_the_bounded_schedule(self):
        self.respond = False
        self.run_for(400)
        times = [t for t, _ in self.pulses]
        steps = [round(b - a) for a, b in zip([0.0] + times, times)]
        self.assertEqual(steps[0], m.PULSE_FIRST)
        self.assertEqual(steps[1:], list(m.SCHEDULE))  # each measured from the previous pulse
        self.assertEqual(self.readvertises, [])

    def test_lost_source_waits_the_original_ten_seconds(self):
        self.signal.write_text('locked 1280x720')
        self.respond = False
        self.script = {50: 'none'}
        self.run_for(100)
        self.assertEqual(len(self.pulses), 2)          # 10 s after loss, then 20 s later
        self.assertGreaterEqual(self.pulses[0][0], 60)
        self.assertLess(self.pulses[0][0], 60.3)
        self.assertAlmostEqual(self.pulses[1][0] - self.pulses[0][0], m.SCHEDULE[1], delta=0.5)

    def test_returning_source_power_restarts_the_fresh_schedule(self):
        self.respond = False
        self.power.value = False
        self.power_script = {30: True}
        self.run_for(50)
        self.assertEqual(len(self.pulses), 2)
        self.assertGreaterEqual(self.pulses[0][0], 30 + m.PULSE_FIRST)
        self.assertLess(self.pulses[0][0], 30 + m.PULSE_FIRST + 0.3)
        self.assertAlmostEqual(self.pulses[1][0] - self.pulses[0][0], m.SCHEDULE[0], delta=0.5)

    def test_absent_power_or_failed_owner_is_never_pulsed(self):
        for case in ('absent', 'failed'):
            with self.subTest(case=case):
                self.setUp()
                if case == 'absent':
                    self.power.value = False
                else:
                    (self.params / 'failed').write_text('Y')
                self.run_for(60)
                self.assertEqual(self.pulses, [])

    def test_refused_pulse_stops_the_service_like_a_refused_readvertise(self):
        self.refuse = True
        self.assertEqual(self.run_for(10), 1)

    def test_owner_without_the_pulse_keeps_the_original_hold_schedule(self):
        (self.params / 'hpd_pulse').unlink()
        with redirect_stdout(io.StringIO()):
            m.main(lambda: self.time, self.sleep, polls=40, power=self.power)  # 1 s polls
        self.assertEqual(self.pulses, [])
        self.assertEqual(self.readvertises, [10.0, 30.0])

    def test_pulse_length_meets_the_hdmi_minimum(self):
        self.assertGreaterEqual(m.PULSE_MS, 100)
        self.assertLessEqual(m.PULSE_MS, 2000)

    def activity_owner(self):
        (self.params.parent / 'version').write_text('ddc-activity-hpd-pulse-v2\n')
        (self.params / 'ddc_scan').write_text('window 06840094 count 4 seq 10 clear 0 act 0\n')
        self.order = []
        original = Path.write_text
        def spy(path, data, *a, **k):
            if path.name in ('ddc_scan', 'hpd_pulse'):
                self.order.append((path.name, data))
            return spy.inner(path, data, *a, **k)
        spy.inner = Path.write_text
        p = patch.object(Path, 'write_text', spy)
        p.start()
        self.addCleanup(p.stop)

    def test_activity_owner_logs_and_rearms_before_each_pulse(self):
        self.activity_owner()
        out = io.StringIO()
        with redirect_stdout(out):
            m.main(lambda: self.time, self.sleep, polls=int(60 / m.PULSE_POLL), power=self.power)
        names = [n for n, _ in self.order]
        self.assertEqual(names[names.index('hpd_pulse') - 1], 'ddc_scan')
        self.assertIn(('ddc_scan', m.ACTIVITY_WINDOW + '\n'), self.order)
        phases = [__import__('json').loads(l)['phase'] for l in out.getvalue().splitlines() if l.startswith('{')]
        self.assertEqual(phases[:3], ['start', 'before_pulse', 'source_seen'])
        self.assertEqual(len(self.pulses), 1)

    def test_production_owner_never_touches_the_scan(self):
        (self.params / 'ddc_scan').write_text('window 0 count 0 seq 1 clear 0\n')
        self.order = []
        before = (self.params / 'ddc_scan').read_text()
        out = io.StringIO()
        with redirect_stdout(out):
            m.main(lambda: self.time, self.sleep, polls=int(60 / m.PULSE_POLL), power=self.power)
        self.assertEqual((self.params / 'ddc_scan').read_text(), before)
        self.assertNotIn('ddc_activity', out.getvalue())
        self.assertEqual(len(self.pulses), 1)


FAILED = 'window 06840094 count 4 seq 9000 clear 0 act 8828 last 8960 busy 46\n'
GOOD = 'window 06840094 count 4 seq 60000 clear 0 act 53706 last 55597 busy 1148\n'
IDLE = 'window 06840094 count 4 seq 100 clear 0 act 0 last 0 busy 0\n'


class Event(Pulse):
    """hpd-event-v1: pulse on the failed-EDID-read signature, schedule as backstop."""
    def setUp(self):
        super().setUp()
        (self.params.parent / 'version').write_text('hpd-event-v1\n')
        self.scan = self.params / 'ddc_scan'
        self.scan.write_text(IDLE)
        self.ddc = {}                      # time -> header text
        self.after_pulse = None            # header written 0.5 s after each pulse
        self.order = []
        inner = Path.write_text
        def spy(path, data, *a, **k):
            if path.name in ('ddc_scan', 'hpd_pulse'):
                self.order.append((round(self.time, 2), path.name, data))
            if path.name == 'hpd_pulse' and self.after_pulse:
                self.ddc[round(self.time + 0.65, 3)] = self.after_pulse
            return inner(path, data, *a, **k)
        p = patch.object(Path, 'write_text', spy)
        p.start()
        self.addCleanup(p.stop)
        base_sleep = self.sleep
        def sleep(seconds):
            before = self.time
            base_sleep(seconds)
            for t, text in sorted(self.ddc.items()):
                if before < t <= self.time:
                    self.scan.write_text(text)
        self.sleep = sleep

    # Logging-only and production-owner tests do not describe the event owner.
    test_activity_owner_logs_and_rearms_before_each_pulse = None
    test_production_owner_never_touches_the_scan = None

    def run_for(self, seconds):          # inherited timer tests, now under the event owner
        with redirect_stdout(io.StringIO()):
            return m.main(lambda: self.time, self.sleep, polls=int(seconds / m.EVENT_POLL), power=self.power)

    def run_events(self, seconds):
        with redirect_stdout(io.StringIO()) as out:
            m.main(lambda: self.time, self.sleep, polls=int(seconds / m.EVENT_POLL), power=self.power)
        return out.getvalue()

    def test_failed_read_pulses_within_a_quarter_second_after_rearming(self):
        self.ddc = {0.5: FAILED}
        out = self.run_events(6)
        self.assertEqual(len(self.pulses), 1)
        self.assertGreaterEqual(self.pulses[0][0], 0.5 + m.FAILED_READ_QUIET)
        self.assertLess(self.pulses[0][0], 0.5 + m.FAILED_READ_QUIET + 2 * m.EVENT_POLL + 0.01)
        names = [n for _, n, _ in self.order]
        self.assertEqual(names[names.index('hpd_pulse') - 1], 'ddc_scan')   # re-armed first
        self.assertIn('failed EDID read (busy 46 passes)', out)
        self.assertIn('"phase": "failed_read"', out)

    def test_a_real_read_never_triggers_the_event(self):
        self.respond = False
        self.ddc = {0.5: GOOD}
        self.run_events(5)
        self.assertGreaterEqual(self.pulses[0][0], m.PULSE_FIRST)

    def test_a_burst_still_running_waits_for_quiet(self):
        self.ddc = {0.5 + 0.1 * i: FAILED.replace('last 8960', f'last {8960 + i}') for i in range(6)}
        self.run_events(6)
        self.assertGreaterEqual(self.pulses[0][0], 1.0 + m.FAILED_READ_QUIET)

    def test_event_pulses_are_capped_spaced_then_the_schedule_takes_over(self):
        self.respond = False
        self.ddc = {0.5: FAILED}
        self.after_pulse = FAILED
        self.run_events(30)
        times = [t for t, _ in self.pulses]
        self.assertGreaterEqual(times[1] - times[0], m.EVENT_GAP)
        self.assertGreaterEqual(times[2] - times[1], m.SCHEDULE[0] - 0.01)     # backstop (schedule step 2), not a third event
        self.assertEqual(len(times), 3)

    def test_no_event_while_a_source_is_acquiring(self):
        self.signal.write_text('acquiring')
        self.ddc = {0.5: FAILED}
        self.run_events(6)
        self.assertEqual(self.pulses, [])

    def test_a_lost_source_rearms_so_its_failed_return_read_pulses_at_once(self):
        self.signal.write_text('locked 1280x720')
        self.scan.write_text(GOOD)                       # the earlier, successful read
        self.respond = False
        self.script = {5: 'none'}
        self.ddc = {6.0: FAILED}                         # the returning source fails its read
        out = self.run_events(12)
        self.assertIn('"phase": "source_lost"', out)
        rearm = [t for t, n, d in self.order if n == 'ddc_scan' and d == m.ACTIVITY_WINDOW + '\n']
        self.assertTrue(rearm and 5 <= rearm[0] < 5.3, rearm)
        self.assertEqual(len(self.pulses), 1)
        self.assertGreaterEqual(self.pulses[0][0], 6.0 + m.FAILED_READ_QUIET)
        self.assertLess(self.pulses[0][0], 6.5)          # not the 10 s lost-source step

    def test_returning_power_rearms_the_watch(self):
        self.power.value = False
        self.power_script = {3: True}
        out = self.run_events(4)
        self.assertIn('"phase": "source_power_returned"', out)

    def test_owner_without_the_event_version_keeps_the_timer(self):
        (self.params.parent / 'version').write_text('hpd-pulse-v1\n')
        self.respond = False
        self.ddc = {0.5: FAILED}
        self.run_events(5)
        self.assertGreaterEqual(self.pulses[0][0], m.PULSE_FIRST)
        self.assertNotIn(m.ACTIVITY_WINDOW + '\n', [d for _, n, d in self.order if n == 'ddc_scan'])   # never re-armed


if __name__ == '__main__':
    unittest.main()
