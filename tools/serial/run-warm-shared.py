#!/usr/bin/env python3
"""First direct warm test of the shared cold/warm HDMI startup. One run per
fresh cold cycle; every action happens once and nothing retries.

  resume   continue from the recorded cold session of a run that stopped
           before any reboot or launch (same boot still up).
  run      cold production boot (watched, never interrupted) -> cold health
           -> orderly reboot -> warm prompt -> census -> RAM
           warm-shared.scr -> one `source` -> warm health -> cold/warm compare.
           Leaves the board running for the operator's picture/audio check.
  poweroff orderly production poweroff, confirmed on UART.

This process is the sole UART reader for the whole run. Arm it, see OPEN in
events.log, then ask for power. Plan: docs/hdmi-shared-startup-plan-2026-10-23.md
Use --boot-stop gp7 for an orderly reboot with the existing bootloader
reboot argument: the kernel writes GP7, U-Boot clears it and waits without
an interrupt key. No direct register write or saved environment change.
For SysRq-b, --boot-stop gp7 arms the same word through the RTC nvmem
provider with readback before the abrupt reset (no reboot notifier runs).
"""
import argparse,hashlib,importlib.util,json,os,re,select,shlex,subprocess,sys,threading,time,zlib
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from console import open_port,write_slow,drain
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1']
BOOTCMD='if fatload mmc 1:2 0x52000000 h713-hdmi.scr; then source 0x52000000; else echo HDMI startup script missing - use h713_hdmi_previous_bootcmd for recovery; fi'
FIT=ROOT/'build/out/h713-kernel.fit'
PREBOOT=rb'(?m)^H713 RESET v1 stage=proper_preboot gp6=(\w{8}) gp7=(\w{8}) mips_clk=(\w{8}) mips_reset=(\w{8}) mips_status=(\w{8})\r?$'
# Every failure text the installed and warm scripts can print, plus the guard.
FAILURES=(b'launch latch set - capture disabled',b'source/boot failed',b'preparation/launch failed',b'WARM-SHARED requires',
          b'hold-guard: reboot refused',b'warm logo bring-up failed',b'Kernel panic')
# Before the autoboot interrupt, a logo stage means the installed script already ran.
BEFORE_INTERRUPT=FAILURES+(b'stage=pre_workspace',)
ABRUPT_MARKER='H713_WARM_SHARED_SYNC_DONE'
ABRUPT_GP7_MARKER=ABRUPT_MARKER+' gp7=b007c0de gp6=48444d49'
GP7_STOP='b007c0de'
BOOTSTOP_PREBOOT=load('startup_bootstop',ROOT/'tools/hdmi/build-startup.py').PREBOOT

def orderly_bootstop_script(boot):
    """Use the installed kernel reboot-mode driver, never raw MMIO."""
    return '''import pathlib,subprocess
P=pathlib.Path
if P('/proc/sys/kernel/random/boot_id').read_text().strip()!=%r:raise RuntimeError('boot changed; no reboot')
dt=P('/proc/device-tree/reboot-mode')
if (dt/'compatible').read_bytes()!=b'nvmem-reboot-mode\\0':raise RuntimeError('wrong reboot-mode driver')
if (dt/'mode-bootloader').read_bytes()!=bytes.fromhex('b007c0de'):raise RuntimeError('wrong bootloader magic')
if not P('/sys/bus/platform/drivers/nvmem-reboot-mode/reboot-mode').is_dir():raise RuntimeError('reboot-mode driver not bound')
help=subprocess.run(['systemctl','--help'],capture_output=True,text=True,check=True).stdout
if '--reboot-argument=' not in help:raise RuntimeError('systemctl lacks reboot argument')
subprocess.run(['systemctl','reboot','--no-block','--reboot-argument=bootloader'],check=True)
''' % boot

def check_bootstop_mode(reset,boot_stop):
    if boot_stop not in ('interrupt','gp7'):raise ValueError('unknown boot-stop mode')
    if reset not in ('orderly','sysrq-b'):raise ValueError('unknown reset mode')

def check_bootstop_env(preboot,bootdelay):
    if preboot!=BOOTSTOP_PREBOOT or bootdelay!='-1':raise RuntimeError('GP7 preboot/volatile bootdelay mismatch; no launch')

