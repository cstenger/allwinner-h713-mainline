# Handoff 2026-11-10: startup speed and display hand-over work

For ChatGPT, picking up from a Claude Code session that ran 2026-11-09 and
2026-11-10. Everything below is committed and pushed to
`cstenger/allwinner-h713-mainline` `main` (tip `3d60b474`), and the
working tree is clean. The board runs exactly what is described here.
Detailed evidence for every change is in
[production-evidence/2026-11-09-startup-and-parallel-aic/README.md](production-evidence/2026-11-09-startup-and-parallel-aic/README.md).

## 1. Where things stand

HDMI video now starts about **10.3-10.8 s** after Linux starts on a warm
or cold boot, down from ~14 s on 2026-11-09. Time from the first SPL
output is roughly +7.8 s on top of that. Most of the remaining spread is
the HDMI source PC's reaction to hot-plug (1.1-1.8 s after HPD goes up),
which the board cannot speed up.

Current boot timeline (warm, Linux monotonic):

| Step | Time |
| --- | ---: |
| Kernel start (after SPL) | ~7.8 s after first SPL output |
| `user@1000` active | ~6.8-7.0 s |
| HDMI prepare done (`h713-hdmi-prepare`) | ~8.6-8.7 s |
| Capture unit done (now a no-op) | +~0.06 s |
| EDID/HPD up (`h713-hdmi-signal`) | ~8.9-9.1 s |
| Source starts sending, signal locked | ~10.2-10.9 s |
| `h713-hdmi-video` started | ~10.3-11.0 s |

## 2. What changed in this session (commit order)

| Commit | Change | Effect |
| --- | --- | --- |
| `ecade877..ccd9e407` | `h713-letterbox` squashed into 10 topic commits on `main`; old history under `archive/*` tags | Clean `main` |
| `7f95eff7` | `build-startup.py` defaults to the single MIPS launch (U-Boot 0004) | |
| `c372e3ad` | AIC8800 WiFi loads alongside HDMI startup | |
| `1166ab3f` | U-Boot 0005: early panel-off, 3 s hold overlaps the loads | Kernel starts 0.8 s sooner |
| `932d1749` | Root filesystem grown once (`h713-rootfs-grow-once.service`), not every boot | Removes a 1.7 s outlier |
| `cdd33ffd` | HDMI prepare runs MIPS IPC checks in-process | Prepare 7.1 s -> 5.0 s |
| `afd611a1` | udev rule hides unused eMMC partitions from systemd | User session ready 2.3 s sooner |
| `196afed5` | Kernel: `# CONFIG_LEGACY_PTYS is not set` | User manager start 1.9 s -> 0.5 s |
| `6ce6d8dd` | Kernel patch 0190: cover the console <-> video route hand-over | No pale/green frame at switches |
| `386bc0cf` | Kernel builds pass `RUSTC=/dev/null/rustc`; host rustc can't reach `.config` | Reproducible kernel builds |
| `35cd38a7` | DSP patch (724 pairs) streamed on the busy handshake, no 1 ms per-pair sleep | Patch 824 ms -> 15 ms |
| `ca240e09` | Capture unit `ExecStart=/usr/bin/true`; `check-startup.sh` checks prepare | HPD ~0.4 s sooner |
| `3d60b474` | Bridge delivers black for all-zero capture slots | No green flash at video start |

Key findings worth remembering:

- **systemd device units are expensive here.** Every manager start or reload
  pays ~5 ms of CPU per device-unit name. 27 Android partitions (kept as
  reference, never mounted) and 256 legacy BSD ptys made ~800 units.
- **DSP write busy bit.** AudioTop `0x06144000` bit 4 is a real handshake:
  back to back, the DSP holds it ~19 us per word. The vendor's 1 ms
  per-pair sleep was margin on top of it. The other DSP writes still keep
  the 1 ms.
