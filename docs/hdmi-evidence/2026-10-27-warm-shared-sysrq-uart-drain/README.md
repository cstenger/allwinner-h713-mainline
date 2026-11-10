# SysRq-b acknowledgement drain fix, October 27: offline only

Live preceding attempt reached U-Boot via one GP7-armed SysRq-b, but its UART
acknowledgement was cut at gp7=b immediately before sysrq: Resetting. Runner
stopped under the full-marker guard; no RAM transfer/source. Evidence in
../2026-10-27-warm-shared-gp7-sysrq/.

The generated abrupt trigger previously flushed its Python stream but did not
wait for the tty transmitter. Added termios.tcdrain(f.fileno()) after flush
and before issuing SysRq-b. This targets reset overtaking UART output; it does
not establish that the earlier unrelated capture-loss issue is fixed.

46 offline tests pass. New regression verifies acknowledgement write -> UART
drain -> SysRq-b ordering; removing drain makes it fail (mutation.log contains
the deliberate failing test followed by mutation-caught confirmation).
All UART/reset actions in these tests are mocked. No new board action.

New candidate build/hdmi-warm-shared-gp7-sysrq-drain-2026-10-27 and manifest
pin fixed runner; RAM startup image remains unchanged. Original live trial's
manifest is untouched. No further reset/continuation/transfer was attempted.
Board left held at U-Boot; await explicit approval for any further board step.
