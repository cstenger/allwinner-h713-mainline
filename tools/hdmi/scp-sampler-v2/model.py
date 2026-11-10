"""Independent binary decoder, delayed-store model and native C transaction adapter.

Only host bytearrays and a native shared library are used. No hardware APIs.
"""
import ctypes as C
import json
from pathlib import Path
import random
import struct

class Fault(RuntimeError): pass

class CPU:
    def __init__(self, packet, seed=0, phase=0, sr=0x8081, store_delay=0):
        self.packet=Path(packet);self.m=json.loads((self.packet/'manifest.json').read_text())
        self.mem=bytearray((self.packet/'baseline-sram.bin').read_bytes());self.before=bytes(self.mem)
        self.rng=random.Random(seed);self.reg=[self.rng.getrandbits(32) for _ in range(32)]
        self.reg[0]=0;self.reg[3]=0x4f00;self.reg[4]=0;self.reg[10]=0x48444d49;self.reg[11]=0x07090000
        self.context=list(self.reg);self.sr=sr&~0x200;self.flag=False
        self.pc=0x4404+4*phase;self.branch=0x4404 if phase==3 else None
        self.pending=[];self.store_delay=store_delay;self.ticks=0;self.log=[]
        self.reads=[];self.stores=[];self.peripheral={a:self.rng.getrandbits(32) for a in self.m['read_registers']}
        self.stall_at=None;self.stalled=False;self.disabled=False;self.stop_delegated=False
        self.stale_hook=False;self.suppress_echo=False;self.sticky_hook=False;self.saw_hook=False
        self.stale_boot_slot=False
        self.stale_sync=False;self.sync_witness=False;self.monitor_entered=False
        self.bootstrap_fetch_mix=False;self.history={0x4404:[self.arm_read(0x4404)],0x4410:[self.arm_read(0x4410)]}
        self.on_entry=None
        self.freeze_at_done=False;self.late_release=False;self.fetch_stop_at=None
        self.entry_count=0;self.return_count=0;self.last_return_context=None;self.guard_parked=False
        self.allowed_pc=set(range(0x4404,0x441c,4))
        for f in self.m['fragments']:self.allowed_pc.update(range(f['offset'],f['offset']+f['bytes'],4))

    def arm_read(self,off):
        if off&3 or not 0<=off<=0x4ffc:raise Fault('ARM access outside SRAM')
        return struct.unpack_from('<I',self.mem,off)[0]

    def arm_write(self,off,value):
        if off&3 or not 0<=off<=0x4ffc:raise Fault('ARM access outside SRAM')
        struct.pack_into('<I',self.mem,off,value)
        if hasattr(self,'history') and off in self.history and value not in self.history[off]:self.history[off].append(value)
        self.log.append(('arm-write',off,value,self.ticks))

    def commit(self,all_pending=False):
        remain=[];blocked=set()
        for off,value,due in self.pending:
            if all_pending or (due<=self.ticks and off not in blocked):struct.pack_into('<I',self.mem,off,value)
            else:remain.append((off,value,due));blocked.add(off)
        self.pending=remain

    def load(self,off):
        for address,value,_ in reversed(self.pending):
            if address==off:return value
        return self.arm_read(off)

    def store(self,off,value):
        if off&3 or not 0x4f80<=off<=0x4ffc:raise Fault('SCP non-mailbox store: '+hex(off))
        self.stores.append((off,value));self.log.append(('scp-store',off,value,self.ticks))
        if self.suppress_echo and off==0x4ff0:return
        if self.store_delay:
            self.pending.append((off,value,self.ticks+self.rng.randint(1,self.store_delay)))
        else:struct.pack_into('<I',self.mem,off,value)

    def step(self):
        self.ticks+=1;self.commit()
        if self.disabled or self.stalled:return
        if self.pc==0x4414:
            if self.arm_read(0x4414)==0:self.guard_parked=True
            elif self.arm_read(0x4414)==struct.unpack_from('<I',self.before,0x4414)[0]:
                self.stop_delegated=True;self.disabled=True;return
        if self.fetch_stop_at==self.pc:return
        if self.pc not in self.allowed_pc:raise Fault('unreviewed PC '+hex(self.pc))
        if self.freeze_at_done and self.arm_read(0x4f8c)==self.m['nonce']:
            self.disabled=True;return
        pc=self.pc;insn=self.arm_read(pc)
        if self.bootstrap_fetch_mix and not self.monitor_entered:
            if pc==0x4404 and insn!=self.m['hook']:insn=self.rng.choice(self.history[pc])
            if pc==0x4410:insn=self.rng.choice(self.history[pc])
        if pc==0x4404:
            if self.stale_hook and insn==self.m['hook']:insn=0x84830010
            elif self.sticky_hook and self.saw_hook:insn=self.m['hook']
            if insn==self.m['hook']:self.saw_hook=True
        if pc==0x4410 and self.stale_boot_slot:insn=0x15000000
        if pc==0x440c and insn==0x22800000 and self.stale_sync:insn=0x0ffffffe
        if pc==self.m['fragments'][0]['offset']:
            if not self.sync_witness:raise Fault('new-target fetch without witnessed pre-entry psync')
            self.monitor_entered=True
            self.entry_count+=1
            if self.on_entry:self.on_entry()
        if any(f['offset']<=pc<f['offset']+f['bytes'] for f in self.m['fragments']) and not self.sync_witness:
            raise Fault('scratch fetch before pre-entry synchronization')
        if pc==0x4408:self.return_count+=1;self.last_return_context=list(self.reg)
        op=insn>>26;d=(insn>>21)&31;a=(insn>>16)&31;imm=insn&65535
        pending=self.branch;self.branch=None;nextpc=pc+4
        if op in [0,3,4]:
            n=insn&0x3ffffff;n=n-(1<<26) if n&(1<<25) else n
            if op==0 or (op==3 and not self.flag) or (op==4 and self.flag):self.branch=pc+4*n
        elif insn==0x15000000:pass
        elif insn in [0x22000000,0x22800000]:
            self.commit(True)
            if pc==0x440c and insn==0x22800000:self.sync_witness=True
        elif op==6:self.reg[d]=imm<<16
        elif op==0x2a:self.reg[d]=self.reg[a]|imm
        elif op==0x29:self.reg[d]=self.reg[a]&imm
        elif op==0x2d and a==0 and imm==17:self.reg[d]=self.sr|(0x200 if self.flag else 0)
        elif op==0x2f:
            if ((insn>>21)&31)!=1:raise Fault('unknown comparison')
            n=imm-65536 if imm&0x8000 else imm
            self.flag=self.reg[a]!=(n&0xffffffff)
        elif insn&0xffe007ff==0xe4200000:self.flag=self.reg[a]!=self.reg[(insn>>11)&31]
        elif op==0x21:
            off=self.reg[a]+(imm-65536 if imm&0x8000 else imm)
            if off in self.peripheral:
                if self.stall_at==len(self.reads):self.stalled=True;return
                self.reads.append(off);self.reg[d]=self.peripheral[off]
            else:self.reg[d]=self.load(off)
        elif op==0x35:
            n=((insn>>21)&31)<<11|(insn&2047)
            off=self.reg[a]+(n-65536 if n&0x8000 else n)
            self.store(off,self.reg[(insn>>11)&31])
        else:raise Fault(f'unknown instruction {insn:08x} at {pc:04x}')
        self.pc=pending if pending is not None else nextpc

    def advance(self,n):
        for _ in range(n):self.step()


