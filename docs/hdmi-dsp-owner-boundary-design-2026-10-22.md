# No-reset patched control and matched shutdown boundaries — October 22, 2026

**Prepared and built offline. Board remains powered down; no capture armed,
no board files/services/modules changed.**
[Build/test evidence](hdmi-evidence/2026-10-22-dsp-owner-boundary-preparation/README.md).

The two [control-only trials](hdmi-evidence/2026-10-22-dsp-minimum-control-replication/README.md)
qualified completed version access with AudioTop `700/0`, but both read zero
after orderly shutdown, reset, a warm logo and interface preparation. Source
review adds a crucial earlier bracket: normal audio removal first restores
22 saved DSP graph words, later restores AudioTop configuration/control,
then restores clocks and can assert demod reset. The existing data do not
isolate CPU reset as the first loss point.

## Two runs in the next batch

1. **Arm 1 — sham positive control:** fresh guarded cold startup; initialize
   the normal pinned patch/graph once using an isolated copy of the audio
   owner. Verify fresh initial-zero → patched `1/1` journal and live source3.
   Keep that owner, clocks and both domains held. Obtain four explicit version
   pairs with matching checkpoints/settling waits, without graph restoration,
   AudioTop changes, module removal, reset or warm logo after patching.
   All four must complete `1/1`; otherwise do not run arm 2.
2. **Arm 2 — matched shutdown prefix:** separate disconnected cold cycle,
   identical script/module/firmware/kernel and initialization. Require the
   exact successful sham record, fresh boot ID, identical baseline register
   census and all 22 saved graph words. Obtain a patched positive pair,
   then observe after graph restoration, after config clear, and after
   control off/on, stopping at the first changed/mixed pair or timeout.

There is **no CPU/MIPS/demod reset or warm logo after the verified patch**
in either arm. The usual cold source3 launch/normal setup occurs before
patch initialization, once per physical power cycle. The normal module's
initial patch and graph writes are deliberate baseline setup. The boundary
arm's graph restoration is the exact existing reverse-order, verified
22-word normal teardown, using saved values; it is not a new patch or an
arbitrary address interface.

## Fixed implementation and isolation

Candidate: `build/hdmi-dsp-owner-boundary-2026-10-22/candidate/`.
Both arms use the same module and 4,360-byte RAM script. Immutable load
parameter `owner_arm=1|2` selects the arm; a RAM DT marker
`h713,dsp-owner-boundary-v1=<0x4f574e31>` and fresh cold proof are required.

* Production kernel unchanged: `6.18.38 #1 SMP Fri Oct 16 15:44:49 PDT 2026`,
  FIT SHA-256 `0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70`.
  This is **not** the earlier warm minimum-observer kernel.
* Isolated audio module SHA-256
  `6cbc305cfcd14b20d9c72c25c293402cc2c7490d1cf3e977ba60654c5bf62001`.
  Same kernel headers/Symvers/vermagic; loaded GNU build-ID note verified.
  Production audio/receiver sources and installed startup script are pinned
  by hash before building. Normal source/module files are not edited.
* Cold script SHA-256
  `0f3245113d33501761e51aa87c59980e63e03c2569d6b05e3276b47d18e6e1d1`.
  Derived from the exact installed cold startup path, with all cold-latch,
  MIPS/source3/worker/DT checks retained. Warm fallback is removed. Lamp off.
  Adds only the bench DT marker and explicit boot args including `panic=0`,
  `loglevel=7`, bench opt-in and runtime masks for capture/signal/speaker.
  Does not save environment or replace boot media. Normal cold GP6 latch
  publication remains; no GP6 clear/reuse or GP7 write is added.
* Sole audio owner reserves the DSP port/stock lock as normal. No independent
  probe competes with it. PCM registration is omitted and audio IRQ handlers
  disabled before measurement in **both** arms. A module lifetime pin keeps
  normal unload/teardown from running between checkpoints. Receiver remains
  held and MIPS live; no signal/DDC/SCP helper or userspace capture starts.
* Initialization refuses nonzero saved AudioTop control/config, an existing
  audio/receiver owner, existing ledger/proof, or an unqualified arm-2 sham.
  Existing owner helper performs its established per-clock IPC/readiness
  checks before loading the bench module and restores firmware search path.
* Health checks gate PPU reads on the open PPU bus, require both domains
  ON/idle and MIPS exactly live, and check exact expected AudioTop values.
  The control-off step reads only those health/AudioTop registers; no DSP
  or AudIf access occurs until control is restored. Audio IRQs remain disabled.

