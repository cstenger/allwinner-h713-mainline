# VP9 and AV1 on the H713: one closed, one identified

**2026-09-24.** Static scouting, no board time beyond read-only sysfs. Asked
whether VP8's success — where the hardware, the kernel driver and the V4L2 uAPI
all existed and only the VA shim was missing — could be repeated for VP9, and
then for AV1.

**VP9 is CLOSED: the silicon is not on this part.**
**AV1 is REAL, is Google's IP, and has no driver anywhere.**

## VP9 — closed, do not re-investigate

The H713 has no VP9 decoder. Allwinner removed the H6's VP9 block and put an
AV1 block in its place.

| | VP9 references in CCU | AV1 references |
| --- | --- | --- |
| H6, `ccu-sun50i-h6.c` | **8** (`vp9_clk`, `bus_vp9_clk`, …) | 0 |
| H713, `ccu-sun50i-h713.c` | **0** | **7** |

Mainline *does* have a VP9 driver for this SoC family —
`drivers/media/platform/verisilicon/sunxi_vpu_hw.c`, compatible
`allwinner,sun50i-h6-vpu-g2`, `.codec = HANTRO_VP9_DECODER`, at `0x01c00000` on
H6 — and it is useless here, because the clocks it binds (`CLK_BUS_VP9`,
`CLK_VP9`, `RST_BUS_VP9`) do not exist on the H713.

That also explains why cedrus advertises no VP9 and has no `cedrus_vp9.c`: not
an unimplemented feature, just absent hardware. **VP9 is software-decode only.**

### The detour worth recording

`libawvp9Hw.so` is in the H713 firmware extract, which looks like evidence of
VP9 hardware and is not. It uses the Hantro **DWL** API (`DWLInit`,
`DWLMapRegisters`, `DWLReadAsicConfig`, `DWLMallocRefFrm`) and opens
**`/dev/hx170`**, the Hantro VPU device node — i.e. it is the H6-era driver for
the block this part no longer has, carried along in a shared Allwinner
codebase. **A vendor library shipping in the firmware is not proof the
corresponding hardware is on the die.** The CCU is the better witness.

## AV1 — real, and it is Google's IP

Two independent sources agree, which is why this is stated as fact rather than
as the peer tree's claim.

**1. The vendor's own device tree** (`local/stock-boot/sunxi.fex`, a genuine
DTB — `d00dfeed` — from the stock boot package, *not* the peer RE tree):

```dts
av1: av1@1c0d000 {
	compatible = "allwinner,sunxi-google-ve";
	reg = <0x0 0x1c0d000 0x0 0x1000  0x0 0x2001000 0x0 0x1000>;
	interrupts = <0x00 0x6b 0x04>;          /* GIC_SPI 107, level high */
	clock-names = "bus_ve", "bus_av1", "av1", "mbus_av1";
	reset-names = "reset_ve", "reset_av1";  /* indices 7, 8 */
	iommus = <0x11 0x05 0x01>;              /* IOMMU master 5 */
	power-domains = <0x12 0x04>;            /* PPU domain 4 */
};
```

**2. The decoder library's own C++ namespace.** `libawav1.so` is built around
`taffel::ctypes::SwRegisters` and `BigSeaRegisters` — Taffel and BigSea being
Google AV1 IP codenames.

The vendor calls it `sunxi-google-ve`. The peer RE tree's "Google Collaboration
Hardware" comment, which was reasonable to distrust, turns out to be right —
though its `av1-decoder@1c0e000` node is still wrong, since `0x1c0e000` is the
VE's own address. **Use `local/stock-boot/sunxi.fex`, not the peer tree, for
anything load-bearing.**

### There is no driver for this anywhere

Nothing in mainline matches `taffel` or `bigsea`. Mainline's only AV1 backend
is `rockchip_vpu981_hw_av1_dec.c`, and it does not fit:

| | register file |
| --- | --- |
| Allwinner/Google AV1 (this SoC) | **292 regs** (1168 B), or 204 (816 B) |
| Rockchip VPU981 AV1 (mainline) | **395 regs** (1580 B), `AV1_DEC_REG(394, …)` |

