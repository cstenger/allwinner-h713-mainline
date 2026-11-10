"""Run the exact SSH peer program against fake files, memfd and native C model.

No actual SSH, module load, sysfs, device file or board access occurs. The peer
executes on a thread with per-exec import substitution, not global patches.
"""
import builtins
import copy
import hashlib
import json
import mmap
import os
from pathlib import Path
import stat
import threading
from types import SimpleNamespace


class Peer:
    def __init__(self,capture,model,library,packet,root,stall=None):
        self.capture=capture;self.model=model;self.root=Path(root);self.packet=Path(packet)
        self.cpu=model.CPU(packet);self.cpu.stall_at=stall;self.tx=model.Transaction(library,self.cpu)
        self.manifest=copy.deepcopy(self.cpu.m)
        self.virtual=self.root/'virtual';self.virtual.mkdir()
        self.remote_done=threading.Event();self.cleanup=threading.Event()
        self.rc=None;self.errors=[];self.commands=[];self.param_writes=[];self.device_reads=[]
        self.sram=self.root/'fake-sram'
        with self.sram.open('wb') as f:f.seek(0x100000);f.write(self.cpu.mem)
        def file(path,data):
            p=self.virtual/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p
        owner=b'fake owner';notes=b'fake kernel notes';owner_note=b'fake owner note'
        ident=self.manifest['identity']
        ident['owner_sha256']=hashlib.sha256(owner).hexdigest()
        ident['kernel_notes_sha256']=hashlib.sha256(notes).hexdigest()
        ident['owner_note_sha256']=hashlib.sha256(owner_note).hexdigest()
        file('/proc/device-tree/model',b'HY200 QZ713DF_A1 (Allwinner H713)\0')
        file('/proc/sys/kernel/random/boot_id',(ident['boot_id']+'\n').encode())
        file('/sys/kernel/notes',notes)
        file('/sys/module/h713_hdmi_signal/notes/.note.gnu.build-id',owner_note)
        file('/usr/lib/h713-hdmi/h713-hdmi-signal.ko',owner)
        file('/sys/devices/platform/h713-hdmi-ring/signal',b'none\n')
        self.pins={}
        for i in range(56):
            path=f'/fake/pin-{i}';p=file(path,f'pin{i}'.encode());s=p.stat()
            self.pins[path]=dict(bytes=s.st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                 mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
        for module,name,value in [('h713_hdmi_receiver','clock_count','4'),('h713_hdmi_receiver','edid_ready','Y'),
            ('h713_hdmi_receiver','init_error','0'),('h713_hdmi_receiver','firmware_pin','Y'),
            ('h713_hdmi_signal','ready','Y'),('h713_hdmi_signal','failed','N'),('h713_hdmi_signal','restored','N')]:
            file('/sys/module/'+module+'/parameters/'+name,(value+'\n').encode())
        self.client_packet=self.root/'client-packet';self.client_packet.mkdir()
        for name in ['baseline-sram.bin','fragment-a.bin','fragment-b.bin']:
            (self.client_packet/name).write_bytes((self.packet/name).read_bytes())
        (self.client_packet/'h713-scp-sampler-v2.ko').write_bytes(b'fake transferred module; NEVER loaded')
        self.file=file

    def popen(self,args,**kwargs):
        if args[0]!='ssh' or 'root@192.168.4.1' not in args:raise AssertionError('unexpected process')
        # All child interfaces are pipes; this object satisfies the host driver.
        child_in,parent_in=os.pipe();parent_out,child_out=os.pipe()
        self.stdin=os.fdopen(parent_in,'wb',buffering=0);self.stdout=os.fdopen(parent_out,'rb',buffering=0)
        self.peer_in=os.fdopen(child_in,'r');self.peer_out=os.fdopen(child_out,'w',buffering=1)
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
        return self

    def run(self):
        peer=self
        class FakePath:
            def __init__(self,p):self.path=p.path if isinstance(p,FakePath) else str(p)
            def __truediv__(self,p):return FakePath(self.path+'/'+str(p))
            def real(self):return peer.virtual/self.path.lstrip('/')
            def exists(self):return self.real().exists()
            def read_bytes(self):return self.real().read_bytes()
            def read_text(self):return self.real().read_text()
            def stat(self):return self.real().stat()
            def write_text(self,value):
                if self.path!='/sys/module/h713_scp_sampler_v2/parameters/capture':raise AssertionError('unexpected target write '+self.path)
                if value!=hex(peer.manifest['nonce'])+'\n':raise AssertionError('bad capture request')
                peer.param_writes.append((self.path,value))
                rc=peer.tx.run()
                with peer.sram.open('r+b') as f:f.seek(0x100000);f.write(peer.cpu.mem)
                base='/sys/module/h713_scp_sampler_v2/parameters/'
                for name,val in [('status',peer.tx.receipt.phase),('reason',peer.tx.receipt.reason),
                                 ('bootstrap_sr',peer.tx.receipt.bootstrap_sr),('original_r13',peer.tx.receipt.original_r13)]:
                    peer.file(base+name,(str(val)+'\n').encode())
                if rc==0:
                    frame=[peer.manifest['nonce'],8,0,peer.tx.receipt.sr,*peer.tx.receipt.values]
                    peer.file(base+'result',(' '.join(str(n) for n in frame)+'\n').encode())
                return len(value)
        def fake_open(path,flags,*args,**kwargs):
            if path!='/dev/mem' or flags&os.O_ACCMODE!=os.O_RDONLY:raise AssertionError('unexpected device operation')
            peer.device_reads.append((path,flags));return os.open(peer.sram,flags)
        def fake_run(args,**kwargs):
            if args[0]!='insmod' or not args[1].startswith('/proc/self/fd/'):raise AssertionError('unexpected command '+str(args))
            peer.commands.append(args)
            fd=int(args[1].rsplit('/',1)[1]);data=os.pread(fd,1000000,0)
            if data!=(peer.client_packet/'h713-scp-sampler-v2.ko').read_bytes():raise AssertionError('memfd contents changed')
            peer.file('/sys/module/h713_scp_sampler_v2/parameters/status',b'0\n')
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        fake_os=SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
        fake_os.open=fake_open
        modules={'pathlib':SimpleNamespace(Path=FakePath),'os':fake_os,'mmap':mmap,
                 'subprocess':SimpleNamespace(run=fake_run),
                 'sys':SimpleNamespace(stdin=self.peer_in,stdout=self.peer_out)}
        original_import=builtins.__import__
        def imported(name,*args,**kwargs):return modules[name] if name in modules else original_import(name,*args,**kwargs)
        custom=dict(vars(builtins));custom['__import__']=imported
        custom['print']=lambda *args,**kwargs:builtins.print(*args,**dict(kwargs,file=self.peer_out))
        try:
            exec(compile(self.capture.REMOTE,'<fake SSH peer>','exec'),{'__builtins__':custom})
            self.rc=0
        except BaseException as e:
            self.errors.append(e);self.rc=1
        finally:
            self.peer_out.close();self.remote_done.set()
            # Preserve the fake owner mutex until assertions complete. This
            # harness-only cleanup has NO corresponding production RPC.
            self.cleanup.wait(5);self.tx.cleanup();self.peer_in.close()

    def poll(self):return self.rc if self.remote_done.is_set() else None
    def wait(self,timeout=None):
        if not self.remote_done.wait(timeout):raise TimeoutError('fake peer did not finish')
        return self.rc
    def terminate(self):self.terminated=True  # SSH loss does not release the fake kernel owner
    def close(self):
        self.cleanup.set()
        if hasattr(self,'stdin'):self.stdin.close()
        if hasattr(self,'thread'):self.thread.join(2)
        if hasattr(self,'stdout'):self.stdout.close()