- **Route hand-over (0190).** The selector at `lvds+0x06c` picks the
  console or video route. The vblender cover (0165) only acts on the video
  route, and it blacks it out even with source 0 idle. So every switch now
  happens on the covered video route.
- **Empty capture slots.** Right after lock the capture pair counter runs
  ahead of the pixel data. With an empty ring (cold boot) the first 4-5
  copied frames are all zero, which shows as solid green.
  `h713_frame_empty()` in `modules/hdmi-v4l2` now shows them as black.

## 3. Board state

- Board: HY200 QZ713DF_A1 (H713, DDR3), reached over WiFi at
  `root@192.168.4.1`. Use the dedicated known_hosts:
  `local/recovery/2026-11-03-production-install-03/known_hosts`. The
  wrapper `local/recovery/2026-11-09-startup-timeline/b.sh` does this. Do
  **not** edit `~/.ssh/known_hosts`; it has a stale key.
- Kernel FIT `9d496308` (0190 + no legacy ptys + rustc-free config). Script
  cmd `2dd9adb1` / scr `4c2453a4`. Installed with
  `tools/hdmi/install-kernel-fit.py`.
- Audio module `45ba26fe` (DSP patch without the 1 ms sleep).
- Bridge `h713-hdmi-v4l2.ko` `b15d20e3` (committed source + empty-frame
  fix). It replaced a 2026-11-05 diagnostic variant
  (`reject-trace-power-v2`, `5de83b88`).
- Capture unit `35883a89` (`ExecStart=/usr/bin/true`); health
  `check-startup.sh` `299a4b0f`.
- Rollback records (each has a `RESUME.json` with the exact command):
  `local/recovery/2026-11-10-dsp-gap`,
  `local/recovery/2026-11-10-capture-noop`,
  `local/recovery/2026-11-10-first-frames`,
  `local/recovery/2026-11-09-green-switch`,
  `local/recovery/2026-11-09-legacy-ptys`,
  `local/recovery/2026-11-09-user-manager`. Backups of the replaced files
  live under `/var/lib/h713-hdmi-startup/` on the board.
- Leftovers in `/root` on the board, all diagnostic and safe to delete:
  - swap and install scripts: `swap-*.sh`, `install-capture-unit.sh`;
  - zeroing test: `zero-ring.py`, `h713-zero-ring.service`;
  - live register tests: `selector-cover-test.py`, `vblend-cover-test.py`;
  - staged modules and units: `h713-hdmi-v4l2-*.ko`, `*.new`;
  - old packages: `*-package` and `*-bundle` directories.

  Keep the `/var/lib` backups until the next release build supersedes them.

## 4. Open work, in suggested order

1. **Signal service start-up (~0.25 s before HPD).** `h713-hdmi-signal.py
   start` spends most of its ~0.33 s on Python start-up and imports
   (`argparse`, `subprocess`, ...). Profile with `python3 -m cProfile` on
   the board and trim or defer imports. HPD then comes up sooner, which is
   the only lever before the PC's reaction time.
2. **Stale first frames on warm reboot (theoretical).** On a warm reboot the
   first 4-5 slots after lock hold the previous boot's last picture. The
   zero check can't catch that. Nobody has seen it, but it may show as a
   brief old-picture flash. A proper fix would skip slots until capture
   has written them once.
3. **Remaining prepare time (~4 s).** Five receiver clock stages, each
   followed by a MIPS `help win` IPC check (~0.45 s, the firmware's reply
   time), then the audio module (~0.2 s now). Whether every stage needs its
   own IPC check has not been examined.
4. **Release.** The final release build (run twice for reproducibility),
   deployment packet, lifecycle regression and qualification are still
   pending. The release build (`tools/release/build.py`) now produces all
   of the above from source. Rebuild and re-pin anything that pins the old
   installed hashes.

## 5. How to work safely on this board

- **Commit or push only when the user asks.** Push only to `cstenger/*`.
  `git push` needs to run outside the sandbox (1Password SSH agent).
