# Separating reset, warm-logo and AudioTop effects — October 22, 2026

**Prepared offline; not installed or run. Board remains shut down after the
previous diagnostic. No UART capture is armed.**

The [previous live run](hdmi-evidence/2026-10-22-dsp-retention-live/README.md)
returned completed DSP versions `0/0` after an orderly reset, one warm logo
and AudioTop setup, despite TVFE staying ON. The next experiment observes
versions before AudioTop writes and after each of its three writes, then
compares two independently captured cold → warm paths with and without the
warm logo. This is a version-observation experiment, not a RAM dump.

## Candidate and controls

Prepared candidate: `build/hdmi-dsp-boundary-2026-10-22/candidate/`.
Self-contained board files: its `bundle/` directory. Expected board path:
`/root/hdmi-dsp-boundary-2026-10-22/`.
[Build verification](hdmi-evidence/2026-10-22-dsp-boundary-preparation/README.md).

* FIT: 7,754,288 bytes; SHA-256
  `bbadfaaa28b299ee6d4d4e514e9d38c2f11e180b7f8171aaeaca1d289e171a83`.
* Kernel: `6.18.38`, `#4 SMP Thu Oct 22 01:01:15 PDT 2026`;
  full production `Module.symvers` unchanged.
* Opt-ins: `h713_tvfe_trace=1 h713_tvfe_retain=1 h713_dsp_boundary=1`,
  with `panic=0 loglevel=7 clk_ignore_unused pd_ignore_unused`.
* Same early warm-only eligibility and TVFE ALWAYS_ON policy as the tested
  retention kernel; both domains must already be ON/idle. No domain is
  powered on and no reset is asserted.
* Both arms use the **same embedded DTB**. Relative to production, only
  `/soc/display@5600000` and `/soc/cpu-comm@3003000` are disabled, and chosen
  marker `h713,dsp-boundary-v1 = <0x424e4431>` is added. This prevents early
  display/CPU_COMM MMIO before the logo-free observer prepares its access.
  Do not compare this DT change with the previous run as an isolated factor;
  the new one-logo arm must re-establish the outcome with the new DT.
* Same bench shutdown guard, SHA-256
  `5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`.
  It remains installed from the previous test. Verify its bytes; preserve
  the original mode-0755 backup at
  `/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard` (SHA-256
  `96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113`).
  Do not overwrite that backup or remove the guard during a held boot.

There are no production kernel/DT/script/bootloader changes. Candidate FIT
is staged separately and booted only from RAM. No GP6/GP7 writes, firmware
launch, DSP patch/graph operation, reset assertion or source3 recovery exists
in the observer. Only logical DSP address `0x80ff` is accepted.

## Order and step boundaries

Run **one-logo first**, with a fresh cold production `0/0` → verified pinned
patch `1/1` baseline. It keeps the previously proven functional lock context
while qualifying the new pre-AudioTop access. Only after that access returns
completed responses should a separate fully disconnected cold cycle run the
**no-logo** arm. Each arm has its own cold and warm boot IDs, raw capture and
baseline. Never use a second warm reboot within the retained diagnostic.

The sysfs paths remain `/sys/kernel/h713_dsp_retention/{state,step}` but the
schema is `h713-dsp-boundary-v1`. State is software-only; initialization does
not touch DSP/AudioTop/lock. `h713_dsp_boundary=1` is required to publish it.

