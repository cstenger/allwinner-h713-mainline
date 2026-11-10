#!/usr/bin/env python3
"""Read-only live preconditions used by the finalized migration transaction."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import stat
import struct
import subprocess


def require(value,reason):
    if not value:raise ValueError(reason)


def validate_identity(actual,manifest,expected_boot_id):
    require(manifest.get('finalized') is True and manifest.get('offline_only') is False,'live-finalized package required')
    pinned=manifest['live_identity']
    require(expected_boot_id==pinned['boot_id'],'explicit expected boot does not match pinned collection')
    for key in ['model','boot_id','cid','type','dev_number','capacity_bytes','logical_sector_bytes','linux_hardware_partition']:
        require(actual[key]==pinned[key],'live identity mismatch: '+key)
    require(not actual['reserved_partition_mounted'],'reserved partition is mounted')
    require(not actual['reserved_partition_holders'],'reserved partition has holders')


def check_board(manifest,expected_boot_id,fd=None):
    root=Path('/sys/class/block/mmcblk0')
    text=lambda p:Path(p).read_text().strip('\0\n')
    require(text('/proc/device-tree/model')=='HY200 QZ713DF_A1 (Allwinner H713)','wrong board model')
    own=fd is None
    if own:fd=os.open('/dev/mmcblk0',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd);require(stat.S_ISBLK(info.st_mode),'live preflight requires block device')
        require(info.st_rdev==os.stat('/dev/mmcblk0').st_rdev,'opened device is not eMMC user device')
        capacity=struct.unpack('<Q',fcntl.ioctl(fd,0x80081272,bytes(8)))[0]
        sector=struct.unpack('<I',fcntl.ioctl(fd,0x1268,bytes(4)))[0]
        reserved=Path('/sys/class/block/mmcblk0p18')
        rdev=text(reserved/'dev')
        actual=dict(model=text('/proc/device-tree/model'),boot_id=text('/proc/sys/kernel/random/boot_id'),
                    cid=text(root/'device/cid'),type=text(root/'device/type'),
                    dev_number=f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}',
                    capacity_bytes=capacity,logical_sector_bytes=sector,linux_hardware_partition='user',
                    reserved_partition_mounted=any(line.split()[2]==rdev for line in Path('/proc/self/mountinfo').read_text().splitlines()),
                    reserved_partition_holders=[p.name for p in (reserved/'holders').iterdir()])
        validate_identity(actual,manifest,expected_boot_id)
        for region in manifest['protected']:
            data=os.pread(fd,region['bytes'],region['offset'])
            require(len(data)==region['bytes'] and hashlib.sha256(data).hexdigest()==region['sha256'],
                    'protected storage mismatch: '+region['name'])
        for name,item in manifest['file_pins'].items():
            path=Path(name);s=path.stat();data=path.read_bytes()
            require(len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'], 'installed file drift: '+name)
            require(stat.S_IMODE(s.st_mode)==item['mode'] and s.st_uid==item['uid'] and s.st_gid==item['gid'], 'installed metadata drift: '+name)
        names=['h713-hdmi-'+name+'.service' for name in ['capture','signal','ring','video','speaker','health-ack']]
        service=subprocess.run(['systemctl','show',*names,'-p','Id','-p','ActiveState','-p','SubState','-p','NRestarts','-p','ExecMainStartTimestampMonotonic'],capture_output=True,text=True,check=True,timeout=20)
        require(service.stdout==manifest['service_pins'],'service state/start identities changed')
        for name,value in manifest['runtime_pins'].items():
            current=Path(name).read_bytes().hex() if 'boot-v1' in name else text(name)
            require(current==value,'runtime precondition changed: '+name)
        require(json.loads(Path('/run/h713-hdmi-session/state.json').read_text())==manifest['session_pin'],'session changed')
        rtc=Path('/sys/firmware/devicetree/base/soc/rtc@7090000')
        require((rtc/'compatible').read_bytes()==b'allwinner,sun50i-h713-rtc\0','wrong RTC compatible')
        require((rtc/'reg').read_bytes()==bytes.fromhex('0709000000000400'),'wrong RTC range')
        providers=[p for p in Path('/sys/bus/nvmem/devices').iterdir() if (p/'of_node').resolve()==rtc.resolve()]
        require(len(providers)==1,'RTC nvmem ambiguous')
        require((providers[0].resolve().parent/'driver').resolve().name=='sun6i-rtc','wrong RTC driver')
        nfd=os.open(providers[0]/'nvmem',os.O_RDONLY|os.O_CLOEXEC)
        try:
            require(os.fstat(nfd).st_size==32,'wrong RTC nvmem size')
            require(os.pread(nfd,8,0x18).hex()==manifest['latch_pin'],'startup/reboot latches changed')
        finally:os.close(nfd)
        fs=subprocess.run(['dumpe2fs','-h','/dev/mmcblk0p26'],capture_output=True,text=True,check=True,timeout=20)
        fields=dict(line.split(':',1) for line in fs.stdout.splitlines() if ':' in line)
        require(fields.get('Filesystem state','').strip()=='clean','root filesystem state is not clean')
        require(int(fields.get('FS Error count',fields.get('Error count','0')).strip())==0,'root filesystem errors recorded')
        require(text('/proc/sys/kernel/random/boot_id')==expected_boot_id,'boot changed during preflight')
        kernel=subprocess.run(['dmesg','--color=never'],capture_output=True,text=True,check=True,timeout=20)
        require('EXT4-fs error' not in kernel.stdout,'ext4 error in current boot log')
        rootmount=subprocess.run(['findmnt','-rn','-o','SOURCE,FSTYPE,OPTIONS','/'],capture_output=True,text=True,check=True,timeout=20)
        require(rootmount.stdout==manifest['live_identity']['root_mount']['stdout'],'root mount changed')
        return dict(result='PASS live identity/protected storage/files/services/runtime preflight',
                    boot_id=expected_boot_id,cid_sha256=hashlib.sha256(actual['cid'].encode()).hexdigest(),
                    protected_ranges=len(manifest['protected']),files_verified=len(manifest['file_pins']),board_writes=False)
    finally:
        if own:os.close(fd)
