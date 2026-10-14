# H713 firmware-lifetime receiver owner

This module replaces the diagnostic `h713_hdmi_power` and `h713_edid_clock`
holds. Its lifetime follows running MIPS firmware, independently of an ALSA
capture module. No firmware start/stop, receiver MMIO, IRQ or GPIO operation is
implemented here. EDID clock/reset ownership uses the existing DT test-consumer
node. Source3 still requires the guarded U-Boot sequence.

Status: exact-kernel LLVM W=1 build and native release/clock-step checks passed.
Firmware-lifetime guards, all three capture input rates and audio teardown
passed on the board; receiver holds remained active with clients0 and MIPS
responsive. See [evidence](../../docs/hdmi-evidence/2026-10-14-receiver-owner/README.md). The audio driver now requires this
owner by default, acquiring a client/module reference before audio hardware
setup and dropping it only after DSP/audio/TVFE restoration. Explicit
`require_receiver_owner=0` preserves legacy diagnostic holds.

## Lifetime

Loading requires `armed=1 live_source3=1`, initial `clock_count=0`, and the
read-only hardware MIPS reset status0306101c must be1, matching the CPU_COMM
and mips-shell implementation. The module takes a firmware lifetime reference
to itself before attaching power domains. Both TVFE/TVCAP domains are resumed;
four receiver clocks are enabled one step at a time in the validated order;
skipped steps and decreases are rejected. The
boot helper checks benign MIPS IPC after each increment. At clock4 the EDID
platform driver registers and acquires its clock/reset. Until all resources
are ready, ALSA acquisition returns EAGAIN.

A setup failure retains partial holds and the lifetime reference, reports
`init_error`, and blocks capture. It does not automatically power off underneath
live firmware. EDID unbinding through sysfs is disabled. Ordinary receiver
module removal is refused while the firmware reference remains.

`release_when_parked=1` never stops MIPS. It refuses release unless the hardware
status is exactly0 and there are no audio clients. Only then may it release
EDID, receiver clocks, domain references and the firmware module pin. Unknown
status fails closed. Domain-detach failure retains the pin. Never force module
removal or clear/reset MIPS to bypass this protection.

The parked release predicate and terminal parking handoff passed native and
hardware tests. Live audio prevented parking; after full audio restoration,
all three MIPS resets and status0 verified, the owner released and unloaded,
TVFE powered off and Linux stayed responsive. TVCAP remains on under the
existing boot-retention policy. See
[parking evidence](../../docs/hdmi-evidence/2026-10-14-parked-handoff/README.md).

## Bench setup

Use a physical cold boot and manual U-Boot stop, followed by the established
single MIPS launch/source3 worker verification and RAM-only Linux IRQ correction.
Do not remove existing diagnostic power holds beneath live firmware to replace
them. Instead stage this module in `/tmp/h713-linux-return` on the new boot,
then on the host run:

```sh
python3 tools/hdmi/prepare-source3.py --postboot-only --receiver-owner \
  --trace-reader /tmp/h713-linux-return/read-comm-trace.py
python3 tools/hdmi/load-managed-audio.py /tmp/h713-owner-audio-load
```

The first command loads the owner, stages four clocks with IPC checks and
verifies EDID/lifetime readiness. The second stages the managed audio module
and pinned firmware, restores the temporary firmware search path, and checks
TVFE/DSP readiness. The existing three-rate capture runner supports this owner.

After capture, unload only the audio module and restore WirePlumber if its
control handle needed releasing. Require22 DSP and15 TVFE clock/bus restore
checks, owner `clients=0`, `firmware_pin=Y`, and responsive MIPS. The receiver
owner remains active for the firmware lifetime. A new audio initialization
still requires fresh DSP versions0/0 from a physical cold boot.

## Terminal parking (bench validated)

The optional `h713,hdmi-mips-shutdown-bench` RAM device-tree consumer provides
three exclusive CCU reset lines (RST_BUS_MIPS/DBG/CFG) and two MIPS clock holds.
The owner validates all provider/ID assignments before acquisition. Capture-only
boots without this consumer retain their existing behavior. Prepare this node
with `boot-managed-audio.py OUTPUT --cold-boot-confirmed --park-capable`.

`park_for_shutdown=1` executes under the same owner lock as audio acquisition
and resource release. It requires shutdown_ready, exact live hardware status1,
no audio clients and no initialization error. It blocks new clients, asserts
and verifies each reset through the CCU provider, waits up to20ms for hardware
status0, then drops the two MIPS clock holds. It does not restart firmware.
Any failure latches init_error and park_failed, retains receiver holds and
blocks retry and parked release. A physical cold cycle is then required.

The target session's explicit `park --terminal-shutdown` requires a successful
managed audio stop with persisted restoration verification, no diagnostic or
video helpers, clients0 and working IPC immediately before parking. It checks
parked status before requesting the existing parked-only release and receiver
removal. The intended bench sequence is service stop, terminal park, then
runtime-unit cleanup. CPU_COMM is retained; no firmware RPC is issued after
parking. This candidate is not connected to system poweroff or suspend.

The exact-kernel LLVM W=1 build,20 Python guard tests, native policy matrix
and hardware handoff pass. MIPS clocks disabled, TVFE powered off and owner
removal passed after three-rate capture. Actual system poweroff, suspend and
TVCAP power-off remain unvalidated. See [parking evidence](../../docs/hdmi-evidence/2026-10-14-parked-handoff/README.md).
