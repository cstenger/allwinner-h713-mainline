#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Host checks of the patched kernel's real HEVC/VP9 helpers and PIO DTBs.

Usage: python3 tools/video/test-kernel-followups.py --kernel <prepared tree>
Compiles extracted source with ASan/UBSan and minimal queue stubs; never opens
a device. Hardware decode, PHY reset and interrupt delivery need board tests.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


def definition(source, marker):
    start = source.index(marker)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


PREAMBLE = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <linux/v4l2-controls.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define typeof_member(T, m) __typeof__(((T *)0)->m)
'''

QUEUE_STUBS = r'''
struct cedrus_buffer { struct { struct { unsigned int mv_col_buf_size; } h265; } codec; };
struct vb2_buffer { struct cedrus_buffer cedrus; uint64_t timestamp; };
struct vb2_queue { struct vb2_buffer buffers[16]; bool present[16]; };
struct cedrus_ctx { struct { struct { struct vb2_queue *queue; } *m2m_ctx; } fh; };
#define V4L2_BUF_TYPE_VIDEO_CAPTURE 1
static struct vb2_queue *v4l2_m2m_get_vq(__typeof__(((struct cedrus_ctx *)0)->fh.m2m_ctx) m, int type)
{ (void)type; return m->queue; }
static struct vb2_buffer *vb2_find_buffer(struct vb2_queue *q, uint64_t timestamp)
{
    for (unsigned int i = 0; i < 16; i++)
        if (q->present[i] && q->buffers[i].timestamp == timestamp) return &q->buffers[i];
    return NULL;
}
static struct cedrus_buffer *vb2_to_cedrus_buffer(struct vb2_buffer *b) { return &b->cedrus; }
'''

HEVC_CASES = r'''
int main(void)
{
    struct vb2_queue q = {0};
    __typeof__(*(((struct cedrus_ctx *)0)->fh.m2m_ctx)) m = { .queue = &q };
    struct cedrus_ctx ctx = { .fh.m2m_ctx = &m };
    struct v4l2_hevc_dpb_entry dpb[V4L2_HEVC_DPB_ENTRIES_NUM_MAX] = {0};
    u8 refs[V4L2_HEVC_DPB_ENTRIES_NUM_MAX] = {0};
    struct v4l2_ctrl_hevc_slice_params s = {0};
    for (unsigned int i = 0; i < 16; i++) {
        dpb[i].timestamp = q.buffers[i].timestamp = i + 1;
        q.present[i] = true;
        q.buffers[i].cedrus.codec.h265.mv_col_buf_size = 1024;
    }
    for (unsigned int active = 1; active <= 16; active++) {
        for (unsigned int i = 0; i < active; i++) refs[i] = i;
        assert(cedrus_h265_check_ref_list(&ctx, refs, active, dpb, active) == 0);
        refs[0] = active;
        assert(cedrus_h265_check_ref_list(&ctx, refs, 1, dpb, active) == -EINVAL);
    }
    refs[0] = 255;
    assert(cedrus_h265_check_ref_list(&ctx, refs, 1, dpb, 16) == -EINVAL);
    refs[0] = 0;
    assert(cedrus_h265_check_ref_list(&ctx, refs, 17, dpb, 16) == -EINVAL);
    assert(cedrus_h265_check_ref_list(&ctx, refs, 1, dpb, 0) == -EINVAL);
    q.present[0] = false;
    assert(cedrus_h265_check_ref_list(&ctx, refs, 1, dpb, 16) == -EINVAL);
    q.present[0] = true;
    q.buffers[0].cedrus.codec.h265.mv_col_buf_size = 0;
    assert(cedrus_h265_check_ref_list(&ctx, refs, 1, dpb, 16) == -EINVAL);
    s.slice_type = V4L2_HEVC_SLICE_TYPE_P;
    s.collocated_ref_idx = 255;
    assert(cedrus_h265_check_collocated(&s) == 0); /* no temporal MVP */
    s.flags = V4L2_HEVC_SLICE_PARAMS_FLAG_SLICE_TEMPORAL_MVP_ENABLED;
    s.slice_type = V4L2_HEVC_SLICE_TYPE_I;
    assert(cedrus_h265_check_collocated(&s) == 0);
    s.slice_type = V4L2_HEVC_SLICE_TYPE_P;
    s.num_ref_idx_l0_active_minus1 = 2;
    s.num_ref_idx_l1_active_minus1 = 0;
    s.collocated_ref_idx = 2;
    assert(cedrus_h265_check_collocated(&s) == 0);
    s.collocated_ref_idx = 3;
    assert(cedrus_h265_check_collocated(&s) == -EINVAL);
    s.slice_type = V4L2_HEVC_SLICE_TYPE_B;
    s.collocated_ref_idx = 1;
    assert(cedrus_h265_check_collocated(&s) == -EINVAL); /* L1 has one entry */
    s.flags |= V4L2_HEVC_SLICE_PARAMS_FLAG_COLLOCATED_FROM_L0;
    assert(cedrus_h265_check_collocated(&s) == 0);
    s.num_ref_idx_l0_active_minus1 = 15;
    s.collocated_ref_idx = 15;
    assert(cedrus_h265_check_collocated(&s) == 0);
    s.collocated_ref_idx = 16;
    assert(cedrus_h265_check_collocated(&s) == -EINVAL);
    puts("HEVC reference bounds, missing buffers/MV allocations and collocated P/B/I cases pass");
}
'''

CORE_CASES = r'''
int main(void)
{
    struct v4l2_ctrl_hevc_slice_params s = {0};
    s.ref_idx_l0[0] = s.ref_idx_l1[0] = 255; /* core keeps sentinel policy */
    for (unsigned int l0 = 0; l0 < 256; l0++) {
        s.num_ref_idx_l0_active_minus1 = l0;
        s.num_ref_idx_l1_active_minus1 = 255;
        s.slice_type = V4L2_HEVC_SLICE_TYPE_P;
        assert(validate(&s) == (l0 < 16 ? 0 : -EINVAL));
        for (unsigned int l1 = 0; l1 < 256; l1++) {
            s.slice_type = V4L2_HEVC_SLICE_TYPE_B;
            s.num_ref_idx_l1_active_minus1 = l1;
            assert(validate(&s) == (l0 < 16 && l1 < 16 ? 0 : -EINVAL));
        }
    }
    puts("HEVC core: all 65,536 B-slice count pairs, P-slice counts and missing-reference sentinels pass");
}
'''

VP9_CASES = r'''
int main(void)
{
    struct cedrus_vp9_tx_skip saved;
    struct v4l2_vp9_frame_context original, actual, expected;
    uint32_t state = 1;
    assert(sizeof(saved) == 15);
    for (unsigned int n = 0; n < 512; n++) {
        for (unsigned int i = 0; i < sizeof(original); i++) {
            state = state * 1664525 + 1013904223;
            ((u8 *)&original)[i] = state >> 24;
        }
        memset(&actual, 0xa5, sizeof(actual));
        expected = actual;
        memcpy(expected.tx8, original.tx8, sizeof(expected.tx8));
        memcpy(expected.tx16, original.tx16, sizeof(expected.tx16));
        memcpy(expected.tx32, original.tx32, sizeof(expected.tx32));
        memcpy(expected.skip, original.skip, sizeof(expected.skip));
        save_tx_and_skip(&saved, &original);
        restore_tx_and_skip(&actual, &saved);
        assert(memcmp(&actual, &expected, sizeof(actual)) == 0);
    }
    puts("VP9: 15-byte save/restore preserves all four fields and leaves other probabilities untouched (512 contexts)");
}
'''


class KernelFollowups(unittest.TestCase):
    def compile_run(self, code, succeeds=True):
        with tempfile.TemporaryDirectory(prefix='h713-followups-') as tmp:
            c = Path(tmp) / 'test.c'
            binary = Path(tmp) / 'test'
            c.write_text(PREAMBLE + code)
            compiled = subprocess.run(
                ['clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra',
                 '-Werror', '-fsanitize=address,undefined',
                 '-D__EXPORTED_HEADERS__',
                 '-I', str(KERNEL / 'include/uapi'), str(c), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
            if succeeds:
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                print(run.stdout.strip())
            else:
                self.assertNotEqual(run.returncode, 0, 'regression escaped the test')

    def test_hevc_references(self):
        source = (KERNEL / 'drivers/staging/media/sunxi/cedrus/cedrus_h265.c').read_text()
        helpers = '\n'.join(definition(source, marker) for marker in (
            'static int cedrus_h265_check_ref_list(', 'static int cedrus_h265_check_collocated('))
        self.compile_run(QUEUE_STUBS + helpers + HEVC_CASES)
        # Prove both historically unsafe cases are exercised, not just valid streams.
        for before in ('list[i] >= num_active_dpb_entries',
                       'slice_params->collocated_ref_idx > max'):
            self.assertIn(before, helpers)
            self.compile_run(QUEUE_STUBS + helpers.replace(before, '(' + before + ' && false)') + HEVC_CASES,
                             succeeds=False)
        setup = definition(source, 'static int cedrus_h265_setup(')
        engine = setup.index('cedrus_engine_enable(ctx)')
        self.assertLess(setup.index('cedrus_h265_check_ref_list('), engine)
        self.assertLess(setup.index('cedrus_h265_check_collocated('), engine)
        self.assertIn('V4L2_HEVC_SLICE_TYPE_B', setup[:engine])

    def test_hevc_core_counts(self):
        source = (KERNEL / 'drivers/media/v4l2-core/v4l2-ctrls-core.c').read_text()
        function = definition(source, 'static int std_validate_compound(')
        branch = function[function.index('\tcase V4L2_CTRL_TYPE_HEVC_SLICE_PARAMS:'):]
        branch = branch[:branch.index('\n\tcase ', 1)]
        wrapper = ('#define V4L2_CTRL_TYPE_HEVC_SLICE_PARAMS 1\n'
                   'static int validate(struct v4l2_ctrl_hevc_slice_params *p) {\n'
                   'struct v4l2_ctrl_hevc_slice_params *p_hevc_slice_params;\n'
                   'switch (1) {\n' + branch + '\n} return 0; }\n')
        self.compile_run(wrapper + CORE_CASES)
        # Widening >= to > must fail exactly at the 16-entry boundary.
        self.compile_run(wrapper.replace(' >=', ' >') + CORE_CASES, succeeds=False)

    def test_vp9_probability_preservation(self):
        source = (KERNEL / 'drivers/staging/media/sunxi/cedrus/cedrus_vp9.c').read_text()
        header = (KERNEL / 'include/media/v4l2-vp9.h').read_text()
        structs = '\n'.join(definition(header, 'struct ' + name + ' {') + ';'
                            for name in ('v4l2_vp9_frame_mv_context', 'v4l2_vp9_frame_context'))
        helpers = definition(source, 'struct cedrus_vp9_tx_skip {') + ';\n'
        helpers += definition(source, 'static void save_tx_and_skip(') + '\n'
        helpers += definition(source, 'static void restore_tx_and_skip(') + '\n'
        self.compile_run(structs + helpers + VP9_CASES)
        # Omitting the skip-field copy must be observable.
        mutated, count = re.subn(r'\tmemcpy\(dst->skip, src->skip, sizeof\(dst->skip\)\);',
                                '', helpers, count=1)
        self.assertEqual(count, 1)
        self.compile_run(structs + mutated + VP9_CASES, succeeds=False)
        finish = definition(source, 'static void cedrus_vp9_finish(')
        self.assertNotIn('struct v4l2_vp9_frame_context tx_skip', finish)

    def test_gpio_parent_irq_and_both_board_dtbs(self):
        source = (KERNEL / 'drivers/pinctrl/sunxi/pinctrl-sunxi.c').read_text()
        self.assertRegex(source, r'pctl->irq\[i\] = platform_get_irq\(pdev, i\);')
        pins = (KERNEL / 'drivers/pinctrl/sunxi/pinctrl-sun50i-h713.c').read_text()
        banks = re.search(r'h713_irq_bank_map\[\] = \{(.*?)\};', pins, re.S).group(1)
        banks = re.sub(r'/\*.*?\*/', '', banks, flags=re.S)
        banks = [int(n) for n in re.findall(r'\d+', banks)]
        self.assertEqual(banks, [0, 1, 2, 3, 5, 6, 7])
        for board in ('hy200-qz713df-a1', 'hy200-qz713-v2'):
            dtb = KERNEL / ('arch/arm64/boot/dts/allwinner/sun50i-h713-' + board + '.dtb')
            data = subprocess.check_output(['fdtget', '-t', 'u', str(dtb),
                                            '/soc/pinctrl@2000000', 'interrupts'], text=True)
            irqs = [int(n) for n in data.split()]
            self.assertEqual(irqs, [n for spi in range(54, 61) for n in (0, spi, 4)])
            self.assertEqual(dict(zip(banks, irqs[1::3]))[7], 60)

    def test_usb_hci_config(self):
        source = (KERNEL / 'drivers/phy/allwinner/phy-sun4i-usb.c').read_text()
        cfg = definition(source, 'static const struct sun4i_usb_phy_cfg sun50i_h713_cfg =')
        self.assertIn('.hci_phy_ctl_clear = PHY_CTL_SIDDQ', cfg)
        self.assertIn('.pmu_enable_bit0 = true', cfg)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    args, rest = parser.parse_known_args()
    KERNEL = args.kernel.resolve()
    unittest.main(argv=[__file__, *rest])
