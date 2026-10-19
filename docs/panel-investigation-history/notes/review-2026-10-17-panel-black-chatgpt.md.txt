# Critical review and fix plan: black panel after warm reboot

2026-10-17. Review of Claude's handoff, trial README and selected raw trial
artifacts, startup generator, display dump scripts, kernel patches 0183/0184,
and `build/uboot-src-kdts/arch/arm/mach-sunxi/h713_mips.c`.
This is an offline review; no hardware commands, reboots or firmware changes
were performed. Existing unrelated working-tree changes were left alone.

## 2026-10-18: promoted into the normal build

The normal orchestrator and quick U-Boot helper now export the validated
320a17f71d41 revision, apply `patches/u-boot/series` (tested DT/regulator
prerequisites followed by the focused initial-off fix), and sync the shared
kernel DTS/bindings/generated CCU table. Content-addressed source preparation
leaves the external checkout and diagnostic worktree untouched. Tested
panel-control source and DDR3 configuration match the installed validation
build; both board profiles compile, DDR3 only is hardware-validated.

The current build/results/rollback runbook is
`docs/uboot-panel-initial-state.md`. It preserves the exact binary rollback,
separate older FEL rescue, scoped pass counts and remaining limitations.
Build integration does not flash the board; validated trial stays installed.

## 2026-10-18: initial live-media and emergency-reset validation complete

After the3cold/4warm visual passes, sampled live720p video and bounded digital
audio at48/32/44.1kHz input passed. One clean cold-start listening trial passed
without speaker restart/direct codec intervention, XRUNs0. Earlier transient
silence remains unexplained; diagnostics and waveform levels differed.

Abnormal-reset trial: synced filesystem writes, left all HDMI services and
both audio PCMs live, then immediate SysRq-b at465.752331s uptime. This skips
normal service/device shutdown. U-Boot applied new initial-off hold, committed
logo; Linux adopted720p. Operator confirms logo and console returned, HDMI
connected at both ends. Warm guard correctly leaves HDMI capture inactive.
One trial passed, not an autonomous watchdog/hung-kernel demonstration.

Initial validation set complete within these scopes; long-term reliability,
full-rate video and broader fault coverage remain unproven. Trial stays
installed with rollback/rescue available; board at visible console, serial
capture left running. Detailed evidence:
`docs/hdmi-evidence/2026-10-18-panel-initial-state-trial/README.md`.

## 2026-10-18: recoverable trial installed, three cold/warm pairs passed

User authorized trial installation. Proper4391dfa0… installed/readback verified
at0x49ac00,1867 sectors; fresh stage2 rollbackcf1941d6… saved on host/board.
SPL, environment, rescue and surrounding image tail verified unchanged.
Three independent cold/first-warm pairs with HDMI connected at both ends all
showed logo and console; an extra second warm in pair1 also passed (3cold,
4warm). Cold HDMI handoff and all HDMI services active each time; warm logo
commits and Linux720p adoption verified. Request uptimes55.54s,70.41s and
unknown in pair3 (UART kernel restart77.788714s; SSH output lost), extra warm
147.26s. No software latch clear or diagnostic TCON accesses introduced.

Eight captured startups including preliminary warm check show~3.007s from
off-state log to first logo-record completion, not electrical rail discharge.
Evidence and caveats: `docs/hdmi-evidence/2026-10-18-panel-initial-state-trial/`.
Three pairs support the fix candidate but do not prove production reliability
or the panel's exact internal failure mechanism. Live capture/audio correctness,
matched prompt second-warm, longer repetition and abnormal resets remain
unverified. Trial remains installed with rollback/rescue available; serial
capture left running. Board left at visible Linux console after third pair.

## Patch candidate prepared; hardware unchanged

Prepared `patches/u-boot/0001-h713-establish-initial-panel-power-state.patch`
against the current DT/regulator U-Boot worktree. Before logo record replay,
quiet output with the fabric safely prepared, hold/verify reset, acquire and
turn off/verify the panel supply, then explicitly wait at least3s (or a larger
DT off-on delay). Preserve stock on-side timing and the firmware-only cold
HDMI relaunch; propagate reset-release errors. This closes the first-probe/
-EALREADY timing gap rather than assuming the earlier550ms was spent off.

