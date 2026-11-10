# Bounded ring-write experiment, 2026-09-06

Result: one initial ring write plus four additional writes survived. Increasing
the budget did not change any of the seventeen composition registers or AFBD
geometry. This does not validate the handoff's proposed causal fix.

## Setup

Following the user's cold boot into default Linux, returned to U-Boot by a
normal software reboot, ran `h713_disp init 0x34`, verified both firmware and
application readiness and core status 1, and booted
`/root/fits/h713-kernel-decd-iommu-0076v3.fit` with
`initcall_blacklist=h713_afbd_platform_driver_init`.
This experiment therefore followed a warm reboot after the user's cold boot;
it was not a direct cold-boot-to-test sequence.

The test kernel automatically loaded the regular DECD module. Replaced it,
before submitting any frames, with `/root/sunxi-decd-budget.ko
ring_writes_max=1`, and loaded `/root/hy310-cpu-comm-next.ko`.
MIPS `cmds` returned its command list. The corrected client SHA-256 matched
`256143c876bd6fa2f1564946436564c7a32c5c13b79abe26f78bf1fdff363651`.

## Measurements

- Before the first submit, composition, AFBD and selector reads were all zero.
  Core status was 1 and IOMMU bypass register was `0x7c`. Clock/power gating is
  a possible explanation for the zero reads; they are not proof of cleared
  hardware state. The module replacement is another setup difference.
- Submitted the corrected client with `/root/decd-test-frame.nv12`, 2000 ms.
  Counters reached 1/1. All seventeen composition values matched the August 31
  1280x720 reference. This alone does not prove a firmware composition update:
  the submission also issued PM_HINT on, and baseline reads were zero.
- Ran `dtv get_fb`, waited and captured again. Composition stayed identical.
  The elog contained parsed 1280x720 frame information and stride 1280.
- Increased the absolute maximum from 1 to 5, submitted the same corrected
  frame again, and repeated the captures and `dtv get_fb`. Counters reached
  5/5, with core alive and SSH responsive. Composition and AFBD geometry did
  not change. No new SetWindow/CalcWindow/WriteReg entries were found in the
  captured elog compared with baseline. The log contains damaged/partial
  records, so absence of these entries is not definitive proof of no service.

After both submissions AFBD source geometry was `0x043f077f` (1920x1088
minus one), strides were `0x780` (1920), picture/chroma geometry was
1280x720/1280x360, and source control was `0x03000010`.
After the second submit all Y slots changed from `0xffe00000` to
`0xffc00000`, all C slots from `0xffee1000` to `0xffce1000`, and descriptor
address from `0x4d941000` to `0x4d942000`. These are real ring updates.
IOMMU bypass remained `0x7c`; the Y/C addresses are consequently inconsistent
with the physical-buffer recipe. Selector stayed `0x29000000`.

## Interpretation and next step

The extra writes were tolerated in this run. They did not produce a geometry
transition, and the initial 852x480 mismatch was not reproduced. Descriptor
parsing is demonstrated, completed window programming is not. Do not call the
snapshot names `first-serviced`/`more-serviced` proof of service: those labels
mean only that the capture followed `dtv get_fb`.

Next, establish what drives the firmware window state machine on this boot,
using the earlier SetSource/THidTVPro evidence and current firmware logs.
Before any visual test, resolve the AFBD geometry and addressing mismatches
and compare the complete state against the successful capture. No visual
test or manual composition correction was performed in this experiment.

Board remains alive, modules loaded, ring budget exhausted at 5/5. No default
boot settings or FAT configuration were changed. The user reported a blank
screen before the first submit; no later visual result was requested.

Raw register snapshots, client output, script, and gzip-compressed firmware
logs are in [composition-budget-2026-09-06](composition-budget-2026-09-06/).
Board originals are under `/root/composition-budget-20260906`.
