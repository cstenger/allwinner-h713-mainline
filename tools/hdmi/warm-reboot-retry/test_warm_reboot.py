#!/usr/bin/env python3
"""Offline tests for the warm-reboot retry packet. Contacts no board; replays real evidence."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

TARGET = Path(os.environ.get('H713_HRT_DIR', Path(__file__).resolve().parent))
REPO = Path(__file__).resolve().parents[3]
RECOVERY = REPO / 'local/recovery'
BOOT, NEXT = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
HOST_A, HOST_B = 'aaaaaaaa-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000002'
MAGIC = (0x48444d49).to_bytes(4, 'little')


def load_run():
    spec = importlib.util.spec_from_file_location('hrt_run', TARGET / 'run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load_run()


def sram(fill=0x5a):
    data = bytearray([fill]) * 0x5000
    data[0x4f00:0x4f80] = bytes(0x80)
    for index in (0, 2, 5):
        data[0x4f00 + 4 * index:0x4f04 + 4 * index] = MAGIC
    return bytes(data)


class Board:
    """A fake board filesystem plus fake commands that log what they were asked to do."""

    def __init__(self, tmp):
        self.root = Path(tmp) / 'root'
        self.bin = Path(tmp) / 'bin'
        self.log = Path(tmp) / 'commands.log'
        self.bin.mkdir()
        files = {
            'proc/device-tree/model': 'HY200 QZ713DF_A1 (Allwinner H713)\0',
            'proc/sys/kernel/random/boot_id': BOOT + '\n',
            'proc/uptime': '100.0 100.0\n',
            'sys/class/block/mmcblk0/device/cid': 'cid-1\n',
            'sys/kernel/notes': 'notes',
            'sys/devices/platform/h713-hdmi-ring/signal': 'locked 1280x720\n',
            'run/h713-hdmi-session/state.json': json.dumps({'boot_id': BOOT, 'phase': 'ready'}),
            'run/h713-hdmi-signal/owned': 'x', 'run/h713-hdmi-signal/attempted': 'x',
            'sys/fs/ext4/mmcblk0p26/errors_count': '0\n',
            'etc/systemd/system/h713-hdmi-signal.service.d/90-start-delay.conf': 'zero',
            'usr/lib/h713-hdmi/pinned': 'pinned',
            'usr/lib/h713-hdmi-delay-bench/manifest.json': 'manifest',
        }
        params = {'h713_hdmi_signal': dict(ready='Y', failed='N', restored='N', recovery='0'),
                  'h713_hdmi_receiver': dict(clock_count='4', clients='2', edid_ready='Y', init_error='0'),
                  'h713_hdmi_audio': dict(graph_ready='Y', dsp_failed='N')}
        for module, values in params.items():
            for name, value in values.items():
                files['sys/module/%s/parameters/%s' % (module, name)] = value + '\n'
        for name, content in files.items():
            self.write(name, content)
        (self.root / 'var/backups/h713-hdmi-zero-control-20261101-01').mkdir(parents=True)
        (self.root / 'dev').mkdir()
        with (self.root / 'dev/mem').open('wb') as f:
            f.seek(0x100000)
            f.write(sram())
            f.seek(0x07000400)
            f.write((1).to_bytes(4, 'little'))
            f.seek(0x07022004)
            f.write((0x22222200).to_bytes(4, 'little'))
            f.truncate(0x07100000)
        (self.root / 'dev/mmcblk0').write_bytes(b'storage!')
        self.cmd('findmnt', 'echo "/dev/mmcblk0p26 ext4 rw,noatime"')
        self.cmd('dmesg', 'echo "[ 1.0] EXT4-fs (mmcblk0p26): mounted"')
        self.cmd('journalctl', 'echo journal "$@"')
        self.cmd('sync', 'echo sync >> "%s"' % self.log)
        self.cmd('systemctl', '''case "$1" in
 poweroff) echo poweroff >> "%s";;
 is-system-running) echo running;;
 show) case "$2" in
  *signal*) if [ "$4" = ExecStart ]; then echo 'ExecStart={ /usr/lib/h713-hdmi-delay-bench/h713-hdmi-signal.py start --bundle x --bench-delay-ms=0 --bench-manifest=m }'; echo 'ExecStop={ /usr/lib/h713-hdmi/h713-hdmi-signal.py stop }'; else echo ActiveState=active; fi;;
  *) echo ActiveState=active;;
 esac;;
esac''' % self.log)

    def write(self, name, content):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content) if isinstance(content, str) else p.write_bytes(content)

    def cmd(self, name, body):
        p = self.bin / name
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)

    def pins(self):
        import hashlib
        h = lambda name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        info = (self.root / 'usr/lib/h713-hdmi/pinned').stat()
        return {'file_pins': {'/usr/lib/h713-hdmi/pinned': {'bytes': 6, 'mode': info.st_mode & 0o7777, 'uid': info.st_uid,
                                                            'gid': info.st_gid, 'sha256': h('usr/lib/h713-hdmi/pinned')}},
                'runtime_hashes': {'manifest.json': h('usr/lib/h713-hdmi-delay-bench/manifest.json')},
                'storage': [{'name': 'disk', 'offset': 0, 'bytes': 8, 'sha256': h('dev/mmcblk0')}],
                'dropin_sha256': h('etc/systemd/system/h713-hdmi-signal.service.d/90-start-delay.conf'),
                'kernel_notes_sha256': h('sys/kernel/notes'), 'cid': 'cid-1'}

    def run(self, mode, pins=None, snippet=None, **extra):
        with patch.dict(os.environ, {'H713_HRT_TEST_ROOT': str(self.root)}):
            script = R.render(mode, pins or self.PINS, **extra)
        if snippet:  # replace the final dispatch so one function can be probed
            script = script[:script.rindex('result = {')] + snippet
        env = {**os.environ, 'PATH': '%s:%s' % (self.bin, os.environ['PATH'])}
        return subprocess.run([sys.executable, '-I', '-'], input=script, capture_output=True, text=True, env=env, timeout=30)

    def commands(self):
        return self.log.read_text().split() if self.log.exists() else []

    @property
    def receipt(self):
        return self.root / ('var/backups/h713-hdmi-zero-control-20261101-01/' + R.TAG + '-poweroff-request.json')


class BoardScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Board(self.tmp.name)
        self.b.PINS = self.b.pins()
        out = self.b.run('preflight')
        self.assertEqual(out.returncode, 0, out.stderr)
        self.pre = json.loads(out.stdout)

    def tearDown(self):
        self.tmp.cleanup()

    def poweroff(self):
        return self.b.run('poweroff', expected_boot=BOOT, s0_bank_sha256=self.pre['sram']['bank_backup_sha256'])

    def test_preflight_writes_and_powers_off_nothing(self):
        self.assertEqual(self.b.commands(), [])
        self.assertFalse(self.b.receipt.exists())
        self.assertEqual(self.pre['signal'], 'locked 1280x720')
        self.assertEqual(len(bytes.fromhex(self.pre['sram']['sram_hex'])), 0x5000)

    def test_poweroff_runs_once_and_never_twice(self):
        out = self.poweroff()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('ISSUING_ONE_ORDINARY_SYSTEMCTL_POWEROFF', out.stdout)
        self.assertEqual(self.b.commands(), ['sync', 'poweroff'])
        self.assertEqual(json.loads(self.b.receipt.read_text())['expected_boot_id'], BOOT)
        self.assertNotEqual(self.poweroff().returncode, 0)
        self.assertEqual(self.b.commands(), ['sync', 'poweroff'])

    def test_every_gate_stops_before_any_write(self):
        cases = {
            # Session follows the boot, so only the expected-boot gate can stop this one.
            'boot': lambda: (self.b.write('proc/sys/kernel/random/boot_id', NEXT),
                             self.b.write('run/h713-hdmi-session/state.json', json.dumps({'boot_id': NEXT, 'phase': 'ready'}))),
            'model': lambda: self.b.write('proc/device-tree/model', 'other'),
            'cid': lambda: self.b.write('sys/class/block/mmcblk0/device/cid', 'other'),
            'kernel': lambda: self.b.write('sys/kernel/notes', 'other'),
            'diagnostic': lambda: (self.b.root / 'sys/module/h713_scp_probe').mkdir(),
            'signal': lambda: self.b.write('sys/devices/platform/h713-hdmi-ring/signal', 'none'),
            'session': lambda: self.b.write('run/h713-hdmi-session/state.json', '{"boot_id":"x","phase":"ready"}'),
            'owner': lambda: self.b.write('sys/module/h713_hdmi_signal/parameters/failed', 'Y'),
            'graph': lambda: self.b.write('sys/module/h713_hdmi_audio/parameters/graph_ready', 'N'),
            'latch': lambda: (self.b.root / 'run/h713-hdmi-signal/owned').unlink(),
            'dropin': lambda: self.b.write('etc/systemd/system/h713-hdmi-signal.service.d/90-start-delay.conf', '2000'),
            'pin': lambda: self.b.write('usr/lib/h713-hdmi/pinned', 'pinneD'),
            'runtime': lambda: self.b.write('usr/lib/h713-hdmi-delay-bench/manifest.json', 'other'),
            'storage': lambda: self.b.write('dev/mmcblk0', b'storagE!'),
            'ext4': lambda: self.b.write('sys/fs/ext4/mmcblk0p26/errors_count', '1'),
            'readonly': lambda: self.b.cmd('findmnt', 'echo "/dev/mmcblk0p26 ext4 ro,noatime"'),
            'exec': lambda: self.b.cmd('systemctl', 'case "$1" in show) echo "--bench-delay-ms=2000 ActiveState=active";; esac'),
            'bank': lambda: self.b.PINS and self._poke_sram(0x4780, b'\\x00'),
            'scp': lambda: self._poke_sram(0x4f00 + 4 * 3, (1).to_bytes(4, 'little')),
        }
        for name, change in cases.items():
            with self.subTest(gate=name):
                self.tearDown()
                self.setUp()
                change()
                out = self.poweroff()
                self.assertNotEqual(out.returncode, 0, name)
                self.assertEqual(self.b.commands(), [], name)
                self.assertFalse(self.b.receipt.exists(), name)

    def _poke_sram(self, offset, data):
        with (self.b.root / 'dev/mem').open('r+b') as f:
            f.seek(0x100000 + offset)
            f.write(data)

    def test_forbidden_addresses_are_refused(self):
        for address, size in ((0x07091000, 4), (0x07091014, 4), (0x06940000, 4), (0x105000, 4), (0xfffff, 8), (0x07000400, 8)):
            with self.subTest(address=hex(address)):
                out = self.b.run('preflight', snippet='physical(%d, %d)\n' % (address, size))
                self.assertIn('address not allowed', out.stderr)

    def test_collect_reports_a_failed_detection_without_refusing(self):
        self.b.write('proc/sys/kernel/random/boot_id', NEXT)
        self.b.write('sys/devices/platform/h713-hdmi-ring/signal', 'none')
        out = self.b.run('collect', previous_boot=BOOT)
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout)
        self.assertEqual(result['signal'], 'none')
        self.assertIn('-b %s ' % BOOT.replace('-', ''), result['previous_boot_signal_journal']['stdout'])
        self.assertEqual(self.b.commands(), [])
        self.assertFalse(self.b.receipt.exists())

    def test_collect_refuses_the_old_boot(self):
        self.assertNotEqual(self.b.run('collect', previous_boot=BOOT).returncode, 0)


class Evidence(unittest.TestCase):
    """Real retained data, so these numbers can fail."""

    def test_known_power_loss_classifies_as_lost(self):
        a = json.loads((RECOVERY / '2026-10-31-hdmi-discovery/coprocessor-state.json').read_text())['sram_hex']
        b = json.loads((RECOVERY / '2026-11-01-board-boot-uart/coprocessor-readonly.json').read_text())['sram_hex']
        result = R.bank_comparison(a, b)
        self.assertEqual((result['edid_ram'], result['differing_bits'], result['bytes']), ('LOST', 537, 768))
        self.assertEqual(R.bank_comparison(a, a)['edid_ram'], 'RETAINED')
        flipped = bytearray.fromhex(a)
        flipped[0x4780] ^= 1
        self.assertEqual(R.bank_comparison(a, flipped.hex())['edid_ram'], 'PARTIAL')

    def test_timing_reproduces_recorded_passes(self):
        for name, connected, lock in (('2026-11-01-hdmi-delay-boot-validation', .860, 1.301),
                                      ('2026-11-01-hdmi-delay-cold-validation', .954, 1.315),
                                      ('2026-11-01-hdmi-zero-cold-validation', .861, 1.307)):
            with self.subTest(run=name):
                d = RECOVERY / name
                kernel = json.loads((d / 'POSTBOOT.json').read_text())['kernel_all']['stdout']
                t = R.timing(d / 'host-hdmi-01/events.jsonl', d / 'uart-01/serial-timestamped.log', kernel)
                self.assertAlmostEqual(t['ready_to_connected'], connected, delta=.03)
                self.assertAlmostEqual(t['ready_to_lock'], lock, delta=.002)

    def test_uart_summary_of_real_cold_run(self):
        s = R.uart_summary(RECOVERY / '2026-11-01-hdmi-zero-cold-validation/uart-01/serial-timestamped.log')
        self.assertEqual((len(s['spl']), len(s['power_down']), s['disconnects']), (1, 1, 0))
        self.assertTrue(s['login'] and s['spl'][0] - s['power_down'][0] > 60)

    def test_failed_boot_has_no_lock(self):
        kernel = json.loads((RECOVERY / '2026-11-01-board-boot-uart/board-readonly.json').read_text())['kernel_hdmi_log']
        self.assertIsNone(R.kernel_time(kernel, r'h713-hdmi-v4l2: signal locked'))
        self.assertIsNotNone(R.kernel_time(kernel, r'EDID and HPD ready'))

    def test_sealed_pins_load(self):
        pins = R.load_pins()
        self.assertEqual((len(pins['file_pins']), len(pins['runtime_hashes']), len(pins['storage'])), (56, 5, 10))

    def test_real_uevent_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'u.log'
            p.write_text('monitor will print the received events for:\nKERNEL - the kernel uevent\n\n'
                         'KERNEL[8551.649691] change   /devices/pci0000:00/0000:0c:00.0/drm/card1 (drm)\n'
                         'ACTION=change\nHOTPLUG=1\nSUBSYSTEM=drm\n\n')
            u = R.uevents(p, 'x')
            self.assertEqual((u['drm_events'], u['hotplug_properties'], u['first_monotonic']), (1, 1, 8551.649691))
            self.assertEqual(R.uevents(Path(tmp) / 'absent', 'x')['drm_events'], 0)


class Conclusions(unittest.TestCase):
    BANK = {'edid_ram': 'RETAINED'}

    def test_each_outcome(self):
        self.assertIn('refuted', R.classify(True, True, True, self.BANK))
        self.assertIn('INVALID', R.classify(True, False, True, self.BANK))
        self.assertIn('INVALID', R.classify(False, False, False, self.BANK))
        self.assertIn('toward host state', R.classify(False, False, True, self.BANK))
        self.assertIn('unseparated', R.classify(False, False, True, {'edid_ram': 'LOST'}))
        self.assertIn('Preserve', R.classify(False, False, True, {'edid_ram': 'PARTIAL'}))


class Fake:
    """Simulates host time, DRM, recorders and ssh for the whole stage sequence."""

    def __init__(self, tmp):
        self.dir = Path(tmp) / 'run'
        self.host = HOST_A
        self.hdmi = dict(status='connected', enabled='enabled', edid_bytes=256, edid_sha256=R.EDID_SHA256)
        self.board_calls = []
        self.boots = [HOST_A]
        self.journal = ''
        self.ended = 'systemd-logind[1]: reboot requested from client PID 1\n'
        self.detect = True
        self.s0 = sram(0x11).hex()
        self.s1 = sram(0x11).hex()
        self.t0 = time.time()
        self.power_down = None
        self.mono = 1000.0

    def boards(self, script, timeout=180):
        mode = script[script.index("'mode': '") + 9:].split("'")[0]
        self.board_calls.append(mode)
        if mode == 'preflight':
            out = dict(boot_id=BOOT, signal='locked 1280x720', ext4_kernel_lines=[],
                       sram=dict(sram_hex=self.s0, bank_backup_sha256='s0'))
        elif mode == 'poweroff':
            self.power_down = time.time()
            self.line('uart-pre', "b'[ 1550.2] reboot: Power down\\r\\n'")
            self.hdmi = dict(status='disconnected', enabled='disabled', edid_bytes=0, edid_sha256=R.EMPTY_SHA256)
            return subprocess.CompletedProcess([], 255, 'ISSUING_ONE_ORDINARY_SYSTEMCTL_POWEROFF\n', '')
        else:
            journal = '\\"delay_ms\\": 0 x \\"delay_ms\\": 0'
            kernel = '[ 23.2] h713-hdmi-signal: EDID and HPD ready\n' + ('[ 24.5] h713-hdmi-v4l2: signal locked 1280x720\n' if self.detect else '')
            out = dict(boot_id=NEXT, signal='locked 1280x720' if self.detect else 'none', sram=dict(sram_hex=self.s1),
                       pin_failures=[], runtime_failures=[], storage_checks={'a': True}, cid_matches=True,
                       kernel_notes_match=True, parameters={'h713_hdmi_signal.ready': 'Y', 'h713_hdmi_signal.failed': 'N'},
                       loaded_commands='start --bench-delay-ms=0 --x', signal_journal_json={'stdout': journal},
                       kernel_all=kernel, previous_boot_signal_journal={'stdout': 'and DDC ownership restored'})
        return subprocess.CompletedProcess([], 0, json.dumps(out), '')

    def line(self, phase, text):
        with (self.dir / phase / 'serial-timestamped.log').open('a') as f:
            f.write('%s %s\n' % (R.datetime.fromtimestamp(time.time(), R.timezone.utc).isoformat(), text))

    def recorders(self, run, phase):
        for kind in ('uart', 'hdmi'):
            (self.dir / (kind + '-' + phase)).mkdir(exist_ok=True)
        (self.dir / ('uart-' + phase) / 'serial-timestamped.log').touch()
        self.event(phase, 'initial')

    def event(self, phase, label):
        with (self.dir / ('hdmi-' + phase) / 'events.jsonl').open('a') as f:
            f.write(json.dumps(dict(host_utc=R.utc(), host_monotonic_ns=1, phase=label, snapshot=dict(ok=True, **self.hdmi))) + '\n')

    def stop(self, phase):
        self.line('uart-' + phase, 'CAPTURE STOP')

    def subprocess_run(self, args, **kw):
        if args[:2] == ['journalctl', '--list-boots']:
            return subprocess.CompletedProcess(args, 0, json.dumps([dict(boot_id=b.replace('-', '')) for b in self.boots]), '')
        if args[:1] == ['journalctl']:
            previous = args[2] != '--no-pager'
            return subprocess.CompletedProcess(args, 0, self.ended if previous else self.journal, '')
        raise AssertionError('unexpected command: %r' % (args,))


class Stages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fake(self.tmp.name)
        self.run_ = R.Run(self.f.dir)
        self.patches = [patch.object(R, n, v) for n, v in {
            'on_board': self.f.boards, 'host_boot': lambda: self.f.host, 'cached_hdmi': lambda: dict(self.f.hdmi),
            'start_recorders': self.f.recorders, 'stop_recorders': self.f.stop,
            'verify_recorders': lambda run, phase: {'cached_hdmi': self.f.hdmi},
            'load_pins': lambda: {'file_pins': {}, 'runtime_hashes': {}}, 'host_journal': lambda: [],
        }.items()]
        self.patches.append(patch.object(R.subprocess, 'run', self.f.subprocess_run))
        real_sleep = time.sleep
        self.patches.append(patch.object(R.time, 'sleep', lambda s: real_sleep(0)))
        self.patches.append(patch('builtins.print'))
        for p in self.patches:
            p.start()
        self.args = type('A', (), dict(supply_removed=True, wait=5))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def stage(self, name):
        if self.f.dir.is_dir():
            self.run_.begin(name)
        getattr(R, 'stage_' + name.replace('-', '_'))(self.run_, self.args)

    def to_powered_off(self):
        for name in ('arm-pre', 'preflight', 'poweroff'):
            self.stage(name)

    def reboot_host(self):
        self.f.host = HOST_B
        self.f.boots.append(HOST_B)

    def age_power_down(self, seconds):
        receipt = self.run_.receipt('poweroff')
        value = json.loads(receipt.read_text())
        value['power_down_utc'] = time.time() - seconds
        receipt.write_text(json.dumps(value))
        return value['power_down_utc']

    def boot_board(self, off_seconds=500):
        spl = self.run_.load('poweroff')['power_down_utc'] + off_seconds
        stamp = R.datetime.fromtimestamp(spl, R.timezone.utc).isoformat()
        (self.f.dir / 'uart-post/serial-timestamped.log').write_text(stamp + " b'U-Boot SPL 2026'\n")
        self.f.line('uart-post', "b'h713-arm64 login: root'")

    def to_ready(self):
        self.to_powered_off()
        self.reboot_host()
        self.stage('arm-post')
        self.age_power_down(500)
        self.stage('ready')
        ready = self.run_.load('ready')
        self.assertEqual(ready['power_on_by_utc'], self.run_.load('poweroff')['power_down_utc'] + R.MAX_OFF_SECONDS)

    def finish(self, detect):
        self.f.detect = detect
        self.boot_board()
        if detect:
            self.f.hdmi = dict(status='connected', enabled='enabled', edid_bytes=256, edid_sha256=R.EDID_SHA256)
            self.f.event('post', 'change')
        else:
            with patch.object(R, 'AFTER_LOGIN_WINDOW_SECONDS', 0):
                self.stage('observe')
            self.stage('collect')
            self.stage('analyze')
            return self.run_.load('analyze')
        self.stage('observe')
        self.stage('collect')
        self.stage('analyze')
        return self.run_.load('analyze')

    def assertRefused(self, name, text=''):
        with self.assertRaises(SystemExit) as caught:
            self.stage(name)
        self.assertIn(text, str(caught.exception))

    def test_order_is_enforced(self):
        self.f.dir.mkdir()
        self.assertRefused('preflight', 'arm-pre')
        self.stage('arm-pre')
        self.assertRefused('poweroff', 'preflight')
        self.assertRefused('arm-pre', 'single-use')

    def test_full_detected_run(self):
        self.to_ready()
        result = self.finish(True)
        self.assertEqual(self.f.board_calls, ['preflight', 'poweroff', 'collect'])
        self.assertTrue(result['detected'])
        self.assertIn('refuted', result['conclusion'])
        self.assertEqual(result['edid_bank_comparison']['edid_ram'], 'RETAINED')
        self.assertTrue(all(result['checks'].values()), result['checks'])
        self.stage('close')
        self.assertTrue((self.f.dir / 'SHA256SUMS').exists())

    def test_full_not_detected_run_changes_nothing_on_the_board(self):
        self.to_ready()
        changed = bytearray(sram(0x11))
        changed[0x4780] ^= 0xff
        changed[0x4880:0x4a80] = bytes(x ^ 0x0f for x in changed[0x4880:0x4a80])
        self.f.s1 = changed.hex()
        result = self.finish(False)
        self.assertEqual(self.f.board_calls, ['preflight', 'poweroff', 'collect'])
        self.assertFalse(result['detected'])
        self.assertIn('NOT DETECTED', result['conclusion'])
        self.assertIn('unseparated', result['conclusion'])
        self.assertTrue(self.run_.load('observe')['contacted_board'] is False)

    def test_failed_match_invalidates_rather_than_concludes(self):
        self.to_powered_off()
        self.reboot_host()
        self.stage('arm-post')
        self.age_power_down(500)
        self.stage('ready')
        self.f.detect = False
        self.f.line('uart-post', "b'U-Boot SPL'")
        self.f.line('uart-post', "b'U-Boot SPL'")
        self.f.line('uart-post', "b'h713-arm64 login: root'")
        with patch.object(R, 'AFTER_LOGIN_WINDOW_SECONDS', 0):
            self.stage('observe')
        self.stage('collect')
        self.stage('analyze')
        self.assertIn('INVALID', self.run_.load('analyze')['conclusion'])

    def test_arm_post_needs_a_real_host_reboot(self):
        self.to_powered_off()
        self.assertRefused('arm-post', 'not rebooted')

    def test_arm_post_needs_exactly_one_reboot(self):
        self.to_powered_off()
        self.f.host = HOST_B
        self.f.boots += ['cccccccc-0000-4000-8000-000000000003', HOST_B]
        self.assertRefused('arm-post', 'exactly one')

    def test_arm_post_refuses_a_host_poweroff(self):
        self.to_powered_off()
        self.reboot_host()
        self.f.ended = 'systemd-logind[1]: poweroff requested from client PID 1\n'
        self.assertRefused('arm-post', 'warm reboot only')

    def test_arm_post_refuses_a_reboot_after_a_poweroff_request(self):
        self.to_powered_off()
        self.reboot_host()
        self.f.ended = 'poweroff requested from client\nreboot requested from client\n'
        self.assertRefused('arm-post', 'warm reboot only')

    def test_arm_post_refuses_an_unrequested_restart(self):
        self.to_powered_off()
        self.reboot_host()
        self.f.ended = 'no shutdown request: a crash or a reset\n'
        self.assertRefused('arm-post', 'warm reboot only')

    def test_arm_post_needs_the_operator_confirmation(self):
        self.to_powered_off()
        self.reboot_host()
        self.args.supply_removed = False
        self.assertRefused('arm-post', 'supply-removed')

    def test_arm_post_refuses_an_earlier_connect_this_host_boot(self):
        self.to_powered_off()
        self.reboot_host()
        self.f.journal = 'x wireplumber[1]: s-monitors: HDMI connected: showing H713 HDMI IN\n'
        self.assertRefused('arm-post', 'not a first advert')

    def test_arm_post_refuses_a_connected_host(self):
        self.to_powered_off()
        self.reboot_host()
        self.f.hdmi['status'] = 'connected'
        self.assertRefused('arm-post', 'not disconnected')

    def test_ready_enforces_the_off_window(self):
        self.to_powered_off()
        self.reboot_host()
        self.stage('arm-post')
        self.age_power_down(100)
        self.assertRefused('ready', 'wait')
        self.age_power_down(R.MAX_OFF_SECONDS + 10)
        self.assertRefused('ready', 'match is lost')

    def test_ready_refuses_a_board_that_already_started(self):
        self.to_powered_off()
        self.reboot_host()
        self.stage('arm-post')
        self.age_power_down(500)
        self.f.line('uart-post', "b'U-Boot SPL'")
        self.assertRefused('ready', 'invalid')

    def test_poweroff_is_one_attempt(self):
        self.stage('arm-pre')
        self.stage('preflight')
        (self.f.dir / 'POWEROFF-INTENT.json').write_text('{}')
        self.assertRefused('poweroff', 'already attempted')
        self.assertNotIn('poweroff', self.f.board_calls)

    def test_poweroff_stale_preflight(self):
        self.stage('arm-pre')
        self.stage('preflight')
        with patch.object(R, 'PREFLIGHT_MAX_AGE_SECONDS', -1):
            self.assertRefused('poweroff', 'stale')
        self.assertNotIn('poweroff', self.f.board_calls)

    def test_poweroff_without_uart_marker_tells_the_operator_to_wait(self):
        self.stage('arm-pre')
        self.stage('preflight')

        def silent(script, timeout=180):
            return subprocess.CompletedProcess([], 255, 'ISSUING_ONE_ORDINARY_SYSTEMCTL_POWEROFF\n', '')
        with patch.object(R, 'on_board', silent):
            self.args.wait = 0
            self.assertRefused('poweroff', 'do not remove power')

    def test_observe_never_contacts_the_board(self):
        self.to_ready()
        before = list(self.f.board_calls)
        self.boot_board()
        with patch.object(R, 'AFTER_LOGIN_WINDOW_SECONDS', 0):
            self.stage('observe')
        self.assertEqual(self.f.board_calls, before)


class Static(unittest.TestCase):
    def test_only_expected_board_commands(self):
        import ast
        tree = ast.parse((TARGET / 'board_script.py').read_text())
        firsts = set()
        for node in ast.walk(tree):
            candidates = []
            if isinstance(node, ast.Call) and node.args:
                candidates.append(node.args[0])
            if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'args':
                candidates.append(node.value)
            for item in candidates:
                if isinstance(item, ast.List) and item.elts and isinstance(item.elts[0], ast.Constant):
                    firsts.add(item.elts[0].value)
        self.assertEqual(firsts, {'findmnt', 'systemctl', 'dmesg', 'journalctl', 'sync'})

    def test_writes_are_one_exclusive_receipt(self):
        source = (TARGET / 'board_script.py').read_text()
        self.assertEqual(source.count('O_CREAT'), 1)
        self.assertEqual(source.count('O_EXCL'), 1)
        for forbidden in ('write_text', 'write_bytes', 'PROT_WRITE', 'O_RDWR', "'w+'", 'rmmod', 'insmod', "'reboot'", '/stop', '/release'):
            self.assertNotIn(forbidden, source)

    def test_host_never_forces_detection(self):
        source = (TARGET / 'run.py').read_text()
        for forbidden in ('modetest', 'nvidia-smi', '/dev/nvidia', 'dri/card', "'detect'", 'nmcli', "'reboot'"):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    result = unittest.main(exit=False, verbosity=0).result
    print('ran %d tests, %d failures, %d errors, %d skipped' % (result.testsRun, len(result.failures), len(result.errors), len(result.skipped)))
    sys.exit(not result.wasSuccessful())
