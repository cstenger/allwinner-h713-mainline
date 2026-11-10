#!/usr/bin/env python3
"""Exercise the real IPC transaction with simulated rings; no /dev/mem access."""
import contextlib
import fcntl
import importlib.util
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('shell', Path(__file__).with_name('mips-shell.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
REPLY = b'help win\r\r\ncommand help of win\r\r\nfor window debug only\r\r\n\r\r\nVS:/$ '


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now = round(self.now + seconds, 9)


class Terminal:
    def __init__(self, clock, chunks=None, stale=b'', consume_at=0.01):
        self.clock = clock
        self.chunks = list(chunks if chunks is not None else [(0.02, REPLY)])
        self.stale = stale
        self.consume_at = consume_at
        self.down = [SimpleNamespace(wroff=0, rdoff=0)]
        self.sent = []
        self.mem = None
    def send(self, command):
        self.sent.append(command)
        self.down[0].wroff = 9
        return 9
    def drain(self):
        if not self.sent:
            stale, self.stale = self.stale, b''
            return stale
        if self.clock() >= self.consume_at:
            self.down[0].rdoff = self.down[0].wroff
        data = b''
        while self.chunks and self.chunks[0][0] <= self.clock():
            data += self.chunks.pop(0)[1]
        return data


class Completion(unittest.TestCase):
    def transaction(self, term, alive=True, timeout=0.1):
        return m.check_ipc(term, alive, timeout, clock=term.clock, sleep=term.clock.sleep)
    def test_recorded_reply_matches_and_returns_early(self):
        root = Path(__file__).resolve().parents[2]
        record = (root/'docs/hdmi-evidence/2026-10-14-receiver-owner/missing-owner.log').read_bytes()
        recorded = record.split(b'[reply: 66 bytes]\n')[1][:-1]
        self.assertEqual(recorded, REPLY)
        clock = Clock(); term = Terminal(clock)
        result = self.transaction(term)
        self.assertTrue(result['complete'])
        self.assertEqual(result['command'], 'help win')
        self.assertEqual(result['reply_bytes'], 66)
        self.assertEqual(term.sent, ['help win\r'])
        self.assertLess(clock(), 0.1)
    def test_every_split_of_reply_is_supported(self):
        for split in range(1, len(REPLY)):
            clock = Clock(); term = Terminal(clock, [(0.01, REPLY[:split]), (0.04, REPLY[split:])])
            result = self.transaction(term)
            self.assertGreaterEqual(result['elapsed_seconds'], 0.04)
    def test_stale_reply_is_discarded_and_cannot_supply_completion(self):
        for fresh in (b'', b'VS:/$ ', REPLY[:20]):
            clock = Clock(); term = Terminal(clock, [(0.01, fresh)], stale=REPLY)
            with self.assertRaisesRegex(RuntimeError, 'deadline'): self.transaction(term)
        clock = Clock(); term = Terminal(clock, stale=REPLY)
        self.assertEqual(self.transaction(term)['stale_bytes'], len(REPLY))
    def test_prompt_echo_partial_and_wrong_body_do_not_pass(self):
        for data in (b'VS:/$ ', b'help win\r\nVS:/$ ', REPLY[:-1],
                     REPLY.replace(b'for window debug only', b'unknown command'),
                     b'noise'+REPLY):
            clock = Clock(); term = Terminal(clock, [(0.01, data)])
            with self.subTest(data=data), self.assertRaisesRegex(RuntimeError, 'deadline'):
                self.transaction(term)
    def test_parked_busy_and_invalid_deadline_never_send(self):
        clock = Clock(); term = Terminal(clock)
        with self.assertRaisesRegex(RuntimeError, 'parked'): self.transaction(term, alive=False)
        term.down[0].wroff = 1
        with self.assertRaisesRegex(RuntimeError, 'busy'): self.transaction(term)
        for timeout in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): self.transaction(term, timeout=timeout)
        self.assertEqual(term.sent, [])
    def test_full_reply_requires_command_consumption(self):
        clock = Clock(); term = Terminal(clock, consume_at=1)
        with self.assertRaisesRegex(RuntimeError, 'deadline'): self.transaction(term)
    def test_late_reply_times_out_without_retry(self):
        clock = Clock(); term = Terminal(clock, [(0.1, REPLY)])
        with self.assertRaisesRegex(RuntimeError, 'deadline'): self.transaction(term)
        self.assertEqual(term.sent, ['help win\r'])
        self.assertEqual(clock(), 0.1)
    def test_flood_and_short_publication_fail(self):
        clock = Clock(); term = Terminal(clock, [(0.01, b'x'*4097)])
        with self.assertRaisesRegex(RuntimeError, 'bounded'): self.transaction(term)
        clock = Clock(); term = Terminal(clock)
        with patch.object(term, 'send', return_value=8), self.assertRaisesRegex(RuntimeError, 'publication'):
            self.transaction(term)
    def test_cli_rejects_mixed_actions_before_terminal_access(self):
        for args in (['--status'], ['--drain'], ['--cmd', 'help win'], ['--release'],
                     ['--unbind'], ['--raw'], ['--wait', 'nan']):
            with patch('sys.argv', ['mips-shell.py', '--check-ipc', *args]), \
                 patch.object(m, 'Terminal') as terminal, contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit):
                m.main()
            terminal.assert_not_called()
    def test_cli_lock_contention_prevents_terminal_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'lock'
            with path.open('a') as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                with patch('sys.argv', ['mips-shell.py', '--check-ipc']), \
                     patch('builtins.open', side_effect=lambda *a: path.open('a')), \
                     patch.object(m, 'Terminal') as terminal, self.assertRaisesRegex(SystemExit, 'busy'):
                    m.main()
                terminal.assert_not_called()


if __name__ == '__main__': unittest.main()
