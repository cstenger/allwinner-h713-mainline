#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise extracted ARM lock code against the pinned firmware's gate/owner ABI."""
import argparse
from pathlib import Path
import subprocess
import tempfile
from importlib.machinery import SourceFileLoader
h = SourceFileLoader('handoff', str(Path(__file__).with_name('test-cpu-comm-handoff.py'))).load_module()
STUBS = h.COMMON + r'''
#include <stdlib.h>
#include <stdatomic.h>
#define HWLOCK_RAW 0
#define SPINLOCK_MAX_ID 11
#define SPINLOCK_HW_OFFSET 2
#define SPINLOCK_ENTRY_SIZE 12
#define SPINLOCK_FREE 2
#define SPINLOCK_HWID_NONE 255
#define SPINLOCK_OFF_MUTEX 2
#define SPINLOCK_OFF_GATE 0
static unsigned char shared[144] __attribute__((aligned(4)));
static pthread_mutex_t hw = PTHREAD_MUTEX_INITIALIZER;
static void *hwlocks[14];
static int fail_hw;
struct task { unsigned pid, tgid; };
static _Thread_local struct task task;
#define current (&task)
static u8 *getSpinLockMemArea(void) { return shared; }
static unsigned getCurCPUID(int x) { return 0; }
static u32 readl(void *p) { return *(volatile u32 *)p; }
static void writel(u32 v, void *p) { *(volatile u32 *)p=v; }
static int __hwspin_lock_timeout(void *p,int t,int mode,void *f) {
 return fail_hw ? -1 : pthread_mutex_trylock(&hw);
}
static void __hwspin_unlock(void *p,int mode,void *f) { assert(!pthread_mutex_unlock(&hw)); }
#define schedule() sched_yield()
static void reset(void) {
 memset(shared,0,sizeof shared);
 for(int i=0;i<12;i++) { shared[i*12]=shared[i*12+1]=shared[i*12+3]=2; writel(255,shared+i*12+8); }
 task.pid=17; task.tgid=42;
}
'''
TEST = r'''
static atomic_int active, total;
static void critical(void) {
 assert(atomic_fetch_add(&active,1)==0);
 sched_yield(); atomic_fetch_add(&total,1);
 assert(atomic_fetch_sub(&active,1)==1);
}
static void *arm(void *id) {
 task.pid=(unsigned)(uintptr_t)id;task.tgid=42;
 for(int i=0;i<500;i++) { assert(spinLock(2,2)==2); critical(); comm_SpinUnLock(2,0); }
 return 0;
}
/* Firmware 8b1250e8 gates byte 0 under HW lock; 8b125674 uses
 * byte 1 for persistent ownership and asserts free implies thread==255.
 */
static void peer_gate(u8 *e) {
 for(;;) {
  pthread_mutex_lock(&hw);
  if(READ_ONCE(e[0])==2) { WRITE_ONCE(e[0],1);dmb(ish);pthread_mutex_unlock(&hw);return; }
  pthread_mutex_unlock(&hw);sched_yield();
 }
}
static void peer_leave(u8 *e) { dmb(ish);WRITE_ONCE(e[0],2); }
static void *peer(void *unused) {
 u8 *e=shared+24;
 for(int i=0;i<1000;i++) {
  for(;;) {
   peer_gate(e);
   if(READ_ONCE(e[1])==2) {
    assert(readl(e+8)==255 && readl(e+4)==0);
    writel(99,e+8);writel(1,e+4);WRITE_ONCE(e[1],1);peer_leave(e);break;
   }
   peer_leave(e);sched_yield();
  }
  critical();peer_gate(e);
  assert(READ_ONCE(e[1])==1 && readl(e+8)==99 && readl(e+4)==1);
  writel(0,e+4);writel(255,e+8);WRITE_ONCE(e[1],2);peer_leave(e);
 }
 return 0;
}
int main(int argc,char **argv) {
 reset(); u8 *e=shared+24; u8 saved[12];
 if(argc>1) {
  assert(spinLock(2,2)==2);
  /* Regression: ARM must publish CPU0 owner, not leave it free. */
  assert(e[1]==0 && readl(e+8)==17 && e[0]==2);
  return 0;
 }
 WRITE_ONCE(e[1],1);writel(99,e+8);writel(1,e+4);memcpy(saved,e,12);
 assert(!spinLock(2,0));assert(!memcmp(saved,e,12));
 reset();e[0]=1;memcpy(saved,e,12);assert(!spinLock(2,0));assert(!memcmp(saved,e,12));
 reset();fail_hw=1;memcpy(saved,e,12);assert(!spinLock(2,0));assert(!memcmp(saved,e,12));fail_hw=0;
 reset();comm_SpinLocksetType(2,1);assert(e[0]==2 && e[1]==2 && e[2]==1);
 comm_SpinLocksetType(2,0);assert(e[0]==2 && e[1]==2 && e[2]==0);
 assert(spinLock(2,1)==2);assert(spinLock(2,1)==1);assert(readl(e+4)==2);
 comm_SpinUnLock(2,0);assert(readl(e+4)==1);
 task.pid=18;assert(!spinLock(2,0));memcpy(saved,e,12);comm_SpinUnLock(2,0);assert(!memcmp(saved,e,12));
 task.pid=17;comm_SpinUnLock(2,0);assert(e[0]==2 && e[1]==2 && readl(e+8)==255);
 reset();pthread_t threads[5];
 for(int i=0;i<4;i++) assert(!pthread_create(&threads[i],0,arm,(void *)(uintptr_t)(100+i)));
 assert(!pthread_create(&threads[4],0,peer,0));
 for(int i=0;i<5;i++) assert(!pthread_join(threads[i],0));
 assert(total==3000 && active==0 && e[0]==2 && e[1]==2 && !readl(e+4) && readl(e+8)==255);
 puts("PASS peer ownership, gate arbitration, timeout refusal, per-thread recursion and 3000 ARM/MIPS critical sections");
}
'''
def source(path):
 p=Path(path)
 if (p/'drivers').exists(): p=p/'drivers/soc/sunxi/cpu_comm'
 return (p/'cpu_comm_hw.c').read_text()
def run(src, baseline=False):
 funcs='\n'.join(h.function(src,k) for k in ('static '+('void' if baseline else 'bool')+' enterCritical(', 'static void leaveCritical(', 'static int spinLock(', 'void comm_SpinUnLock(', 'void comm_SpinLocksetType('))
 with tempfile.TemporaryDirectory() as d:
  p=Path(d);(p/'test.c').write_text(STUBS+'\n#define SPINLOCK_OFF_OWNER '+('3' if baseline else '1')+'\n'+funcs+TEST)
  subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-pthread',str(p/'test.c'),'-o',str(p/'test')],check=True)
  r=subprocess.run([str(p/'test')]+(['baseline'] if baseline else []),env={**__import__('os').environ,'ASAN_OPTIONS':'detect_leaks=0'},capture_output=True,text=True,timeout=30)
  if baseline:
   assert r.returncode != 0 and 'e[1]==0' in r.stderr, r.stdout+r.stderr
   print('PASS baseline reproduces firmware free-owner/nonfree-thread conflict')
  else:
   assert r.returncode==0,r.stdout+r.stderr
   print(r.stdout,end='')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel',required=True);p.add_argument('--baseline');a=p.parse_args();run(source(a.kernel))
 if a.baseline:run(source(a.baseline),True)
