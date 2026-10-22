# Locate TVFE OFF during boot — prepared October 21, 2026

**Status: first RAM-kernel stage run; TVFE OFF localized to genpd provider
sync-state.** See [live results](hdmi-evidence/2026-10-21-tvfe-boot-trace-live/README.md).
Board ended in orderly poweroff; no catcher is armed. The optional U-Boot
proper remains uninstalled. The following is the pre-run design.

The [preceding diagnostic](hdmi-evidence/2026-10-21-warm-prelogo-ppu/README.md)
found TVFE ON at a warm prompt after one logo invocation, but OFF in Linux.
It did not prove a Linux callback caused the transition. The next diagnostic
separates U-Boot handoff, early Linux, PPU probe/init and runtime callbacks.
DSP versions/retention and HDMI recovery remain outside this experiment.

## Prepared candidate

Directory: `build/hdmi-tvfe-boot-trace-2026-10-21/candidate/`.
Recorded [preparation evidence](hdmi-evidence/2026-10-21-tvfe-boot-trace-preparation/README.md).

| Artifact | Size | SHA-256 |
| --- | --- | --- |
| `artifacts/kernel.fit` | 7,747,368 bytes | `54a691f727e3b405540ea806f11afe5da6178109adb3747094b55ea4f12fbf7e` |
| `artifacts/board.dtb` | 34,666 bytes | `4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940` |
| `artifacts/proper.itb` (optional second stage) | 959,793 bytes | `171ed608bb7e4d2d97f0a2495160937bc1b53e3711ac370673709af6d1bfc074` |

The exact production kernel base is
`build/linux-6.18.38-edffad3c91a035b25a5c2a7df05ef63af488d7e89c286a29c7efa9aaba677efc/`:
its Image matches production `Image.gz` after decompression, its UTS_VERSION
matches October 16 15:44:49, and its DTB matches the live candidate's hash.
The older `da2bc49…` tree in historical handoffs has identical PPU source but
an older Image; it is not the diagnostic build base.

The U-Boot base is the installed reset-controls build's source and object
trees at `build/hdmi-reset-controls-2026-10-20/{src,obj}`. Independent copies
were patched; production sources and `build/out` were not modified. Compiler
is clang 23.1.3, versus production kernel clang 23.1.1. Kernel release remains
`6.18.38`, the complete `Module.symvers` is unchanged, and the production DTB
is copied without edits. This is ABI/build evidence, not runtime qualification.

## Observation points

All samples emit `H713 TVFE v1 stage=... gate=... state=...`. They read the
R_CCU gate/reset word first. PPU reads occur only when both b0 and b16 are
set. Closed/half-open buses emit `state=skipped`, never guessed domain values.
`state=begin` precedes the two status reads, then `state=sample` records them.
Snapshots are sequential, not atomic. Additional UART output changes timing.

| Stage | Scope |
| --- | --- |
| `uboot_final_entry` | entry to `bootm_final`, before the normal kernel announcement |
| `uboot_before_quiesce` / `uboot_after_quiesce` | bracket `board_quiesce_devices()` |
| `uboot_before_dm_remove` / `uboot_after_dm_remove` | bracket device removal, before ARM cache/MMU cleanup |
| `linux_early_initcall` | early initcall, before the PPU platform driver's device initcall |
| `ppu_probe_entry` | first instruction added at PPU probe entry |
| `ppu_before_reset_deassert` / `ppu_after_reset_deassert` | bracket the existing PPU bus reset release |
| `ppu_before_clock_enable` / `ppu_after_clock_enable` | bracket the existing PPU bus clock enable |
| `domain_init_before` / `domain_init_after_wait` / `domain_init_after_on_delay` / `domain_init_after_off_delay` | bracket each of the existing three init writes, for all five physical domains; preceding metadata names domain and hardware ID |
| `ppu_probe_complete` | after registering the genpd provider |
| `power_cmd_before` / `power_cmd_after` | bracket each existing domain power command; metadata records domain and requested state |

