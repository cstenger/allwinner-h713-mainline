# Proc scaler grey-streak analysis — 2026-09-13

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
The earlier inference of generic scaler latency was incorrect: that scaled
log is an interlaced/deinterlaced path. CalcWindow at `0x8b1a6430` computes
`in_vs_delay + 1 + upstream_vertical_start + mb_420_format`. Progressive AFBD
retains the boot start of 27. Cold-boot tests with 27 and 39 both showed the
streak; revised patch 0109 preserves the upstream timing and documents why.

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


## 2026-09-14 continuation: retained fields and phase model

Re-disassembled the board-A binary with file offset zero mapped to
`0x8b1008e0`. The writer at `0x8b1a66d0` establishes:

| proc field | writer | firmware source |
| --- | --- | --- |
| `0x00[31:16]` | `0x8b1a6770` | constant `0x0f00` |
| `0x04[15:0]` | `0x8b1a677c` | constant `0x0f00` |
| `0x04[31:16]` | `0x8b1a6824` | object `+0x38`, fixed 16 in CalcWindow |
| `0x08[30:28]`, `[26:24]` | `0x8b1a67ac`, `0x8b1a67bc` | H/V integer phases |
| `0x14[31:28]` | `0x8b1a66fc` | zero |
| `0x20[31:24]` | `0x8b1a66e8` | upstream object byte `+0x0c` (meaning unresolved) |
| `0x2c[31:16]` | `0x8b1a6814` | upstream object `+0x14` plus four |
| `0x30[19:18]` | `0x8b1a685c` | zero |
| `0x38[31:16]` | `0x8b1a6844` | `16 + max(object[0x90] - output_width, 0)` |
| `0x40[31]` | `0x8b1a6708` | one |
| `0x44[15:0]` | `0x8b1a6834` | upstream object `+0x14` |
| `0x50[31:16]` | `0x8b1a6728` | upstream-derived line start, not generic scale latency |

This writer does not explain every retained bit (including `0x30[16]` and
`0x40[30]`). Do not assign meanings or change them without tracing their
other writers. The `0x38` upper field depends on horizontal dimensions, not
input height, in this function.

A simple fractional accumulator wraps repeatedly, not once near the observed
streak: for source heights 544/608/640, ratios are `0xc16c`/`0xd82d`/`0xe38e`
and initial phases are `0xe0b6`/`0xec16`/`0xf1c7`. All have their first carry on
output line 1. A one-off midframe artifact cannot be explained by that first
carry alone. A periodicity or line-buffer boundary hypothesis requires a
measured panel coordinate and an explicit counter model.

Ruled NV12 cards for 1280x544, 1280x608, and 1280x640 are staged on p23 as
`/mnt/media-data/h713-ruled-1280xHEIGHT.nv12`. Labels represent nominal output
y at 40-line intervals. No new visible test has run: operator confirmation is
pending. Patches 0109 and 0111 were corrected locally and apply without fuzz;
the board still runs the earlier kernel with line start 39 when scaling.

### First ruled-card observation window

After the operator explicitly said `watching`, ran:

```sh
ARMED=yes SRC=1280x544 /mnt/media-data/kms-nv12-plane-test \
    /mnt/media-data/h713-ruled-1280x544.nv12 30
```

The harness exited 0 and reported `NV12 plane disabled; KMS RGB restored`.
Operator report of the image/streak and visible console restoration is pending.
The subsequent register read caught restored unity state, not active scaling:
`proc+0x14=0x08000000`, `+0x34=0x050002d0`, `+0x38=0x00100000`,
`+0x3c=0x00010000`, `+0x50=0x001b02d0`. Do not treat it as an active
544-line capture. Other restored values were `+0x04=0x00100f00`,
`+0x20=0x02000000`, `+0x2c=0x00350500`, `+0x30=0x000102d0`,
`+0x40=0xc0000500`, `+0x44=0x00000031`. No live writes were made.

Operator supplied `/home/chris/Downloads/IMG_0863.JPEG` for the ruled 1280x544
run and identified the streak between labels 520 and 560. The photograph
shows a short bright horizontal segment toward the right in that band. Record
nominal panel y in [520,560] rather than asserting an exact line from the
perspective-distorted photograph. Visible console restoration was not reported.
Next discriminator: repeat the ruled card at 1280x640, preserving all other
test parameters, and compare its measured band with this baseline. This tests
ratio-dependent movement; it does not yet identify a phase-counter mechanism.
Require a fresh watching confirmation before that test. Capture the active
registers inside the same remote script as the held frame, after the harness
reports its observation window, to avoid repeating the late unity capture.

