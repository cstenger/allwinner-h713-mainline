#!/usr/bin/env python3
"""Build a mode-specific H713 SCP EDID probe from repository sources."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "modules/scp-probe"
MODULE_CMD = ROOT / "modules/hdmi-v4l2/.h713-hdmi-v4l2.ko.cmd"
KERNEL_RELEASE = "6.18.38"


def run(argv, timeout=120):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1200:]} {result.stderr[-1200:]}")
    return result.stdout


def validated_kernel_build(path):
    release = path / "include/config/kernel.release"
    if (path / "Module.symvers").is_file() and release.is_file():
        if release.read_text().strip() == KERNEL_RELEASE:
            return path
    return None


def find_kernel_build(explicit):
    if explicit:
        path = validated_kernel_build(explicit.resolve())
        if not path:
            raise RuntimeError(f"kernel build is incomplete or not {KERNEL_RELEASE}: "
                               f"{explicit}")
        return path

    if MODULE_CMD.is_file():
        match = re.search(r"-T (\S+)/scripts/module\.lds", MODULE_CMD.read_text())
        if match:
            path = validated_kernel_build(Path(match.group(1)))
            if path:
                return path

    candidates = sorted((ROOT / "build").glob(f"linux-{KERNEL_RELEASE}-*"),
                        key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        path = validated_kernel_build(candidate)
        if path:
            return path
    raise RuntimeError(f"no complete Linux {KERNEL_RELEASE} build tree was found")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("640x480", "1280x720"),
                    default="1280x720")
    ap.add_argument("--kernel-build", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    output = (args.output or
              ROOT / "build" / f"scp-probe-{args.mode.replace('x', '-')}")
    output.mkdir(parents=True, exist_ok=True)
    kernel_build = find_kernel_build(args.kernel_build)
    shutil.copy2(SOURCE / "Makefile", output / "Makefile")
    shutil.copy2(SOURCE / "h713-scp-probe.c", output / "h713-scp-probe.c")
    run([sys.executable, str(HERE / "make-edid-trial-code.py"),
         "--mode", args.mode, str(output / "edid-trial-code.h")])
    run(["make", "-C", str(kernel_build), f"M={output}", "ARCH=arm64",
         "LLVM=1", "modules"])

    module = output / "h713-scp-probe.ko"
    vermagic = run(["modinfo", "-F", "vermagic", str(module)]).strip()
    if vermagic.split()[0] != KERNEL_RELEASE:
        raise RuntimeError(f"unexpected probe vermagic: {vermagic}")
    result = {"mode": args.mode, "module": str(module),
              "sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
              "kernel_build": str(kernel_build), "vermagic": vermagic}
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
