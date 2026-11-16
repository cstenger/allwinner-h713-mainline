#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Source-bound CPU_COMM TX reservation and send-error tests; no device access.

Extracts the actual prepared kernel functions, compiles them with ASan/UBSan
and pthread/MMIO stubs, and checks:

- the ARM -> MIPS doorbell never writes into a full eight-word FIFO, and a
  refusal happens before any shared-memory publication;
- concurrent senders cannot interleave data writes and TX_IRQ_EN pulses, and
  no word is lost while a simulated MIPS drains slowly;
- SendCommLow/SendAckLow leave the shared header untouched when refused,
  quarantine a refused or still-published ACK instead of BUG(), and
  publish SENT before the doorbell when accepted;
- SendComm2CPUEx propagates a refused send, clears its pending ACK, releases
  the unpublished wait object, keeps the unpublished slot cached and drops
  its sequence semaphore; copy failures unwind the same way;
- a late RETURN whose RETURN_ACK was refused is not recycled.

--baseline runs the old tree's sender/ACK paths against the same cases and
requires them to fail. --mutations requires broken candidate variants to fail.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, marker):
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def struct(source, name):
    start = source.index('struct ' + name + ' {')
    return source[start:source.index('};', start) + 2]


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
#define pr_info_ratelimited(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_info(...) ((void)0)
#define BUG() assert(!"BUG")
#define dmb(x) __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define CPU_ID_MAX 2
#define FIFO_DEFAULT_CAP 21
#define MAX_WAIT_ENTRIES 20
#define WAIT_ENTRY_SIZE 32
#define COMM_MSG_SIZE 104
#define SESSION_ID_MASK 0x3FFFFFFF
#define SEND_TIMEOUT_JIFFIES 500
#define MSG_TYPE_CALL_ACK 2
#define MSG_TYPE_RETURN_ACK 3
#define MSG_FLAG_NOTIFY BIT(0)
#define MSG_FLAG_RETURN_ACK BIT(1)
#define MSG_FLAG_SENT BIT(2)
#define INTR_TYPE_SEND 0
'''

# ── Hardware doorbell ─────────────────────────────────────────────────
HW = r'''
#define H713_MSGBOX_TX_IRQ_EN 0x830
#define H713_MSGBOX_TX_FIFO 0x864
#define H713_MSGBOX_TX_DATA 0x874
#define H713_MSGBOX_TX_IRQ_BIT BIT(3)
#define USEC_PER_MSEC 1000L
typedef long long ktime_t;
static pthread_mutex_t regs_lock=PTHREAD_MUTEX_INITIALIZER;
static volatile int fifo_count, en_level, delivered, overflow, interleave, writer=-1, published_outside;
static volatile int lock_owner=-1, lock_depth;
static volatile int stick_full;   /* simulated MIPS never drains */
static long long now_us;
static __thread int tid;
static unsigned char regs[0x1000];
static unsigned char *msgbox_ctrl_base=regs;
static u32 readl(const void *a){
    long off=(const unsigned char*)a-msgbox_ctrl_base;assert(off==H713_MSGBOX_TX_FIFO);
    pthread_mutex_lock(&regs_lock);u32 v=fifo_count;pthread_mutex_unlock(&regs_lock);return v;
}
static void writel(u32 v,void *a){
    long off=(unsigned char*)a-msgbox_ctrl_base;
    pthread_mutex_lock(&regs_lock);
    if(off==H713_MSGBOX_TX_DATA){
        if(fifo_count>=8)overflow++; else fifo_count++;
        if(writer!=-1)interleave++; writer=tid;
    }else{
        assert(off==H713_MSGBOX_TX_IRQ_EN);
        if(writer!=tid)interleave++;
        if(v==H713_MSGBOX_TX_IRQ_BIT)en_level=1;
        else {assert(v==0);en_level=0;writer=-1;}
    }
    pthread_mutex_unlock(&regs_lock);
}
#define udelay(n) sched_yield()
#define might_sleep() ((void)0)
static ktime_t ktime_get(void){return __atomic_load_n(&now_us,__ATOMIC_SEQ_CST);}
#define ktime_add_us(t,u) ((t)+(u))
#define ktime_after(a,b) ((a)>(b))
static volatile int freeze_clock;
static void usleep_range(unsigned long lo,unsigned long hi){if(!freeze_clock)__atomic_add_fetch(&now_us,lo,__ATOMIC_SEQ_CST);sched_yield();}
static pthread_mutex_t msgbox_tx_lock=PTHREAD_MUTEX_INITIALIZER;
#define spin_lock(l) do{assert(!pthread_mutex_lock(l));lock_owner=tid;}while(0)
#define spin_unlock(l) do{lock_owner=-1;assert(!pthread_mutex_unlock(l));}while(0)
typedef struct {int counter;} atomic_t;
#define atomic_inc(a) __atomic_add_fetch(&(a)->counter,1,__ATOMIC_SEQ_CST)
static atomic_t msgbox_tx_full;
static void cpu_comm_msgbox_kick(void){}
static const char *cpu_comm_msgbox_type_name(u32 raw){return "x";}
'''
HW_CASES = r'''
static int publishes;
static void publish(void *ctx){
    if(lock_owner!=tid)published_outside++;
    assert(writer==-1);   /* publication precedes the doorbell word */
    publishes++; if(ctx)++*(int*)ctx;
}
static void *drainer(void *arg){
    while(!__atomic_load_n((int*)arg,__ATOMIC_SEQ_CST)){
        pthread_mutex_lock(&regs_lock);
        if(fifo_count && !stick_full){fifo_count--;delivered++;}
        pthread_mutex_unlock(&regs_lock);
        usleep(20);
    }
    return 0;
}
static void *sender(void *arg){
    tid=(int)(long)arg;
    for(int i=0;i<300;i++){int mine=0;
        int r=cpu_comm_msgbox_send(i&3,publish,&mine);
        assert(r==0 && mine==1);}
    return 0;
}
int main(void){
    tid=99;
    /* Accepted: publish then data then pulse 1 -> 0. */
    int c=0;assert(cpu_comm_msgbox_send(2,publish,&c)==0);
    assert(c==1 && fifo_count==1 && en_level==0 && !overflow && !interleave);
    /* Full and never drained: refused, nothing published or written. */
    fifo_count=8;stick_full=1;c=0;
    assert(cpu_comm_msgbox_send(0,publish,&c)==-EBUSY);
    assert(c==0 && fifo_count==8 && !overflow && msgbox_tx_full.counter==1);
    /* Unmapped: refused before publication. */
    unsigned char *base=msgbox_ctrl_base;msgbox_ctrl_base=0;c=0;
    assert(cpu_comm_msgbox_send(0,publish,&c)==-ENODEV && c==0);msgbox_ctrl_base=base;
    /* Concurrent senders against a slow drain: no overflow, no interleave. */
    fifo_count=8;stick_full=0;freeze_clock=1;  /* bound covered above */
    int stop=0;pthread_t d,t[4];assert(!pthread_create(&d,0,drainer,&stop));
    for(long i=0;i<4;i++)assert(!pthread_create(t+i,0,sender,(void*)i));
    for(int i=0;i<4;i++)assert(!pthread_join(t[i],0));
    while(fifo_count)usleep(100);
    __atomic_store_n(&stop,1,__ATOMIC_SEQ_CST);assert(!pthread_join(d,0));
    assert(!overflow && !interleave && !published_outside);
    assert(delivered==8+1200);
    puts("PASS doorbell reserves FIFO room before publication; serialized, lossless under contention");
}
'''

# ── Protocol send/ACK publication ─────────────────────────────────────
PROTO = r'''
static bool cc_zero_wait_ptr;
static bool cc_tx_desynced[2];
static u8 header[0x200];
static int send_result, doorbells, local_actions;
static u32 doorbell_type;
static u32 getCurCPUID(int unused){return 0;}
static int queueAction(u32 d,u32 c){local_actions++;return 0;}
int cpu_comm_msgbox_send(u32 t,void (*publish)(void *),void *ctx){
    if(send_result)return send_result;
    publish(ctx);doorbells++;doorbell_type=t;return 0;
}
/* Baseline transport: cannot report failure; models a lost FIFO word. */
static void sunxi_cpu_comm_send_intr_to_mips(u32 t,u32 k,u32 v){doorbells++;doorbell_type=t;}
'''
PROTO_CASES = r'''
static u8 before[sizeof(header)];
static void reset(void){
    memset(header,0x5a,sizeof(header));header[0]=1;header[1]=0;header[2]=0;
    header[8]=0;header[105]=0;memcpy(before,header,sizeof(header));
    send_result=doorbells=local_actions=0;cc_tx_desynced[1]=false;
}
int main(void){
    /* CALL refused: no header byte changes and the caller sees the error. */
    reset();send_result=-EBUSY;
    assert(SendCommLow(header,3,2,0x1234,0x20000010)==-EBUSY);
    assert(!memcmp(before,header,sizeof(header)) && !doorbells);
    /* CALL accepted: metadata and SENT published before the doorbell. */
    reset();assert(SendCommLow(header,3,2,0x1234,0x20000010)==0);
    assert(doorbells==1 && doorbell_type==0 && header[16]==3 && (header[8]&MSG_FLAG_SENT));
    assert(*(u32*)(header+20)==0x1234 && *(u64*)(header+24)==0x20000010);
    /* ACK refused by the FIFO: header untouched, link quarantined. */
    reset();send_result=-EBUSY;
    assert(SendAckLow(header,20,0,7,0x8b15bd448baa0000ULL)==-EBUSY);
    assert(!memcmp(before,header,sizeof(header)) && cc_tx_desynced[1]);
    /* Previous ACK still published: refuse and quarantine instead of BUG. */
    reset();header[105]=4;memcpy(before,header,sizeof(header));
    assert(SendAckLow(header,20,0,7,1)==-EBUSY);
    assert(!memcmp(before,header,sizeof(header)) && cc_tx_desynced[1] && !doorbells);
    /* ACK accepted: 64-bit handle echoed and SENT set. */
    reset();header[2]=1;
    assert(SendAckLow(header,20,0,7,0x8b15bd448baa0000ULL)==0);
    assert(doorbells==1 && doorbell_type==MSG_TYPE_RETURN_ACK && (header[105]&4));
    assert(*(u64*)(header+112)==0x8b15bd448baa0000ULL && !cc_tx_desynced[1]);
    puts("PASS refused CALL/ACK publish nothing; stale ACK flag quarantines instead of BUG");
}
'''

# ── SendComm2CPUEx unwinding ─────────────────────────────────────────
SENDER = r'''
#define __user
struct task { int pid; } cur_task={1234}, *current=&cur_task;
#define KERN_INFO ""
#define DUMP_PREFIX_OFFSET 0
#define print_hex_dump(...) ((void)0)
static bool cc_force_remote, cc_zero_wait_ptr, cc_dump_slot, cc_uboot_flags;
static unsigned int cc_channel_pid, cc_channel_chan;
static u32 s_CallSessionId;
static bool cc_tx_desynced[2];
u32 comm_intrsem[16];
static u32 sockets[2496];
static u8 seqw[0x1000] __attribute__((aligned(8)));
static u32 waits[8][8];
static int send_result, ack_ok, copy_from_fail, copy_to_fail;
static int sends, waits_added, waits_removed, waits_released, sem_ups, sem_downs;
static unsigned long pending_sem; static u32 pending_session;
static u32 getCurCPUID(int u){return 0;}
static int IsCPUReset(u32 c){return 0;}
static int isCPUAppReady(u32 c){return 1;}
static int FindRoutine(u32 id,u8 *buf){assert(0);return 1;}
static unsigned long getSeq(u32 cpu){return (unsigned long)&sockets[cpu*1248];}
static unsigned long getShareSeqW(u32 cpu,u32 dir){return (unsigned long)seqw;}
static int fifo_isNearlyFull(u32 *f,int n){return 0;}
static void schedule(void){}
static u32 cc_ref(const void *p){
    if((const u8*)p>=(u8*)sockets && (const u8*)p<(u8*)(sockets+2496))return 0x10000000+(u32)((const u8*)p-(u8*)sockets);
    if((const u8*)p>=seqw && (const u8*)p<seqw+sizeof(seqw))return 0x20000000+(u32)((const u8*)p-seqw);
    if((const u8*)p>=(u8*)waits && (const u8*)p<(u8*)waits+sizeof(waits))return 0x30000000+(u32)((const u8*)p-(u8*)waits);
    assert(0);return 0;
}
static unsigned long cc_deref(u32 r){
    if(!r)return 0;
    if(r>=0x20000000 && r<0x20000000+sizeof(seqw))return (unsigned long)seqw+r-0x20000000;
    assert(0);return 0;
}
static int free_slot_taken;
static unsigned long Comm_GetFreeCall(void *s){assert(!free_slot_taken);free_slot_taken=1;return (unsigned long)(seqw+360+104*5);}
static int copy_from_user(void *d,const void *s,unsigned long n){
    if(copy_from_fail){memset(d,0xee,n/2);return n-n/2;}memcpy(d,s,n);return 0;}
