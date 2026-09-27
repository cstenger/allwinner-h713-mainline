# HDMI input to panel: production roadmap

This is the ordered work from the present board-B prototype to using the
projector as a 1280×720, 60 Hz, low-latency HDMI monitor for the connected
computer. Each gate needs hardware evidence before the next depends on it.
Keep HDMI work on `codex/hdmi-capture` in its own checkout, based on the merged
video kernel; coordinate kernel/display integration with Claude's video work
without changing Claude's checkout or silently replacing the board's kernel.

## Starting point, 2026-09-25

- The source GPU detects a temporary 640×480 EDID, and the firmware HDMI1
  path writes 640×480 NV16 into a three-pair Y/UV ring. A removable V4L2
  bridge exposes `/dev/video1`. The currently restored board module still
  infers predecessor-pair handoff from ring changes; the tested replacement
  below is event-gated but is not yet installed as the default.
- A bounded live preview shows the moving source pattern on the 1280×720
  panel. The optical recording shows console → moving image → console, black
  side bars for the 4:3 input, and no large horizontal wrap or green edge.
  See [panel evidence](hdmi-evidence/2026-09-25-panel-preview/README.md).
- Scaling directly from V4L2 mmap buffers feeds only about 11 frames/s.
  Buffered V4L2 `read()` feeds a 20 fps player at about 16 frames/s with
  full-plane verification, or about 31 frames/s with experimental sparse
  checks. A 120-frame buffered-read motion test had zero band-ID and stripe
  mismatches. See [rate evidence](hdmi-evidence/2026-09-25-preview-rate/README.md).
  The optical quality of this faster preview has not yet been checked.
- HPD/EDID and source selection are still bounded diagnostic operations.
  The current panel route uses FFmpeg software NV16→BGR0 conversion and mpv
  DRM presentation. V4L2 `read()` followed by rawvideo loses V4L2 timestamps
  and sequence numbers. The board is presently left with full verification
  enabled, HPD released, and the normal console scanout restored.
- A guarded MIPS trace now proves the capture ordering over an 8.003-second
  motion run: 480 `cap-vde` and 480 `cap-vs` events, 481 single-pair write
  epochs, and 480 error-free `0→1→2` transitions. `cap-vde` always leads
  `cap-vs`, with no ring writes observed between them, so VDE is the earliest
  demonstrated completed-pair boundary. See
  [production-gate evidence](hdmi-evidence/2026-09-25-production-gates/README.md).
- An event-gated V4L2 prototype delivered 121/121 sparse-verified frames with
  zero overwrites, rejections, unstable copies, skipped motion IDs, band
  errors, or stripe errors. The full-plane diagnostic oracle remained clean
  but delivered 121 of 162 produced frames because its double-read costs about
  20.4 ms. All 481 attributable write epochs shared one stable modulo-three
  offset between `cap_vde` and the completed pair. A follow-on static-image
  trial showed that the offset's absolute value is boot-specific, so the bridge
  now learns it once during source startup and retains it across stream reopen
  instead of assuming offset zero. A guarded AFBD current-pair vote now also
  resolves cold module load after an already-static source.
  The board was returned to its original bootloader and the prior
  full-verification module after the bounded tests.

## Required finish line

The product path must accept 1280×720 at 60 Hz from an ordinary GPU and show
the full image on the 1280×720 panel at a sustained 60 Hz, with correct crop,
color, and aspect ratio. It must keep latency low and bounded: record source
frame ID, capture completion, display submit, panel flip, and optical response
so median, worst-case, and dropped-frame behavior are measurable. Do not call
the path low latency solely because its queue is short or its nominal mode is
60 Hz. Set an absolute latency acceptance limit from those measurements with
the user; minimize buffering toward the newest complete frame and report the
measured result.

The HDMI input must connect and recover without a diagnostic script or serial
console. A source plug/unplug, mode change, source blank, capture-client exit,
and reboot must leave the display and other video functions usable. Normal
operation must use a reproducible merged kernel and installable components,
not test-only register pokes, an always-running trace probe, or a hard-coded
one-shot HPD window.

## Ordered gates

### 1. Confirm the faster picture and establish measurements

1. Repeat `run-panel-preview.py --input-api read --display-fps 20` first with
   default full verification, then, if visually clean, one bounded
   `--sparse-verify` comparison. Record the panel and source screen together
   over the same clock, including before and after. Verify no shift, green
   edge, blanking, obvious tearing, or failure to restore console.
2. Save source pattern IDs, V4L2 sequence/timestamps where available, FFmpeg
   production rate, DRM flip timestamps, and a time-aligned optical clip.
   Separate input drops from conversion stalls and presentation drops. The
   buffered-read pipe is a useful rate experiment, but its synthetic rawvideo
   timestamps must not be used as capture-latency measurements.
