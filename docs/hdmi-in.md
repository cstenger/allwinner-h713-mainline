# H713 HDMI input bring-up

Started 2026-09-02. The projector's HDMI connector is an **input**
(DW-HDMI-RX); there is no HDMI-TX on this SoC. Goal for this round was the
first milestone only: get a source to see this board as a display, which needs
HPD asserted and an EDID it can read.

**Not achieved yet.** What follows is what was established, because most of it
is reusable and two of the results are negatives worth not repeating.

## The gate: TVFE and TVCAP are off at boot

Every HDMI-RX register window is behind the TVFE/TVCAP power domains, and with
them off an access **hard-locks the SoC** — no abort, no watchdog, power cycle
to recover. That cost a power cycle before it was understood.

It was visible for free the whole time, in two places we already drive:

```text
/sys/kernel/debug/pm_genpd/pm_genpd_summary   TVCAP off-0, TVFE off-0
/sys/kernel/debug/clk/clk_summary             bus-tvcap, tvfe-1296m,
                                              bus-cap-300m, vincap-dma,
                                              hdmi-audio, bus-hdmi-audio  en=0
```

**Check both before the first access to any new window.** A read is only safe
when the target block is known to be powered.

Note this contradicts the comment on the `ppu` node in the dtsi, which says all
five domains were verified ON. genpd disagrees at runtime, and genpd is what
governs the access that hangs.

### Do not use the vendor tvtop driver to open the gate

`sunxi-tvtop` owns those clocks, and enabling it is the wrong lever:

- its node claims `GIC_SPI 110`, **the interrupt the KMS display driver owns
  for AFBD** — the same "exactly one may own the block" conflict recorded
  between KMS and DECD;
- it carries `panel_bl_en = <&pio 1 5 ...>`, which is **PB5, the backlight and
  fan enable** that must never be driven low.

Patch 0087 takes the narrow lever instead: attach PPU domains **1 = TVFE** and
**2 = TVCAP**, enable `bus-tvcap` / `bus-cap-300m` / `vincap-dma` /
`tvfe-1296m`, no interrupt and no GPIOs. After it, the HDMI-RX space is
readable and nothing else regresses.

## This block is BYTE-WIDE, and word access lies

The single most expensive misunderstanding of the round. The wrapper at
`0x0680xxxx` ignores 32-bit writes and returns nonsense to 32-bit reads:

```text
mmio-rw  d 6800800 8      ->  all zeros          (word: meaningless)
mmio-rw db 68008f0 4      ->  00 00 29 02        (byte: real)
mmio-rw  w 68008f0 01010101 -> reads back 0x00000000
mmio-rw wb 68008f1 01       -> reads back 0x01
```

`mmio-rw` grew `rb`/`wb`/`db` for this. **Every word-based conclusion about
`0x0680xxxx` taken before that is void**, including a dump that reported
`0x06800800..0x081c` as "all zeros".

The vendor driver touches this whole block with `writeb()` and never `writel()`
— which was the clue, and was in front of us the entire time.

## Map, as far as it is confirmed

| window | state |
| --- | --- |
| `0x050c0000` THDMIRX global | **alive**, structured: `0x70F80029`, `0xFE000115`, `0x03FF00FF` |
| `0x050c0300` `SCDC_CONFIG` | **writable** — HPD control (`HPDLOW` = BIT(1)) works |
| `0x050c4400` DMA / EDID bank | **DEAD** — see below |
| `0x06800800` RX controller | **alive** via byte access; `+0x8f1` port-select, `+0x8fc` PHY reset (`0x33`) |
| `0x06840000` per-port state | **alive**: `0xc0c0c0c0`, `0xcececece`, `0x18181818` — bytes replicated per port |

The peer's offsets like `+0x40202` imply their wrapper base is **`0x06800000`**,
not the `0x06840000` in their `ioremap` call; read that way every one of their
writes lands inside `0x0684xxxx`, which matches their own header comment.

## NEGATIVE: the EDID RAM is not at THDMIRX+0x4424 here

`DMA_CONFIG11` (`0x050c4428`) will not take a write, so no EDID was ever
loaded. This is not a width problem and not any of the obvious causes:

- **byte access** — byte reads of the whole bank are zero, byte writes do not
  stick either;
- **global enable** — the peer's full `SWENABLE = 0x3B01` sticks and changes
  nothing;
- **reset** — `RST_BUS_TVCAP` is CCU `0xd88` BIT(16) and already reads
  `0x00010001`; asserting and clearing `GLOBAL_SWRESET_REQUEST` changes
  nothing;
- **port-select** — `0x068008f1` was `0x00` and now takes `0x01`, no change;
- **wrapper init** — the peer's ten `writeb(0)` registers all applied
  (`0x068400c0` moved `0x02`→`0x00`), no change.

