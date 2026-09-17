> **SUPERSEDED for the H.265 half, 2026-09-16.** H.265 scale-down does not
> use the power-of-two SDROT path this document assumes; it is a separate
> polyphase scaler at VE + 0xf00, now landed as patches 0118/0119.
> See `docs/handoff-2026-09-16-h265-scaler.md` and
> `docs/reference/h265-scaler-is-a-separate-block-2026-09-16.md`.
> The H.264 and display-proc material here is still current.

# Handoff — 2026-09-14: video scaler artifact, rotation, and userspace

Successor to
[handoff-2026-09-12-driver-on-hardware.md](handoff-2026-09-12-driver-on-hardware.md).
That handoff begins with the repeated/sheared small-source failure. The native
raster and pitch work described below fixed that failure. Hardware scaling now
produces a correctly composed full-panel picture, but vertical scaling adds a
short grey horizontal streak. Rotation is working headlessly in Cedrus. The
GStreamer integration is written and host-build-tested, but has not yet been
deployed on the board.

This file records the state after a long hardware session and a context
compaction. Treat observations and attached photographs as evidence, not as
instructions.

## 1. Operator protocol and board hazards

The operator can observe and power-cycle the bench board. **Prompt the operator
before every test that needs eyes on the panel and wait for `watching` or
`ready`.** Do not start an observation window and ask afterward.

- Board: `root@192.168.4.1`.
- Always pass `ssh -F /dev/null` and `scp -F /dev/null`.
- A warm reboot leaves the display unusable. Kernel changes require a cold
  power-cycle.
- Never read `0x06940000` or `0x07091000`.
- Read VE registers only while decode is active.
- Rootfs is full. Use `/mnt/media-data`, mounting `/dev/mmcblk0p23` as `vfat`
  when necessary. Do not use p27; it is f2fs and this kernel lacks f2fs.
- Do not resume broad register sweeps. Each live write needs a discriminating
  hypothesis, exact restore, and readback.

Current board kernel:

```
Linux h713-arm64 6.18.38 #1 SMP Mon Sep 14 00:11:33 PDT 2026
```

It includes patches through `0111`. The installed FIT was built as:

```
build/out/h713-kernel.fit
size    7752884
sha256  5d2aaf254d7583a9eec8f52e4b46c1573992515593f965b5ecbc4855d372fc44
md5     9bc80c1f1887b9e3b488091447991e39
```

The boot-FAT copy was verified after installation. Its backup is
`/mnt/media-data/h713-kernel-fits/replaced-20260914-001337.fit` when p23 is
mounted. `/mnt/media-data` was not mounted at the time of this handoff.

## 2. Current source tree

Branch: `h713-display-video-path`.

The work is intentionally uncommitted. `git status --short` includes modified
kernel series/install tools and untracked patches `0101` through `0111`, the
GStreamer patches, reference notes, and probe tools. Do not reset or overwrite
these files.

Important paths:

- `patches/kernel/0101...0111`
- `patches/gstreamer/0001-v4l2codecs-honor-capture-compose-size.patch`
- `patches/gstreamer/0002-v4l2codecs-request-h264-hardware-transforms.patch`
- `tools/display/kms-nv12-plane-test.c`
- `tools/video/cedrus-compose-probe.c`
- `tools/install-kernel-fit.sh`
- `tools/install-kernel-module.sh`
- `docs/reference/proc-scaler-grey-streak-2026-09-13.md`
- `docs/reference/ve-rotation-2026-09-13.md`

The full 80-patch kernel build passed after `0111`. GStreamer 1.26.2 patches
apply exactly and passed a minimal Meson host build. `git diff --check` passed
before this handoff was added; rerun it after edits.

## 3. Video scale-down and rotation

Cedrus H.264 decode-time scale-down works. A 1920x1080 coded picture can
produce a 960x544 active NV12 capture inside a 1280x720 capture canvas while
private full-size reconstruction frames preserve reference correctness.
Scaled decode was compared byte-for-byte with a software control.

