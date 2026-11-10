#!/usr/bin/env python3
"""Check when the re-advertise service asks the signal owner for an HPD cycle."""
import importlib.util
import io
import errno
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('readvertise', Path(__file__).with_name('h713-hdmi-readvertise.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Readvertise(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        m.SIGNAL, m.PARAMS = root / 'signal', root / 'parameters'
        m.PARAMS.mkdir()
        (m.PARAMS / 'ready').write_text('Y\n')
        (m.PARAMS / 'failed').write_text('N\n')
        (m.PARAMS / 'readvertise').write_text('')
        m.SIGNAL.write_text('none\n')
        self.now, self.requests, self.script = 0.0, [], {}

    def sleep(self, seconds):
        # Record a request the moment the owner receives one, then advance time.
        written = (m.PARAMS / 'readvertise').read_text()
        if written:
            self.requests.append((self.now, written.strip()))
            (m.PARAMS / 'readvertise').write_text('')
        self.now += seconds
        if int(self.now) in self.script:
            m.SIGNAL.write_text(self.script[int(self.now)])

    def run_for(self, seconds):
        with redirect_stdout(io.StringIO()):
            return m.main(clock=lambda: self.now, sleep=self.sleep, polls=seconds)

    def test_no_source_follows_the_schedule_then_stops(self):
        self.run_for(1000)
        self.assertEqual([t for t, _ in self.requests], [10, 30, 70, 150, 310])
        self.assertTrue(all(value == str(m.HOLD_MS) for _, value in self.requests))

    def test_a_sending_source_is_never_pulsed(self):
        for state in ('locked 1280x720\n', 'acquiring\n', 'hold 1280x720\n', 'unsupported 640x480\n'):
            with self.subTest(state=state):
                self.requests = []
                m.SIGNAL.write_text(state)
                self.run_for(400)
                self.assertEqual(self.requests, [])

    def test_a_lost_source_restarts_the_schedule(self):
        m.SIGNAL.write_text('locked 1280x720\n')
        self.script = {100: 'none\n'}
        self.run_for(300)
        self.assertEqual([t for t, _ in self.requests], [110, 130, 170, 250])

    def test_lock_after_a_request_stops_further_requests(self):
        self.script = {12: 'locked 1280x720\n'}
        self.run_for(400)
        self.assertEqual([t for t, _ in self.requests], [10])

    def test_a_lock_resets_the_schedule_for_the_next_loss(self):
        self.script = {12: 'locked 1280x720\n', 100: 'none\n'}
        self.run_for(200)
        self.assertEqual([t for t, _ in self.requests], [10, 110, 130, 170])

    def test_failed_or_unready_owner_gets_no_request(self):
        for name, value in (('failed', 'Y\n'), ('ready', 'N\n')):
            with self.subTest(name=name):
                self.setUp()
                (m.PARAMS / name).write_text(value)
                self.run_for(400)
                self.assertEqual(self.requests, [])

    def test_unreadable_signal_acts_on_nothing(self):
        m.SIGNAL.unlink()
        self.run_for(400)
        self.assertEqual(self.requests, [])

    def test_owner_without_the_request_is_left_alone(self):
        (m.PARAMS / 'readvertise').unlink()
        self.assertEqual(self.run_for(400), 0)

    def test_a_refused_request_stops_the_service(self):
        (m.PARAMS / 'readvertise').unlink()
        (m.PARAMS / 'readvertise').mkdir()  # writes fail like an EPERM from the owner
        orig = m.PARAMS / 'readvertise'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(clock=lambda: self.now, sleep=lambda s: setattr(self, 'now', self.now + s), polls=60), 1)
        self.assertTrue(orig.is_dir())

    def power(self, sample):
        test = self
        class FakePower:
            def read(self):
                return sample(test.now)
            def wait(self, seconds, sleep):
                sleep(seconds)
            def close(self):
                self.closed = True
        return FakePower()

    def test_known_absent_never_pulses(self):
        power = self.power(lambda now: False)
        m.main(clock=lambda: self.now, sleep=self.sleep, polls=400, power=power)
        self.assertEqual(self.requests, [])
        self.assertTrue(power.closed)

    def test_reconnect_starts_a_full_wait(self):
        power = self.power(lambda now: now >= 100)
        m.main(clock=lambda: self.now, sleep=self.sleep, polls=200, power=power)
        self.assertEqual([t for t, _ in self.requests], [110, 130, 170])

    def test_disconnect_resets_an_exhausted_schedule(self):
        power = self.power(lambda now: not 320 <= now < 400)
        m.main(clock=lambda: self.now, sleep=self.sleep, polls=440, power=power)
        self.assertEqual([t for t, _ in self.requests], [10, 30, 70, 150, 310, 410, 430])

    def test_unknown_after_absent_preserves_timeout_fallback(self):
        power = self.power(lambda now: False if now < 100 else None)
        m.main(clock=lambda: self.now, sleep=self.sleep, polls=180, power=power)
        self.assertEqual([t for t, _ in self.requests], [109, 129, 169])

    def test_reconnect_does_not_pulse_acquiring_video(self):
        m.SIGNAL.write_text('acquiring\n')
        power = self.power(lambda now: now >= 100)
        m.main(clock=lambda: self.now, sleep=self.sleep, polls=400, power=power)
        self.assertEqual(self.requests, [])

    def test_absent_at_final_recheck_prevents_request(self):
        reads = [True] * 11 + [False] * 100
        power = self.power(lambda now: reads.pop(0))
        m.main(clock=lambda: self.now, sleep=self.sleep, polls=40, power=power)
        self.assertEqual(self.requests, [])

    def test_native_empty_event_queue_keeps_power_status_available(self):
        for empty_errno in (errno.ENOENT, errno.EAGAIN):
            for value in (0, 1):
                calls = []
                def ioctl(fd, request, data, *args):
                    calls.append(request)
                    if request == m.DQEVENT:
                        raise OSError(empty_errno, 'empty event queue')
                    if request == m.QUERYCTRL:
                        data[:] = struct.pack('=II32siiiiIII', m.POWER_ID, 8, b'Power Present', 0, 1, 0, 0, 4, 0, 0)
                    if request == m.G_CTRL:
                        data[:] = struct.pack('=Ii', m.POWER_ID, value)
                monitor = m.PowerEvents()
                with self.subTest(errno=empty_errno, value=value), patch.object(m.os, 'open', return_value=42), patch.object(m.os, 'close') as close, patch.object(m.fcntl, 'ioctl', ioctl):
                    self.assertIs(monitor.read(), bool(value))
                    self.assertEqual(monitor.fd, 42)
                    close.assert_not_called()
                    self.assertEqual(calls, [m.SUBSCRIBE_EVENT, m.SUBSCRIBE_EVENT, m.DQEVENT, m.QUERYCTRL, m.G_CTRL, m.QUERYCTRL])
                    monitor.close()


if __name__ == '__main__':
    unittest.main()
