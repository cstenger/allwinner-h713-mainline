# SetSource with a readable descriptor, 2026-09-08

The single SetSource(1) RPC returned successfully in 74,726 microseconds.
No measured state-machine, detector-header, AFBD, or composition change followed.

## Setup

The board had rebooted since September 6 and was running default Linux with
MIPS parked and no budgeted DECD module. Returned to U-Boot by normal reboot,
ran `h713_disp init 0x34`, verified firmware/application readiness and core=1,
then booted `/root/fits/h713-kernel-decd-iommu-0076v3.fit` with the AFBD
platform-init blacklist. Replaced the automatically loaded DECD module with
`sunxi-decd-budget.ko ring_writes_max=1`, then loaded CPU_COMM.

Verified the corrected client against the recorded SHA-256. Submitted the
1280x720 test frame once and invoked `dtv get_fb` before taking the baseline.
The firmware log reported stride 1280 and picture width 1280 (later captures
also contained height 720). The ring was exhausted at 1/1 before SetSource
and remained 1/1 throughout. This is a fresh-boot variant of the proposed
5/5 experiment; no additional ring writes occurred during the comparison.

## Result

Issued exactly `/root/cpu-comm-probe THal_Vp_SetSource_1_000 1`.
Captured registers and logs after the RPC and again after a two-second delay.
Captures are sequential, not atomic; the first capture also takes time.

All captured `.comp`, `.afbd`, `.state`, and `.budget` files are byte-identical
across baseline, immediate, and delayed observations:

- THidTVPro singleton resolved to ARM `0x4b83084c`, expected vtable
  `0x8b1f8bdc`; state at +0x5a0 stayed 1 (NoSignal), enable at +0x5a4 stayed 1.
- Detector resolved to `0x4b830ea8`, expected vtable `0x8b1f8d80`.
  The four sampled words at each of +0xb0 and +0x140 stayed zero. These are
  header samples, not complete buffer dumps.
- All seventeen composition registers retained the 1280x720 reference values.
- AFBD retained source control `0x03000010`, source geometry `0x043f077f`,
  strides `0x780`, Y/C addresses `0xffe00000`/`0xffee1000`.
- Core remained 1, bypass `0x7c`, selector `0x29000000`.

The log comparison found new CPU_COMM callback entries, but no new
THal_Vp_SetSource/AppTopSetSource/SetSignalInfo/CalcWindow/WriteReg entries.
Existing records at boot timestamp zero are not evidence of this call.
The elog reader yields partial/damaged records and changes in previously read
records, so log absence does not establish exactly where dispatch stopped.
In particular, this run does not independently confirm that the window
manager received SetSignalInfo, unlike the September 4 capture.

## Interpretation

A readable descriptor plus this SetSource RPC was insufficient to advance the
observed NoSignal state. Parsing by the debug command is distinct from latching
signal-detector state. No visual result was requested or inferred.

Next investigation: trace this RPC's actual firmware dispatch and the
device-manager path that invokes the detector/state-machine poll. Establish
that call path before another write experiment; do not equate RPC success
with execution of the desired window operation.

Board remains alive with DECD/CPU_COMM loaded and budget exhausted at 1/1.
Default boot configuration and display_cfg.xml were not changed.

Evidence and the executed script: [setsource-2026-09-08](setsource-2026-09-08/).
Board originals: `/root/setsource-20260908`.
