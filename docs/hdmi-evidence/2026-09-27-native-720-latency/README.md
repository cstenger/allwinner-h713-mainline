# Native 720p capture-to-physical-scanout latency

This gate measures the software-controlled part of the native HDMI-to-panel
path. One bounded 360-frame run joined V4L2 capture completion through
GStreamer conversion and KMS submission to the AFBD physical-vsync interrupt.
The operator saw full-frame motion and Madame Leota in order, followed by the
restored Linux console.

## Timestamp boundaries

`gst-native-720-panel.c` records each buffer's V4L2 sequence and PTS at the
source pad, both pad-arrival times around `videoconvert`, and the pipeline base
time. For this live `v4l2src`, `base_time + PTS` reconstructs the monotonic V4L2
capture-completion timestamp. The runner also samples the GStreamer system
clock against `g_get_monotonic_time`; their measured offset was -23.8 us, below
the analyzer's 1 ms rejection threshold.

Kernel patch 0164 adds a fixed 512-entry trace to
`h713_scanout_trace`. The IRQ path records framebuffer ID, Y/C DMA identity,
the time AFBD accepted READY, the following physical-vsync time, and the
physical-vblank sequence. It allocates and formats nothing in IRQ context.

The analyzer requires contiguous trace indices, consistent kernel latency
fields, monotonic V4L2 sequences and vblanks, and the one known KMS bootstrap
repeat specifically at trace index 1. Removing that repeat leaves exactly 360
changed physical presentations for 360 pipeline buffers; frames are joined in
their preserved order.

## Accepted run

The command was:

```text
python3 tools/hdmi/run-native-720-panel.py --operator-ready
```

The source used the pinned EDID SHA256
`1bf44b2172fb4e512d8a575c58f2abbcfd96d2f2902bea5b8a7a323248fb9013`.
Firmware reported receiver state 5, 1280x720 active, and pixel repeat zero.

| stage | minimum | median | p95 | p99 | maximum |
| --- | ---: | ---: | ---: | ---: | ---: |
| capture completion -> source pad | 2.95 ms | 17.42 ms | 25.66 ms | 26.60 ms | 37.36 ms |
| source pad -> sink pad (conversion) | 2.01 ms | 3.31 ms | 6.43 ms | 8.36 ms | 11.59 ms |
| sink pad -> accepted display submit | 0.15 ms | 0.20 ms | 0.28 ms | 0.92 ms | 3.61 ms |
| capture completion -> display submit | 12.13 ms | 22.21 ms | 29.53 ms | 32.47 ms | 41.26 ms |
| display submit -> physical vsync | 4.72 ms | 12.85 ms | 13.67 ms | 14.18 ms | 19.05 ms |
| **capture completion -> physical vsync** | **25.64 ms** | **33.82 ms** | **41.92 ms** | **42.65 ms** | **53.81 ms** |

The first 60 frames had a 39.51 ms median capture-to-vsync latency; the last 60
had a 30.61 ms median. The -8.90 ms change is evidence against a growing queue
over this bounded run. It is not a long-duration drift claim.

Cadence and cleanup remained intact:

- 360 source, sink, and rendered buffers; zero sink drops, PTS mismatches, or
  unmatched buffers;
- 361 submitted and physically presented updates: one known KMS bootstrap
  repeat and 360 changed-framebuffer presentations;
- every physical presentation occurred on the next vblank, with zero
  coalesced, aborted, or pending updates;
- 59.13 measured fps, 3.84 ms mean conversion time, and no new DRM/IOMMU
  errors; and
- the NV12 overlay detached, fbcon's primary framebuffer remained unchanged,
  the fallback capture module reloaded, and source 3 was restored.

The capture driver produced 365 events and delivered 362 while the bounded
pipeline selected 360; three events were overwritten under the intentional
newest-frame policy and five occurred beyond the pipeline's requested window.
The retained pipeline frames still joined one-to-one to their physical
presentations.

## Build provenance

- kernel: Linux 6.18.38, built `Sun Sep 27 19:59:04 PDT 2026`
- FIT size: 7,758,436 bytes
- FIT SHA256:
  `9d235cde1073c15ccf1a14b8b3a277d999ef06a498c8317b05ecb9b08f3e7b43`
- capture module SHA256:
  `73e5c9ed36799def03acd99dcbb9634a62efb1bf854ed284cf4386f3a17e0332`
- native probe SHA256:
  `da78b61bf86c3f434e433ff5a7ffe9dd752198e6253b04d5b4080e659701975d`
- GStreamer runner source SHA256:
  `4de64bf055d0fdf2e995f8d6bca221bc8396c312b4d7aba1941464fb32daf761`
- latency analyzer SHA256:
  `d165a0a63a3e515ba17fef75c3645018a47425dc81a1aa331dcd52e0a1e2bd3b`

The raw timestamp CSV, scanout trace, pipeline and driver summaries,
before/during/after KMS and scanout state, source log, restore result, and
top-level machine result are retained in this directory.

## Claim boundary and next gate

This result measures capture completion to the display engine's physical scan
boundary. It does **not** measure source-to-photon latency: the source's actual
pixel-change time, receiver time before capture completion, panel transfer, and
projector response are outside this clocked interval. No absolute acceptance
limit has yet been agreed. The next latency gate must film a timestamped source
display and the projected panel in the same high-frame-rate view, then repeat
with a moving desktop or pointer before production latency can be accepted.
