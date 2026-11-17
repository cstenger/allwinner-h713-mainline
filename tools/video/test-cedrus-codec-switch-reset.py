#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Source-bound test of cedrus's codec-switch decode-engine reset; no device.

Extracts the prepared kernel's cedrus_reset_on_codec_switch(), compiles it
under ASan/UBSan with reset stubs, and checks: no reset without a VE3 line;
none on the first job or the same codec; exactly one RST_BUS_VE3 pulse per
switch and never the RST_BUS_VE line the AV1 core depends on; a failed pulse
leaves the codec unrecorded so the next job retries. Structurally, the helper
runs in cedrus_device_run() before any request setup or register write, and
runtime resume clears the record after releasing VE3.

--mutations requires broken variants to fail.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, marker):
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
struct reset_control { const char *name; };
struct device { int unused; };
struct cedrus_dev { struct device *dev; struct reset_control *rstc; struct reset_control *rstc_ve3; u32 last_codec; };
static struct reset_control ve = {"ve"}, ve3 = {"ve3"};
static int pulses_ve, pulses_ve3, fail_next, warnings;
static int reset_control_reset(struct reset_control *r){
    assert(r);                      /* never called on an absent line */
    if (r == &ve) { pulses_ve++; return 0; }
    assert(r == &ve3);
    pulses_ve3++;
    if (fail_next) { fail_next = 0; return -5; }
    return 0;
}
#define dev_warn_ratelimited(d, ...) (warnings++)
'''
CASES = r'''
#define VP9 0x39305056u
#define H265 0x35364853u
int main(void){
    struct device d; struct cedrus_dev dev = {&d, &ve, NULL, 0};
    /* No VE3 line (other SoCs): never resets, never records. */
    cedrus_reset_on_codec_switch(&dev, VP9); cedrus_reset_on_codec_switch(&dev, H265);
    assert(!pulses_ve && !pulses_ve3 && dev.last_codec == 0);
    dev.rstc_ve3 = &ve3;
    cedrus_reset_on_codec_switch(&dev, VP9);           /* first job */
    assert(!pulses_ve3 && dev.last_codec == VP9);
    cedrus_reset_on_codec_switch(&dev, VP9);           /* same codec */
    assert(!pulses_ve3);
    cedrus_reset_on_codec_switch(&dev, H265);          /* switch */
    assert(pulses_ve3 == 1 && dev.last_codec == H265);
    fail_next = 1;
    cedrus_reset_on_codec_switch(&dev, VP9);           /* failed pulse */
    assert(pulses_ve3 == 2 && dev.last_codec == H265 && warnings == 1);
    cedrus_reset_on_codec_switch(&dev, VP9);           /* retried */
    assert(pulses_ve3 == 3 && dev.last_codec == VP9);
    const u32 seq[] = {VP9, H265, VP9, VP9, H265};
    int before = pulses_ve3;
    for (unsigned i = 0; i < 5; i++) cedrus_reset_on_codec_switch(&dev, seq[i]);
    assert(pulses_ve3 - before == 3);
    assert(pulses_ve == 0);                             /* the AV1 core's line is never touched */
    puts("PASS VE3-only pulse per codec switch; none first/same/without VE3; failed pulse retried");
}
'''


def structure(src):
    run = function(src['cedrus_dec.c'], 'void cedrus_device_run(')
    call = run.index('cedrus_reset_on_codec_switch(dev, ctx->src_fmt.pixelformat);')
    for later in ('v4l2_ctrl_request_setup(', 'dev->dec_ops[', 'cedrus_engine_enable('):
        if later in run:
            assert call < run.index(later), 'reset must precede ' + later
    resume = function(src['cedrus_hw.c'], 'int cedrus_hw_resume(')
    clear = resume.index('dev->last_codec = 0;')
    assert resume.index('reset_control_deassert(dev->rstc_ve3)') < clear, 'record cleared before VE3 release'
    helper = function(src['cedrus_hw.c'], 'void cedrus_reset_on_codec_switch(')
    assert not re.search(r'dev->rstc\b', helper), 'helper names the shared VE line'
    print('PASS structure: reset before request setup/register writes; resume clears after VE3 release')


MUTATIONS = [
    ('pulses-shared-ve-line', ('reset_control_reset(dev->rstc_ve3)', 'reset_control_reset(dev->rstc)')),
    ('pulses-on-first-job', ('if (dev->last_codec && dev->last_codec != codec)', 'if (dev->last_codec != codec)')),
    ('pulses-on-same-codec', ('if (dev->last_codec && dev->last_codec != codec)', 'if (dev->last_codec)')),
    ('no-pulse-on-switch', ('if (dev->last_codec && dev->last_codec != codec)', 'if (0)')),
    ('records-after-failure', ('\t\t\treturn;\n\t\t}\n\t}\n\n\tdev->last_codec = codec;', '\t\t}\n\t}\n\n\tdev->last_codec = codec;')),
    ('no-ve3-guard', ('\tif (!dev->rstc_ve3)\n\t\treturn;\n', '')),
]
STRUCT_MUTATIONS = [
    ('call-after-request-setup', 'cedrus_dec.c', ('\tcedrus_reset_on_codec_switch(dev, ctx->src_fmt.pixelformat);\n', ''),
     ('\t\tv4l2_ctrl_request_setup(src_req, &ctx->hdl);\n',
      '\t\tv4l2_ctrl_request_setup(src_req, &ctx->hdl);\n\tcedrus_reset_on_codec_switch(dev, ctx->src_fmt.pixelformat);\n')),
    ('resume-keeps-record', 'cedrus_hw.c', ('\tdev->last_codec = 0;\n', '')),
]


def compile_run(directory, name, code, expect_failure):
    source = directory / (name + '.c')
    exe = directory / name
    source.write_text(code)
    built = subprocess.run(['clang', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            str(source), '-o', str(exe)], capture_output=True, text=True)
    if built.returncode:
        if expect_failure:
            print('PASS rejected (does not build):', name)
            return
        print(built.stderr)
        raise SystemExit('build failed: ' + name)
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30,
                         env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
    if expect_failure:
        assert run.returncode != 0, 'unexpectedly passed: ' + name
        why = [l for l in (run.stderr + run.stdout).splitlines() if 'Assertion' in l]
        print('PASS rejected:', name, '--', why[0].split(': ', 2)[-1] if why else 'exit %d' % run.returncode)
    else:
        assert run.returncode == 0, run.stderr
        print(run.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--mutations', action='store_true')
    args = parser.parse_args()
    d = args.kernel / 'drivers/staging/media/sunxi/cedrus'
    src = {n: (d / n).read_text() for n in ('cedrus_dec.c', 'cedrus_hw.c')}
    helper = function(src['cedrus_hw.c'], 'void cedrus_reset_on_codec_switch(')
    with tempfile.TemporaryDirectory(prefix='h713-cedrus-switch-') as tmp:
        tmp = Path(tmp)
        compile_run(tmp, 'switch-reset', HARNESS + helper + CASES, False)
        structure(src)
        if args.mutations:
            for label, (old, new) in MUTATIONS:
                assert helper.count(old) == 1, 'mutation anchor missing: ' + label
                compile_run(tmp, 'mutant-' + label, HARNESS + helper.replace(old, new) + CASES, True)
            for label, name, *edits in STRUCT_MUTATIONS:
                broken = dict(src)
                for old, new in edits:
                    assert broken[name].count(old) == 1, 'mutation anchor missing: ' + label
                    broken[name] = broken[name].replace(old, new)
                try:
                    structure(broken)
                except (AssertionError, ValueError) as error:
                    print('PASS rejected:', 'mutant-' + label, '--', error or 'structure check')
                else:
                    raise SystemExit('unexpectedly passed: mutant-' + label)


if __name__ == '__main__':
    main()
