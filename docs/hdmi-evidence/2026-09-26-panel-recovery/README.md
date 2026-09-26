# AFBD capture on the projector panel, 2026-09-26

Two bounded runs exercised the AFBD-bootstrap V4L2 driver through the existing
640×480 NV16 → 960×720 BGR0 conversion and 1280×720 DRM panel route. Both used
buffered V4L2 `read()` input and paced the panel at 20 fps. The tested module
SHA-256 was
`d91a6705379b9bab05838b4d7ea155de719ce414863b24f4b240ef627ceb343b`.

The full-verification and sparse-verification runs both submitted all 120
frames, reported the first DRM video frame shown, and exited successfully. In
both runs the primary framebuffer changed from 40 to 45 during playback and
returned to 40 afterward. Hardware scanout likewise returned exactly to its
initial `0xffc00000` address. The bounded EDID/HPD operation reported
`peripheral_restored=1 mismatch=0`, and the source connector returned to
disconnected and disabled before the second run and after the test.

The full diagnostic oracle converted about 30 frames/s. Its capture stream
delivered 121 clean buffers, but the expensive double-read caught and rejected
12 copies that changed under the combined capture, conversion, and DRM load.
It accounted for 310 produced frames, 177 overwritten frames, and no delivered
unstable copy:

```text
stream polls=1154 completion_events=198 no_buffer=65 copies=133 unstable=12
delivered=121 produced=310 overwritten=177 rejected=12
```

The sparse run converted about 31 frames/s and reported zero unstable copies.
It delivered 121 buffers, accounted for 216 produced and 88 overwritten
frames, and conservatively rejected seven phase-unknown or phase-mismatch
events. The phase monitor relearned offset 2 each time before delivery resumed:

```text
stream polls=928 completion_events=183 no_buffer=55 copies=121 unstable=0
delivered=121 produced=216 overwritten=88 rejected=7
```

This proves that the complete capture/scale/DRM route can start after AFBD
phase bootstrap, restore the console, disconnect, and start again. The logs do
not replace an operator's optical assessment of tearing, color, or short
freezes. The nonzero rejection counts also mean this is recovery evidence, not
a zero-drop or latency pass.

Only the established temporary trace U-Boot proper was used. After the tests,
the original U-Boot readback was restored to
`47ebcfa6dbfd646b2eab83fc1e5206086a2a1226cb5d840512051cbbf6e9e95d`
and the untouched SPL remained
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
The MIPS source-3 canaries were verified, the prior full-verification module
was reloaded, and the SCP probe was absent.
