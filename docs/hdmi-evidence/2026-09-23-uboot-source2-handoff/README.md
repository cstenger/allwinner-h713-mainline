# U-Boot source-2 preselection and Linux handoff, 2026-09-23

After a physical power cycle, the dedicated-trace U-Boot initialized the
authenticated board-B MIPS firmware for project `0x34`. Its live channel table
reported channel 0, PID `0x8b8f275c`. One direct
`THal_Vp_SetSource(2)` call through `commcall eaf13de5` returned in about
1 ms with `nret=0`. The guarded trace reported callback `0x5102`, worker
`0x5203`, event 0, new source 2, previous source 0, and queue result zero.
The source transition and CPU_COMM return both completed in U-Boot on this
same firmware and bootloader image.

The one-time diagnostic FIT `h713-hdmi-trace-page-0131.fit` then booted Linux
6.18.38 #1 built September 23 09:41:06 PDT. FIT kernel and DTB hashes
verified, TVCAP was retained, and the trace page was reserved `no-map`.
Before any modules loaded, Linux read the same source-2 trace state with both
canaries intact. The matching receiver power, EDID-clock, receiver-init,
and CPU_COMM modules loaded; the trace remained readable. The full
`hy310-hdmird-callback --no-src --no-socket` initialization completed every
pre-source RPC, and the MIPS debug shell answered `cmds` with 917 bytes.
No Linux `SetSource` call was made on this boot.

After the no-source initialization, the trace's event/new fields were
overwritten by unrelated event 6/new 1 while callback `0x5102` and worker
`0x5203` remained. Consequently the trace proves the source-2 transition
completed before Linux and that Linux remained responsive through full
initialization; it does **not** independently prove the source object's
private current-source field after `THal_Vp_Init`.

The planned ten-second SCP HPD/EDID trial stopped at its prerequisite check,
before asserting HPD: the private 0131 FIT lacked the
`h713-edid-clock-hold` device-tree node. `h713-edid-clock.ko` loaded but
did not bind or hold the EDID clock/reset. HDMI patch 0132 adds that bench
node. A corrected one-time FIT with the **same kernel hash** and a new DTB
was built as ignored `build/out/h713-hdmi-trace-page-edid-0132.fit`, SHA256
`7c3e8258b0b3436880f50c01d82f545c0ab40fd59d9d667eb4a3043dc0c12f1e`.
The target copy's hash matched. Its DTB has the trace reservation plus
`clocks = <&r_ccu CLK_R_EDID>` and `resets = <&r_ccu RST_R_EDID>`.
It has not yet been booted. No HPD/EDID signal window ran in this control.

The adjacent logs are CR-normalized copies of the original captures in
ignored `build/`. The installed kernel and persistent U-Boot environment
were not changed by this handoff trial.
