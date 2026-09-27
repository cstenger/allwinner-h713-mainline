# Native 1280x720 capture-to-panel at 60 fps

This milestone closes the prototype's native-raster throughput bottleneck. A
bounded camera-gated run carried the 1280x720@60 source through the firmware
NV16 ring, the event-gated V4L2 bridge, four-thread NV16-to-NV12 conversion,
and the DRM video plane. GStreamer consumed all 360 requested frames in
6.084532503 seconds, or 59.17 frames/s. The operator saw the motion pattern and
the Madame Leota video play correctly in order, followed by the Linux console.

The tested Linux 6.18.38 FIT had SHA-256
`7d0eebf3f8a38cfff10570abe9dc63f93abd23f87551a070244e6ba177c77c5a`.
The out-of-tree V4L2 module had SHA-256
`d90ece45713e530b438cb3708290de811506d80e5fdbf4677ab036ca74cb247e`.
The source playlist used the deterministic native-resolution motion pattern
followed by
`Madame Leota Complete Audio Loop - 720.mp4`.

## Memory and conversion path

The original write-combining firmware-ring mapping took about 22.3 ms per
1280x720 NV16 copy, already longer than one 60 Hz interval. Mapping the no-map
ring cacheable and explicitly invalidating each producer plane before reading
it reduced sparse-verified copy time to about 2.3-2.6 ms. Using cached vmalloc
V4L2 output buffers avoided making the CPU write through the DMA-contiguous
allocator's uncached mapping. Both choices are opt-in module parameters;
legacy diagnostic behavior remains the default.

A retained 120-frame raw capture on the resulting path had 120 patterned
frames, zero band mismatches, zero stripe mismatches, 118 sequential ID steps,
one duplicate step, and zero skipped steps. Driver accounting was 122
produced, 122 delivered, zero overwritten, zero rejected, and zero unstable.

Conversion was then isolated without touching the projector. GStreamer
consumed 240 NV16 frames, converted them to NV12, and reached EOS in
4.010656668 seconds (59.84 frames/s). Driver accounting was exactly 240
produced and delivered with zero overwritten, rejected, or unstable frames.
The alternative BGR0 userspace route sustained only about 37 frames/s and was
not used for the passing panel test.

## Display-rate A/B

The first NV12 `kmssink` panel run used the sink's default vblank wait and
consumed 360 frames in 12.170468214 seconds (29.58 frames/s). The H713 atomic
DRM driver already completes commits on physical vblank, so the sink's second
wait halved the rate. GStreamer's own `kmssink` documentation identifies
`skip-vsync` for this atomic-driver case.

The passing command therefore ended in:

```text
... ! video/x-raw,format=NV12 ! \
  kmssink driver-name=sun50i-h713-afbd sync=false skip-vsync=true
```

The saved pipeline log records bounded EOS after 6.084532503 seconds. During
playback DRM kept fbcon framebuffer 40 on `plane-0` and placed NV12 framebuffer
42 on `video-0`. After EOS, `video-0` was disabled and framebuffer 40 remained
the primary console scanout. The fallback 640x480 diagnostic module was then
restored successfully.

The final capture counters were 365 produced, 362 delivered, 3 overwritten
because no V4L2 buffer was queued, 0 rejected, and 0 unstable. The accounting
closes exactly: `365 = 362 + 3 + 0`. Counters were sampled after EOS; the five
source events beyond the pipeline's requested 360-frame count are consistent
with the bounded stream-off tail. The harness now permits at most eight such
tail events while still requiring at least 360 deliveries, zero rejection,
zero instability, closed accounting, EOS, and at least 55 frames/s. It reports
the three overwrites rather than relabeling them as zero-drop evidence.

This proves sustained consumption and native-plane presentation for the
diagnostic route. It does not prove that every one of the 360 buffers caused a
distinct physical page flip, nor does it establish end-to-end optical latency;
those remain separate timestamped gates.

## Cold-boot recovery rule

The testing also exposed an operational trap: entering the source-3 sequence
through a warm reboot can leave the panel black even when Linux later boots.
For a parked MIPS core, arm
`tools/serial/reboot-to-uboot.py /dev/ttyUSB0 45 --wait-for-power-cycle` before
the physical cold power-on, catch the U-Boot prompt, and only then run the
guarded MIPS trace/source-3 commands. If the panel state is uncertain, use the
U-Boot vendor-logo panel test as a positive control before `run bootcmd`.
`prepare-source3.py --postboot-only` is only for the already-live, traced
source-3 state; it now refuses to convert a parked state with a warm reboot.
