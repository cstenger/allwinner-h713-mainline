# Cedrus controls: compliance 49/49, 2026-09-17

Patch **0121** fixes the remaining `VIDIOC_G/S/TRY_EXT_CTRLS` failure.
`v4l2-compliance` 1.30.1 on the H713 bench board, running kernel 6.18.38,
now reports **49 succeeded, 0 failed, 0 warnings**.

## Cause and fix

`v4l2-test-controls.cpp:939` tries a control's current value obtained through
`G_EXT_CTRLS`. On a newly opened Cedrus device the HEVC SPS was initialized
by the generic compound-control initializer to zero. That gives
`chroma_format_idc=0` (monochrome), while Cedrus's validator accepts only
`chroma_format_idc=1` (4:2:0). Trying the driver's own initial value therefore
returned EINVAL. This was present before the scaler patches.

0121 supplies a driver-specific 8-bit 4:2:0 SPS default through
`v4l2_ctrl_config.p_def.p_const`. Unsupported chroma formats and bit depths
are still rejected. No compliance tests or decoder validation were disabled.

There was also a separate state-management bug: the HEVC `.try_ctrl` callback
changed `ctx->bit_depth` and recalculated capture/reconstruction formats.
Trying Main10 could enlarge the buffer format without committing the SPS.
Allocating buffers after that TRY could also undermine the intended guard
against increasing bit depth while buffers are allocated.

Validation remains in `.try_ctrl`; bit-depth and format changes now happen
only in `.s_ctrl`, when the framework commits a changed control. Allocated
buffers keep their negotiated maximum bit depth, including when an 8-bit SPS
is accepted after negotiating Main10. The early Main10 declaration used by
the VA driver still sizes capture and full-resolution reconstruction side
planes before allocation.

## Reproduction and validation

`tools/video/cedrus-control-test.c` checks the fresh SPS value, current-value
TRY/SET, pure Main10 TRY, unchanged stored SPS, allocation after TRY, rejection
of a subsequent depth increase while busy, a successful Main10 commit after
freeing buffers, and continued invalid SPS rejection.

Before 0121, the fresh-default reproduction printed:

```text
HEVC default chroma_format_idc=0 depth=8/8
FAIL: VIDIOC_TRY_EXT_CTRLS returned EINVAL
```

Bypassing only that invalid default to isolate the second bug, trying Main10
changed `G_FMT`, failing the format-equality assertion. Both cases pass after
0121. The scaler API test also passes.

Build:

```sh
JOBS=12 tools/build/build.sh kernel
```

All **88** series entries apply to a clean pinned 6.18.38 source tarball.
Image, both DTBs, modules, and the bench FIT build successfully. Final tree:

```text
build/linux-6.18.38-2aa602684a789bcb98086f3365e656d2d013baa10186142d98e9d198aa877463
```

The installed and loaded module MD5 is `772c6a46b668baafb98dcf00ddb15429`.
The prior module was backed up under `/mnt/media-data/h713-module-backups`.
No reboot or FIT flash was required.

Run the focused test and compliance on the board:

```sh
cc -O2 -Wall -Wextra -Werror -o cedrus-control-test cedrus-control-test.c
./cedrus-control-test /dev/video0
v4l2-compliance -d /dev/video0
```

`compliance.txt`, `controls.log`, and `scaler-api.log` preserve the results.
The **53-capture** codec pixel regression passes with no DMA overruns or
kernel faults, including both codecs, Main10, concurrent contexts, larger
pitches, and later P-frame reconstruction. All 51 capture checks common to
the pre-fix matrix have byte-identical active pixels. `results.json`,
`scaler.log`, and the empty `dmesg-new.txt` preserve the final results. x265's
nonfatal NUMA-affinity messages occur during test-stream generation, not
hardware decoding.

Losslessly compressed `.nv12.gz` captures remain on the board under
`/mnt/media-data/cedrus-control-fix/scaler`. DMA guards are restored to zero,
the decoder is idle, and rootfs usage remains at 93%.
