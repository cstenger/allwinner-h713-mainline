#!/usr/bin/env python3
"""Check evidence integrity and the exact C MMIO read boundary, offline."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('domain_trace', HERE / 'analyze-domain-trace.py')
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


def lines(stage='proper_preboot', occurrence_value='00000000'):
    return (f'H713 RESET v1 stage={stage} gp6=48444d49 gp7=00000000 '
            'mips_clk=00000000 mips_reset=00000000 mips_status=00000000\n'
            f'H713 DOMAINS v1 stage={stage} ' +
            ' '.join(f'{field}={occurrence_value}' for field in analyzer.FIELDS) + '\n')


class Trace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clean, self.abrupt = self.root / 'clean', self.root / 'abrupt'

    def test_differences_and_missing_stages_remain_unproven(self):
        self.clean.write_text(lines() + lines('pre_workspace') + lines('pre_workspace'))
        self.abrupt.write_text(lines(occurrence_value='00000001'))
        result = analyzer.compare(self.clean, self.abrupt)
        self.assertEqual(result['hardware_recovery'], 'unproven')
        self.assertEqual(len(result['comparison']), 3)
        self.assertTrue(any(row['missing_trial'] == 'abrupt' for row in result['comparison']))
        self.assertTrue(any('scp_reset' in row['differences'] for row in result['comparison']))

    def test_equal_vectors_never_authorize_recovery(self):
        self.clean.write_text(lines()); self.abrupt.write_text(lines())
        self.assertEqual(analyzer.compare(self.clean, self.abrupt)['hardware_recovery'], 'unproven')

    def test_incomplete_detached_reordered_and_mixed_boots_are_rejected(self):
        good = lines()
        for broken in (good + good, good.splitlines()[0] + '\n',
                       good.replace('scp_reset=00000000 ', ''),
                       good.replace('scp_reset=00000000', 'scp_reset=unknown!'),
                       good.replace('adc_clk=00000000', 'scp_reset=00000000'),
                       good.replace('\nH713 DOMAINS', '\nnoise\nH713 DOMAINS'),
                       good.replace('DOMAINS v1 stage=proper_preboot', 'DOMAINS v1 stage=manual')):
            with self.subTest(broken=broken):
                self.clean.write_text(broken)
                with self.assertRaises(ValueError):analyzer.parse(self.clean)

    def test_real_header_reads_only_allowlisted_controls_and_skips_spl(self):
        root = self.root
        (root / 'include').mkdir()
        # Apply the actual patch files rather than compiling a duplicate of the implementation.
        header_patch = (HERE / 'reset-trace/0001-proper-reset-observation.patch').read_text().split(
            '--- a/board/sunxi/board.c')[0]
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], input=header_patch,
                       text=True, cwd=root, check=True, capture_output=True)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                        str(HERE / 'reset-trace/0003-proper-domain-controls.patch')],
                       cwd=root, check=True, capture_output=True)
        (root / 'include/asm').mkdir(); (root / 'include/linux').mkdir()
        (root / 'include/asm/io.h').write_text('unsigned int readl(unsigned long address);\n')
        (root / 'include/linux/types.h').write_text('#include <stdbool.h>\ntypedef unsigned int u32;\n')
        source = '''#include <assert.h>
#include <h713_reset_trace.h>
static unsigned int count;
static const unsigned long allowed[] = {
 0x07000400, 0x02001d10, 0x02001d20, 0x02001d24, 0x02001d28,
 0x02001d2c, 0x02001d30, 0x02001d34, 0x02001d38, 0x02001d40,
 0x02001d48, 0x02001d4c, 0x02001d50, 0x02001d58, 0x02001d5c,
 0x02001d60, 0x02001d64, 0x02001d6c, 0x02001d74, 0x02001d80,
 0x02001d84, 0x02001d88 };
unsigned int readl(unsigned long address) {
 assert(count < sizeof(allowed)/sizeof(allowed[0]));
 assert(address == allowed[count++]); return (unsigned int)address;
}
int main(void) { h713_domain_trace("proper_preboot"); assert(count == 22); return 0; }
'''
        (root / 'check.c').write_text(source)
        subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-I', str(root / 'include'),
                        str(root / 'check.c'), '-o', str(root / 'check')], check=True, capture_output=True)
        result = subprocess.run([str(root / 'check')], check=True, capture_output=True, text=True)
        self.assertIn('scp_reset=07000400', result.stdout)
        self.assertEqual(len(result.stdout.split()), 26)
        # SPL is allowed only the original four controls: any extra access aborts.
        source = '''#include <assert.h>
#include <h713_reset_trace.h>
static unsigned int count;
unsigned int readl(unsigned long address) {
 const unsigned long allowed[] = {0x07090118,0x0709011c,0x02001600,0x0200160c};
 assert(count < 4); assert(address == allowed[count++]); return 0;
}
int main(void) { h713_reset_trace("spl_pre_dram", false); assert(count == 4); return 0; }
'''
        (root / 'check.c').write_text(source)
        subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-I', str(root / 'include'),
                        str(root / 'check.c'), '-o', str(root / 'check')], check=True, capture_output=True)
        subprocess.run([str(root / 'check')], check=True, capture_output=True)


if __name__ == '__main__':unittest.main()
