# Receiver-map correction and bounded MIPS pointer trace

The board-B MIPS display firmware census identifies `0x050c0000` as DETN
display noise reduction, `0x05000000` as display composition, and
`0x05040000` as a picture-quality measurement tap. The earlier HDMI notes
misidentified these windows as HDMI RX, PHY, and THDMIRX. The experimental
`h713-thdmirx-init` module's prior writes and its constant read-only samples
therefore say nothing about receiver enable or TMDS lock. Historical raw
measurements remain in place, with correction notices in the related notes.

The module now returns `-EOPNOTSUPP` for `apply=1` before requesting or mapping
the DETN region. It compiled against the installed merged Linux 6.18.38 tree.
The verified no-write module (SHA256
`8643031ae6dd4707d810dd3596f1c98dad99a1a9518c030f7f85a52c2e8878c8`)
replaced the staged `/root/hdmi-diagnostic-merged/h713-thdmirx-init.ko` on the
projector; the former staged binary was renamed `.retired-detn`. On the
running kernel, `insmod ... apply=1` returned “Operation not supported”, the
module remained unloaded, and the kernel logged `refusing writes`. The board
remained reachable. `check-power.sh` labels those historical safe reads DETN.

For source selection, the earlier U-Boot trace showed that the SetSource
adapter received request 3 and returned while the source callback/worker
markers stayed at startup source 1. The firmware's dispatcher loads its
callback object from cached MIPS address `0x8b253578` and returns success
even if that pointer is null. The earlier run did not sample its live value.
The guarded trace now takes one snapshot of that exact pointer at adapter
entry into trace slot `+0x60` before tail-calling the original SetSource
implementation. Existing requested-source, return, callback, and worker
markers are unchanged. The 407 guarded patch words have unique addresses;
the offline relocation audit found the expected 60 trace bases and 73 stores.
`read-comm-trace.py` verifies the new trampolines before reading the slot.

The board's normal `hy200_qz713df_a1_defconfig` produced a FIT image at
`build/uboot-pointer-trace/u-boot-sunxi-with-spl.fit.fit`, 920,169 bytes,
requiring 1,798 sectors. SHA256 of the image is
`87071df67e2a927e3229790a0b3e862968091011690fc5f991392105966ec2d9`;
SHA256 after zero-padding to the sector boundary is
`ce3192fe2f10ad882b69f413038d4c632b9cc3f25450095288034e04e8129920`.
`mkimage -l` recognizes its AArch64 U-Boot, ATF, and board FDT. The first
attempt used the FEL recovery defconfig and was discarded; it lacked the
recovery payload header and is not a boot candidate.

## Bounded device result

With the owner's specific approval, the original 1,798 sectors at the
established U-Boot-proper LBA `0x49ac00` were saved as
`/root/uboot-backup/pre-pointer-trace-20260924.bin`; their SHA256 was
`6395d30973f82d4bb5c5344840520da851f7a72429035e94bad638ec54f69f16`,
matching the previously installed cache-fixed image. Only those sectors were
written, and their read-back SHA256 matched the new padded image above. SPL,
environment, and the merged default kernel were untouched. The new U-Boot
identified itself as `2026.07-rc5-gf62a84dff41f` and booted the merged
kernel. The first cold boot's autoboot countdown was missed, so a controlled
warm reboot stopped at U-Boot; no diagnostic trace had run before that reboot.

One `h713_disp mips-comm-trace 0x34` run authenticated the exact board-B
firmware and installed the guarded trace. Pre-call adapter state was zero with
requested source and callback pointer at the `ffffffff` sentinel. The source
callback/worker markers were `5102`/`5203`, with event 0, new 1, old 0.
One `commcall eaf13de5 chan=0 pid=8b8f275c 3` then received CALL_ACK and
RETURN in 1 ms and fully recycled its CPU_COMM rings. The adapter reached
`5302`, recorded request 3, and captured **non-null callback object
`0x8b8c8378`** from MIPS-cached `0x8b253578`. The CPU_COMM sender, CALL
dispatcher, and RETURN_ACK markers reached `c013`/`e011`/`f003`. A later
read-only snapshot had the same callback/worker stage markers, with event 1,
new `0x8b253e7c`, and old 0; those shared slots do not prove that source 3
was or was not processed. The null-callback-object explanation for the
previous RETURN is no longer supported by this entry snapshot.

After booting the merged kernel, the guard-checked Linux reader found the
trace page and patched instructions intact, with the same final markers.
Read-only ARM snapshots of reserved MIPS RAM showed object vtable
`0x8b1eb594`, slot 3 `0x8b107574` (the statically identified source
callback), object `+0xe0=3`, and requested-source global `0x8b2729ac=3`.
These values support a source-3 state, but ARM can see stale data from the
MIPS cache, and no pre-call `+0xe0` snapshot exists. They do not establish
that the callback ran, the HDMI input was selected, or receiver lock. No
receiver MMIO was accessed. The readable, line-normalized UART excerpt is
[`pointer-trace-uart.log`](hdmi-evidence/2026-09-24-hdmi1-signal/pointer-trace-uart.log);
the [compressed raw byte stream](hdmi-evidence/2026-09-24-hdmi1-signal/pointer-trace-uart.raw.gz)
is retained for exact replay (uncompressed SHA256
`dfdcf3c51751c3a5873239aa310570a0c71d6222d930755dcbc7684504e5e7e6`).

