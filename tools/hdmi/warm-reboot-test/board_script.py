"""Board side of the warm-reboot repeat. Sent over ssh stdin; nothing is stored on the board.

The host prepends CONFIG. Modes: preflight and collect only read. poweroff adds one
exclusive receipt and one `systemctl poweroff`, after every preflight gate passes again.
Never maps the receiver window 0x07091000-0x07091fff or 0x06940000.
"""
from pathlib import Path
import glob
import hashlib
import json
import mmap
import os
import stat
import struct
import subprocess

ROOT = Path(CONFIG.get('root', '/'))
SRAM_BASE, SRAM_SIZE = 0x100000, 0x5000
SCALARS = (0x07000400, 0x07022004)  # SCP reset control, PL8-PL15 mux
BANKS = (0x4780, 0x4a80)  # the SCP's backup of the three EDID banks at entry
MARKER = 0x48444d49
DIAGNOSTICS = ('h713_scp_sampler_v2', 'h713_scp_probe', 'h713_hdmi_dsp_probe')
UNITS = ('capture', 'signal', 'ring', 'speaker', 'video')
RECEIPT_DIR = '/var/backups/h713-hdmi-zero-control-20261101-01'
RECEIPT = RECEIPT_DIR + '/warm-reboot-poweroff-request.json'
DROPIN = '/etc/systemd/system/h713-hdmi-signal.service.d/90-start-delay.conf'
BENCH = '/usr/lib/h713-hdmi-delay-bench'


def path(name):
    return ROOT / name.lstrip('/')


def text(name):
    return path(name).read_text().strip('\0\n')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(args, timeout=20):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}


