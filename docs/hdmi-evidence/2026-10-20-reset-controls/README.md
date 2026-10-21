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

Linux was then powered off normally for an independently cold-started abrupt
trial. That comparison is pending. Full raw capture and Linux collectors
remain local under `build/hdmi-reset-controls-2026-10-20/`. Automatic warm
capture recovery remains unproven; GP6 and all recovery/shutdown guards stay
intact. Do not infer an abrupt-reset result from the orderly result.
