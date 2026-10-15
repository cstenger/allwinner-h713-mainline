# h713-hdmi-signal production-readiness review (2026-10-14)

Scope: `modules/hdmi-signal/h713-hdmi-signal.c`, `tools/hdmi/h713-hdmi-signal.py`,
`tools/hdmi/h713-hdmi-signal.service`, and the exit path of
`modules/ddc-bringup/h713-ddc-pins.c`. This was a desk review. Nothing ran on
hardware, no module was loaded or unloaded, and no target unit was changed.
Kernel claims were checked against the 6.18.38 build tree.

**Verdict:** the hold-retention logic is sound. Every failure after SCP release
keeps the receiver client, the SRAM and reset regions, and the module pin, and
the reference accounting is correct. Two gaps block "production ready":

1. The peripheral restoration proof is incomplete: the control registers are
   written but never read back (H1).
2. There is no defined policy for an `ExecStop` failure. Every failure path
   currently ends in an **unparked** poweroff, and that state has not been
   tested (H2, M1).

## Findings, most severe first

### H1. The peripheral restoration proof only covers the EDID banks

The payload's restore path (`0x4414`–`0x45ec`) does three things:
- It copies the three saved EDID banks back to `0x07091c00/1d00/1e00`.
- It **reads them back and compares** them (the `recheck0-2` loops). A
  mismatch gives `+24 = 2` and no completion marker.
- It writes back DDC control `0x1b00/1b04/1b08`, HPD `0x1014` and, when
  `+64` is set, IO `0x1020/1030/1034/1038` from META (`0x4a80`–`0x4a9c`). These
  writes are **never read back**.

ARM cannot read these registers itself, because reads in the `0x07091000`
block wedge the SoC. So `restored=Y` currently means: the EDID matches, the
SCP reached the end, the SRAM and vectors are byte-exact, and the SCP is in
reset. It does **not** prove HPD, DDC or IO state. In the old code,
`restore_sram()` then overwrote the page and destroyed the only evidence.

*Fix applied (safe):* `report()` now logs the payload status words, the META
originals and the active snapshot. It runs at ready, at setup failure, and in
`stop` before the page is restored. It reads only SCP SRAM.

*Implemented, host-verified, and **one hardware lifetime cycle passed**
(2026-10-14, [evidence](hdmi-evidence/2026-10-14-signal-lifetime/README.md)):*
the stop readback equalled the originals for all 8 registers
(`1014=7 b00=00a0a0a0 b04=07000000 b08=00606060`, IO all 0), and the source saw
the exact fixture EDID while the module was ready. It is **deployed** with
`update-signal-owner.sh` and passed an unattended cold boot
([deploy evidence](hdmi-evidence/2026-10-14-signal-owner-deploy/README.md)). Details:

- **Payload** (`make-edid-trial-code.py --verify-restore`): after the last
  restore write, and before the `+28` completion marker, the SCP reads all 8
  registers into `EDID_CHECK_OFFSET` = `0x4aa0` (META+32). Each read is a
  `lwz r4,off(r11)` / `sw` pair: 16 instructions, so the program now runs to
  0x4670 against the 0x4680 limit. Both restore paths reach the readback,
  including `skip_io_restore`. The SCP already reads every one of these
  registers in its ready snapshot.
- **Byte-identical without the flag:** the generator's default output is
  unchanged, so `build-scp-probe.py` still produces the tested probe payload.
  The signal module `#error`s against a header that lacks the readback.
- **Module:** before launch, it poisons the readback area with all-ones and
  verifies the poison; zero would collide with the legitimate original IO
  values. In `stop`, after the completion and exception checks and **before**
  `restore_sram()` or any release, it requires readback == META for all 8
  registers. On a mismatch it returns `-EIO` and leaves `failed` with every
  hold kept. `report()` logs the readback beside the META originals.
