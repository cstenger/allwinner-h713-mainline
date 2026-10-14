# HDMI shutdown ordering integration, 2026-10-14

## Latest: real recorder and automatic shutdown handoff passed

`hardware-boot/result.json` records an uninterrupted cold parking-capable boot
with the integrated runtime drop-in active. `hardware-ordering.log` records a
real arecord process(PID869) in RUNNING state and matching consumer MainPID.
Only the capture backend was explicitly stopped. Requires/After propagation
closed the consumer first, then the backend's combined ExecStop verified all22
DSP graph words and15 TVFE clock words/bus, parked MIPS and released/unloaded
the receiver owner. Both services deactivated successfully.

The journal places consumer stop at56.808675s, backend stop beginning56.818110s
and completion61.818989s. No explicit separate park command was needed.
A repeated combined shutdown reported already_parked. Hardware status0306101c
was0; CCU02001600 was00000002 and0200160c was0, matching asserted MIPS resets
and disabled module/bus gates. Linux/SSH remained responsive.

`final-state.log` confirms the terminal state, absent audio/receiver/recorder
and temporary units/drop-ins, and source hashes matching the tested manifest.
WirePlumber was active and firmware path restored. TVFE is off; TVCAP remains
on under the existing boot-retention policy. The original late h713-off hook's
SHA256 remains2397aa576ac49eed1afdf119179e2bee62a7eb5fd53a1ab8ad7fc8868acdb10a.
No persistent install, system poweroff/halt or lamp/fan GPIO action occurred.
A physical cold cycle is required for another firmware/DSP initialization.
Full-system poweroff, persistent installation and suspend remain unvalidated.

## Implementation and earlier fixture checks


The parking-capable cold coordinator now installs a runtime drop-in that
replaces the capture service's ExecStop with the guarded combined `shutdown
--terminal-shutdown` action. That action verifies parking capability before
stopping audio, restores and verifies the audio graph/TVFE state, then invokes
the validated terminal parking and receiver release. A failed stop prevents
parking. Terminal failures remain latched, and a completed shutdown is harmless
to repeat. Default capture-only boots retain their original stop behavior.

Capture consumers must use both `Requires=h713-hdmi-capture.service` and
`After=h713-hdmi-capture.service`. Stopping the backend then propagates to the
consumer and closes it first. The backend is ordered after user@1000.service,
so it stops before the user manager and WirePlumber remains available during
restoration. RequiresMountsFor keeps the /tmp bundle and /run state mounts
available until the backend stops. The optional terminal stop has a60-second
systemd deadline; individual hardware operations retain their existing bounds.

No existing key, standby, hotspot, lamp/fan poweroff hook or persistent unit
configuration was changed. The existing late systemd-shutdown h713-off hook
runs after service teardown. No system poweroff/halt or GPIO action was invoked
by these tests. Suspend is outside this integration. A failed ExecStop reports
failure and retains hardware holds; it does not veto systemd's overall shutdown.

## Validation completed

- `native-session-tests.log`:17 tests, including combined restoration-before-
  parking order, busy/capture-only refusal, failure short-circuiting, terminal
  failure latching and completed shutdown idempotence.
- `native-boot-tests.log`:7 tests, including runtime-only drop-in installation
  exclusively for parking-capable boots and target unit verification before
  service start.
- `systemd-ordering-fixture.log`: target systemd-analyze verify passed for the
  merged real unit/drop-in. The effective ExecStop is the combined shutdown
  action. With hardware commands replaced by recording commands, systemd
  started backend then consumer, stopped consumer then backend, and kept the
  user manager active. All runtime fixtures were removed afterward.
- `parked-idempotence.log`: the actual new CLI reported already_parked on the
  parked board without loading modules or changing the terminal state. Runtime
  test units/drop-ins were absent. The existing h713-off hook hash is recorded.

`tested-files.json` records integration source hashes. Prior hardware evidence
for three-rate capture, verified restoration, terminal parking, TVFE power-off
and owner release is in ../2026-10-14-parked-handoff/. The new combined ExecStop subsequently passed the fresh-board test above.

## Fresh-boot test procedure (completed above)

To repeat on a new boot, physically cold-cycle, stop at U-Boot, then run the
guarded coordinator with --park-capable. Do not reuse the current parked boot.
`check-hardware-ordering.py` starts a bounded real ALSA recorder in an ordered
consumer service, verifies its PCM ownership, then stops only the backend.
The consumer must stop first; the backend must automatically restore audio,
park MIPS and release the receiver. The script checks final state and journal
order and removes runtime units. It does not power off the board.

Actual full-system poweroff transaction, persistent installation and suspend
remain unvalidated. TVCAP remains on under the existing keep-tvcap-on policy.
