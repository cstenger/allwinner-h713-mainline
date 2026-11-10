#!/usr/bin/env python3
"""Drive update-signal-owner.sh against a synthetic installed generation."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).with_name('update-signal-owner.sh')
SCOPE=['h713-hdmi-signal.ko','h713-ddc-pins.ko','h713-hdmi-signal.py','h713-hdmi-hold-guard','install-startup.sh']
OTHER=['h713-hdmi-receiver.ko','h713-hdmi.scr','firmware/h713/hdmi-audio-dsp.bin']


def sums(root):
    files=sorted(p for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS' and '.new' not in p.name)
    (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))


def tree(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


class Update(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);t=Path(tmp.name)
        self.bundle,self.install,self.state,self.sys,self.hooks=t/'bundle',t/'install',t/'state',t/'sys',t/'hooks'
        for d in (self.install,self.state,self.sys,self.hooks):d.mkdir()
        (self.hooks/'h713-off').write_text('lamp hook')
        for name in OTHER:
            (self.install/name).parent.mkdir(parents=True,exist_ok=True);(self.install/name).write_text('same '+name)
        for name in SCOPE:(self.install/name).write_text('old '+name)
        (self.install/'h713-hdmi-signal.py').chmod(0o755)
        sums(self.install)
        shutil.copytree(self.install,self.bundle)
        for name in SCOPE:(self.bundle/name).write_text('new '+name)
        shutil.copy(SCRIPT,self.bundle/'update-signal-owner.sh')
        sums(self.bundle)

    def run_update(self):
        env={'PATH':'/usr/bin:/bin','H713_HDMI_INSTALL':str(self.install),'H713_HDMI_STATE':str(self.state),'H713_HDMI_SYSMODULE':str(self.sys),'H713_HDMI_SHUTDOWN_HOOKS':str(self.hooks)}
        return subprocess.run(['sh',str(self.bundle/'update-signal-owner.sh')],env=env,capture_output=True,text=True)

    def assert_refused(self,reason):
        before=tree(self.install),tree(self.hooks);r=self.run_update()
        self.assertNotEqual(r.returncode,0);self.assertIn(reason,r.stderr);self.assertIn('nothing changed',r.stderr)
        self.assertEqual((tree(self.install),tree(self.hooks)),before);self.assertEqual(list(self.state.iterdir()),[])

    def test_replaces_only_scope_keeps_backup_and_is_idempotent(self):
        others={n:(self.install/n).read_bytes() for n in OTHER}
        r=self.run_update();self.assertEqual(r.returncode,0,r.stderr)
        for name in SCOPE:self.assertEqual((self.install/name).read_text(),'new '+name)
        self.assertEqual((self.install/'SHA256SUMS').read_bytes(),(self.bundle/'SHA256SUMS').read_bytes())
        self.assertEqual({n:(self.install/n).read_bytes() for n in OTHER},others)
        self.assertEqual(oct((self.install/'h713-hdmi-signal.py').stat().st_mode&0o777),'0o755')
        hook=self.hooks/'h713-hdmi-hold-guard'
        self.assertEqual(hook.read_text(),'new h713-hdmi-hold-guard');self.assertEqual(oct(hook.stat().st_mode&0o777),'0o755')
        self.assertEqual((self.hooks/'h713-off').read_text(),'lamp hook')
        backup,=self.state.iterdir()
        self.assertEqual({p.name:p.read_text() for p in backup.iterdir() if p.name!='SHA256SUMS'},{n:'old '+n for n in SCOPE})
        subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=self.install,check=True)
        r=self.run_update();self.assertIn('already current',r.stdout);self.assertEqual(len(list(self.state.iterdir())),1)

    def test_refuses_when_an_out_of_scope_file_differs(self):
        (self.bundle/'h713-hdmi-receiver.ko').write_text('changed receiver');sums(self.bundle)
        self.assert_refused('installed h713-hdmi-receiver.ko differs from bundle')

    def test_refuses_a_failed_loaded_owner(self):
        (self.sys/'h713_hdmi_signal/parameters').mkdir(parents=True);(self.sys/'h713_hdmi_signal/parameters/failed').write_text('Y\n')
        self.assert_refused('loaded signal owner has failed')

    def test_refuses_a_corrupt_bundle_or_installed_generation(self):
        (self.bundle/'h713-hdmi-signal.ko').write_text('tampered')
        self.assert_refused('bundle checksum mismatch')
        self.setUp();(self.install/'h713-hdmi.scr').write_text('edited in place')
        self.assert_refused('installed generation fails its own checksums')

    def test_restores_a_missing_or_edited_hook_copy(self):
        self.assertEqual(self.run_update().returncode,0)
        for damage in ('edit','remove'):
            with self.subTest(damage=damage):
                hook=self.hooks/'h713-hdmi-hold-guard'
                hook.write_text('edited') if damage=='edit' else hook.unlink()
                r=self.run_update();self.assertEqual(r.returncode,0,r.stderr);self.assertNotIn('already current',r.stdout)
                self.assertEqual(hook.read_text(),'new h713-hdmi-hold-guard')

    def test_completes_an_interrupted_update(self):
        (self.install/'h713-hdmi-signal.ko').write_text('new h713-hdmi-signal.ko')  # first file landed, SUMS still old
        r=self.run_update();self.assertEqual(r.returncode,0,r.stderr)
        subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=self.install,check=True)


if __name__=='__main__':unittest.main()
