# On-screen signal-loss recovery, 2026-09-26

This bounded board-B test deliberately disabled the source GPU's HDMI output
while the sparse-verification V4L2 stream and DRM panel preview were active.
It then re-enabled the same 640×480 mode, reopened capture, and required a
second on-screen preview to finish. The operator recorded the complete visible
sequence after an explicit camera-ready checkpoint.

The first preview switched the projector from console framebuffer 40 to video
framebuffer 44. At 9.385 seconds the source output became disabled while HPD
and the EDID remained present. The driver stopped the active stream after its
no-frame timeout; `dd` received the expected `EIO`, the preview pipeline exited
nonzero, and the projector returned to console framebuffer 40.

At 15.966 seconds the same source output became enabled again. AFBD bootstrap
learned completion phase offset 2 from an 11/12 majority, a fresh V4L2 stream
opened, and the panel switched to video framebuffer 42. The recovered pipeline
submitted all 120 frames and exited successfully, after which the panel
returned to framebuffer 40. At the end of the bounded window the source was
disconnected and disabled and the EDID/HPD helper reported
`peripheral_restored=1 mismatch=0`.

Both streams reported zero unstable copies. The interrupted stream delivered
159 buffers before signal loss and the recovered stream delivered 121. Under
the combined capture, conversion, and DRM load the safety checks rejected 14
and 13 phase-unknown or phase-mismatch events respectively; no rejected event
was delivered. This is a successful fail-closed and reopen recovery result,
not a zero-drop or latency pass.

The tested V4L2 module SHA-256 was
`d91a6705379b9bab05838b4d7ea155de719ce414863b24f4b240ef627ceb343b`.
After the run, U-Boot proper was restored and read back as
`47ebcfa6dbfd646b2eab83fc1e5206086a2a1226cb5d840512051cbbf6e9e95d`;
the untouched SPL remained
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
The source-3 trace canaries were verified, the prior full-verification module
was restored, and the SCP probe was absent.

The optical recording will be linked and assessed separately once its local
path is available.