- **The HDMI source PC runs the assistant.** Never log out or reboot it.
  Board commands that outlive the ssh session must be detached.
- **Cold boot** means: unplug serial and USB, power off for at least 1
  minute, then power on. The user does this; shut the board down first
  (`systemd-run --on-active=1 systemctl poweroff`) and confirm it's down
  (ping) before asking. Operator-timed tests get their own turn: ask, then
  wait for "done".
- **Warm reboot** from the host: `systemd-run --on-active=1 systemctl
  reboot`, then poll for a new `/proc/sys/kernel/random/boot_id`. It resets
  the DSP (versions 0/0), so it's the cheap test loop for DSP/startup work.
- **Health:** every boot must end `running` with no failed units.
  `h713-hdmi-health-ack` must set RTC GP6 to `HDOK`; U-Boot's crash-loop
  guard reads it.
- **Verify boot-critical changes on a cold boot.** U-Boot's image-size
  check and the `h713,hdmi-boot-v1` handoff only run on the cold path.
- **Hard locks:** never read `0x07091000` (CPUS/ARISC) or `0x06940000`.
  `0x05001530` wedges the SoC on the logo-free path.
- **Rebuild baselines byte-for-byte first.** Before changing a module or
  kernel, rebuild the unmodified source and match the installed hash; only
  then is a diff evidence. Recipes:
  - kernel: `local/recovery/2026-11-09-legacy-ptys/kbuild.sh` (release
    epoch 1793693083, `KERNEL_CONFIG=production`);
  - audio module: `local/recovery/2026-11-10-dsp-gap/mbuild.sh`;
  - bridge: `local/recovery/2026-11-10-first-frames/vbuild.sh`.
- **Kernel/script installs** go through `tools/hdmi/build-kernel-fit-bundle.py`
  (checks config diff, `Module.symvers`, release and DTB) and
  `tools/hdmi/install-kernel-fit.py` (guarded, FIT before script, full
  rollback).
- **Audio check:** `tools/hdmi/run-pipewire-tone-check.py <new-dir>` plays
  1 kHz/2 kHz from the PC over HDMI at 48/32/44.1 kHz. The board records
  through PipeWire, with the speaker muted during the test. The rootfs has
  no `arecord`.
- **Panel checks need the user's slow-motion recordings** (`local/lcd-photos/test_*`,
  4x slow motion, so 1 s of video = 0.25 s real). Scan them per frame
  (`ffmpeg -vf scale=64:36 -f rawvideo -pix_fmt rgb24`) and look at the
  frames. The boot logo's text and the console text are green-tinted, so a
  "green" flag there is not a flash.

## 6. Traps that cost time in this session

- **Results that can't fail.** Each of these produced a false all-clear:
  - `tools/re/awemu.py` silently swallows `usleep`, `malloc`, `memcpy`,
    `free` and a few more before user hooks run. It gave "stock has no
    sleeps", which was false; rename the stub to record it.
  - `llvm-objcopy ... /dev/stdout` writes nothing, so section hashes of
    empty output all matched.
  - `mmap.flush()` on a `/dev/mem` mapping raises EINVAL. It came after
    the writes, so the writes did happen; don't misread the error as "no
    write".

  Always find the line that would have failed, or prove the check catches
  a known-bad input.
- **Units are a chain.** Capture owns the session teardown, and the signal
  unit starts after it so it stops first at shutdown. Don't reorder; change
  only `ExecStart`.
- **The release's module tests compile real C.**
  `tools/hdmi/test-frame-discard-contract.py` extracts the bridge's capture
  loop and builds it against stubs. A new helper in that loop must be added
  to its extraction.

## Update 2026-11-11

The signal-service optimization is installed and remains uncommitted in
`tools/hdmi/h713-hdmi-signal.py`: exact `start` bypasses argparse, while the
bench CLI and shutdown path retain it. Installed SHA-256 starts `b5244934`;
rollback is recorded in `local/recovery/2026-11-10-signal-startup/RESUME.md`.
Three warm boots improved service-start-to-HPD by about 34 ms at the median.

