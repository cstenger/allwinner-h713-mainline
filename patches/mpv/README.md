# mpv patches

Downstream changes for bare-console playback through the H713 DRM video plane.
The series targets the official mpv 0.40.0 tag at commit
`e48ac7ce08462f5e33af6ef9deeac6fa87eef01e`.

## Why this patch exists

Upstream `vo=drm` accepts software frames only: it scales them on the CPU and
copies them into DRM dumb buffers. mpv's existing `drmprime-overlay` support can
put hardware frames on a KMS plane, but it is initialized through a GPU render
context. That needlessly starts Panfrost on this board.

`0001` gives `vo=drm` a direct hardware path:

1. create a VAAPI decode device for the selected DRM card;
2. map each VAAPI frame to FFmpeg's existing `AV_PIX_FMT_DRM_PRIME` descriptor;
3. import that descriptor with mpv's existing `drm_prime` framebuffer helper;
4. submit the framebuffer to the selected DRM-prime video plane with an atomic
   page-flip event; and
5. retain the mapped image until a later flip makes it safe to release.

No FFmpeg changes, EGL/GBM context, GPU rendering, or CPU pixel copy are used.
The original software path remains available when hardware decoding is not
selected.

## Apply and build

```sh
git clone --branch v0.40.0 https://github.com/mpv-player/mpv.git mpv-0.40
while read -r p; do
    git -C mpv-0.40 apply "$PWD/patches/mpv/$p"
done < patches/mpv/series

meson setup mpv-0.40/build \
    --buildtype=release \
    -Dauto_features=disabled \
    -Dalsa=enabled -Ddrm=enabled -Dgl=disabled \
    -Dlibmpv=false -Dvaapi=enabled -Dvaapi-drm=enabled
ninja -C mpv-0.40/build mpv
```

Build against the Debian 13 arm64 libraries used by the target. The hardware
test build used FFmpeg 7.1.5, libva 2.22.0, and libdrm 2.4.124.

## Run

```sh
LIBVA_DRIVER_NAME=v4l2_request \
mpv --no-config --vo=drm --hwdec=vaapi video.h264
```

The H713 plane is deliberately constrained by the kernel driver to uncropped,
unrotated, fullscreen 1280x720 linear NV12. The direct path rejects geometry
outside that contract. The plane is an exclusive hardware mux, so mpv OSD and
subtitles are not composed over direct video.

## Hardware result — 2026-09-03

A 150-frame paced run with an external 48 kHz PCM audio track reported:

```text
Using hardware decoding (vaapi).
AO: [alsa] 48000Hz mono 1ch s16
VO: [drm] 1280x720 vaapi[nv12]
Using direct DRM PRIME video-plane scanout
```

The VA driver recorded 152 successful dma-buf exports and balanced capture
QBUF/DQBUF counts at 154/154. There were zero hwdownloads, zero new Panfrost
interrupts, zero new IOMMU faults or Cedrus timeouts, and A/V stayed within
0.001 seconds. At exit the video plane was detached (`crtc=(null)`, `fb=0`) and
the RGB console was restored.

The pre-existing `vo=drm` teardown warning remains: restoring the saved atomic
state returns `EINVAL` after playback, despite the panel and plane state being
restored correctly. It is tracked separately and is not introduced by this
series.
