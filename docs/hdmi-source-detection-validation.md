# Source detection and EDID validation

2026-09-18, board A, GPU HDMI output physically connected to the projector input.
Workstation NVIDIA connector: card1-HDMI-A-1, COSMIC desktop. Temporary target
kernel: 6.18.38 #3 SMP Thu Sep 17 16:24:17 PDT 2026. No persistent boot settings,
normal kernel images, or Claude checkout files were changed.

## Cold recovery

Both systems were cold-booted by the owner. Target normal kernel #1 came up with
SCP reset held and R_CCU EDID clock/reset registers zero. SSH reconnected through
the existing spirits AP. The test FIT was absent and was restaged, checked against
SHA256 2fdb850382b2190d1a35f4a2726208470e82b3a60394cf9cbce59b0236aca100,
then booted once through U-Boot using volatile settings. TVFE/TVCAP and four
receiver clocks were held through the existing removable consumer. The EDID
consumer supplied 24 MHz and released its reset. A fixed read-only SCP snapshot
passed and verified SRAM/vector restoration.

## Reversible test

The DDC pinctrl consumer claimed PL10–PL15 through the framework, selecting
s_twi0/1/2 for all three port pairs. It avoids guessing which physical port is
wired. A tiny SCP program backed up three 256-byte EDID windows, HPD, DDC
configuration, and four optional stock controls before any peripheral write.
It held HPD low, disabled DDC, programmed and verified the same test EDID on all
ports, enabled DDC, asserted HPD for ten seconds, then restored the saved values.
ARM never accessed HPD or the previously faulting wrapper.

The first cold-run trial read back intended HPD/control values but did not cause
source detection. EDID headers read zero after DDC enable. The next revision
used explicit paired 64-bit ARM SRAM writes/readbacks for the payload and added
SCP checks of its first two words before modifying peripherals. That run detected
the sink and read the exact EDID. These revisions also changed instruction
layout; this does not independently isolate the cause of the first failure.

The subsequent trial omitted all optional stock control writes. Those registers
read zero while active, yet the source again detected the sink:

- At 1.387 seconds: connected, EDID 128 bytes, 640x480 modes.
- At 1.654 seconds: the desktop enabled the HDMI output.
- At 11.458 seconds: disconnected after restoration; subsequently disabled.
- Source EDID SHA256: 0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290.
- Source bytes matched the generated file exactly; edid-decode conformity PASS.

This verifies source-side HPD and DDC over the attached cable. The four optional
stock controls are not needed for this repeat test; this has not been separately
repeated from a cold boot without first testing those controls.

## Readbacks and cleanup

SCP-visible payload words: ffffff00, 00ffffff. Each EDID window's first word
was ffffff00 before DDC enable, then read zero while DDC was enabled. The GPU
nevertheless read the full correct EDID. Active-window zero readback therefore
cannot alone establish an empty EDID or failed programming.

Active HPD=0, B00=00a0a0a0, B04=07000007, B08=00c0c0c0.
Cleanup reported peripheral_restored=1, mismatch=0, exception=0, restored=1,
SCP reset=0. A separate read-only snapshot confirmed original HPD=7,
B00=00a0a0a0, B04=07000000, B08=00606060 and all four controls zero.
DDC pins were returned to gpio_in, with ownership released. Their initial
mux was disabled (F); cleanup uses input (0), rather than reproducing that mux.
PL9 IR and other pins were preserved; GPIO config read 0000003f afterward.

The eight previously validated THDMIRX words were unchanged while the source
was connected. This is not a lock-status test. No PHY/controller initialization,
receiver timing result, captured frame, or V4L2 interface is established yet.

Evidence: [source states](hdmi-evidence/2026-09-18-detection/source.json),
[target](hdmi-evidence/2026-09-18-detection/target.log),
[cleanup](hdmi-evidence/2026-09-18-detection/cleanup.log),
[receiver](hdmi-evidence/2026-09-18-detection/receiver.log),
[source EDID](hdmi-evidence/2026-09-18-detection/source.edid).
