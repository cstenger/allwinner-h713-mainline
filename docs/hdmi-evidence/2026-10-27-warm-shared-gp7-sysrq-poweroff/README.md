# Approved checked poweroff before SysRq-b trial, October 27

Operator authorized one checked poweroff and instructed leaving the board
unpowered until OPEN. Read-only precheck boot be9e6729-f523-491d-b5d4-d19a643d451f,
uptime 372.31 s; fuser found no serial owner. Sent one orderly poweroff via
the detached runner, not a GP7 arm or reboot. UART confirmed reboot: Power down
at board uptime 387.248290 s; host receipt 2026-10-27 09:01:23 UTC
(October 27 02:01:23 PDT). Reader closed normally. Evidence in events.log,
uart-poweroff.log and host-runner.log. Next: trial reader OPEN, then operator
power/serial/USB disconnect for >=1 minute before serial-first/mains restart.
