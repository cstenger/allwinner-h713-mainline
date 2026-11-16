#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Generate an opt-in bench-only patch for a prepared 0207 tree.

Never add the output to the production series. The diagnostics act only on
H713 DDR3 CMD18 reads wholly inside the pinned vendor-system LBA range.
It bypasses 0206 for at most 2048 selected read requests to seek the natural
full-FIFO failure under load.
Timing registers, writes and rootfs-sector requests are never modified.
"""
import argparse
import difflib
from pathlib import Path

CODE='''static unsigned int emmc_test_no_threshold;
module_param_named(emmc_test_no_threshold, emmc_test_no_threshold, uint, 0600);
static unsigned int emmc_test_bypassed;
module_param_named(emmc_test_bypassed, emmc_test_bypassed, uint, 0444);
static unsigned int emmc_test_recovered;
module_param_named(emmc_test_recovered, emmc_test_recovered, uint, 0444);

static bool sunxi_mmc_emmc_test_target(struct sunxi_mmc_host *host,
                                     struct mmc_request *mrq)
{
    return of_machine_is_compatible("cstenger,hy200-qz713df-a1") &&
           host->cfg->recover_read_errors && mrq->data &&
           mrq->data->flags == MMC_DATA_READ &&
           mrq->cmd->opcode == MMC_READ_MULTIPLE_BLOCK &&
           mrq->data->blksz == 512 && mrq->data->blocks &&
           mrq->data->blocks <= 4096 &&
           mrq->cmd->arg >= 599040 &&
           mrq->cmd->arg <= 4793344 - mrq->data->blocks;
}

'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();s=(a.kernel/'drivers/mmc/host/sunxi-mmc.c').read_text()
    assert 'static int sunxi_mmc_reinit_after_read_error(' in s
    assert 'emmc_test_no_threshold' not in s
    marker='/* Called in interrupt context! */\nstatic irqreturn_t sunxi_mmc_finalize_request'
    assert s.count(marker)==1
    new=s.replace(marker,CODE+marker,1)
    marker='\t\tsunxi_mmc_thld_ctl_emmc(host, data);'
    assert new.count(marker)==1
    new=new.replace(marker,marker+'''
        if (sunxi_mmc_emmc_test_target(host, mrq)) {
            unsigned int count = READ_ONCE(emmc_test_no_threshold);

            if (count && count <= 2048 &&
                cmpxchg(&emmc_test_no_threshold, count, count - 1) == count) {
                writel(0, host->reg_base + SDXC_REG_THLD);
                emmc_test_bypassed++;
            }
        }''',1)
    marker='\t\t\tdev_warn_ratelimited(mmc_dev(host->mmc),\n\t\t\t\t"read error: controller restored, CMD12 completed\\n");'
    assert new.count(marker)==1
    new=new.replace(marker,'\t\t\temmc_test_recovered++;\n'+marker,1)
    new=new.replace('"send stop command failed\\n");',
                    '"send stop command failed (RINT=%08x)\\n", ri);', 1)
    a.output.write_text(''.join(difflib.unified_diff(s.splitlines(True),new.splitlines(True),fromfile='a/drivers/mmc/host/sunxi-mmc.c',tofile='b/drivers/mmc/host/sunxi-mmc.c')))


if __name__=='__main__':main()