Fresh full AArch64 Clang build passed, as did11 native helper sequencing/failure
cases and exact patch apply/reverse/whitespace checks. See
`patches/u-boot/README.md` for baseline hashes, scope, tests and hardware
acceptance criteria. Output is separate in `build/uboot-panel-initial-state`;
no image was flashed, no persistent environment changed, and the candidate
has not run on hardware. Three seconds remains a conservative tested bench
hold, not a measured minimum or a proven production fix.

## Latest result: RAM-only pre-initialization normalization passed once

Fresh cold-HDMI session followed by first warm reboot, with PC connected/
enabled and services active. Before normal logo initialization, source-reviewed
guarded teardown established LVDS rest, reset asserted and PF6 low; checked
state, held3s, then ordinary logo init. Operator sees logo. Final720p, MIPS
reset/status0, panel supply/reset high; Linux never started. No firmware or
persistent environment writes. Evidence:
`docs/hdmi-evidence/2026-10-17-uboot-output-diagnostic/preinit-validation/`.

One startup pass is encouraging but not proof of prevention: normal startup
also passes intermittently, recently3 consecutive reproduction attempts.
Together with2 independent local recoveries and negative output/reset controls,
this supports explicit initial panel power/reset/output sequencing as a fix
candidate. The temporary generic teardown also touches AFBD/MIPS/fabric;
factor a bounded panel-specific initial-state operation for a production
candidate rather than blindly adding generic teardown. Validate independent
warm-trigger cycles with source conditions captured and verify Linux adoption/
capture functionality, cold boot and abnormal resets before claiming completion.
Derive final off timing from documentation/measurement;3s is tested conservative
bench hold, not established minimum. No permanent fix installed yet.

## Latest result: second local ordered supply-cycle recovery, stable720p

On the same black U-Boot state where output-only restart and quiet-output
reset failed, added PF6 off/on with PH16 held and outputs at rest. Supply
GPIO low-to-high interval3.253s; reset low4.761s by host UART timestamps.
Logo returned. Every before/after timing snapshot plus recovered full dump
remained720p; MIPS reset/status stayed0. Thus prior1080p readbacks are not
necessary for recovery. Two independent black U-Boot states have now locally
recovered with the compound ordered supply/reset/output cycle.

Concrete code gap: h713_disp_stock_panel_power waits550ms BEFORE first
regulator acquisition, then immediately enables it and only afterward asserts
reset. U-Boot fixed-regulator first acquisition requests output inactive;
first enable does not enforce off_on_delay_us, which is applied on successful
explicit disable. Probe-to-enable therefore lacks a guaranteed off interval.
The wait before acquisition does not establish controlled panel power-off.
Earlier acquisition by another code path and actual rail behavior must be
checked; this is a root-cause candidate, not proof of exact mechanism.

Next validate a RAM-only explicit initial off/reset/output-rest sequence
before ordinary warm-logo bring-up on fresh cold-trigger reboots, then implement
the sequence in the panel owner. Use documented/measured off/on requirements;
do not claim3s is minimum or automatically required. No firmware flash yet.
Evidence: `docs/hdmi-evidence/2026-10-17-uboot-output-diagnostic/staged-supply-cycle/`.

## Latest result: panel reset with quiet output also failed

On the same fresh black U-Boot session, after output-only restart failed,
asserted PH16 while known LVDS-output controls were at rest, held reset>=1s,
released it and restored output, with PF6 supply commanded high throughout.
Panel stayed black. Ten stages had before/after timing/MIPS/GPIO snapshots;
all timing remained720p and MIPS stayed reset. HDMI connected throughout.
Evidence: `docs/hdmi-evidence/2026-10-17-uboot-output-diagnostic/quiet-reset/`.

