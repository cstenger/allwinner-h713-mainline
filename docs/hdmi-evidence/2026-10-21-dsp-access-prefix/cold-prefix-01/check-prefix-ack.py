import json,sys
from pathlib import Path
n=int(sys.argv[1]);name=sys.argv[2]
base=Path('build/hdmi-dsp-access-audit-2026-10-21/cold-prefix-01')
s=(base/f'step-{n:02d}.txt').read_text();records=[];decoder=json.JSONDecoder()
while s.strip():
    s=s.lstrip();obj,end=decoder.raw_decode(s);records.append(obj);s=s[end:]
ack=records[-1]
assert ack['event']=='acknowledged',ack
r=ack['result']
assert r['completed']==n and r['attempted']==n and r['failed']=='N' and r['released']=='N',r
uart=(base/'bench-uart.log').read_text()
for tag in ('BEGIN','DONE'):
    marker=f'h713-dsp-access-audit: {tag} step={n} operation={name}'
    assert uart.count(marker)==1,(marker,'missing or duplicated')
print(f'PASS step={n} operation={name} completed={r["completed"]} value=0x{r["last_value"]:08x} next={r["next_operation"]}; UART BEGIN/DONE retained')
