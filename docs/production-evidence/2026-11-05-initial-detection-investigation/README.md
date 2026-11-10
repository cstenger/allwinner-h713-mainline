# Initial HDMI advertisement: source-host history is a confound

Initial evidence/event review was read-only. After source-host reboot coordination
was confirmed, control B was selected on disk and an orderly poweroff requested.
The automatic retry policy is unchanged. No manual HPD pulse, DDC transaction,
receiver MMIO access, callback registration or live module/service restart was
requested.
[Structured findings](RESULT.json), [prepared control plan](EXPERIMENT-PLAN.json).

## New correlation

The clean parallel-AIC boot began at 02:13:04 PST on November 5. The source PC
then rebooted at 16:41:49 PST, boot 8746c44d-dc57-478b-90aa-9d4668c38270.
The missed board boot began at 16:44:36 PST, 167 seconds after the source reboot.
The operator had reported the board off before that boot. Thus clean and missed
runs did not have the same source-host startup history. Existing November 2
evidence already records NVIDIA first-advertisement failures after source boot
before these startup changes, and success with another source. This supports
that existing hypothesis; it does not prove a root cause or rule out altered
probability from earlier setup or radio overlap.
[Source-host correlation](host-boot-correlation.json),
[earlier investigation](../../hdmi-first-advert-plan-2026-11-02.md).

The two recent EDID/HPD-ready logs are only 79 ms apart (12.433 vs 12.511 s).
Capture/radio initialization and full RC audits pass in both. On the missed run,
no source was acquired until the ten-second deadline and two-second HPD hold;
source lock followed at 26.202 s and video service at 26.251 s. This isolates the
observed delay to initial advertisement/source response, not a multi-second
regression in setup. It does not identify the electrical HPD edge or first DDC
request. The current boot has already recovered automatically, so its present
register/state values cannot reconstruct the missed initial transaction.

## Events and their limits

| Candidate | What it distinguishes | H713 qualification |
| --- | --- | --- |
| Source +5V present/edge | Powered source connected vs no source power | Not exposed/validated in current bridge |
| HPD | Sink advertisement to source | Our output; not independent cable detection |
| DDC request/progress/error | Source attempted EDID handshake | Need proven firmware-side observation; current controls do not prove bus traffic |
| TMDS/timing/frame activity | Source is sending video | Current guarded firmware-port/ring state supports signal events |
| MIPS hotplug callback | Potential lower-level source-change event | Transport exists; firmware registration/meaning must be audited before use |

The bridge's none state combines unplugged, powered-off/disabled source and
failed initial connection. Existing V4L2_SOURCE_CHANGE is published on a new
validated resolution lock; it cannot warn that the first handshake never
started. Earlier GetPortStatus=0x2 occurred with and without active video and
tracked clock/reset enable, so it is not proof of cable +5V. Historical receiver
maps have known corrections; use the corrected pointer-trace evidence, not
older mislabeled register tables. ARM reads of receiver windows remain prohibited.

A powered-source/no-video state is useful, but +5V does not guarantee that a
source intends to transmit. A connected source may keep +5V on while output is
disabled or asleep, and an already-connected cable may have no new edge after
board startup. Consequently a fully event-only failed-handshake detector is
not established. A practical design would start/cancel connection attempts on
validated source-power events, expose EDID/lock progress, avoid pulsing any
acquiring/active stream, and retain a bounded watchdog for a stalled attempt.
No retry behavior is changed here.

Linux provides V4L2_CID_DV_RX_POWER_PRESENT for detected source power and
V4L2_EVENT_SOURCE_CHANGE for video transitions. Those APIs describe suitable
semantics, not a sensor already present in this H713 implementation:
[power-present reference](https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-dv.html),
[video timing/events](https://docs.kernel.org/userspace-api/media/v4l/dv-timings.html).
Other receivers, such as ADV7611, expose dedicated 5V detection and interrupt
hardware; that does not establish the H713's register or interrupt mapping:
[manufacturer description](https://www.analog.com/en/products/adv7611.html).

## Next causal controls

Keep the same source PC, driver/content/cable, kernel, EDID, countdown and guard.
Every first-advertisement arm needs a fresh SOURCE-PC boot with the board off;
a second board boot on a primed source is a different condition. The prepared
plan compares current early+parallel, original global radio loading with the
other optimizations held fixed, and parallel radio with a separately reviewed
initial-advert delay. Preserve all retry outcomes. Compare actual initialization
and advertisement times rather than claiming global-radio rollback isolates
radio overlap by itself. Repeat any apparent difference before attributing it.

The original-radio restore package/backup passed its offline transaction tests
and was subsequently applied as control B. Its 74-file audit and native systemd
verification pass; HDMI, zero countdown and diagnostic guard pins are unchanged. Delayed-advert
payload still requires preparation and review. Host observer now records source
host boot ID, UTC and uptime at arm time for every new run. Fresh-host test
coordination is requested because restarting the user's working PC interrupts
this process; the agent will not reboot that PC automatically.

## Control B selected for the next fresh-source test

Chris confirmed they can reboot the source PC between arms. The tested exact
radio rollback restored the original AIC global module list and hotspot/BT unit
files and removed the new blacklist/owner/enablement link. No live driver/service
restart was performed. Native systemd verification and the 74-file control RC
identity audit passed. The board was requested to power off through its existing
guarded shutdown. [Installed control audit](control-B-installed-audit.json).

Operator sequence: leave the board off, disconnect its supply and UART/USB,
reboot the HDMI source PC, return to this chat while the board remains off, then
rearm passive UART and the observer before board power-on. Preserve HDMI cable,
source mode/content and all other settings. Record the new source-host boot ID
and its age at first board advertisement. This control tests whether a miss also
occurs without radio overlap; observed advertisement time must be retained, since
restoring global radio loading also moves HDMI later. No cause or probability
comparison is claimed before this measurement and the separate timing control.

## Fresh-source control B, first observation

With original global AIC loading restored, the first HDMI advertisement missed
again. The source host has a verified new boot ID; first board SPL arrived
324.928 seconds after host start. EDID/HPD was ready at Linux uptime 14.683506 s,
one automatic retry was requested at 25.023261 s, and the video service became
active at 28.504287 s. Radio global module loading finished at 6.507537 s, before
HDMI preparation began at 7.920657 s. This establishes that parallel radio
initialization is not necessary for this failure. It does not establish the
relative failure probability, or exclude advertisement timing as a contributor.
The complete five-minute result and audit receipts are recorded separately.

The five-minute deadline completed: 59.7096 fps during live sampling, no rejected
frames, guard/invalid-pair errors or audio xruns, no service restarts or additional
retries. Both audio PCMs remained RUNNING. All 74 RC checks and original radio
readiness/ordering checks passed. The no-retry qualification remains INVALID
solely for the initial HPD re-advertisement; it is not waived.
[Control B result](control-B-01-result.json). The board remains running with
original radio startup; no further configuration change was made during this run.
