# Claude second-opinion handoff: intermittent HDMI first detection

Prepared November 1, 2026, America/Los_Angeles. Workspace:
`/home/chris/Projects/h713`, branch `h713-letterbox`, HEAD
`848339d02baaa229e2586b9a97f4419fb236b94d`. Many relevant files are dirty or
untracked; HEAD alone does not describe this work. Preserve the working tree
and ignored `local/recovery/` evidence. This handoff was prepared offline.

## Request to Claude

Please independently review the evidence and startup implementation. Challenge
the current interpretation and recommend the single most informative next
software-only experiment. The two-second delay is **not an established fix**:
both the matched 2,000 ms and 0 ms variants passed one recorded cold start.
Do not assume a missing delay, erased EDID, host-driver defect or hardware fault.

Start with offline source/evidence review. Return: (1) established facts versus
inferences, (2) overlooked confounders or code defects with file/line references,
(3) competing explanations and observations that would distinguish them,
(4) one minimal next experiment, its expected outcomes and any offline safety
work needed. Explain what cannot be identified with software alone. Do not
implement/deploy a change or operate the board as part of this review request.

## Current state: distinguish last validation from latest operator report

* The last **validated** boot was the 0 ms cold test,
  `275f5bce-8d22-4d20-9ba8-9551b05dac7f`. It had correct EDID, 720p lock, healthy
  Linux, all 56 production pins, five private runtime files and ten storage
  regions verified. Recorders stopped cleanly; UART was released.
* **After those recorders stopped**, the operator abruptly removed board power,
  let it sit off, powered it on, and reported that the host desktop appeared
  again. No fresh checks or capture were performed for that cycle. Exact off
  interval, boot ID, loaded command, filesystem state and service counters are
  unknown. Do not reuse the preceding boot ID as a current identity guard.
* Board is powered on and showing the desktop **per operator report**. The
  persistent temporary 0 ms override is expected still present, but has not
  been rechecked after that abrupt power cycle. A read-only identity/filesystem
  health check would be sensible before another live test, when requested.
* No capture is currently known to be running. No active SCP diagnostic lock
  is known from the recent validated boots. Old retained-sampler warnings refer
  to earlier, ended boots; do not reuse those boot-bound packages.

Expected persistent configuration, as last verified:

```
/etc/systemd/system/h713-hdmi-signal.service.d/90-start-delay.conf
  ExecStart=                         # reset inherited ExecStart
  ExecStart=/usr/bin/python3 /usr/lib/h713-hdmi-delay-bench/h713-hdmi-signal.py start --bundle /usr/lib/h713-hdmi --bench-delay-ms=0 --bench-manifest=/usr/lib/h713-hdmi-delay-bench/manifest.json
```

Loaded production ExecStop remains
`/usr/bin/python3 /usr/lib/h713-hdmi/h713-hdmi-signal.py stop`. Original production
wrapper/unit/module bytes were not replaced. No automatic override removal was
installed; this temporary override persists until explicitly changed.

## Problem and evidence chronology

Target is the DDR3 bench HY200 QZ713DF_A1 / Allwinner H713 board, running the
validated Linux 6.18.38 #1 October 16 build. The separate LPDDR3 board is not
qualified. Recorded eMMC capacity is 7,818,182,656 bytes. Identity and installed
binary hashes, rather than a generic H713 model name, gate live scripts.

The NVIDIA GPU on the host feeds **HDMI input on the projector board**. The
projector should show normal startup/Linux console and then the host desktop.
The failure is first source detection: board reports no input and host caches
HDMI disconnected with no EDID, despite the software startup path succeeding.
GPU-end cable reseating is a known workaround; it destroys the failure state
and is unsuitable as a diagnostic observation.