| Steps | Operation / review boundary |
| --- | --- |
| 1–2 | claim/map resources and acquire clock/reset handles; sample only safe CCU/PPU/SPL TVTOP state and original TVFE words; no gated display read |
| 3–8 | hold six receiver clocks; snapshot `receiver-clocks` |
| 9 | release demod bus reset only if asserted; record initial state; snapshot `reset-release` |
| 10–25 | verify/apply 15 stock TVFE clock words and open demod gate; snapshot `tvfe-clocks` |
| 26–36 | hold audio/display clocks; snapshot `interface-clocks` |
| 37 | release display reset only if asserted; record state; snapshot `display-reset` |
| 38 | release TVCAP reset only if asserted; record state; snapshot `tvcap-reset` |
| 39–45 | verify/apply seven proven TVTOP route words individually, skip identical words; record original words and write mask; 12 ms settle/readback per word |
| 46 | verify complete routing and open TVCAP/demod buses; snapshot `route-ready` |
| 47 | AudioTop control/config census only; accept reset config or known inherited production baseline; snapshot `audiotop-read` |
| 48–49 | read peer/ARM lock separately, refuse `0x55`; snapshot `lock-sampled` |
| 50 | bounded ARM `0x55` claim and readback; snapshot `lock-claimed-before-at` |
| 51 | **new exploratory** DSP status read before AudioTop writes; refuse busy; snapshot `exploratory-pre-at-status` |
| 52–55 | one device-0 request, one device-1 request, ARM release/readback, final check; snapshot after each response and at `pair-before-at` |
| 56–61 | conditional AudioTop control `ctl \| 0x700`, readback; new stock-lock claim, version pair, release and check; snapshot `pair-after-control` |
| 62–67 | conditional AudioTop config `…001a5e00`, readback; version pair with claim/release/check; snapshot `pair-after-config` |
| 68–73 | conditional AudioTop latch `…011a5e00`, readback; version pair with claim/release/final check; snapshot `complete` |

The helper's `STAGES` table defines **all** intermediate acknowledgments,
including after a write, claim and device response. One invocation performs
one operation, never a loop. Snapshot and inspect each stage before the next
operation with its exact `--stage-ack`. Inherited baseline AudioTop causes
steps 56/62/68 to make no writes; the census and `interface_inherited` expose
that distinction. At most eight version commands occur per arm.

**The pre-AudioTop DSP access is not yet hardware-qualified.** Clock gates,
domain status and writable lock cannot prove that an unconfigured DSP port
is readable or that a completed zero response reflects DSP RAM contents.
AudIf is never touched. BEGIN/DONE on UART localizes a possible bus stall.
A 50 ms polling bound cannot interrupt a stalled MMIO transaction. If the
lock claim fails, stop before DSP status/request. A hard failure or uncertain
ledger means no further operations; preserve evidence and power off. No
skip-lock, invented backing register, forced release or fallback firmware.

On a request timeout, only the current pair's device-1 skip (if applicable),
lock release and final check remain reachable. Snapshot and power off there;
never continue to a new AudioTop write/pair. A kernel-level refusal also
blocks those transitions even if the helper is bypassed. No retries or later
post-setup request is permitted in that cold cycle after a timeout.

## Live procedure, after separately arming capture

1. Fully disconnect the powered-off board, allow the cold interval, then arm
   and verify sole host UART ownership and actual OPEN before asking for
   power. Catch one cold SPL, GP6 zero, parked MIPS and correct proper.
   Record the original bootcmd. Boot unchanged production, collect a fresh
   `warm-retention-census.py` baseline, require active owners/both domains ON
   and pinned DSP patch verified `1/1`.
2. During that production boot, stage the complete bundle plus this arm's
   exact fresh `cold-census.json` at the fixed board path. Refuse an existing
   arm proof from another run; archive the old experiment directory during
   normal cold maintenance before staging a later arm. Verify bundle hashes,
   installed bench guard and original backup. Do not change FAT FIT/script,
   environment or firmware. Begin a verified warm catcher, then issue one
   fresh-ID/owner-checked orderly reboot.
3. Catch one warm SPL with GP6 magic/MIPS parked. Verify unchanged bootcmd
   and use `warm-retention-uboot.py --open-ppu-bus` to open only the PPU
   register bus; require both domains ON, then stop at the prompt.
4. For **one-logo**, record `gpio clear PB5`, then exactly one:

   ```text
   if h713_disp auto 0x34 logo; then echo H713_DSP_BOUNDARY_LOGO_OK; else echo H713_DSP_BOUNDARY_LOGO_FAILED; fi
   ```

   Use continuous UART and at least 20 seconds silence tolerance, require
   the exact success marker and post-logo parked MIPS. Keep the lamp off
   (`gpio clear PB5` after completion too); no display viewing is needed.
   For **no-logo**, execute no display preparation or firmware command.
