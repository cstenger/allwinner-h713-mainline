#!/usr/bin/env python3
"""Map every MMIO access in the image by tracking lui-loaded bases across offsets.

block-survey.py counts lui SITES, which undercounts a block reached through one
lui and many displacements -- that is how 0x05180000 read as "1 site".
"""
import struct, sys
BASE=0x8b100000
data=open('/home/chris/Projects/h713/local/mips-display/board-b-mips/display.bin','rb').read()
N=len(data)//4
W=struct.unpack('<%dI'%N,data[:N*4])
LOADS={0x23,0x20,0x24,0x21,0x25}; STORES={0x2b,0x28,0x29}
hits={}
base={}
for i,w in enumerate(W):
    va=BASE+i*4; op=w>>26; rt=(w>>16)&31; rs=(w>>21)&31
    imm=w&0xffff; simm=imm-0x10000 if imm&0x8000 else imm
    if op==0x0f:
        base[rt]=imm<<16
    elif op==0x09 and rs in base and rs!=rt:
        base[rt]=base[rs]+simm            # addiu rt, rs, off  -> derived base
    elif op in LOADS|STORES and rs in base:
        full=base[rs]+simm
        if 0xba000000<=full<0xbb000000:
            arm=full-0xB5000000
            blk=arm & 0xffff0000
            hits.setdefault(blk,{}).setdefault(arm,set()).add('w' if op in STORES else 'r')
    elif op in (0x00,) and ((w>>11)&31) in base:
        pass
for blk in sorted(hits):
    regs=hits[blk]
    print(f"=== {blk:#010x}   {len(regs)} distinct registers, "
          f"{sum(1 for a in regs if 'w' in regs[a])} written")
for blk in (0x05180000,0x05040000,0x050c0000):
    if blk in hits:
        print(f"\n--- {blk:#010x} ---")
        for a in sorted(hits[blk]):
            print(f"   {a:#010x}  {'/'.join(sorted(hits[blk][a]))}")
