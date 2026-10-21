# Logo-free cold access attempt — October 21, 2026

**Result: maintenance boot passed; access preparation became unresponsive.**
No version request was sent. This is a failed access experiment, not evidence
that a reset clears or retains a DSP patch. Do not repeat this bundle unchanged.

## Identity and cold boundary

The operator confirmed all power/USB/UART had been disconnected for at least
60 seconds, then reconnected UART before applying board power with HDMI
connected. The catcher recorded fresh SPL/proper boot and exactly one space
at the autoboot countdown. It stopped at the prompt before logo/workspace
initialization. GP6, GP7, MIPS clock/reset/status and SCP reset were zero;
demod bus was zero and audio functional gates were off.

The installed proper banner was
`2026.07-rc5-g320a17f71d41-reset-trace-cf29b4f054d9`.
The module/wrapper source was repository commit `a6b7f8c`; exact module,
wrapper, guard and boot identities are in the manifests. The module SHA-256
was `9d6fdcece8769017a571f2c1643aaf4146697a0e3a8aa9026d9777fb78645d7c`.

## Maintenance boot passed

Every guarded RAM command acknowledged success, including GP6/MIPS/SCP
checks, FIT length/CRC, copied DT edits, and GP6 reservation. `bootm` checked
embedded subimage hashes. No logo/source3 command ran. Boot media, saved
environment, SPL, BL31 and proper were not written in this attempt.

The uninterrupted UART boot and SSH health capture both identified Linux
boot `fcff9719-ac23-418c-b013-b7d030984a04`, kernel `6.18.38`. The dedicated
DT marker was `44535031`, AFBD/display and CPU_COMM nodes were disabled,
there was no HDMI handoff or CPU_COMM device, and capture/signal/speaker
units were inactive with failed conditions (expected skips, not service
failures). No competing HDMI owner appeared in the module list.

Root mounted read/write on mmcblk0p26 with UUID
`956d9901-0eb3-4d75-bb44-e37a46ba9f40`; growfs completed. No ext4 error or
journal recovery appeared in this boot before preparation. Existing Wi-Fi
regulatory/firmware diagnostics and the Bluetooth opcode failure remain in
the complete log; this does not claim a globally error-free boot.

## Failed preparation boundary

A passive UART recorder was opened before the single supported wrapper
`prepare` request, pinned to the above boot ID and staged bundle. No
`versions` or `restore` request followed. The prepare SSH client returned no
result. A separate read-only SSH inspection timed out; the host had fallen
back to its other Wi-Fi connection and reactivation of the board connection
reported that the network could not be found. UART recorded no bench output,
command echo, health reply, panic or reboot. A write-only serial health
request and an ordinary `systemctl poweroff` request also produced no output.

This is consistent with a board/kernel stall during the pending preparation,
but does not localize it. The wrapper has no flushed before-insmod milestone,
and the module's first informative log is late in setup (AudioTop). We could
not read its phase file, loaded state or sysfs flags afterward. Module entry,
resource acquisition, power domains, display/TVFE/audio clock/reset operations,
AudioTop, DSP status and ownership sampling therefore cannot be distinguished
by this trace. Absence of UART output does not prove any particular last
instruction or peripheral fault. The DSP command timeout was never tested:
module preparation contains no DSP command, and the separate version request
was never issued.

The stalled local SSH client was closed without another board command. There
was no SysRq, reset, force-unload, latch clear, source3 launch or setup retry.
The operator subsequently confirmed lamp/fan off and all board power/USB/UART
disconnected, leaving the board off. The passive recorder was then stopped.
An orderly Linux shutdown was **not** observed. The next boot must inspect
root/journal health before any further hardware experiment.

The previously installed extended shutdown hook remains on disk, with the
old hook backed up. Its protection depends on a responsive kernel/shutdown
path; it cannot recover a stalled bus transaction. Module holds and GP6 state
during the stall could not be inspected. Physical disconnection is the recovery
boundary, not successful software cleanup.

## Next experiment gate

1. Audit access dependencies against the no-logo DT and the production
   prerequisites. Do not assume clock/domain setup proven after source3 is
   valid without source3, or blame a specific power domain from this trace.
2. Prepare a revised, separately identified bench with flushed userspace
   milestones before module load and serial-visible before/after markers at
   each resource, domain, clock/reset and MMIO boundary. Split preparation
   into explicitly acknowledged stages, with no automatic continuation after
   loss of acknowledgment. Stop before AudioTop/status/ownership until earlier
   stages are independently established. Poll deadlines cannot bound a stalled
   MMIO access. Do not reinstall/retry the current module unchanged.
3. On another fully disconnected cold boot, re-establish boot identity and
   filesystem health, capture passively, then qualify prerequisites one stage
   at a time. Preserve the existing GP6 policy and physical rescue route.
4. Only after access preparation is demonstrated may a separate one-shot
   version pair be considered. Retained-patch discrimination and automatic
   warm recovery remain later unimplemented work.

## Files

`cold-uboot.log` and catcher events preserve the pre-logo stop; `ram-boot.log`
contains all RAM commands and Linux startup. `uart-identity.txt` and
`linux-preflight.txt` correlate identities and Linux prerequisites. The empty
`prepare.txt` is intentional: the pending SSH request returned no output.
`bench-uart.log` contains only its recorder start line; it is not missing
positive DSP evidence. Health/poweroff request files document sent commands,
not execution. `host-health.txt` is a hand-curated host observation, not a raw
command transcript. JSON manifests identify prepared boot/bundle inputs;
`sha256.json` authenticates the copied evidence bytes by local digest only.
Board wall time reset to April 13; use boot IDs and kernel monotonic times.
