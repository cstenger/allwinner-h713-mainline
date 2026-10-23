#!/usr/bin/env python3
"""Offline tests for the first warm shared-startup test (script, runner, checker)."""
import contextlib,importlib.util,io,json,pathlib,re,struct,tempfile,unittest,zlib
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def load(name,file):
    s=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=load('build_warm',HERE/'build-warm-shared.py');c=load('checker',HERE/'check-warm-shared.py');r=load('runner',ROOT/'tools/serial/run-warm-shared.py')
INSTALLED=(b.INSTALLED/'h713-hdmi.cmd').read_text()
EVID=ROOT/'docs/hdmi-evidence/2026-10-22-dsp-retention-live'

class Script(unittest.TestCase):
    def setUp(self):self.text=b.warm_script(INSTALLED)
    def test_only_the_reviewed_differences_from_the_installed_cold_branch(self):
        old,new=b.stages(INSTALLED),b.stages(self.text)
        self.assertEqual(set(old),set(new))
        for name in old:
            if name not in ('hdmi_launch','hdmi_source'):self.assertEqual(old[name],new[name],name)
        self.assertEqual(new['hdmi_launch'],old['hdmi_launch'].replace("'itest.l *0x0306101c == 0 && gpio clear PB5 && "+b.GP6_WRITE,"'itest.l *0x0306101c == 0 && "+b.CENSUS+"gpio clear PB5 && "))
        self.assertEqual(new['hdmi_source'],old['hdmi_source'].replace(b.COLD_ECHO,b.WARM_ECHO))
        # The loop that discovers the source-3 PID is the installed one, unchanged.
        cold_body=INSTALLED.split('\nelse\n',1)[1].rsplit('else gpio set PB5; echo H713 HDMI preparation/launch failed',1)[0]
        self.assertIn(cold_body,self.text)
    def test_never_writes_gp6_gp7_or_env(self):
        self.assertNotIn('mw.l 0x07090118',self.text);self.assertNotIn('mw.l 0x0709011c',self.text)
        self.assertIsNone(re.search(r'(^|&& |; |\n\s*)env ',self.text))
        for bad in ('saveenv','setenv bootargs','0x07091','0x06940000','gpio set PB5\n    if h713_disp auto'):self.assertNotIn(bad,self.text)
    def test_runs_only_on_cold_path_latch_with_census_before_logo(self):
        self.assertIn('if itest.l *0x07090118 == 48444d49; then\n',self.text)
        self.assertNotIn('*0x07090118 != 0',self.text);self.assertNotIn('*0x07090118 == 0;',self.text)
        launch=b.stages(self.text)['hdmi_launch']
        for check in ('itest.l *0x0306101c == 0','itest.l *0x0709011c == 0','itest.l *0x070101ac == 0','itest.l *0x07090118 == 48444d49'):
            self.assertLess(launch.index(check),launch.index('h713_disp auto 0x34 logo'),check)
        self.assertEqual(self.text.count('bootm '),1);self.assertEqual(self.text.count('h713_disp auto 0x34 logo'),1)
        self.assertNotIn('warm logo',self.text);self.assertTrue(self.text.rstrip().endswith('else echo H713 WARM-SHARED requires the cold-path latch; false; fi'))
    def test_changed_installed_script_is_refused(self):
        with self.assertRaises(ValueError):b.warm_script(INSTALLED.replace('mw.l 0x07090118 0x48444d49 && ',''))
        with self.assertRaises(ValueError):b.warm_script(INSTALLED.replace(b.COLD_ECHO,'echo other'))
    def test_built_image_matches_text_and_legacy_crc(self):
        out=ROOT/'build/hdmi-warm-shared-2026-10-23'
        if not out.exists():self.skipTest('candidate not built')
        scr=(out/'warm-shared.scr').read_bytes();hdr=bytearray(scr[:64]);hcrc=struct.unpack('>I',hdr[4:8])[0];hdr[4:8]=b'\0'*4
        self.assertEqual(zlib.crc32(bytes(hdr)),hcrc);self.assertEqual(zlib.crc32(scr[64:]),struct.unpack('>I',scr[24:28])[0])
        n=struct.unpack('>I',scr[64:68])[0];self.assertEqual(scr[72:72+n].decode(),self.text);self.assertEqual((out/'warm-shared.cmd').read_text(),self.text)
        m=json.loads((out/'manifest.json').read_text());self.assertEqual(m['installed_script_sha256'],b.SCRIPT_SHA)

def feed(stage,data,size=97):
    results=[]
    for i in range(0,len(data),size):
        x=stage.feed(data[i:i+size])
        if x:results.append(x)
        if x=='done':break
    return results