WRAPPER = r'''
#include <pthread.h>
#include <stddef.h>
#include <string.h>
#include "core.h"
#define READ_ONCE(x) (x)
#define MODULE_STATE_LIVE 1
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct kset { int unused; };
struct kobject { struct kset *kset; int refs; };
struct module;
struct module_kobject { struct kobject kobj; struct module *mod; };
struct kernel_param;
struct ops { int (*get)(char *,const struct kernel_param *); };
struct kernel_param { const char *name; struct ops *ops; int value; };
struct module { int state,refs; struct module_kobject mkobj; unsigned int num_kp;
 struct kernel_param *kp; pthread_mutex_t mutex; };
static struct kset set;
static struct module self,owner;
#define THIS_MODULE (&self)
static int missing,going_race,stop_calls,held,locked_reads,initialized;
static struct kobject *kset_find_obj(struct kset *s,const char *n)
{ if(missing || s!=&set || strcmp(n,"h713_hdmi_signal"))return NULL;
 owner.mkobj.kobj.refs++;return &owner.mkobj.kobj; }
static int try_module_get(struct module *m)
{ if(going_race)m->state=2; if(m->state!=1)return 0;m->refs++;return 1; }
static void kobject_put(struct kobject *o) { o->refs--; }
static void kernel_param_lock(struct module *m) { pthread_mutex_lock(&m->mutex);held=1; }
static void kernel_param_unlock(struct module *m) { held=0;pthread_mutex_unlock(&m->mutex); }
static int get_bool(char *v,const struct kernel_param *p)
{ if(!held)return -1;locked_reads++;v[0]=p->value?'Y':'N';return 1; }
static struct ops bool_ops={get_bool};
#define param_ops_bool bool_ops
static struct kernel_param params[3]={{"ready",&bool_ops,1},{"failed",&bool_ops,0},{"restored",&bool_ops,0}};
#include "owner.h"
void setup(int absent,int race,int ready)
 { if(initialized)pthread_mutex_destroy(&owner.mutex);
 memset(&self,0,sizeof(self));memset(&owner,0,sizeof(owner));
 self.mkobj.kobj.kset=&set;owner.mkobj.kobj.kset=&set;owner.mkobj.mod=&owner;
 owner.mkobj.kobj.refs=1;owner.state=1;owner.refs=1;owner.kp=params;owner.num_kp=3;
 pthread_mutex_init(&owner.mutex,NULL);initialized=1;params[0].value=ready;
 missing=absent;going_race=race;stop_calls=held=locked_reads=0; }
int execute(struct scps_io *io,struct scps_receipt *r)
{ struct module *m=scps_get_owner();if(!m){r->phase=SCPS_REJECTED;r->reason=14;return -1;}
 return scps_run_owned(m,io,r); }
int held_lock(void){return held;}
int owner_refs(void){return owner.refs;}
int object_refs(void){return owner.mkobj.kobj.refs;}
int bool_reads(void){return locked_reads;}
int stops(void){return stop_calls;}
void competing_stop(void){kernel_param_lock(&owner);stop_calls++;kernel_param_unlock(&owner);}
void explicit_success_release(void){kernel_param_unlock(&owner);}
int release_guard(struct scps_io *io,struct scps_receipt *r)
{return scps_release_guard(io,r);}
/* Fake mutex teardown ONLY: never a production FROZEN release operation. */
void harness_cleanup(void){if(held)kernel_param_unlock(&owner);}
'''

