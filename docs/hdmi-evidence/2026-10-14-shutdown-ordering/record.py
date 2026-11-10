import json,subprocess,sys
from pathlib import Path
state=subprocess.run(['systemctl','is-active','user@1000.service'],capture_output=True,text=True,check=False).stdout.strip()
with Path('/tmp/h713-shutdown-ordering/events.jsonl').open('a') as stream:
 stream.write(json.dumps({'event':sys.argv[1],'user_manager':state})+'\n')