Mainline reaches register 394; this block's map cannot hold that layout. Not
the same core.

### What the block's register interface looks like

Unusually tractable — better than anything else reverse-engineered in this
project:

- **`AsicFlushRegs` is a flat word-by-word copy** of a shadow array into MMIO,
  with a readback after each write. No command queue, no indirection.
- **The register file is HLS-modelled and bit-accurate**, so the layouts are
  typed rather than guessed:

  | model | width | serialises to |
  | --- | --- | --- |
  | `SwRegisters` | `ac_int<9276>` | `char[1168]` |
  | `BigSeaRegisters` | `ac_int<6474>` | `char[816]` |
  | `BodpSwRegisters` | `ac_int<137>` | `char[32]` |

  `AsicRegisterMapWidth` picks 1168 or 816 at runtime by comparing a core ID
  against **`0xb16c`** — so there are two hardware variants and the ID says
  which this die is.
- **Named mapping functions** decode cleanly: `MapPdecBaseSwRegs`,
  `MapPdecGenSwRegs`, `MapPdecEntropySwRegs`, `MapPdecDimSwRegs`, plus
  `SwRegistersToBigSeaRegisters`. One already decoded — `MapPdecBaseSwRegs`
  writes seven 64-bit reference-buffer base addresses at a 16-byte stride from
  `+0x28`, with a parallel field array from `+0x178`. That is AV1's reference
  model, readable straight out of the disassembly.
- **`libawav1.so` is not stripped.**

### What our tree already has

| piece | status |
| --- | --- |
| `bus_av1` gate | `0x69c` BIT(1) |
| `mbus_av1` gate | `0x804` BIT(4) |
| `RST_BUS_AV1` | `0x69c` BIT(17) |
| AV1 power domain | enumerated by our PPU driver, **live on the board** |
| IOMMU master 5 | supported (patch 0041, seven masters) |
| **`av1` module clock** | **MISSING** |

The power domain is the strongest independent evidence that the block is on
this die. `/sys/kernel/debug/pm_genpd/pm_genpd_summary` reports `AV1  off-0`
alongside `VE`, `TVCAP`, `TVFE` and `GPU` — present, and off only because
nothing claims it.

The reset indices in the stock DT (7 = `reset_ve`, 8 = `reset_av1`) match our
own CCU bindings exactly, which cross-validates the clock driver against the
vendor's.

### The missing module clock, and why it is not the next step

The family puts the VE module clock at `0x690` (same on H616), with the group's
bus gates at `0x69c`, leaving `0x694`/`0x698` as the plausible AV1 and VE3
module clocks. That is a guess and **cannot be confirmed read-only**: a gated
sunxi CCU register reads `0x00000000`, so the only test is writing a gate bit
to a register whose identity is inferred.

It is also probably unnecessary for a first probe. The module clock drives the
decode core; *register access* needs the bus clock, and `bus_av1`, its reset and
the power domain are all already in hand.

## Next step

A minimal probe driver: claim the AV1 power domain, `bus_av1` and `reset_av1`
from a DT node built from the stock description above, read the core ID at
`0x01c0d000`, print it, stop. No decode, no module clock, nothing written to an
unverified register. It answers both open questions at once — whether the block
is alive, and which of the two register-file variants this die carries.

## Method notes, and four traps

- **`objdump` cannot disassemble these libraries** ("architecture UNKNOWN").
  Use `arm-none-eabi-objdump`, and `-M force-thumb` for the Thumb-2 code, which
  is most of it.
- **Android packed relocations** mean `readelf -r` shows no `RELATIVE` entries
  and data vtables read as zeros in the file. Do not conclude a function-pointer
  table is empty; it is filled at load time.
- **`busybox devmem` needs the explicit width argument.** `devmem ADDR` without
  `32` silently returns `0x00000000`, which is indistinguishable from a real
  zero. This cost a wrong conclusion until `0x02001058` (PLL_VE, known
  non-zero) was used as a control. Always read a known-live register first.
- **A gated clock register reads zero.** Absence of a value is not absence of a
  register, and on this SoC the VE clocks read zero whenever cedrus is
  runtime-suspended — which is most of the time.
