# DSP warm retention diagnostic — October 22, 2026

**Completed: both DSP version reads returned `0/0`, with TVFE held ON and
both requests completed. Board ended in orderly poweroff.** This rules out
the previously identified Linux TVFE power-off command as a necessary cause
of this run's zero-version result. It does not directly prove DSP RAM erasure
by reset: the warm logo and interface preparation remain interventions.

## Observations

| Point | Evidence / result |
| --- | --- |
| Fresh cold production | Boot `96cae8c6-c621-4133-b416-0583ae9ca996`; handoff present, capture/signal/speaker active, both domains ON; DSP `0000/0000` → pinned 724-pair patch verified `1/1` ([baseline](cold-census.json)) |
| Orderly warm reset | One warm SPL, GP6 `48444d49`, GP7 zero, MIPS parked; original bootcmd unchanged ([capture](warm-catch/serial.log)) |
| Bus-only pre-logo probe | Opened only PPU bus gate/reset; TVFE/TVCAP both `00010000` ([census](warm-prelogo/census.json)) |
| Single warm logo | Full success marker and parked MIPS captured; no sustained source3 relaunch ([UART](warm-logo.log)) |
| Final U-Boot check | Both domains still ON; installed bench hook size/CRC and diagnostic FIT size/CRC/hash checked ([loader evidence](ram-boot/preboot.json), [UART](ram-boot/serial.log)) |
| Diagnostic Linux | Boot `9fd2d002-951b-43d8-a656-eec7cc02c995`; exact `6.18.38 #3` build; `eligible=1`, `applied=1`; no TVFE power command/violation; no handoff and HDMI services inactive ([health](warm-health.txt), [exact-boot journal](warm-kernel-journal.txt)) |
| Access setup | All steps completed. Demod bus reset initially asserted (`demod_before=1`), released once; receiver/audio/display clocks held; 15 stock TVFE words verified. No reset assertion or domain power transition. |
| AudioTop census | Control/config `00000000/00000000`, not inherited. Known control/config/latch setup completed at steps 38–40 ([snapshot 37](board-export/snapshot-37.json)) |
| Status and lock | DSP status initially zero, peer/own `0/0`; stock ARM claim succeeded with `0x55` readback and bounded peer checks; no peer write ([snapshot 42](board-export/snapshot-42.json)) |
| Device 0 | Step 43 completed, outcome 1, raw response zero, status `00000020`; no timeout ([snapshot](board-export/snapshot-43.json)) |
| Device 1 | Step 44 completed, outcome 1, raw response zero, status `00000120`; no timeout ([snapshot](board-export/snapshot-44.json)) |
| Final check | Step 46; hold 1, violated/failed/timeout/claimed all 0, both outcomes 1; ARM release `0xaa` verified; both domains ON ([final snapshot](board-export/snapshot-46.json), [analysis](analysis.json)) |
| End | Fresh-ID/state/owner-checked poweroff; UART guard retained-hold notice, panel shutdown, `reboot: Power down` at 696.521177 s ([continuous steps/shutdown UART](steps-uart.log)) |

Every operation used one helper invocation, with saved snapshots and exact
stage acknowledgments. [Step logs](step-43.log) preserve before/after records;
[ledger](board-export/ledger.json) ends at 46 with `uncertain=false`.
[Verification](verification.json) checks ordered BEGIN/DONE 1–46, one SPL per
catch, one successful warm logo, final state and powerdown. No failed request
was retried. No new DSP patch, DSP graph initialization, source3 launch,
DSP reset assertion, GP6/GP7 write, or boot-media/environment change occurred.

## Meaning and limits

The analyzer classifies this as `zero_versions_after_warm_access`, with
`patch_version_survives_tested_warm_path=false`. These are completed zero
responses, not substituted values from a timeout. Keeping TVFE ON through
Linux boot was insufficient to preserve the patched ready-version pair.

The tested path is cold production patch → orderly reboot → early U-Boot →
one normal warm logo → held-domain Linux → clock/reset-release/AudioTop
setup → version pair. The experiment does not locate the first loss within
that path or distinguish RAM loss from effects of later interface startup.
It does not authorize repatching, adopting warm DSP state, clearing GP6 or
relaxing the one sustained source3 launch per cold cycle policy. Automatic
HDMI recovery remains unproven.

Further work should first inspect reset and AudioTop initialization effects
and design an earlier, equally guarded observation point that separates the
warm logo from interface startup. A new live trial needs a fully disconnected
cold cycle and fresh baseline; no additional trial was run here.

## Persisted board changes and restoration

The candidate was staged separately at
`/root/hdmi-dsp-retention-2026-10-21/` and booted only from RAM. Normal FAT FIT,
startup script and bootloader were unchanged. [Candidate manifest](candidate-manifest.json)
pins FIT SHA-256 `538224b413efa5bd7d92a4196c8a7327a223eebec32dc4fe124dbabc7b35c553`.
[Tool hashes](tool-hashes.json) identify the tested sources.

The **bench shutdown hook remains installed**, SHA-256
`5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`.
Original bytes and mode 0755 were saved on board as
`/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard` and copied
[here](previous-hold-guard), SHA-256
`96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113`.
[Installation record](install-guard.json) verifies all bundle hashes and backup.
Restore only after fully disconnected cold power into normal production,
verify the retain flag absent and both hashes, then atomically restore the
exact backup. Do not restore from a running retained bench kernel.

The passive recorder closed after powerdown; no UART catcher remains armed.
Host UTC capture times identify the experiment date; board wallclock reset
to April, so boot IDs and monotonic journal/UART times identify each boot.
