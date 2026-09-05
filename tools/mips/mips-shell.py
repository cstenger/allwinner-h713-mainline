#!/usr/bin/env python3
"""Drive the MIPS display firmware's debug shell from the ARM side.

RUNS ON THE BOARD (needs /dev/mem):

    scp tools/mips/mips-shell.py root@192.168.4.1:/root/
    ssh root@192.168.4.1 python3 -u /root/mips-shell.py --status
    ssh root@192.168.4.1 python3 -u /root/mips-shell.py --cmd 'win wi'

WHY THIS EXISTS.  display.bin spawns two shell threads.  `shell_thread_uart`
polls UART4, whose only pin routes are unavailable to us.  `shell_thread_monitor`
runs the *same command parser* over a ring buffer in DRAM, and 2026-08-07
confirmed on hardware that the ring is registered, ARM-reachable and uncached.
It has never been driven.  Doing so gives us the firmware's own `win` command --
`win wi` dumps the live geometry of every WCE window node -- plus `regr`/`regw`,
the MIPS's own view of the fabric.

THE PROTOCOL, recovered from the firmware and confirmed against the live object.
This is SEGGER-RTT-shaped.  A control block at MIPS 0xabd01000:

    +0x00  char acID[16]
    +0x10  MaxNumUpBuffers      (3)
    +0x14  MaxNumDownBuffers    (3)
    +0x18  aUp[3]               24 bytes each -- MIPS writes, we read
    +0x60  aDown[3]             24 bytes each -- we write, MIPS reads

    each descriptor: { sName, pBuffer, SizeOfBuffer, WrOff, RdOff, Flags }

The firmware's own accessors pin the field order beyond doubt: the read path
(`0x8b155af0`, reached from getc `0x8b19d3b4`) loads pBuffer from `+0x64`,
SizeOfBuffer from `+0x68`, WrOff from `+0x6c` and RdOff from `+0x70` -- i.e.
aDown[0] -- and the rx-ready predicate at `0x8b155f78` returns
`WrOff != RdOff` over the same pair.  24-byte stride is explicit in the code as
`(idx*2 + idx) << 3`.

Read live on 2026-09-04 with the MIPS parked, which confirms every field:

    aUp[0]    pBuffer 0xabd01300  size 0x41c00  WrOff 8  RdOff 0
    aDown[0]  pBuffer 0xabd01200  size 0x100    WrOff 0  RdOff 0

and those 8 pending output bytes are `1b 5b 32 4a 1b 5b 31 48` = `ESC[2J
ESC[1H`, the shell clearing its screen during bring-up.  That is firmware
output sitting in the ring, which is as direct a confirmation of the decode as
this project is going to get without running the thing.

ADDRESS WINDOW.  MIPS kseg0/kseg1 map to system addresses through the measured
+0x40000000 window: kseg0 `0x8b232c20` -> `0x4b232c20`, kseg1 `0xabd01000` ->
`0x4bd01000`.

LINE TERMINATOR.  The shell's key table binds both `0x0d` and `0x0a` to the
"enter" handler at `0x8b18337c`, so either works; we send `\\r`.

THE MIPS MUST BE ALIVE.  Nothing is consumed while the core is parked -- a
staged command simply sits in the ring until it runs.  That is a feature for
testing (stage first, release second), but it means a silent `--cmd` with the
core parked is not a failure of this tool.  `--status` reports the core state.

PRIVILEGE CAVEAT, unresolved.  In the shell's command table `win` carries flag
word `0x2000`, the same as `regw`, while `regr`/`cmds`/`keys` carry `0x2100`.
There is a `users` command and a "default user" entry, so `0x2000` may be a
privilege level the monitor stream does not have.  If `win` comes back
rejected, that is the first thing to look at -- try `cmds` first, which is
`0x2100` and should always work.
"""
import argparse
import ctypes
import mmap
import os
import struct
import sys
import time

DEVICE_GLOBAL = 0x4B232C20      # system address of the pointer to the block
PAGE = 0x1000


def mips_to_sys(addr):
    """kseg0/kseg1 MIPS address -> system physical, via the +0x40000000 window."""
    if 0x80000000 <= addr < 0xA0000000:
        return addr - 0x80000000 + 0x40000000
    if 0xA0000000 <= addr < 0xC0000000:
        return addr - 0xA0000000 + 0x40000000
    return addr