static int copy_to_user(void *d,const void *s,unsigned long n){if(copy_to_fail)return n;memcpy(d,s,n);return 0;}
#define get_user(x,p) ((x)=*(p),0)
static int GetFreeWaitComm(void *f,u32 **w){*w=waits[waits_added&7];return 0;}
static int AddtoWaitComm(void *l,unsigned long w){waits_added++;return 0;}
static int GetWaitbySessionId(void *l,u32 s,u8 *r){waits_removed++;*(u32**)r=0;return 0;}
static void ReleaseWaitComm(u32 c,unsigned long w){waits_released++;}
static int cpu_comm_sem_down_interruptible(void *p){assert(*(u32*)p==1);*(u32*)p=0;sem_downs++;return 0;}
static int cpu_comm_sem_down_timeout(void *p,long t){if(!ack_ok)return -ETIME;return 0;}
static void cpu_comm_sem_up(void *p){++*(u32*)p;sem_ups++;}
static void cpu_comm_set_pending_ack(u32 c,unsigned long s,u32 sess){pending_sem=s;pending_session=sess;}
int SendCommLow(u8 *seq,u32 slot,u8 type,u32 param,u32 sem_ref){
    assert(pending_sem);sends++;if(send_result)return send_result;seq[8]|=MSG_FLAG_SENT;return 0;}
