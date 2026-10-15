"""Bounded test-only HPD owner; wait for SCP init before releasing DDC."""
import json,subprocess,sys,time
from pathlib import Path
module=Path('/sys/module/h713_scp_probe')
def run(argv,timeout=70):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 if p.returncode:raise RuntimeError('signal helper failed')
if sys.argv[1]=='start':
 run(['insmod','/tmp/h713-ddc-pins.ko','run=1'])
 run(['insmod','/tmp/h713-scp-probe.ko','run=1','edid_trial=1','stock_io=1','hold_ms=45000'])
 # Remain alive for ExecStop even after the bounded HPD pulse has restored.
 time.sleep(45)
elif sys.argv[1]=='stop':
 deadline=time.monotonic()+60
 while module.exists() and (module/'initstate').read_text().strip()!='live':
  if time.monotonic()>=deadline:raise RuntimeError('SCP still initializing; retain DDC holds')
  time.sleep(.1)
 if module.exists():
  status={name:(module/'parameters'/name).read_text().strip() for name in ('restored','peripheral_restored','edid_mismatch')}
  print(json.dumps({'signal_restore':status}),flush=True)
  if status!={'restored':'Y','peripheral_restored':'Y','edid_mismatch':'0'}:raise RuntimeError('SCP restoration not verified; retain holds')
  run(['rmmod','h713_scp_probe'])
 if Path('/sys/module/h713_ddc_pins').exists():run(['rmmod','h713_ddc_pins'])
 print('H713 signal helper restoration and removal verified',flush=True)
else:raise ValueError('unknown action')
