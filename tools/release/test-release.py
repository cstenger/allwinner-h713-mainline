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

    def test_host_rustc_in_kernel_config_is_refused(self):
        clean='CONFIG_RUSTC_VERSION=0\nCONFIG_RUSTC_LLVM_VERSION=0\nCONFIG_RUSTC_SUPPORTS_ARM64=y\nCONFIG_HAVE_RUST=y\n'
        self.assertEqual(b.rustc_probe_leaks(clean),[])
        # The eight lines rustc 1.99 put into the production .config (2026-11-09).
        host=('CONFIG_RUSTC_VERSION=109900\nCONFIG_RUSTC_LLVM_VERSION=230101\nCONFIG_RUSTC_HAS_COERCE_POINTEE=y\n'
              'CONFIG_RUSTC_HAS_SPAN_FILE=y\nCONFIG_RUSTC_HAS_UNNECESSARY_TRANSMUTES=y\nCONFIG_RUSTC_HAS_FILE_WITH_NUL=y\n'
              'CONFIG_RUSTC_HAS_FILE_AS_C_STR=y\nCONFIG_HAVE_CFI_ICALL_NORMALIZE_INTEGERS_RUSTC=y\n')
        self.assertEqual(b.rustc_probe_leaks(host),host.splitlines()+['missing CONFIG_RUSTC_VERSION=0'])
        for line in host.splitlines()[1:]:
            self.assertEqual(len(b.rustc_probe_leaks(clean+line+'\n')),1,line)
        self.assertEqual(b.rustc_probe_leaks(clean+'CONFIG_RUST=y\n'),['CONFIG_RUST=y'])
        self.assertEqual(b.rustc_probe_leaks('CONFIG_RUSTC_SUPPORTS_ARM64=y\n'),['missing CONFIG_RUSTC_VERSION=0'])

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
            path.write_text(json.dumps(data));self.assertEqual(b.calibration(path)['hdmi_audio_delay_seconds'],data['hdmi_audio_delay_seconds'])
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
            self.assertIn('--boot-handoff',(units/'h713-hdmi-prepare.service').read_text())
            self.assertIn('ExecStart=/usr/bin/true',(units/'h713-hdmi-capture.service').read_text())
            self.assertTrue((units/'multi-user.target.wants/h713-hdmi-readvertise.service').is_symlink())
            elog=units/'h713-mips-elog-level.service'
            self.assertTrue((units/'multi-user.target.wants/h713-mips-elog-level.service').is_symlink())
            self.assertIn('mips-shell.py --elog-level 2',elog.read_text())
            self.assertIn('After=h713-hdmi-capture.service',elog.read_text())
            self.assertFalse((units/'multi-user.target.wants/h713-hdmi-video.service').exists())
            self.assertFalse((units/'multi-user.target.wants/h713-hdmi-prepare.service').exists())
            self.assertEqual((units/'h713-hdmi-prepare.service').read_bytes(),
                             (out/'usr/lib/h713-hdmi/h713-hdmi-prepare.service').read_bytes())
            self.assertIn('Requires=h713-hdmi-prepare.service',
                          (units/'h713-hdmi-capture.service').read_text())
            delay=json.loads((b.ROOT/'config/hy200-ddr3-calibration.json').read_text())['hdmi_audio_delay_seconds']
            self.assertIn('H713_HDMI_AUDIO_DELAY_SEC='+delay+'\n',(out/'etc/default/h713-hdmi-speaker').read_text())
            self.assertFalse((out/'usr/lib/h713-hdmi-speaker/hdmi-speaker.c').exists())
            self.assertIn('== 4d2',(out/'usr/lib/h713-hdmi/h713-hdmi.cmd').read_text())

    def test_projector_payload_has_the_runtime_without_a_startup_script(self):
        # The V2's U-Boot (boot-v2) owns the launch; only the bench board ships a script.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);dsp=root/'dsp.bin';dsp.write_bytes(b'fixture')
            modules={}
            for kind,name in [('receiver','h713-hdmi-receiver'),('audio','h713-hdmi-audio'),
                              ('signal','h713-hdmi-signal'),('ddc','h713-ddc-pins'),('video','h713-hdmi-v4l2')]:
                path=root/(name+'.ko');path.write_bytes(name.encode());modules[kind]=path
            out=root/'overlay';out.mkdir();b.hdmi_payload(out,modules,dsp,'0.115')
            units=out/'etc/systemd/system'
            for unit in ('h713-hdmi-capture','h713-hdmi-signal','h713-hdmi-ring','h713-hdmi-health-ack'):
                self.assertTrue((units/'multi-user.target.wants'/(unit+'.service')).is_symlink())
            self.assertEqual((out/'usr/lib/h713-hdmi-video/h713-hdmi-v4l2.ko').read_bytes(),b'h713-hdmi-v4l2')
            self.assertEqual((out/'usr/lib/h713-hdmi/firmware/h713/hdmi-audio-dsp.bin').read_bytes(),b'fixture')
            self.assertIn('H713_HDMI_AUDIO_DELAY_SEC=0.115\n',(out/'etc/default/h713-hdmi-speaker').read_text())
            self.assertEqual(list(out.rglob('h713-hdmi.scr'))+list(out.rglob('h713-hdmi.cmd')),[])
            self.assertFalse((out/'etc/h713-keystone.conf').exists())


    def test_v2_calibration_is_explicitly_without_keystone(self):
        v2=b.ROOT/'config/hy200-v2-calibration.json'
        cal=b.calibration(v2,'v2')
        self.assertEqual(cal['hdmi_audio_delay_seconds'],'0.115')
        self.assertIsNone(cal['keystone'])
        self.assertTrue((b.ROOT/cal['evidence']).is_file())
        with self.assertRaisesRegex(ValueError,'wrong calibration board'):b.calibration(v2,'ddr3')
        with self.assertRaisesRegex(ValueError,'wrong calibration board'):
            b.calibration(b.ROOT/'config/hy200-ddr3-calibration.json','v2')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'calibration.json'
            data=json.loads(v2.read_text())
            for keystone in ({'bias_y':'0'},{},'none'):
                path.write_text(json.dumps(dict(data,keystone=keystone)))
                with self.subTest(keystone=keystone),self.assertRaisesRegex(ValueError,'keystone'):b.calibration(path,'v2')
            path.write_text(json.dumps({k:v for k,v in data.items() if k!='keystone'}))
            with self.assertRaisesRegex(ValueError,'keystone'):b.calibration(path,'v2')
            # The bench board still needs its measured pose.
            a1=json.loads((b.ROOT/'config/hy200-ddr3-calibration.json').read_text())
            path.write_text(json.dumps(dict(a1,keystone=None)))
            with self.assertRaisesRegex(ValueError,'lens calibration required'):b.calibration(path,'ddr3')

    def test_v2_vendor_lock_is_the_bench_bytes_without_boot_assets(self):
        a1=json.loads((b.ROOT/'config/production-vendor.json').read_text())
        v2=json.loads((b.ROOT/'config/production-vendor-v2.json').read_text())
        self.assertEqual(v2['board'],b.BOARDS['v2']['name'])
        self.assertEqual(set(v2['files']),{n for n in a1['files'] if not n.startswith('boot/')})
        for name,pin in v2['files'].items():
            self.assertEqual(pin,a1['files'][name],name)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in a1['files']:
                (root/name).parent.mkdir(parents=True,exist_ok=True)
            # An A1 vendor directory is not a V2 one: the lock names the exact set.
            with self.assertRaisesRegex(ValueError,'missing vendor file'):b.vendor_inputs(root,'v2')

    def test_v2_overlay_omits_bench_only_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);dsp=root/'dsp.bin';dsp.write_bytes(b'fixture')
            modules={}
            for kind,name in [('receiver','h713-hdmi-receiver'),('audio','h713-hdmi-audio'),
                              ('signal','h713-hdmi-signal'),('ddc','h713-ddc-pins'),('video','h713-hdmi-v4l2')]:
                path=root/(name+'.ko');path.write_bytes(name.encode());modules[kind]=path
            cal=b.calibration(b.ROOT/'config/hy200-v2-calibration.json','v2')
            out=root/'overlay';b.v2_overlay(out,modules,dsp,cal)
            self.assertEqual([p for p in out.rglob('*') if 'elog' in p.name],[])
            self.assertEqual(list(out.rglob('h713-hdmi.scr'))+list(out.rglob('h713-hdmi.cmd')),[])
            self.assertFalse((out/'etc/h713-keystone.conf').exists())
            self.assertIn('H713_HDMI_AUDIO_DELAY_SEC=0.115\n',(out/'etc/default/h713-hdmi-speaker').read_text())
            self.assertEqual(json.loads((out/'usr/share/h713-release/calibration.json').read_text()),cal)
            self.assertTrue((out/'.h713-release-overlay').is_file())
            self.assertTrue((out/'etc/systemd/system/multi-user.target.wants/h713-hdmi-health-ack.service').is_symlink())

    def _rootfs_fixture(self,root,extra=()):
        tree=root/'tree'
        if tree.exists():shutil.rmtree(tree)
        names=['usr/bin/python3','usr/bin/pw-loopback','usr/bin/pw-dump','usr/bin/pw-cli',
               'usr/local/bin/h713-play','usr/local/bin/gst-plane-play',
               'usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so',
               'usr/lib/h713-hdmi-speaker/alsa-ctl','usr/lib/h713-hdmi-speaker/pipewire-speaker.py',
               'etc/default/h713-hdmi-speaker','usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard',
               'usr/lib/h713-hdmi-video/h713-hdmi-v4l2.ko','usr/lib/h713-hdmi/firmware/h713/hdmi-audio-dsp.bin']
        names+=['usr/lib/h713-hdmi/'+n+'.ko' for n in ('h713-hdmi-receiver','h713-hdmi-audio','h713-hdmi-signal','h713-ddc-pins')]
        names+=['usr/lib/'+n+'/SHA256SUMS' for n in ('h713-hdmi','h713-hdmi-health','h713-hdmi-video','h713-hdmi-speaker')]
        for name in [*names,*extra]:
            path=tree/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('' if name.endswith('SHA256SUMS') else 'x')
        tar=root/'rootfs.tar'
        subprocess.run(['tar','-C',str(tree),'-cf',str(tar),'.'],check=True)
        return tar

    def test_v2_rootfs_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for board in ('ddr3','v2'):
                self.assertEqual(b.verify_rootfs(self._rootfs_fixture(root),board)['status'],'PASS production payload checks')
            # The plain defconfig's AV1 probe is what failed the V2 images.
            probe=self._rootfs_fixture(root,['usr/lib/modules/6.18.38/kernel/drivers/misc/sunxi-h713-av1-probe.ko'])
            for board in ('ddr3','v2'):
                with self.subTest(board=board),self.assertRaisesRegex(ValueError,'diagnostic kernel module'):
                    b.verify_rootfs(probe,board)
            for extra in ('etc/systemd/system/h713-mips-elog-level.service',
                          'etc/systemd/system/multi-user.target.wants/h713-mips-elog-level.service',
                          'usr/lib/h713-hdmi/h713-mips-elog-level.service',
                          'etc/h713-keystone.conf','usr/lib/h713-hdmi/h713-hdmi.scr'):
                tar=self._rootfs_fixture(root,[extra])
                with self.subTest(extra=extra),self.assertRaisesRegex(ValueError,'shipped'):b.verify_rootfs(tar,'v2')
                b.verify_rootfs(tar,'ddr3')

    def test_rauc_keys_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaisesRegex(ValueError,'ca.cert.pem'):b.rauc_keys(root)
            for name in ('ca.cert.pem','signer.cert.pem','signer.key.pem'):(root/name).write_text(name)
            self.assertEqual(set(b.rauc_keys(root)),{'ca.cert.pem','signer.cert.pem','signer.key.pem'})
            (root/'signer.key.pem').write_text('')
            with self.assertRaisesRegex(ValueError,'signer.key.pem'):b.rauc_keys(root)

    @unittest.skipUnless(shutil.which('mkfs.vfat') and shutil.which('mcopy') and
                         (b.ROOT/'build/uboot-lpddr3/tools/mkimage').is_file(),
                         'mtools, dosfstools and a built LPDDR3 mkimage required')
    def test_v2_boot_image_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fit=root/'kernel.fit';fit.write_bytes(os.urandom(4096))
            env=dict(os.environ,SOURCE_DATE_EPOCH='1793693083',H713_BUILD_DIR=str(b.ROOT/'build'))
            images=[]
            for name,epoch in (('first','1793693083'),('second','1793693083'),('control','1793693084')):
                image=root/(name+'.vfat')
                subprocess.run([b.ROOT/'tools/v2-boot-image.sh',fit,image],check=True,
                               env=dict(env,SOURCE_DATE_EPOCH=epoch),capture_output=True)
                images.append(b.sha(image))
            self.assertEqual(images[0],images[1])
            # Control: the comparison sees a one-second difference in the build time.
            self.assertNotEqual(images[0],images[2])


if __name__=='__main__':unittest.main()
