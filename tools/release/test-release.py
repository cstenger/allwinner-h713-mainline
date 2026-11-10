#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('release',Path(__file__).with_name('build.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


class ReleaseTests(unittest.TestCase):
    def test_signal_module_is_the_qualified_event_pulse_build(self):
        root=Path(b.ROOT)
        with tempfile.TemporaryDirectory() as directory:
            header=Path(directory)/'edid-trial-code.h'
            subprocess.run(['python3',root/'tools/hdmi/make-edid-trial-code.py',*b.SIGNAL_SCP_FLAGS,
                            '--edid',root/'tools/hdmi/fixtures/hdmi-audio-edid.hex',header],check=True,capture_output=True)
            text=header.read_text()
        for define in ('#define EDID_HPD_PULSE 1','#define EDID_SCAN_BYTES 1','#define EDID_SCAN_ARM 0x06840094',
                       '#define EDID_SCAN_BUSY ','#define EDID_CHECK_OFFSET ','#define EDID_EXT_OFFSET '):
            self.assertIn(define,text)
        for absent in ('EDID_HPD_DIAGNOSTIC','EDID_DDC_DIAGNOSTIC','EDID_SAMPLER_OFFSET','EDID_SCAN_WORDS','EDID_INITIAL_'):
            self.assertNotIn(absent,text)
        source=(root/'modules/hdmi-signal/h713-hdmi-signal.c').read_text()
        self.assertIn('#elif defined(EDID_HPD_PULSE) && defined(EDID_SCAN_BUSY)\n',source)
        self.assertIn('MODULE_VERSION("hpd-event-v1");',source)
        policy=(root/'tools/hdmi/h713-hdmi-readvertise.py').read_text()
        self.assertIn("EVENT_VERSIONS = ('hpd-event-v1',)",policy)
        self.assertIn("ddc_activity('source_lost', clock, rearm=True)",policy)
        self.assertNotIn('DIAGNOSTIC_DDC_ONLY = True',policy)
        self.assertNotIn('DIAGNOSTIC_HPD_ONLY = True',policy)

    def test_generated_module_outputs_do_not_become_source_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);module=root/'modules/hdmi-signal';module.mkdir(parents=True)
            subprocess.run(['git','init','-q',str(root)],check=True)
            for name in ('Makefile','signal.c','protocol.h'):(module/name).write_text('source\n')
            subprocess.run(['git','-C',str(root),'add','modules'],check=True)
            with patch.object(b,'ROOT',root):
                before={p.name:b.sha(p) for p in b.module_sources('hdmi-signal')}
                for name in ('signal.mod.c','edid-trial-code.h','untracked-experiment.c'):
                    (module/name).write_text('leftover generated or experimental payload\n')
                self.assertEqual({p.name:b.sha(p) for p in b.module_sources('hdmi-signal')},before)
                self.assertEqual(set(before),{'Makefile','signal.c','protocol.h'})

    @unittest.skipUnless(shutil.which('mke2fs'), 'mke2fs required for filesystem check')
    def test_tar_populated_ext4_is_independent_of_creation_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tree=root/'tree';tree.mkdir()
            (tree/'räksmörgås').write_text('release fixture\n')
            subprocess.run(['tar','--sort=name','--mtime=@1793693083','--numeric-owner',
                            '-C',str(tree),'-cf',str(root/'root.tar'),'.'],check=True)
            env=dict(os.environ,E2FSPROGS_FAKE_TIME='1793693083',LC_ALL='C.UTF-8')
            for name in ['first','second']:
                image=root/(name+'.ext4')
                with image.open('wb') as f:f.truncate(32*1024*1024)
                subprocess.run(['mke2fs','-q','-F','-t','ext4','-U','6ad2069c-83c6-5dd8-a2f8-97b59c251c82',
                    '-E','hash_seed=6ad2069c-83c6-5dd8-a2f8-97b59c251c82,lazy_itable_init=0,lazy_journal_init=0',
                    '-d',str(root/'root.tar'),str(image)],check=True,env=env)
            self.assertEqual(b.sha(root/'first.ext4'),b.sha(root/'second.ext4'))

    def test_accepted_startup_bytes_unchanged_by_parameterization(self):
        startup=b.load_module(b.ROOT/'tools/hdmi/build-startup.py')
        # The pre-0004 two-launch script, still reproducible on request.
        self.assertEqual(hashlib.sha256(startup.legacy_image(startup.script(single_launch=False,early_panel_off=False).encode())).hexdigest(),
                         'fcea3a9589432f9b44781178d70433486aac5872a618970039b3326744e7fe7b')
        # The single-launch script installed 2026-11-06, built for that kernel
        # (FIT 0x7428ec, DTB 0x876a), byte for byte.
        self.assertEqual(hashlib.sha256(startup.script(fit_size=0x7428ec,fdt_size=0x876a,early_panel_off=False).encode()).hexdigest(),
                         'd2e8cb7a2744c0abb8bce97a441a75ff05d03c0a1a0df7959f215d3cd28e7ad2')
        # The default: single launch + early panel off, installed 2026-11-09.
        self.assertEqual(hashlib.sha256(startup.script(fit_size=0x7428ec,fdt_size=0x876a).encode()).hexdigest(),
                         'b2ea58fed3fe8d4b242687c663390d4a384a4e06b78a3ac838927d3ba9472114')
        self.assertIn('h713_disp panel-off',startup.script())
        self.assertIn('h713_disp auto 0x34 logo comm-trace',startup.script())
        changed=startup.script(fit_size=0x123456,fdt_size=0x7890)
        self.assertIn('itest ${filesize} == 123456',changed)
        self.assertIn('itest ${hdmi_fdt_size} == 7890',changed)
        self.assertNotIn('itest ${filesize} == 76f3d4',changed)

    def test_wrong_vendor_payload_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaisesRegex(ValueError,'missing vendor file'):b.vendor_inputs(root)
            first=next(iter(json.loads((b.ROOT/'config/production-vendor.json').read_text())['files']))
            file=root/first;file.parent.mkdir(parents=True);file.write_bytes(b'wrong firmware')
            with self.assertRaisesRegex(ValueError,'vendor hash mismatch'):b.vendor_inputs(root)

    def test_calibration_cannot_inject_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'calibration.json'
            data=json.loads((b.ROOT/'config/hy200-ddr3-calibration.json').read_text())
            path.write_text(json.dumps(data));self.assertEqual(b.calibration(path)['hdmi_audio_delay_seconds'],'0.040')
            for value in ['0.04; reboot', '-1', '2', 'NaN', '0\n1']:
                data['hdmi_audio_delay_seconds']=value;path.write_text(json.dumps(data))
                with self.subTest(value=value),self.assertRaises(ValueError):b.calibration(path)

    def test_overlay_has_runtime_units_and_no_bench_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vendor=root/'vendor';(vendor/'hdmi').mkdir(parents=True)
            (vendor/'hdmi/hdmi-audio-dsp.bin').write_bytes(b'fixture')
            modules={}
            for kind,name in [('receiver','h713-hdmi-receiver'),('audio','h713-hdmi-audio'),
                              ('signal','h713-hdmi-signal'),('ddc','h713-ddc-pins'),('video','h713-hdmi-v4l2')]:
                path=root/(name+'.ko');path.write_bytes(b'module');modules[kind]=path
            fit=root/'kernel.fit';fit.write_bytes(b'x'*1234);dtb=root/'kernel.dtb';dtb.write_bytes(b'y'*567)
            cal=b.calibration(b.ROOT/'config/hy200-ddr3-calibration.json')
            out=root/'overlay';b.overlay(out,modules,vendor,fit,dtb,cal)
            units=out/'etc/systemd/system'
            self.assertIn('--boot-handoff',(units/'h713-hdmi-capture.service').read_text())
            self.assertTrue((units/'multi-user.target.wants/h713-hdmi-readvertise.service').is_symlink())
            self.assertFalse((units/'multi-user.target.wants/h713-hdmi-video.service').exists())
            self.assertFalse((units/'multi-user.target.wants/h713-hdmi-prepare.service').exists())
            self.assertEqual((units/'h713-hdmi-prepare.service').read_bytes(),
                             (out/'usr/lib/h713-hdmi/h713-hdmi-prepare.service').read_bytes())
            self.assertIn('Requires=h713-hdmi-prepare.service',
                          (units/'h713-hdmi-capture.service').read_text())
            self.assertIn('H713_HDMI_AUDIO_DELAY_SEC=0.040',(out/'etc/default/h713-hdmi-speaker').read_text())
            self.assertFalse((out/'usr/lib/h713-hdmi-speaker/hdmi-speaker.c').exists())
            self.assertIn('== 4d2',(out/'usr/lib/h713-hdmi/h713-hdmi.cmd').read_text())


if __name__=='__main__':unittest.main()