3. Establish a reproducible baseline on the current 640×480 signal: frame
   delivery and unique IDs over more than one 120-frame burst, CPU use,
   buffer occupancy, memory bandwidth if observable, and end-to-end latency.

**Progress, 2026-09-26:** The AFBD-bootstrap driver completed both requested
buffered-read panel runs at 20 fps. Full and sparse verification each submitted
120 frames, switched the DRM primary framebuffer, restored the original
framebuffer and hardware scanout, disconnected cleanly, and started again on
the next bounded window. Full verification rejected 12 changing diagnostic
copies; sparse verification had zero unstable copies but conservatively
rejected seven phase events and relearned offset 2 before resuming. This is a
successful automated screen-route recovery test, not yet a zero-drop or
operator-confirmed optical-quality pass. See
[panel recovery evidence](hdmi-evidence/2026-09-26-panel-recovery/README.md).

**Pass:** the faster route visibly shows the correct moving image, returns to
console, and the measured rates agree with the saved kernel/user logs.

### 2. Prove completed-frame ownership and harden capture

**Progress, 2026-09-25:** Step 1 is proved for the present 640×480 signal.
The event-gated prototype also passes one full-oracle and one sparse 120-frame
motion run, with explicit produced/delivered/overwritten/rejected accounting.
Before declaring the whole gate passed, retain the completion ABI without a
debug-only trace dependency and complete static-image startup, stream
stop/restart, repeated disconnect/reconnect, signal-loss, and endurance tests.

**Progress, 2026-09-26:** A visually static source passed five sparse and three
full-verification stream close/reopen cycles with zero unstable or rejected
frames. A subsequent disconnect/reconnect and 120-frame motion regression had
zero band/stripe errors, zero skipped IDs, and zero driver rejections. Testing
also disproved a fixed zero counter phase: the bridge must learn and retain a
boot-specific modulo-three offset. It now invalidates that phase after lost
completion events or a mode change. A follow-on three-cycle AFBD-only test kept
one module instance loaded across full disconnect timeouts; every reconnect
relearned phase 2, and all 90 motion frames were sequential and marker-clean
with zero driver overwrites, unstable copies, or rejections. Longer endurance,
and mode-change runs remain. A recorded panel test also disabled the source GPU
output while capture and presentation were active: V4L2 failed closed with
`EIO`, the panel returned to console, the same source mode was re-enabled,
AFBD relearned phase 2, and a fresh 120-frame panel preview completed before a
final console restore. See
[signal-recovery evidence](hdmi-evidence/2026-09-26-panel-signal-recovery/README.md).
See [static restart evidence](hdmi-evidence/2026-09-26-static-restart/README.md).
Static MMIO analysis found no capture-domain producer index, but the AFBD
current-pair window at `0x05600320/324` supplies a robust bootstrap when treated
as a multi-event vote rather than a single authoritative read. Static and
moving telemetry strongly favored one phase while exposing occasional latch
races. With ring-content learning disabled, cold module loads after a settled
static source independently learned offset 2 from unanimous 0/0/12 votes and
passed eight stream opens with zero unstable or rejected frames. The default
configuration then passed another 120-frame moving-pattern regression with
zero band or stripe mismatches. See
[AFBD phase evidence](hdmi-evidence/2026-09-26-afbd-phase/README.md) and
[capture memory path](hdmi-capture-memory-path.md).

1. Correlate the firmware `cap-vde`/`cap-vs` events and the capture ring's
   0→1→2 updates in an isolated read-only MIPS trace. Establish which event
   means a full Y and UV pair is safe to consume, or find the actual DMA
   completion/producer index. Do not use the ARM reads of capture-domain
   registers that previously locked this board.
2. Replace hash-change/predecessor inference with the proved completion
   condition. Count produced, delivered, overwritten, and rejected frames.
   Preserve monotonic capture timestamps and sequence IDs in V4L2. Handle
   startup, no-signal, signal loss, and source format changes without a
   wedged queue or a board power cycle.
3. Run moving frame-ID and stripe tests across all rows, with wraparound,
   repeated disconnect/reconnect, and full source activity. Keep full-plane
   comparison available as a diagnostic oracle until the event-driven path
   has passed equivalent integrity and endurance checks.

**Pass:** frame ownership is tied to a demonstrated completion signal, with
zero mixed/tearing IDs in the defined tests and clean stream stop/restart.

### 3. Reach 60 frames/s at the existing 640×480 signal

**Progress, 2026-09-25:** Event-gated sparse capture itself reached 121/121
produced/delivered frames with intact moving IDs. This does not pass gate 3:
60 Hz DRM presentation, preserved V4L2 timing through the consumer, optical
evidence, and bounded end-to-end latency are still outstanding.

