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
   - **the `rx` controller window at `0x05000000`** — see "the window we never
     mapped" below. This is the live lead.
   - ~~the **ARISC**~~ — closed, see below.
   - ~~the **wrapper** at `0x0684xxxx`~~ — scanned, see below.
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

## CLOSED: the ARISC does not store EDID

Read the peer's `docs/re/arisc-firmware.md` and `docs/re/edid-protocol.md`
rather than the firmware image, which was the cheaper move and settled it.

There is a full documented ARM↔ARISC protocol — msgbox/rpmsg, BOP frames, a
132-byte `_tagMcuCommParam`, and nine EDID sub-commands (`RequestEDID 0x0315`,
`UpdateEDID 0x0111` in 4x64-byte chunks, `PullHotPlug 0x0211`, ...). It looks
exactly like the answer and is not:

> The ARISC EDID handlers (dispatcher at `0x12490`) all return `status=-3`
> ("imt error") — **hollow by design.** Stock sends EDID sub-commands to ARISC,
> ARISC says no, and the EDID is written via the direct Synopsys path.

So stock's own EDID route is the DMA path, not the coprocessor. **Do not spend
a session on the ARISC for EDID.** The protocol is still worth knowing for HPD
(`PullHotPlug`) and for the receive side (EDID-Ready and EDID-Package
notifications arrive on channel `0xf8`).

Also from there, confirming the HPD register independently: `0x07091014`, three
bits, `0x00` = all ports low, `0x07` = all high, and **ARISC writes it without
raising a GIC IRQ**, which is why hotplug detection never fires.

## The window we never mapped: `rx` at 0x05000000

The peer's DT node maps **three** regions, and every experiment above used only
the third:

```text
"rx"      0x05000000 + 0x10000   HDMI-RX controller
"phy"     0x05040000 + 0x01000   H713 custom PHY
"thdmirx" 0x050c0000 + 0x10000   DDC / EDID-RAM / HDCP
```

This matters because their `controller_enable()` writes the `SNPS_*` registers
— `GLOBAL_TIMER_REF_BASE`, `CMU_CONFIG0`, `DESCRAND_EN_CONTROL`, `CED_CONFIG`,
`DEFRAMER_CONFIG0` — through `rx_base`, **not** through thdmirx. Only the
`THDMIRX_*` names are thdmirx-relative. So the enable sequence approximated
above was writing to the wrong register file, and "SWENABLE sticks and changes
nothing" is exactly what that produces.

`0x05000000` is alive with the TV domains up — scanned, 16 populated blocks,
no hang:

```text
0x05000300  01 01 01 01 ff 3c c1 c1      0x05000400  ef c3 04 ee c5 04 ed c7
0x05000600  02 28 02 02 18 0a 7b 40      0x05000a00  bd bf 62 01 5e 2d 62 01
0x05001000  ff ff ff ff 01 ff 01 03      0x05001500  10 f4 4b 10 f4 4b 80 63
```

Two more details from their node worth copying rather than rediscovering:

- **clocks**: `"bus"` and `"mod"` are BOTH `CLK_BUS_DISP`. Their comment says
  stock vmlinux RE shows H713 has only `bus-disp`, `bus-tvcap` and
  `bus-hdmi-audio` as real TV gates, and supplying `CLK_BUS_DISP` twice
  satisfies the driver's refcount without driving phantom HDMI-TX gates.
- **no `resets` property at all**, deliberately: bus-disp is shared with
  h713-drm / tvtop / decd, and the internal soft-reset is driven via MMIO
  through `GLOBAL_SWRESET_REQUEST` instead.
- **power-domains**: only `pd_tvcap` (index 2). We attach TVFE as well, which
  is harmless but apparently unnecessary.

### Next

Port `controller_enable()` against `rx_base = 0x05000000` and then retry the
EDID write. That is the first attempt that will have been made with the right
register file, and it is the only untried thing left that the peer's working
stack actually does.

## The rx window has a WRITABLE EDID interface

Retrying against `rx_base = 0x05000000` rather than thdmirx immediately behaves
differently. The peer's header carries a second, simpler register set that is
`rx`-relative, not thdmirx-relative:

```text
HDMI_RX_SYS_CTRL     0x000      HDMI_RX_HPD_STATUS   0x040
HDMI_RX_EDID_CTRL    0x050      HDMI_RX_EDID_DATA    0x054
HDMI_RX_DDC_CTRL     0x060      HDMI_RX_DDC_STATUS   0x064
```

