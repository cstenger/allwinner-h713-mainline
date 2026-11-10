#!/usr/bin/env python3
"""Host-only: DSP words written by individual stock graph calls.

Runs libmspdriver Init_Modules, then each named MAPI call in isolation and
records the tdAudioDSPWrite* calls it makes. No board access; hardware
readiness and firmware are not modelled. Code intent, not live readback.
"""
import argparse, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "re"))
from awemu import Lib, RET
from unicorn.arm_const import UC_ARM_REG_PC

DRIVER_SHA = "a03e6344ad0f672e5be965fd3008c8c44c74b367868318501a9d2a4798ce88ea"

# Stock route 0x8f data path, from Sound_Path_Init + Sound_Path_Connect(0x8f):
# 9600 -> 8400 -> 8500 -> 8f01 in 2/3 -> 9009/900a -> 9500 (DTVOUT1).
EDGES = [(0x8400, p, 0x9600, p) for p in (0, 1)] + \
        [(0x8500, p, 0x8400, p) for p in range(6)] + \
        [(0x8f01, 2, 0x8500, 0), (0x8f01, 3, 0x8500, 1),
         (0x9009, 0, 0x8f01, 0), (0x900a, 0, 0x8f01, 1),
         (0x9500, 0, 0x9009, 0), (0x9500, 1, 0x900a, 0)]
MIXER = [(0x8f01, 0, 0, 0x20), (0x8f01, 0, 2, 0x20),
         (0x8f01, 1, 1, 0x20), (0x8f01, 1, 3, 0x20)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("driver", type=Path, help="exact stock libmspdriver.so")
    args = ap.parse_args()
    assert hashlib.sha256(args.driver.read_bytes()).hexdigest() == DRIVER_SHA
    lib = Lib(args.driver)
    writes = []
    for name in ["tdAudioDSPWriteRegMaskWord", "tdAudioDSPWriteRegWord",
                 "DSP_WriteReg", "aud_dsp1_write_reg"]:
        lib.intercept(name, lambda l, a, name=name:
                      writes.append(dict(function=name, args=a)) or 0)
    # DSP ownership handshake bypassed inside the emulator only (exact build).
    lib.intercept(0x1f0a4, lambda l, a: 0)
    for name in ["tdAudioDSPReadRegWord", "aud_dsp1_read_reg", "DSP_ReadReg"]:
        if name in lib.exports:
            lib.intercept(name, lambda l, a: 0)
    assert lib.call("Init_Modules") == 0 and lib.uc.reg_read(UC_ARM_REG_PC) == RET

    def run(fn, *a):
        writes.clear()
        rc = lib.call(fn, *a)
        assert lib.uc.reg_read(UC_ARM_REG_PC) == RET, (fn, "budget")
        return dict(function=fn, args=list(a), rc=rc, writes=writes[:])

    out = [run("MAPI_AUD_SetSourceSelectPort", d, dp, s, sp, 0) for d, dp, s, sp in EDGES]
    scratch = lib.alloc(16)
    out += [run("MAPI_AUD_SetMixer", *m) for m in MIXER]
    for m in (0x8400, 0x8500, 0x8f01, 0x9009, 0x900a, 0x9500):
        out.append(run("MAPI_AUD_EnableInterface", m, scratch, 0, 0))
    print(json.dumps(dict(driver_sha256=DRIVER_SHA,
                          evidence="offline emulation after Init_Modules; not live readback",
                          calls=out), indent=1))


if __name__ == "__main__":
    main()
