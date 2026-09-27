# Handoff — HDMI display lessons for video decode, 2026-09-27

This note is for Claude's Cedrus, VA-API, mpv, and panel-playback work. The HDMI
capture work reached a sustained native 1280x720 path on branch
`codex/hdmi-capture-completion`, but only part of that work belongs in the
decoder stack. The important shared boundary is the H713 AFBD DRM driver and
its fullscreen NV12 overlay, not the firmware HDMI capture ring.

The validated HDMI milestone is commit `8e44cde` (`hdmi: sustain native 720p
capture at 60 fps`). Its evidence is in
[`hdmi-evidence/2026-09-27-native-720-60fps/`](hdmi-evidence/2026-09-27-native-720-60fps/README.md).
Do not cherry-pick that commit wholesale into a decoder-only branch: it also
contains HDMI-specific cache maintenance, V4L2 diagnostics, and source-3
recovery tooling.

## What transfers directly

### 1. Physical-vsync framebuffer retirement

Commit `e406649` and kernel patch 0136 replace timer-like DRM retirement with
the AFBD physical-vsync IRQ. The display engine retained old framebuffer reads
after a new source was latched; releasing a decoded DMA-BUF too early could
leave AFBD reading an invalid IOVA. This is equally relevant to Cedrus/VA-API
buffers imported into `video-0`.

The working series is cumulative:

```text
0133 wait for scanout before releasing old framebuffer
0134 retain old framebuffer through the observed read window
0135 express retirement in vblank sequence terms
0136 drive retirement from the physical AFBD vsync counter
0137 quiesce RGB before framebuffer cleanup
```

Do not take 0136 or 0137 alone if the destination branch lacks their earlier
0133-0135 context. On a branch already containing 0133-0135, the clean commit
boundary is `e406649` followed by `6dfacb3`.

### 2. Hardware-acknowledged cleanup and console restoration

Commit `6dfacb3` and patch 0137 stop RGB fetch, wait for `AFBD_STATUS_DONE`, and
observe the next physical frame boundary before DRM releases the outgoing
framebuffer. The refined implementation also restores the complete validated
active control word; restoring only bit 0 left bit 31 set and produced a black
panel.

This benefits every transition involving the shared DRM device:

- decoded NV12 playback to fbcon;
- fbcon to decoded playback;
- client exit or failure cleanup;
- modeset teardown and shutdown;
- sequential ownership by decoder playback and HDMI preview.

The eight-vsync retirement queue remains the conservative fallback when the
explicit disable acknowledgement times out. It is also still used for active
framebuffer replacement.

### 3. Avoid a second vblank wait in GStreamer

The H713 atomic driver already commits against physical display progress. In a
camera-gated A/B, `kmssink` with its default internal vblank wait consumed the
same 360-frame NV12 stream at 29.58 fps. Setting
`skip-vsync=true` consumed it at 59.17 fps. The installed plugin describes this
property as appropriate for atomic drivers to avoid double vsync.

This is directly actionable for any decoder pipeline ending in GStreamer
`kmssink`:

```text
... ! video/x-raw,format=NV12 ! \
  kmssink driver-name=sun50i-h713-afbd sync=false skip-vsync=true
```

Treat this as a hypothesis to revalidate with decoded DMA-BUF input, not as a
reason to change mpv. mpv's direct DRM path has its own page-flip scheduling;
do not add a `skip-vsync` analogue without measuring that path independently.

### 4. Reusable acceptance pattern

The HDMI gate records DRM state before, during, and after playback. For the
decoder path, require the same facts:

- before: `plane-0` owns fbcon and `video-0` is disabled;
- during: `video-0` is on `crtc-0`, format NV12, 1280x720, with changing
  framebuffer IDs;
- after: `video-0` is disabled and the original fbcon framebuffer remains;
- no failed atomic commit, IOMMU fault, quiesce timeout, or retirement timeout;
- the operator sees a deliberately distinguishable sequence and the console
  return.

The useful accounting rule is also shared: produced work must equal displayed,
explicitly dropped, rejected, and bounded teardown work. Do not turn a small
post-EOS tail into a claim of zero drops, and do not treat it as an active-play
failure without timing evidence.

## What must stay HDMI-specific

Do **not** copy these mechanisms into Cedrus:

- `source_cached=1` and direct `dcache_inval_poc()` calls exist because the
  diagnostic bridge reads a firmware-owned, non-coherent, no-map DRAM ring.
  Cedrus must continue to use the DMA API and DMA-BUF CPU-access synchronization.
- `vb2_vmalloc_memops` helps a CPU-produced V4L2 output buffer. Cedrus capture
  surfaces must remain DMA-backed so they can reach DRM without a software copy.
- Patch 0138 exports an arm64 cache primitive for that out-of-tree diagnostic
  bridge. Patch 0139 makes the vmalloc allocator selectable for the same
  bridge. Neither is a decoder optimization.
- EDID, HPD, MIPS source-3, HDMI receiver clocks, and the cold source-3 recovery
  sequence have no place in decoder initialization.

The final combined HDMI-and-decoder product kernel may still contain 0138 and
0139 because the HDMI diagnostic module needs them. Their presence should not
change the Cedrus buffer path.

## Integration plan for Claude

### Gate 0 — establish the destination baseline

1. Work in Claude's own checkout; do not replace or modify this HDMI worktree.
2. Record the destination branch, HEAD, dirty files, patch-series length, FIT
   hash, and installed board kernel before changing anything.
3. Check whether patches 0133-0137, or equivalent code, are already present.
   Compare behavior and code rather than trusting patch numbers if that series
   has been renumbered.
