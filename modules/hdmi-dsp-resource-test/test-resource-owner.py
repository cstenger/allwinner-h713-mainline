#!/usr/bin/env python3
"""Compile the actual module source against a fake Linux resource registry."""
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
headers = r'''
#ifndef FAKE_MODULE_H
#define FAKE_MODULE_H
#include <stdbool.h>
#include <errno.h>
#define __init
#define __exit
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define module_init(...)
#define module_exit(...)
#define MODULE_LICENSE(...)
#define MODULE_DESCRIPTION(...)
#endif
'''
registry = r'''
#ifndef FAKE_IOPORT_H
#define FAKE_IOPORT_H
#include <assert.h>
#include <stddef.h>
struct resource { int unused; };
static struct resource region;
static int occupied, requests, releases;
static struct resource *request_mem_region(unsigned long start, unsigned long size,
                                          const char *name) {
    assert(start==0x06144000 && size==0x1c && name);
    ++requests;
    if (occupied) return NULL;
    occupied=1;
    return &region;
}
static void release_mem_region(unsigned long start, unsigned long size) {
    assert(start==0x06144000 && size==0x1c && occupied);
    occupied=0;
    ++releases;
}
#endif
'''
tests = r'''
int main(void) {
    /* The default never reserves anything. */
    assert(owner_init()==-EPERM && requests==0 && releases==0);
    armed=true;
    /* A competing owner is preserved on failed module initialization. */
    occupied=1;
    assert(owner_init()==-EBUSY && occupied && requests==1 && releases==0);
    occupied=0;
    assert(owner_init()==0 && occupied && requests==2 && releases==0);
    assert(request_mem_region(0x06144000,0x1c,"competitor")==NULL);
    owner_exit();
    assert(!occupied && releases==1);
    /* Successful unload permits the next owner to reserve the exact range. */
    assert(request_mem_region(0x06144000,0x1c,"competitor")!=NULL);
    release_mem_region(0x06144000,0x1c);
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='h713-resource-owner-test-') as d:
    path = Path(d)
    (path / 'linux').mkdir()
    (path / 'linux/module.h').write_text(headers)
    (path / 'linux/ioport.h').write_text(registry)
    # Include the whole module, so adding an MMIO call fails this native build
    # unless the test is explicitly changed to provide such an API.
    (path / 'test.c').write_text('#include "h713-dsp-resource-owner-test.c"\n' + tests)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-I', str(path), '-I', str(HERE), str(path / 'test.c'),
                    '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('PASS: unarmed refusal, conflicting ownership, exact reservation and unload release; no MMIO API')
