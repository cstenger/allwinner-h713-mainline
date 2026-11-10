#!/usr/bin/env python3
"""Exercise passive recorder reconnection and failures with a fake UART."""
import errno
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('capture', Path(__file__).with_name('capture-panel-validation.py'))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class Recorder(unittest.TestCase):
    def run_fake(self, output, chunks, setup_error=False):
        stop = threading.Event()
        iterator = iter(chunks)

        def read(fd, count):
            chunk = next(iterator)
            if isinstance(chunk, Exception):
                raise chunk
            if chunk == b'last':
                stop.set()
            return chunk

        attrs = [0, 0, 0, 0, 0, 0, [0] * 32]
        with mock.patch.object(capture.os, 'open', side_effect=[41, 42]) as opened, \
                mock.patch.object(capture.os, 'read', side_effect=read), \
                mock.patch.object(capture.os, 'write') as sent, \
                mock.patch.object(capture.os, 'close') as closed, \
                mock.patch.object(capture.termios, 'tcgetattr', return_value=attrs), \
                mock.patch.object(capture.termios, 'tcsetattr',
                                  side_effect=[OSError(errno.EIO, 'setup lost'), None] if setup_error else None), \
                mock.patch.object(capture.select, 'select', side_effect=lambda fds, *args: (fds, [], [])), \
                mock.patch.object(stop, 'wait', return_value=False):
            try:
                capture.record('/fake/uart', output, stop)
            finally:
                self.last_closed = [call.args[0] for call in closed.call_args_list]
        sent.assert_not_called()
        for call in opened.call_args_list:
            self.assertEqual(call.args[0], '/fake/uart')
            self.assertEqual(call.args[1], capture.os.O_RDONLY | capture.os.O_NOCTTY | capture.os.O_NONBLOCK)
        return opened.call_count, [call.args[0] for call in closed.call_args_list]

    def test_disconnect_reconnect_preserves_raw_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'new'
            opened, closed = self.run_fake(output, [b'first\x00\r\n', OSError(errno.EIO, 'gone'), b'last'])
            self.assertEqual((opened, closed), (2, [41, 42]))
            self.assertEqual((output / 'serial.log').read_bytes(), b'first\x00\r\nlast')
            text = (output / 'serial-timestamped.log').read_text()
            self.assertIn('DISCONNECTED', text)
            self.assertIn('CAPTURE STOP', text)

    def test_eof_and_would_block(self):
        with tempfile.TemporaryDirectory() as d:
            opened, closed = self.run_fake(Path(d) / 'new', [BlockingIOError(), b'', b'last'])
            self.assertEqual((opened, closed), (2, [41, 42]))

    def test_failed_serial_configuration_closes_before_reconnect(self):
        with tempfile.TemporaryDirectory() as d:
            opened, closed = self.run_fake(Path(d) / 'new', [b'last'], setup_error=True)
            self.assertEqual((opened, closed), (2, [41, 42]))

    def test_existing_output_refused_before_uart_open(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(capture.os, 'open') as opened:
            with self.assertRaises(FileExistsError):
                capture.record('/fake/uart', Path(d), threading.Event())
            opened.assert_not_called()

    def test_output_failure_and_short_write_are_fatal_and_close_uart(self):
        for failure in ('full', 'short'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                original_open = Path.open
                broken = mock.MagicMock()
                broken.__enter__.return_value = broken
                if failure == 'full':
                    broken.write.side_effect = OSError(errno.ENOSPC, 'disk full')
                else:
                    broken.write.return_value = 1

                def open_path(path, *args, **kwargs):
                    if path.name == 'serial.log':
                        return broken
                    return original_open(path, *args, **kwargs)

                with mock.patch.object(Path, 'open', open_path), self.assertRaises(OSError) as exc:
                    self.run_fake(Path(d) / 'new', [b'last'])
                self.assertEqual(exc.exception.errno, errno.ENOSPC if failure == 'full' else errno.EIO)
                self.assertEqual(self.last_closed, [41])
                broken.__exit__.assert_called_once()


if __name__ == '__main__':
    unittest.main()
