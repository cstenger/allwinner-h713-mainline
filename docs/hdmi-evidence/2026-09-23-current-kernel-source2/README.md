# Current-code diagnostic kernel and source-2 control, 2026-09-23

The target's recovered default kernel was `Linux 6.18.38 #1 SMP Tue Sep 22
22:33:01 PDT 2026`, with normal boot arguments and no TVCAP retention DT
property. The HDMI branch merged the current `h713-display-video-path` code.
Its HDMI kernel patches were renumbered 0125–0129 after mainline's MPEG-2
0123–0124; diagnostic patch 0130 added `allwinner,keep-tvcap-on` to the
QZ713DF_A1 DTB used by this target. All six patches applied to the latest
mainline kernel tree with zero fuzz. The isolated build produced FIT SHA256
`d0edd890f93bbc91a3316a71815c26f8e68ad38808dba2efe21f82598a64f088`.
The staged target copy matched that hash. Nothing was written to `boot_a` or
the persistent U-Boot environment.

A one-time boot of that FIT reported `Linux 6.18.38 #1 SMP Wed Sep 23 01:01:04
PDT 2026`, `TVCAP domain retained from boot`, and the volatile AFBD initcall
blacklist. The guarded MIPS trace passed its patch checks; the firmware shell
returned its 917-byte `cmds` list. The matching CPU_COMM module loaded and a
read-only `GetSource` returned 0 in 74,960 us. The matching power, EDID-clock,
and safe Synopsys receiver modules loaded. With `--no-src`, the callback-aware
daemon completed its full pre-source RPC sequence and exited normally.

The GPU connector stayed disconnected and HPD/EDID were untouched. A bounded
`--src 2` control repeated the same pre-source sequence and then entered
`SetSource(2)`. The last MIPS trace sample recorded handler entry and source
callback marker `0x5101`, event 0, new source 2, old source 0, at target uptime
`269.237456`. It did not sample `0x5102` or a new worker stage. Serial then
reported `systemd[1]: Caught <SEGV> from PID -1951793152` and, at
`269.677056`, CPU_COMM's no-RETURN message for session `0x2c`. The SSH sessions
closed and subsequent SSH timed out; a five-second passive UART listen was
silent. The 30-second serial capture did not show a kernel panic. The owner
power-cycled the target, and the normal September 22 #1 kernel returned.

This shows the failure is not exclusive to requested source 3, and the source
2 test needed no live HDMI signal. It does **not** establish the cause. An
offline audit found the trace mailbox at CPU_COMM shared offset `+0x40000`
lies inside the SMM allocator region, which starts at `+0x2ccf0` in
`cpu_comm.h`. The allocator's data area starts around `+0x32000`, so the
mailbox could overwrite an allocation. Whether that range was actually in use
in these runs is unmeasured. The source-2 trace and the earlier traced
source-3 crashes are therefore confounded; their PID 1 fault cannot be
attributed to the requested source or queue code alone. Earlier untraced
source-3 stalls still require explanation. The trace mailbox must move to a
verified non-IPC location before another instrumented source test.

Files: `uboot-trace.log` and `boot.log` record the one-time boot;
`no-source.log` records the successful baseline; `source2-daemon.log`,
`source2-trace.log`, and `source2-serial.log` record the bounded control.
