# Relocated MIPS trace and bounded source-2 control, 2026-09-23

The projector's original U-Boot proper was backed up read-only to ignored
`build/uboot-proper-before-safe-trace.bin` (4 MiB, SHA256
`d2165e36bd208f95f7a374eed6f965f1b87b35ebca9524743c34a598638ebb0d`).
The SPL was backed up to `build/spl-before-safe-trace.bin` (32 KiB, SHA256
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`).
After GPT identity and live-hash checks, only 1,798 sectors at U-Boot-proper
LBA `0x49ac00` were written. Read-back matched the padded candidate SHA256
`b437d05ef0c638929b4d158fa2c6730789112ddd401141621a15d426d7007ed5`;
the SPL hash was unchanged. The installed kernel and persistent environment
were not written.

The new U-Boot identified itself as a September 23 01:24 build, authenticated
the board-B firmware, verified the comm-trace patch sites, and reported
`CPU_COMM RETURN progress trace installed at 0x4b100e00`. A one-time boot of
the current-code HDMI FIT reported Linux #1 built September 23 01:01, with
TVCAP retained from U-Boot. The Linux trace reader checked 22 relocated words
and mailbox magic, then read an already-completed source-1 transition:
callback `0x5102`, worker `0x5203`, queue result zero. The four matching
diagnostic modules loaded; the first receiver-init insertion omitted its
required `apply=1` option and made no changes, then the explicit insertion
succeeded. A no-source daemon run completed all pre-source RPCs and exited.

The single `SetSource(2)` control was run with the GPU connector disconnected
and HPD/EDID untouched. It completed the pre-source sequence, then its SSH
session closed without a source result. The final guarded snapshots were:

| Target uptime | Callback | Worker | New | `vp_init` |
| --- | --- | --- | --- | --- |
| 193.932837 | `0x5101` | `0x5203` (old) | 2 | `0x7105` |
| 194.029531 | `0x5101` | `0x5203` (old) | 2 | `0x8baa0000` |

The reader did not sample source-2 callback completion or a new worker event.
The worker `0x5203`, queue result zero, and old source zero belonged to the
earlier source-1 transition. `0x8baa0000` is unexpected at mailbox `+0x38`:
the guarded trace's VP-init stores only publish `0x7101..0x7105`. Although the
raw firmware gap is zero and outside the known CPU_COMM heap, these results
do not establish exclusive runtime ownership. Serial logged CPU_COMM's
no-RETURN message at uptime 194.371901, then no further response. There was
no PID 1 SIGSEGV in the capture, unlike the old-mailbox control. SSH timed out
and a serial SysRq help request received no reply. A physical power cycle was
requested. No further source-selection attempt was made.

The log files here are copies of the captured output with CR characters and
trailing whitespace removed for readable diffs. The original captures remain
under the ignored `build/` directory in the isolated HDMI checkout.
