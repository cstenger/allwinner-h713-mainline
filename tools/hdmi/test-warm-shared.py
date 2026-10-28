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
    def console(self,values,crc,env=None):
        sent=[]
        class Con:
            def __init__(s,fd,raw):pass
            def run(s,line):
                sent.append(line)
                if line=='printenv bootcmd':return b'bootcmd='+r.BOOTCMD.encode()+b'\r\n=> '
                if env is not None and line.startswith('printenv '):
                    key=line.split()[1];return (key+'='+env[key]+'\r\n=> ').encode()
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
    def test_uart_transient_eagain_keeps_reading_but_real_errors_stop(self):
        for error in (BlockingIOError(11,'try again'),OSError(5,'I/O error')):
            uart=r.Uart.__new__(r.Uart)
            uart.fd=123;uart.raw=io.BytesIO();uart.data=b'';uart.lock=r.threading.Lock();uart.error=None;uart.stopping=False
            def read(*args):
                if not calls:
                    calls.append(1);raise error
                uart.stopping=True;return b'next UART bytes'
            calls=[]
            with mock.patch.object(r.select,'select',return_value=([123],[],[])),mock.patch.object(r.os,'read',side_effect=read):uart.loop()
            if isinstance(error,BlockingIOError):
                self.assertIsNone(uart.error);self.assertEqual(uart.data,b'next UART bytes');self.assertEqual(uart.raw.getvalue(),uart.data)
            else:self.assertIs(uart.error,error);self.assertEqual(uart.data,b'')
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
class GP7Stop(unittest.TestCase):
    def trace(self):
        return REBOOT.replace(b'gp7=00000000',b'gp7=b007c0de')
    def test_gp7_prompt_requires_markers_but_never_sends_an_interrupt(self):
        stage=r.reboot_stage('orderly','gp7')
        self.assertEqual(feed(stage,self.trace(),size=1),['done'])
        self.assertFalse(stage.sent);self.assertFalse(stage.interrupt)
        r.check_warm_preboot(stage.preboot(),'gp7')
        with self.assertRaises(RuntimeError):r.check_warm_preboot(r.reboot_stage().preboot(),'gp7')
        p=stage.preboot();p['gp7']='00000000'
        with self.assertRaises(RuntimeError):r.check_warm_preboot(p,'gp7')
    def test_gp7_missing_markers_extra_reset_or_automatic_boot_never_launches(self):
        for marker in (b'reboot: Restarting system',b'U-Boot SPL ',b'stage=proper_preboot',b'=> '):
            self.assertNotIn('done',feed(r.reboot_stage('orderly','gp7'),self.trace().replace(marker,b'MISSING')))
        for bad in (b'stage=pre_workspace',b'Starting kernel',b'## Executing script',b'boot logo published',b'hold-guard: reboot refused'):
            with self.assertRaises(RuntimeError):r.reboot_stage('orderly','gp7').feed(self.trace().replace(b'=> ',bad+b'\r\n=> '))
        with self.assertRaises(RuntimeError):r.reboot_stage('orderly','gp7').feed(self.trace()+self.trace())
    def test_prompt_env_and_consumed_gp7_are_verified_before_fit_load(self):
        startup=load('startup_for_tests',HERE/'build-startup.py')
        for key,val in ((None,None),('preboot','usb start'),('bootdelay','5'),('gp7',0xb007c0de)):
            env={'preboot':startup.PREBOOT,'bootdelay':'-1'};values=dict(Census.GOOD)
            if key in env:env[key]=val
            if key=='gp7':values[0x0709011c]=val
            fake,sent=Census().console(values,zlib.crc32(r.FIT.read_bytes()),env)
            with tempfile.TemporaryDirectory() as t,mock.patch.object(r,'load',return_value=fake):
                run=r.Run(pathlib.Path(t),'unused',boot_stop='gp7')
                if key is None:run.census(None,io.BytesIO(),{})
                else:
                    with self.assertRaises(RuntimeError):run.census(None,io.BytesIO(),{})
            self.assertEqual(any(x.startswith('fatload ') for x in sent),key is None)
            self.assertFalse(any('saveenv' in x or 'mw.l' in x or 'setenv' in x for x in sent))
    def test_orderly_trigger_uses_kernel_bootloader_argument_only_after_guards(self):
        script=r.orderly_bootstop_script('B1');compile(script,'gp7-trigger','exec')
        for failure in (None,'boot','compatible','magic','bound','help'):
            class P:
                def __init__(self,path):self.path=str(path)
                def __truediv__(self,key):return P(self.path+'/'+key)
                def read_text(self):return 'other' if failure=='boot' else 'B1'
                def read_bytes(self):
                    if self.path.endswith('compatible'):return b'wrong' if failure=='compatible' else b'nvmem-reboot-mode\0'
                    return b'wrong' if failure=='magic' else bytes.fromhex('b007c0de')
                def is_dir(self):return failure!='bound'
            calls=[]
            def command(cmd,**kw):
                calls.append(cmd)
                return mock.Mock(stdout='' if failure=='help' else '--reboot-argument=ARG')
            with mock.patch('pathlib.Path',P),mock.patch('subprocess.run',command):
                if failure:
                    with self.assertRaises(RuntimeError):exec(script,{})
                else:exec(script,{})
            self.assertEqual(['systemctl','reboot','--no-block','--reboot-argument=bootloader'] in calls,failure is None,failure)
        for bad in ('devmem','/dev/mem','07090118','0709011c','saveenv','--force'):
            self.assertNotIn(bad,script)
    def test_gp7_request_is_detached_once_and_intent_precedes_submission(self):
        p={'gp6':'48444d49','gp7':'b007c0de','mips_clk':'00000000','mips_reset':'00000000','mips_status':'00000000'}
        with tempfile.TemporaryDirectory() as t:
            run=r.Run(pathlib.Path(t),'unused',require_video=True,boot_stop='gp7')
            def request(name,command,**kw):
                self.assertIn('REBOOT REQUESTED orderly',(run.out/'events.log').read_text())
                self.assertTrue(command.startswith('setsid nohup python3 -c '))
                self.assertTrue(command.endswith('< /dev/null &'))
            stage=mock.Mock();stage.preboot.return_value=p
            with mock.patch.object(run,'health',return_value=({'boot_id':'B1'},{'passed':True})),mock.patch.object(run,'ssh',side_effect=request) as ssh,mock.patch.object(run,'watch',return_value=(stage,0)) as watch:
                run.reboot_from_cold(mock.Mock(data=b''))
                self.assertEqual(ssh.call_count,1);self.assertFalse(watch.call_args.args[1].interrupt)
            self.assertEqual((run.out/'orderly-bootstop-trigger.py.txt').read_text(),r.orderly_bootstop_script('B1'))
    def test_invalid_reset_and_resume_mode_changes_refused_before_uart(self):
        with mock.patch.object(r,'open_port') as op:
            with self.assertRaises(ValueError):r.Run(pathlib.Path('/unused'),'unused',reset='invalid',boot_stop='gp7')
            op.assert_not_called()
        fixture=Resume();fixture.setUp()
        try:
            run=r.Run(fixture.out,'unused',boot_stop='gp7')
            with mock.patch.object(r,'open_port') as op,mock.patch.object(run,'wait_ssh') as ssh:
                with self.assertRaisesRegex(RuntimeError,'resume options differ'):run.resume(fixture.prepared,'B1')
                op.assert_not_called();ssh.assert_not_called()
        finally:fixture.tearDown()

