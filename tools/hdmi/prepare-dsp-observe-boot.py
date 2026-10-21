#!/usr/bin/env python3
"""Prepare a pinned, cold-only, logo-free RAM boot. Never install or boot it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zlib

FIT_SHA = '0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70'
DTB_SHA = '4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940'
DISABLED = ('/soc/display@5600000', '/soc/cpu-comm@3003000')
PPU = '/soc/power-controller@7001014'
# v2 (boot-v4) also drops the TVCAP retention flag, so genpd's TVCAP state
# comes from hardware. MIPS never runs in this boot, which is the only reason
# the flag exists; production DTs keep it.
KEEP_TVCAP = 'allwinner,keep-tvcap-on'
MARKER_V2 = '44535032'


def prepare(fit, dumpimage, output, variant='v1'):
    if variant not in ('v1', 'v2'):raise ValueError('Unknown variant')
    data = fit.read_bytes()
    if len(data) != 7795668 or hashlib.sha256(data).hexdigest() != FIT_SHA:
        raise ValueError('Refusing unpinned kernel FIT')
    output.mkdir(parents=True, exist_ok=False)
    original = output / 'original.dtb'
    subprocess.run([str(dumpimage), '-T', 'flat_dt', '-p', '1', '-o', str(original), str(fit)],
                   check=True, capture_output=True)
    if len(original.read_bytes()) != 34666 or hashlib.sha256(original.read_bytes()).hexdigest() != DTB_SHA:
        raise ValueError('Unexpected FIT device tree')
    for node in DISABLED:
        subprocess.run(['fdtget', '-l', str(original), node], check=True, capture_output=True)
    # Produce an offline reference for the RAM-only DT changes.
    reference = output / 'logo-free-reference.dtb'
    reference.write_bytes(original.read_bytes())
    for node in DISABLED:
        subprocess.run(['fdtput', '-t', 's', str(reference), node, 'status', 'disabled'], check=True)
    subprocess.run(['fdtput', '-t', 'x', str(reference), '/chosen', 'h713,dsp-observation-v1', '44535031'], check=True)
    if variant == 'v2':
        subprocess.run(['fdtget', str(original), PPU, KEEP_TVCAP], check=True, capture_output=True)
        subprocess.run(['fdtput', '-d', str(reference), PPU, KEEP_TVCAP], check=True)
        if subprocess.run(['fdtget', str(reference), PPU, KEEP_TVCAP], capture_output=True).returncode == 0:
            raise ValueError('TVCAP retention flag survived removal')
        subprocess.run(['fdtput', '-t', 'x', str(reference), '/chosen', 'h713,dsp-observation-v2', MARKER_V2], check=True)
    stale = subprocess.run(['fdtget', str(original), '/chosen', 'h713,hdmi-boot-v1'], capture_output=True)
    if stale.returncode != 1:raise ValueError('Unexpected handoff or DT query result')
    commands = [
        'itest.l *0x07090118 == 0',  # A physical cold budget only.
        'itest.l *0x0306101c == 0', 'itest.l *0x07000400 == 0',
        'fatload mmc 1:2 0x50000000 h713-kernel.fit', 'itest ${filesize} == 76f3d4',
        'crc32 0x50000000 ${filesize} 0x4efff000',
        # crc32_wd_buf stores htonl(crc), while itest.l reads a native LE word.
        f'itest.l *0x4efff000 == {int.from_bytes(zlib.crc32(data).to_bytes(4, "big"), "little"):08x}',
        'fdt addr 0x50000000', 'fdt get size dsp_fdt_size /images/fdt-1 data',
        'itest ${dsp_fdt_size} == 876a', 'fdt get addr dsp_fdt /images/fdt-1 data',
        'cp.b ${dsp_fdt} 0x4f000000 ${dsp_fdt_size}', 'fdt addr 0x4f000000', 'fdt resize 0x1000',
    ]
    # Keep numeric pins generated from the verified artifact, not transcribed.
    commands[4] = f'itest ${{filesize}} == {len(data):x}'
    commands += ['fdt set ' + node + ' status disabled' for node in DISABLED]
    commands += ['fdt set /chosen h713,dsp-observation-v1 <0x44535031>']
    if variant == 'v2':
        # fdt rm fails (stopping the runner) unless the flag was present and removed;
        # Linux-side tools then verify absence in the DT the kernel actually booted.
        commands += ['fdt rm ' + PPU + ' ' + KEEP_TVCAP,
                     'fdt set /chosen h713,dsp-observation-v2 <0x' + MARKER_V2 + '>']
    commands += ['mw.l 0x07090118 0x48444d49', 'itest.l *0x07090118 == 48444d49',
                 'echo H713 DSP OBSERVATION cold RAM boot - no logo or source3' +
                 (' - TVCAP genpd from hardware' if variant == 'v2' else ''),
                 'bootm 0x50000000 - 0x4f000000']
    (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    result = {'scope': 'cold-only RAM DT edits; no environment save or boot-media write',
              'fit_sha256': FIT_SHA, 'dtb_sha256': DTB_SHA, 'disabled_nodes': DISABLED,
              **({'variant': 'v2', 'removed_property': PPU + ' ' + KEEP_TVCAP,
                  'marker_v2': MARKER_V2} if variant == 'v2' else {}),
              'gp6': 'require zero, then set launch budget; never clear',
              'commands_sha256': hashlib.sha256((output / 'commands.json').read_bytes()).hexdigest(),
              'ram_transport_crc32': f'{zlib.crc32(data):08x}',
              'hash_limit': 'Installed U-Boot lacks hash command. FIT SHA256 pinned offline; RAM transport CRC and bootm subimage SHA256 checks retained.'}
    (output / 'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit', required=True, type=Path)
    parser.add_argument('--dumpimage', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--variant', choices=('v1', 'v2'), default='v1',
                        help='v2 = boot-v4: also remove the TVCAP retention flag')
    args=parser.parse_args()
    print(json.dumps(prepare(args.fit, args.dumpimage, args.output, args.variant), indent=2))


if __name__ == '__main__':main()