A one-frame lower-panel green flash in `test_118` is confirmed but remains
unresolved after unsuccessful reproductions. Investigation was deferred on
2026-11-11. See the new follow-up section in the production-evidence README.
Diagnostic video overrides and the panel recorder service have been removed;
the board is healthy on the production video command. Evidence and backups
are retained. No kernel/module changes or commits were made in this follow-up.

The four-check HDMI prepare variant is now installed for cold qualification.
`h713-hdmi-session.py` SHA-256 starts `fef5210d`; its bundle manifest starts
`6a250223`. Three warm boots and all nine three-rate tone trials passed.
Median prepare duration was 3.770 s versus the measured 4.214 s baseline.
The final duplicate clock-4 IPC check was consolidated with the readiness
gate, preserving a check after every hardware stage. Rollback and qualification
records are in `local/recovery/2026-11-11-four-ipc/RESUME.md`. Cold boot
`1dd76235` passed on 2026-11-11, with four IPC replies, prepare 3.674 s, HPD
8.557 s, signal lock 9.896 s and video-service start 9.959 s. Three-rate audio,
zero XRUNs, health and preceding shutdown restoration passed. These source/test
changes are uncommitted.

A separately authorized shorter-probe comparison passed without changing the
startup implementation or installed files. `cmds` was traced to command-table
listing/formatting, with seven live code/table ranges matching the reviewed
firmware. Eight balanced pairs measured 448.44 ms mean for `help win` versus
251.38 ms for `cmds`: 197.06 ms saved per probe, projecting to 0.788 s for
four checks. All nine `cmds` replies were the same complete 917-byte response;
rings ended empty and health/hashes passed. See
`local/recovery/2026-11-11-short-probe/RESULT.md` and `ROLLBACK.md`.
Adopting the pinned shorter reply in startup still needs separate approval,
negative/mutation tests and warm/cold/audio qualification; keep all four gates.

## Update 2026-11-13: pinned cmds installed, warm qualification passed

The user authorized adoption of the pinned `cmds` probe, keeping all four
receiver-stage gates. Installed session SHA-256 starts `06ab1e7a`, MIPS helper
`5d0dd84e`, and bundle manifest `a552c7f5`. The full command-list reply remains
required, with the same lock, deadline, stale-output handling and request
consumption check. A tracked 917-byte fixture is at
`docs/production-evidence/2026-11-09-startup-and-parallel-aic/cmds-reply.reply`.

Three warm boots passed: prepare 2.924/3.032/2.664 s; all four checks completed
on each. Median aggregate IPC wait fell from 1.752 s on today's baseline to
0.969 s. All nine three-rate audio trials passed, with restored speaker state
and zero XRUNs. Preceding shutdown ordering, signal/DSP/TVFE restoration and
terminal parking passed. Final boot before cold-test shutdown is `ee151004`.

Preview, exact original/candidate files and rollback are recorded in
`local/recovery/2026-11-13-cmds-probe/RESUME.md`; board backups are under
`/var/lib/h713-hdmi-startup/cmds-probe-2026-11-13`. Negative tests cover altered
or missing rows, legacy replies, stale/partial/unconsumed replies and retained
stage gates; all 13 mutations were caught. Cold qualification is still pending.
No module/kernel changes, commits or pushes were performed.

The board has now been powered off and confirmed offline by three consecutive
failed pings plus SSH timeout. Wait for the operator's cold power cycle and
done reply before continuing. Retrieve the previous boot's persisted shutdown
journal on return; its live SSH follower closed before teardown messages.

