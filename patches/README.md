# Patch series index

This directory holds independent component series (including a retired one). They target different source
trees, are applied by different build stages, and must never be mixed.

| Directory | Applies to | Filenames | Count |
|-----------|-----------|-----------|-------|
| [`u-boot/`](u-boot/README.md) | Pinned validated U-Boot commit plus shared kernel DT (`tools/build/prepare-uboot.sh`) | `0000-…`, `0001-…` | 2 in `series` |
| [`kernel/`](kernel/README.md) | mainline Linux tarball, `config/versions.env` → `KERNEL_VERSION` | `0001-…` … `0NNN-…` | 120 in `series` |
| [`aic8800/`](aic8800/README.md) | AIC8800 vendor driver tarball, `radxa-pkg/aic8800` @ pinned commit | `aic8800-0001-…` | 8 |
| [`libva-v4l2_request/`](libva-v4l2_request/README.md) | megi's `libva-v4l2_request` v1.2 at its pinned base (`tools/video/build-va-driver.sh`) | `0001-…` | 6 |
| [`libva-v4l2-request/`](libva-v4l2-request/README.md) | **retired 2026-10-03**: bootlin `libva-v4l2-request`, PR #38 (`build-va-driver-bootlin.sh`) | `0001-…` | 25 |
| [`mpv/`](mpv/README.md) | official mpv 0.40.0 | `0001-…` | 4 |
| `gstreamer/` | GStreamer 1.26.2, the v4l2codecs plugin only (`tools/video/build-gst-v4l2codecs.sh`) | `0001-…` | 1 in `series` (0003); 0001/0002 on disk, never deployed |

Each series has its own pinned source and preparation step. U-Boot exports
a validated commit from its existing fork before applying this incremental
series; the tarball-based components keep their existing preparation.

**Telling them apart:** kernel patches are bare-numbered (`0007-pwm-add-…`);
AIC8800 patches always carry the `aic8800-` prefix. For the bare-numbered
series, use the containing directory as the authority; kernel, VA-driver, and
mpv patches must never be applied across source trees.

They are also independently versioned: bumping `KERNEL_VERSION` has no effect on
the AIC8800 series, and bumping the AIC8800 commit has no effect on the kernel
series.
