# MIPS display recovery plan

This plan recovers the H713 bench kernel first, then brings up the display
coprocessor one dependency at a time. It deliberately separates "the kernel
boots" from "the MIPS firmware starts" and from "ARM/MIPS RPC works." A build
that merely links is not evidence that the shared-memory protocol is safe.

The DDR3 `HY200_QZ713DF_A1` bench board is the only target in scope. Do not
flash these experiments to the untested LPDDR3 projector board.

## Current status (2026-07-27)

The reviewed end state deliberately moves MIPS boot ownership out of Linux:

- the active Linux 6.18.38 series contains 31 patches; Gemini's 910-line
  `sunxi-mipsloader` patch and the later read-only MMIO observer are removed;
- the kernel, modules, both board DTBs, and bench FIT build from a fresh
  extraction;
- NSI, CPU_COMM, TVTOP, DECD, and GE2D remain disabled;
- the compiled bench DTB contains one MIPS object: a no-map reserved-memory
  pool at `0x4b100000+0x0e41000`. It has no MIPS platform device, boot-vector
  property, clock/reset handle, or control-register address;
- the linked kernel has no loader/observer symbols and Linux creates no
  `/dev/mips*` device;
- no display firmware is embedded in the kernel or root filesystem.

The current RAM-only kernel artifact is `build/out/h713-kernel.fit`
(7,701,060 bytes), SHA-256:

```
2791e08e4bc18f5b032829bb98ad869711e22ccbd9b1870b38cd0695cd66b067
```

Its embedded kernel and bench DTB hashes are, respectively:

```
3a5c27c37eabaef514a4a4b43e87d87cd4bca40ee5320aa60f7a74c35fe028e1
23d37712e9822d44152dcb93ef0923f6b382288bdfea85a3cae6ae7397df3ac7
```

U-Boot verified both hashes before the 2026-07-27 bench boot. Linux reached
the Debian root shell and `systemctl is-system-running` reported `running`.
The UART log showed four CPUs, the ext4 root, eMMC, RTC, Panfrost, Cedrus,
AIC8800, serial getty, hotspot, Bluetooth attach, and SSH coming up. The only
MIPS lines in `dmesg` were reserved-memory initialization; `/dev/mips*` did not
exist. This passed the point where the observer-equipped kernel had stopped
responding.

The observer-equipped FIT, SHA-256
`3ee4e49beef8671e3727df319b7f2f1e7c79b0f04b4d16fd417664f2f7a361ce`,
is rejected evidence and must not be reused. Although its driver performed only
a register read, the board stopped responding after Linux clock takeover. The
safety boundary is therefore stronger than "read-only": Linux does not map or
touch the MIPS control registers during this phase.

The factory cold-start sequence is substantially narrower. Reverse engineering
the stock U-Boot
`0a44d54b3683453765fdbda93744eb5510b8d68ce829d1b0481c2cf2844e28f0`
shows that it loads `display.bin` at ARM physical `0x4b100000` and writes that
physical address, not its MIPS KSEG0 alias, to boot-address register
`0x03061030`. It then drives the MIPS clock/reset registers as follows, with
12 ms between reset stages and 300 ms after release:

```
0x02001600 <- 0x80000002
0x0200160c <- 0x00000000
0x0200160c <- 0x00010000
0x0200160c <- 0x00030000
0x0200160c <- 0x00030001
0x03061030 <- 0x4b100000
0x0200160c <- 0x00070001
```

UART-controlled tests established the hardware boundary:

- Writing stock register `0x051c0010 <- 0x01800045` by itself stalled both
  ARM UART and USB ACM. This register belongs to the factory fast-logo/LVDS
  sequence, not the standalone MIPS reset primitive. A power cycle recovered
  the board, and the known-good kernel subsequently booted cleanly.
- Replaying only the MIPS clock/reset sequence remained stable and changed CPU
  status register `0x0306101c` from zero to one. Status one therefore proves
  reset release, not firmware readiness.