Cold qualification completed on 2026-11-13, boot `bc095368`. The board is now
running with the qualified pinned cmds variant. Exactly four complete replies,
cold handoff, receiver/EDID/DSP readiness, HDOK and previous poweroff restoration/
parking passed. Prepare 2.811 s, kernel HPD 7.745 s, signal lock 9.076 s and
video-service start 9.131 s. All three cold audio rates passed, completing 12
warm/cold tone trials; speaker state restored, recordings removed, zero XRUNs
or unit restarts, running/no failed units and full bundle hashes passed.
Cold records are in `local/recovery/2026-11-13-cmds-probe/cold/`; exact rollback
remains in that experiment's RESUME.md. Source/test changes remain uncommitted.

Read-only pre-clock investigation is recorded in
`local/recovery/2026-11-13-preclock-review/ASSESSMENT.md`. The cold interval
from prepare fork to first clock is 1.551 s; systemd handoff accounts for 79 ms.
Cached, idle-board imports/parsing/preflight take ~255 ms plus ~101 ms Python
startup. Existing logs do not separate the remaining boot overhead from module
insertion/early park preparation. A matched in-memory CLI fastpath saves only
~33 ms; os.uname and batching modinfo offer ~14 ms more. Recommendation is a
single lightweight wall/CPU span trace at boot before any further optimization;
that trace has not been installed or authorized. Board/configuration unchanged.

The user subsequently authorized that single warm-boot trace. It completed on
boot `f1151ea9`, then the qualified session (`06ab1e7a`) and manifest (`a552c7f5`)
were restored and verified. The board is running, no failed units/restarts or
audio XRUNs; all four cmds checks and preceding shutdown passed. Monotonic
timing needs no RTC battery, NTP or calendar correction.

The trace resolved the gap: 817 ms from exec handoff to first Python statement,
612 ms in imports, 44 ms parsing, 74 ms guards, 24 ms receiver insmod and 0.5 ms
first clock write. Python startup/imports account for 83.5% of 1.711 s before
the first clock. Imports used only 248 ms CPU over 612 ms elapsed; I/O versus
scheduling remains unseparated. A guarded read-only -S comparison did not show
a meaningful cached-workload gain. Keep the qualified version unchanged; any
large next optimization needs attribution of that off-CPU time or a larger
native-start development effort. Full record:
`local/recovery/2026-11-13-preclock-trace/RESULT.md`. No commits/pushes.

Further read-only storage/scheduler attribution feasibility is in
`local/recovery/2026-11-13-python-waits-review/ASSESSMENT.md`. Shipping kernel
has no schedstat/task-I/O wait totals. Per-child CPU-clock/state/wchan/stack
sampling works; sleep, host-only known contention and board read-only direct
storage controls distinguish the cases. Cached guarded preflight probes showed
~3–6 ms estimated runnable delay and no sampled storage sleep, not the boot's
delays. An initial per-interval estimator falsely manufactured >100 ms waiting
and was rejected; use same-window aggregate CPU/state totals, with uncertainty.
Zero major faults or I/O counters does not rule out storage (demonstrated by
the read-only storage control). Next proposed test is one native-supervised
warm boot with phase-matched samples and CPU-frequency observation, preserving
all four checks and restoring qualified files afterwards. It is NOT installed
or authorized yet. Board/configuration remained unchanged and healthy.

At the user's request, the next warm-boot test is now prepared locally at
`local/recovery/2026-11-13-python-waits-test/README.md`, but NOT installed or
rebooted. The static AArch64 native supervisor avoids preloading Python's shared
libraries, samples CPU/state/context switches/wait stacks/faults/frequency, and
stops sampling after first-clock observation while waiting for all four checks
to finish. Marker logic is the previously tested candidate. Install/rollback,
native controls, one-reboot collection and automatic restoration are prepared;
offline/negative tests, reproducible cross-build and qemu smoke passed. Final
read-only board preview passed against f1151ea9 and confirmed the qualified
files, no diagnostic artifacts and zero XRUNs. Installation/reboot still needs
go-ahead. Full hashes and exact commands are in that package.

## Resumed Python wait trace — 2026-11-14