Read = C.CFUNCTYPE(C.c_uint,C.c_void_p,C.c_uint)
Write = C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,C.c_uint)
Action = C.CFUNCTYPE(None,C.c_void_p)
Phase = C.CFUNCTYPE(None,C.c_void_p,C.c_uint)
class IO(C.Structure):
    _fields_=[('context',C.c_void_p),('read',Read),('write',Write),('fence',Action),('wait',Action),('phase',Phase)]
class Receipt(C.Structure):
    _fields_=[('phase',C.c_uint),('reason',C.c_uint),('touched',C.c_uint),('sr',C.c_uint),('values',C.c_uint*14),
              ('bootstrap_sr',C.c_uint),('original_r13',C.c_uint)]

class Transaction:
    def __init__(self,library,cpu):
        self.lib=C.CDLL(str(library));self.cpu=cpu;self.errors=[];self.writes=[];self.phases=[]
        self.fail_write=None;self.on_phase=None;self.write_count=0;self.steps_per_io=2
        self.before_read=None;self.before_write=None
        self.active=False
        def advance():
            if self.errors:return
            try:self.cpu.advance(self.steps_per_io)
            except Exception as e:self.errors.append(e);self.cpu.disabled=True
        def read(_,off):
            advance()
            if self.before_read:self.before_read(off)
            try:return self.cpu.arm_read(off)
            except Exception as e:self.errors.append(e);return 0xffffffff
        def write(_,off,value):
            advance();self.write_count+=1
            if self.before_write:
                replacement=self.before_write(off,value)
                if replacement is not None:value=replacement
            if self.fail_write==self.write_count:return -1
            try:self.cpu.arm_write(off,value);self.writes.append((off,value));return 0
            except Exception as e:self.errors.append(e);return -1
        def wait(_):
            try:self.cpu.advance(100)
            except Exception as e:self.errors.append(e);self.cpu.disabled=True
        def phase(_,n):
            self.phases.append(n)
            if self.on_phase:self.on_phase(n)
        self.callbacks=[Read(read),Write(write),Action(lambda _:None),Action(wait),Phase(phase)]
        self.io=IO(None,*self.callbacks);self.receipt=Receipt()
        self.lib.execute.argtypes=[C.POINTER(IO),C.POINTER(Receipt)]
        self.lib.execute.restype=C.c_int
        self.lib.release_guard.argtypes=[C.POINTER(IO),C.POINTER(Receipt)]

    def run(self,absent=0,race=0,ready=1):
        self.lib.setup(absent,race,ready)
        self.active=True
        rc=self.lib.execute(C.byref(self.io),C.byref(self.receipt))
        if self.errors:raise self.errors[0]
        return rc

    def cleanup(self):
        if self.active:self.lib.harness_cleanup();self.active=False
