#!/usr/bin/env python3
"""Offline refusal checks and native execution of the actual MMIO helpers."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
import zlib

HERE = Path(__file__).resolve().parent
ASSETS = HERE / 'tvfe-boot-trace'
sys.path.insert(0, str(HERE.parent / 'serial'))


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = load('analyze-tvfe-boot-trace')
preparer = load('prepare-tvfe-boot-trace')
spec = importlib.util.spec_from_file_location('trace_boot', HERE.parent / 'serial/run-tvfe-boot-trace.py')
boot_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot_runner)


def sample(stage, value='00010000', gate='00010001'):
    return (f'H713 TVFE v1 stage={stage} gate={gate} state=begin\n'
            f'H713 TVFE v1 stage={stage} gate={gate} state=sample tvfe={value} tvcap=00010000\n')


class Evidence(unittest.TestCase):
    def test_missing_early_samples_never_imply_cause_or_recovery(self):
        r = analyzer.analyze(sample('ppu_probe_complete', '00020000'))
        self.assertEqual(r['coverage'], 'incomplete')
        self.assertEqual(r['on_to_off_intervals'], [])
        self.assertEqual(r['dsp_retention'], 'not measured')

    def test_localizes_adjacent_on_to_off_samples(self):
        text = ''.join(sample(s, '00010000' if i < 3 else '00020000')
                       for i, s in enumerate(analyzer.REQUIRED))
        text += ''.join(sample(s, '00020000') for unused in range(5) for s in analyzer.DOMAIN_INIT)
        r = analyzer.analyze(text)
        self.assertEqual(r['coverage'], 'complete')
        self.assertEqual(r['on_to_off_intervals'][0]['first_off']['stage'], 'ppu_after_reset_deassert')
        self.assertTrue(analyzer.analyze(text, True)['missing_sample_stages'])

    def test_bad_or_unsafe_markers_and_mixed_boots_refuse(self):
        for text in (sample('x', gate='00000000'), sample('x', gate='00000001'),
                     sample('x', gate='00010000'), 'H713 TVFE v1 stage=x broken',
                     'Linux version 6.18.38\nLinux version 6.18.38',
                     sample('x').splitlines()[1], sample('x').splitlines()[0] + '\n' + sample('x')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                analyzer.analyze(text)

    def test_begun_but_missing_readback_is_explicit(self):
        r = analyzer.analyze('H713 TVFE v1 stage=ppu_probe_entry gate=00010001 state=begin\n')
        self.assertEqual(r['incomplete_begin_stages'], ['ppu_probe_entry'])

    def test_existing_output_refuses_before_source_read_or_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'keep').write_text('existing')
            with self.assertRaises(FileExistsError):
                preparer.validate(p / 'absent', p / 'absent', p / 'absent', p)
            self.assertEqual((p / 'keep').read_text(), 'existing')


class Native(unittest.TestCase):
    def compile_run(self, code, includes=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            if includes:
                for name in includes:
                    (path / name).parent.mkdir(parents=True, exist_ok=True)
                    (path / name).write_text('')
            (path / 'test.c').write_text(code)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', '-I', str(path),
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True, capture_output=True)
            subprocess.run([str(path / 'test')], check=True, capture_output=True)

    def test_uboot_actual_helper_never_reads_ppu_behind_closed_gate(self):
        code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#define BIT(n) (1U << (n))
static u32 gate;
static int ppu_reads;
static u32 readl(uintptr_t address) {
 if (address == 0x070101ac) return gate;
 assert(address == 0x070010a4 || address == 0x07001124);
 assert((gate & 0x10001) == 0x10001); ppu_reads++; return 0x10000;
}
''' + (ASSETS / 'h713_tvfe_boot_trace.h').read_text() + r'''
int main(void) {
 for (unsigned i=0; i<3; i++) { gate=(u32[]){0,1,0x10000}[i];
   h713_tvfe_boot_trace("test"); assert(ppu_reads==0); }
 gate=0x10001; h713_tvfe_boot_trace("test"); assert(ppu_reads==2);
 return 0;
}
'''
        self.compile_run(code, ['asm/io.h', 'linux/bitops.h'])

    def test_kernel_actual_helper_is_opt_in_machine_checked_and_gate_checked(self):
        code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define __iomem
#define __init
#define BIT(n) (1U << (n))
#define pr_info(...) printf(__VA_ARGS__)
#define pr_err(...) printf(__VA_ARGS__)
#define early_param(a,b)
#define early_initcall(a)
static u32 gate;
static int reads, ppu_reads, maps, wrong_machine;
static bool of_machine_is_compatible(const char *s) {return !wrong_machine;}
static void *ioremap(uintptr_t p, unsigned size) {maps++; return (void *)p;}
static void iounmap(void *p) {}
static u32 readl(void *ptr) {
 uintptr_t p=(uintptr_t)ptr; reads++;
 if(p==0x070101ac) return gate;
 assert(p==0x070010a4 || p==0x07001124);
 assert((gate & 0x10001)==0x10001); ppu_reads++; return 0x10000;
}
''' + (ASSETS / 'kernel-trace.inc').read_text() + r'''
int main(void) {
 h713_tvfe_boot_trace("disabled"); h713_tvfe_trace_early(); assert(!reads && !maps);
 assert(h713_tvfe_trace_setup("0")==-EINVAL);
 assert(h713_tvfe_trace_setup(NULL)==-EINVAL);
 assert(!h713_tvfe_trace_setup("1")); wrong_machine=1;
 h713_tvfe_trace_early(); assert(!reads && !maps);
 wrong_machine=0; h713_tvfe_trace_setup("1"); gate=0;
 h713_tvfe_trace_early(); assert(maps==2 && ppu_reads==0);
 gate=1; h713_tvfe_boot_trace("half"); assert(ppu_reads==0);
 gate=0x10000; h713_tvfe_boot_trace("half"); assert(ppu_reads==0);
 gate=0x10001; h713_tvfe_boot_trace("open"); assert(ppu_reads==2);
 return 0;
}
'''
        self.compile_run(code)

    def test_embedded_patch_matches_native_tested_helper(self):
        additions = '\n'.join(line[1:] for line in (ASSETS / '0001-kernel-ppu-observation.patch').read_text().splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
        self.assertIn((ASSETS / 'kernel-trace.inc').read_text().strip(), additions)
        for line in additions.splitlines():
            self.assertNotIn('writel(', line)  # only original power/init writes remain


class RAMBoot(unittest.TestCase):
    def test_capture_survives_long_silence_and_stops_at_total_deadline(self):
        from unittest.mock import patch
        import io
        now = [0]
        chunks = iter([b'before intentional hold\n', b'after intentional hold\n'])
        def select_once(*unused):
            now[0] += 5
            return ([99], [], []) if now[0] in (5, 20) else ([], [], [])
        raw = io.BytesIO()
        with patch.object(boot_runner.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(boot_runner.select, 'select', side_effect=select_once), \
             patch.object(boot_runner.os, 'read', side_effect=lambda *args: next(chunks)):
            boot_runner.capture(99, raw, 30)
        self.assertEqual(now[0], 30)
        self.assertIn(b'after intentional hold', raw.getvalue())

    def test_capture_detects_unexpected_reset_without_retry(self):
        from unittest.mock import patch
        import io
        with patch.object(boot_runner.time, 'monotonic', return_value=0), \
             patch.object(boot_runner.select, 'select', return_value=([99], [], [])), \
             patch.object(boot_runner.os, 'read', return_value=b'U-Boot SPL unexpected'):
            with self.assertRaisesRegex(RuntimeError, 'unexpected reset'):
                boot_runner.capture(99, io.BytesIO(), 30)

    class Console:
        def __init__(self, **values):
            self.values = {boot_runner.warm.R_CCU_PPU: 0x10001,
                           boot_runner.warm.PPU_TVFE: 0x10000,
                           boot_runner.warm.PPU_TVCAP: 0x10000,
                           boot_runner.warm.GP6: 0x48444d49,
                           boot_runner.warm.MIPS_STATUS: 0}
            for key, val in values.items():
                self.values[getattr(boot_runner.warm, key)] = val
            self.lines = []
            self.crc = zlib.crc32(b'fit')

        def run(self, line):
            self.lines.append(line)
            if line == 'printenv bootcmd':
                return b'bootcmd=production\r\n=> '
            if line.startswith('crc32 '):
                return ('CRC32 for 50000000 ==> %08x\r\n=> ' % self.crc).encode()
            addr = int(line.split()[1], 16)
            return ('%08x: %08x\r\n=> ' % (addr, self.values[addr])).encode()

        def checked(self, line):
            self.lines.append(line)

    def test_valid_warm_state_uses_only_ram_load_and_volatile_environment(self):
        con = self.Console()
        boot_runner.boot(con, 'production', b'fit')
        self.assertIn('ext4load mmc 1:1a 0x50000000 ' + boot_runner.REMOTE_FIT, con.lines)
        self.assertIn('setenv bootargs ' + boot_runner.BOOTARGS, con.lines)
        self.assertFalse(any('saveenv' in s or 'h713_disp' in s or 'mw.' in s or 'mmc write' in s for s in con.lines))
        self.assertIn('panic=0', boot_runner.BOOTARGS)

    def test_wrong_latch_live_mips_or_off_domains_never_loads_or_changes_environment(self):
        for kwargs in ({'GP6': 0}, {'MIPS_STATUS': 1}, {'PPU_TVFE': 0x20000}, {'PPU_TVCAP': 0x20000}):
            con = self.Console(**kwargs)
            with self.assertRaises(RuntimeError):
                boot_runner.boot(con, 'production', b'fit')
            self.assertFalse(any(s.startswith(('ext4load', 'setenv')) for s in con.lines))

    def test_bootcmd_and_ram_crc_mismatch_stop(self):
        con = self.Console()
        with self.assertRaises(RuntimeError):
            boot_runner.boot(con, 'wrong', b'fit')
        self.assertFalse(any(s.startswith('ext4load') for s in con.lines))
        con = self.Console()
        con.crc = 0
        with self.assertRaises(RuntimeError):
            boot_runner.boot(con, 'production', b'fit')
        self.assertFalse(any(s.startswith('setenv') for s in con.lines))


if __name__ == '__main__':
    unittest.main()
