# First ALSA module load stopped responding

The user physically cold-booted and manually stopped at U-Boot. `mips-start.log`
records one guarded launch, current live channel0 PID8b8f275c and readiness.
`source3-fit.log` verifies source3 completion and unchanged FIT/DT size.
`ram-dt-boot.log` records the RAM-only IRQ correction and boot. Linux kernel
and board model matched; the saved SSH host key was verified before staging.
`linux-preparation.log` verifies source3/canaries and receiver holds.

`driver-load.log` records the staged hashes and successful MIPS `help win`
after TVFE hold setup. The next command was insmod of the first ALSA driver,
SHA256ca44d7e95e46e726bf1c58b77f172931f7eae334c92fdd9025b66fa0cad37291.
That command did not return. A fresh SSH connection timed out and the serial
console produced no reply. The pending local SSH process was terminated.
ALSA registration was not confirmed. No DSP probe/patch/graph operation or
playback/capture test was run.

## Identified source error and correction

The added inactive-SPDI1 check read AudIf before the inherited, hardware-proven
IHB retiming and AudioTop initialization. This is a concrete ordering change
from the successful bridge diagnostic and an error in the new driver.

The check now follows that setup, and AudIf IRQ registration also follows the
setup so its handler cannot introduce an early read. A boundary message is
emitted before the check. The revised module builds cleanly with LLVM W=1.
`clock-order-fix-build.json` records the new sources/module and original hash.

The exact instruction at the hang is **not known**: the first command only
requested dmesg after insmod, so it could not retrieve intermediate messages.
The ordering error is a plausible cause, not a hardware-proven explanation.
On the next test, stream bounded kernel logs separately before insmod so its
last completed stage is preserved even if module loading stops responding.

## Recovery

Board state cannot be restored remotely while it is unresponsive. No persistent
boot artifacts were modified. A physical cold boot, with serial/all USB
disconnected and power removed for at least one minute, is required. The user
will stop at U-Boot manually. No serial listener or capture process remains.
Do not use a warm MIPS relaunch. The ALSA recording tests remain pending.
