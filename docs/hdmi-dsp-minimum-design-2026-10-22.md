# Minimum AudioTop setup for DSP version access — October 22, 2026

**Level 1 sufficiency replicated October 22: control `0x700` alone completed
both DSP version reads, returning `0/0` without timeout in two separate cold
cycles. Board powered down; recorder closed.**
[First trial](hdmi-evidence/2026-10-22-dsp-minimum-control-live/README.md),
[replication](hdmi-evidence/2026-10-22-dsp-minimum-control-replication/README.md).
Both trials passed all 58 steps with configuration/latch writes skipped,
exact final control/config `700/0`, and identical terminal observer state.
The replication captured the full cold SPL, addressing the first trial's
missing cold capture. Control-only access is sufficient under the tested
one-logo warm path; minimum individual bits and patch-loss timing remain
unresolved. Next work is a no-reset patched positive control and a matched
boundary experiment. Reset/early boot, warm logo, interface preparation and
the control write remain inside the loss interval.
The [next owner-based positive-control/boundary batch](hdmi-dsp-owner-boundary-design-2026-10-22.md)
is now prepared offline and tests graph/AudioTop shutdown operations before
adding another reset or warm logo.

The [boundary trial](hdmi-evidence/2026-10-22-dsp-boundary-one-logo-live/README.md)
failed before AudioTop setup: device 0 timed out, status `0x10`, no completed
version; device 1 was skipped. Its trace could not distinguish initial busy
from a published request whose completion never arrived. This candidate
selects setup **before the first request**, records the missing phases and
never adds setup after a timeout.

## Fixed setup levels

All trials use the same FIT and one normal warm logo after a fresh verified
cold production patch. An immutable early boot argument selects one level:

| Level | AudioTop operations before the first DSP attempt | Expected control/config |
| --- | --- | --- |
| **1 — first trial** | write control `0x700` only | `00000700 / 00000000` |
| 2 | control, then config `0x001a5e00` | `00000700 / 001a5e00` |
| 3 | control, config, then latch `0x011a5e00` | `00000700 / 011a5e00` |

A fresh census must be **exactly control/config `0/0`**; inherited or unknown
setup refuses the experiment. Each write is a separate acknowledged step
with exact readback. Unselected config/latch steps advance the software
cursor without touching AudioTop. No setup operation follows any request.

Start with level 1. If it completes both version reads, it is sufficient;
repeat it in another cold cycle before adopting a stable access recipe.
If a properly verified trial publishes a command and times out waiting for
completion, finish skip/release/final, power off, fully disconnect, then a
new separately armed cold cycle may test the next level. An initial-busy,
lock, resource, hold, ledger or MMIO failure needs review; do not automatically
interpret it as needing more setup. Every trial must have fresh cold/warm
boot IDs and a production DSP `0/0` → pinned patch verified `1/1` baseline.

This finds the lowest completed **nonempty prefix of the established stock
sequence under the tested warm path**, not the minimum individual control
bits or all alternative write orders. The previous no-setup failure is
context, not a phase-qualified, identical-FIT level-0 control. A successful
control-only result proves sufficiency, not that all three `0x700` bits are
necessary. The experiment does not claim when DSP RAM lost its patch.

## Candidate and protections

Candidate: `build/hdmi-dsp-minimum-2026-10-22/candidate/`; self-contained board
files in `bundle/`; fixed remote directory `/root/hdmi-dsp-minimum-2026-10-22/`.
[Preparation evidence](hdmi-evidence/2026-10-22-dsp-minimum-preparation/README.md).

* FIT: **7,754,772 bytes**, SHA-256
  `e1b475a8cb66ba86846a30dc8845c6cb0e76c8459f0d2bc2f3ba47edf63d8aeb`.
* Kernel `6.18.38`, exact version **`#4 SMP Thu Oct 22 02:35:16 PDT 2026`**.
  The full timestamp distinguishes it from the prior boundary `#4` build.
  Production exported symbol versions are unchanged.
* Mandatory flags: `h713_tvfe_trace=1 h713_tvfe_retain=1
  h713_dsp_minimum=1 h713_dsp_at_level=N`, with `panic=0 loglevel=7` and the
  existing ignore-unused flags. Level N is 1–3 and cannot be changed via
  sysfs. Without minimum opt-in or a valid level, no observer is published.