The main untested addition relative to earlier compound recovery is PF6 supply
interruption. Next test it on this retained black state, using the same output/
reset sequence plus3s off/on and per-boundary timing captures, without prior
latch/FIFO interventions. This is not yet proof of actual discharge or a fixed
minimum off-time. Do not assume recovered1080p readbacks are required or caused
by power cycling until the phase is directly captured.

## Latest result: isolated LVDS output restart failed, timing stayed720p

After three good reproduction attempts, the fourth fresh cold-trigger lineage
produced black at U-Boot-only hold. PC HDMI was connected/enabled during cold
session; firmware port status returned2. With no preliminary latch/FIFO/reset
experiments, isolated LVDS output tail/control/mid/route disable and exact
restore left the panel black. Timing, output, MIPS and panel GPIO snapshots
were captured before/after all eight steps. No timing values changed;720p
remained. PF6/PH16 stayed high at sampled boundaries, MIPS remained reset.
Evidence: `docs/hdmi-evidence/2026-10-17-uboot-output-diagnostic/lvds-only/attempt4/`.

Output rest/restore alone is insufficient in this state and did not cause the
prior unexplained1080p readback. The successful earlier compound rail/reset/
output sequence remains a candidate. Next isolate panel reset while output
quiet without dropping supply; if ineffective, test the ordered rail cycle
with timing captures at every GPIO/output boundary. Do not attribute the
earlier timing change to a phase not sampled at the time. Current black state
is preserved for follow-up; no subsequent recovery writes yet.

## Latest result: black captured and locally recovered entirely in U-Boot

Automated interception replicated normal reset-to-logo timing (~9.69s).
Operator confirmed black after U-Boot display initialization, Linux never
started. Good/black U-Boot snapshots differed only in scan counter among382
sampled addresses. Same-session TCON latch, forced stock FIFO reset/latch,
and panel reset alone each left black. Ordered LVDS-output rest + panel
reset/supply-off3s + power/reset/output restoration recovered visible logo,
without SoC reboot, firmware reload or HDMI interruption. Evidence:
`docs/hdmi-evidence/2026-10-17-uboot-output-diagnostic/`.

This is a local recovery candidate, not an isolated panel-power fix. The
recovered snapshot unexpectedly shows1080p timing readbacks instead of720p,
although the supply-cycle command never wrote timing. Repeated MIPS reset/
status reads remain0. Timing was not sampled after every preceding operation,
so the phase of this change is unknown; investigate banked/shadow/latch
semantics and earlier FIFO/latch effects. Do not claim identical final timing
or proof that panel discharge alone caused recovery. Next isolate output
rest/restore without a rail cycle on fresh black, snapshot timing and ownership
at every boundary, then reset while output quiet and finally ordered rail
cycle as needed. Keep the current good U-Boot state as a reference.

## Latest result: independent delayed second-reboot recovery repeated

A fresh cold-HDMI lineage (first reboot requested at cold uptime70.00s)
produced operator-confirmed black. Second warm reboot requested exactly at
black-boot uptime238.07s restored logo and console; HDMI stayed connected
and no diagnostic TCON accesses occurred. Evidence:
`docs/hdmi-evidence/2026-10-17-delayed-second-repeat1/`.

Independent second-reboot results now: delayed238.07s recovered2/2;
prompt54.58s recovered0/1. A delayed THIRD reboot at695.23s recovered in
a separate reset-count arm. Timing merits further controlled comparison,
but samples are small and no threshold or reliable workaround is proven.
Next repeat the prompt second-reboot arm on a fresh cold lineage, matching
first-reboot cold dwell near70s, and record actual second-reboot uptime.
Pre-arm a timer gated on visual black confirmation; mark missed windows
rather than calling late requests exact matches. Alternate arms and repeat.

## Latest result: longer-delay follow-up recovered after prompt failure

In the prompt-reboot lineage, the first warm boot was black; a second warm
reboot requested at black-boot uptime54.58s remained black. A third warm
reboot requested at uptime695.23s of the next black boot recovered the logo
and console. HDMI stayed connected throughout; neither recovery attempt
accessed diagnostic TCON registers. The delayed target238.07s had already
elapsed, so this was not an exact match. Evidence is in
`docs/hdmi-evidence/2026-10-17-prompt-second-reboot/`.