### Second ruled-card observation window: 1280x640

After a fresh `watching` confirmation, held the staged 1280x640 ruled card
for 30 seconds. The harness exited 0 and reported RGB restoration. This time
the same remote script captured registers two seconds after starting the
harness, while it was alive. Active scaling is confirmed by bypass clear:

```
05180000 0x0F008000
05180004 0x00100F00
05180008 0x32010000
05180014 0x00000000
05180020 0x02000000
0518002c 0x00350500
05180030 0x000102D0
05180034 0x05000280
05180038 0x0010F1C7
0518003c 0x0000E38E
05180040 0xC0000500
05180044 0x00000031
05180050 0x00270280
05140108 0x02800000
0514011c 0x02808002
05140128 0x02800000
```

Board logs: `h713-gst-transform-20260914/ruled-640-panel.log` and
`ruled-640-registers.log` under `/mnt/media-data`. Operator observation of
streak position and visible console restoration is pending.


Operator supplied `/home/chris/Downloads/IMG_0864.JPEG` and placed the 640-line
source streak between labels 640 and 680. Together with IMG_0863:

| source height | nominal output y band | source-coordinate band y * ratio |
| --- | --- | --- |
| 544 | 520–560 | approximately 393–423 |
| 640 | 640–680 | approximately 569–604 |

The disjoint bands reject both a fixed output row and a fixed source row
under the nominal scaling model. They do not establish a unique timing or
phase mechanism. The movement is 80–160 output lines for a 96-line source
height change; claiming an exact slope from these photographs is unwarranted.
The earlier 640-to-656 guard-window test with ratio unchanged remains relevant:
merely extending declared height limits did not move the streak.

Next observation: the already staged 1280x608 ruled card, with fresh watching
confirmation and active register capture. A simple linear interpolation of the
two measured bands predicts y in roughly 600–640. This is a falsifiable
interpolation check, not a firmware-derived counter prediction. A result
outside that band would reject the simple interpolation. A result inside it
would still require a separate causal test before any driver change.

### Third ruled-card observation window: 1280x608

After a fresh `watching` confirmation, held the 1280x608 ruled card for
30 seconds. Harness exited 0 and reported RGB restoration. The active
register capture, taken two seconds into the same remote script, was:

```
05180000 0x0F008000
05180004 0x00100F00
05180008 0x32010000
05180014 0x00000000
05180020 0x02000000
0518002c 0x00350500
05180030 0x000102D0
05180034 0x05000260
05180038 0x0010EC16
0518003c 0x0000D82D
05180040 0xC0000500
05180044 0x00000031
05180050 0x00270260
05140108 0x02600000
0514011c 0x02608002
05140128 0x02600000
```

Operator supplied `/home/chris/Downloads/IMG_0865.JPEG` and said it appears
the same as the previous test. Visually following the slanted ruled lines
at the streak's horizontal position puts it approximately between 600 and
640, rather than the preceding image's 640–680 band. Keep these distinct:
the operator reported similarity; the 600–640 band is the assistant's image
interpretation, not an operator-confirmed precise measurement.

This is compatible with the interpolation prediction but does not prove a
linear law, phase wrap, or underflow. The three tests now provide the requested
height comparison; further height sampling alone is unlikely to discriminate
the cause. No new register writes or kernel changes were made. Visible console
restoration remains unconfirmed by the operator.

## Linked-address correction and per-axis phase fix

The board-A file maps offset zero to **0x8b100000**, not 0x8b1008e0 as the
handoff states. Independent checks: data at linked `0x8b2071c4` is 0x10000;
`0x8b207430` contains `CalcWindow`; `0x8b20743c` contains `%s : ENTER`.
The erroneous base resolves all three to unrelated table data. Calls from the
constructor and WriteReg also resolve coherently with the corrected base.
The existing `tools/mips/disasm.py` uses the correct base, but its self-test
stub addresses are for another firmware variant and FAIL for this board-A
file. Do not report that self-test as validation of this image.