The TVFE `power_off` callback additionally prints its return address and
`dump_stack()` **before** entering the existing power transition. This is an
informational stack dump, not a warning/oops. Original hardware writes,
polling, errors and domain policy remain unchanged. No new power command is
introduced. No DSP, lock, receiver or SCP SRAM access is added.

Kernel instrumentation is opt-in with **`h713_tvfe_trace=1`** and checks the
H713 machine compatible before mapping its two diagnostic windows. Without
that flag it creates no diagnostic mappings or MMIO reads. Maps remain for
the boot lifetime so later callbacks can be sampled. If either map fails,
the trace disables itself and logs failure; normal driver behavior continues.

U-Boot probes are compiled only for H713 proper, excluding SPL and host tools.
The optional proper does not open bus-r-ppu itself. Post-device-removal UART
availability has not been qualified; a missing final marker is missing data.
There is deliberately no `printf` added after ARM cache/MMU cleanup. The
interval from the last U-Boot sample to Linux early-init remains a bounded
interval if no intervening sample can be obtained safely.

## First live run: RAM kernel, installed U-Boot

This stage needs **no boot-firmware replacement or saved environment change**.
Do not install the optional proper merely to get the first kernel trace.

1. With host device access enabled, arm the cold catcher and verify its
   actual `OPEN /dev/ttyUSB0` event before asking the operator to reconnect.
   Use a new output directory. Catch one SPL, record GP6 zero and cold
   preboot census, then permit the normal production cold startup.
2. Record a fresh boot ID, production health/census, DSP `0/0` followed by
   verified `1/1`, and both domains ON. Stage only `artifacts/kernel.fit`
   at board `/root/hdmi-tvfe-boot-trace-2026-10-21/kernel.fit` using SSH/SCP.
   Verify its board SHA-256 against the table. Keep the normal FAT FIT and
   startup script unchanged. Staging this file is future live work, not done.
3. Arm the warm catcher, verify its OPEN event and sole UART ownership, then
   perform an orderly reboot guarded by that fresh production boot ID and
   normal ownership. Stop at the next prompt before the logo. Repeat the
   reviewed `warm-retention-uboot.py --open-ppu-bus` diagnostic with the saved
   bootcmd. It opens only the PPU bus and stops; require both domains ON.
4. Run the production warm-logo step **once**: PB5 off, then
   `h713_disp auto 0x34 logo`, then PB5 restored after a recorded successful
   completion. Capture continuously, using at least **20 seconds** of silence
   tolerance or a fixed deadline. Do not combine a three-second timeout with
   the logo's three-second panel hold. On missing acknowledgment or failure,
   stop; never rerun initialization to fill a logging gap.
5. After reviewing that single logo and the prompt, invoke:

   ```sh
   python3 tools/serial/run-tvfe-boot-trace.py \
     --port /dev/ttyUSB0 \
     --prepared build/hdmi-tvfe-boot-trace-2026-10-21/candidate \
     --expected-bootcmd PATH/TO/THIS-CYCLE-bootcmd.txt \
     --output build/hdmi-tvfe-boot-trace-2026-10-21/live-kernel-01 \
     --post-logo-ack one-reviewed-warm-logo
   ```

   The runner refuses unless the local FIT matches the manifest, build and
   symbol-version checks passed, bootcmd matches, GP6 is `48444d49`, MIPS is
   parked, and both domains read ON. It loads the fixed rootfs path into RAM
   with `ext4load`, checks exact filesize and RAM CRC32, then sets only volatile
   placement/bootargs. `bootm` performs FIT hash verification. It re-samples
   both domains immediately before boot and never runs the logo or bootcmd.

   Bootargs preserve the recorded production root and ignore-unused flags,
   add `h713_tvfe_trace=1 loglevel=7`, and replace `panic=5` with **`panic=0`**
   to prevent an automatic reboot after a failed diagnostic. No `initcall_debug`
   or broad function tracing is added. The current normal startup builder pins
   the production FIT size; **do not substitute this FIT into that builder**.

   UART capture runs for a fixed 60 seconds and does not end for silence.
   Unexpected SPL or UART loss raises an error without reset/retry. Do not
   start another UART reader during capture. The acknowledgment flag records
   the agent/operator's reviewed logo observation; it cannot independently
   prove logo completion.
