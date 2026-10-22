# Warm DSP patch retention diagnostic — October 22, 2026

**Live run completed October 22: both DSP requests completed with versions
`0/0`, TVFE held ON, no timeout. Board ended in orderly poweroff; recorder
closed. Bench shutdown hook remains installed with exact original backup.**
[Live result and restoration details](hdmi-evidence/2026-10-22-dsp-retention-live/README.md).
Preparation began October 21; the experiment directory retains that date.
Use **`candidate-v2`**, not the earlier prototype.

The [last live trace](hdmi-evidence/2026-10-21-tvfe-boot-trace-live/README.md)
proved that Linux provider sync-state explicitly powers TVFE OFF after its
probe, despite `pd_ignore_unused`. This diagnostic prevents that specific
observation-induced transition, then queries the two DSP patch-version words.
It does not implement production warm HDMI recovery.

## Candidate and protection

Prepared tree: `build/hdmi-dsp-retention-2026-10-21/candidate-v2/`.
Self-contained board bundle: its `bundle/` directory.
[Build and verification evidence](hdmi-evidence/2026-10-22-dsp-retention-preparation/README.md).

| File | Identity |
| --- | --- |
| `artifacts/kernel.fit` / `bundle/kernel.fit` | 7,753,056 bytes; SHA-256 `538224b413efa5bd7d92a4196c8a7327a223eebec32dc4fe124dbabc7b35c553` |
| `artifacts/board.dtb` | production DTB unchanged; SHA-256 `4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940` |
| kernel release / build | `6.18.38`; `#3 SMP Thu Oct 22 00:04:05 PDT 2026` |
| current guard expected before installation | SHA-256 `96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113` |
| bench guard | SHA-256 `5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d` |

The kernel is an independent copy of the successful TVFE-trace candidate.
No normal kernel source, patch series, startup script, FIT or boot firmware
was replaced. No optional proper is needed. Exported symbol versions are
unchanged; existing rootfs modules still require a live health check.

Both `h713_tvfe_trace=1` and **`h713_tvfe_retain=1`** are required. Early
eligibility reads the verified-open PPU bus, production GP6 latch, parked
MIPS, stopped SCP and both ON/idle domains. Cold latch zero, half-open bus,
running processors, OFF/transitioning domains or a disabled trace refuse
eligibility. Nothing commands an initially OFF domain ON.

At TVFE's PPU initialization, the driver rechecks physical ON before/after
its original init writes and applies **`GENPD_FLAG_ALWAYS_ON` only to TVFE**
under that validated bench predicate. TVCAP retains its existing policy;
GPU/VE/AV1 policy is unchanged. No genpd-core global behavior is modified.
Any attempted TVFE power command latches `violated` and revokes the proof;
the observer cannot proceed. The default boot without the retain flag gets
no hold, observer node, resources or protocol requests.

The bench shutdown hook preserves the normal owner checks and additionally
treats the exact cmdline token `h713_tvfe_retain=1` as a retained hold, even
before any observer step. Reboot/kexec become orderly poweroff; ordinary
poweroff/halt remain unchanged. This requires a responsive kernel and is
not a bus-stall or hardware-watchdog recovery mechanism. Use `panic=0`.

The RAM loader also loads the **installed hook** into scratch RAM at
`0x53000000`, verifies filesize and CRC against the prepared guard, then
loads/checks the diagnostic FIT at `0x50000000`. It refuses a wrong hook
before booting. These are filesystem reads into RAM, not boot-media writes.

## Built-in observer and steps

There is no external probe module. With a valid applied hold and absent
production handoff, the kernel publishes:

```text
/sys/kernel/h713_dsp_retention/state   read-only software state, JSON
/sys/kernel/h713_dsp_retention/step    root-only write, exact next integer
```

Initialization creates the interface only. Resource acquisition, clock
changes and requests require explicit step writes. Acquired resources and
references remain until poweroff; there is no unload, restore or retry path.
Hard failure poisons subsequent steps. A process interrupted around a write
leaves an uncertain ledger and cannot resume commands. Read-only snapshots
remain available after a failed/uncertain step when the boot context verifies.

