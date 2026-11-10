# Expanded reset controls — October 20, 2026

The [access audit and protocol](../../hdmi-reset-controls-2026-10-20.md)
define this proper-only instrumentation. Source commit `ed5b1e1` adds 22
CCU/SCP control reads, with no DSP protocol, receiver MMIO or SCP SRAM access.

## Installation and cold control

The exact 1877-sector candidate was installed at LBA `0x49ac00`. Full 2-MiB
primary-region readback matched; SPL, configured/active environment and rescue
regions also matched. BL31 and the U-Boot DTB are unchanged. Exact rollback
is under `/root/hdmi-reset-controls-2026-10-20/` on the board and in the local
build directory. The previous 1867-sector rollback alone is insufficient for
this expanded extent. See [installation.json](installation.json),
[install output](install.txt), and [preparation.json](preparation.json).

After an orderly shutdown and an operator-confirmed fully disconnected cold
cycle, boot `679a3e47-b729-40e1-a05c-d3c4b5bffd79` produced four complete
adjacent control vectors: proper-preboot, first pre-workspace, post-logo and
second pre-workspace. The [cold trace](cold.serial.log) includes its immediate
UART boot-ID check. The first Linux collector overlapped startup; a later
settled collector and [health check](cold-health.txt) established active
capture/signal/speaker, both PCMs RUNNING, DSP failure N, zero capture XRUNs,
clean root and successful growfs. No new audible/visual qualification.

## Orderly-reset result

One boot-ID/service/DSP-guarded normal reboot completed signal restore, 22
DSP and 15 TVFE restores, terminal parking and receiver removal. New boot
`4f75d15b-014e-4c69-8005-539d2dd59fc4` has no HDMI handoff and all three
HDMI services skipped. UART and SSH boot IDs agree. Root remains clean and
growfs succeeds. See [teardown and health](clean-teardown-and-health.txt),
[raw warm trace](clean-reset.serial.log) and [parsed controls](clean-controls.json).

All 22 control words at proper-preboot match the cold baseline: SCP reset
is zero; demod, shared capture and TVCAP bus controls are zero. As in the
cold control, logo initialization then changes the TVCAP TCD3/DMA/shared bus,
HDMI-audio and bus/reset controls. The zero programmed bus words do not prove
rails discharged, DSP patch erased or a safe receiver access window.

## Abrupt-reset result and comparison

After a separate operator-confirmed disconnected cold cycle, boot
`eb7f026a-3363-4035-b974-025d504a8504` passed active units, both PCMs RUNNING,
DSP failure N, zero capture XRUNs and clean root. Four complete cold vectors
are retained in [abrupt-cold.serial.log](abrupt-cold.serial.log).

The [guarded trigger](abrupt-reset-trigger.py.txt) synced filesystem writes,
rechecked boot ID/services/PCMs/DSP failure, and drained its complete UART
marker before SysRq-b. Reset occurred at **61.307404 seconds**. The
[trigger interval](abrupt-trigger-interval.serial.log) contains the marker
and `sysrq: Resetting`, with no normal teardown sequence. This is an
emergency-reset test, not actual watchdog expiry or a hung-kernel injection.

New Linux boot `a02e888b-4f77-4b65-a95d-bafefa1705c5` was captured directly in
UART and SSH before recording ended. It reports parked MIPS, no handoff and
all three HDMI units skipped. Ext4 reports recovery complete, root clean and
growfs success; both environment regions, SPL, rescue and primary image still
match. Journald replaced system/user journals as corrupted or uncleanly shut
down; this is not evidence of lossless logging or an offline filesystem check.
See [post-reset health](abrupt-after-health.txt) and [raw trace](abrupt-reset.serial.log).

[Domain comparison](domain-comparison.json) finds **no differences in any of
22 control words** at proper-preboot, pre-workspace or post-logo. The
[original five-field comparison](mips-comparison.json) also matches at all
stages. Both warm traces begin with SCP run/reset zero and the same TVFE/audio
and TVCAP control values as the corresponding cold baseline. The logo then
sets the same TVCAP controls in both. There are no missing control stages.
The analyzers still label hardware recovery `unproven`.

The board remains on that guarded warm boot. Full raw captures and collectors
are local under `build/hdmi-reset-controls-2026-10-20/`; extraction offsets,
hashes and status are in [installation.json](installation.json). The capture
was closed only after both immediate post-reset boot IDs and collectors were
retained. This pair has no usage-limit boot-attribution gap.

## What this permits next

At proper initialization, neither SCP run nor these programmed CCU controls
distinguishes clean teardown from this synced abrupt reset. They do not prove
DSP RAM/patch reset, cleared protocol locks, receiver readiness, SCP SRAM
freshness, power discharge or the responsible reset domain. Earlier SPL/BL31
and initialization effects remain unseparated.

Next review a dedicated pre-logo DSP observation protocol: establish which
power/clock/reset and ownership predicates are sufficient before issuing even
a version read; preserve original controls and refuse inherited ownership or
busy/failure state. Alternatively instrument an existing firmware initialization
read before it overwrites DSP evidence. Neither approach is implemented or
authorized by these control values alone. Do not launch SCP merely to read
receiver state, overwrite retained SRAM, relax DSP versions, clear GP6 or
retry source3. Automatic warm HDMI recovery remains a release blocker.
