# ALSA bring-up attempt 2: load works; open-callback fix awaits testing

The user physically cold-booted and stopped at U-Boot. The guarded MIPS launch,
current PID, source3 completion, preserved FIT and RAM IRQ correction passed.
`linux-preparation.log` verifies source3/canaries and receiver holds.

## Corrected clock order passed

The clock-order-corrected module8d0586a1... loaded successfully. `kernel-live.log`
was streamed independently before insmod; it records IHB/AudioTop setup, the
inactive-SPDI1 check, private DMA, IRQ registration and ALSA card registration.
`load-result.json` records insmod rc0. This supports the ordering correction;
the exact instruction at the previous hang remains unmeasured.

ALSA card H713HDMI appeared. The board lacked arecord, so the official Debian
trixie arm64 alsa-utils1.2.14-1 package was downloaded and checked against the
official Packages.xz SHA256 (`recorder-package.json`). Only its executable was
staged as `/tmp/h713-linux-return/arecord`; no package was installed on the board.
The runner now accepts `--recorder` for that temporary executable.

Both cold DSP versions0/0 were verified; the exact724-pair stock patch produced
versions1/1 and all22 graph words passed readback. The HDMI tone test did not
start: the host never acquired H713 HDMI IN ELD. `capture-test/1-48000` preserves
the failed acquisition and helper evidence. HPD/EDID cleanup succeeded with
zero mismatches. The user later confirmed reseating PC-to-HDMI1.

## Confirmed ALSA open-callback defect

Ordinary bounded no-link captures returned EIO, while a diagnostic with
external ALSA status polling showed RUNNING, a moving real DMA pointer and
one successful short recording (`pointer-no-link.log`). All clients closed.
This is not reliable recording or HDMI tone verification.

An initial status-bit hypothesis was tested with counters during a driver-only
reload (`reload/`). It was refuted:72 IRQs arrived,72 had the expected bit,
but0 period notifications occurred. Additional counters (`counter-debug/`)
showed70 owned IRQs but0 active-stream handler entries.

The open callback incorrectly used `if (ret)` on the result of
`snd_pcm_hw_constraint_integer`. In the exact kernel this calls
`snd_interval_setinteger`, which returns **1 on successful constraint change**.
ALSA accepts the nonnegative open return, but the driver returned before
assigning capture_stream. Thus IRQ handling had no stream to notify. The fix
checks `ret < 0`, attaches the stream and returns0. The speculative IRQ-status
change and extra pointer reads were removed. Read-only activity/progress
counters remain. The corrected driver builds cleanly with LLVM W=1; its hash
and sources are in `open-fix/build-manifest.json`. It has not been loaded yet.

Driver-only reloads restored all22 graph words before unloading the DSP helper
and ALSA driver, while TVFE/receiver holds and MIPS remained active. The patch
survived these clock-only transitions: both versions were positively reread1/1
each time, without patch replay or MIPS relaunch. These were not recoveries
from a DSP timeout. Do not infer that reloading can clear a hardware fault.

## Restoration timeout and final cleanup

Before loading the confirmed open fix, reverse graph restoration timed out
reading0103 after its saved-value write. `counter-debug/restore-timeout.log`
records completion-clear50108us, status00000120, error-110 and failure latch.
005a/0059 had already been restored and verified;0103's final value and the
remaining restoration are unverified. No further DSP command was issued.

`cleanup.log`: all capture clients closed; DSP helper unloaded without commands;
ALSA and TVFE modules unloaded, restoring SPDI1, ostream0, AudioTop, IHB and
TVFE clock/reset settings. MIPS help win responded. Base HDMI power/EDID holds
remain; volatile patch/partial graph require a physical cold boot to clear.
No listeners or test processes remain. No boot artifact or persistent
environment changed. Hardware recording validation is still pending.

Next: user-stopped cold boot at U-Boot, load the open-fixed driver, apply the
proven patch/graph once, and run the recording test with the reseated cable.