A sparse byte scan across `0x050c4000`–`0x050c5000` is **uniformly zero**,
while `0x050c0000` reads `0x29` in the same breath. That bank is simply not
backed at this address in this configuration.

So either the EDID RAM lives somewhere else on this silicon, or it needs a
clock/enable not yet identified. **Do not re-run the five checks above.**

### The window is only ~0x0d00 bytes backed, and 0x4424 is outside it

Settled by scanning rather than guessing (`tools/display/mmio-scan.c`, byte
reads, 256-byte blocks over the whole 64 KiB):

```text
0x050c0000   50/256 nonzero   29 f8 70 15 01 fe ff ff
0x050c0200  115/256           0c 09 03 03 84 25 ad e5
0x050c0300   47/256           10 ff ff 03 59 48 12 2a
0x050c0400   62/256           01 0f ff 05 01 04 80 4c
0x050c0500   44/256           01 0f ff 05 01 04 80 4c
0x050c0600   46/256           01 0f ff 01 01 04 80 4c
0x050c0700   35/256           5a d3 04 f3 d4 04 f3 d4
0x050c0800   42/256           22 33 01 02 03 01 88 08
0x050c0900   60/256           04 61 08 02 48 50 40 41
0x050c0c00   98/256           0f 9a ff 88 0f 45 ff b0

10 of 256 blocks contain data
```

**Everything from 0x050c0d00 upward is zero**, so `DMA_CONFIG10/11` at
`+0x4424/+0x4428` are simply outside the register file on this silicon. That is
the whole explanation for the dead EDID port, and it also means no amount of
enabling was ever going to help.

`0x0400`, `0x0500` and `0x0600` look alike and are 256 bytes apart, which on a
receiver with three HPD ports invites reading them as three per-port EDID RAMs.
They are not: a full dump of `0x050c0400` has no `00 FF FF FF FF FF FF 00`
header and is sparse register content with a repeating `00 C1 D1 04`. Three
per-port *register* banks, not EDID.

So the peer's EDID path is an **indirect write port** whose control registers
do not exist here. EDID is not served over a DT-described I2C bus either —
neither the dtsi nor the stock DTB mentions `ddc` or `edid` anywhere.

### The wrapper aliases every 0x800, and holds no EDID

`0x06840000` scanned at 0x40 stride: `0x06840000`–`0x068407ff` repeats
byte-identically at `0x06840800`–`0x06840fff`. A **0x800 period**, which is the
per-port aliasing the peer describes, and it means the useful register file is
2 KiB, not the 0x50000 their `ioremap` reserves.

Searching all three confirmed-alive regions for the EDID header signature
`00 ff ff ff ff ff ff 00`:

```text
THDMIRX  (0x050c0000, 0x0d00)   no EDID magic
rx-ctrl  (0x06800000, 0x1000)   no EDID magic
rx-wrap  (0x06840000, 0x1000)   no EDID magic
```

**Read this precisely.** It proves no EDID is *currently resident* in any window
we can reach. It does **not** prove there is no EDID RAM: on stock, firmware
writes the EDID at runtime, so an empty RAM on a boot where nothing writes one
is exactly what an empty RAM would look like. The scan narrows where a
*populated* EDID could be hiding; it does not close the question of where one
should be written.

What it does do is remove the last cheap place to look on the ARM side, which
promotes the ARISC hypothesis from "one of three" to "the one worth the next
session".

## Next

1. **Find the EDID RAM.** `SCDC_CONFIG` already gives HPD, so EDID is the only
   missing half of the milestone. The THDMIRX window is now scanned and ruled
   out, so the candidates left are, in rough order of cheapness:
   - the **ARISC**. Stock handles HPD in ARISC firmware (the peer RE'd its
     handler at `0x121e4`), and the HPD pin register at `0x07091014` is in that
     domain. If HPD is ARISC-owned, EDID plausibly is too — served in software
     over DDC rather than from a hardware RAM. Reading the ARISC firmware is
     free and does not risk the board.
   - ~~the **wrapper** at `0x0684xxxx`~~ — scanned, see below.
   - an **external EEPROM** on the DDC lines, which would make this a board
     question rather than a SoC one.
2. **Do not assert HPD until EDID works.** Advertising a display with no EDID
   behind it is a worse state than being absent.
3. The source must be **connected before power-on** — the peer reports the
   hotplug IRQ never fires on this hardware.

## Architecture note: do not give the MIPS the AFBD block

TMDS decode is MIPS-owned, but scanout need not be. Our KMS driver owns AFBD
and provides the NV12 plane the drmprime mpv path targets; handing AFBD to the
MIPS would remove that plane and force a bespoke client, which is exactly what
the peer had to write — and their picture is broken (4x1 grayscale) precisely
because they do not control the scanout side. Treat the MIPS as a frame
producer writing into a buffer we scan out.
