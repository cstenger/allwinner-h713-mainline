#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise actual prepared recovery/stop/completion helpers under sanitizers."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def definition(source, name):
    match = re.search(r'static (?:int|bool|void) '+name+r'\([^;]*?\)\s*\{', source, re.S)
    assert match, name
    start=match.start(); end=match.end();depth=1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

STUBS=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
typedef uint32_t u32;
#define BIT(n) (1U<<(n))
#define GENMASK(h,l) ((~0U>>(31-(h))) & (~0U<<(l)))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define IS_ERR_OR_NULL(p) (!(p) || (intptr_t)(p)<0)
#define dev_err(...) ((void)0)
#define dev_warn_ratelimited(...) ((void)0)
#define mmc_dev(m) (m)
#define spin_lock_irqsave(l,f) do { assert(!locked); locked=1; } while(0)
#define spin_unlock_irqrestore(l,f) do { assert(locked); locked=0; } while(0)
#define REG_CARG SDXC_REG_CARG
#define REG_CMDR SDXC_REG_CMDR
#define REG_RINTR SDXC_REG_RINTR
#define REG_RESP0 SDXC_REG_RESP0
#define REG_DMAC SDXC_REG_DMAC
static unsigned long ticks;
#define jiffies (ticks++)
#define msecs_to_jiffies(n) 3
#define time_before(a,b) ((a)<(b))
struct mmc_ios { unsigned char bus_width; };
struct mmc_host { struct mmc_ios ios; };
struct mmc_command { unsigned opcode,arg,resp[4]; int error; };
struct mmc_data { unsigned flags; int error; };
struct mmc_request { struct mmc_command *cmd,*stop; struct mmc_data *data; };
struct sunxi_mmc_cfg { bool recover_read_errors; };
struct sunxi_mmc_host { struct mmc_host *mmc; struct sunxi_mmc_cfg *cfg; void *reset; int ferror,recovery_error,lock; struct mmc_request *manual_stop_mrq; };
static int events[64],nevents,locked,done,reset_error,init_error,clock_error,dma_stuck,stop_mode;
static void event(int value){assert(!locked);events[nevents++]=value;}
static int reset_control_reset(void*p){event(1);return reset_error;}
static int sunxi_mmc_init_host(struct sunxi_mmc_host*h){event(2);return init_error;}
static void sunxi_mmc_set_bus_width(struct sunxi_mmc_host*h,unsigned char w){event(3);assert(w==3);}
static void sunxi_mmc_set_clk(struct sunxi_mmc_host*h,struct mmc_ios*i){event(4);h->ferror=clock_error;}
static u32 mmc_readl(struct sunxi_mmc_host*h,unsigned reg){
 if(reg==REG_DMAC){event(5);return dma_stuck?SDXC_IDMAC_SOFT_RESET:0;}
 if(reg==REG_RINTR)return stop_mode==0?SDXC_COMMAND_DONE:stop_mode==1?SDXC_DATA_CRC_ERROR:0;
 assert(reg==REG_RESP0);return 0x900;
}
static void mmc_writel(struct sunxi_mmc_host*h,unsigned reg,u32 v){
 if(reg==REG_CMDR){event(6);assert((v&63)==MMC_STOP_TRANSMISSION || (v&63)==SD_IO_RW_DIRECT);}
 else assert(reg==REG_CARG || reg==REG_RINTR);
}
static struct sunxi_mmc_host *current_host;
static void mmc_request_done(struct mmc_host*m,struct mmc_request*r){
 assert(!locked);assert(!current_host->manual_stop_mrq);done++;event(7);
}
'''
CASES=r'''
static struct mmc_host mmc={.ios.bus_width=3};
static struct sunxi_mmc_cfg cfg;
static struct sunxi_mmc_host host;
static struct mmc_command cmd,stop;
static struct mmc_data data;
static struct mmc_request req;
static void setup(void){
 nevents=locked=done=reset_error=init_error=clock_error=dma_stuck=stop_mode=0;ticks=0;
 cfg.recover_read_errors=true;
 cmd=(struct mmc_command){.opcode=MMC_READ_MULTIPLE_BLOCK,.error=-ETIMEDOUT};
 stop=(struct mmc_command){.error=-ETIMEDOUT};data=(struct mmc_data){.flags=MMC_DATA_READ,.error=-ETIMEDOUT};
 req=(struct mmc_request){.cmd=&cmd,.stop=&stop,.data=&data};
 host=(struct sunxi_mmc_host){.mmc=&mmc,.cfg=&cfg,.reset=(void*)1,.manual_stop_mrq=&req};current_host=&host;
}
static void order(const int *expected,int count){assert(nevents==count);for(int i=0;i<count;i++)assert(events[i]==expected[i]);}
int main(void){
 setup();sunxi_mmc_finish_manual_stop(&host,&req);
 const int good[]={1,2,5,3,4,6,7};order(good,7);
 assert(done==1 && !host.recovery_error && !host.manual_stop_mrq);
 assert(cmd.error==-ETIMEDOUT && data.error==-ETIMEDOUT && stop.error==-ETIMEDOUT && stop.resp[0]==0x900);
 assert(!sunxi_mmc_refuse_failed_recovery(&host,&req));assert(done==1);
 for(int stage=0;stage<7;stage++){
  setup();int expected;
  switch(stage){
   case 0:host.reset=0;expected=-ENODEV;break;
   case 1:reset_error=-EIO;expected=-EIO;break;
   case 2:init_error=-EBUSY;expected=-EBUSY;break;
   case 3:dma_stuck=1;expected=-ETIMEDOUT;break;
   case 4:clock_error=-EINVAL;expected=-EINVAL;break;
   default:stop_mode=stage==5?1:2;expected=-ETIMEDOUT;break;
  }
  sunxi_mmc_finish_manual_stop(&host,&req);
  assert(done==1 && !locked && !host.manual_stop_mrq);
  assert(host.recovery_error==expected && cmd.error==expected && data.error==expected && stop.error==expected);
  if(stage<5)for(int i=0;i<nevents;i++)assert(events[i]!=6);
  const int lengths[]={1,2,3,4,6,7,7};assert(nevents==lengths[stage]);
  host.ferror=0; /* set_ios must not erase the terminal recovery failure */
  nevents=0;cmd.error=stop.error=data.error=0;
  assert(sunxi_mmc_refuse_failed_recovery(&host,&req));
  assert(nevents==1 && events[0]==7 && done==2);
  assert(cmd.error==expected && data.error==expected && stop.error==expected);
  nevents=0;req.data=0;req.stop=0;cmd.opcode=13;cmd.error=0;
  assert(sunxi_mmc_refuse_failed_recovery(&host,&req));assert(done==3 && cmd.error==expected && nevents==1);
 }
 /* Wrong-controller, CMD17, CMD53, write and missing-data paths never reset. */
 for(int scenario=0;scenario<5;scenario++){
  setup();if(scenario==0)cfg.recover_read_errors=false;
  if(scenario==1)cmd.opcode=17;if(scenario==2)cmd.opcode=SD_IO_RW_EXTENDED;
  if(scenario==3)data.flags=MMC_DATA_WRITE;if(scenario==4)req.data=0;
  assert(!sunxi_mmc_needs_read_recovery(&host,&req));
  sunxi_mmc_finish_manual_stop(&host,&req);
  const int legacy[]={6,7};order(legacy,2);assert(done==1 && !host.recovery_error);
 }
 setup();req.stop=0;clock_error=-EIO;sunxi_mmc_finish_manual_stop(&host,&req);assert(done==1 && data.error==-EIO);
 puts("PASS reset/init/IDMA/clock/CMD12 failures, skipped unsafe stop, exact-once cleanup, sticky refusal before I/O and unchanged non-target paths");
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--mutations',action='store_true');a=p.parse_args()
    s=(a.kernel/'drivers/mmc/host/sunxi-mmc.c').read_text()
    configs=re.findall(r'static const struct sunxi_mmc_cfg (\w+) = \{(.*?)\n\};',s,re.S)
    assert [name for name,body in configs if re.search(r'\.recover_read_errors\s*=\s*true',body)]==['sun50i_h713_emmc_cfg']
    request=definition(s,'sunxi_mmc_request')
    assert re.search(r'if\s*\(sunxi_mmc_refuse_failed_recovery\(host, mrq\)\)\s*return;',request)
    assert request.index('sunxi_mmc_refuse_failed_recovery(host, mrq)') < request.index('sunxi_mmc_map_dma(')
    start=s.index('static irqreturn_t sunxi_mmc_handle_manual_stop(')
    thread=s[start:s.index('static int sunxi_mmc_oclk_onoff(',start)]
    assert thread.count('sunxi_mmc_finish_manual_stop(host, mrq)')==1
    headers=s+'\n'+(a.kernel/'include/linux/mmc/mmc.h').read_text()+'\n'+(a.kernel/'include/linux/mmc/sdio.h').read_text()+'\n'+(a.kernel/'include/linux/mmc/core.h').read_text()
    constants='\n'.join(line for line in headers.replace('\\\n',' ').splitlines() if re.match(r'#define\s+(?:SDXC_\w+|MMC_READ_MULTIPLE_BLOCK|MMC_STOP_TRANSMISSION|SD_IO_RW_EXTENDED|SD_IO_RW_DIRECT|SDIO_CCCR_ABORT|MMC_DATA_READ|MMC_DATA_WRITE)\s+',line))
    functions='\n'.join(definition(s,name) for name in ('sunxi_mmc_send_manual_stop','sunxi_mmc_reinit_after_read_error','sunxi_mmc_needs_read_recovery','sunxi_mmc_finish_manual_stop','sunxi_mmc_refuse_failed_recovery'))
    with tempfile.TemporaryDirectory(prefix='h713-recovery-test-') as directory:
        path=Path(directory)
        # Constants are needed by the MMIO stubs as well as the extracted code.
        (path/'test.c').write_text('#define BIT(n) (1U<<(n))\n'+constants+'\n'+STUBS+'\n'+functions+CASES)
        subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
        subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','UBSAN_OPTIONS':'halt_on_error=1'})
    print('PASS H713-eMMC-only cfg and request refusal before DMA mapping')
    if a.mutations:
        init=definition(s,'sunxi_mmc_reinit_after_read_error')
        finish=definition(s,'sunxi_mmc_finish_manual_stop')
        refuse=definition(s,'sunxi_mmc_refuse_failed_recovery')
        scope=definition(s,'sunxi_mmc_needs_read_recovery')
        variants={
            'ignored reset error':s.replace(init,init.replace('if (ret)\n\t\treturn ret;','if (ret)\n\t\tret = 0;',1)),
            'ignored clock error':s.replace(init,init.replace('return host->ferror;','return 0;')),
            'ignored CMD12 error':s.replace(finish,finish.replace('ret = sunxi_mmc_send_manual_stop(host, mrq);','sunxi_mmc_send_manual_stop(host, mrq);')),
            'missing controller guard':s.replace(scope,scope.replace('host->cfg->recover_read_errors && ','',1)),
            'non-sticky refusal':s.replace(refuse,refuse.replace('READ_ONCE(host->recovery_error)','READ_ONCE(host->ferror)')),
            'uncleared request':s.replace(finish,finish.replace('host->manual_stop_mrq = NULL;','/* missing cleanup */')),
        }
        with tempfile.TemporaryDirectory(prefix='h713-recovery-mutations-') as directory:
            root=Path(directory);target=root/'drivers/mmc/host/sunxi-mmc.c'
            target.parent.mkdir(parents=True);(root/'include').symlink_to((a.kernel/'include').resolve())
            for name,variant in variants.items():
                assert variant!=s,name
                target.write_text(variant)
                result=subprocess.run(['python3',str(Path(__file__).resolve()),'--kernel',str(root)],capture_output=True,text=True)
                assert result.returncode!=0,'mutation survived: '+name
                print('CAUGHT '+name)


if __name__=='__main__':main()