Timing is worth investigating, but delay and cumulative reset count are
confounded. Prior independent delayed SECOND reboot at238.07s also recovered,
so three resets are not universally necessary. Next compare prompt versus
delayed SECOND reboots on independent freshly reproduced black states,
matching cold-session dwell and reset count, alternating/randomizing order
and recording actual timing and visual state. Repeat before claiming a
minimum delay or a reliable workaround. HDMI removal and pattern writes
remain unnecessary for the demonstrated recoveries, not proven irrelevant
to every possible failure mechanism.

## Latest result: prompt second warm reboot did not recover

A new cold-HDMI session followed by warm reboot produced black. A second
warm reboot requested promptly on operator confirmation, at black-boot
uptime54.58s, left the panel black. No diagnostic TCON access or HDMI
changes. See `docs/hdmi-evidence/2026-10-17-prompt-second-reboot/`.

This contrasts with the delayed reboot-only recovery at uptime238.07s.
It shows an additional warm reboot is not guaranteed to recover black;
it motivates timing tests but does not establish a delay requirement.
Different trigger trials and reset counts remain confounders. Preserve
black, test a delayed reboot without HDMI/TCON interventions, then repeat
short/long waits with matched reset counts across independent trials.

## Latest result: reboot-only control also recovers black

The 2026-10-17 reboot-only control recovered a confirmed black warm boot
without HDMI disconnection or any diagnostic TCON accesses. The reboot
marker was at uptime 238.07s, matching the prior pattern control. Operator
confirmed logo/console returned with HDMI connected throughout. Evidence:
`docs/hdmi-evidence/2026-10-17-reboot-only-control/`.

Neither cable removal nor checkerboard/restore writes are necessary for the
observed recoveries. Waiting plus normal shutdown/reinitialization suffices
in this one control; it does not establish why. Reboot still performs the
normal display-register writes. Prior claims of irreversible black across
warm resets need re-testing with controlled boot age and reset count.
Distinguish elapsed time, additional initialization attempts and cumulative
reset effects using prompt versus delayed reboots and independent repeats.
Back-power remains possible but is not specifically supported by recovery
requiring cable removal, since that requirement did not hold here.

## Important subsequent result: HDMI disconnection unnecessary in matched control

On 2026-10-17, a confirmed black warm boot recovered after a 114.01-second
TCON checkerboard hold, verified restore, approximately 11-second delay and
warm reboot, with HDMI connected at both ends throughout. Operator never
saw the checkerboard but saw the logo and console after reboot. Evidence:
`docs/hdmi-evidence/2026-10-17-matched-no-disconnect/`.

This supersedes any inference below that HDMI interruption was required for
the recent recoveries. Pattern/restore writes, elapsed time, repeated warm
initialization or their combination can account for this control's recovery.
Back-power remains a hypothesis, not established by the unplug trials. The
next discriminating control is comparable idle time then warm reboot from
black, without pattern writes or HDMI changes; if black persists, retry the
pattern sequence on that state. Pattern hold was closely matched to the
PC-end trial, but pre-pattern boot dwell was not identical.

## Assessment

HDMI-dependent retained electrical or peripheral state is the strongest
working hypothesis. Back-power is plausible, but **back-power specifically
into the panel supply has not been established**. A cable-powered receiver,
pad or protection circuit retaining state is a different mechanism and could
leave the panel supply perfectly healthy. A clock/serializer initialization
failure remains credible too.

The evidence justifies stopping the Linux service bisection. It does not yet
justify a particular RX register write, a hardware modification, or changing
the reset source as the panel fix.

## Conclusions that need narrowing

1. **Unplugging is not a selective +5 V test.** It also removes DDC, CEC,
   TMDS connections and a ground/shield connection to the PC. HPD-low and
   host connector status do not measure those electrical conditions. E4
   shows that lowering HPD is insufficient; it does not establish the
   absence of all source-driven current or activity. Also, recovery was
   observed after *unplug plus reboot*. There is no documented
   unplug/replug-before-reboot control proving that cable removal alone
   durably clears the state.