Static analysis supplied a separate execution witness. The reset path enters
at the firmware's MIPS BFC vector, executes `eret` to `0x8b1b0868`, and then
clears BSS from MIPS address `0x8b232c00` through `0x8bac7c28`. The firmware's
observed address translation maps these to ARM physical
`0x4b232c00..0x4bac7c28`. Witness address `0x4b600000` is inside that loop but
is the first word beyond the five-megabyte window cleared by U-Boot. The
command writes `0x4d495053` there, flushes that ARM cache line, releases the
MIPS, then invalidates the line before reading it. Only a firmware-owned store
is expected to turn the seed into zero.

The ownership boundary is now explicit: U-Boot proper loads, verifies, and
releases `display.bin` before Linux. SPL remains responsible only for DRAM and
normal boot prerequisites unless a specific clock/interconnect dependency is
later proven to require earlier setup. Linux must not reload or restart the
coprocessor; its eventual role is reserved-memory protection and post-boot IPC
or display management.

A manual U-Boot command implements this boundary without changing autoboot.
`h713_mips load` reads the exact 1,256,216-byte image from a filesystem, clears
the five-megabyte firmware window, and accepts only SHA-256
`16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9`.
Separate `verify`, `start`, `stop`, and `status` operations keep each bench
transition observable. Before reset release, `start` applies only the
bench-proven display PLL/module-clock, TVTOP-routing, and mixer prerequisites.
It deliberately excludes LVDS, PH pinmux, TVCAP, HDMI, and INCAP. `start`
requires both CPU status one and the independent BSS-clear witness; it returns
the core to reset if either check fails.

The first installed and hardware-tested DDR3 bench artifact containing the
execution-witness command was 844,537 bytes, SHA-256:

```
493c45149a84e528f04b4b5861853cbbff43543bbd7048602966aca7d920d1ce
```

The current installed DDR3 build incorporates the proven display prerequisites
and deletes the unsafe experimental `factory-start` path. It also disables the
MIPS clock in `stop` after asserting reset. It is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (844,537 bytes), SHA-256:

```
956a03a61693add8c281f6f2678609e8d427a972b0797a3bd09b22fd8428fef2
```

The command is compiled into U-Boot proper and is absent from SPL as designed.
It is enabled only in the DDR3 bench defconfig, not the projector defconfig,
and it is manual: the normal autoboot path remains unchanged.

Bench execution validated the negative and transition paths:

- uninitialized firmware was rejected and left reset/status zero;
- the known image transferred by YMODEM produced the pinned SHA-256;
- deliberately dirtied bytes beyond the image were cleared before start;
- `start` reproduced the stock staged reset transition and reported status one
  with physical boot address `0x4b100000`;
- on three fresh firmware loads, the BSS witness changed from `0x4d495053` to
  zero while status remained one, independently proving that the MIPS fetched
  and executed its firmware startup code;
- the running firmware modifies bytes in its loaded image. A second `start`
  without restoring a pristine image produced SHA-256
  `6a7a86d23be26a712c6af9671acfd06ed4bcdb1d7216fa89949f6fca3d2bccde`;
  the pinned-image check rejected it and kept the MIPS in reset. Every new run
  must therefore use `load`/`boot` or otherwise restore the pristine image;
- UART and USB ACM remained responsive during all three runs, and `stop`
  returned reset, status, and boot address to zero.

The first post-test Linux handoff stopped producing UART output during driver
bring-up. At that point `stop` had asserted reset but left MIPS clock register
`0x02001600` at `0x80000002`, unlike its cold-boot value of zero. A follow-up
build disabled that clock after asserting reset and was hardware-verified to
return clock, reset, status, and boot address to zero. Linux nevertheless
stopped at the same point after the start/stop cycle. The lingering clock was
therefore not the sole cause. Abruptly resetting active firmware may leave an
outstanding transaction or another display/interconnect register in a state
that reset does not unwind.

Do not treat `stop` after successful execution as a clean Linux handoff. The
intended ownership-model test instead loaded and started the MIPS in U-Boot,
left it running, and booted the protected-memory Linux image. A power cycle
remains the known recovery for a failed post-execution handoff.

