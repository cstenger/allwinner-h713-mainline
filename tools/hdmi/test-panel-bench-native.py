#!/usr/bin/env python3
"""Compile actual bench lifecycle/MMIO functions with fake resources only."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TVFE = ROOT / 'modules/hdmi-tvfe-bench'
for suffix in ('c', 'h'):
    link = TVFE / f'h713-hdmi-tvfe.{suffix}'
    if not link.is_symlink() or link.readlink() != Path(f'../hdmi-audio/h713-hdmi-tvfe.{suffix}'):
        raise RuntimeError('TVFE bench must use the production relative symlink')

source = (TVFE / 'h713-tvfe-bench-main.c').read_text()
actual = source[source.index('static void audio_top_release('):source.index('module_init(')]
defines = '\n'.join(line for line in source.splitlines() if line.startswith('#define AUDIO_'))
preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
typedef unsigned int uint;
#define __init
#define __exit
#define __iomem
static bool armed, audio_top, keep_audio_top, top_cfg=true;
static uint top_ctl=0x700;
static bool receiver_held, region_held, ihb_retimed, top_initialized;
static void *ihb, *top;
static u32 ihb_saved, top_saved_ctl, top_saved_cfg;
static int (*receiver_acquire)(void);
static void (*receiver_release)(void);
static u32 ihb_reg, top_regs[4];
static int gets, puts, refs, reserved, prepared, released, maps, unmaps, writes, errors, restored;
static int missing_symbols, busy, prepare_error, acquire_error, clocks_error, fail_map, reject_write, reject_top_once;
static int h713_receiver_acquire(void) { ++gets; if(acquire_error) return acquire_error; ++refs; return 0; }
static void h713_receiver_release(void) { --refs; }
#define symbol_get(name) (missing_symbols ? 0 : name)
#define symbol_put(name) (++puts)
static void *request_mem_region(unsigned long base,unsigned long size,const char *name) {
 assert(base==0x0614a000 && size==0x10 && name); if(busy) return NULL; ++reserved; return &reserved;
}
static void release_mem_region(unsigned long base,unsigned long size) {
 assert(base==0x0614a000 && size==0x10 && reserved==1); --reserved;
}
static int h713_hdmi_tvfe_prepare(void) { ++prepared; return prepare_error; }
static void h713_hdmi_tvfe_release(void) { ++released; }
static int audio_clocks_on(void) { return clocks_error; }
static void *ioremap(unsigned long base,unsigned long size) {
 ++maps; if(maps==fail_map) return NULL;
 if(base==0x02001d50) { assert(size==4); return &ihb_reg; }
 assert(base==0x0614a000 && size==0x10); return top_regs;
}
static void iounmap(void *p) { assert(p); ++unmaps; }
static u32 readl(void *p) { return *(u32 *)p; }
static void writel(u32 v,void *p) { ++writes; if(reject_top_once && p==top_regs) {reject_top_once=0; return;} if(!reject_write) *(u32 *)p=v; }
#define pr_info(fmt,...) do { if(strstr(fmt,"restored audio-top")) ++restored; } while(0)
#define pr_err(...) (++errors)
'''
tests = r'''
static void reset(void) {
 armed=false; audio_top=false; keep_audio_top=false; top_cfg=true; top_ctl=0x700;
 receiver_held=region_held=ihb_retimed=top_initialized=false;
 receiver_acquire=NULL; receiver_release=NULL; ihb=top=NULL;
 gets=puts=refs=reserved=prepared=released=maps=unmaps=writes=errors=restored=0;
 missing_symbols=busy=prepare_error=acquire_error=clocks_error=fail_map=reject_write=reject_top_once=0;
 ihb_reg=0x123; top_regs[0]=0x50; top_regs[3]=0x90000000;
}
int main(void) {
 reset(); assert(h713_tvfe_bench_init()==-EPERM && !gets && !writes);
 reset(); armed=true; keep_audio_top=true; assert(h713_tvfe_bench_init()==-EINVAL && !gets);
 reset(); armed=true; top_ctl=1; assert(h713_tvfe_bench_init()==-EINVAL && !gets);
 reset(); armed=true; missing_symbols=1; assert(h713_tvfe_bench_init()==-ENODEV && !gets);
 reset(); armed=true; acquire_error=-EBUSY; assert(h713_tvfe_bench_init()==-EBUSY && !refs && !prepared && puts==2);
 reset(); armed=true; busy=1; assert(h713_tvfe_bench_init()==-EBUSY && !refs && !prepared && !writes);
 reset(); armed=true; prepare_error=-EIO; assert(h713_tvfe_bench_init()==-EIO && !refs && !reserved && !maps);
 reset(); armed=true; audio_top=true; clocks_error=-EBUSY;
 assert(h713_tvfe_bench_init()==-EBUSY && !maps && !refs && !reserved && released==1);
 reset(); armed=true; audio_top=true; fail_map=2;
 assert(h713_tvfe_bench_init()==-ENOMEM && unmaps==1 && !refs && !reserved && released==1);
 reset(); armed=true; audio_top=true; reject_write=1;
 assert(h713_tvfe_bench_init()==-EIO && unmaps==2 && !refs && !reserved);
 reset(); armed=true; audio_top=true; reject_top_once=1;
 assert(h713_tvfe_bench_init()==-EIO && !refs && !reserved && unmaps==2 && restored==1);
 assert(top_regs[0]==0x50 && top_regs[3]==0x90000000 && ihb_reg==0x123);
 reset(); armed=true; assert(!h713_tvfe_bench_init() && reserved==1 && refs==1 && !maps);
 h713_tvfe_bench_exit(); assert(!refs && !reserved && released==1 && puts==2);
 reset(); armed=true; audio_top=true; assert(!h713_tvfe_bench_init());
 assert(top_regs[0]==0x750 && top_regs[3]==0x911a5e00 && ihb_reg==0x81000002);
 h713_tvfe_bench_exit(); assert(top_regs[0]==0x50 && top_regs[3]==0x90000000 && ihb_reg==0x123);
 assert(restored==1 && !errors && unmaps==2 && !refs && !reserved);
 reset(); armed=true; audio_top=true; top_ctl=0; top_cfg=false;
 assert(!h713_tvfe_bench_init() && top_regs[0]==0x50 && top_regs[3]==0x90000000);
 h713_tvfe_bench_exit(); assert(!refs && !reserved);
 reset(); armed=true; audio_top=true; assert(!h713_tvfe_bench_init()); reject_write=1;
 h713_tvfe_bench_exit(); assert(errors==2 && !restored && !refs && !reserved && unmaps==2);
 return 0;
}
'''
watchdog = (ROOT / 'modules/r-wdog-reboot-bench/h713-r-wdog-reboot.c').read_text()
watchdog = watchdog[watchdog.index('static int h713_r_wdog_restart('):watchdog.index('module_init(')]
wd_preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#define __init
#define __exit
#define R_WDOG_PHYS 0x07020400u
#define NOTIFY_DONE 0
#define pr_emerg(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
struct notifier_block { int (*notifier_call)(struct notifier_block *,unsigned long,void *); int priority; };
static bool armed;
static void *r_wdog;
static uint32_t regs[8], values[4];
static int offsets[4], writes, maps, unmaps, registered, unregistered, register_error, map_fail, occupied, busy;
static void *request_mem_region(unsigned long base,unsigned long size,const char *name) { assert(base==R_WDOG_PHYS && size==0x20 && name); if(busy) return NULL; assert(!occupied); occupied=1; return &occupied; }
static void release_mem_region(unsigned long base,unsigned long size) { assert(base==R_WDOG_PHYS && size==0x20 && occupied); occupied=0; }
static int delays[2], delay_count;
static void *ioremap(unsigned long base,unsigned long size) { assert(base==R_WDOG_PHYS && size==0x20); ++maps; return map_fail?NULL:regs; }
static void iounmap(void *p) { assert(p==regs); ++unmaps; }
static int register_restart_handler(struct notifier_block *nb) { assert(nb->priority==200); ++registered; return register_error; }
static void unregister_restart_handler(struct notifier_block *nb) { assert(nb->priority==200); ++unregistered; }
static void writel(uint32_t v,void *p) { offsets[writes]=(char *)p-(char *)regs; values[writes++]=v; *(uint32_t *)p=v; }
static uint32_t readl(void *p) { return *(uint32_t *)p; }
static void mdelay(int n) { delays[delay_count++]=n; }
'''
wd_tests = r'''
int main(void) {
 assert(h713_r_wdog_init()==-EPERM && !maps && !registered);
 armed=true; busy=1; assert(h713_r_wdog_init()==-EBUSY && !maps); busy=0; map_fail=1; assert(h713_r_wdog_init()==-ENOMEM && !registered && !occupied);
 map_fail=0; register_error=-EBUSY; assert(h713_r_wdog_init()==-EBUSY && unmaps==1 && !writes && !occupied);
 register_error=0; assert(!h713_r_wdog_init() && !writes);
 assert(h713_r_wdog_restart(NULL,0,NULL)==NOTIFY_DONE);
 assert(writes==4 && offsets[0]==0 && offsets[1]==0x10 && offsets[2]==0x14 && offsets[3]==0x14);
 assert(values[0]==0 && values[1]==0x16aa0101 && values[2]==0x16aa0000 && values[3]==0x16aa0001);
 assert(delay_count==2 && delays[0]==1 && delays[1]==2000);
 h713_r_wdog_exit(); assert(unregistered==1 && unmaps==2 && !occupied);
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='h713-panel-bench-') as d:
    for name, code in [('tvfe', preamble + defines + '\n' + actual + tests),
                       ('watchdog', wd_preamble + watchdog + wd_tests)]:
        path = Path(d)
        (path / (name + '.c')).write_text(code)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        str(path / (name + '.c')), '-o', str(path / name)], check=True)
        subprocess.run([str(path / name)], check=True)
print('PASS: production symlinks; TVFE guards/ownership/MMIO/restore faults; watchdog registration/sequence/fallback cleanup (all mocked)')
