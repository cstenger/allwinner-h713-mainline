#!/usr/bin/env python3
"""Single-use execution of ONE previously reviewed installation-packet phase.

No reboot, erase, environment save, recovery or write retry. Explicit --execute
is required. Baseline/previous-phase receipts bind each write to this host boot.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import termios
import time

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('packet',ROOT/'tools/release/prepare-install.py')
p=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(p)
BANNER='U-Boot 2026.07-rc5-g320a17f71d41-h713-b3b5f2d2 (Oct 30 2026 - 02:09:43 -0700) Allwinner Technology'
ORDER=('root','fat','proper','spl')


def need(ok,message):
    if not ok:raise RuntimeError(message)


def body(reply,command):
    data=reply.replace(b'\r',b'')
    need(data.endswith(b'\n=> '),'missing UART prompt')
    need(data.startswith(command.encode()+b'\n'),'UART command echo mismatch')
    return data[len(command)+1:-len(b'\n=> ')].strip().decode('ascii')


def check_read(text,lba,sectors):
    expected=f'MMC read: dev # 1, block # {lba}, count {sectors} ...'
    need(re.fullmatch(re.escape(expected)+r'\s*'+str(sectors)+r' blocks read: OK',text.strip()) is not None,'MMC read failed/short or range mismatch')


def check_crc(text,address,size,expected):
    match=re.fullmatch(r'CRC32 for ([0-9a-fA-F]+) \.\.\. ([0-9a-fA-F]+) ==> ([0-9a-fA-F]{8})',text.strip(),re.I)
    need(match is not None,'CRC reply format mismatch')
    need((int(match[1],16),int(match[2],16),match[3].lower())==(address,address+size-1,expected),'CRC address/data mismatch')


def check_getvar(text,key,expected):
    matches=re.findall(r'^'+re.escape(key)+r':\s*(\S+)\s*$',text,re.M)
    need(len(matches)==1,'getvar missing/duplicate: '+key)
    value=matches[0]
    need(int(value,16)==int(expected,16) if expected.startswith('0x') else value==expected,'getvar mismatch: '+key)


def atomic_json(path,value):
    temp=path.with_suffix('.new')
    with temp.open('w') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)


class UART:
    def __init__(self,port,output):
        self.fd=os.open(port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        need(stat.S_ISCHR(os.fstat(self.fd).st_mode),'not UART character device')
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.ioctl(self.fd,termios.TIOCEXCL)
        own=subprocess.run(['fuser',port],capture_output=True,timeout=5)
        need(own.returncode==0 and own.stdout.split()==[str(os.getpid()).encode()],'UART ownership audit failed')
        a=termios.tcgetattr(self.fd);a[0]=a[1]=a[3]=0;a[2]=termios.CS8|termios.CREAD|termios.CLOCAL
        a[4]=a[5]=termios.B115200;a[6][termios.VMIN]=a[6][termios.VTIME]=0;termios.tcsetattr(self.fd,termios.TCSANOW,a)
        self.rx=(output/'uart-rx.bin').open('xb',buffering=0);self.tx=(output/'uart-tx.bin').open('xb',buffering=0)
        self.events=(output/'uart-events.jsonl').open('x',buffering=1)
        self.buffer=b''
    def note(self,**event):
        self.events.write(json.dumps(dict(monotonic=time.monotonic(),**event))+'\n');self.events.flush();os.fsync(self.events.fileno())
    def send(self,command):
        need('\r' not in command and '\n' not in command,'multiline UART command forbidden')
        data=command.encode()+b'\r';self.note(command_intent=command)
        for char in data:
            need(os.write(self.fd,bytes([char]))==1,'short UART TX; no retry');self.tx.write(bytes([char]));time.sleep(.002)
        termios.tcdrain(self.fd)
    def poll(self,timeout=.02):
        if select.select([self.fd],[],[],timeout)[0]:
            data=os.read(self.fd,65536);need(data,'UART disconnected; no reconnect')
            self.rx.write(data);self.buffer+=data
            need(len(self.buffer)<2*1024*1024,'unexpected UART output volume')
            need(b'Starting kernel' not in self.buffer and b'Kernel panic' not in self.buffer and b'U-Boot SPL ' not in self.buffer,'unexpected boot/reset during phase')
    def prompt(self,timeout=90):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.poll()
            if self.buffer.replace(b'\r',b'').endswith(b'\n=> ') or self.buffer==b'=> ':
                result=self.buffer;self.buffer=b'';return result
        raise RuntimeError('UART timeout; no retry')
    def command(self,command):
        need(not self.buffer,'unconsumed UART output before command')
        self.send(command);return body(self.prompt(),command)
    def close(self):
        self.rx.close();self.tx.close();self.events.close()
        fcntl.ioctl(self.fd,termios.TIOCNXCL);os.close(self.fd)


def wait_fastboot_usb(serial,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        for node in Path('/sys/bus/usb/devices').glob('*'):
            try:
                if ((node/'idVendor').read_text().strip(),(node/'idProduct').read_text().strip(),(node/'serial').read_text().strip())!=('1f3a','1010',serial):continue
                interfaces=list(node.parent.glob(node.name+':*'))
                ready=any(tuple((i/k).read_text().strip() for k in ('bInterfaceClass','bInterfaceSubClass','bInterfaceProtocol'))==('ff','42','03') for i in interfaces)
                if not ready:continue
                dev=Path('/dev/bus/usb')/f"{int((node/'busnum').read_text()):03d}"/f"{int((node/'devnum').read_text()):03d}"
                if not os.access(dev,os.R_OK|os.W_OK):continue
                subprocess.run(['udevadm','settle','--timeout=10'],check=True,capture_output=True)
                need(os.access(dev,os.R_OK|os.W_OK),'USB access disappeared after udev settle')
                return str(dev)
            except (FileNotFoundError,NotADirectoryError):continue
        time.sleep(.1)
    raise RuntimeError('fastboot USB/interface/permissions not ready; no query or write issued')


def version_gate(packet_root,mode,text):
    allowed=[BANNER]
    if mode=='rollback':
        for name in ('payloads/install/proper.bin','rescue/rescue-full-region.bin'):
            for value in re.findall(rb'U-Boot 20[^\x00\r\n]{0,180} Allwinner Technology',(packet_root/name).read_bytes()):
                allowed.append(value.decode('ascii'))
    need(any(b in text.splitlines() for b in allowed),'unexpected RAM U-Boot build')


def run_fastboot(argv,uart,output,name,timeout):
    need(argv[0]=='fastboot','unexpected executable')
    stdout=(output/(name+'.stdout')).open('xb');stderr=(output/(name+'.stderr')).open('xb')
    process=subprocess.Popen(argv,cwd=RUN_PACKET,stdout=stdout,stderr=stderr)
    start=time.monotonic()
    try:
        while process.poll() is None:
            uart.poll(.1)
            if time.monotonic()-start>timeout:raise RuntimeError('fastboot timeout; inspect phase write-intent journal; no retry')
        need(process.returncode==0,'fastboot failed; no retry: '+name)
    except BaseException:
        if process.poll() is None:process.terminate();process.wait(timeout=10)
        raise
    finally:stdout.close();stderr.close()
    text=(output/(name+'.stdout')).read_text()+(output/(name+'.stderr')).read_text()
    need(not re.search(r'\bFAILED\b|\berror:',text,re.I),'fastboot reports failure: '+name)
    return text


RUN_PACKET=None

def execute(packet_root,mode,role,receipt,run_dir,port):
    global RUN_PACKET
    RUN_PACKET=packet_root.resolve();packet=json.loads((RUN_PACKET/'packet.json').read_text())
    p.validate_structure(packet,RUN_PACKET)
    pins=p.ledger(RUN_PACKET,'SHA256SUMS')
    need(p.sha(RUN_PACKET/'packet.json')==pins['packet.json'],'packet identity')
    tool=json.loads((RUN_PACKET/'HOST-TOOLS.json').read_text())['fastboot']
    need(p.sha(Path(tool['path']))==tool['sha256'],'fastboot executable changed')
    need(subprocess.check_output([tool['path'],'--version'],text=True).splitlines()[0]==tool['version'],'fastboot version changed')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();previous=json.loads(receipt.read_text())
    manifest_sha=p.sha(RUN_PACKET/'packet.json');index=ORDER.index(role)
    need(previous['packet_sha256']==manifest_sha and previous['host_boot_id']==boot,'receipt packet/host boot mismatch')
    if index==0:
        need(previous['status']=='PASS read-only device verification' and previous['mode']==('baseline' if mode=='install' else 'recovery'),'wrong preflight receipt')
        need(previous['compared_sha256']==packet['baseline_sha256'],'baseline/protection receipt mismatch')
    else:
        need(previous['status']=='PASS flash and UART CRC checkpoints' and previous['mode']==mode and previous['role']==ORDER[index-1],'phase chain mismatch')
    output=run_dir/('phase-'+mode+'-'+role);output.mkdir(mode=0o700,exist_ok=False)
    phase=next(x for x in packet['phases'][mode] if x['role']==role)
    result=dict(status='IN PROGRESS',packet_sha256=manifest_sha,host_boot_id=boot,mode=mode,role=role,
                previous_receipt_sha256=p.sha(receipt),flash_intent=False,flash_completed=False,crc_chunks_verified=0)
    atomic_json(output/'RESULT.json',result);uart=None
    try:
        uart=UART(port,output)
        need(uart.command('echo H713_PACKET_SYNC')=='H713_PACKET_SYNC','unexpected synchronization reply')
        version=uart.command('version');version_gate(RUN_PACKET,mode,version)
        fan=uart.command('gpio status PB5');need('PB5: output: 1' in fan,'fan not confirmed high')
        serial=uart.command('printenv serial#');need(serial=='serial#='+packet['usb_serial'],'UART serial mismatch')
        for cmd in phase['uart_setup'][:-1]:
            reply=uart.command(cmd)
            if cmd=='mmc dev 1 0':need(reply=='switch to partitions #0, OK\nmmc1(part 0) is current device','wrong MMC user device')
            elif cmd.startswith('printenv '):need(reply==cmd[9:]+'='+phase['uart_setup'][2].split(' ',2)[2],'raw alias confirmation mismatch')
            else:need(reply=='','unexpected setenv reply')
        uart.send('run fastboot_mode')
        result['fastboot_usb_node']=wait_fastboot_usb(packet['usb_serial'])
        atomic_json(output/'RESULT.json',result)
        ready_end=time.monotonic()+3
        while time.monotonic()<ready_end:uart.poll(.1)
        need(os.access(result['fastboot_usb_node'],os.R_OK|os.W_OK),'USB access lost during startup interval')
        for i,gate in enumerate(phase['host_gates']):
            text=run_fastboot(gate['argv'],uart,output,'getvar-'+str(i),30)
            check_getvar(text,gate['argv'][-1],gate['value'])
        result['flash_intent']=True;atomic_json(output/'RESULT.json',result)
        uart.note(flash_intent=phase['host_flash'],payload_sha256=phase['sha256'])
        run_fastboot(phase['host_flash'],uart,output,'flash',1200)
        result['flash_completed']=True;atomic_json(output/'RESULT.json',result)
        run_fastboot(phase['host_return'],uart,output,'continue',30)
        returned=uart.prompt(15).replace(b'\r',b'')
        need(returned.startswith(b'run fastboot_mode\n'),'fastboot lifecycle echo mismatch')
        for i,check in enumerate(phase['uart_checkpoint']):
            read,crc=check['uart'];read_reply=uart.command(read)
            check_read(read_reply,int(read.split()[3],16),check['expected_read_sectors'])
            check_crc(uart.command(crc),int(crc.split()[1],16),int(crc.split()[2],16),check['expected_crc32'])
            result['crc_chunks_verified']=i+1;atomic_json(output/'RESULT.json',result)
            if (i+1)%8==0 or i+1==len(phase['uart_checkpoint']):print(json.dumps(dict(role=role,crc_chunks=i+1,total=len(phase['uart_checkpoint']))),flush=True)
        result['status']='PASS flash and UART CRC checkpoints';atomic_json(output/'RESULT.json',result)
        print(json.dumps(result),flush=True)
    except BaseException as e:
        result['status']='FAILED; STOP; NO RETRY';result['error']=str(e);atomic_json(output/'RESULT.json',result);raise
    finally:
        if uart:uart.close()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--packet',required=True,type=Path);ap.add_argument('--mode',choices=['install','rollback'],default='install')
    ap.add_argument('--phase',choices=ORDER,required=True);ap.add_argument('--receipt',required=True,type=Path)
    ap.add_argument('--run-dir',required=True,type=Path);ap.add_argument('--port',required=True);ap.add_argument('--execute',action='store_true')
    a=ap.parse_args();need(a.execute,'live execution requires explicit --execute')
    execute(a.packet,a.mode,a.phase,a.receipt,a.run_dir,a.port)

if __name__=='__main__':main()
