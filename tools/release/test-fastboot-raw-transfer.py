#!/usr/bin/env python3
"""Exercise the real fastboot binary against localhost memory, never USB."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import unittest

spec=importlib.util.spec_from_file_location('packet',Path(__file__).with_name('prepare-install.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


class FastbootTransfer(unittest.TestCase):
    @unittest.skipUnless(shutil.which('fastboot'),'fastboot required')
    def test_real_client_resparse_writes_all_blocks_including_zero(self):
        size=40*1024*1024;block=4096
        original=bytearray(size)
        for i in range(size//block):original[i*block:(i+1)*block]=bytes([i%251])*block
        target=bytearray(b'\xa5')*size;coverage=bytearray(size//block)
        errors=[];commands=[];downloads=[]
        def exact(c,n):
            out=bytearray()
            while len(out)<n:
                b=c.recv(n-len(out))
                if not b:raise EOFError()
                out.extend(b)
            return bytes(out)
        def packet(c):return exact(c,struct.unpack('>Q',exact(c,8))[0])
        def send(c,data):c.sendall(struct.pack('>Q',len(data))+data)
        def apply(data):
            magic,major,minor,fh,ch,bs,total,chunks,crc=struct.unpack_from('<I4H4I',data)
            assert (magic,major,bs,total)==(0xed26ff3a,1,block,size//block)
            offset=fh;position=0
            for _ in range(chunks):
                typ,_,blocks,total_size=struct.unpack_from('<2H2I',data,offset)
                payload=data[offset+ch:offset+total_size]
                lo,hi=position*block,(position+blocks)*block
                if typ in (0xcac1,0xcac2):
                    piece=payload if typ==0xcac1 else payload*(blocks*block//4)
                    assert len(piece)==hi-lo and hi<=size
                    target[lo:hi]=piece
                    for i in range(position,position+blocks):coverage[i]+=1
                else:assert typ in (0xcac3,0xcac4)
                if typ!=0xcac4:position+=blocks
                offset+=total_size
            assert position==size//block and offset==len(data)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'raw';source.write_bytes(original)
            p.all_raw_sparse(source,root/'all-raw.simg')
            server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1);server.settimeout(20)
            port=server.getsockname()[1]
            def run():
                try:
                    c,_=server.accept()
                    with c:
                        c.settimeout(20);assert exact(c,4)==b'FB01';c.sendall(b'FB01');data=None
                        while True:
                            try:cmd=packet(c).decode()
                            except EOFError:break
                            commands.append(cmd)
                            if cmd.startswith('getvar:'):
                                v=cmd[7:]
                                values={'version':'0.4','max-download-size':'0x02000000','is-userspace':'no',
                                        'has-slot:h713pkt_root':'no','partition-size:h713pkt_root':hex(size)}
                                send(c,('OKAY'+values[v]).encode() if v in values else b'FAILUnknown variable')
                            elif cmd.startswith('download:'):
                                n=int(cmd[9:],16);assert n<=16*1024*1024
                                send(c,('DATA'+cmd[9:]).encode());data=bytearray()
                                while len(data)<n:data.extend(packet(c))
                                assert len(data)==n;downloads.append(n);send(c,b'OKAY')
                            elif cmd=='flash:h713pkt_root':
                                assert data is not None;apply(data);data=None;send(c,b'OKAY')
                            else:raise AssertionError('unexpected command '+cmd)
                except BaseException as e:errors.append(e)
                finally:server.close()
            thread=threading.Thread(target=run,daemon=True);thread.start()
            client=subprocess.run(['fastboot','-s','tcp:127.0.0.1:'+str(port),'-S','16M',
                                   'flash','h713pkt_root',str(root/'all-raw.simg')],capture_output=True,text=True,timeout=30)
            thread.join(2)
            self.assertFalse(thread.is_alive(),'mock server did not finish')
            self.assertFalse(errors,repr(errors));self.assertEqual(client.returncode,0,client.stderr)
            self.assertGreaterEqual(len(downloads),3)
            self.assertTrue(all(n==1 for n in coverage),'at least one target block was skipped or written twice')
            self.assertEqual(hashlib.sha256(target).digest(),hashlib.sha256(original).digest())
            print('PASS real fastboot: '+str(len(downloads))+' downloads, '+str(size//block)+
                  ' blocks each written once; zeros preserved; localhost memory only')

if __name__=='__main__':unittest.main()