| Observation | Evidence quality | Result |
| --- | --- | --- |
| Prior October 31 ordinary warm boot, production wrapper | Recorded + operator confirmed | Desktop returned without reseat |
| November 1 fresh boot, production wrapper, boot `afe48e93-6604-44de-a220-acb9416e8363` | UART + read-only board/cache evidence | No signal, zero transitions/frames; host disconnected/empty EDID; startup and 56 pins pass |
| Matched bench 2,000 ms, warm boot `7e9e206d-bd7b-493a-b3fe-af69ab3be77f` | UART + continuous cached host monitor + read-only checks + operator | PASS; measured interval 2.021350376 s |
| Same 2,000 ms bench, cold boot `e6ccc77a-dfb2-411c-a2cf-139c35d4dceb` | Same evidence; orderly poweroff then reported supply removal ≥60 s | PASS; interval 2.021728043 s; desktop appeared |
| Matched 0 ms bench, cold boot `275f5bce-8d22-4d20-9ba8-9551b05dac7f` | Same evidence and minimum reported supply-off condition | PASS; interval 0.021638583 s for common completion checks; no deliberate wait; desktop appeared |
| Latest abrupt off/on with desktop return | Operator only; no capture/checks | Additional reported success, expected 0 ms config; not a validated trial |

There is one recorded cold pass per bench condition, no failure-rate estimate
and no randomized/repeated series. Both recorded cold tests started by orderly
shutdown from a working HDMI session. Actual supply-off durations were not
equalized or independently measured beyond operator-confirmed minimums. Source
state/history and the conditions of the original failure remain confounders.

### Timing is kernel uptime, not mains-on time or board calendar time

| Run | DSP graph ready | EDID/HPD ready | Graph → ready | First 720p lock |
| --- | ---: | ---: | ---: | ---: |
| Earlier successful uninstrumented warm | 22.440588 | 22.871197 | 0.430609 | 24.195194 |
| Failed uninstrumented fresh boot | 22.718392 | 23.143246 | 0.424854 | None observed |
| Bench 2,000 ms cold | 22.419615 | 24.967893 | 2.548278 | 26.283372 |
| Bench 0 ms cold | 22.687333 | 23.240379 | 0.553046 | 24.547561 |

The zero bench is **not** the original production timing: it retains extra
read-only checks/logging. Its graph-to-ready interval exceeds the failed original
by about 128 ms. That does not prove this overhead helps, but means a zero-bench
pass cannot eliminate every startup-settling hypothesis. Conversely, the
two-second interval itself was unnecessary in the observed zero-bench run.
Ready log timestamps follow SCP operations; they are not physical HPD edges.
Board calendars are wrong; use boot IDs, kernel/monotonic times and host UTC.

## What code actually does

1. U-Boot prepares the MIPS display path and Linux handoff. Linux uses receiver
   ownership, clocks and DSP graph readiness before the signal service.
2. The production [signal unit](../tools/hdmi/h713-hdmi-signal.service) Requires/
   After capture; [wrapper](../tools/hdmi/h713-hdmi-signal.py) checks graph ready,
   writes the per-boot attempt/ownership markers, claims DDC pins, and loads the
   persistent reversible signal module. Existing failure-retention and shutdown
   behavior must be preserved.
3. The private bench copy adds manifest/file/readiness checks before/after a
   monotonic deadline, **after the original graph gate and before markers/DDC
   claim/SCP initialization**. Both 0 and 2,000 ms controls use identical code,
   checks, logging and binaries. Their drop-ins differ only in the delay argument.
4. [SCP generator](../tools/hdmi/make-edid-trial-code.py), activation around lines
   51–65: payload validation → force HPD low → disable DDC → configure controls →
   write three EDID banks → verify banks → enable DDC → release HPD force-low →
   active readbacks/ready. There is no explicit timed DDC-enable-to-HPD-release
   gap. The experimental wait does not change that internal sequence.
5. The production signal module holds receiver/SCP ownership until explicit
   verified restoration. Do not use service restarts or latch clearing to retry.

Code entry points:

