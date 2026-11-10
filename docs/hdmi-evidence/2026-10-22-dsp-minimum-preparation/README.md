# Minimum AudioTop diagnostic preparation — October 22, 2026

**Offline preparation complete; no board access, staging, power action or
capture occurred. Board remains shut down after the previous trial.**
[Design and live runbook](../../hdmi-dsp-minimum-design-2026-10-22.md).

The next trial starts with **control-only setup, level 1**, before its first
DSP request. Levels 2/3 add the established config/latch, each in a separate
fresh cold → patched production → orderly warm → one-logo cycle. No setup
or retry follows a failed request. This identifies sufficiency/minimum
among the three nonempty stock prefixes under the tested path, not minimum
individual bits or electrical RAM retention.

## Candidate

`build/hdmi-dsp-minimum-2026-10-22/candidate/`, independently copied from the
tested retention `candidate-v2`; [manifest](candidate-manifest.json).

| Item | Identity |
| --- | --- |
| FIT | 7,754,772 bytes; SHA-256 `e1b475a8cb66ba86846a30dc8845c6cb0e76c8459f0d2bc2f3ba47edf63d8aeb` |
| Kernel | `6.18.38 #4 SMP Thu Oct 22 02:35:16 PDT 2026` (full timestamp matters) |
| DTB | 34,710 bytes; SHA-256 `7e75f896ec5924272e3c7a25d6d1bd5358e8e9f57e38e316d4b07c8b19a7ae6e` |
| Guard | Existing bench `5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`, unchanged |

All levels share identical FIT bytes. DT changes from production are only
disabled display/CPU_COMM plus the minimum-diagnostic marker. TVFE hold/PPU
policy is unchanged. Exact kernel build, manifest hashes, DT, fresh patched
baseline, inactive owners, guard, panic/console settings and boot/level/FIT
proof are required by the stepped helper. No production source/FIT/script/
DT/bootloader/environment changes were made.

58 operations retain the tested access prefix, demand AudioTop census
exactly `0/0`, then perform the selected setup before any request. One
stock-lock claim protects at most one request per device; release/readback
and final domain/interface checks end the trial. No DSP patch/graph,
source3 relaunch, processor launch, reset assertion, power-domain transition,
GP6/GP7 write or arbitrary logical address exists in the observer. All
resources remain held until poweroff, with the existing shutdown guard.

New tracing records initial-busy wait, command-write entry, returned command
write, done wait, completion/timeout and skip. State has immutable level,
actual setup mask/readbacks, per-device sent flags, phases, status and
outcome-qualified raw data. A write-return marker is not a DSP completion
acknowledgment. Initial-busy timeout is distinguished from sent/done timeout.
A hard MMIO stall remains beyond the poll bound and must not be retried.

## Verification

* [Build log](build.log): real kernel Image/modules build succeeds without
  warnings/errors; full exported symbols unchanged.
* [Independent artifact check](artifact-verification.json),
  [checker](verify-artifacts.py): FIT-extracted kernel/DTB and decompressed
  Image match; DT exactly reproduces only the intended edits; bundle hashes
  valid; compiled observer matches tested source.
* [70 passing offline tests](tests.log): 11 new tests plus 59 boundary/
  retention/trace/warm/guard regressions. Native tests execute the actual
  observer with fake MMIO, exercising all fixed levels, setup thresholds,
  completed zero/one responses and immediate completion, initial-busy vs
  sent/done timeouts, device-1 timeout, suppressed request after failure,
  lock/resource/power failure, inherited setup refusal, missing opt-ins,
  exact setup-write counts and terminal refusal of retries/escalation.
  Command-write assertions require a preceding trace entry; peer/PPU/RTC
  writes are forbidden by the model. Evidence tests reject inconsistent
  phases/sent counts, wrong level, incomplete pair/release, mismatched FIT/
  initial setup context and unresolved lower levels. Loader tests reject
  absent/invalid levels, no-logo history and duplicate logo markers.
* [Source hashes](source-hashes.json) identify tested files. Kernel source,
  packed helper/analyzer and manifest are verified together.

These checks establish software control flow, not the hardware minimum.
A completed `0/0` pair is successful access with zero versions; a timeout
has no version value. Minimum comparison requires valid independently cold
trials with matched initial state, and reports uncertainty when lower-level
failures were not phase-qualified. Repetition is needed before adoption.
The previous no-setup trial is historical context, not a matched phase-
qualified level-0 run of this FIT.

No new board files were installed. Existing bench guard/original backup
remain as [previously recorded](../2026-10-22-dsp-boundary-one-logo-live/README.md).
Disabled display means no normal DRM panel-shutdown callback: lamp stays
off and physical disconnection follows orderly poweroff. No capture is armed.
