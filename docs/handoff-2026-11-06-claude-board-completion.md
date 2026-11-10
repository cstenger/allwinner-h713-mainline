# H713 DDR3 board completion handoff for Claude — November 6, 2026

## Objective and reading order

Chris wants to finish the current **HY200 QZ713DF_A1 DDR3 board**, then move to
the **HY200 QZ713_V2 LPDDR3 board**. Immediate priority: reduce boot time,
investigate/fix initial HDMI detection without needing the automatic retry,
then finish optimization, integration and final qualification. Do not let
optional research indefinitely delay finishing this board.

Start with this document, then:

1. [Early boot review](hdmi-early-boot-review-2026-11-06.md).
2. [Current runtime resume state](production-evidence/2026-11-05-source-power-driver/RESUME.json).
3. [Startup timing and accepted improvements](production-evidence/2026-11-04-startup-timing/README.md).
4. [Reproducible build](reproducible-production.md) and
   [qualification plan](production-qualification-plan.md).

Older roadmaps and handoffs contain obsolete status, addresses and endpoints.
This handoff supersedes their current-state descriptions where they conflict.
In particular, warm HDMI recovery, PipeWire audio, 40 ms A/V calibration,
production rebuilding, the GF1 discard disposition and standby wake are already
completed for their documented scope. Do not restart them from old TODOs.

## Current endpoint: live state differs from disk

Last read-only board check: Linux boot
`d50d994e-b1f6-4afc-8b84-dccf6483c1b5`, HDMI `locked 1280x720`, desktop confirmed
by Chris. Board supply, HDMI and UART were connected; board was left running.
Verify fresh identity/state on arrival rather than assuming these remain true.

The live signal module is **`ddc-hpd-isolation-v1`**, because the last diagnostic
was tested without live reloads. Its disk files have since been **rolled back**:
the next boot uses the original signal owner and normal retry policy, retaining
the accepted startup improvements, source-power V2 and standby soft-start.
Both the diagnostic audit and restored-baseline audit passed 75 file pins plus
kernel/package/raw boot/environment/bundle/startup checks. Do not reinstall the
diagnostic because an old resume field names its package.

Last source-PC boot: `9df6717c-ea4b-4585-b53f-270178c13431`.
The source PC is the workstation running the agent. Never reboot it automatically.
It must be manually rebooted between meaningful fresh-source first-advert tests.
That kills host sessions, so save state before requesting it and rearm capture
afterward, while the board is still off.

Private working state is under `/home/chris/Projects/h713/local/recovery/`.
The primary resume file is
`2026-11-05-source-power-driver/RESUME.json`; it is mirrored in docs. Historical
host sessions: UART 83071, power observer 92610. Do not assume those IDs or
recorders survive a new agent/session/host reboot. Check the process/device owner
before opening another serial reader. The five-minute startup observer finished.

Access:

```sh
ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/home/chris/Projects/h713/local/recovery/2026-11-03-production-install-03/known_hosts \
  -o ConnectTimeout=5 -o ServerAliveInterval=2 -o ServerAliveCountMax=2 \
  root@192.168.4.1
```

UART:
`/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`,
115200 baud. The saved Wi-Fi profile is `spirits`; if UART shows Linux but SSH
cannot connect, inspect NetworkManager and the route. Bringing up that saved
profile has restored access without affecting wired networking. Do not expose
credentials. The target has no `rg`; filter copied logs locally.

Chris does not have a scope, logic analyzer or HDMI breakout. Work with software
and existing captures. Chris prefers leaving UART connected when removing board
supply; do not repeat obsolete instructions requiring UART disconnection.

## What has already improved boot time

| Change | State / evidence |
| --- | --- |
| Completion-aware MIPS IPC checks instead of fixed reply collection | Installed and accepted; capture initialization improved about 5.21 s. Preserve stale-response drain and positive completion checks. |
| Capture preparation overlapping user-session startup | Installed and accepted; HDMI ready another 3.15 s earlier. Explicit shutdown ordering matters. |
| Combined startup comparison | Three alternating cold boots per arm, five-minute observations, all six clean. Mean video activation 24.426 → 16.239 Linux seconds, improvement 8.187 s on primed sources. Earlier five warm checks also passed. |
| Autoboot countdown 5 → 0 | Installed, measured about 4.996 s saving before Linux. Existing reboot-to-U-Boot/FEL recovery preserved. Do not count this saving again. |
| Parallel AIC/Wi-Fi initialization | Implemented/tested, but **restored to original global loading, control B**, during first-advert investigation. Not currently selected. |
| Hardware-derived source-power events | V4L2 `reject-trace-power-v2` installed; useful absence/reconnect policy, **not a measured first-picture speedup**. |

