# Patch series index

This directory holds **four independent series**. They target different source
trees, are applied by different build stages, and must never be mixed.

| Directory | Applies to | Filenames | Count |
|-----------|-----------|-----------|-------|
| [`kernel/`](kernel/README.md) | mainline Linux tarball, `config/versions.env` → `KERNEL_VERSION` | `0001-…` … `00NN-…` | 38 |
| [`aic8800/`](aic8800/README.md) | AIC8800 vendor driver tarball, `radxa-pkg/aic8800` @ pinned commit | `aic8800-0001-…` | 4 |
| [`libva-v4l2-request/`](libva-v4l2-request/README.md) | Bootlin `libva-v4l2-request`, PR #38 at its pinned base | `0001-…` | 7 |
| [`mpv/`](mpv/README.md) | official mpv 0.40.0 | `0001-…` | 1 |

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
