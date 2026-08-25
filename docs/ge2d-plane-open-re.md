# Plane-open RE — Stage 1, 2026-08-25

Static analysis of the stock display driver to answer one question: **is
plane-open separable from cold bring-up, or must we own the whole display
init to use a video plane?**

Answer: **separable, on the evidence below.** That contradicts the standing
note that a plane cannot be added to a running pipeline.

## The binary

`ge2d_dev.ko`, board B's stock display driver. **ARM 32-bit, unstripped, 926
symbols, relocations intact.** SHA-256
`a79017e5d3bc9563135e463404d3bb38bf6f263d5b31fbe122768f2dca11583f`.

Stashed at `local/h713-lab/extracted/ge2d_dev.ko` (gitignored) with the
extraction recipe, so this is not re-derived. Summary: `super` begins at byte
**306708480** of `board-b-mmcblk0-20260705T072349Z.img` — confirm by checking
for the LP geometry magic `67 44 6c 61` at +4096 — then `lpunpack
--partition=vendor_a`, then `debugfs -R "dump /lib/modules/ge2d_dev.ko"`.
Disassemble with `llvm-objdump -d --triple=armv7-none-linux-gnueabi`.

## Finding 1: plane-init is reachable at runtime

```
init_osd_plane.constprop.12  <- ge2d_resume_operation, tgd_init_planesetting
tgd_init_planesetting        <- no intra-module callers  (exported entry)
```

Two independent reasons this is not probe-only work:

- `tgd_init_planesetting` has **no callers inside the module** and is a global
  `T` symbol, i.e. it is an entry point reached from outside — the ioctl
  surface.
- `ge2d_resume_operation` calls it. Resume re-runs plane init against hardware
  that is already up, which makes the sequence **repeatable** rather than a
  one-shot cold-boot action. Its first ~40 instructions assert **no display
  reset** — it re-applies register values and proceeds.

**What this retires.** The earlier conclusion "no register poke can add a plane
to a running pipeline" came from writing `tgd_is_plane_open`'s status bit
(OSD base `+0x1c` bit 0) and observing nothing. That reading was right about
the bit and wrong about the mechanism: the bit is a *readout*, and the action
is a function — one that is callable at runtime.

## Finding 2: writes go through `io_accessor_write_reg`

Not `writel`. The stock driver writes MMIO through the `trix,io-accessor`
driver, whose DT node maps exactly the windows in play (`0x5240000`,
`0x51c0000`, `0x5200000`, `0x5600000`):

```
io_accessor_write_reg(r0 = space id (2), r1 = address, r2 = value, r3 = mask)
   returns 0 on success; every call site checks it
```

`init_osd_plane` makes **19 writes and 3 read-modify-writes**.

## Finding 3: the values are the live ones — plus bit 31 on the ctrl

Extracted values, cross-checked against register dumps taken independently from
a running board and against the `LogoRegData.bin` block set:

| value written | live register value | note |
| --- | --- | --- |
| `0x83001901` | `0x05600140` = `0x03001901` | **same value with bit 31 set** |
| `0x008000ff` | `0x05600148` = `0x008000ff` | exact match |
| `0x00ff0080` | — | |
| `0x00000808` | `0x05600164` = `0x00000808` | exact match |
| `0x00000082` | — | |
| `0x00000021` | `0x0560016c` = `0x00000021` | exact match |

Then a read-modify-write triple against the LVDS block (`0x051c006c`), one
write of `0x80fc0208`, and nine writes to the OSD block (`0x0524c000`
region): `0x04650898`, `0x0000ff00`, `0x03000140`, `0x02000000`, `0x00100010`,
`0x03000000`, `0x01000100`, `0x00000100`.

Note `0x80fc0208` also carries bit 31.

**The inference worth testing first, clearly labelled as inference:** three of
the six channel values are byte-identical to what the running pipeline already
holds, and the one that differs differs *only* by bit 31. On Allwinner display
blocks bit 31 is commonly an update/commit enable. If that holds here, it
explains cleanly why the 2026-08-14 live-poke campaign could write the vendor's
own values, verify them sticking on readback, and still see nothing: it wrote
the payload without the commit bit.

This is a hypothesis derived from a value comparison. It is not established.

## What is NOT established

- **Per-write addresses.** The extraction resolves values reliably but not
  each write's target: the address register is reloaded from a struct of
  ioremapped bases and the analyzer conflates consecutive loads. The six
  channel writes almost certainly map to `0x05600140/148/14c/164/168/16c` in
  order, matching both the value cross-check and the LogoRegData block set —
  but "almost certainly" is not a register map. Resolving the struct layout
  built in `ge2d_drv_probe` is the remaining desk work.
