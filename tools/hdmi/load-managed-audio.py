#!/usr/bin/env python3
"""Stage/load the managed HDMI audio driver on an already prepared source3 board.

Requires the guarded boot and firmware-lifetime receiver owner. No TVFE/DSP diagnostic
helper is loaded. Firmware search-path changes are temporary and verified.
"""
import argparse
import hashlib
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SSH = ['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
       '-o','ConnectTimeout=5','root@192.168.4.1']
SCP = ['scp','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5']
PATCH_SHA = '8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5'
BASE = '/tmp/h713-linux-return'
PARAM = '/sys/module/firmware_class/parameters/path'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--module',type=Path,default=ROOT/'modules/hdmi-audio/h713-hdmi-audio.ko')
    parser.add_argument('--firmware',type=Path,default=ROOT/'docs/hdmi-evidence/2026-10-07-android-audio/audio-dsp-patch.bin')
    args=parser.parse_args()
    data=args.firmware.read_bytes()
    if len(data)!=2896 or hashlib.sha256(data).hexdigest()!=PATCH_SHA:
        parser.error('firmware must match the pinned stock patch')
    args.output.mkdir(parents=True,exist_ok=False)

    def remote(command,name):
        p=subprocess.run(SSH+[command],capture_output=True,text=True,timeout=25)
        (args.output/name).write_text(p.stdout+p.stderr)
        if p.returncode:
            raise RuntimeError(f'board command failed; see {args.output/name}')
        return p.stdout

    remote('set -e; test "$(uname -r)" = 6.18.38; '
           'test ! -d /sys/module/h713_hdmi_audio; '
           'test ! -d /sys/module/h713_hdmi_dsp_probe; '
           'test ! -d /sys/module/h713_hdmi_tvfe_hold; '
           'test "$(cat /sys/module/h713_hdmi_receiver/parameters/clock_count)" = 4; '
           'test "$(cat /sys/module/h713_hdmi_receiver/parameters/init_error)" = 0; '
           'test "$(cat /sys/devices/h713-hdmi-tvfe/power/runtime_status)" = active; '
           'test "$(cat /sys/devices/h713-hdmi-tvcap/power/runtime_status)" = active; '
           'test "$(cat /sys/module/h713_hdmi_receiver/parameters/edid_ready)" = Y; '
           'timeout 5s python3 /root/mips-shell.py --cmd "help win"; '
           f'mkdir -p {BASE}/firmware/h713','preflight.log')
    subprocess.run(SCP+[str(args.module),f'root@192.168.4.1:{BASE}/h713-hdmi-audio.ko'],check=True,capture_output=True,timeout=20)
    subprocess.run(SCP+[str(args.firmware),f'root@192.168.4.1:{BASE}/firmware/h713/hdmi-audio-dsp.bin'],check=True,capture_output=True,timeout=20)
    original=remote(f'cat {PARAM}','firmware-path-original.txt').rstrip('\n')
    try:
        remote("printf '%s\\n' "+shlex.quote(BASE+'/firmware')+f' > {PARAM}','firmware-path-set.log')
        remote(f'timeout 15s insmod {BASE}/h713-hdmi-audio.ko armed=1 live_source3=1 receiver_powered=1','insmod.log')
        remote('set -e; test "$(cat /sys/module/h713_hdmi_audio/parameters/manage_tvfe)" = Y; '
               'test "$(cat /sys/module/h713_hdmi_audio/parameters/manage_dsp)" = Y; '
               'test "$(cat /sys/module/h713_hdmi_audio/parameters/graph_ready)" = Y; '
               'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
               'cat /proc/asound/cards; dmesg | tail -36','load.log')
    finally:
        # A zero-byte write does not invoke sysfs's setter. Always write newline.
        remote("printf '%s\\n' "+shlex.quote(original)+f' > {PARAM}','firmware-path-restore.log')
        restored=remote(f'cat {PARAM}','firmware-path-final.txt').rstrip('\n')
        if restored!=original:
            raise RuntimeError('firmware path restoration did not verify')
    print('Managed TVFE/DSP ready; original firmware search path restored.')


if __name__ == '__main__':
    main()