GP7_ARM_CODE=r'''
# Pin the RTC provider and the existing reboot-mode cell, never /dev/mem.
dt=P('/sys/firmware/devicetree/base')
rtc=dt/'soc/rtc@7090000';cell=rtc/'reboot-mode-magic@1c';mode=dt/'reboot-mode'
if (rtc/'compatible').read_bytes()!=b'allwinner,sun50i-h713-rtc\0':raise RuntimeError('wrong RTC compatible')
if (rtc/'reg').read_bytes()!=bytes.fromhex('0709000000000400'):raise RuntimeError('wrong RTC register range')
if (cell/'reg').read_bytes()!=bytes.fromhex('0000001c00000004'):raise RuntimeError('wrong GP7 cell range')
if (mode/'compatible').read_bytes()!=b'nvmem-reboot-mode\0':raise RuntimeError('wrong reboot-mode compatible')
if (mode/'mode-bootloader').read_bytes()!=bytes.fromhex('b007c0de'):raise RuntimeError('wrong bootloader magic')
if len((cell/'phandle').read_bytes())!=4 or (mode/'nvmem-cells').read_bytes()!=(cell/'phandle').read_bytes():raise RuntimeError('wrong reboot-mode cell reference')
providers=[p for p in P('/sys/bus/nvmem/devices').iterdir()
           if (p/'of_node').resolve()==rtc.resolve() and (p/'nvmem').is_file()]
if len(providers)!=1:raise RuntimeError('RTC nvmem provider absent or ambiguous')
provider=providers[0]
if (provider.resolve().parent/'driver').resolve().name!='sun6i-rtc':raise RuntimeError('wrong RTC driver')
fd=os.open(str(provider/'nvmem'),os.O_RDWR|os.O_CLOEXEC)
try:
    if os.fstat(fd).st_size!=32:raise RuntimeError('wrong RTC nvmem size')
    before=os.pread(fd,8,0x18)
    if len(before)!=8 or before[:4]!=bytes.fromhex('494d4448') or before[4:]!=bytes(4):raise RuntimeError('unexpected GP6/GP7; no arm')
    guard()
    print('GP7_ARM_INTENT provider='+str(provider)+' boot='+expected,flush=True)
    # One aligned four-byte write at offset 0x1c. GP6 is read-only.
    if os.pwrite(fd,bytes.fromhex('dec007b0'),0x1c)!=4:raise RuntimeError('short GP7 write; stop, no retry')
    if os.pread(fd,8,0x18)!=before[:4]+bytes.fromhex('dec007b0'):raise RuntimeError('GP7 readback/GP6 mismatch; stop, no retry')
    print('GP7_ARMED_READBACK_OK boot='+expected,flush=True)
finally:os.close(fd)
'''

def abrupt_script(boot,boot_stop='interrupt'):
    """Synced emergency reset, with no service stop or driver teardown."""
    return '''import os,pathlib,subprocess,termios
P=pathlib.Path
expected=%r
def guard():
    if P('/proc/sys/kernel/random/boot_id').read_text().strip()!=expected:raise RuntimeError('boot changed; no reset')
    for u in ('capture','signal','speaker','ring','video'):
        subprocess.run(['systemctl','is-active','--quiet','h713-hdmi-'+u],check=True)
    for card,stream in (('H713HDMI','pcm0c'),('Codec','pcm0p')):
        if not P('/proc/asound/'+card+'/'+stream+'/sub0/status').read_text().startswith('state: RUNNING'):raise RuntimeError('PCM not running')
    if P('/sys/module/h713_hdmi_audio/parameters/dsp_failed').read_text().strip()!='N':raise RuntimeError('DSP failed')
    if P('/sys/devices/platform/h713-hdmi-ring/signal').read_text().strip()!='locked 1280x720':raise RuntimeError('video not locked')
guard()
os.sync()
guard()
%s
with open('/dev/ttyS0','w') as f:
    f.write(%r+' boot='+expected+'\\n');f.flush()
    termios.tcdrain(f.fileno())  # flush alone does not wait for UART transmission
with open('/proc/sysrq-trigger','w') as f:f.write('b')
raise RuntimeError('SysRq returned unexpectedly')
''' % (boot,GP7_ARM_CODE+'\nguard()' if boot_stop=='gp7' else '',ABRUPT_GP7_MARKER if boot_stop=='gp7' else ABRUPT_MARKER)

