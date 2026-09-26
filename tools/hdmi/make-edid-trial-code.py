#!/usr/bin/env python3
"""Emit a fixed OR1K program for a backed-up HDMI EDID/HPD bench trial."""
import argparse,runpy
from pathlib import Path
CODE=0x4000;PAYLOAD=0x4680;BACKUPS=[0x4780,0x4880,0x4980];META=0x4a80
class Program:
 def __init__(self):self.words=[];self.labels={};self.fixups=[]
 def emit(self,w,s):self.words.append((w,s))
 def label(self,n):self.labels[n]=len(self.words)
 def branch(self,op,label):self.fixups.append((len(self.words),op,label));self.emit(0,label)
 def done(self):
  for i,op,n in self.fixups:self.words[i]=(op<<26 | ((self.labels[n]-i)&0x3ffffff),f'{["j","jal","?","bnf","bf"][op]} {n}')
  return self.words
p=Program()
def nop():p.emit(0x15000000,'nop')
def hi(d,i):p.emit(0x18000000|d<<21|i,f'movhi r{d},0x{i:x}')
def ori(d,a,i):p.emit(0xa8000000|d<<21|a<<16|i,f'ori r{d},r{a},0x{i:x}')
def addi(d,a,i):p.emit(0x9c000000|d<<21|a<<16|(i&0xffff),f'addi r{d},r{a},{i}')
def lw(d,a,i=0):p.emit(0x84000000|d<<21|a<<16|(i&0xffff),f'lwz r{d},{i}(r{a})')
def sw(a,b,i=0):
 u=i&0xffff;p.emit(0xd4000000|((u>>11)<<21)|a<<16|b<<11|(u&0x7ff),f'sw {i}(r{a}),r{b}')
def andr(d,a,b):p.emit(0xe0000003|d<<21|a<<16|b<<11,f'and r{d},r{a},r{b}')
def sfne(a,b):p.emit(0xe4200000|a<<16|b<<11,f'sfne r{a},r{b}')
def sfnei(a,i):p.emit(0xbc200000|a<<16|(i&0xffff),f'sfnei r{a},{i}')
def addr(d,a):hi(d,a>>16);ori(d,d,a&0xffff)
def io(a):
 assert a>>16==0x0709
 ori(5,11,a&0xffff)
def clear_enable():
 io(0x07091b04);lw(4,5);addi(2,0,-8);andr(4,4,2);sw(5,4)
def hold_hpd():
 io(0x07091014);lw(4,5);ori(4,4,7);sw(5,4)
