#!/usr/bin/env python3
"""Offline end-to-end tests: real protocol and ctypes/libc codec, fake kernel peer."""
import argparse
import ctypes as C
import errno
from dataclasses import replace
import importlib.util
import io
import contextlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import protocol as p
import transport as t
import reader as r
HERE=Path(__file__).resolve().parent

class Kernel:
    def __init__(self):
        self.trace=[];self.closed=[];self.resources=set();self.fail_at=None;self.status_at=None
        self.after=False;self.override={};self.corrupt_envelope=False
    def ioctl(self,fd,request,data,mutate):
        assert fd==9 and mutate is True
        types={0xc020462b:t.Alloc,0xc020462a:t.Control,0xc0104629:t.Free}
        assert request in types
        api=types[request].from_buffer(data)
        assert api.status==0xffffffff
        code=api.klass if request==0xc020462b else api.command if request==0xc020462a else 0
        size=getattr(api,'size',0);pointer=getattr(api,'params',0)
        array=(C.c_uint32*(size//4)).from_address(pointer) if pointer else []
        incoming=tuple(array);self.trace.append((request,code,incoming));n=len(self.trace)
        if self.fail_at==n and not self.after:raise OSError('injected syscall failure')
        if request==0xc020462b:
            if code==0x41:
                assert (api.root,api.parent,api.object,pointer,size)==(0,0,0,0,0)
                api.object=0xc0000000;self.resources.add(api.object)
            elif code==0x80:
                assert api.root in self.resources and api.parent==api.root and api.object==0x10001
                assert incoming==(0,)*14;self.resources.add(api.object)
            elif code==0x73:
                assert api.root==0xc0000000 and api.parent==0x10001 and api.object==0x10002 and size==0
                self.resources.add(api.object)
            else:raise AssertionError('unapproved alloc')
        elif request==0xc020462a:
            assert api.flags==0 and api.root==0xc0000000
            if code in [0x201,0x205,0x21b]:assert api.object==api.root
            else:assert api.object==0x10002
            replies={0x201:(0xdeadbeef,)+(0xffffffff,)*31,
              0x21b:(0xdeadbeef,0,12),0x205:(0xdeadbeef,9,0,0,0,5,0,0xffffffff),
              0x730107:(0,0x10101,0x10101),0x730108:(0,0x31,0x10001,0),
              0x730109:(0,0,0x10101,0x10101,0x10101,0),0x73010a:(0,0,0x10000)}
            if code==0x730250:
                assert incoming[0]==0 and incoming[1] in (1,0x100,0x10000) and not any(incoming[2:])
                bit=incoming[1]
                reply=(0,bit,1,bit,1,2 if bit==0x10000 else 1,0x61 if bit==0x10000 else 0x46,0)+(0,)*10
            else:
                assert code in replies,'unapproved control'
                reply=replies[code]
                if code==0x730108:assert incoming==(0,0x31,0x10101,0)
            reply=self.override.get(code,reply)
            assert len(reply)==len(array),(code,len(reply),len(array))
            for i,v in enumerate(reply):array[i]=v
            if self.corrupt_envelope:api.flags=1
        else:
            assert (api.root,api.parent,api.object)==(0xc0000000,0,0xc0000000)
            self.resources.clear()
        api.status=0x56 if self.status_at==n else 0
        if self.fail_at==n and self.after:raise OSError('applied but observation failed')
    def close(self,fd):
        assert fd==9;self.closed.append(fd);self.resources.clear()
    def transport(self):return t.Transport(9,self.ioctl,self.close)

class Tests(unittest.TestCase):
    def run_kernel(self,k=None):
        k=k or Kernel();s=p.Snapshot(k.transport());result=s.run();return k,s,result
    def test_01_full_wire_snapshot(self):
        k,s,x=self.run_kernel()
        self.assertEqual(len(k.trace),13);self.assertEqual(k.closed,[9]);self.assertFalse(k.resources)
        self.assertEqual([row[1] for row in k.trace],
          [0x41,0x201,0x21b,0x205,0x80,0x73,0x730107,0x730250,0x730250,0x730250,0x730108,0x73010a,0])
        self.assertEqual(x['hdmi_a_display_ids'],['0x10000'])
        self.assertTrue(x['hdmi_a_cached_connected'][0]['connected'])
        self.assertEqual(x['physical_hpd'],'not measured');self.assertFalse(x['board_access'])
        self.assertFalse(x['ddc_transactions_requested']);self.assertTrue(x['own_client_freed'])
        with self.assertRaises(p.Refused):s.run()
        self.assertEqual(len(k.trace),13)
    def test_02_all_syscall_failures_before_and_after(self):
        for after in [False,True]:
            for n in range(1,14):
                k=Kernel();k.fail_at=n;k.after=after;s=p.Snapshot(k.transport())
                with self.assertRaises((OSError,p.Refused)):s.run()
                self.assertEqual(k.closed,[9]);self.assertFalse(k.resources)
                self.assertLessEqual(sum(row[1]==0 for row in k.trace),1)
                self.assertLessEqual(sum(row[1]==0x41 for row in k.trace),1)
                if n<13 and n>1:self.assertEqual(k.trace[-1][1],0)
                self.assertTrue(all(row[0] in [0xc020462a,0xc020462b,0xc0104629] for row in k.trace))
    def test_03_all_RM_status_failures(self):
        for n in range(1,14):
            k=Kernel();k.status_at=n;s=p.Snapshot(k.transport())
            with self.assertRaises(p.Refused):s.run()
            self.assertEqual(k.closed,[9]);self.assertFalse(k.resources)
            self.assertEqual(sum(row[1]==0x41 for row in k.trace),1)
            if n>1:self.assertEqual(k.trace[-1][1],0)
    def test_04_cached_flags_exhaustive(self):
        for flags in range(256):
            call=p.Call('control',7,0,p.DISPLAY,p.CONNECT,(0,flags,1,0))
            if flags==0x31:call.validate(7)
            else:
                with self.assertRaises(p.Refused):call.validate(7)
    def test_05_forbidden_control_set(self):
        for cmd in [0x730109,0x73012d,0x730245,0x730110,0x73010b,0x20800101,0x402c0101,0,0xffffffff]:
            with self.assertRaises(p.Refused):p.Call('control',7,0,p.DISPLAY,cmd,(0,0,0)).validate(7)
    def test_06_forbidden_allocations(self):
        for klass in [0,1,0x5070,0xc670,0x2080,0x30,0x79]:
            with self.assertRaises(p.Refused):p.Call('alloc',7,7,77,klass,()).validate(7)
    def test_07_ownership_and_lifecycle(self):
        for bad in [None,0,1,7]:
            with self.assertRaises(p.Refused):p.Call('free',8,0,8,0,()).validate(bad)
        k=Kernel();wire=k.transport()
        with self.assertRaises(p.Refused):wire.exchange(p.Call('control',7,0,p.DISPLAY,p.STATE,(0,0,0)))
        self.assertEqual(k.trace,[])
    def test_08_metadata_wrong_gpu(self):
        for cmd,reply in [(0x201,(0xffffffff,)*32),(0x201,(0xdeadbeef,2)+(0xffffffff,)*30),
           (0x21b,(0xdeadbeef,0,13)),(0x205,(0xdeadbeef,8,0,0,0,0,0,0)),
           (0x205,(0xdeadbeef,3,0,0,0,0,0,0)),(0x205,(0xdeadbeef,9,32,0,0,0,0,0))]:
            k=Kernel();k.override[cmd]=reply
            with self.assertRaises(p.Refused):p.Snapshot(k.transport()).run()
            self.assertNotIn(0x80,[row[1] for row in k.trace]);self.assertEqual(k.closed,[9])
    def test_09_mapping_is_static_and_bounded(self):
        k=Kernel();k.override[0x730250]=(0,1,1,1,5)+(0,)*13
        with self.assertRaises(p.Refused):p.Snapshot(k.transport()).run()
        self.assertNotIn(0x730108,[row[1] for row in k.trace])
    def test_10_cached_reply_validation(self):
        for reply in [(0,0,1,0),(0,0x31,2,0),(0,0x31,1,1),(1,0x31,1,0)]:
            k=Kernel();k.override[0x730108]=reply
            with self.assertRaises(p.Refused):p.Snapshot(k.transport()).run()
            self.assertNotIn(0x73010a,[row[1] for row in k.trace])
    def test_11_zero_cached_connection_is_success(self):
        k=Kernel();k.override[0x730108]=(0,0x31,0,0);_,_,x=self.run_kernel(k)
        self.assertEqual(x['connected_mask'],'0x0');self.assertFalse(x['hdmi_a_cached_connected'][0]['connected'])
    def test_12_envelope_corruption(self):
        k=Kernel();k.corrupt_envelope=True
        with self.assertRaises(p.Refused):p.Snapshot(k.transport()).run()
        self.assertEqual(k.trace[-1][1],0);self.assertEqual(k.closed,[9])
    def test_13_param_size_and_output_placeholders(self):
        for cmd,size in p.SIZES.items():
            root=cmd in [p.IDS,p.INFO,p.PCI];target=7 if root else p.DISPLAY
            for count in [0,1,100]:
                if count*4==size:continue
                with self.assertRaises(p.Refused):p.Call('control',7,0,target,cmd,(0,)*count).validate(7)
        with self.assertRaises(p.Refused):p.Call('control',7,0,p.DISPLAY,p.CONFIG,(0,1,0,0,0,0)).validate(7)
    def test_14_uints(self):
        for x in [None,True,-1,2**32,1.0,'1']:
            with self.assertRaises(p.Refused):p.u32(x)
    def test_15_node_wrong_identity_before_open(self):
        for mode,uid,dev in [(stat.S_IFREG,0,os.makedev(195,255)),(stat.S_IFCHR,1,os.makedev(195,255)),
                            (stat.S_IFCHR,0,os.makedev(195,0))]:
            fake=mock.Mock(st_mode=mode,st_uid=uid,st_rdev=dev)
            with mock.patch.object(t.os,'stat',return_value=fake),mock.patch.object(t.os,'open',side_effect=AssertionError('unsafe open')):
                with self.assertRaises(p.Refused):t.open_control()
    def test_16_node_control_only(self):
        fake=mock.Mock(st_mode=stat.S_IFCHR,st_uid=0,st_rdev=os.makedev(195,255),st_dev=1,st_ino=2)
        with mock.patch.object(t.os,'stat',return_value=fake),mock.patch.object(t.os,'fstat',return_value=fake), \
             mock.patch.object(t.os,'open',return_value=9) as opened:
            x=t.open_control()
        opened.assert_called_once_with('/dev/nvidiactl',os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW)
        self.assertEqual(x.fd,9)
    def test_17_node_changed_on_open(self):
        before=mock.Mock(st_mode=stat.S_IFCHR,st_uid=0,st_rdev=os.makedev(195,255),st_dev=1,st_ino=2)
        after=mock.Mock(st_mode=stat.S_IFCHR,st_uid=0,st_rdev=os.makedev(195,255),st_dev=1,st_ino=3)
        with mock.patch.object(t.os,'stat',return_value=before),mock.patch.object(t.os,'fstat',return_value=after), \
             mock.patch.object(t.os,'open',return_value=9),mock.patch.object(t.os,'close') as closed:
            with self.assertRaises(p.Refused):t.open_control()
        closed.assert_called_once_with(9)
    def fixture(self,root):
        files={'sys/module/nvidia/version':b'615.78.08\n','proc/sys/kernel/random/boot_id':b'fake-boot\n',
          'sys/bus/pci/devices/0000:0c:00.0/vendor':b'0x10de\n',
          'sys/bus/pci/devices/0000:0c:00.0/driver/module/version':b'615.78.08\n'}
        for name,data in files.items():
            f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
        card=root/'sys/class/drm/card1';card.mkdir(parents=True);(card/'device').symlink_to(root/'sys/bus/pci/devices/0000:0c:00.0',target_is_directory=True)
        for name,state,enabled,edid in [('card1-HDMI-A-1','disconnected','disabled',b''),('card1-DP-1','connected','enabled',b'cached edid')]:
            f=root/'sys/class/drm'/name;f.mkdir();(f/'device').symlink_to(card,target_is_directory=True)
            for label,data in [('status',state.encode()),('enabled',enabled.encode()),('edid',edid)]: (f/label).write_bytes(data)
    def test_18_cached_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);x=r.baseline(root)
            self.assertEqual(x['version'],'615.78.08');self.assertEqual(len(x['connectors']),2)
            (root/'sys/class/drm/card1-HDMI-A-1/status').write_text('connected')
            self.assertEqual(r.baseline(root)['connectors']['card1-HDMI-A-1']['status'],'connected')
    def test_19_no_desktop_or_wrong_version(self):
        for name,value in [('sys/module/nvidia/version','wrong'),('sys/class/drm/card1-DP-1/enabled','disabled'),
                           ('sys/bus/pci/devices/0000:0c:00.0/vendor','0x1234')]:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);self.fixture(root);(root/name).write_text(value)
                with self.assertRaises(p.Refused):r.baseline(root)
    def test_20_default_inert(self):
        with mock.patch('sys.argv',['reader.py']),mock.patch.object(Path,'open',side_effect=AssertionError('file')), \
             mock.patch.object(r,'baseline',side_effect=AssertionError('host read')), \
             mock.patch.object(t,'open_control',side_effect=AssertionError('driver open')),contextlib.redirect_stdout(io.StringIO()) as out:
            r.main()
        self.assertFalse(json.loads(out.getvalue())['hardware_executed'])
    def test_21_full_orchestrator(self):
        with tempfile.TemporaryDirectory() as td:
            k=Kernel();out=Path(td)/'capture';base=dict(boot_id='fake-boot',connectors={})
            with mock.patch.object(r,'sealed',return_value=dict(host_boot_id='fake-boot')), \
                 mock.patch.object(r,'baseline',return_value=base),mock.patch.object(t,'open_control',side_effect=k.transport):
                result=r.execute(out)
            self.assertTrue(result['snapshot_complete']);self.assertEqual(k.closed,[9])
            self.assertTrue((out/'INTENT.json').exists());self.assertTrue((out/'RESULT.json').exists())
            events=[json.loads(line) for line in (out/'events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(x['phase']=='intent' for x in events),13)
            self.assertEqual(sum(x['phase']=='returned' for x in events),13)
    def test_22_orchestrator_failure_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            k=Kernel();k.fail_at=11;out=Path(td)/'capture'
            with mock.patch.object(r,'sealed',return_value=dict(host_boot_id='fake-boot')), \
                 mock.patch.object(r,'baseline',return_value=dict(boot_id='fake-boot')),mock.patch.object(t,'open_control',side_effect=k.transport):
                with self.assertRaises(OSError):r.execute(out)
            self.assertTrue((out/'FAILURE.json').exists());self.assertFalse((out/'RESULT.json').exists())
            self.assertEqual(k.closed,[9]);self.assertEqual(k.trace[-1][1],0)
    def test_23_wrong_boot_refuses_before_driver(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(r,'sealed',return_value=dict(host_boot_id='old')), \
                 mock.patch.object(r,'baseline',return_value=dict(boot_id='new')), \
                 mock.patch.object(t,'open_control',side_effect=AssertionError('driver open')):
                with self.assertRaises(p.Refused):r.execute(Path(td)/'out')
    def test_24_vendor_abi(self):
        path=HERE/'abi.json'
        if not path.exists():self.skipTest('vendor ABI record supplied in final package')
        abi=json.loads(path.read_text())
        for cls,name in [(t.Alloc,'NVOS21_PARAMETERS'),(t.Control,'NVOS54_PARAMETERS'),(t.Free,'NVOS00_PARAMETERS')]:
            self.assertEqual(C.sizeof(cls),abi[name])
        self.assertEqual(t.Alloc.params.offset,abi['NVOS21_PARAMETERS.pAllocParms'])
        self.assertEqual(t.Control.params.offset,abi['NVOS54_PARAMETERS.params'])
        self.assertEqual(t.IOCTLS,dict(alloc=abi['ioctl_alloc'],control=abi['ioctl_control'],free=abi['ioctl_free']))
        self.assertEqual(abi['NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS'],12)
        self.assertEqual(abi['NV0073_CTRL_SPECIFIC_GET_CONNECTOR_DATA_PARAMS'],72)
    def test_25_no_duplicate_cleanup(self):
        k,s,_=self.run_kernel();s.cleanup();s.cleanup()
        self.assertEqual(k.closed,[9]);self.assertEqual(sum(row[1]==0 for row in k.trace),1)
    def test_26_wire_second_root_and_free_refused(self):
        k=Kernel();wire=k.transport();root=p.Call('alloc',0,0,0,0x41,())
        wire.exchange(root)
        with self.assertRaises(p.Refused):wire.exchange(root)
        wire.admit_root(0xc0000000);free=p.Call('free',wire.root,0,wire.root,0,())
        wire.exchange(free)
        with self.assertRaises(p.Refused):wire.exchange(free)
        wire.close();self.assertEqual(k.closed,[9])
    def test_27_unrecognized_operations(self):
        for kind in ['reset','i2c','mmap','notify','attach','detach','modeset','unknown']:
            with self.assertRaises(p.Refused):p.Call(kind,7,0,7,0,()).validate(7)
    def test_28_supported_mask_bounds(self):
        for reply in [(0,0,0),(0,1,2),(0,0x1ffff,0)]:
            k=Kernel();k.override[0x730107]=reply
            with self.assertRaises(p.Refused):p.Snapshot(k.transport()).run()
            self.assertNotIn(0x730250,[row[1] for row in k.trace])

    def test_29_ABI_verifier_rejects_drift(self):
        path=HERE/'abi.json'
        if not path.exists():self.skipTest('vendor ABI record supplied in final package')
        abi=json.loads(path.read_text());t.verify_abi(abi)
        for key in ['NVOS21_PARAMETERS','NVOS54_PARAMETERS.params','ioctl_control',
                    'NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS.slot','cached_flags',
                    'NV0073_CTRL_SPECIFIC_GET_CONNECTOR_DATA_PARAMS']:
            changed=dict(abi);changed[key]+=1
            with self.assertRaises(p.Refused):t.verify_abi(changed)

    def test_30_cleanup_failure_never_reports_success(self):
        k=Kernel()
        def broken_close(fd):k.close(fd);raise OSError('close failed')
        wire=t.Transport(9,k.ioctl,broken_close);session=p.Snapshot(wire)
        with self.assertRaisesRegex(p.Refused,'cleanup failed'):session.run()
        self.assertEqual(k.closed,[9]);self.assertFalse(k.resources)

    def test_31_malformed_replies(self):
        for reply in [None,{},dict(status=0,words=[]),dict(status=0,words=(0,)),
                      dict(status=True,words=(1,)),dict(status=0,words=(True,))]:
            class Broken:
                def exchange(self,call):return reply
                def admit_root(self,root):raise AssertionError('bad root admitted')
                def close(self):self.closed=True
            backend=Broken();session=p.Snapshot(backend)
            with self.assertRaises(p.Refused):session.run()
            self.assertTrue(backend.closed)

    def test_32_sealed_package_refuses_corruption(self):
        if not (HERE/'abi.json').exists():self.skipTest('vendor ABI record supplied in final package')
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in ['reader.py','protocol.py','transport.py','abi.json']:shutil.copyfile(HERE/name,root/name)
            gate=dict(prepared_for_one_explicit_snapshot=True,board_preservation_required=False,
                      qualification_basis='version-matched supported API contract plus open host lifecycle audit')
            (root/'LIVE-GATE.json').write_text(json.dumps(gate))
            (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n' for f in sorted(root.iterdir())))
            with mock.patch.object(r,'ROOT',root):
                self.assertTrue(r.sealed()['prepared_for_one_explicit_snapshot'])
                (root/'protocol.py').write_text('corrupt')
                with self.assertRaises(p.Refused):r.sealed()

    def test_33_live_requires_output_before_access(self):
        with mock.patch('sys.argv',['reader.py','--execute-approved']), \
             mock.patch.object(r,'baseline',side_effect=AssertionError('host access')), \
             mock.patch.object(t,'open_control',side_effect=AssertionError('GPU open')):
            with self.assertRaises(p.Refused):r.main()

    def test_34_wrong_cached_card_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);node=root/'sys/class/drm/card1/device';node.unlink();node.symlink_to(root)
            with self.assertRaises(p.Refused):r.baseline(root)

    def test_35_log_failure_closes_only_own_session(self):
        k=Kernel();count=0
        def broken_log(event):
            nonlocal count
            count+=1
            if count>2:raise OSError('log storage failed')
        session=p.Snapshot(k.transport(),record=broken_log)
        with self.assertRaises(OSError):session.run()
        self.assertEqual(k.closed,[9]);self.assertFalse(k.resources)
        self.assertEqual(len(k.trace),1)

    def test_36_native_EINTR_never_retried(self):
        for error in [errno.EINTR,errno.EAGAIN,errno.EIO]:
            def failure(fd,request,pointer):C.set_errno(error);return -1
            function=mock.Mock(side_effect=failure);lib=mock.Mock(ioctl=function)
            with mock.patch.object(t.C,'CDLL',return_value=lib):
                with self.assertRaises(OSError) as got:t.native_ioctl(9,0xc020462a,bytearray(32),True)
            self.assertEqual(got.exception.errno,error);self.assertEqual(function.call_count,1)

    def test_37_native_mutable_buffer(self):
        def success(fd,request,pointer):
            self.assertEqual((fd,request),(9,0xc020462a))
            (C.c_ubyte*32).from_address(pointer.value)[0]=123
            return 0
        function=mock.Mock(side_effect=success);lib=mock.Mock(ioctl=function);data=bytearray(32)
        with mock.patch.object(t.C,'CDLL',return_value=lib):self.assertEqual(t.native_ioctl(9,0xc020462a,data,True),0)
        self.assertEqual(data[0],123);self.assertEqual(function.call_count,1)


def mutations():
    edits=[
      ('probe flags','protocol.py','CACHE_FLAGS=0x31','CACHE_FLAGS=0'),
      ('skip in-use requirement','protocol.py','info[1]&1 and not info[1]&2','True'),
      ('skip PCI binding','protocol.py',"(pci[1],pci[2]&65535,pci[2]>>16)==self.pci",'True'),
      ('skip cached return check','protocol.py','connected[1]==CACHE_FLAGS and','True and'),
      ('skip single GPU gate','protocol.py','len(live)==1 and ids[0]==live[0] and all(x==0xffffffff for x in ids[1:])','bool(live)'),
      ('skip status error','protocol.py',"need(status==0,'RM failure; no retry or alternate detection')",'pass'),
      ('skip own client free','protocol.py',"if self.root is not None:self.send(Call('free',self.root,0,self.root,0,()))",'if False:pass'),
      ('open GPU node','transport.py',"path='/dev/nvidiactl'","path='/dev/nvidia0'"),
      ('skip pre-open node check','transport.py',"need(stat.S_ISCHR(before.st_mode) and before.st_uid==0 and\n         (os.major(before.st_rdev),os.minor(before.st_rdev))==(195,255),'control node identity; refuse before open')",'pass'),
      ('skip version check','reader.py',"need(version==VERSION,'wrong NVIDIA version')",'pass'),
      ('suppress syscall error','transport.py','if result<0:','if False:'),
    ]
    with tempfile.TemporaryDirectory() as td:
        for i,(label,name,old,new) in enumerate(edits):
            root=Path(td)/str(i);root.mkdir()
            for n in ['protocol.py','transport.py','reader.py','test.py']:
                shutil.copyfile(HERE/n,root/n)
            s=(root/name).read_text();assert s.count(old)==1,(label,s.count(old));(root/name).write_text(s.replace(old,new))
            run=subprocess.run([sys.executable,'-B',str(root/'test.py'),'--fail-fast'],capture_output=True,text=True)
            assert run.returncode!=0,'SURVIVED '+label
            assert 'FAIL:' in run.stderr or ('ERROR: test_' in run.stderr and
               any(x in run.stderr for x in ['AssertionError:','protocol.Refused:'])),'not a behavioral kill '+label+'\n'+run.stderr[-1300:]
            print('CAUGHT '+label,flush=True)
    print(f'PASS all {len(edits)} safety mutations detected')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mutations',action='store_true');parser.add_argument('--fail-fast',action='store_true')
    args=parser.parse_args()
    if args.mutations:mutations()
    else:raise SystemExit(not unittest.TextTestRunner(verbosity=2,failfast=args.fail_fast).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
