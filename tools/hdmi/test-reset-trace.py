#!/usr/bin/env python3
"""Offline checks for evidence ambiguity and source/output isolation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = load('reset_analyzer', 'analyze-reset-trace.py')
preparer = load('reset_preparer', 'prepare-reset-trace.py')


def marker(stage, status='00000000', gp6='48444d49'):
    return (f'H713 RESET v1 stage={stage} gp6={gp6} gp7=00000000 '
            f'mips_clk=00000000 mips_reset=00000000 mips_status={status}\n')


class Evidence(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.clean, self.abrupt = self.root / 'clean', self.root / 'abrupt'

    def test_missing_phases_and_differences_never_become_recovery_pass(self):
        self.clean.write_text(marker('proper_preboot') + marker('pre_workspace') + marker('post_logo'))
        self.abrupt.write_text(marker('proper_preboot', status='00000001'))
        result = analyzer.compare(self.clean, self.abrupt)
        self.assertEqual(result['hardware_recovery'], 'unproven')
        rows = {r['stage']: r for r in result['comparison']}
        self.assertEqual(rows['pre_workspace']['missing_trial'], 'abrupt')
        self.assertIn('mips_status', rows['proper_preboot']['differences'])

    def test_identical_snapshots_still_do_not_prove_recovery(self):
        self.clean.write_text(marker('proper_preboot'))
        self.abrupt.write_text(marker('proper_preboot'))
        self.assertEqual(analyzer.compare(self.clean, self.abrupt)['hardware_recovery'], 'unproven')

    def test_mixed_missing_and_malformed_boots_are_rejected(self):
        for text in (marker('proper_preboot') * 2, marker('post_logo'),
                     marker('proper_preboot') + marker('pre_workspace')[:-6],
                     marker('post_logo') + marker('proper_preboot'),
                     marker('spl_pre_dram', 'unread') * 2 + marker('proper_preboot'),
                     marker('proper_preboot', 'unread')):
            with self.subTest(text=text):
                self.clean.write_text(text)
                with self.assertRaises(ValueError):
                    analyzer.parse(self.clean)

    def test_optional_spl_status_stays_explicitly_unread(self):
        self.clean.write_text(marker('spl_pre_dram', 'unread') +
                              marker('spl_post_dram', 'unread') + marker('proper_preboot'))
        records = analyzer.parse(self.clean)['records']
        self.assertEqual(records[0]['mips_status'], 'unread')


class Isolation(unittest.TestCase):
    def test_existing_output_and_base_are_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, output = root / 'base', root / 'output'
            base.mkdir(); output.mkdir()
            pin = preparer.re.search(r'^UBOOT_SOURCE_COMMIT=([0-9a-f]{40})$',
                                    (preparer.ROOT / 'config/versions.env').read_text(), preparer.re.M)[1]
            (base / '.h713-build-inputs').write_text('source ' + pin + '\n')
            (output / 'keep').write_text('existing evidence')
            before = preparer.tree_digest(root)
            with self.assertRaises(FileExistsError):
                preparer.prepare(base, output)
            self.assertEqual(preparer.tree_digest(root), before)
            with self.assertRaises(ValueError):
                preparer.prepare(base, base / 'nested')
            self.assertEqual(preparer.tree_digest(root), before)

    def test_wrong_source_pin_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.h713-build-inputs').write_text('source ' + '0' * 40 + '\n')
            with self.assertRaises(ValueError):
                preparer.prepare(root, root.parent / (root.name + '-unused'))


if __name__ == '__main__':
    unittest.main()
