# Matched no-HDMI-disconnect control, 2026-10-17

Goal: reproduce black via genuine cold HDMI startup followed by warm reboot; then enable/restore the same TCON checkerboard and warm reboot WITHOUT disconnecting HDMI at either end.

HDMI must remain connected at both ends throughout reproduction and the control. Serial/other USB removed only during physical cold power-off to prevent back-power. GP6 launch guard is not cleared in software.

Initial working warm boot: a25f7cd1-dc99-4737-aa65-52805c33f1ec, GP6 48444d49, no HDMI chosen handoff, capture/signal inactive.

Compare pattern duration and black-state dwell against the preceding PC-end trial; record actual durations. Capture raw UART and host timestamps; target wall clock is incorrect. Prior trials logged root filesystem orphan-file errors at shutdown; preserve any recurrence without making filesystem changes in this display test.

Current phase: setup before physical cold cycle. No HDMI disconnection authorized or intended.

Timing reference from prior PC-end trial host timestamp log: checkerboard readback complete 17:04:45.330906 PDT; restore began 17:06:38.954576 (113.624 s later); restore complete 17:06:39.012164; reboot marker 17:06:50.186481 (11.174 s later). Planned control: approximately 114 s pattern hold, then restore/readback, approximately 11 s delay to reboot; record actual times. Black-state boot dwell will be recorded separately rather than assumed identical.

Cold attempt 1: operator reports logo/console after physical cold cycle, HDMI connected throughout. U-Boot source-3 transition and cold startup handoff verified; Linux handoff, GP6 and active capture/signal verified in cold1-verification.txt. Trigger warm reboot initiated at 2026-10-17T17:11:17.354024-07:00.

Trigger attempt 1 warm reboot: serial confirms terminal MIPS park, ordered panel power-down, restart, warm branch, FIFO reset 2 -> 0, and boot logo commit. Awaiting operator visual verdict before pattern control. HDMI remains untouched.

Operator report received 2026-10-17T17:13:05.703809-07:00: trigger attempt 1 is lit but black, HDMI connected at both ends. Authorized 114-second TCON checkerboard hold, restore and warm reboot with HDMI never disconnected.

Control executed on black boot 2cdaca84-d147-40bc-a8a0-d6cad4c9f96b. Pattern start uptime 112.99s; restore start 227.00s; reboot marker 238.07s. Pattern hold 114.01s. Restore/register checks succeeded; warm reboot reached Linux serial login with warm branch, FIFO reset and logo commit. HDMI untouched throughout per operator instruction; awaiting visual verdict. Serial capture remains running.

## Result: GOOD with HDMI connected throughout

Operator report received 2026-10-17T17:17:26.122149-07:00: logo/console returned after the control reboot; checkerboard was never visible; HDMI remained plugged in at both ends throughout.

This is a successful recovery from operator-confirmed black WITHOUT HDMI interruption: checkerboard enabled and readback verified, held 114.01s, normal registers restored and verified, then warm rebooted. Source connection interruption is therefore not necessary for this recovery. Earlier unplug/replug successes are confounded by the shared pattern/restore sequence, elapsed time and reboot. This result does not establish whether the pattern transition, particular TCON writes, idle duration, repeat bring-up or a combination caused recovery, and does not by itself exclude electrical retention/back-power as an underlying mechanism. The next useful control is a black-state, no-pattern/no-HDMI-change trial with comparable idle time followed by warm reboot. If it remains black, repeat the timed pattern/restore/reboot sequence on that same retained black state.

Differences from PC-end trial: control pattern start uptime 112.99s versus PC-end pattern start approximately 149s (PC-end baseline 138.24s, restore start 262.37s, pattern hold approximately 113.6s); dwell before pattern was not exactly matched. Preserve this limitation when interpreting one successful control.

Subsequent reboot-only control also recovered a confirmed black state at matched reboot age238.07s, without diagnostic TCON accesses or HDMI interruption. See `../2026-10-17-reboot-only-control/README.md`. Waiting, repeated shutdown/initialization or their combination remain unresolved; neither cable removal nor diagnostic pattern writes are established recovery causes.
