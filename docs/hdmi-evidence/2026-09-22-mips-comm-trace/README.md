# Traced HDMI source-change failure, 2026-09-22

This run used the already-flashed `h713_disp mips-comm-trace 0x34`
instrumentation with private kernel #5. U-Boot accepted the exact
`display.bin` SHA256 and all guarded patch words. Linux then verified all 22
trace trampolines before reading the mailbox. The MIPS monitor shell remained
responsive, TVFE/TVCAP and the receiver clocks were active, CPU_COMM adopted
the live shared region, and the safe Synopsys receiver initialization was
present.

The first post-cold-boot HPD assertion was not detected by the host, matching
the earlier cold-start observation. It completed and restored the peripheral
without issuing `SetSource`. The second assertion made the host NVIDIA
connector connected after 1.369 seconds, returned the exact 128-byte EDID, and
enabled 640x480 after 1.652 seconds.

The callback-aware daemon completed every stock-equivalent RPC before source
selection. The MIPS trace then established this boundary:

- `SetSource(3)` entered the CPU_COMM handler.
- The source callback reached `0x5101` (`callback-event`) with `new=3` and
  `old=0`.
- The last captured snapshot still had callback stage `0x5101`, so the trace
  did not prove that the queue send returned (`0x5102`).
- No captured snapshot showed worker stage `0x5201` (`worker-dequeued`); its
  `0x5203` value was the stale completed boot-time transition.
- About 221 ms after the `0x5101` sample, PID 1 exited with status `0x8b`
  (SIGSEGV with core-dump bit) while the kernel trace included `el0_undef`.
  Linux panicked because init died. The requested ten-second reboot did not
  complete and the board required a physical power cycle.

The last sampled firmware state was in the source callback before the queue
send returned; the host crashed before CPU_COMM's five-second RETURN timeout.
The trace narrows the next investigation to the queue-send path and its
interaction with the live source. Polling stopped at the panic, so later MIPS
progress cannot be ruled out. The contemporaneous PID 1 failure suggests
system-wide corruption but does not identify its cause.

Files:

- `serial-boundary.log`: selected serial lines bracketing the failure.
- `source.json`: host connector transitions.
- `daemon.log`: successful pre-source RPCs and `SetSource(3)` entry.
- `receiver.log`: live power, clock, and safe THDMIRX state.
- `edid-0812e13a13f9d6f8.bin`: exact EDID read by the host.
- `target.log` and `cleanup.log`: expected SSH timeouts after the panic.
- `first-assertion/`: the clean, non-detected first cold-start assertion.
