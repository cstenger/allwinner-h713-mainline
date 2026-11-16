#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compile actual prepared threshold helpers with MMIO stubs and sanitizers."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def definition(source, name):
    start = source.index('static void '+name+'(')
    brace = source.index('{', start)
    end, depth = brace+1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


STUB = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#define BIT(n) (1U<<(n))
#define GENMASK(h,l) ((~0U>>(31-(h))) & (~0U<<(l)))
struct sunxi_mmc_cfg { bool v5p3x, emmc_read_threshold; };
struct mmc_host { struct { unsigned char timing; } ios; };
struct mmc_data { unsigned int flags, blksz; };
struct sunxi_mmc_host { const struct sunxi_mmc_cfg *cfg; struct mmc_host *mmc; unsigned char *reg_base; };
static unsigned char registers[4096];
static u32 regval; static int reads, writes;
static u32 readl(void *p) { assert(p==registers+SDXC_REG_THLD); reads++; return regval; }
static void writel(u32 value, void *p) { assert(p==registers+SDXC_REG_THLD); writes++; regval=value; }
'''
CASES = r'''
int main(void) {
    const u32 saved[] = {0, 0xffffffff, 0xa5a5a5a5};
    const unsigned sizes[] = {0,1,64,511,512,513,1024,4095,4096};
    struct mmc_host mmc = {0}; struct mmc_data data;
    struct sunxi_mmc_cfg cfg;
    struct sunxi_mmc_host host = {.cfg=&cfg, .mmc=&mmc, .reg_base=registers};
    unsigned cases=0;
    for (unsigned device=0;device<3;device++)
    for (unsigned timing=0;timing<=16;timing++)
    for (unsigned direction=0;direction<2;direction++)
    for (unsigned size=0;size<sizeof sizes/sizeof *sizes;size++)
    for (unsigned prior=0;prior<sizeof saved/sizeof *saved;prior++) {
        cfg.v5p3x=device==1; cfg.emmc_read_threshold=device==0;
        mmc.ios.timing=timing; data.flags=direction?MMC_DATA_READ:MMC_DATA_WRITE;
        data.blksz=sizes[size]; regval=saved[prior]; reads=writes=0;
        sunxi_mmc_thld_ctl_v5p3x(&host,&data);
        sunxi_mmc_thld_ctl_emmc(&host,&data);
        u32 expected=saved[prior];
        if (device<2) {
            expected &= ~(SDXC_THLD_SIZE_MASK|SDXC_THLD_READ_EN);
            bool enable = direction && (device==0 ?
                (data.blksz>0 && data.blksz<=512 &&
                 (timing==MMC_TIMING_MMC_HS200 || timing==MMC_TIMING_MMC_HS400)) :
                (data.blksz<=1024 &&
                 (timing==MMC_TIMING_UHS_SDR50 || timing==MMC_TIMING_UHS_SDR104 || timing==MMC_TIMING_MMC_HS200)));
            if (enable) expected |= (data.blksz<<16)|SDXC_THLD_READ_EN;
            assert(reads==1 && writes==1);
        } else assert(reads==0 && writes==0);
        assert(regval==expected); cases++;
    }
    /* Sticky READ -> WRITE and HS400 -> legacy transitions must clear it. */
    cfg.v5p3x=false;cfg.emmc_read_threshold=true;data.flags=MMC_DATA_READ;
    data.blksz=512;mmc.ios.timing=MMC_TIMING_MMC_HS400;regval=4;
    sunxi_mmc_thld_ctl_emmc(&host,&data);assert(regval==0x02000005);
    data.flags=MMC_DATA_WRITE;sunxi_mmc_thld_ctl_emmc(&host,&data);assert(regval==4);
    data.flags=MMC_DATA_READ;sunxi_mmc_thld_ctl_emmc(&host,&data);assert(regval==0x02000005);
    mmc.ios.timing=MMC_TIMING_LEGACY;sunxi_mmc_thld_ctl_emmc(&host,&data);assert(regval==4);
    printf("PASS %u timing/direction/size/prior-register/device cases, sticky-state clearing and unrelated-bit preservation\n",cases);
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel',type=Path,required=True);a=p.parse_args()
    source=(a.kernel/'drivers/mmc/host/sunxi-mmc.c').read_text()
    configs=re.findall(r'static const struct sunxi_mmc_cfg (\w+) = \{(.*?)\n\};',source,re.S)
    opted=[name for name,body in configs if re.search(r'\.emmc_read_threshold\s*=\s*true',body)]
    assert opted==['sun50i_h713_emmc_cfg'], opted
    request=definition(source,'sunxi_mmc_request')
    block=request[request.index('if (data) {',request.index('spin_lock_irqsave')):]
    assert block.index('sunxi_mmc_thld_ctl_emmc(host, data);') < block.index('sunxi_mmc_start_dma(host, data);')
    headers=source+'\n'+(a.kernel/'include/linux/mmc/core.h').read_text()+'\n'+(a.kernel/'include/linux/mmc/host.h').read_text()
    names=('SDXC_REG_THLD','SDXC_THLD_SIZE_MASK','SDXC_THLD_READ_EN','MMC_DATA_READ','MMC_DATA_WRITE')
    constants=[]
    for line in headers.splitlines():
        if re.match(r'#define\s+(?:'+ '|'.join(names)+r'|MMC_TIMING_\w+)\s+',line):
            if line.split()[1]=='MMC_TIMING_MAX':continue
            constants.append(line)
    code='\n'.join(constants)+'\n'+STUB+'\n'+definition(source,'sunxi_mmc_thld_ctl_v5p3x')+'\n'+definition(source,'sunxi_mmc_thld_ctl_emmc')+CASES
    with tempfile.TemporaryDirectory(prefix='h713-emmc-test-') as directory:
        path=Path(directory);(path/'test.c').write_text(code)
        subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
        subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
    print('PASS H713-eMMC-only cfg and threshold programming before DMA')


if __name__=='__main__':main()
