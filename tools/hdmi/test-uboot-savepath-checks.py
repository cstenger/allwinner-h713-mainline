#!/usr/bin/env python3
"""Host-only semantic guards and sparse-disk rehearsal for native save validation."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zlib

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--packet',type=Path,required=True);parser.add_argument('--capture',type=Path,required=True)
parser.add_argument('--checker',type=Path,default=Path(__file__).with_name('check-uboot-savepath.py'))
parser.add_argument('--mutations',action='store_true');args=parser.parse_args()
spec=importlib.util.spec_from_file_location('savepath',args.checker);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
BEFORE=(args.packet/'environment-before.bin').read_bytes();BASE=v.decode(BEFORE)
NONCE=json.loads((args.packet/'manifest.json').read_text())['nonce']
PROBE=dict(BASE);PROBE[v.PROBE]=NONCE.encode()


def blob(body):return struct.pack('<I',zlib.crc32(body))+body


class Checks(unittest.TestCase):
    def test_valid_probe_cleanup(self):
        self.assertTrue(v.check(BEFORE,v.encode(PROBE),'probe',NONCE)['marker_present'])
        self.assertFalse(v.check(BEFORE,v.encode(BASE),'cleanup',NONCE)['marker_present'])

    def test_crc(self):
        b=bytearray(v.encode(PROBE));b[0]^=1
        with self.assertRaisesRegex(ValueError,'CRC'):v.decode(b)

    def test_size(self):
        b=blob(BEFORE[4:]+b'\0')
        with self.assertRaisesRegex(ValueError,'size'):v.decode(b)

    def test_duplicate(self):
        body=b'a=one\0a=two\0\0'.ljust(65532,b'\0')
        with self.assertRaisesRegex(ValueError,'duplicate'):v.decode(blob(body))

    def test_terminator(self):
        body=b'a='+b'x'*65530
        with self.assertRaisesRegex(ValueError,'terminator'):v.decode(blob(body))

    def test_original_probe_present(self):
        with self.assertRaisesRegex(ValueError,'original backup'):v.check(v.encode(PROBE),v.encode(PROBE),'probe',NONCE)

    def test_original_bootdelay(self):
        b=dict(BASE);b[b'bootdelay']=b'-1';s=dict(b);s[v.PROBE]=NONCE.encode()
        with self.assertRaisesRegex(ValueError,'bootdelay'):v.check(v.encode(b),v.encode(s),'probe',NONCE)

    def test_missing_guard(self):
        b=dict(BASE);del b[b'bootcmd'];s=dict(b);s[v.PROBE]=NONCE.encode()
        with self.assertRaisesRegex(ValueError,'startup guard'):v.check(v.encode(b),v.encode(s),'probe',NONCE)

    def test_semantic_drift(self):
        s=dict(PROBE);s[b'preboot']=b'wrong'
        with self.assertRaisesRegex(ValueError,'semantic'):v.check(BEFORE,v.encode(s),'probe',NONCE)

    def test_wrong_nonce(self):
        s=dict(PROBE);s[v.PROBE]=b'wrong'
        with self.assertRaisesRegex(ValueError,'semantic'):v.check(BEFORE,v.encode(s),'probe',NONCE)

    def test_filesize_side_effect(self):
        ram=dict(BASE);ram[b'filesize']=b'10000' if BASE.get(b'filesize')!=b'10000' else b'10001';s=dict(ram);s[v.PROBE]=NONCE.encode()
        with self.assertRaisesRegex(ValueError,'RAM environment drift'):v.check(BEFORE,v.encode(s),'probe',NONCE,ram)

    def test_control_fdt_metadata(self):
        ram=dict(BASE);ram[b'fdtcontroladdr']=b'70001000';s=dict(ram);s[v.PROBE]=NONCE.encode()
        self.assertEqual(v.check(BEFORE,v.encode(s),'probe',NONCE,ram)['allowed_RAM_metadata_changes'],['fdtcontroladdr'])

    def test_invalid_control_fdt(self):
        ram=dict(BASE);ram[b'fdtcontroladdr']=b'06940000';s=dict(ram);s[v.PROBE]=NONCE.encode()
        with self.assertRaisesRegex(ValueError,'control-FDT'):v.check(BEFORE,v.encode(s),'probe',NONCE,ram)

    def test_cleanup_reload_proof(self):
        ram=dict(PROBE);ram[v.PROBE]=b'wrong'
        with self.assertRaisesRegex(ValueError,'reload'):v.check(BEFORE,v.encode(BASE),'cleanup',NONCE,ram)

    def test_cleanup_removes_marker(self):
        with self.assertRaisesRegex(ValueError,'semantic'):v.check(BEFORE,v.encode(PROBE),'cleanup',NONCE)

    def test_invalid_phase(self):
        with self.assertRaisesRegex(ValueError,'phase'):v.check(BEFORE,v.encode(BASE),'wrong',NONCE,PROBE)

    def test_invalid_nonce(self):
        s=dict(PROBE);s[v.PROBE]=b'bad/nonce'
        with self.assertRaisesRegex(ValueError,'nonce'):v.check(BEFORE,v.encode(s),'probe','bad/nonce')


def sparse_rehearsal():
    spec=importlib.util.spec_from_file_location('rehearsal',Path(__file__).with_name('rehearse-uboot-migration.py'))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    m=json.loads((args.packet/'manifest.json').read_text())
    with tarfile.open(args.capture) as archive:
        x=json.load(archive.extractfile('inventory.json'))
        ranges=[(item['offset'],archive.extractfile(name).read()) for name,item in x['ranges'].items()]
    with tempfile.TemporaryDirectory() as directory:
        before=Path(directory)/'before.img';after=Path(directory)/'after.img'
        def fresh(path):
            with path.open('wb') as f:
                f.truncate(m['identity']['capacity_bytes'])
                for offset,data in ranges:f.seek(offset);f.write(data)
                f.seek(65536);f.write(b'UNRELATED GAP'.ljust(4096,b'\x5a'))
        fresh(before);fresh(after);offset=m['write_region']['offset'];span=[(offset,offset+65536)]
        for phase,data in [('probe',v.encode(PROBE)),('cleanup',v.encode(BASE))]:
            fd=os.open(after,os.O_RDWR)
            try:assert os.pwrite(fd,data,offset)==65536;os.fsync(fd)
            finally:os.close(fd)
            with after.open('rb') as f:f.seek(offset);stored=f.read(65536)
            v.check(BEFORE,stored,phase,NONCE);helper.same_outside(before,after,span)
            for item in m['protected']:
                with after.open('rb') as f:f.seek(item['offset']);raw=f.read(item['bytes'])
                import hashlib
                assert hashlib.sha256(raw).hexdigest()==item['sha256'],item['name']
            print('PASS sparse host disk: native-result model',phase,'and all 9 protected regions')
        for wrong in [0x32ec00*512,offset-512]:
            fresh(after)
            with after.open('r+b') as f:f.seek(wrong);f.write(v.encode(PROBE))
            try:helper.same_outside(before,after,span)
            except AssertionError:pass
            else:raise AssertionError('out-of-bounds write escaped rehearsal')
            print('CAUGHT sparse fixture write outside intended slot:',hex(wrong))
    print('PASS sparse save/cleanup rehearsal; no device or hardware write')


def mutations():
    variants={
        'CRC unchecked':("struct.unpack('<I',data[:4])[0]==zlib.crc32(data[4:])",'True'),
        'size unchecked':('len(data)==SIZE','True'),
        'duplicate keys accepted':('key and key not in result','key'),
        'terminator unchecked':("b'\\0\\0' in body",'True'),
        'original marker unchecked':('PROBE not in original','True'),
        'bootdelay guard removed':("original.get(b'bootdelay')==b'5'",'True'),
        'startup guard removed':('original.get(key)','True'),
        'semantic equality ignored':('actual==expected','True'),
        'RAM drift ignored':("differences<={b'fdtcontroladdr'}",'True'),
        'control FDT bounds ignored':("re.fullmatch(b'[0-9a-fA-F]{8}',value) is not None and 0x40000000<=int(value,16)<0x80000000",'True'),
        'cleanup nonce proof ignored':('ram.get(PROBE)==nonce.encode()','True'),
        'phase unchecked':("phase in ['probe','cleanup']",'True'),
        'nonce unchecked':("re.fullmatch(r'[A-Za-z0-9_-]{8,64}',nonce) is not None",'True'),
        'valid saves rejected':('actual==expected','False'),
        'valid control FDT update rejected':("differences<={b'fdtcontroladdr'}",'not differences'),
    }
    with tempfile.TemporaryDirectory() as directory:
        for name,(before,after) in variants.items():
            source=args.checker.read_text();assert source.count(before)==1,(name,source.count(before))
            path=Path(directory)/'mutant.py';path.write_text(source.replace(before,after))
            r=subprocess.run([sys.executable,__file__,'--packet',str(args.packet),'--capture',str(args.capture),'--checker',str(path)],capture_output=True)
            assert r.returncode!=0 and b'FAILED' in r.stderr,name
            print('CAUGHT',name)
    print('PASS all 15 semantic-validator mutations caught')


if __name__=='__main__':
    if args.mutations:mutations()
    else:
        result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
        if not result.wasSuccessful():sys.exit(1)
        sparse_rehearsal()
