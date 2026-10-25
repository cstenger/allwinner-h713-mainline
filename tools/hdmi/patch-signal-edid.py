#!/usr/bin/env python3
"""Swap the EDID inside a validated h713-hdmi-signal.ko, changing nothing else.

docs/hdmi-panel-source-design-2026-10-23.md section 10.24.  The EDID is the
256-byte edid_trial_data array the SCP payload copies into the receiver; the
OR1K program around it does not depend on its contents (the generator emits
byte-identical code for any valid EDID).  Rebuilding would also pull in a
newer compiler than the validated 10-16 build, so instead the installed
module is copied with exactly those 256 bytes replaced.  Refuses unless the
old EDID occurs exactly once, both EDIDs are valid 2-block EDIDs, and the
result differs from the input only inside that window.  Modules are not
signed on this kernel (no CONFIG_MODULE_SIG), so no signature is invalidated.

    patch-signal-edid.py IN.ko OLD.hex NEW.hex OUT.ko
    patch-signal-edid.py --self-test
"""
import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def edid(p):
    b = bytes.fromhex("".join(Path(p).read_text().split()))
    if len(b) != 256 or b[:8] != bytes.fromhex("00ffffffffffff00") or b[126] != 1 or \
            any(sum(b[i:i + 128]) % 256 for i in (0, 128)):
        raise ValueError(f"{p}: not a checksum-valid 2-block EDID")
    return b


def patch(ko, old, new):
    if ko.count(old) != 1:
        raise ValueError(f"old EDID occurs {ko.count(old)} times in the module, need exactly 1")
    at = ko.find(old)
    out = ko[:at] + new + ko[at + 256:]
    diff = [i for i in range(len(ko)) if ko[i] != out[i]]
    if len(out) != len(ko) or (diff and (min(diff) < at or max(diff) >= at + 256)):
        raise AssertionError("patch changed bytes outside the EDID window")
    return out, at


def self_test():
    fails = []
    ko_p = ROOT / "modules/hdmi-signal/h713-hdmi-signal.ko"
    ko = ko_p.read_bytes()
    prod = edid(ROOT / "tools/hdmi/fixtures/hdmi-audio-edid.hex")
    wide = edid(ROOT / "tools/hdmi/fixtures/hdmi-wide-edid.hex")
    if hashlib.sha256(ko).hexdigest() != "0a6987ced911cc12f2a36ff2a9550e397c1c0f5889f4b65e8453b298cefe4497":
        fails.append("repo module is not the installed 0a6987ce build")
    out, at = patch(ko, prod, wide)
    if out[at:at + 256] != wide or out[:at] != ko[:at] or out[at + 256:] != ko[at + 256:]:
        fails.append("patched module is not input + new EDID")
    back, _ = patch(out, wide, prod)
    if back != ko:
        fails.append("inverse patch does not restore the original")
    try:
        patch(ko + prod, prod, wide)
        fails.append("accepted an EDID occurring twice")
    except ValueError:
        pass
    try:
        patch(ko, wide, prod)
        fails.append("accepted an EDID that is not in the module")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.hex"
        b = bytearray(prod)
        b[200] ^= 1
        bad.write_text(bytes(b).hex())
        try:
            edid(bad)
            fails.append("accepted an EDID with a bad checksum")
        except ValueError:
            pass
    for f in fails:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else f"passed (EDID at {at:#x}; output sha {hashlib.sha256(out).hexdigest()[:12]})")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="*")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if len(a.args) != 4:
        ap.error("IN.ko OLD.hex NEW.hex OUT.ko")
    ko_in, old, new, ko_out = a.args
    out, at = patch(Path(ko_in).read_bytes(), edid(old), edid(new))
    Path(ko_out).write_bytes(out)
    print(f"{ko_out}: EDID at {at:#x} replaced; sha256 {hashlib.sha256(out).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
