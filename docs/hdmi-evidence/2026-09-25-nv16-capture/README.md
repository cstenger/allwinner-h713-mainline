# First color HDMI input capture

**Resolved:** The apparent last-page shortfall and row wrap were caused by
starting the diagnostic read 4 KiB after the true plane base. The
[corrected full-frame capture](../2026-09-25-corrected-frame/README.md)
documents the 640×480 result. The observations below refer to the original
misaligned read.

The six dynamic regions found in the [page-hash trial](../2026-09-25-framebuf-luma/README.md)
are organized as three near-identical 640x480 luma planes followed by three
near-identical 640x480 interleaved chroma planes. The first three regions have
the desktop luma distribution (mean 87.57); the last three center around
128 (mean 130.52), with different even/odd byte distributions. Pairing
regions 0 and 3 as 4:2:2 semi-planar Y/UV (NV16) reconstructs a recognizable
**full-color image** of the HDMI-connected computer. Regions 1/4 and 2/5 have
the same respective Y and UV distributions, consistent with triple buffering.

The fixed read-only pair sampler, `tools/hdmi/read-nv16-pair.py`, took one
614,400-byte sample while the GPU output was enabled, 2.71 seconds into a
12-second HPD/EDID window. The raw sample is
[`candidate-nv16.bin`](candidate-nv16.bin). The standard-library BT.601
converter `tools/hdmi/nv16-to-png.py` produced
[`candidate-nv16.png`](candidate-nv16.png). The color image visibly matches
the computer's desktop, establishing that the projector's HDMI input reaches
ARM-readable DRAM in a usable color format. The converter does not modify the
capture data. The user subsequently spotted a horizontal wrap in this direct
conversion; a simultaneous source-side screenshot and the exact 384-pixel
row correction are documented in the [alignment follow-up](../2026-09-25-row-alignment/README.md).

From the isolated HDMI worktree, `python3 tools/hdmi/capture-once.py` now
performs the guarded source-3 preparation and saves a color PNG in one command.
It makes at most two clean 12-second GPU-detection attempts and prints the
output path. The one-attempt mode was exercised successfully on the live board
after this capture. It now prints the aligned 640x473 PNG while retaining the
raw buffer and direct 640x480 conversion. Preparation is
idempotent when MIPS is already live with the guarded source-3 trace.

The six-region CRC timeline in [`ring/ring.json`](ring/ring.json) sampled each
candidate plane 20 times over 2.4 seconds, roughly 125 ms apart. Every plane
changed on each successive sample. This confirms ongoing writes during the
live source window, but the sampling rate is too low to infer the producer's
frame cadence, current buffer index, or completion event.

There is a **one-page shortfall**: bytes `0x4a000..0x4afff` in both sampled
planes are zero. Thus 640x480 interpretation contains 473 complete rows,
384 bytes of row 474, and a missing bottom portion; the PNG shows a green
strip from interpreting zero chroma as valid video. The MIPS timing cache
still reports 640x480. We have not yet determined whether this is a DMA
length/configuration problem or a buffer-layout detail. The first slot's
remainder is zero except one trailing page, so this missing region is not
simply another contiguous plane within that slot.

This is a working **color snapshot**, not yet a reliable continuous-capture
interface. The next steps are to identify frame completion and buffer
selection, resolve the final-page shortfall, and expose coherent frames through
V4L2 or a userspace capture stream. TVFE/TVCAP, MIPS, Linux, and SSH stayed
responsive; SCP restored its peripheral state and released DDC pins after
the window. No receiver MMIO was accessed from ARM and nothing was flashed.
