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

## 5. Remaining display defect: grey streak

Vertical-only 1280x544 and two-axis 960x544 scaling produce the right full
image but add a short grey horizontal streak. It occurs on decoded video and
on a uniform limited-range NV12 black source. A software-scaled native
1280x720 copy is clean.

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

## 6. Correction required before the next kernel build

Patch `0109-drm-h713-account-for-proc-scaler-line-latency.patch` currently
forces proc line start 39 whenever scaling. Its premise needs correction.

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

The disassembly at `0x8b1a5b50` computes:

```
line_start = in_vs_delay + 1 + upstream_vertical_start + mb_420_format
```

For this progressive AFBD path, vertical scaling alone does not establish a
15-line input delay. The earlier inference that 39 is a generic scaler latency
was wrong. Patch `0109` should be removed or rewritten so the progressive
path retains the boot value 27. This will not itself fix the streak: the streak
was present before `0109`, and cold-boot tests showed no change after it.

Patch `0111` has a similarly overconfident commit message claiming the route
window mismatch causes the invalid segment. Its code matches firmware and is
a valid correctness fix, but the message should state that hardware testing
showed it was not the streak's cause.

## 7. Best next investigation

The newest result argues for reconstructing the vertical engine's boundary
and phase semantics rather than changing more windows. Continue from the
firmware `ProcWinNode::CalcWindow` at `0x8b1a59e0` and `WriteReg` near
`0x8b1a5df0` in:

```
local/h713-lab/analysis/board-a-stock-20260622/bootloader_a_files/mips/display.bin
file offset 0 == MIPS 0x8b100000 (corrected by linked calls and data references)
```

Verified calculations:

- `ratio_v = floor((in_h << 16) / out_h)`;
- fractional V phase is `(0x10000 + ratio_v) >> 1`;
- upscale integer V phase begins at 2;
- unity wraps fractional phase to zero and advances integer V phase to 3.

Useful discriminators, in order:

1. Recover the meaning and writer of every live upper field in proc instance
   0, especially fields retained from the boot-time unity setup. Compare
   firmware scaled-path values with Linux values rather than assuming the
   low-field `ins` operations are the entire stage configuration.
2. Establish whether the streak position follows a phase-accumulator event.
   Use two or three source heights whose ratios place the fractional wrap at
   widely separated output lines and record the streak's panel y coordinate.
   Generate a high-contrast ruled card so the y coordinate can be measured
   from a photograph. Prompt the operator before each observation.
3. If the predicted phase-wrap line matches, vary only initial V fractional
   phase by a calculated amount that moves the wrap to a known line. This is a
   narrow A/B test, not a sweep.
4. If it does not match, inspect status/underflow counters dynamically during
   native, horizontal-only, and vertical-only frames. Capture them headlessly
   and avoid the two forbidden MMIO ranges.

Do not configure proc instance 1 speculatively. Prior tests showed instances 0
and 1 can both affect video, but firmware has only one `lui 0xba18` writer and
hardcodes instance 0. Enabling another scaler stage risks double-scaling and
does not follow from the current evidence.

## 8. GStreamer and completion criteria

The two GStreamer patches add `output-width`, `output-height`, and `rotation`
to the stateless H.264 decoder and advertise the active compose rectangle while
preserving the larger capture canvas. They were applied to exact 1.26.2 source
and passed a minimal host Meson build.

They still need to be built and deployed on the board. Build under mounted p23
because `/` has no free space. Then run an end-to-end pipeline that requests
1920x1080 H.264 -> Cedrus 960x544 -> DRM 1280x720 and verify playback, rotation
at 90/180/270, teardown back to console, and repeated start/stop. The visible
vertical scaling streak must be resolved or explicitly bounded before calling
the video path complete.



## 9. Continuation in the isolated Codex worktree

