#!/usr/bin/env python3
"""Generate a read-only target audit to stream over SSH; installs no framework."""
import argparse,hashlib,json,tarfile
from pathlib import Path

REMOTE = r'''
import gzip,hashlib,json,os,stat,struct,subprocess
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

result={'status':'RUNNING','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
try:
    need(Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode()==EXPECTED['model'],'board model mismatch')
    need(Path('/sys/block/mmcblk0/device/cid').read_text().strip()==EXPECTED['cid'],'eMMC CID mismatch')
    need(int(Path('/sys/class/block/mmcblk0p26/size').read_text())*512==2952790016,'Linux partition size changed')
    rootdev=os.stat('/').st_dev
    need(rootdev==os.stat('/dev/mmcblk0p26').st_rdev,'root is not Linux p26')
    cpus=Path('/sys/devices/system/cpu/online').read_text().strip()
    need(cpus=='0-3','four CPUs not online')
    config=gzip.decompress(Path('/proc/config.gz').read_bytes())
    need(hashlib.sha256(config).hexdigest()==EXPECTED['kernel_config_sha256'],'running kernel config differs from built candidate')
    verified=[]
    for name,pin in EXPECTED['files'].items():
        path=Path('/'+name);s=path.lstat()
        need((stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)==(pin['mode'],pin['uid'],pin['gid']),'metadata drift: '+name)
        if 'symlink' in pin:need(path.is_symlink() and os.readlink(path)==pin['symlink'],'symlink drift: '+name)
        else:need(path.is_file() and not path.is_symlink() and digest(path)==pin['sha256'],'file drift: '+name)
        verified.append(name)
    for name in EXPECTED['forbidden']:need(not Path('/'+name).exists(),'development/retired payload shipped: '+name)
    for module in ('sunxi_h713_av1_probe','h713_scp_probe','h713_hdmi_dsp_probe','h713_hdmi_power','h713_edid_clock','h713_hdmi_tvfe_hold'):
        need(not Path('/sys/module/'+module).exists(),'diagnostic module loaded: '+module)
    raw={}
    with open('/dev/mmcblk0','rb',buffering=0) as f:
        for name,pin in EXPECTED['raw'].items():
            f.seek(pin['offset']);data=f.read(pin['bytes'])
            need(len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],'raw boot/environment drift: '+name)
            raw[name]='PASS'
    actual_packages=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n'])
    need(hashlib.sha256(actual_packages).hexdigest()==EXPECTED['package_list_sha256'],'runtime package/version set differs')
    bundle_checks=[]
    for bundle in ('h713-hdmi','h713-hdmi-health','h713-hdmi-video','h713-hdmi-speaker'):
        p=subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd='/usr/lib/'+bundle,capture_output=True,text=True,timeout=30)
        need(p.returncode==0,'bundle manifest failure: '+bundle);bundle_checks.append({'bundle':bundle,'stdout':p.stdout})
    startup=command(['sh','/usr/lib/h713-hdmi-health/check-startup.sh'])
    need(startup['returncode']==0 and '\nPASS\n' in '\n'+startup['stdout'],'HDMI startup gate failed')
    services={}
    for unit in ('h713-hdmi-capture','h713-hdmi-signal','h713-hdmi-ring','h713-hdmi-video','h713-hdmi-speaker','h713-hdmi-health-ack','h713-hdmi-readvertise'):
        state=subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','NRestarts'],text=True)
        need('ActiveState=active' in state.splitlines() and 'NRestarts=0' in state.splitlines(),'service state/restarts: '+unit);services[unit]=state
    result.update(status='PASS candidate runtime identity/startup checks',cpus=cpus,files_verified=len(verified),
                  package_set='PASS',kernel_config='PASS',raw=raw,bundles=bundle_checks,startup=startup,services=services,
                  uname=command(['uname','-a']),storage=command(['df','-B1','/']),bluetooth=command(['bluetoothctl','list']))
except BaseException as e:result.update(status='FAIL',error=str(e))
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status'].startswith('PASS') else 1)
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--packet',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('refuse existing audit output')
    packet=json.loads((a.packet/'packet.json').read_text())
    expected={'model':packet['model'],'cid':packet['emmc_cid'],'kernel_config_sha256':hashlib.sha256((a.candidate/'provenance/kernel.config').read_bytes()).hexdigest(),'files':{},'raw':{},'forbidden':['usr/local/sbin/wifi-baseline','usr/bin/gcc','usr/bin/cc','usr/bin/gdb','usr/bin/strace','usr/bin/meson','usr/bin/ninja','usr/bin/v4l2-ctl','usr/lib/h713-hdmi-speaker/hdmi-speaker','usr/lib/h713-hdmi-speaker/alsa-ctl.c']}
    with tarfile.open(a.candidate/'rootfs/rootfs.tar') as t:
        for m in t:
            n=m.name.removeprefix('./')
            if n=='usr/share/h713-release/runtime-packages.tsv':expected['package_list_sha256']=hashlib.sha256(t.extractfile(m).read()).hexdigest()
            selected=n.startswith(('usr/lib/h713-hdmi','etc/default/h713-hdmi','etc/systemd/system/h713','usr/lib/systemd/system-shutdown/h713','usr/local/bin/h713-','usr/local/bin/gst-plane-play','usr/lib/modules/6.18.38/updates/')) or n in ('etc/fstab','etc/h713-keystone.conf','etc/ssh/sshd_config.d/10-h713.conf') or (n.startswith('etc/systemd/system/multi-user.target.wants/') and 'h713' in n)
            if not selected or not (m.isfile() or m.issym()):continue
            pin={'mode':m.mode,'uid':m.uid,'gid':m.gid}
            if m.issym():pin['symlink']=m.linkname
            else:pin['sha256']=hashlib.sha256(t.extractfile(m).read()).hexdigest()
            expected['files'][n]=pin
    for phase in packet['phases']['install']:
        if phase['role'] not in ('proper','spl'):continue
        expected['raw'][phase['role']]={k:phase[k] for k in ('offset','bytes','sha256')}
    expected['raw']['environment']={'offset':0x49ec00*512,'bytes':65536,'sha256':packet['boot_environment']['sha256']}
    if 'package_list_sha256' not in expected:raise ValueError('missing target package list')
    a.output.write_text('EXPECTED='+repr(expected)+'\n'+REMOTE);a.output.chmod(0o600)
    print(json.dumps({'audit':str(a.output),'expected_files':len(expected['files']),'target_operations':'read-only; stream through SSH stdin'},indent=2))

if __name__=='__main__':main()
