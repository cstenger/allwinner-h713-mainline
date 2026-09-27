# Hardware-acknowledged RGB cleanup

Patch 0137 replaces the empirical eight-vsync hold during a successful CRTC
disable with a hardware-acknowledged teardown sequence.  It clears the RGB
fetch enable through `AFBD_READY`, waits for `AFBD_STATUS_DONE`, and then waits
for the next physical AFBD vsync before DRM may release the outgoing
framebuffer.  Active page flips continue to use the validated eight-vsync
retirement queue, and any disable acknowledgement timeout falls back to that
queue.

The first hardware trial exposed an incomplete resume operation.  The disable
completed and the framebuffer address returned to `0xFFC00000`, but the screen
remained black because the source commit only ORed in control bit 0.  That left
the disable-only bit 31 set: `AFBD_CTRL` read `0x83001901` instead of the
validated active value `0x03001901`.  Writing the full active value immediately
recovered the Linux console without an IOMMU fault.

The refined patch therefore makes every RGB source commit restore the captured,
probe-validated `rgb_ctrl_active` word.  This is the same exact restoration
already used by the proven NV12-overlay-to-RGB handoff, rather than a partial
bit update.

The corrected FIT was built from the complete 101-patch series:

```text
file: build/out/h713-kernel.fit
size: 7753044 bytes
sha256: f83a428d5481be1a91267c5749ab30be69ff12b3b2c9a79f514f902b89004393
md5: d81fc055611ce8d44aafd038a09d6b68
uname: Linux h713-arm64 6.18.38 #1 SMP Sat Sep 26 20:39:18 PDT 2026 aarch64 GNU/Linux
```

After reboot and console unblank, the camera-gated test command was:

```text
python3 tools/hdmi/run-panel-bgr-diagnostic.py --camera-ready
```

The final run displayed a generated 1280x720 SMPTE color-bar frame through
direct DRM for eight seconds, then returned to the Linux framebuffer.  Its
machine result was:

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

The kernel logged `RGB fetch quiesced at physical vblank 10347`.  The post-run
state was framebuffer blank `0`, `AFBD_CTRL=0x03001901`, and
`AFBD_SRC=0xFFC00000`; there was no quiesce timeout or IOMMU page fault.  The
operator observed the color bars and confirmed that the Linux console returned
correctly.

This closes the determinism gap identified in the physical-vsync retirement
milestone for the CRTC-disable path: framebuffer cleanup is now gated by an
explicit fetch disable acknowledgement and a physical frame boundary, not by a
random timeout or an empirically selected number of scans.  The older
eight-vsync mechanism remains as the conservative timeout fallback and the
active-page-flip retirement mechanism.
