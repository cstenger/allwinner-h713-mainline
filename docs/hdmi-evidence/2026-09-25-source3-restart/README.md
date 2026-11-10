# Source-3 restart on the merged kernel

The projector began from a physical cold power-on, already booted into its
default merged Linux 6.18.38 (`#1 Thu Sep 24 01:45:24 PDT 2026`). The MIPS core
was parked. A warm reboot stopped at the installed diagnostic U-Boot prompt;
one authenticated `mips-comm-trace 0x34` launch and one
`THal_Vp_SetSource(3)` call completed. `commtrace` reported one source-3
callback, one worker event, and one completed transition, with the worker's
new source equal to 3. The unchanged default kernel then booted, and its
read-only guarded trace reader reconfirmed the transition and intact canaries.

Persistent modules under `/root/hdmi-diagnostic-merged/` matched the running
kernel. TVFE and TVCAP were held active with zero additional clocks, then the
four known receiver clocks were enabled one at a time. The MIPS shell answered
`help win` after each step. The EDID clock was held. No receiver register was
accessed directly from ARM and nothing was flashed.

The first 15-second SCP HPD/EDID window did not cause the GPU to connect;
see `first-miss/`. In the second, the GPU read the same 128-byte EDID
(`0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290`),
connected at 2.22 seconds, and enabled 640x480 output at 2.51 seconds. During
that window the read-only firmware port cache changed HDMI1 from state 3 to
state 5 and reported 640 horizontal by 480 vertical active pixels. It returned
to state 3 with zero active dimensions afterward. See `second-connected/`.
Both trials reported restored SCP peripheral state and zero EDID mismatch.
The trial tool released the DDC pins. MIPS and Linux remained responsive.

`tools/hdmi/prepare-source3.py` now makes the known-good setup repeatable. It
checks whether MIPS is parked or already alive, only launches it when parked,
validates the source-3 trace before proceeding, stages the persisted modules,
and checks MIPS after every clock step. `--postboot-only` was run successfully
against this live board. The script fails closed on an unexpected MIPS state or
trace result. It does not locate a pixel buffer or register a capture node;
the next work remains identifying the DMA destination, stride, format, and
frame-completion signal in the exact board-B firmware.