Previous instruction listings examined the right bytes but printed PCs 0x8e0
too high. Correct linked addresses are CalcWindow 0x8b1a59e0, line-start
calculation 0x8b1a5b50, proc register writer 0x8b1a5df0, and enclosing
WriteReg 0x8b1a6128. See `proc-window-linked.asm` for corrected PCs; retain the
old listing only as historical evidence, not for following calls.

The corrected trace also confirms an independent bug in patch 0108: it always
writes H=3/V=2 while scaling either axis. The firmware increments each axis
independently at unity, so vertical-only scaling needs H=4/V=2 and
horizontal-only needs H=3/V=3. Patch 0112 fixes this without changing two-axis
scaling or native restore. The latter cases already demonstrate the streak,
so this is not yet a claimed streak fix. A single-field H-phase A/B harness is
prepared at `tools/display/proc-unity-phase-ab.py`; it verifies active geometry,
changes only bits 30:28 of proc+0x08, checks readback, restores before stopping
the KMS frame, and requires explicit operator confirmation. Not yet run.

Corrected kernel series through 0112 built successfully: Image, modules,
bench/projector DTBs, and FIT. Packaging uses the existing host mkimage from
`/home/chris/Projects/h713/build/uboot-ddr3/tools/mkimage`, linked into this
worktree's ignored build directory. FIT is `build/out/h713-kernel.fit`,
7,753,216 bytes. It has not been installed. The phase-selection expression
also matched the traced firmware thresholds for 95 supported aligned
one-axis dimension cases. `git diff --check` passed. The compiled kernel is a
correctness candidate, not a verified streak fix; waiting for the requested
single-field observed A/B before deciding the next deployment step.

### H unity-phase A/B execution

After the operator said `watching`, executed the prepared harness. It verified
the active 1280x608 geometry and original proc+0x08=0x32010000, held A for
8 seconds, wrote 0x42010000 (only H integer phase 3->4) and read back exactly
0x42010000, held B for 12 seconds, restored 0x32010000 with exact readback,
and held restored A for 8 seconds. It then terminated the KMS harness, which
reported `NV12 plane disabled; KMS RGB restored`. The overall script exited 0.
The KMS harness log says 60 seconds because that was its safety dwell limit;
the A/B script intentionally terminated it after the 28-second sequence.
Operator report of streak behavior is pending. No kernel installation occurred.

Operator result for the H unity-phase A/B: **the streak did not change**.
This excludes H integer phase 3 versus 4 as the visible artifact's cause in
the 1280x608 vertical-only case. Patch 0112 remains a firmware-conformance fix,
not a streak fix. Do not repeat this A/B or deploy it as an artifact solution.

### Proc event flags located (not underflow counters)

Linked firmware handler `0x8b185d48` reads `0x05140e00`, intersects its low
byte with `0x05140034[7:0]`, and acknowledges those events using a low/high/low
pulse in `0x05140034[23:16]`, preserving other fields. Its table at linked
`0x8b202a1c` identifies bits 0=input VS, 1=input VDE, 3=upscaler VS,
4=upscaler VDE, 5=output VDE, 6=output VS, 7=scene change. These names do
not identify an underflow condition or a free-running count.

Read-only console-state check: `0x05140034=0xb0000040`,
`0x05140e00=0x0000ffff`, proc bypass `0x08000000`. All low event bits already
set makes simple snapshot comparison useless: historical pending flags cannot
be attributed to a new frame. No acknowledgement or mask writes have yet been
performed. Avoid claiming that unchanged pending flags rule out underflow.

### Event-cadence discriminator

The firmware-derived low/high/low acknowledgement worked for currently masked
bits 0,1,3,4,5. The monitor refuses enabled target bits or already-asserted
acknowledgements, preserves all other control fields, checks every control
write, and restores 0xb0000040 exactly. After ack, status changed from 0xffff
to 0xffc4. Over two seconds, console input/upscaler flags each recurred 119
times. Bit 5 reasserted at polling cadence (~2,875 observations), so it is not
usable as a frame counter with this mechanism.

A headless comparison (no visual assessment) used synthetic black for native
1280x720, horizontal-only 960x720, and vertical-only 1280x608. The first attempt
with the old `/mnt/media-data/kms-nv12-plane-test` rejected `/dev/null` before
enabling a frame because it lacks SYNTH_BLACK support. Verified the string in
`/root/kms-nv12-plane-test` and used that newer harness for all three cases.
Each frame was held for five seconds and automatically disabled afterward.