- **Whether the sequence works against a *U-Boot*-initialised pipeline.** Stock
  runs it against its own bring-up. Ours is U-Boot's, via the MIPS
  co-processor. This is the assumption that has already produced two wrong
  conclusions in this project; it needs a hardware test, not an argument.
- **Whether opening a plane is sufficient** to then feed it from cedrus. That
  was always the third of the "three stacked unknowns" and remains untouched.

## The bit-31 test: NEGATIVE, 2026-08-25

Run on hardware, on the running U-Boot-initialised pipeline. Cost: one register
write, fully reversed afterwards.

```
write 0x83001901 -> 0x05600140      (live value 0x03001901, bit 31 added)
readback immediate : 0x83001901
readback after 1s  : 0x83001901
readback after 4s  : 0x83001901
changed registers  : 0x05600140 only
```

Snapshot covered `0x05600100`–`0x05600178` (both AFBD channel blocks) and the
OSD blocks `0x05248000`/`0x0524c000` including their `+0x1c` status words.

**Bit 31 is sticky, not a trigger.** It does not self-clear, which is what a
commit/update-enable bit would do. Nothing else latched.

Second half of the test: with bit 31 still set, a normal page flip was issued
(the driver's commit path is read-modify-write, `CTRL |= 1` then `READY = 1`,
so the flip carries bit 31). Result: `rc=0`, **no register changed**, no
`flip_done` timeouts, no driver errors. Restored to `0x03001901` afterwards and
the display path re-verified with a BGRx commit.

**So the cheap hypothesis is dead.** Setting the ctrl bit the vendor sets, on
its own, does not open a plane.

What this does *not* rule out: that bit 31 is meaningful *within* the full
sequence. The vendor writes it as the first of 22 operations, and the ones that
follow — nine writes to the `0x0524c000` OSD block, a read-modify-write triple
against LVDS `0x051c006c`, and the `0x80fc0208` write — are untested. A bit
that gates a later write would look exactly like this in isolation.

The value of the test is that it cost one write to learn the plane does not
open on the ctrl bit alone, before anyone built a 22-register sequence on that
assumption.

## The struct-offset map — RESOLVED 2026-08-25

The address argument is `[table + offset]`, where the table is a per-plane set
of register bases. Recovered by emulating the stores across the whole module:

| offset | plane 0 | plane 1 | fixed (set by `init_svp`) |
| --- | --- | --- | --- |
| +0x1c | | | `0x05240000` GE2D core |
| +0x20 | | | `0x0525c000` mixer |
| +0x24 | `0x05280040` | `0x05280080` | |
| +0x28 | `0x05248000` | `0x0524c000` | OSD |
| +0x2c | `0x05288000` | `0x0529c000` | |
| +0x30 | `0x05600100` | `0x05600140` | AFBD channel |
| +0x34 | | | `0x05600000` AFBD base |
| +0x38 | | | `0x051c0000` LVDS base |
| +0x3c | `0x0520002c` | `0x05200034` | |
| +0x40 | `0x051c0060` | `0x051c006c` | |
| +0x44 | `0x051c0180` | `0x051c019c` | |

**`init_osd_plane` stores only the plane-0 set, so it operates on channel 0** —
the channel the 2026-08-14 poke campaign tried to clone by hand and got null
from. Our KMS driver drives channel 1.

## The sequence

Addresses resolved for 21 of 22 operations; values are literal for 15, the rest
computed at runtime (geometry and buffer addresses).

```
0x05600100 <- 0x83001901      AFBD ch0 ctrl   (ch1 live: 0x03001901)
0x05600108 <- 0x008000ff                      (ch1 live: 0x008000ff)  same
0x0560010c <- 0x00ff0080                      (ch1 live: 0x00000080)
0x05600124 <- 0x00000808                      (ch1 live: 0x00000808)  same
0x05600128 <- 0x00000082                      (ch1 live: 0x000003b2)
0x0560012c <- 0x00000021                      (ch1 live: 0x00000021)  same

0x051c001c -> read ; 0x051c0010 <- computed   LVDS read-modify-write, x3

<unresolved addr> <- 0x80fc0208

0x05248010 <- 0x04650898      OSD plane 0
0x05248014 <- computed
0x05248050 <- 0x0000ff00
0x0524807c <- 0x03000140
0x05248080 <- 0x02000000
0x05248004 <- 0x00100010
0x05248018 <- 0x03000000
0x05248058 <- 0x01000100
0x0524805c <- 0x00000100
```

