#!/usr/bin/env python3
"""Offline low-level init and patch-download trace from captured libmspsound.

All device operations are stubs. Stop before hardware version checks; never
pretend this establishes hardware readiness or a complete initialization.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "re"))
from awemu import Lib, RET
from unicorn.arm_const import UC_ARM_REG_PC


class PatchCheckpoint(Exception):
    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("library")
    ap.add_argument("--patch-output", required=True)
    args = ap.parse_args()
    digest = hashlib.sha256(Path(args.library).read_bytes()).hexdigest()
    assert digest == "61f349440c08dd28ef1289f463a7934b3213b15518113ff1044f881bf237e8c4"
    lib = Lib(args.library)
    events, registers = [], {}

    def write(l, r):
        registers[r[0]] = r[1]
        events.append(dict(function="aud_write_reg", args=r[:2]))
        return 0

    lib.extern["aud_read_reg"] = lambda l, r: registers.get(r[0], 0)
    lib.extern["aud_write_reg"] = write
    for name in ["MAPI_ADU_CFG_SetDSPClockSpeed", "MAPI_AUD_CFG_Enable_HDMI_Rx",
                 "MAPI_ADU_CFG_SetHDMIMuteForI2sIn"]:
        lib.extern[name] = lambda l, r, name=name: events.append(
            dict(function=name, args=r[:2])) or 0
    assert lib.call("sound_lowlevel_init") == 0
    assert lib.uc.reg_read(UC_ARM_REG_PC) == RET
    patch = bytes(lib.uc.mem_read(lib.sym("patch_msp"), 2896))
    Path(args.patch_output).write_bytes(patch)
    prefix, writes = [], []
    lib.extern["tdAudioDSPWriteRegWord"] = lambda l, r: prefix.append(r[:3]) or 0
    lib.extern["aud_dsp1_write_reg"] = lambda l, r: writes.append(r[:2]) or 0

    def stop(l, r):
        raise PatchCheckpoint()

    lib.extern["tdAudioDSPReadRegWord"] = stop
    try:
        lib.call("msp_download_sxl")
    except PatchCheckpoint:
        pass
    else:
        raise AssertionError("patch checkpoint not reached")
    # Vendor loop consumes all 724 big-endian (address, value) pairs.
    assert writes == [list(struct.unpack_from(">HH", patch, o))
                      for o in range(0, len(patch), 4)]
    assert prefix == [[0, 0xfff7, 0], [0, 0, 0]]
    print(json.dumps(dict(library_sha256=digest,
        evidence="Offline execution, zero initial MMIO; stopped before hardware version checks.",
        lowlevel=events, patch_sha256=hashlib.sha256(patch).hexdigest(),
        patch_prefix=prefix, patch_write_count=len(writes), patch_writes=writes), indent=2))


if __name__ == "__main__":
    main()
