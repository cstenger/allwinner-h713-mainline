# Staged DSP access prefix preparation — October 21, 2026

**Offline preparation only. No new board access, staging or live result.**
The preceding [cold attempt](../2026-10-21-dsp-cold-access/README.md) stalled
during the old monolithic prepare operation. Its cause remains unknown.
The [audit and live gate](../../hdmi-dsp-access-audit-2026-10-21.md) define the
limited new experiment. The Claude handoff has been updated to this state.

The new prefix module requires the existing cold maintenance DT marker and
stopped-state predicates but separates load from 33 explicitly acknowledged
operations. It stops before domain setup, clock/reset writes and all
AudioTop/DSP/lock accesses. The initial resource claims on those latter ranges
are only software reservations. `steps.json` defines expected names/numbers.
The helper/guard enforce this separately staged experiment; do not use the old
failed bundle or mistake these preparations for software recovery.

`dt-audit.json` records actual fdtget queries against the exact previously
prepared `boot-v3/logo-free-reference.dtb`. It confirms retained
`allwinner,keep-tvcap-on`, the reset descriptors and disabled tvtop/display.
PPU source marks retained TVCAP software state on without checking hardware
state in that branch. This is an unresolved prerequisite, not a proven cause
of the stall. Kernel-source hashes in `preparation.json` identify the inspected
code; no new PMU read or transition was attempted.

`module-build.txt` records a successful W=1 build, with only the known compiler
23.1.3 versus kernel 23.1.1 warning. `module-vermagic.txt` is
`6.18.38 SMP mod_unload aarch64`. `module-imports.txt` records provider/resource
APIs and excludes clock-enable/reset-change/runtime-PM/genpd imports; source
review is still needed for inline MMIO. The module was built in the ignored
isolated host directory, never installed or loaded.

- `prefix-tests.txt`: 10 tests pass, covering refusal, explicit ordering,
  terminal boundary, failed/uncertain operations, acknowledgment loss, kernel
  cursor mismatch, release and Python/C protocol consistency.
- `guard-tests.txt`: 3 tests pass, including the new module's reboot/kexec
  conversion and unchanged ordinary halt/poweroff behavior.
- `legacy-observe-tests.txt`: 5 tests pass, including new-audit owner/attempt
  refusal before legacy load.
- `helper-help.txt`: CLI exposes load, a single explicit step, status and
  release. No versions action or automatic advance loop exists.

`bundle-manifest.json` pins the three locally prepared bundle files. Exact
new module SHA-256:
`c57229a40b6f9a7fc8fd158a38ee98f8f3fd4d44a1b86c43c898ca4326df1ea8`.
The new guard SHA-256 is
`96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113`;
this differs from the currently installed legacy-only guard. Board files
remain unchanged. The local bundle is
`build/hdmi-dsp-access-audit-2026-10-21/bundle/`.

`preparation.json` records exact source/kernel inputs and output hashes. Its
base commit is the existing handoff commit; the new source identities are the
recorded working-tree content hashes, not that base commit alone. Generated
kernel/module binaries are not committed. `sha256.json` covers the curated
preparation evidence. These checks establish offline consistency, not hardware
access safety, a reset-domain result, DSP retention or automatic warm recovery.
