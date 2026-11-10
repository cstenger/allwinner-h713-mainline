#!/usr/bin/env python3
"""Run the real diagnostic setter with failing SCP stages, without hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class Owner(unittest.TestCase):
    def test_real_cycle_setter(self):
        source = (Path(__file__).resolve().parents[2] / 'modules/hdmi-signal/h713-hdmi-signal.c').read_text()
        name = 'static int cycle_ddc(const char *value, const struct kernel_param *kp)'
        function = name + source.split(name, 1)[1].split('\n}\n', 1)[0] + '\n}\n'
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned int u32;
struct kernel_param { int ignored; };
#define MARKER_OFFSET 0x4f00
#define EDID_META_OFFSET 0x4a80
#define EDID_RELEASE_HPD_OFFSET 120
#define EDID_RELEASE_DDC_OFFSET 124
#define EDID_REQ_DDC_OFF 5
#define EDID_REQ_DDC_ON 3
#define mutex_lock(x) ((void)(x))
#define mutex_unlock(x) ((void)(x))
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
static int signal_lock;
static unsigned char storage[0x5000];
static void *sram = storage;
static bool ready,failed,restored,terminal;
static unsigned int ddc_cycles,readvertised;
static int requests,slept,fault;
static unsigned int readl(const void *p) { unsigned int x; memcpy(&x,p,4); return x; }
static void writel(unsigned int x, void *p) { memcpy(p,&x,4); }
static unsigned int marker(unsigned int off) { return readl(storage+MARKER_OFFSET+off); }
static void set(unsigned int off,unsigned int value) { writel(value,storage+MARKER_OFFSET+off); }
static int kstrtouint(const char *s,unsigned int base,unsigned int *out) {
 char *end; unsigned long v=strtoul(s,&end,base);
 if (end == s || (*end && *end != '\n') || v > 0xffffffffUL) return -EINVAL;
 *out=v; return 0;
}
static void msleep(unsigned int ms) {
 assert((ms == 2000 && requests == 1) || (ms == 100 && requests == 2)); slept+=ms;
}
static int scp_request(unsigned int command) {
 if (!requests) {
  assert(command == 5 && !slept); requests++;
  if (fault == 1) return -EIO;
  if (fault != 2) set(120,0);
  if (fault != 3) set(124,0x07000000);
  if (fault == 4) set(12,1);
 } else {
  assert(command == 3 && requests == 1 && slept == 2000); requests++;
  if (fault == 5) return -EIO;
  if (fault != 6) set(120,0);
  if (fault != 7) set(124,0x07000007);
  if (fault == 8) set(24,1);
 }
 return 0;
}
FUNCTION
static void reset(void) {
 memset(storage,0,sizeof storage); slept=requests=0;
 ready=true; failed=restored=terminal=false; ddc_cycles=readvertised=0;
 writel(7,storage+EDID_META_OFFSET); set(44,0x07000007);
}
int main(void) {
 for (fault=0; fault<=8; ++fault) {
  reset(); int result=cycle_ddc("2000",NULL);
  assert(ready && !restored && !readvertised);
  if (!fault) assert(!result && ddc_cycles == 1 && !failed && !terminal && slept == 2100);
  else assert(result == -EIO && !ddc_cycles && failed && terminal);
  int before=requests;
  assert(cycle_ddc("2000",NULL) == -EPERM && requests == before);
 }
 reset(); assert(cycle_ddc("100",NULL) == -EINVAL && !requests);
 reset(); assert(cycle_ddc("invalid",NULL) == -EINVAL && !requests);
 reset(); ready=false; assert(cycle_ddc("2000",NULL) == -EPERM && !requests);
 reset(); restored=true; assert(cycle_ddc("2000",NULL) == -EPERM && !requests);
 reset(); readvertised=1; assert(cycle_ddc("2000",NULL) == -EPERM && !requests);
 puts("PASS actual DDC setter, separate counts, one-shot gates and terminal stage failures");
}
'''.replace('FUNCTION', function)
        with tempfile.TemporaryDirectory() as directory:
            c = Path(directory) / 'test.c'
            binary = Path(directory) / 'test'
            c.write_text(harness)
            subprocess.run(['clang', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                            str(c), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__': unittest.main()
