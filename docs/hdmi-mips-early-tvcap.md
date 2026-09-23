# MIPS continuity with TVCAP retained from boot

On 2026-09-22, private kernel #5 tested whether the MIPS failure at TVCAP
power-on came from the transition or the active domain. Retaining TVCAP from
U-Boot through Linux kept the MIPS scheduler, shell, and CPU_COMM alive.

## Diagnostic image

Patch 0128 (0126 in private #5) adds opt-in `allwinner,keep-tvcap-on` support to the H713 PPU
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

Patch 0129 (0127 in private #5) adds the missing CPU_COMM userspace callback path: per-open-file
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

After the next physical power cycle, SSH identified the default kernel as
`Linux 6.18.38 #1 SMP Tue Sep 22 22:33:01 PDT 2026` with normal boot arguments.
The DT reports `cstenger,hy200-qz713df-a1` and has no
`allwinner,keep-tvcap-on` property. This confirms the recovered target is
running a different image from private #5. The HDMI branch now includes the
current mainline MPEG-2 changes; its HDMI patches are renumbered 0125–0129
after mainline 0123–0124. Diagnostic patch 0130 opts the QZ713DF_A1 DT into
TVCAP retention for the next private FIT. All six patches applied to the latest
mainline kernel source with zero fuzz. No new source-selection call has been
issued on recovered #1.

## Current-code source-2 control and trace overlap

An updated private FIT built from current mainline plus HDMI patches 0125–0130
booted successfully on the QZ713DF_A1 target. It retained TVCAP, kept the
MIPS shell responsive, completed read-only `GetSource`, and passed the full
callback-aware initialization with source selection disabled. With the GPU
still disconnected, `SetSource(2)` reached callback marker `0x5101` and did
not return. Serial reported a PID 1 segmentation fault and a CPU_COMM
no-RETURN message; SSH and UART then stopped responding. After a physical
power cycle, the installed September 22 #1 kernel booted normally. This
control rules out a fault confined to the source-3 selection.

An audit of the trace placement found a confound: the persistent marker area
at shared `+0x40000` is inside CPU_COMM's SMM heap, whose header begins at
`+0x2ccf0` and whose allocatable data begins around `+0x32000`. Its writes may
corrupt IPC allocations. Actual overlap with a live allocation has not been
measured, so the traced PID 1 failures do not prove that the source callback
or queue is the corruptor. Earlier untraced source-3 stalls remain. Do not
repeat a traced source switch until the mailbox is moved to a verified
non-IPC location.

Current-code evidence: [`hdmi-evidence/2026-09-23-current-kernel-source2`](hdmi-evidence/2026-09-23-current-kernel-source2/).

## Isolated safe-mailbox trace build

The HDMI branch now pins a separate U-Boot worktree that moves only
`mips-comm-trace`'s mailbox to physical `0x4b100e00` (MIPS uncached alias
`0xab100e00`). In the exact board-B `display.bin` (SHA256
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`),
the trace code caves end at firmware `+0xac4`, this `+0xe00..+0xe54` range is
all zero, and exception vectors begin at `+0x1000`. U-Boot checks that the
mailbox and every original patch site are pristine before installation, then
relocates the trace's 58 base loads and 69 stores. The Linux-side reader
checks 22 relocated instructions and the mailbox magic before sampling.
These checks are specific to the exact firmware hash guarded by U-Boot.

The tested U-Boot-proper image is retained as
`build/out/u-boot-proper-safe-trace.bin` (920,169 bytes, SHA256
`8e9ee6f19b6a906c0143d1c55c1be1474ea3b0a5c7353b6f6104cd781c7266ce`).
The original projector U-Boot proper and SPL were backed up read-only to
`build/uboot-proper-before-safe-trace.bin` and
`build/spl-before-safe-trace.bin` (4 MiB and 32 KiB respectively). The device
was initially still running its original boot chain and default September 22
kernel when the image was prepared.

## Safe-mailbox source-2 control

With owner approval, 1,798 sectors of U-Boot proper were written at its
established LBA `0x49ac00`; full read-back matched SHA256
`b437d05ef0c638929b4d158fa2c6730789112ddd401141621a15d426d7007ed5`.
The SPL's SHA256 remained
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
U-Boot booted, authenticated the exact board-B firmware, verified every patch
site, and installed the relocated mailbox at `0x4b100e00`. The one-time
current-code FIT again retained TVCAP, and the Linux reader verified all 22
relocated patch words plus mailbox magic. U-Boot's earlier source-1 transition
was visible as callback `0x5102`, worker `0x5203`; no-source daemon
initialization and all four kernel-matched diagnostic modules completed.

One no-signal `SetSource(2)` still did not return. The final two sampled trace
states show callback `0x5101`, event 0, new source 2; no new `0x5102` or worker
stage was sampled. The existing worker `0x5203`, old source 0, and queue result
0 are from an earlier source-1 event and **cannot** be credited to this
source-2 call. About 97 ms after the first source-2 sample, the `vp_init`
mailbox word unexpectedly changed from `0x7105` to `0x8baa0000`. None of the
five VP-init marker stores can write that value. This may be a runtime writer
or corruption in the apparently zero-filled firmware gap; its ownership is
not established by the static image check. The trace is outside the known
CPU_COMM heap, but is not yet proven free of all runtime uses.

The serial capture contained a CPU_COMM no-RETURN message, then went silent.
The earlier PID 1 SIGSEGV did not recur in this capture, but SSH timed out and
serial SysRq help produced no output. The owner was asked to power-cycle the
projector. No further source switch should run until the `+0xe38` mutation is
explained or the mailbox is placed in a runtime-proven reserved range. The
unsampled interval also leaves open whether the source worker ran after the
last readable trace state.

Evidence: [`hdmi-evidence/2026-09-23-safe-mailbox-source2`](hdmi-evidence/2026-09-23-safe-mailbox-source2/).

## Dedicated trace-page candidate (offline)

The next U-Boot candidate retargets the same 391 guarded patch sites to a
dedicated page at ARM physical `0x4d980000` / MIPS uncached `0xad980000`.
That page is after the declared MIPS framebuffer and 128 KiB decoder buffer,
before U-Boot's temporary logo at `0x4e000000`, and before CPU_COMM at
`0x4e300000`. Diagnostic kernel patch 0131 reserves exactly 4 KiB there with
`no-map`; U-Boot clears the page before installing trace stores and places
canaries at `+0x80` and `+0xffc`. The Linux reader verifies both canaries and
22 patch words before reading, and reports canary changes during a watch.
This removes the known heap and boot-code-gap placements, though exclusive
MIPS runtime ownership still needs a hardware check.

Both images built offline: U-Boot proper at
`build/out/u-boot-proper-dedicated-trace.bin` (SHA256
`55ff1829d193889881e33bcc1b2d1ec919d9adc6d34ca7384de8ace0d05f1c4d`)
and current-code FIT at `build/out/h713-hdmi-trace-page-0131.fit` (SHA256
`558e256534f63a1d5a53a89b9383034220c8c2691253f7ffecb798855a4a0cee`).
The FIT contains the QZ713DF_A1 DTB with `reg = <0x4d980000 0x1000>` and
`no-map`; its kernel-matched CPU_COMM, power, EDID-clock, and receiver modules
were rebuilt under `build/hdmi-diagnostic-0131/`. None of these new candidate
artifacts has been installed or run on the projector. Its cold boot after the
previous stall returned to the normal September 22 kernel, and the flashed
earlier U-Boot proper and original SPL both retain their verified hashes.