The authorized temporary revision-3 test completed one warm reboot after the
user powered both machines back on. Preview/new rollback were recorded before
writes. Current boot `7c9c1c7c-861f-4a7d-bb03-1c9dfd52f85d` is running with
qualified session `06ab1e7a`, helper `5d0dd84e`, manifest `a552c7f5` and prepare
unit `64d4ecd6`; full bundle/original ExecStart verified. No failed units,
restarts or XRUNs; all four pinned cmds gates, HDOK and prior shutdown passed.
Diagnostic sampler/RAM artifact removed after verified retrieval; backups remain.
No kernel/module changes, host power operation, commit or push.

Markers show 653 ms child-exec-to-first-statement and 383 ms imports, totaling
1.036 s of 1.256 s before clock 1. Imports used 235 ms CPU. Native observer
CPU 8.054 ms passed its budget; all frequency snapshots were 1.296 GHz.
File-read/executable-page storage waits were witnessed, but their duration is
unknown. Scheduler attribution FAILS coverage: combined loss/rejection counter
10013, one sequence error; supplemental snapshots are also insufficient. Do
not use the computed runnable/blocked split or claim another >=100 ms saving.
The combined counter cannot identify actual kernel loss versus PID/parser
rejection; improve diagnostics/negative controls locally before proposing any
new board experiment. Qualified startup remains unchanged; no next test is
authorized. Full result and evidence:
`local/recovery/2026-11-13-python-waits-test/RESULT-2026-11-14.md`.

## Recorder correction/stress tests — local only, 2026-11-14

At user request, revision 4 was corrected and tested entirely on the host; no
board access/write/reboot. Historical r3 bytes/results remain intact. R4 uses
a 1 MiB perf ring, 131072 retained switches, independent 10 ms perf drains/50 ms
proc samples, separate loss/rejection reasons, bounded wrong-ID examples and
a process-CPU consistency gate. All four IPC checks and startup sequencing
remain unchanged (30 session tests/startup AST equivalence passed).

Three ~50000-switch runs and three real file-fault runs had zero loss and valid
coverage. The old recorder, intentionally tiny ring and tiny event-array variants
failed under the same load and were rejected. 26 package tests, three C guard
mutations, six Python/status mutations and ASan/UBSan passed/caught expected
failures. Static ARM64 build reproduced; qemu status/JSON smoke passed, not perf
or performance qualification. CPU-accounting versus switch-timestamp discrepancy
is reported/checked, not normalized away; host overhead is not ARM evidence.

Next proposal: prepare guarded r4 deploy/collection, preview/new rollback before
writes, run native timer/storage/cached/burst controls with <=20 ms observer CPU
and zero loss, then ONE warm reboot and automatic qualified restoration. User
approval is pending; nothing installed. Candidate sampler 7577ab68, manifest
e198bdf8; qualified original hashes unchanged. Full details/results/limits:
`local/recovery/2026-11-14-python-waits-r4/README.md`.

## R4 native preflight halted/restored — 2026-11-14

User authorized the revised warm test. Exact preview/new rollback preceded
installation (backup python-waits-r4-2026-11-14). First native timer control
used20.844958ms observer CPU, exceeding the fixed20ms budget. The failure path
restored qualified files immediately. NO warm reboot/boot trace; storage, burst
and cached native controls were not run. No retry/limit relaxation.

Timer had47 switches, zero loss/rejections and valid switch/CPU coverage; CPU
discrepancy0.420ms. This confirms basic native sideband delivery, not burst
qualification or low enough overhead. Frequency varied480–1296MHz; do not
attribute overhead solely to polling without further measurement.

restored-health.txt verifies same boot7c9c1c7c, qualified session06ab1e7a,
helper5d0dd84e, manifesta552c7f5, unit64d4ecd6, full bundle and original Python
ExecStart; sampler/trace absent, running/no failed units/restarts/XRUNs. All
four cmds gates unchanged; no fresh boot/audio qualification. Backups retained,
no host power/kernel/module/commit/push action. Full outcome and follow-up
proposal: local/recovery/2026-11-14-python-waits-r4/RESULT.md. Next proposed
step is local observer-cost profiling/event-driven drains; not yet authorized.

