#!/usr/bin/env python3
"""Derive a test DTB that identity-maps the MIPS frame-buffer pool for the display.

Design: docs/hdmi-panel-source-design-2026-10-23.md section 10.12.  The
firmware's HDMI picture path makes AFBD source 0 fetch the capture ring at
physical addresses inside the pool 0x4bf41000 + 0x1a00000 (display_cfg.xml
<frame_buffer>).  On our kernel AFBD (IOMMU master 2) translates from probe,
so that fetch needs an identity map.  This is the same mechanism patch 0080
uses for the U-Boot scanout (iommu-addresses on a reserved-memory node the
device lists in memory-region), plus the VE-side IOVA reservation that
0126's comment explains: the display, VE and AV1 share one IOMMU group, and
only the first device to initialise the domain populates the IOVA allocator.

Starting from an exact DTB (the installed FIT's fdt-1), it makes these edits
and nothing else:
  * framebuf@4bf41000 gains iommu-addresses = <&display 0x4bf41000 0x1a00000>
    and a phandle;
  * a new reg-less node iova-reserve-mips-framebuf, iommu-addresses =
    <&ve 0x4bf41000 0x1a00000>;
  * the VE's memory-region gains that node;
  * the display's memory-region gains framebuf@4bf41000, and
    memory-region-names gains "mips-framebuf".  The driver looks up only the
    name "framebuffer", so its allocation is unchanged.

    make-pool-identity-dtb.py IN.dtb OUT.dtb      # writes OUT.dtb and OUT.dts
"""
import re
import subprocess
import sys
from pathlib import Path

POOL = (0x4BF41000, 0x1A00000)


def dts_of(dtb):
    return subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts", str(dtb)],
                          capture_output=True, text=True, check=True).stdout


def one(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"anchor found {text.count(old)} times, want 1:\n{old}")
    return text.replace(old, new)


def phandle_of(text, node_regex):
    m = re.search(node_regex + r"\{(?:[^{}]|\{[^{}]*\})*?phandle = <(0x[0-9a-f]+)>;", text)
    if not m:
        raise SystemExit(f"no phandle for {node_regex}")
    return int(m.group(1), 16)


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    t = dts_of(src)
    display = phandle_of(t, r"display@5600000 ")
    ve = phandle_of(t, r"video-codec@1c0e000 ")
    used = [int(x, 16) for x in re.findall(r"phandle = <(0x[0-9a-f]+)>;", t)]
    fb_ph, iova_ph = max(used) + 1, max(used) + 2
    a, s = POOL

    t = one(t, "\t\tframebuf@4bf41000 {\n\t\t\treg = <0x4bf41000 0x1a00000>;\n\t\t\tno-map;\n\t\t\tstatus = \"okay\";\n\t\t};\n",
            "\t\tframebuf@4bf41000 {\n\t\t\treg = <0x4bf41000 0x1a00000>;\n\t\t\tno-map;\n\t\t\tstatus = \"okay\";\n"
            f"\t\t\tiommu-addresses = <{display:#04x} {a:#x} {s:#x}>;\n\t\t\tphandle = <{fb_ph:#04x}>;\n\t\t}};\n")
    t = one(t, "\t\tiova-reserve-scanout {\n",
            f"\t\tiova-reserve-mips-framebuf {{\n\t\t\tiommu-addresses = <{ve:#04x} {a:#x} {s:#x}>;\n"
            f"\t\t\tphandle = <{iova_ph:#04x}>;\n\t\t}};\n\n\t\tiova-reserve-scanout {{\n")
    # VE: its single memory-region (the scanout IOVA reservation) gains the new one.
    m = re.search(r"(video-codec@1c0e000 \{(?:[^{}]|\{[^{}]*\})*?memory-region = <)(0x[0-9a-f]+)(>;)", t)
    if not m:
        raise SystemExit("VE memory-region not found")
    t = t[:m.start()] + m.group(1) + f"{m.group(2)} {iova_ph:#04x}" + m.group(3) + t[m.end():]
    t = one(t, '\t\t\tmemory-region = <0x29>;\n\t\t\tmemory-region-names = "adopted-scanout";\n',
            f'\t\t\tmemory-region = <0x29 {fb_ph:#04x}>;\n\t\t\tmemory-region-names = "adopted-scanout", "mips-framebuf";\n')

    out.with_suffix(".dts").write_text(t)
    subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(out), str(out.with_suffix(".dts"))], check=True)
    print(f"display {display:#x}, ve {ve:#x}, new phandles {fb_ph:#x} (pool) {iova_ph:#x} (VE IOVA reserve)")


if __name__ == "__main__":
    main()
