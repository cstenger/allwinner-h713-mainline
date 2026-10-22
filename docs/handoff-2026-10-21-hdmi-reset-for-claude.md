# HDMI reset recovery handoff for Claude — October 21, 2026

## LIVE STATUS — read this first (updated continuously; newest at top)

**October 22: Phase A bench BUILT and offline-verified (Claude); board still
unplugged; no catcher armed; no power requested.**
[Preparation evidence](hdmi-evidence/2026-10-22-dsp-teardown-a-preparation/README.md).
New isolated candidate `build/hdmi-dsp-teardown-a-2026-10-22/candidate/`
(old owner candidate untouched). 37 one-shot steps, six version pairs:
positive → common graph restore (both arms) → SPDI1 restore → bridge restore
→ AudioTop config → AudioTop control off/on, each followed by a pair; first
changed/echo/timeout pair is terminal. Sham performs identical reads/waits
but no SPDI/bridge/AudioTop writes. W=1 build clean against the unchanged
production kernel; module `cffa83e6…`; 26 new tests (real includes on fake
MMIO, 13 mutations caught) plus 43 regressions pass. New DT marker
`h713,dsp-teardown-a-v1`, bootarg `h713_teardown_a=1`, state schema
`h713-teardown-a-v1`; old sham cannot qualify this module.

**Next: arm 1 (new sham) on a fresh cold cycle, then arm 2 on another.**
Runbook per cycle (`R` = new `docs/hdmi-evidence/<date>-dsp-teardown-a-<sham|teardown>-live`,
whose name is also the remote bundle directory under
`/root/hdmi-dsp-teardown-a-2026-10-22/`):
1. Board fully unplugged ≥1 min (user confirms). Write `R/capture-plan.json`
   with `arm` (1 or 2), candidate path, manifest/module/script hashes, and
   for arm 2 the sham `snapshot-37.json` path and canonical hash.
2. Start the sole catcher in the background:
   `tools/serial/catch-cold-uboot.py --port /dev/ttyUSB0 --output R/cold-catch`;
   confirm `OPEN` in `R/cold-catch/events.log`; only then ask for power.
3. At the captured prompt: `tools/serial/run-dsp-teardown-cold.py --prepared
   <candidate> --cold-catch R/cold-catch/serial.log --arm N [--sham-record …]
   --port /dev/ttyUSB0 --output R/cold-boot` (one launch, never repeated).
   Check source3, 720p re-latch and handoff in `R/cold-boot/serial.log`.
4. Wi-Fi `spirits`, then `tools/hdmi/dsp-teardown-a-host.py --run R`:
   `health-stage`; `uart` (background, sole reader); `snapshot`;
   `initialize`; then for n = 1…37: `step n <ack>` where `<ack>` is
   the stage name of the previous step if it is in `STAGES` (see
   `tools/hdmi/dsp-teardown-a.py`), and `snapshot` after every staged step.
   Stop at `terminal`. Then `export`, `poweroff`; confirm UART
   `reboot: Power down`; `touch R/stop-steps-uart`.
5. Arm 2 only after `analyze-dsp-teardown-a.py` gives
   `sham_positive_control_passed` on the sham's terminal snapshot.
Do not continue to Phase B on a cycle that ends in a changed pair/timeout.

**October 22: CLAUDE TAKEOVER — board fully unplugged, user confirmed.**
No running capture, UART reader, SSH diagnostic or bench operation. Last
completed run is matched boundary arm 2, commit `57c6328`; it preserved
reported patched versions `1/1` after graph restoration, config clear and
control off/on, matching successful sham commit `119be31`. Both completed
runs exported/checksummed and reached UART Power down; recorders closed.
User requests next diagnostic preparation and this handoff because Codex
usage is nearly exhausted. No permission question is pending.

**Next diagnostic design is prepared; executable implementation/build is
still required.** Read
[remaining teardown/reset design](hdmi-dsp-remaining-teardown-design-2026-10-22.md)
and [source review/preparation](hdmi-evidence/2026-10-22-dsp-remaining-teardown-preparation/README.md).
First implement **Phase A: normal-order graph → SPDI → Audio Bridge →
AudioTop**, inside a new isolated, pinned sole-owner bench. The old module
has only 25 graph/AT operations; do not use it for unimplemented boundaries
or silently accept the old sham for a changed build. New matching sham and
intervention arm are required. No new module/FIT/boot script was generated,
no new board staging occurred, and no capture has been armed for this plan.

Source review found an important extra bracket: normal session shutdown
performs audio clock/TVFE restoration and possible **demod reset**, then
terminal **MIPS parking asserts three resets before CPU reboot**. Receiver
parked release can subsequently release clocks/domains. These are distinct
from CPU reset and warm logo; previous post-warm zeros do not isolate any
one of them. `h713_receiver_release()` only decrements the audio client;
actual parked resource release is separate. Preserve that distinction.

After Phase A qualifies, design/validate clock restore → access reacquisition
without demod reset, then demod reset separately. Clock-off observer cannot
read DSP/stock lock/debug providers blindly. Existing owner health requires
MIPS live; parked-MIPS observer needs a separate contract, and production
park refuses audio clients. Do not bypass client accounting or relaunch MIPS.
Keep domains held until an explicitly separate domain test. CPU reset /
pre-logo observer comes only after earlier qualified boundaries as needed.
Implementation safety/acceptance gates and precise source/register map are
in the new design. No raw MMIO commands or automatic reset sequence provided.

**Claude's immediate next action:** read the design, implement Phase A in a
new directory (preserve old candidate/evidence), native/Python negative tests,
real W=1 production-kernel module build and pinned provenance checks. Only
then arm a sole cold catcher, verify OPEN and tell user when to apply power.
Use UART `/dev/ttyUSB0` 115200; SSH `root@192.168.4.1`, host Wi-Fi `spirits`.
Host hardware/network calls in this Codex environment require escalated
execution; local sandbox does not expose the host UART. No credentials in
handoff. Installed guard and original backup remain unchanged (hashes below).
One launch per fresh disconnected cold cycle; do not write GP7/clear GP6 or
restart a failed/uncertain cycle. Follow exact stop/export/poweroff rules.
Further run count depends on the new matched tests; old 2–4 estimate is not
a promise. The current no-reset graph/AT batch needs no automatic repeat.



**October 22: matched boundary arm 2 COMPLETE — tested boundaries preserved `1/1`.**
[Live evidence](hdmi-evidence/2026-10-22-dsp-owner-boundary-live/README.md).
All four version pairs completed **`1/1`**, including after 22 verified
reverse-order graph restores, AudioTop config clear, then control off/on.
All full responses `00000001`, statuses `00000120`, phase `[5,5]`, sent/
outcome `[1,1]`. Eight requests once each, no timeout/echo/skip/failure.
All 25 ordered UART BEGIN/DONE and exact restores validated. Terminal lock
released, graph_remaining 0, ctl/cfg `700/0`, resources/domains retained,
certain ledger. Fresh production boot `77d7afff-6ff8-4629-961d-1fa56dc3015d`;
exact candidate and all baseline registers/saved graph words matched sham.
Cold origin, single source3/handoff and initial-zero → pinned-patch `1/1`
verified. No reset/warm logo/repatch/unload after initialization.
Export 266333 bytes, SHA-256
`e4ad3512a5f1aa1901d737b0419b424cbac60a7ce5e80a89b41a5a57f8f2e0b9`,
verified on host before checked poweroff. UART `reboot: Power down` at
274.472661 seconds; sole recorder closed. User instructed to fully unplug
and leave off; post-run physical disconnection not yet confirmed. No capture
active. Guard and original backup unchanged. Wi-Fi reconnect/SSH worked.
**Interpretation:** this matched no-reset graph/AudioTop sequence preserved
the version report. It did not reproduce earlier post-shutdown/reset/logo
zeros and does not prove reset retention or directly inspect patch RAM.
Normal SPDI/bridge restoration was omitted in both arms; order/interactions
remain relevant. Next design should bracket omitted SPDI/bridge and
clock restoration/demod reset, followed by CPU reset/early boot/warm logo
as required. No new intervention improvised after terminal checkpoint.
Both planned arms complete; no clear loss finding to confirm yet. Roughly
2–4 further matched runs remains an estimate, depending on results.
Exact boundary record:
`docs/hdmi-evidence/2026-10-22-dsp-owner-boundary-live/board-export/snapshot-25.json`.
Exact sham record follows in prior status. Normal one-launch/recovery policy
unchanged; restore guard only under documented cold normal-boot conditions.


**October 22: no-reset patched positive-control SHAM COMPLETE — PASS.**
[Live evidence](hdmi-evidence/2026-10-22-dsp-owner-sham-live/README.md).
All four measured version pairs completed **`1/1`**: eight single requests,
phase/outcome/sent `[5,5]/[1,1]/[1,1]`, full responses `00000001`, statuses
`00000120` for both devices throughout. All 25 explicit steps and UART
BEGIN/DONE checked once/in order; no timeout, failure, skip or uncertainty.
AudioTop remained `700/011a5e00`, all 22 graph values held, saved words
unchanged. Terminal lock released, resources pinned, both domains ON.
Fresh production boot `dcfe762c-9cb5-44ca-a546-049f03e2a1fd`, one captured
cold SPL/source3/handoff and initial-zero → pinned-patch `1/1` setup.
No graph/AudioTop change, reset, warm logo or teardown after patching.
Exact module/script/manifest unchanged from preparation; Wi-Fi/SSH worked.
Export verified on host: 264868 bytes, SHA-256
`1362d88effaceb1e82df5996f9deecd4655d70b4ad762f23be30ae4d240c7bf5`.
Checked poweroff, UART `reboot: Power down` at 414.276830 seconds, recorder
closed. User instructed to physically unplug and leave off; disconnection
not yet confirmed. No active capture or arm-2 initialization.
Use exact exported successful sham:
`docs/hdmi-evidence/2026-10-22-dsp-owner-sham-live/board-export/snapshot-25.json`.
Canonical sorted-JSON-plus-newline hash
`eb31e9e00a49666804f1f3cfe7060b2251152da655a1c01d337823ff2f728fa6`.
Next is **arm 2**, separate disconnected cold cycle >=1 minute, same prepared
candidate and exact sham, fresh boot ID/proof and matching baseline/saved
22 graph words. Follow runbook; graph restore → pair, config clear → pair,
control off/on → pair; stop at first change/timeout. No automatic capture
armed. This pass qualifies access/control and does not establish reset
retention or locate loss yet. One matched run remains in this batch,
usually one further confirmation if clear. Guard/original backup unchanged.


