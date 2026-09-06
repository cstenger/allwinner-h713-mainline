# MIPS → scanout: a frame on the panel through the window layer

2026-09-05. **Operator-confirmed: a frame appeared on the glass**, routed by the
MIPS window layer. First time in this project.

## What was on screen — CORRECTED after seeing the photographs

**The output is corrupt.** `local/lcd-photos/test_68/` shows green/yellow
horizontal bands with fine vertical comb striping, and a band of noise-like
speckle across the top ~20%, occupying roughly the top-left two-thirds of the
projected frame with the remainder blank.

This section originally read the operator's "greyscale and didn't fill the
screen" as two fully explained symptoms. That was wrong and oversold the
result: the photographs show comb-striping and a noise band that neither
explanation accounts for.

**What is genuinely established is the routing, not the picture.** Pixels reach
the glass through the MIPS window layer, which nothing before this session
achieved. The image itself is garbage.

The two partial explanations below still stand as far as they go:

**Greyscale** — `0x05140508` read `0x14000000`. Bits 23:16 are the chroma gain
and were `0x00`, which is the documented greyscale signature from the
2026-08-31 scanout work; colour needs `0x4C` there (`0x144C0000`). Set and
re-run for a second observation.

**Not filling the screen** — the WCE computed it that way. `CalcWindow`
produced `m_video_win_2: [49, 22, 852, 480]` inside the 1280x720 panel, and
`PanelWinNode` logged `right_width:428` and `bottom_width:240` — exactly
1280-852 and 720-480. The picture is where the firmware put it.

## The full state that produced it

```
h713_disp init 0x34                       # live, handshaken core
h713-kernel-decd-iommu-0076v3.fit         # dec okay, display disabled
sunxi-decd-budget.ko ring_writes_max=1    # one ring write, no 60 Hz rewrite
decd-client show ...                      # populates Y/C/VideoInfo
mips-shell.py --cmd "dtv get_fb"          # firmware reads the descriptor
0x051c006c = 0x39000000                   # route video to the panel
```

with the firmware having programmed, on its own:

```
0x05600010  0x03000013   video source enabled
0x05600030  0x01E00354   852 x 480
0x05000174  0x002B002B   scaler engaged, 43/64
```

## What this settles

- **The hardware scales** — `0x05000174` off unity, programmed by firmware.
- **The window layer will composite our frames** — given a descriptor it can
  read and a source it has been told about.
- **The LVDS selector is ours to flip after all.** Earlier the same write was
  inert; the difference is that nothing was composited behind it then. It was
  never the selector that was wrong.

## The split-geometry theory — tested, NEGATIVE

The AFBD source block was left internally contradictory:

```
0x05600020  0x02CF04FF   1279 x 719     <- our driver: 1280x720
0x05600024  0x002C004F   blocks for 1280x720
0x05600040  0x00000500   Y stride 1280
0x05600044  0x00000500   C stride 1280

0x05600030  0x01E00354   852 x 480      <- firmware
0x05600048  0x01E00354   luma 852x480   <- firmware
0x0560004c  0x00F00354   chroma 852x240 <- firmware
```

That is the seven-word coherence problem from 2026-09-04, mirrored: the firmware
moved its three words while our four stayed. A fetch whose line length and line
advance disagree produces exactly comb-shear, and chroma at the wrong offset
produces green.

**Tested by forcing all seven to 1280x720** (`0x30`/`0x48` = `0x02D00500`,
`0x4c` = `0x01680500`, chroma gain `0x144C0000`, commit latch pulsed) and
re-routing. **Operator: the same corruption.** So split geometry was not the
cause, or not the only one.

*Process note: this run was started without prompting the operator to watch,
against the standing rule that operator-timed tests get their own turn. Part of
it went unobserved.*

## The strongest untested candidate: the format selector

`0x05600010` reads `0x03000013`. Bits 15:8 are the **pixel-format selector** and
they are **`0x00`**. `dec_reg_video_channel_attr_config` — the vendor's only
writer of that field, dead code in stock and uncalled in our port — writes **6**
for 8-bit NV12 (`mode == 1`), and the vocabulary the firmware emits is
`{1, 6, 7}`.

A fetch interpreting NV12 under format 0 would give wrong luma stride *and*
wrong chroma placement, which is the shape of what the photographs show. Setting
bits 15:8 to 6 (`0x03000613`) and pulsing the commit latch is a one-register
test.

