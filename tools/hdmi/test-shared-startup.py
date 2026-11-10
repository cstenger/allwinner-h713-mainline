#!/usr/bin/env python3
"""Offline production-startup tests: real generated shell, fake RTC and roots."""
import importlib.util,os,pathlib,shutil,struct,subprocess,tempfile,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
b=load('startup',HERE/'build-startup.py');h=load('ack',HERE/'h713-hdmi-health-ack.py');i=load('installer',HERE/'install-shared-startup.py');pack=load('package',HERE/'build-shared-startup.py')
SHELL=r'''
set -f
setenv() { printf -v "$1" '%s' "${*:2}"; }
itest() { local a=$((16#$1)) op=$2 z=$((16#$3)); if [ "$op" = '==' ]; then (( a == z )); else (( a != z )); fi; }
itest.l() {
 local value=0
 case "$1" in '*0x07090118') value=$gp6;; esac
 if [ "$1" = "$BAD" ]; then value=1; fi
 itest "$value" "$2" "$3"
}
mw.l() { echo "WRITE $1 $2"; [ "$1" = 0x07090118 ] || return 1; gp6=${2#0x}; }
gpio() { echo "GPIO $*"; }
h713_disp() { echo "FIRMWARE gp6=$gp6"; }
fatload() { return 0; }
bootm() { echo FALLBACK_BOOT; }
setexpr() { return 0; }
run() {
 echo "RUN $1"
 case "$1" in
 hdmi_launch)
  local cmd
  while IFS= read -r cmd; do
   eval "$cmd" || return 1
   if [[ "$cmd" == 'h713_disp auto '* ]]; then hdmi_count=1;hdmi_bad=0;hdmi_pid=8b8f275c;return 0;fi
  done < <(printf '%s\n' "$hdmi_launch" | sed 's/ \&\& /\n/g');;
 hdmi_record) hdmi_key=ffffffff;;
 hdmi_source) echo SHARED_BOOT;;
 esac
}
'''
def simulate(gp6,bad=''):
    text=SHELL+'\ngp6='+format(gp6,'x')+'\nBAD='+repr(bad)+'\n'+b.script()+'\nrc=$?;echo FINAL_GP6=$gp6;exit "$rc"\n'
    return subprocess.run(['bash','-c',text],capture_output=True,text=True)

class Startup(unittest.TestCase):
    def test_both_builders_include_the_health_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)/'bundle';b.build(out)
            for name in ('h713-hdmi-health-ack.py','h713-hdmi-health-ack.service','check-startup.sh','install-shared-startup.py'):
                self.assertTrue((out/name).is_file(),name)
            self.assertFalse((out/'install-startup.sh').exists())
            i.verify(out)
    def test_four_states_and_unacknowledged_second_boot(self):
        for word,shared in ((0,True),(h.HDOK,True),(h.HDMI,False),(0xdeadbeef,False)):
            r=simulate(word);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual('SHARED_BOOT' in r.stdout,shared)
            self.assertEqual('FALLBACK_BOOT' in r.stdout,not shared)
            if shared:
                self.assertIn('FIRMWARE gp6=48444d49',r.stdout)
                self.assertLess(r.stdout.index('WRITE 0x07090118'),r.stdout.index('FIRMWARE'))
                # An unacknowledged launch leaves HDMI and must fall back next boot.
                next_boot=simulate(h.HDMI);self.assertNotIn('SHARED_BOOT',next_boot.stdout)
            else:self.assertNotIn('WRITE',r.stdout)
    def test_each_census_failure_stops_before_lamp_or_firmware(self):
        for addr in ('0306101c','02001600','0200160c','0709011c','070101ac'):
            for state in (0,h.HDOK):
                r=simulate(state,'*0x'+addr);self.assertNotEqual(r.returncode,0);self.assertNotIn('FIRMWARE',r.stdout)
                self.assertNotIn('GPIO clear',r.stdout);self.assertNotIn('WRITE',r.stdout);self.assertIn('GPIO set PB5',r.stdout)
    def test_proven_source_and_image_stages_unchanged_except_echo(self):
        def stages(s):return {l.split()[1]:l for l in s.splitlines() if l.startswith('setenv hdmi_')}
        old=stages((pack.OLD/'h713-hdmi.cmd').read_text());new=stages(b.script())
        for key in ('hdmi_image','hdmi_record'):self.assertEqual(new[key],old[key])
        self.assertEqual(new['hdmi_source'],old['hdmi_source'].replace('HDMI cold startup','HDMI shared startup'))
        self.assertNotIn('mw.l 0x0709011c',b.script());self.assertNotIn('0x07091',b.script());self.assertNotIn('0x06940000',b.script())

