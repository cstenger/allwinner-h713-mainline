# The hardware mirror (installation mode): recipe, 2026-10-06

WP5 Phase 0 ([../mirror-plan.md](../mirror-plan.md)). Desk RE of `display.bin`,
the stock capture of 2026-10-01, and read-only checks on the board (kernel
0165). **Nothing was written to display hardware.** The model lives in
`tools/display/letterbox-recipe.py`, alongside the letterbox recipe; its
self-test now also checks the stock mirrored states.

## Result

The stock firmware's installation mode is two independent mechanisms. Both are
reproduced exactly by the model, for all four modes:

| Mode (stock name) | `mirror_mode` | H (panel) | V (fetch) |
| --- | --- | --- | --- |
| Front | 0 | — | — |
| Rear | 1 | yes | — |
| Rear ceiling | 2 | — | yes |
| Front ceiling | 3 | yes | yes |

**H mirror** is the panel's line reversal. It is global: it acts on whatever the selector feeds the panel. It also costs one line, so everything upstream of it starts one line earlier.

| Register | Field | Native | H | Firmware |
| --- | --- | --- | --- | --- |
| lvds `0x051c00a0` | [0] | `80000000` | `80000001` | `PanelWinNode::WriteReg` `0x8b1a5c38`–`5c44` (node+0x10) |
| comp `0x0500080c` | [31:16] fetch y | `001402D0` | `001302D0` | via vde |
| comp `0x05000840` | [15:0] fetch y − 1 | `02D10015` | `02D10014` | via vde |
| comp `0x05000858` | [15:0] out y | `02D00015` | `02D00014` | via vde |
| proc `0x05180050` | [31:16] line-enable start | `001B02D0` | `001A02D0` | via vde (instance 0 only) |
| vblend `0x05200010`, `0x05200024` | [15:0] overlay y | `02D00016` | `02D00015` | via vde; never dumped by stock |

**V mirror** is AFBD's bottom-up fetch. It sits inside NR's geometry group, so it is written within the hold/release bracket. No address, stride or window changes; the picture's position does not move.

| Register | Field | Native | V | Firmware |
| --- | --- | --- | --- | --- |
| AFBD `0x05600010` | [3:2] | `03000013` | `0300001B` (= 2) | `0x8b1a43f0` |
| comp `0x05000040` | [3] | `02090208` | `02090200` (= 0) | `0x8b1a43f0`, source mode 2 |

Both words are shared with state the driver drives for other reasons:
- `0x05600010` is source 0's CTRL, written on every source on/off;
- `0x05000040[25]` is the NR hold bit.

So both are applied read-modify-write. The recipe tool emits them under `"ctl"`, never as whole words in `"regs"`.

## Evidence

**The vde shift (H).**
- `SetWindow` derives `hflag = ((mode & ~2) == 1)` at `0x8b1aa3ec`.
- WCETop's vde function (`0x8b1a8928`) subtracts it (`0x8b1a89a0`–`89b0`). The letterbox reference called this "−1 if interlaced"; it is corrected there.
- `PanelWinNode::CalcWindow` stores the flag at node+0x10 (`0x8b1a537c`), and adds 1 back only to the program window (`0x8b1a546c`). That is why `0x051c00c0` stays `{720, 22}`.

**The border overlays follow vde.**
- `0x8b1a55d8` and `0x8b1a57c0` write vblend `0x00c/0x010` and `0x020/0x024` from the panel node's rectangle at node+0x94..+0xa0 = {x 49, w 1280, y, h 720}.
- Its y (node+0x9c) is stored at `0x8b1a5460`, **before** the program window's +1, so it is vde.
- The elog prints `m_border_overlay_win [49,21]` under H.
- Stock never dumped the vblender, so these two words are the only part of the model taken from the firmware alone.