## What is still open

- **The STM sits at 2 (`SignalChanging`), not 3 (`SignalValid`).** Repeated
  `dtv get_fb` does not advance it — that command reaches slot 14
  (`GetFrameInfo`), not slot 16 (the state machine), and nothing invokes slot 16.
- **The whole path depends on a debug command.** `dtv get_fb` is what makes the
  firmware read the descriptor. For a real pipeline the periodic poll has to be
  found, or the read triggered another way.
- **852x480 is not 1280x720.** Why the WCE chose that window is unexamined —
  aspect ratio, overscan, or a default with `b_par_valid: 0` and `afd: 0` in the
  signal info. It is a window-geometry question, not a scaling one.
- The selector flip is manual and does not persist.

## ROOT CAUSE — the fetch was never reading our buffer

Found 2026-09-05 after three visual tests. **All of them were reshaping
garbage.**

```
0x02010030 = 0x0000007C     bit 2 set -> IOMMU master 2 BYPASSING
0x05600070 = 0xFFE00000     Y
0x05600084 = 0xFFEE1000     C
```

DRAM is `0x40000000`-`0x7fffffff`. `0xFFE00000` is an **IOVA**, and with master 2
bypassing the fetch engine takes it as a physical address. So it has been
reading whatever that aliases to, not our frame.

That retires the interpretation of the whole test sequence:

| test | reading at the time | actual meaning |
| --- | --- | --- |
| fine comb, green (test_68) | split geometry | garbage, shaped by our stride |
| coarse stripes + flat (test_69) | format selector wrong | garbage, reshaped by format 6 |
| stripes gone, diagonal weave (test_70) | 2x stride was right | garbage, reshaped again |

The stride and format changes *did* alter the fetch's interpretation — which is
why the pattern kept changing — but of the wrong memory.

**What a correct render should look like**, from the frame itself: luma almost
entirely `0x51` with min 12 / max 222, i.e. a mostly-uniform mid-dark image with
some structure; chroma `dc a6 d9 a2 ...`, a definite colour cast. Nothing like a
green weave.

### The fix, and its ordering constraint

Either make master 2 translate so the IOVAs resolve, or give the hardware
physical addresses (the `h713-kernel-decd-contiguous.fit` variant).

The flip is one register but has a **documented hazard**: patch 0076 established
that `0x02010030` may only go `0x7c -> 0x78` while the **DECD video source is
disabled**, because the source sits at base 0 with inherited geometry and scans
low memory the instant it is enabled. The safe order is therefore:

```
selector -> RGB
source 0 disable (0x05600010 bits 1:0 = 0) + commit
0x02010030 = 0x78
source 0 enable + commit
selector -> video
```

### Method note

Three operator observations were spent before checking whether the fetch address
was even valid. The address was visible in a register the whole time, and the
project's own notes already record IOVA-as-physical as a known failure mode with
this exact signature. **Check that the source address is in DRAM before
interpreting anything about pixel layout.**

## The IOMMU flip fixed the address — one clean fault left

Ran with the documented ordering (selector to RGB, source 0 off, `0x02010030`
`0x7c -> 0x78`, source on, route):

```
bypass      0x7C -> 0x78
IOMMU INT_STA  0x00000000    zero faults across all three windows
core           0x00000001
```

**Zero faults with master 2 translating proves the IOVAs are genuinely mapped** —
an unmapped one would have faulted immediately.

`local/lcd-photos/test_71/` then shows something categorically different from
every previous attempt: **clean, bold diagonal stripes in green and magenta,
sharp-edged, with no noise band and no fine weave.**

That is the signature of a **pure stride mismatch** — each line offset from the
previous by a constant, and nothing else wrong. The structure is real data, not
aliased garbage: sharp edges and only two colours mean the fetch is walking a
real plane at the wrong line pitch.

So the fault has gone from "reading the wrong memory" to "reading the right
memory with the wrong line length", which is a one-parameter problem.

### Next: sweep the stride, do not derive it

The arithmetic is under-determined — the display window (852 wide), the source
(1280), the scaler ratio (43/64) and the 2x-vs-1x question all feed the pitch,
and the previous three attempts to reason it out were each wrong. A sweep costs
one operator window and settles it empirically: step `0x05600040`/`0x44` through
candidate values, hold each a few seconds, and look for the frame where the
diagonal goes vertical.

