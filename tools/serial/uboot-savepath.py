#!/usr/bin/env python3
"""Bounded, single-use UART save-path controller. Default is an offline plan.

No reboot/power control, raw storage writes, recovery, or retries. A live phase
requires explicit execution selection, a verified Linux capture, exclusive UART
ownership and an operator-ready sequence. See the dated validation runbook.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import stat
import subprocess
import tarfile
import termios
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('savecheck', Path(__file__).with_name('check-uboot-savepath.py')
                                               if Path(__file__).with_name('check-uboot-savepath.py').exists()
                                               else ROOT/'tools/hdmi/check-uboot-savepath.py')
env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(env)
require = env.require
BANNER = b'U-Boot 2026.07-rc5-g320a17f71d41-h713-b3b5f2d2 (Oct 30 2026 - 02:09:43 -0700) Allwinner Technology'
SPL = b'U-Boot SPL 2026.07-rc5-g7b178056c329-dirty (Aug 25 2026 - 20:13:26 -0700)'
LOAD = b'Loading Environment from MMC... Reading from MMC(1) at 0x93d80000... OK'
PROMPT = b'=> '


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_packet(path):
    """Check sealed packet before constructing any commands."""
    lines = (path/'SHA256SUMS').read_text().splitlines()
    names = set()
    for line in lines:
        sha, name = line.split('  ', 1)
        require(name == Path(name).name and name not in names, 'unsafe/duplicate ledger member')
        require(not (path/name).is_symlink() and digest((path/name).read_bytes()) == sha, 'packet checksum mismatch: '+name)
        names.add(name)
    require({'manifest.json', 'environment-before.bin', 'uboot.config'} <= names, 'incomplete packet ledger')
    m = json.loads((path/'manifest.json').read_text())
    require(m['schema'] == 'h713-savepath-preparation-v1', 'wrong packet schema')
    require(re.fullmatch(r'[A-Za-z0-9_-]{8,64}', m['nonce']), 'unsafe nonce')
    require(m['probe_key'] == env.PROBE.decode(), 'wrong probe key')
    w = m['write_region']
    require((w['offset'], w['lba'], w['bytes'], w['sectors']) == (0x93d80000, '0x49ec00', 65536, 128), 'wrong mutable region')
    before = (path/'environment-before.bin').read_bytes()
    require(digest(before) == w['before']['sha256'], 'wrong backup generation')
    env.check(before, env.encode(env.decode(before)), 'cleanup', m['nonce'])
    require(len(m['protected']) == 9, 'nine protected ranges required')
    config = (path/'uboot.config').read_text()
    for setting in ['CONFIG_HUSH_PARSER=y', 'CONFIG_CMD_ECHO=y', 'CONFIG_CMD_SAVEENV=y', 'CONFIG_CMD_CRC32=y',
                    'CONFIG_CMD_MEMORY=y', 'CONFIG_CMD_MMC=y', 'CONFIG_CMD_GPIO=y',
                    '# CONFIG_CMD_MMC_REG is not set']:
        require(setting+'\n' in config, 'unexpected installed command configuration')
    require('inventory-private.json' in names, 'missing pinned file inventory')
    m['_file_pins'] = json.loads((path/'inventory-private.json').read_text())['files']
    file_count = m.get('installed_file_count', 50)
    require(file_count in (50, 52) and len(m['_file_pins']) == file_count,
            'incomplete installed file inventory')
    return m, before


def read_capture(path, m):
    """Read-only Linux evidence: identity, health and every pinned raw range."""
    with tarfile.open(path) as t:
        members = t.getmembers()
        require(all(p.isfile() and p.name == Path(p.name).name and p.size <= 40*1024*1024 for p in members), 'unsafe capture')
        require(len(members) == len({p.name for p in members}), 'duplicate capture member')
        files = {p.name: t.extractfile(p).read() for p in members}
    x = json.loads(files['inventory.json'])
    for key in ['model', 'cid', 'capacity_bytes', 'logical_sector_bytes', 'device', 'type', 'dev_number', 'linux_hardware_partition']:
        require(x['identity'][key] == m['identity'][key], 'capture identity mismatch: '+key)
    require(x['identity']['boot_id'] == x['ending_boot_id'] == x['session']['boot_id'] and x['session']['phase'] == 'ready', 'capture not one ready Linux boot')
    require(x['latches']['gp6_gp7_hex'] == '4b4f444800000000', 'startup/latch gate failed')
    require(len(x['bundle_checks']) == 4 and all(b['all_match'] for b in x['bundle_checks']), 'bundle gate failed')
    require(x['files'] == m['_file_pins'], 'installed file/metadata pins changed')
    require(x['filesystem']['returncode'] == x['services']['returncode'] == 0, 'health commands failed')
    services = [dict(line.split('=', 1) for line in record.splitlines() if '=' in line)
                for record in x['services']['stdout'].strip().split('\n\n')]
    require(len(services) == 6 and all(s.get('ActiveState') == 'active' and s.get('NRestarts') == '0' for s in services), 'service health gate failed')
    fs = dict(line.split(':', 1) for line in x['filesystem']['stdout'].splitlines() if ':' in line)
    require(fs.get('Filesystem state', '').strip() == 'clean' and int(fs.get('FS Error count', fs.get('Error count', '0')).strip()) == 0, 'filesystem gate failed')
    require('EXT4-fs error' not in x['kernel_log']['stdout'], 'filesystem error logged')
    require(not x['reserved_partition_holders'] and not x['reserved_partition_mounts'], 'reserved partition in use')
    for name in ['h713_hdmi_audio/parameters/period_xruns', 'h713_hdmi_v4l2/parameters/frames_rejected']:
        require(x['runtime']['/sys/module/'+name] == '0', 'runtime error counter')
    for name, r in x['ranges'].items():
        require(len(files[name]) == r['bytes'] and digest(files[name]) == r['sha256'], 'capture range checksum')
    def region(offset, size):
        for name, r in x['ranges'].items():
            if r['offset'] <= offset and offset+size <= r['offset']+r['bytes']:
                start = offset-r['offset']
                return files[name][start:start+size]
        raise ValueError('uncaptured storage region')
    for p in m['protected']:
        require(digest(region(p['offset'], p['bytes'])) == p['sha256'], 'protected region mismatch: '+p['name'])
    return x, region(0x93d80000, 65536)


def ram_map(body):
    lines = body.splitlines()
    require(lines and re.fullmatch(rb'Environment size: [0-9]+/[0-9]+ bytes', lines[-1]), 'missing RAM snapshot footer')
    values = {}
    for line in lines[:-1]:
        if not line:
            continue
        require(b'=' in line and all(c >= 32 and c < 127 for c in line), 'malformed RAM snapshot')
        k, v = line.split(b'=', 1)
        require(re.fullmatch(rb'[A-Za-z0-9_#.-]+', k) and k not in values, 'duplicate/unsafe RAM key')
        # hexport_r('\n') doubles literal backslashes; newline values are
        # deliberately unsupported by this packet, so only \\ is accepted.
        require(b'\\' not in v.replace(b'\\\\', b''), 'unsupported RAM value escape')
        values[k] = v.replace(b'\\\\', b'\\')
    return values


class Controller:
    """Transport-independent state machine; feed bytes, receive paced TX requests.

    A single owner calls feed/tick; errors are terminal and cause no recovery TX.
    Prompt is accepted only at frame end, exact echo and unique status token are
    required, and all command output is checked before advancing.
    """
    def __init__(self, m, before, current, phase, now=0, preflight_boot_id=None):
        require(phase in ['probe', 'cleanup'], 'invalid phase')
        self.m, self.before, self.current, self.phase = m, before, current, phase
        self.state, self.buffer, self.deadline = 'boot', b'', now+180
        self.tx, self.events, self.ram = [], [], None
        self.index, self.saves, self.error = 0, 0, None
        self.after_crc = None
        self.prompt_deadline = None
        self.preflight_boot_id = preflight_boot_id or m['identity']['boot_id']

    def fail(self, message):
        self.state, self.error = 'failed', message
        self.tx.clear()
        self.events.append({'failure': message, 'save_attempts': self.saves})
        raise ValueError(message)

    def tick(self, now):
        if self.state not in ['done', 'failed'] and now >= self.deadline:
            self.fail('deadline exceeded in '+self.state+'; no retry or recovery')
        if self.state in ['command', 'interrupt'] and self.prompt_deadline is not None and now >= self.prompt_deadline:
            self.fail('total prompt budget exceeded; no retry or recovery')

    def send(self, command, kind, now):
        self.index += 1
        token = f'__SP_{self.m["nonce"]}_{self.phase}_{self.index}'
        self.ok, self.bad = (token+'_OK__').encode(), (token+'_FAIL__').encode()
        self.wire = b'if '+command.encode()+b'; then echo '+self.ok+b'; else echo '+self.bad+b'; fi'
        require(len(self.wire) < 1024, 'console line too long')
        self.state, self.kind, self.buffer, self.deadline = 'command', kind, b'', now+15
        self.tx.append(self.wire+b'\r')
        self.events.append({'command': command, 'gate': kind})

    def read_slot(self, old, purpose, now):
        self.old, self.purpose = old, purpose
        address, lba = ('0x43000000', '0x32ec00') if old else ('0x42000000', '0x49ec00')
        self.send(f'mmc read {address} {lba} 0x80', 'read', now)

    def feed(self, data, now):
        self.tick(now)
        if self.state in ['failed', 'done']:
            return
        self.buffer += data.replace(b'\r', b'')
        if len(self.buffer) > 131072:
            self.fail('console frame overflow')
        b = self.buffer
        if self.state == 'boot':
            if b.count(b'U-Boot SPL ') > 1 or b.count(b'\nU-Boot 20') > 1:
                self.fail('repeated boot')
            if b'Starting kernel' in b or b'login:' in b or b'H713 RESET v1 stage=pre_workspace' in b:
                self.fail('missed autoboot window')
            if b'Hit any key to stop autoboot:' in b:
                if not (b.count(SPL) == b.count(BANNER) == b.count(LOAD) == 1):
                    self.fail('unrecognized boot build/environment load')
                self.state, self.deadline = 'interrupt', now+5
                self.prompt_deadline = now+120
                self.tx.append(b' ')
                # The countdown and prompt can be in one received chunk.
                tail = b.split(b'Hit any key to stop autoboot:', 1)[1]
                if PROMPT in tail:
                    self.fail('prompt arrived before our interrupt; unexpected console input')
                self.buffer = tail
            elif PROMPT in b:
                self.fail('unexpected prompt without ordinary countdown')
            return
        if self.state == 'interrupt':
            if b'Linux version' in b or b'Starting kernel' in b or b'U-Boot SPL ' in b:
                self.fail('autoboot interrupt failed')
            if b.endswith(b'\n'+PROMPT):
                # U-Boot's video console repaints the countdown using erase-line
                # and repeats its label, including a final 0 after interruption.
                # Accept only that exact repaint sequence, never arbitrary ANSI.
                if not re.fullmatch(rb'(?:[0-9 \x08\n]|\x1b\[2K|Hit any key to stop autoboot:)*\n=> ', b):
                    self.fail('unexpected interrupt reply')
                self.send('gpio set PB5', 'fan', now)
            return
        if self.state == 'linux':
            if b'\n' in b:
                if not b.startswith(b'run bootcmd\n'):
                    self.fail('bootcmd echo mismatch')
            if b'U-Boot SPL ' in b or b'\n=> ' in b or b'Kernel panic' in b:
                self.fail('unexpected reset/prompt/panic after bootcmd')
            if b'H713 HDMI shared startup handoff verified' in b and b'Starting kernel ...' in b and b'h713-arm64 login:' in b:
                self.state = 'done'
                self.events.append({'result': 'UART phase complete; Linux raw storage/health verification still required'})
            return
        if not b.endswith(b'\n'+PROMPT):
            return
        try:
            require(b.startswith(self.wire+b'\n'), 'command echo mismatch')
            body = b[len(self.wire)+1:-len(b'\n'+PROMPT)]
            require(body.endswith(self.ok) and body.splitlines().count(self.ok) == 1 and self.bad not in body,
                    'command status missing/failed')
            body = body[:-len(self.ok)].rstrip(b'\n')
            self.advance(body, now)
        except ValueError as e:
            self.fail(str(e))

    def advance(self, body, now):
        k = self.kind
        if k == 'fan':
            require(body == b'gpio: pin PB5 (gpio 37) value is 1', 'shared lamp/fan gate failed')
            self.send('version', 'version', now)
        elif k == 'version':
            require(BANNER in body.splitlines(), 'version gate failed')
            self.send('mmc dev 1 0', 'device', now)
        elif k == 'device':
            require(body.splitlines() == [b'switch to partitions #0, OK', b'mmc1(part 0) is current device'], 'MMC user device gate failed')
            self.send('mmc info', 'info', now)
        elif k == 'info':
            for line in [b'Manufacturer ID: 15', b'OEM: 0', b'Name: 8GTF4R', b'Rd Block Len: 512', b'High Capacity: Yes']:
                require(line in body.splitlines(), 'MMC info gate failed')
            require(re.search(rb'^MMC version [0-9.]+$', body, re.M), 'not eMMC')
            self.read_slot(False, 'before', now)
        elif k == 'read':
            lba = 0x32ec00 if self.old else 0x49ec00
            expected = f'MMC read: dev # 1, block # {lba}, count 128 ... 128 blocks read: OK'.encode()
            require(body.strip() == expected, 'MMC raw read extent/status failed')
            addr = '0x43000000' if self.old else '0x42000000'
            self.send(f'crc32 {addr} 0x10000', 'crc', now)
        elif k == 'crc':
            addr = 0x43000000 if self.old else 0x42000000
            prefix = re.escape(f'crc32 for {addr:08x} ... {addr+65535:08x} ==> '.encode())
            match = re.fullmatch(prefix+rb'([0-9a-f]{8})', body)
            require(match is not None, 'CRC readback format failed')
            crc = int(match[1], 16)
            if self.old or self.purpose == 'before':
                require(crc == zlib.crc32(self.before if self.old else self.current), 'preimage/protected old-slot CRC mismatch')
            else:
                self.after_crc = f'{crc:08x}'
            if not self.old:
                self.read_slot(True, self.purpose, now)
            elif self.purpose == 'before':
                self.send('env print -a', 'ram', now)
            else:
                self.state, self.buffer, self.deadline = 'linux', b'', now+180
                self.tx.append(b'run bootcmd\r')
                self.events.append({'command': 'run bootcmd', 'gate': 'continue same boot; no reset'})
        elif k == 'ram':
            self.ram = ram_map(body)
            expected = dict(self.ram)
            if self.phase == 'probe':
                expected[env.PROBE] = self.m['nonce'].encode()
            else:
                expected.pop(env.PROBE, None)
            env.check(self.before, env.encode(expected), self.phase, self.m['nonce'], self.ram)
            self.expected = expected
            command = ('env set '+env.PROBE.decode()+' '+self.m['nonce']) if self.phase == 'probe' else 'env delete '+env.PROBE.decode()
            self.send(command, 'edit', now)
        elif k == 'edit':
            require(body == b'', 'unexpected env edit output')
            self.send('env print -a', 'edited', now)
        elif k == 'edited':
            require(ram_map(body) == self.expected, 'RAM changed between snapshot and save')
            require(self.saves == 0, 'save already attempted')
            self.saves += 1  # mark BEFORE transmission: errors are ambiguous, never retried
            self.send('env save', 'save', now)
        elif k == 'save':
            require(body == b'Saving Environment to MMC... Writing to MMC(1)... OK', 'native save failed or wrong device')
            self.read_slot(False, 'after', now)
        else:
            raise ValueError('invalid controller state')

    def result(self):
        return dict(schema='h713-savepath-uart-v1', phase=self.phase, state=self.state,
                    nonce=self.m['nonce'], save_attempts=self.saves, failure=self.error,
                    before_sha256=digest(self.current), after_crc32=self.after_crc,
                    preflight_boot_id=self.preflight_boot_id,
                    ram={k.decode(): v.hex() for k, v in (self.ram or {}).items()},
                    packet_manifest_sha256=digest(json.dumps(self.m, sort_keys=True).encode()),
                    hardware_storage_verified=False, events=self.events)


def verify_phase(m, before, capture, result):
    require(result['schema'] == 'h713-savepath-uart-v1' and result['state'] == 'done' and result['save_attempts'] == 1, 'previous UART phase incomplete')
    require(result['nonce'] == m['nonce'] and result['packet_manifest_sha256'] == digest(json.dumps(m, sort_keys=True).encode()), 'previous phase packet mismatch')
    x, saved = read_capture(capture, m)
    require(result['preflight_boot_id'] != x['identity']['boot_id'], 'Linux capture did not advance past the preflight boot')
    ram = {k.encode(): bytes.fromhex(v) for k, v in result['ram'].items()}
    checked = env.check(before, saved, result['phase'], m['nonce'], ram)
    require(f'{zlib.crc32(saved):08x}' == result['after_crc32'], 'Linux bytes differ from UART CRC')
    return x, saved, checked


def persist_result(path, value):
    temporary = path.with_name(path.name+'.new')
    with temporary.open('w') as journal:
        json.dump(value, journal, indent=2)
        journal.write('\n')
        journal.flush()
        os.fsync(journal.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def live(port, output, controller):
    """Exclusive raw UART; no DTR/RTS toggles, flush, reconnect or retry."""
    os.umask(0o077)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    fd = None
    exclusive = False
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        require(stat.S_ISCHR(os.fstat(fd).st_mode), 'UART is not a character device')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        exclusive = True
        # TIOCEXCL prevents future opens, not existing readers. Reject them too.
        # Run on the full host (not a restricted PID namespace); see runbook.
        owners = subprocess.run(['fuser', port], capture_output=True, timeout=5)
        require(owners.returncode == 0 and owners.stdout.split() == [str(os.getpid()).encode()], 'UART has other owners or ownership audit failed')
        require(owners.stderr.strip() == (port+':').encode(), 'UART ownership audit reported warnings')
        own_fds = []
        for entry in Path('/proc/self/fd').iterdir():
            try:
                s = entry.stat()
                if stat.S_ISCHR(s.st_mode) and s.st_rdev == os.fstat(fd).st_rdev:
                    own_fds.append(entry.name)
            except FileNotFoundError:
                pass
        require(own_fds == [str(fd)], 'duplicate UART descriptor in controller process')
        a = termios.tcgetattr(fd)
        a[0], a[1], a[2], a[3] = 0, 0, termios.CS8 | termios.CREAD | termios.CLOCAL, 0
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = a[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, a)
        start = time.monotonic()
        print('ARMED: waiting for a fresh ordinary boot; no reboot or power command issued', flush=True)
        with (output/'rx.bin').open('xb', buffering=0) as rx, (output/'tx.bin').open('xb', buffering=0) as tx, \
                (output/'IO-EVENTS.jsonl').open('x', buffering=1) as io_events:
            while controller.state not in ['done', 'failed']:
                controller.tick(time.monotonic()-start)
                if select.select([fd], [], [], .02)[0]:
                    data = os.read(fd, 4096)
                    require(data, 'UART disconnected; no reconnect')
                    rx.write(data)
                    io_events.write(json.dumps(dict(rx_bytes=len(data), rx_end=rx.tell(), seconds=time.monotonic()-start))+'\n')
                    controller.feed(data, time.monotonic()-start)
                while controller.tx:
                    wire = controller.tx.pop(0)
                    io_events.write(json.dumps(dict(tx_intent_hex=wire.hex(), seconds=time.monotonic()-start))+'\n')
                    io_events.flush()
                    os.fsync(io_events.fileno())
                    os.fsync(rx.fileno())
                    os.fsync(tx.fileno())
                    # Persist the ambiguous-write boundary before sending even
                    # the first byte. A crash never justifies repeating a save.
                    persist_result(output/'CHECKPOINT.json', controller.result())
                    for char in wire:
                        require(os.write(fd, bytes([char])) == 1, 'short UART write; no retry')
                        tx.write(bytes([char]))
                        time.sleep(.002)
                    termios.tcdrain(fd)
                    os.fsync(tx.fileno())
    except BaseException as e:
        controller.state, controller.error = 'failed', str(e)
        raise
    finally:
        try:
            persist_result(output/'RESULT.json', controller.result())
        finally:
            if fd is not None:
                try:
                    if exclusive:
                        fcntl.ioctl(fd, termios.TIOCNXCL)
                finally:
                    os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--phase', choices=['probe', 'cleanup'], default='probe')
    p.add_argument('--preflight', type=Path, help='fresh read-only Linux capture; cleanup uses post-probe capture')
    p.add_argument('--probe-result', type=Path, help='completed probe RESULT.json, required for cleanup')
    p.add_argument('--verify-result', type=Path, help='offline: verify a completed phase against --preflight capture')
    p.add_argument('--execute-approved', action='store_true', help='LIVE UART TX including ONE env save; requires separate operator authorization')
    p.add_argument('--port', help='explicit UART path; no autodiscovery')
    p.add_argument('--output', type=Path, help='new private single-use run directory')
    a = p.parse_args()
    m, before = load_packet(a.packet)
    if a.verify_result:
        require(not a.execute_approved and a.preflight, 'verification is offline and requires capture')
        x, saved, checked = verify_phase(m, before, a.preflight, json.loads(a.verify_result.read_text()))
        print(json.dumps(dict(checked, boot_id=x['identity']['boot_id'], protected_regions=9), indent=2))
        return
    current = before
    if a.preflight:
        x, current = read_capture(a.preflight, m)
        if a.phase == 'cleanup':
            require(a.probe_result, 'cleanup requires completed probe evidence')
            result = json.loads(a.probe_result.read_text())
            require(result['phase'] == 'probe', 'cleanup requires probe phase')
            verify_phase(m, before, a.preflight, result)
        else:
            require(current == before, 'probe preflight environment generation changed')
    if not a.execute_approved:
        print(json.dumps(dict(mode='OFFLINE PLAN ONLY', phase=a.phase, nonce=m['nonce'],
                              native_saves=1, reboot_commands=0, hardware_opened=False,
                              requires='fresh identity/storage/health preflight, sole UART owner, operator-ready authorization'), indent=2))
        return
    require(a.preflight and a.port and a.output, 'live mode requires preflight, explicit port and new output')
    def stop(*unused):
        raise KeyboardInterrupt('operator stopped controller; no retry or recovery')
    signal.signal(signal.SIGTERM, stop)
    live(a.port, a.output, Controller(m, before, current, a.phase, preflight_boot_id=x['identity']['boot_id']))


if __name__ == '__main__':
    main()
