# Patch series index

This directory holds **five independent series**. They target different source
trees, are applied by different build stages, and must never be mixed.

| Directory | Applies to | Filenames | Count |
|-----------|-----------|-----------|-------|
| [`kernel/`](kernel/README.md) | mainline Linux tarball, `config/versions.env` → `KERNEL_VERSION` | `0001-…` … `0NNN-…` | 115 in `series` |
| [`aic8800/`](aic8800/README.md) | AIC8800 vendor driver tarball, `radxa-pkg/aic8800` @ pinned commit | `aic8800-0001-…` | 8 |
| [`libva-v4l2-request/`](libva-v4l2-request/README.md) | Bootlin `libva-v4l2-request`, PR #38 at its pinned base | `0001-…` | 19 |
| [`mpv/`](mpv/README.md) | official mpv 0.40.0 | `0001-…` | 4 |
| `gstreamer/` | GStreamer 1.26.2, the v4l2codecs plugin only (`tools/video/build-gst-v4l2codecs.sh`) | `0001-…` | 1 in `series` (0003); 0001/0002 on disk, never deployed |

Both follow the same philosophy — a curated series on a pinned upstream tarball
rather than a fork — so each can be rebased onto a newer upstream by replaying
the series.

**Telling them apart:** kernel patches are bare-numbered (`0007-pwm-add-…`);
AIC8800 patches always carry the `aic8800-` prefix. For the bare-numbered
series, use the containing directory as the authority; kernel, VA-driver, and
mpv patches must never be applied across source trees.

They are also independently versioned: bumping `KERNEL_VERSION` has no effect on
the AIC8800 series, and bumping the AIC8800 commit has no effect on the kernel
series.
