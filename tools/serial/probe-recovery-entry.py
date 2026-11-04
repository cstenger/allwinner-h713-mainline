#!/usr/bin/env python3
"""Probe sealed rollback aliases/getvars from a held rescue prompt; never flash."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time

spec=importlib.util.spec_from_file_location('controller',Path(__file__).with_name('install-production-packet.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def plan(packet):
    phases=packet['phases']['rollback']
    c.need(tuple(x['role'] for x in phases)==c.ORDER,'wrong role order')
    for phase in phases:
        role=phase['role'];alias='h713pkt_'+role
        expected=['mmc dev 1 0','setenv fastboot_partition_alias_'+alias,
                  f"setenv fastboot_raw_partition_{alias} 0x{phase['start_lba']:x} 0x{phase['sectors']:x} mmcpart 0",
                  'printenv fastboot_raw_partition_'+alias,'run fastboot_mode']
        c.need(phase['uart_setup']==expected,'unexpected RAM setup command')
        expected_keys=['serialno','is-userspace','max-download-size','has-slot:'+alias,'partition-size:'+alias]
        c.need([g['argv'] for g in phase['host_gates']]==[['fastboot','-s',packet['usb_serial'],'getvar',key] for key in expected_keys],'non-getvar command in probe')
    return phases


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--packet',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--port');ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    root=a.packet.resolve();packet=json.loads((root/'packet.json').read_text())
    c.p.validate_structure(packet,root);phases=plan(packet)
    c.need(c.p.sha(root/'packet.json')=='c2491f0f7a84ff14221d5ad35122895adf69259acecf5bf41656f23407894390','packet changed')
    tool=json.loads((root/'HOST-TOOLS.json').read_text())['fastboot']
    c.need(shutil.which('fastboot')==tool['path'] and c.p.sha(Path(tool['path']))==tool['sha256'],'fastboot executable mismatch')
    c.need(subprocess.check_output([tool['path'],'--version'],text=True).splitlines()[0]==tool['version'],'fastboot version mismatch')
    if not a.execute:
        print(json.dumps({'status':'PASS probe-only plan','getvar_commands':sum(len(p['host_gates']) for p in phases),'storage_write_commands':0}));return
    c.need(a.port is not None,'explicit UART required');a.output.mkdir(mode=0o700,exist_ok=False)
    c.RUN_PACKET=root;uart=None;result={'status':'IN PROGRESS','storage_writes':False,'gates_verified':0,'packet_sha256':c.p.sha(root/'packet.json')}
    c.atomic_json(a.output/'RESULT.json',result)
    try:
        uart=c.UART(a.port,a.output)
        c.need(uart.command('echo H713_RESCUE_PROBE')=='H713_RESCUE_PROBE','sync mismatch')
        version=uart.command('version');c.version_gate(root,'rollback',version)
        c.need('U-Boot 2026.07-rc5-ga1358432003c-dirty' in version,'not the pinned rescue proper')
        c.need('PB5: output: 1' in uart.command('gpio status PB5'),'fan not high')
        c.need(uart.command('printenv serial#')=='serial#='+packet['usb_serial'],'serial mismatch')
        for phase in phases:
            for cmd in phase['uart_setup'][:-1]:
                reply=uart.command(cmd)
                if cmd=='mmc dev 1 0':c.need(reply=='switch to partitions #0, OK\nmmc1(part 0) is current device','wrong MMC device')
                elif cmd.startswith('printenv '):c.need(reply==cmd[9:]+'='+phase['uart_setup'][2].split(' ',2)[2],'raw alias mismatch')
                else:c.need(reply=='','unexpected RAM setenv reply')
        uart.send('run fastboot_mode');result['usb_node']=c.wait_fastboot_usb(packet['usb_serial'])
        end=time.monotonic()+3
        while time.monotonic()<end:uart.poll(.1)
        for phase in phases:
            for i,gate in enumerate(phase['host_gates']):
                reply=c.run_fastboot(gate['argv'],uart,a.output,phase['role']+'-getvar-'+str(i),15)
                c.check_getvar(reply,gate['argv'][-1],gate['value']);result['gates_verified']+=1
                c.atomic_json(a.output/'RESULT.json',result)
        c.run_fastboot(['fastboot','-s',packet['usb_serial'],'continue'],uart,a.output,'continue',15)
        c.need(uart.prompt(15).replace(b'\r',b'').startswith(b'run fastboot_mode\n'),'return lifecycle mismatch')
        for role in c.ORDER:
            for name in ('fastboot_raw_partition_h713pkt_','fastboot_partition_alias_h713pkt_'):
                c.need(uart.command('setenv '+name+role)=='','RAM alias cleanup mismatch')
        c.need('PB5: output: 1' in uart.command('gpio status PB5'),'fan not high on return')
        result['status']='PASS rescue UART, RAM aliases and all USB getvar gates; no storage writes'
    except BaseException as e:
        result.update(status='FAILED; STOP; NO RETRY',error=str(e));raise
    finally:
        c.atomic_json(a.output/'RESULT.json',result)
        if uart:uart.close()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
