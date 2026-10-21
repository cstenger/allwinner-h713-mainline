# Staged DSP access audit — October 21, 2026

**Status: prefix bench prepared; a first live run exists but is not curated.**
`build/hdmi-dsp-access-audit-2026-10-21/cold-prefix-01/` (boot
`460adf1a-ac3d-4c8e-b6bb-b86b2154fd0b`) records a cold catch, guard install,
`load`, and steps 1–9 acknowledged with UART BEGIN/DONE; step 9
`read-mips-stopped` read `00000000`. The recorder then ran to its 60-minute
deadline with no further output. The console threshold was raised by hand
before step 1 (finding 7). Nothing beyond step 9 was sent, and the board's
state after that run is not recorded. Curate that run into
`docs/hdmi-evidence/` before relying on it. The stalled
[earlier experiment](hdmi-evidence/2026-10-21-dsp-cold-access/README.md) remains
unlocalized. Do not repeat that monolithic preparation unchanged.

## Findings from source and exact maintenance DT

1. The old wrapper persisted `attempted` before insmod but did not flush a
   before-insmod milestone. Its subprocess captured output until completion.
   A silent SSH log cannot identify module entry or the failing syscall.
2. Before its first informative AudioTop log, the old module requested four
   resource ranges, mapped four control windows, read MIPS/SCP/CCU controls,
   obtained reset handles/status, obtained 17 clock handles, registered and
   resumed two domain devices, prepared display/receiver/audio clocks,
   released resets, programmed TVFE words, mapped AudioTop/DSP/lock windows
   and read both initial AudioTop words. Any of these remains a possible
   pending boundary; absence of logs does not identify the culprit.
3. In the installed kernel source, `of_clk_get_from_provider()` resolves a
   provider and creates/links a consumer handle; it does not prepare/enable
   the clock. Plain exclusive `of_reset_control_get_exclusive()` does not
   request deassertion. `reset_control_status()` dispatches to CCU status,
   which reads the mapped reset bit and inverts it (API 1 means asserted).
   These operations can be separated from subsequent state changes.
4. The exact maintenance reference DT retains
   `allwinner,keep-tvcap-on` on `/soc/power-controller@7001014`. The PPU driver
   marks TVCAP ALWAYS_ON and initializes genpd as on in that branch without
   checking its hardware power-state field. Thus software domain state cannot
   independently prove TVCAP powered on in a no-logo boot. This is a dependency
   to verify before domain/receiver access, **not a demonstrated cause** of the
   stall. Do not remove the property or power-cycle the domain speculatively.
5. The PPU probe already deasserts its own reset, enables its clock and writes
   domain timing controls during Linux startup. No-logo Linux is not pristine
   reset-entry observation. Even the revised prefix samples after those effects.
6. `/soc/tvtop@5700000` is already disabled in the pinned DT. The old bench
   uses it as a reset-descriptor container, not as a bound live driver. Its
   reset names and CCU phandles are present. This is not itself a missing
   reset-name defect; the prefix preserves that lookup rather than enabling
   tvtop. AFBD/display and CPU_COMM remain disabled as before.
7. The rootfs sets `kernel.printk = 5 4 1 7` (`tools/rootfs/customize.sh`).
   The console prints only levels strictly below 5, i.e. warnings and worse.
   The old module's informative lines are `pr_info` and the new module's
   INIT/BEGIN/DONE are `pr_notice`; at the default threshold **none of them
   reach the UART**. Only `pr_err` FAIL lines would. Consequently the October
   21 cold attempt's empty `bench-uart.log` carries no information about how
   far the old module progressed, even had it reached or passed AudioTop.
   The earlier wording that its "first informative log is late, at AudioTop"
   is true of dmesg, not of the serial console. (No RCU stall report, which is
   `pr_err` and would have printed, appeared either; that is consistent with
   the whole SoC or the UART path wedging rather than one CPU stalling, but
   does not establish it.) Raise the threshold at runtime with `dmesg -n 7`;
   do not demote or promote module log levels (session tooling parses the
   info lines from dmesg).
