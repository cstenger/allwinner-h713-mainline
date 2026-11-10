# No-reset patched positive control — October 22, 2026

**PASS: all four measured DSP version pairs completed `1/1`.** Arm 1,
production kernel `6.18.38 #1 SMP Fri Oct 16 15:44:49 PDT 2026`, fresh boot
`dcfe762c-9cb5-44ca-a546-049f03e2a1fd`. Board reached UART `Power down`
at 414.276830 seconds, sole recorder closed, user instructed to physically
unplug and leave off. Physical disconnection has not yet been confirmed.

This qualifies the patched positive control for the separately powered
matched boundary arm. It does not measure reset retention or identify the
patch-loss boundary. No graph restoration, AudioTop change, owner teardown,
reset or warm logo occurred after one-time normal pinned patch/graph setup.
The installed guard and original mode-0755 backup were verified unchanged.

## Observed result

| Checkpoint | DSP 0 / DSP 1 | Full response / status per device |
| --- | --- | --- |
| Patched baseline pair | 1 / 1 | `00000001 / 00000120` |
| Graph sham pair | 1 / 1 | `00000001 / 00000120` |
| Config sham pair | 1 / 1 | `00000001 / 00000120` |
| Control sham pair | 1 / 1 | `00000001 / 00000120` |

Each request was sent once and completed (phase 5, outcome 1). No timeout,
command echo, skip, hard failure or uncertain ledger. All 25 explicit steps
returned once, in order; stock ARM lock released at terminal step 25.
AudioTop stayed `00000700/011a5e00` throughout measured steps; all 22 saved
graph words remained held and their saved values were unchanged.

Cold catcher recorded one SPL, zero GP6/GP7 and parked MIPS. Loader verified
unchanged bootcmd and production FIT, transferred only the 4,360-byte RAM
script and performed one cold source3 launch with verified handoff. Initial
DSP `0/0` was followed by the pinned 724-pair patch verified `1/1`. Isolated
owner omitted PCM, disabled audio IRQs and pinned receiver/audio resources.
Wi-Fi/SSH worked. Board RTC dates are stale; boot ID and host capture order
bind the evidence.

## Evidence and reuse

* `cold-catch/`, `cold-boot/`: raw cold origin, transfer and Linux boot.
* `cold-health.log`, `initialize.log`, `arm-proof.json`, `baseline.json`,
  `manifest.json`: fresh boot/setup and exact candidate identity.
* `step-*.json`, `snapshot-*.json`: host returns and reviewed checkpoints.
* `board-export/`: exact remote snapshots, ledger, initialization and final
  kernel journal/state. **Use `board-export/snapshot-25.json` as the exact
  arm-2 sham record**, not the host snapshot with added analyzer output.
* `steps-uart.log`, `steps-uart-events.log`: sole step/initialization/shutdown
  recorder with OPEN/CLOSE, all 25 ordered BEGIN/DONE and eight requests.
* `analysis.json`, `validation.json`, `validate.py`: classifier and independent
  sequence/state/archive checks. Validator runs from the repository root.
* `export.log`, `board-export.tar.gz`, `poweroff.log`: verified export and
  checked poweroff. SSH exit 255 followed poweroff; UART confirms completion.
* `observe.py`, `record-steps.py`, `export-host.py`: exact host orchestration.

Export: 264,868 bytes, SHA-256
`1362d88effaceb1e82df5996f9deecd4655d70b4ad762f23be30ae4d240c7bf5`.
Exact exported snapshot canonical SHA-256 (sorted JSON plus newline):
`eb31e9e00a49666804f1f3cfe7060b2251152da655a1c01d337823ff2f728fa6`.
Module `6cbc305cfcd14b20d9c72c25c293402cc2c7490d1cf3e977ba60654c5bf62001`;
script `0f3245113d33501761e51aa87c59980e63e03c2569d6b05e3276b47d18e6e1d1`;
manifest `e1bdbf185f3cd9bc3f198d54caae8d13daa4c38911ad3ea3683f2e4a172711f8`.
No module/FIT binaries are included here. See [prepared design/runbook](../../hdmi-dsp-owner-boundary-design-2026-10-22.md).

Next: arm 2 after at least one minute fully disconnected, same candidate,
new cold proof/boot ID and matching baseline/saved graph values. Compare
patched pair, then graph restoration, config clear, control off/on, stopping
at the first version change or timeout. No automatic second run was armed.
One planned matched run remains in this batch; a clear finding would normally
need one independent confirmation. Further count depends on that outcome.