- **Strict equality is justified by the probe evidence:** over 300 runs,
  values the payload wrote read back unchanged, except that `0x1b00`/`0x1b08`
  bits 31:24 read 0. The META originals are themselves read values, so their
  top byte is already 0. The IO registers read back their written 3/0/0x18/0x18
  values exactly.
- **Host test** (`test-edid-trial-payload.py`, class `Readback`): an OR1K
  interpreter runs the generated payload against a simulated receiver register
  file, from launch to ready to stop to completion. It checks:
  - readback == META, and all registers and EDID banks are restored;
  - a dropped restore write to 0x1014, 0x1b04 or 0x1038 is caught at exactly
    that register's slot;
  - the default payload writes no readback.

  Two generator mutants both fail the tests: readback placed before the IO
  restore, and a swapped register order.
- **Remaining risk:** a register with a volatile status bit would cause a false
  terminal failure. Such a failure fails safe: holds are retained and a cold
  cycle is needed. One bench lifetime (load, stop, `rmmod`) should confirm that
  the `stop` readback line equals the `original` line before this replaces the
  installed module. The procedure is in
  [hdmi-signal-lifetime-bench.md](hdmi-signal-lifetime-bench.md), with the bundle in
  `build/signal-lifetime/`.

### H2. ExecStop-failure policy: adopted, guarded, and bench-validated

