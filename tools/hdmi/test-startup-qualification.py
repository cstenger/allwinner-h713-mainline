#!/usr/bin/env python3
"""Fail-closed qualification evidence tests; no board commands or resets."""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('q',Path(__file__).with_name('startup-qualification.py'))
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)


def fixture():
    services={name:{'ActiveState':'active','Result':'success','NRestarts':'0',
                   'ExecMainStartTimestampMonotonic':'8000000',
                   'ExecMainExitTimestampMonotonic':'14000000',
                   'ActiveEnterTimestampMonotonic':'14500000'} for name in q.UNITS}
    services['user@1000.service']={'ExecMainStartTimestampMonotonic':'8500000','ActiveEnterTimestampMonotonic':'12000000'}
    ipc={'schema':'h713-mips-ipc-v1','complete':True,'command':'help win','reply_bytes':66,'elapsed_seconds':0.43}
    ack={'boot_id':'B1','gp6_after':'48444f4b','gp7':'00000000'}
    journal='\n'.join('MIPS IPC completion '+json.dumps(ipc) for _ in range(5))
    journal+='\n'+json.dumps(ack)+'\n{"already_ready": true}'
    return {'boot_id':'B1','uptime':100,'frames':10000,'services':services,
            'errors':{'rejected':0,'xruns':0,'bad_guard':0,'invalid_pair':0},
            'signal':'locked 1280x720','capture_pcm':'state: RUNNING','playback_pcm':'state: RUNNING',
            'journal':journal,'failed_units':'','readvertised':0,'startup_time':'fixture'}


class Evidence(unittest.TestCase):
    def test_shutdown_ssh_disconnect_observes_one_new_boot_without_retry(self):
        for timed_out in (False,True):
            with self.subTest(timed_out=timed_out):self.transport_case(timed_out)

    def transport_case(self,timed_out):
        old='11111111-1111-1111-1111-111111111111';new='22222222-2222-2222-2222-222222222222'
        before=fixture();before['boot_id']=old;before['journal']=before['journal'].replace('B1',old)
        after=copy.deepcopy(before);after['boot_id']=new
        calls=[]
        def remote(script,timeout=90):
            calls.append(script)
            if len(calls)==1:
                if timed_out:raise subprocess.TimeoutExpired('ssh',20)
                return SimpleNamespace(returncode=255,stdout='',stderr='SSH closed')
            return SimpleNamespace(returncode=0,stdout=json.dumps(after),stderr='')
        def read(script,path):
            return {'status':'PASS fixture','boot_id':old} if path.name=='before-identity.json' else before
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);audit=root/'audit.py';audit.write_text('# never executed fixture')
            argv=['qualification','warm','--root',directory,'--label','warm-01','--from-boot',old,'--audit',str(audit)]
            with patch('sys.argv',argv),patch.object(q,'remote',remote),patch.object(q,'read_remote',read),patch.object(q,'collect',return_value={'status':'PASS'}) as collect,contextlib.redirect_stdout(io.StringIO()):
                q.main()
                collect.assert_called_once()
                self.assertEqual(collect.call_args.kwargs,{'expected':new,'previous':old})
                with self.assertRaises(FileExistsError):q.main()
        self.assertEqual(sum("['systemctl','reboot','--no-block']" in script for script in calls),1)

    def test_remote_snapshot_parses_separate_units_and_original_counters(self):
        env={};exec(q.REMOTE,env)
        item=fixture();raw='\n\n'.join('Id='+name+'\n'+'\n'.join(k+'='+v for k,v in unit.items()) for name,unit in item['services'].items())
        env['command']=lambda args:raw
        def read(path):
            if path.endswith('/boot_id'):return 'B1'
            if path=='/proc/uptime':return '100.0 80.0'
            if path.endswith('/signal'):return 'locked 1280x720'
            if path.endswith('/status'):return 'state: RUNNING'
            if path.endswith('/frames_produced'):return '10000'
            return '0'
        env['read']=read
        row=env['snapshot']();q.healthy(row)
        self.assertEqual(set(row['services']),set(item['services']))
    def test_complete_startup_evidence_and_stable_frames(self):
        row=fixture();self.assertGreater(q.startup_evidence(row)['user_overlap_seconds'],0)
        samples=[]
        for i in range(7):
            sample=copy.deepcopy(row);sample.update(uptime=100+i*5,frames=10000+i*300);samples.append(sample)
        self.assertEqual(q.stable(samples)['fps'],60)
        for mutation in ('boot','restart','identity','frames','errors','short'):
            changed=copy.deepcopy(samples)
            if mutation=='boot':changed[-1]['boot_id']='B2'
            elif mutation=='restart':changed[-1]['services'][q.UNITS[0]]['NRestarts']='1'
            elif mutation=='identity':changed[-1]['services'][q.UNITS[0]]['ExecMainStartTimestampMonotonic']='1234'
            elif mutation=='frames':changed[2]['frames']=1
            elif mutation=='errors':changed[-1]['errors']['rejected']=1
            else:changed=changed[:2]
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):q.stable(changed)
    def test_missing_ipc_ack_adoption_overlap_or_health_refuses(self):
        for mutation in ('ipc','ack','adoption','overlap','pcm','failed','service'):
            row=fixture()
            if mutation=='ipc':row['journal']=row['journal'].replace('"complete": true','"complete": false',1)
            elif mutation=='ack':row['journal']=row['journal'].replace('48444f4b','00000000')
            elif mutation=='adoption':row['journal']=row['journal'].replace('"already_ready": true','"already_ready": false')
            elif mutation=='overlap':row['services']['user@1000.service']['ActiveEnterTimestampMonotonic']='7000000'
            elif mutation=='pcm':row['capture_pcm']='state: XRUN'
            elif mutation=='failed':row['failed_units']='unexpected.service failed'
            else:del row['services'][q.UNITS[0]]
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):q.startup_evidence(row)
    def test_shutdown_requires_restoration_and_the_real_stop_order(self):
        prefix='EDID/HPD, SCP SRAM/vectors and DDC ownership restored\n'+json.dumps({'phase':'parked','receiver_removed':True,'dsp_restored_words':22,'tvfe_restored_words':15})+'\n'
        units=['video','speaker','signal','capture','prepare']
        lines=['Stopped h713-hdmi-'+name+'.service - fixture' for name in units]+['Stopped user@1000.service - fixture']
        self.assertTrue(q.shutdown_evidence(prefix+'\n'.join(lines)).startswith('PASS'))
        for bad in (prefix.replace('22','21')+'\n'.join(lines),prefix+'\n'.join(reversed(lines)),prefix+'\n'.join(lines[:-1])):
            with self.assertRaises(RuntimeError):q.shutdown_evidence(bad)


if __name__=='__main__':unittest.main()
