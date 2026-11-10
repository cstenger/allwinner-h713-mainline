#!/usr/bin/env python3
"""Read-only target collector. Stream private tar to stdout, create no target files.

Run via python3 -B - over SSH. Opens the eMMC user device O_RDONLY only;
reads documented boot slots, GPT/identity, FAT and health. No MMIO or writes.
"""
from pathlib import Path
import fcntl
import hashlib
import io
import json
import os
import stat
import struct
import subprocess
import sys
import tarfile
import time


def text(path):
    return Path(path).read_text().strip('\0\n')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=20)
    return dict(argv=args,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)


def main():
    boot=text('/proc/sys/kernel/random/boot_id')
    model=text('/proc/device-tree/model')
    if model!='HY200 QZ713DF_A1 (Allwinner H713)':raise ValueError('unexpected board model')
    device=Path('/dev/mmcblk0');sysblock=Path('/sys/class/block/mmcblk0')
    if text(sysblock/'device/type')!='MMC':raise ValueError('target is not eMMC')
    fd=os.open(device,os.O_RDONLY|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if not stat.S_ISBLK(info.st_mode):raise ValueError('target is not a block device')
        capacity=struct.unpack('<Q',fcntl.ioctl(fd,0x80081272,bytes(8)))[0]
        sector=struct.unpack('<I',fcntl.ioctl(fd,0x1268,bytes(4)))[0]
        if capacity!=7818182656 or sector!=512:raise ValueError('unexpected device geometry')
        identity=dict(model=model,boot_id=boot,device=str(device),capacity_bytes=capacity,
                      logical_sector_bytes=sector,linux_hardware_partition='user',
                      dev_number=f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}',
                      sysfs_device=str((sysblock/'device').resolve()),
                      root_mount=command(['findmnt','-rn','-o','SOURCE,FSTYPE,OPTIONS','/']))
        for name in ['cid','csd','name','manfid','oemid','serial','hwrev','fwrev','type']:
            path=sysblock/'device'/name
            identity[name]=text(path) if path.exists() else None
        identity['sysfs_sector_count']=int(text(sysblock/'size'))
        identity['sysfs_read_only']=text(sysblock/'ro')
        partitions=[]
        for path in sorted(sysblock.parent.glob('mmcblk0p*')):
            if (path/'partition').exists():
                partitions.append(dict(device=path.name,number=int(text(path/'partition')),
                                       start_lba=int(text(path/'start')),sectors=int(text(path/'size'))))
        inventory=dict(schema='h713-migration-live-v1',identity=identity,partitions=partitions,
                       start_monotonic=time.monotonic(),ranges={})
        inventory['mounts']=command(['findmnt','-rn','-o','SOURCE,TARGET,FSTYPE,OPTIONS'])
        inventory['reserved_partition_holders']=[p.name for p in (Path('/sys/class/block/mmcblk0p18/holders')).iterdir()]
        inventory['reserved_partition_mounts']=[line for line in inventory['mounts']['stdout'].splitlines()
                                                if line.split()[0]=='/dev/mmcblk0p18']
        with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
            def add(name,data):
                entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o600;entry.mtime=0
                archive.addfile(entry,io.BytesIO(data))
            def read_range(name,offset,size):
                if offset<0 or offset+size>capacity or size<=0 or size>40*1024*1024:
                    raise ValueError('read outside bounded collection')
                data=os.pread(fd,size,offset)
                if len(data)!=size:raise ValueError('short storage read')
                inventory['ranges'][name]=dict(offset=offset,bytes=size,sha256=digest(data))
                add(name,data)
                return data
            prefix=read_range('disk-prefix-64KiB.bin',0,65536)
            read_range('disk-suffix-64KiB.bin',capacity-65536,65536)
            header=prefix[512:1024]
            if header[:8]!=b'EFI PART':raise ValueError('missing primary GPT signature')
            entries_lba,count,entry_size=struct.unpack_from('<QII',header,72)
            if not (1<=count<=4096 and 128<=entry_size<=1024 and count*entry_size<=256*1024):
                raise ValueError('unbounded GPT entry array')
            read_range('gpt-primary-entries.bin',entries_lba*512,count*entry_size)
            last=os.pread(fd,512,capacity-512)
            if last[:8]!=b'EFI PART':raise ValueError('missing backup GPT signature')
            entries_lba2,count2,size2=struct.unpack_from('<QII',last,72)
            if count2!=count or size2!=entry_size:raise ValueError('GPT entry geometries differ')
            read_range('gpt-backup-entries.bin',entries_lba2*512,count2*size2)
            read_range('proper-region-2MiB.bin',0x49ac00*512,2*1024*1024)
            read_range('rescue-region-2MiB.bin',0x4a0c00*512,2*1024*1024)
            read_range('active-environment-64KiB.bin',0x32ec00*512,65536)
            # Surround the intended slot by 64 KiB on each side.
            read_range('intended-environment-surrounding-192KiB.bin',0x49ec00*512-65536,3*65536)
            bootpart=next(p for p in partitions if p['number']==2)
            if bootpart['sectors']!=65536:raise ValueError('unexpected boot FAT extent')
            read_range('boot-fat-32MiB.bin',bootpart['start_lba']*512,bootpart['sectors']*512)
            files={};bundles=[]
            for dirname in ['/usr/lib/h713-hdmi','/usr/lib/h713-hdmi-health',
                            '/usr/lib/h713-hdmi-video','/usr/lib/h713-hdmi-speaker']:
                base=Path(dirname)
                for path in sorted(base.rglob('*')):
                    if path.is_file() and '__pycache__' not in path.parts:
                        data=path.read_bytes();s=path.stat()
                        files[str(path)]=dict(sha256=digest(data),bytes=len(data),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
                checks=[]
                for line in (base/'SHA256SUMS').read_text().splitlines():
                    expected,name=line.split('  ',1)
                    if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe installed checksum entry')
                    checks.append(dict(name=name,expected=expected,actual=files[str(base/name)]['sha256']))
                bundles.append(dict(path=str(base/'SHA256SUMS'),checks=checks,
                                    all_match=all(c['expected']==c['actual'] for c in checks)))
            for name in ['/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard',
                         '/etc/default/h713-hdmi-speaker','/usr/local/bin/h713-play','/usr/local/bin/gst-plane-play']:
                data=Path(name).read_bytes();s=Path(name).stat()
                files[name]=dict(sha256=digest(data),bytes=len(data),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
            inventory['files']=files;inventory['bundle_checks']=bundles
            add('speaker-defaults.txt',Path('/etc/default/h713-hdmi-speaker').read_bytes())
            names=['h713-hdmi-'+name+'.service' for name in ['capture','signal','ring','video','speaker','health-ack']]
            inventory['services']=command(['systemctl','show',*names,'-p','Id','-p','ActiveState','-p','SubState',
                '-p','NRestarts','-p','ExecMainStartTimestampMonotonic'])
            inventory['filesystem']=command(['dumpe2fs','-h','/dev/mmcblk0p26'])
            inventory['kernel_log']=command(['dmesg','--color=never'])
            inventory['free_space']=command(['df','-B1','/'])
            inventory['runtime']={}
            for name in ['/sys/module/h713_hdmi_audio/parameters/period_xruns',
                         '/sys/module/h713_hdmi_v4l2/parameters/frames_rejected',
                         '/sys/module/h713_hdmi_v4l2/parameters/allow_480p',
                         '/sys/devices/platform/h713-hdmi-ring/signal',
                         '/proc/device-tree/chosen/h713,hdmi-boot-v1']:
                path=Path(name)
                inventory['runtime'][name]=path.read_bytes().hex() if 'boot-v1' in name else text(path)
            rtc=Path('/sys/firmware/devicetree/base/soc/rtc@7090000')
            if (rtc/'compatible').read_bytes()!=b'allwinner,sun50i-h713-rtc\0':raise ValueError('wrong RTC compatible')
            if (rtc/'reg').read_bytes()!=bytes.fromhex('0709000000000400'):raise ValueError('wrong RTC range')
            providers=[p for p in Path('/sys/bus/nvmem/devices').iterdir() if (p/'of_node').resolve()==rtc.resolve()]
            if len(providers)!=1:raise ValueError('RTC nvmem provider ambiguous')
            if (providers[0].resolve().parent/'driver').resolve().name!='sun6i-rtc':raise ValueError('wrong RTC driver')
            nfd=os.open(providers[0]/'nvmem',os.O_RDONLY|os.O_CLOEXEC)
            try:
                if os.fstat(nfd).st_size!=32:raise ValueError('wrong RTC nvmem size')
                latch=os.pread(nfd,8,0x18)
                if len(latch)!=8:raise ValueError('short latch read')
                inventory['latches']=dict(provider=str(providers[0]),gp6_gp7_hex=latch.hex())
            finally:os.close(nfd)
            if text('/proc/sys/kernel/random/boot_id')!=boot:raise ValueError('boot changed during collection')
            inventory['end_monotonic']=time.monotonic()
            inventory['session']=json.loads(Path('/run/h713-hdmi-session/state.json').read_text())
            inventory['ending_boot_id']=boot
            # Verify every raw captured preimage is stable across the whole collection.
            for name,item in inventory['ranges'].items():
                if digest(os.pread(fd,item['bytes'],item['offset']))!=item['sha256']:
                    raise ValueError('storage range changed during collection: '+name)
            add('inventory.json',(json.dumps(inventory,indent=2)+'\n').encode())
    finally:os.close(fd)


if __name__=='__main__':main()
