#!/usr/bin/env python3
"""Recover the C++ class hierarchy and vtables of the H713 MIPS display firmware.

`display.bin` is C++ built with RTTI, and the whole window/composition layer is
expressed as classes (`TIWinNode`, `RNWinNode`, ...).  That is the most useful
structure in the image: a vtable slot names an operation, and the slot index is
stable across every subclass, so one recovered vtable reads all of them.

Layout, Itanium ABI as GCC emits it for MIPS32:

    typeinfo   = { &vtable_for___si_class_type_info + 8, &name, [&base_typeinfo] }
    vtable     = { offset_to_top (0), &typeinfo, fn0, fn1, ... }

The scan is anchored on the name strings (`9RNWinNode`, `10CapWinNode`: a
decimal length followed by that many identifier characters), because those are
unambiguous, then walks back to the typeinfo and forward to the vtable.

    vtables.py FIRMWARE                 # every class, with bases
    vtables.py FIRMWARE --name WinNode  # only classes whose name matches
    vtables.py FIRMWARE --slots 12      # how many virtual slots to print
"""
import argparse
import re
import struct

BASE = 0x8B100000
NAME = re.compile(rb"(\d+)([A-Za-z_][A-Za-z0-9_]*)")


def load(path):
    with open(path, "rb") as handle:
        return handle.read()


class Image:
    def __init__(self, data):
        self.data = data
        self.end = BASE + len(data)

    def word(self, va):
        return struct.unpack_from("<I", self.data, va - BASE)[0]

    def inside(self, va):
        return BASE <= va < self.end

    def cstr(self, va, limit=96):
        offset = va - BASE
        end = self.data.find(b"\0", offset, offset + limit)
        return self.data[offset:end].decode("latin1") if end > offset else ""

    def refs(self, value):
        """Every 4-byte-aligned word in the image equal to `value`."""
        out = []
        needle = struct.pack("<I", value)
        pos = self.data.find(needle)
        while pos != -1:
            if pos % 4 == 0:
                out.append(BASE + pos)
            pos = self.data.find(needle, pos + 1)
        return out


def find_names(image):
    """VA -> demangled-ish class name, for every plausible typeinfo name string."""
    names = {}
    for match in NAME.finditer(image.data):
        length, ident = match.group(1), match.group(2)
        if int(length) != len(ident) or len(ident) < 3:
            continue
        # The string must be NUL-terminated exactly where the length says.
        end = match.start() + len(length) + len(ident)
        if end >= len(image.data) or image.data[end] != 0:
            continue
        names[BASE + match.start()] = ident.decode()
    return names


def recover(image, names):
    """Return {class name: {'typeinfo':…, 'vtable':…, 'bases':[…], 'slots':[…]}}."""
    typeinfos = {}
    for name_va, name in names.items():
        for site in image.refs(name_va):
            # name pointer sits at typeinfo+4
            typeinfo = site - 4
            if not image.inside(typeinfo):
                continue
            if not image.inside(image.word(typeinfo)):
                continue          # typeinfo[0] is the type_info class's own vptr
            typeinfos[typeinfo] = name

    classes = {}
    for typeinfo, name in typeinfos.items():
        bases = []
        candidate = image.word(typeinfo + 8)
        if candidate in typeinfos:
            bases.append(typeinfos[candidate])
        elif image.inside(candidate) and image.inside(image.word(candidate + 4)):
            base_name = image.cstr(image.word(candidate + 4), 64)
            match = NAME.fullmatch(base_name.encode())
            if match:
                bases.append(match.group(2).decode())

        vtable = None
        for site in image.refs(typeinfo):
            if site - 4 >= BASE and image.word(site - 4) == 0:
                vtable = site - 4
                break
        classes[name] = {"typeinfo": typeinfo, "vtable": vtable, "bases": bases}
    return classes


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("firmware")
    parser.add_argument("--name", help="substring filter on the class name")
    parser.add_argument("--slots", type=int, default=16)
    args = parser.parse_args()

    image = Image(load(args.firmware))
    classes = recover(image, find_names(image))

    for name in sorted(classes):
        if args.name and args.name not in name:
            continue
        info = classes[name]
        bases = f" : {', '.join(info['bases'])}" if info["bases"] else ""
        vtable = f"vtable {info['vtable']:#x}" if info["vtable"] else "vtable not found"
        print(f"{name}{bases}   typeinfo {info['typeinfo']:#x}  {vtable}")
        if not info["vtable"]:
            continue
        for slot in range(args.slots):
            va = info["vtable"] + 8 + slot * 4
            target = image.word(va)
            if not image.inside(target):
                break
            print(f"    [{slot:2d}] {target:#010x}")


if __name__ == "__main__":
    main()