The follow-up dispatcher trace below records the vtable target and source
argument. Source callback/worker invocations and the receiver core and PHY
map still need verification before a live TMDS-lock test.

## Firmware-owned HDMI wrapper addresses

Disassembly of the same SHA256-verified board-B `display.bin` establishes the
HDMI wrapper addresses independently of the peer driver's labels:

- `0x8b13ceac` returns physical `0x06800800`, and nearby setup at
  `0x8b13cebc` accesses `0x06801017`, `0x0680101a`, and `0x06841001`.
- `0x8b13ce70`/`0x8b13ce88` index a four-entry table at `0x8b1f7b98`;
  every entry is physical `0x06840000`. `0x8b13cea0` returns
  `0x06841000`.
- The common accessor at `0x8b180340` checks the physical address, adds
  `0xb5000000`, ORs `0x20000000`, and uses `lbu`. Its write companion at
  `0x8b180394` uses `sb`; `0x8b1803dc` performs masked byte writes. Thus
  the vendor MIPS path uses byte accesses to these physical windows, not
  32-bit ARM MMIO. The address guard beginning at `0x8b1801cc` includes
  the `0x06800000` region.
- `0x8b13eff0` reads a byte at physical `0x0684037a` through that MIPS
  accessor, masks its low nibble, and returns one bit indexed by the port
  argument. The bit's physical meaning is not yet proven; the accessor is a
  bounded candidate for a later MIPS-side receiver-state snapshot.

This proves that the MIPS firmware has accessors for the wrapper and port
state. It does not prove safe access from ARM: the earlier ARM byte read of
`0x068008f1` returned a bus error, and subsequent `0x068008fc` access likely
locked the board. Future wrapper snapshots should run through bounded MIPS
instrumentation after validating the relevant call path. The Synopsys core,
PHY details, and receiver lock registers remain unidentified.
The exact instruction excerpt is in
[`hdmi-wrapper-disassembly.txt`](hdmi-evidence/2026-09-24-hdmi1-signal/hdmi-wrapper-disassembly.txt).

## Dispatcher-target probe

The next guarded U-Boot trace is built offline in
`build/uboot-dispatch-trace/u-boot-sunxi-with-spl.fit.fit` from submodule
commit `a1358432003`. At the exact board-B firmware call site
`0x8b1091d8`, a trampoline preserves the original `a1` delay-slot setup and
virtual-call return path while recording the callback target at trace
`+0x64` and its source argument at `+0x68`. A null object skips the hook and
leaves both slots at `ffffffff`. Startup events may fill the slots, so the
source-3 call is distinguished by whether `+0x68` becomes `3`. The reader
verifies the patched call site and trampoline before interpreting either
value. All 415 guarded patch words match the exact firmware, with unique
addresses; the expected relocation counts are 61 bases and 75 stores.

The normal board configuration produced a 920,169-byte FIT (1,798 sectors),
recognized by `mkimage -l`. Image SHA256 is
`f90a1cede4b29b37860294e2a4edfad9ad1f3f7bb05e9bf7735b8afad74b2a0f`;
sector-padded SHA256 is
`5a7d86438f6bd2098b69886761d9b1e3f2073f0fe158e0745f2e1b804f4120ee`.
With the owner's authorization to continue, the prior U-Boot-proper range was
saved as `/root/uboot-backup/pre-dispatch-trace-20260924.bin` (920,576 bytes;
SHA256 `ce3192fe2f10ad882b69f413038d4c632b9cc3f25450095288034e04e8129920`).
Only the established 1,798 sectors at LBA `0x49ac00` were replaced. Flash
read-back matched the new padded SHA256 above. SPL, environment, and the
installed merged default kernel were untouched.

After a physical power cycle, U-Boot identified itself as
`2026.07-rc5-ga1358432003c` and authenticated the same board-B MIPS firmware.
One `h713_disp mips-comm-trace 0x34` installed the guarded trace. Before the
call, `commtrace` showed the startup virtual callback target `0x8b107574`
with source argument `1`; adapter request and callback-object slots were
still at their sentinels. One
`h713_disp commcall eaf13de5 chan=0 pid=8b8f275c 3` received `CALL_ACK`
and `RETURN` in about 1 ms and recycled the CPU_COMM rings. The immediate
and delayed trace snapshots showed adapter stage `5302`, request `3`,
non-null callback object `0x8b8c8378`, the same virtual target
`0x8b107574`, and dispatcher source argument **`3`**. CPU_COMM stages were
`c013`/`e011`/`f003`. This demonstrates that the source-3 request reached
the virtual callback call site; the successful RPC return indicates that the
call path returned. The source callback/worker stage markers stayed at
`5102`/`5203`, so they still do not establish that the source-3 worker ran or
that HDMI input became active.

