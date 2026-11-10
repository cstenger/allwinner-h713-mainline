#!/usr/bin/env python3
"""Read-only target inventory. Run via SSH stdin; create no board files.

No mounts, builds, service starts, firmware calls, MMIO, clock changes or
network configuration/credential reads. Raw storage reads are limited to
the documented bootloader ranges; only their hashes leave the board.
"""
from pathlib import Path
import datetime
import gzip
import hashlib
import json
import os
import stat
import subprocess
import time
import struct
import zlib


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(args):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=12)
        return {'argv': args, 'returncode': p.returncode,
                'stdout': p.stdout, 'stderr': p.stderr}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'argv': args, 'error': str(e)}


files = {}
text_names = {'SHA256SUMS', 'manifest.json', 'kernel.sha256', 'h713-video-stack', 'h713-hdmi-hold-guard'}
text_suffixes = {'.py', '.sh', '.c', '.service', '.conf', '.rules', '.cmd', '.json', '.glsl', '.lua', '.sha256'}


def record(p):
    p = Path(p)
    if str(p) in files:
        return
    item = {}
    files[str(p)] = item
    try:
        s = p.lstat()
        item.update(mode=oct(stat.S_IMODE(s.st_mode)), uid=s.st_uid, gid=s.st_gid,
                    size=s.st_size, mtime_epoch=s.st_mtime)
        if p.is_symlink():
            item['symlink'] = os.readlink(p)
        if p.is_file():
            data = p.read_bytes()
            item['sha256'] = sha(data)
            if (p.name in text_names or p.suffix in text_suffixes) and len(data) < 300000:
                item['text'] = data.decode('utf-8', errors='replace')
    except OSError as e:
        item['error'] = str(e)


for directory in ('/usr/lib/h713-hdmi', '/usr/lib/h713-hdmi-health',
                  '/usr/lib/h713-hdmi-video', '/usr/lib/h713-hdmi-speaker',
                  '/usr/local/share/h713'):
    p = Path(directory)
    if not p.exists():
        record(p)
    else:
        for f in sorted(p.rglob('*')):
            if f.is_file() or f.is_symlink():
                record(f)

for pattern in ('/etc/systemd/system/*h713*', '/etc/systemd/system/*h713*/*.conf',
                '/etc/systemd/system/multi-user.target.wants/*h713*',
                '/etc/udev/rules.d/*h713*', '/etc/default/h713-hdmi*',
                '/etc/systemd/timesyncd.conf.d/*', '/etc/sysctl.d/*h713*',
                '/etc/systemd/journald.conf.d/*h713*',
                '/usr/local/bin/h713-*', '/usr/local/sbin/h713-*',
                '/usr/lib/systemd/system-shutdown/*h713*',
                '/lib/modules/**/*.ko*',
                '/usr/lib/firmware/aic8800_fw/SDIO/aic8800D80/*',
                '/mnt/boot/h713*', '/var/lib/h713-hdmi-startup/*.sha256'):
    import glob
    for f in sorted(glob.glob(pattern, recursive=True)):
        record(f)

for f in ('/usr/local/bin/h713-play', '/usr/local/bin/gst-plane-play',
          '/usr/bin/mpv', '/usr/local/bin/mpv', '/usr/local/bin/mpv-direct',
          '/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so',
          '/etc/h713-video-stack', '/etc/h713-keystone.conf', '/etc/h713-mirror.conf',
          '/etc/systemd/timesyncd.conf', '/etc/adjtime', '/etc/timezone',
          '/etc/os-release', '/etc/fstab', '/etc/fw_env.config'):
    record(f)

services = ['h713-hdmi-capture', 'h713-hdmi-signal', 'h713-hdmi-ring',
            'h713-hdmi-video', 'h713-hdmi-speaker', 'h713-hdmi-health-ack',
            'systemd-timesyncd', 'chrony', 'systemd-time-wait-sync']
