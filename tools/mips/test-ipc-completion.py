#!/usr/bin/env python3
"""Exercise the real IPC transaction with simulated rings; no /dev/mem access."""
import contextlib
import fcntl
import importlib.util
import io
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('shell', Path(__file__).with_name('mips-shell.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FIXTURE = Path(__file__).resolve().parents[2]/'docs/production-evidence/2026-11-09-startup-and-parallel-aic/cmds-reply.reply'
REPLY = FIXTURE.read_bytes()


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
        self.down[0].wroff = len(command)
        return len(command)
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
        self.assertEqual(hashlib.sha256(REPLY).hexdigest(),
                         'abff1a9772c00c9ef81e9f90ddad5844c0c5dd0ca48de4dab3d705fe3cb44b0e')
        clock = Clock(); term = Terminal(clock)
        result = self.transaction(term)
        self.assertTrue(result['complete'])
        self.assertEqual(result['command'], 'cmds')
        self.assertEqual(result['reply_bytes'], 917)
        self.assertEqual(term.sent, ['cmds\r'])
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
        for data in (b'VS:/$ ', b'cmds\r\nVS:/$ ', REPLY[:-1],
                     REPLY.replace(b'list all cmd', b'unknown command'),
                     b'noise'+REPLY):
            clock = Clock(); term = Terminal(clock, [(0.01, data)])
            with self.subTest(data=data), self.assertRaisesRegex(RuntimeError, 'deadline'):
                self.transaction(term)
    def test_every_command_row_is_pinned_and_legacy_reply_is_rejected(self):
        lines = REPLY.split(b'\r\r\n')
        rows = [i for i, line in enumerate(lines) if b'CMD ' in line]
        self.assertEqual(len(rows), 19)
        bad = [b'help win\r\r\ncommand help of win\r\r\nfor window debug only\r\r\n\r\r\nVS:/$ ']
        for i in rows:
            changed = lines.copy(); changed[i] += b' changed'
            bad.append(b'\r\r\n'.join(changed))
            bad.append(b'\r\r\n'.join(lines[:i]+lines[i+1:]))
        bad.append(REPLY+REPLY)
        for reply in bad:
            clock = Clock(); term = Terminal(clock, [(0.01, reply)])
            with self.subTest(reply=reply), self.assertRaisesRegex(RuntimeError, 'deadline'):
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
        self.assertEqual(term.sent, ['cmds\r'])
        self.assertEqual(clock(), 0.1)
    def test_flood_and_short_publication_fail(self):
        clock = Clock(); term = Terminal(clock, [(0.01, b'x'*4097)])
        with self.assertRaisesRegex(RuntimeError, 'bounded'): self.transaction(term)
        clock = Clock(); term = Terminal(clock)
        with patch.object(term, 'send', return_value=4), self.assertRaisesRegex(RuntimeError, 'publication'):
            self.transaction(term)
    def test_cli_rejects_mixed_actions_before_terminal_access(self):
        for args in (['--status'], ['--drain'], ['--cmd', 'cmds'], ['--release'],
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


ELOG_REPLY = b'elog -l 2\r\r\n\r\r\nVS:/$ '


class Mem:
    """Pinned handler words plus a filter word whose update can lag the reply."""
    def __init__(self, clock, before=5, takes_effect_at=0.3, level=2):
        self.clock = clock; self.before = before; self.at = takes_effect_at; self.level = level
        self.words = dict(m.ELOG_HANDLER_WORDS)
    def u32(self, address):
        if address == m.ELOG_LEVEL_WORD:
            low = self.level if self.at is not None and self.clock() >= self.at else self.before
            return 0x00000100 | low
        return self.words[address]


class ElogLevel(unittest.TestCase):
    def run_set(self, term, alive=True, level=2, timeout=0.5, settle=1.0):
        return m.set_elog_level(term, alive, level, timeout, settle, clock=term.clock, sleep=term.clock.sleep)
    def term(self, chunks=None, **mem):
        clock = Clock()
        t = Terminal(clock, chunks if chunks is not None else [(0.06, ELOG_REPLY)])
        t.mem = Mem(clock, **mem)
        return t
    def test_native_command_and_lagging_readback_verify(self):
        t = self.term()
        r = self.run_set(t)
        self.assertEqual(t.sent, ['elog -l 2\r'])
        self.assertEqual((r['schema'], r['level'], r['before'], r['verified'], r['reply_bytes']),
                         ('h713-mips-elog-v1', 2, 5, True, 21))
        self.assertGreaterEqual(r['elapsed_seconds'], 0.3)
    def test_every_split_of_reply_is_supported(self):
        for split in range(1, len(ELOG_REPLY)):
            t = self.term([(0.01, ELOG_REPLY[:split]), (0.05, ELOG_REPLY[split:])])
            self.assertTrue(self.run_set(t)['verified'])
    def test_stale_partial_wrong_and_unconsumed_replies_fail(self):
        for fresh in ([(0.01, b'VS:/$ ')], []):     # a stale reply alone never completes
            clock = Clock(); t = Terminal(clock, fresh, stale=ELOG_REPLY); t.mem = Mem(clock)
            with self.subTest(fresh=fresh), self.assertRaisesRegex(RuntimeError, 'deadline'): self.run_set(t)
        for data in (ELOG_REPLY[:-1], ELOG_REPLY.replace(b'2', b'3', 1), b'noise' + ELOG_REPLY,
                     b'elog -l 2\r\r\nunknown\r\r\nVS:/$ '):
            with self.subTest(data=data), self.assertRaisesRegex(RuntimeError, 'deadline'):
                self.run_set(self.term([(0.01, data)]))
        clock = Clock(); t = Terminal(clock, [(0.01, ELOG_REPLY)], consume_at=9); t.mem = Mem(clock)
        with self.assertRaisesRegex(RuntimeError, 'deadline'): self.run_set(t)
    def test_filter_that_never_changes_is_not_verified(self):
        t = self.term(takes_effect_at=None)
        with self.assertRaisesRegex(RuntimeError, 'not verified'): self.run_set(t)
        self.assertEqual(t.sent, ['elog -l 2\r'])

    # 2026-11-18 no-source boot: the reply arrived, but the idle firmware left
    # the new value unwritten until a source locked minutes later.
    def run_sourced(self, t, source_at, settle=5.0, grace=60.0):
        active = lambda: source_at is not None and t.clock() >= source_at
        with contextlib.redirect_stderr(io.StringIO()):
            return m.set_elog_level(t, True, 2, 0.5, settle, clock=t.clock, sleep=t.clock.sleep,
                                    source_active=active, grace=grace)
    def test_stale_readback_without_a_source_waits_for_one(self):
        t = self.term(takes_effect_at=471.0)          # value lands once activity resumes
        r = self.run_sourced(t, source_at=470.0)
        self.assertTrue(r['verified']); self.assertTrue(r['waited_for_source'])
        self.assertGreaterEqual(r['elapsed_seconds'], 471.0)
        self.assertEqual(t.sent, ['elog -l 2\r'])     # never re-sent
    def test_no_source_never_fails_on_a_clock(self):
        t = self.term(takes_effect_at=None)
        with self.assertRaisesRegex(RuntimeError, 'not verified'):
            self.run_sourced(t, source_at=3600.0)
        self.assertGreaterEqual(t.clock(), 3600.0 + 60.0)   # only after a source and its grace
        self.assertLess(t.clock(), 3600.0 + 60.0 + 6.0)
    def test_wrong_level_with_a_source_present_still_fails(self):
        t = self.term(takes_effect_at=None)
        with self.assertRaisesRegex(RuntimeError, 'not verified'):
            self.run_sourced(t, source_at=0.0)
        self.assertLess(t.clock(), 60.0 + 1.0)
    def test_normal_boot_with_a_source_verifies_quickly(self):
        t = self.term()                               # word changes at 0.3 s
        r = self.run_sourced(t, source_at=0.0)
        self.assertTrue(r['verified']); self.assertFalse(r['waited_for_source'])
        self.assertLess(r['elapsed_seconds'], 1.0)
    def test_cli_releases_the_ring_lock_before_confirming(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'lock'; seen = {}
            def confirm(mem, sent, **kw):
                with path.open('a') as other:          # another ring user must get the lock now
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB); seen['free'] = True
                seen['source'] = kw['source_active']
                return {'verified': True}
            with patch('sys.argv', ['mips-shell.py', '--elog-level', '2']), \
                 patch('builtins.open', side_effect=lambda *a: path.open('a')), \
                 patch.object(m, 'Terminal'), patch.object(m, 'mips_alive', return_value=True), \
                 patch.object(m, 'send_elog_level', return_value={'level': 2}) as send, \
                 patch.object(m, 'confirm_elog_level', side_effect=confirm), \
                 contextlib.redirect_stdout(io.StringIO()):
                m.main()
            send.assert_called_once()
            self.assertTrue(seen['free']); self.assertIs(seen['source'], m.hdmi_source_active)
    def test_source_state_reads_the_ring_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'signal'
            for text, active in (('none\n', False), ('locked 1280x720\n', True),
                                 ('acquiring\n', True), ('', False)):
                path.write_text(text)
                with self.subTest(text=text): self.assertIs(m.hdmi_source_active(str(path)), active)
            self.assertFalse(m.hdmi_source_active(str(path) + '.missing'))
    def test_wrong_firmware_parked_busy_bad_filter_and_arguments_never_send(self):
        t = self.term(); t.mem.words[m.ELOG_HANDLER_WORDS[1][0]] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'pinned firmware'): self.run_set(t)
        t = self.term(before=0x41)
        with self.assertRaisesRegex(RuntimeError, 'outside'): self.run_set(t)
        t = self.term()
        with self.assertRaisesRegex(RuntimeError, 'parked'): self.run_set(t, alive=False)
        t.down[0].wroff = 1
        with self.assertRaisesRegex(RuntimeError, 'busy'): self.run_set(t)
        t.down[0].wroff = 0
        for level in (-1, 8, 2.0, True, '2'):
            with self.subTest(level=level), self.assertRaises(ValueError): self.run_set(t, level=level)
        for timeout in (0, float('nan'), float('inf')):
            with self.assertRaises(ValueError): self.run_set(t, timeout=timeout)
        self.assertEqual(t.sent, [])
    def test_cli_rejects_mixed_elog_actions_before_terminal_access(self):
        for args in (['--check-ipc'], ['--status'], ['--cmd', 'cmds'], ['--release'], ['--lock-wait', '500']):
            with patch('sys.argv', ['mips-shell.py', '--elog-level', '2', *args]), \
                 patch.object(m, 'Terminal') as terminal, contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit):
                m.main()
            terminal.assert_not_called()
    def test_cli_waits_for_the_lock_then_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'lock'
            with path.open('a') as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                with patch('sys.argv', ['mips-shell.py', '--elog-level', '2', '--lock-wait', '0.3']), \
                     patch('builtins.open', side_effect=lambda *a: path.open('a')), \
                     patch.object(m, 'Terminal') as terminal, self.assertRaisesRegex(SystemExit, 'busy'):
                    m.main()
                terminal.assert_not_called()


if __name__ == '__main__': unittest.main()