The initial live-MIPS handoff reached Linux but stopped deterministically in
the Panfrost probe. Panfrost printed its 864 MHz core and 100 MHz bus clock
rates, then the machine stopped before the next, normally immediate GPU-ID
line. The same boundary occurred after an execute/stop cycle and with the MIPS
left running, so the stop implementation was not the root cause. MIPS startup
needed an earlier display-fabric prerequisite before Linux's first GPU MMIO
access.

A one-boot `modprobe.blacklist=panfrost` isolation test confirmed the boundary:

- the pinned firmware passed its hash and BSS execution witness and remained
  running across the Linux handoff;
- the kernel command line contained the temporary Panfrost blacklist;
- Cedrus, AIC8800, networking, SSH, serial getty, and the Debian root filesystem
  came up;
- `systemctl is-system-running` reported `running` with no failed units;
- Panfrost and DRM scheduler modules were absent, and Linux still created no
  `/dev/mips` device.

The blacklist was transient and was not saved to the U-Boot environment or
kernel image. A normal reboot after the isolation test removed the blacklist,
left the MIPS off, loaded Panfrost, reached `systemd` state `running`, and
reported no failed units.

Register isolation then recovered the missing prerequisite. SPL already leaves
the display bus clock/reset enabled, but the video2 PLL parent and the deint,
panel, SVP-DTL, and AFBD module clocks are gated. The safe pre-start sequence:

```
0x02001050 |= BIT(31)       # video2 PLL parent
0x02001db0 |= BIT(31)       # deint, cold divider preserved
0x02001db4 |= BIT(31)       # panel, cold divider preserved
0x02001db8 |= BIT(31)       # SVP-DTL, cold divider preserved
0x02001dc0 |= BIT(31)       # AFBD, cold divider preserved
0x02001dd8 |= BIT(16)|BIT(0)

0x05700004 <- 0x00000001
0x05700044 <- 0x11111111
0x05700088 <- 0x11111111
0x05700000 <- 0xfff11111
0x05700040 <- 0x00011111
0x05700080 <- 0x00001111
0x05700084 <- 0xfff000ef
0x0525c038 <- 0x00000100
```

With only those writes, the mixer remained readable, the MIPS passed its BSS
execution witness, and Linux booted with Panfrost enabled. Panfrost read GPU ID
`0x7093`, reported one shader and one L2, registered DRM minor zero, and created
`/dev/dri/card0` plus `/dev/dri/renderD128`. Debian reached `running` with zero
failed units. The same handoff passed first as a manual register experiment and
again from the installed cleaned U-Boot implementation.

The broader factory sequence is not safe to carry forward. A diagnostic
`factory-start` path containing PH, TVCAP, HDMI, and LVDS phases wedged after
MIPS release and has been deleted. Direct INCAP access at `0x06940000` wedges
independently even after reconstructing the display and TVCAP clocks and was
also excluded. LVDS registers become ARM-accessible once the display clock tree
is prepared, but no LVDS write is required for the proven Linux handoff, so
they remain out of `h713_mips`.

The specific claim that stock register `0x051c0010 <- 0x01800045` stalls ARM
UART and USB ACM is **withdrawn**. That observation predates
`h713_display_prepare()` and was a clocking artifact, not a property of the
register. Retested on the bench on 2026-07-28 with the MIPS held in reset and
only the prepared clock tree applied by hand:

- the whole LVDS window `0x051c0000..0x051c0057` reads back zero, so the block
  is idle rather than absent;
- `0x051c0010` is readable, and the stock write lands and persists — a
  subsequent read returns `0x01800045`;
- the write is repeatable: two back-to-back writes both completed, and no other
  register in the window changed, so it behaves as a standalone enable rather
  than the entry point of a state machine;
- UART stayed responsive throughout. An observed reset during the first attempt
  was the 16 s watchdog expiring (`wdt start` does not self-service), not a
  stall; re-running the whole sequence inside a single `;`-separated line
  reproduced the writes with no reset.

