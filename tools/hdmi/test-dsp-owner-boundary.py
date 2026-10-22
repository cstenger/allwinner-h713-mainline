#!/usr/bin/env python3
import copy,hashlib,importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest,contextlib,io
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def load(name,file):
    s=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load('a',HERE/'analyze-dsp-owner-boundary.py');b=load('b',HERE/'prepare-dsp-owner-boundary.py')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=pathlib.Path(cls.temp.name)
        (cls.path/'linux').mkdir();(cls.path/'linux/mutex.h').write_text('')
        for p in (HERE/'dsp-owner-boundary').iterdir():shutil.copyfile(p,cls.path/p.name)
        shutil.copyfile(ROOT/'modules/hdmi-dsp-probe/h713-dsp-lock.h',cls.path/'h713-dsp-lock.h')
        subprocess.run(['cc','-std=gnu11','-I'+str(cls.path),str(cls.path/'native-test.c'),'-o',str(cls.path/'test')],check=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_sham_and_preserved_boundary(self):
        for mode in ('sham','preserved'):
            result=subprocess.run([str(self.path/'test'),mode],check=True,capture_output=True,text=True)
            state=json.loads(result.stdout);self.assertEqual(len(state['pairs']),4);self.assertEqual(len(state['graph_saved']),22);self.assertEqual(state['step'],25)
    def test_config_loss_stops_before_control_and_control_loss_bracket(self):
        for mode in ('lose-graph','lose-cfg','lose-ctl'):subprocess.run([str(self.path/'test'),mode],check=True)
    def test_failure_and_timeout_never_retry_or_advance_boundary(self):
        for mode in ('missing-arm','missing-marker','health-bad','lock-bad','busy-timeout','done-timeout','bad-positive','context-drift','late-timeout','graph-failure'):subprocess.run([str(self.path/'test'),mode],check=True)
class Analysis(unittest.TestCase):
    def record(self,arm=1):
        return {'boot_id':'boot'+str(arm),'preflight_valid':True,'proof':{'verified':True,'boot_id':'boot'+str(arm),'arm':arm,'manifest_sha256':'same','module_sha256':'module','cold_script_sha256':'script'},'baseline':{'boot_id':'boot'+str(arm),'tv_domains_both_on':True,'reads':{'mips_status':'00000001'},'dsp_journal':['DSP versions 0000/0000','pinned 724-pair DSP patch verified versions 1/1']},'state':{'schema':'h713-owner-boundary-v1','arm':arm,'step':25,'graph_saved':[0]*22,'graph_remaining':22 if arm==1 else 0,'failed':0,'claimed':0,'terminal':1,'timeout':0,'ctl':0x700,'cfg':0x011a5e00 if arm==1 else 0,'pairs':[{'raw':[1,1],'outcome':[1,1],'phase':[5,5],'sent':[1,1]} for i in range(4)]}}
    def test_sham_and_preserved(self):
        self.assertEqual(a.analyze(self.record())['classification'],'sham_positive_control_passed')
        self.assertEqual(a.analyze(self.record(2))['classification'],'tested_shutdown_boundaries_preserved_patch')
    def test_loss_at_each_boundary(self):
        r=self.record(2);r['state']['step']=18;r['state']['pairs'][2]['raw']=[0,0]
        self.assertEqual(a.analyze(r)['classification'],'version_change_after_config_clear')
        r=self.record(2);r['state']['pairs'][3]['raw']=[0,0]
        self.assertEqual(a.analyze(r)['classification'],'version_change_after_control_off_on')
    def test_timeout_or_unknown_response_never_patch_loss(self):
        r=self.record(2);r['state']['timeout']=1;r['state']['pairs'][1].update(raw=[0xffffffff,0xffffffff],outcome=[2,3],phase=[4,6],sent=[1,0])
        self.assertEqual(a.analyze(r)['classification'],'access_timeout')
        r['state']['timeout']=0;self.assertEqual(a.analyze(r)['classification'],'inconclusive')
    def test_command_echo_is_not_a_zero_version(self):
        r=self.record(2);r['state'].update(step=12,cfg=0x011a5e00);r['state']['pairs'][1]['raw']=[0x80ff0000,0x80ff0000]
        self.assertEqual(a.analyze(r)['classification'],'ambiguous_command_echo')
    def test_graph_restore_is_an_earlier_boundary(self):
        r=self.record(2);r['state'].update(step=12,cfg=0x011a5e00);r['state']['pairs'][1]['raw']=[0,0]
        self.assertEqual(a.analyze(r)['classification'],'version_change_after_graph_restore')
    def test_bad_positive_not_used_for_attribution(self):
        r=self.record(2);r['state']['pairs'][0]['raw']=[0,0]
        self.assertEqual(a.analyze(r)['classification'],'patched_positive_control_not_observed')
    def test_matched_pair_requires_qualified_distinct_exact_sham(self):
        sham=self.record();bound=self.record(2);bound['proof']['sham_record_sha256']=hashlib.sha256((json.dumps(sham,sort_keys=True)+'\n').encode()).hexdigest()
        self.assertEqual(a.compare(sham,bound)['classification'],'matched_tested_shutdown_boundaries_preserved_patch')
        for field in ('manifest_sha256','module_sha256','cold_script_sha256','sham_record_sha256'):
            changed=copy.deepcopy(bound);changed['proof'][field]='bad';self.assertEqual(a.compare(sham,changed)['classification'],'unmatched_or_unqualified')
class Ledger(unittest.TestCase):
    def test_uncertain_snapshot_cannot_be_reported_as_success(self):
        h=load('helper',HERE/'dsp-owner-boundary.py')
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t);sys=p/'sys';sys.mkdir();run=p/'run';run.mkdir()
            r=Analysis().record();proof=r['proof'];proof['boot_id']=r['boot_id']
            (sys/'owner_arm').write_text('1');(sys/'dsp_failed').write_text('N');(sys/'owner_state').write_text(json.dumps(r['state']))
            (run/'ledger.json').write_text(json.dumps({'boot':r['boot_id'],'uncertain':True}))
            (p/'baseline.json').write_text(json.dumps(r['baseline']));shutil.copyfile(HERE/'analyze-dsp-owner-boundary.py',p/'analyze-dsp-owner-boundary.py')
            out=io.StringIO()
            with mock.patch.object(h,'SYS',sys),mock.patch.object(h,'RUN',run),mock.patch.object(h,'preflight',return_value=({},proof)),mock.patch.object(h.subprocess,'check_output',return_value='journal'),contextlib.redirect_stdout(out):h.observe(p,'snapshot',None,None)
            record=json.loads(out.getvalue());self.assertFalse(record['preflight_valid']);self.assertEqual(record['analysis']['classification'],'inconclusive');self.assertNotIn('debug',record)
