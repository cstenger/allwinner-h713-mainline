# Delayed HDMI cold-start validation passed

**PASS: one power-off cold start with the unchanged two-second variant.** The
measured wait was **2.021728043 seconds**; the host detected the expected EDID,
the board locked to 1280×720, Linux started normally, and the operator reported
that the desktop appeared after startup as expected.

This follows the [successful delayed warm test](../2026-11-01-startup-delay-boot/README.md).
It is positive evidence for the startup-timing experiment, not yet proof that
the delay causes a repeatable production fix. No matched 0 ms cold run or repeated
cold-start series was performed here.

## Power-off and capture conditions

Fresh read-only checks passed before shutdown. The same wrapper, manifest,
two-second drop-in, production modules, EDID and SCP sequence were retained.
One guarded ordinary `systemctl poweroff` was issued from boot
`7e9e206d-bd7b-493a-b3fe-af69ab3be77f`. UART captured `reboot: Power down` at uptime
601.740591 seconds. There was no reboot request, force option, latch arming or
UART transmission.

The operator confirmed: “Power removed for at least 60 seconds; board still off.”
Both recorders were checked before prompting power-on, with no boot yet observed
and cached HDMI disconnected/empty. The physical supply interval is established
by the operator report, not a software voltage measurement. Requested conditions
were to keep HDMI connected and host settings unchanged. The off interval is a
controlled test condition, not an HDMI timing requirement.

UART then captured exactly one SPL/proper startup and Linux login, without an
intervening kernel restart. Migrated U-Boot loaded its environment from MMC offset
`0x93d80000` successfully. New boot ID: `e6ccc77a-dfb2-411c-a2cf-139c35d4dceb`.

## Delay and HDMI detection

The loaded unit uses the staged `--bench-delay-ms=2000` wrapper with production
ExecStop unchanged. Its journal contains exactly one delay pair and no retry.

| Milestone | Linux uptime, seconds |
| --- | ---: |
| DSP graph verified | 22.419615 |
| Delay start | 22.902980676 |
| Delay complete | 24.924708719 |
| Kernel EDID/HPD ready | 24.967893 |
| Initial signal none | 25.611424 |
| Signal acquiring | 26.079363 |
| Signal locked, 1280×720 | 26.283372 |

These use kernel uptime and monotonic journal payloads, not the board wall clock.
The delay finishes before EDID/HPD readiness. It remains a pre-initialization
wait, not a new interval inside the SCP DDC/HPD sequence.

The cached host recording covers connected → disconnected → connected. During
shutdown it observed disconnected/empty EDID and then disabled output. During
cold startup it observed the 256-byte EDID at **09:07:28.531104 UTC**, followed by
connected/enabled at **09:07:28.781889 UTC**, November 1. Individual attributes are
sampled sequentially; these are cached observations, not physical HPD-edge or
first DDC transaction timestamps.

EDID SHA256 is
`edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`,
matching the unchanged board payload and warm test. Header and both 128-byte
checksums pass. No later disconnect was observed through recorder shutdown at
09:12:54 UTC. The operator independently reported the desktop appearing after
startup. No recovery, reseat, forced detection or display configuration operation
was issued by the agent; no intervention was reported by the operator.

## Linux and continued operation

Linux reports running, multi-user target active and zero failed units. Capture,
signal, ring, speaker and video services are successful with zero restarts. The
session belongs to this boot; signal owner ready, failed N, restored N, recovery
zero. The original startup check passes.

At uptime 272 seconds, video was locked with 14,659 frames produced and 14,656
delivered. At 304 seconds it remained locked with 16,570 produced and 16,565
delivered. Bad guards, rejected frames and invalid AFBD counters stayed zero;
ring overwrites rose from three to five. This checks startup and continued frame
flow, not a separate media-quality/audio stress qualification.

All **56 production file/metadata pins**, **eight protected storage ranges** and
**both installed migration regions** match before and after the run. Staged
runtime/drop-in and backup hashes remain unchanged.

## Recording closure and temporary configuration

Both original host recorders ran through shutdown, the reported off interval and
cold startup. UART had a sole read-only owner, no transmission and no disconnect
or reopen. Cached monitoring had no read errors; maximum heartbeat gap was 5.106
seconds. No GPU ioctl or force-detect operation was used. Both recorders stopped
cleanly and UART is released.

The board is left running with HDMI locked and the desktop visible. The temporary
override remains installed. Remove it and review the production merged unit
before another boot, using the [backup/reversion record](../2026-11-01-startup-delay-stage/README.md),
unless another explicitly planned experiment requires it. No reversion or extra
boot was performed during validation.

Evidence: [result and timing](RESULT.json), [signal journal](signal-journal.txt),
[UART milestones](uart-excerpt.txt), [operator observations](OPERATOR-OBSERVATION.json)
and [recorder closure](RECORDER-STOP.json). Raw recordings, cached EDID, read-only
snapshots, sources and dispatch receipts are checksum-sealed under
`local/recovery/2026-11-01-hdmi-delay-cold-validation/` and its sibling archive.