Evidence: [matched comparison](production-evidence/2026-11-05-matched-startup-trace/README.md),
[zero countdown](production-evidence/2026-11-05-autoboot-countdown/README.md),
[radio experiment](production-evidence/2026-11-05-parallel-wifi/README.md),
[radio rollback/control](production-evidence/2026-11-05-initial-detection-investigation/README.md).

Keep timing origins separate: UART receipt relative to first SPL, Linux
monotonic service times, and physical power-to-first-picture are different
measurements. Service activation is not first visible pixel or audible sample.

## First priority: single firmware launch in U-Boot

Chris supports eliminating the duplicated launch and grouping initialization as
ways to reduce boot time and potentially fix initial detection. **Neither new
change is implemented or hardware qualified.** The last exchange established
that a single long-lived firmware instance is closer to stock's architecture.
That is not proof that a proposed combined implementation exactly reproduces
every stock step or works on our boot chain.

Current installed script does:

1. Validate FIT/FDT and GP6/GP7/MIPS/DSP state; lamp off.
2. `h713_disp auto 0x34 logo`: load firmware/assets, establish panel power
   state, run MIPS to readiness, quiesce MIPS, restore native timing, draw logo.
3. `h713_disp mips-comm-trace 0x34`: reload assets/workspace, install guarded
   CPU_COMM instrumentation, launch MIPS again and prove readiness.
4. Find the exact live CPU_COMM endpoint; call `eaf13de5` with source 3;
   prove worker transition, re-latch 720p timing, lamp on, publish Linux handoff.

The recent UART capture places logo commit near SPL receipt +7.77 s, second
MIPS readiness near +8.88 s, handoff near +9.25 s. Thus the second load/start
occupies roughly **1.1 s**, not the whole five-second logo stage. These are
buffered UART observations, not guaranteed savings. The initial 3 s panel-off
hold and stock 550 ms power pre-delay are separate and must initially remain.

Use the exact installed source cache:

`build/uboot-src-b3b5f2d2575fedc5016774e92caa14772d4f8ec7f1c25bf8c71510a8430f8396/arch/arm/mach-sunxi/h713_mips.c`

SHA256 `3c44fc5af23eaa55a698fbc1e5e509cb23cff76382c4d5425b1d178cc829b450`.
Source comes from the pinned submodule plus `patches/u-boot/series`; implement
reproducibly there, not only in a generated cache or by dirtying a submodule.
See [U-Boot series](../patches/u-boot/README.md).

Relevant functions: `h713_disp_auto_logo_mode`, `h713_disp_run`,
`h713_mips_release_raw`, and the `mips-comm-trace` command handler.
`tools/hdmi/build-startup.py` generates the guarded boot script.

Recommended design: one cold initialization that includes panel power setup,
the required firmware patches/CPU_COMM trace, firmware readiness, logo and the
eventual source-3 transition, keeping MIPS alive through the Linux handoff.
Determine the safe logo-publication point with the firmware live. Existing
`logo-live` is explicitly an experimental command with display-contention
warnings; do not substitute it into production and call that a validated fix.
Likewise, deleting either existing command loses setup or handoff prerequisites.
The second run currently inherits state from the first: inspect that dependency.

Preserve the logo → console → HDMI product behavior, source-worker proof,
720p re-latch after source changes, protected memory/firmware identities,
GP6 crash-loop handling, GP7 reboot mode, and panel/lamp/fan sequencing.
First test the combined launch with the current EDID/retry policy unchanged.
Compare cold and ordinary warm startup, then the established abrupt-reset
coverage using reviewed recovery tools. Check picture, speaker audio, counters,
service identities and startup audits, not merely successful Linux login.

