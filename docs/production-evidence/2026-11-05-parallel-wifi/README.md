# Parallel AIC8800 startup — repeat exposed initial-detection miss

Latest: cold-01 was clean at 13.85 s. Cold-02 required one automatic HPD retry
and reached video at 26.25 s; its no-retry gate failed. Runtime and radio audits
pass. This failure is retained and first-advertisement reliability needs
investigation before further optimization. [Repeat result](cold-02-result.json).

Chris authorized preparation, installation and cold-boot comparison of independent
Wi-Fi/Bluetooth startup, preserving dependencies. Baseline is zero-countdown
boot 3636858d-5ab9-49a8-9445-5e3ae5bd4048, with completion-aware MIPS checks,
parallel capture preparation and reject-trace-v1 unchanged. Baseline modules-load
lasted 2.858901 s and video service was active at Linux 16.147241 s. Its first
SPL → kernel-entry UART message interval was 9.729194 s.

## Installed scope

Six exact configuration/link changes:

- /etc/modules-load.d/aic8800.conf now documents explicit ownership and contains
  no module load requests. Other global module lists are retained.
- /etc/modprobe.d/h713-aic8800-startup.conf blacklists the three AIC module aliases
  to suppress udev/SDIO coldplug; explicit modprobe remains permitted.
- h713-aic8800-modules.service runs after basic/sysinit and global modules-load,
  sequentially loads BSP → Wi-Fi → BT low-power support, then checks wlan0 exists.
  It is oneshot/RemainAfterExit, enabled under multi-user.target, with 30-second
  startup timeout and no module-unloading ExecStop.
- Hotspot and BT-attach units now Require/After this owner, retaining their existing
  global-loader ordering, commands, hotspot restart policy, BT priming/retry logic
  and bounded stop timeout. The owner also orders itself before both clients.

The BSP owns shared chip power and exports dependencies used by Wi-Fi and BT.
No kernel/module/firmware binary, radio options, hotspot credentials, HDMI unit,
backend manifest, boot environment, recovery or teardown program was changed.
The rootfs builder emits the same payloads, with updated build checks.

## Validation before installation

Source inspection found BSP's broad SDIO class alias and Wi-Fi's SDIO ID aliases;
both would allow early udev loading if only the global module list were changed.
Board modprobe dependency-report dry runs proved both aliases resolved under the
original configuration (positive control) and resolve to no load actions under
the candidate blacklist. Explicit BSP/Wi-Fi/BT requests remain valid, with BSP
first. Installed effective policy also suppresses aliases while retaining original
Wi-Fi default_ccode=US and aicwf_dbg_level=0x1 options.
[Structured alias checks](alias-policy-result.json).

Four host tests pass: actual payload sequencing/dependency/shutdown contract,
preview/install/explicit rollback, failures after each of all six writes restoring
all originals, and foreign baseline/payload refusal. Shell syntax checks pass.
Native board systemd verification of AIC, hotspot, BT and existing prepare/capture
units passes. The existing two HDMI ordering tests also pass; their first native
host attempt hit sandbox credential-socket restrictions and passed outside that
sandbox without any service startup. Radio observer compilation and synthetic
failure checks verify every added radio/global-loader failure invalidates the run.

The installer pins exact three original file hashes and absence of the three new
objects, validates model/eMMC/boot, refuses competing unit drop-ins or duplicate
global module requests, serializes with the existing startup-state directory lock,
backs up originals, performs checked atomic writes/new symlink creation, reads back
all targets and restores partial writes. No daemon/service/module operation is
inside the transaction. Rollback restores the original three files and removes
new configuration, unit and enablement link; it does not unload active modules.

## Installation