* Same tested warm-only TVFE hold: open PPU bus, GP6 warm latch, MIPS parked,
  SCP stopped, both domains already ON/idle. No OFF domain is powered on.
  Health checks and TVFE power-command violation latch remain enforced.
* Identical DT across levels: production plus disabled display/CPU_COMM and
  chosen marker `h713,dsp-minimum-v1 = <0x4d494e31>`. This avoids early
  display/CPU_COMM accesses and keeps the new trials comparable.
* Existing bench guard unchanged, SHA-256
  `5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`.
  Preserve original mode-0755 backup
  `/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard`, SHA-256
  `96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113`.

This is a separate RAM-only kernel, not a production update. No normal
FIT/script/DT/bootloader/environment changes. No observer DSP reset
assertion, domain power transition, DSP patch/graph write, MIPS/SCP launch,
source3 relaunch, GP6/GP7 write, arbitrary logical address, AudIf access,
unload, reset or retry path. The only DSP logical address is `0x80ff`.

## Explicit step sequence

The paths remain `/sys/kernel/h713_dsp_retention/{state,step}` with new
schema `h713-dsp-minimum-v1`. Initialization only publishes the interface;
there is no MMIO access or DSP request until explicit steps.

| Steps | Operation |
| --- | --- |
| 1–46 | reviewed boundary prefix: resources, safe census, receiver clocks, conditional demod reset release, 15 stock TVFE words, demod gate, audio/display clocks, conditional display/TVCAP reset releases, seven verified routing words and final interface check |
| 47 | AudioTop census; require exact `0/0`; snapshot `audiotop-zero` |
| 48 | control `0x700` and readback; snapshot `control-ready` |
| 49 | config `0x001a5e00` for level 2/3; no write for level 1; snapshot `config-reviewed` |
| 50 | latch `0x011a5e00` for level 3; no write for level 1/2; snapshot `setup-ready` |
| 51–52 | peer and ARM lock census separately; snapshot `lock-sampled` |
| 53 | bounded stock ARM claim/readback/peer recheck; snapshot `lock-claimed` |
| 54 | DSP status census; refuse busy; snapshot `status-ready` |
| 55 | device-0 version attempt; snapshot `device0` |
| 56 | device-1 attempt, or software-only skip if device 0 timed out; snapshot `device1` |
| 57 | release only ARM lock, verify `0xaa` |
| 58 | final health, released-lock and exact selected AudioTop configuration check; snapshot `complete`; terminal |

Every helper invocation performs one exact next operation. Snapshot/review
all boundaries in `dsp-minimum.py:STAGES`, including the earlier prefix
boundaries, before the matching `--stage-ack`. Do not loop stages or change
level after boot. Acquired resources remain held until poweroff. A hard
failure/uncertain ledger prevents further operations; no forced cleanup.

For each device, state and UART record:

| Phase code | Meaning / UART marker |
| --- | --- |
| 0 | unattempted; response unknown |
| 1 | `BUSY_WAIT`; `BUSY_TIMEOUT` means command not written, sent 0 |
| 2 | `COMMAND_WRITE_BEGIN` printed before the MMIO write; if that write stalls, no sent marker |
| 3 | `COMMAND_SENT`, sent 1: the MMIO write returned; this is not a DSP completion acknowledgment |
| 4 | `DONE_WAIT`; `DONE_TIMEOUT` means sent 1, completion absent |
| 5 | `COMPLETE`: done bit observed, response read; raw value valid |
| 6 | `SKIPPED`: suppressed after previous timeout, no request |

Busy/done polls are independently bounded at 50 ms, lock peer checks at
10 ms. Immediate completion is valid; no clear edge is required. A stalled
MMIO transaction cannot be interrupted by a polling bound. Keep a passive
UART recorder and a bounded host invocation; a missing DONE/uncertain call
means stop, not retry. A timeout permits only current-pair skip/release/
final and poweroff. Maximum two version-command writes per trial.

State includes selected `level`, actual setup-write mask, per-step readbacks
(unknown sentinels for skipped writes), per-device phase, sent flags,
busy-wait exit status, outcomes and raw responses. Only phase 5/outcome 1
is a completed response. Zero is never substituted for timeout.

## Live sequence, when separately armed

1. Fully disconnect the board and allow the cold interval. Arm/verify the
   sole UART catcher OPEN before requesting power. Capture one cold SPL,
   GP6 zero, correct proper/parked MIPS and original bootcmd. Boot unchanged
   production. Collect/validate a fresh production census and patched `1/1`
   baseline, all owners active and both domains ON.
