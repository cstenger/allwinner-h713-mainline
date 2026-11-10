# Rate-test preparation: aborted before playback

The rate sweep has **not run**. No conclusion about 32 or 44.1 kHz support.

The operator cold-cycled twice. The first listener incorrectly waited for the
host UART adapter to disappear; the second, watching ttyUSB0, expired before
the operator completed the next cycle. Linux autobooted with MIPS parked.
The actual responsive board console was ttyACM0. Read-only SSH verified the
fresh boot, parked MIPS, saved SSH host key, board model HY200 QZ713DF_A1 and
the expected 6.18.38 #1 Oct 7 kernel.

The documented `reboot bootloader` command then reached U-Boot with bootdelay
-1 without saving environment. U-Boot's ordinary panel initialization runs
and quiesces MIPS before the prompt. This return is a deviation from attempt
2's direct cold-boot stop; do not attribute a subsequent failure solely to
DSP timing. `mips-start.log` records the guarded trace launch and readiness;
`channels.log` verifies current channel 0 PID 8b8f275c. `source3-fit.log` shows
the guarded source-3 worker completion and unchanged FIT/embedded DT size.
`ram-dt-boot.log` records the RAM-only IRQ correction and Linux boot.

The three module hashes matched successful graph-chain attempt 2 exactly:

- DSP: 8b5c8e643421837b6216ee37ec62fb7c0b9c79aeed9593f7497c97cc63e9acdc
- Bridge: 1e137200a921ae318eda8cbd53d3faaf6ed678ee8ae5c69000d11fdaef71ebe1
- TVFE: 8f32cf93d04650082aacc825bcc6d7350a3e9bff40cdc8e4a6d0912e9047f816

The transfer review initially rejected staging as an unverified destination.
Strict SSH host-key and board identity checks resolved that rejection; the
same temporary staging transfer was then approved.

`linux-preparation.log` verifies source 3 and trace canaries, then holds.
`audio-setup.log` records bridge CONFIG2207/private coherent DMA, TVFE and
DSP setup and both DSP version words zero. `dsp-patch.log` records the
724-pair volatile stock patch and versions1/1.

## Setup failure

`dsp-graph-failure.log`: all 22 originals were read. Nine writes were verified
(0003,800c,800d,00ac,0077,004d,805a,8059,0130). The next write,0012=8180,
was issued, but its readback did not observe completion-clear within the
stock-size50ms budget (50102us logged, status00000120). The probe latched
failed and released ownership. No further DSP command or software retry.
0012's final value is unverified; later graph words were not applied.

This resembles the prior completion-clear failure, but whether the command
was not serviced or a clear/set transition escaped observation is unknown.
The probe demands a visible clear; stock read code does not. Do not remove
that guard merely to make this run pass, or claim a sample-rate failure.

## Cleanup and current state

`cleanup.log`: DSP probe unloaded without further commands; bridge and TVFE
unloaded, restoring SPDI1, ostream0, AudioTop, IHB and TVFE clock/reset state.
MIPS `help win` responded. Base HDMI receiver-power and EDID holds remain.
The volatile patch and partial DSP graph could not be restored because of
the failure latch. Physical cold boot is mandatory before another DSP trial.
No kernel, bootloader or persistent environment files were changed.

Next: catch a physical cold boot on the actual board CDC console before
autoboot, then re-establish the proven graph. The rate runner remains ready.