**How a failure plays out.** When `h713-hdmi-signal.py stop` fails during
shutdown (a busy PCM, a refused `stop`, incomplete restoration, or a failed
`rmmod`):
1. systemd marks the unit failed and continues.
2. The backend refuses to park ("signal owner/helper must restore and stop
   before backend shutdown"), so the DSP/TVFE restoration, MIPS park and
   receiver release do not run.
3. The final stage runs with MIPS live, the receiver held, and possibly the
   SCP still asserting HPD.

M1 and any backend failure end in the same state.

**Board facts that shape the policy:**
- `h713-off` (a systemd-shutdown hook) switches the lamp, and so the fan, off
  **only** for `poweroff`/`halt`.
- systemd-shutdown hooks run in parallel at the very end, with root
  read-only and journald stopped.
- `RebootWatchdogSec=16s` warm-resets the SoC if the final stage stalls.
- The journal is persistent (`/var/log/journal`), so the failure messages
  from the earlier phase survive. Read them by boot ID; the RTC is wrong, so
  relative `-b -1` can pick the wrong boot.

**Policy (adopted 2026-10-14):**
1. **Fail closed and never tear down partially.** This was already true: each
   step requires the previous one.
2. **Shutdown is never blocked by a hold.** A powered-off board is the safe
   state, and removing power is the recovery.
3. **Retained holds make reboot and kexec into poweroff.** By the existing
   hardware rules, a retained hold needs a physical cold cycle, and a warm
   reset cannot give one. Whether R_CPUCFG and the SCP survive a warm reset is
   also unverified. This applies to `reboot fastboot`/`bootloader` too.
   - **Trade-off:** on a sealed unit, recovering from such a failure needs a
     mains power cycle, which the hardware rules already require.
   - The 16 s reboot watchdog remains a warm-reset fallback if the final stage
     itself hangs.
4. **Record:** the earlier failure messages are in the persistent journal.
   The guard also logs to `/dev/kmsg` and `/dev/console` (serial).

**Implemented:**
- `tools/hdmi/h713-hdmi-hold-guard` is installed as
  `/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard` by
  `update-signal-owner.sh` and `install-startup.sh`. It decides from actual
  state: whether any of `h713_hdmi_signal`, `h713_ddc_pins`, `h713_scp_probe`,
  `h713_hdmi_audio` or `h713_hdmi_receiver` is still loaded. Clean terminal
  parking removes all five, and the receiver/audio modules are only ever
  `insmod`ed by the session. So the guard covers every failure path,
  including backend failures, without relying on markers.
  - With holds, `reboot`/`kexec` becomes `h713-off poweroff` (lamp off), then
    `systemctl --force --force poweroff`.
  - `poweroff`/`halt` only log.
- Host tests (`test-hdmi-hold-guard.py`) cover all five holds against each
  verb, and clean state against every verb. Three mutants are caught.
- `check-startup.sh` now requires the guard to be installed.
- Deployed 2026-10-14
  ([evidence](hdmi-evidence/2026-10-14-hold-guard/)). A live dry run against
  the real `/sys/module`, with lamp-off and poweroff stubbed, named the four
  loaded holds. It only logged for `poweroff` and converted `reboot`.

**Both bench runs PASSED (2026-10-14/15, operator watching):**
- [Run 1](hdmi-evidence/2026-10-14-hold-guard/run1-poweroff/README.md):
  forced failure, then `poweroff`. The stop refused, the backend refused to
  park, and the board made its **first unparked poweroff**: lamp and fan off,
  no reboot or watchdog reset.
- [Run 2](hdmi-evidence/2026-10-14-hold-guard/run2-reboot/README.md): the same
  failure, then `reboot`. The journal reaches `reboot.target` and "Shutting
  down", but the board **stayed off** with lamp and fan off. Its access point
  was still absent almost 5 min later, so the guard converted the reboot.

The next cold boot after each run verified clean.

Both runs used `tools/hdmi/run-hold-failure.sh`:
- **Run 1:** `inject poweroff`.
- **Run 2:** `inject reboot`.

Each run starts a transient recorder unit ordered `Before=` the signal unit,
so at shutdown it still holds the PCM when the signal stop runs. This is the
realistic failure. On the following cold boot, `verify` proves from the
injected boot's journal that:
- the stop refused;
- the backend refused to park;
- nothing was restored or parked;
- shutdown reached its final stage.

**Still not exercised:**
- a hang in the final stage, which would hand over to the 16 s watchdog's warm
  reset;
- the reboot-to-fastboot variant;
- a sealed-unit recovery without a bench operator.

### M1. A clean pre-launch init failure left DDC held: fixed (wrapper), host-verified

If `insmod h713-hdmi-signal.ko` fails before SCP release, the kernel has
already reverted everything: the SRAM restore is verified and the receiver
client is released. The failures are `-EAGAIN`, `-EBUSY`, an SCP that is
already running, or an SRAM readback mismatch. Before the fix, the wrapper
then left the DDC helper loaded and `OWNED` set. The unit was `failed`, so
systemd never ran its `ExecStop`, DDC stayed held until poweroff, and the
backend refused to park. The H2 guard made that outcome safe, but it remained
an avoidable unparked shutdown.

*Fixed (2026-10-15):*
- `h713-hdmi-signal.py start` writes a per-boot latch,
  `/run/h713-hdmi-signal/attempted`, **before** the first hold. This also
  fixes the L3 ordering point.
- If the signal `insmod` fails and the module is absent, it unloads the DDC
  helper, clears `OWNED`, and reports "refused before SCP release; nothing
  retained". The backend can then park normally.
- The latch still refuses a retry on the same boot. Only a complete stop
  removes it, so restarting after a clean stop works as before.
- Every hold is kept in these cases:
  - the module is still present after a failed `insmod` (an init that
    returned 0 with `failed=Y`, or an `insmod` that never finished);
  - the DDC unload fails, which is reported as "DDC retained".

  An `insmod` timeout is not treated as a refusal.

*Verification:*
- **Host:** `test-hdmi-signal.py` has 14 tests. They cover:
  - releasing DDC so the backend can park, with a no-op unit stop afterwards;
  - the latch refusing a retry;
  - ownership kept when the DDC release fails;
  - every hold kept when the module stays loaded;
  - the latch being written before the DDC `insmod`;
  - a restart after a complete stop.

  Five mutants are caught.
- **Hardware:** deployed with `update-signal-owner.sh`
  ([evidence](hdmi-evidence/2026-10-15-m1-wrapper-deploy/)). The next boot's
  start and shutdown exercise the new wrapper's normal path. The refusal
  branch itself has **not** run on hardware: no clean pre-launch failure can
  be triggered under the service without a test-only module. Its hardware
  action, `rmmod h713_ddc_pins`, is the same step as the normal stop, which is
  validated.

### M2. User-session capture consumers and the closed-check/stop race: fixed (hardware-verified)

**The problem:** `h713-hdmi-capture.service` is deliberately
`After=user@1000.service`, so at shutdown the signal unit stops while the
user session still runs. WirePlumber publishes the HDMI capture as **the
default source** ("H713 HDMI Input Stereo"). Any client recording from the
default input (a browser, `pw-record`, a voice app) therefore makes the
user's PipeWire hold the PCM. That made the stop refuse, which ended in the
H2 guarded, unparked poweroff. Separately, the wrapper checked "status
closed" and only then wrote `stop`, so a consumer could open the device in
between.

**Fixed (2026-10-15)** in `h713-hdmi-signal.py stop`:
- **Exclusive hold.** The wrapper opens the single capture substream
  `O_NONBLOCK` and holds it across the `stop` write and its checks,
  releasing it before `rmmod` (in a `finally`).
  - `EBUSY` means a consumer has the device, which is the existing refusal.
  - `EAGAIN` means the graph isn't ready, so nobody can capture.
  - Any other open now fails, or, if it is a blocking open, waits until the
    source is gone. This replaces the status check.
  - `pcm_open` has no hardware effect. `pcm_close` only rewrites the inert
    stream registers, as every consumer's close already does.
- **Reclaim at shutdown only.** When `systemctl is-system-running` reports
  `stopping`, the wrapper sends SIGTERM to the processes holding *this*
  device, waits up to 5 s, then sends SIGKILL with 2 s more, before taking
  the hold. systemd would kill those processes moments later anyway.
  - On a running system, a stop with a consumer still refuses: user apps
    are never killed there.
  - A failed owner never reclaims.
- **Bench-only knob.** A runtime file, `/run/h713-hdmi-signal/no-reclaim`,
  keeps consumers alive so H2's busy-PCM injection still fails;
  `run-hold-failure.sh inject` sets it.

*Verification:*
- **Host:** 26 wrapper tests. They cover:
  - the hold taken before and released after the stop, including after an
    incomplete restoration;
  - no killing on a running system;
  - SIGTERM, then SIGKILL escalation;
  - the knob;
  - a failed owner;
  - a busy device whose holder can't be seen;
  - a graph that isn't ready.

  Six mutants are caught.
- **Hardware**
  ([evidence](hdmi-evidence/2026-10-15-m2-consumers/README.md)): `pw-record`
  ran through the user's PipeWire and kept capturing past the signal stop.
  The shutdown logged "closing HDMI capture consumers [328]" (PipeWire, which
  released on SIGTERM), then restored, returned DDC, parked MIPS and powered
  off. Next-boot `verify` passed.

*Not covered:* a consumer that reopens faster than the reclaim loop can
catch it. The hold then refuses and the H2 guard handles it.

### M3. DDC pins: fallible release, DT pin states, exact io_disabled restore (hardware-verified)

**Before:** `h713_ddc_pins_exit()` was `void`. A failed idle restore was only
logged, and ownership was released anyway: the module-static maps forbid
skipping cleanup in exit. The idle state, `gpio_in`, was also assumed to be
the original.

**Fixed (2026-10-15):**
- The helper now holds a self-reference from a verified claim until a
  verified release. Restoration is an explicit `release=1` parameter that
  returns the pinctrl error and keeps the module pinned on failure. `rmmod`
  without a release is refused, and exit only drops bookkeeping.
- It reads the PL8–15 mux register (`0x07022004`; read only, since PL9 is the
  IR receiver):
  - at load, recording `original_mux`;
  - after claim, requiring all six fields to read DDC (`222222`);
  - after release, requiring `000000` and recording `released_mux`.
- A `held` flag under a lock prevents a release before or during init.
  Without it, `insmod … release=1` would dereference NULL.
- The wrapper's `release_ddc()` writes `release=1` before `rmmod`. On
  failure it keeps the helper and the ownership record. A helper without the
  parameter is removed directly, which kept the upgrade boot working.
- `run-detection-trial.py` also releases first.

**Verification:**
- **Host:** 17 wrapper tests, including a failed restore keeping DDC and
  ownership and the old-helper fallback. Three mutants are caught. W=1 build
  clean.
- **Hardware** ([evidence](hdmi-evidence/2026-10-15-ddc-release/README.md)):
  - The bare `rmmod` was refused.
  - The release read back `000000`, and the live register became `0x0000003F`
    with the IR pin unchanged.
  - The unit stopped `inactive success`.
  - The upgrade poweroff exercised the fallback.

**Measured gap, then closed (long-term fix, same day):** the pre-claim mux
was `ffffff`, meaning all six pins were 0xF, "disabled", which no pinctrl
function could select. The fix:
- Kernel patch `0178` adds `io_disabled` (0xF) to every R_PIO pin.
- `0179` moves the pins into the board DT as an `h713-lab,ddc-pins` node:
  `default` = `s_twi0/1/2`, `sleep` = `io_disabled`.
- The helper is now a platform driver for that node. It records the original
  mux before binding, the claim is applied by the driver core, and release
  selects `sleep` and requires `ffffff`.

On hardware (kernel FIT `68c0b730…`,
[evidence](hdmi-evidence/2026-10-15-ddc-dt-pins/README.md)): the claim read
`222222` with the pins owned by the DT device, and the release read
`ffffff`. The live register returned to `0xFFFFFF3F`, bit-for-bit the
pre-claim state.

The first boot of the new FIT stopped at U-Boot, because the guarded startup
script still pinned the old FIT and FDT sizes. That stop was safe: it
happened before any launch. `build-startup.py` now derives those guards from
one constant and refuses to build against a different `build/out` kernel.

### M4. Post-release init failures: undone from proven states (hardware-verified)

Previously, init set `failed` without resetting the SCP, and `stop` always
refused, so any post-release failure held everything until a cold cycle. At
shutdown that ended in the H2 guarded unparked poweroff.

**Fixed (2026-10-15; policy approved):** `stop=1` on an init-failed owner
reads the payload's own SRAM words and undoes the failure only from proven
states:
1. **Late ready** (code 1): the normal cooperative stop, with readback ==
   originals.
2. **EDID mismatch** (code 2): the payload ran its own full restore, and the
   readback equals the originals.
3. **`data_failed`** (code 3): the header check failed before any receiver
   write, and the readback is still the launch poison.

Each undo asserts SCP reset and restores SRAM and vectors byte-exactly. Other
states refuse without touching anything, and once an attempt begins acting
any failure is terminal.

The wrapper attempts the recovery at `start` itself, under the exclusive
capture hold. On success it removes the module and releases DDC, so nothing
is retained. The per-boot latch still forbids a retry.

Bench builds (`-DH713_SIGNAL_FAULT_INJECTION`) add `fault=1|2` to inject
`data_failed` and the mismatch. Production builds contain neither.

*Verification:*
- **Host:** the OR1K simulator classifies both injected faults as intended,
  with no receiver registers left changed. There are 29 wrapper tests, and
  four mutants are caught.
- **Hardware**
  ([evidence](hdmi-evidence/2026-10-15-m4-recovery/README.md)): `fault=1`
  was undone from state 3. `fault=2` was undone from state 2, after the
  payload's own restore ran on hardware with readback == originals. After
  each, nothing was held and the DDC register read `0xFFFFFF3F`. The
  following poweroff parked MIPS normally.
- Late ready (state 1) shares the normal stop path but was not injected.

### L1. Concurrent `stop` writes and state reads: no torn state is observable (verified)

- `param_attr_show()` and `param_attr_store()` both hold `kernel_param_lock(mod)`
  (`kernel/params.c:570,587`). The transient `failed=Y` inside `stop_signal()`
  and its ~150 ms poll are therefore invisible to sysfs readers, and two
  writers are serialized.
- The only window where `signal_lock` matters is init. Module param sysfs
  exists before `init` runs (`mod_sysfs_setup` at `kernel/module/main.c:3497`
  precedes `do_init_module` at `:3516`), so `stop` is writable during init.

*Fix applied:* init now publishes `ready`/`failed` under `signal_lock`. That
gives `stop_signal()`'s mutex acquire a matching release.

### L2. Module and receiver reference accounting is correct (verified)

- **Success:** the module pin is +1, and there is one receiver client.
- **Successful stop:** releases exactly one client, guarded by `receiver_owned`,
  then calls `module_put`.
- **Init errors before release:** each returns through exactly one release
  path:
  - `client:` for errors before the regions are requested;
  - `release_resources()` for errors after they are requested.
- **Failed SRAM restore before launch:** keeps the client and takes the pin.
- **`module_put()` before `mutex_unlock()` inside the param callback:** safe.
  A concurrent `rmmod` runs `exit` (where `restored` is already true), and
  `free_module()` → `mod_sysfs_teardown()` waits for the kernfs active
  reference of the in-flight store.
- **Forced unload:** `CONFIG_MODULE_FORCE_UNLOAD` is off, so `rmmod -f` cannot
  bypass the pin.
- **Partial `ioremap` failure:** this calls `iounmap(NULL)`, which is a no-op
  with arm64 generic ioremap.

### L3. Other minor wrapper and unit points: all resolved (2026-10-15)

- **Ownership before the first hold (fixed).** `start` now writes both the
  `attempted` latch and `OWNED` **before** the DDC `insmod`. No hold can exist
  that this service cannot later prove it owns. A failed DDC `insmod` leaves
  only the records: `stop` is a no-op and a retry is still refused (tested).
- **Restored but not removed (fixed).** `start` now reports "already restored
  but not removed; run stop to finish (no hardware holds)". `stop` on an
  owner that is already restored goes straight to `rmmod`, with no reclaim,
  no capture hold and no rewrite of `stop` (tested, including during
  shutdown).
- **Same-boot relaunch (now an evidenced claim).** A complete stop clears the
  latch, so a restart relaunches the payload. On hardware this has run 3
  times on one boot: the installed owner and two bench faults
  ([M4 bench](hdmi-evidence/2026-10-15-m4-recovery/README.md)). The
  lifetime bench ran a stop and a second launch. Every restoration was
  byte-exact. The wrapper test `test_start_after_a_complete_stop_is_allowed`
  pins the behaviour.
- **R_CPUCFG write (fixed).** `restore_sram()` now does read-modify-write of
  bit 0 only and verifies it. It warns if other bits changed since init,
  instead of writing back the init-time snapshot. **Confirmed on hardware:**
  `0x00000001` while the SCP ran became `0x00000000` after the stop, with no
  warning ([evidence](hdmi-evidence/2026-10-15-l3-cleanup/README.md)).
- **Vector delay slot (documented).** A comment at the validation step says
  that only the jump word is written, and that the stock table's `nop` delay
  slot is required.
- **Unit ordering (verified, no change).** `Requires`+`After` the backend
  means the signal stops first. The matching `Condition` means a skipped
  backend cannot leave the signal running. The 20 s subprocess timeouts fit
  inside the 30 s stop timeout.

## Changes made in this review

| File | Change |
|---|---|
| `modules/hdmi-signal/h713-hdmi-signal.c` | `report()` logs status, META originals, readback and the active snapshot at ready, at setup failure, and before the stop restore. Init publishes `ready`/`failed` under `signal_lock`. H1: verified readback poison before launch, readback == META required before any release, and a build `#error` without the readback header. |
| `tools/hdmi/make-edid-trial-code.py` | H1: opt-in `--verify-restore` post-restore readback at 0x4aa0. The program is wrapped in `build()`. Default output is byte-identical. |
| `tools/hdmi/test-edid-trial-payload.py` | H1: OR1K payload simulator with 3 tests (clean readback, dropped write caught, default unchanged). |
| `tools/hdmi/h713-hdmi-hold-guard`, `test-hdmi-hold-guard.py` | H2: systemd-shutdown guard that turns reboot/kexec into lamp-off poweroff while HDMI holds are retained. |
| `tools/hdmi/update-signal-owner.sh`, `install-startup.sh`, `build-startup.py`, `check-startup.sh` | H2: the guard is shipped, installed into `system-shutdown/`, and required at startup. The updater scope now includes the guard and `install-startup.sh`, and backup directories are unique (`mktemp`). |
| `tools/hdmi/h713-hdmi-signal.py`, `test-hdmi-signal.py` | M1: per-boot `attempted` latch written before the first hold. A clean pre-launch init refusal releases DDC, so the backend can park. |
| `modules/ddc-bringup/h713-ddc-pins.c`, wrapper `release_ddc()` | M3: pinned until a verified, fallible `release=1`. Mux register readback proves the claim and the release, and records the original mux. |
| wrapper `reclaim()`/`hold_capture()`, `run-hold-failure.sh consumer` | M2: exclusive capture hold across the stop; shutdown-only reclaim of capture consumers; `no-reclaim` bench knob; consumer bench mode. |
| module `classify_init_failure()`/`recovery`, wrapper `recover_init_failure()`, `run-signal-fault.sh` | M4: proven-state recovery of post-release init failures, bench fault-injection build and script. |
| `tools/hdmi/run-hold-failure.sh` | H2: bench failure injection (busy PCM ordered to outlive the signal stop) and next-boot journal verification. |
| `tools/hdmi/run-signal-lifetime.sh` | Self-checking bench lifetime cycle through a runtime-only drop-in ([procedure](hdmi-signal-lifetime-bench.md)). The wrapper also gained `--bundle`, which has a test. |
| `modules/hdmi-signal/README.md` | Build command uses `--verify-restore`. Describes the readback proof. |
| `modules/ddc-bringup/h713-ddc-pins.c` | Exit claims restoration only on success, and says so when it releases ownership despite a failed restore. |
| `tools/hdmi/h713-hdmi-signal.py` | A refused `stop` write gives "signal stop refused (…); holds retained" instead of a raw `OSError`. The probe and graph paths are now patchable constants. |
| `tools/hdmi/test-hdmi-signal.py` | 4 → 10 tests: start ordering (`OWNED` and DDC before SCP release), idempotent start, post-release failure retention (no `stop`, `rmmod` or retry), latch after a refused `insmod`, competing helpers and an unready backend, a refused `stop` write, and DDC-only stop. |

Verification:
- `python3 tools/hdmi/test-edid-trial-payload.py`: 4 pass. The two H1
  generator mutants fail. The regenerated signal header comes from the
  fixture EDID with `--verify-restore`.
- `python3 tools/hdmi/test-hdmi-signal.py`: 10 pass. Each new test was
  mutation-checked: six wrapper mutants each fail at least one test.
- `test-build-startup.py` (5) and `test-hdmi-session.py` (19) still pass.
- Both modules build cleanly with `W=1` (`LLVM=1`, arm64, 6.18.38).

The rebuilt `.ko` files are **not** the installed bundle. The C changes are
logging and locking only, but they still need one on-target load/stop cycle
before they replace the validated build.
