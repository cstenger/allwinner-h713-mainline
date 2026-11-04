#!/usr/bin/env python3
import copy,hashlib,importlib.util,json,os,pty,select,subprocess,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('live',Path(__file__).with_name('install-production-packet.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ExecutionTests(unittest.TestCase):
    def test_mmc_echo_status_and_count(self):
        good='MMC read: dev # 1, block # 5555200, count 32768 ... 32768 blocks read: OK'
        m.check_read(good,5555200,32768);m.check_read(good.replace(' ... ',' ...\n'),5555200,32768)
        for bad in [good.replace('dev # 1','dev # 0'),good.replace('5555200','5555201'),good.replace('32768 blocks','1 blocks'),good.replace('OK','ERROR'),good+'\nunexpected']:
            with self.subTest(reply=bad),self.assertRaises(RuntimeError):m.check_read(bad,5555200,32768)
    def test_real_crc_format_and_wrong_range(self):
        text='crc32 for 50000000 ... 50ffffff ==> aab2c76f'
        m.check_crc(text,0x50000000,0x1000000,'aab2c76f')
        for bad in [text.replace('50000000','50000001'),text.replace('50ffffff','51000000'),text.replace('aab2c76f','00000000')]:
            with self.assertRaises(RuntimeError):m.check_crc(bad,0x50000000,0x1000000,'aab2c76f')
    def test_echo_and_getvar_fail_closed(self):
        self.assertEqual(m.body(b'printenv serial#\r\nserial#=fixture\r\n=> ','printenv serial#'),'serial#=fixture')
        for reply in [b'wrong\r\n=> ',b'printenv serial#\r\nfixture',b'printenv serial#\r\n=> unexpected']:
            with self.assertRaises(RuntimeError):m.body(reply,'printenv serial#')
        m.check_getvar('partition-size:x: 0x80000000\nFinished.\n','partition-size:x','0x0000000080000000')
        for text in ['has-slot:x: yes\n','has-slot:x: no\nhas-slot:x: no\n','FAILED (remote)']:
            with self.assertRaises(RuntimeError):m.check_getvar(text,'has-slot:x','no')
    def test_real_pty_fragmented_command_and_no_extra_sender(self):
        with tempfile.TemporaryDirectory() as d:
            master,slave=pty.openpty();port=os.ttyname(slave);os.close(slave)
            stop=threading.Event();seen=[];errors=[]
            def peer():
                pending=b''
                try:
                    while not stop.is_set():
                        if not select.select([master],[],[],.02)[0]:continue
                        try:data=os.read(master,1024)
                        except OSError:continue
                        pending+=data
                        while b'\r' in pending:
                            cmd,pending=pending.split(b'\r',1);seen.append(cmd)
                            response=(b'\r\nREPEATED LAST COMMAND\r\n=> ' if not cmd else cmd+b'\r\n'+(cmd[5:] if cmd.startswith(b'echo ') else b'reply')+b'\r\n=> ')
                            for i in range(0,len(response),3):os.write(master,response[i:i+3]);time.sleep(.001)
                except BaseException as e:errors.append(e)
            thread=threading.Thread(target=peer,daemon=True);thread.start();uart=None
            try:
                owner=subprocess.CompletedProcess(['fuser',port],0,stdout=str(os.getpid()).encode(),stderr=b'')
                with patch.object(m.subprocess,'run',return_value=owner):uart=m.UART(port,Path(d))
                self.assertEqual(uart.command('echo H713_PACKET_SYNC'),'H713_PACKET_SYNC')
                self.assertEqual(uart.command('version'),'reply')
                self.assertEqual(seen,[b'echo H713_PACKET_SYNC',b'version'])
            finally:
                stop.set()
                if uart:uart.close()
                thread.join(2);os.close(master)
            self.assertFalse(errors,repr(errors))
    def test_bare_gadget_return_prompt(self):
        uart=object.__new__(m.UART);uart.buffer=b'=> ';uart.poll=lambda *a:None
        self.assertEqual(uart.prompt(.1),b'=> ')

    def test_ambiguous_flash_records_intent_and_never_retries(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);packet=root/'packet';packet.mkdir();run=root/'run';run.mkdir();tool=root/'fastboot';tool.write_bytes(b'fixture')
            serial='0123456789abcdef'
            phase={'role':'root','sha256':'fixture','uart_setup':['mmc dev 1 0','setenv fastboot_partition_alias_h713pkt_root','setenv fastboot_raw_partition_h713pkt_root 0x54c400 0x400000 mmcpart 0','printenv fastboot_raw_partition_h713pkt_root','run fastboot_mode'],
                   'host_gates':[],'host_flash':['fastboot','flash','fixture'],'host_return':['fastboot','continue'],'uart_checkpoint':[]}
            data={'usb_serial':serial,'baseline_sha256':'baseline','phases':{'install':[phase]}}
            (packet/'packet.json').write_text(json.dumps(data));sha=m.p.sha(packet/'packet.json')
            (packet/'HOST-TOOLS.json').write_text(json.dumps({'fastboot':{'path':str(tool),'sha256':m.p.sha(tool),'version':'fixture'}}))
            receipt=root/'receipt.json';receipt.write_text(json.dumps({'packet_sha256':sha,'host_boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'status':'PASS read-only device verification','mode':'baseline','compared_sha256':'baseline'}))
            class FakeUART:
                def __init__(self,*args):pass
                def send(self,c):assert c,'blank Enter would repeat last U-Boot command'
                def prompt(self,*args):return b'\r\n=> '
                def note(self,**args):pass
                def close(self):pass
                def poll(self,*args):time.sleep(.01)
                def command(self,c):
                    return {'echo H713_PACKET_SYNC':'H713_PACKET_SYNC','version':m.BANNER,'gpio status PB5':'Bank PB:\nPB5: output: 1 [ ]','printenv serial#':'serial#='+serial,'mmc dev 1 0':'switch to partitions #0, OK\nmmc1(part 0) is current device','printenv fastboot_raw_partition_h713pkt_root':'fastboot_raw_partition_h713pkt_root=0x54c400 0x400000 mmcpart 0'}.get(c,'')
            calls=[]
            def interrupted(argv,uart,output,name,timeout):
                calls.append(name);state=json.loads((output/'RESULT.json').read_text());self.assertTrue(state['flash_intent']);raise RuntimeError('simulated USB interruption')
            with patch.object(m.p,'validate_structure'),patch.object(m.p,'ledger',return_value={'packet.json':sha}),patch.object(m.subprocess,'check_output',return_value='fixture\n'),patch.object(m,'UART',FakeUART),patch.object(m,'wait_fastboot_usb',return_value='fixture USB'),patch.object(m.os,'access',return_value=True),patch.object(m,'run_fastboot',side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError,'simulated USB'):m.execute(packet,'install','root',receipt,run,'fixture')
                with self.assertRaises(FileExistsError):m.execute(packet,'install','root',receipt,run,'fixture')
            self.assertEqual(calls,['flash']);state=json.loads((run/'phase-install-root/RESULT.json').read_text())
            self.assertEqual(state['status'],'FAILED; STOP; NO RETRY');self.assertTrue(state['flash_intent']);self.assertFalse(state['flash_completed'])

if __name__=='__main__':unittest.main()
