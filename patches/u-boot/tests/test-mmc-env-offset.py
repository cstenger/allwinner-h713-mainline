#!/usr/bin/env python3
"""Compile actual mmc_offset() source with host stubs; no firmware execution."""
import argparse
from pathlib import Path
import subprocess
import tempfile

STUBS = r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
typedef int64_t s64;
typedef int32_t s32;
typedef uint32_t u32;
typedef int ofnode;
struct mmc { uint64_t capacity; };
#define __weak
#define IS_ENABLED(x) (x)
#define debug(...) ((void)0)
#define ENV_MMC_INVALID_OFFSET ((s64)-1)
static int node_valid, property_ok, partition_ok, guid_ok, hwpart;
static u32 property;
static const char *partition_name;
static const char *last_property;
static int partition_calls;
static ofnode ofnode_path(const char *s) { (void)s; return node_valid; }
static int ofnode_valid(ofnode n) { return n; }
static int ofnode_read_u32(ofnode n, const char *p, u32 *v) {
    (void)n; last_property=p; *v=property; return property_ok ? 0 : -1;
}
static int ofnode_conf_read_int(const char *p, int fallback) {
    last_property=p; return node_valid && property_ok ? (int)property : fallback;
}
static const char *ofnode_conf_read_str(const char *s) { (void)s; return partition_name; }
static int mmc_get_env_part(struct mmc *m) { (void)m; return hwpart; }
static int mmc_offset_try_partition(const char *s, int copy, s64 *v) {
    (void)copy; partition_calls++; *v = s ? 0x100000020LL : 0x100000040LL;
    return (s ? partition_ok : guid_ok) ? 0 : -1;
}
'''

# Each case runs the actual extracted branch with independently chosen config.
CASES = [
    ('missing node high absolute', {}, 'assert(mmc_offset(&m,0)==0x93d80000LL); assert(!mmc_get_env_addr(&m,0,&addr) && addr==0x93d80000U);'),
    ('missing property high absolute', {}, 'node_valid=1; assert(mmc_offset(&m,0)==0x93d80000LL); assert(!mmc_get_env_addr(&m,0,&addr) && addr==0x93d80000U);'),
    ('DT positive override', {}, 'node_valid=property_ok=1; property=4096; assert(mmc_offset(&m,0)==4096);'),
    ('DT negative override preserved', {}, 'node_valid=property_ok=1; property=0xffff0000; assert(mmc_offset(&m,0)==-65536);'),
    ('relative fallback', {'ENV_MMC_OFFSET': '(-65536LL)'}, 'assert(mmc_offset(&m,0)==-65536); m.capacity=0x80000000; assert(!mmc_get_env_addr(&m,0,&addr) && addr==0x7fff0000);'),
    ('invalid sentinel', {'ENV_MMC_OFFSET': '(-1LL)'}, 'assert(mmc_offset(&m,0)==-1); assert(mmc_get_env_addr(&m,0,&addr)==-ENOENT);'),
    ('redundant fallback', {'CONFIG_ENV_REDUNDANT': '1'}, 'assert(mmc_offset(&m,1)==0x93da0000LL);'),
    ('redundant property', {'CONFIG_ENV_REDUNDANT': '1'}, 'node_valid=property_ok=1; property=8192; assert(mmc_offset(&m,1)==8192); assert(!strcmp(last_property,"u-boot,mmc-env-offset-redundant"));'),
    ('named partition wins', {}, 'partition_name="env"; partition_ok=guid_ok=1; node_valid=property_ok=1; assert(mmc_offset(&m,0)==0x100000020LL); assert(partition_calls==1);'),
    ('GUID fallback wins', {}, 'partition_name="missing"; guid_ok=1; assert(mmc_offset(&m,0)==0x100000040LL); assert(partition_calls==2);'),
    ('hardware partition skips GUID', {}, 'hwpart=1; guid_ok=1; assert(mmc_offset(&m,0)==0x93d80000LL); assert(partition_calls==0);'),
    ('no OF control', {'OF_CONTROL': '0'}, 'assert(mmc_offset(&m,0)==0x93d80000LL);'),
    ('no OF redundant', {'OF_CONTROL': '0', 'CONFIG_ENV_REDUNDANT': '1'}, 'assert(mmc_offset(&m,1)==0x93da0000LL);'),
]


def run(source, out, allow_failures=False):
    start = source.index('static inline s64 mmc_offset(struct mmc *mmc, int copy)')
    end = source.index('static bool mmc_env_is_redundant_in_both_boot_hwparts', start)
    body = '#if OF_CONTROL\n' + source[start:end]
    address_start=source.index('__weak int mmc_get_env_addr(')
    address_end=source.index('#ifdef CONFIG_ENV_MMC_EMMC_HW_PARTITION',address_start)
    body+=source[address_start:address_end]
    failures=[]
    for number, (name, overrides, assertion) in enumerate(CASES):
        config = dict(OF_CONTROL='1', CONFIG_ENV_REDUNDANT='0',
                      CONFIG_ENV_MMC_EMMC_HW_PARTITION='0', CONFIG_PARTITION_TYPE_GUID='1',
                      ENV_MMC_OFFSET='0x93d80000LL', ENV_MMC_OFFSET_REDUND='0x93da0000LL')
        config.update(overrides)
        code = STUBS + '\n'.join(f'#define {k} {v}' for k,v in config.items()) + '\n'
        code += body + '\nint main(void) { struct mmc m={7818182656ULL}; u32 addr; ' + assertion + ' return 0; }\n'
        c = out / f'case-{number}.c'; binary = out / f'case-{number}'
        c.write_text(code)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter',
                        str(c), '-o', str(binary)], check=True, capture_output=True)
        result = subprocess.run([str(binary)], capture_output=True)
        if result.returncode:
            failures.append(name)
        elif not allow_failures:
            print('PASS', name)
    if failures and not allow_failures:
        raise ValueError(failures)
    return failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--mutations', action='store_true')
    args=parser.parse_args(); source=args.source.read_text()
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory)
        run(source,out)
        if args.mutations:
            variants = {
                'original narrowing': ('return defvalue;', 'return ofnode_conf_read_int(propname, defvalue);'),
                'cast narrowed fallback': ('return defvalue;', 'return (s64)(int)defvalue;'),
                'ignore DT overrides': ('return (s32)dt_offset;', 'return defvalue;'),
                'unsigned DT regression': ('return (s32)dt_offset;', 'return dt_offset;'),
                'redundant fallback wrong': ('defvalue = ENV_MMC_OFFSET_REDUND;', 'defvalue = ENV_MMC_OFFSET;'),
                'partition priority lost': ('if (!err)\n\t\t\treturn val;', 'if (!err)\n\t\t\treturn 0;'),
                'GUID used in boot hwpart': ('&& hwpart == 0', '&& hwpart >= 0'),
                'non-OF narrowed': ('return offset;', 'return (int)offset;'),
                'negative fallback lost': ('return defvalue;', 'return defvalue < 0 ? 0 : defvalue;'),
            }
            killed=set()
            for name,(before,after) in variants.items():
                assert before in source,name
                failures=run(source.replace(before,after),out,True)
                assert failures,name
                killed.update(failures)
                print('CAUGHT',name,':',', '.join(failures))
            assert killed=={case[0] for case in CASES},'a source case never failed under mutation'
            print('PASS all 9 source mutations caught; every one of the 13 cases fails under a relevant mutation')


if __name__=='__main__':
    main()
