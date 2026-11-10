#!/usr/bin/env python3
"""Build an isolated owner module and RAM-only cold script; never accesses board."""
import argparse,hashlib,importlib.util,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
KERNEL=ROOT/'build/linux-6.18.38-edffad3c91a035b25a5c2a7df05ef63af488d7e89c286a29c7efa9aaba677efc'
INSTALLED=ROOT/'build/hdmi-reset-baseline-2026-10-20/artifacts/installed'
SOURCES={'h713-hdmi-pcm.c':'0dc33b3ca0fb6bcb61df30b8d9009587ee833849f9a7c18af1f8b8dcae856e1a','h713-hdmi-dsp.c':'466baed82dcb9df4ba58ee3aafd2b23e9172460b51c0739f713e7cfd4d024be2','h713-hdmi-tvfe.c':'4a58038dff996db65fbdafd1c1ad368a8082bfa16b8a8c86f1b879ec635c23d7'}
FIT_SHA='0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70'
SCRIPT_SHA='298fb56d6525e4984d75fd2a0dbe998dd6dba7e813393dd798a4a32371de99fb'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def replace_once(s,old,new):
    if s.count(old)!=1:raise ValueError('ambiguous source anchor: '+old[:70])
    return s.replace(old,new)
def cold_script(source):
    # Keep only the proven cold branch. No warm fallback can launch a logo.
    head,body=source.split('if itest.l *0x07090118 != 0; then\n',1)
    cold=body.split('\nelse\n',1)[1]
    assert cold.endswith('fi\n')
    cold=cold[:-3]
    source=head+'if itest.l *0x07090118 == 0; then\n'+cold+'else echo H713 OWNER cold latch required; false; fi\n'
    source=source.replace('gpio set PB5','gpio clear PB5')
    args='console=ttyS0,115200 console=tty0 earlycon root=/dev/mmcblk0p26 rootwait rootfstype=ext4 rw net.ifnames=0 panic=0 clk_ignore_unused pd_ignore_unused cma=128M loglevel=7 systemd.mask=h713-hdmi-capture.service systemd.mask=h713-hdmi-signal.service systemd.mask=h713-hdmi-speaker.service h713_owner_boundary=1'
    prefix='fdt set /chosen h713,dsp-owner-boundary-v1 <0x4f574e31> && setenv bootargs '+args+' && '
    return replace_once(source,'bootm 0x50000000 - 0x4f000000',prefix+'bootm 0x50000000 - 0x4f000000')
