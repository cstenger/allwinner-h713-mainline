#!/usr/bin/env python3
"""Generate the canonical H713 HDMI-input EDID."""
import argparse
from pathlib import Path

DTD_720P60 = "011d007251d01e206e28550040b41000001e"
DISPLAY_NAME = b"H713 HDMI IN\n"
DISPLAY_RANGE = "000000fd003b3d1f2e08000a202020202020"


def checksum(block):
 return (-sum(block)) & 255


def make_cta_extension():
 # CTA-861 revision 3.  Advertise only capabilities that this project can
 # actually exercise: VIC 4 (native 720p60), VIC 1 (safe VGA fallback), and
 # two-channel baseline HDMI LPCM.  The HDMI VSDB makes this an HDMI sink
 # rather than an audio-capable DVI display; physical address 1.0.0.0 is a
 # harmless root-level address until CEC is implemented.
 blocks = bytes([
  0x42, 0x04, 0x01,              # video: VIC 4, then VIC 1
  0x23, 0x09, 0x07, 0x01,        # basic audio: LPCM, 2ch, 32/44.1/48 kHz, 16-bit
  0x83, 0x01, 0x00, 0x00,        # speakers: front left/right
  0x65, 0x03, 0x0c, 0x00, 0x10, 0x00,  # HDMI VSDB, PA 1.0.0.0
  0xe2, 0x00, 0x4a,              # VCDB: selectable RGB, always underscan
 ])
 e=bytearray(128)
 # Underscan, Basic Audio, and one native detailed timing (the base block's
 # preferred DTD).  Basic Audio requires 2ch 16-bit LPCM at all three baseline
 # sample rates, which the Audio Data Block above states explicitly.
 e[0:4]=bytes([0x02,0x03,4+len(blocks),0xc1])
 e[4:4+len(blocks)]=blocks
 e[127]=checksum(e)
 return bytes(e)


def make_edid():
 e=bytearray(128);e[:8]=bytes.fromhex('00ffffffffffff00');e[8:10]=(0x2070).to_bytes(2,'big');e[10:12]=(0x713).to_bytes(2,'little');e[12:16]=(0).to_bytes(4,'little');e[16:25]=bytes([38,36,1,3,0x80,32,18,120,0x0f])
 coords=[round(v*1024) for v in [.64,.33,.30,.60,.15,.06,.3127,.329]]
 e[25]=(coords[0]&3)<<6|(coords[1]&3)<<4|(coords[2]&3)<<2|(coords[3]&3)
 e[26]=(coords[4]&3)<<6|(coords[5]&3)<<4|(coords[6]&3)<<2|(coords[7]&3)
 e[27:35]=bytes(v>>2 for v in coords);e[35]=0x20;e[38:54]=b'\x01\x01'*8
 e[54:72]=bytes.fromhex(DTD_720P60)
 e[72:90]=b'\0\0\0\xfc\0'+DISPLAY_NAME
 e[90:108]=bytes.fromhex(DISPLAY_RANGE)
 e[108:126]=b'\0\0\0\xff\0'+b'H713-0000001\n'
 e[126]=1
 e[127]=checksum(e)
 result=bytes(e)+make_cta_extension()
 assert len(result)==256
 assert sum(result[:128])%256==0 and sum(result[128:])%256==0
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('output',type=Path)
 a=p.parse_args();a.output.write_bytes(make_edid())
