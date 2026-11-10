#!/usr/bin/env python3
"""Generate a volatile replacement for the verified 391-entry U-Boot trace table.
No device writes. Run with output directory; emulator checks every trampoline.
Trace words use existing shared trace page +0x80..0x9c through KSEG1.
"""
import hashlib,json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN,UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0,UC_MIPS_REG_PC
BASE=0x8b100000
fw=Path('local/mips-display/board-b-mips/display.bin').read_bytes()
assert hashlib.sha256(fw).hexdigest()=='4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce'
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
def words(ws):return struct.pack('<%dI'%len(ws),*ws)
def ins(op,rt,rs,imm):return op<<26|rs<<21|rt<<16|(imm&65535)
def jump(a):return 0x08000000|((a>>2)&0x3ffffff)
def original(a):return list(struct.unpack_from('<2I',fw,a-BASE))
# count slot, optional last-value register, condition on message ID, exit style
sites=[('event8',0x8b156bf8,0x80,None,True,'normal'),
 ('callback',0x8b147678,0x84,None,False,'thunk'),
 ('check',0x8b147dd0,0x88,None,False,'normal'),
 ('return0',0x8b147ee4,0x8c,2,False,'return'),
 ('return1',0x8b147f34,0x8c,2,False,'return'),
 ('return2',0x8b147fbc,0x8c,2,False,'return'),
 ('rpc',0x8b10a218,0x94,None,False,'normal'),
 ('hal',0x8b14b448,0x98,4,False,'normal')]
patches=[];hooks=[];cave=BASE+0x400
for name,site,slot,value,cond,kind in sites:
 old=original(site)
 code=[ins(9,29,29,-16),ins(43,24,29,0),ins(43,25,29,4)]
 branch=None
 if cond:
  code += [ins(35,25,5,0),ins(9,24,0,8)]
  branch=len(code);code += [0,0]
 code += [ins(15,24,0,0xae34),ins(35,25,24,slot),ins(9,25,25,1),ins(43,25,24,slot)]
 if value is not None:code += [ins(43,value,24,slot+4)]
 if branch is not None:code[branch]=ins(5,25,24,len(code)-branch-1)
 code += [ins(35,24,29,0),ins(35,25,29,4),ins(9,29,29,16)]
 if kind=='normal':code += old+[jump(site+8),0];end=site+8
 elif kind=='thunk':code += old;end=0x8b147390
 else:code += old;end=BASE+0x2000
 assert not any(fw[cave-BASE:cave-BASE+len(code)*4])
 for i,w in enumerate(code):patches.append((cave-0x40000000+i*4,0,w))
 patches += [(site-0x40000000,old[0],jump(cave)),(site-0x40000000+4,old[1],0)]
 hooks.append((name,site,cave,code,end,kind,slot,value,cond))
 cave+=len(code)*4
assert cave<=BASE+0xb00
# Compare GPRs and original stack effects against the uninstrumented pair.
for name,site,stub,code,end,kind,slot,value,cond in hooks:
 for event in [7,8]:
  for retval in [0,1]:
   states=[]
   for patched in [False,True]:
    u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
    # Unicorn translates KSEG0/1 into physical addresses.
    u.mem_map(0x0b100000,0x200000);u.mem_write(0x0b100000,fw)
    u.mem_map(0x0e340000,0x1000);u.mem_map(0x100000,0x20000)
    for r in range(1,32):u.reg_write(UC_MIPS_REG_0+r,0x100100+r*16)
    u.reg_write(UC_MIPS_REG_0+29,0x110000);u.reg_write(UC_MIPS_REG_0+31,BASE+0x2000)
    u.reg_write(UC_MIPS_REG_0+2,retval)
    u.mem_write(u.reg_read(UC_MIPS_REG_0+5),words([event]))
    if patched:
     u.mem_write(site&0x1fffffff,words([jump(stub),0]));u.mem_write(stub&0x1fffffff,words(code))
    u.hook_add(UC_HOOK_CODE,lambda uc,a,size,data: uc.emu_stop() if a==end else None)
    u.emu_start(site,0,count=100)
    assert u.reg_read(UC_MIPS_REG_PC)==end,(name,hex(u.reg_read(UC_MIPS_REG_PC)))
    states.append([u.reg_read(UC_MIPS_REG_0+r) for r in range(32)])
    if patched:
     count=struct.unpack('<I',u.mem_read(0x0e340000+slot,4))[0]
     assert count==int(not cond or event==8),(name,count)
     if value is not None:
      expected=retval if value==2 else 0x100100+4*16
      assert struct.unpack('<I',u.mem_read(0x0e340000+slot+4,4))[0]==expected
   assert states[0]==states[1],name
assert len(patches)<=391
# Safe no-op padding: preflight checks all entries before any write.
patches += [(0x4b100b00,0,0)]*(391-len(patches))
blob=b''.join(struct.pack('<QII',*p) for p in patches)
(out/'event8-table.bin').write_bytes(blob)
(out/'hooks.json').write_text(json.dumps([{'name':n,'site':hex(s),'stub':hex(c),'words':[hex(w) for w in ws]} for n,s,c,ws,*_ in hooks],indent=2)+'\n')
print('PASS: 32 paired emulator cases; all GPRs preserved; counters and captured values checked')
print('table bytes',len(blob),'crc32',hex(__import__('zlib').crc32(blob)),'cave end',hex(cave))
