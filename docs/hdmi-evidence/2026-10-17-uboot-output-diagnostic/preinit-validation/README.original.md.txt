# RAM-only initial panel power-state validation

User authorizes validating the ordered off/reset/output-rest sequence BEFORE ordinary logo initialization, using temporary U-Boot commands. No firmware flash, persistent environment writes, Linux patch, GP6 clear or stock partition modification.

Need a fresh cold-HDMI session -> first warm reset. Arm prepared host controller only after verifying cold Linux handoff/services. GP7 one-shot stop b007c0de consumed at U-Boot, persistent latch unchanged. First reset target~70s, HDMI connected throughout.

At warm prompt: check RTC/MIPS safe registers, replace normal countdown with5s wait, call existing `h713_disp teardown`. Source-reviewed teardown first ensures clocks/fabric accessible, stops AFBD/MIPS, places LVDS controls at rest, asserts reset and acquires/disables regulator. Verify PF6/PH16 low, PHY rest, MIPS reset. No direct gated display access before helper establishes access. Hold3s, verify low pins, then run ordinary `h713_disp auto 0x34 logo` once with PB5 restored on success/failure; remain in U-Boot and do not boot Linux.

This validates initial state normalization through the existing teardown helper, which also programs fabric/clocks and stops AFBD/MIPS; success alone would not isolate every operation or prove3s is minimum. Initial regulator acquisition can drive PF6 low with enable_count0; helper explicitly waits configured250ms on EALREADY plus deliberate3s hold. Actual rail voltage unmeasured. Normal power-on also retains550ms pre-delay and stock2ms/5ms reset pulse plus20ms settle.

Temporary controller is PREPARED NOT RUNNING while awaiting physical cold cycle. UART capture in parent logs remains active. Current board showing recovered logo at U-Boot; safe to begin physical cold cycle directly, no Linux shutdown needed.

PB5 explicitly high during pre-init off/hold sequence to retain fan operation; ordinary logo-init lamp blanking remains bounded and restores PB5 high.

Execution1: cold652992a7-6638-4887-b86b-5b9bf316282b verified25.32s with active services, source connected/enabled, firmware port-status2. First warm reset target70s. One-shot stop consumed; guarded teardown verified PF6/PH16 low and output rest before3s hold; normal logo init succeeded, PB5 high, Linux NOT started. Final timing720p, MIPS reset/status0, supply/reset high. No firmware/persistent environment writes. Timing:
2026-10-17T23:30:50.466192-07:00 reset_plus=0.000s reboot: Restarting system
2026-10-17T23:30:58.647649-07:00 reset_plus=8.181s H713 panel: teardown: supply off, reset held
2026-10-17T23:30:58.716997-07:00 reset_plus=8.251s H713_PREINIT_HOLD_DONE
2026-10-17T23:31:01.729750-07:00 reset_plus=11.264s H713_PREINIT_HOLD_DONE
2026-10-17T23:31:02.744663-07:00 reset_plus=12.278s H713 panel: stock power phase complete
2026-10-17T23:31:03.833358-07:00 reset_plus=13.367s H713 disp: boot logo published and committed
Awaiting operator visual verdict.

## Execution1 visual result: GOOD

Operator report received 2026-10-17T23:46:09.391850-07:00: logo showing. This is first successful pre-initialization normalization trial (1/1), not a confirmed prevention rate. Normal initialization also succeeds intermittently, including three consecutive recent good baseline attempts; do not interpret a single pass as proof of fix.

Combined evidence: two independent U-Boot black states locally recovered using ordered supply/reset/output cycle; output-only and quiet-output-reset controls failed on the second state. Startup normalization using guarded generic teardown +3s controlled-off interval then normal logo succeeded. Candidate belongs in explicit panel initial-state/power/reset sequencing. Generic teardown also touches AFBD/MIPS/fabric, so isolate/factor the panel operation rather than blindly inserting all teardown side effects into permanent startup. Physical rail behavior, required minimum off interval and tolerance of abnormal resets remain unmeasured. No firmware/persistent environment changes; current good logo preserved in U-Boot and capture remains active.