**October 22: no-reset patched positive control / matched shutdown-prefix
batch PREPARED OFFLINE; board OFF; no capture armed.**
[Design/runbook](hdmi-dsp-owner-boundary-design-2026-10-22.md),
[build and tests](hdmi-evidence/2026-10-22-dsp-owner-boundary-preparation/README.md).
Use `build/hdmi-dsp-owner-boundary-2026-10-22/candidate/`.
**Two new cold-cycle runs:** arm 1 sham must complete four patched `1/1`
pairs; arm 2 is permitted only with that exact successful record and a
separate fresh boot/matched baseline/saved graph values. Normal audio
teardown restores 22 saved DSP graph words, then AudioTop config/control,
then clocks and possibly demod reset, before CPU reset. The next test
therefore brackets these earlier shutdown operations instead of attributing
previous zeros directly to reset/logo.
Same isolated owner module in both arms, SHA-256
`6cbc305cfcd14b20d9c72c25c293402cc2c7490d1cf3e977ba60654c5bf62001`,
production kernel `6.18.38 #1 SMP Fri Oct 16 15:44:49 PDT 2026` unchanged.
RAM-only cold script SHA-256
`0f3245113d33501761e51aa87c59980e63e03c2569d6b05e3276b47d18e6e1d1`.
This is not the earlier warm minimum kernel. Script retains exact guarded
cold source3 startup, removes warm fallback, sets bench DT marker and
runtime service masks, panic 0/loglevel 7, lamp off. No media/env update.
Owner loads pinned patch/graph once as baseline, omits PCM, disables audio
IRQs and pins itself/receiver/resources. No competing ARM probe, service
teardown, unload, reset or warm logo after patching. Arm immutable at load.
Up to 25 explicit operations: patched pair; existing 22-word graph restore
(or sham) and pair; config clear (or sham) and pair; control off/on (or sham)
and pair. Stop at the first changed/mixed/timed-out pair; no later boundary.
Timeout allows only current-pair skip/release/checkpoint/export/poweroff.
Hard failure or uncertain ledger means stop, no forced cleanup/retry.
Exact command echo is ambiguous, never version zero. Full raw words,
protocol phases, original saved graph words, state/ledger/journal/UART saved.
Host proof checks exact kernel/bundle/loaded module build ID/fresh cold
capture/arm/boot/guard; arm 2 checks exact qualified sham and context.
43 offline tests pass (14 new +29 relevant regressions); real W=1 module
build, vermagic/Symvers and script CRC/payload/hash checks pass. Kbuild notes
host clang 23.1.3 versus kernel clang 23.1.1; no C diagnostics. No board access
or install occurred. Existing guard/original backup remain unchanged.
Next live action: separately arm sole cold catcher for **sham arm 1** before
power. One launch per cold cycle; use the new cold loader. After either arm,
export/checksum, checked poweroff, record UART Power down, physically unplug.
If a clear boundary appears, expect one confirmation run; if all preserve
patch reports, budget roughly 2–4 further matched runs for remaining
SPDI/bridge/clock/demod/reset/early-boot/logo bracket. Estimate, not a hard
upper bound. No more control-only qualification repeats are planned.
Normal startup/recovery policy and production one-launch protections stay.


**October 22 afternoon: fresh control-only replication COMPLETE; board OFF;
recorder closed. Control-only access sufficiency replicated in two cycles.**
[Replication evidence](hdmi-evidence/2026-10-22-dsp-minimum-control-replication/README.md).
Full cold SPL captured this time: GP6/GP7 zero, MIPS parked, unchanged
bootcmd. Fresh production boot `47702c3c` verified DSP `0/0` → pinned
patch `1/1`, active owners and both domains ON. One checked/captured warm
reset and one successful lamp-off warm logo preceded the same exact
minimum FIT/kernel at fixed level 1, warm boot `cb320a62`.
All 58 steps passed. AudioTop initial `0/0`, control `0x700` readback,
config/latch skipped. Both single version requests completed, returning
**`0/0`**, phase `[5,5]`, sent/outcomes `[1,1]`, statuses `20/120`, no timeout.
Lock released; terminal hold/domain/interface/exact `700/0` checks and
certain ledger passed. Entire terminal observer state is identical to
live-control-02, including reset/clock/routing context and responses.
No TVFE power command or violation. Full step UART audited once/in order;
records exported and checksum verified before checked poweroff.
UART `reboot: Power down` at 306.378926 s; user instructed to physically
disconnect and leave board off. Host Wi-Fi/SSH worked after both boots.
No individual-bit minimum or reset RAM-erasure claim. Loss interval still
includes reset/early boot, warm logo, interface/demod-reset preparation and
control write. Next: design a no-reset patched positive control and matched
boundary trial using the replicated control-only access recipe. Levels 2/3
are unnecessary for sufficiency; no extra request/no-logo/reboot in this boot.
Normal boot files/environment/bootloader unchanged; bench guard and original
mode-0755 backup preserved. Restore only after cold normal boot/hash checks.
Work directory `build/hdmi-dsp-minimum-2026-10-22/live-control-03/`;
previous completed board staging archived as
`/root/hdmi-dsp-minimum-2026-10-22-previous-68081628`. No automatic recovery
or production one-launch policy changes.


**October 22 afternoon: control-only AudioTop trial COMPLETE; board OFF;
recorder closed. Host Wi-Fi works after the user restarted both machines.**
[Live evidence](hdmi-evidence/2026-10-22-dsp-minimum-control-live/README.md).
Fresh production boot `e5d341d0` verified DSP `0/0` → pinned patch `1/1`,
active owners and both domains ON. User reported hours fully off; cold SPL
was not captured because power was already applied. One captured orderly
warm reset and one successful lamp-off warm logo preceded exact minimum
kernel `#4 SMP Thu Oct 22 02:35:16 PDT 2026`, warm boot `68081628`.
All 58 explicit operations passed. TVFE hold eligible/applied, no TVFE power
command/violation; AudioTop census exact `0/0`. **Control `0x700` alone
completed both version reads, returning `0/0`**. Setup mask 1, config/latch
skipped, phase `[5,5]`, sent `[1,1]`, outcomes `[1,1]`, statuses `20/120`,
no timeout. ARM lock released; final exact `700/0`, domain/interface health
and certain ledger verified. UART records every BEGIN/DONE once and both
command-sent/COMPLETE sequences. Evidence exported/checksummed before
checked poweroff; UART `reboot: Power down` at 367.918841 s.
Control-only setup is sufficient in this trial. Config/latch writes are
not needed to observe zero versions; the loss interval still includes
reset/early boot, warm logo, interface preparation/demod reset release and
the control write. No claim of direct DSP RAM erasure or minimal individual
control bits. Routing matched (zero writes); display/TVCAP reset already
released. Next: replicate level 1 in a new disconnected cold cycle with
cold SPL capture, then design a no-reset patched positive control/matched
boundary experiment. No reason to escalate to levels 2/3 in this boot.
Normal boot files/environment/bootloader unchanged; existing bench guard
and original backup preserved. Lamp off; user instructed to disconnect
power and leave it off. Restore guard only after cold normal boot/hash
checks. Work directory `build/hdmi-dsp-minimum-2026-10-22/live-control-02/`.
Earlier live-control-01 ended before warm reboot/observer steps; its UART
FIT transfer completed successfully, and old board staging was archived.
No automatic recovery or production one-launch policy changes.