## Explicit sequence

Sysfs is `/sys/module/h713_hdmi_audio/parameters/{owner_step,owner_state}`;
state schema `h713-owner-boundary-v1`. Reading state is software-only.

| Steps | Operation |
| --- | --- |
| 1 | Safe health/control/config census; require exact `700/011a5e00` |
| 2–6 | Claim stock ARM lock; one device-0 read; one device-1 read; release/readback; positive checkpoint |
| 7 | Arm 2: exact 22 saved graph-word restorations under stock lock, each verified; keep maps/clocks/module held. Arm 1: no writes. Common settling wait |
| 8–12 | Claim; device 0; device 1; release; graph-boundary checkpoint |
| 13 | Arm 2: config `011a5e00` → `0`, exact readback, control stays `700`. Arm 1: no writes. Common settling wait |
| 14–18 | Claim; device 0; device 1; release; config-boundary checkpoint |
| 19 | Arm 2: control `700` → `0`, exact readback. Arm 1: no writes. No DSP access |
| 20 | Arm 2: control `0` → `700`, exact readback. Arm 1: no writes |
| 21–25 | Claim; device 0; device 1; release; terminal health/checkpoint |

Each host `step` writes one exact next operation; do not loop checkpoints or
synthesize acknowledgments. Snapshot/review all boundaries in the helper's
`STAGES` map before the matching `--stage-ack`. The graph restoration is one
bounded existing teardown transaction with its own claim/release and up to
22 verified normal restore writes. UART identifies every restored word.
This transaction can fail partway; no rollback or retry is provided.

Every pair requires a patched predecessor before another intervention.
After any non-`1/1` completed pair the checkpoint becomes terminal: step 6,
12, 18 or 25. Do not continue to a later boundary. A timeout suppresses
remaining device requests in the current pair, permits only its lock release
and checkpoint, then export/poweroff. Graph-restore error, health/readback/
lock error or uncertain host ledger is a hard stop; no further bus commands,
forced cleanup, unload, restart, extra patch or reset. Physically disconnect
if orderly software handling cannot be confirmed.

Version requests use only logical `0x80ff`; maximum eight diagnostic request
writes per complete arm. Graph restoration additionally uses the established
22 graph addresses/readbacks. Busy/done waits are 50 ms, peer lock checks
10 ms. Retain full raw words, phases/outcomes/sent/status, `graph_saved[22]`,
remaining graph words, exact AudioTop values and UART BEGIN/DONE. A host call
must have a fixed deadline (20 s for each observer step, 60 s for initialize)
and a sole continuous UART reader. A stalled MMIO access is not bounded by
these protocol polling deadlines; missing return/DONE means stop, not retry.

## Live runbook, only after capture is separately armed

Keep board fully disconnected for at least one minute between arms. Use
separate host trial directories and fresh remote bundle directories, e.g.
`/root/hdmi-dsp-owner-boundary-2026-10-22/sham` and `.../boundary`.
Never copy a previous `arm-proof.json`, ledger, owner-arm file or baseline.

1. Arm `catch-cold-uboot.py` and verify OPEN before requesting power. Require
   one cold SPL, GP6/GP7 zero, MIPS parked, correct proper U-Boot and prompt.
2. Use the prepared cold-only loader:

   ```sh
   python3 tools/serial/run-dsp-owner-cold.py \
     --port /dev/ttyUSB0 \
     --prepared build/hdmi-dsp-owner-boundary-2026-10-22/candidate \
     --cold-catch TRIAL/cold-catch/serial.log --arm 1 --output TRIAL/cold-boot
   ```

   For arm 2 use `--arm 2 --sham-record SHAM/snapshot-25.json`. This must be
   the exact exported successful sham snapshot subsequently staged on board.
   Loader verifies fresh cold evidence, unchanged normal bootcmd, production
   FIT size/CRC and script hash; YMODEM sends only the small script to RAM
   with CRC verification. One `source` runs the established cold launch.
   Fixed 90 s UART capture; never retry a launch or run normal boot afterward
   as recovery. Require source3/handoff success and exact production kernel.
3. Reconnect host Wi-Fi to `spirits`. Verify `panic=0`, console threshold 7,
   bench marker/handoff and runtime masks. All three HDMI services must be
   inactive and neither receiver nor audio loaded yet. Set `dmesg -n 7` if
   needed. Stage only `candidate/bundle/` in a fresh bench directory, plus
   `arm-intent.json` from this cold loader; for arm 2 stage its exact
   `sham-record.json`. Do not install modules/services/firmware over normal
   files. Verify bundle hashes and unchanged installed guard/original backup.