class VideoAndAbrupt(unittest.TestCase):
    def video_rec(self):
        rec=GOOD_REC()
        rec['bridge_dmesg']=['h713-hdmi-v4l2: registered']
        rec['video']=[{'t':10+i*3,'signal':'locked 1280x720',
                       'units':{'h713-hdmi-ring':'active','h713-hdmi-video':'active'},
                       'counters':{'frames_produced':100+i*180,'frames_delivered':100+i*179,'frames_rejected':0}}
                      for i in range(2)]
        return rec
    def test_video_gate_rejects_missing_unlocked_stalled_or_rejected_video(self):
        self.assertTrue(c.evaluate(self.video_rec(),require_video=True)['passed'])
        cases=[('video',[]),('bridge_dmesg',[])]
        for key,val in cases:
            rec=self.video_rec();rec[key]=val;self.assertFalse(c.evaluate(rec,True)['passed'])
        for key,val in (('signal','holding 1280x720'),('units',{}),('t',9),
                        ('counters',{'frames_produced':100,'frames_delivered':100,'frames_rejected':1}),('counters',{})):
            rec=self.video_rec();rec['video'][1][key]=val;self.assertFalse(c.evaluate(rec,True)['passed'],key)
        rec=self.video_rec();del rec['video']
        self.assertTrue(c.evaluate(rec)['passed']);self.assertFalse(c.evaluate(rec,True)['passed'])
    def test_compare_enforces_video_on_both_boots(self):
        a=self.video_rec();b=self.video_rec();b.update(label='warm',boot_id='b2')
        self.assertTrue(c.compare(a,b,True)['passed'])
        for bad in (a,b):
            saved=bad.pop('video');self.assertFalse(c.compare(a,b,True)['passed']);bad['video']=saved
    def test_abrupt_uart_requires_own_markers_and_exactly_one_reset(self):
        data=REBOOT.replace(b'reboot: Restarting system',r.ABRUPT_MARKER.encode()+b' boot=b1\r\nsysrq: Resetting')
        self.assertEqual(feed(r.reboot_stage('sysrq-b'),data,size=1),['space','done'])
        self.assertNotIn('done',feed(r.reboot_stage('sysrq-b'),REBOOT))
        with self.assertRaises(RuntimeError):r.reboot_stage('sysrq-b').feed(data+data)
    def test_abrupt_trigger_guards_boot_and_health_before_and_after_sync(self):
        script=r.abrupt_script('b1');events=[]
        class P:
            def __init__(self,path):self.path=path
            def read_text(self):
                if self.path.endswith('boot_id'):return boot[0]
                if self.path.endswith('dsp_failed'):return 'N'
                if self.path.endswith('/signal'):return 'locked 1280x720'
                return 'state: RUNNING\n'
        def opened(path,mode):
            events.append(path);f=mock.MagicMock();f.__enter__.return_value=f;f.fileno.return_value=123;return f
        def synced():
            events.append('sync')
            if change[0]:boot[0]='other'
        for initial,flip,should_reset in (('b1',False,True),('other',False,False),('b1',True,False)):
            boot=[initial];change=[flip];events.clear()
            with mock.patch('pathlib.Path',P),mock.patch('os.sync',synced),mock.patch('subprocess.run'),mock.patch('builtins.open',opened),mock.patch('termios.tcdrain'):
                with self.assertRaises(RuntimeError):exec(script,{})
            self.assertEqual('/proc/sysrq-trigger' in events,should_reset)
            if should_reset:self.assertLess(events.index('sync'),events.index('/proc/sysrq-trigger'))
    def test_reset_intent_is_saved_before_a_failed_request_and_never_retried(self):
        for reset in ('orderly','sysrq-b'):
            with tempfile.TemporaryDirectory() as t:
                run=r.Run(pathlib.Path(t),'unused',reset,True)
                def request(*args):
                    self.assertIn('REBOOT REQUESTED '+reset,(run.out/'events.log').read_text())
                    raise RuntimeError('uncertain')
                with mock.patch.object(run,'health',return_value=({'boot_id':'b1'},{'passed':True})),mock.patch.object(run,'ssh',side_effect=request) as ssh:
                    with self.assertRaisesRegex(RuntimeError,'uncertain'):run.reboot_from_cold(mock.Mock(data=b''))
                    self.assertEqual(ssh.call_count,1)
    def test_unhealthy_baseline_never_requests_a_reset(self):
        with tempfile.TemporaryDirectory() as t:
            run=r.Run(pathlib.Path(t),'unused','sysrq-b',True)
            with mock.patch.object(run,'health',return_value=({}, {'passed':False,'reasons':['bad video']})),mock.patch.object(run,'ssh') as ssh:
                with self.assertRaises(RuntimeError):run.reboot_from_cold(mock.Mock(data=b''))
                ssh.assert_not_called()

