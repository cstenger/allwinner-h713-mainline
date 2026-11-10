#!/usr/bin/env python3
"""The kernel .config (embedded in the FIT by IKCONFIG) must not depend on host rustc.

Runs `tools/build/build.sh kernel-config` with KERNEL_CONFIG=production in a
throwaway H713_BUILD_DIR (the shared kernel trees are not touched; the pinned
tarball comes from the normal cache) three times:

  1. a fake rustc 1.99 first on PATH        -> .config A, the probe says "none"
  2. no rustc anywhere on PATH              -> .config B, must equal A
  3. control: H713_KERNEL_RUSTC=<fake>      -> .config C, must carry the fake's
     RUSTC_VERSION, proving the fake really is probed. Without this a broken
     fake would make 1 == 2 pass trivially.

Takes about a minute (extract + patch); needs the kernel tarball in the cache
and fails, not skips, without it.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get('H713_BUILD_DIR') or ROOT/'build')
FAKE_RUSTC = '''#!/bin/sh
# Answers like rustc 1.99 and accepts every option, so every Kconfig probe of it succeeds.
case "$*" in
  *--version*--verbose*|*-vV*) printf 'rustc 1.99.0 (b940084d7 2026-09-28)\\nLLVM version: 23.1.1\\n' ;;
  *--version*) echo 'rustc 1.99.0 (b940084d7 2026-09-28)' ;;
esac
exit 0
'''
HOST_LINES = re.compile(r'^CONFIG_(?:RUSTC_VERSION|RUSTC_LLVM_VERSION|RUSTC_HAS_\w+|\w+_RUSTC)=.*$', re.M)


def without_rustc(path):
    return os.pathsep.join(d for d in path.split(os.pathsep) if d and not (Path(d)/'rustc').exists())


class KernelRustcProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tarballs = sorted((BUILD/'cache').glob('linux-*.tar.xz'))
        if not tarballs:
            raise AssertionError('no kernel tarball in '+str(BUILD/'cache')+'; run tools/build/build.sh kernel once')
        cls.work = Path(tempfile.mkdtemp(prefix='test-kernel-rustc-probe.', dir=BUILD))
        (cls.work/'cache').mkdir()
        for t in tarballs: (cls.work/'cache'/t.name).symlink_to(t)
        cls.bin = cls.work/'fake-bin'; cls.bin.mkdir()
        (cls.bin/'rustc').write_text(FAKE_RUSTC); (cls.bin/'rustc').chmod(0o755)
        base = without_rustc(os.environ['PATH'])
        env = {k: v for k, v in os.environ.items() if k != 'H713_KERNEL_RUSTC'}
        env.update(H713_BUILD_DIR=str(cls.work), KERNEL_CONFIG='production', LC_ALL='C')
        cls.configs = {}
        for name, extra in (('fake-on-path', dict(PATH=str(cls.bin)+os.pathsep+base)),
                            ('no-rustc', dict(PATH=base)),
                            ('control', dict(PATH=base, H713_KERNEL_RUSTC=str(cls.bin/'rustc')))):
            run = subprocess.run([ROOT/'tools/build/build.sh', 'kernel-config'], env=dict(env, **extra),
                                 capture_output=True, text=True)
            if run.returncode:
                raise AssertionError(name+' failed:\n'+run.stdout[-3000:]+run.stderr[-3000:])
            tree = subprocess.check_output([ROOT/'tools/build/build.sh', 'kernel-tree'],
                                           env=dict(env, **extra), text=True).strip()
            cls.configs[name] = (Path(tree)/'.config').read_text()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_control_shows_the_fake_rustc_is_probed(self):
        lines = HOST_LINES.findall(self.configs['control'])
        print('control (probe not neutralised):', *lines, sep='\n  ', file=sys.stderr)
        self.assertIn('CONFIG_RUSTC_VERSION=109900', lines)
        self.assertIn('CONFIG_RUSTC_LLVM_VERSION=230101', lines)
        self.assertTrue(any(l.startswith('CONFIG_RUSTC_HAS_') for l in lines))

    def test_config_is_independent_of_host_rustc(self):
        a, b = self.configs['fake-on-path'], self.configs['no-rustc']
        print('fake on PATH:', *HOST_LINES.findall(a), sep='\n  ', file=sys.stderr)
        self.assertEqual(HOST_LINES.findall(a), ['CONFIG_RUSTC_VERSION=0', 'CONFIG_RUSTC_LLVM_VERSION=0'])
        self.assertEqual(a, b)
        self.assertIn('CONFIG_IKCONFIG=y', a.splitlines())


if __name__ == '__main__':
    unittest.main()