**Two independent cross-checks say this decode is right.** The channel offsets
used are `+0x00/+0x08/+0x0c/+0x24/+0x28/+0x2c`, which are exactly the six
registers the LogoRegData block set writes on channel 1 at
`0x05600140/148/14c/164/168/16c` — confirming the 0x40 channel stride from a
completely different direction. And four of the six values are byte-identical
to what channel 1 holds on a running board.

So what `init_osd_plane` does is **configure channel 0 to mirror the channel 1
that is already scanning out**, then program its OSD block. That is what
"opening a plane" means here.

The peer tree's partial decodes line up too, one plane over: their
`0x0524c004` (OSD v_active), `0x0524c010` (htotal+hsync) and `0x0524c014`
(timing) are the plane-1 counterparts of `0x05248004`, `0x05248010` and
`0x05248014` here.

**A trap for the replay.** `0x05248010 <- 0x04650898` unpacks as 0x0898 = 2200
and 0x0465 = 1125 — 1080p60 totals, not the 1650x750 this 1280x720 panel runs.
That matches the stock driver initialising its framebuffer at 1920x1080. The
sequence cannot be replayed verbatim on our timing; the geometry writes need
recomputing for the mode actually running, and that is a second reason the
2026-08-14 attempt to clone ch0 from ch1 by hand could not have worked.

## Does the sequence work against the U-Boot pipeline? NO — tested 2026-08-25

The load-bearing assumption, tested directly rather than argued about.

**A clean success criterion exists.** `tgd_is_plane_open()` reads OSD base
`+0x1c` bit 0. On a running board:

```
0x0524c01c = 0x79860601   plane 1 (live)  -- bit 0 SET
0x0524801c = 0x00000000   plane 0         -- bit 0 clear
```

So "did the plane open" is answerable by reading one register. No eyes needed.

**Pre-state also resolved the 22nd write.** OSD plane 0 (`0x05248000`) reads
all zeros — completely unconfigured, so writing it cannot disturb the live
path. And live plane 1 base `0x0524c000` reads `0x00fc0202`, which makes the
vendor's unresolved `0x80fc0208` obviously the plane-0 analogue at OSD `+0x00`.
That is the write whose address would not resolve statically.

Four more OSD literals — `0x0000ff00`, `0x01000100`, `0x00000100`,
`0x03000140` — are byte-identical to live plane 1, which is a third
independent confirmation of the decode.

**The test.** All 15 literal writes applied verbatim in disassembly order (the
3 LVDS read-modify-writes and the computed values were skipped, being
runtime-dependent):

```
plane0 open bit BEFORE: 0x00000000
plane0 open bit AFTER : 0x00000000
```

**Unmoved.** Every write landed and read back; nothing else in the snapshot
latched; plane 1 was unaffected throughout. One incidental finding: the write
to `0x05600128` did **not** stick — it stayed 0 — so that register is
read-only or gated, unlike its neighbours.

Restored afterwards; display re-verified with a BGRx commit, `rc=0`.

**What this says.** Configuring a plane is not the same as opening it. The
registers `init_osd_plane` writes are the plane's *configuration*; something
else must route it into the output before the status bit reflects anything.
`init_osd_plane` never writes the mixer (`0x0525c000`) or the VBlender
(`0x0520002c` / `0x05200034`) — it only *stores their bases in the table* — so
the enabling step is somewhere else, most plausibly `tgd_put_plane_info` at
11064 bytes, the largest function in the module and still unexamined.

It is also possible the bit only ever reflects real scanout, in which case no
amount of configuration will set it until the mixer routes the plane.

**What this does not say.** It does not show the sequence is wrong — every
cross-check says the decode is right. It shows the sequence is *incomplete*.
And it leaves the original question open in one respect: the LVDS
read-modify-writes were skipped, so "verbatim" here means 15 of 22 operations.

## Next

1. ~~Resolve the struct-offset → MMIO map.~~ **Done, above.**
0. **Disassemble `tgd_put_plane_info`** (11064 B). It is the biggest function,
   it is an exported entry point, and it is where the enable most likely lives.
   Desk work; no board time.
2. Replay the full sequence, not fragments of it. The single-register result
   above is the argument against further piecemeal poking.
3. Read the peer tree's `sunxi_ge2d_firmware.c` alongside step 1 — it has
   partial decodes of the same OSD registers (`0x0524c004` v_active,
   `0x0524c010` htotal+hsync, `0x0524c014` timing).

The peer tree's `sunxi_ge2d_firmware.c` has partial decodes of the same
territory (`0x05600140` dual-port bit, `0x0524c010` htotal+hsync,
`0x0524c004` OSD v_active, `0x0524c014` OSD timing) and is worth reading
alongside step 1 rather than after it.
