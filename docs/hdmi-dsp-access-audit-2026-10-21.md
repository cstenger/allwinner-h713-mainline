# Staged DSP access audit — October 21, 2026

**Status: offline audit and new prefix bench prepared; no new hardware access.**
The board's last confirmed state is fully off/disconnected. The stalled
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
state before each potentially pending operation. The cursor advances only on
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
localization, but do not guarantee delivery before a hard stall. Keep passive
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
5. First execute `load` only and retain INIT/INIT DONE, cursor zero and matching
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
