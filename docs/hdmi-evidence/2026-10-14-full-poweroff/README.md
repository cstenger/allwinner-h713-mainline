# Full OS poweroff from parked HDMI state, 2026-10-14

One normal `systemctl poweroff` passed. The board started in the terminal state
from the preceding hardware shutdown-ordering test: MIPS parked, audio and
receiver unloaded, restoration verified, Linux running and lamp bl_power0.
The existing /usr/lib/systemd/system-shutdown/h713-off hook was inspected and
left unchanged. It writes lamp bl_power4 on poweroff/halt, switching lamp/fan
off before PSCI halts the CPUs.

Serial recorded network teardown, filesystem sync/unmount, final systemd
poweroff, display RGB fetch quiesce and `reboot: Power down`. SSH returned0.
The bounded serial capture observed90.03seconds after Power down without any
U-Boot/kernel reboot output. It then closed its serial descriptor automatically.
The operator confirmed: “Both off; board stayed off.” Both lamp and fan were
physically off. No force/reboot command, power-rail experiment or persistent
configuration change was used.

A Bluetooth hci0 reset opcode0x0c03 timeout(-110) occurred during shutdown.
Shutdown continued through Power down; it was not a poweroff blocker.

## Records

- `pre-poweroff-state.json`: state read over SSH immediately before the test.
- `serial-poweroff.log`: bounded serial trace, without any serial writes.
- `ssh-poweroff.log`: the single authorized poweroff request.
- `operator-confirmation.json`: physical lamp/fan/stayed-off confirmation.
- `result.json`: completed observation and operator-confirmed outcome.
- `run-poweroff.py`: one-shot test runner; its attempt marker prevents reuse.

## Scope

This validates full OS poweroff and the existing lamp/fan hook from the already
parked/unloaded state. The previous integration test independently validated
real recorder closure, restoration and automatic parking via service stop.
A single poweroff transaction beginning with a live HDMI recorder remains
untested. Persistent installation and suspend remain separate work.

As documented in ../../standby-plan.md, this board's PSCI SYSTEM_OFF halts CPUs;
it does not cut all main rails. The physical result validated here is lamp/fan
off with no restart, not a main-rail cutoff. The board remains off. A physical
cold cycle is required before another managed firmware/DSP initialization.