See `reference/gstreamer-board-validation-2026-09-14.md` for current board
validation. The original sections above describe the incoming state. Locally,
0109 now preserves progressive line start and 0111 no longer claims to solve
the streak; both patch applications were checked with zero fuzz. These kernel
changes have not been built/deployed or cold-booted yet.

The p23 filesystem is mounted at `/mnt/media-data`. An isolated patched
GStreamer plugin is built under `h713-gst-transform-20260914`; it requires the
explicit plugin environment recorded in the validation note. The stock plugin
was not replaced. No new panel test has started; the operator was asked to
confirm watching for the first ruled 1280x544 test.

## 10. Corrected FIT installed; next cold power-cycle required

After the operator's intervening cold boot (boot ID
`3d08c776-567d-4045-8a18-981ef7b08de7`), installed the locally built kernel
through 0112 using `tools/install-kernel-fit.sh`, without --reboot. Successful
backup and boot-FAT remount/readback verification:

- New FIT: 7,753,216 bytes,
  SHA-256 `8bf82190b7d98278bd502bf4796443c2c6902fe3d29172c57afa6983af6fca0f`,
  MD5 `2745430f9d303681254bf001a0790550`.
- Previous FIT backup:
  `/mnt/media-data/h713-kernel-fits/replaced-20260914-093150.fit`.
- Runtime still has the old kernel until a new cold power-cycle.
- Cedrus module was not replaced; preserve the verified rotation implementation.
- 0109 now preserves progressive line start; 0111 message is corrected;
  0112 fixes per-axis unity phase. These are NOT a verified grey-streak fix.
- Both H integer-phase and V fractional-phase live A/Bs left the streak unchanged.
- Frame event cadence was normal (~60 Hz) in native/H-only/V-only tests;
  no specific underflow flag has been found.
- Apparent proc banks share active geometry readback after bank-0-only writes;
  do not configure a second bank independently.

See the appended proc reference note for exact observations and limits. Ask
for a cold power-cycle now, verify the new boot, then obtain fresh watching
confirmation before any test that needs panel observation.

### Corrected kernel cold-boot verification

Operator cold power-cycled after installation. First SSH attempt timed out
during startup; retry succeeded. Running kernel is now
`6.18.38 #1 SMP Mon Sep 14 03:07:13 PDT 2026`, boot ID
`eec2a7e5-dae5-43b5-ab4d-23184b678945`. Idle proc state is native/bypassed.

A four-second headless synthetic-black 1280x608 frame verified the corrections:
proc+0x08=0x42010000 (H unity integer 4, V upscale integer 2),
+0x14=0, +0x34=0x05000260, +0x38=0x0010ec16,
+0x3c=0x0000d82d, +0x50=0x001b0260 (progressive line start 27).
Harness exited 0 and reported RGB restoration. This was register verification,
not visual validation. Recreated the isolated GStreamer plugin directory and
registry in /tmp. Existing Cedrus module passed 60 frames of 1080p H.264 to
960x544 NV12/fakesink with the patched plugin, exit 0. Board logs:
corrected-kernel-608.log and corrected-kernel-decode.log in the test directory.
A visible observation on the corrected cold-boot baseline is still needed.

### Latest operator and decoder results

Operator confirmed the corrected-kernel 608-line card still has the streak
and the console returned. No streak fix has been established.

Module patch 0113 is now built and loaded: it maps scale fields to rotated
output axes. Oversized tiny pixel captures prove the correction, and all
four 1080p rotations into a 1280x720 canvas passed 60 frames, including the
formerly faulting asymmetric quarter turns. See the appended rotation note
for evidence, module backup, and recovery from full-root depmod failure.

Next useful panel discriminator: 1280x240 black source (exact 3x vertical
upscale). Exact 2x would require 360 source lines, which the current 16-line
alignment contract rejects. Obtain fresh watching confirmation first.

### 2026-09-15 cold boot

