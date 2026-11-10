#!/usr/bin/env python3
"""Compare real original/diagnostic workers and negative controls on the host."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
b=load('builder','build-frame-reject-diagnostic.py')
c=load('contract','test-frame-discard-contract.py')


class Diagnostic(unittest.TestCase):
    def test_same_guard_outcomes_and_pair_read_counts_with_trace(self):
        original=c.SOURCE.read_text();changed=b.instrument(original)
        self.assertIn('MODULE_VERSION("'+b.module_version(original)+'");',changed)
        self.assertEqual(c.function(original,'h713_copy_frame'),c.function(changed,'h713_copy_frame'))
        stubs=c.STUBS.replace('#define pr_info(...) ((void)0)',
                            '#define pr_info(...) ((void)0)\n#define pr_info_ratelimited(...) printf(__VA_ARGS__)\nstatic int pair_reads;')
        stubs=stubs.replace('int idx=step%3;return','pair_reads++;int idx=step%3;return')
        main=c.MAIN.replace('    return 0;\n}', '    printf("pair_reads=%d\\n",pair_reads);\n    return 0;\n}')
        with tempfile.TemporaryDirectory() as directory:
            counts={}
            for variant,text in (('original',original),('diagnostic',changed),('bypass',changed)):
                worker=c.function(text,'h713_capture_thread_pair')
                if variant=='bypass':
                    self.assertEqual(worker.count('if (copy_result || pair_after != idx)'),1)
                    worker=worker.replace('if (copy_result || pair_after != idx)','if (0)')
                path=Path(directory)/(variant+'.c');exe=path.with_suffix('')
                path.write_text(stubs+c.function(text,'h713_copy_frame')+'\n'+worker+main)
                subprocess.run(['cc','-std=c11','-O1',str(path),'-o',str(exe)],check=True,capture_output=True)
                for fault in (0,1,2):
                    run=subprocess.run([str(exe),str(fault)],capture_output=True,text=True,timeout=5)
                    with self.subTest(variant=variant,fault=fault):
                        if variant=='bypass' and fault:
                            self.assertNotEqual(run.returncode,0);continue
                        self.assertEqual(run.returncode,0,run.stderr)
                        counts[variant,fault]=run.stdout.split('pair_reads=')[1].strip()
                        if variant=='diagnostic':
                            if fault==0:self.assertNotIn('reject=',run.stdout)
                            elif fault==1:self.assertIn('copy_rc=-11 pair_before=1 pair_after=-2',run.stdout)
                            else:self.assertIn('copy_rc=0 pair_before=1 pair_after=2',run.stdout)
            for fault in (0,1,2):self.assertEqual(counts['original',fault],counts['diagnostic',fault])

    def test_source_pin_and_package_scope(self):
        original=c.SOURCE.read_text()
        with self.assertRaisesRegex(RuntimeError,'differs'):b.instrument(original+'\n')
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'package';manifest=b.build(output)
            self.assertFalse(manifest['installed']);self.assertFalse(manifest['module_built'])
            self.assertFalse(list(output.rglob('*.ko')))
            before={str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
            with self.assertRaises(FileExistsError):b.build(output)
            self.assertEqual(before,{str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()})


if __name__=='__main__':unittest.main()
