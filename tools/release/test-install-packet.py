#!/usr/bin/env python3
"""Adversarial offline scope/format tests; optional real fastboot loopback test."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import unittest
import uuid
import zlib

spec=importlib.util.spec_from_file_location('packet',Path(__file__).with_name('prepare-install.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def fixture_gpt(path, change=None):
    entries=bytearray(28*128)
    pins={2:('bootloader_b',0x22000,0x10000),9:('super',0x92400,0x400000),
          18:('empty',0x49ac00,0x7800),26:('linux',5555200,5767168),27:('UDISK',11322368,2021113344//512)}
    for i in range(1,28):
        name,start,count=pins.get(i,('part'+str(i),100000+i,1))
        e=bytearray(128);e[:16]=uuid.UUID('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7').bytes_le
        e[16:32]=uuid.UUID(int=i).bytes_le;struct.pack_into('<QQ',e,32,start,start+count-1)
        e[56:56+len(name.encode('utf-16-le'))]=name.encode('utf-16-le');entries[(i-1)*128:i*128]=e
    if change:change(entries)
    crc=zlib.crc32(entries)&0xffffffff;last=p.DISK_BYTES//512-1
    def header(current,other,array_lba):
        h=bytearray(512);h[:8]=b'EFI PART';struct.pack_into('<IIII',h,8,0x10000,92,0,0)
        struct.pack_into('<QQQQ',h,24,current,other,34,last-33);h[56:72]=uuid.UUID(int=123).bytes_le
        struct.pack_into('<QIII',h,72,array_lba,28,128,crc);struct.pack_into('<I',h,16,zlib.crc32(h[:92])&0xffffffff)
        return h
    with path.open('wb') as f:
        f.truncate(p.DISK_BYTES);f.seek(512);f.write(header(1,last,2));f.write(entries)
        f.seek((last-7)*512);f.write(entries);f.write(header(last,1,last-7))


class PacketTests(unittest.TestCase):
    def test_gpt_moved_linux_rejected_even_with_valid_crcs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'disk';fixture_gpt(path);self.assertEqual(p.gpt(path)['entry_slots'],28)
            def move(e):struct.pack_into('<Q',e,25*128+32,5555201)
            fixture_gpt(path,move)
            with self.assertRaisesRegex(ValueError,'partition identity'):p.gpt(path)

    def test_gpt_overlap_rejected_even_with_valid_crcs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'disk'
            def overlap(e):struct.pack_into('<QQ',e,2*128+32,5555200,5555201)
            fixture_gpt(path,overlap)
            with self.assertRaisesRegex(ValueError,'overlapping'):p.gpt(path)

    def test_gpt_crc_and_spl_overlap_expansion_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'disk';fixture_gpt(path)
            # Actual primary header lives at byte 512; corrupt its count then
            # repair header CRC, so the explicit 28-slot guard must reject it.
            with path.open('r+b') as f:
                f.seek(512);h=bytearray(f.read(512));struct.pack_into('<I',h,80,128);struct.pack_into('<I',h,16,0)
                struct.pack_into('<I',h,16,zlib.crc32(h[:92])&0xffffffff);f.seek(512);f.write(h)
            with self.assertRaisesRegex(ValueError,'GPT array would overlap'):p.gpt(path)
            fixture_gpt(path)
            with path.open('r+b') as f:f.seek(1024);f.write(b'bad')
            with self.assertRaisesRegex(ValueError,'array CRC'):p.gpt(path)

    def test_raw_sparse_preserves_zero_blocks_and_rejects_skip(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'raw';target=Path(d)/'sparse'
            data=bytes(4096)+b'x'*4096+bytes(4096);source.write_bytes(data)
            p.all_raw_sparse(source,target)
            with target.open('r+b') as f:f.seek(28);f.write(struct.pack('<H',0xcac3))
            with self.assertRaisesRegex(ValueError,'skips/fill forbidden'):p.check_all_raw(target,hashlib.sha256(data).hexdigest(),len(data))

    def test_egon_corruption_and_write_bounds(self):
        b=bytearray(32768);b[4:12]=b'eGON.BT0';struct.pack_into('<II',b,12,0x5f0a6c39,len(b))
        checksum=sum(struct.unpack('<8192I',b))&0xffffffff;struct.pack_into('<I',b,12,checksum)
        p.check_spl(bytes(b));b[-1]^=1
        with self.assertRaisesRegex(ValueError,'checksum'):p.check_spl(bytes(b))
        layout={'partitions':[dict(number=26,start_lba=5555200,sectors=5767168),dict(number=2,start_lba=0x22000,sectors=0x10000)]}
        for role,size in [('root',2952790016+512),('fat',33554432+512),('proper',955904+512),('spl',32768+512)]:
            with self.subTest(role=role),self.assertRaises(ValueError):p.target_bounds(role,size,layout)

    def test_overlay_hash_covers_outside_changes_and_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)/'base';raw=Path(d)/'new';base.write_bytes(b'a'*4096);raw.write_bytes(b'b'*512)
            old_size,old_chunk=p.DISK_BYTES,p.CHUNK
            try:
                p.DISK_BYTES=4096;p.CHUNK=1024
                a=p.disk_pins(base,[]);b=p.disk_pins(base,[(512,512,raw)])
                self.assertNotEqual(a['chunks'][0]['sha256'],b['chunks'][0]['sha256'])
                self.assertEqual(a['chunks'][1:],b['chunks'][1:])
                self.assertEqual(b['sha256'],hashlib.sha256(b'a'*512+b'b'*512+b'a'*3072).hexdigest())
                with base.open('r+b') as f:f.seek(3072);f.write(b'x')
                self.assertNotEqual(p.disk_pins(base,[(512,512,raw)])['sha256'],b['sha256'])
            finally:p.DISK_BYTES,p.CHUNK=old_size,old_chunk

    def test_recovery_masks_only_allowed_write_windows(self):
        original=b'a'*4096;changed=bytearray(original);changed[512:1024]=b'b'*512
        ranges=[{'offset':512,'bytes':512}]
        self.assertEqual(p.mask_recovery(changed,0,ranges,io.BytesIO(original)),original)
        changed[2048]=ord('x')
        self.assertNotEqual(hashlib.sha256(p.mask_recovery(changed,0,ranges,io.BytesIO(original))).digest(),hashlib.sha256(original).digest())

    def test_ledger_path_escape_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'SHA256SUMS').write_text('0'*64+'  ../secret\n')
            with self.assertRaisesRegex(ValueError,'unsafe packet path'):p.ledger(root,'SHA256SUMS')
            (root/'link').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(ValueError,'symlink'):p.safe(root,'link')


if __name__=='__main__':unittest.main()