Verified boot ID d4231b15-d5ee-4191-a557-05480addf8b3, kernel still
03:07:13 PDT and installed/loaded Cedrus module through 0113, MD5
8ea937c5bc8cc05bcc1090a502d7fb88. Remounted p23 and recreated the
isolated GStreamer environment. Both 90 and 270 degree 1080p decodes into
1280x720 canvas passed 60 frames after cold boot, with no new decoder fault.
Twelve previous repeat logs exist and are empty, but the interrupted task
did not retain their final exit-status output; do not count them as independently
verified passes. Asked for fresh watching for a 30-second 1280x240 black
vertical-scale panel test; that test has NOT yet run.

### Grey streak: causal field found, patch 0114 building

240-line black source: photo IMG_0873 gives approximate output y250 +/-15.
Single-field A/B +50 low16 240->480->240 moved the streak down and back.
Re-reading CalcWindow 8b1a5b90 exposed an earlier min/max mistake: slt;
move; movz selects MAX(input height, output height).

Fresh operator-confirmed 240->720->240 test: operator missed initial A,
but observed no streak in B and its return in restored A, then console.
Patch 0114 changes PROC_FRAME_LINES to max(in_h,out_h), keeps upper start
field and all geometry/ratios unchanged. Full clean-series kernel build is
running. AFBD is built-in, so FIT install and cold power-cycle are necessary.
Persistent ruled-card and decoded-video validation are still required.

### Patch 0114 installed, awaiting cold power-cycle

Full clean-series build through 0114 passed (Image, modules, bench/projector
DTBs, FIT). Build tree digest:
72d41a56277a333da6589cbc076f927290febeed5fb89af17231dd7566bde47a.
FIT 7,753,608 bytes, SHA256
aa3adb18af26376a7c93bd7346f55bae5a86ac9505e4308970ed5aa4cd0cafe0,
MD5 2cae85bdbe263b89d24831ba8e042f9f. Installed with boot-FAT remount
and readback verification, no reboot. Backup:
/mnt/media-data/h713-kernel-fits/replaced-20260915-171029.fit.
Cedrus module through 0113 remains installed. Current boot before installation
was d4231b15-d5ee-4191-a557-05480addf8b3, kernel Sep14 03:07:13 PDT.
Next: user cold power-cycle, verify new kernel and driver count=720 during
scaled frame, then fresh watching for ruled-card and decoded-video validation.
Do not rerun the old A/B scripts expecting +50 low16=source height on 0114.

### 0114 cold boot verified

New running kernel: 6.18.38 #1 SMP Tue Sep 15 17:10:03 PDT 2026.
Boot ID 8086d5be-08ce-4d48-95ff-0b0c3596995d. Cedrus module checksum
remains 8ea937c5bc8cc05bcc1090a502d7fb88. Remounted p23.
Four-second headless 1280x608 black register check passed: +08=42010000,
+14=0, +34=05000260, +38=0010ec16, +3c=d82d, +50=001b02d0.
Driver now programs 720 lines automatically; no MMIO writes were made.
Harness exited 0 and reported RGB restoration. Visual confirmation still
needed; next test is the existing 1280x608 ruled card after fresh watching.

### Ruled card clean; decoded playback prepared

Operator confirmed clean 1280x608 grid, no streak, with IMG_0876.JPEG.
Updated tools/display/kms-nv12-plane-test.c with opt-in CEDRUS_TRANSFORM=1
setting patched decoder output-width=1280/output-height=720. Also fixed
existing g_shell_quote misuse: GstParse treated single quotes as part of the
filename; now assigns filesrc location via g_object_set before PLAYING.
Built with -Wall -Wextra -Werror as board testdir/kms-nv12-transform-test.
With isolated plugin environment, SRC=960x544 CEDRUS=1 CEDRUS_TRANSFORM=1
DECODE_ONLY=1 acquired frame60 DMA-BUF and exited0, no display commit.
Next fresh-watching test: same environment, omit DECODE_ONLY, MOVING=1
PACED=1, /root/leota-1080p.h264, dwell30. This moving test has NOT run.