* `tools/hdmi/startup-delay-bench/{build.py,hdmi_delay_bench.py,test_delay_bench.py,test_mutations.py,test_units.py,RUNBOOK.md}`
* `local/recovery/2026-11-01-hdmi-start-delay/package/h713-hdmi-signal.py`: exact generated private wrapper; companion manifest/helper/drop-ins in that directory.
* `tools/hdmi/{h713-hdmi-signal.py,h713-hdmi-session.py,h713-hdmi-signal.service,test-hdmi-signal.py,make-edid-trial-code.py}`
* `modules/hdmi-signal/h713-hdmi-signal.c`, `modules/ddc-bringup/h713-ddc-pins.c`
* `modules/hdmi-receiver/h713-receiver-{power,edid,park}.c` and policy/header files.

Preparation qualification: 24 delay tests + 31 existing wrapper regressions,
six broken variants detected, both unit variants verified and original AST
preserved outside added bench hooks. Original staging had eight transaction
rehearsals; switching to zero had nine. These are offline behavior/safety checks,
not proof of the HDMI root cause.

The source snapshot is for review, not a claim that every installed binary can
be rebuilt from a clean checkout. Use the retained file pins as installed
identities; preserve ignored build/recovery inputs. In particular, do not use
the SCP generator's default EDID mode as a substitute for the captured,
checksum-identified current EDID.

## Important observations that previously led to wrong inferences

* Host cached EDID after successful bench detection is 256 bytes, HCP/H713 HDMI
  IN; SHA256 `edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`.
  Both blocks pass checksums; it matches the retained board payload.
* HPD control 1014 was `7` at SCP entry in both a known-good and failed earlier
  boot. The current delay may extend an inherited low condition, but no physical
  HPD voltage/dwell was measured. Control bits do not establish the waveform.
* Active-window EDID reads of zero also occurred in a historical successful
  detection with correct host EDID. Zero bank readbacks do not prove erasure.
* `readback ffffffff` in setup logs is unused post-restore poison space, not
  evidence of failed active readback. Refer to the module/data layout.
* Earlier guarded live SCP sampling found the sampled controls matched handoff;
  it did not establish electrical HPD/DDC state or first-transaction behavior.
  That retained session ended on power-off. Do not resurrect its authorization.
* Cached host status/enabled/EDID reads are sequential observations at 250 ms
  intervals. Mixed intermediate snapshots and timestamps are not atomic state
  transitions, physical edges or transaction traces.
* The 0 ms run stayed locked past 19 minutes. Two rejected and two overwritten
  frames were recorded, stable across final snapshots; bad-guard/AFBD-invalid
  counters were zero. These runs qualified startup, not lossless media/audio.

## Evidence map and backups

Read these in order; older documents often contain now-stale endpoint statements:

1. [Zero cold validation + comparison](hdmi-evidence/2026-11-01-zero-control-cold/README.md)
2. [Two-second cold validation](hdmi-evidence/2026-11-01-startup-delay-cold/README.md)
3. [Two-second warm validation](hdmi-evidence/2026-11-01-startup-delay-boot/README.md)
4. [Original fresh failure](hdmi-evidence/2026-11-01-board-boot/README.md)
5. [Comparison with older startup tests](hdmi-startup-timing-analysis-2026-11-01.md)
6. [Earlier SCP analysis](hdmi-scp-capture-analysis-2026-10-31.md), [September detection](hdmi-source-detection-validation.md)
7. [Bench preparation](hdmi-evidence/2026-11-01-startup-delay/README.md), [first staging](hdmi-evidence/2026-11-01-startup-delay-stage/README.md), [zero staging](hdmi-evidence/2026-11-01-zero-control-stage/README.md)

Full private evidence directories (each has SHA256SUMS and a sibling archive):

