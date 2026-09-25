# Source-side confirmation of the horizontal wrap

**Resolved:** The apparent wrap and missing bottom page came from reading each
plane 4 KiB after its actual base, not from the capture producer. See the
[corrected full-frame capture](../2026-09-25-corrected-frame/README.md). The
analysis below describes the original misaligned sample.

The user identified a roughly 60% horizontal displacement in the first
color capture. During one additional bounded 15-second HDMI window, COSMIC's
noninteractive screenshot captured the GPU's 640x480 HDMI output at the same
time as the projector's read-only NV16 DRAM sampler. The HDMI portion of that
screenshot is [`source-hdmi-output.png`](source-hdmi-output.png); it shows the
wallpaper and menu in their expected positions. The raw projector sample is
[`candidate-nv16.bin`](candidate-nv16.bin) and its direct conversion is
[`candidate-nv16.png`](candidate-nv16.png). Thus the source-side output is
correct and the wrap is in the projector capture path or our interpretation
of its buffers.

Rotating **each captured row left by exactly 384 pixels** puts Workspaces and
Applications at the left of the menu and the clock near the center, matching
the source screenshot. The captured Orion wallpaper was also compared to the
installed `/usr/share/backgrounds/cosmic/orion_nebula_nasa_heic0601a.jpg`
after a centered 4:3 crop. Over wallpaper rows 30..459, grayscale correlation
rose from **0.025** without correction to **0.992** after the 384-pixel row
rotation. Neighboring shifts 383 and 385 scored about 0.982. Comparing the
simultaneous source and receiver screenshots gives RGB correlation 0.025
uncorrected and 0.919 after rotation. This is a row-wise wrap, not a color
channel offset or an intentional wallpaper crop.

The corrected [`candidate-nv16-aligned.png`](candidate-nv16-aligned.png) also
omits the incomplete bottom seven rows; it is 640x473. The underlying NV16
sample is unchanged. Both planes still have an unwritten final 4 KiB page,
so the crop hides the green strip **without recovering those pixels**.
`tools/hdmi/nv16-to-png.py` now accepts `--rotate-left 384 --valid-rows 473`,
and new `--dump-nv16` trials and `capture-once.py` produce the aligned PNG
alongside the direct conversion. The subsequent base-address correction
recovered the complete frame without changing firmware or capture DMA
configuration.

The trial returned the GPU to disconnected state, and SCP reported restored
peripheral state and zero EDID mismatch. The board remained responsive.
