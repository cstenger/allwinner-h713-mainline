#!/usr/bin/env python3
"""Compile and execute the actual DSP lock header against a fake MMIO bus."""
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=r'''
#include <stdint.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;
#define __iomem
static u32 words[2];
static int reads, writes, phase, mode;
static u32 readl(void *p) {
 if (p == &words[0]) {
  ++reads;
  if (mode == 1 && reads == 3) words[0] = 0;
  if (mode == 2 && phase && reads == 4) words[0] = 0;
 }
 return *(u32 *)p;
}
static void writel(u32 value, void *p) {
 assert(p == &words[1]); assert(value == 0x55 || value == 0xaa); ++writes;
 if (value == 0x55) {
  phase = 1;
  if (mode == 2 || mode == 3) words[0] = 0x55;
  if (mode == 4) return;
 }
 if (value == 0xaa && mode == 5) return;
 *(u32 *)p = value;
}
#define readl_poll_timeout(p, value, condition, delay, timeout) ({ \
 int err = -ETIMEDOUT; \
 for (int poll = 0; poll < 32; ++poll) { \
  value = readl(p); if (condition) {err = 0; break;} \
 } err; })
#include "h713-dsp-lock.h"
static void reset(int m, u32 peer, u32 own) {
 mode=m; words[0]=peer; words[1]=own; reads=writes=phase=0;
}
int main(void) {
 struct h713_dsp_lock lock = {&words[0], &words[1]};
 reset(0,0,0xaa); assert(!h713_dsp_claim(&lock)); assert(words[1]==0x55);
 assert(!h713_dsp_release(&lock)); assert(words[1]==0xaa && words[0]==0 && writes==2);
 reset(1,0x55,0xaa); assert(!h713_dsp_claim(&lock)); assert(reads>=3); assert(!h713_dsp_release(&lock));
 reset(2,0,0xaa); assert(!h713_dsp_claim(&lock)); assert(reads>=4); assert(!h713_dsp_release(&lock));
 reset(0,0x55,0xaa); assert(h713_dsp_claim(&lock)==-ETIMEDOUT && writes==0);
 reset(3,0,0xaa); assert(h713_dsp_claim(&lock)==-ETIMEDOUT && words[1]==0xaa && writes==2);
 reset(0,0,0x55); assert(h713_dsp_claim(&lock)==-EBUSY && writes==0);
 reset(4,0,0xaa); assert(h713_dsp_claim(&lock)==-EIO && words[1]==0xaa && writes==2);
 reset(5,0,0xaa); assert(!h713_dsp_claim(&lock)); assert(h713_dsp_release(&lock)==-EIO);
 reset(0,0,0xaa); for(int i=0;i<1000;++i) {assert(!h713_dsp_claim(&lock));assert(!h713_dsp_release(&lock));}
 assert(words[0]==0 && words[1]==0xaa && writes==2000);
 puts("PASS: idle/contended/racing peer, both timeouts, stale ARM claim, latch failures, 1000 cycles; writes only to ARM lock word");
}
'''
Path('/tmp/h713-dsp-lock-test.c').write_text(source)
subprocess.run(['clang','-Wall','-Wextra','-Werror','-I',str(root/'modules/hdmi-dsp-probe'),'/tmp/h713-dsp-lock-test.c','-o','/tmp/h713-dsp-lock-test'],check=True)
subprocess.run(['/tmp/h713-dsp-lock-test'],check=True)
