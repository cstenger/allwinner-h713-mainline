# Control-only AudioTop replication — October 22, 2026

**Replicated: control `0x700` alone completed both DSP version reads,
returning `0/0`, with no timeout.** All 58 steps passed; final observer state
is identical to the [first completed trial](../2026-10-22-dsp-minimum-control-live/README.md).
This run captured the full cold SPL as well as the warm reset. Board ended
in orderly poweroff and the sole UART recorder closed.

## Evidence

| Boundary | Recorded result |
| --- | --- |
| Cold power-on | Capture OPEN before user applied power; one SPL, correct proper U-Boot, GP6/GP7 zero, MIPS parked, no prior logo ([cold capture](cold-catch/serial.log), [events](cold-catch/events.log)) |
| Production boot | Original bootcmd matched the preceding trial; unchanged production boot. New boot `47702c3c-7090-4848-9e9c-2ffdb41ca930`, DSP `0/0` at 18.498396 s → pinned 724-pair patch verified `1/1` at 19.420081 s; capture/signal/speaker active, both domains ON, MIPS running ([preboot](cold-preboot/census.json), [baseline](cold-census.json), [production UART](cold-production-uart.log)) |
| Staging | Same FIT SHA-256 `e1b475a8cb66ba86846a30dc8845c6cb0e76c8459f0d2bc2f3ba47edf63d8aeb`; previous proof/baseline archived intact. Fresh bundle/census, installed guard and original mode-0755 backup verified ([stage check](stage-verification.log), [manifest](candidate-manifest.json)) |
| Warm reset | One fresh-ID/owner-checked orderly reset; one SPL with GP6 magic and parked MIPS; unchanged bootcmd; approved PPU bus-gate probe, both domains ON ([request](orderly-reboot-request.log), [capture](warm-catch/serial.log), [pre-logo census](warm-prelogo/census.json)) |
| Logo/RAM boot | Exactly one successful normal warm logo, lamp off, MIPS parked. Same RAM kernel `6.18.38 #4 SMP Thu Oct 22 02:35:16 PDT 2026`; fixed level 1, loader FIT/guard size/CRC checks passed ([logo](warm-logo.log), [RAM boot](ram-boot/serial.log), [preboot](ram-boot/preboot.json)) |
| New warm identity | Boot `cb320a62-9818-422e-ae45-e2e825d79e05`; hold eligible/applied, no TVFE power command/violation, owners inactive, zero cursor; fresh exact-kernel/FIT/DT/baseline/guard/level proof ([proof](arm-proof.json), [health](warm-health-connected.log), [kernel journal](final/journal.txt)) |
| Setup | Demod reset initially asserted then released; display/TVCAP reset already released. Seven routing words matched, zero route writes. AudioTop initial exact `0/0`; control readback `0x700`, setup mask 1; config/latch steps skipped ([snapshot 47](board-export/snapshot-47.json), [snapshot 50](board-export/snapshot-50.json)) |
| Device 0 | Step 55: one request, command-sent at 269.124728 s, COMPLETE at 269.134121 s; phase 5, outcome 1, status `0x20`, raw response `0` ([UART](steps-uart.log), [snapshot 55](board-export/snapshot-55.json)) |
| Device 1 | Step 56: one request, command-sent at 277.734363 s, COMPLETE at 277.743753 s; phase 5, outcome 1, status `0x120`, raw response `0` ([snapshot 56](board-export/snapshot-56.json)) |
| Terminal state | Stock ARM lock released/readback verified; final exact control/config `700/0`, domain/interface checks passed; step 58, hold 1, failed/violated/timeout/claimed 0, ledger certain ([final snapshot](board-export/snapshot-58.json), [ledger](board-export/ledger.json), [analysis](analysis.json)) |
| Export/shutdown | Archive SHA-256 verified before fresh-proof/kernel/guard/state/ledger/owner-checked poweroff. UART `reboot: Power down` at 306.378926 s; recorder CLOSE verified ([export](export-final.log), [request](end-poweroff-request.log), [UART](steps-uart.log), [events](steps-uart-events.log)) |

All 58 command records passed preflight and contain the exact completed next
step. Continuous UART has each BEGIN/DONE once in order and exactly one
BUSY_WAIT/WRITE_BEGIN/SENT/DONE_WAIT/COMPLETE sequence per device.
[Validation](validation.json) and [comparison](replication-comparison.json)
record the audit. Host Wi-Fi/SSH worked, including saved-profile reconnection
after the RAM boot. No serial reader competed with the passive recorder.

## What the replication establishes

The same FIT and fixed level produced completed `0/0` in two separate cold
cycles with different cold/warm boot IDs and fresh production patch proofs.
The entire final observer state matches, including original TVFE clock
words, reset states, routing words, setup readbacks, protocol phases and
response statuses. The first trial lacked cold SPL capture; this run fills
that capture gap without reusing its baseline or arm proof.

Control-only sufficiency is now replicated for the tested one-logo warm
path. Configuration/latch writes are unnecessary both for completed version
access and for observing the zero versions in this path. This does not
establish the minimum individual bits within `0x700`, all possible write
orders, or a qualified matched level-0 comparison. Levels 2/3 were not run.

The patch was no longer reported by the first control-only reads, despite
TVFE remaining ON. Reset/early boot, the warm logo, interface preparation
(including conditional demod reset release) and the control write remain
inside the loss interval. These completed reads are not direct DSP RAM
content/erasure measurements. No added DSP patch/graph writes, DSP reset
assertions, source3 relaunch or request retries occurred in the observer.
No automatic recovery or production one-launch policy changes were made.

Next: design a no-reset patched positive control and matched boundary
experiment using this replicated access recipe. A no-logo variant requires
separate reviewed preparation and a new disconnected cold cycle; it is not
an extra request or reboot in this completed boot.

## Board state and preserved files

The board is powered down; user instructed to physically disconnect and
leave it off. Lamp remained off. The display DT node was disabled, so the
usual panel-shutdown callback did not run. Normal boot FIT/script/DT,
bootloader and saved environment were not replaced.

Previous board staging is preserved as
`/root/hdmi-dsp-minimum-2026-10-22-previous-68081628`; this trial remains at
`/root/hdmi-dsp-minimum-2026-10-22`. The unchanged bench guard SHA-256 is
`5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`.
Original mode-0755 backup remains at
`/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard`, SHA-256
`96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113`.
Restore only after a fully disconnected cold normal boot without retain
and verification of those hashes. Work directory:
`build/hdmi-dsp-minimum-2026-10-22/live-control-03/`.