2. **The pattern test localizes the failure to the TCON's pattern/output
   path and everything after it.** It makes framebuffer/AFBD/composition
   investigation a low priority. It does not exonerate the TCON's clock,
   output enable, latch state, reset, or serializer interface. The good
   control also changed cable presence. The pattern cannot distinguish
   missing LVDS clock from an unresponsive panel; a waveform measurement can.

3. **The register coverage is smaller than the prose implies.**
   `tools/display/disp-regdump.sh` reads TCON `0x05880000..3c`, but not the
   pattern color word at `+0x40` or FIFO status `0x05880fe0`. Its TVTOP
   range ends at `0x0570003c`, excluding the noted `+0x40/+0x44/+0x80`
   controls and FIFO reset control at `+0x88`. It omits main CCU clocks and
   resets and main PIO mux/data/pull/drive state. The R-domain dump adds
   R_CCU and bank L, not banks F/H. Identical sampled values also cannot
   rule out an unsampled status bit, a write-only latch, a transient bad
   sequence, or PLL lock failure. Do not discard the FIFO clue just because
   `0x2` also occurs on good cold starts: it is not a classifier, but the
   success of its reset sequence is still worth measuring.

4. **GPIO/regulator state does not prove panel voltage or reset delivery.**
   `regulator_is_enabled()` on a GPIO-controlled fixed supply reports its
   control state, not measured rail voltage. PF6 low for three minutes
   therefore did not prove that the panel discharged. PH16's electrical
   connection, voltage at the panel, and reset pulse relative to actual
   supply rise also need checking.

   Raw trial dumps report `panel-reset` as `in hi ACTIVE LOW`, even on the
   good control. This deserves verification, not an immediate direction
   fix: the inspected sunxi GPIO implementation lacks `get_direction`,
   and the kernel acquires the descriptor with `GPIOD_ASIS`, so debugfs
   direction can reflect software bookkeeping rather than the actual mux.
   Read the mux and measure PH16 before concluding it floats.

5. **The shutdown timings are inferred.** At approximately lines 6051–6066,
   U-Boot explicitly calls the off-timing assignment “SYMMETRY, NOT
   KNOWLEDGE”; `PanelOnTiming2 = 75` is also unaccounted for. Patch 0184's
   narrative sounds more established and still states a causal explanation
   the later trials have not confirmed. Cold register values described as
   LVDS “at rest” also do not prove electrically high-impedance lanes.
   Verify rail, reset and lane behavior, including the next U-Boot bring-up,
   before ruling out power sequencing.

6. **The cold branch contains a second display replay, not just a source
   switch.** `hdmi_launch` runs `auto ... logo`, then `mips-comm-trace`.
   The latter calls `h713_disp_run(... stock_panel_power=false,
   release_mips=true)`, replaying prologue/timing/DE/clocks on an already
   powered panel, without repeating the panel-power phase. This can alter
   clocks and output state before SetSource(3). A test omitting only
   SetSource must preserve this second replay to be meaningful. A later
   test can separate that replay from the second MIPS release.

7. **Stock parity is incomplete until observed dynamically.** No reboot
   hook in 45 kernel modules does not exclude userspace input/standby RPCs,
   firmware reactions to lost 5 V, or the running SCP's wider power policy.
   A hand-replayed R_WDOG sequence tests the watchdog, not all stock
   shutdown behavior. Trial 28 establishes that watchdog substitution alone
   is insufficient. Stock failing would establish a shared failure under
   those conditions, not prove that software sequencing is irrelevant.

## First bench session: exploit an existing black state

Preserve the current black state if available. Keep stock partitions and
the GP6 launch guard intact. Use the existing safe access paths; never ARM
read `0x07091000..0x07091fff` or `0x06940000`, and do not read gated display
blocks at an early U-Boot prompt. Avoid long lamp/fan-off intervals.

### A. Cheapest missing control

1. Enable the proven TCON pattern on the black warm boot. Observe it while
   unplugging HDMI, without rebooting or changing panel controls.
