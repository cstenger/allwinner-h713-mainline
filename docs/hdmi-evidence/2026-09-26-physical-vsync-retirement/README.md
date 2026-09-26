# Physical-vsync framebuffer retirement

The H713 AFBD DRM driver now retains an outgoing framebuffer until eight
physical AFBD vsync interrupts have completed after `cleanup_fb`.  The modeset
cleanup is the retirement boundary, while physical scan progress—not elapsed
wall-clock time or DRM's modeset-suppressed vblank work—controls release.

This follows three diagnostic iterations.  Waiting for AFBD `DONE` plus one
vblank still faulted.  A 100 ms delayed framebuffer reference passed one run,
but a later run observed a stale display-master read at about 120 ms.  Scheduling
`drm_vblank_work` was not usable here because all schedules returned zero while
DRM marked the adopted CRTC `inmodeset`.

The validated kernel FIT was built from the complete 100-patch series:

```text
file: build/out/h713-kernel.fit
size: 7752804 bytes
sha256: 13a643cfceaab0d725ccc2099683a167cb8b8aed5ccca8ada94d18822fb57a8d
md5: 73ca2708f2ba92001213ec8ea36ae774
uname: Linux h713-arm64 6.18.38 #1 SMP Sat Sep 26 13:57:32 PDT 2026 aarch64 GNU/Linux
```

After a cold kernel boot, the pre-test state was framebuffer blank `0`, AFBD
source `0xFFC00000`, and zero IOMMU page faults.  The camera-gated test command
was:

```text
python3 tools/hdmi/run-panel-bgr-diagnostic.py --camera-ready
```

It displayed a generated 1280×720 SMPTE color-bar frame through direct DRM for
eight seconds and then returned to the Linux framebuffer.  The machine result
was:

```json
{
  "camera_ready": true,
  "bgr0_sha256": "d0fa323bcab1b51b92bae88a7a0159b2c05995eb46b9ad6fedbfa3c6f1b2434b",
  "primary_fb_before": 40,
  "primary_fb_during": 44,
  "primary_fb_after": 40,
  "scanout_before": "05600178 0xFFC00000",
  "scanout_during": "05600178 0xFF000000",
  "scanout_after": "05600178 0xFFC00000",
  "iommu_faults_before": 0,
  "iommu_faults_after": 0
}
```

The post-test kernel log contained no AFBD/DRM warning, Oops, BUG, or IOMMU
page fault.  The operator confirmed that the color bars appeared correctly and
that the Linux console returned correctly.  Together, the KMS state, hardware
source readback, fault counter, and optical observation pass the retirement
gate that the elapsed-time implementations failed.

## Determinism boundary

The physical-vsync counter removes wall-clock scheduling from the normal path,
but eight scans remain an empirically established safety bound rather than a
documented hardware “last read complete” event.  The generic DRM commit tail
waits for vblank or `flip_done` before cleaning old framebuffers, and drivers
with stronger hardware signals wait for a flush-complete interrupt.  Neither
AFBD `DONE` nor the normal DRM flip event is strong enough on this block: both
preceded the stale read in the failed runs.  The sun50i IOMMU reports TLB
invalidation completion and faults, but does not expose completion of a display
master's outstanding reads.

The closest board-specific precedent is the reconstructed vendor DECD path.  A
live frame is retired only when a later frame displaces it from the four-entry
queue.  Teardown stops the frame manager, disables its IRQ, kills the tasklet,
and flushes deferred release work before freeing frame state.  A future
improvement should test the analogous AFBD sequence—quiesce fetch, wait for the
disable latch at a physical frame boundary, select the permanent console
buffer, and only then release the outgoing framebuffer.  Until that sequence
is hardware-proven, the passing eight-vsync retention stays as the safe
milestone implementation.