class GP7Abrupt(unittest.TestCase):
    """Whole remote trigger on a fake sysfs/proc tree; no hardware access."""
    def simulate(self,change=None,short_write=False,bad_readback=False,post_arm_boot_change=False):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);real_path=pathlib.Path
            def path(s):return root/str(s).lstrip('/')
            def put(s,data):
                p=path(s);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            dt='/sys/firmware/devicetree/base';rtc=dt+'/soc/rtc@7090000';cell=rtc+'/reboot-mode-magic@1c';mode=dt+'/reboot-mode'
            values={rtc+'/compatible':b'allwinner,sun50i-h713-rtc\0',rtc+'/reg':bytes.fromhex('0709000000000400'),
                    cell+'/reg':bytes.fromhex('0000001c00000004'),cell+'/phandle':bytes.fromhex('00000043'),
                    mode+'/compatible':b'nvmem-reboot-mode\0',mode+'/mode-bootloader':bytes.fromhex('b007c0de'),mode+'/nvmem-cells':bytes.fromhex('00000043'),
                    '/proc/sys/kernel/random/boot_id':b'B1', '/sys/module/h713_hdmi_audio/parameters/dsp_failed':b'N',
                    '/sys/devices/platform/h713-hdmi-ring/signal':b'locked 1280x720'}
            for card,stream in (('H713HDMI','pcm0c'),('Codec','pcm0p')):values['/proc/asound/'+card+'/'+stream+'/sub0/status']=b'state: RUNNING\n'
            for key,data in values.items():put(key,data)
            dev=path('/sys/devices/platform/7090000.rtc');provider=dev/'nvmem0';provider.mkdir(parents=True)
            driver=path('/sys/bus/platform/drivers/sun6i-rtc');driver.mkdir(parents=True)
            (dev/'driver').symlink_to(driver);(provider/'of_node').symlink_to(path(rtc))
            nvmem=provider/'nvmem';before=bytes(range(24))+bytes.fromhex('494d4448')+bytes(4);nvmem.write_bytes(before)
            bus=path('/sys/bus/nvmem/devices');bus.mkdir(parents=True);(bus/'nvmem0').symlink_to(provider)
            if change:change(path,nvmem,bus)
            writes=[];events=[];commands=[];opened=[];errors=[]
            real_pwrite=r.os.pwrite;real_pread=r.os.pread;real_open=r.os.open;real_close=r.os.close
            def wr(fd,data,offset):
                writes.append((bytes(data),offset));events.append('arm')
                # A short count remains uncertain even if the word changed.
                if short_write:real_pwrite(fd,data,offset);return 0
                result=real_pwrite(fd,data,offset)
                if post_arm_boot_change:path('/proc/sys/kernel/random/boot_id').write_text('OTHER')
                return result
            def rd(fd,n,offset):
                events.append('readback' if writes else 'before')
                return bytes(n) if bad_readback and writes else real_pread(fd,n,offset)
            def op(name,flags):
                self.assertEqual(real_path(name).resolve(),nvmem.resolve());opened.append(name);return real_open(name,flags)
            def close(fd):events.append('close');return real_close(fd)
            def command(cmd,**kw):commands.append(cmd);return mock.Mock(returncode=0)
            class Stream(io.StringIO):
                def __init__(self,name):super().__init__();self.name=name
                def write(self,text):events.append((self.name,text));return super().write(text)
                def fileno(self):return 123
            def out(name,mode):return Stream(name)
            with mock.patch('pathlib.Path',side_effect=path),mock.patch('os.sync',side_effect=lambda:events.append('sync')),mock.patch('os.open',side_effect=op),mock.patch('os.close',side_effect=close),mock.patch('os.pread',side_effect=rd),mock.patch('os.pwrite',side_effect=wr),mock.patch('subprocess.run',side_effect=command),mock.patch('builtins.open',side_effect=out),mock.patch('termios.tcdrain',side_effect=lambda fd:events.append('uart-drained')),contextlib.redirect_stdout(io.StringIO()):
                try:exec(r.abrupt_script('B1','gp7'),{})
                except Exception as e:errors.append(str(e))
            return {'writes':writes,'events':events,'commands':commands,'opened':opened,'errors':errors,'before':before,'after':nvmem.read_bytes()}
    def test_single_aligned_gp7_write_preserves_gp6_and_resets_without_teardown(self):
        d=self.simulate();self.assertEqual(d['errors'],['SysRq returned unexpectedly'])
        self.assertEqual(d['writes'],[(bytes.fromhex('dec007b0'),0x1c)])
        self.assertEqual(d['after'][:28],d['before'][:28]);self.assertEqual(d['after'][28:],bytes.fromhex('dec007b0'))
        e=d['events'];self.assertLess(e.index('sync'),e.index('arm'));self.assertLess(e.index('readback'),e.index('close'))
        self.assertIn(('/proc/sysrq-trigger','b'),e)
        marker=next(i for i,x in enumerate(e) if isinstance(x,tuple) and x[0]=='/dev/ttyS0')
        self.assertIn(r.ABRUPT_GP7_MARKER,e[marker][1]);self.assertLess(e.index('close'),marker);self.assertLess(marker,e.index(('/proc/sysrq-trigger','b')))
        self.assertTrue(d['commands']);self.assertTrue(all(x[:2]==['systemctl','is-active'] for x in d['commands']))
    def test_uart_ack_is_drained_before_abrupt_reset(self):
        e=self.simulate()['events']
        marker=next(i for i,x in enumerate(e) if isinstance(x,tuple) and x[0]=='/dev/ttyS0')
        self.assertLess(marker,e.index('uart-drained'));self.assertLess(e.index('uart-drained'),e.index(('/proc/sysrq-trigger','b')))
    def test_bad_provider_cell_or_magic_refused_before_any_write(self):
        dt='/sys/firmware/devicetree/base';rtc=dt+'/soc/rtc@7090000';mode=dt+'/reboot-mode'
        cases=[lambda p,n,b,key=key:p(key).write_bytes(b'wrong') for key in
               (rtc+'/compatible',rtc+'/reg',rtc+'/reboot-mode-magic@1c/reg',rtc+'/reboot-mode-magic@1c/phandle',mode+'/compatible',mode+'/mode-bootloader',mode+'/nvmem-cells')]
        cases += [lambda p,n,b:(b/'nvmem0').unlink(),lambda p,n,b:(b/'duplicate').symlink_to((b/'nvmem0').resolve()),
                  lambda p,n,b:n.write_bytes(bytes(28)),lambda p,n,b:(n.parent.parent/'driver').unlink()]
        for change in cases:
            d=self.simulate(change=change);self.assertTrue(d['errors']);self.assertEqual(d['writes'],[]);self.assertNotIn(('/proc/sysrq-trigger','b'),d['events'])
    def test_wrong_initial_gp6_gp7_or_unhealthy_session_cannot_arm(self):
        cases=[lambda p,n,b:n.write_bytes(n.read_bytes()[:24]+bytes(8)),lambda p,n,b:n.write_bytes(n.read_bytes()[:28]+bytes.fromhex('dec007b0')),
               lambda p,n,b:p('/proc/sys/kernel/random/boot_id').write_text('OTHER'),
               lambda p,n,b:p('/sys/devices/platform/h713-hdmi-ring/signal').write_text('holding 1280x720')]
        for change in cases:
            d=self.simulate(change=change);self.assertTrue(d['errors']);self.assertFalse(d['writes']);self.assertNotIn(('/proc/sysrq-trigger','b'),d['events'])
    def test_failed_write_readback_or_post_arm_guard_never_retries_or_resets(self):
        for kwargs in ({'short_write':True},{'bad_readback':True},{'post_arm_boot_change':True}):
            d=self.simulate(**kwargs);self.assertEqual(len(d['writes']),1);self.assertTrue(d['errors'])
            self.assertNotIn(('/proc/sysrq-trigger','b'),d['events']);self.assertIn('close',d['events'])
    def test_gp7_abrupt_stream_requires_readback_ack_and_no_keypress(self):
        trace=REBOOT.replace(b'reboot: Restarting system',r.ABRUPT_GP7_MARKER.encode()+b' boot=B1\r\nsysrq: Resetting').replace(b'gp7=00000000',b'gp7=b007c0de')
        s=r.reboot_stage('sysrq-b','gp7');self.assertEqual(feed(s,trace,size=1),['done']);self.assertFalse(s.sent);r.check_warm_preboot(s.preboot(),'gp7')
        self.assertNotIn('done',feed(r.reboot_stage('sysrq-b','gp7'),trace.replace(r.ABRUPT_GP7_MARKER.encode(),r.ABRUPT_MARKER.encode())))
    def test_sysrq_gp7_runner_selects_armed_script_once(self):
        with tempfile.TemporaryDirectory() as t:
            run=r.Run(pathlib.Path(t),'unused',reset='sysrq-b',require_video=True,boot_stop='gp7')
            p={'gp6':'48444d49','gp7':'b007c0de','mips_clk':'00000000','mips_reset':'00000000','mips_status':'00000000'}
            stage=mock.Mock();stage.preboot.return_value=p
            with mock.patch.object(run,'health',return_value=({'boot_id':'B1'},{'passed':True})),mock.patch.object(run,'ssh') as ssh,mock.patch.object(run,'watch',return_value=(stage,0)) as watch:
                run.reboot_from_cold(mock.Mock(data=b''))
                self.assertEqual(ssh.call_count,1);self.assertFalse(watch.call_args.args[1].interrupt)
                command=ssh.call_args.args[1];self.assertTrue(command.startswith('setsid nohup python3 -c '));self.assertTrue(command.endswith('< /dev/null &'))
            script=(run.out/'abrupt-reset-trigger.py.txt').read_text();self.assertEqual(script,r.abrupt_script('B1','gp7'));self.assertIn('os.pwrite',script)

if __name__=='__main__':unittest.main()
