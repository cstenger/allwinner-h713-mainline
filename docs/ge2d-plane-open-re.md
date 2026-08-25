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

## Next

1. Resolve the struct-offset → MMIO map from `ge2d_drv_probe`, giving an exact
   address/value/mask list. Without it the remaining 21 operations cannot be
   replayed in the right order to the right registers, and order is now the
   most likely place the effect lives.
2. Replay the full sequence, not fragments of it. The single-register result
   above is the argument against further piecemeal poking.
3. Read the peer tree's `sunxi_ge2d_firmware.c` alongside step 1 — it has
   partial decodes of the same OSD registers (`0x0524c004` v_active,
   `0x0524c010` htotal+hsync, `0x0524c014` timing).

The peer tree's `sunxi_ge2d_firmware.c` has partial decodes of the same
territory (`0x05600140` dual-port bit, `0x0524c010` htotal+hsync,
`0x0524c004` OSD v_active, `0x0524c014` OSD timing) and is worth reading
alongside step 1 rather than after it.