The cold module-clock dividers were captured in the same session and
independently corroborate the recovered frequencies: `0x02001050` is
`0x08003101` (N=49, 1200 MHz), and deint/panel `0x00000007` (÷8 = 150 MHz) and
SVP-DTL `0x00000005` (÷6 = 200 MHz) match the documented rates. AFBD
`0x00000000` (÷1) implies 1200 MHz, not the 600 MHz recorded earlier; treat the
AFBD figure as unverified. `0x02001dd8` already reads `0x00010001` cold, so
that line of `h713_display_prepare()` is a no-op against the current SPL.

The general lesson is that "this register wedges the interconnect" has meant
"this block was unclocked" every time it has been run down. Apply the same
suspicion to the remaining exclusions — INCAP at `0x06940000` in particular —
before treating them as hardware limits.

## Firmware startup trace (2026-07-28)

`h713_mips probe-trace` instruments the authenticated image with 671 volatile
word patches — code caves plus `j`/`jal` redirection — that store marker ids to
the firmware's uncached `0xae340000` alias, visible to the ARM at
`H713_MIPS_SHMEM_ADDR + H713_MIPS_TRACE_OFF`. Markers are streamed to UART as
they change rather than dumped after the poll loop, because the failure being
chased stalls the interconnect and kills the ARM console; a post-hoc dump
returns nothing in exactly the case that matters.

A marker fires when its call is **entered**, so the last marker reported names
a call that never returned. Relevant sites:

| Marker | Site | Enters |
| --- | --- | --- |
| 17 | `0x4b152cf0` | `0x4b10e770` |
| 18 | `0x4b152cf8` | `0x4b10d40c` |
| 29 | `0x4b10d584` | `0x4b114a8c` |
| 30 | `0x4b10d598` | `0x4b115cec` |
| 31 | `0x4b10d5a4` | `0x4b1140c0` |

Two runs from a hash-verified pristine image differ only in whether the ARM
releases TVCAP when marker 14 appears:

- **Without the TVCAP release** the firmware reaches markers 10-14, 16, 17,
  26-30 and stops. Marker 30's call into `0x4b115cec` never returns. The ARM
  survives the full timeout, `status=1`, the BSS witness is clear, both CPU_COMM
  magics read `deadbeef`, and the ARM flag reads back `0x5` — but MIPS READY is
  never set.
- **With the TVCAP release** markers 18, 19, 20 and 31 additionally fire, and
  then the interconnect stalls and takes ARM's UART with it.

The TVCAP release is therefore a genuine prerequisite, not the fault: it is what
lets `0x4b115cec` return. The wedge lives on the path it unblocks. The firmware
references INCAP `0x06940000` (9 sites), HDMI-RX `0x06840000` (15) and
`0x068c0000` (48), which is consistent with the independent finding that direct
INCAP access wedges even after the display and TVCAP clocks are reconstructed.

The next bisect therefore runs **with** TVCAP released and adds markers beyond
20/31 to find the first capture-block access that stalls the bus. Markers
130-132 (trace slots 148-150) are already installed across the four-registration
group at `0x8b128020` — ids `0x12e`, `0x130`, `3`, `8` — and will report once
execution reaches it.

Treat the earlier note that a run reached the `0x130` registration as
unverified. It predates hash-verified staging and live streaming, and no trace
output was preserved from it.

Do not add MIPS autoboot yet. The next prerequisite is a bounded mailbox/IPC
acknowledgement that proves higher-level firmware readiness; CPU_COMM remains
downstream of that work.

The filesystem `load`/`boot` path is build-tested but has not yet been exercised
against a target filesystem containing `display.bin`. The working way to get a
pristine image into the firmware window is fastboot RAM staging into the
`-l 0x4b100000 -s 0x132b18` buffer, exited with `fastboot continue` — a warm
reset destroys the staged image (see [flash.md](flash.md)). Always confirm with
`h713_mips verify` before any `start`, `probe-ready`, or `probe-trace`. Before installing
U-Boot, the prior one-megabyte LBA-16 region was backed up on the board as
`/root/u-boot-lba16-pre-mips-backup.bin`, SHA-256
`db98d1b15c59349fec96b28ac332e850de932d0bab7786db4a44173db323829e`.