| Steps | Operation |
| --- | --- |
| 1 | reserve DSP port, stock lock, AudioTop and SCP-reset window; map controls; acquire clock/reset handles; no DSP/AudioTop/lock read or hardware write; post-step health samples the known-safe controls |
| 2 | gated PPU/processor checks, inherited TVTOP route verification, TVCAP bus/reset verification and original TVFE clock-word census |
| 3–8 | hold PLL-video0, PLL-ADC, TVCAP/capture/VIncap/TVFE clocks through CCF |
| 9 | deassert the demod bus reset only if already asserted; **never assert it**; record its initial state |
| 10–24 | verify/apply the 15 production TVFE clock words individually, skipping identical values |
| 25 | open the demod bus gate after reset release; never toggle it off |
| 26–36 | hold audio and inherited display clock trees, one clock per step; no display reset or TVTOP route write |
| 37 | read AudioTop control/config; accept only known reset config or inherited production baseline |
| 38–40 | if already at baseline, perform no writes; otherwise apply the established AudioTop control/config/latch sequence in three explicit steps |
| 41 | sample DSP status and stock lock words, after domain/bus/clock/routing prerequisites |
| 42 | claim the stock ARM lock with bounded wait, readback and peer recheck |
| 43 | one logical `0x80ff` request to device 0; bounded busy/done waits and completed response |
| 44 | one logical `0x80ff` request to device 1; skipped if device 0 timed out |
| 45 | release only ARM's lock word, verify `0xaa` |
| 46 | final retained-domain, processor, interface and released-lock checks |

Health checks before/after operations require an open PPU bus, both domains
ON/idle, parked MIPS, stopped SCP and an unviolated hold. Full `0x0500xxxx`
lock access is gated on the exact inherited TVTOP route. The observer never
powers a domain, asserts a reset, rewrites TVTOP, launches MIPS/SCP, changes
GP6/GP7, loads a patch, initializes DSP registers/graphs/selectors or accepts
arbitrary addresses. Its only DSP logical address is `0x80ff`.

The claim/release and read completion use the existing stock-protocol headers.
One claim covers both requests. Completion may be immediate; no visible
clear edge is required. A busy/done timeout records an outcome and suppresses
all later requests; release remains reachable. Raw response fields start
unknown and count only when the corresponding completion outcome is valid.
A hard failure while claimed leaves the state held for poweroff, not forced
cleanup through potentially invalid MMIO.

The helper saves original TVFE words, demod reset state and AudioTop config,
and records whether AudioTop was inherited. Clock setup/reset release and
AudioTop initialization are observation interventions. A negative result is
about the tested warm-access path; it cannot by itself isolate electrical
RAM erasure by reset from later firmware/interface startup behavior.
The generic `last` field retains the most recent explicitly sampled value;
use dedicated reset/config/claim/outcome fields for operations without a new
sample. It is not a DSP response-valid flag.

## Live sequence, when separately armed

1. Verify sole host UART ownership and an actual catcher OPEN event before
   requesting power. Capture a fully unplugged cold boot with GP6 zero and
   one SPL, record bootcmd, then boot unchanged production.
2. Capture a fresh cold boot ID and existing production census. Require all
   owners active, both domains ON, and journal DSP `0/0` followed by the pinned
   724-pair patch verified `1/1`. Save this **fresh** cold-census JSON as the
   baseline; do not reuse the previous experiment's boot ID.
3. Stage the complete `candidate-v2/bundle/` contents in board
   `/root/hdmi-dsp-retention-2026-10-21/`. Verify its file hashes. Also stage
   the fresh baseline JSON there. Check the installed hook against the
   expected **previous** hash above. Save its exact bytes and permissions as
   `previous-hold-guard` in this directory, refusing to overwrite a backup.
   Atomically install the bench hook mode 0755 and verify its new hash.
   Do not overwrite the normal FAT FIT, startup script or saved environment.
   The old hook backup is the exact restoration artifact for this change.
4. Arm and verify the warm catcher, then request one orderly reboot guarded
   by the current production boot ID and owners. Stop before logo, verify
   the same bootcmd, and run the reviewed bus-only PPU opening probe.
   Require both domains ON. Run the normal warm-logo command exactly once
   with continuous recording and at least 20 seconds of silence tolerance.
   Require its success marker and parked MIPS; do not retry a missing marker.
