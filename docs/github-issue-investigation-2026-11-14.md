# well0nez issue investigation — 2026-11-14

Offline source, captured-artifact, and emulator investigation supporting
[the draft replies](github-replies-2026-11-14.md). No board access, firmware
installation, GPIO changes, IRQ requests, DRAM clock changes, or GitHub
comments were performed. Results below distinguish software reproduction
from hardware validation.

Project source reviewed: `10af96af825dfef18b51f22b949f2f204ca9047f` plus the
unchanged relevant files in the working tree. Contributor source reviewed:
`149f51d0df24c45b12674c81aab128b1fc8f5d4b`, retrieved through GitHub's API.

## 1. Main PIO IRQ indexing: reproduced from source

Read the IRQ-bank map from kernel patch 0002 and the actual DT interrupt list
from patch 0024. Apply the lookup expression in patch 0004:

| Bank | Hardware index | IRQ-bank index | Current lookup SPI | Lookup by IRQ-bank index |
| --- | ---: | ---: | ---: | ---: |
| PA | 0 | 0 | 54 | 54 |
| PB | 1 | 1 | 55 | 55 |
| PC | 2 | 2 | 56 | 56 |
| PD | 3 | 3 | 57 | 57 |
| PF | 5 | 4 | 59 | 58 |
| PG | 6 | 5 | 60 | 59 |
| PH | 7 | 6 | 61 | 60 |

This reproduces all three mismatches reported in contributor patches
0143/0144. Our prepared kernel also still contains
`platform_get_irq(pdev, hw_bank)`. The chained handler associated with SPI 60
therefore uses PG's bank index rather than PH's. This corroborates the
reported interrupt-storm mechanism, but no PH17 hardware interrupt was
triggered in this review. Trim the DT only after fixing the lookup: with
seven entries and the old lookup, PH requests nonexistent index 7.

## 2. Msgbox IRQ assignment: independently corroborated in stock capture

`local/stock-boot/sunxi.dts:1561` describes three msgbox windows and interrupts
`<0 0x2e 4 0 0x6d 4 0 0x6c 4>`: SPI **46, 109, 108**. Our kernel patch 0024
still assigns SPI 21 to CPU_COMM. The driver defaults to polling and makes
IRQ mode opt-in, so successful round trips do not validate the DT IRQ.

Contributor follow-up patch
[`0014c`](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0014c-soc-sunxi-cpu-comm-request-only-the-line-of-the-bank-it-owns.patch)
adds an important ownership constraint: ARM receives on bank 0/SPI 46;
requesting bank 1/SPI 109 produced a storm on their HY310. Describing all
hardware lines does not authorize an ARM client to request them all.

One qualification to the original report: our current DTS uses SPI 21 for
S/PDIF, but the saved stock DT's OWA0 at `0x02036000` uses **SPI 23** (`0x17`).
Thus the evidence establishes that CPU_COMM's SPI 21 is wrong; it does not
establish the stock ownership of SPI 21. Correct msgbox IRQ delivery still
needs bench testing, and the wider interrupt table should be audited before
assuming that changing one DT value settles every interrupt conflict.

## 3. USB: parts superseded, parts remain outstanding

Inspected prepared U-Boot source
`build/uboot-src-6c10c952df27bf284889ff3d815b80f7b0201b4cae76af5b37699c901146b0e8`
and the tracked preparation/generation patches. This cache predates patch
0005; that later display patch does not change the USB code inspected here.

- Generated `clk_h713.c` has OHCI clocks and PHY resets at `0xa70`, `0xa78`,
  `0xa80`, including port 2. The reported D1 spacing defect is addressed by
  the current generator/kernel CCU inputs.
- Shared DT includes R_PIO and all six EHCI/OHCI nodes. The historical
  absence-of-nodes report does not describe the prepared tree now.
- H713 binds to `sun20i_d1_cfg`, which already sets
  `.hci_phy_ctl_clear = PHY_CTL_SIDDQ`. The initialization code actually
  clears that mask in each available PMU. Therefore it is incorrect to say
  our current U-Boot never clears SIDDQ.
- That D1 configuration still has `num_phys = 2`. Port-2 clocks and DT nodes
  alone do not make the third PHY available through this driver.
- **Corrected during the subsequent full-repository review on November 14:**
  the `pmu_enable_bit0` field is absent, but an equivalent write is present.
  `sun4i_usb_phy_passby()` includes `SUNXI_ULPI_BYPASS_EN = BIT(0)` in the
  PMU-base mask and is called for host PHY initialization. The missing
  H713-specific field is therefore not, by itself, a functional gap. The
  earlier conclusion based on the absent field was too strong.
- Legacy `board_init()` calls ignoring PB5 GPIO errors still exist, but
  patch 0000 disables `CONFIG_H713_POWERON_LIGHT_FAN` for the DDR3 profile.
  Current display code uses its own PB5 setup. The historical failure is not
  proof that our current bench fan is off; HY260 fan/VBUS behavior still
  requires board-specific verification.

No USB controller was started or cold-boot enumeration tested. U-Boot PR #1
was closed without merge, so these are equivalent or subsequent code paths,
not evidence that the PR was merged wholesale.

