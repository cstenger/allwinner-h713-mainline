# TVFE boot trace preparation — October 21, 2026

**Offline preparation only. Nothing installed or executed on the board.**
Board remains unpowered; no UART catcher is armed.

See the [design and live run instructions](../../hdmi-tvfe-boot-trace-design-2026-10-21.md).

Built candidate:
`build/hdmi-tvfe-boot-trace-2026-10-21/candidate/`.

The first diagnostic uses the installed U-Boot and a separately staged,
RAM-loaded kernel FIT. Its trace requires `h713_tvfe_trace=1`. The optional
U-Boot proper observes bootm device cleanup and is built for a possible
second stage; its installation/rollback package is not prepared.

Recorded files:

- `manifest.json`: exact base paths/pins, patch hashes, compiler, build
  commands, unchanged exported symbol versions and artifact hashes/sizes.
- `build-0.log`: successful real arm64 kernel and modules build.
- `build-1.log`: successful proper build; existing-source compiler warnings
  are retained. No new trace/bootm code warning was reported.
- `tests.txt`: 13 new offline tests and 19 warm-retention regressions passed.
- `validation.json`: tool hashes and additional FIT/source/ABI checks.
- `sha256.json`: hashes of this preparation evidence.

The FIT kernel/DTB were independently extracted and compared with the output
files; decompression matches the new arm64 Image. The DTB is byte-identical
to production. Baseline inputs still validate after the builds, and every
original PPU hardware-write statement remains in the same sequence. Native
tests verify the actual trace helpers refuse gated/half-open PPU accesses.

No live pass, TVFE cause, DSP-retention result or warm-recovery pass is claimed.
The next action is a controlled cold production startup, staging only the
diagnostic FIT, then a captured orderly warm boot per the runbook. Verify
host UART OPEN before requesting power; preserve the single-logo rule.