## DDR3 kernel follow-ups — hardware checked, 2026-11-14

At the user's request, kernel patches 0191–0197 from the attributed well0nez
review were installed and tested. Release-equivalent baseline rebuilds match
the formerly installed FIT and Cedrus module exactly. Current installed FIT
is `22ee12d4`, Cedrus module `1c8c87ba`, and startup script `79c039ac`.
The guarded FIT installer now supports the paired Cedrus file update; the
bundle builder permits only the expected PIO DT interrupt-list change.

Warm boot `14fa86b6` passed seven bit-exact HEVC/VP9 vectors (748 displayed
frames), three malformed HEVC control/recovery checks and eight real PH17
input IRQ edges. PH17 was restored to unclaimed/input/bias-disabled, and its
test module was unloaded. The initial malformed-reference harness incorrectly
required a nonzero pipeline exit; the preserved corrected run verifies the
kernel rejection and clean recovery instead.

Cold boot `0fa73d3d` enumerated the SanDisk SSD at 480 Mb/s on EHCI0 with
preboot `usb start` temporarily removed. After the host-session interruption,
boot `2f81b106-80ae-4fee-8883-d026a724f770` resumed and the **original saved
environment was restored byte for byte** (`e6a56d4c…`). Current health is
running/no failed units, four startup IPC gates pass, health ACK succeeds,
and the SSD is read-only/unmounted. The candidate remains installed. This hardware verification preceded
publication of the fixes and GitHub replies.

Results and limits: [DDR3 hardware record](reviews/well0nez-2026-11-14/hardware.md).
Exact recovery commands and receipts:
`local/recovery/2026-11-14-kernel-followups/RESUME.json`. The paired original
kernel/script/module backup is
`/var/lib/h713-hdmi-startup/kernel-fit-74b3f9c8971d48cd9a5efe475b568547`.
No general damaged-stream/AV1 concurrency, other USB ports, gadget operation,
physical R_PIO-key/host-wake stimulus, or LPDDR3 tests are implied by this run.

## CPU_COMM IRQ trial — restored polling, 2026-11-14

0198/0199 prepare the attributed stock IRQ mapping and owned threaded RX
trial path. IRQ-only reception passed 203 serial calls (406 RX messages,
zero polling), but four concurrent clients then timed out. Polling A/B
passed all 200 concurrent calls. A repeat IRQ boot `8a148120` suffered kernel
memory corruption with MIPS-looking pointers and needed an operator power
cycle after UART SysRq failed. IRQ mode is **not qualified**; the review
patch retains polling by default. Shared-memory coherency/lifetime and
deferred dispatch need investigation before another IRQ trial.

The board was guardedly rolled back and is healthy on boot `dbe874ad`:
FIT `22ee12d4`, CPU_COMM `8244df26`, startup script `79c039ac`, Cedrus
`1c8c87ba`. Three polling recovery calls, all startup gates and health check
pass; no failed units. Original saved environment `e6a56d4c…` unchanged,
modprobe trial override removed. SSD absent at final check after the power
cycle (no SSD writes by these trials); USB was not requalified. Trial candidates
are not installed. No commit/push/GitHub comment in this follow-up.

Results: [CPU_COMM IRQ trials](reviews/well0nez-2026-11-14/cpu-comm-irqs.md).
Exact local receipts/capture: `local/recovery/2026-11-14-cpucomm-irqs/RESUME.json`.

## CPU_COMM handoff follow-up — board off, final bundle ready

Latest user state: board powered off. CP2102 moved to ttyUSB1; use its stable
`/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`
path. New capture uses `local/recovery/2026-11-14-cpucomm-handoff/quarantine-uart/`;
never replay the older TX queue.