4. Keep sole passive UART capture. Run once, with a fixed host deadline:

   ```sh
   python3 REMOTE/dsp-owner-boundary.py --bundle REMOTE initialize \
     --intent REMOTE/arm-intent.json
   ```

   It binds the new boot, creates an uncertain ledger before setup, invokes
   only the established cold source3 receiver/audio initialization, verifies
   loaded module build ID/arm, initial-zero → patched journal and active
   domains, records baseline and marks proof verified. Any failed initialize
   is terminal for this cold cycle. Do not stop/unload the pinned owner.
5. Snapshot first, then invoke explicit next steps:

   ```sh
   python3 REMOTE/dsp-owner-boundary.py --bundle REMOTE snapshot
   python3 REMOTE/dsp-owner-boundary.py --bundle REMOTE step --number N \
     --stage-ack EXACT_REVIEWED_STAGE
   ```

   Omit acknowledgment only when prior cursor is not in `STAGES`. Export
   each return to a unique host file; validate status and inspect snapshots
   before the next boundary. State and module build ID/proof are rechecked.
6. At a released terminal checkpoint, take its final snapshot, run `export`,
   retrieve the archive, verify the reported size/SHA-256, and save all UART,
   command records, proof, baseline and kernel journal on the host. Run:

   ```sh
   python3 REMOTE/dsp-owner-boundary.py --bundle REMOTE export
   python3 REMOTE/dsp-owner-boundary.py --bundle REMOTE poweroff \
     --export-sha256 VERIFIED_ARCHIVE_SHA256
   ```

   Record `reboot: Power down`, close recorder, physically disconnect and
   leave off. Do not invoke session `stop`, `park`, `shutdown`, rmmod, reboot
   or kexec: those would introduce teardown/reset and break this test.
7. Analyze the exported snapshot; compare exact sham first and boundary second:

   ```sh
   python3 tools/hdmi/analyze-dsp-owner-boundary.py SHAM/snapshot-25.json BOUNDARY/FINAL.json
   ```

## Interpretation and remaining runs

| Result after a qualified sham | Meaning / next action |
| --- | --- |
| Positive pair not `1/1`, timeout, changed sham or failed setup | Access/control unqualified; stop and review. Do not attribute loss or proceed to boundary arm |
| First completed change after graph restoration | Loss of reported patched version associated with the verified graph-restore transaction and following pair; no later AudioTop/reset/logo intervention occurred |
| Graph pair stays `1/1`, first change after config clear | First observed change bracketed around config clear and its read pair, after graph restoration was qualified |
| Graph/config pairs stay `1/1`, first change after control off/on | Bracket includes control off, restoration to `700` and its read pair. No safe DSP read while control is off is assumed |
| All four pairs stay `1/1` in both arms | Tested prefix preserves the patch report; next matched batch addresses remaining SPDI/bridge teardown, clock restoration/demod reset, then CPU reset/early boot/logo as required |
| Timeout or exact command echo `80ff0000` after a boundary | Access/completion ambiguity, not version zero or proof of erased patch |

A completed zero here is the established stock version protocol's observation,
not direct RAM inspection. Immediate completion remains allowed; no new
clear-edge requirement is invented. Full raw words and matched patched sham
help expose aliasing/echo failures but cannot prove a physical erasure
mechanism. Normal shutdown also restores SPDI/bridge state between graph
and AudioTop teardown; this focused test omits those operations in both arms.
Thus a loss identifies a sufficient observed boundary in the controlled
path, not automatically the earliest instruction in full normal teardown.
Timing is recorded; sham has the same checkpoints/settling waits, but host
review gaps and graph-transaction duration are not cycle-identical.

**Count:** two new cold-cycle runs are planned now. If a clear boundary
appears, plan one additional independent confirmation run. If all tested
boundaries preserve `1/1`, allow roughly two to four further matched runs
to split the remaining teardown/reset/logo bracket. This is an estimate,
not a guaranteed upper bound; failed positive controls or contradictory
results require review rather than an automatic chain of more tests.
Control-only access qualification is finished; no more repeats are planned
unless a changed experiment invalidates that access recipe.

The installed bench guard and exact original mode-0755 backup remain
unchanged. Restore only after a fully disconnected cold normal boot and hash
checks. No automatic recovery or production one-launch policy relaxation.