8. The maintenance command line contains `panic=5`. An arm64 SError from an
   inaccessible peripheral normally panics, and the kernel would then
   warm-reboot after 5 s. That bypasses the shutdown guard, which only sees an
   orderly reboot, and reaches the warm reset this experiment must not use to
   escape a latched state. Set `sysctl kernel.panic=0` at runtime before
   `load`; a panic then halts and waits for physical cold recovery.
   The October 21 attempt showed no panic text and no SPL banner afterwards,
   so a panic reboot was not what happened there.
9. The helper's attempt state lives in `/run`, which is tmpfs. Its `fsync`
   orders the write before each operation within the boot, which is what
   blocks retries; it does **not** make the state survive a power cycle.
   After a hard stall, the only localization is the UART and whatever SSH
   output arrived before the network died.

The exact DT queries, source/kernel input hashes, build output and offline
checks are preserved in
[the preparation evidence](hdmi-evidence/2026-10-21-dsp-access-audit/README.md).
No source finding establishes that a particular MMIO read is safe in the
current hardware state or that any reset erased DSP state.

## Limited replacement: initial prefix only

The new [prefix module](../modules/hdmi-dsp-access-audit/README.md) and
[helper](../tools/hdmi/dsp-access-audit.py) deliberately stop **before** the old
module's domain-device creation/resume loop. Load validates DT/software state
and pins the module; hardware/handle work starts only on a separate step call.
There are 33 steps, each requiring the precise expected number/name and one
sysfs write. Resource claiming is not peripheral access. The only MMIO samples
are the existing initial MIPS/SCP/CCU/reset-status predicates; no AudioTop,
DSP port or shared lock word is mapped/read by this prefix.

There is no domain attachment/resume, clock enable/state query, reset change,
TVFE/AudioTop programming, firmware launch, DSP request or ownership write.
The new module moves its protective self-pin ahead of this prefix and adds
pauses/logging between operations. It is not a byte-identical replay of the
old init function; a pass would validate these operations in the new recorded
context, not rule out every timing-dependent failure in the old one.

The helper has no automatic loop or continuation into the legacy setup. It
checks eligible boot/DT/units/owners, pins module/helper/guard bytes and ABI,
uses an exclusive flock, flushes before/after milestones, and fsyncs attempt
state (tmpfs; same-boot only, see finding 9) before each potentially pending
operation. Every `load`, `step` and `release` preflight also refuses unless the
console threshold is at least 6 and `kernel.panic` is 0 (findings 7 and 8).
These two checks are newer than the bundle staged for `cold-prefix-01`
(`bundle/`, helper `5fbfd4a8…`, which lacks them). Use
`build/hdmi-dsp-access-audit-2026-10-21/bundle-v2/` for the next boot: same
module `c57229a4…` and guard `96f37655…`, helper
`432dd643466894aa81eb7fa5b407c46b79a4badba172538c4b13fe5201a94340`. Its
manifest and test output are in the preparation evidence as
`bundle-v2-manifest.json` and `prefix-tests-v2.txt`. Stage it in a new board
directory rather than over `/root/hdmi-dsp-access-audit-2026-10-21`. The cursor advances only on
acknowledged success; failure/uncertainty prevents retry or release. A healthy
partial prefix can explicitly release only its software handles and mappings.

The kernel blocks `advance`/`release_prefix` callbacks until initialization
finishes, including attempts to supply them as insmod arguments. It pins on
load and retains the pin/resources on operation error. New guard support
converts reboot/kexec with this audit module present into poweroff. The legacy
wrapper also refuses a loaded new audit or any new-audit attempt state. The
new wrapper refuses any legacy attempt/owner. This prevents supported helpers
from switching experiments within a boot, including after healthy release.
Direct root sysfs/module manipulation is outside this supported protocol.

BEGIN/DONE printk messages and flushed userspace acknowledgments improve
localization only once the console threshold is raised (finding 7), and even
then do not guarantee delivery before a hard stall. Steps 1–8 touch no
hardware, so their BEGIN/DONE pairs double as a check that markers reach the
UART; do not send step 9 unless all eight pairs were captured. Keep passive
UART and SSH output together. A lost reply is a consumed attempt even if the
kernel may have completed. Poll/subprocess timeouts do not bound stalled MMIO.

