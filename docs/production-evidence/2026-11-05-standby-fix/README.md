# Standby wake soft-start fix — November 5, 2026

An abrupt lamp/fan enable reproducibly reset the board. A half-second startup
pulse ramp now wakes it without rebooting. The installed fix changes only
`/usr/local/bin/h713-standby` and adds `/usr/local/bin/h713-lamp-ramp`.
The original script is backed up under
`/var/lib/h713-standby-wake/20261105-softstart/h713-standby.before`.
Exact package and installed hashes are in [the install manifest](install-manifest.json).

Stopping HDMI video/speaker consumers did not prevent reset. Restoring and
pinning the CPU at its active1296MHz operating point before lamp enable also
failed. Neither rejected approach is included in the installed fix. Both
negative controls and their captured resets are retained here.

The new helper uses the existing GPIO-backlight sysfs owner, not raw MMIO. It
ramps1% to100% duty at500Hz over250cycles, approximately0.5seconds, then holds
lamp/fan power fully on. It is a startup ramp, not steady reduced-duty fan
operation. The helper locks memory and requests low-priority FIFO scheduling
for the bounded timing interval. Failure leaves the lamp off and returns
failure; standby retains its state and CPU cap. Missing helper refuses standby
entry. Repeated wake after lamp already enabled does not pulse it again.

One trial plus two installed-script cycles (3s and10s standby) and a virtual
KEY_POWER pair through the unchanged h713-keyd all passed on boot
`72aba591-6346-482f-a905-5d4b50ee7bb7`. Lamp power returned0, CPU limit
returned1296000kHz, signal stayed locked1280x720, and HDMI video/speaker
services were active. The key cycle retained frame rejects1->1 (no new
rejection) and audio xruns0. No zero-lifetime-rejection claim is made.
Operator confirmed that desktop, lamp and fan are back after the wake tests.

Offline checks passed: real C helper under simulated clock/sysfs with failure
injection,3shell lifecycle tests,6release tests, strict native/static arm64
compilation, shell syntax, and changed-file whitespace checks. Rootfs
customization now compiles the helper alongside the key daemon, and release
source locking includes the new source. A complete new rootfs image was not
built or flashed.

The updated75-file audit script adds the helper hash and replaces the original
standby hash. After explicit approval for its transfer, all75file pins,
package/kernel identity, raw bootloader/environment pins and startup checks
passed on the same Linux boot. [Audit receipt](audit.json).

This validates a software mitigation of the reset trigger. Supply/CPU/reset
rails were not measured, so the underlying electrical cause is not established.
Extended HDMI-active fan-off thermal qualification remains separate from these
brief wake checks. No kernel, bootloader, firmware, receiver or HPD policy was
changed by the fix.

[Structured result](RESULT.json), [install readback](install.log),
[installed cycles](installed-cycles.log), [key-handler cycle](key-cycle.log).

The operator later reported the board supply disconnected. A separate cold
start is being prepared to verify persistence of the installed fix.

## Installed-fix cold boot and wake validation

After supply removal, cold startup completed normally on boot
`45c76aa6-337c-4935-9918-9341434ea99d`. All75file pins and
kernel/package/raw bootloader/environment/startup audits passed again.
The host saved board Wi-Fi profile needed reconnection before SSH was
available; UART had already confirmed Linux startup.

A ten-second standby cycle entered at174.60s and woke at185.17s, preserving
that Linux boot ID. Lamp power returned0, original CPU maximum was restored,
video/speaker services were active and signal locked1280x720. Rejected frames,
audio xruns, bad-guard and invalid-pair counters were all0 afterward; sampled
rejected frames and audio xruns were0 before the cycle too. Latest physical
return confirmation is requested separately. No further wake test is needed
unless that report contradicts the recorded state.
[Cold result](cold-01-result.json), [audit](cold-01-audit.json),
[wake log](cold-01-cycle.log).

Operator confirmed that desktop, lamp and fan all returned after the cold-boot
wake test. Standby wake fix validation is complete; board is left running.