def copy(src,dst,n,label):
 (addr(5,src) if src>65535 else ori(5,0,src));(addr(6,dst) if dst>65535 else ori(6,0,dst));ori(7,0,n//4)
 p.label(label);lw(8,5);sw(6,8);addi(5,5,4);addi(6,6,4);addi(7,7,-1);sfnei(7,0);p.branch(4,label);nop()
def verify(src,dst,n,label,fail):
 ori(5,0,src);addr(6,dst);ori(7,0,n//4);p.label(label);lw(8,5);lw(9,6);sfne(8,9);p.branch(4,fail);nop();addi(5,5,4);addi(6,6,4);addi(7,7,-1);sfnei(7,0);p.branch(4,label);nop()
hi(0,0);hi(11,0x0709);ori(3,0,0x4f00);hi(10,0x4844);ori(10,10,0x4d49);sw(3,10)
for i,a in enumerate([0x07091014,0x07091b00,0x07091b04,0x07091b08]):io(a);lw(4,5);sw(0,4,META+4*i)
lw(4,0,META);sw(3,4,4)
for i,a in enumerate([0x07091020,0x07091030,0x07091034,0x07091038]):io(a);lw(4,5);sw(0,4,META+16+4*i)
for i in range(3):copy(0x07091c00+0x100*i,BACKUPS[i],256,f'backup{i}')
sw(3,10,20)
# backup-only mode signals completion without changing any peripheral.
lw(4,3,32);sfnei(4,0);p.branch(4,'activate');nop();sw(3,10,8);sw(3,10,28);p.branch(0,'spin');nop()
p.label('activate')
for i,v in enumerate([0xffffff00,0x00ffffff]):
 lw(4,0,PAYLOAD+4*i);sw(3,4,84+4*i);addr(2,v);sfne(4,2);p.branch(4,'data_failed');nop()
hold_hpd();clear_enable()
lw(4,3,64);sfnei(4,0);p.branch(3,'skip_io');nop()
for a,v in [(0x07091030,0),(0x07091034,24),(0x07091038,24),(0x07091020,3)]:io(a);ori(4,0,v);sw(5,4)
p.label('skip_io')
for a,v in [(0x07091b00,0xa0a0a0a0),(0x07091b08,0xc0c0c0c0)]:io(a);addr(4,v);sw(5,4)
for i in range(3):copy(PAYLOAD,0x07091c00+0x100*i,256,f'write{i}')
for i in range(3):verify(PAYLOAD,0x07091c00+0x100*i,256,f'verify{i}','mismatch')
for i,a in enumerate([0x07091c00,0x07091d00,0x07091e00]):io(a);lw(4,5);sw(3,4,92+4*i)
io(0x07091b04);lw(4,5);ori(4,4,7);sw(5,4)
io(0x07091014);lw(4,0,META);addi(2,0,-8);andr(4,4,2);sw(5,4)

for i,a in enumerate([0x07091014,0x07091b00,0x07091b04,0x07091b08,0x07091c00,0x07091d00,0x07091e00]):io(a);lw(4,5);sw(3,4,36+4*i)
for i,a in enumerate([0x07091020,0x07091030,0x07091034,0x07091038]):io(a);lw(4,5);sw(3,4,68+4*i)
sw(3,10,8);p.label('wait');lw(4,3,16);sfnei(4,0);p.branch(3,'wait');nop()
p.label('restore');hold_hpd();clear_enable()
for i in range(3):copy(BACKUPS[i],0x07091c00+0x100*i,256,f'restore{i}')
for i in range(3):verify(BACKUPS[i],0x07091c00+0x100*i,256,f'recheck{i}','restore_failed')
for i,a in enumerate([0x07091b00,0x07091b04,0x07091b08,0x07091014]):
 io(a);lw(4,0,META+4*([1,2,3,0][i]));sw(5,4)
lw(4,3,64);sfnei(4,0);p.branch(3,'skip_io_restore');nop()
for i,a in enumerate([0x07091020,0x07091030,0x07091034,0x07091038]):io(a);lw(4,0,META+16+4*i);sw(5,4)
p.label('skip_io_restore');sw(3,10,28);p.label('spin');p.branch(0,'spin');nop()
p.label('mismatch');ori(4,0,1);sw(3,4,24);p.branch(0,'restore');nop()
p.label('data_failed');ori(4,0,3);sw(3,4,24);sw(3,10,28);p.branch(0,'spin');nop()
p.label('restore_failed');ori(4,0,2);sw(3,4,24);p.branch(0,'spin');nop()
w=p.done()
if len(w)%2:w.append((0x15000000,'pair padding'))
assert CODE+4*len(w)<=PAYLOAD, len(w)
assert PAYLOAD+256<=BACKUPS[0] and BACKUPS[-1]+256<=META and META+32<=0x4c00
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--mode',choices=('640x480','1280x720'),default='640x480');a.add_argument('output',type=Path);args=a.parse_args();edid=runpy.run_path(str(Path(__file__).with_name('make-test-edid.py')))['make_edid'](args.mode)+bytes(128)
 text='#define EDID_PAYLOAD_OFFSET 0x4680\n#define EDID_BACKUP_OFFSET 0x4780\n#define EDID_META_OFFSET 0x4a80\n/* Generated by tools/hdmi/make-edid-trial-code.py; fixed bench program. */\nstatic const u32 edid_trial_code[] = {\n'+''.join(f'\t0x{v:08x}, /* {CODE+4*i:04x}: {s} */\n' for i,(v,s) in enumerate(w))+'};\nstatic const u8 edid_trial_data[] = {\n'+''.join('\t'+','.join(f'0x{x:02x}' for x in edid[i:i+16])+',\n' for i in range(0,len(edid),16))+'};\n';args.output.write_text(text);print(f'{len(w)} instructions; data 0x{PAYLOAD:x}; backup-only and reversible trial modes')
