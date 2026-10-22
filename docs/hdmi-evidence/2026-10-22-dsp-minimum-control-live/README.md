# Control-only AudioTop live trial — October 22, 2026

**Completed: control `0x700` alone allowed both DSP version reads to complete,
returning `0/0`. Board ended in orderly poweroff; UART recorder closed.**
The config/latch writes were skipped. This establishes control-only access
sufficiency in this one warm trial, while the pinned patch was no longer
reported. It does not locate patch loss within reset, warm logo, access
preparation or the control write, and does not prove DSP RAM erasure.

## Identity and evidence

| Check | Result |
| --- | --- |
| Fresh production baseline | Cold boot `e5d341d0-ce97-4a87-b2b5-37aecd31fa7d`; DSP initial `0000/0000` at 18.600961 s, pinned 724-pair patch verified `1/1` at 19.516051 s; capture/signal/speaker active, both domains ON, MIPS running ([census](cold-census.json)) |
| Reset boundary | One checked orderly warm reboot; one captured SPL, retained GP6 `48444d49`, GP7 zero, MIPS parked; unchanged bootcmd; approved PPU gate write/readback, both domains ON ([capture](warm-catch/serial.log), [pre-logo census](warm-prelogo/census.json)) |
| Warm logo | Exactly one success marker and parked-MIPS post-logo trace; lamp off before/after ([log](warm-logo.log)) |
| RAM candidate | FIT SHA-256 `e1b475a8cb66ba86846a30dc8845c6cb0e76c8459f0d2bc2f3ba47edf63d8aeb`; exact kernel `6.18.38 #4 SMP Thu Oct 22 02:35:16 PDT 2026`; fixed level 1; FIT and installed guard size/CRC verified by RAM loader ([manifest](candidate-manifest.json), [loader capture](ram-boot/serial.log), [preboot](ram-boot/preboot.json)) |
| Warm identity | Boot `68081628-2eba-49eb-a48c-283723ae9d54`; TVFE hold eligible/applied; zero cursor bound to exact FIT/kernel/DT/guard/baseline/level; owners inactive ([proof](arm-proof.json), [health](warm-health-connected.log), [kernel journal](final/journal.txt)) |
| Setup | Initial control/config exactly `0/0` at step 47; step 48 control readback `0x700`; setup mask 1; steps 49/50 software skips, no config/latch writes ([snapshot 47](board-export/snapshot-47.json), [snapshot 50](board-export/snapshot-50.json)) |
| Device 0 | Step 55, sent 1, phase 5, outcome 1, status `0x20`, raw response `0`; command-sent and COMPLETE UART markers at 309.982641/309.992052 s |
| Device 1 | Step 56, sent 1, phase 5, outcome 1, status `0x120`, raw response `0`; command-sent and COMPLETE UART markers at 321.702935/321.712369 s |
| Terminal health | Step 57 lock release/readback passed; step 58 final domains/interface/exact control/config checks passed; hold 1, failed/violated/timeout/claimed 0, ledger certain ([final snapshot](board-export/snapshot-58.json), [ledger](board-export/ledger.json), [analysis](analysis.json)) |
| UART audit | All 58 BEGIN/DONE pairs occur once and in order; exactly one BUSY_WAIT/WRITE_BEGIN/SENT/DONE_WAIT/COMPLETE sequence per device; no TVFE power command or hold violation ([validation](validation.json), [continuous UART](steps-uart.log), [recorder events](steps-uart-events.log)) |
| Shutdown | Checked fresh proof/kernel/guard/terminal state/ledger/inactive owners; evidence exported and archive SHA verified before poweroff. UART `reboot: Power down` at 367.918841 s ([request](end-poweroff-request.log), [export](export-final.log)) |

## Session restart and transport

The preceding `live-control-01` session staged the candidate over UART while
host Intel Wi-Fi rejected PTK installation. Its FIT transfer ultimately
finished with matching MD5; no warm reset or observer operation followed in
that session. The user subsequently reported both machines powered back on
after hours off. Host Wi-Fi now connected to `spirits`, and SSH worked;
a saved-profile reconnect after the diagnostic boot also succeeded. This
trial used SSH plus a sole passive UART reader for all observer operations
and shutdown. No Wi-Fi driver workaround was applied after the restart.

**Protocol limitation:** the fresh cold SPL was not recorded, since the user
had already powered the board before requesting continuation. The cold
interval is user-reported; the new production boot ID, initial-zero then
patched journal sequence, active owners and gated domain census were
recorded before the single captured warm reset. A replication should also
capture the cold SPL as originally planned.

Old board staging was archived as
`/root/hdmi-dsp-minimum-2026-10-22-previous-a0f682c6`; the fixed diagnostic
directory was freshly staged with this boot's census. [Stage verification](stage-verification.log)
checked all bundle hashes, the unchanged installed bench guard and original
mode-0755 backup. The normal bootcmd, FIT, script, DT and bootloader were
not replaced. Only the RAM diagnostic boot changed the live kernel/DT.

## Interpretation and next work

Control `0x700` is sufficient for completed access under this tested warm
path. No config or latch write is required to observe zero versions here;
those later writes cannot be the only necessary cause of the observed loss.
This is the lowest tested **nonempty stock setup prefix**, not proof that
every bit of `0x700` is necessary or that all alternative orders fail.
The previous no-setup timeout used a different FIT and lacked phase evidence;
it is not a matched level-0 comparison.

Patch retention remains unresolved at finer boundaries. This path still
contains reset/early boot, one warm logo, clock preparation, conditional
demod reset release and the control write. Display/TVCAP reset were already
released; the seven routing words already matched (zero route writes).
Completed `0/0` establishes observed versions, not a direct memory-content
measurement. No DSP patch/graph write, DSP reset assertion, request retry or
additional setup was performed by this observer.

Replicate level 1 in a new fully disconnected cold cycle with captured cold
SPL before adopting a stable access recipe. Levels 2/3 are unnecessary to
establish this trial's sufficiency. Then design a no-reset patched positive
control and matched boundary trial using the qualified control-only setup;
do not improvise a no-logo or additional request in this boot. Automatic
warm recovery and the production one-launch policy remain unchanged.

The display driver was disabled, so its usual panel-shutdown callback did
not run. Lamp remained off. Physically disconnect power after poweroff and
leave the board off. The bench guard remains installed, SHA-256
`5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`.
Its original backup remains at
`/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard`, SHA-256
`96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113`,
mode 0755. Restore only after a disconnected cold normal boot without the
retain flag and verified hashes.
