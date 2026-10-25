#!/usr/bin/env python3
"""Find the window-layer objects in a raw MIPS DRAM image and compare two images.

docs/hdmi-panel-source-design-2026-10-23.md section 10.21.  The image is the
`mips-image.bin` that display-sweep.py (ours) or stock-capture.sh sweep
(stock) writes: ARM physical 0x4b100000 onward, MIPS kseg0 = physical +
0x40000000.  Objects are found by vptr (= vtable + 8, recovered with
tools/mips/vtables.py from display.bin 4380f1b3), never by address: stock's
heap layout differs from ours.

Comparison pairs objects of a class in heap order and reports the words that
differ.  A word that points into the MIPS image on both sides is compared by
what it points AT (the pointee's class, or "heap"), so allocation-address
differences do not drown the real ones.

    walk-wce-nodes.py IMAGE                    # list objects + labelled fields
    walk-wce-nodes.py IMAGE_A IMAGE_B          # field differences, A vs B
    walk-wce-nodes.py --self-test
"""
import argparse
import struct
import sys

PHYS, KSEG0 = 0x4B100000, 0x8B100000
# class: (vptr, words to dump, {offset: label})
CLASSES = {
    "NRWinNode": (0x8B207A50, 0x50, {0x4C: "fb_vs (TVs cast)", 0x50: "fb_afbd (TAfbd cast)", 0x54: "fb_in",
                                     0x58: "fb_hist", 0x5C: "colour_format", 0x60: "afbd_source_mode"}),
    "CapWinNode": (0x8B207124, 0x50, {}),
    "ProcWinNode": (0x8B207E14, 0x40, {0x04: "bytes4-7 (+7 = mb_420_format)"}),
    "PanelWinNode": (0x8B207C94, 0x50, {}),
    "MemoryAgent": (0x8B1FB818, 0x60, {0x08: "source", 0x0C: "signal_id", 0xB4: "flags (+0xb5 locked)"}),
    "TVsFrameBuffer": (0x8B207740, 0x26, {0x50: "w", 0x58: "h", 0x5C: "compress", 0x60: "ratio_y",
                                          0x64: "ratio_c", 0x68: "colour_format"}),
    "TAfbdFrameBuffer": (0x8B207754, 0x26, {}),
}
VPTR = {v: n for n, (v, _, _) in CLASSES.items()}


def words(img):
    return struct.unpack_from(f"<{len(img) // 4}I", img)


def find(img):
    """{class: [(kseg0 address, [words])]} in heap order."""
    w = words(img)
    out = {n: [] for n in CLASSES}
    for i, x in enumerate(w):
        if x in VPTR:
            n = VPTR[x]
            out[n].append((KSEG0 + 4 * i, list(w[i:i + CLASSES[n][1]])))
    return out


def pointee(img, v):
    """Describe a word that may point into the image: None if it does not."""
    if not KSEG0 <= v < KSEG0 + len(img) - 3 or v & 3:
        return None
    w = struct.unpack_from("<I", img, v - KSEG0)[0]
    return f"->{VPTR[w]}" if w in VPTR else "->heap"


def show(img):
    for n, objs in find(img).items():
        labels = CLASSES[n][2]
        for addr, ws in objs:
            print(f"{n} @ {addr:08x}")
            for off, label in sorted(labels.items()):
                if off // 4 < len(ws):
                    v = ws[off // 4]
                    print(f"    +{off:03x} {label:<28} {v:08x} {pointee(img, v) or ''}")


def compare(a, b):
    fa, fb = find(a), find(b)
    diffs = []
    for n in CLASSES:
        labels = CLASSES[n][2]
        if len(fa[n]) != len(fb[n]):
            diffs.append((n, None, None, f"{len(fa[n])} vs {len(fb[n])} objects", ""))
        for k, ((aa, wa), (ab, wb)) in enumerate(zip(fa[n], fb[n])):
            for i, (x, y) in enumerate(zip(wa, wb)):
                px, py = pointee(a, x), pointee(b, y)
                if px is not None and py is not None:
                    if px != py:
                        diffs.append((n, k, 4 * i, f"{x:08x}{px}", f"{y:08x}{py}"))
                elif x != y:
                    diffs.append((n, k, 4 * i, f"{x:08x}", f"{y:08x}"))
    return diffs


def self_test():
    fails = []
    size = 0x10000

    def image(objs):
        img = bytearray(size)
        for off, ws in objs:
            struct.pack_into(f"<{len(ws)}I", img, off, *ws)
        return bytes(img)

    nr = CLASSES["NRWinNode"][0]
    fb = CLASSES["TVsFrameBuffer"][0]
    # A: NR at 0x1000 pointing at a TVs frame buffer at 0x2000, mode 1, colour 4
    a_nr = [nr] + [0] * 0x4F
    a_nr[0x4C // 4] = KSEG0 + 0x2000
    a_nr[0x5C // 4], a_nr[0x60 // 4] = 4, 1
    a = image([(0x1000, a_nr), (0x2000, [fb] + [0] * 0x25)])
    # B: same objects at other addresses (heap layout differs) and one real difference
    b_nr = list(a_nr)
    b_nr[0x4C // 4] = KSEG0 + 0x3004  # odd word index on purpose
    b_nr[0x5C // 4] = 2
    b = image([(0x1800, b_nr), (0x3004, [fb] + [0] * 0x25)])
    f = find(a)
    if [x for x, _ in f["NRWinNode"]] != [KSEG0 + 0x1000] or len(f["TVsFrameBuffer"]) != 1:
        fails.append(f"find: {f['NRWinNode']}")
    d = compare(a, b)
    if [(n, off) for n, _, off, _, _ in d] != [("NRWinNode", 0x5C)]:
        fails.append(f"compare reported {[(n, off) for n, _, off, _, _ in d]}, want only NR +0x5c")
    # a pointer to a different class IS a difference
    c_nr = list(a_nr)
    c_nr[0x4C // 4] = KSEG0 + 0x1000  # points at the NR node itself
    c = image([(0x1000, c_nr), (0x2000, [fb] + [0] * 0x25)])
    if not any(off == 0x4C for _, _, off, _, _ in compare(a, c)):
        fails.append("pointer to a different class not reported")
    # object-count mismatch is reported
    if not any(off is None for _, _, off, _, _ in compare(a, image([(0x1000, a_nr)]))):
        fails.append("missing object not reported")
    for x in fails:
        print("FAIL:", x)
    print("self-test", "FAILED" if fails else "passed")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="*")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    imgs = [open(p, "rb").read() for p in a.images]
    if len(imgs) == 1:
        show(imgs[0])
    elif len(imgs) == 2:
        for n, k, off, x, y in compare(*imgs):
            print(f"{n}[{k}] +{off:03x}  {x:<24} {y}" if off is not None else f"{n}: {x}")
    else:
        ap.error("one or two images")
    return 0


if __name__ == "__main__":
    sys.exit(main())
