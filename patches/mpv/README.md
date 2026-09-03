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

## SOLVED — cross-build recipe that works (2026-09-03)

The blocker below was one missing host package. `debian-archive-keyring` was
present only as a cached `.pkg.tar.zst` in `build/cache`, never installed, so
`/usr/share/keyrings/debian-archive-keyring.gpg` did not exist and apt rejected
every repository as unsigned. No amount of `--keyring` juggling helps; install
it and the flag becomes unnecessary:

```sh
sudo pacman -U build/cache/debian-archive-keyring/debian-archive-keyring-*.pkg.tar.zst
```

`arch-test` is not packaged for Arch, so `--skip=check/qemu` stays.

### The recipe, verified end to end

```sh
# 1. arm64 Debian 13 rootfs with mpv's build deps (~1.1 GB, a few minutes)
mmdebstrap --mode=unshare --architecture=arm64 --variant=apt --skip=check/qemu \
  --include=build-essential,meson,ninja-build,pkg-config,ca-certificates,\
libavcodec-dev,libavfilter-dev,libavformat-dev,libavutil-dev,libswresample-dev,\
libswscale-dev,libplacebo-dev,libass-dev,libasound2-dev,libva-dev,libdrm-dev,\
libdisplay-info-dev \
  trixie /tmp/arm64-root.tar

# 2. extract under a user namespace so ownership maps
unshare -r tar -xf /tmp/arm64-root.tar -C /tmp/arm64root

# 3. patched source in, build inside; binfmt's F flag runs aarch64 with no
#    qemu binary copied into the chroot
cp -a local/upstream/mpv-src /tmp/arm64root/build-mpv
unshare -r --mount --pid --fork chroot /tmp/arm64root /bin/bash -c \
  'mount -t proc proc /proc; cd /build-mpv &&
   meson setup build --buildtype=release -Dauto_features=disabled \
     -Dalsa=enabled -Ddrm=enabled -Dgl=disabled -Dlibmpv=false \
     -Dvaapi=enabled -Dvaapi-drm=enabled &&
   ninja -C build mpv'
```

230 compile steps, producing a 2.2 MB aarch64 binary containing the direct-path
marker. Installed to `/usr/local/bin/mpv` on the board and verified:

```text
which mpv -> /usr/local/bin/mpv
Using hardware decoding (vaapi).
VO: [drm] 1280x720 vaapi[nv12]
[vo/drm] Using direct DRM PRIME video-plane scanout
decode failures: 0     panfrost mentions: 0
```

Two things to know. `libdisplay-info-dev` is required by `-Ddrm=enabled`
alongside `libdrm` and is easy to miss — mpv's `meson.build:934` is the
authority. And **apt does not work inside the emulated chroot** (`Sub-process
http returned an error code (112)`), so add packages to the `mmdebstrap
--include` list and rebuild rather than trying to `apt-get install` in place.

**`tools/video/build-mpv.sh` still builds on the board and therefore cannot
work** — see the space finding below. It should be rewritten around this recipe.

## Superseded: cross-build attempt — blocked on mmdebstrap keyring plumbing

Building on the board is **not possible**: its rootfs is 2.7 G at ~97 % full,
and an mpv build tree needs several hundred MB. Freeing 126 M of stale FITs was
not close to enough. Do not retry that route without resizing the filesystem.

The host route is the right one and is *nearly* working. Everything needed is
present on the host:

```text
unprivileged userns   OK        qemu-aarch64 binfmt   registered, flags PF
mmdebstrap            present   debootstrap           present
disk                  1.2 T free
```

`flags: PF` matters — the **F** flag preloads qemu into the kernel, so an arm64
chroot works without copying a qemu binary into it.

**The blocker is that apt inside mmdebstrap rejects the Debian archive as
unsigned**, and `--keyring` does not fix it. Four forms were tried, all failing
identically with `The repository '...trixie InRelease' is not signed`:

1. the project's cached `debian-archive-keyring.gpg` — stale, created 2021;
2. a `gpg --dearmor` of the package's `.asc` files — verified to contain 6 keys
   including trixie;
3. `--setup-hook` `copy-in` into `/etc/apt/trusted.gpg.d/` — needs a
   `mkdir -p "$1"/etc/apt/trusted.gpg.d` setup-hook first, since the directory
   does not exist when setup hooks run. With that added the hook succeeds and
   the signature check still fails;
4. the canonical shipped binary keyrings from
   `usr/share/keyrings/*trixie*.gpg`, passed as a directory.

The keys are not the problem — `gpg --no-default-keyring --keyring <file>
--list-keys` reads them fine. `--keyring` simply is not reaching the apt
invocation that verifies `InRelease`. **Read mmdebstrap's documentation or
source for how it threads the keyring through, rather than trying more key
formats — that avenue is exhausted.**

Working invocation apart from the keyring, for whoever resumes:

```sh
mmdebstrap --mode=unshare --architecture=arm64 --variant=apt \
  --skip=check/qemu \
  --include=build-essential,meson,ninja-build,pkg-config,ca-certificates,\
libavcodec-dev,libavfilter-dev,libavformat-dev,libavutil-dev,\
libswresample-dev,libswscale-dev,libplacebo-dev,libass-dev,libasound2-dev,\
libva-dev,libdrm-dev \
  trixie /path/to/arm64-root.tar
```

`--skip=check/qemu` is required (no `arch-test` on an Arch host). Output must be
a **tarball, not a directory** — writing a directory tree into `$HOME` fails
with "Permission denied" under `--mode=unshare`.

mpv's genuinely required dependencies, taken from its `meson.build` rather than
guessed: libavcodec, libavfilter, libavformat, libavutil, libswresample,
libswscale, libplacebo, libass — plus alsa, libva and libdrm for this
configuration. An earlier guess omitted libavfilter, libplacebo and libass and
cost three round trips.