class ColdProof(unittest.TestCase):
    def test_fresh_cold_evidence_and_arm_gating(self):
        r=load('runner',ROOT/'tools/serial/run-dsp-owner-cold.py')
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t);(p/'cold-owner.scr').write_bytes(b'script')
            digest=hashlib.sha256(b'script').hexdigest()
            (p/'manifest.json').write_text(json.dumps({'bundle':{'h713-hdmi-audio.ko':'module'},'cold_script_sha256':digest}))
            cold=p/'cold.log';cold.write_bytes(b'U-Boot SPL test\r\nH713 RESET v1 stage=proper_preboot gp6=00000000 gp7=00000000 mips_status=00000000\r\n=> ')
            self.assertEqual(r.intent(p,cold,1)['arm'],1)
            with self.assertRaises(AssertionError):r.intent(p,cold,2)
            cold.write_bytes(cold.read_bytes().replace(b'gp6=00000000',b'gp6=48444d49'))
            with self.assertRaises(AssertionError):r.intent(p,cold,1)
class ColdScript(unittest.TestCase):
    def test_only_proven_cold_path_and_runtime_masks(self):
        text=b.cold_script((b.INSTALLED/'h713-hdmi.cmd').read_text())
        self.assertEqual(text.count('bootm '),1);self.assertEqual(text.count('h713_disp auto 0x34 logo'),1)
        self.assertEqual(text.count('h713_disp mips-comm-trace 0x34'),1)
        self.assertNotIn('gpio set PB5',text);self.assertNotIn('saveenv',text);self.assertNotIn('mw.l 0x0709011c',text)
        for unit in ('capture','signal','speaker'):self.assertIn('systemd.mask=h713-hdmi-'+unit+'.service',text)
        self.assertIn('if itest.l *0x07090118 == 0; then',text);self.assertIn('h713,dsp-owner-boundary-v1',text)
    def test_changed_anchors_rejected(self):
        with self.assertRaises(ValueError):b.replace_once('xx','x','y')
if __name__=='__main__':unittest.main()