class Mem:
    """/dev/mem accessed strictly as aligned 32-bit words.

    THIS IS NOT A STYLE CHOICE. The MIPS carveout (`4b100000-4d960fff` in
    /proc/iomem, reserved) maps through /dev/mem as **Device memory**, which on
    arm64 does not tolerate unaligned or multi-register accesses. Python's
    `mmap` slicing is a memcpy and SIGBUSes on it -- non-deterministically,
    because whether it faults depends on which memcpy path the length selects:
    a 16-byte read of the control block succeeded and a 24-byte read of the
    same address died. `busybox devmem` never had trouble because it issues one
    aligned volatile word load.

    So every access here goes through a ctypes uint32 view, and byte-level
    writes become read-modify-write of the covering words.
    """

    def __init__(self):
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self.maps = {}

    def _words(self, base):
        if base not in self.maps:
            page = mmap.mmap(self.fd, PAGE, mmap.MAP_SHARED,
                             mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
            self.maps[base] = (page, (ctypes.c_uint32 * (PAGE // 4)).from_buffer(page))
        return self.maps[base][1]

    def u32(self, addr):
        if addr & 3:
            raise ValueError(f"unaligned 32-bit read at {addr:#x}")
        return self._words(addr & ~(PAGE - 1))[(addr & (PAGE - 1)) // 4]

    def put32(self, addr, value):
        if addr & 3:
            raise ValueError(f"unaligned 32-bit write at {addr:#x}")
        self._words(addr & ~(PAGE - 1))[(addr & (PAGE - 1)) // 4] = value & 0xFFFFFFFF

    def read(self, addr, length):
        """Bytes, assembled from the covering aligned words."""
        first = addr & ~3
        last = (addr + length + 3) & ~3
        raw = b"".join(struct.pack("<I", self.u32(a))
                       for a in range(first, last, 4))
        start = addr - first
        return raw[start:start + length]

    def write(self, addr, data):
        """Bytes, via read-modify-write of the covering aligned words."""
        first = addr & ~3
        last = (addr + len(data) + 3) & ~3
        raw = bytearray(b"".join(struct.pack("<I", self.u32(a))
                                 for a in range(first, last, 4)))
        raw[addr - first:addr - first + len(data)] = data
        for i, a in enumerate(range(first, last, 4)):
            self.put32(a, struct.unpack_from("<I", raw, i * 4)[0])


class Buffer:
    """One RTT-shaped ring descriptor."""

    FIELDS = 24

    def __init__(self, mem, desc_addr):
        self.mem = mem
        self.addr = desc_addr
        name, buf, size, wr, rd, flags = struct.unpack("<6I", mem.read(desc_addr, 24))
        self.name_ptr = name
        self.buffer = mips_to_sys(buf) if buf else 0
        self.size = size
        self.flags = flags

    @property
    def wroff(self):
        return self.mem.u32(self.addr + 12)

    @wroff.setter
    def wroff(self, value):
        self.mem.put32(self.addr + 12, value)

    @property
    def rdoff(self):
        return self.mem.u32(self.addr + 16)

    @rdoff.setter
    def rdoff(self, value):
        self.mem.put32(self.addr + 16, value)

    def __repr__(self):
        return (f"buf={self.buffer:#010x} size={self.size:#x} "
                f"wr={self.wroff} rd={self.rdoff} flags={self.flags:#x}")


class Terminal:
    def __init__(self):
        self.mem = Mem()
        ptr = self.mem.u32(DEVICE_GLOBAL)
        if not ptr:
            sys.exit(f"device global {DEVICE_GLOBAL:#x} is zero -- "
                     "the firmware has never published its debug terminal")
        self.block = mips_to_sys(ptr)
        head = self.mem.read(self.block, 0x18)
        self.acid = head[:16]
        self.n_up, self.n_down = struct.unpack("<2I", head[16:24])
        if not (1 <= self.n_up <= 8 and 1 <= self.n_down <= 8):
            sys.exit(f"control block at {self.block:#x} does not look like one "
                     f"(up={self.n_up} down={self.n_down}) -- refusing to write")
        self.up = [Buffer(self.mem, self.block + 0x18 + i * 24)
                   for i in range(self.n_up)]
        self.down = [Buffer(self.mem, self.block + 0x18 + (self.n_up + i) * 24)
                     for i in range(self.n_down)]

    # -- output: MIPS wrote, we consume -----------------------------------
    def drain(self, index=0):
        buf = self.up[index]
        if not buf.buffer or not buf.size:
            return b""
        wr, rd = buf.wroff, buf.rdoff
        if wr == rd:
            return b""
        if wr > rd:
            data = self.mem.read(buf.buffer + rd, wr - rd)
        else:
            data = (self.mem.read(buf.buffer + rd, buf.size - rd) +
                    self.mem.read(buf.buffer, wr))
        buf.rdoff = wr
        return data

    # -- input: we write, MIPS consumes -----------------------------------
    def send(self, text, index=0):
        buf = self.down[index]
        if not buf.buffer or not buf.size:
            sys.exit(f"down buffer {index} is not configured")
        data = text.encode()
        wr, rd = buf.wroff, buf.rdoff
        # One byte is always left unused so full and empty stay distinguishable
        # -- the firmware's own readers treat WrOff == RdOff as empty.
        free = (rd - wr - 1) % buf.size
        if len(data) > free:
            sys.exit(f"command is {len(data)} bytes and only {free} are free "
                     f"in the {buf.size}-byte down buffer; is the MIPS parked?")
        for byte in data:
            self.mem.write(buf.buffer + wr, bytes([byte]))
            wr = (wr + 1) % buf.size
        # Read the payload back before publishing it. /dev/mem may map this
        # region cached, in which case our bytes could still be in the ARM's
        # cache while the MIPS reads stale DRAM. This does not prove coherency,
        # but a mismatch here proves the absence of it, cheaply.
        start = buf.wroff
        if start + len(data) <= buf.size:
            echo = self.mem.read(buf.buffer + start, len(data))
            if echo != data:
                sys.exit(f"readback mismatch: wrote {data!r}, read {echo!r} -- "
                         "the mapping is probably cached; do not trust this path")
        buf.wroff = wr          # publish last, after the payload is in place
        return len(data)


MIPS_RESET_STATUS = 0x0306101C


def mips_alive(mem):
    """1 = the core is running.

    Read through the mmap path, not a plain read() on /dev/mem: this is MMIO
    with no linear mapping, and read() on it SIGBUSes on arm64. That cost a
    debugging round trip -- the mmap of the same address is fine, which is why
    `busybox devmem` had no trouble with it.
    """
    return mem.u32(MIPS_RESET_STATUS) == 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="describe the rings and exit")
    parser.add_argument("--drain", action="store_true", help="print pending output and exit")
    parser.add_argument("--cmd", help="send a command line, then read the reply")
    parser.add_argument("--wait", type=float, default=1.5, help="seconds to wait for output")
    parser.add_argument("--raw", action="store_true", help="hex-dump output instead of decoding")
    args = parser.parse_args()

    term = Terminal()
    alive = mips_alive(term.mem)

    if args.status or not (args.drain or args.cmd):
        print(f"control block  {term.block:#010x}  acID {term.acid!r}")
        print(f"MIPS core      {'ALIVE' if alive else 'parked'} (0x0306101c)")
        for i, buf in enumerate(term.up):
            print(f"  up[{i}]   {buf}")
        for i, buf in enumerate(term.down):
            print(f"  down[{i}] {buf}")
        if not args.status:
            return
        return

    def show(data, label):
        if not data:
            print(f"[{label}: nothing]")
            return
        if args.raw:
            print(f"[{label}: {len(data)} bytes]")
            print(data.hex(" "))
        else:
            print(f"[{label}: {len(data)} bytes]")
            sys.stdout.write(data.decode("latin1"))
            sys.stdout.flush()
            print()

    if args.drain:
        show(term.drain(), "drained")
        return

    stale = term.drain()
    if stale:
        show(stale, "stale output, discarded before the command")

    n = term.send(args.cmd + "\r")
    print(f"[sent {n} bytes: {args.cmd!r}]")
    if not alive:
        print("[the MIPS is PARKED -- the command is staged in the ring and will")
        print(" be consumed when the core is released; expect no reply now]")

    deadline = time.time() + args.wait
    out = b""
    while time.time() < deadline:
        out += term.drain()
        time.sleep(0.05)
    show(out, "reply")


if __name__ == "__main__":
    main()