'''
SENDER_CASES = r'''
static u8 msg[COMM_MSG_SIZE];
static u32 *sem(void){return (u32*)(getSeq(1)+1036);}
static void reset(void){
    memset(sockets,0,sizeof(sockets));memset(seqw,0,sizeof(seqw));memset(comm_intrsem,0,sizeof(comm_intrsem));
    memset(msg,0,sizeof(msg));*(u16*)(msg+2)=1;
    seqw[0]=1;seqw[1]=0;seqw[2]=0;*(u16*)(seqw+360+104*5+4)=5;
    *sem()=1;free_slot_taken=0;cc_tx_desynced[1]=false;
    send_result=copy_from_fail=copy_to_fail=0;ack_ok=1;
    sends=waits_added=waits_removed=waits_released=sem_ups=sem_downs=0;pending_sem=0;
}
static void unpublished_common(int expect_wait){
    assert(*sem()==1 && sem_ups==1);
    assert(!pending_sem);
    assert(waits_added==expect_wait && waits_removed==expect_wait && waits_released==expect_wait);
    assert(comm_intrsem[2*1+1+8]==cc_ref(seqw+360+104*5)); /* kept for reuse */
    assert(*(u16*)(seqw+360+104*5+4)==5);
    assert(!(seqw[8]&MSG_FLAG_SENT) && !cc_tx_desynced[1]);
}
int main(void){
    /* Success: published, cache handed to the peer, wait stays for RPC. */
    reset();assert(SendComm2CPUEx((unsigned long)msg,1,0)==0);
    assert(sends==1 && waits_added==1 && !waits_released && !comm_intrsem[11] && *sem()==1);
    /* Refused before publication: error returned, everything unwound. */
    reset();send_result=-EBUSY;assert(SendComm2CPUEx((unsigned long)msg,1,0)==-EBUSY);
    assert(sends==1);unpublished_common(1);
    /* The cached slot is reused by the next send; no second free-ring take. */
    send_result=0;assert(SendComm2CPUEx((unsigned long)msg,1,0)==0 && !comm_intrsem[11]);
    /* copy_to_user failure: wait released, slot cached, nothing sent. */
    reset();copy_to_fail=1;assert(SendComm2CPUEx((unsigned long)msg,1,1)==-EFAULT);
    assert(!sends);unpublished_common(1);
    /* Partial copy_from_user: slot index restored, no wait allocated. */
    reset();copy_from_fail=1;assert(SendComm2CPUEx((unsigned long)msg,1,1)==-EFAULT);
    assert(!sends);unpublished_common(0);
    /* ACK timeout after publication: quarantine, wait released, peer owns slot. */
    reset();ack_ok=0;assert(SendComm2CPUEx((unsigned long)msg,1,0)==-ETIME);
    assert(cc_tx_desynced[1] && waits_released==1 && !comm_intrsem[11] && *sem()==1);
    puts("PASS refused/failed sends unwind wait, pending ACK, slot cache and semaphore");
}
'''

# ── Late RETURN recycle after a refused RETURN_ACK ───────────────────
RETURN = r'''
static u32 sockets[2496], *s_CommSockt=sockets;
static u8 shared[0x2000];
static int ack_result, recycled, queued, acks;
static unsigned long getSeq(u32 cpu){return (unsigned long)&sockets[cpu*1248];}
static unsigned long getShareSeqR(u32 c,u32 d){return (unsigned long)shared;}
static unsigned long getShareSeqW(u32 c,u32 d){return (unsigned long)shared+0x1000;}
static u32 cc_ref(const void *p){return 0x10000000+(u32)((const u8*)p-(u8*)sockets);}
static unsigned long cc_deref(u32 r){return r?(unsigned long)sockets+r-0x10000000:0;}
static void cpu_comm_sem_down(void *p){}
static void cpu_comm_sem_up(void *p){}
static int AddReturn2Fifo(u32 *f,void *e){queued++;return 1;}
static void Comm_ReleaseFreeCall(void *s,void *e){recycled++;}
'''
RETURN_CASES = r'''
int main(void){
    /* Empty active list: this RETURN is late. */
    u32 *head=&sockets[1248+24];
    for(int ok=0;ok<2;ok++){
        memset(sockets,0,sizeof(sockets));*head=cc_ref(head);recycled=acks=0;
        ack_result=ok?0:-EBUSY;
        cpu_comm_complete_return(1,42,(unsigned long)shared+360,0,0,0);
        assert(acks==1 && recycled==(ok?1:0) && !queued);
    }
    puts("PASS late RETURN is recycled only after its RETURN_ACK is published");
}
'''
RETURN_ACK_STUB = r'''
int SendAckLow(void *d,u32 a,u8 b,u32 c,u64 e){acks++;return ack_result;}
'''


def sources(tree):
    directory = tree/'drivers/soc/sunxi/cpu_comm'
    if not directory.exists():
        directory = tree
    return {name: (directory/(name+'.c' if name != 'cpu_comm' else name+'.h')).read_text()
            for name in ('cpu_comm', 'cpu_comm_proto', 'cpu_comm_channel', 'cpu_comm_hw')}


def run_case(directory, name, code, expect_failure=False):
    source = directory/(name+'.c'); exe = directory/name
    source.write_text(code)
    built = subprocess.run(['clang', '-pthread', '-O1', '-g', '-fsanitize=address,undefined',
                            '-fno-sanitize-recover=all', '-Wno-unused-function', str(source), '-o', str(exe)],
                           capture_output=True, text=True)
    if built.returncode:
        if expect_failure:
            print('PASS rejected (does not build):', name)
            return
        print(built.stderr)
        raise SystemExit('build failed: '+name)
    run = subprocess.run([str(exe)], capture_output=True, text=True,
                         env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'}, timeout=60)
    if expect_failure:
        assert run.returncode != 0, 'unexpectedly passed: '+name
        why = [l for l in (run.stderr+run.stdout).splitlines() if 'Assertion' in l or 'runtime error' in l]
        print('PASS rejected:', name, '--', (why[0].split(': ', 2)[-1] if why else 'exit %d' % run.returncode))
    else:
        if run.returncode:
            print(run.stdout, run.stderr)
        assert run.returncode == 0, name
        print(run.stdout.strip())


def candidate_parts(s):
    proto, hw, chan = s['cpu_comm_proto'], s['cpu_comm_hw'], s['cpu_comm_channel']
    gates = '\n'.join(function(proto, m) for m in (
        'static bool cpu_comm_tx_available(', 'static bool cpu_comm_tx_may_publish(',
        'static void cpu_comm_tx_quarantine(', 'static void cpu_comm_tx_ack_timeout('))
    depth = re.search(r'^#define H713_MSGBOX_TX_FIFO_DEPTH\s+\d+', hw, re.M).group(0)
    timeout = re.search(r'^#define H713_MSGBOX_TX_SPACE_TIMEOUT_US\s+.*$', hw, re.M).group(0)
    return {
        'hw': depth+'\n'+timeout+'\n'+function(hw, 'int cpu_comm_msgbox_send('),
        'publish': '\n'.join([struct(proto, 'cc_send_publication'), function(proto, 'static void cc_publish_send('),
                              function(proto, 'int SendCommLow('), struct(proto, 'cc_ack_publication'),
                              function(proto, 'static void cc_publish_ack('), function(proto, 'int SendAckLow(')]),
        'gates': gates,
        'sender': function(proto, 'static void cc_release_send_wait(')+'\n'+function(proto, 'int SendComm2CPUEx('),
        'complete': function(chan, 'void cpu_comm_complete_return('),
    }


def programs(p):
    gates_decl = 'static void cpu_comm_tx_quarantine(u32 cpu);\n'
    return {
        'tx-doorbell': COMMON+HW+p['hw']+HW_CASES,
        'tx-publish': COMMON+PROTO+gates_decl+p['gates']+p['publish']+PROTO_CASES,
        'tx-sender': COMMON+SENDER+p['gates']+p['sender']+SENDER_CASES,
        'tx-late-return': COMMON+RETURN+RETURN_ACK_STUB+p['complete']+RETURN_CASES,
    }


MUTATIONS = [
    ('publish-before-reservation', 'hw', ('\tdeadline = ktime_add_us(', '\tpublish(ctx);\n\tdeadline = ktime_add_us('),
     ('\tpublish(ctx);\n\n\t/*', '\t/*')),
    ('no-capacity-check', 'hw', ('if (fifo < H713_MSGBOX_TX_FIFO_DEPTH)', 'if (1)')),
    ('unlocked-doorbell', 'hw', ('\tpublish(ctx);\n', '\tspin_unlock(&msgbox_tx_lock);\n\tpublish(ctx);\n'),
     ('\twritel(0, msgbox_ctrl_base + H713_MSGBOX_TX_IRQ_EN);\n\tspin_unlock(&msgbox_tx_lock);',
      '\twritel(0, msgbox_ctrl_base + H713_MSGBOX_TX_IRQ_EN);')),
    ('ignored-send-result', 'sender', ('\tif (ret) {\n\t\t/* Refused before publication', '\tif (0) {\n\t\t/* Refused before publication')),
    ('copy-to-user-leaks-wait', 'sender', ('\t\t\tgoto out_release_wait;\n\t\t}\n\t} else {', '\t\t\tgoto out_up_sem;\n\t\t}\n\t} else {')),
    ('cache-cleared-on-failure', 'sender', ('out_up_sem:\n', 'out_up_sem:\n\tcomm_intrsem[cache_idx] = 0;\n')),
    ('pending-ack-left-set', 'sender', ('\t\tcpu_comm_set_pending_ack(dst_cpu, 0, 0);\n\t\tpr_err("cpu_comm: SendComm2CPUEx: not published',
                                        '\t\tpr_err("cpu_comm: SendComm2CPUEx: not published')),
    ('slot-index-not-restored', 'sender', ('\t\t\t*(u16 *)(call_slot + 4) = slot_idx;\n\t\t\tret = -EFAULT;', '\t\t\tret = -EFAULT;')),
    ('ack-refusal-not-quarantined', 'publish', ('\t\t       __func__, dst, ret);\n\t\tcpu_comm_tx_quarantine(dst);', '\t\t       __func__, dst, ret);')),
    ('stale-ack-overwritten', 'publish', ('\tif (seq[105] & 4) {', '\tif (0) {')),
    ('recycle-without-ack', 'complete', ('if (!wait && recycle && acked)', 'if (!wait && recycle)')),
]


def mutate(parts, edits):
    out = dict(parts)
    for old, new in edits:
        hits = [k for k in out if old in out[k]]
        assert hits, 'mutation anchor missing: '+old[:60]
        out[hits[0]] = out[hits[0]].replace(old, new, 1)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--mutations', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='h713-cpu-comm-tx-') as tmp:
        directory = Path(tmp)
        parts = candidate_parts(sources(args.kernel))
        for name, code in programs(parts).items():
            run_case(directory, name, code)
        if args.mutations:
            for label, key, *edits in MUTATIONS:
                assert all(old in parts[key] for old, _ in edits), 'mutation anchor missing: '+label
                broken = mutate(parts, edits)
                prog = {'hw': 'tx-doorbell', 'publish': 'tx-publish', 'sender': 'tx-sender',
                        'complete': 'tx-late-return'}[key]
                run_case(directory, 'mutant-'+label, programs(broken)[prog], expect_failure=True)
        if args.baseline:
            b = sources(args.baseline)
            proto, hw = b['cpu_comm_proto'], b['cpu_comm_hw']
            assert 'int cpu_comm_msgbox_send(' not in hw
            # Old doorbell: same MMIO model, writes regardless of the count.
            old_hw = function(hw, 'void sunxi_cpu_comm_send_intr_to_mips(')
            shim = r'''
