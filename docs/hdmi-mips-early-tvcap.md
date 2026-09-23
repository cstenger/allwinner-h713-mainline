# MIPS continuity with TVCAP retained from boot

On 2026-09-22, private kernel #5 tested whether the MIPS failure at TVCAP
power-on came from the transition or the active domain. Retaining TVCAP from
U-Boot through Linux kept the MIPS scheduler, shell, and CPU_COMM alive.

## Diagnostic image

Patch 0126 adds opt-in `allwinner,keep-tvcap-on` support to the H713 PPU
driver. The private board DT enabled it. `GENPD_FLAG_ALWAYS_ON` prevents
generic power-domain sync from turning off U-Boot's TVCAP state.

- Kernel: Linux 6.18.38 #5 SMP Tue Sep 22 14:02:09 PDT 2026
- FIT: `/root/fits/h713-mips-early-tvcap.fit`
- FIT SHA256: `0beecad60219f9216075ff85e0e435a5312dc1e37a11ccc056d6907792f73208`
- Volatile addition: `initcall_blacklist=h713_afbd_platform_driver_init`
- Normal boot image and persistent environment: unchanged

The flashed U-Boot `h713_disp mips-stability 0x34` command verified the exact
firmware and guarded patch sites. Its 60-second self-test advanced 1007-1008
ticks per second with no general or cache exception. The Linux reader
`tools/mips/read-witness.py` verifies all 34 patch words before reading the
mailbox.

## Retained-domain result

Linux logged `TVCAP domain retained from boot`; genpd reported TVCAP `on`, and
the physical control/status values were `00000001` / `00010000`. Over ten
seconds the ThreadX timer advanced from 169910 to 179911 with no exception.
The MIPS shell returned 917 bytes, and GetSource completed in 74576 us.

Acquiring TVFE and four receiver clock references preserved this state. TVFE
and TVCAP both reported `on`; a 12-second witness advanced continuously, the
shell returned 917 bytes, and GetSource completed in 74961 us. TVCAP can remain
active. Powering it off and back on while MIPS runs is the failing operation.

## Source and MIPS initialization

The validated SCP EDID/DDC trial detected the GPU on its second cold-start
assertion. It read the exact 128-byte EDID (SHA256
`0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290`),
listed two 640x480 modes, and enabled output in 1.653 seconds. Cleanup passed.

`THal_Vp_Init(0, 0, 0x4e700000)` returned `ret0=1` in 74480 us. Stock HDMI
port maps `(1,0)`, `(2,1)`, `(3,2)` and the 200 ms HPD interval completed.
The timer continued and no exception was recorded.

## Live SetSource failure boundary

During a new 30-second signal window, the GPU detected the same EDID and
enabled 640x480. One `THal_Vp_SetSource(3)` call began for HDMI1, but no result
returned. SSH closed; subsequent SSH and ping timed out, and serial produced
no bytes. The last remote output is CALL_BEGIN with component `eaf13de5`.

This is broader than the earlier reversible MIPS-only stall. Target-side
witness and elog files could not be recovered, so the mechanism is unresolved.
Do not repeat live SetSource with only the minimal init calls. A future attempt
should reproduce the full stock HDMI initialization with callback registration
or isolate the remaining prerequisite offline first.

Evidence: [`hdmi-evidence/2026-09-22-early-tvcap`](hdmi-evidence/2026-09-22-early-tvcap/).

## Callback-capable full initialization follow-up

Patch 0127 adds the missing CPU_COMM userspace callback path: per-open-file
104-byte queues with `read`/`poll`, MIPS-to-ARM channel registration, and the
channel metadata required by the normal dispatcher. The updated module built
against kernel #5 and loaded without reinitializing shared memory.

With source selection disabled, `hy310-hdmird` registered all ten callback
routines and completed the full pre-source stock sequence. Every RPC returned,
including `Vp_Init`, callback registration, picture defaults, both WCE window
calls, CVBS pedestal, all three port maps, black-screen disable, ARC setup, and
HPD timing. The driver logged delivery of a hot-plug callback (`comp_id
0x38d780e2`) to the daemon's open file. The witness then advanced for another
three seconds with no exception.

A live 30-second EDID/HPD trial again made the GPU connected and enabled with
the exact 128-byte EDID. The callback-aware daemon repeated the full init and
started its receiver thread. `SetSource(3)` then began but did not return; no
`SignalChange` callback arrived. SSH, ping, and serial all stopped responding.
The SCP trial independently completed with peripheral and SRAM restoration
verified and zero EDID mismatches. Callback delivery is therefore necessary,
but it is not the prerequisite blocking `SetSource`.

