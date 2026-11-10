#!/usr/bin/env python3
"""Host-only tests of fresh GPT/identity guards using saved read-only data."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zlib


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--capture',type=Path,required=True);parser.add_argument('--package',type=Path,required=True)
parser.add_argument('--finalizer',type=Path,default=ROOT/'tools/hdmi/finalize-uboot-migration.py')
parser.add_argument('--live',type=Path,default=ROOT/'tools/hdmi/uboot-migration-live.py')
parser.add_argument('--engine',type=Path,default=ROOT/'tools/hdmi/uboot-migration.py')
parser.add_argument('--mutations',action='store_true');args=parser.parse_args()
f=module('finalize',args.finalizer);live=module('live',args.live)
engine=module('engine',args.engine)
with tarfile.open(args.capture) as t:FILES={m.name:t.extractfile(m).read() for m in t.getmembers()}
MANIFEST=json.loads((args.package/'manifest.json').read_text())


def mutate_inventory(files,update):
    x=json.loads(files['inventory.json']);update(x)
    for name,item in x['ranges'].items():item['sha256']=hashlib.sha256(files[name]).hexdigest()
    files['inventory.json']=(json.dumps(x)+'\n').encode()


def reject_capture(files,message):
    try:f.validate_capture(files,MANIFEST)
    except ValueError as e:
        assert message in str(e),(message,str(e));return
    raise AssertionError('invalid collection accepted: '+message)


class LiveChecks(unittest.TestCase):
    def test_valid(self):
        f.validate_capture(FILES,MANIFEST)
        actual=dict(MANIFEST['live_identity'],reserved_partition_mounted=False,reserved_partition_holders=[])
        live.validate_identity(actual,MANIFEST,actual['boot_id'])

    def test_primary_header_crc(self):
        files=dict(FILES);data=bytearray(files['disk-prefix-64KiB.bin']);data[512+20]^=1
        files['disk-prefix-64KiB.bin']=bytes(data);mutate_inventory(files,lambda x:None)
        reject_capture(files,'header CRC')

    def test_backup_header_crc(self):
        files=dict(FILES);data=bytearray(files['disk-suffix-64KiB.bin']);data[-512+20]^=1
        files['disk-suffix-64KiB.bin']=bytes(data);mutate_inventory(files,lambda x:None)
        reject_capture(files,'header CRC')

    def test_table_crc(self):
        files=dict(FILES);data=bytearray(files['gpt-primary-entries.bin']);data[0]^=1
        files['gpt-primary-entries.bin']=bytes(data);mutate_inventory(files,lambda x:None)
        reject_capture(files,'entry CRC')

    def test_gpt_disagreement(self):
        files=dict(FILES);data=bytearray(files['disk-suffix-64KiB.bin']);h=bytearray(data[-512:]);h[56]^=1
        size=struct.unpack_from('<I',h,12)[0];struct.pack_into('<I',h,16,0);struct.pack_into('<I',h,16,zlib.crc32(h[:size]))
        data[-512:]=h;files['disk-suffix-64KiB.bin']=bytes(data);mutate_inventory(files,lambda x:None)
        reject_capture(files,'GPT copies differ')

    def test_kernel_partition_disagreement(self):
        files=dict(FILES)
        def update(x):next(p for p in x['partitions'] if p['number']==18)['start_lba']+=1
        mutate_inventory(files,update);reject_capture(files,'kernel/GPT')

    def test_partition_ownership(self):
        files=dict(FILES)
        table=bytearray(files['gpt-primary-entries.bin']);pos=17*128+56
        table[pos:pos+72]='wrong'.encode('utf-16le').ljust(72,b'\0')
        files['gpt-primary-entries.bin']=files['gpt-backup-entries.bin']=bytes(table)
        for name,index in [('disk-prefix-64KiB.bin',512),('disk-suffix-64KiB.bin',65536-512)]:
            data=bytearray(files[name]);h=bytearray(data[index:index+512]);lba=struct.unpack_from('<Q',h,72)[0]
            base=0 if index==512 else MANIFEST['capacity_bytes']-65536
            offset=lba*512-base;data[offset:offset+len(table)]=table
            struct.pack_into('<I',h,88,zlib.crc32(table));struct.pack_into('<I',h,16,0)
            struct.pack_into('<I',h,16,zlib.crc32(h[:struct.unpack_from('<I',h,12)[0]]));data[index:index+512]=h
            files[name]=bytes(data)
        mutate_inventory(files,lambda x:None);reject_capture(files,'outside reserved empty')

    def test_reserved_partition_in_use(self):
        for key,value in [('reserved_partition_holders',['dm-0']),('reserved_partition_mounts',['mounted'])]:
            files=dict(FILES);mutate_inventory(files,lambda x:x.update({key:value}))
            reject_capture(files,'partition in use')

    def test_boot_change(self):
        files=dict(FILES);mutate_inventory(files,lambda x:x.update(ending_boot_id='different'))
        reject_capture(files,'boot/session')

    def test_active_environment_drift(self):
        files=dict(FILES);data=bytearray(files['active-environment-64KiB.bin']);data[-1]^=1
        files['active-environment-64KiB.bin']=bytes(data);mutate_inventory(files,lambda x:None)
        reject_capture(files,'active environment drift')

    def test_intended_environment_drift(self):
        files=dict(FILES);data=bytearray(files['intended-environment-surrounding-192KiB.bin']);data[65536]=1
        files['intended-environment-surrounding-192KiB.bin']=bytes(data);mutate_inventory(files,lambda x:None)
        reject_capture(files,'intended environment preimage')

    def test_filesystem_state(self):
        files=dict(FILES)
        def update(x):
            x['filesystem']['stdout']='\n'.join('Filesystem state: not clean' if line.startswith('Filesystem state:') else line for line in x['filesystem']['stdout'].splitlines())
        mutate_inventory(files,update);reject_capture(files,'filesystem is not clean')

    def test_latch_changed(self):
        files=dict(FILES);mutate_inventory(files,lambda x:x['latches'].update(gp6_gp7_hex='0'*16))
        reject_capture(files,'latches not healthy')

    def test_identity_drift(self):
        for key in ['model','boot_id','cid','type','dev_number','capacity_bytes','logical_sector_bytes','linux_hardware_partition']:
            actual=dict(MANIFEST['live_identity'],reserved_partition_mounted=False,reserved_partition_holders=[])
            actual[key]='wrong'
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                live.validate_identity(actual,MANIFEST,MANIFEST['live_identity']['boot_id'])

    def test_explicit_boot_binding(self):
        actual=dict(MANIFEST['live_identity'],reserved_partition_mounted=False,reserved_partition_holders=[])
        with self.assertRaisesRegex(ValueError,'explicit expected boot'):
            live.validate_identity(actual,MANIFEST,'wrong')

    def test_live_partition_in_use(self):
        for key,value in [('reserved_partition_mounted',True),('reserved_partition_holders',['dm-0'])]:
            actual=dict(MANIFEST['live_identity'],reserved_partition_mounted=False,reserved_partition_holders=[]);actual[key]=value
            with self.assertRaisesRegex(ValueError,'reserved partition'):
                live.validate_identity(actual,MANIFEST,actual['boot_id'])

    def test_no_write_without_confirmation(self):
        result=subprocess.run([sys.executable,str(args.engine),'install','--package',str(args.package),
            '--device','/dev/mmcblk0','--journal','/unused-host-path','--expected-boot-id',MANIFEST['live_identity']['boot_id']],capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'write confirmation required',result.stderr)

    def test_direct_readback_command(self):
        with patch.object(engine.os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFBLK)), \
             patch.object(engine.subprocess,'run',return_value=SimpleNamespace(stdout=bytes(512))) as run:
            self.assertEqual(engine.read_at(123,512,512),bytes(512))
            command=run.call_args.args[0]
            self.assertIn('iflag=direct',command)
            self.assertIn('if=/dev/mmcblk0',command)
            self.assertFalse(any(x.startswith('of=') for x in command))

    def test_short_direct_readback(self):
        with patch.object(engine.os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFBLK)), \
             patch.object(engine.subprocess,'run',return_value=SimpleNamespace(stdout=bytes(256))):
            with self.assertRaisesRegex(ValueError,'short read'):engine.read_at(123,0,512)

    def test_hardware_fault_injection_disabled(self):
        with patch.object(engine.os,'open',side_effect=AssertionError('hardware must never be opened for a fault test')):
            with self.assertRaisesRegex(ValueError,'hardware fault injection is disabled'):
                engine.operate(args.package,Path('/dev/mmcblk0'),Path('/unused-host-path'),'install',fault='proper-short',board=True)


def mutations():
    variants=[
        ('header CRC unchecked','finalizer',"zlib.crc32(copy)==stored",'True'),
        ('table CRC unchecked','finalizer',"zlib.crc32(table)==crc",'True'),
        ('GPT copies unchecked','finalizer',"primary[key]==backup[key]",'True'),
        ('kernel layout unchecked','finalizer',"kernel is not None and kernel['start_lba']==p['start_lba'] and kernel['sectors']==p['end_lba']-p['start_lba']+1",'True'),
        ('reserved write owner unchecked','finalizer',"len(owners)==1 and owners[0]['number']==18 and owners[0]['name']=='empty'",'True'),
        ('reserved use unchecked','finalizer',"not x['reserved_partition_holders'] and not x['reserved_partition_mounts']",'True'),
        ('boot change unchecked','finalizer',"identity['boot_id']==x['ending_boot_id']==x['session']['boot_id'] and x['session']['phase']=='ready'",'True'),
        ('environment identity unchecked','finalizer',"sha(env)==oldenv['sha256'] and len(env)==65536",'True'),
        ('intended preimage unchecked','finalizer',"not any(intended) and sha(intended)==old_manifest['writes'][0]['before']['sha256']",'True'),
        ('filesystem state unchecked','finalizer',"fields.get('Filesystem state','').strip()=='clean'",'True'),
        ('latches unchecked','finalizer',"x['latches']['gp6_gp7_hex']=='4b4f444800000000'",'True'),
        ('live identity unchecked','live',"actual[key]==pinned[key]",'True'),
        ('explicit boot unchecked','live',"expected_boot_id==pinned['boot_id']",'True'),
        ('live mount guard removed','live',"not actual['reserved_partition_mounted']",'True'),
        ('live holder guard removed','live',"not actual['reserved_partition_holders']",'True'),
        ('direct readback flag lost','engine',"'iflag=direct'","'iflag=fullblock'"),
        ('short read accepted','engine',"require(len(data) == size, 'short read')",'pass'),
        ('hardware fault guard removed','engine',"require(not board or fault is None, 'hardware fault injection is disabled')",'pass'),
        ('write confirmation removed','engine',"require(a.confirm_write==sha((a.package/'manifest.json').read_bytes()),'explicit package-bound write confirmation required')",'None'),
    ]
    with tempfile.TemporaryDirectory() as directory:
        for name,kind,before,after in variants:
            source=getattr(args,kind).read_text();assert source.count(before)==1,name
            path=Path(directory)/'mutant.py';path.write_text(source.replace(before,after))
            command=[sys.executable,__file__,'--package',str(args.package),'--capture',str(args.capture),'--'+kind,str(path)]
            result=subprocess.run(command,capture_output=True)
            assert result.returncode!=0 and b'FAILED' in result.stderr,name
            print('CAUGHT',name)
    print('PASS all 19 fresh identity/storage/live-mode mutations caught')


if __name__=='__main__':
    if args.mutations:mutations()
    else:unittest.main(argv=[sys.argv[0]])
