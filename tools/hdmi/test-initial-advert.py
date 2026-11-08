#!/usr/bin/env python3
"""Execute the actual owner initial-release function with faulted SCP readbacks."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class InitialRelease(unittest.TestCase):
    def test_initial_disabled_hold_then_settle_and_release_faults(self):
        source = (ROOT / 'modules/hdmi-signal/h713-hdmi-signal.c').read_text()
        function = 'static int initial_advertise(void)' + source.split(
            'static int initial_advertise(void)', 1)[1].split('\n}\n', 1)[0] + '\n}\n'
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#define MARKER_OFFSET 0x4f00
#define EDID_META_OFFSET 0x4a80
#define EDID_RELEASE_HPD_OFFSET 120
#define EDID_RELEASE_DDC_OFFSET 124
#define EDID_REQ_RELEASE 4
#define EDID_REQ_DDC_ON 3
#define EDID_INITIAL_DDC_HOLD_MS 2000
#define pr_info(...) ((void)0)
static unsigned char storage[0x5000];
static void *sram = storage;
static int slept, requests, fault;
static unsigned int readl(const void *p) { unsigned int x; memcpy(&x,p,4); return x; }
static void writel(unsigned int x, void *p) { memcpy(p,&x,4); }
static unsigned int marker(unsigned int off) { return readl(storage+MARKER_OFFSET+off); }
static void set(unsigned int off,unsigned int value) { writel(value,storage+MARKER_OFFSET+off); }
static void msleep(int ms) {
 assert((ms == 2000 && !requests && !slept) || (ms == 100 && requests == 1 && slept == 2000));
 slept += ms;
}
static int scp_request(unsigned int command)
{
 if (!requests) {
  assert(command == EDID_REQ_DDC_ON && slept == 2000); requests++;
  if (fault == 1) return -EIO;
  if (fault != 2) set(124,0x07000007);
  if (fault == 3) set(12,1);
 } else {
  assert(command == EDID_REQ_RELEASE && requests == 1 && slept == 2100); requests++;
  if (fault == 4) return -EIO;
  if (fault != 5) set(120,0x1000);
  if (fault != 6) set(124,0x07000007);
  if (fault == 7) set(24,1);
 }
 return 0;
}
FUNCTION
int main(void) {
 for (fault=0; fault<=7; ++fault) {
  memset(storage,0,sizeof storage); slept=requests=0;
  writel(0x1007,storage+EDID_META_OFFSET); set(36,0x1007); set(44,0x07000000);
  int result=initial_advertise();
  assert(requests == (fault >= 1 && fault <= 3 ? 1 : 2));
  assert(fault ? result == -EIO : result == 0);
 }
 for (int bad=0; bad<3; ++bad) {
  memset(storage,0,sizeof storage); slept=requests=0;
  set(36,bad == 0 ? 0 : 7); set(44,bad == 1 ? 7 : bad == 2 ? ~0U : 0);
  assert(initial_advertise() == -EIO && !slept && !requests);
 }
 puts("PASS disabled hold, DDC-on, settle, one release and stage failures");
}
'''.replace('FUNCTION', function)
        with tempfile.TemporaryDirectory() as directory:
            c = Path(directory) / 'test.c'
            binary = Path(directory) / 'test'
            c.write_text(harness)
            subprocess.run(['clang', '-O2', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_settle_single_release_and_faults(self):
        source = (ROOT / 'modules/hdmi-signal/h713-hdmi-signal.c').read_text()
        function = 'static int initial_advertise(void)' + source.split(
            'static int initial_advertise(void)', 1)[1].split('\n}\n', 1)[0] + '\n}\n'
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#define MARKER_OFFSET 0x4f00
#define EDID_META_OFFSET 0x4a80
#define EDID_RELEASE_HPD_OFFSET 120
#define EDID_RELEASE_DDC_OFFSET 124
#define EDID_REQ_RELEASE 4
#define pr_info(...) ((void)0)
static unsigned char storage[0x5000];
static void *sram = storage;
static int slept, requests, fault;
static unsigned int readl(const void *p) { unsigned int x; memcpy(&x,p,4); return x; }
static void writel(unsigned int x, void *p) { memcpy(p,&x,4); }
static unsigned int marker(unsigned int off) { return readl(storage+MARKER_OFFSET+off); }
static void set(unsigned int off,unsigned int value) { writel(value,storage+MARKER_OFFSET+off); }
static void msleep(int ms) { assert(!requests && ms == 100); slept += ms; }
static int scp_request(unsigned int command)
{
 assert(slept == 100 && command == EDID_REQ_RELEASE && !requests++);
 if (fault == 1) return -EIO;
 if (fault != 2) set(120,0x1000);
 if (fault != 3) set(124,0x07000007);
 if (fault == 4) set(12,1);
 if (fault == 5) set(24,1);
 return 0;
}
FUNCTION
int main(void)
{
 for (fault=0; fault<=5; ++fault) {
  memset(storage,0,sizeof storage); slept=requests=0;
  writel(0x1007,storage+EDID_META_OFFSET); set(36,0x1007); set(44,0x07000007);
  int result=initial_advertise();
  assert(requests == 1 && slept == 100);
  assert(fault ? result == -EIO : result == 0);
 }
 for (int bad=0; bad<3; ++bad) {
  memset(storage,0,sizeof storage); slept=requests=0;
  set(36,bad == 0 ? 0 : 7); set(44,bad == 1 ? 0 : bad == 2 ? ~0U : 7);
  assert(initial_advertise() == -EIO && !slept && !requests);
 }
 puts("PASS single settled first release and all SCP/readback failures");
}
'''.replace('FUNCTION', function)
        with tempfile.TemporaryDirectory() as directory:
            c = Path(directory) / 'test.c'
            binary = Path(directory) / 'test'
            c.write_text(harness)
            subprocess.run(['clang', '-O2', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