**Progress, 2026-09-27:** The throughput work advanced directly on the native
1280×720 mode. A cacheable firmware-ring mapping with explicit arm64
invalidate-to-PoC reduced the sparse-verified full-raster copy from about
22.3 ms to 2.3-2.6 ms. Cached vb2 vmalloc output buffers then sustained a
240-frame NV16-to-NV12 conversion at 59.84 fps with zero driver overwrites,
rejections, or unstable frames. These changes remove the known CPU memory-path
bottleneck, but they do not by themselves measure end-to-end latency.

1. Remove avoidable uncached-buffer rereads. The bridge now provides opt-in
   cached source and vb2 vmalloc output paths while retaining the prior
   diagnostic defaults. Keep `CONFIG_VIDEOBUF2_VMALLOC` explicit in the board
   kernel and preserve the invalidate-before-read rule for the non-coherent
   firmware ring. Continue comparing against the validated buffered `read()`
   baseline when this path changes.
2. Profile capture, format conversion, and DRM presentation separately and
   together. Avoid a 1280×720 BGR0 userspace pipe in the final path if an
   existing native YUV plane or GPU shader can present the completed buffer
   more cheaply. Respect DRM ownership; do not bypass the display driver
   with direct AFBD register writes.
3. Schedule against panel vblank and favor the newest **complete** input
   frame. Use bounded queues, explicit drop policy, and timestamps rather
   than letting latency grow when producer and consumer rates differ.

**Pass:** 640×480 moving input presents at sustained 60 Hz with integrity
checks, measured drop counts, bounded latency, and normal console restore.
This is an intermediate gate, not the final resolution.

### 4. Bring up native 1280×720 at 60 Hz end to end

**Progress, 2026-09-26:** The source read the exact checksummed 1280×720 trial
EDID and enabled its native 60 Hz mode. Guarded MIPS cache samples remained
locked at 1280×720, state 5, with no pixel repeat. AFBD retained the same
three-pair address ring. A 720p NV16 plane fits each `0x1ff000` slot with
`0x11e000` bytes spare, and all six planes remain inside the known carveout.
A read-only sampler recovered three complete 1,843,200-byte marker frames;
top/middle/bottom IDs agreed, both horizontal edge markers were present, all
720 rows decoded, and there were zero band or stripe mismatches. This closes
the receiver/ring-layout portion of steps 1–2, but not V4L2 capture, sustained
60 fps, panel presentation, or latency. See
[native 720p capture evidence](hdmi-evidence/2026-09-26-native-720-capture/README.md).

**Progress, 2026-09-26 (panel route):** The event-gated V4L2 bridge completed
a camera-gated native 1280×720 capture-to-panel run.  It presented 240 frames
from a deterministic motion marker and a 720p video, switched and restored the
DRM primary framebuffer, disconnected the source, returned to the Linux
console, and introduced no IOMMU fault.  The operator saw both sources and the
correct console return.  This passes native-raster functional presentation,
but not rate: 957 frames were produced while only 240 were delivered, with
477 full copies, 237 unstable copies, and roughly 26.2 ms spent per copy.  The
FFmpeg stage sustained only about 16 fps.  See
[native 720p panel evidence](hdmi-evidence/2026-09-26-native-720-panel/README.md).

**Progress, 2026-09-27 (sustained native route):** The refined V4L2 path and
DRM NV12 plane consumed 360 requested frames in 6.0845 seconds (59.17 fps).
An A/B run identified and removed a redundant userspace vblank wait:
`kmssink`'s default produced 29.58 fps, while `skip-vsync=true` produced
59.17 fps because the atomic H713 driver already completes commits at physical
vblank. The final run had zero rejected or unstable capture frames and exact
driver accounting. Counters were sampled after EOS, and its three no-buffer
overwrites fit within the bounded stream-off tail; the harness records them
and limits the entire tail to eight source events. DRM activated the NV12
overlay while preserving fbcon,
then disabled it and returned visibly to the console. The operator saw the
motion pattern and Madame Leota sequence play correctly. A separate retained
120-frame raw capture had zero band/stripe mismatches and zero skipped IDs.
This closes the native prototype's sustained-rate and functional-presentation
work, but not distinct physical-flip counting, end-to-end latency, endurance,
or normal monitor integration. See
[60 fps evidence](hdmi-evidence/2026-09-27-native-720-60fps/README.md).

1. Produce and checksum a 1280×720@60 EDID with the timings, color formats,
   and range the receiver can actually support. Verify the GPU reads that
   exact EDID and enables the native mode; inspect source-side output state.
2. Verify firmware receiver lock and reported active timing at 1280×720.
   Locate the actual Y/UV plane bases, strides, ring depth, and allocation
   limits at this mode. Validate that the reserved memory is large enough and
   that no plane overlaps the kernel, display, or adjacent firmware memory.
   Do not assume the 640×480 constants scale linearly.