Instruction execution is now independently proven, but higher-level firmware
readiness is not. There is no bounded mailbox/IPC acknowledgement yet, so the
command remains outside autoboot and no Linux IPC/display driver is enabled.

## Safety rules

- Keep a known-good FIT available and preserve UART as the recovery path.
- Do not enable `cpu-comm`, `tvtop`, `decd`, or GE2D in the recovery image.
- Do not map or access the MIPS control registers from Linux until their clock
  and power-domain behavior is independently understood.
- Do not mix unrelated GPU, filesystem, WiFi, or DVFS changes into display
  experiments.
- Treat `display.bin` and vendor image extracts as local-only research inputs.
  Record their hashes, but do not embed workstation-specific paths in defconfig.
- Every patch-series edit must pass a fresh `build/build.sh kernel`; cached or
  previously published artifacts are not proof of the current tree.
- A driver must return an error when its hardware does not become ready. Probe
  success and log messages must not conceal a failed reset/clock/firmware step.

## Milestone 0 — preserve evidence and restore a buildable series

Actions:

1. Keep the experimental GE2D patch and reverse-engineering inputs out of the
   active series while they are reviewed.
2. Repair all malformed or stale new-file hunk counts.
3. Remove the absolute `CONFIG_EXTRA_FIRMWARE_DIR` and rootfs dependency on
   `tmp/`.
4. Restore the bench overlay to its known boot-safe state: reserve the firmware
   DRAM, but expose no MIPS control device to Linux.
5. Revert unrelated GPU IRQ and ext4 `norecovery` changes.

Acceptance:

- `build/build.sh kernel` applies every patch from a clean extraction.
- `Image`, both board DTBs, modules, and the bench FIT are published.
- The bench DTB has no enabled MIPS/display device and contains only the
  no-map firmware DRAM reservation.
- No MIPS/display firmware is compiled into the recovery kernel.

## Milestone 1 — verify the recovery kernel on the bench

Boot the Milestone 0 FIT over the existing safe path before writing it to eMMC.

Acceptance on UART:

- U-Boot hands off to Linux and Debian reaches the normal login target.
- Root ext4 mounts normally, without `norecovery`.
- Fan, UART, eMMC, RTC/reboot-mode, and the existing WiFi fixes show no
  regression.
- Save the complete UART log and FIT SHA-256 as the new display-recovery
  baseline.

## Milestone 2 — U-Boot firmware loader

Keep the operation in U-Boot proper while it needs filesystem access and
SHA-256. Do not place the proprietary firmware in SPL or the U-Boot image.
Keep the command manual until firmware readiness has a bounded independent
witness.

Required behavior:

- hold MIPS reset before modifying its DRAM window;
- accept only the known size and SHA-256 of `display.bin`;
- clear the complete factory five-megabyte load window before copying;
- flush ARM caches before releasing the external processor;
- use the recovered physical boot address and staged reset sequence;
- prepare only the proven display clocks, TVTOP routing, and mixer register;
- exclude LVDS, PH pinmux, TVCAP, HDMI, and INCAP;
- return to reset after a bad hash, short read, or unexpected CPU status;
- print reset status separately from firmware readiness.

Acceptance:

- The command is present only in the DDR3 bench U-Boot proper image and absent
  from SPL and the projector defconfig. **Passed on 2026-07-27.**
- A rejected or missing firmware image leaves CPU status zero. **Passed on
  2026-07-27.**
- The known image produces the expected hash and reset transition without
  disrupting UART, USB ACM, or eMMC. **Passed on 2026-07-27.**
- A second observable witness, such as a firmware-owned memory word or bounded
  IPC acknowledgement, proves instruction execution before autoboot is added.
  **Passed on 2026-07-27:** the cache-coherent BSS-clear witness passed on three
  pristine firmware loads.