2. Leave HDMI out for a recorded interval, then replug it **before** any
   reboot. Observe the pattern at both transitions.
3. Warm reboot with HDMI attached, retaining the ordinary warm branch.
4. If still black, repeat the established recovery with HDMI absent during
   reboot to restore a known-good state.

Immediate recovery implicates a live electrical dependency or removal
event. Recovery only after a reboot with the cable reattached supports a
durably cleared state. Recovery only when booting with the cable absent
keeps a cable-dependent boot/initialization interaction in scope. A negative
result needs an interval check; discharge time is not known.

### B. Highest-value instrumented test

**Capture actual panel VCC and PH16, with PF6 disabled, while selectively
removing source power and then performing the same panel reinitialization.**
Use a suitable HDMI breakout to interrupt pin 18 separately from the other
connections, keeping ground intact. If no breakout is available, full
unplug is a useful preliminary measurement but cannot identify the conductor.

Measure at the panel-side supply, not just PF6. Prefer a scope for minimum
voltage, fall/rise time and reset ordering; a meter provides the initial DC
comparison. Record black and good controls with the same attached source.
Include accessible panel bias supplies and relevant LVDS/IO supply rails
if panel VCC fully collapses. Use appropriate high-impedance/differential
probing for LVDS; verify clock presence/frequency, differential swing and
common mode against a good boot.

| Observation | Consequence |
|---|---|
| Panel VCC remains elevated with PF6 off and falls when source power is removed | Evidence of panel back-power; establish whether discharge followed by re-init actually restores the image |
| Panel VCC collapses identically but source-power interruption permits recovery | Investigate cable-powered RX/IO state or another rail, rather than panel VCC |
| Pin-18 interruption fails, full cable removal recovers | Check remaining DDC/CEC/TMDS injection and ground effects; pin 18 was not the sole sustaining path |
| LVDS clock or differential output is absent/incorrect only in black | Focus on TCON/serializer/PLL/reset and analog supply initialization |
| LVDS output is comparable, but panel reset/power differs | Focus on panel control and its local supplies; comparable waveforms are supporting evidence, not a complete protocol decode |

A small residual voltage is evidence of coupling, not proof of causation.
Recovery must correlate with the affected rail crossing its real reset/POR
requirement. Conversely, cutting pin 18 does not guarantee all parasitic
power paths are gone: DDC/CEC may still be driven.

## Second session: isolate the trigger with controlled variants

Before each independent trigger trial, establish the same recovered initial
state, then use the existing physical-cold protocol and verify GP6. Record
source power, cable state, boot hashes, exact commands, firmware source trace,
boot IDs, elapsed times and the visual outcome. Do not count multiple warm
reboots from one bad state as independent trigger trials.

Keep Linux HDMI services disabled for the first comparison, since trial 9b
shows they are unnecessary. Give each variant a bounded, identical dwell;
restore the same final 720p timing and lamp behavior.

| Variant | Purpose |
|---|---|
| A: logo-only, as trials 20/20b/20c | Matched negative control |
| B: logo plus existing second replay/MIPS launch, omit SetSource(3) | Tests everything before source selection |
| C: full cold path with SetSource(3) | Positive trigger control |
| D: full path with cable absent until Linux is up, then attach and dwell | Separates cable presence during initialization from later exposure |

If B fails, instrument and split the second register replay from firmware
execution; do not immediately blame HDMI source selection. If only C fails,
trace the RX PHY, termination, mux, shared clock/reset and power operations
around SetSource(3). Do not limit RE to routines whose names contain “5V”.

Use targeted, known-safe register captures at stage boundaries, after clocks
are valid: before/after second replay, MIPS readiness, source switch, park,
and next warm initialization. Add the omitted main CCU/PIO/TVTOP/FIFO
controls with their access prerequisites verified. Sample scan/FIFO/lock
status over time, not just final configuration values. Avoid blind sweeps
of unknown or read-to-clear MMIO.

Run the stock reference early, alongside these tests: cold boot, actually
select HDMI with the same source, warm reboot, repeat. Capture source/panel
waveforms and serial through shutdown/startup. If stock succeeds, trace its
userspace RPCs, MIPS and SCP behavior at the transitions where our waveforms
diverge. Static similarity of ARM writes is not sufficient parity.