class Stage:
    """Pure stream matcher: required markers in order, forbidden texts, SPL count."""
    def __init__(self,name,required,spl,forbidden=FAILURES,interrupt=False):
        self.name,self.required,self.spl_max,self.forbidden,self.interrupt=name,list(required),spl,forbidden,interrupt
        self.buffer=b'';self.found=[];self.spl=0;self.sent=False
    def feed(self,data):
        """Returns 'space' once (interrupt stages), 'done' when complete, else None. Raises on failure."""
        self.buffer+=data
        self.spl=self.buffer.count(b'U-Boot SPL ')
        if self.spl>self.spl_max:raise RuntimeError(self.name+': unexpected extra reset; no retry')
        for bad in self.forbidden:
            if bad in self.buffer:raise RuntimeError(self.name+': '+bad.decode())
        while len(self.found)<len(self.required):
            pos=self.buffer.find(self.required[len(self.found)],self.found[-1][1] if self.found else 0)
            if pos<0:break
            self.found.append((self.required[len(self.found)],pos+len(self.required[len(self.found)])))
        if self.interrupt and not self.sent and len(self.found)==len(self.required)-1 and self.required[-1]==b'=> ':
            if b'Hit any key to stop autoboot:' in self.buffer[self.found[-1][1]:]:
                self.sent=True;return 'space'
        return 'done' if len(self.found)==len(self.required) else None
    def preboot(self):
        m=re.search(PREBOOT,self.buffer)
        if not m:raise RuntimeError(self.name+': no proper_preboot census line')
        return dict(zip(('gp6','gp7','mips_clk','mips_reset','mips_status'),(g.decode() for g in m.groups())))
def cold_stage():
    return Stage('cold-boot',[b'U-Boot SPL ',b'stage=proper_preboot',b'Hit any key to stop autoboot',b'H713 panel 720p timing re-latched after source 3',
                              b'H713 HDMI cold startup handoff verified',b'Starting kernel',b'login:'],spl=1)
def reboot_stage(reset='orderly',boot_stop='interrupt'):
    check_bootstop_mode(reset,boot_stop)
    marker=ABRUPT_GP7_MARKER if boot_stop=='gp7' else ABRUPT_MARKER
    markers=[b'reboot: Restarting system'] if reset=='orderly' else [marker.encode(),b'sysrq: Resetting']
    return Stage('warm-reboot',markers+[b'U-Boot SPL ',b'stage=proper_preboot',b'=> '],spl=1,
                 forbidden=BEFORE_INTERRUPT+(b'Starting kernel',b'## Executing script',b'boot logo published'),interrupt=boot_stop=='interrupt')
def warm_stage():
    return Stage('warm-shared',[b'## Executing script',b'H713 panel 720p timing re-latched after source 3',b'H713 WARM-SHARED startup handoff verified',
                                b'Starting kernel',b'login:'],spl=0)
def check_cold_preboot(p):
    if p!={'gp6':'00000000','gp7':'00000000','mips_clk':'00000000','mips_reset':'00000000','mips_status':'00000000'}:raise RuntimeError('cold preboot is not a fresh power-on: '+json.dumps(p))
def check_warm_preboot(p,boot_stop='interrupt'):
    if p!={'gp6':'48444d49','gp7':GP7_STOP if boot_stop=='gp7' else '00000000','mips_clk':'00000000','mips_reset':'00000000','mips_status':'00000000'}:raise RuntimeError('warm preboot not the expected cold-path warm state: '+json.dumps(p))

class Uart:
    """Sole reader: a thread copies every byte to the raw log and a buffer, so
    nothing is lost while the host runs health checks. Paused only while the
    interactive prompt census talks to U-Boot directly."""
    def __init__(self,fd,raw):
        self.fd,self.raw,self.data,self.lock,self.error,self.stopping=fd,raw,b'',threading.Lock(),None,False
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def loop(self):
        try:
            while not self.stopping:
                if not select.select([self.fd],[],[],0.1)[0]:continue
                try:chunk=os.read(self.fd,65536)
                except BlockingIOError:continue  # readiness can change on a nonblocking tty
                if not chunk:raise RuntimeError('UART lost; no reconnect')
                self.raw.write(chunk)
                with self.lock:self.data+=chunk
        except Exception as e:self.error=e
    def stop(self):self.stopping=True;self.thread.join()
