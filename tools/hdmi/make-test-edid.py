#!/usr/bin/env python3
"""Generate a base EDID for the bounded 640x480 HDMI sink test."""
import argparse
from pathlib import Path

def make_edid():
 e=bytearray(128);e[:8]=bytes.fromhex('00ffffffffffff00');e[8:10]=(0x2070).to_bytes(2,'big');e[10:12]=(0x713).to_bytes(2,'little');e[12:16]=(0).to_bytes(4,'little');e[16:25]=bytes([38,36,1,4,0xa2,16,12,120,0x06])
 coords=[round(v*1024) for v in [.64,.33,.30,.60,.15,.06,.3127,.329]]
 e[25]=(coords[0]&3)<<6|(coords[1]&3)<<4|(coords[2]&3)<<2|(coords[3]&3)
 e[26]=(coords[4]&3)<<6|(coords[5]&3)<<4|(coords[6]&3)<<2|(coords[7]&3)
 e[27:35]=bytes(v>>2 for v in coords);e[35]=0x20;e[38:54]=b'\x01\x01'*8
 e[54:72]=bytes.fromhex('d60980a020e02d101060a200a07800000018')
 e[72:90]=b'\0\0\0\xfc\0'+b'HDMI Capture\n'
 e[90:108]=bytes.fromhex('000000fd003b3d1f2003010a202020202020')
 e[108:126]=b'\0\0\0\xff\0'+b'H713-0000001\n'
 assert len(e)==128
 e[127]=(-sum(e))&255
 return bytes(e)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();a.output.write_bytes(make_edid())
