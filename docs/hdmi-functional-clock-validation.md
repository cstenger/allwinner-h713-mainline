# Receiver and MIPS functional clock descriptions

2026-09-18. Patch 0125 corrects five CCU clocks against the full-symbol vendor
kernel SHA256 3e0d2d3420e066277021fe78d8398eff3937afdaf00c3625354becfbc398bc04.
Public IDs are unchanged. Existing rate flags are retained, without adding
CLK_SET_RATE_PARENT. No assigned rates/parents, live PLL reprogramming, or
consumer rate calls were added. The new descriptions give local rate control
when a future consumer explicitly requests it.

## Primary vendor descriptors

The packed divider fields record shift/width; parent-name arrays and the
clock-init num_parents field independently establish the mux order.

| Clock | Vendor descriptor | Register | M | P | Mux | Parent order |
|---|---|---|---|---|---|---|
| mips | c1464014, 88 bytes | 600 | 0:3 | none | 24:2 | pll-periph0-2x, pll-video0-4x, dcxo24M |
| tvfe_1296M | c14620a8, 108 bytes | d20 | 0:5 | 8:2 | 24:1 | pll-video0-4x, pll-adc |
| vincap_dma | c146192c, 88 bytes | d74 | 0:5 | none | 24:1 | pll-video2-4x, pll-periph0 |
| tcd3 | c14619a0, 108 bytes | d6c | 0:3 | 8:2 | 24:1 | pll-video0-4x, pll-adc |
| hdmi_audio | c1461820, 88 bytes | d84 | 0:5 | none | 24:1 | pll-video3-4x, pll-periph0-2x |

All five enable masks are 80000000. Receiver clocks were previously modeled
as AHB gates, falsely reporting 100 MHz. MIPS previously used a different
four-parent order and four-bit divider, reporting 8 MHz for mux 0 / M=2.
The vendor has three parents and M width 3. dcxo24M maps to the existing
osc24M input. P division is exponential, matching the existing CCU MP helper.

## Build and target test

Kernel Image/dtbs built successfully with Clang/LLD 22.1.8. Patch dry-run on
an independent pre-0125 source passed with --fuzz=0; git diff --check passed.
One-time FIT: /root/fits/h713-hdmi-functional-clocks.fit, SHA256
f807d7276c2c4d2f78c45d8627e64afde0bf8d1774879604bb20646d99dbc181.
Target kernel: 6.18.38 #4 SMP Fri Sep 18 00:16:45 PDT 2026.
Linux, serial, and SSH came up. No captured oops/BUG; the existing Wi-Fi
supplier-link and regulatory.db boot messages remain.

Framework rate reports after boot:

- TVFE: 1296 MHz; load of the power hold adds prepare/enable 1/1, hardware Y.
- TCD3: 27 MHz.
- VINCAP DMA: 150 MHz; power hold adds prepare/enable 1/1, hardware Y.
- HDMI audio: 1152 MHz, without a consumer reference.
- MIPS: 200 MHz, with the core stopped.

These are computed from the inherited PLL providers and registers, not
frequency measurements. This patch does not independently validate every
root PLL definition. A gate reporting Y does not prove its parent PLL is on
or the functional receiver is locked.

Before #4 and while its holds were active, sampled registers matched:
600=80000002, d20=80000000, d6c=80000305, d74=81000001,
d84=80000000. d20 was zero immediately after boot, before the hold, as
expected. Sampled PLL registers 02001020/28/40/50/60/68 were unchanged.
No shared PLL write was performed. Correct parent ownership means releasing
functional references may also gate unreferenced parents through normal CCF
behavior; the holds were left active after this test, rather than claiming
an exact boot-state rollback through unload.

## Source detection remains working

The default ten-second reversible trial passed on #4 with optional stock
controls disabled. At 1.502 seconds, the GPU read the exact 128-byte EDID
SHA256 0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290;
at 1.752 seconds COSMIC enabled output. Restoration returned it to disconnected
at 11.622 seconds, then disabled. All saved peripheral/SRAM restoration checks
passed. Separate read-only snapshot confirmed original HPD/DDC and controls.
SCP and MIPS are both stopped; DDC module is removed and pins are unclaimed.
Only removable TVFE/TVCAP and EDID consumers remain loaded.

MIPS IPC timeout was observed on #3, not repeated on #4. This clock-description
fix does not claim to resolve it. Receiver lock, timings, frame DMA, and V4L2
capture remain pending.

Evidence: [before](hdmi-evidence/2026-09-18-functional-clocks/before.log),
[boot](hdmi-evidence/2026-09-18-functional-clocks/after-boot.log),
[holds](hdmi-evidence/2026-09-18-functional-clocks/held.log),
[source](hdmi-evidence/2026-09-18-functional-clocks/source.json),
[final state](hdmi-evidence/2026-09-18-functional-clocks/final-state.log).
