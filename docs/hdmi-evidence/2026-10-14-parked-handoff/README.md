# Cold coordinator confirmation and parking candidate, 2026-10-14

## Latest: terminal parking and receiver release passed

The parking-capable cold boot, live-audio parking rejection, three-rate capture,
verified audio restoration, terminal MIPS parking and receiver removal passed.
See `parking-summary.json` and `terminal-parking.log`. The first capture attempt
received no source HDMI connection/ELD; after the operator reseated both cable
ends, all three16-second captures passed (48/32/44.1kHz input, fixed48kHz output,
zero driver XRUNs) on the same DSP load. The failed attempt and its clean helper
restoration are preserved in `parking-capture/`; passing evidence is under
`parking-capture-reseat/`.

Parking was refused with EBUSY while the audio driver held a receiver client;
MIPS IPC and the graph remained healthy (`live-parking-guard.log`). After
service stop verified all22 DSP graph words and15 TVFE clock words/bus, the
terminal operation asserted and verified all three CCU reset lines, polled
exact hardware MIPS status0, released the MIPS clock holds, then released the
receiver's EDID/clock/domain/module references and unloaded the owner.

CCU02001600 changed80000002→00000002 and0200160c changed00070001→00000000.
Clock debugfs reported both mips and bus-mips disabled with zero enable/prepare
counts. TVFE is off with zero domain consumers. TVCAP remains on with zero
consumers because the existing keep-tvcap-on board policy marks it always-on;
this test does not establish TVCAP power-off. Linux/SSH stayed responsive.
No kernel warning, reset timeout or detach failure appeared.

Repeated stop preserved the terminal state; warm start and repeat park were
refused without kernel-log changes. WirePlumber is active and the original
firmware path restored. The runtime unit, audio/receiver modules and signal
helpers are gone. Final state and target hashes are in `parking-final-state.log`;
`parking-tested-files.json` identifies tested sources/modules. A physical cold
cycle is required before any new firmware/DSP initialization. System poweroff
ordering, suspend and persistent installation remain separate unvalidated work.

## Earlier uninterrupted capture-only boot and candidate preparation


`boot/result.json` records a successful uninterrupted cold coordinator run.
MIPS was initially exactly parked, launched once, reached source3, and Linux
booted with the corrected0x8319-byte FDT guard and RAM-only audio IRQ settings.
The runtime service initialized the receiver and managed DSP/audio normally.

`current-stop.log` records successful service teardown with22 verified DSP
restore words and15 TVFE clock words/bus, harmless repeated stop, warm restart
refused without kernel-log changes, WirePlumber active, firmware path restored
and responsive MIPS. The runtime unit was removed. At that earlier checkpoint audio was
unloaded and the capture-only receiver owner remained pinned with its holds active.

## Candidate design (subsequently tested above)

The new owner optionally acquires exclusive CCU resets1/2/3 and MIPS clocks19/20
from a validated volatile DT consumer. A write-only terminal parking operation
serializes against audio acquisition and release, requires no clients, prevents
new clients, asserts/verifies reset lines, verifies hardware parked status0 and
only then drops MIPS clock holds. It never restarts firmware. Failed parking
latches and retains receiver holds; the parked-only release cannot bypass it.

This follows the documented U-Boot reset/stop primitive in
`external/u-boot/arch/arm/mach-sunxi/h713_mips.c`, using the exact kernel's CCU
reset/clock provider instead of raw Linux control-register writes. Applying it
under Linux with the receiver active was initially a bench hypothesis; the terminal handoff
was subsequently validated above, independently of system poweroff. Reset lines are asserted individually while the bus clock
is held, before clock release; this differs from U-Boot's whole-word write.

`boot-managed-audio.py --park-capable` adds the opt-in consumer only to the RAM
FDT and checks its reset/clock properties before Linux boot. Default boot
behavior remains capture-only. The target session now records successful
restoration in its boot-ID latch; terminal parking requires that proof and
refuses live audio or competing diagnostic/video helpers. Native tests cover
successful simulated parking, reset/release failure retention and retry refusal.

`build.log` is the exact6.18.38 LLVM W=1 receiver build. Six host boot tests and
fourteen target state-machine tests pass, plus the native release/clock/parking
predicate matrix. Candidate source/module hashes are in `candidate-files.json`;
these differ from the capture-only module used in the successful `boot/` run.

## Planned test (completed above)

A new physical cold cycle was required because the pinned capture-only owner
could not be replaced beneath live firmware and the volatile DT consumer was
missing from that earlier boot. Run one cold `--park-capable` coordinator, verify healthy
capture, stop the service with full restoration proof, then execute explicit
terminal parking and inspect reset/status/receiver cleanup. Do not relaunch
MIPS or reload DSP on that boot. System shutdown ordering, suspend, TVCAP power-off and persistent installation
remain unvalidated; TVFE power-off passed in the terminal test above.
