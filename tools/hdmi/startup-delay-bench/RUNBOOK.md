# Temporary startup-delay experiment — offline package

This packet is prepared for review, not installed. No live run or next reboot is
authorized by its preparation. Never restart the active signal owner to try it.
The present failed boot `afe48e93-6604-44de-a220-acb9416e8363` is explicitly
excluded even if its owner were later removed.

## Intended change

`delay-2000.conf` replaces only the signal unit's ExecStart with a private wrapper
copy. After capture readiness, read-only baseline checks and the original graph
gate, it waits **at least 2,000 ms on the monotonic clock**, repeats those checks,
then enters the original ownership-marker → DDC claim → signal initialization
sequence. `delay-0.conf` uses the identical checks/logging without the wait.
The checks add some common overhead; compare these matched variants rather than
assuming the uninstrumented production wrapper is an exact 0 ms control.

No EDID, SCP code/layout, kernel module, clock programming, register order, source
selection or shutdown code changes. This is a delay *before* the existing signal
initialization, not a new delay between DDC enable and HPD release. It does not
establish a measured physical HPD-low duration or diagnose a specific race.

The private wrapper requires the manifest's SHA256 embedded at build time;
all 56 production file content/size/mode/uid/gid pins, current capture-session
ownership, receiver/DSP readiness, domain state and absence of diagnostic/signal
owners are checked before/after waiting. Extra signal parameters and alternate
bundles are forbidden with bench options. Checks/logging/clock/sleep errors
abort before the original ownership marks and holds. Later initialization
failure behavior is unchanged and retains holds unless restoration is proved.
The original per-boot attempt latch and service `Restart=no` remain; a successful
explicit stop still has the production latch-removal behavior. Do not reuse the
experiment in the same boot. These checks assume the existing systemd single
service invocation, with no concurrent manual wrapper or module operations.

## Package review and later activation boundary

1. Verify packet SHA256SUMS, AST-PROOF, tests and the original production pins.
   Keep candidate/helper/manifest together. Candidate runtime location would be
   `/usr/lib/h713-hdmi-delay-bench/`; module bundle stays `/usr/lib/h713-hdmi/`.
2. A later explicitly authorized staging step must back up the original unit,
   its drop-ins and their metadata, check unit precedence and confirm the target
   board identity, kernel and 56 pins again. Review this package's pre-signal
   readiness values on that software generation. No installer is included.
3. Stage exactly one sample as a temporary signal service ExecStart drop-in,
   after reviewing the fully merged unit offline. Preserve production ExecStop,
   Requires/After capture, Type=oneshot, RemainAfterExit, Restart=no and 30-second
   timeouts. Do not start/restart the service on the current boot. A persistent
   temporary drop-in is needed across power-off; a /run-only drop-in will vanish.
4. Before a separately authorized boot, arm passive UART and cached host
   connector/EDID observation. Keep source/cable conditions fixed. Record boot
   identity, both delay JSON milestones, original receiver/DSP/EDID-ready logs,
   first video lock, Linux startup and projector behavior. No host detect ioctl,
   reseat, HPD pulse, alternate probe or service recovery during measurement.
5. Verify the actual elapsed wait and that DDC/SCP initialization followed
   completion. A missing milestone, timeout or readiness/pin mismatch invalidates
   the run; do not retry or clear latches. Preserve evidence and holds.
6. Remove the temporary override after the run, restore the prior files and
   metadata, and inspect the merged production unit before another boot. Do not
   stop a live owner merely to revert its files. Preserve normal safe shutdown.
   This removal/staging and any reboot remain separately authorized operations.

Repeat matched 0/2000 ms boot conditions before claiming improvement. A single
success does not qualify a production fix, and a failure does not rule out the
separate DDC-enable-to-HPD interval or the electrical path.

## Reproduction on the workstation

From the repository root, with Python 3 and no hardware:

```
python3 -B tools/hdmi/startup-delay-bench/test_delay_bench.py
python3 -B tools/hdmi/startup-delay-bench/build.py --out /tmp/h713-delay-review
python3 -B /tmp/h713-delay-review/test-hdmi-signal.py
python3 -B tools/hdmi/startup-delay-bench/test_mutations.py
python3 -B tools/hdmi/startup-delay-bench/test_units.py /tmp/h713-delay-review
```

The final command runs the existing wrapper ownership/failure/shutdown tests
against the generated private candidate with bench flags absent. The dedicated
tests exercise explicit bench starts in a temporary filesystem with mocked
module commands, including one real workstation two-second wait. None opens
serial, SSH, /dev/mem, a DRM device or a board sysfs path.
The final unit check uses systemd-analyze verify with generators disabled in an
isolated temporary root, with placeholder dependencies/executable. It validates
syntax and dependency composition; it does not execute the service or qualify
the installed board's merged drop-ins or actual boot timing.
