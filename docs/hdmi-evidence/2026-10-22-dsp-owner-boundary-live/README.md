# Matched no-reset shutdown boundaries — October 22, 2026

**All tested boundaries preserved reported patched DSP versions `1/1`.**
Arm 2 completed all 25 operations; each of four version pairs completed
once without timeout. Exact candidate and baseline matched the
[successful sham](../2026-10-22-dsp-owner-sham-live/README.md).
This is one matched boundary trial, not proof of reset retention or direct
DSP RAM retention. No version-loss boundary was observed in this sequence.

## Results

| Pair | Preceding operation | DSP 0 / DSP 1 |
| --- | --- | --- |
| 0 | Normal pinned patch/graph initialization | `1 / 1` |
| 1 | All 22 saved graph words restored in normal reverse order, individually verified | `1 / 1` |
| 2 | AudioTop config `011a5e00 → 0`, control remains `700` | `1 / 1` |
| 3 | AudioTop control `700 → 0 → 700`, config remains `0` | `1 / 1` |

All full responses were `00000001`, statuses `00000120`, phase 5,
sent/outcome 1. No command echo, skip, timeout, hard failure or uncertain
ledger. Terminal step 25 released the ARM lock, graph_remaining 0,
AudioTop `700/0`; receiver/audio resources and both domains remained held.
No DSP/AudIf access occurred while control was off. No CPU/MIPS/demod reset,
warm logo, module unload, service teardown or repatch after initialization.

The tested graph/AudioTop sequence by itself did not reproduce previous
post-shutdown/reset/logo zeros. Remaining possibilities include omitted
SPDI/bridge restoration, clock restoration/demod reset, CPU reset/early
boot, warm logo, and interactions/order with those operations. Normal
teardown restores SPDI/bridge between graph and AudioTop; these operations
were omitted in both arms. Do not treat this as proof that graph/AudioTop
can never contribute in the full teardown path. Next design should bracket
remaining teardown operations before assigning loss directly to reset.
No further capture is armed and no additional boundary was improvised.

## Identity and provenance

Fresh cold boot `77d7afff-6ff8-4629-961d-1fa56dc3015d`, distinct from sham
`dcfe762c-9cb5-44ca-a546-049f03e2a1fd`. User confirmed full physical
unplugging between runs. Cold catcher recorded fresh OPEN at
22:56:27 UTC and interrupt/prompt at 22:57:50 UTC. One SPL with zero
GP6/GP7 and parked MIPS; one guarded cold source3/handoff, unchanged normal
bootcmd and production FIT. Production kernel remains
`6.18.38 #1 SMP Fri Oct 16 15:44:49 PDT 2026`.

Initial DSP `0/0` → pinned 724-pair patch verified `1/1`, managed graph
verified 22 words, PCM omitted, IRQs disabled and module/resources pinned.
Initialization checked exact baseline register census and all 22 saved
graph words against the exported sham before any measurement. Firmware,
script, module/loaded build ID and manifest matched. Installed guard and
original mode-0755 backup verified unchanged. Wi-Fi initially timed out
before board networking was ready; reconnect then SSH succeeded.

Exact source artifacts:

* Module SHA-256 `6cbc305cfcd14b20d9c72c25c293402cc2c7490d1cf3e977ba60654c5bf62001`.
* Cold RAM script SHA-256 `0f3245113d33501761e51aa87c59980e63e03c2569d6b05e3276b47d18e6e1d1`.
* Manifest SHA-256 `e1bdbf185f3cd9bc3f198d54caae8d13daa4c38911ad3ea3683f2e4a172711f8`.
* Qualified sham canonical sorted-JSON-plus-newline SHA-256
  `eb31e9e00a49666804f1f3cfe7060b2251152da655a1c01d337823ff2f728fa6`;
  exact bytes preserved in `cold-boot/sham-record.json`.

## Evidence and checks

`cold-catch/` and `cold-boot/` preserve raw cold origin, transfer and boot.
`cold-health.log`, `initialize.log`, `arm-proof.json`, `baseline.json` and
`manifest.json` preserve setup/identity. Host `step-*.json` and
`snapshot-*.json` record explicit operations/reviewed checkpoints.
`board-export/` contains exact remote snapshots, ledger, initialization and
final kernel journal/state. `steps-uart.log` and events preserve one sole
reader from before initialization through Power down and CLOSE.
`observe.py`, `stage-host.py`, `initialize-host.py`, `record-steps.py` and
`export-host.py` preserve host orchestration; do not replay this completed
trial. No FIT/module binaries are included.

`validate.py` (run from repository root) passed: matched classifier,
fresh boot/ledger identity, 25 ordered BEGIN/DONE, eight ordered complete
requests, exact 22 reverse-order restores and saved values, every step's
expected graph/control/config state, fresh cold handoff and verified archive.
See `analysis.json`, `matched-analysis.json` and `validation.json`.
Raw boot UART contains one non-UTF-8 byte in the automatic-login banner;
it is preserved unchanged and decoding for validation uses replacement.
All diagnostic step UART is decodable, and expected sequences validate.
Board RTC is stale; boot IDs/host capture order establish provenance.

Export `board-export.tar.gz`: 266,333 bytes, SHA-256
`e4ad3512a5f1aa1901d737b0419b424cbac60a7ce5e80a89b41a5a57f8f2e0b9`,
retrieved and verified before checked poweroff. SSH exit 255 followed
poweroff; UART confirmed guard retaining HDMI holds and
`reboot: Power down` at 274.472661 seconds. Recorder closed. User instructed
to physically unplug and leave off; post-run disconnection not yet confirmed.

The planned two-arm batch is complete. No clear loss boundary exists to
confirm yet; roughly two to four further matched cold-cycle runs remain an
estimate for the remaining teardown/reset/logo bracket, with count dependent
on findings. See [design/runbook](../../hdmi-dsp-owner-boundary-design-2026-10-22.md).