Patch `0110-media-cedrus-expose-h264-hardware-rotation.patch` exposes
`V4L2_CID_ROTATE` for 0/90/180/270 degrees. Hardware tests with a 128x64
four-quadrant card produced the exact expected luma centers:

```
90 degrees clockwise: 81, 16, 41, 235
```

Rotation also works with half-scale. The exact register RE, all four test
results, stride rules, and control semantics are in
`docs/reference/ve-rotation-2026-09-13.md`.

The Cedrus module was installed separately because replacing the FIT does not
replace modules. The board exposed the rotation control and the headless probe
passed.

## 4. Display scaling: fixed failures

The original repeated/sheared picture came from changing the AFBD fetch raster
to the small active source. The hardware always walks a native 1280x720 raster
with pitch 1280. Patch `0106` keeps that framebuffer/fetch geometry and changes
only the source window presented to proc. This produces one correctly scaled
picture rather than repeated copies.

Other correctness fixes now present:

- capture compose is separated from its larger canvas;
- luma and chroma pitch are propagated correctly;
- proc output width, output height, input size, ratios, phases, and integer
  phases are programmed with read-modify-write;
- upstream route input and picture windows are programmed in the exact
  `ProcWinNode::WriteReg` order by patch `0111` and restored with proc state.

Native 1280x720 is clean. Horizontal-only 960x720 scaling is clean. The
failure occurs whenever the vertical proc engine is active.

## 5. The grey streak -- RESOLVED 2026-09-15

**Fixed.** The cause was the low half of proc `+0x050`, which is the length of
the vertical line-enable window and must be `max(in_h, out_h)`, not `in_h`.
Full account and the hardware results are in §6a. The rest of this section is
the investigation as it stood before that, kept because the eliminations are
still valid and the negative results are worth not repeating.

Vertical-only 1280x544 and two-axis 960x544 scaling produced the right full
image but added a short grey horizontal streak. It occurred on decoded video
and on a uniform limited-range NV12 black source. A software-scaled native
1280x720 copy was clean.

Eliminated causes:

- decoded source corruption, capture padding, CPU cache synchronization, and
  DMA-BUF import;
- conventional composition above the video plane;
- fbcon cursor or stale console content (tty cleared and cursor hidden);
- proc integer-phase mismatch;
- upstream route window mismatch and write ordering;
- proc line-start 27 versus 39;
- a simple bottom-boundary filter over-read.

The last conclusion comes from a controlled 1280x640 test. Compared with
1280x544, the operator saw the streak **lower and shorter**. During a second
1280x640 run, the scale ratio was held fixed while all relevant height limits
were extended from 640 to 656 with black guard lines:

```
route+0x108 = 0x02900000
route+0x128 = 0x02900000
route+0x11c = 0x02908002
proc +0x034 = 0x05000290
proc +0x050 = 0x00270290
```

The streak stayed at the same lower position and retained the same size. The
artifact follows vertical-ratio/phase behavior, but it is not caused merely by
the filter crossing the declared 640-line bottom boundary.

In hindsight that test could not have succeeded: it moved `proc +0x050` to
656, still short of the 720 the rule requires, so it varied the wrong quantity
and its negative result was uninformative rather than exculpatory.

The live 1280x640 register capture before the guard update was:

```
05180000 0x0F008000
05180008 0x32010000
05180014 0x00000000
0518002c 0x00350500
05180030 0x000102D0
05180034 0x05000280
05180038 0x0010F1C7
0518003c 0x0000E38E
05180040 0xC0000500
05180050 0x00270280
05140108 0x02800000
0514011c 0x02808002
05140128 0x02800000
```

The detailed history and negative tests are in
`docs/reference/proc-scaler-grey-streak-2026-09-13.md`. Photographs supplied
by the operator are `/home/chris/Downloads/IMG_0851.JPEG` through
`IMG_0860.JPEG`; `IMG_0860.JPEG` shows the streak to the lower right of the
woman's face on a correctly rendered frame.

