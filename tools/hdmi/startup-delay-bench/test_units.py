#!/usr/bin/env python3
"""Parse both sample overrides using an isolated systemd root; never starts units."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def check(package):
    results=[]
    with tempfile.TemporaryDirectory(prefix='h713-unit-offline-') as temp:
        root=Path(temp)
        units=root/'etc/systemd/system';units.mkdir(parents=True)
        (units/'h713-hdmi-signal.service').write_bytes((package/'production-signal.service').read_bytes())
        (units/'h713-hdmi-capture.service').write_text('[Service]\nType=oneshot\nExecStart=/usr/bin/python3\nRemainAfterExit=yes\n')
        for target in ('sysinit','basic','shutdown','multi-user'):
            (units/f'{target}.target').write_text('[Unit]\nDescription=Offline fixture\n')
        executable=root/'usr/bin/python3';executable.parent.mkdir(parents=True)
        executable.write_text('# offline verification placeholder, never executed\n');executable.chmod(0o755)
        dropins=units/'h713-hdmi-signal.service.d';dropins.mkdir()
        before=(package/'production-signal.service').read_text()
        assert 'Restart=no\n' in before and 'TimeoutStartSec=30\n' in before
        for delay in (0,2000):
            text=(package/f'delay-{delay}.conf').read_text()
            directives=[line for line in text.splitlines() if line and not line.startswith(('#','['))]
            assert len(directives)==2 and directives[0]=='ExecStart='
            assert directives[1].startswith('ExecStart=/usr/bin/python3 ')
            assert f'--bench-delay-ms={delay} ' in directives[1]
            (dropins/'90-start-delay.conf').write_text(text)
            run=subprocess.run(['systemd-analyze',f'--root={root}','--generators=no',
                '--man=no','verify','h713-hdmi-signal.service'],capture_output=True,text=True,timeout=15)
            results.append({'delay_ms':delay,'returncode':run.returncode,
                            'stdout':run.stdout,'stderr':run.stderr,
                            'only_execstart_overridden':True})
    print(json.dumps({'schema':'h713-delay-unit-check-v1','results':results},indent=2))
    if any(result['returncode'] for result in results):raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    check(parser.parse_args().package)