- The complete recovery kernel reaches userspace with the MIPS running.
  **Passed on 2026-07-27:** the installed minimal display preparation makes the
  live-MIPS handoff safe with Panfrost enabled; DRM and the render node register
  and Debian reports `running` with zero failed units.
- A bounded firmware mailbox/IPC acknowledgement proves higher-level readiness
  before autoboot or Linux clients are added. **Pending.**

## Milestone 2b — Linux post-boot ownership

Enable only the no-map MIPS firmware reservation. Do not instantiate a Linux
MIPS loader, observer, or management driver. Keep CPU_COMM, TVTOP, DECD, GE2D,
and their extra framebuffers disabled.

Acceptance:

- Linux reaches userspace when U-Boot has not started the MIPS. **Passed on
  2026-07-27.**
- Linux reaches userspace with MIPS running and Panfrost transiently
  blacklisted. **Passed on 2026-07-27; diagnostic configuration only.**
- Linux reaches userspace with MIPS running and Panfrost enabled after U-Boot
  applies the minimal display prerequisites. **Passed on 2026-07-27; installed
  U-Boot and unmodified kernel command line.**
- Linux never loads `display.bin`, rewrites the boot vector, or toggles the
  MIPS reset sequence.
- The compiled DT contains no MIPS control-register address and Linux creates
  no MIPS platform or character device. **Passed on 2026-07-27.**
- `dmesg` reports only the no-map firmware reservation, not a MIPS probe.
  **Passed on 2026-07-27.**

## Milestone 3 — CPU_COMM address model

Do not enable CPU_COMM until its address domains are explicit:

- native kernel virtual addresses use `uintptr_t`/pointers and are never stored
  in protocol `u32` fields;
- shared-memory protocol fields contain 32-bit MIPS-visible physical addresses
  or offsets, converted through checked helpers;
- no helper reconstructs a pointer by OR-ing a fixed arm64 VA prefix;
- kernel-only lists use native `struct list_head` or native-width storage;
- shared structures retain the vendor ABI with compile-time layout assertions.

Add host-side KUnit or equivalent tests for FIFO wrap/full/empty behavior,
physical↔virtual conversion bounds, list insertion/removal, and malformed
shared-memory values.

Acceptance:

- The CPU_COMM objects build without pointer-to-int or int-to-pointer warnings.
- The platform driver is present in the linked image and probes exactly once.
- Invalid shared pointers return errors rather than reaching `BUG()`.
- With MIPS running, ARM and MIPS exchange a bounded ping/ack before any
  synchronous display RPC is attempted.

## Milestone 4 — TVTOP and DECD

Enable TVTOP first, then DECD. Keep GE2D disabled. Define resource ownership so
shared display clocks, resets, IRQs, and overlapping register windows have one
clear owner. Child population must propagate errors and be paired with
depopulation.

Acceptance:

- Both drivers can defer and reprobe without leaked PM, IRQ, clock, reset, or
  character-device state.
- No IRQ is requested non-shared by two active devices.
- CPU_COMM ping/ack remains reliable while TVTOP and DECD probe.

## Milestone 5 — GE2D and visible panel path

Review the GE2D patch as a separate feature series. Probe must not issue
synchronous MIPS RPC until CPU_COMM reports ready, and every RPC result must be
checked. Start with framebuffer/IRQ/backlight side effects disabled, then enable
one at a time.

Acceptance:

- GE2D can probe without changing fan/backlight GPIO state unexpectedly.
- Panel initialization, PWM configuration, and framebuffer scanout are separate
  observable steps.
- The LVDS path produces a stable test pattern before compositor or GPU
  integration begins.

## Artifact organization

After Milestone 0 builds:

- discard one-off top-level `fix_*.py`, `patch_editor.py`, `wait.sh`, and saved
  build stdout/stderr;
- move useful vendor extracts, firmware, disassembly, and analysis scripts under
  ignored `local/mips-display/`;
- keep the inactive GE2D patch in a clearly named local research location until
  it passes review and has reproducible provenance.

Nothing under `local/` is published or force-added to Git.
