#!/usr/bin/env python3
"""Compute the projector's A/B GPT: split super into root_a and root_b.

  tools/v2-gpt-ab-split.py PRIMARY BACKUP OUTDIR

PRIMARY is LBA 0..8 (or more) of the HY200_QZ713_V2 eMMC, BACKUP its last 33
LBAs. Nothing is written to any device: the script writes OUTDIR/new-primary.bin
(LBA 1..8, header + entries) and OUTDIR/new-backup.bin (the last 33 LBAs), plus
a listing. The entry count stays 26, so the SPL at LBA 16 is untouched.

  p9  super           0x92400..0x4923ff  ->  root_a  0x92400..0x2923ff  (1 GiB)
  p16 vbmeta_vendor_b 0x49a780..0x49a7ff ->  root_b  0x292400..0x4923ff (1 GiB)

Both become Linux filesystem partitions (type 0FC63DAF-...); unique GUIDs and
attributes are kept. vbmeta_vendor_b's old 64 KiB stays unallocated. The script
refuses unless the input table is exactly the stock V2 one for these entries
and both CRCs check out, and re-parses its own output before saving it.
"""
import struct
import sys
import uuid
import zlib
from pathlib import Path

DISK_LBAS = 0xE90000
LINUX_FS = uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4').bytes_le
HDR = struct.Struct('<8sIIIIQQQQ16sQIII')
ENT = struct.Struct('<16s16sQQQ72s')
EXPECT = {9: ('super', 0x92400, 0x4923FF), 16: ('vbmeta_vendor_b', 0x49A780, 0x49A7FF)}
NEW = {9: ('root_a', 0x92400, 0x2923FF), 16: ('root_b', 0x292400, 0x4923FF)}


def die(msg):
    sys.exit(f'v2-gpt-ab-split: REFUSED: {msg}')


def header(sector, where):
    h = list(HDR.unpack_from(sector))
    if h[0] != b'EFI PART' or h[2] != 92:
        die(f'{where}: not a GPT header')
    raw = bytearray(sector[:92])
    raw[16:20] = b'\0\0\0\0'
    if zlib.crc32(raw) != h[3]:
        die(f'{where}: header CRC mismatch')
    return h


def pack_header(h):
    h = list(h)
    h[3] = 0
    raw = bytearray(HDR.pack(*h))
    h[3] = zlib.crc32(raw)
    return HDR.pack(*h)


def entries(blob, h, where):
    n, esz = h[11], h[12]
    if (n, esz) != (26, 128):
        die(f'{where}: {n} entries of {esz} bytes, expected 26 of 128')
    e = blob[:n * esz]
    if zlib.crc32(e) != h[13]:
        die(f'{where}: entries CRC mismatch')
    return bytearray(e)


def listing(e):
    out = []
    for i in range(26):
        t, g, s, l, a, name = ENT.unpack_from(e, i * 128)
        if t != bytes(16):
            out.append(f'p{i + 1:2d} {name.decode("utf-16le").rstrip(chr(0)):18s} '
                       f'{s:#9x}..{l:#9x} {((l - s + 1) * 512) >> 20:5d} MiB')
    return out


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    pri, bak, outdir = Path(sys.argv[1]).read_bytes(), Path(sys.argv[2]).read_bytes(), Path(sys.argv[3])
    if len(pri) < 9 * 512 or len(bak) != 33 * 512:
        die('PRIMARY must hold LBA 0..8, BACKUP exactly the last 33 LBAs')
    ph = header(pri[512:1024], 'primary')
    bh = header(bak[32 * 512:33 * 512], 'backup')
    if (ph[5], ph[6], bh[5], bh[6]) != (1, DISK_LBAS - 1, DISK_LBAS - 1, 1):
        die('header LBAs are not those of the 7.28 GiB V2 eMMC')
    if ph[10] != 2:
        die(f'primary entries at LBA {ph[10]}, expected 2')
    pe = entries(pri[1024:], ph, 'primary')
    b_off = (bh[10] - (DISK_LBAS - 33)) * 512
    be = entries(bak[b_off:], bh, 'backup')
    if pe != be:
        die('primary and backup entries differ')

    for p, (name, s, l) in EXPECT.items():
        t, g, cs, cl, a, cn = ENT.unpack_from(pe, (p - 1) * 128)
        cname = cn.decode('utf-16le').rstrip('\0')
        if (cname, cs, cl) != (name, s, l):
            die(f'p{p} is {cname} {cs:#x}..{cl:#x}, expected {name} {s:#x}..{l:#x}')
    for p, (name, s, l) in NEW.items():
        t, g, cs, cl, a, cn = ENT.unpack_from(pe, (p - 1) * 128)
        nm = name.encode('utf-16le').ljust(72, b'\0')
        ENT.pack_into(pe, (p - 1) * 128, LINUX_FS, g, s, l, a, nm)

    # No overlaps, all inside the usable range.
    spans = []
    for i in range(26):
        t, g, s, l, a, n = ENT.unpack_from(pe, i * 128)
        if t == bytes(16):
            continue
        if not (ph[7] <= s <= l <= ph[8]):
            die(f'p{i + 1} {s:#x}..{l:#x} outside usable LBAs')
        spans.append((s, l, i + 1))
    spans.sort()
    for (s1, l1, a), (s2, l2, b) in zip(spans, spans[1:]):
        if s2 <= l1:
            die(f'p{a} and p{b} overlap')

    ecrc = zlib.crc32(bytes(pe))
    ph[13] = bh[13] = ecrc
    new_pri = bytearray(8 * 512)
    new_pri[0:92] = pack_header(ph)
    new_pri[512:512 + len(pe)] = pe
    new_bak = bytearray(bak)
    new_bak[b_off:b_off + len(pe)] = pe
    new_bak[32 * 512:32 * 512 + 92] = pack_header(bh)

    # Re-parse what we built.
    h2 = header(bytes(new_pri[0:512]), 'new primary')
    e2 = entries(bytes(new_pri[512:]), h2, 'new primary')
    h3 = header(bytes(new_bak[32 * 512:]), 'new backup')
    e3 = entries(bytes(new_bak[b_off:]), h3, 'new backup')
    if e2 != e3 or e2 != pe:
        die('rebuilt tables do not re-parse identically')

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / 'new-primary.bin').write_bytes(new_pri)
    (outdir / 'new-backup.bin').write_bytes(new_bak)
    text = ['before:'] + listing(be) + \
           ['after:'] + listing(pe) + \
           [f'write new-primary.bin at LBA 1 (8 sectors), new-backup.bin at LBA {DISK_LBAS - 33:#x} (33 sectors)']
    (outdir / 'listing.txt').write_text('\n'.join(text) + '\n')
    for line in listing(pe):
        if line.startswith(('p 9', 'p16')):
            print(line)
    print(f'entries crc {ecrc:#010x}; files in {outdir}')


if __name__ == '__main__':
    main()
