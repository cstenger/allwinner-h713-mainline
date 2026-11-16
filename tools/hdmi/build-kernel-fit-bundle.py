#!/usr/bin/env python3
"""Assemble the offline kernel FIT bundle for install-kernel-fit.py; no board access.

Inputs are two release-equivalent kernel builds (tools/build/build.sh kernel
with KERNEL_CONFIG=production and the release epoch/identity): the baseline
from the installed sources and the candidate with the change. Refused unless:
  - the baseline FIT reproduces the installed FIT byte-for-byte (--installed-*
    pins; the defaults are what the board runs),
  - the two .configs differ only in the --config-diff symbols (none: a
    source-only change),
  - Module.symvers and the kernel release are identical (the installed
    out-of-tree and in-tree modules keep loading),
  - the board DTB is identical (or --pio-irq-fix permits exactly the
    SPI 54..62 to SPI 54..60 parent-interrupt correction), and
  - the baseline script reproduces the installed startup script.

--cpu-comm-irq-fix permits exactly msgbox SPI 21 -> 46/109/108 and watchdog
SPI 46 -> 53. --installed-cpu-comm packages the baseline-reproduced CPU_COMM
module in the same guarded transaction.

--module-only is for a change confined to loadable modules: the candidate FIT
and startup script must equal the installed ones, the configuration and board
DTB must be unchanged, and at least one module (--installed-cpu-comm and/or
--installed-cedrus) must change. The bundle then carries only the modules, with
the FIT and script hashes as read-only installer preconditions.

--installed-cedrus also packages the changed in-tree decoder module, after its
baseline rebuild matches the supplied installed SHA-256. It is then backed up,
staged and rolled back with the FIT/script by the installer.

--rustc-probe-transition is for the first bundle after build.sh stopped
letting host rustc into .config (2026-11-09). FITs installed before it embed
rustc 1.99's probe results, so their baseline only reproduces with
H713_KERNEL_RUSTC=<that rustc>; the candidate is built normally. The option
expects exactly RUSTC_PROBE_SYMBOLS to differ, set in the baseline and "none"
in the candidate. Later baselines build without rustc and need no option.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Installed since 2026-11-10 (0190 + rustc-free kernel config, install-kernel-fit.py).
INSTALLED_FIT = '9d49630823d0d8636fc192cb4db7b000dbbf57f30361ee845e9e2fe517675ca6'
INSTALLED_CMD = '2dd9adb1bdd42a9325b429abfad68aabea3330f4012fe0a10a872896718c7b0b'
INSTALLED_SCR = '4c2453a4ee311bc8cec1b069cf078ce3d471172c87157fdfb1f4d9150f1c02d8'
DTB = 'sun50i-h713-hy200-qz713df-a1.dtb'
CEDRUS = 'drivers/staging/media/sunxi/cedrus/sunxi-cedrus.ko'
CPU_COMM = 'drivers/soc/sunxi/cpu_comm/hy310-cpu-comm.ko'
# What rustc 1.99 (installed kernels up to 2026-11-09) wrote into .config.
RUSTC_PROBE_SYMBOLS = {
    'CONFIG_RUSTC_VERSION': ('109900', '0'), 'CONFIG_RUSTC_LLVM_VERSION': ('230101', '0'),
    **{'CONFIG_RUSTC_HAS_'+s: ('y', None) for s in
       ('COERCE_POINTEE', 'SPAN_FILE', 'UNNECESSARY_TRANSMUTES', 'FILE_WITH_NUL', 'FILE_AS_C_STR')},
    'CONFIG_HAVE_CFI_ICALL_NORMALIZE_INTEGERS_RUSTC': ('y', None),
}


def sha(b): return hashlib.sha256(b).hexdigest()


def need(ok, message):
    if not ok: raise SystemExit(message)


def tree(work):
    trees = sorted((work/'build').glob('linux-*/'))
    need(len(trees) == 1, 'expected exactly one kernel tree in '+str(work))
    return trees[0]


def config(path):
    out = {}
    for line in path.read_text().splitlines():
        if m := re.fullmatch(r'(CONFIG_\w+)=(.*)', line): out[m[1]] = m[2]
        elif m := re.fullmatch(r'# (CONFIG_\w+) is not set', line): out[m[1]] = 'n'
    return out


def check_pio_irq_dtb(baseline, candidate):
    """Permit exactly the nine-to-seven PIO parent IRQ correction, nothing else."""
    node = '/soc/pinctrl@2000000'
    with tempfile.TemporaryDirectory(prefix='h713-pio-dtb-') as directory:
        old, new = (Path(directory)/name for name in ('old.dtb', 'new.dtb'))
        old.write_bytes(baseline); new.write_bytes(candidate)
        def irqs(path):
            run = subprocess.run(['fdtget', '-t', 'u', str(path), node, 'interrupts'],
                                 capture_output=True, text=True)
            need(run.returncode == 0, 'cannot read PIO interrupt property: '+run.stderr)
            return [int(n) for n in run.stdout.split()]
        expected = lambda end: [n for spi in range(54, end) for n in (0, spi, 4)]
        need(irqs(old) == expected(63), 'baseline PIO interrupts are not SPI 54..62')
        need(irqs(new) == expected(61), 'candidate PIO interrupts are not SPI 54..60')
        subprocess.run(['fdtput', '-t', 'i', str(old), node, 'interrupts',
                        *map(str, expected(61))], check=True, capture_output=True)
        def canonical(path):
            return subprocess.check_output(['dtc', '-q', '-s', '-I', 'dtb', '-O', 'dts', str(path)])
        need(canonical(old) == canonical(new), 'DTB differs outside the PIO interrupt correction')


def check_cpu_comm_irq_dtb(baseline, candidate):
    """Allow only stock msgbox-bank and watchdog interrupt corrections."""
    with tempfile.TemporaryDirectory(prefix='h713-cpu-comm-dtb-') as directory:
        old, new = (Path(directory)/name for name in ('old.dtb', 'new.dtb'))
        old.write_bytes(baseline); new.write_bytes(candidate)
        for node, before, after in (
            ('/soc/cpu-comm@3003000', [0, 21, 4], [0, 46, 4, 0, 109, 4, 0, 108, 4]),
            ('/soc/watchdog@2051000', [0, 46, 4], [0, 53, 4]),
        ):
            def irqs(path):
                out = subprocess.run(['fdtget', '-t', 'u', str(path), node, 'interrupts'],
                                     capture_output=True, text=True)
                need(out.returncode == 0, 'cannot read '+node+' interrupts: '+out.stderr)
                return [int(v) for v in out.stdout.split()]
            need(irqs(old) == before, 'unexpected baseline interrupts: '+node)
            need(irqs(new) == after, 'unexpected candidate interrupts: '+node)
            subprocess.run(['fdtput', '-t', 'i', str(old), node, 'interrupts',
                            *map(str, after)], check=True, capture_output=True)
        def canonical(path):
            return subprocess.check_output(['dtc', '-q', '-s', '-I', 'dtb', '-O', 'dts', str(path)])
        need(canonical(old) == canonical(new), 'DTB differs outside CPU_COMM/watchdog IRQ corrections')


def check_cpu_comm_witness_dtb(baseline, candidate):
    """Permit only growing the existing no-map trace reservation to 256 KiB."""
    node = '/reserved-memory/hdmi-trace@4d980000'
    with tempfile.TemporaryDirectory(prefix='h713-witness-dtb-') as directory:
        old, new = (Path(directory)/name for name in ('old.dtb', 'new.dtb'))
        old.write_bytes(baseline); new.write_bytes(candidate)
        def cells(path):
            out = subprocess.run(['fdtget', '-t', 'u', str(path), node, 'reg'],
                                 capture_output=True, text=True)
            need(out.returncode == 0, 'missing witness trace reservation')
            return [int(v) for v in out.stdout.split()]
        need(cells(old) == [0x4d980000, 0x1000], 'unexpected baseline trace reservation')
        need(cells(new) == [0x4d980000, 0x40000], 'unexpected witness reservation')
        need(subprocess.run(['fdtget', str(new), node, 'no-map'],
                            capture_output=True).returncode == 0, 'witness reservation must be no-map')
        subprocess.run(['fdtput', '-t', 'i', str(old), node, 'reg',
                        str(0x4d980000), str(0x40000)], check=True, capture_output=True)
        def canonical(path):
            return subprocess.check_output(['dtc', '-q', '-s', '-I', 'dtb', '-O', 'dts', str(path)])
        need(canonical(old) == canonical(new), 'DTB differs outside the witness reservation')


def check(baseline, candidate, installed_fit, expected_diff, rustc_transition=False,
          pio_irq_fix=False, cpu_comm_irq_fix=False, cpu_comm_witness=False, module_only=False):
    bt, ct = tree(baseline), tree(candidate)
    bfit = (baseline/'build/out/h713-kernel-production.fit').read_bytes()
    cfit = (candidate/'build/out/h713-kernel-production.fit').read_bytes()
    need(sha(bfit) == installed_fit, 'baseline build does not reproduce the installed FIT')
    if module_only:
        need(cfit == bfit, 'module-only bundle needs the installed FIT unchanged')
        need(not (expected_diff or rustc_transition or pio_irq_fix or cpu_comm_irq_fix or cpu_comm_witness),
             'module-only bundle cannot change configuration or DTB')
    else:
        need(cfit != bfit, 'candidate FIT equals the baseline')
    bc, cc = config(bt/'.config'), config(ct/'.config')
    diff = sorted(k for k in set(bc) | set(cc) if bc.get(k) != cc.get(k))
    if rustc_transition:
        for k, (old, new) in RUSTC_PROBE_SYMBOLS.items():
            need((bc.get(k), cc.get(k)) == (old, new), 'not the rustc probe transition: %s %s -> %s'
                 % (k, bc.get(k), cc.get(k)))
        expected_diff = [*expected_diff, *RUSTC_PROBE_SYMBOLS]
    need(diff == sorted(expected_diff), 'unexpected config difference: '+str(diff))
    need((bt/'Module.symvers').read_bytes() == (ct/'Module.symvers').read_bytes(), 'Module.symvers differs')
    release = lambda t: (t/'include/config/kernel.release').read_text()
    need(release(bt) == release(ct), 'kernel release differs')
    bdtb, cdtb = ((w/'build/out'/DTB).read_bytes() for w in (baseline, candidate))
    need(sum((pio_irq_fix, cpu_comm_irq_fix, cpu_comm_witness)) <= 1, 'select only one DT correction')
    if cpu_comm_witness:
        check_cpu_comm_witness_dtb(bdtb, cdtb)
    elif cpu_comm_irq_fix:
        check_cpu_comm_irq_dtb(bdtb, cdtb)
    elif pio_irq_fix:
        check_pio_irq_dtb(bdtb, cdtb)
    else:
        need(bdtb == cdtb, 'board DTB differs')
    return bfit, cfit, bdtb


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--baseline', required=True, type=Path, help='baseline kernel work directory')
    p.add_argument('--candidate', required=True, type=Path, help='candidate kernel work directory')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--installed-fit', default=INSTALLED_FIT)
    p.add_argument('--installed-cmd', default=INSTALLED_CMD)
    p.add_argument('--installed-scr', default=INSTALLED_SCR)
    p.add_argument('--config-diff', action='append', default=[],
                   help='a CONFIG_ symbol the candidate is meant to change (repeat)')
    p.add_argument('--rustc-probe-transition', action='store_true',
                   help='baseline built with H713_KERNEL_RUSTC (rustc 1.99), candidate without')
    p.add_argument('--pio-irq-fix', action='store_true',
                   help='allow only the H713 PIO interrupt-list correction from nine banks to seven')
    p.add_argument('--cpu-comm-irq-fix', action='store_true',
                   help='allow only stock CPU_COMM and watchdog interrupt corrections')
    p.add_argument('--cpu-comm-witness', action='store_true',
                   help='allow only the dedicated trace reservation growth from 4 to 256 KiB')
    p.add_argument('--installed-cpu-comm',
                   help='package CPU_COMM after reproducing this installed module SHA-256')
    p.add_argument('--module-only', action='store_true',
                   help='FIT/script unchanged; package and install only the changed modules')
    p.add_argument('--installed-cedrus',
                   help='also package Cedrus; require this installed SHA-256 to match its baseline rebuild')
    a = p.parse_args()
    bfit, cfit, bdtb = check(a.baseline, a.candidate, a.installed_fit, a.config_diff,
                           a.rustc_probe_transition, a.pio_irq_fix, a.cpu_comm_irq_fix, a.cpu_comm_witness,
                           a.module_only)
    need(not a.module_only or a.installed_cpu_comm or a.installed_cedrus,
         'module-only bundle needs --installed-cpu-comm and/or --installed-cedrus')
    cdtb = (a.candidate/'build/out'/DTB).read_bytes()
    if a.rustc_probe_transition: a.config_diff += list(RUSTC_PROBE_SYMBOLS)
    spec = importlib.util.spec_from_file_location('startup', ROOT/'tools/hdmi/build-startup.py')
    st = importlib.util.module_from_spec(spec);spec.loader.exec_module(st)
    old = st.script(fit_size=len(bfit), fdt_size=len(bdtb)).encode()
    new = st.script(fit_size=len(cfit), fdt_size=len(cdtb)).encode()
    need(sha(old) == a.installed_cmd and sha(st.legacy_image(old)) == a.installed_scr,
         'baseline script does not reproduce the installed script')
    if a.module_only:
        need(new == old, 'module-only bundle needs the installed script unchanged')
    a.output.mkdir(parents=True, exist_ok=False)
    files = ({} if a.module_only else
             {'h713-kernel.fit': cfit, 'h713-hdmi.cmd': new, 'h713-hdmi.scr': st.legacy_image(new)})
    module_baseline = {}
    if a.installed_cedrus:
        old_module = (tree(a.baseline)/CEDRUS).read_bytes()
        new_module = (tree(a.candidate)/CEDRUS).read_bytes()
        need(sha(old_module) == a.installed_cedrus, 'baseline Cedrus does not reproduce the installed module')
        need(new_module != old_module, 'candidate Cedrus equals baseline')
        files['sunxi-cedrus.ko'] = new_module
        module_baseline['sunxi-cedrus.ko'] = a.installed_cedrus
    if a.installed_cpu_comm:
        old_module = (tree(a.baseline)/CPU_COMM).read_bytes()
        new_module = (tree(a.candidate)/CPU_COMM).read_bytes()
        need(sha(old_module) == a.installed_cpu_comm, 'baseline CPU_COMM does not reproduce the installed module')
        need(new_module != old_module, 'candidate CPU_COMM equals baseline')
        files['hy310-cpu-comm.ko'] = new_module
        module_baseline['hy310-cpu-comm.ko'] = a.installed_cpu_comm
    for name, data in files.items(): (a.output/name).write_bytes(data)
    shutil.copy(ROOT/'tools/hdmi/install-kernel-fit.py', a.output/'install-kernel-fit.py')
    manifest = dict(schema='h713-kernel-fit-v1', **({'scope': 'modules'} if a.module_only else {}),
                    files={n: sha(d) for n, d in files.items()},
                    baseline={'h713-kernel.fit': a.installed_fit, 'h713-hdmi.cmd': a.installed_cmd,
                              'h713-hdmi.scr': a.installed_scr, **module_baseline},
                    sizes=dict(baseline_fit=len(bfit), candidate_fit=len(cfit),
                               baseline_fdt=len(bdtb), fdt=len(cdtb)),
                    checks={'module_symvers_equal': True, 'kernel_release_equal': True,
                            'config_diff': sorted(a.config_diff),
                            'dtb_change': ('cpu-comm-witness-reservation-only' if a.cpu_comm_witness else
                                           'cpu-comm-watchdog-irqs-only' if a.cpu_comm_irq_fix else
                                           'pio-spi-54-60-only' if a.pio_irq_fix else 'none'),
                            **({'fit_unchanged': True, 'script_unchanged': True} if a.module_only else {}),
                            'cpu_comm_module_reproduced': bool(a.installed_cpu_comm),
                            'cedrus_module_reproduced': bool(a.installed_cedrus)},
                    installer=sha((a.output/'install-kernel-fit.py').read_bytes()))
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
