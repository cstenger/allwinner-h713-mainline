#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Extract and exercise the actual CPU_COMM IRQ and receive-mode helpers.

MMIO/IRQ/timer stubs validate ownership and ordering; actual GIC delivery and
protocol round trips still require the DDR3 bench. --kernel is a patched tree.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def definition(source, marker):
    start = source.index(marker)
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef int irqreturn_t;
#define IRQ_NONE 0
#define IRQ_WAKE_THREAD 1
#define IRQ_HANDLED 2
#define IRQF_ONESHOT 4
#define IRQF_SHARED 8
#define H713_MSGBOX_RX_IRQ_EN 0x120
#define H713_MSGBOX_RX_IRQ_STAT 0x124
#define H713_MSGBOX_RX_IRQ_BIT 4
#define H713_MSGBOX_RX_FIFO 0x164
#define H713_MSGBOX_RX_DATA 0x174
#define MSGBOX_POLL_IDLE_MS 4
#define MSGBOX_POLL_FAST_US 250
#define NSEC_PER_MSEC 1000000
#define CLOCK_MONOTONIC 1
#define HRTIMER_MODE_REL 1
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define INIT_WORK(a,b) (work_inits++)
#define ns_to_ktime(a) (a)
#define cpu_comm_msgbox_poll_fn 0
#define cpu_comm_msgbox_tick 0
#define H713_FW_CAVE_PHYS 0x4b100300
#define H713_FW_CAVE_SIZE 0x920
#define H713_MIPS_LUI_K0 0x3c1a0000
static unsigned char regs[0x1000], *msgbox_ctrl_base=regs;
#define __iomem
static uint32_t fwcave[0x920/4]; static int cave_maps, cave_unmaps, cave_fail;
static void *ioremap(unsigned long a,unsigned long n){
    assert(a==0x4b100300 && n==0x920); if(cave_fail)return 0; cave_maps++; return fwcave;
}
static void iounmap(void *p){assert(p==(void *)fwcave);cave_unmaps++;}
static u32 enables, status;
static int events[32], nevents, drained=2, irq_result, registered, freed;
static int work_inits, timers, cancels, work_cancels;
static bool msgbox_irq_taken, msgbox_poll_active, msgbox_use_irq=true;
static int msgbox_irq=-1, msgbox_poll_timer, msgbox_rx_work;
static int msgbox_rx_by_irq, msgbox_rx_by_poll;
static void (*msgbox_rx_callback)(int,int);
static void atomic_add(int n,int *p){*p+=n;}
static int atomic_read(int *p){return *p;}
static u32 readl(void *v){
    unsigned char *p=v;
    if(p>=(unsigned char *)fwcave && p<(unsigned char *)fwcave+sizeof fwcave)return *(uint32_t *)p;
    if(p==regs+0x120)return enables;
    if(p==regs+0x124)return status;
    assert(p==regs+0x164); return 0;
}
static void writel(u32 v,void *q){
    unsigned char *p=q;
    if(p==regs+0x120){enables=v;events[nevents++]=v&4?3:1;}
    else {assert(p==regs+0x124);assert(v==4);status &= ~v;events[nevents++]=2;}
}
static int cpu_comm_msgbox_drain(void){events[nevents++]=4;return drained;}
static const char *cpu_comm_msgbox_type_name(u32 raw){return "unused";}
static int request_threaded_irq(int irq,irqreturn_t (*h)(int,void*),irqreturn_t (*t)(int,void*),int flags,const char *name,void *data){
    assert(irq==78);assert(flags==(IRQF_ONESHOT|IRQF_SHARED));registered++;return irq_result;
}
static void free_irq(int irq,void *p){assert(irq==78);freed++;enables|=4; /* thread completing during free_irq */}
static void hrtimer_setup(int *p,int cb,int clock,int mode){timers++;}
static void hrtimer_start(int *p,unsigned long ns,int mode){assert(ns==4000000);}
static void hrtimer_cancel(int *p){cancels++;}
static void cancel_work_sync(int *p){work_cancels++;}
'''
CASES = r'''
static void reset(void){
    enables=0x40;status=0x80;nevents=0;registered=freed=0;irq_result=0;
    work_inits=timers=cancels=work_cancels=0;msgbox_irq_taken=false;
    msgbox_poll_active=false;msgbox_use_irq=true;msgbox_irq=-1;msgbox_ctrl_base=regs;
    for(unsigned i=0;i<sizeof fwcave/4;i++)fwcave[i]=0;
    fwcave[0x1c0/4]=0x3c18ad98;fwcave[0x1c4/4]=0x3419a002;fwcave[0x1c8/4]=0xaf190000; /* 0006 marker */
    cave_maps=cave_unmaps=cave_fail=0;
}
int main(void){
    reset();
    assert(cpu_comm_msgbox_hardirq(78,0)==IRQ_NONE);assert(nevents==0);
    status|=4;assert(cpu_comm_msgbox_hardirq(78,0)==IRQ_NONE);assert(nevents==0);
    enables|=4;assert(cpu_comm_msgbox_hardirq(78,0)==IRQ_WAKE_THREAD);
    assert(enables==0x40);assert(nevents==1 && events[0]==1);
    assert(cpu_comm_msgbox_thread(78,0)==IRQ_HANDLED);
    assert(nevents==4 && events[1]==4 && events[2]==2 && events[3]==3);
    assert(status==0x80 && enables==0x44 && msgbox_rx_by_irq==2);
    msgbox_ctrl_base=0;assert(cpu_comm_msgbox_hardirq(78,0)==IRQ_NONE);
    reset();assert(cpu_comm_msgbox_request_irq(78,0)==0);
    assert(registered==1 && msgbox_irq_taken && !msgbox_poll_active);
    assert(cave_maps==1 && cave_unmaps==1);
    assert(timers==0 && work_inits==0 && status==0x80 && enables==0x44);
    cpu_comm_msgbox_free_irq();assert(freed==1 && enables==0x40 && cancels==0 && work_cancels==0);
    for(int mode=0;mode<5;mode++){
        reset();if(mode==0)irq_result=-16;if(mode==1)msgbox_use_irq=false;
        if(mode==3)fwcave[0x1c0/4]=0x3c1aad98;   /* pre-0006 lui k0 marker */
        if(mode==4)cave_fail=1;                /* cave not mappable */
        assert(cpu_comm_msgbox_request_irq(mode==2?-6:78,0)==0);
        assert(!msgbox_irq_taken && msgbox_poll_active && timers==1 && work_inits==1);
        assert(enables==0x40 && status==0x80 && nevents==0);
        if(mode>=3)assert(registered==0);
        cpu_comm_msgbox_free_irq();assert(freed==0 && cancels==1 && work_cancels==1);
    }
    puts("PASS ownership, mask/drain/ack/unmask, IRQ-only default, pre-0006 marker and unmapped-cave refusal, fallback and teardown");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    args = parser.parse_args()
    source = (args.kernel/'drivers/soc/sunxi/cpu_comm/cpu_comm_hw.c').read_text()
    assert 'static bool msgbox_use_irq = true;' in source, 'IRQ reception is the default since 0205'
    helpers = '\n'.join(definition(source, marker) for marker in (
        'static irqreturn_t cpu_comm_msgbox_hardirq(',
        'static irqreturn_t cpu_comm_msgbox_thread(',
        'static bool cpu_comm_fw_kreg_markers(',
        'int cpu_comm_msgbox_request_irq(', 'void cpu_comm_msgbox_free_irq('))
    with tempfile.TemporaryDirectory(prefix='h713-cpucomm-test-') as directory:
        path = Path(directory); (path/'test.c').write_text(STUBS+helpers+CASES)
        subprocess.run(['clang', '-fsanitize=address,undefined', '-g', '-O1',
                        str(path/'test.c'), '-o', str(path/'test')], check=True)
        subprocess.run([str(path/'test')], check=True,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})


if __name__ == '__main__':
    main()
