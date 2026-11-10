#!/usr/bin/env python3
"""Offline checks of build-kernel-fit-bundle.py's baseline/candidate comparison."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('bundle', Path(__file__).with_name('build-kernel-fit-bundle.py'))
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

COMMON = 'CONFIG_IKCONFIG=y\nCONFIG_RUSTC_SUPPORTS_ARM64=y\n'
NO_RUSTC = 'CONFIG_RUSTC_VERSION=0\nCONFIG_RUSTC_LLVM_VERSION=0\n' + COMMON
# The rustc-specific lines of the production .config built with rustc 1.99 on PATH (2026-11-09).
RUSTC_199 = ('CONFIG_RUSTC_VERSION=109900\nCONFIG_RUSTC_LLVM_VERSION=230101\n'
             'CONFIG_RUSTC_HAS_COERCE_POINTEE=y\nCONFIG_RUSTC_HAS_SPAN_FILE=y\n'
             'CONFIG_RUSTC_HAS_UNNECESSARY_TRANSMUTES=y\nCONFIG_RUSTC_HAS_FILE_WITH_NUL=y\n'
             'CONFIG_RUSTC_HAS_FILE_AS_C_STR=y\nCONFIG_HAVE_CFI_ICALL_NORMALIZE_INTEGERS_RUSTC=y\n' + COMMON)


def work(root, name, config, fit):
    w = Path(root)/name; t = w/'build/linux-x'; t.mkdir(parents=True); (t/'include/config').mkdir(parents=True)
    (t/'.config').write_text(config); (t/'Module.symvers').write_text('symvers')
    (t/'include/config/kernel.release').write_text('6.18.38')
    (w/'build/out').mkdir(); (w/'build/out/h713-kernel-production.fit').write_bytes(fit)
    (w/'build/out'/b.DTB).write_bytes(b'dtb')
    return w


class Bundle(unittest.TestCase):
    def check(self, base_config, cand_config, **kw):
        with tempfile.TemporaryDirectory() as d:
            base = work(d, 'base', base_config, b'old'); cand = work(d, 'cand', cand_config, b'new')
            return b.check(base, cand, hashlib.sha256(b'old').hexdigest(), [], **kw)

    def test_rustc_transition_accepts_exactly_the_probe_symbols(self):
        self.check(RUSTC_199, NO_RUSTC, rustc_transition=True)

    def test_rustc_drift_is_refused_without_the_transition(self):
        with self.assertRaisesRegex(SystemExit, 'unexpected config difference'):
            self.check(RUSTC_199, NO_RUSTC)

    def test_transition_refuses_a_candidate_that_still_has_rustc(self):
        with self.assertRaisesRegex(SystemExit, 'not the rustc probe transition'):
            self.check(RUSTC_199, RUSTC_199, rustc_transition=True)

    def test_transition_refuses_a_baseline_without_rustc(self):
        with self.assertRaisesRegex(SystemExit, 'not the rustc probe transition'):
            self.check(NO_RUSTC, NO_RUSTC, rustc_transition=True)

    def test_transition_does_not_hide_another_config_change(self):
        with self.assertRaisesRegex(SystemExit, 'unexpected config difference'):
            self.check(RUSTC_199, NO_RUSTC + 'CONFIG_LEGACY_PTYS=y\n', rustc_transition=True)


if __name__ == '__main__':
    unittest.main()
