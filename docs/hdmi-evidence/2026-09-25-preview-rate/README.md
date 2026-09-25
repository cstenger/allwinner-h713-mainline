# Live HDMI preview throughput isolation

The first panel preview was functional but only delivered about 11 frames/s.
All trials below used the same 640×480 NV16 HDMI test source, the existing
source-3 setup, a 30-second EDID/HPD window, 120 converted output frames,
960×720 scale plus black side bars to 1280×720 BGR0, and the same removable
V4L2 bridge. Each trial restored HPD and the console framebuffer. Sparse
trials also reloaded the module with `verify_full=1` afterward.

| V4L2 input / verification | Output | FFmpeg producer rate | Capture worker |
| --- | --- | ---: | --- |
| mmap / full, player 10 fps | DRM | ~11 fps | [first panel run](../2026-09-25-panel-preview/trial.log) |
| mmap / full, player 20 fps | DRM | ~11 fps | [log](full20-trial.log) |
| mmap / sparse, player 20 fps | DRM | ~11 fps | [log](sparse20-trial.log) |
| mmap / sparse | discard | ~12 fps | [log](sparse-mmap-null-trial.log) |
| buffered `read()` / sparse | discard | ~47 fps | [log](sparse-read-null-trial.log) |
| buffered `read()` / sparse, player 20 fps | DRM | ~31 fps | [log](sparse-read-panel-trial.log) |
| buffered `read()` / full, player 20 fps | DRM | ~16 fps | [log](full-read-panel-trial.log) |

The synthetic cached-memory scale/pad/BGR0 conversion fed `cat` at about
74 fps. The [synthetic DRM run](synthetic-panel-ffmpeg.log) fed its 20 fps
player at about 31 fps, so neither the conversion arithmetic nor DRM
presentation alone explains the 11 fps live pipeline. Raising player pace
or removing full-plane verification did not change the mmap pipeline rate.
Its capture worker reported many ring events without an available V4L2
buffer, indicating downstream backpressure.

The V4L2 bridge currently uses `vb2_dma_contig_memops`. FFmpeg's V4L2
input mmaps those DMA buffers and scales directly from them. The buffered
route uses V4L2 `read()` through `dd iflag=fullblock bs=614400`, then feeds
complete NV16 frames to FFmpeg as rawvideo. Its much higher rate is
consistent with paying for one copy out of the DMA buffer and then scaling
from ordinary cached memory. This is an inference from the controlled
comparison, not a direct cache-policy measurement. The current kernel does
not build `CONFIG_VIDEOBUF2_VMALLOC`, so swapping the kernel module's vb2
allocator would require a kernel change. The userspace buffered route leaves
the installed kernel and firmware untouched.

The successful [sparse buffered panel run](sparse-read-panel-summary.json)
fed all 120 frames above the player's 20 fps pace with zero unstable copies;
its [FFmpeg log](sparse-read-panel-target-ffmpeg.log) and
[mpv log](sparse-read-panel-target-mpv.log) are preserved. The
[full-verification buffered panel run](full-read-panel-summary.json) also
completed and improved over mmap, but its 16 fps producer cannot sustain the
20 fps display pace. Both restored the console, and the sparse run's
[module restoration](sparse-read-panel-restore.log) passed. The optical
appearance of these faster runs was not yet confirmed by the operator.

A separate bounded [120-frame moving-pattern read() trial](read-motion-analysis.json)
then checked the actual NV16 bytes before conversion. All 120 frames were
patterned, with zero mismatched IDs across the sampled bands and zero stripe
position mismatches. There were 118 sequential frame steps, one duplicate,
and no skips. Its [trial log](read-motion-trial.log) and
[full-verification restoration](read-motion-restore.log) are preserved.
This checks the buffered read path against moving source content; it does not
prove that every future firmware ring turnover is tear-free.

`read()` plus rawvideo discards V4L2 timestamps and sequence numbers; this
is a preview-throughput experiment, not the final recording interface.
Firmware ring completion and ownership remain inferred. The next capture
work should pair the faster buffered preview with a motion-integrity check
and obtain a real ring-completion signal before relying on sparse verification
for continuous use.