**October 22: minimum AudioTop diagnostic PREPARED OFFLINE; board OFF;
no capture armed.**
[Runbook](hdmi-dsp-minimum-design-2026-10-22.md),
[build and tests](hdmi-evidence/2026-10-22-dsp-minimum-preparation/README.md).
Use `build/hdmi-dsp-minimum-2026-10-22/candidate/`: FIT SHA-256
`e1b475a8cb66ba86846a30dc8845c6cb0e76c8459f0d2bc2f3ba47edf63d8aeb`,
exact kernel `6.18.38 #4 SMP Thu Oct 22 02:35:16 PDT 2026` (not the older
boundary #4 timestamp). Next live trial: **level 1, control 0x700 only**
before any DSP request. Level 2 adds config `001a5e00`, level 3 adds latch
`011a5e00`; each requires a separate disconnected cold cycle, fresh patched
baseline and one warm logo. Boot flag `h713_dsp_at_level=N` fixes the level;
`h713_dsp_minimum=1` plus trace/retain enables the new 58-step observer.
It refuses inherited/nonzero initial AudioTop setup. Prefix/access/TVFE
hold unchanged; display/CPU_COMM disabled and minimum DT marker added.
Explicit BUSY_WAIT/COMMAND_WRITE_BEGIN/COMMAND_SENT/DONE_WAIT/COMPLETE or
TIMEOUT traces and per-device phase/sent fields resolve the previous gap.
Only one version attempt/device; timeout allows only skip/release/final,
never setup afterward, retry, reset, firmware or patch. Host level-bound
loader/binder/helper verify kernel/FIT/DT/baseline/boot/owners/guard/proof.
Completed zero versions count as access success, not retained patch. The
analyzer compares matched independent levels conservatively; minimum means
lowest completed nonempty stock prefix under this path, not individual bits
or all register orders. Initial-busy/invalid/missing lower trials do not
establish a minimum; first success should be replicated in a new cold cycle.
Real kernel/modules build no warnings; FIT/DT/ABI checks pass; 11 new tests
+59 regressions pass. No board access/install occurred. Existing bench
guard/original backup unchanged. Lamp off, physical disconnect after
poweroff (display shutdown callback disabled). Automatic recovery unchanged.



**October 22: boundary one-logo trial ENDED INCONCLUSIVE; board OFF;
recorder closed.**
[Live evidence](hdmi-evidence/2026-10-22-dsp-boundary-one-logo-live/README.md).
Cold production `013a628c` verified DSP `0/0` → pinned patch `1/1` with both
TV domains ON and all owners active. One orderly warm reset/one successful
warm logo preceded RAM boundary kernel `#4`, boot `5b3937e4`. Hold eligible/
applied, no TVFE power command. Steps 1–51 passed: clocks/routing verified,
demod reset released; display/TVCAP reset already released; no routing
writes; AudioTop census `0/0`; stock lock claim verified; DSP status idle.
**First pre-AudioTop device-0 attempt at step 52 timed out**, status `0x10`
(busy bit 4 set, done bit 5 clear), outcome 2, raw unknown `ffffffff`.
Device 1 was skipped (outcome 3), lock release/final check passed at 55.
No step 56+, no AudioTop setup, request retry or no-logo trial. Analyzer
reports inconclusive; no completed version pair. Current trace cannot
separate initial-busy timeout from post-command done timeout: at most one
command write, not a proven command-sent event. Do not treat unknown as zero.
UART confirms `reboot: Power down` at 436.198947 s. Lamp stayed off; display
DT node disabled, so no normal DRM panel-shutdown callback. User must fully
disconnect power before another trial. Existing bench guard/original backup
remain unchanged; boundary bundle/boot-bound arm proof staged separately.
Normal FIT/script/environment/bootloader unchanged. Next: separately design
minimum-interface qualification with explicit wait/command-sent phases and
ultimately a no-reset patched positive control. Pre-AudioTop access is not
qualified, so do not advance to no-logo or add setup after this timeout.
Patch-loss location and automatic warm recovery remain unresolved.



**October 22: next reset/logo/AudioTop diagnostic PREPARED OFFLINE; board OFF;
no capture armed.**
[Design/runbook](hdmi-dsp-boundary-design-2026-10-22.md),
[build/tests](hdmi-evidence/2026-10-22-dsp-boundary-preparation/README.md).
Use `build/hdmi-dsp-boundary-2026-10-22/candidate/`: FIT SHA-256
`bbadfaaa28b299ee6d4d4e514e9d38c2f11e180b7f8171aaeaca1d289e171a83`,
kernel `6.18.38 #4`. Both arms share one FIT/DT; display and CPU_COMM are
now disabled to prevent premature logo-free MMIO. Existing TVFE hold and
shutdown guard unchanged; new opt-in `h713_dsp_boundary=1` publishes the
73-step observer. It attempts versions before AudioTop writes, then after
control/config/latch individually, with four separate claim/read/release/
check pairs. The no-logo prefix adds conditional display/TVCAP reset
release and proven routing words, with readbacks/original-state records.
**One-logo first** qualifies the new pre-AudioTop access; no-logo needs a
separate fully disconnected cold cycle/fresh patched baseline. Stop if the
lock is unwritable or a new access stalls. After any request timeout only
current-pair skip/release/final is permitted, never later setup/requests.
Host loader validates arm history and RAM image/hook checks; binder creates
boot/FIT/baseline-bound proof before helper steps. Generic warm census is
still unsafe. All four pairs, interventions, journal and UART are exported.
Real kernel/modules build has no warnings; FIT extraction, exact DT edits
and unchanged symbol versions verified; 11 new tests +48 regressions pass.
No board access/staging occurred. Pre-AudioTop access remains exploratory:
completed zeros do not prove DSP RAM contents through an unqualified
interface. Reset+early boot/access preparation remain one bracket even if
zero precedes logo/setup; all-negative outcomes may remain inconclusive.
Disabled display means no DRM panel-shutdown callback: lamp stays off and
physical disconnection follows poweroff. Previous bench guard stays
installed with original backup preserved. No automatic recovery relaxation.



**October 22: DSP retention live diagnostic COMPLETE; board OFF.**
[Live evidence and interpretation](hdmi-evidence/2026-10-22-dsp-retention-live/README.md).
Cold production boot `96cae8c6` established DSP `0/0` → pinned patch verified
`1/1`, active owners and both domains ON. One orderly warm reset and one
successful normal warm logo preceded RAM-only diagnostic boot `9fd2d002`.
TVFE hold was eligible/applied; no TVFE power command or violation occurred.
All 46 explicit operations passed: stock lock claim/release verified, both
`0x80ff` requests completed and returned **`0/0`**, no timeout or retry.
Final hold valid, both domains ON, owners inactive. Thus patched versions did
not survive this tested warm-access path even without Linux powering TVFE
OFF. This is **not direct DSP RAM-erasure proof**: demod bus reset initially
asserted and was released; AudioTop control/config were `0/0`, requiring the
known three-step setup. Warm-logo and interface startup effects remain to
be separated before attributing first loss to reset. No new patch/graph,
DSP reset assertion, source3 relaunch or GP6/GP7 writes occurred.
UART confirms orderly `reboot: Power down` at 696.521177 s; recorder closed.
**Bench shutdown hook remains installed**, with exact original mode-0755
backup at `/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard` (also in
live evidence). Restore only after a fully disconnected cold normal boot
without retain flag and hash verification. Normal FIT/script/environment/
bootloader unchanged. Next: offline review/design to separate early warm
reset/logo/interface effects; new bench trial requires fresh cold baseline.
Automatic HDMI recovery remains unproven; production one-launch policy stays.


**October 22: next DSP-retention diagnostic PREPARED OFFLINE; board remains
shut down; no catcher armed.**
[Design/runbook](hdmi-dsp-retention-design-2026-10-22.md),
[preparation evidence](hdmi-evidence/2026-10-22-dsp-retention-preparation/README.md).
Use `build/hdmi-dsp-retention-2026-10-21/candidate-v2/`, not the prototype
`candidate/`. Bench flags verify warm latch/parked processors/open bus and
both domains ON/idle, then retain only TVFE via `GENPD_FLAG_ALWAYS_ON`.
No OFF domain is powered on. A built-in, idle-until-stepped observer provides
46 operations for clocks, conditional AudioTop preparation, stock lock and
one `0x80ff` pair; no patch/graph/reset assertion or firmware launch exists.
The separate bench shutdown hook blocks reboot/kexec on the retain cmdline
even before observation starts; RAM loader verifies its installed bytes.
Real kernel/modules build, unchanged production DTB and exported symbols,
11 new tests plus 37 regressions pass. No board installation/live action
was performed during preparation. Next live work needs a newly captured cold
patched baseline, verified hook backup/install, one orderly warm reboot,
hold proof, staged access and poweroff. Generic warm census is unsafe before
interface clocks in this held-domain boot; use the new helper's snapshots.
DSP retention is still unmeasured; read the runbook's intervention limits.

**TVFE OFF writer FOUND; diagnostic live run complete; board OFF.**
[Live trace and interpretation](hdmi-evidence/2026-10-21-tvfe-boot-trace-live/README.md).
Cold boot `d7017dce` passed DSP `0/0` → verified `1/1` with both domains ON.
After orderly warm reset, both domains were ON before the logo and at final
U-Boot sampling. Diagnostic Linux boot `73c7ebcb` kept TVFE ON through early
init and every PPU init write. At ~7.35 s, deferred-probe **`genpd_sync_state`
called the TVFE power-off callback**; the explicit `domain=TVFE hw=1 on=0`
command is bracketed by `00010000` → `00020002`. TVCAP stayed ON.
`pd_ignore_unused` suppresses the late unused sweep, **not provider sync-state**.
Full stack, exact-boot journal, source excerpts and complete kernel coverage
are curated. One warm-logo success was fully captured. Optional proper was
not installed; only a diagnostic FIT was staged separately and RAM-booted.
Orderly poweroff ended boot `73c7ebcb` with UART `reboot: Power down`.
No catcher remains armed. Next: design a narrowly scoped bench retention
policy to prevent this observation-induced TVFE OFF, then the warm DSP
version-read sequence. DSP retention and automatic HDMI recovery remain
unmeasured/unimplemented. Analyzer now accepts identical console-banner
replay; 15 offline tests pass. See the live record for limits.

**Next diagnostic PREPARED OFFLINE; board remains unpowered; no catcher armed.**
[TVFE boot trace design/runbook](hdmi-tvfe-boot-trace-design-2026-10-21.md),
[build/test evidence](hdmi-evidence/2026-10-21-tvfe-boot-trace-preparation/README.md).
`build/hdmi-tvfe-boot-trace-2026-10-21/candidate/` contains a built diagnostic
kernel FIT and optional U-Boot proper. The first run RAM-loads only the kernel
under installed U-Boot. Opt-in `h713_tvfe_trace=1` samples early Linux, PPU
probe, each original init write and power callbacks; TVFE OFF callbacks dump
their caller/stack. Both builds pass; 13 new tests and 19 regressions pass;
production DTB and exported symbol versions unchanged. Exact kernel base is
`edffad3…` (October 16 Image); historical `da2bc49…` has identical PPU source
but an older Image. Guarded RAM runner verifies warm state and loaded CRC,
sets `panic=0`, and records a fixed-duration UART log. Optional proper adds
read-only bootm cleanup samples, but is **not installed and has no new
installation/rollback package**. No live operations were performed during
this preparation. Read the runbook before requesting power.

**Codex live continuation COMPLETE; board OFF.**
[Pre-logo PPU results](hdmi-evidence/2026-10-21-warm-prelogo-ppu/README.md):
from production boot `fe51947d` (DSP `0/0` then patch `1/1`), orderly reboot
was caught before logo. After opening only bus-r-ppu, **TVFE and TVCAP were
both ON**. Both were still ON at the prompt after one logo invocation;
MIPS was parked. After direct warm-branch FIT boot, Linux boot `1889c531`
had **TVFE OFF, TVCAP ON**, no handoff/owners. Orderly poweroff recorded
`reboot: Power down`. The cold preboot capture was missed because host UART
was invisible inside the sandbox; the logo completion UART also has a gap
from the three-second silence timeout. Read the evidence limitations before
drawing conclusions. No DSP version request or TV-domain power command was
sent. **Next: instrument the interval from final U-Boot sample through
kernel PPU probe/runtime callbacks offline.** The transition is localized
to that interval in this diagnostic cycle, not yet to a specific writer.
All host UART/network operations need escalation in this environment;
verify a real `OPEN /dev/ttyUSB0` event before asking for power. No catcher
is currently armed. DSP retention and automatic warm recovery remain unresolved.

**Codex continuation: offline warm-logo review complete; pre-logo PPU probe
prepared, not run.** Operator confirmed the board is unpowered; cold catcher armed at
`build/hdmi-warm-prelogo-ppu-2026-10-21/cold-catch/`, awaiting reconnection. See
[review and next-run protocol](hdmi-warm-prelogo-ppu-review-2026-10-21.md).
All 41 curated A–C evidence hashes match. No direct ARM PPU power-off was
identified in the actual installed-build logo source; the table walker
rejects PPU addresses, but the logo runs MIPS firmware, so this does not
exclude firmware power control. `pd_ignore_unused` only excludes the late
unused-domain sweep, not every runtime-PM transition; earlier wording below
overstates that exclusion. The next measurement is before both logo and Linux.
`warm-retention-uboot.py --open-ppu-bus` now checks the expected bootcmd,
closed bus, production GP6 latch and parked MIPS, checkpoints intent, writes
only bus-r-ppu `00010001`, verifies it and reads both PPU statuses. It forbids
automatic boot and stops at the prompt. All 19 offline tests pass. **Phase D
and automatic warm HDMI recovery remain unimplemented.**

**Warm-retention test phases A–C: BOTH CYCLES COMPLETE; board OFF** (orderly poweroff from boot `4f760916`, UART `reboot: Power down`). Curated evidence: [warm-retention results](hdmi-evidence/2026-10-21-warm-retention/README.md) (raw copies remain in `build/hdmi-warm-retention-2026-10-21/`).

**Results (identical for orderly and abrupt reset):**

| Point | R_CCU PPU `0x070101ac` | TVFE | TVCAP | lock peer/own | other |
| --- | --- | --- | --- | --- | --- |
| cold preboot | `00000000` | not read | not read | — | GP6 0 |
| cold-live (production) | `00010001` | ON | ON | `0`/`0xaa` | DSP `0000/0000` → `1/1`; AudioTop `700`/`011a5e00`; DSP status `0x120` |
| warm preboot (orderly **and** SysRq-b) | **`00000000`** | not read | not read | — | GP6 latched |
| warm-parked Linux (both) | `00010001` | **OFF** | ON | `0`/**`0`** | MIPS parked, no handoff, HDMI skipped; TVTOP routed |

Interpretation:
- Both resets return the R_CCU PPU bus gate/reset to cold default.
- **TVFE is OFF after both warm boots, including the abrupt one with no
  teardown.** It is not caused by production teardown. The production
  cmdline has `pd_ignore_unused`, so Linux genpd did not do it either. It
  comes from the reset itself or from U-Boot's warm branch (logo path).
- TVCAP stays ON. The lock own word is cleared (`0xaa` → `0`) in both.
- Whether the DSP patch survives is **still not measured**: no version read
  was done, and AudioTop/DSP status were skipped because TVFE is off. If the
  DSP RAM is in TVFE, its power-down would erase the patch (inference only).

**Next steps:**
1. ~~Curate~~ done.
2. **Separate "reset powers TVFE off" from "U-Boot warm branch powers TVFE
   off":** at warm preboot, the PPU bus is closed. Options: (a) a single
   reviewed U-Boot write opening bus-r-ppu (`0x070101ac` ← `0x00010001`, the
   same thing Linux does), then read the PPU; or (b) find, offline in U-Boot
   `h713_mips.c` and the warm `h713-hdmi.scr` script, whether the warm branch
   touches the PPU/TVFE. Do (b) first, offline.
3. Design phase D (the warm version read). It now needs TVFE powered, which
   is a domain transition; extension stage P shows how. Read versions with
   the stock lock (it reads `0` in the warm-parked state).

(Historical record of cycle 2 progress follows.) Cycle 2 (abrupt) started:** operator unplugged everything; the cold catcher was armed at 02:18:27Z into `cycle2/cold-catch/`. A1 done: one SPL, `gp6=0`, R_CCU PPU `00000000`, `bootcmd` identical to cycle 1. A2 done (`cycle2/A2-*`): **board RUNNING production cold-live, boot `63bb0271-b454-494e-818e-a5cee4d56822`**; DSP `0000/0000` → `1/1`; census identical to cycle 1 A2 (both ON, routed, AudioTop baseline, DSP status `0x120`, lock `0`/`0xaa`). C1 done (`cycle2/C1-*`): guarded SysRq-b fired from boot `63bb0271`, all units active and PCMs RUNNING; UART marker `H713_WARM_RETENTION_ABRUPT_SYNC_DONE` at 88.95 s, then `sysrq: Resetting`, no teardown. C2 done (`cycle2/C2-warm-*`): one warm SPL, `gp6=48444d49`, `bootcmd` matched, **R_CCU PPU `00000000`, the same as the orderly case.** `boot` sent. Next: C3 census (label `C3-abrupt-warm-parked`), then poweroff, then curation.
Design: [warm-retention test](hdmi-warm-retention-test-design-2026-10-21.md).
Tools: `tools/serial/warm-retention-uboot.py` (U-Boot set U) and
`tools/hdmi/warm-retention-census.py` (Linux set L, read-only, streamed with
`ssh root@192.168.4.1 'python3 - LABEL' < tools/hdmi/warm-retention-census.py`).
Raw outputs: `build/hdmi-warm-retention-2026-10-21/cycle1/` (not yet curated).

**Board state at last update: OFF** after cycle 2 (orderly poweroff from boot
`4f760916`). Cycle 1 ended with an orderly poweroff from warm boot
`4062c792` (`cycle1/end-poweroff-*`). Earlier in
cycle 1 it ran normal production cold-live as boot
`f5c76641-c095-4f6f-ac7b-03f92ddb493b` (HDMI handoff present; capture,
signal and speaker active; h713_ddc_pins/hdmi_audio/hdmi_receiver/hdmi_signal
loaded). A passive UART recorder (`soak-capture.py`, 60-minute deadline from
about 19:04 local) may still hold `/dev/ttyUSB0`. Make sure no other reader
holds the port before arming a catcher (`fuser /dev/ttyUSB0`). If the
recorder is still alive it belongs to the previous agent; stopping it loses
nothing.

Done so far in cycle 1:
- **First attempt aborted:** the board booted before the catcher opened, and
  GP6 was still `48444d49` (not a cold start). Its log is in
  `cycle1/cold-catch/` and `passive-after-abort.log`. The operator cut power.
- **A1 cold catch** (`cycle1/cold-catch-2/`, `cycle1/A1-cold-preboot/`): one
  SPL, `gp6=0`. Set U: **R_CCU `0x070101ac` = `00000000`** (PPU bus closed, so
  the PPU was not read, as designed). `bootcmd` recorded in
  `cycle1/bootcmd.txt` (sha256 `b88572b5…`). Then `boot`.
- **A2 cold-live** (`cycle1/A2-health.txt`, `cycle1/A2-census.json`): journal
  `DSP versions 0000/0000`, then `pinned 724-pair DSP patch verified versions 1/1`.
  Census: MIPS status 1; R_CCU PPU `00010001`; PPU TVFE/TVCAP `00010000` (both
  ON); TVTOP production routing (`fff11111`/`1`/`00011111`/`11111111`/
  `00001111`/`fff000ef`/`11111111`); AudioTop `700`/`011a5e00`; DSP status
  `0x120`; **lock peer `0`, own `0xaa`** (the lock works MIPS-live).
  - The first census attempt failed before any read (a binary DT property was
    decoded as text). The census was fixed to use an existence check and
    rerun; the failed attempt is kept as `A2-census-attempt1-unicode-error.txt`.

- **B1** (`cycle1/B1-reboot-request.txt`, `cycle1/B2-warm-catch/`):
  `systemctl reboot` from boot `f5c76641` with all units active; UART
  `reboot: Restarting system` at 124.5 s; one warm SPL; `gp6=48444d49`
  (latch, as expected), MIPS 0 at preboot.
- **B2 warm preboot** (`cycle1/B2-warm-preboot/census.json`): `bootcmd`
  matched the cold record. **R_CCU `0x070101ac` = `00000000`**, the same as
  cold preboot and not the `00010001` Linux had before the reboot. **The
  orderly warm reset returned the R-domain PPU bus gate/reset to cold
  default.** The PPU was not read, as designed. This shows the R_CCU was
  reset; it does not by itself prove the TV power switches dropped. Then
  `boot` was sent; the board should be booting the production warm branch.

- **B3 warm-parked** (`cycle1/B3-census.json`, boot `4062c792-2301-44df-84c7-22235e7b9162`):
  MIPS parked (0), no handoff, HDMI units inactive, no h713 modules. R_CCU
  PPU `00010001` (reopened by Linux). **PPU TVFE `00020000` (OFF), TVCAP
  `00010000` (ON)**; both were ON in A2. TVTOP fully routed by the warm logo
  path. **Lock peer `0`, own `0`**: own was `0xaa` before the reboot, so it
  was cleared across reset and logo, and it reads like functional storage
  again (not the logo-free all-ones). AudioTop/DSP status skipped by the gate
  (TVFE off).
  - **Caveat:** TVFE OFF may come from production's orderly teardown, which
    releases the receiver domain references, not from the reset itself.
    TVCAP is retained by `keep-tvcap-on`. **Cycle 2 (abrupt, no teardown)
    discriminates.**
  - The cold boot's journal was not found in the board's boot list (boot
    clock resets): `cycle1/B3-journal-boot-check.txt`. Teardown evidence is
    therefore only the B1 request plus the UART `reboot: Restarting system`.

**Next steps (exact):**
1. ~~B1~~ done. (Original instructions kept for cycle 2:) arm `tools/serial/catch-cold-uboot.py --port /dev/ttyUSB0 --output
   build/hdmi-warm-retention-2026-10-21/cycle1/B2-warm-catch` (it waits for
   the next SPL), then over SSH run `systemctl reboot`. Production teardown
   runs, and the guard permits the reboot once no HDMI owner remains. Keep
   the teardown evidence: `journalctl -b -1` after the warm boot, matched by
   `_BOOT_ID`.
2. **B2:** `python3 tools/serial/warm-retention-uboot.py --port /dev/ttyUSB0
   --output .../cycle1/B2-warm-preboot --label warm-preboot --expected-bootcmd
   .../cycle1/bootcmd.txt --boot`. **The key result is R_CCU `0x070101ac`
   and, if open, PPU TVFE/TVCAP state at warm preboot.**
3. **B3:** after the warm Linux is up (expect no handoff, HDMI units skipped,
   MIPS parked), run the census with label `B3-warm-parked`.
4. Orderly `systemctl poweroff`. No HDMI owner is loaded on the warm path.
5. **Cycle 2:** operator cold cycle; repeat A1/A2 into `cycle2/`. Then a SysRq-b
   trigger using the guarded script
   `docs/hdmi-evidence/2026-10-20-reset-controls/abrupt-reset-trigger.py.txt`
   (arm the catcher first), then C2 (set U), C3 (census), poweroff.
6. Curate both cycles into `docs/hdmi-evidence/2026-10-21-warm-retention/`,
   interpret them per the design's table, then design phase D (the gated
   warm version read).

Rules that still apply:
- Never clear GP6 or reuse GP7.
- Read `0x070010a4`/`0x07001124` only behind an open `0x070101ac`.
- Never read `0x07091xxx`.
- Never read `0x0500xxxx` without TVTOP routing.
- Never write the lock peer word.
- One step per action, retaining UART and acknowledgments.
- A cold cycle means unplugging serial and USB too, for at least a minute,
  with the catcher armed *before* reconnecting.

### Findings since the October 21 morning handoff (all committed)

- The October 21 stall cause has two parts:
  - **TVCAP is physically off and in reset at a logo-free cold boot.**
    `keep-tvcap-on` hid this from genpd; boot-v4 drops it. See the
    [extension run](hdmi-evidence/2026-10-21-dsp-access-ext-live/README.md).
  - **The `0x0500xxxx` lock window needs TVTOP routing.** See the
    [AudioTop stage run](hdmi-evidence/2026-10-21-dsp-access-at-live/README.md)
    (hard lock), the [prerequisite note](hdmi-dsp-lock-window-prerequisite-2026-10-21.md)
    and the [TVTOP stage run](hdmi-evidence/2026-10-21-dsp-access-tvtop-live/README.md)
    (fixed).
- **Logo-free, the lock words are readable but do not hold writes.** See the
  [version-stage run](hdmi-evidence/2026-10-21-dsp-access-version-live/README.md)
  and [what backs the lock](hdmi-dsp-lock-word-backing-2026-10-21.md). No
  firmware or vendor table addresses `0x0500153x`. Hence the pivot to the
  MIPS-live warm-retention test above.
- Staged audit module, helper and docs: `modules/hdmi-dsp-access-audit/`,
  `tools/hdmi/dsp-access-audit.py`, and the stage design docs
  `docs/hdmi-dsp-*-2026-10-21.md`.

## Objective and immediate assignment

Finish HDMI support for the final integrated H713 build. The user explicitly
requires **automatic HDMI recovery after warm reboot before release**. A
physical cold cycle as the normal release recovery procedure is unacceptable.
Recovery must restore live HDMI video **and audible audio**; panel/logo/console
recovery alone does not qualify.

The immediate assignment is to **localize the stall in logo-free DSP access
preparation**, then establish a safe observation path for the reset contract.
**Update:** the read-only opening prefix passed live (cold-prefix-02). The
next stage is to design and review the staged domain/clock/reset extension
(section 3 below) without power transitions taken on assumption.
A new staged initial-prefix bench is now built/tested offline; qualify it on
a fresh cold maintenance boot before designing later power/clock operations.
Do not start by implementing an assumed DSP reset or retrying the failed bench.
Automatic warm HDMI recovery is still unimplemented, and a software-only
solution has not been demonstrated.

## Current state at handoff

- Repository: `/home/chris/Projects/h713`, branch `h713-letterbox`.
- Latest live investigation: `7f256b0` — successful logo-free boot and stalled
  preparation; failed monolithic bench source: `a6b7f8c`. `b1c3c7c` committed
  the standalone handoff. The staged-prefix source and preparation evidence
  are committed as `d2f47d5`.
- **Latest live state: the read-only prefix passed and the board is off.**
  [Live runs](hdmi-evidence/2026-10-21-dsp-access-prefix/README.md):
  `cold-prefix-02` (boot `36c40861-5bd6-4d21-875a-fce2fc1811b9`, bundle v2)
  completed all 33 steps on a fresh cold boot, released its software
  resources and ended with an orderly poweroff (root remounted read-only,
  `reboot: Power down`). An earlier `cold-prefix-01` (bundle v1) passed steps
  1–9; its end was not recorded. The live guard is now `96f37655…`; the
  previous guard is backed up on the board as
  `/root/hdmi-dsp-access-audit-2026-10-21/previous-hold-guard`.
  Recheck physical state with the operator before further live work.
- **The extension passed live; the board is off.**
  [Live run](hdmi-evidence/2026-10-21-dsp-access-ext-live/README.md)
  `cold-ext-01` (boot `0c26fed5-c211-4dbd-8c68-7aa45b942bd9`, boot-v4) ran all
  82 steps of the [extension](hdmi-dsp-access-extension-design-2026-10-21.md)
  and ended in an orderly poweroff with the module loaded. It confirmed that at
  cold **TVCAP is physically off and its bus reset asserted**; under the old
  DT genpd hid this, so the October 21 bench reached AudioTop with TVCAP
  unpowered and in reset (leading stall explanation, not yet proven).
  AudioTop was not accessed there.
- **AudioTop stage run: hard lock at the lock window; the board is off.**
  [Live run](hdmi-evidence/2026-10-21-dsp-access-at-live/README.md)
  `cold-at-01` (boot `e49a6b15-5824-47a0-bffc-8b7fa78b76a8`): AudioTop
  (`0x0614a000`) and DSP status (`0x06144000`) are readable and AudioTop
  initializes to the Android baseline. A plain read of the lock word
  `0x05001530` then wedged the SoC, despite both domains, both resets and
  every clock being up. The `0x05000000` region needs a further prerequisite
  (logo/MIPS provides it in production). **Do not read `0x0500xxxx` in a
  logo-free bench until that prerequisite is identified offline.** The
  October 21 bench would have hung there at the latest.
- **Offline result:** the missing prerequisite is almost certainly **TVTOP
  routing at `0x05700000`** (U-Boot `h713_display_prepare()` writes), not
  clocks. This is the same failure as the 2026-08-07 AFBD hang. See the
  [lock-window prerequisite note](hdmi-dsp-lock-window-prerequisite-2026-10-21.md);
  the [TVTOP stage](hdmi-dsp-tvtop-stage-design-2026-10-21.md) (steps 93–104,
  then the lock read at 105–108) is implemented offline
  ([preparation](hdmi-evidence/2026-10-21-dsp-access-tvtop/README.md), bundle
  `build/hdmi-dsp-access-tvtop-2026-10-21/bundle/`).
- **TVTOP stage passed live; the board is off.**
  [Live run](hdmi-evidence/2026-10-21-dsp-access-tvtop-live/README.md)
  `cold-tvtop-01` (boot `046a1262-cc72-4d5e-b505-f174b90eccb6`): all 108 steps
  passed. Cold TVTOP is SPL-only. After the seven routing writes the lock
  words read `fffffffe` with no hang. The old bench's complete `ready` state is
  reproduced from cold with every precondition verified.
- **Version-request stage implemented offline only:**
  [design](hdmi-dsp-version-request-stage-design-2026-10-21.md) (steps
  109–119: lock claim, one-shot `0x80ff` pair, release; timeout recorded,
  not fatal), [preparation](hdmi-evidence/2026-10-21-dsp-access-version/README.md),
  bundle `build/hdmi-dsp-access-version-2026-10-21/bundle/`.
- **Version stage run: the lock word is not writable logo-free; the board is
  off.** [Live run](hdmi-evidence/2026-10-21-dsp-access-version-live/README.md)
  `cold-version-01` (boot `55a8aced-dc37-4c16-8d0d-70216e952ecf`): steps 1–109
  passed. A `0x55` write to `0x05001534` completed but read back `ffffffff`, so
  the claim stopped the run before any DSP request. Lock-word cold values vary
  per boot. Offline follow-up:
  [what backs the lock words](hdmi-dsp-lock-word-backing-2026-10-21.md). No
  firmware or vendor table addresses `0x0500153x`; the leading candidate is
  that the composition block is not running without MIPS. The note proposes
  a read-only two-state census and recommends asking the warm-reset version
  question on the MIPS-live path.
- No UART reader or pending SSH client from the failed attempt remains active.
  Do not reuse old process/session IDs.
- The last Linux boot was `4f760916-de5d-48e5-89db-d3281518da36` (warm-parked
  after SysRq-b; ended by orderly poweroff).
  Every subsequent live action needs a newly collected boot ID.
- Tracked working tree was clean before this handoff was created. Many
  historical/local untracked files remain intentionally outside commits.
  Do not bulk-add, delete or recurate them as part of this investigation.
- New `modules/hdmi-dsp-access-audit/` and `tools/hdmi/dsp-access-audit.py`
  implement a 33-step **initial read-only prefix only**, not the full access
  setup. It builds for 6.18.38, all 18 offline tests pass, and it passed live
  (above). The helper now also refuses unless the console
  threshold is at least 6 and `kernel.panic` is 0 (see below); that change
  postdates the bundle staged for `cold-prefix-01`; the next boot uses
  `build/hdmi-dsp-access-audit-2026-10-21/bundle-v2/` (helper
  `432dd643…`, module and guard unchanged), staged in a new board directory. The original failed bundle remains on disk
  and must not be retried unchanged.

Read these first, in order:

1. [Version stage live run: lock word not writable logo-free](hdmi-evidence/2026-10-21-dsp-access-version-live/README.md).
2. [TVTOP stage live run: the complete verified pre-request state](hdmi-evidence/2026-10-21-dsp-access-tvtop-live/README.md).
3. [AudioTop stage live run and the lock-window hard lock](hdmi-evidence/2026-10-21-dsp-access-at-live/README.md).
4. [Extension live run and the TVCAP finding](hdmi-evidence/2026-10-21-dsp-access-ext-live/README.md).
5. [Extension design](hdmi-dsp-access-extension-design-2026-10-21.md).
6. [Prefix live runs and what they establish](hdmi-evidence/2026-10-21-dsp-access-prefix/README.md).
7. [Staged access audit, findings and next live gate](hdmi-dsp-access-audit-2026-10-21.md).
8. [Stalled monolithic cold attempt](hdmi-evidence/2026-10-21-dsp-cold-access/README.md).
9. [DSP access rationale and experiment design](hdmi-dsp-observation-2026-10-20.md).
10. [Completion plan and release gates](hdmi-completion-plan-2026-10-20.md).
11. [Expanded clean/abrupt reset comparison](hdmi-evidence/2026-10-20-reset-controls/README.md).
12. [Warm-reset investigation](hdmi-warm-reset-investigation-2026-10-20.md).

Some historical documents/manifests say the board is running an earlier boot
or that the bench is only prepared. Those are snapshots of their dates;
October 21 evidence and the physical-off state above take precedence.

## What we know

The production policy permits one sustained MIPS/source3 HDMI launch per
physical power cycle. RTC GP6 retains the launch latch through warm reset;
the warm branch may temporarily run MIPS for logo initialization, then parks
it, omits the capture handoff and skips the HDMI services. This is intentional
fail-closed behavior, not automatic HDMI recovery.

The expanded proper-only trace sampled five MIPS/latch fields plus 22 SCP/CCU
control words. Independent cold→orderly and cold→synced-SysRq-b trials found
identical controls at proper-preboot, pre-workspace and post-logo stages.
Both warm boots parked MIPS and skipped capture. Immediate UART and SSH boot
IDs correlated the expanded trials. SysRq-b was an emergency reset, **not**
actual watchdog expiry or a hung-kernel test.

Those controls do not prove DSP patch/RAM erasure, cleared protocol locks,
receiver readiness, SCP SRAM freshness, rail discharge, or the responsible
reset domain. SPL/BL31/earlier initialization effects are still unseparated.

A direct early DSP version read was rejected as unsafe without prerequisite
access setup. The stock protocol writes a request and ARM ownership 0x55,
then releases ownership to 0xaa. A logical read changes state. Poll deadlines
cannot bound a single inaccessible-bus MMIO transaction.

The new experiment therefore boots maintenance Linux without logo/source3,
disables AFBD/display and CPU_COMM in a **RAM-only DT**, and attempts managed
power/clock/reset access setup before a separate one-shot version request.
Setup itself changes domains, resets, functional clocks and AudioTop. Even a
successful version result afterward would be **after controlled setup**, not
pristine hardware reset-entry state. Setup might erase retained DSP state;
a later retained-patch control would be needed to distinguish that.

## What happened in the latest attempt

1. The operator performed a fully disconnected cold cycle, reconnecting UART
   first and waiting before applying board power with HDMI connected.
2. The catcher recorded fresh SPL/proper and stopped autoboot before any logo
   or workspace initialization. GP6/GP7, MIPS clock/reset/status, SCP reset and
   demod bus were zero; audio functional clocks were gated.
3. All 20 guarded RAM setup commands acknowledged success. The pinned FIT
   length/CRC and embedded bootm hashes passed. The DT disabled
   `/soc/display@5600000` and `/soc/cpu-comm@3003000`, added observation marker
   `44535031`, and contained no HDMI handoff. GP6 was reserved, never cleared.
4. Linux `6.18.38` booted; UART/SSH IDs matched. CPU_COMM device was absent,
   HDMI capture/signal/speaker units skipped through their conditions, and
   no competing HDMI modules appeared. Root mounted read/write and growfs
   completed without ext4 errors or journal recovery in that startup.
5. A passive UART recorder started. Exactly one supported wrapper `prepare`
   command was sent over SSH with the expected boot ID and pinned bundle.
6. The request returned no result. A separate SSH inspection timed out; the
   board AP disappeared and the host fell back to its other Wi-Fi connection.
   UART recorded no bench message, panic, reboot, command echo or health reply.
   Ordinary serial `systemctl poweroff` also produced no response.
7. **No `versions` or `restore` request was sent.** No retry, SysRq, reset,
   source3 launch, force-unload or latch clear followed. The user confirmed
   lamp/fan off and disconnected everything. Software shutdown was not verified.

This is consistent with a board/kernel stall during pending preparation, but
**the failing instruction/stage is unknown**. Userspace lacks a flushed
before-insmod milestone. The module's first informative log is late, at
AudioTop, and it is `pr_info`: the rootfs console threshold
(`kernel.printk = 5 4 1 7`) prints only warnings and worse, so **no bench
info line could have reached the UART however far the module got**. The
empty `bench-uart.log` therefore says nothing about progress. No RCU stall
report (`pr_err`, which would print) appeared either, which fits an SoC-wide
or UART-path wedge but does not prove one. We could not retrieve phase
state, loaded-module state or flags.
Do not claim insmod completion, blame a particular domain, or infer DSP state
from missing UART output. The DSP command timeout was never exercised.

## Next steps, in priority order

### 1. Review the prepared initial-prefix experiment

The [staged access audit](hdmi-dsp-access-audit-2026-10-21.md) records the new
findings and exact live protocol. Source inspection and the exact maintenance
DT revealed a dependency to verify: `allwinner,keep-tvcap-on` initializes the
PPU driver's TVCAP genpd as already on without checking the hardware power
state in that branch. This is **not a demonstrated stall cause**. PPU probe
also changes its own reset/clock/timing controls during Linux startup, so even
logo-free samples are not pristine reset state. Do not remove the property or
power-cycle a domain speculatively.

The new prefix module loads with software/DT checks only. Separate steps
cover resource claims, control-window mappings, individual initial MIPS/SCP/
CCU/status reads, exclusive reset-handle lookup/status, and all 17 clock-handle
lookups. It stops before domain creation/resume; there are no clock enables,
reset changes, TVFE/AudioTop writes, DSP/lock reads or DSP requests. Step 9 is
the first direct register read. Clock lookup is distinct from enable; reset
lookup is distinct from deassertion. The disabled tvtop DT node still contains
the required reset descriptors and need not be enabled for those lookups.

The helper checks identities and eligibility before each action, flushes
milestones, fsyncs attempt state before load/step/release, requires both exact
next step number/name, and blocks retry after uncertainty even if the kernel
may have finished. Each next stage needs retained UART and helper
acknowledgments; do not run a stage loop. Those UART markers are `pr_notice`
and stay invisible unless the console threshold is raised first: run
`dmesg -n 7` and `sysctl kernel.panic=0` before `load` (the maintenance
cmdline has `panic=5`, which would warm-reboot past the shutdown guard on a
panic). The helper refuses to run otherwise. Steps 1–8 touch no hardware and
double as a check that markers reach the UART. The helper's fsync'd state is
on tmpfs (`/run`): it blocks retries within one boot but does not survive a
power cycle. A healthy prefix can explicitly
release software resources only; failure retains its pin/resources for cold
recovery. Successful prefix completion does not prove later access safe.

New guard source covers `h713_hdmi_dsp_access_audit`; the board's currently
installed guard does not. The pinned new bundle cannot load through its helper
until that guard is backed up, atomically installed and verified. The legacy
and new helpers mutually exclude experiment owners/attempts in the same boot.

Local prepared files are in `build/hdmi-dsp-access-audit-2026-10-21/`:
`bundle/`, `preparation.json`, `steps.json`, `dt-audit.json`, isolated `module/`
and check outputs. Committed preparation evidence is under
`docs/hdmi-evidence/2026-10-21-dsp-access-audit/`. Ten new prefix tests, three
guard tests and five legacy-helper tests pass; W=1 build/vermagic match with
the known compiler-version warning. No hardware pass is claimed.

For later extensions beyond the prefix, the following audit requirements
still apply:

Audit the no-logo DT and dependencies against production receiver/display/audio
setup. Existing production success follows source3/logo and does not establish
that the same access sequence works without it. Useful sources:

- `modules/hdmi-dsp-observe/h713-hdmi-dsp-observe.c`
- `modules/hdmi-receiver/h713-receiver-power.c` and other receiver ownership code
- `modules/hdmi-dsp-probe/h713-dsp-lock.h` and `h713-dsp-completion.h`
- `tools/hdmi/dsp-observe.py`
- Installed-kernel PPU/CCU sources in the build tree listed below.

Any later extension needs:

- Flushed/persisted userspace milestones before each preflight operation and
  before/after module loading; preserve the exact invoked command and boot ID.
- Serial-visible before/after markers around resource acquisition, each domain
  operation, individual clock/reset operations and each new MMIO boundary.
  Logging itself must be considered carefully: a queued printk is not proof
  that its preceding operation completed or that text reached the UART.
- Explicitly acknowledged stages, with no automatic continuation when an
  acknowledgment is missing. Qualify earlier prerequisites before allowing
  AudioTop, DSP status/ownership accesses or any DSP request.
- Exact source/build/module/guard hashes, preserved one-shot failure behavior,
  and passive capture armed before any live operation.

Do not simply add a timeout around the same monolithic access sequence and
call it safe. Do not reinstall or rerun the current failed module unchanged.
Build and test offline first. Keep hardware installation/launch separate from
preparation and document the scope of each proposed live stage.

### 2. Establish a fresh cold maintenance control

Coordinate physical actions with the operator. Keep FEL/OTG rescue available.
Use only one UART reader; arm the cold catcher before power is applied. Require
fresh SPL evidence and stop before logo initialization. If the catcher misses
the boundary, do not improvise a warm restart to recreate a cold baseline.

The already-tested RAM boot tools can be reused after reviewing artifact
identities; do not use the failed monolithic access setup. Use fresh
output directories, and preserve all acknowledgments. After Linux boots,
correlate UART/SSH boot IDs immediately and inspect root/journal/growfs health
**before further hardware work**. The last run ended by physical disconnection
without a verified clean shutdown. Do not run fsck on a mounted root; offline
repair, if needed, has its own recovery procedure and backups.

### 3. Qualify access, then observation

Stage/verify the new prefix bundle and extended guard after Linux health
checks. Raise the console threshold and set `kernel.panic=0`, confirm a
notice-level marker on the UART, then run `load` only and retain INIT DONE/cursor zero. Then run only
the reviewed next stage, inspect its result, and continue explicitly one stage
at a time. Stop at the first unexplained failure; preserve evidence
and use physical cold recovery rather than trying another clock/reset mix.
The present prefix stops before domain operations and has no version action.
If it passes, separately design staged domain/clock/reset and peripheral
access; check the inherited TVCAP assumption before those transitions. Only
after full access preparation is established should a separate one-shot
logical 0x80ff device-0/device-1 version pair be considered.

Then design a retained-patch comparison with explicit limits on setup effects.
A cold 0/0 result alone would not establish warm DSP erasure. Retained nonzero
words would not automatically authorize adoption or relaxing production checks.

### 4. Complete the integrated HDMI product path

Follow the full checklist below once the reset contract is established.
Offline packaging, recovery preparation and consumer development can proceed
while investigating reset, but final qualification must use one frozen build.

## Full completion checklist for finished HDMI support

This expands the [completion plan](hdmi-completion-plan-2026-10-20.md) into an
implementation and acceptance sequence. All counts/durations below are
**proposed qualification minima**, not completed passes or newly agreed user
requirements. Automatic warm-reboot recovery is the explicit user requirement.
Numeric latency/sync limits still need agreement after baseline measurement.
Track each item as pending, implemented or qualified, with candidate hashes
and evidence links; do not equate an implementation commit with qualification.

### A. Define the supported release contract

- Specify HY200 QZ713DF_A1 DDR3, native 1280×720 near 60 Hz, HDMI PCM input
  at 32/44.1/48 kHz, fixed 48 kHz stereo S16_LE capture and internal speakers.
  Measure actual source/panel cadence rather than assuming exactly 60.000 Hz.
- Make EDID and runtime format validation match that contract. Verify full
  raster, aspect, crop, color, stereo/channel order and audio-rate behavior.
- Define normal HDMI selection/exit, no-input presentation, delayed-source
  acquisition and return to console. Decide how unsupported formats fail
  clearly and safely. Do not advertise other resolutions, compressed or
  multichannel audio, HDCP/protected content, suspend/resume or LPDDR3 V2
  hardware without separate qualification. Build coverage is not hardware
  support evidence.

Deliverable: a supported-mode/behavior specification and test matrix used by
EDID, services, consumers, documentation and acceptance tests.

### B. Resolve reset state and implement automatic recovery

- Finish the staged access investigation above. Determine which required
  DSP/TVFE/MIPS/SCP/receiver state survives clean and abrupt resets and which
  initialization operations alter it. Identify a proven reset sequence or
  validated retained-state adoption contract.
- Implement bounded, observable boot decisions for cold, orderly warm and
  abrupt reset. Clean shutdown may restore/park owners; abrupt recovery cannot
  depend on shutdown having executed. Preserve guards until a proven new
  predicate safely replaces their old behavior. Do not treat clearing GP6 as
  the implementation.
- Integrate boot firmware/script, handoff, kernel owners and service startup
  under that contract. Record recovery decisions and first valid media times.
  Fail closed with diagnostics when state cannot be verified; no blind retry
  loop, duplicate firmware launch or ambiguous partial adoption.
- Review signal-init failures, concurrent stop, references and failed ExecStop
  paths. Validate any required domain/power-control change; software-only
  feasibility remains unresolved.

Acceptance: after a cold control, ten consecutive orderly warm reboots restore
moving HDMI video and audible audio automatically, with no cable reseat,
manual service restart, direct-codec priming or physical cycling. Then qualify
abrupt reset and actual watchdog expiry with active media. A Linux prompt or
panel logo is insufficient. If an essential reset path cannot recover,
finished HDMI support remains blocked.

### C. Produce one reproducible integrated candidate and exact recovery package

- Correct the saved-environment address narrowing defect through a controlled
  migration that preserves existing startup guards and rollback values. An
  offset-only code fix would stop loading the current saved environment.
- Assemble panel/reset changes, receiver/audio/signal ownership, DDC/EDID,
  speaker playback/click suppression, rootfs/ACL setup, the V4L2 bridge and
  managed video consumer. The existing startup and speaker builders create
  separate bundles; neither is a complete HDMI release image.
- Verify kernel/FIT/DTB and module ABI alignment, required configs and runtime
  dependencies, service ordering, device permissions and mixer policy.
  Provision proprietary firmware through the established local process and
  record its provenance/hash; do not publish it incidentally in the repository.
- Create one manifest: repository/submodule revisions, patches, toolchains,
  configs, SPL/BL31/proper/FIT/DTB hashes/sizes, rootfs, modules/vermagic,
  firmware, scripts, environment, units, consumers and install layout.
- Prepare and rehearse backup/install/update/rollback for the exact installed
  extents and files, preserving rescue and both environment locations. A
  combined SPL+proper build artifact is not a valid whole-image write recipe
  for this board. Prior FEL-to-prompt success is not exact rollback testing.
- Run relevant offline builder, lifecycle and refusal checks, then verify
  installed bytes. Exclude experimental access probes from normal startup.
  Freeze candidate hashes before acceptance testing; rerun affected gates
  after any change.

Deliverable: a reproducible complete package, manifest, verified rescue and
rollback package, and installation/update instructions.

### D. Integrate continuous managed video with the persistent HDMI owners

- Audit the V4L2 completion/shared-memory ABI, cache coherency, completed-frame
  ownership, buffer lifetime, sequence/timestamps and mode-change invalidation
  against the final cold/warm startup implementation. Preserve frame integrity
  and diagnostic accounting for produced/delivered/rejected/overwritten frames.
- Package the bridge and adapt the native 720p harness into a managed video
  consumer. Existing startup does not package a managed continuous video path.
  Historical preview launchers can own HPD, prepare source3 or pin older
  kernels; do not run them unchanged against a persistent session.
- Reuse existing receiver/signal ownership. Respect DRM ownership and normal
  driver APIs; do not bypass them with panel/AFBD register pokes. Bound queues,
  prefer the newest complete frame, and prevent accumulating presentation lag.
- Implement source absent/lost/returned behavior, selection/exit, client crash
  and console restoration. Run video and speakers simultaneously. ALSA capture
  is exclusive: explicitly hand over consumers for capture-analysis tests;
  those tests cannot simultaneously prove uninterrupted speaker playback.

Acceptance: at least ten minutes of native moving content with geometry and
frame-ID integrity, preserved capture/presentation timestamps, distinct physical
display-flip evidence, reported repeats/drops and sustained cadence near the
actual source rate. Verify clean stop/crash ownership, console return and
other video/display functions sharing DRM resources. Prior 360-frame runs or
eight recent frames do not close this integrated gate.

### E. Close audio startup reliability and acoustic click suppression

- Run ten independent cold-start/shutdown cycles plus the warm cycles above
  through installed services. Observe first audible output before any remedial
  action; keep source waveform/channel markers, mixer/PA settings, service
  restart counts, PCM state, DSP failure state and XRUN counters.
- Record startup and shutdown acoustics with the actual candidate/patch.
  Diagnose intermittent silence before restarting services or trying direct
  codec playback. Such intervention must leave the original trial marked
  failed. Existing click-free startup evidence does not prove shutdown is
  click-free or autonomous playback is repeatable.
- Test active-video/playback input-rate transitions 48→32→44.1→48 kHz while
  retaining fixed capture format, correct channels and fresh audio. Check
  no stale buffers, unexpected remute or XRUNs.

Acceptance: repeatable autonomous audible startup, verified startup/shutdown
acoustics including click-free shutdown, correct rate/channel behavior and
zero XRUNs under the defined supported workload. Unresolved silence or
unverified shutdown acoustics remains a release blocker.

### F. Measure and meet optical latency and A/V synchronization limits

- Establish a common source flash/beep stimulus and external observation of
  source, projected panel light and speaker sound. Correlate source frame IDs,
  capture completion, display submission/flip and optical/acoustic output.
- Measure source-to-panel and source-to-speaker latency, reporting median,
  p95, p99, maximum, repeats/drops and audio-minus-video offset over an hour.
  Define clock alignment and measurement uncertainty. Software timestamps or
  frame rate alone cannot establish end-to-end latency.
- Adapt `tools/video/av-sync-probe.c` if useful; its plane/PipeWire monitor
  observations do not measure panel optical delay and its audio assumptions
  do not directly match the ALSA speaker path.
- Agree numeric latency, jitter and A/V sync limits with the user from the
  measured baseline **before final sign-off**. Fix queueing, scheduling or
  synchronization if the resulting candidate misses them, then remeasure.

Deliverable: reproducible measurement method, agreed budgets and recorded
passes on the exact candidate. No numeric budget is currently accepted.

### G. Qualify source recovery, lifecycle, failures and endurance

Use normal installed services and the frozen build. Retain machine-readable
results plus operator visual/acoustic observations for every scenario.

| Scenario | Required work / proposed minimum coverage |
| --- | --- |
| Source availability | Cold/warm start with source connected, absent and delayed; supported source arrival automatically acquires video and audio. |
| Physical/source recovery | Ten physical unplug/replug cycles, ten software HPD cycles, source sleep/wake, reboot and blank/unblank; verify fresh moving frames and audible audio after each return. |
| Format/rate changes | Supported modes/rates, including 48→32→44.1→48 kHz during active video/speakers; unsupported input fails safely without stale output or a wedged session. |
| Client lifecycle | Repeated selection/exit, video/speaker stop/restart/crash, busy PCM and failed startup; no leaked owners, duplicate launch, broken console or hidden resource dependency. |
| Integrated soak | At least eight hours of moving video and speaker playback, all three supported audio input rates and recovery events; collect CPU/memory/temperature, queue depth, cadence, repeats/drops, XRUNs and A/V drift. |
| Update/fault handling | Missing/corrupt script or firmware, wrong kernel/module ABI, interrupted or partial bundle update and exact rollback. Validate inert/offline cases first, then controlled hardware cases with rescue prepared. |
| Power/reset | Active-media orderly poweroff, ten warm reboots, abrupt reset and real watchdog expiry; verify panel, capture, audible playback and released/restored ownership, plus root/journal health. |

Bound operations and classify failures explicitly. Distinguish source absence
from backend failure. Preserve diagnostic state and protective holds until the
new recovery contract proves an alternative; do not use repeated launches to
hide a failure. Existing one-hour audio-only or software-HPD passes do not
substitute for this simultaneous-media matrix.

### H. Final release review and handover

- Attach candidate/rollback manifests and all acceptance evidence to the exact
  revisions/hashes. Record unsupported capabilities, known limitations and
  any remaining failures. Complete items A–G; do not declare release complete
  with warm HDMI recovery, intermittent silence, acoustic validation or agreed
  latency/sync limits unresolved.
- Verify clean reproducible installation/update/rollback instructions and
  ordinary user startup/selection/exit behavior. Document diagnostics, service
  ownership, recovery decisions and safe failure handling for maintainers.
- Retest gates affected by any late packaging, kernel, firmware, environment,
  service or consumer change. A collection of historical component passes
  does not qualify a newly assembled image.

Finished HDMI support means the supported contract works autonomously on the
released integrated build, survives the defined source/client/reset events,
meets measured media acceptance limits, and has reproducible deployment and
recovery evidence. Evidence cleanup and the present reset investigation are
necessary work toward that finish line, not completion themselves.

## Hardware access and experiment boundaries

Hardware: HY200 QZ713DF_A1, Allwinner H713, DDR3. UART normally
`/dev/ttyUSB0`, 115200 baud. SSH when the board AP is running:

```sh
ssh -F /dev/null -o BatchMode=yes -o ConnectTimeout=5 root@192.168.4.1
```

Host network reconnection, when needed:

```sh
nmcli connection up uuid db33ab32-412d-410b-8e9b-9af23591e736 ifname wlan0
```

Network/device access may require the environment's permission escalation.
No passwordless host sudo is available. Prior host device ACLs should not be
assumed to survive reconnects. The board root SSH account is usable when up.

Use paced serial writes (`tools/serial/console.py`); burst writes have corrupted
commands on this board. A passive recorder must remain the sole reader if
sending through a separate write-only serial handle. `console.py --listen N`
ends after N seconds of silence, not a fixed total duration.

Do not clear GP6 (`0x07090118`), repurpose GP7 (`0x0709011c`), relax production
DSP version predicates, run the normal live-source3 DSP helper in maintenance
Linux, launch SCP to obtain observations, or bypass ownership guards. These
are not proven recovery paths. On failures, do not force-unload pinned modules
or reset/retry to escape a latched bench state.

The bench's extended shutdown guard converts reboot/kexec to poweroff while
its module is loaded. It requires a responsive kernel; it cannot rescue a bus
stall. Preparation failure is intended to retain partial holds and a module
pin, but that state could not be verified in the failed run.

## Installed artifacts and recovery details

- Installed proper: expanded controls trace,
  `2026.07-rc5-g320a17f71d41-reset-trace-cf29b4f054d9`.
  Primary write extent: **1877 sectors / 961024 bytes at LBA `0x49ac00`**.
  SHA-256: `1b1f702fc7b52adf8246b124b8fbe209b7dadc651a37e53a600689810c45302e`.
- Exact 1877-sector rollback SHA-256:
  `dffd10fe06d32e329364fe53558786bd408ad1af42e5ef7ef800aa975e479317`.
  Package: board `/root/hdmi-reset-controls-2026-10-20/`, host
  `build/hdmi-reset-controls-2026-10-20/`. The older 1867-sector rollback alone
  does not restore the expanded extent. Consult installation manifests before
  any write. No boot-media write is needed to prepare the next experiment.
- SPL/BL31/U-Boot DTB were not replaced by the expanded-controls installation;
  optional SPL trace probes were not installed. The latest RAM boot wrote none
  of these and did not save environment changes.
- **Unfixed environment defect:** configured LBA `0x49ec00` is not the active
  CRC-valid environment at `0x32ec00` inside Android super; narrowing of the
  address is documented. Preserve both. Do not save/migrate environment as an
  incidental experiment change. Controlled correction is later release work.
- Root: `/dev/mmcblk0p26`, UUID `956d9901-0eb3-4d75-bb44-e37a46ba9f40`.
  Prior offline repair evidence: `docs/hdmi-evidence/2026-10-20-ext4-repair/`;
  backups: `build/ext4-repair-2026-10-20/`.
- Bench files are staged on board at `/root/hdmi-dsp-observe-2026-10-20/`.
  **Do not run its prepare command unchanged.** Bundle identities are in the
  latest evidence's `bundle-manifest.json`.
- The live shutdown hook `/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard`
  was updated to include `h713_hdmi_dsp_observe` before the cold attempt.
  SHA-256: `365fe6c97cefb24794d5e4a315d6711b08a8a136874eebb00a08a750cc8e7de6`.
  Exact previous hook is staged as `original-hold-guard` in that board bundle;
  host copy is `build/hdmi-dsp-prelogo-2026-10-20/guard-before.sh`.
  The older `/usr/lib/h713-hdmi` bundle guard copy was not updated. This live
  hook covers the legacy observation module only. The new prefix requires a
  separately verified guard update; source preparation is not installation.

## Host files, tools and validation

All relative paths below are under `/home/chris/Projects/h713`.

- New offline prefix preparation: `build/hdmi-dsp-access-audit-2026-10-21/` (next boot: `bundle-v2/`);
  its `bundle/manifest.json` pins the new module/helper/guard. Never substitute
  the old monolithic bundle. Details/checks: `docs/hdmi-dsp-access-audit-2026-10-21.md`.
- Canonical committed live evidence:
  `docs/hdmi-evidence/2026-10-21-dsp-cold-access/`.
  `prepare.txt` is intentionally empty. `bench-uart.log` contains only the
  recorder start line. Request logs prove commands sent, not execution.
  Raw UART CR/whitespace is preserved. `sha256.json` covers curated files.
- Local preparation/raw workspace:
  `build/hdmi-dsp-prelogo-2026-10-20/`.
  Use **`boot-v3/`**, not `boot/` or `boot-v2/`: earlier versions assumed an
  unavailable U-Boot hash command or the wrong CRC byte order.
- Boot tools: `tools/serial/catch-cold-uboot.py`,
  `tools/serial/run-dsp-observe-boot.py`,
  `tools/hdmi/prepare-dsp-observe-boot.py`. They refuse existing output dirs.
- FIT: `build/hdmi-dsp-prelogo-2026-10-20/kernel-current.fit`, 7795668 bytes,
  SHA-256 `0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70`.
  Embedded DTB SHA-256:
  `4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940`.
  U-Boot lacks `hash`; offline SHA pinning, RAM CRC32 and bootm embedded hashes
  are distinct checks. CRC is not cryptographic authentication.
- Kernel build:
  `build/linux-6.18.38-da2bc49e45e531a23632a1063266bd439454e31dd383f49c502ddb793277d731/`.
  Bench isolated build: `build/hdmi-dsp-prelogo-2026-10-20/module/`.
  The local `preparation.json` records sources, headers, compiler and ABI.
- Existing checks: `tools/hdmi/test-dsp-observe.py`,
  `test-dsp-observe-boot.py`, `test-hdmi-hold-guard.py`, `test-dsp-lock.py`,
  and `test-dsp-stock-response.c`. Build and these checks passed before live
  testing. Clang 23.1.3 gave a known warning against kernel compiler 23.1.1;
  vermagic matched `6.18.38 SMP mod_unload aarch64`.
  Mock/native tests did not establish hardware access safety.
- Board wall time resets to April 13. Correlate by boot ID and monotonic kernel
  time; use exact journal `_BOOT_ID` matching rather than trusting chronological
  `journalctl -b -1` ordering. Date this investigation in host/operator time.

Keep new source changes and live evidence reviewable in focused commits.
Preserve the distinction between observed facts, hypotheses and proposed
qualification. The initial prefix now has a correlated live pass; the next
deliverable is a reviewed, staged domain/peripheral extension design.
HDMI warm recovery has not been solved.
