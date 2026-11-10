#!/usr/bin/env python3
"""Build a complete candidate from source and explicit private firmware inputs.

No board access, flash, service operation or historical bundle import exists here.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
MODULES = {'receiver': 'hdmi-receiver', 'audio': 'hdmi-audio',
           'signal': 'hdmi-signal', 'ddc': 'ddc-bringup', 'video': 'hdmi-v4l2'}
BACKEND = {
    'h713-hdmi-session.py': 'tools/hdmi/h713-hdmi-session.py',
    'h713-hdmi-capture.service': 'tools/hdmi/h713-hdmi-capture-startup.service',
    'h713-hdmi-prepare.service': 'tools/hdmi/h713-hdmi-prepare.service',
    'h713-hdmi-signal.py': 'tools/hdmi/h713-hdmi-signal.py',
    'h713-hdmi-signal.service': 'tools/hdmi/h713-hdmi-signal.service',
    'h713-hdmi-readvertise.py': 'tools/hdmi/h713-hdmi-readvertise.py',
    'h713-hdmi-readvertise.service': 'tools/hdmi/h713-hdmi-readvertise.service',
    'h713-hdmi-hold-guard': 'tools/hdmi/h713-hdmi-hold-guard',
    'mips-shell.py': 'tools/mips/mips-shell.py',
    'read-comm-trace.py': 'tools/mips/read-comm-trace.py',
}
HEALTH = {name: 'tools/hdmi/'+name for name in
          ['h713-hdmi-health-ack.py', 'h713-hdmi-health-ack.service', 'check-startup.sh']}
VIDEO = {name: 'tools/hdmi/'+name for name in
         ['h713-hdmi-ring.service', 'h713-hdmi-video.service', '71-h713-hdmi-in.rules']}
SPEAKER = {'h713-hdmi-speaker.service': 'tools/hdmi/h713-hdmi-speaker.service',
           'enable-mixer.sh': 'tools/hdmi/enable-speaker-mixer.sh',
           'pipewire-speaker.py': 'tools/hdmi/pipewire-speaker.py',
           'alsa-ctl.c': 'tools/audio/alsa-ctl.c'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def run(argv, env=None, **kwargs):
    print('+', ' '.join(map(str, argv)), flush=True)
    return subprocess.run(list(map(str, argv)), check=True, env=env, **kwargs)


def load_module(path):
    spec = importlib.util.spec_from_file_location('release_startup', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def vendor_inputs(directory):
    lock = json.loads((ROOT/'config/production-vendor.json').read_text())
    for name, pin in lock['files'].items():
        path = directory/name
        need(path.is_file() and not path.is_symlink(), 'missing vendor file: '+name)
        need(sha(path) == pin['sha256'], 'vendor hash mismatch: '+name)
        need('bytes' not in pin or path.stat().st_size == pin['bytes'], 'vendor size mismatch: '+name)
    entries=list(directory.rglob('*'))
    need(not any(p.is_symlink() for p in entries), 'vendor inputs must not contain symlinks')
    actual={str(p.relative_to(directory)) for p in entries if p.is_file()}
    need(actual == set(lock['files']), 'unexpected vendor files; only locked firmware assets may ship')
    return lock


def calibration(path):
    data = json.loads(path.read_text())
    need(data.get('schema') == 'h713-calibration-v1', 'wrong calibration schema')
    need(data.get('board') == 'HY200 QZ713DF_A1 (Allwinner H713)', 'wrong calibration board')
    delay = data['hdmi_audio_delay_seconds']
    need(isinstance(delay, str) and delay.replace('.', '', 1).isdigit() and 0 <= float(delay) <= 1,
         'invalid audio delay')
    pose=data.get('keystone',{})
    need(set(pose)=={'bias_y','bias_x','bias_z','lens_s','lens_tb','lens_tt'},
         'explicit accelerometer/lens calibration required')
    for key,value in pose.items():
        need(isinstance(value,str) and re.fullmatch(r'[-+]?[0-9]+(?:\.[0-9]+)?',value)
             and abs(float(value))<=10, 'invalid keystone calibration: '+key)
    need(float(pose['lens_s'])>0, 'lens scale must be positive')
    return data


def copy(source, dest, mode=0o644):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    dest.chmod(mode)


def manifest(directory):
    return {str(p.relative_to(directory)): dict(sha256=sha(p), bytes=p.stat().st_size,
                                               mode=p.stat().st_mode & 0o777)
            for p in sorted(directory.rglob('*')) if p.is_file() and not p.is_symlink()}


def verify_rootfs(path):
    """Check the delivered image, after all target compilation and purging."""
    required = ['usr/bin/python3','usr/bin/pw-loopback','usr/bin/pw-dump','usr/bin/pw-cli',
                'usr/local/bin/h713-play', 'usr/local/bin/gst-plane-play',
                'usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so',
                'usr/lib/h713-hdmi-speaker/alsa-ctl',
                'usr/lib/h713-hdmi-speaker/pipewire-speaker.py',
                'etc/default/h713-hdmi-speaker',
                'usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard']
    required += ['usr/lib/h713-hdmi/'+name+'.ko' for name in
                 ('h713-hdmi-receiver','h713-hdmi-audio','h713-hdmi-signal','h713-ddc-pins')]
    required += ['usr/lib/h713-hdmi-video/h713-hdmi-v4l2.ko',
                 'usr/lib/h713-hdmi/firmware/h713/hdmi-audio-dsp.bin']
    required += ['usr/lib/'+bundle+'/SHA256SUMS' for bundle in
                 ('h713-hdmi','h713-hdmi-health','h713-hdmi-video','h713-hdmi-speaker')]
    forbidden = ['usr/bin/gcc', 'usr/bin/cc', 'usr/bin/meson', 'usr/bin/ninja',
                 'usr/bin/gdb', 'usr/bin/strace', 'usr/bin/v4l2-ctl', 'usr/include/gstreamer-1.0/gst/gst.h',
                 'usr/include/va/va.h', 'usr/lib/h713-hdmi-speaker/hdmi-speaker',
                 'usr/local/sbin/wifi-baseline',
                 'usr/lib/h713-hdmi-speaker/alsa-ctl.c']
    with tarfile.open(path) as archive:
        members = {m.name.removeprefix('./'): m for m in archive.getmembers()}
        for name in required:
            need(name in members, 'production image missing '+name)
        for name in forbidden:
            need(name not in members, 'development/retired payload shipped: '+name)
        for name, item in members.items():
            need(not re.fullmatch(r'usr/lib/python3\.[0-9]+/test(?:/.*)?', name),
                 'Python regression suite shipped: '+name)
            need(not name.startswith('usr/lib/aarch64-linux-gnu/spa-0.2/test/'),
                 'SPA test plugin shipped: '+name)
            need(not (name.endswith('.ko') and ('probe' in Path(name).name or 'bench' in Path(name).name)),
                 'diagnostic kernel module shipped: '+name)
            if name.startswith(('usr/lib/h713-hdmi', 'etc/systemd/system/h713')):
                need(not any(part in name for part in ('-bench', '-probe', 'test-')),
                     'bench component shipped: '+name)
            if name.startswith('usr/lib/h713-hdmi') and name.endswith('/SHA256SUMS'):
                base = str(Path(name).parent)
                for line in archive.extractfile(item).read().decode().splitlines():
                    expected, relative = line.split('  ',1)
                    relative = relative.removeprefix('./')
                    need('..' not in Path(relative).parts and not relative.startswith('/'), 'unsafe bundle checksum path')
                    payload = archive.extractfile(members[base+'/'+relative]).read()
                    need(hashlib.sha256(payload).hexdigest() == expected, 'bundle payload drift: '+relative)
    return dict(required_files=len(required),forbidden_files=len(forbidden),status='PASS production payload checks')


def module_sources(dirname):
    names = subprocess.check_output(['git','-C',ROOT,'ls-files','-z','--',
                                     'modules/'+dirname],text=True)
    paths = sorted(ROOT/name for name in names.split('\0') if name
                   and (Path(name).suffix in ('.c','.h') or Path(name).name=='Makefile'))
    need(any(p.name=='Makefile' for p in paths), 'module sources not tracked: '+dirname)
    need(all(p.is_file() and not p.is_symlink() for p in paths), 'unsafe module source: '+dirname)
    return paths


def source_lock():
    names = subprocess.check_output(['git','-C',ROOT,'ls-files','-z','--',
        'config','patches','tools/build','tools/rootfs','tools/release','tools/hdmi',
        'tools/audio','tools/mips','tools/video','tools/display','tools/sensors','tools/standby'],text=True)
    paths = {ROOT/name for name in names.split('\0') if name}
    # Include this proposed source change before it is committed, but never
    # silently import other untracked bench work or generated module objects.
    paths.update(p for p in (ROOT/'tools/release').glob('*.py'))
    paths.update(ROOT/p for p in ['config/production-vendor.json','config/production-toolchain.json',
        'config/hy200-ddr3-calibration.json','patches/kernel/board/production.config',
        'tools/rootfs/cache-debs.py',
        'tools/standby/h713-lamp-ramp.c',
        'modules/hdmi-dsp-probe/h713-dsp-lock.h','modules/hdmi-dsp-probe/h713-dsp-completion.h'])
    for name in MODULES.values():
        paths.update(module_sources(name))
    for p in (ROOT/'patches').rglob('series'):
        paths.add(p)
        for name in p.read_text().splitlines():
            if name and not name.startswith('#'):
                paths.add(p.parent/name)
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def external_sources():
    """Reject a changed source checkout, and record the gitlink identities."""
    result = {}
    for name in ('arm-trusted-firmware', 'u-boot', 'aic8800'):
        path = 'external/'+name
        pin = subprocess.check_output(['git','-C',ROOT,'rev-parse','HEAD:'+path],text=True).strip()
        head = subprocess.check_output(['git','-C',ROOT/path,'rev-parse','HEAD'],text=True).strip()
        dirty = subprocess.check_output(['git','-C',ROOT/path,'status','--porcelain','--untracked-files=no'],text=True)
        need(head == pin and not dirty, 'submodule source differs from checkout pin: '+path)
        result[path] = head
    return result


# The signal owner's SCP program: restore-verified EDID/HPD ownership, the
# request handler, the HDMI-spec HPD-only pulse, and the DDC-line watch armed at
# owner ready (MIPS wrapper 0x06840094..97). Together they build MODULE_VERSION
# "hpd-event-v1": h713-hdmi-readvertise.py pulses on a failed-EDID-read
# signature (qualified 2026-11-07/08, local/recovery/2026-11-07-hpd-event).
SIGNAL_SCP_FLAGS = ('--verify-restore', '--readvertise', '--hpd-pulse', '--scan-bytes')


def modules(kernel, work, env):
    outputs = {}
    # These shared protocol headers are also used by the diagnostic source;
    # no diagnostic module is compiled or installed into the release.
    shared=work/'hdmi-dsp-probe';shared.mkdir()
    for name in ('h713-dsp-lock.h','h713-dsp-completion.h'):
        copy(ROOT/'modules/hdmi-dsp-probe'/name,shared/name)
    for kind, dirname in MODULES.items():
        dest = work/dirname
        dest.mkdir()
        for p in module_sources(dirname):
            copy(p, dest/p.name)
        if kind == 'signal':
            run(['python3', ROOT/'tools/hdmi/make-edid-trial-code.py', *SIGNAL_SCP_FLAGS,
                 '--edid', ROOT/'tools/hdmi/fixtures/hdmi-audio-edid.hex', dest/'edid-trial-code.h'], env)
        symbols = [] if kind in ('receiver', 'ddc', 'video') else [f'KBUILD_EXTRA_SYMBOLS={outputs["receiver"].parent}/Module.symvers']
        run(['make', '-C', kernel, f'M={dest}', 'ARCH=arm64', 'LLVM=1', 'W=1', *symbols, 'modules'], env)
        built = list(dest.glob('*.ko'))
        need(len(built) == 1, 'expected one module from '+dirname)
        outputs[kind] = built[0]
    return outputs


def overlay(output, module_files, vendor, fit, dtb, board_calibration):
    output.mkdir()
    for bundle, sources in [('h713-hdmi', BACKEND), ('h713-hdmi-health', HEALTH),
                            ('h713-hdmi-video', VIDEO), ('h713-hdmi-speaker', SPEAKER)]:
        base = output/'usr/lib'/bundle
        for name, source in sources.items():
            copy(ROOT/source, base/name, 0o755 if name.endswith('.sh') or name == 'h713-hdmi-hold-guard' else 0o644)
        for name in sources:
            if name.endswith('.service'):
                copy(base/name, output/'etc/systemd/system'/name)
                if name not in ('h713-hdmi-video.service', 'h713-hdmi-prepare.service'):
                    link = output/'etc/systemd/system/multi-user.target.wants'/name
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.symlink_to('../'+name)
    for kind in ('receiver', 'audio', 'signal', 'ddc'):
        copy(module_files[kind], output/'usr/lib/h713-hdmi'/module_files[kind].name)
    copy(module_files['video'], output/'usr/lib/h713-hdmi-video/h713-hdmi-v4l2.ko')
    copy(vendor/'hdmi/hdmi-audio-dsp.bin', output/'usr/lib/h713-hdmi/firmware/h713/hdmi-audio-dsp.bin')
    copy(ROOT/'tools/hdmi/71-h713-hdmi-in.rules', output/'etc/udev/rules.d/71-h713-hdmi-in.rules')
    copy(ROOT/'tools/hdmi/h713-hdmi-hold-guard', output/'usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard', 0o755)
    startup = load_module(ROOT/'tools/hdmi/build-startup.py')
    text = startup.script(fit_size=fit.stat().st_size, fdt_size=dtb.stat().st_size)
    for bundle in ('h713-hdmi', 'h713-hdmi-health'):
        base = output/'usr/lib'/bundle
        (base/'h713-hdmi.cmd').write_text(text)
        (base/'h713-hdmi.scr').write_bytes(startup.legacy_image(text.encode()))
    defaults = output/'etc/default/h713-hdmi-speaker'
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text('# Explicit per-board calibration supplied to the release build.\n'
                        'H713_HDMI_AUDIO_DELAY_SEC='+board_calibration['hdmi_audio_delay_seconds']+'\n')
    (output/'etc/h713-keystone.conf').write_text(''.join(key+'='+value+'\n' for key,value in board_calibration['keystone'].items()))
    release = output/'usr/share/h713-release'
    release.mkdir(parents=True)
    (release/'calibration.json').write_text(json.dumps(board_calibration, indent=2)+'\n')
    (output/'.h713-release-overlay').write_text('h713-production-overlay-v1\n')
    return startup


def build(a):
    os.umask(0o022)
    work = a.work.resolve()
    need(not work.exists(), 'work directory must be new; existing builds are never overwritten')
    vendor = a.vendor.resolve()
    vendor_lock = vendor_inputs(vendor)
    cal = calibration(a.calibration)
    need(a.ssh_key.is_file(), 'explicit SSH public key required')
    private_inputs={'ssh_public_key':sha(a.ssh_key),'calibration':sha(a.calibration)}
    if a.hotspot:private_inputs['hotspot_configuration']=sha(a.hotspot)
    need(a.mirror.startswith('https://snapshot.debian.org/archive/debian/') and a.mirror.rstrip('/').split('/')[-1].endswith('Z'),
         'use an explicit immutable Debian snapshot URL')
    for command in ['clang', 'ld.lld', 'llvm-objcopy', 'make', 'dtc', 'mmdebstrap', 'qemu-aarch64-static']:
        need(shutil.which(command), 'missing host build tool: '+command)
    # Images contain the explicitly supplied private hotspot configuration.
    work.mkdir(parents=True,mode=0o700)
    host_env=dict(os.environ)
    perl_probe=subprocess.run(['mmdebstrap','--version'],capture_output=True,text=True)
    if perl_probe.returncode and any(s in perl_probe.stderr for s in ('syscall.ph','ioctl.ph')):
        # Arch Perl upgrades can invalidate generated C-header bindings. Keep
        # the repair inside this build; never modify system Perl directories.
        headers=work/'perl-headers';headers.mkdir()
        converted=subprocess.run(['h2ph','-d',str(headers),'-a','syscall.h','sys/ioctl.h'],
                                  cwd='/usr/include',capture_output=True,text=True)
        (work/'perl-header-generation.log').write_text(converted.stdout+converted.stderr)
        host_env['PERL5LIB']=str(headers)+(':'+host_env['PERL5LIB'] if host_env.get('PERL5LIB') else '')
        # h2ph can report unsupported, unused branches of libc headers. Require
        # the actual consumer to load its generated bindings successfully.
        subprocess.run(['mmdebstrap','--version'],env=host_env,check=True,capture_output=True)
    toolchain=json.loads((ROOT/'config/production-toolchain.json').read_text())
    for command,expected in toolchain['versions'].items():
        version=subprocess.run([command,'--version'],capture_output=True,text=True,check=True,env=host_env)
        need((version.stdout or version.stderr).splitlines()[0]==expected,
             'host toolchain drift: '+command+'; use the recorded production version')
    if a.source_cache:
        cache=work/'build/cache';cache.mkdir(parents=True)
        for file in a.source_cache.glob('linux-*.tar.xz'):
            # build.sh always verifies the configured SHA-256 before extraction.
            copy(file,cache/file.name)
    env = dict(host_env, H713_BUILD_DIR=str(work/'build'), BOARD='ddr3', KERNEL_CONFIG='production',
               SOURCE_DATE_EPOCH=str(a.epoch), KBUILD_BUILD_USER='builder', KBUILD_BUILD_HOST='h713',
               KBUILD_BUILD_VERSION='1', TZ='UTC', LC_ALL='C',
               KBUILD_BUILD_TIMESTAMP=datetime.fromtimestamp(a.epoch,timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y'))
    for key in ('CFLAGS','CXXFLAGS','CPPFLAGS','LDFLAGS','KCFLAGS','KCPPFLAGS','LOCALVERSION','CROSS_COMPILE'):
        env.pop(key,None)
    # Out-of-tree Wi-Fi/HDMI objects can embed absolute kernel-header __FILE__
    # strings. Map the private build root before compilation, not after linking.
    env['KCFLAGS']='-ffile-prefix-map='+str(work)+'=.'
    env['H713_VA_DRIVER_SRC'] = str(work/'va-driver-src')
    env['H713_RELEASE_UUID'] = '6ad2069c-83c6-5dd8-a2f8-97b59c251c82'
    env['E2FSPROGS_FAKE_TIME'] = str(a.epoch)
    before = source_lock()
    external_before = external_sources()
    (work/'source-lock.json').write_text(json.dumps(before,indent=2)+'\n')
    for stage in ['kernel', 'bl31', 'uboot', 'aic8800']:
        run([ROOT/'tools/build/build.sh', stage], env)
    kernel = Path(subprocess.check_output([ROOT/'tools/build/build.sh','kernel-tree'],env=env,text=True).strip())
    kout = work/'build/out'
    fit = kout/'h713-kernel-production.fit'
    dtb = kout/'sun50i-h713-hy200-qz713df-a1.dtb'
    built = modules(kernel, work, env)
    ov = work/'overlay'
    startup = overlay(ov, built, vendor, fit, dtb, cal)
    # build.sh's generic rootfs expects an explicit firmware location. Stage only
    # the pinned vendor files at the configured source path in this source tree.
    # The release invocation provides an override, avoiding local/ lookup.
    env['H713_AIC_FW_SOURCE'] = str(vendor/'wifi')
    rootfs_args=[ROOT/'tools/rootfs/build.sh', '--profile', 'production', '--kernel-tree', kernel,
         '--output-dir', work/'rootfs', '--ssh-key', a.ssh_key.resolve(), '--mirror', a.mirror,
         '--hotspot-conf', a.hotspot.resolve() if a.hotspot else '/dev/null',
         '--release-overlay', ov]
    if a.debian_cache:rootfs_args+=['--debian-cache',a.debian_cache.resolve()]
    run(rootfs_args, env)
    payload_check = verify_rootfs(work/'rootfs/rootfs.tar')
    boot = work/'boot'
    shutil.copytree(vendor/'boot', boot)
    copy(fit, boot/'h713-kernel.fit')
    copy(ov/'usr/lib/h713-hdmi/h713-hdmi.scr', boot/'h713-hdmi.scr')
    firmware=work/'firmware';firmware.mkdir()
    for name, source in [('bl31.bin',kout/'bl31.bin'),
                         ('u-boot-sunxi-with-spl-ddr3.bin',kout/'u-boot-sunxi-with-spl-ddr3.bin')]:
        copy(source,firmware/name)
    combined=(firmware/'u-boot-sunxi-with-spl-ddr3.bin').read_bytes()
    proper=combined[32768:]
    need(len(proper)>=8 and struct.unpack('>II',proper[:8])==(0xd00dfeed,len(proper)),
         'unexpected combined SPL/proper layout; refuse guessed extraction')
    (firmware/'spl-region.bin').write_bytes(combined[:32768])
    (firmware/'u-boot-proper.itb').write_bytes(proper)
    provenance=work/'provenance';provenance.mkdir()
    for name,source in [('kernel.config',kernel/'.config'),('kernel.symvers',kernel/'Module.symvers'),
                        ('uboot.config',work/'build/uboot-ddr3/.config'),
                        ('uboot.inputs',kout/'u-boot-ddr3.inputs')]:
        copy(source,provenance/name)
    (work/'boot-environment.json').write_text(json.dumps(dict(bootcmd=startup.BOOTCMD,preboot=startup.PREBOOT,
        note='Review with board identity and recovery plan before installing; never auto-save environment.'),indent=2)+'\n')
    need(source_lock() == before, 'source inputs changed during build')
    need(external_sources() == external_before, 'external source inputs changed during build')
    current_private={'ssh_public_key':sha(a.ssh_key),'calibration':sha(a.calibration)}
    if a.hotspot:current_private['hotspot_configuration']=sha(a.hotspot)
    need(current_private==private_inputs,'private configuration changed during build')
    result = dict(schema='h713-production-release-v1', qualification='UNQUALIFIED CANDIDATE; no board changes',
                  source_date_epoch=a.epoch, debian_snapshot=a.mirror, vendor_inputs=vendor_lock,
                  external_sources=external_before,
                  payload_check=payload_check,
                  calibration=cal, source_lock_sha256=sha(work/'source-lock.json'),
                  private_input_sha256=private_inputs,
                  fit_sha256=sha(fit), tools={n:subprocess.check_output([n,'--version'],text=True).splitlines()[0]
                                             for n in ('clang','ld.lld','make')},
                  files=manifest(work/'rootfs'), boot_files=manifest(boot),
                  firmware_files=manifest(firmware), provenance_files=manifest(provenance))
    (work/'release.json').write_text(json.dumps(result,indent=2)+'\n')
    with tarfile.open(work/'boot.tar','w',format=tarfile.USTAR_FORMAT) as archive:
        for p in sorted(boot.rglob('*')):
            if p.is_file():
                info=archive.gettarinfo(str(p),str(p.relative_to(boot)))
                info.uid=info.gid=0;info.uname=info.gname='root';info.mtime=a.epoch
                with p.open('rb') as f:archive.addfile(info,f)
    sealed=[work/'release.json',work/'source-lock.json',work/'boot-environment.json',
            work/'boot.tar',work/'rootfs/rootfs.tar',work/'rootfs/rootfs.ext4',work/'rootfs/rootfs.simg']
    sealed+=list(firmware.iterdir())+list(provenance.iterdir())
    (work/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(work))+'\n' for p in sorted(sealed)))
    print(json.dumps(dict(status='CANDIDATE BUILT; hardware qualification required',directory=str(work)),indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--vendor',type=Path,required=True)
    p.add_argument('--calibration',type=Path,required=True)
    p.add_argument('--ssh-key',type=Path,required=True)
    p.add_argument('--mirror',required=True)
    p.add_argument('--hotspot',type=Path)
    p.add_argument('--epoch',type=int,required=True)
    p.add_argument('--source-cache',type=Path,help='optional downloaded tarballs; configured hashes are still verified')
    p.add_argument('--debian-cache',type=Path,help='optional checksummed Debian download cache; signed snapshot metadata is still fetched')
    build(p.parse_args())