## Next: initialize EDID/DDC coherently and investigate the retry

The early review found:

| Captured Linux time | Observation |
| --- | --- |
| 11.620276 s | EDID clock enabled at 24 MHz; reset released, `was_asserted=1`. |
| 14.856091 s | DDC pins claimed: PL10–PL15 `ffffff` → `222222`. |
| 14.876294 s | SCP original snapshot: HPD force-low control 7, DDC `07000000`. |
| 14.876588 s | Our EDID/HPD owner ready; active HPD control 0, DDC `07000007`. |

This weakens an earlier *working EDID* advertisement hypothesis. It cannot
exclude earlier transients or prove HPD voltage. MIPS firmware contains a
mailbox HPD-request path; our fixed SCP program does not implement the stock
mailbox dispatcher. Static presence does not prove when requests were sent.
Do not run the stock SCP alongside our owner.

The available **board-A** stock SCP initializes EDID reset/clock/DDC pins
together. Its identity and focused instruction evidence are in the early review;
do not transplant it wholesale to board B. Our 3.24 s resource-to-pin gap
contains audio/DSP initialization, not an idle sleep available to delete.
Current signal wrapper requires the verified audio graph. A design that exposes
EDID sooner must explicitly review that dependency and retain ownership,
failure handling and shutdown ordering. Do not parallelize hardware clock
transitions or remove their IPC checks to make a timing number smaller.

Prepared tool:

```sh
python3 -B tools/hdmi/prepare-early-hdmi-observe.py \
  --installed-command local/recovery/2026-11-06-early-hdmi-review/installed-h713-hdmi.cmd \
  --output /tmp/h713-early-observe-new
```

The already-generated candidate is under
`local/recovery/2026-11-06-early-hdmi-review/checkpoint-candidate/`.
**Prepared only: no installer, transfer, installation or hardware run yet.**
It inserts seven U-Boot checkpoint reads of EDID reset/clock and DDC mux around
logo/relaunch/source selection/Linux. It never accesses receiver MMIO. Removal
of observations restores the original script byte-for-byte; legacy CRC/length
checks pass. Logging adds time and boundary snapshots miss in-stage transients.
Use it where observations will inform the combined-launch design; avoid an
unnecessary full flash just to obtain these reads. A boot-script update needs
an exact backup, guarded transaction, matching installed/FAT copies/manifests,
updated audit and rollback before activation. It does not require a new proper.

### What has actually been tried

Chris corrected the framing: earlier work investigated the failure and added
the retry workaround. The recent tests are the first focused attempts to
eliminate the need for it. Do not describe the problem as exhausted.

| Experiment | Result / limit |
| --- | --- |
| Source-PC reboot with board off | Reliable first-advert failure condition on NVIDIA; later board boots on the same primed source often pass. |
| Startup delays, off-time variation, cold/warm comparisons | No reliable no-retry fix. |
| Source forced connector detection during failure | Still disconnected. Historical EDID read failed before recovery, succeeded afterward. Do not repeat bus scans indiscriminately. |
| Failed/good receiver and SRAM snapshots | Sampled state did not explain failure; no electrical waveform measured. |
| Mac source | First advertisement passed in one recorded trial; useful compatibility clue, not a general qualification. |
| Initial DDC-on → 100 ms settle → first HPD release | Still needed one HPD retry; video about 29.00 Linux seconds. |
| Initial 2 s DDC-disabled hold → DDC-on → 100 ms settle → first HPD release | Still needed one retry; video about 31.19 s. |
| DDC-only 2 s reset after failure, HPD control unchanged | No lock. Subsequent normal HPD/DDC fallback recovered; video 38.93 s. Added diagnostic delay was rolled back. |
| HPD-only pulse with DDC kept enabled | **Not tested**; useful remaining isolation, still a retry rather than a no-retry fix. |

The last diagnostic recovered stream ran five minutes at 59.706788 fps with
all four error counters zero; the desktop was confirmed. Its no-retry result
fails solely because one HPD retry occurred. Evidence:
[settle](production-evidence/2026-11-05-initial-advert-settle/README.md),
[initial hold](production-evidence/2026-11-05-initial-advert-reset/README.md),
[DDC isolation](production-evidence/2026-11-05-ddc-hpd-isolation/README.md),
[historical first advert investigation](hdmi-first-advert-plan-2026-11-02.md).