def physical(address, size):
    """Read-only mapped load, limited to SCP SRAM and the two established scalars."""
    in_sram = SRAM_BASE <= address and address + size <= SRAM_BASE + SRAM_SIZE
    require(in_sram or (address in SCALARS and size == 4), 'address not allowed: ' + hex(address))
    fd = os.open(path('/dev/mem'), os.O_RDONLY | os.O_SYNC | os.O_CLOEXEC)
    try:
        base = address & ~4095
        length = ((address - base + size + 4095) // 4096) * 4096
        with mmap.mmap(fd, length, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ, offset=base) as view:
            data = view[address - base:address - base + size]
    finally:
        os.close(fd)
    require(len(data) == size, 'short physical read')
    return data


def sram_snapshot():
    data = physical(SRAM_BASE, SRAM_SIZE)
    words = struct.unpack_from('<32I', data, 0x4f00)
    return {
        'sram_hex': data.hex(),
        'sram_sha256': hashlib.sha256(data).hexdigest(),
        'bank_backup_sha256': hashlib.sha256(data[BANKS[0]:BANKS[1]]).hexdigest(),
        'marker': {'marker': words[0], 'ready': words[2], 'exception': words[3], 'stop': words[4],
                   'backup': words[5], 'error': words[6], 'done': words[7]},
        'scp_reset_control': struct.unpack('<I', physical(SCALARS[0], 4))[0],
        'ddc_mux': struct.unpack('<I', physical(SCALARS[1], 4))[0] >> 8,
    }


def pin_failures():
    failures = []
    for name, pin in CONFIG['file_pins'].items():
        try:
            p = path(name)
            info = p.lstat()
            ok = (stat.S_ISREG(info.st_mode) and
                  (info.st_size, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) ==
                  (pin['bytes'], pin['mode'], pin['uid'], pin['gid']) and
                  hashlib.sha256(p.read_bytes()).hexdigest() == pin['sha256'])
        except OSError:
            ok = False
        if not ok:
            failures.append(name)
    return failures


def runtime_failures():
    failures = []
    for name, digest in CONFIG['runtime_hashes'].items():
        try:
            if hashlib.sha256(path(BENCH + '/' + name).read_bytes()).hexdigest() != digest:
                failures.append(name)
        except OSError:
            failures.append(name)
    return failures


def storage_checks():
    checks = {}
    fd = os.open(path('/dev/mmcblk0'), os.O_RDONLY | os.O_CLOEXEC)
    try:
        for region in CONFIG['storage']:
            data = os.pread(fd, region['bytes'], region['offset'])
            checks[region['name']] = (len(data) == region['bytes'] and
                                      hashlib.sha256(data).hexdigest() == region['sha256'])
    finally:
        os.close(fd)
    return checks


def filesystem():
    mount = run(['findmnt', '-no', 'SOURCE,FSTYPE,OPTIONS', '/'])['stdout'].split()
    counts = {}
    for name in glob.glob(str(path('/sys/fs/ext4')) + '/*/errors_count'):
        counts[Path(name).parent.name] = Path(name).read_text().strip()
    return {'mount': mount, 'errors_count': counts}


def unit_show(unit, *properties):
    args = ['systemctl', 'show', unit]
    for name in properties:
        args += ['-p', name]
    return run(args)['stdout']


def loaded_commands():
    return unit_show('h713-hdmi-signal.service', 'ExecStart', 'ExecStop', 'DropInPaths')


def state():
    params = {}
    for module, names in {
            'h713_hdmi_signal': ('ready', 'failed', 'restored', 'recovery'),
            'h713_hdmi_receiver': ('clock_count', 'clients', 'edid_ready', 'init_error'),
            'h713_hdmi_audio': ('graph_ready', 'dsp_failed'),
            'h713_hdmi_v4l2': ('sig_transitions', 'sig_bad_guard', 'frames_produced',
                               'frames_delivered', 'frames_rejected', 'afbd_invalid')}.items():
        for name in names:
            p = '/sys/module/%s/parameters/%s' % (module, name)
            params[module + '.' + name] = text(p) if path(p).exists() else None
    session = path('/run/h713-hdmi-session/state.json')
    return {
        'boot_id': text('/proc/sys/kernel/random/boot_id'),
        'uptime': text('/proc/uptime'),
        'signal': text('/sys/devices/platform/h713-hdmi-ring/signal'),
        'parameters': params,
        'session': json.loads(session.read_text()) if session.exists() else None,
        'services': {u: unit_show('h713-hdmi-%s.service' % u, 'ActiveState', 'SubState', 'Result', 'NRestarts')
                     for u in UNITS},
        'system_state': run(['systemctl', 'is-system-running'])['stdout'].strip(),
        'loaded_commands': loaded_commands(),
        'dropin_sha256': hashlib.sha256(path(DROPIN).read_bytes()).hexdigest() if path(DROPIN).exists() else None,
        'filesystem': filesystem(),
    }


def identity_gates():
    require(text('/proc/device-tree/model') == 'HY200 QZ713DF_A1 (Allwinner H713)', 'board model')
    require(text('/sys/class/block/mmcblk0/device/cid') == CONFIG['cid'], 'board eMMC identity')
    require(hashlib.sha256(path('/sys/kernel/notes').read_bytes()).hexdigest() == CONFIG['kernel_notes_sha256'],
            'kernel changed')
    for module in DIAGNOSTICS:
        require(not path('/sys/module/' + module).exists(), 'diagnostic owner present: ' + module)


def live_gates(r):
    p = r['parameters']
    require(r['signal'].startswith('locked'), 'HDMI not locked: ' + r['signal'])
    require(r['session'] == {'boot_id': r['boot_id'], 'phase': 'ready'}, 'session not ready on this boot')
    for key, value in (('ready', 'Y'), ('failed', 'N'), ('restored', 'N')):
        require(p['h713_hdmi_signal.' + key] == value, 'signal owner state: ' + key)
    require(p['h713_hdmi_audio.graph_ready'] == 'Y', 'graph not ready')
    for name in ('owned', 'attempted'):
        require(path('/run/h713-hdmi-signal/' + name).is_file(), 'ownership latch missing: ' + name)
    for unit in ('capture', 'signal', 'ring', 'speaker'):
        require('ActiveState=active' in r['services'][unit], 'service not active: ' + unit)
    require(r['dropin_sha256'] == CONFIG['dropin_sha256'], '0 ms override changed')
    commands = r['loaded_commands']
    require(BENCH + '/h713-hdmi-signal.py start' in commands and '--bench-delay-ms=0 ' in commands,
            'loaded ExecStart is not the 0 ms bench')
    require('/usr/lib/h713-hdmi/h713-hdmi-signal.py stop' in commands, 'loaded ExecStop is not production')
    fs = r['filesystem']
    require(len(fs['mount']) == 3 and fs['mount'][1] == 'ext4' and fs['mount'][2].split(',')[0] == 'rw',
            'root filesystem is not ext4 rw')
    require(fs['errors_count'] and all(v == '0' for v in fs['errors_count'].values()), 'ext4 errors recorded')
    failures = pin_failures()
    require(not failures, 'file pins changed: ' + ','.join(failures))
    failures = runtime_failures()
    require(not failures, 'bench runtime changed: ' + ','.join(failures))
    checks = storage_checks()
    require(all(checks.values()), 'protected storage changed')
    return checks


def sram_gates(snapshot):
    m = snapshot['marker']
    require(m['marker'] == MARKER and m['ready'] == MARKER and m['backup'] == MARKER, 'SCP markers')
    require(not (m['exception'] or m['error'] or m['stop'] or m['done']), 'SCP not in its wait state')
    require(snapshot['scp_reset_control'] & 1, 'SCP not running')
    require(snapshot['ddc_mux'] == 0x222222, 'DDC mux')


def preflight():
    identity_gates()
    r = state()
    r['storage_checks'] = live_gates(r)
    r['sram'] = sram_snapshot()
    sram_gates(r['sram'])
    r['ext4_kernel_lines'] = [line for line in run(['dmesg', '--color=never'])['stdout'].splitlines()
                              if 'EXT4-fs' in line]
    return r


def poweroff():
    identity_gates()
    r = state()
    require(r['boot_id'] == CONFIG['expected_boot'], 'boot changed since preflight')
    live_gates(r)
    snapshot = sram_snapshot()
    sram_gates(snapshot)
    require(snapshot['bank_backup_sha256'] == CONFIG['s0_bank_sha256'], 'bank backups changed since preflight')
    require(path(RECEIPT_DIR).is_dir(), 'backup directory missing')
    receipt = {'status': 'PREFLIGHT_PASS_ONE_ORDINARY_POWEROFF', 'expected_boot_id': r['boot_id'],
               'maximum_poweroffs': 1, 'next_boot_control_delay_ms': 0,
               'method': 'sync then systemctl poweroff', 'experiment': 'warm-reboot-first-advert'}
    fd = os.open(path(RECEIPT), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(receipt, f, sort_keys=True, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps(receipt, sort_keys=True), flush=True)
    subprocess.run(['sync'], check=True, timeout=20)
    require(text('/proc/sys/kernel/random/boot_id') == r['boot_id'], 'boot changed before dispatch')
    print('ISSUING_ONE_ORDINARY_SYSTEMCTL_POWEROFF', flush=True)
    subprocess.run(['systemctl', 'poweroff'], check=True, timeout=20)
    return None


def collect():
    """Report, never gate on, the state: a failed detection must be recorded as it is."""
    for module in DIAGNOSTICS:
        require(not path('/sys/module/' + module).exists(), 'diagnostic owner present: ' + module)
    r = state()
    require(r['boot_id'] != CONFIG['previous_boot'], 'board did not boot again')
    r['model'] = text('/proc/device-tree/model')
    r['cid_matches'] = text('/sys/class/block/mmcblk0/device/cid') == CONFIG['cid']
    r['kernel_notes_match'] = (hashlib.sha256(path('/sys/kernel/notes').read_bytes()).hexdigest() ==
                               CONFIG['kernel_notes_sha256'])
    r['pin_failures'] = pin_failures()
    r['pins_total'] = len(CONFIG['file_pins'])
    r['runtime_failures'] = runtime_failures()
    r['storage_checks'] = storage_checks()
    r['sram'] = sram_snapshot()
    r['kernel_all'] = run(['dmesg', '--color=never'])['stdout']
    r['signal_journal_json'] = run(['journalctl', '-b', '-u', 'h713-hdmi-signal.service', '--no-pager', '-o', 'json'])
    # By id: `-b -1` returned this boot's own lines in the earlier run (S1 of board boot b3cf2171).
    r['previous_boot_signal_journal'] = run(['journalctl', '-b', CONFIG['previous_boot'].replace('-', ''), '-u', 'h713-hdmi-signal.service', '--no-pager'])
    r['boot_id_end'] = text('/proc/sys/kernel/random/boot_id')
    require(r['boot_id'] == r['boot_id_end'], 'boot changed during collection')
    return r


result = {'preflight': preflight, 'poweroff': poweroff, 'collect': collect}[CONFIG['mode']]()
if result is not None:
    print(json.dumps(result, sort_keys=True))
