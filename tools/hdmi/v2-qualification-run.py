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
    ... --fel N --fel-images RESCUE UBOOT BL31 [--uart /dev/ttyUSB0]
                                      chain N boots through FEL: reboot fel, load the
                                      rescue SPL, BL31 and U-Boot over USB (RAM only)

    ... --logo-fel N --fel-images ...  N cycles of: GP6 HDOK->HDMI, warm reboot into a
                                      logo-only boot, dwell, GP6 HDMI->HDOK, then a FEL
                                      boot from that logo-only boot (the stalled boot's start)

A FEL step stops the chain, with no retry, if FEL never appears (the board is
then in FEL or booted another way and needs a look), if the loader fails, or
if the board comes back without having been loaded over FEL.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUAL = REPO / 'tools/hdmi/startup-qualification.py'
FEL_LOADER = REPO / 'tools/fel-uboot.sh'
BOARD_GUARD = REPO / 'tools/board-guard.py'
FEL_ID = '1f3a:efe8'
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


GP6 = r'''
import json, os, struct, sys
from pathlib import Path
boot, expect, new = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
def nvmem():
    rtc = Path('/sys/firmware/devicetree/base/soc/rtc@7090000')
    assert (rtc / 'compatible').read_bytes() == b'allwinner,sun50i-h713-rtc\0', 'wrong RTC'
    assert (rtc / 'reg').read_bytes() == bytes.fromhex('0709000000000400'), 'wrong RTC range'
    found = [p / 'nvmem' for p in Path('/sys/bus/nvmem/devices').iterdir()
             if (p / 'of_node').resolve() == rtc.resolve() and (p / 'nvmem').is_file()]
    assert len(found) == 1, 'RTC nvmem absent or ambiguous'
    return found[0]
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot, 'boot changed'
fd = os.open(nvmem(), os.O_RDWR | os.O_CLOEXEC)
try:
    before = os.pread(fd, 8, 0x18)
    gp6, gp7 = struct.unpack('<II', before)
    assert gp7 == 0, 'GP7 reboot-mode request pending'
    assert gp6 == expect, 'GP6 is %08x, expected %08x' % (gp6, expect)
    assert os.pwrite(fd, struct.pack('<I', new), 0x18) == 4, 'short write'
    after = os.pread(fd, 8, 0x18)
    assert after == struct.pack('<II', new, 0), 'readback mismatch %s' % after.hex()
finally:
    os.close(fd)
print(json.dumps({'boot_id': boot, 'gp6_before': '%08x' % gp6, 'gp6_after': '%08x' % new, 'gp7': '%08x' % gp7}))
'''
LOGO_STATE = r'''
import json, os, struct, subprocess
from pathlib import Path
rtc = Path('/sys/firmware/devicetree/base/soc/rtc@7090000')
nv = [p / 'nvmem' for p in Path('/sys/bus/nvmem/devices').iterdir()
      if (p / 'of_node').resolve() == rtc.resolve() and (p / 'nvmem').is_file()][0]
gp6, gp7 = struct.unpack('<II', nv.read_bytes()[0x18:0x20])
units = subprocess.run(['systemctl', 'is-active', 'h713-hdmi-prepare', 'h713-hdmi-capture', 'h713-hdmi-video'],
                       capture_output=True, text=True).stdout.split()
print(json.dumps({'boot_id': open('/proc/sys/kernel/random/boot_id').read().strip(),
                  'uptime': float(open('/proc/uptime').read().split()[0]),
                  'handoff': Path('/proc/device-tree/chosen/h713,hdmi-boot-v1').exists(),
                  'gp6': '%08x' % gp6, 'gp7': '%08x' % gp7, 'units': units,
                  'cmdline': open('/proc/cmdline').read().strip()}))
'''
HDMI_LATCH, HDOK = '48444d49', '48444f4b'


def set_gp6(args, boot, expect, new, path):
    out = ssh(args.known_hosts, 'python3', '-', boot, expect, new, stdin=GP6, timeout=30)
    path.write_text(out)
    return json.loads(out)


def logo_only_boot(args, label, boot):
    """GP6 HDOK -> HDMI, one guarded warm reboot, and proof that the new boot is logo-only."""
    directory = args.root / label
    directory.mkdir(exist_ok=False)
    set_gp6(args, boot, HDOK, HDMI_LATCH, directory / 'gp6-to-hdmi.json')
    stop = threading.Event()
    if args.uart:
        target = argparse.Namespace(uart=args.uart, log=args.root / f'{label}-serial.log')
        threading.Thread(target=uart_capture, args=(target, stop), daemon=True).start()
    script = ("from pathlib import Path\nimport subprocess\n"
              f"assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=={boot!r}\n"
              "subprocess.run(['sync'],check=True)\n"
              "subprocess.run(['systemctl','reboot','--no-block'],check=True)\nprint('requested')\n")
    try:
        ssh(args.known_hosts, 'python3', '-', stdin=script, timeout=20)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass  # the shutdown may close SSH first; never resend
    deadline = time.monotonic() + 180
    row = None
    while time.monotonic() < deadline:
        time.sleep(5)
        try:
            row = json.loads(ssh(args.known_hosts, 'python3', '-', stdin=LOGO_STATE, timeout=20))
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        if row['boot_id'] != boot:
            break
    else:
        sys.exit(f'{label}: no new boot within 180 s after the warm reboot; chain stopped')
    (directory / 'logo-state.json').write_text(json.dumps(row, indent=2) + '\n')
    stop.set()
    if row['handoff'] or row['gp6'] != HDMI_LATCH or row['gp7'] != '00000000':
        sys.exit(f'{label}: boot {row["boot_id"]} is not the expected logo-only boot ({row}); chain stopped')
    if any(u == 'active' for u in row['units']):
        sys.exit(f'{label}: HDMI units active on a logo-only boot ({row["units"]}); chain stopped')
    new = row['boot_id']
    # The stalled boot's predecessor had been up 161 s when it rebooted into FEL.
    while row['uptime'] < args.logo_dwell:
        time.sleep(min(10, args.logo_dwell - row['uptime']))
        row = json.loads(ssh(args.known_hosts, 'python3', '-', stdin=LOGO_STATE, timeout=20))
        if row['boot_id'] != new:
            sys.exit(f'{label}: logo-only boot changed during the dwell; chain stopped')
    words(args.known_hosts, directory, new)
    set_gp6(args, new, HDMI_LATCH, HDOK, directory / 'gp6-to-hdok.json')
    print(f'{label}: logo-only boot {new[:8]} up {row["uptime"]:.0f} s, GP6 HDMI -> HDOK', flush=True)
    return new


def fel_present():
    return subprocess.run(['lsusb', '-d', FEL_ID], capture_output=True).returncode == 0


def uart_capture(path, stop):
    """Passive serial log (never writes to the port) until stop is set."""
    sys.path.insert(0, str(REPO / 'tools/serial'))
    import console
    import os
    import select
    fd = console.open_port(path.uart)
    started = time.monotonic()
    with open(path.log, 'w') as out:
        try:
            while not stop.is_set():
                if select.select([fd], [], [], 0.25)[0]:
                    data = os.read(fd, 4096).decode('utf-8', 'replace')
                    out.write(''.join(f'{time.monotonic() - started:9.3f} {line}\n' if line else ''
                                      for line in data.replace('\r', '').split('\n')))
                    out.flush()
        finally:
            os.close(fd)


def fel_load(args, label, log):
    """Wait for the board in FEL, check its identity, then load U-Boot into RAM."""
    deadline = time.monotonic() + 90
    while not fel_present():
        if time.monotonic() > deadline:
            return 'FEL device never appeared within 90 s'
        time.sleep(0.5)
    log.write(f'FEL seen after reboot request\n')
    guard = subprocess.run([sys.executable, str(BOARD_GUARD), '--expect', 'hy200-qz713-v2', '--fel'],
                           capture_output=True, text=True, timeout=60)
    log.write(guard.stdout + guard.stderr)
    if guard.returncode:
        return f'board-guard refused (exit {guard.returncode})'
    rescue, uboot, bl31 = args.fel_images
    # TTY= : never send the autoboot-stopping keystrokes; U-Boot must boot Linux.
    load = subprocess.run([str(FEL_LOADER), str(rescue), str(uboot), str(bl31)], capture_output=True,
                          text=True, timeout=240, env={**os.environ, 'TTY': ''})
    log.write(load.stdout + load.stderr)
    if load.returncode or 'starting BL31' not in load.stdout:
        return f'FEL loader failed (exit {load.returncode})'
    return None


def step(args, action, label, boot, previous=None, from_logo_only=False):
    cmd = [sys.executable, str(QUAL), action, '--root', str(args.root), '--label', label,
           '--from-boot', boot, '--audit', str(args.audit), '--known-hosts', str(args.known_hosts)]
    if previous:
        cmd += ['--previous-boot', previous]
    if from_logo_only:
        cmd += ['--from-logo-only']
    if action != 'fel':
        proc = subprocess.run(cmd, capture_output=True, text=True)
    else:
        if fel_present():
            sys.exit(f'{label}: a FEL device is already on USB before the reboot; chain stopped')
        stop = threading.Event()
        uart = None
        if args.uart:
            target = argparse.Namespace(uart=args.uart, log=args.root / f'{label}-serial.log')
            uart = threading.Thread(target=uart_capture, args=(target, stop), daemon=True)
            uart.start()
        qual = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with open(args.root / f'{label}-fel.log', 'w') as log:
            problem = fel_load(args, label, log)
        if problem:
            qual.terminate()
            out, err = qual.communicate()
            (args.root / f'{label}.log').write_text(out + err)
            stop.set()
            sys.exit(f'{label}: {problem}; chain stopped, no retry. The board may be sitting in FEL '
                     f'or have booted without FEL: look before doing anything (see {label}-fel.log)')
        out, err = qual.communicate()
        stop.set()
        if uart:
            uart.join(timeout=5)
        proc = subprocess.CompletedProcess(cmd, qual.returncode, out, err)
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
    parser.add_argument('--fel', type=int, default=0, help='boots through FEL to chain')
    parser.add_argument('--fel-images', nargs=3, type=Path, metavar=('RESCUE', 'UBOOT', 'BL31'),
                        help='rescue SPL, U-Boot proper and BL31 for tools/fel-uboot.sh')
    parser.add_argument('--uart', help='serial port to log passively during FEL steps')
    parser.add_argument('--logo-fel', type=int, default=0, help='logo-only boot then FEL boot, N cycles')
    parser.add_argument('--logo-dwell', type=float, default=160, help='uptime of the logo-only boot before FEL')
    args = parser.parse_args()
    if args.cold is not None and not args.previous_boot:
        parser.error('--cold needs --previous-boot')
    if (args.fel or args.logo_fel) and not args.fel_images:
        parser.error('--fel/--logo-fel need --fel-images')
    args.root.mkdir(parents=True, exist_ok=True)
    if args.fel or args.logo_fel:
        for f in args.fel_images:
            if not f.is_file():
                parser.error(f'missing {f}')
        sums = subprocess.run(['sha256sum', *map(str, args.fel_images)], capture_output=True, text=True,
                              check=True).stdout
        with open(args.root / 'fel-images.sha256', 'a') as out:
            out.write(sums)
        print('fel images:\n' + sums.rstrip(), flush=True)
    boot = ssh(args.known_hosts, 'cat', '/proc/sys/kernel/random/boot_id').strip()
    if args.cold is not None:
        if boot == args.previous_boot:
            sys.exit('still on the previous boot: the board was not power-cycled')
        boot = step(args, 'collect', f'cold-{args.cold:02d}', boot, previous=args.previous_boot)
    if args.baseline:
        boot = step(args, 'collect', f'baseline-{boot[:8]}', boot)
    for n in range(args.first, args.first + args.warm):
        boot = step(args, 'warm', f'warm-{n:02d}', boot)
    for n in range(args.first, args.first + args.fel):
        boot = step(args, 'fel', f'fel-{n:02d}', boot)
    for n in range(args.first, args.first + args.logo_fel):
        boot = logo_only_boot(args, f'logo-{n:02d}', boot)
        boot = step(args, 'fel', f'fel-{n:02d}', boot, from_logo_only=True)
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
