# GStreamer 1.26.2 board validation — 2026-09-14

Kernel remains `6.18.38 #1 SMP Mon Sep 14 00:11:33 PDT 2026` through old
0111. No kernel replacement, MMIO writes, or visible panel tests in this
continuation. All SSH/SCP used `-F /dev/null`.

## Deployment and reproducibility

Mounted `/dev/mmcblk0p23` as vfat at `/mnt/media-data` (74 MiB initially free).
Existing `h713-gstbuild` contains a minimal H.264 plugin source subset with
patch 0001 already applied. Copied it to host `/tmp/h713-gstbuild-board`,
applied 0002 with zero fuzz, and copied into a separate board directory:
`/mnt/media-data/h713-gst-transform-20260914`.

Ran `sh build.sh` there. Compiler/linker succeeded, but the final `file`
inspection failed because that utility is absent. The resulting shared object
loads successfully. The `GST_USE_UNSTABLE_API` redefinition is a warning.

The first ordinary plugin-path inspection selected the stock plugin. Do not
use that inspection as deployment evidence. The following isolated registry
and directory select the new object conclusively (`inspect-isolated.log`):

```sh
mkdir -p /tmp/h713-gstplugins
for p in /usr/lib/aarch64-linux-gnu/gstreamer-1.0/*.so; do
    case "$p" in */libgstv4l2codecs.so) continue;; esac
    ln -sf "$p" /tmp/h713-gstplugins/
done
ln -sf /mnt/media-data/h713-gst-transform-20260914/libgstv4l2codecs.so \
    /tmp/h713-gstplugins/libgstv4l2codecs.so
export GST_PLUGIN_SYSTEM_PATH=
export GST_PLUGIN_PATH=/tmp/h713-gstplugins
export GST_REGISTRY=/tmp/h713-isolated-registry.bin
```

No system plugin was overwritten. `/tmp` setup must be recreated after boot.
The new decoder exposes output-width, output-height, and rotation.

## Headless results

Explicit `video/x-raw,format=NV12` caps select linear output. Example:

```sh
timeout 15 gst-launch-1.0 -q \
    filesrc location=/root/leota-1080p.h264 ! h264parse ! \
    v4l2slh264dec output-width=1280 output-height=720 rotation=0 ! \
    video/x-raw,format=NV12 ! fakesink sync=false num-buffers=60
```

| rotation | requested canvas | active caps | result |
| --- | --- | --- | --- |
| 0 | 1280x720 | 960x544 | 60 frames, EOS, clean NULL transition |
| 180 | 1280x720 | 960x544 | 60 frames, EOS, clean NULL transition |
| 90 | 720x1280 | 544x960 | 60 frames, EOS, clean NULL transition |
| 270 | 720x1280 | 544x960 | repeated pipeline exits 0 |
| 90 or 270 | 1280x720 | 1088x480 | failure: IOMMU read fault and decode timeout |

The four passing configurations were repeated five times each (20 independent
start/stop runs, 60 frames per run); all exited 0. These verify decoder teardown,
not return from KMS to console. Equal-axis half-scale is passing. Unequal-axis
scaling with quarter-turn rotation is a newly identified failure, not solved.
The user-facing GStreamer error says insufficient memory, but kernel logs show
IOMMU read faults at `0xff356000` and `0xff3fd000`, followed by frame timeouts.
Available RAM was about 600 MiB. Investigate the hardware address/layout and
asymmetric transform semantics before repeating the faulting configuration.

## Pixel verification

Generated 128x64 NV12 quadrants with Y=16/235/81/41 and neutral chroma, encoded
using libx264 High profile, CRF 18, one frame. Decoded through the new plugin
to filesink with rotation only. All files are 12,288 bytes; centers match exactly:

| angle | output | TL, TR, BL, BR |
| --- | --- | --- |
| 0 | 128x64 | 16, 235, 81, 41 |
| 90 | 64x128 | 81, 16, 41, 235 |
| 180 | 128x64 | 41, 81, 235, 16 |
| 270 | 64x128 | 235, 41, 16, 81 |

An initial QP=0 encode selected High 4:4:4 Predictive and decoded incorrect luma
already at angle 0. Those `quadrants-ANGLE` runs are not valid pixel controls;
the `quadrants-high-ANGLE` runs above use the supported High profile.

Build, inspect, and test logs are under `video-validation-2026-09-14/` and the
board build directory. Empty repeat logs mean the quiet pipeline exited 0;
exit statuses were captured in the task tool output.

## Outstanding work

- Measure the grey streak using staged ruled cards after operator says watching.
- Finish upper-field writer tracing and derive a discriminating boundary test.
- Resolve or safely bound unequal-axis scaling with 90/270 rotation.
- Build corrected kernel patches 0109/0111; install and cold power-cycle.
- Validate the GStreamer-to-DRM path, visible rotation, console restoration,
  and repeated visible playback. Portrait active frames cannot directly satisfy
  the current 1280x720 native-raster display constraint without another layout
  decision; do not present the headless portrait runs as display validation.

## Persistent 0114 moving-video test

After fresh watching confirmation, ran the isolated patched plugin with
CEDRUS_TRANSFORM=1, SRC=960x544, MOVING=1, PACED=1 in the updated
kms-nv12-transform-test for 30 seconds. Hardware decoder frame60 DMA-BUF
was acquired directly and scanned out in the native padded framebuffer.
Harness exited0: 900 flips /30.01s =29.99fps; mean33.37ms, sd2.43ms,
min16.75ms, max50.25ms; 6 late intervals (0.67%). Reported NV12 disabled
and KMS RGB restored. Operator visual assessment is pending. Board log:
/mnt/media-data/h713-gst-transform-20260914/kernel-0114-moving-video.log.
