#!/usr/bin/env python3
"""Derive the widened HDMI-in EDID from the production audio EDID.

docs/hdmi-panel-source-design-2026-10-23.md section 10.24.  Test 1
(characterise-capture.py) can only use modes the host is offered, and the
production EDID (tools/hdmi/fixtures/hdmi-audio-edid.hex, sha edab9bfc...)
offers 1280x720@60 and 640x480 only.  This keeps every byte of it except:

  base block   the range-limits descriptor (bytes 90-107): V 23-61 Hz,
               H 15-68 kHz, max pixel clock 150 MHz (was 59-61 / 31-46 / 80)
  CTA block    the Video Data Block grows to the VICs below; the audio,
               speaker, HDMI VSDB and video-capability blocks are copied
               byte for byte, in the same order

DTD 1 (1280x720@60) stays first and preferred, so a host that is not forced
still picks 720p: production behaviour is unchanged unless a mode is chosen.
No 4K: 148.5 MHz (1080p60) is the ceiling; our receiver path has only run
720p.  The result goes through make-edid-trial-code.py --edid unchanged.

    make-wide-edid.py OUT.hex
    make-wide-edid.py --self-test
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tools/hdmi/fixtures/hdmi-audio-edid.hex"
FIXTURE_SHA = "edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34"
# VIC 4 first (as production), then the additions.  CTA-861 numbering.
VICS = [4, 1, 16, 31, 32, 34, 19, 5, 20, 2, 3, 17, 18]
RANGE = bytes.fromhex("000000fd00" "173d0f440f" "000a202020202020")  # 23-61 Hz, 15-68 kHz, 150 MHz


def load(p):
    t = Path(p).read_text()
    return bytes.fromhex("".join(t.split()))


def blocks(cta):
    """CTA data blocks as (tag, bytes incl. header), and the DTD offset."""
    d = cta[2]
    out, i = [], 4
    while i < d:
        n = cta[i] & 0x1F
        out.append((cta[i] >> 5, cta[i:i + 1 + n]))
        i += 1 + n
    return out, d


def checksum(b):
    b = bytearray(b)
    b[127] = (-sum(b[:127])) & 0xFF
    return bytes(b)


def widen(edid):
    assert len(edid) == 256 and edid[126] == 1
    base = bytearray(edid[:128])
    assert base[90:95] == bytes.fromhex("000000fd00"), "descriptor 3 is not the range limits"
    base[90:108] = RANGE
    cta = edid[128:]
    assert cta[0] == 0x02
    bl, d = blocks(cta)
    if d != 4 + sum(len(b) for _, b in bl) or any(cta[d:127]):
        raise ValueError("CTA block has DTDs or padding this tool does not expect")
    new = []
    for tag, b in bl:
        new.append(bytes([0x40 | len(VICS)]) + bytes(VICS) if tag == 2 else b)
    body = b"".join(new)
    c = bytearray(128)
    c[0:2] = cta[0:2]
    c[2] = 4 + len(body)
    c[3] = cta[3]
    c[4:4 + len(body)] = body
    return checksum(bytes(base)) + checksum(bytes(c))


def self_test():
    fails = []
    src = load(FIXTURE)
    if hashlib.sha256(src).hexdigest() != FIXTURE_SHA:
        fails.append("fixture is not the production EDID edab9bfc")
    w = widen(src)
    # 1. structure: two checksum-valid blocks, one extension, header intact
    if len(w) != 256 or w[:8] != src[:8] or w[126] != 1 or any(sum(w[i:i + 128]) % 256 for i in (0, 128)):
        fails.append("structure / checksums")
    # 2. base block: identical except the range descriptor and the checksum
    diff = [i for i in range(127) if w[i] != src[i]]
    if not diff or min(diff) < 90 or max(diff) > 107:
        fails.append(f"base block changed outside the range descriptor: {diff}")
    if w[54:72] != src[54:72]:
        fails.append("DTD 1 (1280x720@60, preferred) changed")
    # 3. CTA: every non-video block byte-identical and in order; flags unchanged
    sb, _ = blocks(src[128:])
    wb, _ = blocks(w[128:])
    if [b for t, b in sb if t != 2] != [b for t, b in wb if t != 2]:
        fails.append("audio / speaker / VSDB / VCDB blocks not byte-identical")
    if [t for t, _ in sb] != [t for t, _ in wb]:
        fails.append("CTA block order changed")
    if w[128 + 3] != src[128 + 3]:
        fails.append("CTA flags byte changed")
    vdb = next(b for t, b in wb if t == 2)
    if list(vdb[1:]) != VICS or vdb[1] != 4:
        fails.append(f"video data block {list(vdb[1:])}")
    # 4. edid-decode's conformance check passes, and it lists the modes we want
    if shutil.which("edid-decode"):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "w.bin"
            f.write_bytes(w)
            p = subprocess.run(["edid-decode", "--check", str(f)], capture_output=True, text=True)
            out = p.stdout + p.stderr
            if p.returncode or "Failures:" in out and "Failures:\n\n" not in out and "EDID conformity: PASS" not in out:
                fails.append("edid-decode --check did not pass:\n" + "\n".join(l for l in out.splitlines() if "fail" in l.lower() or "warn" in l.lower())[:800])
            for want in ("1920x1080   60.000000 Hz", "1920x1080   50.000000 Hz", "1920x1080   24.000000 Hz",
                         "1920x1080i  60.000000 Hz", "1280x720    50.000000 Hz", "720x576    50.000000 Hz",
                         "Monitor ranges (GTF): 23-61 Hz V, 15-68 kHz H, max dotclock 150 MHz"):
                if want not in out:
                    fails.append(f"edid-decode does not list: {want}")
            pref = [l for l in out.splitlines() if "DTD 1:" in l]
            if not pref or "1280x720" not in pref[0]:
                fails.append(f"preferred DTD is not 1280x720: {pref}")
    else:
        fails.append("edid-decode not installed")
    # 5. the payload generator accepts it, and its code is identical to production's
    gen = ROOT / "tools/hdmi/make-edid-trial-code.py"
    with tempfile.TemporaryDirectory() as d:
        hx = Path(d) / "w.hex"
        hx.write_text(w.hex())
        for name, e in (("prod", FIXTURE), ("wide", hx)):
            subprocess.run([sys.executable, str(gen), "--verify-restore", "--edid", str(e), str(Path(d) / f"{name}.h")],
                           capture_output=True, text=True, check=True)
        code = lambda n: (Path(d) / n).read_text().split("edid_trial_data")[0]
        if code("prod.h") != code("wide.h"):
            fails.append("generator code differs between the production and wide EDIDs")
        prod_h = ROOT / "modules/hdmi-signal/edid-trial-code.h"
        if (Path(d) / "prod.h").read_text() != prod_h.read_text():
            fails.append("regenerated production header differs from modules/hdmi-signal/edid-trial-code.h")
    for f in fails:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else f"passed (wide EDID sha {hashlib.sha256(w).hexdigest()[:12]})")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.out:
        ap.error("OUT.hex required")
    w = widen(load(FIXTURE))
    a.out.write_text(w.hex() + "\n")
    print(a.out, hashlib.sha256(w).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
