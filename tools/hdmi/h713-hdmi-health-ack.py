#!/usr/bin/env python3
"""Acknowledge healthy shared startup: GP6 HDMI -> HDOK through RTC nvmem.

No HDMI source/PCM consumer is required. Never clears GP6, writes GP7, starts
services or touches raw MMIO. --dry-run validates everything without writing.
"""
import argparse
import fcntl
import json
import os
import struct
import subprocess
from pathlib import Path

HDMI=0x48444d49
HDOK=0x48444f4b

class Board:
    def __init__(self,root=Path('/')):self.root=Path(root)
    def path(self,name):return self.root/name.lstrip('/')
    def read(self,name):return self.path(name).read_text()
    def binary(self,name):return self.path(name).read_bytes()
    def command(self,argv):
        return subprocess.run(argv,capture_output=True,text=True,check=True,timeout=60).stdout
    def healthy(self):
        boot=self.read('/proc/sys/kernel/random/boot_id').strip()
        if not boot:raise RuntimeError('missing boot ID')
        handoff=self.binary('/proc/device-tree/chosen/h713,hdmi-boot-v1')
        if len(handoff)!=12:raise RuntimeError('invalid handoff size')
        magic,status,pid=struct.unpack('>III',handoff)
        if magic!=HDMI or status!=0 or pid==0:raise RuntimeError('invalid handoff')
        state=json.loads(self.read('/run/h713-hdmi-session/state.json'))
        if state.get('boot_id')!=boot or state.get('phase')!='ready':raise RuntimeError('session not ready on this boot')
        check=self.command(['/bin/sh',str(Path(__file__).with_name('check-startup.sh'))])
        if check.splitlines()[-1:]!=['PASS']:raise RuntimeError('startup check did not pass')
        return boot
    def nvmem(self):
        rtc=self.path('/sys/firmware/devicetree/base/soc/rtc@7090000')
        if (rtc/'compatible').read_bytes()!=b'allwinner,sun50i-h713-rtc\0':raise RuntimeError('wrong RTC compatible')
        if (rtc/'reg').read_bytes()!=bytes.fromhex('0709000000000400'):raise RuntimeError('wrong RTC range')
        providers=[p for p in self.path('/sys/bus/nvmem/devices').iterdir()
                   if (p/'of_node').resolve()==rtc.resolve() and (p/'nvmem').is_file()]
        if len(providers)!=1:raise RuntimeError('RTC nvmem absent or ambiguous')
        provider=providers[0]
        if (provider.resolve().parent/'driver').resolve().name!='sun6i-rtc':raise RuntimeError('wrong RTC driver')
        return provider/'nvmem'

def acknowledge(board,dry_run=False):
    boot=board.healthy()
    fd=os.open(board.nvmem(),(os.O_RDONLY if dry_run else os.O_RDWR)|os.O_CLOEXEC)
    try:
        if os.fstat(fd).st_size!=32:raise RuntimeError('wrong RTC nvmem size')
        before=os.pread(fd,8,0x18)
        if len(before)!=8:raise RuntimeError('short GP6/GP7 read')
        gp6,gp7=struct.unpack('<II',before)
        if gp7!=0:raise RuntimeError('reboot-mode request pending; no ack')
        if gp6 not in (HDMI,HDOK):raise RuntimeError('GP6 is not HDMI/HDOK; no ack')
        if board.healthy()!=boot:raise RuntimeError('boot changed; no ack')
        # Compare again immediately before writing. Never overwrite a changed latch.
        if os.pread(fd,8,0x18)!=before:raise RuntimeError('GP6/GP7 changed; no ack')
        result={'boot_id':boot,'gp6_before':'%08x'%gp6,'gp7':'%08x'%gp7,'dry_run':dry_run}
        if dry_run or gp6==HDOK:return dict(result,written=False)
        if os.pwrite(fd,struct.pack('<I',HDOK),0x18)!=4:raise RuntimeError('short GP6 write; no retry')
        if os.pread(fd,8,0x18)!=struct.pack('<II',HDOK,gp7):raise RuntimeError('GP6/GP7 readback mismatch; no retry')
        return dict(result,written=True,gp6_after='%08x'%HDOK)
    finally:os.close(fd)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    # One lock for manual invocations as well as systemd; no retry in this unit.
    with open('/run/lock/h713-hdmi-health-ack.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(acknowledge(Board(),a.dry_run)))
if __name__=='__main__':main()