The strongest remaining difference from the peer system is controller setup.
The working peer driver programs the Synopsys block at `0x050c0000` before the
same daemon sequence: timer base, CMU margins, descrambler, CED, deframer,
PHY width, interrupt mask, and `GLOBAL_SWENABLE`. Our earlier experiment read
`GLOBAL_SWENABLE=0`, and the SCP EDID path does not program this block. The
opt-in `tools/hdmi/h713-thdmirx-init.c` module now reproduces only that sequence.
It does not access the unsafe `0x068...` wrapper or `0x07091014` HPD register.
It compiled as SHA256
`b1e5c4c62c192dca89ed381b35416ba1a9bf744f053e901a81f24bd86da3e9dc`
and passed its first hardware stability test after a cold boot. It changed
`GLOBAL_SWENABLE` from `0x00000000` to `0x00203901`; the timer, CMU, PHY,
deframer, and CED values latched, while the five-second witness and MIPS shell
remained healthy. The full no-source daemon initialization also passed.

The synchronized follow-up removed that timing ambiguity. The SCP asserted HPD
at target uptime `132.111731`, and the daemon's MIPS callback channel was live
2.606 seconds later with roughly 27 seconds left in the signal window. The GPU
was connected, EDID-complete, and enabled at 640x480. Every pre-source RPC
returned; `SetSource(3)` began and the live hot-plug callback reached userspace.
The source RPC still did not return. Five seconds later CPU_COMM reported no
RETURN for session `0x16`, and SSH, ping, and serial stopped responding.

This places the next experiment in the existing firmware source-worker trace,
not another uninstrumented source switch. `h713_disp mips-comm-trace 0x34`
already marks source callback queueing and worker stages `0x5201` through
`0x5203`; `tools/mips/read-comm-trace.py` verifies those trampolines and streams
mailbox changes without writing firmware or receiver registers.

Evidence: [`hdmi-evidence/2026-09-22-callback-setsource`](hdmi-evidence/2026-09-22-callback-setsource/).
Controller evidence: [`hdmi-evidence/2026-09-22-thdmirx-init`](hdmi-evidence/2026-09-22-thdmirx-init/).
Synchronized evidence: [`hdmi-evidence/2026-09-22-synchronized-setsource`](hdmi-evidence/2026-09-22-synchronized-setsource/).

## Source-worker trace result

The guarded `mips-comm-trace` follow-up localized the failure further. The host
detected the exact EDID and enabled 640x480, all pre-source RPCs returned, and
the hot-plug callback reached userspace. On `SetSource(3)`, the MIPS source
callback recorded `0x5101` with `new=3`. The last captured snapshot still had
that stage; no sample showed `0x5102` or source-worker stage `0x5201`.

About 221 ms after the `0x5101` trace sample, PID 1 exited with status `0x8b`
(SIGSEGV with core-dump bit) and Linux panicked because init died. The trace
makes the MIPS source callback's queue-send path the next place to investigate.
It does not prove that the queue send or worker never advanced after the last
sample, because ARM sampling stopped at the panic.

Trace evidence: [`hdmi-evidence/2026-09-22-mips-comm-trace`](hdmi-evidence/2026-09-22-mips-comm-trace/).

## No-signal source control and kernel identity

The next trial deliberately kept the GPU connector disconnected. It did not
assert HPD or supply an EDID. With the same private 6.18.38 #5 FIT, retained
TVCAP, callback-capable CPU_COMM, and safe receiver initialization, all
pre-source RPCs returned. `SetSource(3)` again reached callback marker `0x5101`
with `new=3`; about 216 ms after that sample, PID 1 exited with `0x8b` and
Linux panicked. The unsampled interval before the panic still prevents a
conclusion about the queue-send return or worker progress. The result does
show that a live HDMI signal was not necessary to reproduce this failure.

This trial explicitly booted `/root/fits/h713-mips-early-tvcap.fit` (SHA256
`0beecad60219f9216075ff85e0e435a5312dc1e37a11ccc056d6907792f73208`).
The project's `build/out/h713-kernel.fit` was rebuilt later, at 2026-09-22
22:41, and the current `h713-display-video-path` patch series ends at 0124,
without the private HDMI 0126 TVCAP retention or 0127 CPU_COMM callback
patches. Therefore these findings apply to private #5, not to whatever image
is currently installed in `boot_a`. The running kernel must be checked after
the projector recovers, before reusing the diagnostic modules or interpreting
another trial.

Control evidence: [`hdmi-evidence/2026-09-23-no-signal-setsource`](hdmi-evidence/2026-09-23-no-signal-setsource/).
