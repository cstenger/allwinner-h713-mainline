# Guarded runtime HDMI audio lifecycle, 2026-10-14

The cold-U-Boot coordinator and target session implement automatic source3,
receiver and managed DSP/audio startup with a runtime-only systemd unit.
Hardware validation used Linux6.18.38 and the matching receiver/audio modules;
`tested-files.json` records source and module hashes.

All lifecycle checks passed. Three16-second captures at48,32 and44.1kHz
HDMI input passed with fixed48kHz stereoS16_LE output and zero driver XRUNs.
Service stop verified all22 DSP graph words and15 TVFE clock words/bus.
Healthy duplicate start and repeated stop were harmless; busy stop and warm
restart were refused before hardware changes. See `summary.json`.

Final board: audio unloaded, receiver retained, MIPS responsive, WirePlumber
active, original empty firmware path restored; runtime unit removed and no
capture/source player/transient signal helper remains.

## Boot and startup

The first attempt correctly verified cold parked MIPS, launched it exactly
once, proved firmware readiness and source3 completion, and loaded the FIT.
It then stopped before Linux at the FDT size guard: U-Boot printed `8319`,
which is hexadecimal, whereas the original expected constant was decimal.
`fdt-size-diagnostic.log` records the header `d0 0d fe ed 00 00 83 19`, proving
33,561 bytes. The constant and fixture were corrected to `0x8319`.

The guarded resume validates the original parked/readiness/IPC/source3 logs,
then checks current U-Boot identity, live MIPS status, unchanged channel PID
and completed source3 trace. It resumes RAM FIT/FDT preparation without any
MIPS launch or source-selection RPC. `resume/` records the successful RAM boot,
target unit verification and startup. The corrected uninterrupted cold path
has native coverage; this hardware run includes the documented size-guard
stop and resume. No boot image or saved environment was modified.

The host creates proof bound to the resulting Linux boot ID. Target startup
checks that proof, pinned2896-byte firmware hash, kernel/module ABI and live
trace guards; initializes the receiver clocks incrementally with IPC checks;
and loads managed audio once. The original firmware search path is restored.
The service lives under `/run/systemd/system`, with its bundle under `/tmp`.

## Validation records

- `native-boot-tests.log`: five tests covering single launch, cold-state and
  image/address guards, ambiguous PID rejection and resume without relaunch.
- `native-session-tests.log`: eleven tests covering ownership, boot-ID proof,
  idempotency, busy stop, setup failure latching, restore verification and
  preservation of WirePlumber/firmware-path state.
- `live-guards.log`: healthy duplicate start leaves dmesg unchanged; an owned
  five-second capture makes stop fail before changing hardware; graph remains
  ready, reader finishes and closes normally.
- `capture-test/`: established three-rate capture test and signal helper logs.
- `stop-guards.log`: runtime-unit stop, restore evidence, idempotent second
  stop, refused warm restart and final runtime-unit removal.

The native host unit verifier was restricted by sandbox socket permissions;
the actual target's `systemd-analyze verify` and unit startup provide hardware
unit validation.

## Scope and limitations

Audio stop retains the firmware-pinned receiver with clients0, four clocks,
EDID hold and both power domains active. It does not park MIPS. Actual parked
receiver release, system poweroff ordering with consumers, suspend integration
and persistent installation remain unvalidated. Capture clients must close
before stop, and consuming units should order after the capture service.
Existing IR/suspend/poweroff configuration remains intact. No serial listener
is installed. A physical cold cycle is required before another managed DSP
initialization; warm restart is deliberately refused.
