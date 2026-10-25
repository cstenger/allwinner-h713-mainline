#!/usr/bin/env python3
"""Stage-1 read-only snapshot for the HDMI panel-source design.
RUNS ON THE TARGET, as root, from a directory that also holds
letterbox-baseline.py and read-mips-port-cache.py (staged by
run-panel-source-stage1.py).

    panel-source-snapshot.py OUTDIR LABEL

Writes OUTDIR/LABEL-*.txt|json|bin.  Section 10.1 of
docs/hdmi-panel-source-design-2026-10-23.md lists what is read and why:

  * display registers: letterbox-baseline.py unchanged (AFBD 0x000-0x3ff,
    composition incl. NR fetch enables and window, route incl. the proc-blender
    blue screen 0x05140d54, LVDS incl. the panel selector 0x051c006c and the
    panel blue screen 0x051c00b0-b8/0x364, vblender, DETN fetch enables);
  * panel timing 0x05880020/24, one aligned 32-bit load each;
  * the guarded mips-comm-trace page: VIncap counters +0x84..+0x90, only
    after the magic and both canaries match;
  * the HDMI port objects (read-mips-port-cache.py, DRAM only);
  * the firmware elog ring, 2 MiB of MIPS DRAM at 0x4b270000, read twice
    a few seconds apart so uncached lines can be merged on the host.

Never 0x07091000-0x07091fff, never 0x0694xxxx, never GP7.  Nothing here
writes to any device or memory; /dev/mem is opened read-only.
"""
import array
import json
import re
import mmap
import os
import subprocess
import sys
import time
from pathlib import Path

PAGE = 4096
TCON = 0x05880000
TRACE = 0x4D980000
TRACE_MAGIC = 0x434F4D4D
TRACE_CANARY = 0x43414E31
ELOG = 0x4B270000
ELOG_SIZE = 0x200000
FW_CFG = 0x4BE01000   # the firmware's loaded copy of display_cfg.xml
FW_CFG_SIZE = 0x2000
FORBIDDEN = [(0x07091000, 0x07092000), (0x06940000, 0x06950000)]


def guard(base, size):
    for lo, hi in FORBIDDEN:
        if base < hi and base + size > lo:
            raise SystemExit(f"refusing forbidden window {base:#x}+{size:#x}")


def words(fd, base, offsets):
    """One aligned 32-bit load per word (memoryview cast to 'I')."""
    guard(base, max(offsets) + 4)
    span = (max(offsets) + 4 + PAGE - 1) // PAGE * PAGE
    m = mmap.mmap(fd, span, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    try:
        view = memoryview(m).cast("I")
        try:
            return {off: view[off // 4] for off in offsets}
        finally:
            view.release()
    finally:
        m.close()


def dram(fd, base, size):
    """32-bit word loads only, as hidtvreg-raw does for the same ring: the
    reserved MIPS carveout is a device mapping through /dev/mem, so a wide or
    unaligned memcpy is not something to rely on."""
    guard(base, size)
    m = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    try:
        view = memoryview(m).cast("I")
        try:
            return array.array("I", view).tobytes()
        finally:
            view.release()
    finally:
        m.close()


def sh(cmd):
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=20)
    return (p.stdout + p.stderr).strip()


def main():
    out, label = Path(sys.argv[1]), sys.argv[2]
    here = Path(__file__).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        meta = {
            "label": label,
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "uptime": float(Path("/proc/uptime").read_text().split()[0]),
            "handoff": Path("/proc/device-tree/chosen/h713,hdmi-boot-v1").exists(),
            "services": sh("systemctl is-active h713-hdmi-capture h713-hdmi-signal h713-hdmi-speaker"),
            "signal_ready": sh("cat /sys/module/h713_hdmi_signal/parameters/ready"),
        }
        cfg = dram(fd, FW_CFG, FW_CFG_SIZE).split(b"\0", 1)[0].decode("latin1")
        block = re.search(r"<elog_init_setting>(.*?)</elog_init_setting>", cfg, re.S)
        if block:
            tail = re.sub(r"<!--.*?-->", "", block.group(1), flags=re.S)
            meta["elog_cfg"] = dict(re.findall(r"<(\w+) val='(\d+)'", tail))
        else:
            meta["elog_cfg"] = "elog_init_setting not found in the loaded copy"
        # T1 precondition 5: the pool the firmware allocates NR/capture
        # buffers from, and Linux's no-map reservation of the same range.
        block = re.search(r"<frame_buffer>(.*?)</frame_buffer>", cfg, re.S)
        meta["fw_frame_buffer"] = (dict(re.findall(r"<(\w+) val='(0x[0-9A-Fa-f]+)'", block.group(1)))
                                   if block else "frame_buffer not found in the loaded copy")
        node = Path("/proc/device-tree/reserved-memory/framebuf@4bf41000")
        meta["linux_framebuf_reserved"] = {
            "reg": node.joinpath("reg").read_bytes().hex() if node.joinpath("reg").exists() else None,
            "no_map": node.joinpath("no-map").exists(),
        }
        tcon = words(fd, TCON, [0x1C, 0x20, 0x24])
        meta["tcon"] = {f"{TCON + o:#010x}": f"{v:08X}" for o, v in tcon.items()}
        t = words(fd, TRACE, [0x4, 0x80, 0x84, 0x88, 0x8C, 0x90, 0xFFC])
        if t[0x4] == TRACE_MAGIC and t[0x80] == TRACE_CANARY and t[0xFFC] == TRACE_CANARY:
            meta["vincap"] = {"irq": t[0x84], "vde": t[0x88], "vs": t[0x8C], "mode_change": t[0x90]}
        else:
            meta["vincap"] = "trace guard absent; counters not interpreted"

        elog1 = dram(fd, ELOG, ELOG_SIZE)
        (out / f"{label}-elog-1.bin").write_bytes(elog1)
        regs = subprocess.run([sys.executable, str(here / "letterbox-baseline.py")],
                              text=True, capture_output=True, timeout=30)
        (out / f"{label}-regs.txt").write_text(regs.stdout + regs.stderr)
        port = subprocess.run([sys.executable, str(here / "read-mips-port-cache.py")],
                              text=True, capture_output=True, timeout=30)
        (out / f"{label}-port.json").write_text(port.stdout + port.stderr)
        time.sleep(3)
        (out / f"{label}-elog-2.bin").write_bytes(dram(fd, ELOG, ELOG_SIZE))
        t2 = words(fd, TRACE, [0x4, 0x80, 0x88, 0xFFC])
        if isinstance(meta["vincap"], dict) and t2[0x4] == TRACE_MAGIC and t2[0xFFC] == TRACE_CANARY:
            meta["vincap"]["vde_after_3s"] = t2[0x88]
        (out / f"{label}-meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        print(json.dumps(meta))
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