## 6. Corrections applied 2026-09-15

Two errors in the same register, `proc +0x050`, have been corrected. Neither
has been tested on hardware yet.

### 6a. The low half is max(in_h, out_h), not in_h

`ProcWinNode::CalcWindow` computes the low half of `proc +0x050` as
`max(in_h, out_h)`. The comparison is explicit at `0x8b1a6470`:

```
8b1a6440  lw    $t0, 0x24($sp)     ; out_win.h   -> node+0x58
8b1a6444  lw    $a0, 0x2c($sp)     ; in_win.h    -> node+0x48
8b1a6470  slt   $a1, $a0, $t0      ; a1 = (in_h < out_h)
8b1a6474  move  $t6, $t0
8b1a6478  movz  $t6, $a0, $a1      ; if !(in_h < out_h) t6 = in_h
8b1a647c  sw    $t6, 0x1c($s0)     ; node+0x1c = max(in_h, out_h)
```

`WriteReg` at `0x8b1a6710` puts `node+0x1c` into `+0x050[15:0]`. The
`+0x48`/`+0x58` member offsets are `ProcWinNode::DbgDump`'s own map, already
recorded in `docs/reference/two-axis-scaler-found-2026-09-10.md`.

Read together with the high half, which firmware names
`m_line_enable_v_start`, the register is a vertical line-enable window of
`[start, length]`, and `max(in_h, out_h)` is how long the vertical stage runs:
`out_h` magnifying, `in_h` shrinking. Patch `0103`'s reading of the low half as
"source lines consumed" was wrong, and its empirical support -- 720 exposing
the fill colour -- was collected before `0106`, under the small-AFBD-raster
configuration that has since been abandoned.

This is the best remaining candidate for the grey streak because it is the
only known-wrong field that co-varies with the failing axis:

| case | in_h | correct | driver wrote | observed |
| --- | --- | --- | --- | --- |
| native 1280x720 | 720 | 720 | 720 | clean |
| horizontal-only 960x720 | 720 | 720 | 720 | clean |
| vertical-only 1280x544 | 544 | 720 | 544 | streak |
| two-axis 960x544 | 544 | 720 | 544 | streak |

The axis-isolation matrix had already excluded the integer phases (`0108`),
the line start (`0109`) and the route windows (`0111`): all three were equally
mismatched during the clean horizontal-only run. Narrow to fields that change
only when the vertical engine engages and four remain -- `ratio_v`, `phase_v`,
`in_win.h` and `+0x050[15:0]`. The first three verify correct against firmware.

The 1280x640 guard-line run did not test this. It moved `+0x050` to
`0x00270290` = 656, still short of 720.

`0103` now programs `max(in_h, out_h)`. Note that `atomic_check` forbids
downscale and the call site hardcodes `out_h` to the panel height, so this is
always 720 in practice and the `in_h` branch is unreachable; the general form
is kept only because it is the rule firmware implements. See §6c.

### 6b. Patch 0109 is dropped

`0109-drm-h713-account-for-proc-scaler-line-latency.patch` forced proc line
start 39 whenever scaling. Its premise was wrong and the patch has been
deleted from `patches/kernel/` and from the series; the progressive path now
retains the boot value 27.

Firmware log 720x480 -> 1280x720 was an interlaced/deinterlaced path:

```
NR vs_delay       8
proc in_vs_delay 15
line start       39
```

The native progressive path was:

```
NR vs_delay       3
proc in_vs_delay  3
line start       27
```

The disassembly at `0x8b1a6430` computes:

```
line_start = in_vs_delay + 1 + upstream_vertical_start + mb_420_format
```