Both timing candidates and the DDC diagnostic were reverted on disk. Their
generator/module code remains opt-in for evidence. Do not accidentally enable
those flags or packaged `DIAGNOSTIC_DDC_ONLY=True` in a production rebuild.
Keep the bounded fallback until repeated fresh-source runs establish success.
An unconditional second pulse hidden inside startup is still a retry; report it.

### Fresh-source test protocol

For each meaningful initial-advert arm: save evidence, shut down cleanly,
operator removes board supply, operator manually reboots the source PC, board
stays off with HDMI/UART connected, verify new source boot ID, rearm UART and
observers, verify UART OPEN before explicitly asking for board power. Never
interpret a primed-source reboot as a repeat. Preserve every failed attempt.

Tools: `tools/serial/capture-panel-validation.py`,
`tools/hdmi/observe-matched-startup.py`, `observe-power-control.py`, and
`startup-qualification.py`. Use a new output directory and previous board boot
ID. Current V4L2 expected version is `reject-trace-power-v2`; independently check
the signal version and DDC/HPD counts. Default startup observer waits 45 s for
video and watches five minutes from video activation; adapt deliberately if a
new experiment changes the deadline. Record source boot, loaded identity,
initial advert, lock, retries, renderer and audio readiness separately.

## Other optimizations, after the two boot changes

1. Reconsider parallel AIC startup with first-advert controls fixed. It brought
   EDID ready to roughly 12.5 s in prior runs. One missed connection was
   confounded by source reboot history, not proof of a radio regression. Restore
   only with matched tests, Wi-Fi/BT/SSH readiness and shutdown checks.
2. Profile remaining MIPS IPC process/shell overhead, firmware/FAT reloads,
   verbose serial output and actual critical paths. Preserve positive IPC and
   identity checks. Do not redo the already-installed fixed-wait/countdown work.
3. Consider earlier EDID readiness independent of audio only after an ownership
   design. Hardware-derived power events are firmware-polled cache observations;
   they do not guarantee an event earlier than video and cannot identify every
   failed handshake. Cold zero is deliberately unknown until first positive.
4. Review panel waits separately and later. The 3 s initial off/reset hold solved
   expensive panel lifecycle problems; its electrical minimum is unmeasured.
   Keep it and the 550 ms stock delay through the single-launch experiment.
5. Produce a final cold/warm time budget, measured before/after over repeated
   runs, with visible picture/audio confirmation and documented residual waits.
   Avoid arbitrary delay sweeps without a hypothesis and discriminating result.

## Work already completed that must survive

- **HDMI video/audio:** 720p about 59.7 fps, automatic console/video switching,
  PipeWire speaker consumer, host reboot and physical reconnect tested. Hardware
  source-power V2 reports known absence/events and suppresses unnecessary HPD;
  unknown falls back to the original bounded 10/20/40/80/160 s schedule, 2 s hold.
- **Warm recovery:** shared boot/health-ack path is installed. Earlier five
  ordinary warm boots and abrupt-reset evidence passed. New boot changes need
  regression coverage; do not assume those older passes qualify new binaries.
- **Standby wake:** abrupt PB5 lamp/fan enable reproducibly reset the board.
  A bounded 0.5 s, 500 Hz startup ramp through the existing gpio-backlight owner
  fixed it. Four same-boot/key cycles and a post-cold-boot wake passed, desktop,
  lamp and fan confirmed. Ends fully ON, not steady fan PWM. Preserve helper,
  failure behavior, CPU cap/state and rootfs/release integration. Underlying
  electrical cause unmeasured. [Evidence](production-evidence/2026-11-05-standby-fix/README.md).
- **GF1:** one guarded discard in 1,211,737 completions was dispositioned as
  intended protection after actual-C race/guard-bypass tests. The strict failure
  remains recorded; no blanket rejection allowance. Do not weaken copy/pair/
  coherency guards or call future rejects automatically harmless.
