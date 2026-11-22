#!/usr/bin/env python3
"""Chain V2 startup qualification runs, checking each boot for the green stall.

Wraps tools/hdmi/startup-qualification.py (one guarded step per run, never
retried) with the V2 audit from make-v2-runtime-audit.py. After every collect
it reads the AFBD stall signature (0x05600038/338/1cc/1fc, all 0 when healthy)
and the two open configuration words 0x050c0c94 and 0x05040814, so a run of
healthy boots also gives their baseline values. A stalled or failed boot ends
the chain and is left running for inspection: nothing reboots it.

    tools/hdmi/v2-qualification-run.py --root DIR --audit A --known-hosts K [--baseline] [--warm N]
    ... --cold N --previous-boot ID   collect a cold boot, with the shutdown of ID
    ... --poweroff                    request one guarded poweroff of the current boot
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUAL = REPO / 'tools/hdmi/startup-qualification.py'
WORDS = r'''
import json, mmap, os, struct
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
def rd(addr):
    m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=addr & ~0xfff)
    try: return '%08x' % struct.unpack('<I', m[addr & 0xfff:(addr & 0xfff) + 4])[0]
    finally: m.close()
afbd = {hex(a): rd(a) for a in (0x05600038, 0x05600338, 0x056001cc, 0x056001fc)}
other = {hex(a): rd(a) for a in (0x050c0c94, 0x05040814)}
print(json.dumps({'boot_id': open('/proc/sys/kernel/random/boot_id').read().strip(),
                  'afbd': afbd, 'stall': any(int(v, 16) for v in afbd.values()), 'other': other}))
'''


def ssh(known, *argv, stdin=None, timeout=60):
    return subprocess.run(['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'LogLevel=ERROR',
                           '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(known),
                           '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=2',
                           '-o', 'ServerAliveCountMax=2', 'root@192.168.4.1', *argv],
                          input=stdin, capture_output=True, text=True, timeout=timeout, check=True).stdout


def words(known, directory, boot):
    row = json.loads(ssh(known, 'python3', '-', stdin=WORDS))
    (directory / 'words.json').write_text(json.dumps(row, indent=2) + '\n')
    if row['boot_id'] != boot:
        sys.exit(f'boot changed before the stall check ({row["boot_id"]})')
    print(f'{directory.name}: afbd {" ".join(row["afbd"].values())} '
          f'c94 {row["other"]["0x50c0c94"]} 814 {row["other"]["0x5040814"]}'
          + ('  GREEN STALL' if row['stall'] else ''), flush=True)
    return row


def step(args, action, label, boot, previous=None):
    cmd = [sys.executable, str(QUAL), action, '--root', str(args.root), '--label', label,
           '--from-boot', boot, '--audit', str(args.audit), '--known-hosts', str(args.known_hosts)]
    if previous:
        cmd += ['--previous-boot', previous]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    (args.root / f'{label}.log').write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        sys.exit(f'{label}: FAILED (see {args.root / label}); chain stopped, no retry\n' + proc.stderr[-800:])
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    t = result['timing']
    if previous:
        print(f'{label}: preceding shutdown {result["preceding_shutdown"]}', flush=True)
    print(f'{label}: {result["status"]} boot {result["boot_id"][:8]} video {t["video_active"]:.2f} s '
          f'fps {result["stability"]["fps"]:.1f} readvertised {t["readvertised"]}', flush=True)
    if words(args.known_hosts, args.root / label, result['boot_id'])['stall']:
        sys.exit(f'{label}: green stall; board left on boot {result["boot_id"]} for inspection')
    return result['boot_id']


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--known-hosts', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true', help='collect the current boot first')
    parser.add_argument('--warm', type=int, default=0, help='guarded warm reboots to chain')
    parser.add_argument('--first', type=int, default=1, help='number of the first warm run label')
    parser.add_argument('--cold', type=int, help='collect the current boot as cold run N')
    parser.add_argument('--previous-boot', help='boot whose shutdown preceded the cold boot')
    parser.add_argument('--poweroff', action='store_true', help='request one guarded poweroff, then stop')
    args = parser.parse_args()
    if args.cold is not None and not args.previous_boot:
        parser.error('--cold needs --previous-boot')
    args.root.mkdir(parents=True, exist_ok=True)
    boot = ssh(args.known_hosts, 'cat', '/proc/sys/kernel/random/boot_id').strip()
    if args.cold is not None:
        if boot == args.previous_boot:
            sys.exit('still on the previous boot: the board was not power-cycled')
        boot = step(args, 'collect', f'cold-{args.cold:02d}', boot, previous=args.previous_boot)
    if args.baseline:
        boot = step(args, 'collect', f'baseline-{boot[:8]}', boot)
    for n in range(args.first, args.first + args.warm):
        boot = step(args, 'warm', f'warm-{n:02d}', boot)
    if args.poweroff:
        script = ("from pathlib import Path\nimport subprocess\n"
                  f"assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=={boot!r}\n"
                  "subprocess.run(['sync'],check=True)\n"
                  "subprocess.run(['systemctl','poweroff','--no-block'],check=True)\nprint('requested')\n")
        try:
            ssh(args.known_hosts, 'python3', '-', stdin=script, timeout=20)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass  # the shutdown may close SSH first; never resend
        print(f'poweroff requested once for boot {boot}', flush=True)
        return
    print('chain complete', flush=True)


if __name__ == '__main__':
    main()
