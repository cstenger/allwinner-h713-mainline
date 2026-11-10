#!/usr/bin/env python3
"""Emit a fixed OR1K program for a backed-up HDMI EDID/HPD bench trial."""
import argparse,runpy
from pathlib import Path
CODE=0x4000;PAYLOAD=0x4680;BACKUPS=[0x4780,0x4880,0x4980];META=0x4a80;CHECK=META+32
# --readvertise: the code page is full, so the command handler sits in the free
# SRAM after CHECK. Commands share the stop word (+16); the SCP acks at ACK.
EXT=CHECK+32;ACK=116;HOLD,DDC_ON,RELEASE,DDC_OFF,HPD_LOW=2,3,4,5,6
# META order: the saved originals, and with verify_restore their post-restore readback at CHECK.
REGS=[0x07091014,0x07091b00,0x07091b04,0x07091b08,0x07091020,0x07091030,0x07091034,0x07091038]
# --sample-ddc (diagnostic, read-only): the idle wait loop runs a sampler in the
# free SRAM after the 13 trap stubs. Only receiver registers the stock SCP itself
# accesses are read; nothing is ever written to the receiver by the sampler.
SAMP=0x4da0;FIRST=0x4e80;SEQ=0x4f80;CLR=0x4f84;PAIRS=0x4f88
SAMPLED=[0x07091000,0x07091008,0x07091014,0x07091018,0x0709101c,0x07091020,
         0x07091030,0x07091034,0x07091038,0x07091b00,0x07091b04,0x07091b08]
# --scan-ddc (diagnostic, read-only): the same idle-loop sampler shape, but its
# 16-entry address table lives in SRAM (free words after the request handler)
# so the ARM can move a window across the undocumented DDC block 0x07091b00-
# 0x07091bfc at run time. It starts on 0x07091b04 only (stock-read). Each
# clear re-records first; last/toggled are separate arrays.
SCAN_TABLE=0x4ba8;SCAN_N=16;SCAN_LAST=0x4e80;SCAN_MASK=0x4ec0;SCAN_FIRST=0x4f88;SCAN_IDLE=0x1b04
# --scan-bytes (diagnostic, read-only): the same scanner, but table entries are
# full SCP addresses read with l.lbz, for the byte-wide MIPS HDCP/DDC wrapper at
# 0x06840000. Parked entries read the SCP's own SRAM marker word (0x4f00).
SCAN_BYTES_IDLE=0x4f00
# Byte mode also timestamps activity: on the first pass after a clear in which
# any watched bit toggled, ACT = seq+1 (0 = none yet). The module arms the
# window on the MIPS wrapper's DDC line byte at owner ready.
SCAN_ACT=0x4fc8;SCAN_ARM=0x06840094;SCAN_ARM_N=4
# ... plus LASTACT = seq+1 of the latest pass with a toggle and BUSY = number of
# passes with a toggle, both since the last clear: the length of a transfer.
SCAN_LASTACT=0x4fcc;SCAN_BUSY=0x4fd0
# --scan-words (diagnostic, read-only): the same full-address scanner with l.lwz,
# for the SCP-owned receiver block 0x07091000-0x07091bfc. Parked on SCP SRAM; no
# window armed at owner ready (the module allows windows only inside that block).
class Program:
 def __init__(self,base=CODE):self.base=base;self.words=[];self.labels={};self.fixups=[]
 def emit(self,w,s):self.words.append((w,s))
 def label(self,n):self.labels[n]=len(self.words)
 def branch(self,op,label):self.fixups.append((len(self.words),op,label));self.emit(0,label)
 def done(self):
  for i,op,n in self.fixups:
   # A string targets a label here; an int is an absolute SRAM address elsewhere.
   to=self.labels[n] if isinstance(n,str) else (n-self.base)//4
   self.words[i]=(op<<26 | ((to-i)&0x3ffffff),f'{["j","jal","?","bnf","bf"][op]} {n if isinstance(n,str) else hex(n)}')
  return self.words
