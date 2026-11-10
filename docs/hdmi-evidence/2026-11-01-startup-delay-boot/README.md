# Two-second startup-delay boot: warm validation passed

**PASS: one ordinary warm reboot, measured delay, HDMI detection and Linux
startup, with the operator confirming normal projector startup and the host
desktop without any cable or host-output change.** Both recordings are now
stopped cleanly and the UART is released. No second reboot, forced detection,
reseat, board service restart or recovery operation occurred.

## Measured outcome

The boot changed from `afe48e93-6604-44de-a220-acb9416e8363` to
`7e9e206d-bd7b-493a-b3fe-af69ab3be77f`. The guarded request issued exactly one
ordinary `systemctl reboot`, with a normal sync, no force option, no reboot
argument and no bootloader interruption. Its exclusive request receipt is saved
in the existing board backup directory. SSH closed after dispatch; UART then
captured one kernel restart, one SPL/proper boot and the Linux login prompt.
Migrated U-Boot loaded its environment from MMC offset `0x93d80000` successfully.

The loaded signal unit used the exact staged private wrapper with
`--bench-delay-ms=2000`, while retaining production ExecStop. Its journal contains
exactly one start/completion pair for this boot. The actual wait was
**2.021350376 seconds**, and the existing EDID/HPD initialization followed it.

| Milestone | Linux uptime, seconds |
| --- | ---: |
| DSP graph verified | 22.509187 |
| Delay start | 23.019943176 |
| Delay complete | 25.041293552 |
| Kernel EDID/HPD ready | 25.086580 |
| Initial signal none | 25.711290 |
| Signal acquiring | 26.163271 |
| Signal locked, 1280×720 | 26.387334 |

These use kernel uptime and the wrapper's monotonic timestamps, rather than
the board's incorrect wall clock. Host cache observations use host UTC:

| Host observation | UTC, November 1 |
| --- | --- |
| Disconnected/disabled, no EDID | Before reboot |
| Connected, 256-byte EDID, output initially disabled | 08:42:22.023073 |
| Connected/enabled, same EDID | 08:42:22.273904 |

The cached EDID SHA256 is
`edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`.
It exactly matches the unchanged board EDID payload from the preceding failed
boot's saved evidence. Its header and both 128-byte block checksums pass. The
host remained connected/enabled with that EDID through recorder shutdown at
08:44:30 UTC. There were no cached-reader errors or UART disconnects; the maximum
heartbeat interval was 5.101 seconds.

At Linux uptime 51 seconds, video was locked and 1,448 frames had been produced.
At 120 seconds it remained locked with 5,589 produced and 5,587 delivered. Bad
guards, rejected frames and invalid AFBD counters were zero. The two overwritten
frames were already present at the first snapshot and did not increase. This
checks startup and continued frame flow, not a new media-quality/audio stress
qualification.

Linux reports `running`, multi-user target active and zero failed units. Capture,
signal, ring, speaker and video services are successful, with zero restarts.
The session belongs to the new boot and the signal owner is ready, not failed,
not restored, recovery zero. The normal startup check passes. All **56 production
file/metadata pins**, **eight protected storage ranges** and **both installed
migration regions** still match. The staged runtime/drop-in checks also match.
UART includes the existing shutdown watchdog-not-stopped warnings, also present
in the earlier successful warm-boot capture; the requested reboot completed.

## Interpretation and remaining temporary configuration

The requested delayed warm-boot validation passed. It does **not** establish
that two seconds fixes the original cold-start failure: earlier undelayed warm
boots also succeeded, and no matched 0 ms bench run or new cold boot was performed
here. The original SCP sequence, EDID and production binaries are unchanged.

The temporary override remains installed and active for this boot. Remove the
exact new drop-in and review the production merged unit before another boot,
using the [staging backup/reversion record](../2026-11-01-startup-delay-stage/README.md).
No automatic reversion was installed or run, and no live owner was stopped to
change configuration. The board is left running with HDMI locked and the host
desktop visible.

Evidence: [result and timing](RESULT.json), [signal journal](signal-journal.txt),
[UART milestones](uart-excerpt.txt), [operator observation](OPERATOR-OBSERVATION.json)
and [recorder shutdown](RECORDER-STOP.json). Full raw recordings, cached EDID,
read-only snapshots, sources and dispatch receipts are checksum-sealed under
`local/recovery/2026-11-01-hdmi-delay-boot-validation/` and its sibling archive.

## Original arming record

At arming, **both recorders were ready and no boot command had yet been issued**.
This continued the
[verified staging](../2026-11-01-startup-delay-stage/README.md).

The sole UART owner is `h713-delay-boot-uart-20261101-01.service`, initially PID
57240. Its descriptor for the CP2102 `/dev/ttyUSB0` is read-only. The pinned
receive-only recorder uses 115200 baud and records raw bytes plus host UTC chunk
timestamps. It sends no serial data and reconnects if the adapter disappears.
An actual `OPEN` milestone was verified; zero initial raw bytes is consistent
with arming while the already-running board console is quiet.

`h713-delay-boot-hdmi-20261101-01.service`, initially PID 57243, samples only the
cached `status`, `enabled` and `edid` sysfs attributes for `card1-HDMI-A-1`. It
checks the card/connector mapping to NVIDIA PCI `0000:0c:00.0`, samples every
250 ms, and records changes plus five-second heartbeats with host UTC and
monotonic timestamps. EDID length, hash and cached bytes are preserved. Initial
state was disconnected/disabled with zero EDID bytes; a successful heartbeat
was verified after more than 100 samples. No DRM/NVIDIA device descriptors,
GPU ioctls, force-detect calls or sysfs writes are used.

Both transient user services have `Restart=no`, private log permissions and
graceful SIGTERM handling. They persist beyond the assistant turn and require
explicit cleanup after the validation. Four offline reader fixture checks passed
for disconnected cache, connected cache/EDID hash, oversized-attribute refusal
and PCI-mapping refusal. The UART recorder source matches the previously tested
and used SHA256 `957edf66a028f80edd5ca8b241d5f23240fa1e43b2bb63deee35787a5c20c73a`.

Live files are under `local/recovery/2026-11-01-hdmi-delay-boot-validation/`:

* `ARMED.json`: verified service identities, sole owner, descriptor access flags,
  source hashes, initial monitor heartbeat and exact log paths.
* `uart-01/serial.log` and `serial-timestamped.log`: continuously appended UART.
* `host-hdmi-01/events.jsonl` and `latest.json`: cached host observations.
* `PLAN.json`, recorder source copies, launch receipts and offline reader checks.

The logs remained open during capture. The original source/configuration
checksums covered only fixed arming inputs and receipt; the completed packet now
has a separate full checksum manifest and archive.

No board connection/command, service restart, reboot, HPD pulse, cable change or
host display reconfiguration occurred during arming. A later separately
authorized boot should proceed unattended through U-Boot into Linux. Preserve
the cable/source conditions and capture both delay milestones, EDID/HPD-ready,
first source detection and Linux/projector outcome. Do not interrupt U-Boot.
