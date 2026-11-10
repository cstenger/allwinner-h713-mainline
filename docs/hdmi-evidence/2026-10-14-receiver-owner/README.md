# Firmware-lifetime receiver owner, 2026-10-14

The new `h713-hdmi-receiver.ko` replaces the diagnostic power/EDID holders.
Its lifetime follows running MIPS firmware, independently of ALSA. The audio
driver requires its readiness/client API by default and releases its client
only after DSP, audio and TVFE restoration. Exact-kernel LLVM W=1 builds and
native release/clock-step policy checks passed. **PASS: all three input-rate captures and audio teardown with receiver
holds retained for live firmware.** [Summary](summary.json).

## Lifetime design

The owner verifies the same read-only MIPS reset status0306101c used by CPU_COMM
and mips-shell. With status1 and explicit guarded-source3 acknowledgments, it
pins its module before acquiring power resources. It resumes TVFE/TVCAP through
the existing PPU provider, then permits only same-count or one-clock-increment
startup, never decreases. The boot companion verifies benign MIPS IPC after each
of the four validated receiver clocks. Clock4 registers the existing-DT EDID
clock/reset consumer. EDID sysfs bind/unbind attributes are suppressed.

Audio can acquire a client only when core setup succeeded, both domains/four
clocks/EDID are ready and MIPS is still out of reset. A setup error retains
partial holds and the firmware pin, blocks capture, and reports core errors or
unready EDID. It does not power off beneath firmware as initialization rollback.

Ordinary module removal is blocked by the firmware lifetime reference even
with no audio clients. `release_when_parked=1` does not stop/reset MIPS. It
requires hardware status exactly0 and clients0 before releasing holds and the
module pin. Unknown status fails closed; detach failure retains the pin.
The parked release predicate is natively tested; the actual parked power-down
path is not hardware-validated. This run never parks or resets live firmware.

## Work completed before the new boot

[Native policy tests](native-policy.log) exercise the actual policy header:
release allowed only at status0/clients0; active/unknown status and clients
reject it. Clock startup permits only0..4, same count or one increment.
[Missing-owner test](missing-owner.log) verified the updated audio driver
rejects loading before audio setup when the owner is absent. Existing live
power holders were retained, and MIPS remained responsive.

## Guarded new boot

The user physically cold-cycled and manually stopped at U-Boot. The same single
MIPS launch, live channel PID/source3 worker, preserved FIT and RAM-only audio
IRQ correction verified. The new boot loaded no legacy power/EDID/TVFE/DSP
helper. Source3 trace/canaries verified, then
`prepare-source3.py --receiver-owner` loaded the new owner and staged all four
clocks with IPC checks. Both domains and EDID became ready; MIPS responded.
[Preparation](bench/receiver-preparation.log).

With clients0 and firmware live, parked release, ordinary module removal and
clock decreases were rejected, with unchanged kernel log and responsive MIPS.
[Guards](bench/live-firmware-guards.log). After managed audio loaded, clients
read1 and live release remained blocked. Legacy holders were absent.
[Audio client](bench/audio-client-guard.log),
[automatic TVFE/DSP load](bench/audio-load/load.log).

## Build and remaining checks

[Build hashes](build-manifest.json) identify both modules and the changed bench
tools. No receiver MMIO, firmware launch/stop, PLL-rate write, GPIO operation,
boot flash or saved environment change was added. Source3 still starts through
the guarded U-Boot procedure. The long-lived owner must remain loaded at the end
of the live-firmware test; forcing removal is prohibited.

## Final hardware result

All three real16-second recordings passed at actual HDMI inputs48/32/44.1kHz,
producing768,000 frames each at48kHz stereoS16_LE. Expected left/right tones,
zero silence tails, process exits and closed/reopened capture passed. Driver
XRUN count remained zero. [Capture summary](bench/capture-test/summary.json).

Removing only the audio module restored all22 DSP words and15 TVFE clock words
plus bus/reset baseline. Receiver clients changed1->0, while `firmware_pin=Y`,
`edid_ready=Y`, `clock_count=4`, `init_error=0`, and both power-domain devices
remained active. Ordinary receiver removal and explicit release were again
rejected with no audio client, proving the firmware pin independently retains
the resources. MIPS remained responsive.
[Teardown and retained owner](bench/audio-unload-owner-retained.log).

WirePlumber was briefly stopped only to release its audio control handle,
then restored active. The firmware search path is verified at its original
empty value. All four legacy helpers and the audio module are absent; the new
receiver owner remains loaded intentionally for MIPS lifetime. EDID unbind is
not exposed. [Service/path checks](bench/services-restored.log).

No recovery is pending. The volatile DSP patch remains until physical cold
boot; another audio initialization requires fresh0/0 versions. No serial
listener ran, boot artifact was flashed, environment saved, or module installed
persistently. Source3 startup, parked receiver shutdown, long-term recording,
physical hotplug endurance, source changes while open and suspend remain
unvalidated. Do not force receiver removal to finish cleanup.