commands = [command(['uname', '-a']), command(['findmnt', '-rn', '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS']),
            command(['systemctl', 'show', *[s+'.service' for s in services],
                     '-p', 'Id', '-p', 'ActiveState', '-p', 'SubState', '-p', 'UnitFileState',
                     '-p', 'FragmentPath', '-p', 'DropInPaths', '-p', 'NRestarts',
                     '-p', 'ExecMainStartTimestampMonotonic']),
            command(['timedatectl', 'show']),
            command(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n']),
            command(['fw_printenv', 'bootcmd', 'preboot', 'h713_hdmi_previous_bootcmd'])]
runtime = {}
for f in ('/proc/sys/kernel/random/boot_id', '/proc/cmdline', '/proc/modules',
          '/proc/device-tree/model', '/proc/device-tree/chosen/h713,hdmi-boot-v1',
          '/sys/class/rtc/rtc0/name', '/sys/class/rtc/rtc0/date', '/sys/class/rtc/rtc0/time',
          '/sys/module/h713_hdmi_v4l2/parameters/allow_480p',
          '/sys/module/h713_hdmi_v4l2/parameters/frames_rejected',
          '/sys/module/h713_hdmi_audio/parameters/period_xruns',
          '/sys/devices/platform/h713-hdmi-ring/signal', '/run/h713-hdmi-session/state.json'):
    try:
        data = Path(f).read_bytes()
        runtime[f] = {'hex': data.hex()} if 'boot-v1' in f else data.decode(errors='replace').strip('\0\n')
    except OSError as e:
        runtime[f] = {'error': str(e)}
for f in Path('/sys/module').glob('*/srcversion'):
    try:
        runtime[str(f)] = f.read_text().strip()
    except OSError:
        pass
try:
    kernel_config = gzip.decompress(Path('/proc/config.gz').read_bytes()).decode()
except OSError:
    kernel_config = None
bootloader = {}
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    header = os.pread(fd, 40, 0x49ac00 * 512)
    magic, fit_size = struct.unpack_from('>II', header)
    assert magic == 0xd00dfeed and 40 < fit_size < 2 * 1024 * 1024
    proper_sectors = (fit_size + 511) // 512
finally:
    os.close(fd)
for name, lba, sectors in [('uboot-proper', 0x49ac00, proper_sectors), ('spl', 0x10, 64)]:
    try:
        fd = os.open('/dev/mmcblk0', os.O_RDONLY)
        try:
            data = os.pread(fd, sectors * 512, lba * 512)
        finally:
            os.close(fd)
        assert len(data) == sectors * 512
        bootloader[name] = {'device': '/dev/mmcblk0', 'lba': lba, 'sectors': sectors,
                            'sha256': sha(data), 'bytes': len(data)}
    except (OSError, AssertionError) as e:
        bootloader[name] = {'error': str(e)}
environments = {}
for name, lba in [('configured-unused', 0x49ec00), ('documented-active', 0x32ec00)]:
    fd = os.open('/dev/mmcblk0', os.O_RDONLY)
    try:
        raw = os.pread(fd, 65536, lba * 512)
    finally:
        os.close(fd)
    assert len(raw) == 65536
    valid = struct.unpack_from('<I', raw)[0] == zlib.crc32(raw[4:]) & 0xffffffff
    item = {'lba': lba, 'bytes': len(raw), 'sha256': sha(raw), 'crc_valid': valid,
            'all_zero': not any(raw)}
    if valid:
        keep = {b'bootcmd', b'preboot', b'h713_hdmi_previous_bootcmd', b'bootdelay'}
        item['selected_values'] = {line.split(b'=', 1)[0].decode(): line.split(b'=', 1)[1].decode(errors='replace')
                                   for line in raw[4:].split(b'\0') if b'=' in line and line.split(b'=', 1)[0] in keep}
    environments[name] = item
print(json.dumps({'schema': 'h713-read-only-inventory-v1',
                  'board_utc_untrusted': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'monotonic': time.monotonic(), 'files': files, 'runtime': runtime,
                  'commands': commands, 'bootloader': bootloader,
                  'boot_environments': environments,
                  'running_kernel_config': kernel_config}, indent=2))
