#!/usr/bin/env python3
"""Generate the on-board runtime identity audit for an installed candidate.

Pins come from the sealed candidate release and its installation packet, never
from the board: file contents/metadata from rootfs.tar, the kernel config from
provenance, SPL and padded proper from firmware/, the package set from the
image's dpkg status, the eMMC CID and saved environment from packet.json.
The generated script runs on the board read-only and prints one JSON result
(status PASS/FAIL); tools/hdmi/startup-qualification.py takes it as --audit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

PROPER_LBA, PROPER_SECTORS, SPL_LBA, ENV_LBA = 0x49ac00, 0x74b, 0x10, 0x49ec00
# Runtime surface the HDMI product path and recovery depend on. Bytecode
# caches are regenerated on the board and are deliberately not pinned.
PREFIXES = ('etc/systemd/system/h713', 'etc/systemd/system/multi-user.target.wants/h713',
            'usr/lib/h713-hdmi', 'usr/lib/systemd/system-shutdown/h713', 'usr/local/bin/',
            'etc/default/h713', 'etc/h713-', 'etc/modules-load.d/', 'etc/ssh/sshd_config.d/10-h713.conf',
            'etc/fstab', 'etc/udev/rules.d/', 'etc/modprobe.d/h713-',
            'usr/lib/modules/6.18.38/updates/aic8800/')
FORBIDDEN = ['usr/local/sbin/wifi-baseline', 'usr/bin/gcc', 'usr/bin/cc', 'usr/bin/gdb', 'usr/bin/strace',
             'usr/bin/meson', 'usr/bin/ninja', 'usr/bin/v4l2-ctl', 'usr/lib/h713-hdmi-speaker/hdmi-speaker',
             'usr/lib/h713-hdmi-speaker/alsa-ctl.c']
# The AIC8800 loader unit and its modprobe file were retired on 11-05 but are
# required again since c372e3ad (parallel Wi-Fi load); they are pinned, not forbidden.
DIAGNOSTIC_MODULES = ['sunxi_h713_av1_probe', 'h713_scp_probe', 'h713_hdmi_dsp_probe', 'h713_hdmi_power',
                      'h713_edid_clock', 'h713_hdmi_tvfe_hold']
UNITS = ['h713-hdmi-' + n for n in ('prepare', 'capture', 'signal', 'ring', 'video', 'speaker',
                                    'health-ack', 'readvertise')]
BUNDLES = ['h713-hdmi', 'h713-hdmi-health', 'h713-hdmi-video', 'h713-hdmi-speaker']


def need(ok, message):
    if not ok:
        raise SystemExit('refused: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ledger_ok(root, name):
    for line in (root / name).read_text().splitlines():
        digest, relative = line.split(None, 1)
        need(sha((root / relative).read_bytes()) == digest, 'sealed file changed: ' + relative)


def pins(candidate, packet):
    candidate, packet = candidate.resolve(), packet.resolve()
    ledger_ok(candidate, 'SHA256SUMS')
    release = json.loads((candidate / 'release.json').read_text())
    meta = json.loads((packet / 'packet.json').read_text())
    need(meta['candidate_release_sha256'] == sha((candidate / 'release.json').read_bytes()),
         'packet was not prepared from this candidate')
    files, status = {}, None
    with tarfile.open(candidate / 'rootfs/rootfs.tar') as archive:
        for member in archive:
            name = member.name.removeprefix('./')
            if name == 'var/lib/dpkg/status':
                status = sha(archive.extractfile(member).read())
            if '__pycache__' in name or not name.startswith(PREFIXES):
                continue
            entry = {'mode': member.mode & 0o7777, 'uid': member.uid, 'gid': member.gid}
            if member.issym():
                files[name] = dict(entry, symlink=member.linkname)
            elif member.isfile():
                files[name] = dict(entry, sha256=sha(archive.extractfile(member).read()))
    need(status and len(files) >= 60, 'rootfs payload incomplete')
    for name in FORBIDDEN:
        need(name not in files, 'candidate itself ships a forbidden path: ' + name)
    proper = (candidate / 'firmware/u-boot-proper.itb').read_bytes()
    need(len(proper) <= PROPER_SECTORS * 512, 'proper exceeds its extent')
    proper += bytes(PROPER_SECTORS * 512 - len(proper))
    spl = (candidate / 'firmware/spl-region.bin').read_bytes()
    need(len(spl) == 32768, 'SPL region size')
    return {
        'candidate_release_sha256': meta['candidate_release_sha256'],
        'model': release['calibration']['board'],
        'cid': meta['emmc_cid'],
        'kernel_config_sha256': sha((candidate / 'provenance/kernel.config').read_bytes()),
        'files': dict(sorted(files.items())),
        'raw': {'proper': {'offset': PROPER_LBA * 512, 'bytes': len(proper), 'sha256': sha(proper)},
                'spl': {'offset': SPL_LBA * 512, 'bytes': len(spl), 'sha256': sha(spl)},
                'environment': {'offset': ENV_LBA * 512, 'bytes': 65536,
                                'sha256': meta['boot_environment']['sha256']}},
        'forbidden': FORBIDDEN, 'diagnostic_modules': DIAGNOSTIC_MODULES,
        'units': UNITS, 'bundles': BUNDLES, 'dpkg_status_sha256': status,
    }


BODY = r'''
import gzip,hashlib,json,os,stat,subprocess
from pathlib import Path

def need(ok,message):
    if not ok:raise RuntimeError(message)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def command(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=60)
    return dict(argv=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)

result={'status':'RUNNING','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'candidate_release_sha256':EXPECTED['candidate_release_sha256']}
try:
    need(Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode()==EXPECTED['model'],'board model mismatch')
    need(Path('/sys/block/mmcblk0/device/cid').read_text().strip()==EXPECTED['cid'],'eMMC CID mismatch')
    need(int(Path('/sys/class/block/mmcblk0p26/size').read_text())*512==2952790016,'Linux partition size changed')
    need(os.stat('/').st_dev==os.stat('/dev/mmcblk0p26').st_rdev,'root is not Linux p26')
    cpus=Path('/sys/devices/system/cpu/online').read_text().strip()
    need(cpus=='0-3','four CPUs not online')
    config=gzip.decompress(Path('/proc/config.gz').read_bytes())
    need(hashlib.sha256(config).hexdigest()==EXPECTED['kernel_config_sha256'],'running kernel config differs from the candidate')
    verified=[]
    for name,pin in EXPECTED['files'].items():
        path=Path('/'+name);s=path.lstat()
        need((stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)==(pin['mode'],pin['uid'],pin['gid']),'metadata drift: '+name)
        if 'symlink' in pin:need(path.is_symlink() and os.readlink(path)==pin['symlink'],'symlink drift: '+name)
        else:need(path.is_file() and not path.is_symlink() and digest(path)==pin['sha256'],'file drift: '+name)
        verified.append(name)
    for name in EXPECTED['forbidden']:need(not Path('/'+name).exists(),'development/retired payload present: '+name)
    for module in EXPECTED['diagnostic_modules']:need(not Path('/sys/module/'+module).exists(),'diagnostic module loaded: '+module)
    raw={}
    with open('/dev/mmcblk0','rb',buffering=0) as f:
        for name,pin in EXPECTED['raw'].items():
            f.seek(pin['offset']);data=f.read(pin['bytes'])
            need(len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],'raw boot/environment drift: '+name)
            raw[name]='PASS'
    need(digest('/var/lib/dpkg/status')==EXPECTED['dpkg_status_sha256'],'installed package set differs from the candidate')
    bundles=[]
    for bundle in EXPECTED['bundles']:
        p=subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd='/usr/lib/'+bundle,capture_output=True,text=True,timeout=30)
        need(p.returncode==0,'bundle manifest failure: '+bundle);bundles.append({'bundle':bundle,'stdout':p.stdout})
    startup=command(['sh','/usr/lib/h713-hdmi-health/check-startup.sh'])
    need(startup['returncode']==0 and '\nPASS\n' in '\n'+startup['stdout'],'HDMI startup gate failed')
    services={}
    for unit in EXPECTED['units']:
        state=subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','NRestarts'],text=True)
        need('ActiveState=active' in state.splitlines() and 'NRestarts=0' in state.splitlines(),'service state/restarts: '+unit);services[unit]=state
    result.update(status='PASS candidate runtime identity/startup checks',cpus=cpus,files_verified=len(verified),
                  package_set='PASS',kernel_config='PASS',raw=raw,bundles=bundles,startup=startup,services=services,
                  uname=command(['uname','-a']),storage=command(['df','-B1','/']))
except BaseException as e:result.update(status='FAIL',error=str(e))
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status'].startswith('PASS') else 1)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--candidate', type=Path, required=True, help='sealed candidate release directory')
    parser.add_argument('--packet', type=Path, required=True, help='installation packet used for the install')
    parser.add_argument('--output', type=Path, required=True, help='new audit script path')
    args = parser.parse_args()
    need(not args.output.exists(), 'output must be new')
    expected = pins(args.candidate, args.packet)
    args.output.write_text('EXPECTED = ' + json.dumps(expected, sort_keys=True) + '\n' + BODY)
    print(json.dumps({'output': str(args.output), 'files': len(expected['files']),
                      'candidate_release_sha256': expected['candidate_release_sha256']}))


if __name__ == '__main__':
    main()