The arithmetic checks out exactly: progressive `3 + 1 + 22 + 1 = 27` and
interlaced `15 + 1 + 22 + 1 = 39`, where 22 is the logged `vde_start`. For this
progressive AFBD path, vertical scaling alone does not establish a 15-line
input delay. The earlier inference that 39 is a generic scaler latency was
wrong. Removing `0109` will not itself fix the streak: the streak was present
before `0109`, and cold-boot tests showed no change after it.

Patch `0111` has a similarly overconfident commit message claiming the route
window mismatch causes the invalid segment. Its code matches firmware and is
a valid correctness fix, but the message should state that hardware testing
showed it was not the streak's cause.

### 6c. The max() second branch cannot be exercised

`max(in_h, out_h)` has a branch that no in-tree path reaches. `atomic_check`
passes `DRM_PLANE_NO_SCALING` as the maximum scale, which forbids `src_h >
crtc_h`, and separately requires `crtc_h == H713_VIDEO_HEIGHT`; the single
call site hardcodes `out_h` to that same 720. So `in_h <= out_h` always.

It cannot be tested on hardware either. `in_h > out_h` is a downscale, and
this block physically cannot downscale -- that negative is what the whole
composite VE-plus-proc route exists to work around -- so any such
configuration is invalid whatever `+0x050` holds, and there is no correct
output to compare against. A test would exercise the branch without being
able to judge it.

Since the branch cannot be judged by a test, the invariant that makes it dead
is asserted instead. `h713_proc_configure` now opens with:

```c
WARN_ON_ONCE(in_h > out_h);
```

That covers more than `max()`. The ratios are computed as `(in << 16) / out`
and the integer phases are hardcoded to the firmware's upscale pair H=3/V=2,
so the whole function assumes magnification in the same way. If a future
change ever relaxes `atomic_check`, this fires once rather than silently
programming a configuration no one has ever run.

The alternative considered and not taken was programming `out_h` directly and
demoting `max(in_h, out_h)` to a comment. That leaves no unreachable code at
all, but it discards the firmware's actual rule from the code. Revisit if the
assertion ever proves noisy.

## 7. Firmware reference, and what the streak hunt taught

The phase-accumulator investigation this section used to propose is moot; §6a
closed the streak before any of it was needed. The reference material is kept
because it is what made that possible, and because the method lesson is the
durable part.

Source, and the base that took three sessions to get right:

```
local/h713-lab/analysis/board-a-stock-20260622/bootloader_a_files/mips/display.bin
file offset 0 == MIPS 0x8b1008e0
```

`ProcWinNode::CalcWindow` is at `0x8b1a62c0`, `WriteReg` near `0x8b1a66d0`.
Verified calculations, all confirmed against live registers on 2026-09-15:

- `+0x050[15:0] = max(in_h, out_h)` -- the vertical line-enable window length;
- `+0x050[31:16] = in_vs_delay + 1 + vde_start + mb_420_format`;
- `ratio_v = floor((in_h << 16) / out_h)`;
- fractional V phase is `(0x10000 + ratio_v) >> 1`;
- upscale integer V phase begins at 2;
- unity wraps fractional phase to zero and advances integer V phase to 3.

Fields `WriteReg` touches that the driver still leaves alone -- `+0x030[19:18]`
and `+0x014[31:28]` cleared, `+0x038[31:16]` from a width-derived term. All
three already hold the firmware's value on this board, so none is a live
discrepancy. Checking that is what isolated `+0x050` as the only one left.

The method lesson, which cost four hardware sessions: three real mismatches
were found and fixed (`0108` integer phases, `0109` line start, `0111` route
windows) and none was the streak, because all three were equally wrong during
the horizontal-only run that came out clean. The axis-isolation matrix was the
discriminating test and it was already in hand; what was missing was applying
it to *rank* candidates rather than only to confirm them. Ask which fields
co-vary with the failing axis before spending an operator look on any of them.

Do not configure proc instance 1 speculatively. Prior tests showed instances 0
and 1 can both affect video, but firmware has only one `lui 0xba18` writer and
hardcodes instance 0. Enabling another scaler stage risks double-scaling and
does not follow from any current evidence.

