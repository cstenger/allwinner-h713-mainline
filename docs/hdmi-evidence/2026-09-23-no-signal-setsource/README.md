# No-signal SetSource(3) control, 2026-09-23

This trial used the private 6.18.38 #5 HDMI diagnostic FIT
(`/root/fits/h713-mips-early-tvcap.fit`, SHA256
`0beecad60219f9216075ff85e0e435a5312dc1e37a11ccc056d6907792f73208`),
not the current default kernel image. U-Boot installed the guarded
`h713_disp mips-comm-trace 0x34` patch. Linux booted with the volatile
`initcall_blacklist=h713_afbd_platform_driver_init` argument. The TVCAP domain,
CPU_COMM callback, receiver power/clock, EDID clock, and safe Synopsys
initialization modules were loaded as in the preceding live-input trial.

The GPU HDMI connector remained `disconnected`. This run did not assert HPD,
load the SCP EDID, or enable video output. The callback-aware daemon completed
every pre-source RPC, including VP initialization, ten callback registrations,
three HDMI port maps, and HPD interval setup. It also received a hot-plug
callback while the host connector was disconnected.

`SetSource(3)` entered the MIPS CPU_COMM handler. The last sampled source
callback marker was `0x5101`, with event 0 and new source 3; the worker marker
was the stale `0x5203` from boot. Approximately 216 ms after that sample,
Linux panicked because PID 1 exited with `0x8b` (SIGSEGV with core bit). The
kernel call trace included `el0_undef`. ARM sampling ended at the panic; it
cannot establish whether the callback returned or the worker advanced in the
unsampled interval. The mechanism of the PID 1 fault is unresolved.

This reproduces the earlier live-input failure without an active HDMI signal.
It narrows the failure to source selection or shared platform state, rather
than signal timing. It does not establish that the physical receiver or its
initialization is irrelevant. The next hardware trial must first identify the
running kernel and reconcile it with the current mainline code. The projector
was unreachable over SSH after the panic when this note was written.

Files: `serial.log` contains the complete captured trace and panic;
`daemon.log` contains the pre-source RPCs and the source-call entry.
