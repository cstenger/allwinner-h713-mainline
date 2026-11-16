#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check the generated diagnostic's sector, command, direction and board gates."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('generator',HERE/'make-emmc-recovery-diagnostic.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
CODE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define module_param_named(...)
#define MMC_DATA_READ 512
#define MMC_DATA_WRITE 256
#define MMC_READ_MULTIPLE_BLOCK 18
static bool board=true;
static bool of_machine_is_compatible(const char*s){return board;}
struct mmc_data { unsigned flags,blksz,blocks; };
struct mmc_command { unsigned opcode,arg; };
struct mmc_request { struct mmc_data *data;struct mmc_command *cmd; };
struct sunxi_mmc_cfg { bool recover_read_errors; };
struct sunxi_mmc_host { struct sunxi_mmc_cfg *cfg; };
'''
CASES=r'''
int main(void){
 struct sunxi_mmc_cfg cfg={true};struct sunxi_mmc_host host={&cfg};
 struct mmc_command cmd={18,599040};struct mmc_data data={MMC_DATA_READ,512,1};struct mmc_request req={&data,&cmd};
 assert(sunxi_mmc_emmc_test_target(&host,&req));
 cmd.arg=599039;assert(!sunxi_mmc_emmc_test_target(&host,&req));
 cmd.arg=4793343;assert(sunxi_mmc_emmc_test_target(&host,&req));
 cmd.arg=4793344;assert(!sunxi_mmc_emmc_test_target(&host,&req));
 cmd.arg=0xffffffff;assert(!sunxi_mmc_emmc_test_target(&host,&req));
 cmd.arg=599040;data.blocks=4096;assert(sunxi_mmc_emmc_test_target(&host,&req));
 data.blocks=4097;assert(!sunxi_mmc_emmc_test_target(&host,&req));
 data.blocks=0;assert(!sunxi_mmc_emmc_test_target(&host,&req));data.blocks=1;
 for(unsigned i=0;i<5;i++){
   unsigned sectors[]={0,599039,4793344,5600000,0xffffffff};cmd.arg=sectors[i];
   assert(!sunxi_mmc_emmc_test_target(&host,&req));
 }
 cmd.arg=599040;data.flags=MMC_DATA_WRITE;assert(!sunxi_mmc_emmc_test_target(&host,&req));
 data.flags=MMC_DATA_READ|MMC_DATA_WRITE;assert(!sunxi_mmc_emmc_test_target(&host,&req));data.flags=MMC_DATA_READ;
 data.blksz=1024;assert(!sunxi_mmc_emmc_test_target(&host,&req));data.blksz=512;
 cmd.opcode=17;assert(!sunxi_mmc_emmc_test_target(&host,&req));cmd.opcode=53;assert(!sunxi_mmc_emmc_test_target(&host,&req));cmd.opcode=18;
 board=false;assert(!sunxi_mmc_emmc_test_target(&host,&req));board=true;
 cfg.recover_read_errors=false;assert(!sunxi_mmc_emmc_test_target(&host,&req));cfg.recover_read_errors=true;
 req.data=0;assert(!sunxi_mmc_emmc_test_target(&host,&req));
 puts("PASS diagnostic gates: board/controller, CMD18/read-only, exact vendor LBA bounds, sizes and missing data");
}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--kernel',type=Path,required=True);a=p.parse_args()
 source=a.kernel/'drivers/mmc/host/sunxi-mmc.c';original=source.read_bytes()
 with tempfile.TemporaryDirectory(prefix='h713-recovery-diag-') as directory:
  root=Path(directory);patch=root/'diagnostic.patch'
  subprocess.run(['python3',str(HERE/'make-emmc-recovery-diagnostic.py'),'--kernel',str(a.kernel),'--output',str(patch)],check=True)
  assert source.read_bytes()==original
  target=root/'drivers/mmc/host/sunxi-mmc.c';target.parent.mkdir(parents=True);target.write_bytes(original)
  subprocess.run(['patch','--batch','--fuzz=0','-p1','-d',str(root),'-i',str(patch)],check=True,capture_output=True)
  changed=target.read_text();assert changed.count('sunxi_mmc_emmc_test_target(host, mrq)')==1
  assert 'count && count <= 2048' in changed and 'emmc_test_error' not in changed
  (root/'test.c').write_text(CODE+g.CODE+CASES)
  subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined',str(root/'test.c'),'-o',str(root/'test')],check=True)
  subprocess.run([str(root/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','UBSAN_OPTIONS':'halt_on_error=1'})

if __name__=='__main__':main()
