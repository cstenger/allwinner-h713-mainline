#!/usr/bin/env python3
"""Offline-only validation of nonredundant U-Boot environment save results."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

SIZE=65536
PROBE=b'h713_savepath_probe'


def require(value,reason):
    if not value:raise ValueError(reason)


def decode(data):
    require(len(data)==SIZE,'environment size must be 65536')
    require(struct.unpack('<I',data[:4])[0]==zlib.crc32(data[4:]),'environment CRC mismatch')
    body=data[4:];require(b'\0\0' in body,'environment terminator missing')
    result={}
    for item in body.split(b'\0\0',1)[0].split(b'\0'):
        require(b'=' in item,'malformed environment entry')
        key,value=item.split(b'=',1)
        require(key and key not in result,'empty or duplicate key')
        result[key]=value
    return result


def encode(values):
    require(values and all(k and b'=' not in k and b'\0' not in k and b'\0' not in v for k,v in values.items()),'invalid environment map')
    body=b'\0'.join(k+b'='+v for k,v in sorted(values.items()))+b'\0\0'
    require(len(body)<=SIZE-4,'environment map too large')
    body=body.ljust(SIZE-4,b'\0')
    return struct.pack('<I',zlib.crc32(body))+body


def check(before,saved,phase,nonce,ram=None):
    require(phase in ['probe','cleanup'],'invalid save phase')
    require(re.fullmatch(r'[A-Za-z0-9_-]{8,64}',nonce) is not None,'invalid probe nonce')
    original=decode(before);actual=decode(saved)
    require(PROBE not in original,'probe already exists in original backup')
    require(original.get(b'bootdelay')==b'5','backup bootdelay must be 5')
    for key in [b'bootcmd',b'preboot',b'h713_hdmi_previous_bootcmd']:
        require(original.get(key),'required startup guard absent in backup')
    if ram is None:
        ram=dict(original)
        if phase=='cleanup':ram[PROBE]=nonce.encode()
    else:ram=dict(ram)
    if phase=='probe':require(PROBE not in ram,'probe unexpectedly present before test')
    else:require(ram.get(PROBE)==nonce.encode(),'cleanup RAM snapshot did not reload the saved nonce')
    clean_ram={k:v for k,v in ram.items() if k!=PROBE}
    differences={k for k in set(original)|set(clean_ram) if original.get(k)!=clean_ram.get(k)}
    require(differences<={b'fdtcontroladdr'},'unapproved RAM environment drift')
    if b'fdtcontroladdr' in differences:
        value=clean_ram.get(b'fdtcontroladdr',b'')
        require(re.fullmatch(b'[0-9a-fA-F]{8}',value) is not None and 0x40000000<=int(value,16)<0x80000000,'invalid control-FDT RAM address')
    expected=dict(clean_ram)
    if phase=='probe':expected[PROBE]=nonce.encode()
    require(actual==expected,'saved environment semantic mismatch')
    return dict(result='PASS offline save-result semantics',phase=phase,entries=len(actual),
                marker_present=PROBE in actual,critical_startup_guards_preserved=True,
                allowed_RAM_metadata_changes=sorted(k.decode() for k in differences),
                saved_sha256=hashlib.sha256(saved).hexdigest(),hardware_write=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',required=True,type=Path);p.add_argument('--saved',required=True,type=Path)
    p.add_argument('--phase',choices=['probe','cleanup'],required=True);p.add_argument('--nonce',required=True)
    p.add_argument('--ram-json',type=Path,help='private pre-save RAM map: key strings to hex-encoded values; not a target env export')
    a=p.parse_args();ram=None
    if a.ram_json:ram={k.encode():bytes.fromhex(v) for k,v in json.loads(a.ram_json.read_text()).items()}
    print(json.dumps(check(a.before.read_bytes(),a.saved.read_bytes(),a.phase,a.nonce,ram),indent=2))


if __name__=='__main__':main()