```
local/recovery/2026-11-01-board-boot-uart/
local/recovery/2026-11-01-hdmi-start-delay/
local/recovery/2026-11-01-hdmi-delay-stage/
local/recovery/2026-11-01-hdmi-delay-boot-validation/
local/recovery/2026-11-01-hdmi-delay-cold-validation/
local/recovery/2026-11-01-hdmi-zero-control-stage/
local/recovery/2026-11-01-hdmi-zero-cold-validation/
```

Raw runs: `uart-01/{serial.log,serial-timestamped.log}` and
`host-hdmi-01/events.jsonl`; collected board journals and timing/counter data in
`POSTBOOT.json` / `FINAL-READONLY.json`; summaries in `RESULT.json`. The original
failure uses `board-readonly.json`, `coprocessor-summary.json`, etc. Do not edit
these sealed packets or casually execute their live scripts: many encode stale
boot IDs or contain real power/staging actions.

On-board rollback backups, as last verified:

* `/var/backups/h713-hdmi-start-delay-20261101-01/`: original production baseline.
* `/var/backups/h713-hdmi-zero-control-20261101-01/`: pre-zero configuration,
  including exact two-second drop-in and private runtime. Tar SHA256
  `47f15a22c0a56207cbb3408e4a12d71f777cac74ad5fccc726634ca37bab1b54`.

To restore production later, remove the single temporary drop-in after review;
the production unit/wrapper/modules were untouched. To restore the delayed
experiment, restore only its backed-up drop-in/metadata. Do not broadly extract
a baseline archive onto a running system. Neither reversion is authorized by
this second-opinion request.

## Live-work constraints and adjacent work

This request is for handoff/review, not another live test. Start offline. Any
later live operation needs a current-state check and user authorization appropriate
to that action. Preserve any recreated bad state: no reseat, HPD pulse, recovery,
service restart, reset or reboot to make a failed test pass. User requested
software-only diagnosis and explicitly refocused work onto the board after a
long host NVIDIA detour; propose a narrow board experiment rather than resuming
that detour by default.

Hardware constraints from the existing [runbook](chatgpt-hdmi-remaining-work-2026-10-24.md):
never access receiver MMIO `0x07091000..0x07091fff` from ARM; a read can wedge
the SoC. Never touch `0x06940000`. GP6 is the startup/health latch; GP7 belongs to
the established reboot-mode handoff. PB5 drives lamp **and fan**. No new live SCP
code/register/timing changes without dedicated offline layout, ownership,
restoration and failure-path qualification. Do not unload ambiguous retained
owners or read parameters when an active diagnostic lock forbids it.

Known connection, only for a later authorized read-only/live task:
`ssh -F /dev/null -o BatchMode=yes -o ConnectTimeout=5 root@192.168.4.1`.
UART is the CP2102 by-id path recorded in each PLAN.json, 115200 baud. Ensure a
sole read-only recorder before a future boot; let U-Boot run unattended.

Production cleanup also fixed and installed the U-Boot environment-offset
migration; subsequent boot-load checks passed. Native `env save` validation
was prepared but has **not been completed on hardware**. Do not save U-Boot
environment during HDMI diagnosis. Older audit notes describing the pre-migration
proper image/offset or retained SCP sessions are historical, not current truth.

## Suggested review questions, not conclusions

* Does code/evidence reveal a readiness gap hidden by bench checks (~128 ms
  graph-to-ready difference), or is that difference normal scheduling variance?
* Which aspects of receiver readiness, inherited HPD-low history and source
  reconnect history are actually controlled or observable in these runs?
* What failure explanation is consistent with original production failure,
  known-good uninstrumented boots, both bench passes and the unrecorded abrupt
  cycle? What evidence would falsify each candidate?
* Should the next test restore the exact original production wrapper, repeat
  matched bench conditions, or add a specific passive milestone? Pick one with
  the best discriminating value and explain the confounders it preserves.
* Can the desired distinction be made software-only? Do not imply control
  register values or cached host state prove cable-level HPD/DDC behavior.

No board or host-device access was performed while preparing this handoff.
