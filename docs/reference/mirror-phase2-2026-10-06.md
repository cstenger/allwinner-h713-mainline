# WP5 Phase 2: the hardware mirror in the kernel (0166), 2026-10-06

[../mirror-plan.md](../mirror-plan.md). The recipe is from Phase 0 ([mirror-recipe-2026-10-06.md](mirror-recipe-2026-10-06.md)) and Phase 1 ([mirror-phase1-2026-10-06.md](mirror-phase1-2026-10-06.md)). The kernel is patch `0166-drm-h713-mirror-the-panel-in-hardware.patch`, on top of letterbox 0161–0165.

## Interface

| Control | What it does |
| --- | --- |
| `/sys/bus/platform/drivers/sun50i-h713-afbd/5600000.display/mirror_mode` | Installation mode: 0 front, 1 rear (H), 2 rear ceiling (V), 3 ceiling (H+V). Mirrors the whole screen, invisibly to clients. A write re-commits every plane at once (35–61 ms during playback). A write that would make the current state invalid (V with P010 on the plane) fails with `EINVAL` and leaves the mode as it was. |
| `sun50i_h713_afbd.mirror_mode=N` | The mode at probe (kernel command line). |
| plane property `rotation` (both planes) | `rotate-0`, `rotate-180`, `reflect-x`, `reflect-y`. Mirrors that plane's picture inside its rectangle; combined with the installation mode by XOR. |
| debugfs `dri/5600000.display/h713_geometry` | The committed picture in hardware terms (placement, flips); the mirror registers; every window-layer register, live against the model. |

Mapping, as derived in Phase 0 and checked here:

| Flip | Hardware flag | Placement |
| --- | --- | --- |
| H | `hflip = mode_H ^ REFLECT_X` | `dx = REFLECT_X ? 1280−x−w : x` |
| V | `vflip = mode_V ^ REFLECT_Y` | `dy = mode_V ? 720−y−h : y` |

What each route writes:

| Route | V | H |
| --- | --- | --- |
| Video (source 0) | `CTRL[3:2]=2` and comp `+040[3]=0`, inside NR's hold | panel `0x0a0[0]`, plus the recipe's vde −1 (comp `80c/840/858`, proc `+050`, vblend `010/024`) |
| RGB (console, GPU path) | OSD `CTRL` bit 3 | panel `0x0a0[0]`, plus program window `0x0c0` y + 1 |

The panel words are shared, so whichever route owns the mux writes them.

**Availability:** the mirror is available only with the letterbox window layer, on a board that booted unmirrored in AFBD source mode 2. Otherwise the driver logs "hardware mirror: unavailable" and creates no rotation property.

## Gate (all on the final 0166, 15:50 build, cold boot)

- **Headless, `tools/display/mirror-gate.sh`: 20/20 cases, plus the P010-refusal case.**
  - **Cases:** the console in modes 0–3, plus `reflect-x`, `reflect-y`, `rotate-180`, and mode 1 + `reflect-x` (cancels). The video card at native size in modes 0–3; 852x480 at client (0,0) in modes 0–3, with `reflect-x` alone and with mode 1; 1280x536 in modes 0 and 2.
  - **Each case checks:**
    - the mirror registers;
    - debugfs "0 of 42 registers differ from the model";
    - the same 42 registers against `letterbox-recipe.py --mirror/--reflect`, the independent model self-tested against stock;
    - the panel histogram against the same card unmirrored (within 16 px; a lost row moves 1280).
  - **Whether the gate can fail was checked:** it compared 42 of 42 registers in each case, including cases where all 42 move.
- **Mode switching during plane playback:** `h713-play` H.264 720p (plane-native), modes 3, 1, 2, 0. Each switch took 38–61 ms, the fb id kept changing, and the model diff was 0 every time.
- **GPU path:** stock mpv `--vo=gpu` in mode 3. OSD `CTRL` `03001909`, panel H on, window y 23, 486 GPU IRQs in 8 s; restored on mode 0.
- **Operator look:** `tools/display/mirror-look.sh`, video `local/lcd-photos/test_101/IMG_1034.MOV`, on the earlier 0166 build. Orientation and the mirror code paths are unchanged in the final build; only the P010 refusal and the `acquire_ctx` fix were added since.
  - **Console:** modes 1, 2, 3 and `rotate-180` showed left/right, top/bottom, 180° and 180°.
  - **Video:** 852x480 from the top left went to the top right (mirrored), the bottom left (flipped) and the bottom right (180°), as predicted.
- **Warnings and faults:** none in dmesg across all of it.

## Defects found and fixed during the gate

1. **The mode-switch store committed without its acquire context.** `drm_atomic_helper_duplicate_state()` clears it, so every write warned in `drm_atomic_get_plane_state`. The commit itself worked, so the first gate passed anyway. Each warning's backtrace on the serial console made a switch take 300–850 ms; after the fix it takes 35–63 ms.
2. **The 0165 first-frame cover would have overwritten the new overlay-y words.** It assumed the only vblender words in the table were the borders. Fixed before the first build: it now covers `0x000`/`0x004` only.

## P010 under V: refused

AFBD's bottom-up fetch mis-addresses P010. On the glass (look video `test_101`), every line came out rotated by half its width: the right four bars on the left, and the ramp split. NV12 under V is exact (full-histogram difference 26 pixels).

Slot-address shifts were tried with a guarded buffer, `kms-p010-plane-test GUARD=4`, so that no read could leave the allocation. Results, as full-histogram (32 bins) difference against mode 0, and on the glass (`local/lcd-photos/test_102/IMG_1036.MOV`):

| Y / C shift (bytes) | Histogram difference | On the glass |
| --- | --- | --- |
| 0 / 0 (as built) | 4930 | halves swapped |
| −1280 / −1280 | **1548** | correct order; thin magenta line at the bottom edge |
| +1280 / +1280 | 3244 | correct order; bright green line at the top edge |
| −1280 / +1280 | 4304 | — |
| +1280 / −1280 | 3202 | — |

None is clean, so `atomic_check` refuses P010 while V is on. This was the decision agreed before the look.
- `h713-play` already sends 10-bit to the GPU path, which renders onto the RGB plane and mirrors correctly.
- **Follow-up, if 10-bit on the plane under a ceiling mount is ever needed:** start from −1280/−1280. The residual is about one row, at the bottom edge, in chroma.
