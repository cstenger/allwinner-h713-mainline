# HDMI capture on the current video stack

This run rebased the native HDMI capture path onto the current video-decode
branch and exercised the complete physical route:

```text
GPU HDMI-A-1 -> H713 HDMI1 receiver -> V4L2 NV16 capture
  -> GStreamer NV12 conversion -> H713 DRM video plane -> panel
```

The operator confirmed the visible result: “I saw the operating system menu
and the test video run as expected.”  The Linux console returned afterward.

## Build identity

- branch: `codex/hdmi-capture-current`
- presentation-diagnostics integration: `026eb52`
- interactive latency harness: `5f93bad`
- dynamic capture/output discovery: `c7e7a61`
- kernel: `Linux h713-arm64 6.18.38 #1 SMP Mon Oct 5 18:56:45 PDT 2026`
- FIT SHA-256:
  `84a590ea68e4186d6f9b00a2da5db89fcd7d0ee3738232227e1e956de65efe1f`
- source-3 probe module SHA-256:
  `da78b61bf86c3f434e433ff5a7ffe9dd752198e6253b04d5b4080e659701975d`
- HDMI V4L2 module SHA-256:
  `04e216ae0cfe362893d94e3dca07cf9f29b2cf4eae70f56e80b3dd256dc31d0d`

Both modules reported `6.18.38 SMP mod_unload aarch64` vermagic.  The outgoing
FIT was retained on the board as
`/mnt/media-data/h713-kernel-fits/replaced-20261005-185747.fit`.

## Cold source-3 transition

After a physical power cycle, the board was stopped at U-Boot.  The guarded
source-3 sequence used the accepted firmware SHA and exactly one SetSource RPC.
The retained trace recorded CALL, RETURN, RETURN_ACK, source callback, worker
dequeue, transition completion, and worker-new-source 3.  Linux then adopted
the live shared region.  `prepare-source3.py --postboot-only` verified source
3, the MIPS canaries, the TVFE/TVCAP and receiver clock holds, and the EDID
clock.

## Device-order integration

The current video stack registers the Hantro decoder as `/dev/video1`, so the
HDMI capture bridge became `/dev/video2`.  The HDMI tools now locate the node
whose sysfs name is `H713 HDMI1 ring capture` instead of assuming a minor
number.  They also pin both the mpv window and fullscreen placement to the
selected Wayland output and reject mpv output fallback.

The board asserts HPD and serves EDID only during the bounded receiver trial.
Consequently `HDMI-A-1` disappearing from the desktop after a trial is expected
even while the cable remains connected.  For this run the desktop output was
independent rather than mirrored.

## Receiver integrity preflight

The cached, sparse-verified receiver-only trial captured 60 requested native
1280x720 NV16 frames:

```json
{
  "frames": 60,
  "patterned_frames": 60,
  "band_mismatches": 0,
  "stripe_mismatches": 0,
  "sequential_steps": 59,
  "duplicate_steps": 0,
  "skipped_steps": 0
}
```

The driver produced and delivered 61 frames, with zero overwritten, rejected,
or unstable frames.  Frame IDs 184 through 243 were consecutive.

## Panel run

After explicit operator confirmation, the visible run used:

```text
python3 tools/hdmi/run-native-720-panel.py \
  --operator-ready --pattern-only \
  --probe-module /tmp/h713-hdmi-current-scp-720/h713-scp-probe.ko \
  --capture-module /tmp/h713-hdmi-current-v4l2/h713-hdmi-v4l2.ko \
  --fallback-module /tmp/h713-hdmi-current-v4l2/h713-hdmi-v4l2.ko \
  --frames 360
```

The GStreamer runner reported 360 source buffers, 360 sink buffers, and 360
rendered frames in 6.085926 seconds, with zero drops, PTS mismatches, or
unmatched buffers.  Conversion averaged 3554.55 us and reached 12263 us at
maximum.

The capture driver recorded 365 produced frames, 362 delivered frames, three
no-buffer overwrites during start/stop, zero rejected frames, and zero unstable
frames.  The five source events beyond the 360-frame pipeline remained within
the harness's eight-event shutdown-tail budget.

The DRM trace contained 361 submitted and 361 physically presented updates:
one named KMS bootstrap repeat and 360 changed-framebuffer presentations.  It
recorded zero coalesced or aborted updates, and every presentation interval was
exactly one panel vblank.  Submit-to-vsync time averaged 12.65 ms.

The command channel did not deliver the harness's final JSON line.  The
pipeline CSV and preview summary had already been preserved, and the required
driver, KMS, scanout, and cleanup checks were recovered immediately afterward.
All acceptance predicates passed.

## Latency

The joined 360-frame monotonic trace measured capture completion to physical
panel vblank as follows:

| Metric | Time |
| --- | ---: |
| minimum | 27.19 ms |
| mean | 36.80 ms |
| median | 37.38 ms |
| p95 | 43.73 ms |
| p99 | 45.28 ms |
| maximum | 51.91 ms |

The final 60-frame median was 6.88 ms lower than the first 60-frame median, so
the bounded run showed no latency growth.  This is capture-completion to
physical-vsync latency; it does not include source pixel timing or panel
response.

## Restoration

After the run, the NV12 overlay was inactive, fbcon remained on primary
framebuffer 40, and the console was visible.  The tooling restored the
conservative 640x480, full-verification module configuration.  HDMI-A-1
returned to disconnected/disabled when the HPD window ended.  No new IOMMU or
DRM cleanup error was observed.

This closes current-video-branch integration and a bounded operator-confirmed
native 720p capture-to-panel pass.  Persistent monitor presence, the
interactive pointer case, and endurance/recovery remain separate production
gates.
