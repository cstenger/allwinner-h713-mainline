# HDMI reset recovery handoff for Claude — October 21, 2026

## LIVE STATUS — read this first (updated continuously; newest at top)

**In progress: warm-retention test. Cycle 1 (orderly reboot) COMPLETE. Cycle 2 (abrupt) started:** operator unplugged everything; the cold catcher was armed at 02:18:27Z into `cycle2/cold-catch/`. A1 done: one SPL, `gp6=0`, R_CCU PPU `00000000`, `bootcmd` identical to cycle 1. A2 done (`cycle2/A2-*`): **board RUNNING production cold-live, boot `63bb0271-b454-494e-818e-a5cee4d56822`**; DSP `0000/0000` → `1/1`; census identical to cycle 1 A2 (both ON, routed, AudioTop baseline, DSP status `0x120`, lock `0`/`0xaa`). Next: the SysRq-b trigger (catcher armed first), C2, C3, poweroff.
Design: [warm-retention test](hdmi-warm-retention-test-design-2026-10-21.md).
Tools: `tools/serial/warm-retention-uboot.py` (U-Boot set U) and
`tools/hdmi/warm-retention-census.py` (Linux set L, read-only, streamed with
`ssh root@192.168.4.1 'python3 - LABEL' < tools/hdmi/warm-retention-census.py`).
Raw outputs: `build/hdmi-warm-retention-2026-10-21/cycle1/` (not yet curated).

**Board state at last update: OFF** (orderly poweroff from warm boot
`4062c792`, UART `reboot: Power down`, `cycle1/end-poweroff-*`). Earlier in
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
- The last Linux boot was `55a8aced-dc37-4c16-8d0d-70216e952ecf` (ended by
  orderly poweroff after the step-110 refusal).
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
