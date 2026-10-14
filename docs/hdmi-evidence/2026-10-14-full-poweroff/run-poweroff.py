"""One authorized poweroff, bounded serial observation; no serial writes/reboot."""
import importlib.util,json,os,re,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('console',root/'tools/serial/console.py')
console=importlib.util.module_from_spec(spec);spec.loader.exec_module(console)
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=2','root@192.168.4.1']
assert not (out/'poweroff-attempted').exists(),'Never repeat this poweroff automatically'
fd=console.open_port('auto')
started=time.monotonic();chunks=[];down_at=None
try:
 (out/'poweroff-attempted').write_text('One systemctl poweroff request; no force/reboot/retry.\n')
 request=subprocess.Popen(ssh+['systemctl poweroff'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 print('Poweroff requested; bounded serial observation started.',flush=True)
 with (out/'serial-poweroff.log').open('wb') as stream:
  while time.monotonic()-started < 105:
   try:data=os.read(fd,8192)
   except BlockingIOError:data=b''
   if data:
    stream.write(data);stream.flush();chunks.append(data)
    if down_at is None and b'reboot: Power down' in b''.join(chunks):
     down_at=time.monotonic();print('Serial reached reboot: Power down; watching for 90 seconds.',flush=True)
   if down_at is not None and time.monotonic()-down_at>=90:break
   time.sleep(.05)
  elapsed=time.monotonic()-started
 try:stdout,stderr=request.communicate(timeout=1)
 except subprocess.TimeoutExpired:
  request.terminate();stdout,stderr=request.communicate(timeout=3)
 (out/'ssh-poweroff.log').write_bytes(stdout+stderr)
 text=b''.join(chunks).decode(errors='replace')
 after=text.split('reboot: Power down',1)[1] if down_at is not None else ''
 reboot=bool(re.search(r'U-Boot|Starting kernel|Booting Linux|Linux version',after))
 result={'powerdown_seen':down_at is not None,'ssh_returncode':request.returncode,'serial_observation_seconds':elapsed,'seconds_after_powerdown':None if down_at is None else time.monotonic()-down_at,'unexpected_reboot_seen':reboot,'lamp_fan_operator_confirmation_pending':True,'started_with_mips_parked':True,'full_live_capture_poweroff_transaction_tested':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)
 assert down_at is not None and not reboot
finally:os.close(fd)