def build(verify_restore=False,readvertise=None,defer_initial_hpd=False,defer_initial_ddc=False,isolate_ddc=False,isolate_hpd=False,sampler=None,scan=None,scan_bytes=False,scan_words=False):
 """Assemble the program; verify_restore adds the post-restore register readback.
 readvertise, a list, receives the command handler placed at EXT."""
 global p
 if defer_initial_hpd and (not verify_restore or readvertise is None):
  raise ValueError('deferred initial HPD requires restore verification and request handler')
 if defer_initial_ddc and not defer_initial_hpd:
  raise ValueError('deferred initial DDC requires deferred initial HPD')
 if isolate_ddc and (not verify_restore or readvertise is None or defer_initial_hpd):
  raise ValueError('DDC isolation requires the original initial advert and verified request/restore protocol')
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
 if not defer_initial_ddc:
  io(0x07091b04);lw(4,5);ori(4,4,7);sw(5,4)
 if not defer_initial_hpd:
  io(0x07091014);lw(4,0,META);addi(2,0,-8);andr(4,4,2);sw(5,4)

 for i,a in enumerate([0x07091014,0x07091b00,0x07091b04,0x07091b08,0x07091c00,0x07091d00,0x07091e00]):io(a);lw(4,5);sw(3,4,36+4*i)
 for i,a in enumerate([0x07091020,0x07091030,0x07091034,0x07091038]):io(a);lw(4,5);sw(3,4,68+4*i)
 sw(3,10,8);p.label('wait');lw(4,3,16);sfnei(4,0);p.branch(3,SAMP if sampler is not None or scan is not None else 'wait');nop()
 # Stop is 1; any other request goes to the handler, which returns here.
 if readvertise is not None:sfnei(4,1);p.branch(4,EXT);nop()
 p.label('restore');hold_hpd();clear_enable()
 for i in range(3):copy(BACKUPS[i],0x07091c00+0x100*i,256,f'restore{i}')
 for i in range(3):verify(BACKUPS[i],0x07091c00+0x100*i,256,f'recheck{i}','restore_failed')
 for i,a in enumerate([0x07091b00,0x07091b04,0x07091b08,0x07091014]):
  io(a);lw(4,0,META+4*([1,2,3,0][i]));sw(5,4)
 lw(4,3,64);sfnei(4,0);p.branch(3,'skip_io_restore');nop()
 for i,a in enumerate([0x07091020,0x07091030,0x07091034,0x07091038]):io(a);lw(4,0,META+16+4*i);sw(5,4)
 p.label('skip_io_restore')
 # Read every restored register after the last write, before completion is signalled.
 if verify_restore:
  for i,a in enumerate(REGS):lw(4,11,a-0x07090000);sw(0,4,CHECK+4*i)
 sw(3,10,28);p.label('spin');p.branch(0,'spin');nop()
 p.label('mismatch');ori(4,0,1);sw(3,4,24);p.branch(0,'restore');nop()
 p.label('data_failed');ori(4,0,3);sw(3,4,24);sw(3,10,28);p.branch(0,'spin');nop()
 p.label('restore_failed');ori(4,0,2);sw(3,4,24);p.branch(0,'spin');nop()
 w=p.done()
 if len(w)%2:w.append((0x15000000,'pair padding'))
 assert CODE+4*len(w)<=PAYLOAD, len(w)
 if readvertise is not None:
  wait=CODE+4*p.labels['wait']
  p=Program(EXT)
  # The request stays in r4; register writes use r6 so it survives to the ack.
  sfnei(4,HOLD);p.branch(4,'ddc_on');nop()
  io(0x07091014);lw(6,5);ori(6,6,7);sw(5,6)
  io(0x07091b04);lw(6,5);addi(2,0,-8);andr(6,6,2);sw(5,6);p.branch(0,'ack');nop()
  p.label('ddc_on');sfnei(4,DDC_ON);p.branch(4,'release');nop()
  io(0x07091b04);lw(6,5);ori(6,6,7);sw(5,6)
  if defer_initial_ddc or isolate_ddc:lw(6,5);sw(3,6,124)
  if isolate_ddc:io(0x07091014);lw(6,5);sw(3,6,120)
  p.branch(0,'ack');nop()
  p.label('release');sfnei(4,RELEASE);p.branch(4,'ddc_off' if isolate_ddc else 'hpd_low' if isolate_hpd else 'unknown');nop()
  io(0x07091014);lw(6,0,META);addi(2,0,-8);andr(6,6,2);sw(5,6)
  if defer_initial_hpd or isolate_ddc or isolate_hpd:
   # Read back through SCP after the write; ARM only sees copied SRAM.
   lw(6,5);sw(3,6,120);io(0x07091b04);lw(6,5);sw(3,6,124)
  p.branch(0,'ack');nop()
  if isolate_ddc:
   # Disable only DDC; deliberately never write HPD in this branch.
   p.label('ddc_off');sfnei(4,DDC_OFF);p.branch(4,'unknown');nop()
   io(0x07091b04);lw(6,5);addi(2,0,-8);andr(6,6,2);sw(5,6)
   lw(6,5);sw(3,6,124);io(0x07091014);lw(6,5);sw(3,6,120)
   p.branch(0,'ack');nop()
  if isolate_hpd:
   # Force HPD low only; deliberately never write DDC in this branch.
   p.label('hpd_low');sfnei(4,HPD_LOW);p.branch(4,'unknown');nop()
   io(0x07091014);lw(6,5);ori(6,6,7);sw(5,6)
   lw(6,5);sw(3,6,120);io(0x07091b04);lw(6,5);sw(3,6,124)
   p.branch(0,'ack');nop()
  p.label('unknown');ori(4,0,0xff) # acked, nothing written
  p.label('ack');sw(3,4,ACK);sw(3,0,16);p.branch(0,wait);nop()
  readvertise[:]=p.done()
  if len(readvertise)%2:readvertise.append((0x15000000,'pair padding'))
  assert EXT+4*len(readvertise)<=0x4c00, len(readvertise)
 assert PAYLOAD+256<=BACKUPS[0] and BACKUPS[-1]+256<=META and CHECK+32<=0x4c00
 if sampler is not None:
  # `wait` was taken from the main program before the handler was assembled.
  p=Program(SAMP)
  def r3(op,d,a,b,n):p.emit(0xe0000000|op|d<<21|a<<16|b<<11,f'{n} r{d},r{a},r{b}')
  # r12 table, r13 last/sticky pair, r19 first, r14 value, r15 clearing,
  # r20 first sample, r16 count, r17/r18 temps. None is live in the main
  # program across the wait loop (it uses r0-r11 only).
  lw(17,0,SEQ);lw(15,0,CLR);addi(20,0,0)
  sfnei(17,0);p.branch(4,'notfirst');nop();addi(20,0,1);addi(15,0,1)
  p.label('notfirst')
  ori(12,0,0);tbl=len(p.words)-1  # patched to the table address
  ori(13,0,PAIRS);ori(19,0,FIRST);ori(16,0,len(SAMPLED))
  p.label('loop')
  lw(14,12);r3(0,14,14,11,'add');lw(14,14)          # value of 0x0709xxxx
  sfnei(20,0);p.branch(3,'nofirst');nop();sw(19,14)
  p.label('nofirst')
  sfnei(15,0);p.branch(4,'clear');lw(17,13)          # delay slot: last
  r3(5,17,17,14,'xor');lw(18,13,4);r3(4,18,18,17,'or');p.branch(0,'store');sw(13,18,4)
  p.label('clear');sw(13,0,4)
  p.label('store');sw(13,14);addi(12,12,4);addi(19,19,4);addi(16,16,-1);sfnei(16,0);p.branch(4,'loop');addi(13,13,8)
  sfnei(15,0);p.branch(3,'seq');nop();sw(0,0,CLR)
  p.label('seq');lw(17,0,SEQ);addi(17,17,1);sw(0,17,SEQ)
  p.branch(0,wait);nop()
  p.label('table')
  addr_t=SAMP+4*len(p.words)
  p.words[tbl]=(0xa8000000|12<<21|0<<16|addr_t,f'ori r12,r0,0x{addr_t:x}')
  for a in SAMPLED:p.emit(a&0xffff,f'.word 0x{a&0xffff:04x} ({a:#010x})')
  sampler[:]=p.done()
  if len(sampler)%2:sampler.append((0x15000000,'pair padding'))
  assert SAMP>=0x4c00+0x20*13 and SAMP+4*len(sampler)<=FIRST, len(sampler)
  assert FIRST+4*len(SAMPLED)<=0x4f00 and PAIRS+8*len(SAMPLED)<=0x5000
 if scan is not None:
  assert sampler is None and readvertise is not None
  assert EXT+4*len(readvertise)<=SCAN_TABLE and SCAN_TABLE+4*SCAN_N<=0x4c00
  p=Program(SAMP)
  def r3(op,d,a,b,n):p.emit(0xe0000000|op|d<<21|a<<16|b<<11,f'{n} r{d},r{a},r{b}')
  # Same registers as the sampler: r12 table, r13 last (mask at +64), r19
  # first, r14 value, r15 clearing (= record first), r16 count, r17/r18 temps.
  lw(15,0,CLR);r3(4,20,15,0,'or')
  if scan_bytes or scan_words:addi(21,0,0)                         # r21: OR of this pass's toggles
  ori(12,0,SCAN_TABLE);ori(13,0,SCAN_LAST);ori(19,0,SCAN_FIRST);ori(16,0,SCAN_N)
  p.label('loop')
  full=scan_bytes or scan_words
  if scan_words:
   lw(14,12);lw(14,14)                                # word at a full address
  elif scan_bytes:
   lw(14,12);p.emit(0x8c000000|14<<21|14<<16,'lbz r14,0(r14)')   # byte at a full address
  else:
   lw(14,12);r3(0,14,14,11,'add');lw(14,14)          # value of 0x0709xxxx
  sfnei(20,0);p.branch(3,'nofirst');nop();sw(19,14)
  p.label('nofirst')
  sfnei(15,0);p.branch(4,'clear');lw(17,13)          # delay slot: last
  r3(5,17,17,14,'xor');lw(18,13,SCAN_MASK-SCAN_LAST);r3(4,18,18,17,'or')
  if full:r3(4,21,21,17,'or')
  p.branch(0,'store');sw(13,18,SCAN_MASK-SCAN_LAST)
  p.label('clear');sw(13,0,SCAN_MASK-SCAN_LAST)
  p.label('store');sw(13,14);addi(12,12,4);addi(19,19,4);addi(16,16,-1);sfnei(16,0);p.branch(4,'loop');addi(13,13,4)
  if full:
   sfnei(21,0);p.branch(3,'quiet');lw(17,0,SEQ)       # delay slot: this pass's seq
   addi(17,17,1);sw(0,17,SCAN_LASTACT)
   lw(18,0,SCAN_BUSY);addi(18,18,1);sw(0,18,SCAN_BUSY)
   lw(18,0,SCAN_ACT);sfnei(18,0);p.branch(4,'quiet');nop()
   sw(0,17,SCAN_ACT)
   p.label('quiet')
  sfnei(15,0);p.branch(3,'seq');nop();sw(0,0,CLR)
  if full:sw(0,0,SCAN_ACT);sw(0,0,SCAN_LASTACT);sw(0,0,SCAN_BUSY)   # a clear re-arms them
  p.label('seq');lw(17,0,SEQ);addi(17,17,1);sw(0,17,SEQ)
  p.branch(0,wait);nop()
  scan[:]=p.done()
  if len(scan)%2:scan.append((0x15000000,'pair padding'))
  assert SAMP>=0x4c00+0x20*13 and SAMP+4*len(scan)<=SCAN_LAST, len(scan)
  assert SCAN_MASK+4*SCAN_N<=0x4f00 and SEQ<SCAN_FIRST and SCAN_FIRST+4*SCAN_N<=SCAN_ACT<SCAN_LASTACT<SCAN_BUSY<0x5000
 return w
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__)
 a.add_argument('--mode',choices=('640x480','1280x720'),default='640x480')
 a.add_argument('--edid',type=Path,help='Use a validated 256-byte EDID (binary or .hex), including its audio extension')
 a.add_argument('--verify-restore',action='store_true',help='Record post-restore HPD/DDC/IO readback at 0x%x for the lifetime owner'%CHECK)
 a.add_argument('--readvertise',action='store_true',help='Add the HPD hold/DDC enable/release request handler at 0x%x'%EXT)
 a.add_argument('--defer-initial-hpd',action='store_true',help='Keep initial HPD low until the owner requests release after DDC settling')
 a.add_argument('--defer-initial-ddc',action='store_true',help='Also keep DDC disabled until the owner completes an initial 2000 ms hold')
 a.add_argument('--isolate-ddc',action='store_true',help='Diagnostic only: allow DDC-off without writing HPD, with SCP readbacks')
 a.add_argument('--sample-ddc',action='store_true',help='Diagnostic only: read-only sampler of 12 stock-accessed receiver registers in the idle wait loop')
 a.add_argument('--scan-ddc',action='store_true',help='Diagnostic only: read-only 16-register window, moved at run time across 0x07091b00-0x07091bfc')
 a.add_argument('--scan-bytes',action='store_true',help='Diagnostic only: the run-time window reads bytes at full addresses (0x06840000-0x06840fff wrapper)')
 a.add_argument('--scan-words',action='store_true',help='Diagnostic only: the run-time window reads words at full addresses in 0x07091000-0x07091bfc')
 a.add_argument('--isolate-hpd',action='store_true',help='Diagnostic only: allow HPD-low without writing DDC, with SCP readbacks')
 a.add_argument('--hpd-pulse',action='store_true',help='Production: the same HPD-low-only request for a bounded spec HPD pulse (DDC never written)')
 a.add_argument('output',type=Path)
 args=a.parse_args()
 if args.defer_initial_hpd and not (args.verify_restore and args.readvertise):
  a.error('--defer-initial-hpd requires --verify-restore and --readvertise')
 if args.defer_initial_ddc and not args.defer_initial_hpd:
  a.error('--defer-initial-ddc requires --defer-initial-hpd')
 if args.hpd_pulse and (not args.verify_restore or not args.readvertise or args.defer_initial_hpd or args.isolate_ddc or args.isolate_hpd):
  a.error('--hpd-pulse requires --verify-restore --readvertise, the original initial advert and no isolation diagnostic')
 if args.isolate_hpd and (not args.verify_restore or not args.readvertise or args.defer_initial_hpd or args.isolate_ddc):
  a.error('--isolate-hpd requires --verify-restore --readvertise, the original initial advert and no --isolate-ddc')
 if args.isolate_ddc and (not args.verify_restore or not args.readvertise or args.defer_initial_hpd):
  a.error('--isolate-ddc requires --verify-restore --readvertise and the original initial advert')
 if args.edid:
  try:
   edid=bytes.fromhex(args.edid.read_text()) if args.edid.suffix=='.hex' else args.edid.read_bytes()
  except ValueError:
   a.error('--edid hex input is malformed')
  if (len(edid)!=256 or edid[:8]!=bytes.fromhex('00ffffffffffff00') or
      edid[126]!=1 or edid[128]==0 or any(sum(edid[i:i+128])%256 for i in (0,128))):
   a.error('--edid requires two checksum-valid blocks with exactly one extension')
 else:
  edid=runpy.run_path(str(Path(__file__).with_name('make-test-edid.py')))['make_edid'](args.mode)+bytes(128)
 ext=[] if args.readvertise else None
 if args.sample_ddc and not (args.verify_restore and args.readvertise):
  a.error('--sample-ddc requires --verify-restore --readvertise')
 if args.scan_ddc and (args.sample_ddc or not (args.verify_restore and args.readvertise)):
  a.error('--scan-ddc requires --verify-restore --readvertise and excludes --sample-ddc')
 smp=[] if args.sample_ddc else None
 if args.scan_bytes and (args.scan_ddc or args.sample_ddc or not (args.verify_restore and args.readvertise)):
  a.error('--scan-bytes requires --verify-restore --readvertise and excludes --scan-ddc/--sample-ddc')
 if args.scan_words and (args.scan_bytes or args.scan_ddc or args.sample_ddc or not (args.verify_restore and args.readvertise)):
  a.error('--scan-words requires --verify-restore --readvertise and excludes the other scanners')
 scn=[] if args.scan_ddc or args.scan_bytes or args.scan_words else None
 w=build(args.verify_restore,ext,args.defer_initial_hpd,args.defer_initial_ddc,args.isolate_ddc,args.isolate_hpd or args.hpd_pulse,smp,scn,args.scan_bytes,args.scan_words)
 idle=SCAN_BYTES_IDLE if args.scan_bytes or args.scan_words else SCAN_IDLE
 text=((f'#define EDID_SCAN_WORDS 1\n#define EDID_SCAN_ACT 0x{SCAN_ACT:x}\n#define EDID_SCAN_LASTACT 0x{SCAN_LASTACT:x}\n#define EDID_SCAN_BUSY 0x{SCAN_BUSY:x}\n' if args.scan_words else '')+(f'#define EDID_SCAN_BYTES 1\n#define EDID_SCAN_ACT 0x{SCAN_ACT:x}\n#define EDID_SCAN_LASTACT 0x{SCAN_LASTACT:x}\n#define EDID_SCAN_BUSY 0x{SCAN_BUSY:x}\n#define EDID_SCAN_ARM 0x{SCAN_ARM:08x}\n#define EDID_SCAN_ARM_COUNT {SCAN_ARM_N}\n' if args.scan_bytes else '')+(f'#define EDID_SCAN_OFFSET 0x{SAMP:x}\n#define EDID_SCAN_TABLE 0x{SCAN_TABLE:x}\n#define EDID_SCAN_COUNT {SCAN_N}\n#define EDID_SCAN_LAST 0x{SCAN_LAST:x}\n#define EDID_SCAN_MASK 0x{SCAN_MASK:x}\n#define EDID_SCAN_FIRST 0x{SCAN_FIRST:x}\n#define EDID_SCAN_SEQ 0x{SEQ:x}\n#define EDID_SCAN_CLR 0x{CLR:x}\n#define EDID_SCAN_IDLE 0x{idle:x}\n'+'static const u32 edid_scan_code[] = {\n'+''.join(f'\t0x{v:08x}, /* {SAMP+4*i:04x}: {t} */\n' for i,(v,t) in enumerate(scn))+'};\n') if scn is not None else '')+((f'#define EDID_SAMPLER_OFFSET 0x{SAMP:x}\n#define EDID_SAMPLE_FIRST 0x{FIRST:x}\n#define EDID_SAMPLE_SEQ 0x{SEQ:x}\n#define EDID_SAMPLE_CLR 0x{CLR:x}\n#define EDID_SAMPLE_PAIRS 0x{PAIRS:x}\n#define EDID_SAMPLE_COUNT {len(SAMPLED)}\n'+'static const u32 edid_sample_regs[] = {'+','.join(f'0x{a:08x}' for a in SAMPLED)+'};\nstatic const u32 edid_sampler_code[] = {\n'+''.join(f'\t0x{v:08x}, /* {SAMP+4*i:04x}: {t} */\n' for i,(v,t) in enumerate(smp))+'};\n') if args.sample_ddc else '')+('#define EDID_HPD_PULSE 1\n#define EDID_REQ_HPD_LOW 6\n#define EDID_RELEASE_HPD_OFFSET 120\n#define EDID_RELEASE_DDC_OFFSET 124\n' if args.hpd_pulse else '')+('#define EDID_HPD_DIAGNOSTIC 1\n#define EDID_REQ_HPD_LOW 6\n#define EDID_RELEASE_HPD_OFFSET 120\n#define EDID_RELEASE_DDC_OFFSET 124\n' if args.isolate_hpd else '')+('#define EDID_DDC_DIAGNOSTIC 1\n#define EDID_REQ_DDC_OFF 5\n#define EDID_RELEASE_HPD_OFFSET 120\n#define EDID_RELEASE_DDC_OFFSET 124\n' if args.isolate_ddc else '')+('#define EDID_INITIAL_DDC_HOLD_MS 2000\n' if args.defer_initial_ddc else '')+('#define EDID_INITIAL_HPD_DEFERRED 1\n#define EDID_RELEASE_HPD_OFFSET 120\n#define EDID_RELEASE_DDC_OFFSET 124\n' if args.defer_initial_hpd else '')+'#define EDID_PAYLOAD_OFFSET 0x4680\n#define EDID_BACKUP_OFFSET 0x4780\n#define EDID_META_OFFSET 0x4a80\n'+(f'#define EDID_CHECK_OFFSET 0x{CHECK:x}\n' if args.verify_restore else '')+(f'#define EDID_EXT_OFFSET 0x{EXT:x}\n#define EDID_ACK_OFFSET {ACK}\n#define EDID_REQ_HOLD {HOLD}\n#define EDID_REQ_DDC_ON {DDC_ON}\n#define EDID_REQ_RELEASE {RELEASE}\n' if ext is not None else '')+'/* Generated by tools/hdmi/make-edid-trial-code.py; fixed bench program. */\nstatic const u32 edid_trial_code[] = {\n'+''.join(f'\t0x{v:08x}, /* {CODE+4*i:04x}: {s} */\n' for i,(v,s) in enumerate(w))+'};\n'+(('static const u32 edid_readvertise_code[] = {\n'+''.join(f'\t0x{v:08x}, /* {EXT+4*i:04x}: {s} */\n' for i,(v,s) in enumerate(ext))+'};\n') if ext is not None else '')+'static const u8 edid_trial_data[] = {\n'+''.join('\t'+','.join(f'0x{x:02x}' for x in edid[i:i+16])+',\n' for i in range(0,len(edid),16))+'};\n';args.output.write_text(text);print(f'{len(w)} instructions; data 0x{PAYLOAD:x}; backup-only and reversible trial modes')
