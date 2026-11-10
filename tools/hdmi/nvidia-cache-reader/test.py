#!/usr/bin/env python3
"""Offline adversarial tests of the actual reader, gate and request boundary."""
import argparse
import contextlib
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('reader',HERE/'reader.py')
r=importlib.util.module_from_spec(spec)
# dataclasses resolves annotations through the imported module.
import sys
sys.modules['reader']=r
spec.loader.exec_module(r)


def replies():
    return [{'status':0,'data':data} for data in [[0x1234],[],[],[0,0x10101,0x10101],
      [0,0x31,0x10001,0],[0,0,0x10101,0x10101,0x10101,0],[0,0,0x10000],[]]]

class Tests(unittest.TestCase):
    def test_01_exact_sequence(self):
        t=r.Replay(replies());b=r.Boundary(t);result=b.run()
        self.assertEqual(len(t.trace),8)
        self.assertEqual([(x.kind,x.code) for x in t.trace],
           [('alloc',0x41),('alloc',0x80),('alloc',0x73),('control',0x730107),
            ('control',0x730108),('control',0x730109),('control',0x73010a),('free',0)])
        self.assertEqual(t.trace[4].params,(0,0x31,0x10101,0))
        self.assertEqual(t.trace[-1].object,0x1234)
        self.assertEqual(result['connected_mask'],0x10001)
        self.assertFalse(result['hardware_executed']);self.assertFalse(result['live_rm_qualified'])
        self.assertEqual(result['physical_hpd'],'not measured')
        self.assertIn('not established',result['hdmi_port_mapping'])
        self.assertEqual(t.frames,[])
        with self.assertRaises(r.Refused):b.run()
        with self.assertRaises(r.Refused):b.send(t.trace[0])

    def test_02_flags_exhaustive(self):
        good=r.Request('control',0x1234,0,r.DISPLAY,0x730108,(0,0x31,1,0))
        for flags in range(256):
            q=replace(good,params=(0,flags,1,0))
            if flags==0x31:q.validate()
            else:
                with self.assertRaises(r.Refused):q.validate()

    def test_03_dangerous_and_unknown_commands(self):
        # Consuming GET, EDID read, I2C, setters, default/unrecognized control.
        for code in [0x73012d,0x730245,0x730110,0x73010b,0,0xffffffff,0x20800501,0x402c0101]:
            with self.assertRaises(r.Refused):
                r.Request('control',0x1234,0,r.DISPLAY,code,(0,0,0)).validate()

    def test_04_wrong_query_shapes(self):
        for code,size in [(0x730107,3),(0x730108,4),(0x730109,6),(0x73010a,3)]:
            for count in range(10):
                if count==size:continue
                with self.assertRaises(r.Refused):
                    r.Request('control',0x1234,0,r.DISPLAY,code,(0,)*count).validate()

    def test_05_query_output_placeholders_zero(self):
        for code,size in [(0x730107,3),(0x730109,6),(0x73010a,3)]:
            for index in range(size):
                words=[0]*size;words[index]=1
                with self.assertRaises(r.Refused):
                    r.Request('control',0x1234,0,r.DISPLAY,code,tuple(words)).validate()

    def test_06_bad_subdevice_and_mask(self):
        for words in [(1,0x31,1,0),(0,0x31,0,0),(0,0x31,1,1)]:
            with self.assertRaises(r.Refused):r.Request('control',0x1234,0,r.DISPLAY,0x730108,words).validate()

    def test_07_wrong_target_handles(self):
        good=r.Request('control',0x1234,0,r.DISPLAY,0x730109,(0,)*6)
        for key,values in [('root',[0,r.DEVICE,r.DISPLAY]),('parent',[1,r.DEVICE]),('object',[0,r.DEVICE,0x1234])]:
            for value in values:
                with self.assertRaises(r.Refused):replace(good,**{key:value}).validate()

    def test_08_allocation_classes_and_fields(self):
        good=r.Request('alloc',0,0,0,0x41,())
        for code in [0,1,0x2080,0xc670,0x5070,0x30,0xffffffff]:
            with self.assertRaises(r.Refused):replace(good,code=code).validate()
        for key in ['root','parent','object']:
            with self.assertRaises(r.Refused):replace(good,**{key:1}).validate()
        for req in [r.Request('alloc',0x1234,0x1234,r.DEVICE,0x80,(0,)*14),
                    r.Request('alloc',0x1234,r.DEVICE,r.DISPLAY,0x73,())]:
            req.validate()
            with self.assertRaises(r.Refused):replace(req,object=5).validate()
        words=[0]*14;words[4]=1
        with self.assertRaises(r.Refused):r.Request('alloc',0x1234,0x1234,r.DEVICE,0x80,tuple(words)).validate()

    def test_09_free_only_local_root(self):
        q=r.Request('free',0x1234,0,0x1234,0,());q.validate()
        for key in ['root','parent','object','code']:
            with self.assertRaises(r.Refused):replace(q,**{key:99}).validate()
        with self.assertRaises(r.Refused):replace(q,params=(0,)).validate()

    def test_10_unsigned_strict(self):
        for value in [-1,2**32,True,False,None,'1',1.0]:
            with self.assertRaises(r.Refused):r.uint(value)
        for value in [0,2**32-1]:self.assertEqual(r.uint(value),value)

    def test_11_order_gate(self):
        for index in range(8):
            b=r.Boundary(r.Replay(replies()))
            for _ in range(index):b.send(b.expected())
            wrong=r.Request('alloc',0,0,0,0x41,()) if index else r.Request('control',0x1234,0,r.DISPLAY,0x73010a,(0,0,0))
            calls=len(b.transport.trace)
            with self.assertRaises(r.Refused):b.send(wrong)
            self.assertEqual(len(b.transport.trace),calls)
            with self.assertRaises(r.Refused):b.send(b.expected())

    def test_12_status_failure_all_stages(self):
        for index in range(8):
            for status in [1,0x56,0xffffffff]:
                f=replies();f[index]['status']=status;t=r.Replay(f);b=r.Boundary(t)
                with self.assertRaises(r.Refused):b.run()
                self.assertEqual(len(t.trace),index+1)
                self.assertTrue(b.failed)
                with self.assertRaises(r.Refused):b.send(b.expected())
                self.assertEqual(len(t.trace),index+1)

    def test_13_transport_failure_all_stages(self):
        for index in range(8):
            class Broken(r.Replay):
                def exchange(self,req):
                    if len(self.trace)==index:raise OSError('transport failure')
                    return super().exchange(req)
            b=r.Boundary(Broken(replies()))
            with self.assertRaises(OSError):b.run()
            self.assertTrue(b.failed)
            with self.assertRaises(r.Refused):b.send(b.expected())

    def test_14_malformed_envelopes(self):
        for bad in [None,[],{},dict(status=0),dict(status=0,data=[],extra=1),dict(status=True,data=[])]:
            f=replies();f[0]=bad;b=r.Boundary(r.Replay(f))
            with self.assertRaises(r.Refused):b.run()
            self.assertEqual(len(b.trace),1)

    def test_15_malformed_data_all_stages(self):
        for index in range(8):
            for data in [None,'',[-1],[2**32],[True]]:
                f=replies();f[index]['data']=data;b=r.Boundary(r.Replay(f))
                with self.assertRaises(r.Refused):b.run()
                self.assertEqual(len(b.trace),index+1)

    def test_16_invalid_root_response(self):
        for value in [0,r.DEVICE,r.DISPLAY]:
            f=replies();f[0]['data']=[value];b=r.Boundary(r.Replay(f))
            with self.assertRaises(r.Refused):b.run()
            self.assertEqual(len(b.trace),1)
            self.assertEqual(b.index,0)
            self.assertIsNone(b.root)

    def test_17_supported_masks(self):
        for data in [[0,0,0],[0,1,2],[1,1,1]]:
            f=replies();f[3]['data']=data;b=r.Boundary(r.Replay(f))
            with self.assertRaises(r.Refused):b.run()
            self.assertEqual(len(b.trace),4)

    def test_18_cached_reply_must_not_drift(self):
        for data in [[0,0,1,0],[0,0x31,2,0],[0,0x31,1,1],[1,0x31,1,0]]:
            f=replies();f[4]['data']=data;b=r.Boundary(r.Replay(f))
            with self.assertRaises(r.Refused):b.run()
            self.assertEqual(len(b.trace),5)

    def test_19_config_state_validation(self):
        for index,data in [(5,[0,1,0,0,0,0]),(5,[0,0,1,0,0,0]),(6,[0,2,0])]:
            f=replies();f[index]['data']=data;b=r.Boundary(r.Replay(f))
            with self.assertRaises(r.Refused):b.run()
            self.assertEqual(len(b.trace),index+1)

    def test_20_packed_sizes(self):
        b=r.Boundary(r.Replay(replies()));b.run()
        for req in b.trace:
            if req.kind=='control':self.assertEqual(len(req.words()),r.SIZES[req.code])
        self.assertEqual(b.trace[1].words(),bytes(56))

    def test_21_no_unknown_operations(self):
        for kind in ['open','ioctl','mmap','reset','i2c','notify','detect','set','close']:
            with self.assertRaises(r.Refused):r.Request(kind,0,0,0,0,()).validate()

    def test_22_live_always_fails_before_access(self):
        with mock.patch.object(Path,'open',side_effect=AssertionError('file open')), \
             mock.patch.object(r,'LIVE_RM_QUALIFIED',True):
            with self.assertRaisesRegex(r.Refused,'No device was opened'):r.live_reader()

    def test_23_default_cli_inert(self):
        with mock.patch.object(Path,'open',side_effect=AssertionError('open')), \
             mock.patch.object(Path,'read_text',side_effect=AssertionError('read')), \
             mock.patch('sys.argv',['reader.py']),contextlib.redirect_stdout(io.StringIO()) as out:
            r.main()
        x=json.loads(out.getvalue());self.assertFalse(x['hardware_executed']);self.assertFalse(x['live_rm_qualified'])
        self.assertEqual(x['cached_connection_flags'],'0x31')

    def test_24_execute_cli_cannot_override_gate(self):
        with mock.patch('sys.argv',['reader.py','--execute-approved']), \
             mock.patch.object(Path,'open',side_effect=AssertionError('open')):
            with self.assertRaises(r.Refused):r.main()

    def fixture(self,root):
        data={'sys/module/nvidia/version':b'615.78.08\n','sys/class/drm/card1-HDMI-A-1/status':b'disconnected\n',
              'sys/class/drm/card1-HDMI-A-1/enabled':b'disabled\n','sys/class/drm/card1-HDMI-A-1/edid':b''}
        for name,value in data.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
        return data

    def test_25_cached_files_only_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);data=self.fixture(root);opened=[];original=Path.open
            def read_only(p,mode='r',*a,**kw):
                self.assertEqual(mode,'rb');self.assertIn(str(p.relative_to(root)),data)
                opened.append(p);return original(p,mode,*a,**kw)
            with mock.patch.object(Path,'open',read_only):x=r.read_cached(root)
            self.assertEqual(len(opened),4);self.assertEqual(x['nvidia_control_calls'],0)
            self.assertEqual(x['device_nodes_opened'],0);self.assertFalse(x['board_access'])

    def test_26_cached_wrong_version(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);(root/'sys/module/nvidia/version').write_text('other\n')
            with self.assertRaises(r.Refused):r.read_cached(root)

    def test_27_changed_bad_state(self):
        for name,value in [('status',b'connected\n'),('enabled',b'enabled\n'),('edid',b'EDID')]:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);self.fixture(root);(root/'sys/class/drm/card1-HDMI-A-1'/name).write_bytes(value)
                with self.assertRaises(r.Refused):r.read_cached(root)

    def test_28_cached_oversize_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);p=root/'sys/module/nvidia/version';p.write_bytes(b'x'*4097)
            with self.assertRaises(r.Refused):r.read_cached(root)
            p.unlink()
            with self.assertRaises(OSError):r.read_cached(root)

    def test_29_cli_replay(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'replay.json';p.write_text(json.dumps(replies()))
            proc=subprocess.run([sys.executable,'-B',str(HERE/'reader.py'),'--replay',str(p)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertFalse(json.loads(proc.stdout)['hardware_executed'])

    def test_30_replay_length(self):
        for x in [None,{},[],replies()[:-1],replies()+[{}]]:
            with self.assertRaises(r.Refused):r.Replay(x)

    def test_31_vendor_ABI_record(self):
        p=HERE/'abi.json'
        if not p.exists():self.skipTest('run from audited package for vendor ABI integration')
        abi=json.loads(p.read_text())
        self.assertEqual(abi['cached_flags'],r.CACHED_FLAGS)
        self.assertEqual(abi['root_class'],r.ROOT_CLASS)
        self.assertEqual(abi['NV0080_ALLOC_PARAMETERS'],len(r.Request('alloc',0x1234,0x1234,r.DEVICE,0x80,(0,)*14).words()))
        for code,name in [(r.SUPPORTED,'NV0073_CTRL_SYSTEM_GET_SUPPORTED_PARAMS'),
                          (r.CONNECT,'NV0073_CTRL_SYSTEM_GET_CONNECT_STATE_PARAMS'),
                          (r.CONFIG,'NV0073_CTRL_SYSTEM_GET_SET_HOTPLUG_CONFIG_PARAMS'),
                          (r.STATE,'NV0073_CTRL_SYSTEM_GET_HOTPLUG_STATE_PARAMS')]:
            self.assertEqual(abi[name],r.SIZES[code])

    def test_32_live_CLI_refuses(self):
        p=subprocess.run([sys.executable,'-B',str(HERE/'reader.py'),'--execute-approved'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('Live RM access is disabled',p.stderr)
        self.assertEqual(p.stdout,'')

    def test_33_disconnected_cache_is_valid_data(self):
        f=replies();f[4]['data'][2]=0
        x=r.Boundary(r.Replay(f)).run()
        self.assertEqual(x['connected_mask'],0)
        self.assertEqual(x['physical_hpd'],'not measured')
        self.assertFalse(x['hardware_executed'])


def mutations():
    changes=[
      ('probing flags','CACHED_FLAGS = 0x31','CACHED_FLAGS = 0x00'),
      ('weaken query flags','self.params[1]==CACHED_FLAGS','True'),
      ('ignore command sequence',"require(request==self.expected(), 'unexpected command, order or handle')",'pass'),
      ('ignore status',"require(uint(reply['status'])==0, 'RM status failure; no fallback or retry')",'pass'),
      ('allow fallback after failure',"require(not self.failed, 'sequence terminal after refusal; no retry or fallback')",'pass'),
      ('ignore root response','data[0] not in (0,DEVICE,DISPLAY)','True'),
      ('ignore version',"require(version==VERSION, 'driver version mismatch')",'pass'),
      ('ignore changed HDMI',"require(status=='disconnected' and enabled=='disabled' and not data[3], 'preserved bad state changed')",'pass'),
      ('bypass live barrier','raise Refused(LIVE_BLOCKER)','return None'),
      ('accept cached retry hint','data[3]==0','True'),
    ]
    with tempfile.TemporaryDirectory() as td:
        for index,(label,old,new) in enumerate(changes):
            d=Path(td)/str(index);d.mkdir();s=(HERE/'reader.py').read_text()
            if s.count(old)!=1:raise AssertionError((label,s.count(old)))
            (d/'reader.py').write_text(s.replace(old,new));shutil.copyfile(__file__,d/'test.py')
            p=subprocess.run([sys.executable,'-B',str(d/'test.py'),'--fail-fast'],capture_output=True,text=True)
            if p.returncode==0:raise AssertionError('SURVIVED '+label)
            if 'FAIL:' not in p.stderr and not ('ERROR: test_' in p.stderr and 'reader.Refused:' in p.stderr):
                raise AssertionError('not a behavioral kill '+label+'\n'+p.stderr[-1200:])
            print('CAUGHT '+label,flush=True)
    print(f'PASS all {len(changes)} safety mutations detected by behavioral failures')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mutations',action='store_true');p.add_argument('--fail-fast',action='store_true')
    a=p.parse_args()
    if a.mutations:mutations()
    else:raise SystemExit(not unittest.TextTestRunner(verbosity=2,failfast=a.fail_fast).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
