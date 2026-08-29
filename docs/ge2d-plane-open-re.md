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

> ### ⚠ CORRECTED 2026-08-25 — this finding was built on a method error
>
> External review caught it and hardware-independent re-checking confirms it.
> The caller analysis below matched only **resolved `bl` targets in the
> disassembly text**. In an `ET_REL` object, intra-module calls also go through
> **`R_ARM_CALL` relocations**, which that pass never looked at. So "no
> intra-module callers" meant "none I searched for".
>
> The real picture:
>
> ```
> tgd_init_planesetting  <- init_svp        @ 0x99ac   (probe-time path)
> tgd_put_plane_info     <- svp_ioctl       @ 0x8ffc   (the actual ioctl path)
> ```
>
> And the module exports only **`AllocateFB`, `FreeFB`, `InitFBManagement`** —
> none of the `tgd_` functions. So `tgd_init_planesetting` is *not* an exported
> ioctl entry; it is called from probe-time setup.
>
> **What survives:** `ge2d_resume_operation` really does call `init_osd_plane`
> against live hardware with no reset, so plane configuration is still
> re-appliable at runtime. **What does not:** the claim that
> `tgd_init_planesetting` is the runtime entry point. The runtime entry is
> `svp_ioctl -> tgd_put_plane_info`. Its command and payload have since been
> recovered exactly from stock HWC: command `0x4631`, 80-byte `_plane_info`.