Exact package/manifest checks passed. Pre-install expanded RC audit passed 74 file
pins. Installation and daemon-reload completed; native installed systemd graph
verification and the post-install 77-file RC/kernel/package/storage/raw-boot/bundle
audit passed. Live HDMI/hotspot/BT service restart counts remained zero, HCI0 was
UP RUNNING and rejected-copy counter stayed zero. The new owner remains inactive
in this already-booted session; no module or service was restarted to manufacture
a startup result. [Installation receipt](installation-receipt.json),
[post-install identity audit](postinstall-audit.json).

On-board committed backup:
/var/lib/h713-hdmi-startup/parallel-wifi-16a62767967c4d379ff642d7f1ad64fd.
The host retains its complete archive and original files.

## Cold test armed

Passive UART and the same five-minute observer are armed for cold-01, with radio
checks added: AIC owner, hotspot, BT attach and global module loader must stay
successful/active with no restarts, alongside all eight HDMI services. Save module
loader duration, owner/HDMI overlap, IPC/adoption/HDOK, source/PCM/copy-guard counters,
then run the new package/audit-after.py and inspect HCI/hotspot readiness. Compare
Linux video active time to 16.147241 s and first-SPL timing to the zero-delay baseline.
Potential savings are overlap to be measured, not an assumed 2.86-second gain.

The first cold boot completed successfully; see the measured result below. Raw package, rollback, exact
configuration hashes, dependency records and UART are under
local/recovery/2026-11-05-parallel-wifi/. Historical guarded-copy evidence remains
preserved; no guard relaxation or further boot-environment change occurred.

## First cold-boot result

Boot `071a94ba-4847-4beb-9cc1-fd0cfaba47a7` passed the fixed five-minute
observation, all twelve tracked service states/restart checks, final radio
readiness checks and 77-file RC/kernel/package/storage/raw-boot/bundle audit.
Chris confirmed the HDMI desktop returned after >1 minute with power and UART
removed, and kept the same desktop showing.
[Structured cold result](cold-01-result.json).

| Milestone | Previous zero-countdown boot | Parallel AIC boot |
| --- | ---: | ---: |
| Global modules-load duration | 2.858901 s | 0.256609 s |
| HDMI prepare command starts, Linux uptime | 7.893449 s | 4.633472 s |
| Capture ready, Linux uptime | 14.418867 s | 12.136396 s |
| Video service active, Linux uptime | 16.147241 s | 13.850639 s |
| First SPL → kernel-entry UART message | 9.729194 s | 9.742866 s |

Video service readiness improved **2.296602 seconds**. Firmware timing remains
consistent with the installed zero countdown. This is one comparison, not a
repeated reliability series or direct power-switch-to-first-visible-pixel timing.

The radio service activates at Linux 4.621676 s and becomes active at 8.200645 s,
lasting 3.578969 s. HDMI prepare's unit activation overlaps it for 3.557498 s.
The first aicbsp_init kernel message is 4.848472 s, after owner activation and
after global modules-load completed at 3.952150 s. Thus the AIC work was moved
out of the early global barrier. All four owner ExecStart commands succeeded;
hotspot and BT start after owner success. The initial observer overlap field
used ExecMainStart, which reflects only the last command in a multi-command
oneshot. That raw artifact is preserved; the receipt uses native unit activation
bounds (InactiveExit → ActiveEnter). The collector was corrected for future
runs, and all five qualification-collector tests pass. No board change was
needed for this host-side accounting correction.
[Native activation measurement](radio-activation-timing.json).

Hotspot remained active with zero restarts and supported the SSH connection;
HCI0 reports UP RUNNING. Both SDIO functions bind their expected aicwf_sdio and
aicbsp_sdio drivers, all three modules are loaded, both consumer units retain
Requires/After owner dependencies, and alias suppression remains effective.
[Final radio readiness](radio-runtime-result.json).