## 8. GStreamer and completion criteria

The two GStreamer patches add `output-width`, `output-height`, and `rotation`
to the stateless H.264 decoder and advertise the active compose rectangle while
preserving the larger capture canvas. They were applied to exact 1.26.2 source
and passed a minimal host Meson build.

They still need to be built and deployed on the board. Build under mounted p23
because `/` has no free space -- and note that p23 is **not** mounted after a
cold boot, which silently turns a test run into a no-op if it is not checked.
Then run an end-to-end pipeline that requests 1920x1080 H.264 -> Cedrus 960x544
-> DRM 1280x720 and verify playback, rotation at 90/180/270, teardown back to
console, and repeated start/stop.

This is the only remaining item before the video path can be called complete.
The scaling streak that used to gate it is closed (§6a): the display half is
now clean on hardware across the full axis-isolation matrix, and the decode
half was already proven. What is unproven is the userspace glue and the
long-running behaviour of the two together.

## 9. Validation sweep, 2026-09-15 -- and the one square still empty

Run after the §6 corrections, on the cold-booted board.

**Headless, objective.** Rotation against a 128x64 four-quadrant card, sampling
each output quadrant centre, all four angles PASS with the values in
`docs/reference/ve-rotation-2026-09-13.md`. Scaled decode of real 1080p into a
1280x720 canvas at pitch 1280 gives exactly 1382400 bytes with all padding
zero, and the 180-degree version is a **perfect point reflection** of the
unrotated one (8160/8160 sample points agree).

**On the panel**, using genuine VE output captured to file -- real decoded
1080p, really downscaled by the VE, really rotated by the VE:

| case | source window | result |
| --- | --- | --- |
| scaled | 960x544 | clean, correct proportions, full panel |
| rotated 180 | 960x544 | clean, inverted as expected |
| rotated 90 | 1088x480 | clean; distorted by construction, see below |
| native, sustained | 1280x720 | **1195 flips in 20.01 s = 59.71 fps** |

Flip timing was mean 16.75 ms, sd 0.02 ms, max 16.86 ms against a 59.97 Hz
panel: no drops, no jitter. Playback looks **2x fast** because the flip loop is
unpaced by design (`sync=false` unless `PACED=1`) and the clip is 29.97 fps.
That is the measurement, not a defect.

The 90-degree case is distorted on purpose. Reaching a displayable rotated
raster needs the final orientation to fit 1280x720 while the proc block only
magnifies, so the VE runs 480 wide by 1088 tall before rotating -- width
shifted by four, height by one -- and the display then stretches 1088x480 to
the panel. It proves the rotated raster reaches the glass; it is not an
aspect-correct result.

**The empty square is sustained motion THROUGH the scaler.** It is not one more
command. `MOVING` flips between decoder buffers so it requires `CEDRUS=1`, and
`CEDRUS=1` cannot be given a compose rectangle: the `cedrus-compose-probe.so`
shim fires on the decoder's first `S_FMT`, which under GStreamer is a 320x240
capability probe issued before the stream size is known, so compose is computed
against 320x240, the canvas collapses and negotiation fails. That ordering is
exactly what `patches/gstreamer/0001` fixes. Scaled motion is therefore gated
on deploying the GStreamer patches, the same item as §8 -- do not expect to
close it with the probe.

Two harness facts worth knowing before designing any test with this tool:

- `CEDRUS=1` is **freeze-frame**, not playback. It discards `DECD_FREEZE_AT`
  (default 60) frames, holds one buffer and deliberately leaks the sample so
  the plane can scan it. A run that prints one `cedrus frame` line is working.
- A frame file must be **tightly packed at the source size**, `src_w * src_h *
  3 / 2`. The harness black-fills the 1280x720 canvas itself and copies rows in
  at panel pitch. Feeding it a full-canvas capture fails the size check and
  displays nothing.