Candidates worth including: `0x500` (1280, 1x source), `0x6A8` (1704 = 2x the
852 display width), `0x780` (1920), `0x800` (2048), `0xA00` (2560, current), and
`0xC00` (3072).

## Coherent source block removes the shear — test_73

With the IOMMU translating **and** the whole source block set coherently to
1280x720:

```
0x05600020 = 0x02CF04FF   0x05600030 = 0x02D00500   0x05600040/44 = 0x00000500
0x05600024 = 0x002C004F   0x05600048 = 0x02D00500   0x0560004c   = 0x01680500
0x05600010 = 0x03000613   format 6
```

`local/lcd-photos/test_73/` shows the 852x480 window as a **flat uniform field —
no stripes, no weave, no noise band.** The diagonal shear is gone.

Four distinct faults have now been peeled off in order:

| fault | fix | evidence |
| --- | --- | --- |
| reading the wrong memory | IOMMU master 2 translating | test_71: garbage -> clean structure |
| pixel format | `0x05600011` = 6 | test_69: pattern changed character |
| line pitch | strides | test_70: stripes vanished |
| incoherent geometry | all seven words at 1280x720 | test_73: shear gone |

**Note the earlier stride sweep is void.** It was run with `0x30` still at
852x480 while `0x20`/`0x24` said 1280x720, so no stride could have been right;
that is why positions looked similar and "stuck". The firmware was *not*
rewriting the registers — verified by holding `0xC00` and reading it back
unchanged over six seconds.

## What remains: the field is uniform but too bright

The frame's luma is almost entirely `0x51` (~32%), min 12 max 222, so a correct
render is a mid-grey field slightly darker than the blank panel around it. The
window is instead uniformly *brighter* than its surround.

So the geometry is right and the values are not. Candidates, untested:

- we are reading valid memory that is not our frame (the IOVA maps somewhere
  else, or only partially);
- a gain/range conversion in the pipeline (limited vs full range);
- the plane is being read but the content is not what the file holds.

**The decisive next test is content substitution, not another register.**
`/root/decd-green.nv12` and `/root/decd-red.nv12` are distinct known frames.
Submit each and see whether the window changes accordingly. If it tracks the
file, we are reading our buffer and the remaining fault is value mapping. If it
stays uniform white regardless, we are not reading our data at all and the
address still is not right.

## CONFIRMED: our frames render through the MIPS window layer — test_74

Content substitution, three known-different frames, coherent 1280x720 block,
IOMMU translating:

| position | frame | result |
| --- | --- | --- |
| 1 | `decd-green.nv12` | **solid clean green**, correctly placed in the 852x480 window |
| 2 | `decd-red.nv12` | **solid purple** |
| 3 | `decd-test-frame.nv12` | diagonal stripes |

**The window tracks the submitted file.** That settles the open question: we are
reading our own buffer, the MIPS window layer composites it, and it reaches the
glass. A flat frame renders cleanly, uniformly and in the right place.

Note the mechanism that makes this work without extra ring writes: the client
reuses the same dma-buf and the IOVA is stable at `0xFFE00000`, so writing new
content into that buffer changes the display without a fresh ring write. The
exhausted `ring_writes_max` budget therefore did **not** invalidate positions 2
and 3, contrary to what was assumed when the run finished.

### Two faults remain, and they are now cleanly separated

**Colour mapping.** Green renders green; red renders purple. A flat frame proves
luma and placement are right, so this is a chroma issue alone — most likely U/V
order (NV12 vs NV21) or the colour matrix, not the fetch.

**The shear is not gone, only invisible on flat frames.** This corrects the
test_73 reading. A uniform field is unchanged by a stride shear, so green and
red *cannot* show it; only the structured test frame can. test_73 concluded "the
coherent block removes the shear" from a frame whose luma is almost entirely
`0x51` — that conclusion was unsupported, and position 3 here shows the stripes
still present.

Most likely cause, untested: a fresh submit makes the WCE recompute and rewrite
`0x30`/`0x48`/`0x4c` back to 852x480 after our coherent values are applied. The
check is cheap — submit, then read those three registers before routing.

### Method note

**A flat test frame cannot validate geometry.** Two conclusions in this file
were drawn from uniform output. Any future geometry test must use a frame with
structure; `decd-test-frame.nv12` qualifies, the green and red ones do not.