`run bootcmd` returned the device to its default merged Linux 6.18.38 kernel.
SSH and Cedrus `/dev/video0` returned. The read-only Linux reader verified
both trace-page canaries and every patched instruction, then independently
read `dispatch_target=8b107574`, `dispatch_source=00000003`, request `3`,
and object `8b8c8378`. No receiver MMIO was accessed, and no capture frame
or TMDS lock was demonstrated. The [readable UART excerpt](hdmi-evidence/2026-09-24-hdmi1-signal/dispatch-trace-uart.log)
and [compressed exact bytes](hdmi-evidence/2026-09-24-hdmi1-signal/dispatch-trace-uart.raw.gz)
preserve the test (uncompressed SHA256
`53f9aa4db0055dab93acfadb21549bfd6853ec1ae2840b744be9e4f351467d99`).
The follow-up below counts callback and source-worker entries for source 3.
The next milestone is a bounded, MIPS-side receiver-state read through the
firmware's byte accessor before interpreting lock or captured pixels.

## Source-3 worker probe

The guarded U-Boot follow-up in submodule commit `320a17f71d4` keeps the
dispatcher trace and adds counters at trace `+0x6c` for callback event-zero
queue attempts with source 3, `+0x70` for source-3 worker dequeues, and
`+0x7c` for completion of the general source-3 transition path. It also
records the worker's previous and new sources at `+0x74/+0x78`. These
filtered slots persist when a later event-1 notification overwrites the
original last-event fields. The callback and worker trampolines replay the
stock instructions and return to the original control flow.

All 446 patch addresses are unique, their pristine words match the exact
board-B firmware, and the relocation audit found the required 61 trace bases
and 80 stores. Capstone decoded every new trampoline instruction and branch
target. Offline Unicorn execution confirmed that startup source 1 and an
unrelated event-1 notification do not increment the counters, while a
source-3 callback, dequeue, and completed transition each increment their
respective counter once. The normal board configuration built a valid FIT at
`build/uboot-source3-worker-trace/u-boot-sunxi-with-spl.fit.fit` (920,169
bytes, 1,798 sectors). Raw SHA256 is
`2ecbfa43cdb9ffc83fcd91ac7347e6136bfcf99a1b2edb5e2b1c0c0cf30bffa1`;
the zero-padded SHA256 is
`47ebcfa6dbfd646b2eab83fc1e5206086a2a1226cb5d840512051cbbf6e9e95d`.

The currently installed U-Boot-proper sectors were saved read-only as
`/root/uboot-backup/pre-source3-worker-trace-20260924.bin` (920,576 bytes,
SHA256 `5a7d86438f6bd2098b69886761d9b1e3f2073f0fe158e0745f2e1b804f4120ee`).
The candidate was staged on the projector at
`/root/u-boot-proper-source3-worker-padded.fit` and its hash matched the
local padded image. With the owner's specific approval, the 1,798 sectors
at the established U-Boot-proper LBA `0x49ac00` were replaced; flash
read-back matched the padded SHA256 above. SPL, environment, and the merged
default kernel were untouched.

After a physical power cycle, U-Boot identified itself as
`2026.07-rc5-ga1358432003c-dirty` (the FIT was built before the submodule
commit) and authenticated the same board-B firmware. One
`h713_disp mips-comm-trace 0x34` run installed the trace. The pre-call
snapshot had all three source-3 counters at zero, old/new sentinels
`ffffffff`, and startup dispatcher source 1. One source-3 CPU_COMM call
received `CALL_ACK` and `RETURN` in about 1 ms and recycled the rings. The
immediate and delayed snapshots both showed **callback event-zero count 1,
worker event-zero count 1, and transition-completion count 1**, with worker
old `0` and new `3`. The dispatcher target was `0x8b107574`, source argument
`3`, and callback object `0x8b8c8378`. Thus the MIPS firmware both queued
and processed the source-3 event and reached the end of its general source
transition path. The old-source value `0` is preserved as observed; it does
not match a simple interpretation of the startup source-1 marker and needs
separate explanation.

`run bootcmd` returned the projector to the merged Linux 6.18.38 default.
SSH and Cedrus `/dev/video0` returned. The Linux reader verified every
selected patch word and both trace-page canaries, then independently read
the same three counters and old/new values. No receiver MMIO was accessed,
and neither TMDS lock nor a capture frame is established. The
[readable UART excerpt](hdmi-evidence/2026-09-24-hdmi1-signal/source3-worker-uart.log)
and [compressed exact bytes](hdmi-evidence/2026-09-24-hdmi1-signal/source3-worker-uart.raw.gz)
preserve the test (uncompressed SHA256
`f4fc0424fa525263178c39d3c0dd94a92fcf64726e005d234c5bfb143153f0f3`).