4. Preserve unrelated decoder and userspace changes. Stop if the AFBD sections
   have overlapping uncommitted edits that cannot be reconciled safely.

### Gate 1 — integrate only the shared DRM fixes

1. If 0133-0135 are already present, integrate `e406649` then `6dfacb3`.
2. Otherwise port the complete 0133-0137 sequence in order. Do not transplant
   only the final cleanup hunk.
3. Inspect the resulting `sun50i-h713-afbd.c` and require all of the following:

   - framebuffer references retire from the independent physical-vsync count;
   - active replacement retains the outgoing framebuffer for eight scans;
   - driver removal and shutdown drain pending retirements;
   - CRTC disable quiesces RGB and waits for READY, DONE, and a physical scan;
   - the next RGB commit writes the complete saved active control word;
   - timeout paths retain the conservative fallback rather than freeing early.

4. Build the full FIT. The AFBD driver is built in, so a module copy cannot
   validate this change.

### Gate 2 — preserve decoder correctness before touching the panel

Run the current headless decoder gates first:

1. `va-decode-test.sh` and `hevc-decode-test.sh`;
2. MPEG-2 and other codec regressions used by the destination branch;
3. one decoder concurrency run;
4. the provenance/drift check from `decode-production-readiness.md`.

Require bit-exact results and no new timeout, IOMMU, or failed-job messages.
These tests do not prove display behavior; they only prevent a display change
from hiding a decoder regression.

### Gate 3 — cold-boot display and static ownership checks

This gate changes the visible panel. Fully prepare it, state the expected
sequence, then obtain a **fresh explicit `Camera ready`** from the operator.
Never reuse confirmation from a previous test.

1. Install the new FIT and perform a physical cold power cycle. Do not warm
   reboot: warm reboot is a known black-panel failure mode.
2. Confirm the U-Boot logo or another established positive control before
   interpreting Linux display failures.
3. Verify the Linux console, active AFBD control word, and zero initial IOMMU
   faults.
4. For every manual mpv test, set `LIBVA_DRIVER_NAME=v4l2_request`; a cheerful
   mpv DRM line is not proof of hardware decode.
5. Play visually distinguishable H.264, HEVC, Main10, and native 720p cases.
   Insert a black separator or a title card between cases that would otherwise
   look alike.
6. While each plays, require `video-0` on `crtc-0`, NV12 1280x720, and changing
   framebuffer IDs. After each exit, require the overlay disabled and fbcon
   visibly restored.

### Gate 4 — presentation cadence

1. Use [`tools/display/kms-nv12-plane-test.c`](../tools/display/kms-nv12-plane-test.c)
   with its Cedrus and moving-frame modes to collect DRM page-flip event
   timestamps, not merely ioctl return times.
2. Report flip count, elapsed time, interval distribution, and one/two/three
   refresh-period histogram. A 60 fps average alone can conceal doubled gaps.
3. Separately run the decoded GStreamer path with and without
   `skip-vsync=true`. Require the expected near-30 versus near-60 A/B before
   changing its default invocation.
4. For the passing configuration, require the requested frame count, no sink
   drops, no failed atomic commit, and normal console restoration.

This gate also changes the visible panel and requires its own fresh camera
checkpoint. The camera is an optical cross-check; DRM page-flip events are the
authoritative cadence measurement.

### Gate 5 — cleanup, failure, and shared ownership

1. Repeat decode start/stop at least ten times and check console return after
   every run.
2. Terminate one playback client while the NV12 plane is active. Require the
   overlay to release, fbcon to return, and the next playback to work.
3. Exercise one source-format or resolution transition already supported by
   the decoder; keep the known ffmpeg-side mid-stream-resolution limitation
   separate from DRM cleanup results.
4. In the combined image, test sequential ownership:

   ```text
   decoder -> console -> HDMI preview -> console -> decoder -> console
   ```

   The paths share one `video-0` plane and are not expected to display
   concurrently. Normal DRM ownership must reject or serialize contention;
   neither client may bypass it with direct register writes.
5. After the sequence, require zero IOMMU faults, zero quiesce/retirement
   timeout, no leaked DRM client, and successful decode of a known-good vector.

### Gate 6 — decide what becomes production policy

Only after Gates 0-5 pass:

1. Keep 0133-0137 in the merged kernel as shared display correctness fixes.
2. Add `skip-vsync=true` to the supported GStreamer KMS invocation if the
   decoded-input A/B reproduces the HDMI result.
3. Keep mpv unchanged unless its own page-flip timing identifies a defect.
4. Keep HDMI cache/vmalloc options scoped to the diagnostic bridge.
5. Save exact FIT, kernel, userspace, clip, and test-tool hashes with the
   evidence. Do not label the result low latency until source-to-panel optical
   latency is measured separately.

## Acceptance summary

| area | required result |
| --- | --- |
| decode correctness | existing bit-exact gates unchanged |
| DRM ownership | changing 1280x720 NV12 framebuffer IDs on `video-0` |
| cadence | page-flip histogram matches content cadence; no unexplained doubled gaps |
| cleanup | overlay disabled and fbcon visibly restored every time |
| memory safety | zero IOMMU faults and no early framebuffer release |
| failure recovery | killed client does not poison the next playback |
| coexistence | decoder and HDMI work sequentially through normal DRM ownership |
| latency claim | withheld until timestamped source-to-panel measurement exists |

The key distinction for later work is simple: **share the DRM lifetime and
presentation fixes; do not share the HDMI ring's cache workaround.**
