# Mechanism-focused investigation after timing controls

2026-10-17. Supersedes further timing sweeps as the primary next activity.
No new hardware experiment performed for this plan.

## What the controls actually establish

Two independent delayed second warm reboots requested at black-boot
uptime238.07s recovered the visible logo/console. One prompt second reboot
at54.58s did not; a later third reboot in that lineage at695.23s recovered.
HDMI interruption and diagnostic TCON pattern/restore writes were unnecessary
for these recoveries. Small samples do not prove a delay requirement or a
threshold. Both elapsed time and inherited hardware/software state need
measurement.

## Existing traces: concrete findings

Compared prompt failure, delayed695 recovery and both delayed238 recoveries.
All show the same ordered panel shutdown and the same logged PHY/reset/route
values. From RGB-quiesced to panel-powered-down message: prompt failure
~0.370s; delayed695 ~0.368s; delayed238 ~0.367s; repeat238 ~0.366s. These are
software-log intervals, not measurements of panel voltage/discharge.

The successful delay occurred while Linux was running with panel supply
commanded on. It did not directly extend the driver's programmed rail-off
interval. Therefore a several-minute panel discharge must not be inferred.

FIFO status also fails to discriminate: prompt failure and latest delayed
success both had status2/reset applied; an earlier delayed success had clear/
reset skipped. U-Boot completion messages do not prove the physical output.

HDMI capture/signal services have a chosen-property condition; the warm boot
has no handoff and both services were inactive. Their configured60s/30s
service timeouts are not evidence of a delayed action during these warm boots.
Other boot jobs, kernel work, clock/power policies and panel-local state remain
open. Bluetooth/watchdog/filesystem messages occur in successful and failed
traces and are not presently distinguishing evidence.

## Next activity: one instrumented black boot, no time sweep

Start capture before a physical cold cycle, verify source3 handoff and active
services, request first warm reboot at a recorded cold-session age, and obtain
visual black confirmation. Keep HDMI attached. Pre-arrange collection so
observations start early without conversational scheduling delay.

1. Capture monotonic Linux journal/dmesg, boot jobs/failed units, process and
   loaded-driver state; clock, regulator and power-domain summaries; GPIO
   ownership plus safe actual mux/data registers for relevant panel pins.
   Compare early and late in the SAME black boot and against a good boot.
2. Add only a reviewed list of safely readable display/clock/power controls:
   main CCU clocks/resets, relevant TVTOP routing/reset controls, PLL status,
   PF6/PH16 mux/data/pull/drive and known-safe FIFO/status locations. Read-only
   configuration/status tracing is now an explicit diagnostic step; it is
   separate from the completed no-access controls. Avoid clear-on-read or
   unknown registers, gated access, and forbidden ARM CPUS/INCAP reads.
3. Log available kernel clock/regulator/GPIO/power transition tracepoints and
   timestamp driver shutdown stages. Start with existing trace facilities;
   add narrow instrumentation if no existing event reveals the writes.
   Verify which driver/API paths the trace actually covers. No event in a
   trace does not establish absence of raw MMIO or firmware activity.
4. If instruments are available, capture actual panel VCC and reset at the
   panel plus LVDS clock/output, early and late while black and through the
   subsequent reboot. Compare with a good boot. Supply-enable bookkeeping
   cannot establish rail voltage, and matching digital configuration cannot
   establish waveform correctness.

These are event/state observations, not another attempt to find a magic
number of seconds. Stop repeating snapshots once a relevant change or a
useful absence of change identifies the next intervention.

## Turn an observed difference into a causal test

- If a Linux job or resource transition changes a relevant state, reproduce
  its specific operation early on a fresh black boot. Verify that it yields
  recovery with the shorter reboot age. Then suppress/delay that operation
  to test whether its absence prevents the usual delayed recovery. Preserve
  other startup/shutdown conditions.
- If panel reset/rail behavior differs, derive the sequence from the measured
  rail/reset requirements. Verify a controlled panel cycle with HDMI attached
  can recover early. Do not add a rail-off delay until actual voltage shows
  it is needed; do not claim GPIO low is proof of discharge.
- If output clock/serializer/PLL state differs, test the smallest documented/
  RE-validated reset, lock or latch operation that restores correct output.
  Keep bus access clocks valid and use bounded status checks. Prove recovery
  from inherited black, not only successful startup from cold.

If no transition is visible, localize WHERE the wait matters: after a prompt
Linux shutdown, stop at U-Boot before display initialization, wait there, then
continue ordinary boot. Do not read gated display registers at the prompt.
Recovery in that condition would show Linux running during the wait is not
required. Failure would not alone prove a Linux timer: waiting with panel
power off versus on changes the electrical experiment too. Measure or log
that difference before interpreting the comparison. A temporary U-Boot wait
need not require flashing firmware or clearing GP6.

## Fix criterion

Replace the missing operation or incorrect lifecycle dependency in its owner:
panel reset/power sequencing, receiver teardown before MIPS park, or output
clock/reset/lock ordering in U-Boot. Prefer a condition that is measured or
verified complete over an unexplained boot-age sleep. Verify early recovery
with HDMI connected, normal cold HDMI capture/audio, and both orderly and
abnormal reset behavior for the scope claimed. Repeated cycles validate the
identified fix rather than substituting for mechanism discovery.
