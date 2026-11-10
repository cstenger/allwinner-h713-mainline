#!/usr/bin/env python3
"""Decode stock sound_preset.bin routes; optionally emulate MSP routing.

Host-only analysis. This never opens a board device or writes hardware.
DSP writes are intercepted in Unicorn; output is code evidence, not a live
trace or a complete DSP initialization recipe.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


class Preset:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        assert self.data[:8] == b"TRID_AUD"
        assert self.u(16) == len(self.data)
        self.muxes = {}
        graph = self.u(24)
        assert self.data[graph:graph + 4] == b"GRAF"
        for i in range(self.u(graph + 12)):
            m = graph + self.u(graph + 20 + 4 * i)
            assert self.data[m:m + 4] == b"MUX_"
            endpoints = {}
            for kind, count_at, offset_at in [("in", 32, 36), ("out", 40, 44)]:
                endpoints[kind] = {}
                for j in range(self.u(m + count_at)):
                    e = m + self.u(m + offset_at) + j * 32
                    ident, typ, module, port = [self.u(e + k) for k in (16, 20, 24, 28)]
                    endpoints[kind][ident] = dict(name=self.name(e, 16), type=typ,
                                                  module=module, port=port)
            self.muxes[self.u(m + 28)] = dict(name=self.name(m, 24), **endpoints)
        self.routes = {}
        director = self.u(32)
        assert self.data[director:director + 4] == b"PHDR"
        for i in range(self.u(director + 8)):
            p = director + self.u(director + 12 + 4 * i)
            assert self.data[p:p + 4] == b"PATH"
            selections = []
            for j in range(self.u(p + 36)):
                q = p + self.u(p + 40) + 12 * j
                selections.append(tuple(self.u(q + k) for k in (0, 4, 8)))
            self.routes[self.u(p + 28)] = dict(name=self.name(p + 4, 20),
                offset=p, device=self.u(p + 32), selections=selections,
                director_action_count=self.u(p + 44))

    def u(self, offset):
        return struct.unpack_from("<I", self.data, offset)[0]

    def name(self, offset, size):
        return self.data[offset:offset + size].split(b"\0", 1)[0].decode("ascii")

    def decode(self, route):
        r = self.routes[route]
        selected = {(m, out): inp for m, inp, out in r["selections"]}

        def source(module, port, seen=()):
            if module not in self.muxes:
                return module, port
            key = (module, port)
            assert key not in seen, "mux cycle"
            inp = self.muxes[module]["in"][selected[key]]
            assert inp["type"] == 1
            return source(inp["module"], inp["port"], seen + (key,))

        edges = []
        for m, inp, out in r["selections"]:
            a, z = self.muxes[m]["in"][inp], self.muxes[m]["out"][out]
            assert a["type"] == z["type"] == 1
            # An output into another virtual mux is realized when that mux's
            # terminal output is connected. Do not invent a physical module.
            if z["module"] in self.muxes:
                continue
            sm, sp = source(a["module"], a["port"])
            edge = dict(source_module=sm, source_port=sp,
                        destination_module=z["module"], destination_port=z["port"])
            if edge not in edges:
                edges.append(edge)
        return dict(id=route, **r, edges=edges)


def emulate(driver, routes):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "re"))
    from awemu import Lib, RET
    from unicorn.arm_const import UC_ARM_REG_PC
    result = []
    for route in routes:
        lib = Lib(driver)
        writes = []
        for name in ["tdAudioDSPWriteRegMaskWord", "tdAudioDSPWriteRegWord",
                     "DSP_WriteReg", "aud_dsp1_write_reg"]:
            lib.intercept(name, lambda l, args, name=name:
                          writes.append(dict(function=name, args=args)) or 0)
        # The internal DSP_ACCESS_USR ownership handshake is bypassed ONLY
        # inside the emulator. Hardware readiness/firmware is not modeled.
        lib.intercept(0x1f0a4, lambda l, args: 0)
        assert lib.call("Init_Modules") == 0
        assert lib.uc.reg_read(UC_ARM_REG_PC) == RET
        writes.clear()
        for edge in route["edges"]:
            args = [edge["destination_module"], edge["destination_port"],
                    edge["source_module"], edge["source_port"], 0]
            rc = lib.call("MAPI_AUD_SetSourceSelectPort", *args)
            assert lib.uc.reg_read(UC_ARM_REG_PC) == RET, "instruction budget exhausted"
            assert rc == 0, (edge, rc)
        result.append(dict(route=route["id"], writes=writes))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("preset")
    ap.add_argument("--route", action="append", type=lambda s: int(s, 0))
    ap.add_argument("--driver", help="exact ARM32 libmspdriver.so for offline emulation")
    args = ap.parse_args()
    p = Preset(args.preset)
    routes = [p.decode(r) for r in (args.route or [0x71, 0x89, 0x80, 0xbd])]
    output = dict(preset_sha256=hashlib.sha256(p.data).hexdigest(), routes=routes,
                  evidence="static preset and offline emulation; not runtime execution")
    if args.driver:
        # Internal interception address belongs to this exact captured build.
        digest = hashlib.sha256(Path(args.driver).read_bytes()).hexdigest()
        assert digest == "a03e6344ad0f672e5be965fd3008c8c44c74b367868318501a9d2a4798ce88ea"
        output["driver_sha256"] = digest
        output["emulation"] = emulate(args.driver, routes)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
