# Remaining HDMI regression checks — November 2, 2026

**Completed: host reboot PASS; long session PASS; physical reconnect functional
PASS.** The complete pre-unplug session is 3 h 38 min at 59.708 fps with zero
errors. The operator confirmed normal desktop recovery after reconnect; final
startup, 59 file checks and stable video pass on the same board boot.
The recorders expired during the long unplugged interval, so reconnect latency
was not measured. Both temporary recorders are stopped, the heartbeat is
deleted, and the board remains on with HDMI active.
[Final results and limitations](hdmi-evidence/2026-11-02-hdmi-regressions/README.md).
The preparation/phase instructions below are retained as the run history.

**Host reboot PASS; two-hour continuous-input session PASS; physical reconnect pending.**
Host is now boot `c849164e-ed69-4d96-9116-2d6d139302df`; board boot is
unchanged. The operator confirmed normal desktop recovery without reseating
or service intervention. All 59 file checks and startup checks pass, with
zero errors. One automatic re-advertise cycle restored 720p input.
The session passed through board uptime 10667.41: 7,455.39 uninterrupted
seconds at 59.708 fps, zero errors and 59 file checks passing. The periodic
heartbeat was deleted after completion. Await the operator unplug at the host;
record no-source before asking for reconnect. The temporary observer remains
running within its original four-hour bound.
[Results so far](hdmi-evidence/2026-11-02-hdmi-regressions/README.md).

This checks
the installed November 2 HPD re-advertise fix with the board remaining on.
The old host-reboot harness powers the board off and is not used.

## Current run

- Host before reboot: `c7a3a471-30d4-4a44-9112-30bf3fd34729`.
- Board must remain boot `0d1179fa-3f1a-4e65-b3d0-ffabbda024b3`.
- Baseline: 720p lock, expected 256-byte EDID, 59 file checks pass,
  seven HDMI services active without restarts; all sampled error counters zero.
- Temporary recorder: `h713-hdmi-regression-20261102.service` on the board.
  Source and samples are under `/run/h713-hdmi-regression-20261102/`.
  It samples every five seconds, stops after four hours, writes no video,
  accesses no MMIO, and never restarts HDMI services or changes their settings.
- Host evidence: `local/recovery/2026-11-02-hdmi-regressions/`.
  Source: `tools/hdmi/regression-observer.py`; offline analyzer tests:
  `python3 tools/hdmi/test-regression-observer.py`.

## Host reboot

The operator saves host work, leaves the board powered and HDMI connected,
and runs `systemctl reboot` on the host once. After logging back in, resume
this chat with “host rebooted.” Do not use the old harness's board poweroff.
No command whose completion depends on this host session is left on the board;
the observer runs as a detached system transient unit.

On resume:

1. Confirm a new host boot and unchanged board boot. Restore the existing
   `spirits` Wi-Fi connection if necessary (saved UUID
   `1eee0dca-b266-4f1c-a12e-14ed31d555ba`, interface `wlan0`).
2. Read cached host HDMI state/EDID and host journal; collect the board
   observer samples, current startup/file checks and journal. No forced
   detection, service recovery or cable reseat belongs in this test.
3. Require source loss then recovery to 720p, advancing captured frames,
   unchanged owner service start identities, no automatic restarts or errors,
   and a stable recovered interval of at least ten seconds. Record the
   operator's confirmation of the desktop. If failed, preserve evidence.
4. Use `regression-observer.py recovery --input <samples>` for board evidence;
   this does not by itself establish host reboot or visible-picture evidence.

## Long session and reconnect

After host-reboot recovery, mark the first stable recovered sample as the
session start. Observe **two hours of continuous 720p input** on this same board
boot before requesting any physical unplug. `soak --input <samples> --start
<board-uptime> --seconds 7200` requires complete observation, no loss or errors,
unchanged owner services, and at least 50 captured frames/s. If the four-hour
recorder expires before this completes, preserve its evidence and prepare a
separate explicit continuation rather than claiming an unobserved interval.

Once the long session passes, collect a pre-disconnect sample and cached host
monitor baseline. Ask the operator to unplug HDMI at the host, wait for the
recorded no-source state, then reconnect the same cable/port. Keep the board
powered. Time recovery from reconnection, collect at least ten stable seconds
of recovered video, ask for picture confirmation, and rerun startup/files and
error checks. A service restart, forced detect or board reset is a deviation,
not an automatic recovery step.

Finally copy observer logs/journal to the host, stop only the temporary recorder,
and retain raw private evidence plus a public result. Both regression checks
remain unqualified until these steps finish. No regression commit or push has
been requested.