int cpu_comm_msgbox_send(u32 t,void (*publish)(void *),void *ctx){
    publish(ctx);sunxi_cpu_comm_send_intr_to_mips(t,0,0);return 0;}
'''
            run_case(directory, 'baseline-doorbell', COMMON+HW+old_hw+shim+HW_CASES, expect_failure=True)
            stale_ack = r'''
int main(void){
    memset(header,0,sizeof(header));header[0]=1;header[105]=4;
    SendAckLow(header,20,0,7,1);   /* old code: BUG() */
    puts("survived");
}
'''
            run_case(directory, 'baseline-stale-ack-bug', COMMON+PROTO+function(proto, 'void SendAckLow(')+stale_ack,
                     expect_failure=True)
            old_sender = function(proto, 'int SendComm2CPUEx(')
            assert 'SendCommLow(share_seq_w' in old_sender and 'ret = SendCommLow(' not in old_sender
            leak = r'''
int main(void){
    reset();copy_to_fail=1;SendComm2CPUEx((unsigned long)msg,1,1);
    assert(waits_added==waits_released);   /* old code leaks the wait */
}
'''
            gates = '\n'.join(function(proto, m) for m in (
                'static bool cpu_comm_tx_available(', 'static bool cpu_comm_tx_may_publish(',
                'static void cpu_comm_tx_ack_timeout('))
            sender_cases = SENDER_CASES[:SENDER_CASES.index('int main(void){')]
            run_case(directory, 'baseline-copy-to-user-leak', COMMON+SENDER+gates+old_sender+sender_cases+leak,
                     expect_failure=True)


if __name__ == '__main__':
    main()