COLD=(EVID/'cold-catch/serial.log').read_bytes().rsplit(b'=>',1)[0]+(EVID/'cold-production-uart.log').read_bytes()
REBOOT=(EVID/'warm-catch/serial.log').read_bytes()
WARM=(EVID/'cold-production-uart.log').read_bytes().replace(b'H713 HDMI cold startup handoff verified',b'H713 WARM-SHARED startup handoff verified')
class Stream(unittest.TestCase):
    """Stage matchers on real UART from the October 22 production runs."""
    def test_cold_production_boot_is_watched_never_interrupted(self):
        s=r.cold_stage();self.assertEqual(feed(s,COLD),['done']);self.assertFalse(s.sent);r.check_cold_preboot(s.preboot())
    def test_orderly_reboot_sends_exactly_one_space_then_completes(self):
        s=r.reboot_stage();self.assertEqual(feed(s,REBOOT),['space','done']);r.check_warm_preboot(s.preboot())
    def test_warm_shared_boot_completes(self):
        s=r.warm_stage();self.assertEqual(feed(s,b'## Executing script at 52000000\r\n'+WARM),['done'])
    def test_failures_stop_the_run(self):
        cases=[(r.reboot_stage,REBOOT.replace(b'reboot: Restarting system',b'h713-hdmi-hold-guard: reboot refused, HDMI holds retained\r\nreboot: Restarting system')),
               (r.reboot_stage,REBOOT.replace(b'Hit any key',b'H713 RESET v1 stage=pre_workspace\r\nHit any key')),
               (r.reboot_stage,REBOOT+REBOOT[REBOOT.index(b'U-Boot SPL'):]),
               (r.cold_stage,COLD.replace(b'H713 panel 720p',b'H713 HDMI launch latch set - capture disabled\r\nH713 panel 720p')),
               (r.warm_stage,b'## Executing script\r\nH713 WARM-SHARED requires the cold-path latch\r\n'),
               (r.warm_stage,b'## Executing script\r\n'+WARM.replace(b'Starting kernel',b'U-Boot SPL x\r\nStarting kernel')),
               (r.warm_stage,b'## Executing script\r\nH713 HDMI source/boot failed - cold cycle required\r\n')]
        for make,data in cases:
            with self.assertRaises(RuntimeError):feed(make(),data)
    def test_logo_marker_is_only_forbidden_before_the_interrupt(self):
        self.assertIn(b'stage=pre_workspace',COLD);self.assertEqual(feed(r.cold_stage(),COLD),['done'])
    def test_preboot_checks(self):
        r.check_cold_preboot({'gp6':'00000000','gp7':'00000000','mips_clk':'00000000','mips_reset':'00000000','mips_status':'00000000'})
        with self.assertRaises(RuntimeError):r.check_cold_preboot({'gp6':'48444d49','gp7':'00000000','mips_clk':'0','mips_reset':'0','mips_status':'00000000'})
        for bad in ({'gp6':'00000000'},{'gp7':'00000001'},{'mips_status':'00000001'},{'mips_clk':'00000003'},{'mips_reset':'00070000'}):
            p={'gp6':'48444d49','gp7':'00000000','mips_clk':'00000000','mips_reset':'00000000','mips_status':'00000000'};p.update(bad)
            with self.assertRaises(RuntimeError):r.check_warm_preboot(p)

class Census(unittest.TestCase):
    """The prompt census refuses any difference before anything is sent."""
    def console(self,values,crc):
        sent=[]
        class Con:
            def __init__(s,fd,raw):pass
            def run(s,line):
                sent.append(line)
                if line=='printenv bootcmd':return b'bootcmd='+r.BOOTCMD.encode()+b'\r\n=> '
                m=re.match(r'md.l 0x([0-9a-f]{8}) 1',line)
                if m:a=int(m.group(1),16);return b'%08x: %08x    ....\r\n=> '%(a,values[a])
                if line.startswith('crc32'):return b'crc32 for 50000000 ... ==> %08x\r\n=> '%crc
                raise AssertionError(line)
            def checked(s,line):sent.append(line)
        warm=load('warm',ROOT/'tools/serial/warm-retention-uboot.py')
        return mock.MagicMock(Console=Con,warm=warm),sent
    def run_census(self,values,crc=None):
        fit_crc=zlib.crc32(r.FIT.read_bytes()) if crc is None else crc
        fake,sent=self.console(values,fit_crc)
        with tempfile.TemporaryDirectory() as t,mock.patch.object(r,'load',return_value=fake):
            run=r.Run(pathlib.Path(t),'x');run.census(None,io.BytesIO(),{});return sent
    GOOD={0x07090118:0x48444d49,0x0709011c:0,0x0306101c:0,0x070101ac:0}
    def test_good_census_loads_and_crcs_the_fit(self):
        sent=self.run_census(dict(self.GOOD));self.assertIn('fatload mmc 1:2 0x50000000 h713-kernel.fit',sent)
    def test_any_difference_refused_before_fit(self):
        for a,v in ((0x07090118,0),(0x0709011c,1),(0x0306101c,1),(0x070101ac,0x10001)):
            vals=dict(self.GOOD);vals[a]=v
            with self.assertRaises(RuntimeError):self.run_census(vals)
    def test_fit_crc_mismatch_refused(self):
        with self.assertRaises(RuntimeError):self.run_census(dict(self.GOOD),crc=1)

