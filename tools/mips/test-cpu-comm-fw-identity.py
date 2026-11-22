#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Run the driver's display-firmware identification against real images.

Extracts cc_fw_identify() and its helpers from a prepared kernel tree (kernel
0220), compiles them with ASan/UBSan, and backs ioremap() with a fake DRAM
window holding a firmware image at its load address (KSEG 0x8b100000 = ARM
0x4b100000). Each case runs in its own process, because a match is cached.

  - the A1 image (4380f1b3) is the A1 entry and the V2 image (16c74a28) the
    V2 entry; each entry's channel-table pointer and elog addresses follow;
  - empty DRAM, and the stock Android build when given, are unknown;
  - the V2 image with one word of its dev-pointer site changed is unknown, as
    is the V2 image with getCurCPUID changed: the guard refuses rather than
    falling back.

    tools/mips/test-cpu-comm-fw-identity.py --kernel build/linux-6.18.38-<digest> \\
        --a1 A1/display.bin --v2 V2/display.bin [--other STOCK/display.bin]
"""
import argparse
import os
import shutil
import subprocess
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

h = SourceFileLoader('handoff', str(Path(__file__).with_name('test-cpu-comm-handoff.py'))).load_module()

STUBS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
typedef int16_t s16; typedef int32_t s32; typedef uint64_t phys_addr_t;
#define __iomem
#define ENOMEM 12
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define pr_info(...) printf(__VA_ARGS__)
#define pr_err(...) printf(__VA_ARGS__)
#define DRAM_BASE 0x4b000000ull
#define DRAM_SIZE 0x01000000ull
static unsigned char *dram;
static void *ioremap(phys_addr_t p, size_t n)
{
	if (p < DRAM_BASE || p + n > DRAM_BASE + DRAM_SIZE) abort();
	return dram + (p - DRAM_BASE);
}
static void iounmap(void *p) { (void)p; }
static u32 readl(const void *p) { u32 v; memcpy(&v, p, 4); return v; }
'''

TEST = r'''
int main(int argc, char **argv)
{
	const struct cc_fw_build *fw;
	dram = calloc(1, DRAM_SIZE);
	if (strcmp(argv[1], "-")) {
		FILE *f = fopen(argv[1], "rb");
		size_t n = fread(dram + 0x100000, 1, DRAM_SIZE - 0x100000, f);
		fclose(f);
		if (n < 0x100000) return 2;	/* a 1.2 MiB image */
	}
	if (argc > 3) {	/* corrupt one word: KSEG address */
		u32 a = strtoul(argv[3], 0, 16);
		dram[(a & 0x1fffffff) + 0x40000000 - DRAM_BASE] ^= 0x01;
	}
	fw = cc_fw_identify();
	if (!fw) {
		if (cc_fw_identify()) return 3;	/* a miss is not cached as a hit */
		printf("RESULT NULL\n");
		return strcmp(argv[2], "NULL") ? 1 : 0;
	}
	if (cc_fw_identify() != fw) return 4;	/* a hit is cached */
	printf("RESULT %s dev_ptr=%08x elog_mode=%08x\n", fw->name, fw->dev_ptr, fw->elog_mode);
	return strcmp(argv[2], fw->name) ? 1 : 0;
}
'''

def struct(source, name):
    start = source.index('struct ' + name + ' {')
    return source[start:source.index('};', start) + 2]


FUNCTIONS = ('phys_addr_t cc_kseg_to_phys(', 'int cc_fw_read(', 'int cc_fw_readb(',
             'static u32 cc_fw_pair_addr(', 'static bool cc_fw_site_matches(',
             'static bool cc_fw_build_matches(', 'const struct cc_fw_build *cc_fw_identify(')


def source(kernel):
    d = kernel / 'drivers/soc/sunxi/cpu_comm'
    hdr = (d / 'cpu_comm.h').read_text()
    proto = (d / 'cpu_comm_proto.c').read_text()
    structs = struct(hdr, 'cc_fw_site') + '\n' + struct(hdr, 'cc_fw_build') + '\n'
    defines = ''.join(l + '\n' for l in proto.splitlines()
                      if l.startswith(('#define CC_FW_SELFTEST_W0', '#define CC_FW_SELFTEST_W1')))
    assert defines.count('#define') == 2, 'self-test words not found'
    start = proto.index('static const struct cc_fw_build cc_fw_builds[]')
    table = proto[start:proto.index('};', start) + 2] + '\n'
    return STUBS + structs + defines + table + '\n'.join(h.function(proto, f) for f in FUNCTIONS) + TEST


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--a1', type=Path, required=True)
    p.add_argument('--v2', type=Path, required=True)
    p.add_argument('--other', type=Path, help='a build that must be unknown (e.g. stock Android)')
    a = p.parse_args()

    a1, v2 = 'A1 display.bin 4380f1b3', 'V2 display.bin 16c74a28'
    cases = [
        ('A1 image', [str(a.a1), a1]),
        ('V2 image', [str(a.v2), v2]),
        ('empty DRAM', ['-', 'NULL']),
        ('V2, dev_ref word changed', [str(a.v2), 'NULL', '8b11e678']),
        ('V2, getCurCPUID changed', [str(a.v2), 'NULL', '8b122688']),
        ('V2, elog_ref word changed', [str(a.v2), 'NULL', '8b1513a0']),
        ('A1, dev_ref word changed', [str(a.a1), 'NULL', '8b11e7a4']),
    ]
    if a.other:
        cases.append(('other build', [str(a.other), 'NULL']))

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / 'test.c').write_text(source(a.kernel))
        cc = shutil.which('clang') or 'cc'
        subprocess.run([cc, '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        str(t / 'test.c'), '-o', str(t / 'test')], check=True)
        failed = 0
        for name, args in cases:
            r = subprocess.run([str(t / 'test'), *args], capture_output=True, text=True, timeout=30,
                               env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
            result = [l for l in r.stdout.splitlines() if l.startswith('RESULT')]
            ok = r.returncode == 0
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {name}: {result[-1] if result else r.stdout.strip()}"
                  + ('' if ok else f'  (exit {r.returncode}) {r.stderr.strip()[:300]}'))
        if failed:
            raise SystemExit(f'{failed} case(s) failed')
        print('PASS display firmware identity: both builds recognised, unknown and corrupted images refused')


if __name__ == '__main__':
    main()
