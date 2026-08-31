# Which display blocks the MIPS firmware addresses, 2026-08-31

Question: the mixer at `0x0525c000` has been eliminated twice on hardware, and
the content-following taps found on 08-31 are somewhere else entirely. So which
display blocks does the firmware's own code actually reach?

Answered statically, from the authenticated board-B `display.bin` (SHA-256
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`), with
`tools/mips/block-survey.py`. No bench time.

## Method

The firmware reaches peripherals through the aperture recorded in
[mips-firmware-address-map]: MIPS address = ARM physical + `0xB5000000`, so ARM
`0x05600000` (AFBD) is MIPS `0xBA600000`. MMIO addresses in this image are
formed as `lui $rt, 0xbaXX` plus a 16-bit displacement, so counting `lui`
immediates in `0xba00..0xbaff` enumerates every block the code can reach.

The scan is validated in the same run it reports: `tools/mips/disasm.py
--self-test` passes, and the sites it finds disassemble as expected —
`0x8b153410` is `lui $v0, 0xba00` followed by `lw $v1, 4($v0)`, a read of ARM
`0x05000004`.

## Result

```
   MIPS    ARM phys  sites   block
  0xba00  0x05000000     45   composition page (carries the content taps)
  0xba1c  0x051c0000     35   LVDS PHY
  0xba60  0x05600000     29   AFBD (proven per-frame on hardware)
  0xba0c  0x050c0000     22   ** not characterised **
  0xba14  0x05140000     16   display route
  0xba04  0x05040000      7   ** not characterised **
  0xba20  0x05200000      2   VBlender-ish
  0xba18  0x05180000      1   ** not characterised **

total aperture lui sites: 157
```

Known blocks with **zero** sites: GE2D core `0x05240000`, **mixer
`0x0525c000`**, window registers `0x05280000`, TVTOP `0x05700000`, TCON
`0x05880000`, PLL `0x058c0000`.

## The mixer is not merely inactive — the firmware cannot reach it

`0x0525c000` would need `lui 0xba25` or `lui 0xba26` (the latter with a negative
`addiu`). Neither immediate appears anywhere in the image.

This is a third independent line, and the first one that is structural rather
than behavioural:

| evidence | date | says |
| --- | --- | --- |
| block sweep, stock | 08-28 | 0 of 32 mixer registers move idle vs playback |
| forced write, stock | 08-29 | zeroing its layer control, latched, changes nothing |
| **firmware image** | **08-31** | **zero references; the code never addresses it** |

The two mixer differences the 08-29 stock diff surfaced — `0x0525c004` and the
H/V total at `0x0525c000` — are closed for the video path. Do not reopen them.

GE2D reading zero agrees with the separate finding that `/dev/ge2d` is an
ARM-side OSD device. TVTOP, TCON and PLL reading zero agrees with the block
sweep finding them static: U-Boot configures them once and the firmware never
touches them.

### Why the zeroes are trustworthy here

This project has a standing rule that a scan answering "none" must be shown
capable of answering "one" — an earlier cross-reference scan reported zero
stores to `0x8b253570` because it only tracked `lui`-formed bases, and that
near-miss would have supported a confident and wrong conclusion.

This scan clears that bar in the same pass it reports: it finds eight populated
blocks, including AFBD, whose writes to `0x05600010` are independently confirmed
on hardware.

The residual gap is narrow and stated rather than glossed: an address
materialised some other way — loaded whole from a data word, or held in a base
register across a call — would not be counted. Nothing in this firmware's
observed MMIO idiom does that, but the precise claim is **zero `lui`-formed
references**, not "provably never accessed".

## Where the frames actually go

`0x05000000` is the most-addressed display block in the firmware, ahead of AFBD.
It already had four independent reasons to be the composition stage, and this is
the fifth:

- geometry propagates into it and tracks the submitted frame (fourteen fields
  moved to 852x480 and back with the client's coordinate space);
- it carries route words at `+0x30` and `+0x40`;
- both content-following taps are in it (`0x05000a60`, `0x05000a6c`);
- it holds two banks at a clean `0x100` stride that share geometry —
  `+0x444` and `+0x544` are both `0x02D00500`, 1280x720 — while differing in
  what look like coefficient ramps at `+0x400..+0x414` (`0x04C3EF00,
  0x04C5EE00, 0x04C7ED00…` against `0x04C9EC00, 0x04CBEB00, 0x04CDEA00…`);
- and the firmware addresses it more than anything else.

Coefficient ramps and per-instance geometry read as a video processor rather
than a blender, which fits the firmware's entire RPC surface being `THal_Vp_*`
— video *processor*. That is a reading of the register shapes, not a proven
function.

## Three blocks nobody has looked at

`0x050c0000` (22 sites), `0x05040000` (7 sites) and `0x05180000` (1 site) have
**zero mentions anywhere in `docs/`**. They are firmware-driven, they are in
neither the eleven-window sweep nor any capture on either stack, and
`0x050c0000` is addressed more than the display route.

## Caveat on the ranking

Site counts measure how much *code* addresses a block, not how much traffic it
carries at runtime. AFBD is the block proven to move per frame on hardware and
it does not top this table. Read the ranking as where the firmware's logic
lives, not where the pixels flow.

## What this changes

The next capture should not be the composition page alone. `page-sample.sh`
now defaults to the firmware-addressed set plus a control:

```
05000000:400  050c0000:400  05040000:400  05180000:400  05600000:80
```

AFBD is there as a **positive control**, not a subject: its Y/C ring is proven
to move per frame on stock, so it must come back state-driven or free-running.
If it does not, the capture did not observe the state it claims to, and a null
everywhere else means nothing.

[mips-firmware-address-map]: ../plane-brief-for-external-review.md

## All three uncharacterised blocks are real, and one is strongly suggestive

Read on the live board the same day, our Linux, idle console, MIPS parked, no
DECD. One sample in one state, so this is a baseline and a structural
reconnaissance — it cannot separate telemetry from configuration. Full capture:
[linux-firmware-blocks-baseline-2026-08-31.txt](linux-firmware-blocks-baseline-2026-08-31.txt).

```
block         non-zero/1024   geometry markers found
0x05000000        220         1280, 720, 1360, 760, and both total-1 forms
0x05040000        152         1280 x10, 720 x12
0x050c0000        234         1280, 720, 1360, 760
0x05180000         56         1280 x12, 720 x12
0x05140000        470         1280 x8, 720 x9, 1360, 760
```

**Every one carries this panel's geometry**, so all of them are in the display
path. None is empty, dead, or a decode artefact.

### `0x05180000` is four identical full-screen layers

The most suggestive structure found so far, and it is exact rather than
approximate: **four byte-identical banks at a `0x100` stride, 14 non-zero words
each, zero offsets differing between them, and nothing at all past `+0x400`.**
So the block is precisely four instances and is fully accounted for.

```
        bank 0      bank 1      bank 2      bank 3
+0x02c  0x00350500  0x00350500  0x00350500  0x00350500
+0x030  0x000102D0  0x000102D0  0x000102D0  0x000102D0
+0x034  0x050002D0  0x050002D0  0x050002D0  0x050002D0
+0x040  0xC0000500  0xC0000500  0xC0000500  0xC0000500
+0x050  0x001B02D0  0x001B02D0  0x001B02D0  0x001B02D0
```

`0x0500` is 1280 and `0x02D0` is 720 throughout: four slots, each configured
full-screen.

**What this does and does not mean.** Four identical banks at idle is equally
consistent with "four layers, all sitting at their configured default" and
"four layers, all active and full-screen". This capture cannot tell those apart,
and it would be exactly the kind of shape-based over-reading this investigation
has had to retract before.

But it makes a sharp, falsifiable prediction for the stock capture: **if these
are compositor input layers, at least one bank should diverge from the others
during playback.** A bank that changes when video starts is the video layer. If
all four stay identical through playback, they are a static default and this
lead is closed cheaply. Either outcome is worth the capture, which is the
property a good next experiment needs.

### `0x05040000` is two identical instances

72 non-zero words per instance at a `0x800` stride, zero differing. Same
caveat and the same prediction.

### The display route was only ever 1.7% captured

`0x05140000` holds **470** non-zero words. The eleven-window sweep's ROUTE
window covered 8, at `0x05140050`. That block was reported byte-identical
between stock and our stack on 08-29 and used to conclude routing was already
correct on our side — a conclusion drawn from under two percent of a populated
page. It is not overturned, but it is far weaker than it reads, and the widened
capture now covers the whole page.
