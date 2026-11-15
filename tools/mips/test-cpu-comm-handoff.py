#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Source-bound CPU_COMM race and peer-handle tests; no device access.

--baseline additionally proves the old semaphore/ref helpers fail the same
regressions. Compile extracted functions with ASan/UBSan and pthread stubs.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def function(source, marker):
    start = source.index(marker); end = source.index('{', start) + 1; depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}'); end += 1
    return source[start:end]


COMMON = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <sched.h>
#include <unistd.h>
#include <errno.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32; typedef uint64_t u64;
#define BIT(n) (1u<<(n))
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x,v) (READ_ONCE(x)=(v))
#define WARN_ON(x) (!!(x))
#define pr_warn_ratelimited(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_debug(...) ((void)0)
#define BUG() assert(0)
#define dmb(x) __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define CPU_ID_MAX 2
#define MAX_WAIT_ENTRIES 20
#define FIFO_DEFAULT_CAP 21
#define MSG_FLAG_RETURN_ACK 2
#define MSG_FLAG_SENT 4
#define MSG_TYPE_CALL_ACK 2
#define MSG_TYPE_RETURN_ACK 3
#define INTR_TYPE_SEND 0
#define spinlock_t pthread_mutex_t
#define spin_lock_irqsave(p,f) do {(f)=0;assert(!pthread_mutex_lock(p));} while(0)
#define spin_unlock_irqrestore(p,f) do {(void)(f);assert(!pthread_mutex_unlock(p));} while(0)
'''
SEMAPHORES = r'''
static pthread_mutex_t cpu_comm_sem_lock=PTHREAD_MUTEX_INITIALIZER;
static int cpu_comm_sem_wq, interrupted, timed_out;
#define CLAIM(c) ({bool hit=(c); if(hit)usleep(1); hit;})
#define wait_event(w,c) do {while(!CLAIM(c))sched_yield();} while(0)
#define wait_event_interruptible(w,c) ({int r=0;while(!CLAIM(c)){if(interrupted){r=-EINTR;break;}sched_yield();}r;})
#define wait_event_interruptible_timeout(w,c,t) ({long r=1;while(!CLAIM(c)){if(interrupted){r=-EINTR;break;}if(timed_out){r=0;break;}sched_yield();}r;})
#define wake_up_all(p) ((void)0)
'''
SEM_CASES = r'''
static u32 count=1;
static int active, collision, acquired;
static void *void_waiter(void *arg){cpu_comm_sem_down(&count);__atomic_store_n(&acquired,1,__ATOMIC_SEQ_CST);return 0;}
static void *worker(void *arg){
    for(int i=0;i<1000;i++){
        assert(cpu_comm_sem_down_interruptible(&count)==0);
        assert(__atomic_add_fetch(&active,1,__ATOMIC_SEQ_CST)==1);
        sched_yield();__atomic_sub_fetch(&active,1,__ATOMIC_SEQ_CST);
        cpu_comm_sem_up(&count);
    }return 0;
}
int main(void){
    pthread_t t[4];for(int i=0;i<4;i++)assert(!pthread_create(t+i,0,worker,0));
    for(int i=0;i<4;i++)assert(!pthread_join(t[i],0));
    assert(!collision && count==1);
    count=0;interrupted=1;assert(cpu_comm_sem_down_interruptible(&count)==-EINTR && count==0);
    interrupted=0;timed_out=1;assert(cpu_comm_sem_down_timeout(&count,1)==-ETIME && count==0);
    count=1;assert(cpu_comm_sem_down_timeout(&count,1)==0 && count==0);
    interrupted=1;pthread_t v;assert(!pthread_create(&v,0,void_waiter,0));usleep(10000);
    assert(count==0 && !__atomic_load_n(&acquired,__ATOMIC_SEQ_CST));cpu_comm_sem_up(&count);
    assert(!pthread_join(v,0) && acquired && count==0);
    puts("PASS serialized counter claim, signal and timeout ownership");
}
'''
REFS = r'''
#define CC_REF_LOCAL BIT(31)
#define CC_REF_ARENA_SHIFT 28
#define CC_REF_OFF_MASK ((1u<<28)-1)
static unsigned char arena[1024], shared[4096];
static unsigned long ShMemAddrBase=(unsigned long)shared;
static u32 ShMemAddr=0x4e300000, ShMemSize=sizeof(shared);
static struct {unsigned long base;size_t size;u32 mid;} cc_arenas[8];
static int cc_arena_count=1;
static unsigned long Mid2Vir(u32 cpu,u32 ref){return ShMemAddrBase+ref-ShMemAddr;}
'''
REF_CASES = r'''
int main(void){
    cc_arenas[0].base=(unsigned long)arena;cc_arenas[0].size=sizeof(arena);cc_arenas[0].mid=0x41000000;
    assert(cc_deref(0)==0);assert(cc_deref(0x41000010)==(unsigned long)arena+16);
    assert(cc_deref(0x4e300008)==(unsigned long)shared+8);
    for(u32 r=0x40000000;r<0x4e300000;r+=0x12345)if(r<0x41000000||r>=0x41000400)assert(cc_deref(r)==0);
    assert(cc_deref(0x4e301000)==0);assert(cc_deref(0x7fffffff)==0);assert(cc_deref(0x8b15bd44)==0);
    puts("PASS peer references bounded to reserved memory and registered arenas");
}
'''
HANDOFF = r'''
static u32 sockets[2496], *s_CommSockt=sockets;
static unsigned char shared[0x4000], dev[2048];
static void *pcpu_comm_dev=dev;
static int queued, recycled, sent, delivered;
static u32 *expected_wait;
static u64 expected_handle;
static unsigned long cc_pending_ack_sem[2];static u32 cc_pending_ack_session[2];
static pthread_mutex_t cc_pending_ack_lock=PTHREAD_MUTEX_INITIALIZER;
static u32 getCurCPUID(int unused){return 0;}
static unsigned long getSeq(u32 cpu){return (unsigned long)&sockets[cpu*1248];}
static unsigned long getShareSeqR(u32 cpu,u32 dir){return (unsigned long)shared;}
static unsigned long getShareSeqW(u32 cpu,u32 dir){return (unsigned long)shared+0x1000;}
static u32 cc_ref(const void *p){
    if((const u8*)p>=(u8*)sockets && (const u8*)p<(u8*)(sockets+2496))return 0x10000000+(const u8*)p-(u8*)sockets;
    if((const u8*)p>=shared && (const u8*)p<shared+sizeof(shared))return 0x20000000+(const u8*)p-shared;
    return 0;
}
static unsigned long cc_deref(u32 r){
    if(r>=0x10000000 && r<0x10000000+sizeof(sockets))return (unsigned long)sockets+r-0x10000000;
    if(r>=0x20000000 && r<0x20000000+sizeof(shared))return (unsigned long)shared+r-0x20000000;
    return 0;
}
static void cpu_comm_sem_down(void *p){assert(*(u32*)p==1);*(u32*)p=0;}
static void cpu_comm_sem_up(void *p){
    if(p==expected_wait+2){
        assert(sent && sockets[1248+26]==0);delivered++;
        /* Simulate a caller recycling shared metadata immediately on wake. */
        memset(shared+20,0xaa,12);
    }
    ++*(u32*)p;
}
static int AddReturn2Fifo(u32 *f,void *e){assert(sockets[1248+26]==0);queued++;return 1;}
static void Comm_ReleaseFreeCall(void *s,void *e){assert(sent);recycled++;}
static void cpu_comm_userspace_deliver(const void *p){assert(0);}
static void Comm_Add2NewCallFifo(void *p,u32 *f,unsigned long e){assert(0);}
static void Comm_Add2Call2WQ(void *p){assert(0);}
static void queueAction(u32 t,u32 c){assert(0);}
static void sunxi_cpu_comm_send_intr_to_mips(u32 t,u32 k,u32 v){
    assert(t==3);assert(shared[0x1000+104]==20);assert(*(u64*)(shared+0x1000+112)==expected_handle);sent++;
}
void cpu_comm_complete_return(u32,u32,unsigned long,u8,u32,u64);
'''
HANDOFF_CASES = r'''
static void reset(bool live){
    memset(sockets,0,sizeof(sockets));memset(shared,0,sizeof(shared));
    queued=recycled=sent=delivered=0;
    shared[1]=1;shared[0x1000]=1;shared[0x1002]=1;
    expected_wait=&sockets[1248+73];expected_wait[0]=42;
    u32 *head=&sockets[1248+24];*head=cc_ref(live?expected_wait+6:head);
    expected_wait[6]=cc_ref(head);sockets[1248+26]=1;
    *(u32*)(shared+360+12)=42;*(u16*)(shared+360+6)=0;
    *(u64*)(shared+360+32)=0x8b15bd448baa0000ULL; /* peer handle, never dereference */
    expected_handle=0x8b15bd448baa0000ULL;
    *(u64*)(shared+24)=expected_handle;*(u32*)(shared+20)=123;
    shared[8]=0;shared[16]=0;
}
int main(void){
    reset(true);command_action(1,1);
    assert(queued==1 && sent==1 && delivered==1 && recycled==0 && expected_wait[2]==1);
    reset(false);command_action(1,1);assert(queued==0 && sent==1 && delivered==0 && recycled==1);
    reset(true);expected_wait[3]=cc_ref(shared+360);command_action(1,1);
    assert(queued==0 && sent==1 && delivered==0 && recycled==0);
    reset(true);sockets[1248+24]=cc_ref(expected_wait+5);command_action(1,1);
    assert(queued==0 && sent==1 && delivered==0 && recycled==1);
    reset(true);shared[16]=20;command_action(1,1);assert(!sent && !queued && !delivered);
    reset(false);expected_wait=0;u32 *sem=&sockets[100];*sem=0;
    cc_pending_ack_sem[1]=(unsigned long)sem;cc_pending_ack_session[1]=77;
    *(u32*)(shared+108)=77;*(u32*)(shared+112)=cc_ref(sem);
    ack_action(1,0);assert(*sem==1);
    *(u32*)(shared+108)=76;ack_action(1,0);assert(*sem==1);
    *(u32*)(shared+108)=77;*(u32*)(shared+112)=0x8b15bd44;ack_action(1,0);assert(*sem==1);
    *(u32*)(shared+112)=cc_ref(sem);*(u32*)(shared+116)=1;ack_action(1,0);assert(*sem==1);
    puts("PASS ACK-before-wake, 64-bit echo, live-session-only completion, stale/foreign ACK rejection");
}
'''


FREE_RING = r'''
static int cpu_comm_sem_down_timeout(void *p,long t){if(!*(u32*)p)return -ETIME;--*(u32*)p;return 0;}
#define msecs_to_jiffies(n) (n)
static unsigned long fifo_getItemWr(u32 *f){return cc_deref(f[6])+4*f[1];}
static int fifo_requestItemWr(u32 *f){f[1]=(f[1]+1)%f[4];return 1;}
'''
FREE_CASES = r'''
int main(void){
    memset(sockets,0,sizeof(sockets));memset(shared,0,sizeof(shared));
    shared[1]=1;u32 *f=(u32*)(shared+120),*ring=(u32*)(shared+240);
    sockets[1248+235]=1;f[4]=21;f[6]=cc_ref(ring);
    Comm_ReleaseFreeCall(shared,shared+360);assert(f[1]==1 && ring[0]==cc_ref(shared+360));
    Comm_ReleaseFreeCall(shared,shared+360);assert(f[1]==1); /* duplicate cannot free twice */
    sockets[1248+235]=0;Comm_ReleaseFreeCall(shared,shared+464);assert(f[1]==1 && sockets[1248+235]==0);
    sockets[1248+235]=1;f[4]=4000;Comm_ReleaseFreeCall(shared,shared+464);assert(f[1]==1 && sockets[1248+235]==1);
    puts("PASS late-reply recycle guard and no unlocked timeout writes");
}
'''


QUARANTINE = r'''
static bool cc_tx_desynced[2];
'''
QUARANTINE_CASES = r'''
int main(void){
    assert(cpu_comm_tx_available(0) && cpu_comm_tx_available(1));
    assert(cpu_comm_tx_may_publish(1,0));
    assert(!cpu_comm_tx_may_publish(1,MSG_FLAG_SENT));
    assert(!cpu_comm_tx_available(1) && cpu_comm_tx_available(0));
    assert(!cpu_comm_tx_may_publish(1,0)); /* ownership cannot be reset by a new caller */
    cc_tx_desynced[1]=false;cpu_comm_tx_ack_timeout(1);
    assert(!cpu_comm_tx_may_publish(1,0) && cpu_comm_tx_may_publish(0,0));
    assert(!cpu_comm_tx_may_publish(2,0));
    puts("PASS timeout quarantine and refusal to overwrite an outstanding publication");
}
'''


def sources(tree):
    directory = tree/'drivers/soc/sunxi/cpu_comm'
    if not directory.exists(): directory = tree
    return {name: (directory/(name+'.c' if name!='cpu_comm' else name+'.h')).read_text()
            for name in ('cpu_comm', 'cpu_comm_mem', 'cpu_comm_channel', 'cpu_comm_proto', 'cpu_comm_hw')}


def run_case(directory, name, code, expected_failure=False):
    source=directory/(name+'.c'); exe=directory/name; source.write_text(code)
    subprocess.run(['clang','-pthread','-O1','-g','-fsanitize=address,undefined',str(source),'-o',str(exe)],check=True)
    run=subprocess.run([str(exe)],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'},timeout=15)
    if expected_failure:
        assert run.returncode != 0, 'baseline unexpectedly passed '+name
        print('PASS regression reproduced in baseline:',name)
    else:
        if run.returncode: print(run.stderr)
        assert run.returncode==0,name
        print(run.stdout.strip())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--kernel',type=Path,required=True)
    parser.add_argument('--baseline',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='h713-handoff-test-') as tmp:
        directory=Path(tmp)
        for label, tree in [('candidate',args.kernel)]+([('baseline',args.baseline)] if args.baseline else []):
            s=sources(tree);header=s['cpu_comm'];sems=''
            import re
            for name in ('FIFO_DEFAULT_CAP','MAX_WAIT_ENTRIES'):
                value=re.search(r'^#define '+name+r'\s+(\d+)',header,re.M).group(1)
                globals()['COMMON']=re.sub(r'#define '+name+r' \d+', '#define '+name+' '+value, COMMON)
            if 'static inline bool cpu_comm_sem_try_down(' in header:sems+=function(header,'static inline bool cpu_comm_sem_try_down(')
            for marker in ('static inline void cpu_comm_sem_down(', 'static inline int cpu_comm_sem_down_interruptible(',
                           'static inline int cpu_comm_sem_down_timeout(', 'static inline void cpu_comm_sem_up('):sems+=function(header,marker)+'\n'
            run_case(directory,label+'-semaphores',COMMON+SEMAPHORES+sems+SEM_CASES,label=='baseline')
            run_case(directory,label+'-references',COMMON+REFS+function(s['cpu_comm_mem'],'unsigned long cc_deref(')+REF_CASES,label=='baseline')
            if label=='baseline':
                baseline_stubs=HANDOFF+r'''
