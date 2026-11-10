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
05000000:400  050c0000:400  05040000:400  05180000:400  05140000:400  05600000:80
```

(`05140000` was added after the baseline read below found 470 non-zero words in
a block the eleven-window sweep had only ever sampled 8 of.)

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

---

## Run on hardware: MIPS alive, DECD submitting, 2026-08-31

The lock-risking capture was made. It did not lock. Boot was `reboot bootloader`
→ `h713_disp init 0x34` → `ext4load`/`bootm` of the DECD-exclusive FIT; capture
by a non-interactive four-sample script syncing to the rootfs at every step.
Captures: [linux-mips-alive-decd-4sample-2026-08-31.txt](linux-mips-alive-decd-4sample-2026-08-31.txt),
classification in [linux-mips-alive-decd-classified-2026-08-31.txt](linux-mips-alive-decd-classified-2026-08-31.txt).

**The positive control passed**, which is what makes the rest of this usable.
AFBD came back state-driven exactly where it must — source control
`0x03000010 -> 0x03000013`, Y bases `0x05600070-7c` all to `0x6C500000`, C bases
`0x05600084-90` to `0x6C5E1000`, geometry to `0x02CF04FF`, stride to `0x500` —
with the frame counters at `0x05600058/5c` classified free-running. DECD IRQ 331
reached 4716. The capture observed the state it claims to.

### The four-bank prediction is falsified

The previous section called `0x05180000` "the most suggestive structure found so
far" and committed to a test: if those four banks are compositor inputs, at
least one must diverge during a submit.

**Zero of its 1024 words changed.** All four banks stayed byte-identical through
a serviced frame. They are a static default, not layers being fed. The lead is
closed — cheaply, and by the test that was specified in advance rather than
after the data was seen.

### The surprise is `0x05040000`

| block | static | state-driven | free-running |
| --- | ---: | ---: | ---: |
| `0x05000000` composition | 983 | 39 | 2 |
| **`0x05040000`** (was uncharacterised) | 898 | **121** | 5 |
| `0x050c0000` (was uncharacterised) | 1012 | 3 | 9 |
| `0x05180000` four banks | 1024 | **0** | 0 |
| `0x05140000` display route | 952 | 60 | 12 |
| `0x05600000` AFBD (control) | 105 | 19 | 4 |

**A block nobody had ever looked at responds to a DECD submit three times more
than the composition page does**, across sixteen distinct regions. Its
two-instance `0x800` symmetry survives the submit: of 61 changed words in the
first instance, **60 change identically in the second**. Both instances are
driven together.

`0x050c0000` is nearly inert by contrast — 3 state-driven — despite 22 firmware
sites and 234 non-zero words. Firmware attention does not predict per-frame
response, which is the caveat above, now demonstrated rather than asserted.

### The frame descriptor lands in the composition page

```
+0x178  0x6002021C -> 0xE002021C     bit 31 set
+0x1b8  0x60020438 -> 0xE0020438     bit 31 set
+0x278  0x60020168 -> 0xE0020168     bit 31 set
+0x2b8  0x600202D0 -> 0xE00202D0     bit 31 set
+0xac0  0x00000000 -> 0x000E1000  }
+0xac4  0x00000000 -> 0x000E1000  }  0xE1000 = 921600, exactly the
+0xac8  0x00000000 -> 0x000E1000  }  1280x720 NV12 luma plane
+0xacc  0x00000000 -> 0x000E1000  }
+0xa60  0x01400140 -> 0x06040604     content tap
+0xa6c  0x00000000 -> 0x000007A8     content tap
```

Four registers take the exact luma plane size — the same `0xE1000` that
separates the Y and C base addresses — so the submitted buffer's geometry is
propagating into this block, not just into AFBD. Four others have bit 31 set at
a matching stride. Both first-frame words `0x05000058` and `0x05000104` moved
again, reproducing the earlier capture independently.

### What this does not say

Every result here is one stack. Nothing above shows what stock does, so none of
it identifies the gate — it identifies *where to look* and, in the case of
`0x05180000`, one place to stop looking. The comparison still needs the stock
capture, which is now a much better-specified request: the same six windows, the
same four samples, during real playback.

One methodological note worth keeping: the capture script's IRQ helper misparsed
`/proc/interrupts` (`cut -f3` took CPU1's column, not CPU0's) and reported 0
interrupts throughout a run that actually served 4716. The registers, not the
helper, are what established that DECD was live. A convenience readout being
wrong is cheap; it would not have been cheap if the run had been declared a
failure on its word.

## What each responding block actually is, 2026-08-31 (later)

Scanout liveness was established first, on this boot, with `mem-fill` painting a
red→green→blue sequence into `0x6C100000`. The operator saw the green→blue
transition. A transition is stronger than a static fill: the panel is not merely
showing a correct image, it is actively re-fetching. **Every null below is
therefore a real negative**, which is the condition several earlier sessions
lacked.

Also established: **DECD free-runs at 60/s after the client exits** — 89055 to
89175 interrupts across two seconds with no client alive. `repeat=1` re-fetches
every vsync, so the submitting state persists and does not need a process held
open.

### `0x05000000` is a scaler, holding both coordinate spaces at once

The four registers that take bit 31 when a frame lands decode as luma/chroma
height pairs for two different resolutions:

```
+0x1b8  0xE0020438   1080      +0x2b8  0xE00202D0   720
+0x178  0xE002021C    540      +0x278  0xE0020168   360
```

Two instances at `0x100` stride, each a luma/chroma pair at `0x40` stride. That
is exactly the split our VideoInfo declares — canonical 1920x1080 crop and
display frame over a real 1280x720 buffer.

Their neighbours `+0x174`/`+0x1b4`/`+0x274`/`+0x2b4` sit at `0x00400040`, and in
the 852x480 capture those same words read `0x002b002b`. 43/64 = 0.67 = 852/1280
exactly, so **these are scale ratios in 1/64 units with `0x40` as unity** — which
also retroactively explains the 852x480 signature as a scaler input rather than
an unexplained convention.

### `0x05040000` is picture-quality measurement — a tap, not a path

The block that responds most to a submit is measuring the video, not routing it:

- `+0x280..+0x2c0` — twelve bins of arbitrary magnitude
- `+0x380..+0x3c0` — sixteen more accumulators, all zero before the submit
- `+0x348`/`+0x34c` — `0x9A9A0010 -> 0xFFFF0010` and `0x009E9A9A -> 0x00FFFFFF`,
  per-channel maxima saturating
- `+0x534`/`+0x538` — `0x02D00000 -> 0x02CF0000` and `0x05000000 -> 0x04FF0000`,
  720→719 and 1280→1279

Histograms, minima/maxima and size-minus-one. That matches the firmware's
`THal_Vp_*` picture-quality surface, and it makes this block the same category
as `0x05000a60`: it observes the video. Much of `0x05140000`'s response
(`+0x600..+0x6d4`, zero→arbitrary) has the same character.

### `0x05200000` is not the gate

The one block with a compositor-sounding name resolves to seven configuration
words plus two large uniform fills:

```
+0x004  0x40210000
+0x00c  0x05000031   +0x020  0x05000031    1280 wide, x-offset 49
+0x010  0x02D00016   +0x024  0x02D00016     720 high, y-offset 22
+0x100..+0x7fc   448 x 0x00BBA15B
+0x800..+0xffc   512 x 0x00EB2002
```

Two identical window descriptors, then two tables filled with a **constant
rather than a ramp** — i.e. allocated but never meaningfully programmed, which
is consistent with its two firmware sites. Not the output selector.

### Where that leaves it

Video is fetched, scaled, measured and content-sampled. Every block reachable
from here is either static, a measurement tap, or unprogrammed. The unaccounted
step remains output selection, and the sharpest statement of it is a stock fact
this project already established: in the fmt-4 photographs the player's UI was
tiled *inside* source 0's corruption, so **on stock, source 0 is the scanout
path**. On ours, OSD channel `0x05600140` is the scanout path and source 0 feeds
nothing. That difference — which AFBD channel reaches the panel — is the gate.

## The AFBD global is eliminated, properly this time

`0x05600000` low bits were swept on 2026-08-25 with no effect, under the theory
that bit 5 gates channel 1 and bit 4 channel 0. That sweep predated two things
now known to be mandatory: writes to this block are inert without a commit latch
pulse, and the MIPS must be alive for the firmware to own the source.

Re-run with both satisfied, and with a control the original lacked. `mem-fill`
painted the scanout buffer red **continuously for the whole run**, so a panel
showing red cannot be a frozen image:

| step | write | latch | panel |
| --- | --- | --- | --- |
| baseline | `0x80000020` | — | red (provably live) |
| bit 4 added | `0x80000030` | consumed | no change |
| **bit 5 cleared** | `0x80000000` | consumed | **no change, still red** |
| restore | `0x80000020` | consumed | red |

`0x05600004` **is** a real commit latch — written 1, reads back 0, consumed on
every write. So these were committed, verified by readback, and observed against
a provably-live panel. Clearing bit 5 does not disturb the channel that is
actively scanning out. **`0x05600000` does not gate channel output.** The old
null was right; it now has the control that makes it mean something.

## There is no destination buffer anywhere

Searching every captured block for address-shaped values (DRAM base `0x40000000`,
page-aligned) returns only **inputs**: AFBD's Y (`0x6C500000`), C
(`0x6C5E1000`), VideoInfo (`0x4D941000`), and the OSD's own source
(`0x6C100000`). Nothing in `0x05000000`, `0x05040000`, `0x050c0000`,
`0x05140000` or `0x05180000` takes a write destination when video arrives.

Composition here is therefore a **streaming path**, not render-to-buffer-then-
scan. With the AFBD writeback engine already eliminated as disabled on stock,
the gate cannot be a buffer pointer — it must be a mux between two live streams.

## The routing conclusion rests on two registers

`0x05140000` is the block named for exactly that job, and its low region is
twenty non-zero registers whose values look like a crossbar:

```
+0x000  0x0007FFFF     +0x010  0x0C000C80     +0x024  0x00030C0C
+0x004  0x80000000     +0x014  0x0000C040     +0x028  0x0000000C
+0x008  0x0C2030C0     +0x018  0x0C000C00     +0x02c  0x021C03C0
+0x00c  0x000C0C00     +0x01c  0x000000C0     +0x034  0xB0000040
```

Repeated `0x0C` and `0xC0` nibbles packed into words is what a source-selector
matrix looks like. All twenty are static across a video submit — consistent with
configure-once, and equally consistent with nothing on our side ever setting
them for video.

**And they have never been compared with stock.** The ROUTE window in both
sweeps is `0x05140050..0x0514006c` — eight words, of which five are zero. So the
finding that "ROUTE is byte-identical, therefore routing is already correct on
our side" rests on exactly **two non-zero registers** (`+0x054 = 0x40000080`,
`+0x058 = 0x00000002`) out of 470 non-zero words in the block, and the window
starts `0x50` bytes above the crossbar region entirely.

That is the sharpest remaining target: capture `0x05140000..0x0514004c` on stock
during playback. It is twenty registers, in the block named "route", of a
streaming path whose gate must be a mux, and no one has ever looked at them.

## `0x05140000` is a live output gate — the first one found outside AFBD

Probed on hardware with the panel provably live (`mem-fill` repainting red
continuously for the whole run), operator watching:

| phase | write | panel |
| --- | --- | --- |
| baseline | `0x0007FFFF` | red |
| nine crossbar regs `+0x008..+0x028` zeroed | `0` each | **flicker, stays red** |
| restore | — | flicker, stays red |
| **`+0x000` zeroed alone** | `0x00000000` | **BLACK** |
| restore | `0x0007FFFF` | red |

**Zeroing `0x05140000` blanks the panel; restoring it brings the image back.**
Reversible, repeatable, and immediate — **no commit latch is needed for this
block**, which is what makes the rest of this section interpretable.

That last point converts the crossbar result into a real negative. The nine
registers at `+0x008..+0x028` carry the `0x0C`/`0xC0` nibble patterns that look
like a source-selector matrix, and zeroing all nine **took effect** (readback
confirmed, and this block needs no latch) yet produced only a momentary flicker
with the image intact. They perturb the pipeline; they do not gate output. The
crossbar reading in the previous section is **wrong** — the gate is the mask
beside them, not the matrix.

### It is a series enable, not a stream mux

Bisecting the 19 set bits, each group cleared independently against a live panel:

| bits cleared | panel |
| --- | --- |
| 0–5 (`0x0007FFC0`) | black |
| 6–12 (`0x0007E03F`) | black |
| 13–18 (`0x00001FFF`) | black |

**All three blank it.** So no single bit selects a stream — each group holds
something required in series. The hoped-for reading ("one bit gates the OSD,
clear it and video appears in its place") is dead.

### The register is 32 bits wide

Writing `0xFFFFFFFF` reads back `0xFFFFFFFF`, so it is not a 19-bit field:
**thirteen writable bits above bit 18 are currently off**, in a register proven
to control whether anything reaches the panel. Every bit that is *on* is already
on while video is invisible, so if this register is involved in the missing
selection, the answer is necessarily in the bits that are off.

### Why this matters beyond the register

This is the first register anywhere outside AFBD's own channel controls shown to
determine whether an image reaches this panel. It also sits in `0x05140000` —
whose low region the eleven-window sweep never covered, its ROUTE window
starting at `+0x050`, above everything described here.

### The high bits are inert — the gate is closed as a selection lead

Re-run cleanly after a first attempt whose observation was ambiguous (a console
timeout separated the "watch now" from the run, so "didn't notice anything" could
not be distinguished from "wasn't watching"). That ambiguity was deliberately
not recorded as a result.

The controlled run, detached with a 20-second lead-in so the operator's timing
did not depend on a console round-trip:

```
20:38:22  A: 0x000FFFFF   (+bit 19)      readback confirmed   DECD 209451
20:38:39  B: 0x00FFFFFF   (+bits 19-23)  readback confirmed   DECD 210486
20:38:57  C: 0xFFFFFFFF   (all 32)       readback confirmed   DECD 211522
20:39:14  restored 0x0007FFFF
```

Panel repainted red continuously throughout, so it was provably live; every
write took by readback; DECD advanced ~1035 interrupts between phases, ~61/s, so
video was being submitted in every window. **Operator observation: red the whole
time, no flashes.**

So the thirteen writable bits above bit 18 are inert. Combined with the bisection
— every group of set bits blanks the panel when cleared — `0x05140000` is a
**series output enable and nothing more**. It gates whether the display works; it
does not choose what the display shows. Closed as a video-selection lead.

## Method note: three shape hypotheses, three falsifications

Worth recording because the pattern is more useful than any one result. This
session generated three structural hypotheses by reading register shapes, and
hardware refuted all three within hours:

| hypothesis | from | outcome |
| --- | --- | --- |
| `0x05180000`'s four identical banks are compositor input layers | four byte-identical banks at `0x100` stride, all full-screen | 0 of 1024 words moved during a submit |
| `0x05140008..28` is a source-selector crossbar | repeated `0x0C`/`0xC0` nibbles packed into words | writes took, no latch needed, flicker only |
| a high bit of the gate register enables the video stream | it is the one causal register with unset bits left | all thirteen inert |

What did advance the problem came from measurement rather than inspection: the
firmware `lui` survey that eliminated the mixer structurally, the four-sample
capture with a working positive control, and the gate discovery itself — which
came from a destructive test against a live panel, not from reading values and
reasoning about them.

The lesson is not "stop hypothesising" but that on this hardware, **register
shape is close to worthless as evidence and cheap destructive tests against a
provably-live panel are close to decisive.** Budget accordingly: prefer an
experiment that can fail visibly over another pass of reading dumps.
