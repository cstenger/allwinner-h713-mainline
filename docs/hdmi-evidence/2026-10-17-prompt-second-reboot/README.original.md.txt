# Prompt second warm reboot, 2026-10-17

Goal: genuine cold HDMI startup -> first warm reboot -> operator confirms black -> immediately request a second warm reboot, with no HDMI disconnection and no diagnostic TCON reads/writes. Record exact black-boot uptime at second reboot; do not add another confirmation or diagnostic checks after operator confirms black. The meaning of "prompt" is limited by boot time, operator report delay and dispatch latency; report measured age rather than assuming it is immediate after first black output.

Keep HDMI connected at both ends throughout. Cold cycle removes mains and serial/other USB for >=60s, with GP6 guard unchanged in software. Verify cold handoff and active HDMI services before trigger reboot. UART recorder is passive and reconnects across USB removal. Target wall clock is wrong; use host timestamps and /proc/uptime.

Initial working warm boot: 6833767e-43fb-4a1f-a34d-32a71d413f74, uptime4746.01s, no HDMI chosen handoff, capture/signal inactive, GP6 48444d49. Board has been running visibly good per prior report; no new visual confirmation requested.

Planned second-reboot serial command records marker, boot ID and uptime then requests systemctl reboot. No artificial hold and no TCON access. Prior delayed-control reboot marker was uptime238.07s; compare measured prompt reboot age against that.

Current phase: capture setup, before physical cold cycle.

Cold attempt 1: operator confirmed logo/console and HDMI connected through cold cycle. U-Boot source3 transition and cold handoff verified; Linux handoff, GP6 and both active HDMI services verified in cold1-verification.txt. First warm reboot initiated 2026-10-17T18:49:10.602405-07:00. No diagnostic TCON accesses.

First warm reboot: terminal MIPS park, panel power-down, restart, warm branch selected, FIFO status2 reset ->0, logo committed. Awaiting visual verdict. HDMI unchanged; no diagnostic TCON accesses. On black confirmation, send prewritten prompt-reboot-command.txt immediately, without further diagnostic delay.

Operator confirmed lit-but-black after first warm reboot, HDMI connected at both ends, and explicitly requested immediate second reboot. Sent second-reboot command before further diagnostics at 2026-10-17T18:50:30.691486-07:00. Command records boot ID/uptime, sets console log level, requests systemctl reboot. No diagnostic TCON access or HDMI changes.

Second reboot command executed on black boot cf194fa5-203e-4193-9909-511f9bb4e775 at uptime54.58s (previous delayed control238.07s). Serial confirms panel power-down, restart, warm branch, FIFO2 reset ->0, logo commit. Awaiting visual result; capture still active.

## Result: BLACK after prompt second warm reboot

Operator report received 2026-10-17T18:51:39.782500-07:00: panel remains lit but black after prompt second warm reboot. No HDMI changes or diagnostic TCON accesses during test. Prompt second-reboot request was at black boot uptime54.58s, compared with238.07s in successful delayed reboot-only control.

Interpretation: one additional warm initialization did not invariably recover black. Timing-dependent settling/discharge/recovery is plausible, but not established: comparison is between independent trigger trials and another reboot would also increase reset count. Preserve current black state with HDMI attached. Next discriminating step: delayed reboot near uptime238.07s on this still-black boot, no HDMI changes or diagnostic TCON accesses. If it recovers, repeat short/long waits on independent cold-trigger trials with matched reset counts before attributing causality to time. A complementary long dwell before the first post-HDMI reset tests whether the cold session itself sets a persistent state. Recorder remains active pending next step.

Delayed follow-up authorized 2026-10-17T19:02:20.478341-07:00: keep HDMI connected, no TCON access, reboot at uptime238.07s or immediately if target already elapsed; record actual uptime and target difference. Same retained black lineage after failed prompt reboot.

Delayed follow-up executed on retained black boot3250774c-c903-4192-a80d-cfb0c24e5684. Timer started after target had already elapsed: actual reboot-request uptime695.23s versus target238.07s, +457.16s. Script requested reboot immediately. This is a longer-delay trial, not an exact match. No diagnostic TCON accesses or HDMI changes. Serial confirms panel shutdown, restart, warm branch, FIFO2 reset ->0, logo commit and Linux login. Awaiting visual verdict; capture active.

## Delayed follow-up result: GOOD

Operator report received 2026-10-17T19:03:47.443674-07:00: logo and console returned after delayed reboot; HDMI stayed connected at both ends throughout.

Within this cold-trigger lineage: first warm boot black; prompt second warm reboot requested at black-boot uptime54.58s -> still black; subsequent delayed third warm reboot requested at current black-boot uptime695.23s -> logo/console. No diagnostic TCON accesses or HDMI disconnections in either recovery attempt. The delayed request missed the238.07s target because it had already elapsed.

This supports investigating elapsed time but confounds it with cumulative reset/shutdown/reinitialization count. It does not establish a minimum delay, spontaneous recovery during idle, a reliable delay fix, or exclusion of retained electrical state. Earlier independent delayed SECOND reboot recovered at238.07s, so a third reset is not universally necessary either. Next: independent fresh cold-trigger lineages comparing second warm reboot at~55s versus238.07s, both at the same reset count, matched cold-session dwell and verified HDMI service state, with HDMI untouched and no diagnostic TCON accesses. Pre-arm timed commands after first reboot/black confirmation while target is in future, report missed windows explicitly, and record visual state near reboot. Alternate/randomize order and repeat both arms before attributing causality.