0200 fixes counter claim races, out-of-range reference translation, invalid
slot-20 writes into the next sequence header, session-bound ACK validation,
and RETURN ACK-before-wake with timeout exclusion. Host regressions reproduce
three original defects; production build and actual-source tests pass.
0201 preserves a publication after missing CALL_ACK, quarantines sends and
refuses an already outstanding SENT header. Final 0200+0201 module is
`ad2f15f27fb13f248a5d1374df9598b4b7a6de94a06ec1002b7aee22b8a734be`;
FIT remains `091cf636...`. Bundle is `local/recovery/2026-11-14-cpucomm-handoff/quarantine-bundle/`.
It is built and guarded, **not installed or hardware-qualified** yet.

0200 is currently installed, with no IRQ trial override; next boot is polling.
The original baseline backup is
`/var/lib/h713-hdmi-startup/kernel-fit-280eaee55a1041a3a82deaee9f12f21e`.
Rollback that transaction before applying the new baseline-pinned bundle.
Full restore command and hashes are in the local `RESUME.json`.

A matched longer polling control also stalls near 240 total calls; the earlier
shorter polling A/B cannot attribute this stall to IRQs. Firmware synchronously
flushes its full 2 MiB log to UART; session f1 returns over 90 seconds late.
0200 safely ACKs/drops that orphan without waking a recycled wait, Linux stays
healthy. Three recovery plus 600 serial calls pass after draining; a later
concurrent burst again times out, so stress qualification remains incomplete.
The exact original corruption interleaving remains unknown.

Before stress, set native firmware `elog -l 2` and verify its actual global
filter in RAM using aligned loads. Actual CLI emulation proves its setter;
runtime verification is pending. The driver's old ELOG offsets are 0x14 stale
for this firmware: do not blindly use them to modify RAM. Reapply the native
filter after each firmware boot. Qualify >1000 serial/concurrent calls in both
modes and repeat IRQ boot, with no polling fallback, before claiming success.
See [handoff investigation](reviews/well0nez-2026-11-14/cpu-comm-handoff.md)
and its machine-readable validation receipt. No commits, pushes or new GitHub
comments have been made during this follow-up.

### Subsequent 0201 quiet-run result and 0202

0201 installed and three polling calls passed on `b95e47b4`. A MIPS shell
`regr` query stopped SSH/UART before stress output; SysRq failed and the
operator cold-cycled. Do not repeat that native register query.
On `84835e4d`, native `elog -l 2` later reads back as level 2. 603 serial
calls pass; 595 of the concurrent requested calls complete, two callers
time out waiting for RETURN. Linux remains healthy, TX is not quarantined,
but firmware normal tasks/shell cease progress. ELOG count `0x696cf` is
well below capacity. This is a separate failure from full-buffer flushing.

Saved MIPS context contains the assertion PC `0x8b125a54` and stack arguments
for `tridspinlock.c:326`. Firmware uses gate byte 0 and software-owner byte 1;
our old driver used byte 3 for both. 0202 corrects the two-level ABI, refuses
forced entry on hardware timeout, and binds ARM ownership to thread pid.
Host tests reproduce the old free-owner/nonfree-thread conflict and pass
3000 contended ARM/MIPS critical sections with corrected actual functions.
Production build and guarded installation pass. Module now `abb731ff...`,
FIT still `091cf636...`; package `/root/cpucomm-handoff-20261114/spinlock-bundle`.
Current original-baseline backup:
`/var/lib/h713-hdmi-startup/kernel-fit-787770fdceab411192a931dceabff979`.

The requested warm reboot was refused by the HDMI hold guard because the
stalled firmware retained the receiver hold; the board powered down. User
asked for a cold power-cycle. Next boot remains polling, no IRQ override.
Repeat the long quiet polling test before opting in to IRQ. Latest exact
state is in `local/recovery/2026-11-14-cpucomm-handoff/RESUME.json`.