| state | bit 0 | bit 1 | bit 3 | bit 4 |
| --- | --- | --- | --- | --- |
| native | 119 | 119 | 119 | 119 |
| horizontal only | 119 | 119 | 119 | 119 |
| vertical only | 120 | 119 | 119 | 120 |

Every control restoration read back 0xb0000040. These two-second counts are
consistent with ~60 Hz across all states (window-boundary differences of one
are expected). They show no gross sync loss; they do NOT exclude a local
underflow or intra-line corruption. No underflow flag has been identified.
Board logs are `events-WIDTHxHEIGHT.json` and `events-WIDTHxHEIGHT-panel.log`
in `/mnt/media-data/h713-gst-transform-20260914`.

Next single-field observed discriminator is prepared, not run:
`proc-vertical-phase-ab.py` changes only proc+0x38 low 16 bits from 0xec16 to
zero for the same 608-line card, then restores the exact 0x0010ec16 word.
Nominal sample displacement is less than one source line (~1.1 output lines).
A much larger streak movement or disappearance would implicate phase-dependent
behavior; no change would favor other timing/buffering mechanisms. This is
not a claim of a particular accumulator-wrap law or a proposed production fix.

### Vertical fractional-phase A/B execution

After a fresh `watching` confirmation, ran `proc-vertical-phase-ab.py` on the
1280x608 ruled card. Baseline 0x0010ec16 was verified; A held for 8 seconds.
B wrote proc+0x38=0x00100000 with exact readback, held for 12 seconds, then
restored 0x0010ec16 with exact readback and held restored A for 8 seconds.
The script exited 0 and the KMS harness reported RGB restoration. Its logged
60-second dwell was the safety limit, not the actual A/B sequence length.
No ratio, integer phase, upper timing field, or window was changed. Operator
observation is pending; do not infer visual success from register readback.

Operator result for vertical fractional-phase A/B: **the streak did not
change**. This supplies no support for a simple phase-dependent explanation.
Caveat: live readback proves the register value changed, not the hardware's
latching boundary for initial phase. Do not equate a negative live phase test
with proof that all start-time phase programming is irrelevant.

### Cold boot and register-bank coupling

Operator reported a cold boot. Verified running kernel remains the old
`6.18.38 #1 SMP Mon Sep 14 00:11:33 PDT 2026`, boot ID
`3d08c776-567d-4045-8a18-981ef7b08de7`. Native values: proc+0x08=0x43010000,
+0x14=0x08000000, +0x34=0x050002d0, +0x38=0x00100000, +0x50=0x001b02d0.
p23 was not mounted; remounted it as vfat. Temporary plugin setup is gone.

A five-second headless 1280x608 synthetic-black frame then checked only bypass,
input window, and vertical ratio at offsets +0x14/+0x34/+0x3c in banks
0x05180000, 0x05180100, 0x05180200, and 0x05180300. All four read the same
active values: 0x00000000, 0x05000260, 0x0000d82d. Driver helper performs one
read and one write at the base; it does not loop over banks. This establishes
coupled/broadcast or aliased readback for these fields, and rejects the theory
that another apparent bank retains native geometry during this test. It does
not by itself distinguish a bus alias from hardware-broadcast writes.
The harness exited 0 and reported RGB restoration. Do not independently
configure other banks. Logs are proc-banks-idle.log, proc-banks-active.log,
and proc-banks-panel.log in the board test directory.

### Corrected-kernel visible baseline

After fresh watching confirmation on kernel `03:07:13 PDT`, held the ruled
1280x608 card for 30 seconds using `/root/kms-nv12-plane-test`. Active readback:
proc+0x08=0x42010000, +0x14=0, +0x34=0x05000260,
+0x38=0x0010ec16, +0x3c=0x0000d82d, +0x50=0x001b0260.
Harness exited 0 and reported RGB restoration. Operator observation pending.
Board logs: corrected-kernel-608-visible.log and
corrected-kernel-608-visible-regs.log in the test directory.

Operator confirmed the corrected-kernel visible baseline still has the streak,
and explicitly confirmed the console returned afterward. Thus patches 0109
and 0112 establish the corrected baseline but do not solve the artifact;
visible teardown is now confirmed for this ruled-card run.

