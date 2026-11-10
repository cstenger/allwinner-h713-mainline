# Stock SCP loader recovered offline

2026-09-17. This identifies the stock memory-copy and reset sequence; it does
not establish that running this firmware under our boot chain is safe or that
HDMI capture works.

## Live baseline

The owner connected this workstation's GPU HDMI output to the projector's
HDMI input, and authorized taking the serial interface from Claude if needed.
No process owned `/dev/ttyUSB0` when checked. Opening it at 115200 baud reached
`root@h713-arm64` without terminating a process.

The workstation's `/sys/class/drm/card1-HDMI-A-1/status` reported
`disconnected`, and its EDID file was zero bytes. The projector reported:

- Linux `6.18.38`, built Wed Sep 16 00:16:22 PDT 2026.
- About 2h48m uptime; rootfs `/dev/mmcblk0p26`, `cma=128M`.
- TVFE and TVCAP both `off-0`, with no receiver probe attached.
- `/dev/video0` and `/dev/media0`; `sunxi_cedrus` loaded.

No receiver register reads, power-domain changes, reboots, or flashing were
performed. Serial was closed after each read-only command batch.

## Inputs

Local board-A stock extraction, read without modifying Claude's checkout:

`/home/chris/Projects/h713/local/h713-lab/analysis/board-a-stock-20260622/boot-map/`

The two saved TOC1 images contain identical SCP payloads at offset `0xacc00`,
length `0x2b004` (176132 bytes). This offset differs from the peer's image.
The item records alone did not yield a useful destination: the four words
following offset and length are `0, 3, 0, 0` for every item.

SHA256 of `toc1-12MiB-items/monitor.bin`:

`95596d11aa6d10c0f3c8ef2c0d6fa01446be320c412decc201a5b547d6475ed7`

SHA256 of `toc1-12MiB-items/scp.bin`:

`93adf8a90fb190fc567fafcccbc5959e6514aa8cff6d4a6ed15981f08666dfa1`

## Loader in the stock monitor

AArch64 disassembly, displayed at base `0x48000000`. SCP log strings reference
code at file offsets `0x5c38` and `0x5cb8`; these addresses are disassembly
labels, not a proposal to execute the stock monitor.

The routine at `0x48005cb8` performs:

```c
/* Recovered stock behavior; not a ready-to-run loader. */
memcpy((void *)0x00100000, (void *)0x48100000, 0x23000);
clean_invalidate_dcache(0x00100000, 0x23000);
memcpy((void *)0x48100000, (void *)0x48123000, 0x8000);
clean_invalidate_dcache(0x48100000, 0x8000);
memcpy((void *)0x00104008, (void *)0x48000030, 0x80);
clean_invalidate_dcache(0x00104008, 0x80);
isb();
release_scp_reset();
```

The copy helper at `0x4800a0d4` is a byte-by-byte copy from x1 to x0,
count x2. There is no word-byte swap in that helper. The cache helper at
`0x4800c198` uses `dc civac` over aligned cache lines, then `dsb sy`.

The reset routine at `0x48005c38` reads the 32-bit register `0x07000400`,
clears bit 0 and writes it, then reads it again, sets bit 0 and writes it.
This is **R_CPUCFG itself**, matching our TF-A `SUNXI_R_CPUCFG_BASE`, not
`RST_BUS_R_CPUCFG` at the previously investigated R_CCU register.

The key copy arguments appear directly in instructions:

```text
48005cbc mov  x2, #0x3000
48005cc0 movk x2, #2, lsl #16       // length 0x23000
48005cc4 mov  x1, #0x48100000       // source staging area
48005ccc mov  x0, #0x100000         // SRAM destination
48005cd8 bl   #0x4800a0d4
48005cec mov  x1, #0x3000
48005cf0 mov  x2, #0x8000
48005cf4 movk x1, #0x4812, lsl #16  // source 0x48123000
48005cf8 mov  x0, #0x48100000       // DRAM destination
48005cfc bl   #0x4800a0d4
```

## What this settles

The loader uses **both SRAM A1 and A2**, followed by a separate DRAM segment.
Our TF-A map declares A1 `0x00100000 + 0x4000` and A2
`0x00104000 + 0x20000`: combined `0x24000` bytes. The stock `0x23000` copy
fits that combined region. The whole firmware was never supposed to fit A2
alone. Its two copied segments total `0x2b000`; the trailing four file bytes
are not copied by this routine. Their meaning is still unverified.

Our H713 TF-A uses `SUNXI_BL31_IN_DRAM=1`, BL31 at `0x40000000`, and explicitly
disables SCPI PSCI. Stock's SRAM copy would overwrite leftover SPL data;
it does not overlap the configured BL31 location. This is a useful check,
not permission to overwrite SRAM from a running kernel.

## Remaining checks before a loader experiment

Trace the caller to verify how the SCP input reaches `0x48100000` and whether
it is transformed beforehand. Recover all 128 startup-parameter bytes and
how stock fills them, including memory/clock/power settings. Compare board-A
and the test projector's firmware before selecting a blob.

Verify the firmware's address assumptions and reserve its DRAM region against
U-Boot allocations and the Linux page allocator. Check SRAM ownership and
mailbox initialization, then reconcile stock's SCP power-management behavior
with native PSCI. These checks are necessary before choosing the boot stage
and implementing a loader.

Once startup is demonstrated in an isolated test boot, validate the actual
HPD command path, then measure source-side detection and EDID using the
connected GPU. TMDS lock and captured frame buffers follow that milestone.

## Later experimental refinement

The first 0x4000 bytes behave as sparse vector stubs in the tested ARM view,
not ordinary writable instruction RAM. A tiny program in A2 passed, then a
SCP-side HPD read timed out. See [the bounded probe results](hdmi-scp-probe-validation.md).
The stock split-copy sequence remains valid disassembly; the earlier A1/A2
size arithmetic does not establish ordinary RAM semantics for every byte.
