#!/usr/bin/env python3
import copy,hashlib,importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest,contextlib,io
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def load(name,file):
    s=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load('a',HERE/'analyze-dsp-teardown-b.py');b=load('b',HERE/'prepare-dsp-teardown-b.py');h=load('helper',HERE/'dsp-teardown-b.py')
MODES=('sham','sham-driver-clock','preserved','missing-marker','census-reset-flag','census-words','census-bus-saved','lose-clock','lose-reset','lose-prefix','stuck-off','stuck-bus','unrouted','late-timeout','shared-reset','child-hold','driver-clock')
class NativeBuild(unittest.TestCase):
    """Builds and runs the actual kernel includes against fake MMIO."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=pathlib.Path(cls.temp.name)
        (cls.path/'linux').mkdir();(cls.path/'linux/mutex.h').write_text('')
        for p in (HERE/'dsp-teardown-b').iterdir():shutil.copyfile(p,cls.path/p.name)
        shutil.copyfile(ROOT/'modules/hdmi-dsp-probe/h713-dsp-lock.h',cls.path/'h713-dsp-lock.h')
        subprocess.run(['cc','-std=gnu11','-Wall','-Werror','-Wno-unused-function','-Wno-unused-variable','-I'+str(cls.path),str(cls.path/'native-test.c'),'-o',str(cls.path/'test')],check=True)
        cls.out={}
        for mode in MODES:
            r=subprocess.run([str(cls.path/'test'),mode],capture_output=True,text=True)
            cls.out[mode]=(r.returncode,r.stdout,r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def state(self,mode):return json.loads(self.out[mode][1])
class Native(NativeBuild):
    def test_every_mode_passes_its_assertions(self):
        for mode in MODES:self.assertEqual(self.out[mode][0],0,mode+': '+self.out[mode][2])
    def test_sham_never_changes_clocks_or_reset(self):
        s=self.state('sham');t=s['tv'];c=s['ctx']
        self.assertEqual((s['step'],s['steps'],s['requests']),(39,39,8))
        self.assertEqual((t['offs'],t['ons'],t['resets'],t['writes']),(0,0,0,32));self.assertIsNone(t['off_clocks']);self.assertIsNone(t['off_reset'])
        self.assertEqual((c['gate_closes'],c['gate_opens'],c['ihb'][2],c['at_writes']),(2,2,4,5))
    def test_arm2_round_trips_restore_saved_then_stock(self):
        s=self.state('preserved');t=s['tv']
        self.assertEqual((t['offs'],t['ons'],t['resets'],t['writes'],t['reset_status_after']),(2,2,1,65,1))
        self.assertEqual(t['off_clocks'][:15],t['saved']);self.assertEqual(t['off_clocks'][15],0x10000)
        self.assertEqual(t['off_reset'][:15],t['saved']);self.assertEqual(t['off_reset'][15],0)
        self.assertEqual(t['parents'][1],[0,1,0,0]);self.assertEqual(t['state'],0)
    def test_child_hold_is_reported_not_hidden(self):
        self.assertEqual(self.state('child-hold')['tv']['parents'][1][3],1)
    def test_changed_pair_stops_before_next_operation(self):
        for mode,step in (('lose-prefix',15),('lose-clock',27),('lose-reset',39)):
            s=self.state(mode);self.assertEqual(s['step'],step,mode);self.assertTrue(s['terminal']);self.assertEqual(s['ctx']['gate'],1)
        self.assertEqual(self.state('lose-clock')['tv']['resets'],0)
    def test_timeout_skips_and_releases(self):
        s=self.state('late-timeout');self.assertEqual(s['step'],27);self.assertTrue(s['timeout'] and s['terminal'] and not s['claimed'])
    def test_plan_matches_prepare(self):
        self.assertEqual(b.native_plan(),self.state('sham')['plan'])

def proof(arm):return {'verified':True,'boot_id':'boot'+str(arm),'arm':arm,'manifest_sha256':'same','module_sha256':'module','cold_script_sha256':'script'}
def record(state,arm=None):
    arm=arm or state['arm']
    return {'boot_id':'boot'+str(arm),'preflight_valid':True,'proof':proof(arm),'baseline':{'boot_id':'boot'+str(arm),'tv_domains_both_on':True,'reads':{'mips_status':'00000001'},'dsp_journal':['DSP versions 0000/0000','pinned 724-pair DSP patch verified versions 1/1']},'state':state}
class Analysis(NativeBuild):
    def classify(self,mode):return a.analyze(record(self.state(mode)))['classification']
    def test_actual_states_classify_per_boundary(self):
        want={'sham':'sham_positive_control_passed','sham-driver-clock':'sham_positive_control_passed','preserved':'tested_phase_b_boundaries_preserved_patch','lose-prefix':'version_change_after_phase_a_prefix','lose-clock':'version_change_after_clock_round_trip','lose-reset':'version_change_after_clock_and_demod_reset_round_trip','late-timeout':'access_timeout','child-hold':'tested_phase_b_boundaries_preserved_patch','driver-clock':'tested_phase_b_boundaries_preserved_patch'}
        for mode,c in want.items():self.assertEqual(self.classify(mode),c,mode)
    def test_effective_gates_reported(self):
        r=a.analyze(record(self.state('preserved')));self.assertIn('tvfe-1296',r['gates_turned_off']);self.assertIn('audio-cpu',r['gates_turned_off'])
    def test_null_clock_edge_is_not_attributed(self):
        s=self.state('preserved');s['tv']['saved']=list(a.TV_STOCK);s['tv']['off_clocks'][:15]=list(a.TV_STOCK);s['tv']['off_reset'][:15]=list(a.TV_STOCK)
        self.assertEqual(a.analyze(record(s))['classification'],'inconclusive_null_clock_edge')
    def test_sham_with_any_clock_or_reset_change_is_not_qualified(self):
        for key,value in (('offs',1),('resets',1),('writes',33)):
            s=self.state('sham');s['tv'][key]=value;self.assertEqual(a.analyze(record(s))['classification'],'sham_changed_or_incomplete',key)
        s=self.state('sham');s['tv']['parents'][1][2]=1;self.assertEqual(a.analyze(record(s))['classification'],'sham_changed_or_incomplete')
    def test_wrong_off_readback_counts_or_gate_inconclusive(self):
        s=self.state('preserved');s['tv']['off_reset'][15]=0x10000;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
        s=self.state('preserved');s['tv']['reset_status_after']=0;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
        s=self.state('preserved');s['ctx']['gate']=0;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
        s=self.state('preserved');s['ctx']['tvtop_last']=0;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
        s=self.state('preserved');s['tv']['writes']=64;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
    def test_echo_never_a_zero(self):
        s=self.state('lose-clock');s['pairs'][2]['raw']=[0x80ff0000,0x80ff0000];self.assertEqual(a.analyze(record(s))['classification'],'ambiguous_command_echo')
    def matched(self,arm_state):
        sham=record(self.state('sham'));arm=record(arm_state,2);arm['proof']['sham_record_sha256']=a.canonical(sham);return sham,arm
    def test_matched_pair_requires_exact_qualified_sham(self):
        sham,arm=self.matched(self.state('preserved'))
        self.assertEqual(a.compare(sham,arm)['classification'],'matched_tested_phase_b_boundaries_preserved_patch')
        sham,arm=self.matched(self.state('lose-clock'))
        self.assertEqual(a.compare(sham,arm)['classification'],'matched_version_change_after_clock_round_trip')
        for field in ('manifest_sha256','module_sha256','cold_script_sha256','sham_record_sha256'):
            s,c=self.matched(self.state('preserved'));c['proof'][field]='bad';self.assertEqual(a.compare(s,c)['classification'],'unmatched_or_unqualified',field)
    def test_tv_context_must_match_sham(self):
        # Self-consistent arm (classifies on its own) whose saved MPG1 word differs from the sham's.
        st=self.state('preserved');t=st['tv'];t['saved'][14]^=1;t['off_clocks'][14]^=1;t['off_reset'][14]^=1
        self.assertEqual(a.analyze(record(st,2))['classification'],'tested_phase_b_boundaries_preserved_patch')
        sham,arm=self.matched(st);self.assertEqual(a.compare(sham,arm)['classification'],'unmatched_or_unqualified')
        st=self.state('preserved');st['ctx']['audio_clocks'][2][1]=1;sham,arm=self.matched(st)
        self.assertEqual(a.compare(sham,arm)['classification'],'unmatched_or_unqualified')
    def test_phase_a_records_cannot_qualify(self):
        old=json.loads((ROOT/'docs/hdmi-evidence/2026-10-22-dsp-teardown-a-sham-live/board-export/snapshot-37.json').read_text())
        self.assertEqual(a.analyze(old)['classification'],'inconclusive')
        arm=record(self.state('preserved'),2);arm['proof']['sham_record_sha256']=a.canonical(old)
        self.assertEqual(a.compare(old,arm)['classification'],'unmatched_or_unqualified')

class Helper(NativeBuild):
    """Step admission on the board side, with sysfs/run directories faked."""
    def fixture(self,t,state,arm=2,ledger=None,sham=None):
        p=pathlib.Path(t);sys=p/'sys';sys.mkdir();run=p/'run';run.mkdir()
        (sys/'owner_arm').write_text(str(arm));(sys/'dsp_failed').write_text('N');(sys/'owner_state').write_text(json.dumps(state))
        (run/'ledger.json').write_text(json.dumps(ledger or {'boot':'boot2','uncertain':False,'snapshot':state['step'],'state_hash':h.state_hash(state)}))
        (p/'baseline.json').write_text('{}');shutil.copyfile(HERE/'analyze-dsp-teardown-b.py',p/'analyze-dsp-teardown-b.py')
        if sham:(p/'sham-record.json').write_text(json.dumps(sham))
        pr=proof(arm);pr['boot_id']='boot2'
        return p,sys,run,mock.patch.multiple(h,SYS=sys,RUN=run,preflight=mock.MagicMock(return_value=({'plan':state['plan']},pr)))
    def at_step(self,mode,n):
        s=self.state(mode);s.update(step=n,terminal=0);return s
    def test_unacknowledged_or_wrong_stage_refused(self):
        s=self.at_step('preserved',18)
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s)
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',19,'clocks-audio-off')
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',19,None)
            self.assertFalse((sys/'owner_step').exists())
    def test_uncertain_ledger_refuses_step(self):
        s=self.at_step('preserved',18)
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s,ledger={'boot':'boot2','uncertain':True})
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',19,'clocks-tvfe-off')
            self.assertFalse((sys/'owner_step').exists())
    def test_census_mismatch_with_sham_refused_before_requests(self):
        for path in (('ctx','census',1),('tv','census',3),('tv','saved',1)):
            s=self.at_step('preserved',1);sham=record(self.state('sham'));sham['state'][path[0]][path[1]][path[2]]^=1
            with tempfile.TemporaryDirectory() as t:
                p,sys,run,patch=self.fixture(t,s,sham=sham)
                with patch,self.assertRaises(AssertionError):h.observe(p,'step',2,'census')
                self.assertFalse((sys/'owner_step').exists(),path)
    def test_clock_change_refused_unless_prefix_patched(self):
        s=self.at_step('preserved',15);s['pairs'][1]['raw']=[0,0]
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s)
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',16,'pair1-boundary')
            self.assertFalse((sys/'owner_step').exists())
    def snapshot(self,state,ledger_uncertain=False):
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,state,arm=1,ledger={'boot':'boot2','uncertain':ledger_uncertain})
            (p/'baseline.json').write_text(json.dumps(record(state)['baseline']));out=io.StringIO()
            reads=[]
            real=pathlib.Path.read_text
            def read_text(path,*a,**k):
                if str(path).startswith('/sys/kernel/debug'):reads.append(str(path));return 'debug'
                return real(path,*a,**k)
            with patch,mock.patch.object(h.subprocess,'check_output',return_value='journal'),mock.patch.object(pathlib.Path,'read_text',read_text),contextlib.redirect_stdout(out):h.observe(p,'snapshot',None,None)
            return json.loads(out.getvalue()),reads
    def test_uncertain_snapshot_cannot_be_reported_as_success(self):
        r,reads=self.snapshot(self.state('sham'),True)
        self.assertFalse(r['preflight_valid']);self.assertEqual(r['analysis']['classification'],'inconclusive');self.assertNotIn('debug',r);self.assertEqual(reads,[])
    def test_debug_summaries_never_read_with_gate_closed_or_clocks_off(self):
        s=self.state('sham');r,reads=self.snapshot(s);self.assertIn('debug',r);self.assertEqual(len(reads),2)
        for key,section,value in (('gate','ctx',0),('state','tv',1),('state','tv',2)):
            s=self.state('sham');s[section][key]=value;r,reads=self.snapshot(s)
            self.assertNotIn('debug',r);self.assertEqual(reads,[],(section,key,value))
    def test_qualified_sham_rejects_phase_a_same_boot_and_hash(self):
        sham=record(self.state('sham'));pr=proof(2);pr['boot_id']='boot2';pr['sham_record_sha256']=a.canonical(sham)
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t);shutil.copyfile(HERE/'analyze-dsp-teardown-b.py',p/'analyze-dsp-teardown-b.py')
            (p/'sham-record.json').write_text(json.dumps(sham));self.assertEqual(h.qualified_sham(p,pr)['boot_id'],'boot1')
            with self.assertRaises(AssertionError):h.qualified_sham(p,dict(pr,sham_record_sha256='0'*64))
            with self.assertRaises(AssertionError):h.qualified_sham(p,dict(pr,boot_id='boot1'))
            old=json.loads((ROOT/'docs/hdmi-evidence/2026-10-22-dsp-teardown-a-sham-live/board-export/snapshot-37.json').read_text())
            (p/'sham-record.json').write_text(json.dumps(old))
            with self.assertRaises(AssertionError):h.qualified_sham(p,dict(pr,sham_record_sha256=a.canonical(old)))
    def test_stage_table_covers_every_pair_and_intervention(self):
        want=[1,2,3,6,7,8,9,10,11,12,15]+list(range(16,23))+[23,24,27]+list(range(28,35))+[35,36,39]
        self.assertEqual(sorted(h.STAGES),want);self.assertEqual(h.STAGES[19],'clocks-held');self.assertEqual(h.STAGES[30],'reset-tvfe-off')

class HostRunner(unittest.TestCase):
    def test_deadline_is_recorded_uncertain_and_never_retried(self):
        r=load('host',HERE/'dsp-teardown-b-host.py');calls=[]
        def run(*args,**kw):calls.append(args);raise subprocess.TimeoutExpired('ssh',20,output=b'partial')
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t)/'live-sham-01';p.mkdir();(p/'capture-plan.json').write_text('{"arm":1}')
            with mock.patch.object(r.subprocess,'run',run),self.assertRaises(SystemExit):r.observe(p,'step',3,None)
            self.assertEqual(len(calls),1);self.assertIn('HOST DEADLINE',(p/'step-03-uncertain.log').read_text())
            self.assertIn('/dsp-teardown-b.py --bundle /root/hdmi-dsp-teardown-b-2026-10-23/live-sham-01',calls[0][0][-1])
    def test_health_requires_phase_b_boot(self):
        r=load('host',HERE/'dsp-teardown-b-host.py')
        self.assertIn("'h713_teardown_b=1' in cmd and 'h713_teardown_a=1' not in cmd",r.HEALTH);self.assertIn('54445242',r.HEALTH)
        self.assertIn('835e0bf5-fc43-4269-9740-58d153feef99',r.PREVIOUS_BOOTS)
class ColdProof(unittest.TestCase):
    def test_fresh_cold_evidence_and_arm_gating(self):
        r=load('runner',ROOT/'tools/serial/run-dsp-teardown-b-cold.py')
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t);(p/'cold-teardown-b.scr').write_bytes(b'script')
            digest=hashlib.sha256(b'script').hexdigest()
            (p/'manifest.json').write_text(json.dumps({'bundle':{'h713-hdmi-audio.ko':'module'},'cold_script_sha256':digest}))
            cold=p/'cold.log';cold.write_bytes(b'U-Boot SPL test\r\nH713 RESET v1 stage=proper_preboot gp6=00000000 gp7=00000000 mips_status=00000000\r\n=> ')
            self.assertEqual(r.intent(p,cold,1)['schema'],'h713-teardown-b-arm-v1')
            with self.assertRaises(AssertionError):r.intent(p,cold,2)
            old=ROOT/'docs/hdmi-evidence/2026-10-22-dsp-teardown-a-sham-live/board-export/snapshot-37.json'
            with self.assertRaises(AssertionError):r.intent(p,cold,2,old)
            cold.write_bytes(cold.read_bytes().replace(b'gp6=00000000',b'gp6=48444d49'))
            with self.assertRaises(AssertionError):r.intent(p,cold,1)
class ColdScript(unittest.TestCase):
    def test_only_proven_cold_path_and_runtime_masks(self):
        text=b.cold_script((b.INSTALLED/'h713-hdmi.cmd').read_text())
        self.assertEqual(text.count('bootm '),1);self.assertEqual(text.count('h713_disp auto 0x34 logo'),1)
        self.assertEqual(text.count('h713_disp mips-comm-trace 0x34'),1)
        self.assertNotIn('gpio set PB5',text);self.assertNotIn('saveenv',text);self.assertNotIn('mw.l 0x0709011c',text)
        for unit in ('capture','signal','speaker'):self.assertIn('systemd.mask=h713-hdmi-'+unit+'.service',text)
        self.assertIn('if itest.l *0x07090118 == 0; then',text);self.assertIn('h713,dsp-teardown-b-v1 <0x54445242>',text)
        self.assertIn(' h713_teardown_b=1 && bootm',text)
        for old in ('dsp-owner-boundary','h713_owner_boundary','dsp-teardown-a','h713_teardown_a'):self.assertNotIn(old,text)
    def test_changed_anchors_rejected(self):
        with self.assertRaises(ValueError):b.replace_once('xx','x','y')
    def test_source_patch_applies_once_to_pinned_production(self):
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t)
            for n in ('h713-hdmi-pcm.c','h713-hdmi-dsp.c','h713-hdmi-tvfe.c'):shutil.copyfile(ROOT/'modules/hdmi-audio'/n,p/n)
            b.patch_sources(p);pcm=(p/'h713-hdmi-pcm.c').read_text();dsp=(p/'h713-hdmi-dsp.c').read_text();tvfe=(p/'h713-hdmi-tvfe.c').read_text()
            self.assertEqual(pcm.count('#include "teardown-pcm.inc"'),1);self.assertEqual(dsp.count('#include "teardown-observer.inc"'),1);self.assertEqual(tvfe.count('#include "teardown-tvfe.inc"'),1)
            self.assertNotIn('ret = register_pcm();',pcm);self.assertEqual(pcm.count('ret = h713_owner_pin();'),1)
            self.assertLess(pcm.index('ret = h713_owner_init_check();'),pcm.index('if (!armed || !live_source3'))
            for sym in ('static struct snd_card *capture_card;','static bool pcm_running;','static u32 spdi1_saved_ctl1;','static void release_resources(void)','static struct audio_clock audio_clocks[]','static u32 audio_ihb_saved;'):
                self.assertLess(pcm.index(sym),pcm.index('#include "teardown-pcm.inc"'),sym)
            for sym in ('static struct tvfe_word functional_words[]','static struct parent_hold parents[]','static u32 tvfe_saved;'):
                self.assertLess(tvfe.index(sym),tvfe.index('#include "teardown-tvfe.inc"'),sym)
            self.assertLess(tvfe.index('#include "teardown-tvfe.inc"'),tvfe.index('void h713_hdmi_tvfe_release(void)'))
            with self.assertRaises(ValueError):b.patch_sources(p)
if __name__=='__main__':unittest.main()