- **Local playback:** isolated cold local-playback boot passed H.264 and HEVC
  pixel tests, GPU/native picture/tone, mirror, manual keystone, magnification
  and downscaling. Short VP9/AV1 checks passed. HDMI takes priority for the
  whole HDMI boot, even without signal; local decoding must use its supported
  separate boot, not raw player commands bypassing the launcher.
- **A/V sync:** accepted persisted HDMI audio delay is **0.040 s**. Old TODOs
  asking to calibrate it from scratch are stale. Preserve calibration and
  recheck if buffering/path changes. Never delay video to match audio.
- **Build/installation/recovery:** two complete source builds reproduced byte
  identical outputs. November 3 candidate installed and qualified for its stated
  scope, with GF1 disposition November 4. Non-writing FEL/recovery access
  rehearsal passed. Full rollback writes were not rehearsed. Later delta changes
  are not automatically part of that sealed candidate's qualification.

## Finish this board: remaining delivery work and acceptance

Do the remaining work in this order. This is the completion list, not a request
to reopen every historical research thread.

| Work | Required endpoint |
| --- | --- |
| Boot optimization and first detection | Combined launch and coherent resource sequence measured/tested separately. Repeated fresh-source no-retry success, or a candid remaining-issue record and Chris's scope decision. Do not declare retry removal achieved by making retries earlier. |
| Final lifecycle regression | Cold, repeated ordinary warm, reviewed abrupt reset, source reboot while board stays on, no-source boot and physical reconnect; picture/audio, service identity, same-boot wake, counters and audits all captured. Repeat affected gates after changes. |
| Standby thermal coverage | Extended HDMI-active light standby is not qualified by short wake cycles or the old idle test. Verify sustained safe temperature with lamp/fan off and CPU capped; keep failure safeguards. A power meter is unavailable, so do not invent measured watts. |
| Final source integration | Reconcile dirty/untracked accepted changes into reproducible sources, patch series, build inputs and source locks. Keep diagnostics opt-in. Select the intended final V4L2 trace/power version explicitly. Do not omit the new lamp helper from a rebuild. |
| Final complete build | Build the final tree twice independently where practical; compare outputs and record exact tools/vendor/calibration/source/package pins. Keep sealed old candidate/rollback artifacts intact. New tree/output hashes require new acceptance. |
| Exact deployment/rollback | Fresh board/storage inventory and consistent offline backup; device-bound bounded update packet, per-write readback and protected-region comparison. Never reuse old addresses/hashes solely because the version string matches. |
| Final rebuilt-image qualification | Apply the current qualification plan: boot/network/BT/SSH, HDMI, speaker delay, isolated local decoder/playback, mirror/keystone, keys/IR, standby wake, shutdown and recovery. Existing decoder suites need appropriate isolated boot, not an HDMI boot. |
| Endurance | At least the established two-hour continuous HDMI target with stable renderer identity/frame counters, audio and error monitoring; longer/local playback/network coverage as justified by changed code. Preserve failures and investigate new rejects. |
| Documentation and release freeze | Fresh board-specific attestation, complete timing table, known limits/deferred features, recovery instructions, verified host keys/backups and reproducible build instructions. Clean up temporary target tools/media and stale candidate activation paths. Commit/push only as Chris requests. |
| Board transition packet | Leave DDR3 board recoverable and documented, retain accepted artifacts, and prepare a distinct LPDDR3 bring-up plan with its own identities, calibration and recovery inputs. |

Do not expand the release silently. The following are separate/deferred or
need an explicit product decision rather than being assumed blockers:

- 640×480 input is deliberately unsupported (`allow_480p=0`). Wide-EDID 1080p50
  capture drops and interlace coverage are outside current 720p qualification.
- Runtime HDMI-to-local ownership handover is not qualified; use distinct boots.
- Deep standby/CEC wake and default s2idle are not the product's chosen standby.
  Light standby keeps network/USB available. Actual external USB GPIO hardware
  can be tested when available; virtual KEY_POWER handling is already tested.
- Brightness control needs a hardware solution separating lamp dimming from
  shared fan power. Do not turn the wake ramp into steady reduced-duty PB5 dimming.
- Full 10-bit output, exhaustive new codec coverage and upstreaming are separate
  work. An old claim that VP9 cannot work is superseded by the recent smoke test;
  do not reuse it without reviewing the current codec evidence.
