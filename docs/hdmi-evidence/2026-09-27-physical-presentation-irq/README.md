# Physical HDMI-to-panel presentation proof

This gate closes the gap between a userspace sink saying that it rendered a
buffer and the H713 display engine reaching a physical scan boundary with that
buffer accepted. Two bounded native 1280x720 runs were visually correct, showed
the motion pattern followed by Madame Leota, and returned to the Linux console.

## Instrumented boundary

Kernel patch 0163 records an NV12 framebuffer only after `AFBD_VIDEO_READY`
clears, which is the hardware acceptance boundary. The next AFBD physical-vsync
interrupt consumes that pending identity and records its framebuffer ID, Y/C
DMA addresses, submit-to-vsync latency, and interval from the prior physical
presentation.

The accounting is deliberately asynchronous. An earlier revision waited for a
second vblank inside atomic update and reduced the same 360-buffer pipeline to
29.66 fps. Removing that extra wait restored the expected cadence while
retaining an interrupt-confirmed presentation boundary.

The pending slot also makes loss observable:

- a new accepted update while one is pending increments `video_coalesced`;
- disable or a READY timeout with pending work increments `video_aborted`;
- `video_submitted == video_presented`, `video_pending == 0`, and zero
  coalesced/aborted therefore prove every accepted update reached a later
  physical-vsync interrupt before it could be replaced.

## Accepted runs

Both runs used the pinned EDID SHA256
`1bf44b2172fb4e512d8a575c58f2abbcfd96d2f2902bea5b8a7a323248fb9013`.
The live firmware port cache reported state 5, 1280x720 active, and pixel repeat
zero before the overlay opened.

| measurement | run A (`024031Z`) | run B (`024443Z`) |
| --- | ---: | ---: |
| pipeline source / sink / rendered | 360 / 360 / 360 | 360 / 360 / 360 |
| sink drops / PTS mismatches / unmatched | 0 / 0 / 0 | 0 / 0 / 0 |
| elapsed | 6.087106 s | 6.120413 s |
| measured rate | 59.14 fps | 58.82 fps |
| physical submitted / presented | 361 / 361 | 361 / 361 |
| KMS bootstrap repeated framebuffer | 1 | 1 |
| changed-framebuffer presentations | 360 | 360 |
| coalesced / aborted / pending | 0 / 0 / 0 | 0 / 0 / 0 |
| physical interval min / max | 1 / 1 vblank | 1 / 2 vblanks |
| intervals over one vblank | 0 | 1 |
| mean / max submit-to-vsync | 12.087 / 19.035 ms | 12.326 / 19.448 ms |

`kmssink` performs one bootstrap presentation with its first framebuffer and
then submits that framebuffer again when playback starts. The validator names
and requires that single repeat. Subtracting it leaves exactly 360
changed-framebuffer presentations for 360 rendered pipeline buffers.

Run B contained one source-supply interval spanning two vblanks. It was not a
lost or replaced framebuffer: submitted and presented counts remained equal,
pending ended clear, and coalesced/aborted stayed zero. The harness permits at
most one percent isolated single-vblank supply gaps, rejects any gap longer than
one extra vblank, and still requires all 360 changed-framebuffer presentations.
Run A needed no pacing allowance.

The raw pipeline, physical scanout, and KMS before/during/after logs for both
runs are retained in this directory. In both runs fbcon's primary framebuffer
remained unchanged, `video-0` was active only during playback, and the final
state had `video-0` detached. A post-run kernel log query found no IOMMU page
fault, failed atomic commit, RGB quiesce timeout, or retire-drain timeout. The
fallback 640x480 full-verification capture module was restored after each run.

The operator reported both refined runs looked correct. They showed full-frame
motion and Leota in order and ended on the Linux console.

## Build provenance

- kernel: Linux 6.18.38, built `Sun Sep 27 19:33:35 PDT 2026`
- FIT size: 7,758,208 bytes
- FIT SHA256:
  `55d2b50bfaa117dc50e60a40f43e7d83d158a293b7d57a5d1c3ac779d3e95579`
- capture module SHA256:
  `a4d9c1a76fec2bf8e4590c442625a05c8e0e9aac367e1d3826f044acaf52ddd3`
- native probe SHA256:
  `da78b61bf86c3f434e433ff5a7ffe9dd752198e6253b04d5b4080e659701975d`
- GStreamer runner source SHA256:
  `5966811c25b2aa841c8c109497d277f9b662c2737cb8e43885baf0f53791d024`

This proves bounded native capture-to-panel presentation at the display
engine's physical-vsync boundary. It does not measure source-to-photon latency,
long-duration endurance, or production hotplug/service integration.