## Implement the fix indicated by the result

- **Retained RX/IO state:** implement a measured, bounded receiver shutdown
  sequence under its resource owner while the required clocks/firmware are
  still available; verify completion before terminal MIPS park. Keep it
  distinct from unrelated audio restoration and from changing watchdogs.
- **TCON/serializer/PLL state:** add explicit reset/disable/configure/lock/
  enable ordering in U-Boot, with bounded status checks. Reproduce recovery
  from black with cable attached before considering it fixed. Preserve bus
  access clocks while touching registers.
- **Panel sequencing:** correct the reset/power timing from measured or
  documented requirements. Verify outputs are electrically inactive during
  discharge and that reset reaches the panel throughout the required window.
  U-Boot must tolerate the inherited state; Linux shutdown alone cannot
  cover watchdog/crash resets.
- **Physical back-power without a controllable isolation path:** characterize
  the actual board connection before proposing reverse-current blocking,
  a discharge path, or isolation. A reset delay cannot fix a rail that never
  crosses POR. Retain HDMI functionality as a requirement.

First prove a diagnostic operation can recover an existing black state;
then prove it prevents the transition to black. A prevention-only sequence
that cannot recover inherited bad state needs that limitation documented.

## Acceptance and reporting

Use three independent good trigger trials only as a screening gate. The
handoff's `0.2^3 = 0.008` assumes a stationary independent baseline; it is
not the probability a proposed fix is wrong. Ten independent cold-HDMI to
warm cycles with no failures is a practical initial acceptance gate, plus
repeated warm cycles, cable absent/present, delayed attachment, source sleep/
wake, and longer HDMI sessions. Ten passes still do not establish a low field
failure rate. Test abnormal resets separately if claiming boot-time recovery.

Require visible U-Boot logo and Linux console, successful HDMI capture/audio
after cold boot, correct power/reset waveforms, no failed services, and no
regression to stock bootability. Preserve unsuccessful trials. Update patch
comments and the handoff to distinguish observations from hypotheses.

## External grounding

Back-drive is a real interface design concern: TI's
[TPD12S521](https://www.ti.com/product/TPD12S521) describes backdrive protection
and HDMI receiver detection while the receiver is powered off. TI's
[LVDS application handbook](https://www.ti.com/lit/ug/slld009/slld009.pdf)
discusses unpowered receiver input current and drivers remaining high
impedance during power transitions. These support testing cable-powered
state and electrical power sequencing; neither establishes the H713 board's
wiring, protection circuitry, or actual failure mechanism.

## Bench update: unplug/replug control, 2026-10-17

Completed the missing control; evidence is in `docs/hdmi-evidence/2026-10-17-unplug-replug/`. From a black warm boot, unplugging and reconnecting HDMI caused no visible change with the TCON checkerboard enabled. Restored normal TCON settings, then warm rebooted with HDMI connected: operator saw both logo and console. Serial confirmed warm branch, FIFO reset and logo commit. This supports clearing retained state before reboot; cable absence during reboot was unnecessary for this recovery. It is one trial, and does not isolate +5 V or exclude the pattern/restore sequence and elapsed time as co-interventions. Next useful controls are a matched no-unplug trial and selective source-power interruption with rail measurements.

## Bench update: PC-end disconnect, 2026-10-17

Evidence: `docs/hdmi-evidence/2026-10-17-pc-end-disconnect/`. Reproduced black on the second independent cold-HDMI -> warm attempt (first stayed good). Disconnect/reconnect at PC end only, projector socket untouched, caused no immediate visible recovery with checkerboard enabled. Restored normal TCON then warm rebooted with HDMI attached: operator confirmed logo and console. This makes projector-socket mechanical disturbance unnecessary for observed recovery. It implicates interruption of the source connection, but does not isolate +5 V from DDC/CEC/TMDS, ground/shield, or host hotplug behavior. One PC-end trial; matched no-disconnect control remains outstanding.
