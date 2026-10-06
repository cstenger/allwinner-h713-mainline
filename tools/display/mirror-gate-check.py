#!/usr/bin/env python3
"""Judge mirror-gate.sh's samples. Runs on the host.

    mirror-gate-check.py DIR

Per case: the mirror registers against the expected flips, the driver's own
model diff (debugfs), the independent recipe (letterbox-recipe.py, which is
self-tested against the stock captures) against the live registers, and the
panel histogram against the same card unmirrored. Histogram bins count
pixels; a lost row moves 1280 (or the picture width) between bins, so a few
pixels of difference -- 4:2:0 chroma pairing at a mirrored patch edge -- is
tolerated and a row is not.
"""
import json
import re
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 16
REF = {"p": "p0", "v": "v0", "vc": "vc0", "vab": "vab0"}


def parse(path):
    sec, out = None, {"geometry": [], "hist": [], "log": []}
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("== "):
            sec = line[3:]
            continue
        if sec:
            out[sec].append(line)
    regs, lb, differ = {}, {}, None
    for l in out["geometry"]:
        if l.startswith("afbd+010"):
            f = l.split()
            for k, v in zip(f[0::2], f[1::2]):
                regs[k] = int(v, 16)
        elif " model " in l:
            name, live = l.split()[0], int(l.split()[1], 16)
            lb[name] = live
        elif "registers differ" in l:
            differ = int(l.split()[0])
    hist = [int(v, 16) for v in out["hist"] if v.startswith("0x")]
    return regs, lb, differ, hist, out


def flips(mode, rot):
    rx = rot in ("x", "180")
    ry = rot in ("y", "180")
    return (mode & 1) ^ rx, (mode >> 1 & 1) ^ ry


def main():
    d = sys.argv[1]
    cases = [l.split() for l in open(os.path.join(d, "cases.txt")) if l.strip()]
    parsed = {c[0]: parse(os.path.join(d, c[0] + ".txt")) for c in cases}
    npass = 0
    for name, route, mode, rot, commit, rec in cases:
        mode = int(mode)
        regs, lb, differ, hist, raw = parsed[name]
        hf, vf = flips(mode, rot)
        errs = []
        if not regs:
            errs.append("no debugfs geometry (card not up? " + " / ".join(raw["log"][-2:]) + ")")
        else:
            if (regs["lvds+0a0"] & 1) != hf:
                errs.append(f"panel H bit {regs['lvds+0a0'] & 1}, want {hf}")
            want_c0 = 0x02D00016 + (hf if route == "primary" else 0)
            if regs["lvds+0c0"] != want_c0:
                errs.append(f"program window {regs['lvds+0c0']:08X}, want {want_c0:08X}")
            if route == "primary":
                if (regs["afbd+140"] >> 2) & 3 != 2 * vf:
                    errs.append(f"OSD CTRL[3:2] {(regs['afbd+140'] >> 2) & 3}, want {2 * vf}")
                if not regs["comp+040"] & 8:
                    errs.append("comp+040[3] cleared with video off")
            else:
                if (regs["afbd+010"] >> 2) & 3 != 2 * vf:
                    errs.append(f"source 0 CTRL[3:2] {(regs['afbd+010'] >> 2) & 3}, want {2 * vf}")
                if bool(regs["comp+040"] & 8) == bool(vf):
                    errs.append(f"comp+040[3] {(regs['comp+040'] >> 3) & 1}, want {1 - vf}")
            if differ != 0:
                errs.append(f"debugfs: {differ} registers differ from the driver's model")
        if route == "video" and rec != "-" and lb:
            size, rest = rec.split("@")
            at, pitch = rest.split(":")
            cmd = [sys.executable, os.path.join(HERE, "letterbox-recipe.py"), "--live",
                   os.path.join(d, "native.txt"), size, at, "--pitch", pitch,
                   "--mirror", str(mode), "--json", os.path.join(d, name + ".recipe.json")]
            if rot != "-":
                cmd += ["--reflect", rot]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode:
                errs.append("recipe refused: " + r.stderr.strip())
            else:
                doc = json.load(open(os.path.join(d, name + ".recipe.json")))
                bad = []
                for x in doc["regs"]:
                    key = f"{x['block']}+{x['off']:03x}"
                    if key in lb and lb[key] != x["new"]:
                        bad.append(f"{key} live {lb[key]:08X} recipe {x['new']:08X}")
                    elif key == "lvds+0a0" and regs.get(key) != x["new"]:
                        bad.append(f"{key} live {regs.get(key, 0):08X} recipe {x['new']:08X}")
                errs += ["recipe: " + b for b in bad]
        ref = REF["vab" if name.startswith("vab") else "vc" if name.startswith("vc")
                  else "p" if route == "primary" else "v"]
        rh = parsed[ref][3]
        if len(hist) != 4 or len(rh) != 4:
            errs.append("histogram not read")
        else:
            dif = [a - b for a, b in zip(hist, rh)]
            if max(abs(x) for x in dif) > TOL:
                errs.append("histogram differs from " + ref + ": "
                            + " ".join(f"{x:+d}" for x in dif))
        ok = not errs
        npass += ok
        print(f"{'PASS' if ok else 'FAIL'} {name:6} {route:7} mode {mode} rot {rot:3} "
              f"{commit:7} H{hf} V{vf}" + ("" if ok else "\n       " + "\n       ".join(errs)))
    pr = os.path.join(d, "p010-refusal.txt")
    if os.path.exists(pr):
        t = open(pr).read()
        want = ("setV-with-p010 refused", "mode-after 0", "p010-in-V refused", "nv12-in-V committed")
        miss = [w for w in want if w not in t]
        print(("PASS" if not miss else "FAIL") + " p010-refusal" +
              ("" if not miss else ": missing " + ", ".join(miss) + "\n       got: " + t.replace("\n", " | ")))
        if miss:
            npass -= 1
    dm = open(os.path.join(d, "dmesg-after.txt")).read()
    faults = [l for l in dm.splitlines() if re.search(r'iommu.*fault|page fault|unhandled|translation fault', l, re.I)]
    print(f"{npass}/{len(cases)} cases pass; IOMMU/fault lines in dmesg: {len(faults)}")
    for l in faults:
        print("  " + l)
    return 0 if npass == len(cases) and not faults else 1


if __name__ == "__main__":
    sys.exit(main())