def sample(t,periods,play,xruns=0,owner='hdmi-speaker',cap='state: RUNNING',ps='state: RUNNING'):
    return {'t':t,'periods':periods,'xruns':xruns,'capture_state':cap,'capture_owner':owner,'capture_ptr':periods*256,'play_state':ps,'play_owner':owner,'play_ptr':play}
def flow(rate=48000.0,play_rate=48000.0,**kw):
    return [sample(10.0,1000,500000),sample(13.0,1000+int(3*rate/256),500000+int(3*play_rate),**kw)]
GOOD_REC=lambda label='cold',boot='b1':{'label':label,'boot_id':boot,'check_startup':{'rc':0,'output':'...\nPASS'},'speaker':'active',
    'dsp_lines':['h713-hdmi-audio: DSP versions 0000/0000','h713-hdmi-audio: pinned 724-pair DSP patch verified versions 1/1'],'flow':flow()}
class Checker(unittest.TestCase):
    def test_period_counter_undercount_is_not_judged(self):
        # Real October 23 samples: pointer 47979 Hz, period counter 47287 Hz.
        f=[{'t':0.0,'periods':0,'xruns':0,'capture_state':'state: RUNNING','capture_owner':'hdmi-speaker','capture_ptr':0,'play_state':'state: RUNNING','play_owner':'hdmi-speaker','play_ptr':0},
           {'t':3.0,'periods':int(3*47287/256),'xruns':0,'capture_state':'state: RUNNING','capture_owner':'hdmi-speaker','capture_ptr':int(3*47979),'play_state':'state: RUNNING','play_owner':'hdmi-speaker','play_ptr':144000}]
        rec=GOOD_REC();rec['flow']=f;self.assertTrue(c.evaluate(rec)['passed'])
        rec['flow'][1]['capture_ptr']=int(3*44100);self.assertFalse(c.evaluate(rec)['passed'])
    def test_good_session_passes(self):
        res=c.evaluate(GOOD_REC());self.assertTrue(res['passed'],res['reasons']);self.assertAlmostEqual(res['flow']['period_rate'],48000,delta=200)
    def test_each_failure_is_reported(self):
        cases=(('check_startup',{'rc':1,'output':'FAIL: x'},'check-startup'),('speaker','inactive','speaker not active'),('flow',None,'no audio flow'),
               ('flow',flow(rate=44100),'capture rate'),('flow',flow(play_rate=0),'playback not advancing'),('flow',flow(xruns=0)[:1]+[sample(13.0,1562,644000,xruns=2)],'xruns'),
               ('flow',flow(owner='pipewire'),'not owned by hdmi-speaker'),('flow',flow(cap='state: PREPARED'),'capture PCM not RUNNING'),('flow',flow(ps='state: SETUP'),'playback not RUNNING'),
               ('dsp_lines',['h713-hdmi-audio: DSP versions 0001/0001','pinned 724-pair DSP patch verified versions 1/1'],'0/0'),('dsp_lines',['h713-hdmi-audio: DSP versions 0000/0000'],'1/1'))
        for key,value,why in cases:
            rec=GOOD_REC();rec[key]=value;res=c.evaluate(rec)
            self.assertFalse(res['passed'],key);self.assertTrue(any(why in x for x in res['reasons']),(key,why,res['reasons']))
    def test_pass_requires_last_line_pass(self):
        rec=GOOD_REC();rec['check_startup']={'rc':0,'output':'PASS\nsomething after'};self.assertFalse(c.evaluate(rec)['passed'])
    def test_compare(self):
        self.assertTrue(c.compare(GOOD_REC(),GOOD_REC('warm','b2'))['passed'])
        self.assertFalse(c.compare(GOOD_REC(),GOOD_REC('warm','b1'))['passed'])
        self.assertFalse(c.compare(GOOD_REC('warm','b2'),GOOD_REC())['passed'])
        bad=GOOD_REC('warm','b2');bad['speaker']='failed';self.assertFalse(c.compare(GOOD_REC(),bad)['passed'])
    def test_remote_script_compiles_and_never_adds_a_reader_or_restarts(self):
        compile(c.REMOTE,'remote','exec')
        for bad in ('systemctl restart','systemctl start','systemctl stop','insmod','rmmod','/dev/mem','devmem','07091','pw-record','arecord','alsasrc','hw:H713HDMI'):self.assertNotIn(bad,c.REMOTE)
    def test_remote_waits_for_speaker_playback_before_sampling(self):
        self.assertLess(c.REMOTE.index("startswith('state: RUNNING')"),c.REMOTE.index('a=sample()'))
    def test_collect_sends_check_startup_unchanged(self):
        calls=[]
        def run(cmd,**kw):
            calls.append((cmd[-1],kw.get('input')));return mock.MagicMock(returncode=0,stdout=json.dumps({'label':'cold'}),stderr='')
        with mock.patch.object(c.subprocess,'run',run):c.collect('cold')
        self.assertEqual(calls[0],('cat > /run/h713-warm-shared-check.py',c.REMOTE))
        self.assertEqual(calls[1],('python3 /run/h713-warm-shared-check.py cold',(ROOT/'tools/hdmi/check-startup.sh').read_text()))