All three of the interesting ones **take writes and read them back**, which no
register in the thdmirx DMA bank ever did:

```text
0x05000050 EDID_CTRL  <- 0x000000D0   reads back 0x000000D0
0x05000054 EDID_DATA  <- 0x000000AA   reads back 0x000000AA
0x05000060 DDC_CTRL   <- 0x00000001   reads back 0x00000001
```

The first page of the window is populated (`0x05000000` reads `0xFFFFFFFF`,
and 11 of 12 blocks in the first 0x300 hold data), so this is a live register
file, not a floating one.

**What this does and does not establish.** It establishes that a writable,
EDID-named interface exists in the window the peer's controller init actually
targets — which is more than the thdmirx path ever offered here. It does NOT
establish that this is the working EDID path: a register accepting a write
proves it is backed, not that it is wired to an EDID RAM. The peer's own driver
references these names only once each beyond their `#define`, so they may be
partly aspirational in that tree too.

Also note `0x05000000` reads `0xFFFFFFFF`, which is worth a moment's suspicion
before building on it — that is the classic floating-bus pattern, though the
surrounding structured data argues against it here.

### Next

1. Drive the `EDID_CTRL` / `EDID_DATA` pair as a streaming port the way
   `DMA_CONFIG10/11` was meant to work: set a write-enable in `EDID_CTRL`,
   stream 128 bytes through `EDID_DATA`, clear it. Then read `HPD_STATUS` and
   assert HPD via `SCDC_CONFIG`, and check the source.
2. Verify from the **host** side, never by readback. The peer records that
   their EDID RAM reads back zero on runs where a laptop read the data
   correctly, so a readback check here can only manufacture a false negative.
3. Only then port the full `controller_enable()` `SNPS_*` sequence
   (`GLOBAL_TIMER_REF_BASE 0x0028`, `CMU_CONFIG0 0x0060`,
   `DESCRAND_EN_CONTROL 0x0210`, `CED_CONFIG 0x0760`,
   `DEFRAMER_CONFIG0 0x0270`, `MAINUNIT_0_INT_MASK_N 0x5014`), which is only
   needed for the TMDS path, not for DDC and EDID.

## NEGATIVE: EDID streamed, host still sees nothing — and HPD is why

Streamed the 128-byte EDID through the rx-side port: `SCDC_CONFIG.HPDLOW` set,
`EDID_CTRL = 0xD0` (write-enable | slave 0x50), 128 bytes through `EDID_DATA`,
`EDID_CTRL = 0x50`, `HPDLOW` cleared. Every write landed:

```text
0x05000054 EDID_DATA reads 0x000000C9   the EDID checksum, i.e. the last byte
0x05000064 DDC_STATUS                   0x00080000, unchanged throughout
```

Host GPU afterwards: `card1-HDMI-A-1` still `disconnected`, EDID size 0.

**The important part is why, and it corrects an error in the reasoning above.**
`SCDC_CONFIG.HPDLOW` only *forces HPD low*; clearing it merely stops forcing.
HPD is an output from sink to source, and releasing a force-low is not the same
as driving the pin high. So the source was never going to see this board
whether or not the EDID landed. Every "EDID does not work" result in this
document was measured through an instrument that could not have shown success.

`EDID_DATA` reading back the last byte written is also weak evidence: a
write-through port into a RAM and a plain holding register both do that. It
does not show the bytes reached an EDID RAM.

### So the milestone is blocked on HPD, not on EDID

The only known HPD drive is `0x07091014` — three bits, `0x00` low, `0x07` all
high — which is in the block that hard-locks this board, and which stock drives
from **ARISC firmware**. That is consistent with everything seen: the register
is undescribed by any DT node, our kernel never brings that domain up, and the
peer notes ARISC writes it without raising a GIC IRQ.

**Next, in order:**

1. **Get HPD asserted.** This is the whole milestone now. Find what powers the
   `0x07091000` block — it is the CPUS/ARISC side, so look at R_CCU gates and
   whether the ARISC needs to be out of reset, rather than probing the register
   again. It has already cost one power cycle.
2. Only then re-test EDID. With HPD asserted the host becomes a real
   instrument, and every EDID question above becomes answerable in one boot
   instead of by inference.
3. Do not trust `EDID_DATA` readback either way.