5. Use the dedicated host RAM runner (substitute this arm's paths):

   ```sh
   python3 tools/serial/run-dsp-boundary-boot.py \
     --port /dev/ttyUSB0 \
     --prepared build/hdmi-dsp-boundary-2026-10-22/candidate \
     --expected-bootcmd ARM/bootcmd.txt --baseline ARM/cold-census.json \
     --warm-catch ARM/warm-catch/serial.log --output ARM/ram-boot \
     --arm one-logo --arm-ack one-reviewed-warm-logo \
     --logo-log ARM/warm-logo.log
   ```

   For no-logo, use `--arm no-logo --arm-ack no-warm-logo-executed`, omit
   `--logo-log`. That acknowledgment records the operator's command history;
   a log alone cannot prove absence of unrecorded commands. Runner checks
   reset/logo evidence, installed hook CRC, image size/CRC and both domains,
   then captures a fixed 60 seconds. It does not run a logo or flash anything.
6. Verify the new Linux boot, exact build, disabled DT nodes/marker, no
   handoff, inactive HDMI owners/no competing modules, applied hold and no
   TVFE power command. Reconnect Wi-Fi, set `dmesg -n 7` if necessary. Bind
   the loader intent once to the fresh idle diagnostic boot:

   ```sh
   python3 tools/hdmi/bind-dsp-boundary.py \
     --intent ARM/ram-boot/arm-intent.json \
     --prepared build/hdmi-dsp-boundary-2026-10-22/candidate \
     --output ARM/arm-proof.json
   ```

   Binder verifies exact kernel/bundle/guard/baseline, DT, boot/hold/journal
   and inactive owners, and exclusively creates board `arm-proof.json`.
   Helper checks this boot, cold baseline and FIT identity on every operation.
   Do not invent/edit the proof or reuse it on another boot.
7. Keep a sole passive UART recorder open for steps and shutdown. Use:

   ```sh
   python3 /root/hdmi-dsp-boundary-2026-10-22/dsp-boundary.py \
     --bundle /root/hdmi-dsp-boundary-2026-10-22 \
     --baseline /root/hdmi-dsp-boundary-2026-10-22/cold-census.json snapshot
   ```

   Replace `snapshot` with `step --number N [--stage-ack NAME]` for an
   operation. Do not run generic devmem/census on held warm Linux. Review
   the pre-AudioTop pair at 55 before deciding whether any setup is useful.
   On a timeout, end at that pair's final check; do not continue.
8. Export `/run/h713-dsp-boundary/`, all host command acknowledgments, arm
   proof, exact-boot journal and UART before a fresh-ID/owner/state-checked
   **orderly poweroff**. Never unload/reset the observer. Disabled display
   driver means its normal panel-shutdown callback will not run: keep the
   lamp off and fully disconnect board power after UART Power down before
   another arm. A bus stall requires operator physical power removal, no
   forced reboot/retry. End capture only after shutdown, then verify no
   reader remains.
9. Analyze a final released-pair snapshot with
   `analyze-dsp-boundary.py SNAPSHOT.json`. For comparison, pass the no-logo
   snapshot first and `--logo-record ONE_LOGO_SNAPSHOT.json`. Compare only
   valid distinct cold/warm cycles with identical FIT and verified arm proof.

## What outcomes can establish

| Result | Interpretation |
| --- | --- |
| Pre-AudioTop pair `1/1`, then changes after control/config/latch | First observed change is bracketed around that AudioTop operation and the following read pair, without reset/logo between measurements. Replicate before assigning a mechanism. |
| `1/1` before and after every AudioTop operation | Versions survive those operations in that arm; setup is insufficient to reproduce the previous loss under this DT/path. |
| `1/1` without logo, `0/0` with logo before AudioTop writes | Difference is associated with the logo path; replicate the matched pair. Route/reset setup also differs when inherited, so this is not proof of a particular firmware instruction. |
| `0/0` without logo before AudioTop writes | Zero is observed without the warm logo or these AudioTop writes. Reset, SPL/BL31/proper/early Linux and access preparation remain in the bracket. Unconfigured-interface responses still need qualification; this does not prove electrical RAM erasure. |
| Lock unavailable, busy/status failure, incomplete response, timeout, hold violation or uncertain ledger | Inconclusive. Never substitute zero or try a second access path in that run. |

An all-negative result cannot force a three-way answer when the observation
interface itself is unavailable or unqualified. It may require a separately
designed no-reset positive control or earlier boot instrumentation. This
candidate does not implement those by modifying active production owners.
Production one sustained MIPS/source3 launch per cold cycle and warm GP6
policy remain unchanged; automatic HDMI recovery is not authorized.