class Resume(unittest.TestCase):
    """Resume continues only an untouched recorded cold session."""
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.out=pathlib.Path(self.t.name)/'run';self.out.mkdir()
        self.prepared=ROOT/'build/hdmi-warm-shared-2026-10-23'
        if not self.prepared.exists():self.skipTest('candidate not built')
        (self.out/'manifest.json').write_text((self.prepared/'manifest.json').read_text())
        (self.out/'uart-cold-and-reboot.log').write_bytes(COLD)
        (self.out/'events.log').write_text('x OPEN /dev/ttyUSB0\nx cold-boot: complete\nx cold boot B1\nx cold health passed=False\n')
        (self.out/'cold-health.json').write_text('{}')
    def tearDown(self):self.t.cleanup()
    def attempt(self,boot='B1',running='B1'):
        run=r.Run(self.out,'x')
        with mock.patch.object(run,'wait_ssh',return_value=running),mock.patch.object(r,'open_port') as op,mock.patch.object(run,'reboot_from_cold',side_effect=RuntimeError('reached reboot')) as rb:
            with self.assertRaises(RuntimeError) as e:run.resume(self.prepared,boot)
        return str(e.exception),op.called
    def test_good_resume_reaches_the_reboot_and_keeps_attempt1(self):
        msg,opened=self.attempt();self.assertEqual(msg,'reached reboot');self.assertTrue(opened)
        self.assertTrue((self.out/'cold-health-attempt1.json').exists());self.assertFalse((self.out/'cold-health.json').exists())
    def test_refusals_before_the_uart_is_opened(self):
        for change in ('reboot','launch','other-boot','wrong-arg','no-failure','resumed'):
            self.setUp()
            if change=='reboot':(self.out/'events.log').write_text((self.out/'events.log').read_text()+'x REBOOT REQUESTED\n')
            if change=='launch':(self.out/'launch-attempted').write_text('x')
            if change=='no-failure':(self.out/'events.log').write_text((self.out/'events.log').read_text().replace('passed=False','passed=True'))
            if change=='resumed':(self.out/'uart-resume-and-reboot.log').write_bytes(b'')
            msg,opened=self.attempt(boot='B2' if change=='wrong-arg' else 'B1',running='B9' if change=='other-boot' else 'B1')
            self.assertNotEqual(msg,'reached reboot',change);self.assertFalse(opened,change)

class Runner(unittest.TestCase):
    def test_refuses_existing_output_and_changed_script(self):
        prepared=ROOT/'build/hdmi-warm-shared-2026-10-23'
        if not prepared.exists():self.skipTest('candidate not built')
        with tempfile.TemporaryDirectory() as t:
            out=pathlib.Path(t)/'run';out.mkdir()
            with mock.patch.object(r,'open_port') as op,self.assertRaises(FileExistsError):r.Run(out,'x').run(prepared)
            op.assert_not_called()
            fake=pathlib.Path(t)/'prep';fake.mkdir();(fake/'warm-shared.scr').write_bytes(b'other')
            (fake/'manifest.json').write_text((prepared/'manifest.json').read_text())
            with mock.patch.object(r,'open_port') as op,self.assertRaises(AssertionError):r.Run(pathlib.Path(t)/'new','x').run(fake)
            op.assert_not_called()
    def test_ssh_deadline_is_uncertain_not_retried(self):
        calls=[]
        def run(*a,**k):calls.append(a);raise r.subprocess.TimeoutExpired('ssh',20)
        with tempfile.TemporaryDirectory() as t,mock.patch.object(r.subprocess,'run',run):
            with self.assertRaises(r.subprocess.TimeoutExpired):r.Run(pathlib.Path(t),'x').ssh('reboot-request','systemctl reboot --no-block')
            self.assertEqual(len(calls),1);self.assertTrue((pathlib.Path(t)/'reboot-request-uncertain.log').exists())
if __name__=='__main__':unittest.main()