3. Generalize the V4L2 format/stride/buffer size and completion handling.
   Capture a deterministic full-resolution pattern with IDs at top, middle,
   and bottom and markers at both horizontal edges. Check chroma alignment,
   color range, crop, and all rows against the source screenshot.
4. Present the native raster without 4:3 side bars or unwanted scaling.
   Prove capture and display are both 60 Hz **at this mode**, not merely that
   the source advertises 60 Hz. If receiver or firmware cannot produce this
   mode, isolate that limitation before changing the display path.

**Pass:** a 1280×720@60 source is detected, captured, and shown edge to edge
with correct colors and frame IDs at a sustained 60 Hz.

### 5. Minimize and validate end-to-end latency

1. Time-stamp source frame changes, receiver/capture completion, V4L2 dequeue,
   display submit, and vblank/page flip. Film both source and projected panel
   in one high-frame-rate view for an optical cross-check. Report a frame and
   millisecond distribution, including 99th percentile and after mode changes.
2. Remove staging queues and copies that measurements show are costly. Favor
   DMA-BUF/import or a native YUV display path only after buffer ownership,
   cache coherency, and lifetime are demonstrated. If conversion remains
   necessary, benchmark the GPU and existing DRM video-plane routes against
   the CPU route using the same input and timestamps.
3. Repeat the measurement with a moving desktop and interactive pointer,
   not only a synthetic test pattern. Confirm no growing delay or old frames
   after input stalls, and keep console/source-switch transitions reversible.

**Pass:** the measured latency meets the agreed limit, has no queue growth,
and stays bounded while maintaining 1280×720@60 and frame integrity.

### 6. Integrate normal monitor behavior

1. Move EDID/HPD, receiver power, source selection, and capture startup from
   diagnostic scripts into an owned driver/service lifecycle. Assert HPD only
   when the receiver and capture path are ready. Handle cable bounce, source
   suspend/blank, hotplug, resolution changes, and unplug cleanly.
2. Provide a user-visible HDMI input selection and an orderly return to the
   local console. Ensure Cedrus/video playback, the panel driver, and HDMI
   capture share clocks, memory, and DRM ownership without breaking each
   other. Coordinate kernel changes with the current video branch, then
   integrate them into one validated default image.
3. Define the input capability honestly in EDID. Document audio support or
   its absence; test protected-content behavior without claiming unsupported
   HDCP. Establish permissions and service startup so the monitor works on
   cold boot and after a normal system update.

**Pass:** a computer treats the projector as a stable native-resolution
monitor through plug/unplug, reboot, and source switching without manually
running lab tools.

### 7. Production validation and delivery

1. Run long-duration 1280×720@60 motion and desktop soaks with source IDs,
   frame/flip counters, latency samples, memory/CPU use, and temperature.
   Exercise repeated hotplug, signal loss, mode changes, client crashes,
   and coexistence with video decode. Check no corruption, sustained-rate
   regression, memory leak, stalled queue, or unrecoverable board state.
2. Keep automated build and hardware checks for EDID checksum/source read,
   receiver timing, frame integrity, delivered 60 Hz, latency, recovery,
   and the default boot image. Include exact kernel/module provenance and
   a way to compare the installed board state with the tree.
3. Document installation, normal use, supported modes/formats, known limits,
   diagnostics, rollback, and board recovery. Land reviewed changes on the
   merged video branch without overwriting Claude's work; make the tested
   image the default only after the complete acceptance matrix passes.

**Pass:** the native monitor path meets the rate, integrity, latency, and
recovery targets over the agreed soak interval and survives cold boot as the
documented default configuration.

## Evidence discipline

For every hardware gate, save the exact command, source mode/EDID hash,
kernel and module build IDs, capture and DRM counters, before/during/after
state, and cleanup result under `docs/hdmi-evidence/`. Keep large raw streams
outside Git, with checksums and a small representative frame or optical
contact sheet in the evidence directory. A successful script exit or nominal
60 Hz mode alone does not establish a good image, delivered 60 fps, or low
latency.

Before any test that will put content on the projector for optical evidence,
prepare the software and hardware first, then stop and explicitly ask the
operator to ready the camera. Start the bounded visible run only after the
operator confirms recording is ready. State whether the recording must include
the console-before, video, interruption/recovery, and console-after phases.

For a cold source-3 recovery, do not let `prepare-source3.py` warm-reboot a
parked MIPS core. Arm `reboot-to-uboot.py` with `--wait-for-power-cycle` before
the physical power-on, complete the guarded source-3 transition at the caught
U-Boot prompt, and use `prepare-source3.py --postboot-only` only after Linux
returns with the live trace. The helper now refuses the unsafe parked-state
warm-reboot path.