## 4. Doorbell: actual firmware dispatcher tested in Unicorn

Firmware input: `local/mips-display/board-b-mips/display.bin`, SHA-256
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
This is the current local research artifact, not the `a79017e5...` image
named in the old issue. Do not conflate their identities.

Disassembled the receive path and dispatcher with Capstone 5.0.7. The FIFO
value enters the callback in `$a0`; `cpu_comm_cb` at `0x8b122678` copies it to
`$s1` without masking. Emulated the actual dispatcher bytes with Unicorn,
using a mapped stack, `$a1 = 2`, and a bounded 200-instruction execution.
Stubbed only logging at `0x8b150948`; stopped on handler entry or function
return, before any shared-memory handler or peripheral access.

| Input `$a0` | Observed destination |
| --- | --- |
| `0` | CALL, `0x8b11f0a4` |
| `1` | RETURN, `0x8b11f360` |
| `2` | CALL_ACK, `0x8b11f61c` |
| `3` | RETURN_ACK, `0x8b11f804` |
| `4` | Return without dispatch |
| `0x00020000` through `0x00020003` | Return without dispatch, all four cases |

This establishes the parser behavior of this exact firmware, not actual
mailbox interrupt delivery or the origin of historical ACKs.

The subsequent repository review found a further qualification in the
contributor's active 0014f patch: vendor TX_IRQ_EN is used as an ISR-managed
level, and the older experiment said to prove the pulse requirement was
confounded by a parked MIPS. Their code retains the pulse pending testing.
Our known-good transport also retains it; the pulse's necessity and the
edge-trigger explanation are not established by the dispatcher emulator.

The contributor's current
[`0014a`](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0014a-soc-sunxi-cpu-comm-der-h713-stand-vom-04-09.patch)
now ends its encoding with `raw = type & 0x3`, and its updated callers pass
`0 /*sender=ARM*/` as the first argument. It already incorporates the bare
type and pulse correction. Our clean local snapshot of their older driver
(`bcf1b2c694302a8723b66e899207cb95e32de9ca`) also passes sender zero at both
remote send sites, despite the packed encoder there. A formal argument named
`cpu` does not show that the runtime argument was 2. Neither snapshot proves
which code produced the issue's historical 19-ACK result; that still needs
the exact build and paired FIFO/shared-ring capture.

## 5. Board memory identity: decoded from captured boot0 bytes

Decoded little-endian words starting at offset `0x38`, rather than relying
only on defconfig comments:

| Captured artifact | SHA-256 | Clock | Type | ZQ | ODT |
| --- | --- | ---: | ---: | --- | --- |
| Board A `bt0-8KiB-exact-32KiB.img` | `f8ac16e44a83869c8fa7193531bc3a8b228235428a99ac426daa0902026c9f0f` | 720 | 7 | `0x003f3ffb` | `0x31` |
| Board B `boot0-board-b-emmc-sector16.bin` | `b769a41514fe784ead77ff59738a88c97588784a5d425f879c84cfd84a39a817` | 624 | 3 | `0x007b7bfb` | `1` |

Board A's source is
`local/h713-lab/analysis/board-a-stock-20260622/boot-map/`; its independent
July 3 DRAM-discovery report records the same hash. The captured values match
the respective LPDDR3 and DDR3 profiles. This is stronger provenance than a
board-name inference, but does not validate our LPDDR3 SPL or establish a
safe higher clock for the bench chips. No 792 MHz test was attempted.

## 6. Environment offset: regression and mutation checks rerun

Ran:

```sh
python3 patches/u-boot/tests/test-mmc-env-offset.py \
  build/uboot-src-6c10c952df27bf284889ff3d815b80f7b0201b4cae76af5b37699c901146b0e8/env/mmc.c \
  --mutations
```

All **13** cases passed. All **nine** source mutations were caught. Restoring
the original narrowing fails high absolute offsets with absent node/property,
redundancy, and the hardware-partition fallback. Existing cold/warm boot and
migration evidence remains the hardware evidence; this review added host
regression results only.

## Follow-up requiring hardware or unavailable historical inputs

1. PH17 interrupt delivery after correcting the PIO lookup and DT list.
2. ARM-owned msgbox SPI 46 delivery, with bank ownership respected and polling
   fallback retained until interrupt handling is verified.
3. Cold-start USB host enumeration, distinguishing the kernel's missing HCI
   SIDDQ clear from U-Boot's existing SIDDQ/ULPI-bypass writes, and reconciling
   the three-PHY configuration with board-correct VBUS/fan control.
4. Exact historical HY310 build/firmware and traces for the 19-ACK question.
5. Full DRAM chip marking before considering a higher bench clock; independent
   HY260 and LPDDR3 bring-up remain separate hardware qualifications.

The focus-motor identity still rests on the contributor's physical-board
observation. AFBD's 720p probe restriction and kernel series comment parsing
are directly visible in source; removing them is an implementation task,
not evidence of validated 1080p output. LLVM 18/19 minimum-version behavior
was not rerun with those older toolchains.
