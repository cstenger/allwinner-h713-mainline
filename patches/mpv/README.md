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

## Board state, and the reproducibility gap — 2026-09-03

The patched binary lives on the board as **`/root/mpv-h713-test`**. It is not
installed: `/usr/bin/mpv` is stock Debian v0.40.0 with no direct path, and no
mpv build tree remains on the board. Re-verified independently on the clean
VA driver:

```text
Using hardware decoding (vaapi).
VO: [drm] 1280x720 vaapi[nv12]
[vo/drm] Using direct DRM PRIME video-plane scanout
decode failures: 0        panfrost mentions in the log: 0
```

**This series has the problem `build-va-driver.sh` was written to solve.** That
script exists because the VA driver was "built by hand ... nothing in the rootfs
build produces it, so a fresh flash silently loses hardware decode and the way
back lives in somebody's shell history". The patched mpv is now in exactly that
position: one unversioned binary in `/root`, reproducible only by following the
instructions above by hand.

### `tools/video/build-mpv.sh`

Written to close this. It mirrors `build-va-driver.sh`: applies this series to
the pinned tag on the host, ships the tree, **builds on the board** so mpv links
against the board's own FFmpeg/libva/libdrm/ALSA, verifies the direct-path
marker is present in the resulting binary, installs, stamps
`/etc/h713-video-stack`, and with `--test` proves the path on hardware.

Two deliberate choices:

- **Installs to `/usr/local/bin/mpv`, not `/usr/bin/mpv`.** Debian owns the
  latter, so overwriting it means the next `apt upgrade` silently reverts the
  video path. `/usr/local/bin` precedes `/usr/bin` in the board's PATH, so the
  patched build wins while the distro package stays intact.
- **Verifies the marker string in the built binary.** A series that failed to
  apply would otherwise install a stock mpv and look like success until someone
  read the logs.

**It cannot run yet.** The board has no default route, and building mpv needs
dev packages it does not have:

```text
pkgconfig:libavcodec  libavformat  libavutil  libswscale  alsa
```

(`meson`, `ninja`, `cc`, `pkg-config`, `libva` and `libdrm` are all present —
which is why the VA driver builds there fine.) The script checks this first and
stops with the exact list rather than failing deep inside meson. Supply the
arm64 `-dev` packages — temporary route, or copied `.deb` files — and it runs.

Until then `/root/mpv-h713-test` remains the only artifact, and a reflash loses
it.