## Validation and scope

The isolated module builds with W=1 against the exact 6.18.38 kernel tree;
vermagic matches. The only build warning is compiler 23.1.3 versus the kernel's
23.1.1. Its recorded imports contain no clock-enable, reset-change, genpd or
runtime-PM function. Source review also excludes inline register writes; import
inspection alone cannot prove absence of inline MMIO.

Ten prefix-helper tests cover cold/DT/owner/guard/helper/module/ABI refusals,
load without steps, explicit step/name ordering, the 33-step terminal boundary,
failed load/operation, missing acknowledgment, kernel cursor mismatch, partial
healthy release and failed release. The protocol test compares Python step
names with the C plan. Three guard tests and five legacy-wrapper tests pass,
including mutual experiment exclusion. They are offline tests, not live
hardware or physical reset passes.

## Next live gate

1. Review this prefix, source hashes, step list and recovery boundaries. Keep
   the board off until the catcher and passive recording are ready. No boot
   media, environment, SPL, BL31 or proper update is needed for this prefix.
2. Coordinate one fully disconnected cold start with the operator and verify
   FEL/OTG availability. Arm the existing cold catcher first, reconnect UART,
   wait five seconds, then apply board power with the same HDMI source. Stop
   before logo/workspace; require fresh SPL and cold predicates.
3. Review/reuse the pinned `boot-v3` RAM-only maintenance commands with a fresh
   output directory. Immediately match UART/SSH boot IDs. Check root/journal,
   growfs, DT marker/disabled nodes and skipped services. Last shutdown was not
   cleanly verified; repair offline if needed before experiments.
4. Stage the **new** prefix bundle in a new directory, verify each file, back
   up the exact live shutdown hook and atomically install/verify the new guard.
   The current live guard SHA is
   `365fe6c97cefb24794d5e4a315d6711b08a8a136874eebb00a08a750cc8e7de6`;
   it does not cover the new module. Do not assume source changes reached the
   board. Preserve its older backups and ordinary lamp/fan shutdown hook.
5. Before `load`, raise the console threshold and disable panic reboot, then
   confirm both (the helper refuses otherwise). Emit a notice-level marker and
   confirm it on the passive UART capture:

   ```sh
   dmesg -n 7; sysctl kernel.panic=0; cat /proc/sys/kernel/printk /proc/sys/kernel/panic
   echo '<5>H713 PREFIX CONSOLE CHECK' > /dev/kmsg
   ```

   Then execute `load` only and retain INIT/INIT DONE, cursor zero and matching
   boot ID. No step is implicit. Then qualify one explicit stage at a time,
   retaining each BEGIN/DONE and helper acknowledgment before the next.
   Example syntax, with actual staged path/boot ID substituted:

   ```sh
   python3 /root/hdmi-dsp-access-audit-2026-10-21/dsp-access-audit.py load --bundle /root/hdmi-dsp-access-audit-2026-10-21 --expected-boot NEW_BOOT_UUID
   python3 /root/hdmi-dsp-access-audit-2026-10-21/dsp-access-audit.py step --bundle /root/hdmi-dsp-access-audit-2026-10-21 --expected-boot NEW_BOOT_UUID --expected-step 1 --operation claim-dsp-port
   ```

   These are separate gates, not an instruction to chain them. Do not automate
   steps 1–33 in a loop. Stage 9 is the first direct register read.
6. On the first refusal, missing acknowledgment or unexplained behavior, stop;
   do not run the legacy prepare, retry, force-unload, clear GP6 or reset. If
   still responsive, retain read-only diagnostics and request orderly poweroff;
   otherwise coordinate physical cold recovery with lamp/fan confirmed off.
7. If the prefix passes, it excludes only the reproduced initial operations
   under that cold context. It does not establish safety of the omitted
   domain/clock/reset/TVFE/AudioTop/DSP path. Design the next bounded extension
   separately, including verification of the retained-TVCAP assumption and
   staged domain/clock operations. Do not add power transitions merely to get
   a version sample. A later successful read would still require a separate
   retained-patch control before changing warm recovery policy.

Warm automatic HDMI recovery remains unimplemented and release-blocking.
