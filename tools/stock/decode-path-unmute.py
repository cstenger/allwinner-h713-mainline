#!/usr/bin/env python3
"""Host-only linked emulation of the stock HAL path unmute after init+connect.

HAL Check_Sound_Unmute -> Sound_Set_Mute(path,false) -> Thal_Sound_Set
({path, attr 0, 0, mute byte at +0xc}) -> SlaveRoutine_Thal_Sound_Set default
branch -> Sound_Path_SetAttr(struct).

No board access. Hardware and timing imports are explicit stubs; this recovers
code intent, not hardware readiness or measured clocks. Libraries execute in
separate Unicorn contexts with distinct code/stack banks and mirrored memory.
"""
import argparse,hashlib,importlib.util,sys,json
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_PC
root=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('evidence',type=Path,help='captured Android audio directory')
ap.add_argument('--route',type=lambda s:int(s,0),default=0x89,
                help='Stock preset route to connect after initialization')
args=ap.parse_args()
libs=[];banks=[];hashes={}
expected={'libmspsound.so':'61f349440c08dd28ef1289f463a7934b3213b15518113ff1044f881bf237e8c4', 'libmspdriver.so':'a03e6344ad0f672e5be965fd3008c8c44c74b367868318501a9d2a4798ce88ea'}
for i,n in enumerate(['libmspsound.so','libmsp_util.so','libmspdriver.so']):
 spec=importlib.util.spec_from_file_location('awemu_'+str(i),root/'tools/re/awemu.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 mod.BASE+=i*0x1000000;mod.STUBS+=i*0x1000000;mod.STACK+=i*0x1000000
 hashes[n]=hashlib.sha256((args.evidence/n).read_bytes()).hexdigest()
 if n in expected:assert hashes[n]==expected[n], 'unsupported binary'
 l=mod.Lib(args.evidence/n,heap=0x600000);l.brk+=i*0x200000
 libs.append(l)
 hi=max(s['p_vaddr']+s['p_memsz'] for s in l.elf.iter_segments() if s['p_type']=='PT_LOAD');banks.append((mod.BASE,(hi+0xfff)&~0xfff,l));banks.append((mod.STACK,mod.STACK_SZ,l))
for l in libs:
 for a,z,owner in banks:
  if l!=owner:l.uc.mem_map(a,z);l.uc.mem_write(a,bytes(owner.uc.mem_read(a,z)))
banks=[(a,z) for a,z,_ in banks]+[(0x30000000,0x600000)]
def sync(src,dst):
 for a,z in banks:dst.uc.mem_write(a,bytes(src.uc.mem_read(a,z)))
def call(l,n,*args):
 r=l.call(n,*args);assert l.uc.reg_read(UC_ARM_REG_PC)==0x7ff00000,(n,'budget');return r
events=[]
def guard():
 if len(events)>20000: raise RuntimeError('event budget')
for l in libs:
 for n in l.stubs.values():
  target=next((d for d in libs if d!=l and n in d.exports),None)
  if target:
   def f(src,a,n=n,d=target):
    guard();sync(src,d);r=call(d,n,*a,*[src.stack_arg(i) for i in range(4)]);sync(d,src);events.append({'function':n,'args':a,'rc':r});return r
   l.extern[n]=f
  elif n not in ['memcpy','memset','malloc','calloc','free','__cxa_finalize','usleep','strcmp','strncmp'] and not 'log' in n:
   l.extern[n]=lambda l,a,n=n: guard() or events.append({'stub':n,'args':a})or 0
 # awemu lacks strcmp/strncmp default; real bytes comparison required.
 for n in ['strcmp','strncmp']:
  l.extern[n]=lambda l,a,n=n: (lambda x,y:(x>y)-(x<y))(bytes(l.uc.mem_read(a[0],a[2])),bytes(l.uc.mem_read(a[1],a[2]))) if n=='strncmp' else (lambda x,y:(x>y)-(x<y))(l.cstr(a[0]),l.cstr(a[1]))
for l in libs:
 l.extern['strlen']=lambda l,a:len(l.cstr(a[0]))
 l.extern['__strcpy_chk']=lambda l,a:l.uc.mem_write(a[0],l.cstr(a[1]).encode()+b'\0') or a[0]
sound,util,driver=libs
writes=[]
for n in ['tdAudioDSPWriteRegMaskWord','tdAudioDSPWriteRegWord','DSP_WriteReg','aud_dsp1_write_reg']:
 driver.intercept(n,lambda l,a,n=n:writes.append({'function':n,'args':a})or 0)
driver.intercept(0x1f0a4,lambda l,a:0)
for n in ['tdAudioDSPReadRegWord', 'aud_dsp1_read_reg', 'DSP_ReadReg']:
 if n in driver.exports:driver.intercept(n,lambda l,a,n=n:l.wr(a[2],1 if a[1]==0x80ff else 0) or 0 if n=='tdAudioDSPReadRegWord' else 0)
preset=(args.evidence/'sound_preset.bin').read_bytes();p=sound.alloc(len(preset));sound.uc.mem_write(p,preset)
init_rc=call(sound,'Sound_Path_Init',p,len(preset));assert init_rc==0,hex(init_rc)
init={'events':events[:], 'writes':writes[:]}
events.clear();writes.clear()
connect_rc=call(sound,'Sound_Path_Connect',args.route);assert connect_rc==0,hex(connect_rc)
connect={'events':events[:],'writes':writes[:]}
res={}
for label,mute in [('unmute',0),('mute',1)]:
 events.clear();writes.clear()
 st=sound.alloc(0x20);sound.uc.mem_write(st,bytes(0x20))
 sound.wr(st,args.route);sound.uc.mem_write(st+0xc,bytes([mute]))
 try:rc=call(sound,'Sound_Path_SetAttr',st)
 except Exception as ex:rc=repr(ex)
 res[label]={'rc':rc,'events':[e for e in events if not e.get('function','').startswith('BP_AUD_Get')][:400],'writes':writes[:2000]}
print(json.dumps({'evidence':'Offline code execution with hardware/timing stubs','route':args.route,'hashes':hashes,**res},indent=1))