**The V bits.**
- `SetWindow`'s V flag is `(mode − 2) < 2` (`0x8b1aa548`).
- `NRWinNode::CalcWindow` stores it at node+0x20, and `NRWinNode::WriteReg` flag `0x800` reaches `0x8b1a43f0` through `0x8b1a4dc0` → `0x8b1a4538`.
- For source mode 2 (`comp+030[11:10] = 3`, stock's and ours), `0x8b1a43f0` writes AFBD `[3:2] = v ? 2 : 0` and comp `040[3] = !v`.
- Source mode 1 has the opposite polarity and also changes `030[11:10]` and `040[7]`. We never run in mode 1.

**What is not the mirror.** The stock diff listed 22 H words and 4 V words; only the ones above are written by the firmware.
- Status or readback:
  - comp `0xa0c/aa8/aac`
  - DETN `0x050c0940/950/970`
  - route `0x05140e04/e08/e18`
  - panel `0x154/164/184/198/1a0/1b4`
- **Never write these.** `0x051c0164` read `0x29C` during ordinary letterboxed playback on our board, so it is not a mirror flag.
- `0x05040014` toggles in every stock capture, so it is noise.

**Proc instances 1–3 follow instance 0 in hardware.**
- The firmware addresses only `0x05180000`–`0x050` (`block-map.py`).
- On our board (2026-10-06, kernel 0165, read-only), kmssink centring a 1280x536 picture moved instance 0's `+050` to `00770218` (start 27 + 92, length 536), and `+150/+250/+350` read the identical word.
- So the kernel writes instance 0 only, as letterbox already does.

**The RGB/OSD channel** (our primary plane; stock never used it):
- U-Boot writes `mirror_mode` into `0x05600140[3:2]` (`external/u-boot/arch/arm/mach-sunxi/h713_mips.c:5052`).
- Stock's `ge2d_dev.ko` (`tgd_put_plane_info`) clears [3:2] and sets bit 3 for V on every OSD commit, and never sets an H bit.
- Inferred:
  - bit 3 = V on the OSD channel;
  - the panel bit mirrors the RGB route too (it is after the selector).
- **Untested.** That is WP5 Phase 1's job, together with OSD bit 2.

## Checks run

**Self-test** (`letterbox-recipe.py --live BASELINE --self-test --stock local/h713-lab/stock-capture-20261001/out`):
- passes against both the 2026-10-04 reference baseline and a fresh baseline on kernel 0165 (`local/h713-lab/mirror-phase0-20261006/native-card.txt`; 50/50 recipe registers match the reference);
- covers 48 recipe registers in the stock dumps, over 10 captures (4 in mode 0, 2 in each mirrored mode). Every register in every mode matches;
- the four mutations (no vde shift, shift on proc only, inverted `040[3]`, no panel bit) are each caught: 8, 6, 3 and 2 mismatches;
- our native state equals stock mode 0 on all 9 words the mirror moves.

**One difference between our native state and stock's** is outside the mirror: comp `0x278/0x2b8` bit 31 (stock `E…`, ours `6…`). Neither is a modelled field, and the mirror does not touch them. The self-test reports them as notes.

**Client coordinates.** `letterbox-recipe.py … --mirror MODE --reflect x|y|xy|180` maps a client's rectangle to hardware (`hw_place()`):
- an installation mode mirrors the whole screen, position included;
- a plane reflection mirrors only the picture within its rectangle.

The panel's H moves position *and* content, so x is pre-mirrored only for a plane reflection. AFBD's V moves content only, so y is pre-mirrored only for the installation mode:

```
hflip = mode_H ^ REFLECT_X      dx = REFLECT_X ? 1280 − x − w : x
vflip = mode_V ^ REFLECT_Y      dy = mode_V    ? 720  − y − h : y
```

Example: 852x480 at client (0,0).

| Request | Hardware | Expected on the glass |
| --- | --- | --- |
| rear | (0,0), panel H | at (428,0), mirrored |
| `--reflect x` | (428,0), panel H | at (0,0), mirrored in place |
| rear + reflect x | (428,0), no flips | at (428,0), upright |
| rear ceiling | (0,240), fetch V | at (0,240), flipped |
| ceiling + 180 | (428,240), no flips | at (428,240), upright |

## Open, for Phase 1

1. Does the panel bit mirror the RGB route (selector `0x29000000`)? Or does it need OSD bit 2? Is a row lost on that route, given the RGB route has no vde shift of its own?
2. With V and a height that is not a multiple of 16, do AFBD's padding rows flip into view? The card's magenta padding shows it.
3. Does the V fetch work for P010 (AFBD formats 6/7)?
4. Is the vblender upstream of the panel mirror? This decides whether bars follow a mirrored picture. The model assumes so.
5. When does the panel bit latch: on vsync, or immediately?