```
init_osd_plane.constprop.12  <- ge2d_resume_operation, tgd_init_planesetting
tgd_init_planesetting        <- no intra-module callers  (WRONG -- see above)
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

## Finding 1a: the runtime ABI is now exact (2026-08-26)

Stock `hwcomposer.ares.so` opens `/dev/ge2d` and its `submitLayer()` wrapper
issues:

```
ioctl(fd, 0x4631, plane_info)
```

Before the call it sets `_plane_info + 0x4c` to `-1`; on return that word is
the release-fence fd. The object is exactly 80 bytes. Stock `ge2d_dev.ko`
confirms the other side independently: `svp_ioctl` compares command `0x4631`,
copies 80 bytes from userspace, calls `tgd_put_plane_info()` at `0x8ffc`, then
copies all 80 bytes back. This closes the command-number/payload-size unknown.

The controlled DECD-only boot in
[plane-brief-for-external-review.md](plane-brief-for-external-review.md) also
shows why this operation matters. `/dev/decd` accepted and serviced a valid
NV12 frame at 59.7 Hz, but the panel remained on the U-Boot packed-OSD source.
Hiding that OSD produced black. Stock therefore uses a paired design:
`/dev/decd` queues frame data and `/dev/ge2d` commits the plane/topology.

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

## `tgd_put_plane_info`, the latch, and the answer

`tgd_put_plane_info` makes 42 writes, 35 reads, and calls two primitives
`init_osd_plane` does not: **`osd_ready_for_update`** and
**`osd_wait_update_finish`**. The first is the commit our earlier test omitted:

```
osd_ready_for_update(plane):
    ldr r5, [r3, r0, lsl #2]    ; OSD_AFBD_REG_OFFSET[plane]
    add r5, r5, #4              ; base + 4
    mov r2, #1                  ; value 1
    bl  io_accessor_write_reg
```

`OSD_AFBD_REG_OFFSET` dumped from `.rodata+0x280` is
`00016005 40016005` — `{0x05600100, 0x05600140}`. So the plane-0 latch is
**`0x05600104`**, plane-1's is `0x05600144`, which is the register our own KMS
driver already writes every flip.

**Retested with the latch, and with geometry.** ch1's `SIZE_M1`, `SIZE`,
`STRIDE` and `SRC` were mirrored into ch0 first, so that if the plane did open
it would scan valid pixels instead of address zero; then the config writes;
then `write 1 -> 0x05600104`.

```
open bit before latch: 0x00000000
open bit AFTER latch : 0x00000000
ch0 ctrl = 0x83001901   latch = 0x00000001
```

Still closed. And the latch **stayed set** — it does not self-clear, and
writing 0 to it does not clear it either.

### That last detail is the answer

```
0x05600144   ch1 latch   reads 0    -- consumed at each vsync
0x05600104   ch0 latch   reads 1    -- never consumed
```

Channel 1 is serviced by the pipeline, so its READY is taken every vblank.
Channel 0's READY is never taken. **Channel 0 is not part of the running
pipeline at all**, which is why every write to it is inert: not wrong values,
not a missing step in the sequence — an unserviced channel.

This is the "topology latch" model the 2026-08-14 poke campaign inferred, now
with a mechanical demonstration rather than an inference from nulls. And it
answers the question this file was opened to answer:

**The sequence does not work against a U-Boot-initialised pipeline, and no
CPU-side register sequence will make it, because the plane set is fixed before
Linux starts.** U-Boot's `h713_disp` loads the MIPS co-processor, and the MIPS
firmware programs the VBlender topology with one plane. The vendor's stack gets
two because *its* bring-up asks for two.

The stuck latch cleared on reboot; the board came back clean (`adopting
1280x720`, zero warnings) and plane 1 is unaffected throughout.

## Where that leaves it

Getting a video plane requires changing what the **MIPS bring-up** does — which
is open item 2, kernel-side panel init, the large port. It is not reachable by
driving `ge2d_dev.ko`'s plane registers from Linux, and this file should stop
anyone else spending a session finding that out.

Everything else here stands and is worth keeping: the extraction recipe, the
struct-offset map, the decoded 22-operation sequence, and the fact that
plane-init is a runtime-callable function rather than probe-only. If the MIPS
bring-up is ever ported, that is the sequence to run afterwards.
2. Replay the full sequence, not fragments of it. The single-register result
   above is the argument against further piecemeal poking.
3. Read the peer tree's `sunxi_ge2d_firmware.c` alongside step 1 — it has
   partial decodes of the same OSD registers (`0x0524c004` v_active,
   `0x0524c010` htotal+hsync, `0x0524c014` timing).

The peer tree's `sunxi_ge2d_firmware.c` has partial decodes of the same
territory (`0x05600140` dual-port bit, `0x0524c010` htotal+hsync,
`0x0524c004` OSD v_active, `0x0524c014` OSD timing) and is worth reading
alongside step 1 rather than after it.

## What would it take to make the MIPS do it? — answered 2026-08-25

The topology is not authored by MIPS code. **U-Boot programs it**, on the ARM
side, by replaying `LogoRegData.bin` before releasing the coprocessor. That file
is indexed: 13 project descriptors of 0x18 bytes from offset 0x10, each
selecting a *consistent triple* — prologue variant (3 exist), timing variant
(11), and **DE/mixer variant (8)**. Stock's order is prologue, timing, LVDS FIFO
reset, mixer write, DE table, clocks/INCAP/LVDS, coprocessor release, LVDS
finalise.

That made the question tractable, because if any DE variant configured a second
plane this would be a **table selection**, not a port. Records are
`{addr, val, mask, type}` u32 with 4-byte resync. Parsing every block:

```
block            recs   ch0   ch1  OSD0  OSD1
DE variant 0       55     0    13     0    14
DE variant 1       55     0    13     0    14
   ... variants 2-5 identical ...
DE variant 6       56     0    13     0    14
DE variant 7       56     0    13     0    14

ANY record anywhere touching ch0:  NONE
ANY record anywhere touching OSD0: NONE
```

**Not one record in the file touches channel 0 or OSD plane 0** — across all 8
DE variants, all 3 prologues and all 11 timing variants. Every shipped
configuration programs exactly one plane: ch1 (13 records) and OSD1 (14).

### So there is no configuration that gives a second plane

Not by selecting a different project, not by mixing tables. The vendor's own
bootloader data never opens one, on any variant, for any product in this family.

That also resolves the apparent contradiction with stock Android running
`ge2d_dev.ko`: the plane-0/plane-1 duality in that driver is **generic vendor
code**, and this product only ever uses plane 1. Our board's state — plane 1
open, plane 0 closed — is most likely stock's steady state too, not a
regression from it.

### What it would actually take

Authoring DE/mixer programming the vendor never ships: working out the layer
topology of an undocumented display engine well enough to add a second layer
from scratch, and applying it at bring-up before scanout starts. There is no
example to copy — which is the difference between a port and original bring-up
work on undocumented hardware.

**Recommendation: stop here.** The remaining payoff was never throughput — the
GPU path already sustains 59.71 fps against a ~58.9 fps vsync ceiling. It was
freeing the GPU and fixing stock clients, and stock clients are reachable far
more cheaply through the GPU path (open item 5). This thread is closed on
evidence, not fatigue.

## The attempt, 2026-08-25 — configured but never serviced

Made rather than argued about, after the "stop here" recommendation was
overruled. It got further than expected and then hit the same wall from a new
direction, which is worth recording precisely.

**Three things the DE-table dump corrected**, all of which undercut the earlier
reasoning:

1. **`0x0524c01c = 0x79860601` is *written* by the DE table.** The "plane open"
   word is not a hardware status readout — it is a value bring-up writes, and
   `tgd_is_plane_open()` reads back what was written. Every earlier test had
   treated it as a status bit.
2. **`init_osd_plane` never writes it.** So the plane-open test on this page had
   been applying the OSD configuration *without* the word that marks the plane
   open. That was a real gap, not a quibble.
3. **`0x05600000 = 0x80000020` is a global AFBD control** written first — which
   is where bit 31 actually lives, not on the per-channel ctrl.

Also: DE variants 1, 2, 5 and 6 all carry our 1280x720 geometry; variant 0 is
1920x1088. Earlier work using variant 0's values was using the wrong panel.

**What was applied**, from Linux, using DE variant 1 (our panel):

- all 12 AFBD ch1 records mirrored to ch0 (`addr - 0x40`)
- all 14 OSD1 records mirrored to OSD0 (`addr - 0x4000`), **including
  `0x0524801c = 0x79860601`**
- the plane-0 latch, `0x05600104 = 1`
- then, as a separate probe, global AFBD control bits: `0x80000030` (bit 4, on
  the theory that bit 5 gates ch1) and `0x800000f0`

**Result.** Plane 0's open word reads back `0x79860601`, identical to plane 1 —
the configuration takes. But:

```
0x05600144   ch1 latch   0    -- consumed every vsync
0x05600104   ch0 latch   1    -- never consumed, under every variation above
```

Channel 0 is fully configured, byte-identical to the channel that works,
carrying the open word, with the global control's low bits swept — and its
latch is still never taken.

**So the wall is not configuration.** It is not missing registers, wrong values,
the wrong DE variant, or the open word. Everything the vendor's own bring-up
writes for the working plane has now been written for plane 0, and the pipeline
still does not service it. Whatever admits a channel happens before this point
and is not in `LogoRegData.bin`, which contains no ch0 or OSD0 record anywhere.

Restored by reboot; board clean (`adopting 1280x720`, zero warnings), plane 1
unaffected, display verified.

**Not probed, deliberately:** the mixer block (`0x0525c000`–`0x0525c034`, 14
registers, with `0x0525c01c`/`0x034` and `0x0525c020`/`0x030` written as
identical pairs that may be two layer slots). That block *is* the live
compositor, so a wrong write there breaks the working display rather than an
idle channel — a materially different risk from everything above, and worth
taking deliberately rather than incidentally.

### The mixer probe — also negative

The mixer decodes cleanly and does have two window slots. Live values, which
differ from the table because something rewrites them for 720p after the
replay:

```
0x0525c01c / 0x0525c034 = 0x0500003C   width 1280, x-offset 60   (pair)
0x0525c020 / 0x0525c030 = 0x02D00016   height 720, y-offset 22   (pair)
0x0525c004 = 0x00001402                table wrote 0x00001003
```

The low bits of `0x0525c004` looked like a layer-enable mask: the table writes
`0b11`, the live value is `0b10`, i.e. layer 0 enabled at bring-up and cleared
afterwards. Setting bit 0 back (`0x1403`) with plane 0 fully configured and its
source pointed at the U-Boot logo buffer:

- the write takes and reads back
- `0x05600104` still never consumed
- **operator confirms: console text unchanged, no logo, nothing composited**

So layer 0 is inert end to end — not merely unlatched at the AFBD level, but
producing nothing through the DE/mixer path either.

### Where the attempt got to

Everything the vendor's own bring-up writes for the working plane has now been
applied to plane 0 from Linux, and verified reading back: all 12 AFBD channel
records, all 14 OSD records including the open word `0x79860601`, the latch,
the global AFBD control low bits, and the mixer layer-enable bit. The pipeline
services channel 1 and ignores channel 0 under every combination.

**The one variation not tried is timing, not content.** Every write above
happened *after* bring-up. The topology model predicts the writes must land
*during* the sequence, before scanout starts — and that cannot be tested from
Linux or from the U-Boot prompt, both of which are post-bring-up. It needs
`h713_disp` itself extended to emit the mirrored ch0/OSD0 records at the right
point, which means building a modified U-Boot.

That does **not** require flashing the bootloader: FEL-booting a modified
U-Boot tests it without touching the flashed one, which keeps the riskiest
write in the project off the table.

**Confirmed under observation.** The mixer bit was re-toggled with 15-second
dwells, long enough that a steady change would be as visible as a transient,
with the operator watching: no flash, no change, either cycle. Layer 0 is inert.

### The flash, and a process note

An unexplained flash was reported mid-session, with the operator specifying it
happened while the Linux prompt was already up — **not** during the U-Boot to
Linux transition, which rules out the bring-up flash.

It was the verify step used throughout this page: `videotestsrc num-buffers=1
! kmssink` puts a single frame on the panel and exits, and on an idle login
prompt that reads as a flash. **Confirmed by controlled re-run**, not by
assumption: 8 s of steady panel, one frame at 19:46:39, 6 s steady, a second
frame at 19:46:45 — operator reported exactly two flashes.

Check the display path with a register read instead. It answers the same
question without writing to the screen.

**The process note is the more useful part.** That explanation was first
written into this document as "traced to", before any test had been run. It
happened to be right. Had it been wrong it would have sent the next reader
chasing a phantom, in a document whose whole value is separating what was
measured from what was assumed. The same slip appears twice earlier on this
page — bit 31 called a commit enable on a value comparison, and the mixer pairs
called layer slots before they were toggled. Both were labelled as inference at
the time; this one was not.

## Bring-up-time injection: the cheap version, and why it fails

The FEL route turned out to be blocked before it started: `docs/flash.md`
records that **`sunxi-fel uboot` does not work on H713** — the SPL loads, but
the post-SPL handoff is broken. So FEL-booting a modified U-Boot is not
available, and code changes would mean flashing the bootloader.

But the existing U-Boot already exposes enough to test the timing hypothesis
with no rebuild at all:

```
h713_disp teardown   - stop scanout, park the MIPS, drop the panel rail
h713_disp init <id>  - bring the display up and stop
```

The DE table only writes ch1, so pre-setting ch0/OSD0 while the pipeline is
*down* should have survived into a freshly started pipeline. Tried it: teardown,
then all 26 ch0/OSD0 mirror writes via `mw.l`, then `init 0x34`.

**`init` zeroes them.**

```
after init:  0x05600100 = 0x00010000   (pre-set 0x03001901 gone)
             0x0524801c = 0x00000000   (open word gone)
             0x05600140 = 0x03001901   ch1 normal
             0x0524c01c = 0x79860601   plane 1 normal
```

The bring-up sequence clears the channel registers on its way through — almost
certainly the prologue, which runs before the DE table. So there is no window
between "pipeline down" and "pipeline up" that a CPU-side write can occupy: the
sequence overwrites anything staged beforehand, and everything after it is
post-bring-up, which is the case already shown not to work.

**Injection therefore requires modifying the sequence itself**, i.e. changing
`h713_disp` and running the result. With FEL boot unavailable on this SoC, that
means flashing the bootloader — the riskiest write in this project, and the one
the display handoff explicitly says to decide deliberately.

That is where this stops being a probe and starts being a commitment. Two other
practical notes from the attempt: `init` prints "Power-cycle before another
init", so this is one shot per boot; and `--wait` in `tools/serial/console.py`
is a *per-command* dwell, so chaining with `;` is required for long register
sequences rather than passing many arguments.

Board returned to Linux and verified: ch1 `0x03001901`, plane 1 open, mixer
`0x1402`, panel on the login prompt, zero warnings.

## THE DECIDING EXPERIMENT — bring-up injection, 2026-08-25

The bootloader was flashed to run the mirror writes *inside* the bring-up
sequence, which was the one placement never tested. Result: **negative, and
conclusive.**

### Method

`h713_disp_run()` gained 26 register writes plus the plane-0 latch, injected
immediately after the DE-table replay and before the clocks/INCAP/LVDS tail —
the same point stock's own order would use. Values are DE variant 1 (this
panel's 1280x720) shifted ch1 → ch0 by `-0x40` and OSD1 → OSD0 by `-0x4000`.

Only **U-Boot proper** was rewritten, at LBA `0x49ac00` in the `empty`
partition. The contended first stage at LBA `0x10` was never touched, which
keeps the bricking risk off the table entirely. Write verified byte-for-byte on
readback, with the outgoing image backed up to `/root/uboot-backup/` and to the
host first.

### Result

At bring-up, immediately after the DE table:

```
H713 plane0: mirrored 26 registers onto ch0/OSD0, ctrl=03001901 latch=00000001 open=79860601
```

With Linux fully up — past the clocks/INCAP/LVDS tail, the MIPS release and
live scanout:

```
ch0 ctrl = 0x03001901   ch0 latch = 0x00000001   survived bring-up, NEVER consumed
ch1 ctrl = 0x03001901   ch1 latch = 0x00000000   consumed every vsync
plane0   = 0x79860601   plane1    = 0x79860601   identical
```

**Placement was the real variable, and it is now controlled for.** The
configuration survives when injected here, unlike the teardown/init attempt
where the prologue zeroed it. So this is the first test where channel 0 entered
live scanout fully and correctly configured — and its latch is still never
taken. Operator confirms the panel shows the console only: no logo, no blend,
despite ch0 pointing at `0x6c100000`.

### What that settles

The plane set is **not determined by these registers at all.** Not the AFBD
channel block, not the OSD block, not the open word, not the mixer enable, and
not the timing of any of them. Every register the vendor's own bring-up writes
for the working plane has now been written for plane 0, at the same point in
the same sequence, and the pipeline ignores it.

What remains is the one thing this project replays rather than authors: the
MIPS firmware's own VBlender programming. `LogoRegData.bin` contains no ch0 or
OSD0 record in any of its 8 DE variants, 3 prologues or 11 timing variants —
the vendor never opens a second plane on this product, and the plane count is
fixed by `display.bin` before any of these registers matter.

### Two notes for whoever reads this next

**The env gate was wrong and the experiment ran anyway.** `env_get_yesno()`
returns **-1** when a variable is unset, not 0, so `if (!env_get_yesno(...))
return;` does not gate anything — it only suppresses on an explicit `n`. The
injection ran on a boot intended as a control. It was harmless and produced the
result early, but the "safety flag" was not one.

**Restoring was clean.** The backup was written back to the same LBA, verified
identical, and the board rebooted on `U-Boot 2026.07-rc5-gdbad200ca799` with no
injection line, the logo published, and zero warnings. Board state afterwards:
ch0 idle `0x00010000`, OSD0 zero, plane 1 open, mixer `0x1402`, WiFi noise 0,
oops 0, panel on the login prompt.

The U-Boot source change was reverted; the submodule carries only its
pre-existing defconfig change. The register table above is the artifact worth
keeping — if `display.bin` is ever replaced or its VBlender programming
understood, that is the sequence to apply, and it is now known to survive
bring-up when applied at this point.


---

## SUPERSEDED FRAMING — read this before acting on anything above

Everything above investigates "why can we not open a second plane". Late on
2026-08-25 that framing was shown to be wrong.

The vendor's `panel_config.ini` (beside the MIPS firmware) says
`PanelDualPort = 0`, with `PanelODDDataCurrent`/`PanelEvenDataCurrent` present —
odd/even LVDS lanes. The peer project decodes `0x05600140` as carrying a
`dual_port` bit. **AFBD "channel 0" and "channel 1" are most likely the odd and
even LVDS ports, not compositing layers.**

Confirmed in hardware: the operator drove this panel from a Geekworm
HDMI-to-LVDS board as **1-port LVDS**. And all 8 DE variants carry identical
`ctrl=0x03001901` / `global=0x80000020` across every resolution — port config
never varies.

So channel 0 is unused hardware on a single-port panel. The register-level work
above is still accurate and worth keeping; its *conclusion* — that something
mysterious refuses to service a configured plane — has a mundane answer. The
goal is a **serviced YUV fetch route on the one working channel**, not a second
plane. See `plane-brief-for-external-review.md` section 10 and
`handoff-2026-08-25.md`.

---

> ## ⚠ SCOPE CORRECTION — 2026-08-25, later the same day
>
> **The section below over-closes. Read this first.** An external agent review
> went over it and was right on the scope; two of its claims were then verified
> here on the live board and by arithmetic:
>
> - **`0x05600320` = `0x4C7ED000` and `0x05600324` = `0x4CDEA000`** — a
>   non-zero address pair in the AFBD window, holding live DRAM addresses that
>   neither our driver nor patch 0066 ever writes. So *"the register space is now
>   covered, there is nothing left to permute"* below is **false**, and
>   *"do not run a fourth variant"* was bad advice. Nearby at `0x05600300`–`0x31c`
>   is a repeating 8-byte structure (`00800210`/`00800000`, `00800210`/`0080C258`,
>   `00800210`/`0`) consistent with queue slots.
> - **The photograph cannot identify *why* the fetch stayed packed.** It proves
>   the fetch was linear 32-bit under the tested recipe. It cannot distinguish
>   "UI channel, RGB-only in silicon" from "`3` is the wrong format encoding" or
>   "the recipe is incomplete — queue slots, info descriptors, an enable/bypass
>   or a mux". The claim below that this *proves* the 2026-08-14 UI-channel
>   inference asserts a specific cause for a null result, and does not follow.
>   Row 3 remains a three-point fit (rows 0/6/7), not an established encoding.
>
> **The correctly scoped conclusion:** direct NV12 does not work through the
> tested AFBD_SRC channel recipe, and the active channel remains a packed 32-bit
> fetch. Whether some *other* AFBD/DECD/video-plane configuration gives no-GPU
> YUV scanout is **open**.
>
> What survives unchanged: `0x170`/`0x178` do control the live fetch (new, and it
> corrects 0065); the fetch was linear 4 bytes/pixel under this recipe; and
> 0065's "SEPARATE video plane" postmortem was wrong about the global/channel
> offset split. The reviewer's own perspective-corrected read of the photograph
> *confirms* the band arithmetic and refines it — Y ends row 180 predicted vs
> ~183 observed, UV 270 vs ~276, and the 2 MiB allocation boundary at 409.6 vs
> ~419, which also explains the white band and the flashing.
>
> **And the vendor never writes the format selector alone.** `patches/kernel/0013`
> reconstructs `dec_reg_video_channel_attr_config()`, the *only* writer of
> `afbd + 17` (= `0x011`) in the whole driver. Every write is accompanied by:
>
> ```c
> writeb(b16 | 0x10,  base + 16);        /* uncompressed: bit 4 of 0x10 */
> writeb(6,           base + 17);        /* selector */
> writeb((b19 & 0x78) | 3 | ((val & 1) << 7), base + 19);
> writel(2 * cfg[2],  base + 64);        /* plane strides = 2 * width */
> ```
>
> plus `dec_reg_mux_select()` (a 2-bit **mux** at `workaround + 8`, written into
> bits [1:0] *and* [5:4]), `dec_reg_top_enable()` (a separate `top` block and
> `afbd + 0x03` bit 7) and `dec_reg_enable()` (`workaround` +0/+9/+100).
> **Patch 0066 called none of these and does not even map the `top` or
> `workaround` windows.** Codex's "enable/bypass controls, or another mux" is
> confirmed by our own reconstruction. (`0x10` and `0x13` were, as it happens,
> already in the uncompressed configuration — live bytes `0x10` and `0x03` —
> so those two were not the blocker.)
>
> **The selector really is a row index, so our 0066 value was defensible.**
> Vendor `mode` is a format_id: `mode == 1` (row 6) writes selector **6**, and
> `mode == 20` (row 7) writes selector **7**. Selector value equals row index in
> both cases, which confirms the row-index reading in `video-decode.md` rather
> than overturning it. The vocabulary the vendor actually emits is `{1, 6, 7}`,
> and row 3 is one of *four* 8-bit entries (rows 0–3, format_ids 6/4/2/0); the
> claim that 8-bit NV12 is specifically row 3 rests on elimination, not evidence.
>
> See "The DECD ABI is broken by construction" below.

## THE YUV FETCH QUESTION IS CLOSED — 2026-08-25, negative

The reframed goal above lasted a few hours. Patch 0066 answered it on hardware
and the answer is no: **there is no register write to the AFBD window that makes
the live channel fetch YUV.**

### Why the two earlier nulls did not settle it

Each wrote half the register set, and neither could speak for the other.

| | `0x011` fmt | `0x040/44` plane strides | `0x070/084` Y/C addrs | `0x170/178` channel | result |
| --- | --- | --- | --- | --- | --- |
| yuvtry, 08-09/12/14 | yes | yes | **no** (read 0) | yes | 4x repeat, greyscale |
| patch 0065, 08-25 | yes | yes | yes | **no** (skipped) | panel unchanged |
| **patch 0066, 08-25** | yes | yes | yes | yes | **4x repeat, and the proof** |

0065's postmortem concluded those registers drive "a SEPARATE video plane". That
was wrong, and the offsets say so: the AFBD channel stride is `0x40`, so channel
0 begins at `0x100` and channel 1 at `0x140`. Everything at
`0x011/0x040/0x044/0x06c/0x070/0x084` sits *below* that, in global space common
to the window, and does reach the live fetch. 0065's null was not evidence about
YUV — it was evidence that a channel nobody repointed keeps scanning what it
already had (`0x1400`, `0x76D00000`, the fbcon framebuffer).

### What 0066 established

Both halves confirmed in hardware simultaneously, read back live mid-stream:
format byte `0x11` = `03`, plane strides 1280/1280, Y = `0x77300000`,
C = `0x773E1000`, **channel stride `0x500` and channel source on the luma
plane**, ctrl `0x03001901`, READY consumed every vsync, AFBD IRQ advancing.

The panel showed the 4x repeat again — `local/lcd-photos/test_57/IMG_0728.MOV`.

**The `chan_stride` sweep is what makes it decisive.** A packed 4-bytes/pixel
fetch predicts both settings exactly:

- **1280** — 720 rows × 1280 B = 921600 B, precisely the luma plane. The whole
  screen is luma, so *all greyscale*, 4x repeat. Observed exactly that.
- **5120** — rows now advance and consume 5120, walking the buffer contiguously.
  Luma fills 921600/5120 = **180 rows**, chroma (1280×360 = 460800 B) fills
  460800/5120 = **90 rows**, then unrelated memory. Predicts a luma band over a
  chroma band at a **strict 2:1 height ratio**, then white. Measured off the
  photograph: **~115 px over ~60 px, i.e. 1.9:1**, hand-held and off-axis. The
  green/magenta is interleaved UV read as packed BGRA.

So `0x170` **is** honoured — it moved the band boundaries to where the
arithmetic put them — and `0x011` **is not**. The fetch stayed 4 bytes/pixel
with the selector reading `03` throughout, and the hardware walked the NV12
buffer linearly as one packed RGB surface, never as two planes.

### The standing conclusion

> **Superseded 2026-08-26.** Patch 0066 proves only that this serviced OSD fetch
> remained packed 32-bit under that recipe. It does not prove that the SoC has
> no other hardware YUV path, or that the GPU is its only colour-conversion
> engine.

The corrected, stock-shaped `/dev/decd` test has now exercised a separate
hardware video queue at 59.7 Hz with zero panfrost interrupts. Its Y, C and
VideoInfo addresses reached the four-slot register file, but its output was not
routed to the panel: the U-Boot OSD stayed visible, and hiding it produced
black. DECD's internal blue generator also remained black, eliminating the
submitted NV12 data and metadata as causes.

> **The paragraph below was wrong and is retracted — see "ioctl `0x4631` is the
> RGB OSD flip" further down.** `tgd_put_plane_info()` was disassembled in full
> on 2026-08-26. It has no YUV format and never touches a DECD register. It is
> not the missing companion operation.

Stock Android supplies the missing operation. HWC pairs the DECD frame submit
with `/dev/ge2d` ioctl `0x4631`, passing an 80-byte `_plane_info`; stock
`svp_ioctl` calls `tgd_put_plane_info()` for that command. The next experiment
is therefore a controlled reproduction of this paired queue-plus-plane commit
under one MMIO/IRQ owner. More format/address permutations on the adopted packed
OSD channel are not useful.

The mpv `render_fd` path remains a useful zero-copy compatibility fallback, but
it uses panfrost for YUV-to-RGB. It is not evidence against, or a replacement
for, the now-confirmed DECD no-GPU hardware route.

---

## The DECD ABI is broken by construction — 2026-08-25

This is why the earlier DECD experiments could not establish anything, and it is
independent of everything above.

`DECD_IOC_FRAME_SUBMIT` is `0x40706400`. Decoding it is arithmetic:
dir = `_IOC_WRITE`, type = `0x64` = `'d'`, nr = 0, **size = `0x070` = 112 bytes**.

`struct dec_frame_submit_desc` in patch 0013 is **128 bytes**. Computed offsets:

```
linear     +0x00     align      +0x40
image_fd   +0x04     info_fd    +0x4c
format     +0x08     field_sel0 +0x64
width      +0x28     field_sel1 +0x68
height     +0x2c     y_phys     +0x70   <-- past the 112-byte transfer
                     c_phys     +0x78   <-- past the 112-byte transfer
```

Every field up to byte 112 matches the stock layout recovered from the vendor
HWC. **`y_phys` and `c_phys` do not — they sit entirely outside the bytes the
ioctl copies, so the physical addresses our client sets can never arrive.** Any
result from the "linear physical address" path is therefore uninformative: it
was never testing what it claimed to test.

Two further defects reported by the reviewer have now been verified against
stock HWC and `decd.ko`:

- the repeat count is at header `+0x10` in stock; our `dec_ioctl_header` has
  `arg0` at `+0x10` and `arg1` at `+0x18`, and the driver reads `+0x18`;
- stock leaves the flag at `+0x68` always zero and submits **two dma-buf FDs**
  (pixels plus a 32 KiB VideoInfo block) rather than raw physical addresses, so
  setting `+0x68` enters a branch stock never exercises.

**And stock userspace does consume DECD.** The repo has said the opposite in
several places — `video-decode.md` ("DECD probes and works but has no job"),
`kms-display.md`, and `plane-brief-for-external-review.md` §10 (an "AFBC
playback dead end"). Disassembly verifies stock HWC issuing this ioctl from
`DecoderDisplay::present()` for ordinary video. The call site was missed because
the immediate is assembled as `movw 0x6400` / `movt 0x4070` and a byte-pattern
search does not see it. This is the same class of method failure the project
already documented as "relocations are calls too" in the
`tgd_init_planesetting` caller analysis.

### Hazards for whoever tests DECD next

- DECD's node is `disabled` and **our KMS driver owns the `0x05600xxx` window and
  the IRQ** (`kms-display.md`, "What this cost DECD, and why"). Loading DECD
  means two owners for one register window; decide the owner first.
- **DECD's runtime suspend resets the display** (`video-decode.md`, 2026-08-14):
  `dec_disable()` asserts the display reset, and this KMS driver cannot bring the
  panel back. That is a dark projector until reboot, not a soft failure.

---

# ioctl `0x4631` is the RGB OSD flip — 2026-08-26

`tgd_put_plane_info` has now been disassembled end to end rather than inferred
from its callers. **It cannot route DECD output to the panel**, and the "port
the `0x4631` path and run a paired one-frame test" plan recorded above and in
the two companion docs is withdrawn. Doing it would have reimplemented what
`sun50i-h713-afbd` already does on every atomic flip.

Stock `decd.ko` was extracted alongside it, by the same recipe as `ge2d_dev.ko`
but `dump /lib/modules/decd.ko` — 97936 bytes, ARM 32-bit, **unstripped, 835
symbols**, SHA-256
`42dece532c7088a2ce5d9462ca2daf0905ccf14413c299d389f8eb067d2bfb49`. Having both
sides with symbols is what made this tractable; `patches/kernel/0013`'s
reconstruction was previously named from an IDA session nobody kept.

## What the ioctl surface says on its own

`svp_ioctl`'s full dispatch table, recovered by matching each `movw r3, #0x46xx`
to its branch target and the first call there:

| cmd | payload | handler | cmd | payload | handler |
| --- | --- | --- | --- | --- | --- |
| `0x4601` | 160 | `svp_set_var` | `0x4640` | 8 | `tgd_set_vmirror` |
| `0x4602` | — | `svp_get_fix` | `0x4641` | 8 | `tgd_set_vinterpolation` |
| `0x4604` | 24 | `svp_get_cmap` | `0x4650` | 4 | `InitFBManagement` |
| `0x4605` | 24 | `svp_set_cmap` | `0x4651` | 4 | `DestroyFBManagement` |
| `0x4630` | 80 | `tgd_get_plane_info` | `0x4652` | 16 | `AllocateFB` |
| `0x4631` | 80 | `tgd_put_plane_info` | `0x4653` | 4 | `FreeFB` |
| `0x4632` | 8 | `tgd_show_plane` | `0x4660` | 28 | `tgd_set_plane_cmap` |
| `0x4633` | 12 | `tgd_flip_plane` | `0x4661` | 28 | `tgd_get_plane_cmap` |
| `0x4635` | 4 | `tgd_set_fastlogomode` | `0x4670` | 8 | `ion_alloc` |
| `0x4680` | 4 | `_dev_info` | `0x4671` | 8 | (fence list) |
| `0x4681` | — | `sunxi_enable_device_iommu` | `0x4777`/`0x4778` | 8 | `get_afbd_wb_inst` |

That is an fbdev-shaped graphics device: screeninfo, colour maps, framebuffer
allocation, plane flip, writeback. **There is no video-layer ioctl.** The
`0x4631` half of stock HWC's per-present pair is HWC committing its *UI* layer;
the `/dev/decd` half is the *video* layer. Two layers, not two halves of one
operation — which is what a hwcomposer does, and is the whole of the "vendor
division of labour" the earlier note read as a missing companion call.

## The 80-byte `_plane_info`

Twenty `u32`s. Field roles from the uses in `tgd_put_plane_info`:

| off | meaning |
| --- | --- |
| `+0x00` | plane id, 0 or 1; anything else reaches `panic("Invalid osd id: %d")` |
| `+0x08` | colour format, 0–3 (see below) |
| `+0x28` | AFBC-compressed flag → channel `ctrl` bit 31 |
| `+0x2c` / `+0x30` | source width / height |
| `+0x34` / `+0x38` | y / x offset, folded into the source address |
| `+0x3c` / `+0x40` | second width / height pair, written to channel `+0x34` |
| `+0x44` | FB handle: `>= 0` → `ge2d_create_osd_frame()`; `< 0` → use `+0x48` |
| `+0x48` | direct source DRAM address |
| `+0x4c` | **out**: release-fence fd from `osd_fence_fd_create()` |

`+0x04`, `+0x0c`, `+0x10`–`+0x24` carry geometry consumed by the scaling and
resolution code. On success the whole record is `memcpy`'d into
`Plane_Setting[id]` and copied back to userspace.

**Bit 31 is finally explained**: it is `+0x28`, the compressed flag. That
retires the "same value with bit 31 set" puzzle in Finding 3 — stock's
`init_osd_plane` writes `0x83001901` because it brings its framebuffer up
AFBC-compressed, and the live `0x03001901` is the same plane uncompressed. It
was never a commit enable.

## The colour formats are RGB-only

`+0x08` indexes a four-entry bytes-per-pixel table at `.rodata+0x00`, then
selects the value for `ctrl[15:8]`:

| `+0x08` | bytes/pixel | `ctrl[15:8]` | format |
| --- | --- | --- | --- |
| 0 | 4 | `0x19` | 32-bit |
| 1 | 4 | `0x19` | 32-bit |
| 2 | 3 | `0x17` | 24-bit |
| 3 | 2 | `0x18` | 16-bit |

Anything else falls into `printk("Invalid colorformat %d for GD!")`. Live ch1
holds `0x03001901`, i.e. `0x19` — the 32-bit entry. **There is no YUV format,
no chroma plane, and no second address anywhere in the ioctl.**

## Everything it writes

For plane 1 the base table is `OSD 0x0524c000`, `AFBD ch 0x05600140`,
`0x05280080`, `0x0529c000`, VBlender `0x05200034`, LVDS `0x051c006c` /
`0x051c019c`; plane 0's set is the `-0x40`/`-0x4000` mirror already in the
struct-offset map above. The commit path is:

```
0x051c0010      bits 24:23 cleared, set, cleared      LVDS FIFO reset pulse
0x0524c04c      written                                (resolution path)
0x05600140      bit 31    = plane_info[+0x28]          compressed
0x05600140      bits 15:8 = 0x19 / 0x17 / 0x18         format
0x05600150      = ((align16(h)-1) << 16) | (align16(w)-1)
0x05600154      = ((h_blk-1) << 16) | (w_blk-1)
0x05600170      = bytes_per_pixel * width              stride
0x05600174      = (plane_info[+0x40] << 16) | bpp * plane_info[+0x3c]
0x05600140      bits 3:2  from a per-plane driver flag
0x05600178      = source DRAM address                  <- the fetch pointer
0x05600140      bit 0     = 1                          enable
0x05600144      = 1                                    osd_ready_for_update
```

Then `osd_wait_update_finish`. Additional writes to `0x05200034/38`,
`0x051c006c/70` and `0x05240030/34` sit on the "reset vsync delay" sub-path,
not the per-frame commit.

Two negative facts worth as much as the positive ones:

- **`ge2d_dev.ko` never touches `0x05600060`–`0x056000ff`** — DECD's queue and
  `workaround` block. Verified by resolving every `movw`/`movt` immediate in the
  module that lands in `0x05000000`–`0x06000000`.
- **`ge2d_dev.ko` never writes the mixer.** `0x0525c000` appears twice: once in
  `init_svp` storing the base, once in `__get_panel_resolution` *reading*
  `0x0525c01c`/`0x020` for the panel size. The mixer remains the MIPS's.

## What this means for the AFBD register window

The writeback engine gives the block's own view of itself, and it is the most
useful thing in either binary. `__afbd_is_ch_en(id)`, `__afbd_get_pixel_fmt(id)`
and `__afbd_get_pic_size(id)` take **three** ids:

| id | ctrl reg | enable | pixel format | picture size |
| --- | --- | --- | --- | --- |
| 0 | `0x05600010` | bits **1:0** | bits 15:8 | `0x05600030` |
| 1 | `0x05600100` | bit 0 | bits 15:8 | `0x05600134` |
| 2 | `0x05600140` | bit 0 | bits 15:8 | `0x05600174` |

Ids 1 and 2 are the two OSD channels. **Id 0 is the video source, and it is
exactly what DECD programs**: `dec_reg_video_channel_attr_config` writes
`afbd + 0x10` bit 4, the format selector at `afbd + 0x11` (= `0x05600010`
bits 15:8), `afbd + 0x13`, the sizes at `+0x20`–`+0x26` and the plane strides at
`+0x40`/`+0x44`. Three sources with the same (enable, format, size) shape, one
of which is fed by the decoder.

### This gives patch 0066's null a mundane explanation

0066 wrote **source 0's** format byte at `0x05600011` and then observed
**source 2's** fetch at `0x05600140`/`0x170`/`0x178`. Those are different
sources. The channel honoured its own stride and ignored a format field that was
never its own, which is precisely the photographed result. The experiment
configured one source and measured another; it could not have answered the
question either way, and the scope correction above that refused to close it was
right for a reason nobody had yet identified.

### The gap that is actually open

**Nothing we have ever run sets `0x05600010` bits 1:0** — source 0's enable, by
the vendor's own accessor. Neither does stock `decd.ko`: its only writes to that
byte are bit 4 in `dec_reg_video_channel_attr_config`. Neither does
`ge2d_dev.ko`. So the video source's enable is set by something else — the MIPS
bring-up, the U-Boot replay, or reset default — and its live value has never
been read on this board. The 2026-08-26 DECD boot recorded `0x05600011 = 0`, the
format byte, but not the low half of the same word.

That makes the next step a **measurement, not another permutation**:

1. Read `0x05600010`, `0x05600030` and `0x05600140` on a running board, then
   again with DECD submitting frames. Three registers, no writes.
2. Read the same three under stock Android playing video (`run switch_vendor`).
   The diff between "Android idle" and "Android playing" answers the routing
   question outright, and is the capture both companion docs have been asking
   for in a less specific form.

## Step 1 done — the video source is provisioned and switched off

Read on the production kernel, 2026-08-26, DECD not loaded, panel on the login
prompt. `busybox devmem`, no writes.

```
0x05600000 0x80000020    AFBD global
0x05600010 0x03000010    source 0 ctrl     <- enable bits 1:0 = 0
0x05600020 0x043F077F    source 0  w-1 = 1919, h-1 = 1087
0x05600024 0x00420077    source 0  (w-1)>>4 = 119
0x05600030 0x02D00500    source 0 size     1280 x 720
0x05600040 0x00000780    source 0 plane stride 0 = 1920
0x05600044 0x00000780    source 0 plane stride 1 = 1920
0x05600060 0x00000001    DECD enable       bit 0 SET
0x05600064 0x00000000
0x05600068 0x00000122    DECD mux          bits 1:0 = 2, bits 5:4 = 2
0x0560006c 0x00000000    dirty
0x05600070 0x00000000    Y   (nothing queued)
0x05600084 0x00000000    C
0x05600100 0x00010000    ch0 ctrl          disabled
0x05600104 0x00000000    ch0 latch
0x05600134 0x00000000    ch0 size          unconfigured
0x05600140 0x03001901    ch1 ctrl          enabled, format 0x19
0x05600144 0x00000000    ch1 latch         consumed every vsync
0x05600170 0x00001400    ch1 stride        5120
0x05600174 0x02D01400    ch1               (720 << 16) | 5120
0x05600178 0x76D00000    ch1 source        fbcon
0x05600300 0x00800210    queue slot
0x05600310 0x00800210    queue slot
0x05600320 0x4C7ED000    live DRAM address, written by nothing in our stack
0x05600324 0x4CDEA000
```

**The answer to the question this section opened with: bits 1:0 of `0x05600010`
are zero.** By `__afbd_is_ch_en(0)`, the video source is disabled.

**And it is disabled in a block that is otherwise already turned on for it.**
`0x05600060` bit 0 is set — DECD's own enable — and `0x05600068` holds `2` in
both mux fields, which is exactly what stock's `dec_decoder_display_init()`
writes (`dec_reg_mux_select(regs, 2)`). DECD is not loaded on this kernel and
our KMS driver writes none of these, so **U-Boot's bring-up left the video path
enabled and mux'd, with the source itself switched off**. `0x05600010` bit 4 is
also set, the uncompressed bit that `dec_reg_video_channel_attr_config` sets.

Two things this is worth being precise about:

- **The enable is not on the live channel.** `0x05600010` and `0x05600140` are
  different sources. Setting bits 1:0 does not write the register the panel is
  currently scanning from, which makes it a much smaller risk than the mixer
  probe that was deliberately deferred earlier on this page.
- **Its geometry is currently inconsistent.** `0x05600030` says 1280x720 (our
  panel) while `0x05600020`/`0x024` say 1920x1088 and the plane strides at
  `0x40`/`0x44` say 1920 — stock's framebuffer geometry, the same 1080p trap the
  replay note above flags. Whoever enables this source has to reconcile them
  first; DECD rewrites `0x20`–`0x26` and `0x40`/`0x44` per frame, `0x30` it does
  not touch.

**This also confirms the `tgd_put_plane_info` decode against live silicon.** The
two formulas recovered from the disassembly predict the live channel exactly:
`0x170` = bytes-per-pixel × width = 4 × 1280 = `0x1400`, and `0x174` =
`(height << 16) | (bpp × width)` = `(720 << 16) | 5120` = `0x02D01400`. Both
match to the bit, on a channel the vendor driver has never touched on this
board.

One correction to the three-source table above, from these values: for ids 1
and 2 the "size" register holds a **byte stride** and a height, not a pixel
width (`0x174` = 5120, not 1280), while id 0's `0x030` holds true pixel
dimensions. Consistent with id 0 being a planar source and ids 1/2 packed.

## Step 2 — the enable test, built and staged 2026-08-26

`tools/video/decd-enable-test.sh`, staged on the board at
`/root/decd-enable-test.sh`. It writes **only** `0x05600010`, **only** bits 1:0,
read-modify-write, and restores on every exit path including Ctrl-C. That is not
the register the panel scans from (`0x05600140`), which is what makes it a much
smaller risk than the mixer probe deferred earlier on this page.

**The gate is the point of the script.** It refuses to touch the enable until it
has proven frames are flowing — DECD IRQ advancing at ≥30/s and a non-zero Y in
the queue register. The 2026-08-25 mixer layer-0 test was run with DECD idle, so
it had nothing to composite and could not have shown anything either way; this
gate is what stops that from happening twice. It also refuses to run at all if
`/dev/dri/card0` exists, since KMS and DECD cannot both own `0x05600000` and
SPI 110 (verified: it correctly refuses on the production kernel).

It sweeps enable = 1, 2, 3 with an operator dwell at each, dumping the same
18-register set every time so observations are comparable. `--hide-osd` is
opt-in and additionally clears ch1 bit 0, blanking the panel until restore.

**Transient boot path — nothing to persist or restore.** The FAT at `mmc 1:2` has
only 3.4 MB free, too little for a second 7.7 MB FIT, but the test kernel is
already in the ext4 rootfs. Verified working:

```
reboot bootloader
mmc dev 1
ext4load mmc 1:1a 0x50000000 /root/h713-kernel-decd-test.fit
bootm 0x50000000
```

**`1a`, not `26` — U-Boot parses the partition number as hex.** `mmc 1:26` is
partition 0x26 = 38 and fails with `** Invalid partition 38 **`. The load itself
takes 497 ms at 14.9 MiB/s. A plain power cycle returns to the production kernel
because `bootcmd` still reads the FAT.

Then on the target:

```
insmod /root/sunxi-decd-test.ko
/root/decd-enable-test.sh /root/decd-test-frame.nv12 --dwell 15
```

A built-in check worth watching: after submit, `0x05600020` should read
`0x02CF04FF` (1280x720). If it still reads `0x043F077F` then DECD did not
reconfigure the source and it is still carrying stock's 1920x1088 — which the
live read found there, and which would need fixing before a null means anything.

**A readback that does not take is itself a result.** It would mean bits 1:0 are
gated rather than merely unset, which is a different answer from "enabled and
still nothing".

## Step 2 result — NEGATIVE, and properly gated this time (2026-08-26)

Run on the 0068 boot, DECD bound, operator watching. Enable swept 1, 2, 3 at
20 s each.

```
DT: display@5600000=disabled, dec@5600000=okay
DECD irq: 18568 -> 18688 over 2 s  (~60/s, expect ~60)
queued Y=0x6C500000  C=0x6C5E1000
readback 0x03000011 / 0x03000012 / 0x03000013   (all took)
```

**Operator: no change at any of the three values. The panel showed the U-Boot
logo throughout.** Every register outside `0x05600010` was unchanged across all
four dumps, `ch1_ready` stayed consumed, and `mixer_en` stayed `0x00001402`.

Unlike the 2026-08-25 mixer test, this null means something: frames were
demonstrably flowing at the vsync rate with valid Y/C in the queue registers
before the enable was touched, and the enable demonstrably took. So:

- **bits 1:0 are writable, not gated** — they were simply never set, and setting
  them is **not sufficient** to route DECD to the panel.

### The finding that came out of the failed geometry check

The script flags `src0_wh` staying `0x043F077F` (1920x1088) instead of becoming
`0x02CF04FF` (1280x720). That check was written expecting DECD to reprogram the
source per frame. **That expectation was wrong, and being wrong is the useful
part.**

`dec_reg_video_channel_attr_config` — the only writer of the format selector at
`0x05600011` and of `0x20`–`0x26`, `0x40`/`0x44` — is **dead code in stock
`decd.ko`**. Zero relocations reference it (positive control:
`dec_reg_mux_select` shows 1, from `dec_decoder_display_init`), its address is
never taken, and `decd.ko` has **no `__ksymtab` at all**, so nothing outside the
module can reach it either.

So our port not calling it mirrors stock exactly, and the inconsistent geometry
(`0x20` = 1920x1088 vs `0x30` = 1280x720) is not a defect we introduced — both
values were present in the 2026-08-26 production-kernel read, before DECD was
ever loaded. They are U-Boot-era values that neither vendor driver touches.

**Consequence: nothing on the ARM side programs the video source's pixel
format.** Live, `0x05600011` reads `0`, where stock's dead function would have
written `6`. Neither `decd.ko` nor `ge2d_dev.ko` writes it.

### Where that points — labelled as inference

If no ARM-side vendor driver configures the video source, the component that
does is the **MIPS display firmware**, which already owns the VBlender/mixer
topology and which DECD feeds through the 32 KiB VideoInfo dma-buf. That fits
every measurement on this page better than any AFBD-register theory has.

**And it predicts this exact null.** U-Boot's bring-up parks the coprocessor —
`H713 panel: MIPS core quiesced, display clocks retained; reset=00000000` — so
on every boot we have ever tested, the thing that would consume DECD's frames
and program the source is held in reset. That would make the enable bits inert
no matter what value they hold, and it would equally explain the 2026-08-26
result that DECD's *internal blue generator* also showed nothing, which no
frame-contents or format theory can account for.

This is inference, not measurement. The measurement that would settle it is
whether the MIPS can be left running, or restarted, with DECD feeding it — which
is CPU_COMM/VideoInfo work, not AFBD register work. **Stop permuting the AFBD
window.**

An earlier negative is also weaker than it reads. The mixer layer-0 enable test
(`0x0525c004`, live `0x1402` vs table `0x1003`) was run with DECD idle and the
video source unconfigured, so if mixer layer 0 is the *video* layer rather than
AFBD plane 0, it had nothing to composite. That variable is uncontrolled, not
eliminated.

## Two reconstruction claims checked against stock, both good

Having the real `decd.ko` lets the 2026-08-26 patch edits be verified rather
than argued:

- **`dec_reg_blue_en` really is `workaround + 5` bit 0** — confirmed at the
  symbol's true address `0x3818`. The change to patch 0013 is correct. The
  address cited in its comment, `0x37e8`, is not the function: it lands inside
  `dec_reg_int_to_display`, whose body is `workaround + 0 |= 0x10`.
- **Patch 0067's ABI is confirmed from the kernel side**, independently of the
  HWC disassembly it was derived from. Stock `dec_ioctl` copies a 32-byte
  header, and for frame submit copies exactly **112 bytes** of descriptor; the
  header's `+0x10` is passed straight to the submit handler as the repeat count,
  and `+0x08` is the userspace pointer that receives the 4-byte fence fd.

`dec_decoder_display_init` is also verbatim what patch 0013 says it is: a tail
call to `dec_reg_mux_select(regs, 2)`.