class Run:
    def __init__(self,out,port,reset='orderly',require_video=False,boot_stop='interrupt'):
        check_bootstop_mode(reset,boot_stop)
        self.out,self.port,self.reset,self.require_video,self.boot_stop=out,port,reset,require_video,boot_stop
    def options(self):
        return {'reset':self.reset,'require_video':self.require_video,'boot_stop':self.boot_stop}
    def note(self,text):
        with (self.out/'events.log').open('a') as f:f.write(datetime.now(timezone.utc).isoformat()+' '+text+'\n')
    def watch(self,uart,stage,seconds,start=None):
        """Feed the stage from the reader's buffer; returns the buffer position after completion."""
        pos=len(uart.data) if start is None else start;deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if uart.error:raise uart.error
            with uart.lock:chunk=uart.data[pos:];pos+=len(chunk)
            if chunk:
                n=len(stage.found)
                r=stage.feed(chunk)
                for marker,_ in stage.found[n:]:self.note(stage.name+': MARKER '+marker.decode(errors='replace'))
                if r=='space':write_slow(uart.fd,b' ');self.note(stage.name+': SENT ONE AUTOBOOT INTERRUPT SPACE')
                elif r=='done':self.note(stage.name+': complete');return stage,pos
            else:time.sleep(0.05)
        raise RuntimeError(stage.name+': deadline before '+repr(stage.required[len(stage.found)]))
    def ssh(self,name,command,timeout=20):
        try:r=subprocess.run(SSH+[command],capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:(self.out/(name+'-uncertain.log')).write_text('HOST DEADLINE: uncertain, no retry\n');raise
        (self.out/(name+'.log')).write_text(r.stdout+r.stderr);return r
    def wait_ssh(self,boot_not,seconds=240):
        """Reachability polling only (read-only); no board action is repeated."""
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:r=subprocess.run(SSH+['cat /proc/sys/kernel/random/boot_id'],capture_output=True,text=True,timeout=10)
            except subprocess.TimeoutExpired:continue
            if r.returncode==0 and r.stdout.strip() and r.stdout.strip()!=boot_not:return r.stdout.strip()
            time.sleep(5)
        raise RuntimeError('board not reachable over SSH')
    def health(self,label):
        c=load('checker',ROOT/'tools/hdmi/check-warm-shared.py')
        rec=c.collect(label)
        with (self.out/(label+'-health.json')).open('x') as f:f.write(json.dumps(rec,indent=2)+'\n')
        res=c.evaluate(rec,require_video=self.require_video);(self.out/(label+'-evaluation.json')).write_text(json.dumps(res,indent=2)+'\n');self.note(label+' health passed=%s'%res['passed'])
        return rec,res
    def census(self,fd,raw,manifest):
        """Interactive, with the reader thread stopped: U-Boot talks only to us."""
        trace=load('trace_runner',HERE/'run-tvfe-boot-trace.py');con=trace.Console(fd,raw)
        cmd=trace.warm.parse_bootcmd(con.run('printenv bootcmd'))
        if cmd!=BOOTCMD:raise RuntimeError('bootcmd changed; no launch')
        env={}
        if self.boot_stop=='gp7':
            for key in ('preboot','bootdelay'):
                response=con.run('printenv '+key)
                match=re.search(rb'(?m)^'+key.encode()+rb'=(.*?)\r?$',response)
                if not match:raise RuntimeError('missing '+key+'; no launch')
                env[key]=match.group(1).decode()
            check_bootstop_env(env['preboot'],env['bootdelay'])
        want={0x07090118:0x48444d49,0x0709011c:0,0x0306101c:0,0x070101ac:0}
        got={a:trace.warm.parse_md(con.run('md.l 0x%08x 1'%a),a) for a in want}
        (self.out/'warm-prompt-census.json').write_text(json.dumps({'bootcmd':cmd,**env,**{'%08x'%a:'%08x'%v for a,v in got.items()}},indent=2)+'\n')
        if got!=want:raise RuntimeError('warm prompt census differs from expected; no launch')
        con.checked('fatload mmc 1:2 0x50000000 h713-kernel.fit');con.checked('itest ${filesize} == %x'%FIT.stat().st_size)
        m=re.search(rb'==>\s*([0-9a-fA-F]{8})\b',con.run('crc32 0x50000000 %x'%FIT.stat().st_size))
        if not m or int(m.group(1),16)!=zlib.crc32(FIT.read_bytes()):raise RuntimeError('on-media FIT CRC differs; no launch')
    def prepared(self,prepared):
        m=json.loads((prepared/'manifest.json').read_text())
        assert hashlib.sha256((prepared/'warm-shared.scr').read_bytes()).hexdigest()==m['warm_script_sha256']
        assert hashlib.sha256(FIT.read_bytes()).hexdigest()==m['production_fit_sha256']
        return m
    def run(self,prepared):
        m=self.prepared(prepared)
        if self.reset=='sysrq-b' and not self.require_video:raise RuntimeError('SysRq-b requires video health checks')
        self.out.mkdir(parents=True,exist_ok=False);(self.out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
        (self.out/'run-options.json').write_text(json.dumps(self.options(),indent=2)+'\n')
        fd=open_port(self.port)
        try:
            with (self.out/'uart-cold-and-reboot.log').open('xb',buffering=0) as raw:
                uart=Uart(fd,raw);self.note('OPEN '+self.port)
                try:
                    cold,pos=self.watch(uart,cold_stage(),900,start=0);check_cold_preboot(cold.preboot())
                    cold_boot=self.wait_ssh(None);self.note('cold boot '+cold_boot)
                    rec=self.reboot_from_cold(uart)
                finally:uart.stop()
                self.census(fd,raw,m)
        finally:os.close(fd)
        self.launch(prepared,cold_boot,rec)
    def resume(self,prepared,boot):
        """Continue from the recorded cold session of an earlier `run` that
        stopped before any reboot or launch (e.g. a checker defect). Refuses
        unless that exact boot is still up and nothing after cold health ran."""
        m=self.prepared(prepared)
        events=(self.out/'events.log').read_text()
        old=json.loads((self.out/'manifest.json').read_text())
        options=self.out/'run-options.json'
        old_options=json.loads(options.read_text()) if options.exists() else {'reset':'orderly','require_video':False}
        old_options.setdefault('boot_stop','interrupt')
        if old_options!=self.options():raise RuntimeError('resume options differ')
        if old['warm_script_sha256']!=m['warm_script_sha256'] or old['production_fit_sha256']!=m['production_fit_sha256']:raise RuntimeError('prepared script/FIT differ from the original run')
        if 'cold-boot: complete' not in events or 'cold boot '+boot not in events or 'cold health passed=False' not in events:raise RuntimeError('no recorded failed cold health for that boot')
        if 'REBOOT REQUESTED' in events or (self.out/'launch-attempted').exists() or (self.out/'uart-resume-and-reboot.log').exists():raise RuntimeError('a reboot, launch or resume already happened; cold cycle required')
        cold=cold_stage()
        if cold.feed((self.out/'uart-cold-and-reboot.log').read_bytes())!='done':raise RuntimeError('recorded cold boot incomplete')
        check_cold_preboot(cold.preboot())
        if self.wait_ssh(None,seconds=30)!=boot:raise RuntimeError('a different boot is running; cold cycle required')
        for n in ('cold-health','cold-evaluation'):
            if (self.out/(n+'.json')).exists():(self.out/(n+'.json')).rename(self.out/(n+'-attempt1.json'))
        fd=open_port(self.port)
        try:
            with (self.out/'uart-resume-and-reboot.log').open('xb',buffering=0) as raw:
                uart=Uart(fd,raw);self.note('OPEN '+self.port+' RESUME cold boot '+boot)
                try:rec=self.reboot_from_cold(uart)
                finally:uart.stop()
                self.census(fd,raw,m)
        finally:os.close(fd)
        self.launch(prepared,boot,rec)
    def reboot_from_cold(self,uart):
        rec,res=self.health('cold')
        if not res['passed']:raise RuntimeError('cold session unhealthy; warm test not started: '+'; '.join(res['reasons']))
        pos=len(uart.data)
        # Persist intent before submitting anything; an uncertain request cannot be resumed.
        self.note('REBOOT REQUESTED '+self.reset+' boot_stop='+self.boot_stop)
        if self.reset=='orderly':
            if self.boot_stop=='gp7':
                script=orderly_bootstop_script(rec['boot_id'])
                (self.out/'orderly-bootstop-trigger.py.txt').write_text(script)
                command='setsid nohup python3 -c '+shlex.quote(script)+' > /run/h713-warm-shared-bootstop.log 2>&1 < /dev/null &'
                self.ssh('reboot-request',command)
            else:self.ssh('reboot-request','systemctl reboot --no-block')
        else:
            script=abrupt_script(rec['boot_id'],self.boot_stop)
            (self.out/'abrupt-reset-trigger.py.txt').write_text(script)
            command='setsid nohup python3 -c '+shlex.quote(script)+' > /run/h713-warm-shared-reset.log 2>&1 < /dev/null &'
            self.ssh('reboot-request',command)
        warm,pos=self.watch(uart,reboot_stage(self.reset,self.boot_stop),300,start=pos);check_warm_preboot(warm.preboot(),self.boot_stop)
        return rec
    def launch(self,prepared,cold_boot,rec):
        # The sender verifies the RAM CRC before it returns.
        t=subprocess.run([sys.executable,str(HERE/'ymodem-send.py'),str(prepared/'warm-shared.scr'),'0x52000000','--port',self.port],capture_output=True,text=True,timeout=60)
        (self.out/'script-transfer.log').write_text(t.stdout+t.stderr);t.check_returncode()
        fd=open_port(self.port)
        try:
            with (self.out/'uart-warm-shared.log').open('xb',buffering=0) as raw:
                write_slow(fd,b'\n');initial=drain(fd,1,echo=False);raw.write(initial)
                if not re.search(rb'=>\s*$',initial):raise RuntimeError('no prompt before launch; nothing sent')
                uart=Uart(fd,raw)
                try:
                    (self.out/'launch-attempted').write_text('One warm-shared source; no retry permitted.\n')
                    write_slow(fd,b'source 0x52000000\n');self.note('SOURCE SENT')
                    self.watch(uart,warm_stage(),300,start=0)
                    warm_boot=self.wait_ssh(cold_boot);self.note('warm boot '+warm_boot)
                    wrec,wres=self.health('warm')
                finally:uart.stop()
                c=load('checker',ROOT/'tools/hdmi/check-warm-shared.py');cmp=c.compare(rec,wrec,require_video=self.require_video)
                (self.out/'compare.json').write_text(json.dumps(cmp,indent=2)+'\n');self.note('compare passed=%s'%cmp['passed'])
                print(json.dumps({'warm':wres,'compare_passed':cmp['passed'],'reasons':cmp['reasons']},indent=2))
                print('OPERATOR CHECK NOW: picture (live / logo / black) and tone (audible / silent). Then run poweroff.')
                if not cmp['passed']:raise RuntimeError('cold/warm health comparison failed; see compare.json')
        finally:os.close(fd)
    def poweroff(self):
        fd=open_port(self.port)
        try:
            with (self.out/'uart-poweroff.log').open('xb',buffering=0) as raw:
                uart=Uart(fd,raw);self.note('OPEN '+self.port+' for poweroff')
                try:
                    self.ssh('poweroff-request','systemctl poweroff --no-block')
                    self.watch(uart,Stage('poweroff',[b'reboot: Power down'],spl=0,forbidden=(b'Kernel panic',)),180,start=0)
                finally:uart.stop()
        finally:os.close(fd);self.note('CLOSE')
def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action',choices=('run','resume','poweroff'));p.add_argument('--output',required=True,type=Path)
    p.add_argument('--cold-boot',help='resume: the recorded cold boot ID that must still be running')
    p.add_argument('--reset',choices=('orderly','sysrq-b'),default='orderly')
    p.add_argument('--boot-stop',choices=('interrupt','gp7'),default='interrupt',help='gp7: one-shot boot stop; kernel reboot argument for orderly, RTC nvmem arm for SysRq-b')
    p.add_argument('--require-video',action='store_true',help='require locked 720p, active video units and advancing bridge counters')
    p.add_argument('--prepared',type=Path,default=ROOT/'build/hdmi-warm-shared-2026-10-23');p.add_argument('--port',default='/dev/ttyUSB0')
    a=p.parse_args();r=Run(a.output.resolve(),a.port,a.reset,a.require_video,a.boot_stop)
    if a.action=='run':r.run(a.prepared.resolve())
    elif a.action=='resume':r.resume(a.prepared.resolve(),a.cold_boot)
    else:r.poweroff()
if __name__=='__main__':main()
