#!/usr/bin/env python3
"""Finalize the private migration package from a fresh read-only collection archive."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tarfile
import uuid
import zlib

ROOT=Path(__file__).resolve().parents[2]


def sha(data):return hashlib.sha256(data).hexdigest()


def require(value,reason):
    if not value:raise ValueError(reason)


def parse_gpt(header,table,expected_lba,capacity):
    require(len(header)==512 and header[:8]==b'EFI PART','GPT signature invalid')
    size=struct.unpack_from('<I',header,12)[0]
    require(92<=size<=512,'GPT header size invalid')
    copy=bytearray(header[:size]);stored=struct.unpack_from('<I',copy,16)[0];struct.pack_into('<I',copy,16,0)
    require(zlib.crc32(copy)==stored,'GPT header CRC invalid')
    current,backup,first,last=struct.unpack_from('<QQQQ',header,24)
    require(current==expected_lba and first<=last<capacity//512 and backup<capacity//512,'GPT LBA geometry invalid')
    table_lba,count,entry_size,crc=struct.unpack_from('<QIII',header,72)
    require(count>0 and entry_size>=128 and len(table)==count*entry_size,'GPT entry array size invalid')
    require(zlib.crc32(table)==crc,'GPT entry CRC invalid')
    partitions=[]
    for number in range(count):
        entry=table[number*entry_size:(number+1)*entry_size]
        if not any(entry[:16]):continue
        low,high=struct.unpack_from('<QQ',entry,32)
        require(first<=low<=high<=last,'GPT partition outside usable disk')
        require(all(high<p['start_lba'] or low>p['end_lba'] for p in partitions),'GPT partitions overlap')
        partitions.append(dict(number=number+1,name=entry[56:128].decode('utf-16le').rstrip('\0'),
                               start_lba=low,end_lba=high,type_guid=str(uuid.UUID(bytes_le=entry[:16])),
                               unique_guid=str(uuid.UUID(bytes_le=entry[16:32]))))
    return dict(current_lba=current,backup_lba=backup,first_usable=first,last_usable=last,
                disk_guid=str(uuid.UUID(bytes_le=header[56:72])),table_lba=table_lba,
                count=count,entry_size=entry_size,partitions=partitions)


def validate_capture(files,old_manifest):
    x=json.loads(files['inventory.json']);identity=x['identity'];capacity=identity['capacity_bytes']
    require(identity['model']=='HY200 QZ713DF_A1 (Allwinner H713)' and identity['type']=='MMC','wrong board/eMMC type')
    require(capacity==old_manifest['capacity_bytes']==7818182656 and identity['logical_sector_bytes']==512,'device geometry mismatch')
    require(identity['device']=='/dev/mmcblk0' and identity['linux_hardware_partition']=='user','wrong hardware partition')
    require(len(identity['cid'])==32 and all(c in '0123456789abcdefABCDEF' for c in identity['cid']),'invalid CID')
    require(identity['sysfs_sector_count']*512==capacity,'sysfs/ioctl capacity mismatch')
    require(identity['boot_id']==x['ending_boot_id']==x['session']['boot_id'] and x['session']['phase']=='ready','boot/session changed or not ready')
    require(not x['reserved_partition_holders'] and not x['reserved_partition_mounts'],'reserved partition in use')
    for name,item in x['ranges'].items():
        require(len(files[name])==item['bytes'] and sha(files[name])==item['sha256'],'captured storage checksum mismatch: '+name)
    pfx=files['disk-prefix-64KiB.bin'];sfx=files['disk-suffix-64KiB.bin']
    primary=parse_gpt(pfx[512:1024],files['gpt-primary-entries.bin'],1,capacity)
    backup=parse_gpt(sfx[-512:],files['gpt-backup-entries.bin'],capacity//512-1,capacity)
    require(primary['backup_lba']==backup['current_lba'] and backup['backup_lba']==1,'GPT reciprocal LBAs differ')
    for key in ['disk_guid','first_usable','last_usable','partitions','count','entry_size']:
        require(primary[key]==backup[key],'GPT copies differ: '+key)
    require(files['gpt-primary-entries.bin']==files['gpt-backup-entries.bin'],'GPT entry arrays differ')
    require(primary['table_lba']*512+len(files['gpt-primary-entries.bin'])<=len(pfx),'primary GPT not contained in prefix')
    require(backup['table_lba']*512>=capacity-len(sfx),'backup GPT not contained in suffix')
    require(pfx[primary['table_lba']*512:primary['table_lba']*512+len(files['gpt-primary-entries.bin'])]==files['gpt-primary-entries.bin'],'primary table position mismatch')
    pos=backup['table_lba']*512-(capacity-len(sfx))
    require(sfx[pos:pos+len(files['gpt-backup-entries.bin'])]==files['gpt-backup-entries.bin'],'backup table position mismatch')
    for p in primary['partitions']:
        kernel=next((q for q in x['partitions'] if q['number']==p['number']),None)
        require(kernel is not None and kernel['start_lba']==p['start_lba'] and kernel['sectors']==p['end_lba']-p['start_lba']+1,'kernel/GPT partition geometry differs')
    owner=lambda start,size:[p for p in primary['partitions'] if p['start_lba']*512<=start and start+size<=(p['end_lba']+1)*512]
    for item in old_manifest['writes']:
        owners=owner(item['offset'],item['before']['bytes'])
        require(len(owners)==1 and owners[0]['number']==18 and owners[0]['name']=='empty','write outside reserved empty partition')
    require(owner(0x4a0c00*512,2097152)[0]['number']==18,'rescue not contained in reserved partition')
    require(owner(0x32ec00*512,65536)[0]['name']=='super','old environment owner changed')
    env=files['active-environment-64KiB.bin'];oldenv=old_manifest['writes'][0]['after']
    require(sha(env)==oldenv['sha256'] and len(env)==65536,'active environment drift')
    require(struct.unpack('<I',env[:4])[0]==zlib.crc32(env[4:]),'active environment CRC invalid')
    proper=files['proper-region-2MiB.bin'];extent=old_manifest['transaction_sectors']*512
    require(sha(proper[:extent])==old_manifest['rollback_proper_sha256'],'installed proper generation drift')
    require(struct.unpack('>II',proper[:8])==(0xd00dfeed,960817),'current proper FIT header differs')
    intended=files['intended-environment-surrounding-192KiB.bin'][65536:131072]
    require(not any(intended) and sha(intended)==old_manifest['writes'][0]['before']['sha256'],'intended environment preimage changed')
    require(sha(pfx[0x10*512:0x10*512+32768])=='cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec','installed SPL differs')
    rescue=files['rescue-region-2MiB.bin'];magic,size=struct.unpack('>II',rescue[:8])
    require(magic==0xd00dfeed and 40<size<=len(rescue),'rescue FIT header invalid')
    require(sha(rescue[:1798*512])=='c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7','rescue prefix differs')
    require(sha(files['boot-fat-32MiB.bin'])=='79c14f0566ada36158df2bef4995f73674a532987cfe8674c0c5e46789672de5','accepted boot FAT assets changed')
    require(all(b['all_match'] and all(c['expected']==c['actual'] for c in b['checks']) for b in x['bundle_checks']),'installed bundle mismatch')
    require(len(x['bundle_checks'])==4,'missing installed bundle')
    require(x['filesystem']['returncode']==0 and x['kernel_log']['returncode']==0 and x['services']['returncode']==0,'health collection command failed')
    fields=dict(line.split(':',1) for line in x['filesystem']['stdout'].splitlines() if ':' in line)
    require(fields.get('Filesystem state','').strip()=='clean','filesystem is not clean')
    require(int(fields.get('FS Error count',fields.get('Error count','0')).strip())==0,'filesystem has recorded errors')
    require('EXT4-fs error' not in x['kernel_log']['stdout'],'ext4 error in current boot log')
    require(x['latches']['gp6_gp7_hex']=='4b4f444800000000','startup/reboot latches not healthy')
    require(x['runtime']['/sys/module/h713_hdmi_audio/parameters/period_xruns']=='0','audio xruns present')
    require(x['runtime']['/sys/module/h713_hdmi_v4l2/parameters/frames_rejected']=='0','rejected video frames present')
    require('NRestarts=0' in x['services']['stdout'] and not any(line.startswith('NRestarts=') and line!='NRestarts=0' for line in x['services']['stdout'].splitlines()),'service recovery restarts present')
    return x,primary,dict(rescue_fit_bytes=size,rescue_fit_sha256=sha(rescue[:size]),
                          proper_full_region_sha256=sha(proper),boot_fat_sha256=sha(files['boot-fat-32MiB.bin']))


def finalize(source,capture,output):
    require(not output.exists(),'output already exists')
    for line in (source/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);require(Path(name).name==name and sha((source/name).read_bytes())==digest,'source package checksum mismatch')
    old=json.loads((source/'manifest.json').read_text())
    with tarfile.open(capture) as archive:
        members=archive.getmembers()
        require(len({m.name for m in members})==len(members) and all(m.isfile() and Path(m.name).name==m.name for m in members),'unsafe capture members')
        files={m.name:archive.extractfile(m).read() for m in members}
    x,gpt,report=validate_capture(files,old)
    accepted=json.loads((ROOT/'docs/hdmi-evidence/2026-10-30-guard-sync/post-install.json').read_text())
    for name,item in x['files'].items():
        if name in accepted['files']:require(item==accepted['files'][name],'accepted installed file drift: '+name)
    shutil.copytree(source,output)
    for path in list(output.glob('fixture-*.bin')):path.unlink()
    for path in output.glob('__pycache__/*'):path.unlink()
    if (output/'__pycache__').exists():(output/'__pycache__').rmdir()
    def blob(name,data):
        path=output/name;path.write_bytes(data);path.chmod(0o600)
        return dict(file=name,bytes=len(data),sha256=sha(data))
    m=old;m['offline_only']=False;m['finalized']=True
    m['live_identity']=x['identity'];m['file_pins']=dict(x['files']);m['runtime_pins']=x['runtime']
    # The stdin-only live preview will freshly verify these accepted unit pins too.
    for name,item in accepted['files'].items():
        if name.startswith('/etc/systemd/system/') and name.endswith('.service'):m['file_pins'][name]=item
    m['service_pins']=x['services']['stdout'];m['session_pin']=x['session'];m['latch_pin']=x['latches']['gp6_gp7_hex']
    m['capture_sha256']=sha(capture.read_bytes());m['live_gpt']=gpt;m['collection_start_monotonic']=x['start_monotonic'];m['collection_end_monotonic']=x['end_monotonic']
    m['live_preflight_required']=[]
    m['limitation']='Live-pinned current boot; explicit write approval/confirmation and operator readiness still required. No install/reboot performed.'
    # Refresh every rollback preimage from the fresh raw reads.
    extent=m['transaction_sectors']*512
    m['writes'][0]['before']=blob('environment-before.bin',files['intended-environment-surrounding-192KiB.bin'][65536:131072])
    m['writes'][0]['after']=blob('environment-after.bin',files['active-environment-64KiB.bin'])
    m['writes'][1]['before']=blob('proper-before.bin',files['proper-region-2MiB.bin'][:extent])
    m['protected']=[]
    for name,offset,data in [
        ('disk-prefix-including-GPT-and-SPL',0,files['disk-prefix-64KiB.bin']),
        ('disk-suffix-including-backup-GPT',m['capacity_bytes']-65536,files['disk-suffix-64KiB.bin']),
        ('active-environment',0x32ec00*512,files['active-environment-64KiB.bin']),
        ('rescue-full-region',0x4a0c00*512,files['rescue-region-2MiB.bin']),
        ('proper-region-tail',0x49ac00*512+extent,files['proper-region-2MiB.bin'][extent:]),
        ('intended-environment-prefix',0x49ec00*512-65536,files['intended-environment-surrounding-192KiB.bin'][:65536]),
        ('intended-environment-suffix',0x49ec00*512+65536,files['intended-environment-surrounding-192KiB.bin'][131072:]),
        ('boot-FAT',x['ranges']['boot-fat-32MiB.bin']['offset'],files['boot-fat-32MiB.bin'])]:
        item=blob(name+'.bin',data);item.update(name=name,offset=offset);m['protected'].append(item)
    for name in ['uboot-migration.py','uboot-migration-live.py','rehearse-uboot-migration.py']:
        shutil.copyfile(ROOT/'tools/hdmi'/name,output/name)
    m['tool_hashes']={name:sha((output/name).read_bytes()) for name in ['uboot-migration.py','uboot-migration-live.py','rehearse-uboot-migration.py']}
    (output/'inventory-private.json').write_text(json.dumps(x,indent=2)+'\n')
    (output/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    (output/'README.txt').write_text('''LIVE-PINNED MIGRATION PACKAGE — NOT INSTALLED.
All collection and live preview were read-only. No reboot is automated.
Raw environment, eMMC CID and firmware are private; do not commit this package.
Live mode is explicit (--device /dev/mmcblk0); writes require the full manifest
SHA-256 in --confirm-write and the pinned --expected-boot-id, plus separate
operator authorization. Preview opens the target read-only and creates no journal.
Install stages the unchanged environment first, then proper. Rollback restores
proper first. SPL, both GPT copies, old environment, rescue and boot FAT are protected.
The manifest is bound to the collected boot and exact service/runtime state.
If the boot/state changes, stop and re-collect/finalize; never bypass these guards.
The tool does not reboot or execute saveenv. See RECOVERY.txt for FEL fallback.
Rehearsal: python3 rehearse-uboot-migration.py --package . --work /new/host/work/path
''')
    recovery=(output/'RECOVERY.txt').read_text().replace('OFFLINE PREPARATION: hardware use requires fresh identity/GPT/preimage checks,','LIVE-PINNED PREPARATION: runtime preflight is still mandatory at use;')
    recovery=recovery.replace('Do not execute these commands on a board from this historical package alone.','No install or reboot is authorized by package generation. Check the manifest boot ID and CID before recovery.')
    (output/'RECOVERY.txt').write_text(recovery)
    for path in output.iterdir():
        if path.is_file():path.chmod(0o600)
    (output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
    report.update(result='PASS fresh capture validated and package finalized',boot_id=x['identity']['boot_id'],
                  cid_sha256=sha(x['identity']['cid'].encode()),gpt_copies_valid=True,partition_count=len(gpt['partitions']),
                  write_partition=dict(number=18,name='empty'),manifest_sha256=sha((output/'manifest.json').read_bytes()),
                  finalized=True,board_writes=False,installation=False,reboot=False)
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();finalize(a.source,a.capture,a.output)