def build(output):
    if output.exists():raise FileExistsError(output)
    assert sha(KERNEL/'Module.symvers')=='c70895af49e62c1821f8a1e1e22f518b365761f256f9842eb59a528107356f70'
    assert sha(KERNEL/'.config')=='1b2b9392fd8801b8199e20c6e09638b15b80efd77b866b5d237daa4d98ea8522'
    assert sha(KERNEL/'arch/arm64/boot/Image')=='ada92f56dd892eab8c4a4bf76e6d92ce609e6e620daccf8de2b419c5aae35d29'
    assert (KERNEL/'include/config/kernel.release').read_text().strip()=='6.18.38'
    assert '#1 SMP Fri Oct 16 15:44:49 PDT 2026' in (KERNEL/'include/generated/utsversion.h').read_text()
    assert sha(ROOT/'build/out/h713-kernel.fit')==FIT_SHA
    assert sha(INSTALLED/'h713-hdmi.cmd')==SCRIPT_SHA
    for n,h in SOURCES.items():assert sha(ROOT/'modules/hdmi-audio'/n)==h,n
    output.mkdir(parents=True);src=output/'src/hdmi-audio';src.mkdir(parents=True)
    for p in (ROOT/'modules/hdmi-audio').iterdir():
        if p.suffix in ('.c','.h') and not p.name.endswith('.mod.c'):shutil.copyfile(p,src/p.name)
    receiver=output/'src/hdmi-receiver';receiver.mkdir()
    shutil.copyfile(ROOT/'modules/hdmi-receiver/h713-receiver.h',receiver/'h713-receiver.h')
    headers=output/'src/hdmi-dsp-probe';headers.mkdir()
    for n in ('h713-dsp-lock.h','h713-dsp-completion.h'):shutil.copyfile(ROOT/'modules/hdmi-dsp-probe'/n,headers/n)
    for n in ('observer.inc','audiotop.inc'):shutil.copyfile(HERE/'dsp-owner-boundary'/n,src/('owner-'+n))
    p=src/'h713-hdmi-dsp.c';s=p.read_text();s=replace_once(s,'void h713_hdmi_dsp_release(void)','\n#include "owner-observer.inc"\n\nvoid h713_hdmi_dsp_release(void)');p.write_text(s)
    p=src/'h713-hdmi-pcm.c';s=p.read_text()
    s=replace_once(s,'static int verify_stock_irqs(void)','int h713_owner_health(u32 *ctl,u32 *cfg);\nint h713_owner_audiotop(unsigned operation);\n#include "owner-audiotop.inc"\n\nstatic int verify_stock_irqs(void)')
    s=replace_once(s,'\tif (!armed || !live_source3 || !receiver_powered) {','\tret = h713_owner_init_check();\n\tif (ret) return ret;\n\tif (!armed || !live_source3 || !receiver_powered) {')
    s=replace_once(s,'\twritel(audio_top_saved_ctl | 0x700, audio_top + 0x0);','\tif (audio_top_saved_ctl || audio_top_saved_cfg) { ret = -EPERM; goto fail; }\n\twritel(audio_top_saved_ctl | 0x700, audio_top + 0x0);')
    s=replace_once(s,'\tret = register_pcm();','\t/* Bench has no PCM device or userspace stream. */\n\tret = h713_owner_pin();')
    # Keep the unreachable registration helper for minimal source delta; mark unused.
    s=s.replace('static int register_pcm(void)','static int __maybe_unused register_pcm(void)')
    s=replace_once(s,'registered fixed 48-kHz stereo S16_LE capture; DSP graph %s','owner bench ready; PCM omitted, IRQs disabled, module pinned; DSP graph %s')
    p.write_text(s)
    (src/'Makefile').write_bytes((ROOT/'modules/hdmi-audio/Makefile').read_bytes())
    cmd=['make','-C',str(KERNEL),'M='+str(src),'ARCH=arm64','LLVM=1','W=1','modules']
    with (output/'build.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    diagnostics=(output/'build.log').read_text().replace('warning: the compiler differs from the one used to build the kernel','')
    if 'warning:' in diagnostics or 'error:' in diagnostics:raise RuntimeError('C build diagnostics; candidate refused')
    b=output/'bundle';b.mkdir()
    shutil.copyfile(src/'h713-hdmi-audio.ko',b/'h713-hdmi-audio.ko')
    subprocess.run(['llvm-objcopy','--dump-section','.note.gnu.build-id='+str(output/'module-build-id.note'),str(b/'h713-hdmi-audio.ko')],check=True)
    for n in ('h713-hdmi-receiver.ko','h713-hdmi-session.py'):shutil.copyfile(INSTALLED/n,b/n)
    session=b/'h713-hdmi-session.py'
    session.write_text(replace_once(session.read_text(),"'receiver_powered=1'],timeout=20)","'receiver_powered=1','owner_arm='+self.b.read(self.bundle+'/owner-arm.txt').strip()],timeout=20)"))
    shutil.copyfile(HERE/'warm-retention-census.py',b/'read-owner-census.py')
    for n in ('read-comm-trace.py','mips-shell.py'):shutil.copyfile(ROOT/'tools/mips'/n,b/n)
    firmware=b/'firmware/h713';firmware.mkdir(parents=True)
    shutil.copyfile(ROOT/'docs/hdmi-evidence/2026-10-07-android-audio/audio-dsp-patch.bin',firmware/'hdmi-audio-dsp.bin')
    assert sha(firmware/'hdmi-audio-dsp.bin')=='8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5'
    spec=importlib.util.spec_from_file_location('startup',HERE/'build-startup.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    text=cold_script((INSTALLED/'h713-hdmi.cmd').read_text())
    (output/'cold-owner.cmd').write_text(text);(output/'cold-owner.scr').write_bytes(m.legacy_image(text.encode()))
    for n in ('dsp-owner-boundary.py','analyze-dsp-owner-boundary.py'):
        shutil.copyfile(HERE/n,b/n)
    manifest={'schema':'h713-owner-boundary-build-v1','purpose':'isolated no-reset patched owner control and shutdown boundary; not installed','module_note_sha256':sha(output/'module-build-id.note'),'kernel_build':str(KERNEL),'kernel_release':'6.18.38','kernel_uts_version':'#1 SMP Fri Oct 16 15:44:49 PDT 2026','kernel_symvers':sha(KERNEL/'Module.symvers'),'production_fit_sha256':FIT_SHA,'base_script_sha256':SCRIPT_SHA,'production_source_sha256':SOURCES,'build_command':cmd,'arm_names':{'1':'sham','2':'shutdown-prefix'},'guard_sha256':'5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d','bundle':{p.name:sha(p) for p in b.iterdir() if p.is_file()},'firmware_sha256':sha(firmware/'hdmi-audio-dsp.bin'),'cold_script_sha256':sha(output/'cold-owner.scr'),'assets':{p.name:sha(p) for p in (HERE/'dsp-owner-boundary').iterdir() if p.is_file()}}
    for f in (output/'manifest.json',b/'manifest.json'):f.write_text(json.dumps(manifest,indent=2)+'\n')
    print(output/'manifest.json')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=pathlib.Path);a=p.parse_args();build(a.output.resolve())
