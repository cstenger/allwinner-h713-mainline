#!/usr/bin/env python3
"""Compile actual native save/export/device routines against a fake MMC host image."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

HEADER=r'''
#define _FILE_OFFSET_BITS 64
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <zlib.h>
typedef int64_t s64; typedef int32_t s32; typedef uint32_t u32;
typedef unsigned int uint; typedef unsigned char u_char; typedef int ofnode;
#define __weak
#define CONFIG_ENV_SIZE 65536
#define ENV_SIZE 65532
#define ENV_MMC_OFFSET 0x93d80000LL
#define ENV_MMC_OFFSET_REDUND (-1LL)
#define ENV_MMC_INVALID_OFFSET (-1LL)
#define CONFIG_ENV_REDUNDANT 0
#define CONFIG_PARTITION_TYPE_GUID 0
#define CONFIG_ENV_MMC_EMMC_HW_PARTITION 0
#define CONFIG_ENV_MMC_DEVICE_INDEX 0
#define OF_CONTROL 1
#define IS_ENABLED(x) (x)
#define debug(...) ((void)0)
#define pr_err(...) fprintf(stderr,__VA_ARGS__)
#define ALIGN(x,a) (((x)+(a)-1)&~((a)-1))
#define ALLOC_CACHE_ALIGN_BUFFER(t,n,c) t n[c]
#define BOOT_DEVICE_MMC1 1
#define BOOT_DEVICE_MMC2 2
#define ENV_VALID 1
#define ENV_REDUND 2
typedef struct { uint32_t crc; unsigned char data[ENV_SIZE]; } env_t;
_Static_assert(sizeof(env_t)==65536,"nonredundant environment layout");
struct mmc { uint64_t capacity; uint write_bl_len; };
struct blk_desc { int dev; };
static struct mmc model={7818182656ULL,512};
static struct blk_desc descriptor;
static struct { int env_valid; } global_data={ENV_VALID};
#define gd (&global_data)
static int boot_device, image_fd, calls, init_calls, fini_calls, export_calls;
static int selected_dev=-1;
static unsigned long written_start,written_count,written_bytes;
static const char *mode;
static unsigned char serialized[ENV_SIZE];
static int env_htab;
static int sunxi_get_boot_device(void) { return boot_device; }
static ofnode ofnode_path(const char *s) { (void)s; return strcmp(mode,"node-no-prop")==0 || strcmp(mode,"offset-invalid")==0; }
static int ofnode_valid(ofnode n) { return n; }
static int ofnode_read_u32(ofnode n,const char *s,u32 *v) { (void)n;(void)s;*v=0xffffffff;return strcmp(mode,"offset-invalid")==0 ? 0 : -1; }
static int ofnode_conf_read_int(const char *s,int fallback) { (void)s;return fallback; }
static const char *ofnode_conf_read_str(const char *s) { (void)s;return NULL; }
static int mmc_get_env_part(struct mmc *m) { (void)m;return 0; }
static int mmc_offset_try_partition(const char *s,int c,s64 *v) { (void)s;(void)c;(void)v;return -1; }
static struct mmc *find_mmc_device(int dev) { selected_dev=dev;descriptor.dev=dev;return &model; }
static const char *init_mmc_for_env(struct mmc *m) { (void)m;init_calls++;return strcmp(mode,"init-fail")==0 ? "mock init failure" : NULL; }
static void fini_mmc_for_env(struct mmc *m) { (void)m;fini_calls++; }
static int mmc_env_is_redundant_in_both_boot_hwparts(struct mmc *m) { (void)m;return 0; }
static int mmc_set_env_part(struct mmc *m,int p) { (void)m;(void)p;return 0; }
static struct blk_desc *mmc_get_blk_desc(struct mmc *m) { (void)m;return &descriptor; }
static uint blk_dwrite(struct blk_desc *d,uint start,uint count,const unsigned char *buffer) {
    (void)d;calls++;written_start=start;written_count=count;
    assert(count<=128);
    uint n=strcmp(mode,"short")==0 ? count/2 : strcmp(mode,"zero")==0 ? 0 : count;
    if(n) { ssize_t result=pwrite(image_fd,buffer,n*512,(off_t)start*512);assert(result==(ssize_t)n*512);written_bytes=result; }
    return n;
}
static ssize_t hexport_r(void *h,char sep,int flags,char **buffer,size_t size,int argc,void *argv) {
    (void)h;(void)sep;(void)flags;(void)argc;(void)argv;export_calls++;
    if(strcmp(mode,"export-fail")==0) { errno=ENOSPC;return -1; }
    assert(size==ENV_SIZE);memcpy(*buffer,serialized,ENV_SIZE);return ENV_SIZE;
}
int env_export(env_t *out);
'''

MAIN=r'''
int main(int argc,char **argv) {
    assert(argc==5); mode=argv[3];boot_device=atoi(argv[4]);
    image_fd=open(argv[1],O_RDWR|O_NOFOLLOW);assert(image_fd>=0);
    struct stat s;assert(fstat(image_fd,&s)==0 && S_ISREG(s.st_mode) && s.st_size==7818182656LL);
    int input=open(argv[2],O_RDONLY|O_NOFOLLOW);assert(input>=0);
    assert(fstat(input,&s)==0 && S_ISREG(s.st_mode) && s.st_size==65536);
    assert(pread(input,serialized,ENV_SIZE,4)==ENV_SIZE);close(input);
    int rc=env_mmc_save();assert(fsync(image_fd)==0);close(image_fd);
    printf("\n{\"rc\":%d,\"device\":%d,\"calls\":%d,\"lba\":%lu,\"count\":%lu,\"bytes\":%lu,\"init\":%d,\"fini\":%d,\"exports\":%d}\n",
      rc,selected_dev,calls,written_start,written_count,written_bytes,init_calls,fini_calls,export_calls);
    return 0;
}
'''


def code(mmc,common,board):
    start=mmc.index('static inline s64 mmc_offset(struct mmc *mmc, int copy)')
    end=mmc.index('static bool mmc_env_is_redundant_in_both_boot_hwparts',start)
    offsets='#if OF_CONTROL\n'+mmc[start:end]
    start=mmc.index('__weak int mmc_get_env_addr(');end=mmc.index('#ifdef CONFIG_ENV_MMC_EMMC_HW_PARTITION',start)
    offsets+=mmc[start:end]
    start=mmc.index('static inline int write_env(');end=mmc.index('static inline int erase_env(',start)
    save=mmc[start:end]
    start=common.index('int env_export(env_t *env_out)');end=common.index('void env_relocate(',start)
    export=common[start:end]
    start=board.index('int mmc_get_env_dev(void)');end=board.index('\n#endif',start)
    device=board[start:end]
    return '\n'.join([HEADER,device,offsets,save,'#undef CONFIG_ENV_REDUNDANT',export,MAIN])


CASES=[('good',2,0,1,1,1),('node-no-prop',2,0,1,1,1),('init-fail',2,1,0,0,0),
       ('export-fail',2,1,0,1,1),('offset-invalid',2,1,0,1,1),
       ('short',2,1,1,1,1),('zero',2,1,1,1,1),('good',1,0,1,1,1)]


def run(packet,source,out,quiet=False):
    c=out/'save.c';binary=out/'save';c.write_text(source)
    compiled=subprocess.run(['cc','-std=c11','-D_XOPEN_SOURCE=700','-Wall','-Wextra','-Werror',
                    '-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter',str(c),'-lz','-o',str(binary)],capture_output=True,text=True)
    if compiled.returncode:raise RuntimeError(compiled.stderr)
    failures=[]
    baseline=(packet/'environment-before.bin').read_bytes();probe=(packet/'model-probe-NOT-FOR-INSTALL.bin').read_bytes()
    for index,(mode,boot,rc,calls,fini,exports) in enumerate(CASES):
        image=out/f'disk-{index}.img'
        with image.open('wb') as f:
            f.truncate(7818182656);f.seek(0x49ec00*512);f.write(baseline)
            f.seek(0x32ec00*512);f.write(baseline)
            # Adjacent guards catch extent errors while source-selected addresses remain observable.
            for offset in [0x49ec00*512-512,0x49ec00*512+65536]:f.seek(offset);f.write(b'G'*512)
        result=subprocess.run([str(binary),str(image),str(packet/'model-probe-NOT-FOR-INSTALL.bin'),mode,str(boot)],capture_output=True,text=True)
        name=f'{mode}, boot MMC{boot}'
        try:
            assert result.returncode==0,result.stderr
            record=json.loads(result.stdout.splitlines()[-1])
            assert record['rc']==rc and record['calls']==calls and record['fini']==fini and record['exports']==exports,record
            assert record['device']==(1 if boot==2 else 0),record
            if calls:assert record['lba']==0x49ec00 and record['count']==128,record
            with image.open('rb') as f:
                f.seek(0x32ec00*512);assert f.read(65536)==baseline,'old super environment changed'
                f.seek(0x49ec00*512);actual=f.read(65536)
                if rc==0:assert actual==probe,'actual env_export/save bytes differ'
                if calls==0 or mode=='zero':assert actual==baseline
                for offset in [0x49ec00*512-512,0x49ec00*512+65536]:f.seek(offset);assert f.read(512)==b'G'*512
            if not quiet:print('PASS actual native save/export/device:',name)
        except (AssertionError,ValueError,IndexError) as error:
            failures.append((index,name,str(error)))
        image.unlink()
    return failures


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packet',required=True,type=Path);p.add_argument('--mutations',action='store_true');a=p.parse_args()
    source=code((a.packet/'mmc.c').read_text(),(a.packet/'env-common.c').read_text(),(a.packet/'sunxi-board.c').read_text())
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory);failures=run(a.packet,source,out);assert not failures,failures
        if a.mutations:
            variants={
                'original narrowing':('return defvalue;','return ofnode_conf_read_int(propname, defvalue);'),
                'wrong old-slot write':('write_env(mmc, CONFIG_ENV_SIZE, offset,','write_env(mmc, CONFIG_ENV_SIZE, 0x65d80000,'),
                'eMMC device wrong':('case BOOT_DEVICE_MMC2:\n\t\treturn 1;','case BOOT_DEVICE_MMC2:\n\t\treturn 0;'),
                'SD mapping wrong':('case BOOT_DEVICE_MMC1:\n\t\treturn 0;','case BOOT_DEVICE_MMC1:\n\t\treturn 1;'),
                'init error ignored':('if (errmsg) {','if (0 && errmsg) {'),
                'export error ignored':('ret = env_export(env_new);\n\tif (ret)\n\t\tgoto fini;','ret = env_export(env_new);'),
                'invalid-offset status ignored':('if (mmc_get_env_addr(mmc, copy, &offset)) {\n\t\tret = 1;','if (mmc_get_env_addr(mmc, copy, &offset)) {\n\t\tret = 0;'),
                'short/zero write accepted':('return (n == blk_cnt) ? 0 : -1;','(void)n; return 0;'),
                'extent shortened':('blk_cnt\t\t= ALIGN(size, mmc->write_bl_len) / mmc->write_bl_len;','blk_cnt = 127;'),
                'partition restoration omitted':('fini_mmc_for_env(mmc);','(void)mmc;'),
            }
            killed=set()
            for name,(before,after) in variants.items():
                assert source.count(before)==1,(name,source.count(before))
                failures=run(a.packet,source.replace(before,after),out,True);assert failures,'mutation survived: '+name
                killed.update(n for n,_,_ in failures);print('CAUGHT',name)
            assert killed==set(range(len(CASES))),'a source case never failed under mutation'
            print('PASS all 10 native-save mutations caught; all 8 cases fail under a relevant fault')


if __name__=='__main__':main()
