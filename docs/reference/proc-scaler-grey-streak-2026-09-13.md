# Proc scaler grey-streak analysis — 2026-09-13

> **RESOLVED 2026-09-15.** The cause was the low half of proc `0x05180050`:
> it is the length of the vertical line-enable window and the firmware sets it
> to `max(in_h, out_h)`, while the driver programmed `in_h`. A 544-line source
> therefore ran the vertical stage for 544 of the 720 lines it is active for.
> Fixed in patch `0103`; verified clean on hardware across vertical-only
> 1280x544, two-axis 960x544, horizontal-only 960x720 and native 1280x720.
> Full account in `docs/handoff-2026-09-14-video-scaler-and-rotation.md` §6a.
>
> This document is kept as the investigation record. Its eliminations below
> remain valid and are worth not repeating. Its concluding hypothesis was
> wrong, and the reason is instructive: see the note at the end.

The display-proc upscale path can render a correct 960x544 picture over the
1280x720 panel, but it adds a short, fixed grey horizontal streak. The streak
is visible on decoded video and on a black static source. Native 1280x720
scanout of a software-upscaled copy is clean.

## What the evidence establishes

The following changes did not alter the streak:

- mapping the decoded dma-buf for CPU access and synchronizing it;
- copying the decoded surface into the contiguous scanout carveout;
- changing the proc integer phase fields from the boot-time unity values
  (H/V 4/3) to the firmware's upscale values (H/V 3/2);
- programming the five input-window fields in the enclosing firmware
  `ProcWinNode::WriteReg` path for 960x544 instead of 1280x720;
- pulsing proc bypass for multiple refreshes after the source was live;
- replacing the decoded image with a static black 960x544 source in a native
  1280x720 canvas;
- changing the proc line-enable start from the inherited unity value 27 to the
  firmware's scaled value 39;
- programming the five upstream display-route source-window fields in the
  same order as the enclosing firmware `ProcWinNode::WriteReg` path.

The exact decoded capture buffer was dumped and checked before display. Its
active 960x544 window is clean and every byte in the unused right and bottom
padding is zero. A software upscale of that capture to native 1280x720,
displayed with proc bypassed, is clean. This places the artifact after source
memory, cache synchronization and dma-buf import, in the processing route that
is engaged for scaling.

### Could this be another composition layer?

A fixed mark over both video and black makes a stale overlay a reasonable
hypothesis. The native 1280x720 video control narrows it substantially: it used
the same AFBD source and the same `0x051c006c` video selector and had no streak.
With patch 0106, AFBD is also programmed identically for native and scaled
frames; only the active source rectangle, and therefore the proc registers,
changes. An independently blended downstream layer would be present in both
cases.

The older small-raster investigation also captured the composition block
byte-for-byte identical between its working and failing cases. That evidence
predates this particular streak, so it is supporting evidence rather than a
direct exclusion. Taken together, the likely forms of the composition theory
are now limited to stale data inside the proc instance itself, or another proc
instance that becomes visible as a consequence of enabling scaling. They do
not support a conventional OSD overlay above the video plane.

## Firmware comparison

`0x8b1a66d0` is a subroutine of `ProcWinNode::WriteReg`, rather than the whole
function. The enclosing routine at `0x8b1a6a08` also writes input/output and
meter windows in `0x05140000`. For a 960x544 input, the relevant input fields
are:

```
0x05140104 = 0x03c00000
0x05140108 = 0x02200000
0x0514011c = 0x02208002
0x05140124 = 0x03c00000
0x05140128 = 0x02200000
```

Writing that coherent set during a held black scaled frame had no visible
effect. Patch 0111 then moved the writes into the driver's pre-enable path,
matching the firmware ordering and restoring the original values at teardown.
A cold-booted 1280x544 vertical-only black test still showed the streak.
Output and meter windows remain 1280x720 in both the firmware model and the
Linux route.

The integer phases are nevertheless a driver correctness bug. Firmware
`CalcWindow` starts an upscale at H/V 3/2. At unity the fractional phases cross
their thresholds and advance those fields to 4/3. Linux inherited 4/3 from
boot and retained them while changing the ratios. Patch 0108 programs 3/2 for
the upscale case, even though the live A/B test proves this mismatch is not the
grey streak.

Firmware also programs the high half of proc register `0x50` from
`m_line_enable_v_start`. Its own logs change this from 27 at unity to 39 while
upscaling 720x480 to 1280x720; `m_in_vs_delay` changes from 3 to 15 in parallel.
The exact twelve-line delta and the `WriteReg` disassembly show this is scaler
pipeline latency. Linux currently rewrites only the low half of `0x50` and
therefore retains the bypassed value 27. Patch 0109 programs 39 while scaling.
A cold-booted vertical-only test still showed the streak, so the mismatch was
real but was not its cause.

## Test-harness corrections

The KMS test used to send every input file directly into `h264parse`. An MP4 is
a container and must pass through `qtdemux`; the earlier parse failure is not
evidence that `/root/leota-1080p.mp4` is corrupt. The harness now selects
`qtdemux` for MP4/MOV and `matroskademux` for MKV, and reports pipeline parse
errors. It can also generate limited-range NV12 black in the scanout buffer via
`SYNTH_BLACK=1`, removing source-file contents from scaler tests.

## Axis isolation result

Do not resume with individual register pokes. Use a uniform limited-range
black source in a native 1280x720 canvas and test this matrix:

| active source | proc operation | question answered |
| --- | --- | --- |
| 1280x720 | bypass | clean control |
| 960x720 | horizontal only | does the H engine create the streak? |
| 1280x544 | vertical only | does the V engine create the streak? |
| 960x544 | both axes | known positive artifact control |

The matrix was run with the uniform black source. Horizontal-only 960x720 was
clean. Vertical-only 1280x544 showed the same grey streak as two-axis 960x544.
The complete proc-register captures were coherent in both cases; the vertical
test differed in the expected vertical ratio, phase, input height and output
height fields. The defect is therefore isolated to what changes when the
vertical proc engine is active.

## Current composition hypothesis

The mark is a short horizontal dash at a fixed panel position, visually
consistent with an fbcon underscore cursor. A controlled test cleared the
console framebuffer and hid its cursor before showing the same 1280x544
synthetic black frame. The dash remained. It is therefore generated in or
after the vertical proc path, rather than exposed from the underlying RGB
console layer.

## Why this document did not find it — 2026-09-15

The last conclusion above is correct as far as it goes and stops one step
short. "Generated in the vertical proc path" was right; the next question was
never asked.

Everything here treats the axis-isolation matrix as a *confirmation* device —
it established that the vertical engine is implicated. It is also a *ranking*
device, and that use was missed. Four register fields change when the vertical
engine engages and not otherwise: `ratio_v`, `phase_v`, `in_win.h`, and
`0x05180050[15:0]`. Three verify against firmware. Checking the fourth was a
desk exercise of about twenty minutes against a disassembly already open in
this investigation.

Instead, three real mismatches were found and fixed in sequence — integer
phases, line start, route windows — each tested on hardware, each negative.
All three were equally mismatched during the *clean* horizontal-only run, so
the matrix had already excluded them before any of those looks were spent.
The eliminations in this file are honest work; the ordering was not driven by
the evidence already in hand.

The 1280x640 guard-line test deserves its own note. It varied `0x05180050`
from 640 to 656 and concluded from no change that the bottom boundary was not
implicated. Under the real rule the value needed to be 720, so the test moved
the right register by the wrong amount and returned an uninformative negative
that read as an exculpatory one. When a test changes a quantity and nothing
happens, check that the change crossed the threshold the hypothesis predicts.
