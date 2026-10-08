#!/usr/bin/env python3
"""Offline stock MIPS PLL execution; byte MMIO helpers are simulated, never hardware.

Reads default to zero and writes only update a Python dictionary. A firmware
poll can therefore reach the instruction bound: that is an incomplete run,
not a hardware failure. The full-init result does not prove real PLL lock.
"""
import struct,json,hashlib
from pathlib import Path
from unicorn import *
from unicorn.mips_const import *
b=(Path(__file__).resolve().parents[2]/'local/mips-display/board-b-mips/display.bin').read_bytes()
assert hashlib.sha256(b).hexdigest()=='4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce'
def run(entry, initial=0, initialize_zero=False, collapse_byte_writes=False, word_write_shim=False):
 u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
 u.ctl_set_cpu_model(UC_CPU_MIPS32_24KC)
 u.mem_map(0x0b100000,(len(b)+4095)&~4095);u.mem_write(0x0b100000,b)
 if initialize_zero:
  assert struct.unpack_from('<I',b,0x8b13c628-0x8b100000)[0]==0x06000017
  u.mem_write(0x0b13c628,struct.pack('<I',0x1a000017))
 u.mem_map(0x100000,0x100000);u.mem_map(0xd000000,0x10000)
 arg=0x8d000000;stop=0x801f0000;stack=0x80180000
 u.mem_write(arg&0x1fffffff,struct.pack('<7I',74250,6144,48000,0,0,0,0))
 for r,v in [(4,0x06880000),(5,arg),(29,stack),(31,stop)]:u.reg_write(UC_MIPS_REG_0+r,v)
 regs={0x0688000c+i:(initial>>(8*i))&255 for i in range(4)};events=[];visited={};logs=[]
 def reg(r):return u.reg_read(UC_MIPS_REG_0+r)
 def ret(v=0):u.reg_write(UC_MIPS_REG_0+2,v);u.reg_write(UC_MIPS_REG_PC,reg(31))
 def check(a):
  if not 0x06880000<=a<0x0688001c:raise ValueError(hex(a))
 def store(addr, value):
  if word_write_shim and (0x06880000<=addr<0x06880014) and not (0x06880008<=addr<0x0688000c):
   regs[addr]=value&255
  elif collapse_byte_writes:
   aligned=addr&~3
   for lane in range(4):regs[aligned+lane]=0
   regs[aligned]=value&255
  else:regs[addr]=value&255
 def hook(u,a,size,data):
  visited[a]=visited.get(a,0)+1
  if a==stop:u.emu_stop();return
  if a==0x8b150948:
   logs.append(hex(reg(7)));ret();return
  if a==0x8b180340:
   addr=reg(4);check(addr);ret(regs.get(addr,0));return
  if a==0x8b180394:
   addr=reg(4);check(addr);v=reg(5)&255;events.append(dict(addr=f'{addr:08x}',value=v));store(addr,v);ret();return
  if a==0x8b1803dc:
   addr=reg(4);check(addr);v=(regs.get(addr,0)&~reg(5))|(reg(6)&reg(5));events.append(dict(addr=f'{addr:08x}',value=v));store(addr,v);ret();return
 u.hook_add(UC_HOOK_CODE,hook)
 u.emu_start(entry,0,count=200000)
 words={f'{a:08x}':sum(regs.get(a+i,0)<<(8*i) for i in range(4)) for a in range(0x06880000,0x0688001c,4)}
 return dict(entry=f'{entry:08x}',initial_control_word=initial,initialize_zero=initialize_zero,collapse_byte_writes=collapse_byte_writes,word_write_shim=word_write_shim,returned=u.reg_read(UC_MIPS_REG_PC)==stop,result=reg(2),events=events,words=words,max_visits=max(visited.values()),instructions=sum(visited.values()),log_functions=logs)
if __name__ == '__main__':
 print(json.dumps([run(0x8b13bcb8),run(0x8b13c000),run(0x8b13c524,initialize_zero=True),run(0x8b13c524,initialize_zero=True,collapse_byte_writes=True)],indent=2))
