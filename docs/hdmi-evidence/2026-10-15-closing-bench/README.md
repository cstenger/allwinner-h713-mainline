# Closing bench: M1 and late-ready on hardware; clean reboots with the guard, 2026-10-15

**Result: PASS.**

## Faults 1-4 (boot `a094e9d3…`, after an operator power cycle)
`run-signal-fault.sh` used the bench build (`-DH713_SIGNAL_FAULT_INJECTION`,
now with faults 3 and 4) through a runtime drop-in, after stopping the
installed owner cleanly (`bench.log`, `run.log`, `fault*-*.log`):

| Fault | Effect | Result |
|---|---|---|
| 1 | EDID header corrupted after ARM verified it | `data_failed`; undone from **state 3** |
| 2 | Payload's first EDID verify reads the wrong word | Self-restore, readback == originals; undone from **state 2** |
| 3 | Refusal just before SCP release, through the real pre-launch failure path | **M1 on hardware:** the module verified its SRAM restore and unloaded; the wrapper released DDC and reported "refused before SCP release; nothing retained" |
| 4 | Init gives up the ready poll at once | **Late ready on hardware:** the payload became ready after init failed; undone from **state 1** through the full cooperative stop (readback == originals) |

After every fault: neither module was loaded, the receiver had `clients=1`,
the DDC register read `0xFFFFFF3F`, the per-boot latch was kept, and dmesg
had no warnings. Five SCP launches ran on that boot (the installed owner
plus four faults). The production module is unchanged by faults 3 and 4: its
disassembly is identical to the committed build.

## Clean `systemctl reboot` with the hold guard (same boot)
- The signal unit was left `failed` by fault 4 with nothing held, and the
  backend was active.
- `systemctl reboot` (`reboot-verify.log`, `reboot-serial.log`): the backend
  restored 22 DSP and 15 TVFE words, parked MIPS and removed the receiver.
  `systemd-reboot` ran, `reboot.target` was reached, and the log ends at
  "Shutting down". **The guard allowed the reboot.**
- The board came back by itself in about 20 s. U-Boot printed "H713 HDMI
  launch latch set - capture disabled until physical cold cycle" and booted
  the new FIT.
- Linux (boot `e5eb933c…`) has no handoff. Both HDMI units were skipped
  (`ConditionResult=no`) and no HDMI module was loaded.

## `reboot fastboot` with the guard (boot `e5eb933c…`)
- `nvmem-reboot-mode` is bound on the new kernel.
- `reboot fastboot` (`fastboot-serial.log`): the kernel logged "Rebooting
  with argument 'fastboot'" and "Restarting system with command
  'fastboot'". **The guard allowed it.**
- U-Boot did not autoboot. It stopped after "Allwinner mUSB OTG
  (Peripheral)", which is `preboot`'s GP7 dispatch to `fastboot_mode`.
- A Ctrl+C on the console (`fastboot-exit-serial.log`) ended the fastboot
  wait. `preboot` continued with `usb start`, autoboot ran the latched warm
  path, and the board was back in Linux (boot `67a35907…`, HDMI units
  skipped).
- Host USB was not connected, so `fastboot devices` could not be checked.
  Fastboot mode is inferred from the dispatch and the halt.
- Two `md.l` reads sent after the Ctrl+C reached the Linux root console as
  unknown commands, with no effect.

**Board state after the bench:** Linux on the warm path, with capture
disabled by the GP6 latch until the next physical cold cycle.
