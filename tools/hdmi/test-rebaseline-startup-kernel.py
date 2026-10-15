#!/usr/bin/env python3
"""Drive rebaseline-startup-kernel.sh against a fake boot FAT and state dir."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).with_name('rebaseline-startup-kernel.sh')


class Rebaseline(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);t=Path(tmp.name)
        self.fat,self.state=t/'fat',t/'state';self.fat.mkdir();self.state.mkdir()
        self.fit=self.fat/'h713-kernel.fit'
        self.fit.write_bytes(b'old kernel');self.old=hashlib.sha256(b'old kernel').hexdigest()
        (self.state/'kernel.sha256').write_text(f'{self.old}  {self.fit}\n')
        self.new=hashlib.sha256(b'new kernel').hexdigest()

    def run_it(self,want):
        env={'PATH':'/usr/bin:/bin','H713_HDMI_STATE':str(self.state),'H713_BOOT_FAT':str(self.fat)}
        return subprocess.run(['sh',str(SCRIPT),want],env=env,capture_output=True,text=True)

    def pin(self):return (self.state/'kernel.sha256').read_text()

    def test_moves_the_pin_to_the_installed_fit_and_keeps_the_old_one(self):
        self.fit.write_bytes(b'new kernel')
        r=self.run_it(self.new);self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue(self.pin().startswith(self.new))
        kept=[p for p in self.state.iterdir() if p.name.startswith('kernel.sha256.')]
        self.assertEqual(len(kept),1);self.assertTrue(kept[0].read_text().startswith(self.old))
        subprocess.run(['sha256sum','-c','--quiet',str(self.state/'kernel.sha256')],check=True)
        r=self.run_it(self.new);self.assertIn('already current',r.stdout)
        self.assertEqual(len([p for p in self.state.iterdir() if p.name.startswith('kernel.sha256.')]),1)

    def test_refuses_when_the_fat_does_not_hold_the_expected_fit(self):
        before=self.pin()
        r=self.run_it(self.new) # FAT still has the old kernel
        self.assertNotEqual(r.returncode,0);self.assertIn('not the expected',r.stderr)
        self.assertEqual(self.pin(),before);self.assertEqual(len(list(self.state.iterdir())),1)

    def test_refuses_malformed_checksums(self):
        self.fit.write_bytes(b'new kernel')
        for bad in ('',self.new.upper(),self.new[:-1],self.new+'0','g'*64):
            with self.subTest(bad=bad):
                r=self.run_it(bad);self.assertNotEqual(r.returncode,0)
                self.assertTrue(self.pin().startswith(self.old))


if __name__=='__main__':unittest.main()