- HEVC midstream resolution-change limitations remain documented in
  `decode-production-readiness.md`; do not revive retired fixes blindly.
- Android space reclaim, boot FAT repairs and repartitioning are separate storage
  operations, not prerequisites to boot optimization. Preserve the current split.
- Next-board motor/fan/NTC differences, optics/calibration and peripheral wiring
  require board-specific validation, not copying bench assumptions.

## Storage, recovery and operating constraints

Current board: eMMC CID `15010038475446345208604bbe691991`.
Linux is **p26, GPT label `linux`, 2952790016 bytes**; p27 is Android `UDISK`,
2021113344 bytes. Do not select Linux by historical UDISK naming.
Boot FAT: p2, U-Boot `mmc 1:2`. Installed proper LBA `0x49ac00`, SPL LBA `0x10`;
saved environment LBA `0x49ec00` / byte `0x93d80000`. These are orientation,
not authorization to write without fresh inventory and exact packet bounds.
Never flash a combined SPL+proper image into the installed split layout.

Last 75-file baseline audit:
`local/recovery/2026-11-05-standby-fix/audit-after.py`.
Last successful result after diagnostic rollback:
`local/recovery/2026-11-05-ddc-hpd-isolation/cold-01/baseline-restored-audit.json`.
Raw expected pins: proper `326661503b28376284c3082477335f19c5908b5cd33c4970373df5fb8874746b`,
SPL `d593ab799b6d422523d67a33c7427c481765e5afac71f065cc2f16e162ce18cf`,
environment `e6a56d4c6f2703c9360c29da4d1e1aec2d35bafd57bc6ca8232896e0296bc3ab`.
Do not use older environment pins from October handoffs.

No ARM receiver/PHY MMIO: especially `0x07091000`–`0x07091fff`; a read can wedge
the SoC. Receiver observations go through proven SCP/MIPS paths. Do not perform
raw I2C scans, force-probes, GPU resets, firmware callback registration, unsafe
receiver reloads or live owner replacement as shortcuts. Old NVIDIA cache-reader
packages failed live qualification; do not rerun them or reuse consumed approvals.
Respect GP6/GP7; never clear a retention/crash guard simply to get another run.
If held at U-Boot's guard, preserve evidence and coordinate a supply cycle.

PB5 is lamp **and fan** power. Keep the 1296 MHz CPU ceiling; 1416 MHz previously
corrupted memory. Mute through DAC volume, not `Speaker Switch=0`.

This workspace has substantial pre-existing modified/untracked work. Do not
reset, clean, overwrite others' edits, stage everything or commit implicitly.
Current user authorization/preferences take precedence over historical blanket
approval instructions in old docs. New packages previously encountered automatic
approval review requiring exact explicit transfer/execution approval; prior
approvals cover those exact old packages, not arbitrary replacements. If review
rejects a new action, explain the action/reason and obtain the needed approval
for a concrete prepared package. Do not repeatedly ask for approval already given.

## Moving to the LPDDR3 board

Only after the DDR3 completion decision: verify physical silkscreen and DRAM,
obtain board-specific stock backups, establish UART/FEL recovery, then FEL-boot
the LPDDR3 configuration and test DRAM before any eMMC write. DDR3 and LPDDR3
parameters are not interchangeable; wrong parameters may train then hang.
The LPDDR3 config compiling is not hardware validation. Neither board has an
SD slot. Revalidate display/panel, power/fan, network/BT, keys/IR, audio,
HDMI, standby and calibration against its actual wiring. Preserve the working
DDR3 release as the comparison/recovery reference.

## Suggested first Claude session

Read current identity/state and this review; preserve the running picture.
Inspect the exact two launch paths and their inherited state. Prepare a
single-launch candidate that keeps panel safety, logo and CPU_COMM/source-3
proof, with reproducible patch/build and rollback. Decide whether the prepared
resource checkpoints are needed first or can be included as a diagnostic arm.
Do not mix the coherent EDID/DDC change into the first single-launch comparison.
Save a compact resume state after each install/test, and rearm capture before
each operator power-on. Continue through measured optimization and the final
delivery checklist above rather than declaring the board finished at the first
successful desktop.