### 2026-09-15 240-line vertical test

After a fresh “I'm watching”, started a 30-second SYNTH_BLACK=1
SRC=1280x240 test with /root/kms-nv12-plane-test on the cold-booted
corrected kernel. Active readback: +08=42010000, +14=00000000,
+34=050000f0, +38=0010aaaa, +3c=00005555, +50=001b00f0.
This is nominal 3x vertical magnification; the 16.16 ratio truncates 1/3
to 0x5555, so it is NOT a no-fractional-phase control. It tests a substantially
stronger magnification than previous heights. Observation and teardown
were pending when this entry was written.

The harness exited 0 after 30 seconds and reported NV12 disabled and
KMS RGB restored. Operator observation is pending. Board log:
/mnt/media-data/h713-gst-transform-20260914/vertical-240-visible.log.

Operator confirmed the streak remained and moved into the upper half.
IMG_0873.JPEG approximate perspective measurement (2048x1152 preview):
panel corners (365,85), (1820,209), (1672,936), (467,1132); streak endpoints
(1245,494), (1337,493). Four-point homography to 1280x720 gives x671–765,
y248–249. Manual edge selection and projection geometry warrant reporting
roughly y250 +/-15, not pixel precision. This places the artifact near the
240-line source boundary in OUTPUT coordinates, rather than a fixed panel row.

Prepared proc-line-count-ab.py, NOT run: held black 1280x240; only +50 low16
changes 240 -> 480 -> 240, preserving high16=27. Source window and ratio
remain fixed, and 480 is within the native 720-line allocation. This isolates
the line-count field from the earlier coupled 640->656 guard-window test.
Requires fresh watching; negative live result still has latching caveat.

### Line-count-only A/B executed

After fresh “I'm watching”, ran proc-line-count-ab.py: original count 240
for 8 seconds; +50=001b01e0 (480) with exact readback for 12 seconds;
+50=001b00f0 restored with exact readback for 8 seconds. Script exited 0,
and harness reported NV12 disabled / KMS RGB restored. The harness's printed
60 seconds was the safety dwell, not the actual A/B duration. Operator
observation is pending; readback alone does not establish visual effect.

Operator result: streak started in the upper region, moved to the lower half
during count=480 (described as almost a reflection of the top half), returned
to the upper region at count=240, then console returned. This is a reversible
visual response to +50 low16 alone; no exact displacement measured.

CRITICAL RE CORRECTION: linked CalcWindow 8b1a5b90–8b1a5b9c computes
MAX, not MIN: slt a1,a0,t0; move t6,t0; movz t6,a0,a1; sw t6,1c(s0).
If a0<t0, keep t0; otherwise select a0. Writer 8b1a5e34–8b1a5e3c puts
object+1c into proc+50 low16. Earlier min-height interpretation was wrong.
For upscale this requires output height 720, while driver writes in_h.
Prepared proc-line-count-720-ab.py (240 ->720 ->240), not yet run.

### 720-line A/B executed

After fresh “watching”, ran proc-line-count-720-ab.py: 240 lines for
8 seconds, +50=001b02d0 (720) for 12 seconds, original +50=001b00f0
for 8 seconds. Both writes had exact readback. Script exited 0; harness
reported NV12 disabled and KMS RGB restored. Operator observation pending.
No persistent driver change has been made for this field yet.

Operator missed the initial 240 interval but observed no streak during the
720 interval, then its return during restored 240 and console restoration.
This reversible result supports the maximum-height correction. Patch 0114
implements max(in_h,out_h) and corrects the field comment. Persistent boot
and content-bearing visual validation remain outstanding.

### Persistent 0114 ruled-card verification run

After verified cold boot into Sep15 17:10:03 kernel and fresh “watching”,
held the existing 1280x608 ruled card for 30 seconds through the corrected
driver, with no manual register changes. Harness exited 0 and reported
NV12 disabled / KMS RGB restored. Operator assessment of streak and full
grid integrity is pending. Board log:
/mnt/media-data/h713-gst-transform-20260914/kernel-0114-ruled-608-visible.log.

Operator confirmed the persistent 0114 ruled-card test was a clean grid
with no streak. Photo IMG_0876.JPEG supports the observation. This verifies
the cold-booted driver correction on a 1280x608 source; decoded moving
video remains to be verified.
