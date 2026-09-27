# Native 1280x720 capture-to-panel evidence

This gate exercised the complete prototype route at the panel's native raster:
source GPU -> 1280x720 EDID -> firmware HDMI receiver -> event-gated V4L2 NV16
capture -> FFmpeg BGR0 conversion -> DRM panel presentation.  The source
playlist contained the deterministic motion marker followed by
`Madame Leota Complete Audio Loop - 720.mp4`.

The test used Linux 6.18.38 built with patch 0137.  Its FIT SHA-256 was
`f83a428d5481be1a91267c5749ab30be69ff12b3b2c9a79f514f902b89004393`.
The temporary, previously validated U-Boot proper candidate supplied the
guarded VIncap completion hook and had SHA-256
`c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7`.
The exact 1280x720 module used for the run had SHA-256
`00fe1da801793c4577133e84c2694b4153a9219ea78689146b608ce268c791d5`.

The camera-gated command was:

```text
python3 tools/hdmi/run-native-720-panel.py --camera-ready \
  --video '/home/chris/Projects/h713/local/Madame Leota Complete Audio Loop - 720.mp4'
```

The bounded run completed all 240 requested frames.  DRM changed the primary
framebuffer from 40 to 45 and restored 40 afterward.  The source connector
returned to disconnected and disabled, the framebuffer console returned with
`AFBD_CTRL=0x03001901` and `AFBD_SRC=0xFFC00000`, and the IOMMU fault count
remained zero.  The operator saw both the motion marker and the Madame Leota
video, then saw the Linux console return correctly.

## Measured limitation

This is a native-resolution functional and optical pass, not the 60 Hz finish
line.  The firmware completion counter reported 957 produced frames while the
bounded consumer delivered 240.  It attempted 477 copies, rejected 239 frames,
and classified 237 copies as unstable.  Total copy/verification time was
12,491,685 us, or about 26.2 ms per attempted copy.  FFmpeg therefore produced
the 240 output frames at about 16 fps even though the receiver produced close
to 60 completion events per second.

The current 720p copy is longer than one 16.7 ms source interval.  Retrying
copies after the source changes compounds the cost: the prototype copied
nearly twice as many full frames as it delivered.  The next work should profile
and remove the uncached full-raster copy/verification bottleneck, preserve V4L2
timestamps into presentation, and schedule the newest complete frame against
panel vblank.  This result must not be described as sustained 60 Hz.

## Restoration

After the test, the original 1,798 U-Boot-proper sectors were restored and
fully read back with SHA-256
`47ebcfa6dbfd646b2eab83fc1e5206086a2a1226cb5d840512051cbbf6e9e95d`.
The original image booted, the established source-3 trace and canaries were
verified, the normal receiver power/EDID holds were restored, the console was
unblanked, and the board ended with zero IOMMU faults.
