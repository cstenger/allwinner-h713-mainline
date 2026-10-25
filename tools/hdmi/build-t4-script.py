#!/usr/bin/env python3
"""Build the RAM-only T4 startup script: warm-shared, booting the pool-identity FIT.

docs/hdmi-panel-source-design-2026-10-23.md section 10.12.  T4 needs the
production kernel with one change: a DTB that identity-maps the MIPS
frame-buffer pool for the display (tools/display/make-pool-identity-dtb.py).
The installed h713-hdmi.scr pins the production FIT and FDT sizes, so it
would (safely) refuse that FIT.  This script is build-warm-shared.py's
output -- the installed cold branch, run once from RAM on a warm boot --
with exactly these substitutions in the hdmi_image stage:

    fatload mmc 1:2 ... h713-kernel.fit
                                -> ext4load mmc 1:1a ... /root/panel-source-t4/h713-kernel-t4.fit
    itest ${filesize} == ...    -> the T4 FIT size
    itest ${hdmi_fdt_size} == ..-> the T4 FDT size
    itest ${hdmi_fdt_end} -le . -> 0x50000000 + the T4 FIT size

Every other line (including any recovery fallback) stays byte-identical.
The output directory has the layout tools/serial/run-warm-shared.py expects
(warm-shared.scr, warm-shared.cmd, manifest.json), so the proven runner drives
it unchanged.  Never accesses the board; nothing is installed.

    build-t4-script.py --fit build/t4-fit/h713-kernel-t4.fit --output build/hdmi-t4-2026-10-23
    build-t4-script.py --self-test
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PROD = dict(fit=7795668, fdt=34666)
# The boot FAT has ~3 MiB free, so the T4 FIT lives on the ext4 root
# (partition 26 = 0x1a), as earlier test FITs did; nothing goes on the FAT.
T4_PATH = "/root/panel-source-t4/h713-kernel-t4.fit"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fit_sizes(fit):
    mk = next(ROOT.glob("build/uboot-*/tools/mkimage"))
    out = subprocess.run([str(mk), "-l", str(fit)], capture_output=True, text=True, check=True).stdout
    sizes = [int(l.split(":")[1].split()[0]) for l in out.splitlines() if "Data Size:" in l]
    return pathlib.Path(fit).stat().st_size, sizes[1]


def t4_script(warm, fit_size, fdt_size, path=None):
    w = load("warm", HERE / "build-warm-shared.py")
    for old, new in [
        ("fatload mmc 1:2 0x50000000 h713-kernel.fit && itest ${filesize} == %x " % PROD["fit"],
         "ext4load mmc 1:1a 0x50000000 " + (path or T4_PATH) + " && itest ${filesize} == %x " % fit_size),
        ("itest ${hdmi_fdt_size} == %x " % PROD["fdt"], "itest ${hdmi_fdt_size} == %x " % fdt_size),
        ("itest ${hdmi_fdt_end} -le %x " % (0x50000000 + PROD["fit"]),
         "itest ${hdmi_fdt_end} -le %x " % (0x50000000 + fit_size)),
    ]:
        warm = w.replace_once(warm, old, new)
    return warm


def build(fit, output, path=None):
    w = load("warm", HERE / "build-warm-shared.py")
    st = load("startup", HERE / "build-startup.py")
    if output.exists():
        raise FileExistsError(output)
    assert w.sha(w.INSTALLED / "h713-hdmi.cmd") == w.SCRIPT_SHA, "installed script changed"
    warm = w.warm_script((w.INSTALLED / "h713-hdmi.cmd").read_text())
    fit_size, fdt_size = fit_sizes(fit)
    text = t4_script(warm, fit_size, fdt_size, path)
    output.mkdir(parents=True)
    (output / "warm-shared.cmd").write_text(text)
    (output / "warm-shared.scr").write_bytes(st.legacy_image(text.encode()))
    # Cold variant: the whole installed script (GP6 logic included) with the
    # same substitutions, for a caught cold U-Boot prompt (GP6 == 0 there).
    cold = t4_script((w.INSTALLED / "h713-hdmi.cmd").read_text(), fit_size, fdt_size, path)
    (output / "t4-cold.cmd").write_text(cold)
    (output / "t4-cold.scr").write_bytes(st.legacy_image(cold.encode()))
    sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
    manifest = {
        "schema": "h713-warm-shared-v1",
        "purpose": "RAM-only boot of the installed HDMI startup, booting a test FIT "
                   "from ext4 " + (path or T4_PATH) + "; nothing installed",
        "installed_script_sha256": w.SCRIPT_SHA, "production_fit_sha256": w.FIT_SHA,
        "latch": w.LATCH,
        "t4_fit_sha256": sha(fit), "t4_fit_size": fit_size, "t4_fdt_size": fdt_size,
        "warm_script_sha256": sha(output / "warm-shared.scr"),
        "warm_cmd_sha256": sha(output / "warm-shared.cmd"),
        "cold_script_sha256": sha(output / "t4-cold.scr"),
        "tools": {n: sha(HERE / n) for n in ("build-warm-shared.py", "check-warm-shared.py", "build-t4-script.py")}
                 | {"run-warm-shared.py": sha(ROOT / "tools/serial/run-warm-shared.py")},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(output / "manifest.json")


def self_test():
    w = load("warm", HERE / "build-warm-shared.py")
    warm = w.warm_script((w.INSTALLED / "h713-hdmi.cmd").read_text())
    t4 = t4_script(warm, 7795808, 34806)
    fails = []
    a, b = warm.splitlines(), t4.splitlines()
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(a) != len(b) or len(changed) != 1 or not b[changed[0]].startswith("setenv hdmi_image "):
        fails.append(f"expected exactly the hdmi_image line to change, got lines {changed}")
    line = b[changed[0]] if changed else ""
    for want in ("ext4load mmc 1:1a 0x50000000 /root/panel-source-t4/h713-kernel-t4.fit && ", "itest ${filesize} == 76f460 ", "itest ${hdmi_fdt_size} == 87f6 ",
                 "itest ${hdmi_fdt_end} -le 5076f460 "):
        if want not in line:
            fails.append("missing: " + want)
    if "h713-kernel.fit" in line:
        fails.append("production FIT name left in hdmi_image")
    fb = "fatload mmc 1:2 0x50000000 h713-kernel.fit; then bootm"
    if t4.count(fb) != warm.count(fb):
        fails.append("recovery fallback lines changed")
    # Production sizes must be the anchors: a drifted pin must fail loudly.
    try:
        t4_script(warm.replace("== 76f3d4 ", "== 76f3d5 "), 1, 1)
        fails.append("did not refuse a changed production FIT pin")
    except ValueError:
        pass
    for f in fails:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else "passed")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fit", type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path)
    ap.add_argument("--path", help=f"ext4 path of the test FIT on the board (default {T4_PATH})")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    build(a.fit.resolve(), a.output.resolve(), a.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