6. Verify a new Linux boot ID, trace flag, absent HDMI handoff, parked MIPS,
   inactive HDMI services and no experimental h713 modules. Save the current
   boot journal by exact boot ID and collect the existing read-only census.
   Normal Wi-Fi modules still require live ABI/health verification. Preserve
   failure state if SSH is unavailable; do not retry the logo or reset.
7. Analyze the one-boot UART log:

   ```sh
   python3 tools/hdmi/analyze-tvfe-boot-trace.py PATH/TO/serial.log
   ```

   Missing/skipped phases and unfinished BEGIN markers stay explicit. The
   analyzer requires all kernel boundary samples and five occurrences of
   each domain-init phase for complete kernel coverage. It reports observed
   adjacent ON-to-OFF intervals, not an inferred writer or DSP result.
8. End with an orderly poweroff, fresh-ID/owner checks and UART completion
   evidence. Do not unload pinned diagnostic owners, clear GP6, use GP7,
   issue DSP requests or start source3 to test a hypothesis.

## Reading the result and optional second stage

| First OFF observation | Interpretation / next action |
| --- | --- |
| Already OFF at `linux_early_initcall` | Transition precedes the PPU driver's probe; inspect U-Boot cleanup/firmware handoff and earlier kernel code. This does not identify reset itself. |
| ON at early init, OFF at `ppu_probe_entry` | Narrow to the early-init-to-driver interval; add intermediate initcall/provider observations offline. |
| Immediately after reset or clock operation | That operation's interval is implicated; review parent-clock/reset behavior before changing policy. |
| Immediately after a named domain init write | Identify which domain/write via the adjacent metadata; review controller semantics. |
| Bracketed by an explicit TVFE OFF command | The callback/stack identifies the software power-off path. Preserve the caller and diagnose why it requested OFF. |
| OFF with no captured bracket or missing markers | Keep the interval unresolved. Missing data does not prove no callback ran. |
| Stays ON | Compare instrumentation/timing and the bus-open intervention with the prior controls. Do not call this a recovery pass. |

The optional `proper.itb` is built for the second-stage U-Boot boundaries,
but **has no installation package or validated new rollback extent yet**.
If needed, first prepare/review a package based on the exact currently
installed **1877-sector** extent, verify backup/readback and preserve both
environment locations. A raw ITB or a combined SPL+proper output is not a
whole-image installation recipe. Do not replace SPL/BL31/DTB as an incidental
trace change. The prepared optional proper carries the existing guards and
normal logo path plus the new read-only bootm probes. No chainload procedure
has been qualified. Analyze that run with `--require-uboot`.

## Offline verification

`prepare-tvfe-boot-trace.py` refuses existing/overlapping outputs and mismatched
base source/build pins; it copies files independently with reflink support,
applies patches with zero fuzz, builds the kernel/modules and U-Boot, and writes
hashes and commands to its manifest. Native tests execute the actual sample
helpers with fake MMIO to check cold/half-open gates, opt-in and machine checks.
Runner tests cover invalid warm states, bootcmd/CRC refusal and capture through
long silence. Analyzer tests reject malformed, unsafe and mixed-boot evidence.

**Passed:** both real builds; 13 diagnostic tests; 19 warm-retention regression
tests; FIT extraction/decompression matches the built kernel; unchanged DTB
and `Module.symvers`; no patch whitespace errors. U-Boot's existing-source
compiler warnings are recorded in its build log; none originates in the new
trace header or bootm probe code. Hardware read safety and trace completeness
remain unqualified until the controlled live run.
