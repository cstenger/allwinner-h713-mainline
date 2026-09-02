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

## Next

1. **Find the EDID RAM.** The DDC/EDID path is the milestone; `SCDC_CONFIG`
   already gives HPD, so EDID is the only missing half. Worth scanning the
   THDMIRX window byte-wise for backed regions rather than trusting the peer's
   offset, since that offset is the one thing here that has not held up.
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