Five MIPS completion checks pass in 0.428–0.450 s. Prepared-backend adoption,
user overlap (3.228441 s), HDOK acknowledgement and zero GP7 pass. Both PCMs
remain RUNNING, source locked 720p, no HPD re-advertisement or stream restart.
Window ends at Linux 313.850639 s; final sample 314.11 s, sampled 59.709 fps,
zero rejected copies, audio xruns, bad guards or invalid pairs. Loaded capture
trace build-ID matches the baseline. Prior shutdown restored signal ownership,
22 DSP and 15 TVFE words, parked/removed the receiver and retained capture-before-
user-manager stop ordering.

Host Wi-Fi needed saved-profile reactivation, as in earlier tests; first live
sample 55.32 s. Fixed deadline retained and boot-wide kernel logs/cumulative
counters cover earlier rejection outcomes. No board service/network recovery
was performed. The board is left running with parallel radio startup, both
prior startup optimizations, bootdelay=0 and reject-trace-v1. Passive UART and
host observer were closed after collection. Historical rejection evidence is
preserved and no guard changed.

## Cold-02 repeat: initial detection failed, automatic recovery succeeded

After the user reported the board off, host recorder/observer were rearmed for
a repeat without any configuration change. Chris confirmed another >1-minute
power/UART disconnect and desktop return with the same desktop maintained.
Boot `2f6e62e1-b588-43f4-9e12-af587acf5fd5` is retained as **INVALID matched
observation: HPD re-advertisement**, not relabeled as a clean boot.
[Structured repeat result](cold-02-result.json).

Global module loading remains short at 0.270905 s. AIC owner activates at
4.722218 s and becomes active 8.289732 s, with 3.557046 s of overlap with HDMI
prepare. Kernel BSP initialization follows owner activation and hotspot/BT
start after owner success. Capture ready at 12.221815 s; five IPC checks,
prepared adoption, user overlap and HDOK/zero GP7 pass. These are initialization
checks, not a waiver of the first-detection gate.

| Event | Cold-01 clean run | Cold-02 repeat |
| --- | ---: | ---: |
| EDID/HPD-ready kernel log | 12.432510 s | 12.511234 s |
| HPD retry requested | None | 22.817321 s |
| Two-second HPD hold completes | None | 24.947778 s |
| Source locked 720p | 13.798927 s | 26.202287 s |
| Video service active | 13.850639 s | 26.251073 s |

One automatic retry followed the existing ten-second no-source threshold and
two-second HPD hold. No manual HPD pulse, reseat, module reload or service restart
was performed. No further retry or interruption occurred. A similar initial
miss occurred before all startup optimizations (boot 60f461e3-b6a5-461c-af32-
9d9bcfceb1fe, readiness 22.958 s, lock 36.663 s after automatic retry). This
history establishes a pre-existing issue; it does not rule out a changed
probability/phase with earlier startup. Cause remains unresolved.

The five-minute post-video window ends at Linux 326.251073 s; last sample
326.49 s, 59.710 fps, zero rejected frames, audio xruns, bad guards, invalid
pairs or service restarts. Source stays locked and both PCMs RUNNING. The full
77-file/kernel/package/storage/raw-boot/bundle RC audit passes; final Wi-Fi/BT
readiness, alias policy and dependencies pass; capture trace build-ID unchanged.
The host connected normally, with first live sample 34.83 s. The previous boot's
journal has no recorded shutdown sequence, so prior orderly restoration cannot
be qualified for this transition; no cause for that missing evidence is inferred.

The board is left running unchanged after automatic recovery. Host observer and
passive UART are closed. Further optimization is held pending investigation of
first-advertisement reliability. The existing copy-guard rejection history is
separate and remains preserved. No automatic extra reboot or configuration
rollback was performed to replace this failed observation with a passing one.

## Rootfs form of the experiment (not in the default build)

`rootfs-parallel-aic.patch` is the same change written into
`tools/rootfs/customize.sh` and `build.sh`: an explicit
`h713-aic8800-modules.service` replaces global `modules-load.d` loading, with
coldplug blacklisted. The board went back to global loading (control B) during
the first-advert investigation, so the default rootfs build keeps global
loading. To build the parallel form, `git apply` this patch.