static int FindWaitBySessionId(void *l,u32 s,u32 **r){*r=0;return 1;}
'''
                boundary_case=r'''
int main(void){
    shared[1]=1;shared[0x1000]=1;shared[0x1002]=1;shared[16]=20;
    command_action(1,1);
    assert(shared[2440+10]==0 && queued==0 && sent==0);
}
'''
                helpers=function(s['cpu_comm_proto'],'void SendAckLow(')+function(s['cpu_comm_proto'],'void command_action(')
                run_case(directory,'baseline-slot-boundary',COMMON+baseline_stubs+helpers+boundary_case,True)
            if label=='candidate':
                if 'static bool cpu_comm_tx_available(' in s['cpu_comm_proto']:
                    gates='\n'.join(function(s['cpu_comm_proto'],m) for m in ('static bool cpu_comm_tx_available(', 'static bool cpu_comm_tx_may_publish(', 'static void cpu_comm_tx_ack_timeout('))
                    run_case(directory,'quarantine',COMMON+QUARANTINE+gates+QUARANTINE_CASES)
                    sender=function(s['cpu_comm_proto'],'int SendComm2CPUEx(')
                    assert 'share_seq_w[8] &=' not in sender
                    assert sender.index('cpu_comm_sem_down_interruptible(')<sender.index('cpu_comm_tx_may_publish(')<sender.index('memcpy(call_slot,')
                helpers='\n'.join([function(s['cpu_comm_proto'],'void SendAckLow('),function(s['cpu_comm_channel'],'void cpu_comm_complete_return('),
                                   function(s['cpu_comm_proto'],'void command_action('),function(s['cpu_comm_proto'],'void ack_action(')])
                run_case(directory,'handoff',COMMON+HANDOFF+helpers+HANDOFF_CASES)
                ring_stubs=HANDOFF.replace('static void Comm_ReleaseFreeCall(void *s,void *e){assert(sent);recycled++;}', '')
                run_case(directory,'recycle',COMMON+ring_stubs+FREE_RING+function(s['cpu_comm_channel'],'void Comm_ReleaseFreeCall(')+FREE_CASES)


if __name__=='__main__':main()
