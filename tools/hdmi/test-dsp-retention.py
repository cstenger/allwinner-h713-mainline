#!/usr/bin/env python3
"""Native hold/observer fault controls plus evidence and shutdown-policy tests."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ASSETS = HERE / 'dsp-retention'
sys.path.insert(0, str(ROOT / 'tools/serial'))


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


analysis = load('retention_analysis', HERE / 'analyze-dsp-retention.py')
helper = load('retention_helper', HERE / 'dsp-retention.py')
prepare = load('retention_prepare', HERE / 'prepare-dsp-retention.py')
runner = load('retention_runner', ROOT / 'tools/serial/run-dsp-retention-boot.py')


def good_record():
    return {'baseline': {'boot_id': 'cold', 'hdmi_handoff': True, 'tv_domains_both_on': True,
        'units': dict.fromkeys(('capture', 'signal', 'speaker'), 'active'),
        'dsp_journal': ['DSP versions 0000/0000', 'pinned 724-pair DSP patch verified versions 1/1']},
        'warm_boot_id': 'warm', 'preflight_valid': True, 'state': {'schema': 'h713-dsp-retention-v1', 'step': 46,
        'hold': 1, 'violated': 0, 'failed': 0, 'timeout': 0, 'claimed': 0,
        'outcome0': 1, 'outcome1': 1, 'raw0': 0x80ff0001, 'raw1': 0x80ff0001,
        'interface_inherited': 1}}


class Evidence(unittest.TestCase):
    def test_preflight_refuses_wrong_kernel_and_uninstalled_guard_before_owner_actions(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / 'h713-hdmi-hold-guard').write_text('expected')
            (p / 'installed').write_text('different')
            manifest = {'purpose': 'bench DSP warm retention; not installed', 'built': True,
                        'symvers_unchanged': True, 'kernel_release': '6.18.38', 'kernel_uts_version': 'diag',
                        'bundle': {'h713-hdmi-hold-guard': hashlib.sha256(b'expected').hexdigest()}}
            (p / 'manifest.json').write_text(json.dumps(manifest))
            with patch.object(helper.os, 'uname', return_value=SimpleNamespace(release='wrong', version='diag')), \
                 patch.object(helper.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'exact ABI-checked'):
                    helper.preflight(p, good_record()['baseline'])
                run.assert_not_called()
            with patch.object(helper.os, 'uname', return_value=SimpleNamespace(release='6.18.38', version='diag')), \
                 patch.object(helper, 'GUARD', p / 'installed'), patch.object(helper.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'shutdown guard'):
                    helper.preflight(p, good_record()['baseline'])
                run.assert_not_called()

    def test_both_versions_required_for_positive_or_zero_outcome(self):
        r = good_record()
        self.assertTrue(analysis.analyze(r)['patch_version_survives_tested_warm_path'])
        r['state'].update(raw0=0x80ff0000, raw1=0x80ff0000)
        self.assertEqual(analysis.analyze(r)['classification'], 'zero_versions_after_warm_access')
        self.assertEqual(analysis.analyze(r)['dsp_ram_erasure'], 'not directly measured')
        r['state']['raw1'] = 0x80ff0001
        self.assertIsNone(analysis.analyze(r)['patch_version_survives_tested_warm_path'])

    def test_failed_incomplete_timed_out_or_wrong_boot_never_becomes_zero(self):
        for field, value in [('step', 43), ('hold', 0), ('violated', 1), ('failed', 1),
                             ('timeout', 1), ('claimed', 1), ('outcome0', 2), ('outcome1', 3)]:
            r = good_record()
            r['state'].update(raw0=0, raw1=0)
            r['state'][field] = value
            self.assertEqual(analysis.analyze(r)['classification'], 'inconclusive')
            self.assertIsNone(analysis.analyze(r)['versions'])
        r = good_record(); r['warm_boot_id'] = 'cold'
        self.assertEqual(analysis.analyze(r)['classification'], 'inconclusive')
        r = good_record(); r['baseline']['dsp_journal'] = []
        self.assertEqual(analysis.analyze(r)['classification'], 'inconclusive')
        r = good_record(); r['preflight_valid'] = False
        self.assertEqual(analysis.analyze(r)['classification'], 'inconclusive')

    def test_audio_interface_intervention_remains_visible(self):
        r = good_record(); r['state']['interface_inherited'] = 0
        self.assertFalse(analysis.analyze(r)['audiotop_was_inherited'])

    def test_existing_output_is_preserved_before_base_inspection(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t); (p / 'keep').write_text('evidence')
            with self.assertRaises(FileExistsError):
                prepare.prepare(p / 'missing', p)
            self.assertEqual((p / 'keep').read_text(), 'evidence')

    def test_step_table_and_stage_boundaries(self):
        self.assertEqual(len(helper.STEPS), 46)
        self.assertEqual(helper.STEPS[36], 'audiotop-census')
        self.assertEqual(helper.STEPS[42:45], ['device0-version', 'device1-version', 'release-stock-lock'])
        self.assertEqual(helper.STAGES[37], 'audiotop-read')
        text = (ASSETS / 'observer.inc').read_text()
        for forbidden in ('reset_control_assert(', 'pm_runtime_resume', 'h713_ppu_set_power(', 'stock_patch'):
            self.assertNotIn(forbidden, text)

    def test_ram_boot_checks_guard_before_loading_diagnostic(self):
        fake = type('Console', (), {})()
        fake.checked = lambda line: calls.append(line)
        fake.run = lambda line: b'CRC32 ==> 00000000\r\n=> '
        calls = []
        runner.guard_bytes = b'guard bytes'
        with self.assertRaisesRegex(RuntimeError, 'guard CRC mismatch'):
            runner.check_installed_guard(fake)
        self.assertIn('0x53000000', calls[0])
        self.assertIn('h713_tvfe_retain=1', runner.loader.BOOTARGS)


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name)
        for name in ['dt-bindings/clock/sun50i-h713-ccu.h', 'linux/clk-provider.h',
                     'linux/ioport.h', 'linux/kobject.h', 'linux/mutex.h', 'linux/of_clk.h', 'linux/sysfs.h']:
            p = cls.path / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('')
        cmd = ['cc', '-std=gnu11', '-Wall', '-Werror', '-I', str(cls.path), '-I', str(ASSETS),
               '-I', str(ROOT / 'modules/hdmi-dsp-probe'), str(ASSETS / 'native-test.c'), '-o', str(cls.path / 'observer')]
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode:
            raise AssertionError(run.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_actual_observer_normal_inherited_and_zero_responses(self):
        for mode in ['normal', 'inherited', 'zero']:
            subprocess.run([str(self.path / 'observer'), mode], check=True)

    def test_actual_observer_faults_do_not_retry_or_patch(self):
        for mode in ['done-timeout', 'busy-timeout', 'lock-mismatch', 'resource-denied',
                     'closed-gate', 'power-loss', 'violated']:
            with self.subTest(mode=mode):
                subprocess.run([str(self.path / 'observer'), mode], check=True)

    def test_actual_hold_predicate_refuses_off_busy_cold_live_or_half_gated(self):
        code = '#include <stdbool.h>\n#include <stdint.h>\n#include <assert.h>\ntypedef uint32_t u32;\n'
        code += (ASSETS / 'retention-policy.h').read_text()
        code += '''
int main(void) {
 assert(h713_retention_eligible(true,true,0x10001,0x48444d49,0,0,0x10000,0x10000));
 assert(!h713_retention_eligible(false,true,0x10001,0x48444d49,0,0,0x10000,0x10000));
 assert(!h713_retention_eligible(true,false,0x10001,0x48444d49,0,0,0x10000,0x10000));
 unsigned gates[]={0,1,0x10000};
 for(int i=0;i<3;i++)assert(!h713_retention_eligible(true,true,gates[i],0x48444d49,0,0,0x10000,0x10000));
 assert(!h713_retention_eligible(true,true,0x10001,0,0,0,0x10000,0x10000));
 assert(!h713_retention_eligible(true,true,0x10001,0x48444d49,1,0,0x10000,0x10000));
 assert(!h713_retention_eligible(true,true,0x10001,0x48444d49,0,1,0x10000,0x10000));
 assert(!h713_retention_eligible(true,true,0x10001,0x48444d49,0,0,0x20000,0x10000));
 assert(!h713_retention_eligible(true,true,0x10001,0x48444d49,0,0,0x10008,0x10000));
 assert(!h713_retention_eligible(true,true,0x10001,0x48444d49,0,0,0x10000,0x20000));
 assert(!h713_retention_eligible(true,true,0x10001,0x48444d49,0,0,0x10000,0x10008));
 return 0;
}
'''
        p = self.path / 'policy.c'; p.write_text(code)
        subprocess.run(['cc', '-Wall', '-Werror', str(p), '-o', str(self.path / 'policy')], check=True)
        subprocess.run([str(self.path / 'policy')], check=True)


class BenchGuard(unittest.TestCase):
    def test_cmdline_hold_blocks_reboot_without_a_module(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t); (p / 'sys').mkdir(); calls = p / 'calls'
            for name in ['off', 'poweroff']:
                f = p / name; f.write_text('#!/bin/sh\necho ' + name + ' >> ' + str(calls) + '\n'); f.chmod(0o755)
            guard = prepare.make_guard()
            (p / 'guard').write_text(guard)
            env = {'PATH': '/usr/bin:/bin', 'H713_GUARD_SYSMODULE': str(p / 'sys'),
                   'H713_GUARD_CMDLINE': str(p / 'cmdline'), 'H713_GUARD_LAMP_OFF': str(p / 'off'),
                   'H713_GUARD_POWEROFF': str(p / 'poweroff')}
            for line, action, expected in [('h713_tvfe_retain=1', 'reboot', ['off', 'poweroff']),
                 ('x h713_tvfe_retain=1 y', 'kexec', ['off', 'poweroff']),
                 ('h713_tvfe_retain=10', 'reboot', []), ('normal', 'reboot', []),
                 ('h713_tvfe_retain=1', 'poweroff', [])]:
                calls.unlink(missing_ok=True); (p / 'cmdline').write_text(line)
                subprocess.run(['sh', str(p / 'guard'), action], env=env, capture_output=True, check=True)
                self.assertEqual(calls.read_text().splitlines() if calls.exists() else [], expected)


if __name__ == '__main__':
    unittest.main()
