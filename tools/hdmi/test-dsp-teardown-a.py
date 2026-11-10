#!/usr/bin/env python3
import copy,hashlib,importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest,contextlib,io
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def load(name,file):
    s=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load('a',HERE/'analyze-dsp-teardown-a.py');b=load('b',HERE/'prepare-dsp-teardown-a.py');h=load('helper',HERE/'dsp-teardown-a.py')
MODES=('sham','preserved','missing-marker','missing-arm','health-bad','census-stage4','census-pcm','census-active','census-dma','lock-bad','busy-timeout','done-timeout','bad-positive','echo','lose-graph','lose-spdi','lose-bridge','lose-cfg','lose-ctl','context-drift','graph-failure','late-timeout','drift-before-spdi','spdi-bad-readback','bridge-bad-readback')
class NativeBuild(unittest.TestCase):
    """Builds and runs the actual kernel includes against fake MMIO."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=pathlib.Path(cls.temp.name)
        (cls.path/'linux').mkdir();(cls.path/'linux/mutex.h').write_text('')
        for p in (HERE/'dsp-teardown-a').iterdir():shutil.copyfile(p,cls.path/p.name)
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
    def test_sham_writes_nothing_and_completes_six_pairs(self):
        s=self.state('sham');c=s['ctx']
        self.assertEqual((s['step'],s['steps'],s['requests'],s['graph_remaining']),(37,37,12,0))
        self.assertEqual((c['spdi_writes'],c['bridge_writes'],c['at_writes'],c['spdi_applied'],c['bridge_applied']),(0,0,0,0,0))
        self.assertEqual(c['after_spdi'],c['census']);self.assertEqual(c['after_bridge'],c['census'])
    def test_teardown_restores_exact_saved_values(self):
        s=self.state('preserved');c=s['ctx']
        self.assertEqual((c['spdi_writes'],c['bridge_writes'],c['at_writes']),(3,9,3))
        self.assertEqual(c['after_spdi'][:3],c['saved'][:3]);self.assertEqual(c['after_spdi'][3:],c['census'][3:])
        self.assertEqual(c['after_bridge'],c['saved']);self.assertEqual(c['census_stage'],3)
        self.assertEqual((s['ctl'],s['cfg']),(0x700,0))
    def test_changed_pair_stops_before_next_operation(self):
        for mode,step in (('lose-graph',12),('lose-spdi',18),('lose-bridge',24),('lose-cfg',30),('lose-ctl',37),('bad-positive',6),('echo',6)):
            s=self.state(mode);self.assertEqual(s['step'],step,mode);self.assertTrue(s['terminal']);self.assertFalse(s['claimed'])
    def test_timeout_skips_and_releases(self):
        for mode,step in (('busy-timeout',6),('done-timeout',6),('late-timeout',12)):
            s=self.state(mode);self.assertEqual(s['step'],step);self.assertTrue(s['timeout'] and s['terminal'] and not s['claimed'])
    def test_plan_matches_prepare(self):
        self.assertEqual(b.native_plan(),self.state('sham')['plan'])

def proof(arm):return {'verified':True,'boot_id':'boot'+str(arm),'arm':arm,'manifest_sha256':'same','module_sha256':'module','cold_script_sha256':'script'}
def record(state,arm=None):
    arm=arm or state['arm']
    return {'boot_id':'boot'+str(arm),'preflight_valid':True,'proof':proof(arm),'baseline':{'boot_id':'boot'+str(arm),'tv_domains_both_on':True,'reads':{'mips_status':'00000001'},'dsp_journal':['DSP versions 0000/0000','pinned 724-pair DSP patch verified versions 1/1']},'state':state}
class Analysis(NativeBuild):
    def classify(self,mode):return a.analyze(record(self.state(mode)))['classification']
    def test_actual_states_classify_per_boundary(self):
        want={'sham':'sham_positive_control_passed','preserved':'tested_teardown_boundaries_preserved_patch','lose-graph':'version_change_after_common_graph_restore','lose-spdi':'version_change_after_spdi_restore','lose-bridge':'version_change_after_bridge_restore','lose-cfg':'version_change_after_audiotop_config_restore','lose-ctl':'version_change_after_audiotop_control_cycle','echo':'ambiguous_command_echo','busy-timeout':'access_timeout','done-timeout':'access_timeout','late-timeout':'access_timeout','bad-positive':'patched_positive_control_not_observed'}
        for mode,c in want.items():self.assertEqual(self.classify(mode),c,mode)
    def test_sham_with_any_write_is_not_qualified(self):
        for key,value in (('spdi_writes',3),('bridge_writes',9),('at_writes',1),('spdi_applied',1)):
            s=self.state('sham');s['ctx'][key]=value
            self.assertEqual(a.analyze(record(s))['classification'],'sham_changed_or_incomplete',key)
    def test_teardown_with_wrong_readback_or_counts_is_inconclusive(self):
        s=self.state('preserved');s['ctx']['after_bridge'][11]^=1;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
        s=self.state('preserved');s['ctx']['bridge_writes']=8;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
        s=self.state('preserved');s['ctx']['census_stage']=4;self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
    def test_unrecorded_later_pair_or_old_schema_inconclusive(self):
        s=self.state('lose-spdi');s['pairs'][3]['raw']=[1,1];s['pairs'][3]['outcome']=[1,1];s['pairs'][3]['phase']=[5,5];s['pairs'][3]['sent']=[1,1]
        self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
        s=self.state('sham');s['schema']='h713-owner-boundary-v1';self.assertEqual(a.analyze(record(s))['classification'],'inconclusive')
    def matched(self,arm_state):
        sham=record(self.state('sham'));arm=record(arm_state,2);arm['proof']['sham_record_sha256']=a.canonical(sham);return sham,arm
    def test_matched_pair_requires_exact_qualified_sham(self):
        sham,arm=self.matched(self.state('preserved'))
        self.assertEqual(a.compare(sham,arm)['classification'],'matched_tested_teardown_boundaries_preserved_patch')
        sham,arm=self.matched(self.state('lose-bridge'))
        self.assertEqual(a.compare(sham,arm)['classification'],'matched_version_change_after_bridge_restore')
        for field in ('manifest_sha256','module_sha256','cold_script_sha256','sham_record_sha256'):
            s,c=self.matched(self.state('preserved'));c['proof'][field]='bad';self.assertEqual(a.compare(s,c)['classification'],'unmatched_or_unqualified',field)
    def test_dma_address_may_differ_but_census_may_not(self):
        s=self.state('preserved');d=0x65000000;c=s['ctx'];c['dma']=d
        for w in (c['census'],c['after_spdi']):w[5]=d>>4&0xffffff;w[6]=(d+0xffff)>>4&0xffffff;w[11]=w[11]&~0xf0|(d>>28)<<4
        sham,arm=self.matched(s);self.assertEqual(a.compare(sham,arm)['classification'],'matched_tested_teardown_boundaries_preserved_patch')
        s=self.state('preserved');s['ctx']['census'][0]=1;sham,arm=self.matched(s);self.assertEqual(a.compare(sham,arm)['classification'],'unmatched_or_unqualified')
        s=self.state('preserved');s['ctx']['saved'][4]^=1;sham,arm=self.matched(s);self.assertEqual(a.compare(sham,arm)['classification'],'unmatched_or_unqualified')
        s=self.state('preserved');s['ctx']['dma']+=0x10;sham,arm=self.matched(s);self.assertEqual(a.compare(sham,arm)['classification'],'unmatched_or_unqualified')
    def test_old_owner_sham_cannot_qualify(self):
        old=json.loads((ROOT/'docs/hdmi-evidence/2026-10-22-dsp-owner-sham-live/board-export/snapshot-25.json').read_text())
        arm=record(self.state('preserved'),2);arm['proof']['sham_record_sha256']=a.canonical(old)
        self.assertEqual(a.compare(old,arm)['classification'],'unmatched_or_unqualified')

class Helper(NativeBuild):
    """Step admission on the board side, with sysfs/run directories faked."""
    def fixture(self,t,state,arm=2,ledger=None,sham=None):
        p=pathlib.Path(t);sys=p/'sys';sys.mkdir();run=p/'run';run.mkdir()
        (sys/'owner_arm').write_text(str(arm));(sys/'dsp_failed').write_text('N');(sys/'owner_state').write_text(json.dumps(state))
        (run/'ledger.json').write_text(json.dumps(ledger or {'boot':'boot2','uncertain':False,'snapshot':state['step'],'state_hash':h.state_hash(state)}))
        (p/'baseline.json').write_text('{}');shutil.copyfile(HERE/'analyze-dsp-teardown-a.py',p/'analyze-dsp-teardown-a.py')
        if sham:(p/'sham-record.json').write_text(json.dumps(sham))
        pr=proof(arm);pr['boot_id']='boot2'
        return p,sys,run,mock.patch.multiple(h,SYS=sys,RUN=run,preflight=mock.MagicMock(return_value=({'plan':state['plan']},pr)))
    def at_step(self,mode,n):
        s=self.state(mode);s.update(step=n,terminal=0);return s
    def test_unacknowledged_or_wrong_stage_refused(self):
        s=self.at_step('preserved',13)
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s)
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',14,'pair1-boundary')
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',14,None)
            self.assertFalse((sys/'owner_step').exists())
    def test_uncertain_ledger_refuses_step(self):
        s=self.at_step('preserved',13)
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s,ledger={'boot':'boot2','uncertain':True})
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',14,'spdi-restored')
            self.assertFalse((sys/'owner_step').exists())
    def test_census_mismatch_with_sham_refused_before_requests(self):
        s=self.at_step('preserved',1);sham=record(self.state('sham'));sham['state']['ctx']['census'][1]^=1
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s,sham=sham)
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',2,'census')
            self.assertFalse((sys/'owner_step').exists())
    def test_spdi_refused_unless_common_prefix_patched(self):
        s=self.at_step('preserved',12);s['pairs'][1]['raw']=[0,0]
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s)
            with patch,self.assertRaises(AssertionError):h.observe(p,'step',13,'pair1-boundary')
            self.assertFalse((sys/'owner_step').exists())
    def test_uncertain_snapshot_cannot_be_reported_as_success(self):
        s=self.state('sham')
        with tempfile.TemporaryDirectory() as t:
            p,sys,run,patch=self.fixture(t,s,arm=1,ledger={'boot':'boot2','uncertain':True})
            (p/'baseline.json').write_text(json.dumps(record(s)['baseline']));out=io.StringIO()
            with patch,mock.patch.object(h.subprocess,'check_output',return_value='journal'),contextlib.redirect_stdout(out):h.observe(p,'snapshot',None,None)
            r=json.loads(out.getvalue());self.assertFalse(r['preflight_valid']);self.assertEqual(r['analysis']['classification'],'inconclusive');self.assertNotIn('debug',r)
    def test_qualified_sham_rejects_old_schema_same_boot_and_hash(self):
        sham=record(self.state('sham'));pr=proof(2);pr['boot_id']='boot2';pr['sham_record_sha256']=a.canonical(sham)
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t);shutil.copyfile(HERE/'analyze-dsp-teardown-a.py',p/'analyze-dsp-teardown-a.py')
            (p/'sham-record.json').write_text(json.dumps(sham));self.assertEqual(h.qualified_sham(p,pr)['boot_id'],'boot1')
            bad=dict(pr,sham_record_sha256='0'*64)
            with self.assertRaises(AssertionError):h.qualified_sham(p,bad)
            same=dict(pr,boot_id='boot1')
            with self.assertRaises(AssertionError):h.qualified_sham(p,same)
            old=json.loads((ROOT/'docs/hdmi-evidence/2026-10-22-dsp-owner-sham-live/board-export/snapshot-25.json').read_text())
            (p/'sham-record.json').write_text(json.dumps(old))
            with self.assertRaises(AssertionError):h.qualified_sham(p,dict(pr,sham_record_sha256=a.canonical(old)))
    def test_stage_table_covers_every_pair_and_intervention(self):
        self.assertEqual(sorted(h.STAGES),[1,2,3,6,7,8,9,12,13,14,15,18,19,20,21,24,25,26,27,30,31,32,33,34,37])

class HostRunner(unittest.TestCase):
    def test_deadline_is_recorded_uncertain_and_never_retried(self):
        r=load('host',HERE/'dsp-teardown-a-host.py');calls=[]
        def run(*args,**kw):calls.append(args);raise subprocess.TimeoutExpired('ssh',20,output=b'partial')
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t)/'live-sham-01';p.mkdir();(p/'capture-plan.json').write_text('{"arm":1}')
            with mock.patch.object(r.subprocess,'run',run),self.assertRaises(SystemExit):r.observe(p,'step',3,None)
            self.assertEqual(len(calls),1);self.assertIn('HOST DEADLINE',(p/'step-03-uncertain.log').read_text())
            with mock.patch.object(r.subprocess,'run',run),self.assertRaises(FileExistsError):r.remote(p,'step-03-uncertain'[:-10],'x',20)
    def test_step_record_requires_matching_before_event(self):
        r=load('host',HERE/'dsp-teardown-a-host.py')
        state={'arm':1,'step':3,'failed':0,'timeout':0,'claimed':1,'terminal':0,'requests':1,'ctl':0x700,'cfg':0x011a5e00,'graph_remaining':22,'pairs':[],'ctx':{'spdi_writes':0,'bridge_writes':0,'at_writes':0}}
        body=json.dumps({'state':state,'preflight_valid':True,'analysis':{}})
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t)/'live-sham-01';p.mkdir();(p/'capture-plan.json').write_text('{"arm":1}')
            done=subprocess.CompletedProcess([],0,(json.dumps({'event':'before-step','number':4})+'\n'+body).encode(),b'')
            with mock.patch.object(r.subprocess,'run',return_value=done),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(AssertionError):r.observe(p,'step',3,'pair0-lock')
class ColdProof(unittest.TestCase):
    def test_fresh_cold_evidence_and_arm_gating(self):
        r=load('runner',ROOT/'tools/serial/run-dsp-teardown-cold.py')
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t);(p/'cold-teardown.scr').write_bytes(b'script')
            digest=hashlib.sha256(b'script').hexdigest()
            (p/'manifest.json').write_text(json.dumps({'bundle':{'h713-hdmi-audio.ko':'module'},'cold_script_sha256':digest}))
            cold=p/'cold.log';cold.write_bytes(b'U-Boot SPL test\r\nH713 RESET v1 stage=proper_preboot gp6=00000000 gp7=00000000 mips_status=00000000\r\n=> ')
            self.assertEqual(r.intent(p,cold,1)['schema'],'h713-teardown-a-arm-v1')
            with self.assertRaises(AssertionError):r.intent(p,cold,2)
            old=ROOT/'docs/hdmi-evidence/2026-10-22-dsp-owner-sham-live/board-export/snapshot-25.json'
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
        self.assertIn('if itest.l *0x07090118 == 0; then',text);self.assertIn('h713,dsp-teardown-a-v1 <0x54445241>',text)
        self.assertIn(' h713_teardown_a=1 && bootm',text);self.assertNotIn('dsp-owner-boundary',text);self.assertNotIn('h713_owner_boundary',text)
    def test_changed_anchors_rejected(self):
        with self.assertRaises(ValueError):b.replace_once('xx','x','y')
    def test_source_patch_applies_once_to_pinned_production(self):
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t)
            for n in ('h713-hdmi-pcm.c','h713-hdmi-dsp.c'):shutil.copyfile(ROOT/'modules/hdmi-audio'/n,p/n)
            b.patch_sources(p);pcm=(p/'h713-hdmi-pcm.c').read_text();dsp=(p/'h713-hdmi-dsp.c').read_text()
            self.assertEqual(pcm.count('#include "teardown-pcm.inc"'),1);self.assertEqual(dsp.count('#include "teardown-observer.inc"'),1)
            self.assertNotIn('ret = register_pcm();',pcm);self.assertEqual(pcm.count('ret = h713_owner_pin();'),1)
            self.assertLess(pcm.index('ret = h713_owner_init_check();'),pcm.index('if (!armed || !live_source3'))
            # The include must follow every PCM symbol it touches.
            for sym in ('static struct snd_card *capture_card;','static bool pcm_running;','static u32 spdi1_saved_ctl1;','static void release_resources(void)'):
                self.assertLess(pcm.index(sym),pcm.index('#include "teardown-pcm.inc"'),sym)
            with self.assertRaises(ValueError):b.patch_sources(p)
if __name__=='__main__':unittest.main()
