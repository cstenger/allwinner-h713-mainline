# Dedicated MIPS trace page and bounded source-2 control, 2026-09-23

This control repeated the no-signal source-2 call with the trace mailbox on a
dedicated DRAM page at ARM physical `0x4d980000` (MIPS uncached
`0xad980000`). Diagnostic Linux reserved `0x4d980000..0x4d980fff` as a
4 KiB `no-map` region. The U-Boot trace installer authenticated the exact
board-B firmware, checked its patch sites, cleared the page, and installed
the trace. The Linux reader checked 22 relocated instructions, mailbox magic,
and canaries at page offsets `+0x80` and `+0xffc`.

After GPT and live-hash checks, only 1,798 sectors at the established
U-Boot-proper LBA `0x49ac00` were updated. Full read-back of those sectors
matched the padded candidate SHA256
`935a1b33c59f501cab498232d24108c548d941256958366792d29a9a30f0d526`.
The SPL hash remained
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
The previous U-Boot-proper region was backed up read-only under ignored
`build/uboot-proper-before-dedicated-trace.bin`, SHA256
`a43e3efd05fed20cad75d669d49bc44e4d70914441287385d4150acad3167eee`.
The installed kernel and persistent U-Boot environment were not written.

The one-time HDMI FIT (SHA256
`558e256534f63a1d5a53a89b9383034220c8c2691253f7ffecb798855a4a0cee`)
booted Linux 6.18.38 #1 built September 23 09:41:06 PDT and retained TVCAP.
All four matching diagnostic modules loaded, and a no-source daemon run
completed its pre-source sequence. A ten-second guarded baseline watch stayed
stable with both canaries equal to `0x43414e31`, callback `0x5102`, worker
`0x5203`, and VP-init marker `0x7105`. Those stages belong to U-Boot's
earlier source-1 event.

The GPU HDMI connector still reported `disconnected`; HPD and EDID were
unchanged. A single bounded `SetSource(2)` was attempted. The daemon printed
`=== set-source 2 ===`, then its SSH session closed without a result. The
last readable source snapshot at target uptime 147.450306 showed:

| Field | Value | Interpretation |
| --- | --- | --- |
| Page canaries | `0x43414e31 / 0x43414e31` | Both intact |
| Callback | `0x5101` | Source event entered the callback |
| Event / new source | `0 / 2` | Source-2 request observed |
| Worker | `0x5203` | Stale completion from earlier source-1 event |
| VP-init marker | `0x7105` | Intact at the final sample |

The source-2 callback's queue-return marker `0x5102` and a new worker stage
were **not sampled** before the ARM reader lost the connection. The old
worker marker, previous-source word, and queue result must not be attributed
to the new call. At uptime 147.888833 UART logged
`CPUComm_CallEx: no RETURN after 5000 ms (session=0x2b, interrupted)` and
then went silent. The capture contained no PID 1 SIGSEGV, kernel panic, or
Oops. SSH later reported no route to host. This places the last observed
progress inside the source callback but does not prove where execution
stopped during the unsampled interval.

This run removes two earlier trace-memory confounds: the trace was outside
CPU_COMM's SMM heap and the firmware boot-code gap, and both page canaries
and the VP-init word were intact at the final sample. It does not establish
exclusive MIPS runtime ownership of the dedicated page for all time. A
physical power cycle restored SSH and the normal installed Linux 6.18.38 #1
build from September 22 22:33:01 PDT. Read-only verification confirmed the
updated U-Boot-proper sector hash after recovery. No second source-selection
attempt was made. Original captures remain under ignored `build/`; the
adjacent log copies have CR characters and trailing whitespace removed for
readable diffs.
