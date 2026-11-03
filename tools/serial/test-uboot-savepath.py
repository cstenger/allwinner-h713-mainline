#!/usr/bin/env python3
"""Offline UART state/transport tests. Only synthetic peers and Linux PTYs."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
P = argparse.ArgumentParser(description=__doc__)
P.add_argument('--packet', type=Path, required=True)
P.add_argument('--capture', type=Path, required=True)
P.add_argument('--controller', type=Path, default=Path(__file__).with_name('uboot-savepath.py'))
P.add_argument('--mutations', action='store_true')
P.add_argument('--no-pty', action='store_true')
A = P.parse_args()
spec = importlib.util.spec_from_file_location('uart', A.controller)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
M, BEFORE = u.load_packet(A.packet)
BASE = u.env.decode(BEFORE)
NONCE = M['nonce'].encode()

# Independent wire fixtures taken from the pinned source printf formats, not
# controller constants. Never open an actual serial port or contact the board.
BOOT = (b'U-Boot SPL 2026.07-rc5-g7b178056c329-dirty (Aug 25 2026 - 20:13:26 -0700)\r\n'
        b'U-Boot 2026.07-rc5-g320a17f71d41-h713-b3b5f2d2 (Oct 30 2026 - 02:09:43 -0700) Allwinner Technology\r\n'
        b'Loading Environment from MMC... Reading from MMC(1) at 0x93d80000... OK\r\n'
        b'Hit any key to stop autoboot:  5')
INFO = b'Device: mmc@4022000\nManufacturer ID: 15\nOEM: 0\nName: 8GTF4R\nRd Block Len: 512\nMMC version 5.1\nHigh Capacity: Yes\nCapacity: 7.3 GiB\n'
LINUX = (b'run bootcmd\r\nH713 HDMI shared startup handoff verified\r\n'
         b'Starting kernel ...\r\nh713-arm64 login: root (automatic login)\r\n')


def listing(values):
    data = b'\n'.join(k+b'='+v.replace(b'\\', b'\\\\') for k, v in sorted(values.items()))
    return data+b'\n\nEnvironment size: 12345/65532 bytes'


class Peer:
    def __init__(self, phase='probe'):
        self.values = dict(BASE)
        self.values[b'fdtcontroladdr'] = b'7bd12340'
        if phase == 'cleanup':
            self.values[u.env.PROBE] = NONCE
        self.current = BEFORE if phase == 'probe' else u.env.encode(self.values)
        self.saved = None
        self.writes = 0

    def body(self, command):
        if command == 'gpio set PB5': return b'gpio: pin PB5 (gpio 37) value is 1'
        if command == 'version': return BOOT.split(b'\r\n')[1]+b'\nDRAM:  2 GiB'
        if command == 'mmc dev 1 0': return b'switch to partitions #0, OK\nmmc1(part 0) is current device'
        if command == 'mmc info': return INFO.rstrip(b'\n')
        if command == 'env print -a': return listing(self.values)
        if command.startswith('env set '):
            key, value = command[len('env set '):].split(' ', 1)
            self.values[key.encode()] = value.encode()
            return b''
        if command == 'env delete h713_savepath_probe':
            del self.values[u.env.PROBE]
            return b''
        if command == 'env save':
            self.saved = u.env.encode(self.values)
            self.current = self.saved
            self.writes += 1
            return b'Saving Environment to MMC... Writing to MMC(1)... OK'
        if command.startswith('mmc read '):
            _, _, address, lba, count = command.split()
            assert count == '0x80'
            assert (address, lba) in [('0x42000000', '0x49ec00'), ('0x43000000', '0x32ec00')]
            return f'MMC read: dev # 1, block # {int(lba,16)}, count 128 ... 128 blocks read: OK'.encode()
        if command.startswith('crc32 '):
            _, address, size = command.split()
            assert size == '0x10000'
            addr = int(address, 16)
            crc = zlib.crc32(BEFORE if addr == 0x43000000 else self.current)
            return f'crc32 for {addr:08x} ... {addr+65535:08x} ==> {crc:08x}'.encode()
        raise AssertionError('unexpected command '+command)

    def reply(self, wire, alter=None):
        assert wire.startswith(b'if ') and wire.endswith(b'; fi\r')
        command = wire[3:].split(b'; then echo ', 1)[0].decode()
        ok = wire.split(b'; then echo ', 1)[1].split(b';', 1)[0]
        body = self.body(command)
        response = wire[:-1]+b'\n'+body+(b'\n' if body else b'')+ok+b'\n=> '
        return alter(command, response) if alter else response


def run(phase='probe', alter=None, values=None, chunk=65536, stop_gate=None):
    peer = Peer(phase)
    if values: peer.values.update(values)
    c = u.Controller(M, BEFORE, peer.current, phase)
    def feed(data):
        for offset in range(0, len(data), chunk): c.feed(data[offset:offset+chunk], 1)
    feed(BOOT)
    assert c.tx.pop(0) == b' '
    feed(b'\r\n=> ')
    while c.tx:
        if stop_gate and c.kind == stop_gate: break
        wire = c.tx.pop(0)
        if wire == b'run bootcmd\r': feed(LINUX)
        else: feed(peer.reply(wire, alter))
    return c, peer


class Tests(unittest.TestCase):
    def test_real_countdown_repaint(self):
        c = u.Controller(M, BEFORE, BEFORE, 'probe')
        c.feed(BOOT, 0)
        self.assertEqual(c.tx.pop(0), b' ')
        for byte in b'\x1b[2K\rHit any key to stop autoboot: 0\r\n=> ':
            c.feed(bytes([byte]), 1)
        self.assertEqual(c.kind, 'fan')
        self.assertEqual(c.saves, 0)

    def test_interrupt_rejects_other_output(self):
        for extra in [b'unknown', b'\x1b[2J', b'env save', b'Hit any key to stop autoboot: => ']:
            c = u.Controller(M, BEFORE, BEFORE, 'probe')
            c.feed(BOOT, 0)
            c.tx.pop(0)
            with self.assertRaises(ValueError):
                c.feed(extra+b'\n=> ', 1)
            self.assertEqual(c.saves, 0)
            self.assertEqual(c.tx, [])

    def test_sealed_inventory_count(self):
        # The November 2 owner update adds exactly two installed files.
        # A count mismatch must still refuse the packet before UART opens.
        import shutil
        with tempfile.TemporaryDirectory() as td:
            packet = Path(td)/'packet'
            shutil.copytree(A.packet, packet)
            manifest = json.loads((packet/'manifest.json').read_text())
            manifest['installed_file_count'] = 52 if len(M['_file_pins']) == 50 else 50
            (packet/'manifest.json').write_text(json.dumps(manifest))
            ledger = []
            for line in (packet/'SHA256SUMS').read_text().splitlines():
                _, name = line.split('  ', 1)
                ledger.append(u.digest((packet/name).read_bytes())+'  '+name+'\n')
            (packet/'SHA256SUMS').write_text(''.join(ledger))
            with self.assertRaisesRegex(ValueError, 'incomplete installed file inventory'):
                u.load_packet(packet)

    def test_probe(self):
        c, p = run()
        self.assertEqual(c.state, 'done')
        self.assertEqual(p.writes, 1)
        self.assertEqual(c.saves, 1)
        u.env.check(BEFORE, p.saved, 'probe', M['nonce'], c.ram)

    def test_cleanup_reload(self):
        c, p = run('cleanup')
        self.assertEqual(c.state, 'done')
        self.assertNotIn(u.env.PROBE, u.env.decode(p.saved))
        u.env.check(BEFORE, p.saved, 'cleanup', M['nonce'], c.ram)

    def test_fragment_every_byte(self):
        c, _ = run(chunk=1)
        self.assertEqual(c.state, 'done')

    def test_fragment_arbitrary(self):
        for n in [2, 7, 31, 4096]:
            self.assertEqual(run(chunk=n)[0].state, 'done')

    def test_literal_backslashes(self):
        self.assertEqual(u.ram_map(listing({b'example': b'a\\b\\\\c=1'})), {b'example': b'a\\b\\\\c=1'})

    def reject_boot(self, data):
        c = u.Controller(M, BEFORE, BEFORE, 'probe')
        with self.assertRaises(ValueError): c.feed(data, 0)
        self.assertEqual(c.tx, [])

    def test_wrong_build(self): self.reject_boot(BOOT.replace(b'h713-b3b5f2d2', b'h713-unknown0'))
    def test_wrong_spl(self): self.reject_boot(BOOT.replace(b'g7b178056c329', b'g123456789abc'))
    def test_wrong_address(self): self.reject_boot(BOOT.replace(b'0x93d80000', b'0x65d80000'))
    def test_bad_load(self): self.reject_boot(BOOT.replace(b'... OK', b'... bad CRC'))
    def test_repeated_boot(self): self.reject_boot(BOOT+BOOT)
    def test_prompt_without_countdown(self): self.reject_boot(b'\n=> ')
    def test_linux_instead(self): self.reject_boot(b'Starting kernel ...\nlogin:')
    def test_preempted_prompt(self): self.reject_boot(BOOT+b'\n=> ')

    def test_interrupt_missed(self):
        c = u.Controller(M, BEFORE, BEFORE, 'probe'); c.feed(BOOT, 0); c.tx.clear()
        with self.assertRaises(ValueError): c.feed(b'Starting kernel ...', 1)
        self.assertEqual(c.tx, [])

    def test_timeouts(self):
        for gate in [None, 'fan', 'ram', 'save']:
            c = u.Controller(M, BEFORE, BEFORE, 'probe') if gate is None else run(stop_gate=gate)[0]
            c.tx.clear()
            with self.assertRaises(ValueError): c.tick(181)
            self.assertEqual(c.tx, [])

    def test_total_prompt_timeout(self):
        c, _ = run(stop_gate='ram'); c.deadline = 500
        with self.assertRaises(ValueError): c.tick(122)

    def test_echo_corruption(self):
        with self.assertRaisesRegex(ValueError, 'echo'): run(alter=lambda cmd, reply: reply.replace(b'if gpio', b'if ggpio'))

    def test_gpio_wrong_or_warning(self):
        for changed in [b'value is 0', b'value is 1\n   Warning: value of pin is still 0']:
            with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'value is 1', changed))

    def test_missing_status(self):
        with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'_1_OK__\n', b'_1_MISSING__\n'))

    def test_failure_status(self):
        with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'_1_OK__\n', b'_1_FAIL__\n'))

    def test_wrong_device(self):
        with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'mmc1(part 0)', b'mmc0(part 0)'))

    def test_wrong_card(self):
        with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'Name: 8GTF4R', b'Name: WRONG!'))

    def test_short_read(self):
        with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'128 blocks read: OK', b'127 blocks read: ERROR'))

    def test_preimage_crc(self):
        with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'==> 4fcafa2c', b'==> 00000000'))

    def test_old_crc_after_save(self):
        calls = [0]
        def change(cmd, r):
            if cmd == 'crc32 0x43000000 0x10000':
                calls[0] += 1
                if calls[0] == 2: return r.replace(b'==> 4fcafa2c', b'==> 00000000')
            return r
        with self.assertRaises(ValueError): run(alter=change)

    def test_bootdelay_drift(self):
        with self.assertRaises(ValueError): run(values={b'bootdelay': b'-1'})

    def test_policy_drift(self):
        with self.assertRaises(ValueError): run(values={b'bootcmd': b'wrong'})

    def test_unknown_runtime_variable(self):
        with self.assertRaises(ValueError): run(values={b'filesize': b'10000'})

    def test_wrong_nonce(self):
        with self.assertRaises(ValueError): run('cleanup', values={u.env.PROBE: b'wrongnonce'})

    def test_probe_already_present(self):
        with self.assertRaises(ValueError): run(values={u.env.PROBE: NONCE})

    def test_cleanup_missing_nonce(self):
        peer = Peer('cleanup'); del peer.values[u.env.PROBE]
        with self.assertRaises(ValueError):
            u.env.check(BEFORE, u.env.encode(peer.values), 'cleanup', M['nonce'], peer.values)

    def test_duplicate_ram_entry(self):
        with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'Environment size:', b'bootdelay=5\nEnvironment size:'))

    def test_ram_changed_after_edit(self):
        calls = [0]
        def change(cmd, r):
            if cmd == 'env print -a':
                calls[0] += 1
                if calls[0] == 2: return r.replace(b'bootdelay=5', b'bootdelay=9')
            return r
        with self.assertRaises(ValueError): run(alter=change)

    def test_failed_native_save(self):
        for bad in [b'Writing to MMC(1)... failed\nFailed (1)', b'Writing to MMC(0)... OK']:
            with self.assertRaises(ValueError): run(alter=lambda cmd, r: r.replace(b'Writing to MMC(1)... OK', bad))

    def test_no_second_save(self):
        c, _ = run(stop_gate='edited'); c.saves = 1
        peer = Peer(); peer.values = dict(c.expected)
        with self.assertRaises(ValueError): c.feed(peer.reply(c.tx.pop()), 2)
        self.assertEqual(c.tx, [])

    def test_bootcmd_echo_corruption(self):
        c, _ = run()
        c.state, c.buffer, c.deadline = 'linux', b'', 180
        with self.assertRaises(ValueError): c.feed(LINUX.replace(b'run bootcmd', b'rrun bootcmd'), 2)

    def test_linux_panic_reset(self):
        for bad in [b'Kernel panic', b'U-Boot SPL ', b'\n=> ']:
            c, _ = run(); c.state, c.buffer, c.deadline = 'linux', b'run bootcmd\n', 180
            with self.assertRaises(ValueError): c.feed(bad, 2)

    def test_capture_baseline(self):
        _, current = u.read_capture(A.capture, M)
        self.assertEqual(current, BEFORE)

    def test_offline_default_never_opens_port(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'not-created'
            result = subprocess.run(['python3', str(A.controller), '--packet', str(A.packet),
                                     '--port', '/dev/THIS-MUST-NEVER-BE-OPENED', '--output', str(output)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['hardware_opened'])
            self.assertFalse(output.exists())

    def test_live_cleanup_without_probe_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'not-created'
            result = subprocess.run(['python3', str(A.controller), '--packet', str(A.packet),
                                     '--phase', 'cleanup', '--preflight', str(A.capture), '--execute-approved',
                                     '--port', '/dev/THIS-MUST-NEVER-BE-OPENED', '--output', str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'cleanup requires completed probe evidence', result.stderr)
            self.assertFalse(output.exists())

    def test_receipt_and_protected_faults(self):
        c, peer = run()
        with tarfile.open(A.capture) as t:
            files = {p.name: t.extractfile(p).read() for p in t.getmembers()}
        def capture(output, fault=None):
            import io
            data = dict(files); x = json.loads(data['inventory.json'])
            for owner in [x['identity'], x['session']]: owner['boot_id'] = '00000000-0000-4000-8000-000000000001'
            x['ending_boot_id'] = x['identity']['boot_id']
            name = 'intended-environment-surrounding-192KiB.bin'
            data[name] = data[name][:65536]+peer.saved+data[name][131072:]
            x['ranges'][name]['sha256'] = u.digest(data[name])
            if fault == 'protected':
                name = 'active-environment-64KiB.bin'; data[name] = b'X'+data[name][1:]
                x['ranges'][name]['sha256'] = u.digest(data[name])
            if fault == 'identity': x['identity']['cid'] = 'wrong'
            if fault == 'pins': x['files'] = {}
            if fault == 'latch': x['latches']['gp6_gp7_hex'] = '0000000000000000'
            if fault == 'same-boot':
                for owner in [x['identity'], x['session']]: owner['boot_id'] = c.preflight_boot_id
                x['ending_boot_id'] = c.preflight_boot_id
            data['inventory.json'] = json.dumps(x).encode()
            with tarfile.open(output, 'w') as t:
                for name, raw in data.items():
                    entry = tarfile.TarInfo(name); entry.size = len(raw); t.addfile(entry, io.BytesIO(raw))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'capture.tar'; capture(p)
            self.assertEqual(u.verify_phase(M, BEFORE, p, c.result())[1], peer.saved)
            result = c.result(); result['after_crc32'] = '00000000'
            with self.assertRaises(ValueError): u.verify_phase(M, BEFORE, p, result)
            result = c.result(); result['state'] = 'failed'
            with self.assertRaises(ValueError): u.verify_phase(M, BEFORE, p, result)
            for fault in ['protected', 'identity', 'pins', 'latch', 'same-boot']:
                capture(p, fault)
                with self.assertRaises(ValueError): u.verify_phase(M, BEFORE, p, c.result())

    @unittest.skipIf(A.no_pty, 'PTY transport excluded for mutation pass')
    def test_real_transport_pty(self):
        self.pty_session()

    @unittest.skipIf(A.no_pty, 'PTY transport excluded for mutation pass')
    def test_real_transport_failed_echo(self):
        self.pty_session(corrupt=True)

    @unittest.skipIf(A.no_pty, 'PTY transport excluded for mutation pass')
    def test_real_transport_cleanup(self):
        self.pty_session(phase='cleanup')

    @unittest.skipIf(A.no_pty, 'PTY transport excluded for mutation pass')
    def test_disconnect_during_save_no_retry(self):
        self.pty_session(disconnect=True)

    @unittest.skipIf(A.no_pty, 'PTY transport excluded for mutation pass')
    def test_existing_reader_rejected(self):
        master, slave = pty.openpty(); port = os.ttyname(slave); os.close(slave)
        child = subprocess.Popen(['python3', '-c',
                                  'import os,sys; f=os.open(sys.argv[1],os.O_RDWR|os.O_NOCTTY); print("READY",flush=True); sys.stdin.read()', port],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            self.assertEqual(child.stdout.readline(), b'READY\n')
            with tempfile.TemporaryDirectory() as td:
                output = Path(td)/'run'; c = u.Controller(M, BEFORE, BEFORE, 'probe')
                with self.assertRaisesRegex(ValueError, 'owners'): u.live(port, output, c)
                self.assertEqual(c.saves, 0)
                self.assertFalse((output/'tx.bin').exists())
        finally:
            child.communicate(timeout=5); os.close(master)

    def pty_session(self, corrupt=False, phase='probe', disconnect=False):
        master, slave = pty.openpty()
        port = os.ttyname(slave)
        os.close(slave)
        peer = Peer(phase); controller = u.Controller(M, BEFORE, peer.current, phase)
        errors = []
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'run'
            def worker():
                try: u.live(port, output, controller)
                except Exception as e: errors.append(e)
            thread = threading.Thread(target=worker, daemon=True); thread.start()
            try:
                for _ in range(100):
                    if (output/'rx.bin').exists(): break
                    time.sleep(.01)
                self.assertTrue((output/'rx.bin').exists())
                # Exclusive acquisition refuses a competing open.
                with self.assertRaises(OSError): os.open(port, os.O_RDWR | os.O_NOCTTY)
                os.write(master, BOOT)
                pending = b''; deadline = time.monotonic()+25; command_start = None; measured = False
                while thread.is_alive() and time.monotonic() < deadline:
                    if not select.select([master], [], [], .1)[0]: continue
                    try: data = os.read(master, 4096)
                    except OSError as e:
                        if e.errno == 5: break  # slave closed at terminal state
                        raise
                    if not pending and data != b' ': command_start = time.monotonic()
                    pending += data
                    if pending == b' ':
                        pending = b''; os.write(master, b'\r\n=> ')
                    while b'\r' in pending:
                        line, pending = pending.split(b'\r', 1); wire = line+b'\r'
                        if not measured:
                            self.assertGreater(time.monotonic()-command_start, len(wire)*.001)
                            measured = True
                        if disconnect and line.startswith(b'if env save;'):
                            os.close(master); master = None
                            break
                        if wire == b'run bootcmd\r': response = LINUX
                        else:
                            response = peer.reply(wire)
                            if corrupt: response = response.replace(b'if gpio', b'if ggpio')
                        # Real fragmented peer output, including CRLF boundaries.
                        for i in range(0, len(response), 37): os.write(master, response[i:i+37])
                    if master is None: break
                thread.join(1)
                self.assertFalse(thread.is_alive(), 'PTY controller did not terminate')
                result = json.loads((output/'RESULT.json').read_text())
                failed = corrupt or disconnect
                self.assertEqual(result['state'], 'failed' if failed else 'done')
                self.assertEqual(peer.writes, 0 if failed else 1)
                self.assertEqual(result['save_attempts'], 0 if corrupt else 1)
                self.assertEqual(bool(errors), failed)
                if disconnect:
                    self.assertEqual(json.loads((output/'CHECKPOINT.json').read_text())['save_attempts'], 1)
                with self.assertRaises(FileExistsError): u.live(port, output, u.Controller(M, BEFORE, BEFORE, 'probe'))
            finally:
                if master is not None: os.close(master)


def mutations():
    source = A.controller.read_text()
    changes = [
        ('wrong build accepted', 'b.count(BANNER) ==', '1 =='),
        ('wrong load accepted', 'b.count(LOAD) == 1', '1 == 1'),
        ('echo unchecked', "require(b.startswith(self.wire+b'\\n'),", 'require(True,'),
        ('fan unchecked', "require(body == b'gpio: pin PB5 (gpio 37) value is 1',", 'require(True,'),
        ('device unchecked', "require(body.splitlines() == [b'switch to partitions #0, OK', b'mmc1(part 0) is current device'],", 'require(True,'),
        ('preimage CRC unchecked', 'require(crc == zlib.crc32(self.before if self.old else self.current),', 'require(True,'),
        ('RAM guard unchecked', "env.check(self.before, env.encode(expected), self.phase, self.m['nonce'], self.ram)", 'pass'),
        ('postedit RAM unchecked', 'require(ram_map(body) == self.expected,', 'require(True,'),
        ('native save status unchecked', "require(body == b'Saving Environment to MMC... Writing to MMC(1)... OK',", 'require(True,'),
        ('second save allowed', "require(self.saves == 0,", 'require(True,'),
        ('file pins unchecked', "require(x['files'] == m['_file_pins'],", 'require(True,'),
        ('protected bytes unchecked', "require(digest(region(p['offset'], p['bytes'])) == p['sha256'],", 'require(True,'),
    ]
    with tempfile.TemporaryDirectory() as td:
        # Keep helper lookup independent of the temporary controller location.
        import shutil
        shutil.copyfile(Path(u.env.__file__), Path(td)/'check-uboot-savepath.py')
        for label, old, new in changes:
            assert source.count(old) == 1, label
            path = Path(td)/'mutant.py'; path.write_text(source.replace(old, new))
            result = subprocess.run(['python3', str(Path(__file__).resolve()), '--packet', str(A.packet.resolve()),
                                     '--capture', str(A.capture.resolve()), '--controller', str(path), '--no-pty'], capture_output=True)
            if result.returncode == 0:
                raise AssertionError('SURVIVED '+label)
            # Import/CLI failures are not evidence that behavioral tests caught a fault.
            require = u.require
            require(b'FAIL:' in result.stderr or b'ERROR: test_' in result.stderr, 'mutation did not reach tests: '+label)
            print('CAUGHT '+label)
    print(f'PASS all {len(changes)} UART controller mutations caught')


if __name__ == '__main__':
    if A.mutations: mutations()
    else:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(not result.wasSuccessful())