5. After that reviewed single logo, use the prepared RAM loader:

   ```sh
   python3 tools/serial/run-dsp-retention-boot.py \
     --port /dev/ttyUSB0 \
     --prepared build/hdmi-dsp-retention-2026-10-21/candidate-v2 \
     --expected-bootcmd PATH/TO/THIS-CYCLE-bootcmd.txt \
     --output build/hdmi-dsp-retention-2026-10-21/live-01/ram-boot \
     --post-logo-ack one-reviewed-warm-logo
   ```

   The shared loader enforces warm latch, parked MIPS, both domains ON,
   bootcmd, loaded image size/CRC and FIT hashes. The retention wrapper adds
   the hook-byte check and retain flag. It preserves the normal root and
   ignore-unused flags, uses `panic=0 loglevel=7`, and captures a fixed 60
   seconds. No startup-script or second firmware launch is performed.
6. Verify a fresh diagnostic boot ID, exact build version, `eligible=1` and
   `applied=1` in that boot's journal, no TVFE power commands/violations, no
   handoff, inactive HDMI services, and no competing h713 modules. Keep UART
   recording for the stepped test. Ensure console threshold is at least 6
   (`dmesg -n 7` if needed) and `kernel.panic` remains zero.

   **Do not run the generic warm-retention census before interface setup.**
   With the hold, both domains are ON while audio clocks may still be gated;
   that older census would prematurely read AudioTop/DSP. The new helper's
   snapshots read only software state, current-boot journal and known-safe
   clock/genpd debug summaries. No generic `devmem` access is needed.
7. On the board, use one helper invocation per operation:

   ```sh
   python3 /root/hdmi-dsp-retention-2026-10-21/dsp-retention.py \
     --bundle /root/hdmi-dsp-retention-2026-10-21 \
     --baseline /root/hdmi-dsp-retention-2026-10-21/cold-census.json snapshot
   ```

   Use action `step --number N` for the exact next operation. The helper
   never loops through a stage. After steps 2, 8, 9, 25, 36, 37, 40, 41, 42,
   43 and 44, save/review a snapshot and supply the matching `--stage-ack`
   from the helper's `STAGES` table for the next step. Review the AudioTop
   census at 37 before acknowledging `audiotop-read` for conditional init.
   Review lock samples before claim and the claim before device 0. A timeout
   permits only the remaining skip/release/final sequence; never a retry.
8. Snapshot step 46, copy `/run/h713-dsp-retention/` and the exact-boot journal
   to the host before shutdown. Analyze `snapshot-46.json` with the bundled
   `analyze-dsp-retention.py`. Retain UART and all step acknowledgments.
9. End with a fresh-ID/owner-checked orderly poweroff and UART completion.
   Do not remove the bench hook while running the retain-flag kernel. To
   restore it later, first take a fully disconnected cold cycle into normal
   production, verify the retain flag is absent, compare current/backup
   hashes, and atomically restore the exact saved hook. No bootloader rollback
   is needed because this experiment changes no bootloader bytes.

The staged kernel can be reused only after the failure state has been ended
by the required physical cold cycle and a new baseline/captured warm boot.
No abrupt/watchdog test is folded into this first orderly experiment.

## Result interpretation

| Completed pair | Meaning |
| --- | --- |
| `1/1` | Patched ready versions survived the tested production cold → orderly reset → one warm logo → held-domain access path, without a new patch load. |
| `0/0` | Both DSPs completed and returned zero versions after warm access while TVFE was held. Report AudioTop/reset/clock interventions; this is not direct RAM-erasure evidence. |
| Mixed/other | Record exact values; no retained-state adoption or recovery authorization. |
| Timeout, lock failure, missing hold proof, incomplete steps, power violation or mismatched baseline | Inconclusive. Never substitute zero for an uncompleted request. |

The analyzer requires a verified different-boot patched baseline, successful
preflight, complete step 46, both completed responses, released lock and
unviolated hold. It always leaves automatic HDMI recovery unproven. Even a
positive retention result does not authorize source3 relaunch or relaxing
the production DSP predicates/GP6 policy.

## Offline checks

The final kernel/modules build succeeds with no warnings in its build log.
FIT extraction/decompression matches the built Image; DTB and complete
`Module.symvers` match production. Eleven retention tests exercise the actual
observer in fake MMIO, immediate completion, busy/done timeouts, ignored lock
writes, lost power, resource conflicts, no retries, no peer/PPU writes,
warm/idle eligibility, evidence classification, wrong kernel/guard refusal
and the actual generated bench hook. All 15 trace, 19 warm-retention and
3 existing guard regressions also pass. These 48 offline tests and the real
build do not establish a live retention result.