2. Stage the complete bundle and exact fresh `cold-census.json` at the fixed
   remote directory. During subsequent cold normal maintenance, archive the
   previous experiment directory before staging another trial; never reuse
   `arm-proof.json`. Verify bundle files, installed guard and original backup.
   Do not rewrite the guard merely to stage a new candidate.
3. Arm/verify the warm catcher, then perform one fresh-ID/owner-checked
   orderly reboot. Require one warm SPL/GP6 magic/MIPS parked. Verify bootcmd
   and use the reviewed `--open-ppu-bus` probe; both domains must be ON.
4. Record exactly one normal warm logo with lamp off:

   ```text
   gpio clear PB5
   if h713_disp auto 0x34 logo; then echo H713_DSP_MINIMUM_LOGO_OK; else echo H713_DSP_MINIMUM_LOGO_FAILED; fi
   gpio clear PB5
   ```

   Use continuous UART and at least 20 seconds silence tolerance. Require
   success marker and post-logo MIPS parked; never retry a missing marker.
5. Run the fixed-level RAM loader, initially **level 1**:

   ```sh
   python3 tools/serial/run-dsp-minimum-boot.py \
     --port /dev/ttyUSB0 \
     --prepared build/hdmi-dsp-minimum-2026-10-22/candidate \
     --expected-bootcmd TRIAL/bootcmd.txt --baseline TRIAL/cold-census.json \
     --warm-catch TRIAL/warm-catch/serial.log --logo-log TRIAL/warm-logo.log \
     --arm one-logo --arm-ack one-reviewed-warm-logo --level 1 \
     --output TRIAL/ram-boot
   ```

   Loader validates cold/reset/logo evidence, verifies installed guard
   size/CRC and FIT size/CRC, rechecks domains and boots from RAM with the
   selected level. It captures a fixed 60 seconds and never runs a logo or
   flashes media. Levels 2/3 require a different cold cycle, not a loader retry.
6. Verify exact Linux build, new boot ID, hold eligible/applied and no TVFE
   command, disabled DT nodes/marker, absent production handoff and inactive
   HDMI owners/no competing modules. Reconnect Wi-Fi and set `dmesg -n 7` if
   needed. Bind the captured level intent once to this idle boot:

   ```sh
   python3 tools/hdmi/bind-dsp-minimum.py \
     --intent TRIAL/ram-boot/arm-intent.json \
     --prepared build/hdmi-dsp-minimum-2026-10-22/candidate \
     --output TRIAL/arm-proof.json
   ```

   It verifies exact kernel/bundle/guard/DT/baseline, fresh boot and zero
   cursor, matching immutable level, journal and inactive owners. The helper
   rechecks proof/boot/baseline/FIT/level on every operation. Do not edit proof.
7. Keep a sole passive UART recorder for the steps and shutdown. Invoke:

   ```sh
   python3 /root/hdmi-dsp-minimum-2026-10-22/dsp-minimum.py \
     --bundle /root/hdmi-dsp-minimum-2026-10-22 \
     --baseline /root/hdmi-dsp-minimum-2026-10-22/cold-census.json snapshot
   ```

   Replace `snapshot` with `step --number N [--stage-ack NAME]` for each
   explicit operation. Do not run generic warm devmem/census. After a timeout,
   do only the designed skip/release/final. No more setup/requests exist.
8. Export `/run/h713-dsp-minimum/`, proof, exact-boot journal, command records
   and UART before fresh-ID/state/owner-checked orderly poweroff. Record
   UART Power down, close capture, then physically disconnect power. Keep
   lamp off: disabled display means its normal panel-shutdown callback does
   not run. A bus stall requires physical power removal, no forced reboot.
   Do not remove the bench guard during a retained boot.
9. Analyze the terminal snapshot with `analyze-dsp-minimum.py SNAPSHOT.json`.
   Pass multiple independent trial snapshots to compare levels. Comparison
   requires distinct cold/warm IDs, identical FIT, exact initial zero
   AudioTop, valid level proof and matched original reset/routing/clock state.
   Lower initial-busy/invalid/missing trials do not establish a minimum.

A completed `0/0` pair is **access success** with zero versions, not patch
retention. Completed `1/1` is access success and patched versions observed
through that setup. Mixed values remain explicit. None of these alone proves
AudioTop caused RAM erasure or reset preserved it. Automatic warm recovery,
repatching and production GP6/source3 policy changes remain out of scope.