class Ack(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
        self.board=h.Board(self.root)
        def put(name,data):
            p=self.board.path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.put=put
        put('/proc/sys/kernel/random/boot_id',b'B1')
        put('/proc/device-tree/chosen/h713,hdmi-boot-v1',struct.pack('>III',h.HDMI,0,123))
        put('/run/h713-hdmi-session/state.json',b'{"boot_id":"B1","phase":"ready"}')
        rtc=self.board.path('/sys/firmware/devicetree/base/soc/rtc@7090000');self.rtc=rtc
        put('/sys/firmware/devicetree/base/soc/rtc@7090000/compatible',b'allwinner,sun50i-h713-rtc\0')
        put('/sys/firmware/devicetree/base/soc/rtc@7090000/reg',bytes.fromhex('0709000000000400'))
        dev=self.board.path('/sys/devices/platform/7090000.rtc');provider=dev/'nvmem0';provider.mkdir(parents=True)
        driver=self.board.path('/sys/bus/platform/drivers/sun6i-rtc');driver.mkdir(parents=True);(dev/'driver').symlink_to(driver)
        (provider/'of_node').symlink_to(rtc);self.bank=provider/'nvmem';self.original=bytes(range(24))+struct.pack('<II',h.HDMI,0);self.bank.write_bytes(self.original)
        bus=self.board.path('/sys/bus/nvmem/devices');bus.mkdir(parents=True);(bus/'nvmem0').symlink_to(provider);self.bus=bus
        self.command=mock.patch.object(self.board,'command',return_value='...\nPASS\n').start();self.addCleanup(mock.patch.stopall)
    def test_single_gp6_write_idempotence_and_dry_run(self):
        real=os.pwrite
        with mock.patch.object(h.os,'pwrite',wraps=real) as write:
            self.assertFalse(h.acknowledge(self.board,True)['written']);write.assert_not_called();self.assertEqual(self.bank.read_bytes(),self.original)
            self.assertTrue(h.acknowledge(self.board)['written']);self.assertEqual(write.call_count,1)
            self.assertEqual(write.call_args.args[1:],(struct.pack('<I',h.HDOK),0x18))
            self.assertEqual(self.bank.read_bytes()[:24],self.original[:24]);self.assertEqual(self.bank.read_bytes()[28:],bytes(4))
            self.assertFalse(h.acknowledge(self.board)['written']);self.assertEqual(write.call_count,1)
    def test_health_handoff_and_session_fail_closed(self):
        cases=[('/proc/device-tree/chosen/h713,hdmi-boot-v1',b'bad'),
               ('/proc/device-tree/chosen/h713,hdmi-boot-v1',struct.pack('>III',h.HDMI,0,0)),
               ('/run/h713-hdmi-session/state.json',b'{"boot_id":"B2","phase":"ready"}'),
               ('/run/h713-hdmi-session/state.json',b'{"boot_id":"B1","phase":"failed"}')]
        for name,data in cases:
            p=self.board.path(name);original=p.read_bytes();p.write_bytes(data)
            with mock.patch.object(h.os,'pwrite') as write:
                with self.assertRaises(RuntimeError):h.acknowledge(self.board,True)
                write.assert_not_called()
            p.write_bytes(original)
        self.command.return_value='FAIL\n'
        with self.assertRaises(RuntimeError):h.acknowledge(self.board,True)
    def test_wrong_latches_pending_gp7_and_provider_rejected_without_write(self):
        for word,gp7 in ((0,0),(0xdeadbeef,0),(h.HDMI,0xb007c0de)):
            self.bank.write_bytes(self.original[:24]+struct.pack('<II',word,gp7))
            with self.assertRaises(RuntimeError):h.acknowledge(self.board,True)
        self.bank.write_bytes(self.original)
        (self.bus/'duplicate').symlink_to((self.bus/'nvmem0').resolve())
        with self.assertRaises(RuntimeError):h.acknowledge(self.board,True)
        (self.bus/'duplicate').unlink();(self.rtc/'reg').write_bytes(b'bad')
        with self.assertRaises(RuntimeError):h.acknowledge(self.board,True)
    def test_boot_or_latch_change_and_short_write_readback_failure_no_retry(self):
        with mock.patch.object(self.board,'healthy',side_effect=['B1','B2']),mock.patch.object(h.os,'pwrite') as write:
            with self.assertRaises(RuntimeError):h.acknowledge(self.board)
            write.assert_not_called()
        with mock.patch.object(h.os,'pread',side_effect=[self.original[24:],bytes(8)]),mock.patch.object(h.os,'pwrite') as write:
            with self.assertRaisesRegex(RuntimeError,'GP6/GP7 changed'):h.acknowledge(self.board)
            write.assert_not_called()
        with mock.patch.object(h.os,'pwrite',return_value=0) as write:
            with self.assertRaisesRegex(RuntimeError,'short GP6 write'):h.acknowledge(self.board)
            self.assertEqual(write.call_count,1)
        with mock.patch.object(h.os,'pwrite',return_value=4) as write:
            with self.assertRaisesRegex(RuntimeError,'readback mismatch'):h.acknowledge(self.board)
            self.assertEqual(write.call_count,1)
    def test_unit_does_not_require_signal_lock_or_start_consumers(self):
        unit=(HERE/'h713-hdmi-health-ack.service').read_text()
        self.assertIn('Requires=h713-hdmi-capture.service h713-hdmi-signal.service',unit)
        self.assertIn('After=h713-hdmi-capture.service h713-hdmi-signal.service',unit)
        self.assertIn('ConditionPathExists=/proc/device-tree/chosen/h713,hdmi-boot-v1',unit)
        self.assertIn('Restart=no',unit)
        for name in ('speaker','video','ring','ExecStop'):self.assertNotIn(name,unit)

class Installer(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.top=pathlib.Path(tmp.name);self.root=self.top/'root';self.bundle=self.top/'bundle';pack.build(self.bundle)
        for d in (i.BACKEND,i.STATE,i.FAT,'etc/systemd/system'): (self.root/d).mkdir(parents=True,exist_ok=True)
        for name in ('h713-hdmi.scr','h713-hdmi.cmd'):shutil.copyfile(pack.OLD/name,self.root/i.BACKEND/name)
        (self.root/i.BACKEND/'unchanged.ko').write_bytes(b'production module')
        names=('h713-hdmi.scr','h713-hdmi.cmd','unchanged.ko')
        (self.root/i.BACKEND/'SHA256SUMS').write_text(''.join(i.sha(self.root/i.BACKEND/n)+'  '+n+'\n' for n in names))
        shutil.copyfile(pack.OLD/'h713-hdmi.scr',self.root/i.FAT/'h713-hdmi.scr')
        shutil.copyfile(b.FIT,self.root/i.FAT/'h713-kernel.fit')
        (self.root/i.STATE/'kernel.sha256').write_text(pack.FIT_SHA+'  /mnt/boot/h713-kernel.fit\n')
        self.calls=[];self.control=lambda args:self.calls.append(args)
    def snapshot(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def test_dry_run_then_install_and_verified_rollback(self):
        before=self.snapshot();i.install(self.root,self.bundle,self.control,True);self.assertEqual(self.snapshot(),before);self.assertEqual(self.calls,[])
        result=i.install(self.root,self.bundle,self.control);backup=pathlib.Path(result['backup'])
        self.assertEqual(self.calls,[['daemon-reload'],['enable','h713-hdmi-health-ack.service']])
        self.assertEqual((self.root/i.FAT/'h713-hdmi.scr').read_bytes(),(self.bundle/'h713-hdmi.scr').read_bytes())
        i.verify(self.root/i.BACKEND);self.assertTrue((backup/'COMMITTED').exists())
        self.assertEqual((self.root/i.BACKEND/'unchanged.ko').read_bytes(),b'production module')
        current=self.snapshot();i.rollback(self.root,backup,self.control,True);self.assertEqual(self.snapshot(),current)
        i.rollback(self.root,backup,self.control)
        for name,data in before.items():self.assertEqual((self.root/name).read_bytes(),data,name)
        self.assertFalse((self.root/i.HEALTH).exists());self.assertFalse((self.root/i.UNIT).exists())
    def test_foreign_script_kernel_or_modified_backend_refused_in_dry_run(self):
        for path in (self.root/i.FAT/'h713-hdmi.scr',self.root/i.FAT/'h713-kernel.fit',self.root/i.BACKEND/'unchanged.ko'):
            old=path.read_bytes();path.write_bytes(b'foreign');before=self.snapshot()
            with self.assertRaises(RuntimeError):i.install(self.root,self.bundle,self.control,True)
            self.assertEqual(self.snapshot(),before);self.assertEqual(self.calls,[]);path.write_bytes(old)
    def test_failed_enable_leaves_old_boot_and_recoverable_backup(self):
        before=(self.root/i.FAT/'h713-hdmi.scr').read_bytes()
        def fail(args):
            if args[0]=='enable':raise RuntimeError('injected enable failure')
        with self.assertRaises(RuntimeError):i.install(self.root,self.bundle,fail)
        self.assertEqual((self.root/i.FAT/'h713-hdmi.scr').read_bytes(),before)
        backup=next((self.root/i.STATE).glob('shared-*'));self.assertTrue((backup/'INCOMPLETE').exists())
        i.rollback(self.root,backup,self.control);self.assertEqual((self.root/i.FAT/'h713-hdmi.scr').read_bytes(),before)
    def test_failed_partial_backend_update_can_rollback_without_module_change(self):
        before=self.snapshot();real=i.atomic
        def fail(path,data):
            if path==self.root/i.BACKEND/'h713-hdmi.cmd':raise RuntimeError('injected command-copy failure')
            return real(path,data)
        with mock.patch.object(i,'atomic',side_effect=fail):
            with self.assertRaises(RuntimeError):i.install(self.root,self.bundle,self.control)
        self.assertEqual((self.root/i.FAT/'h713-hdmi.scr').read_bytes(),before[i.FAT+'/h713-hdmi.scr'])
        backup=next((self.root/i.STATE).glob('shared-*'));i.rollback(self.root,backup,self.control)
        for name,data in before.items():self.assertEqual((self.root/name).read_bytes(),data)

if __name__=='__main__':unittest.main()
