# VP9 on the H713 VE: the register interface

**Status: DONE -- driven by patch 0143, bit-exact against libvpx (2026-09-29).** This reverses
the "VP9 is CLOSED" verdict in `vp9-av1-codec-scouting-2026-09-24.md`.

## Why the old verdict was wrong

Stock Android decodes VP9 **in hardware on the VE**: during VP9 playback the VE
interrupt (SPI 75, `cedar_dev`) ticks ~31.9/s, `0x0200169c = 0x00050005`
(bus_ve, bus_ve3, both resets), MBUS bit 1 (`mbus_ve3`), and `VE_CTRL =
0xC0130007` -- engine mode **7**. The library doing it is
**`libawvp9HwAL.so`**, VE-native. The earlier scouting looked at
`libawvp9Hw.so`, which is the H6-era Hantro DWL build and really is dead here;
both ship in the firmware. The CCU lacking the H6 VP9 clocks proved only that
the *Hantro* block is gone, not that VP9 is.

## Tools (under `tools/re/`; the vendor binaries stay in `local/h713-lab/ve-extract/libs/`)

| tool | what it is |
| --- | --- |
| `awemu.py` | Unicorn loader for stripped Android ARM32 libs: APS2 + RELR relocations, PLT-to-self calls, nested MiniDebugInfo symbols, VFP enabled, fake MMIO windows with a write trace |
| `vp9/fieldmap.py` | differential field map: runs each register setter, perturbs one context field at a time (auto-discovering data and function pointers), reports which register bits move |
| `ghidra/DecompileAll.java`, `DecompileAt.java` | headless Ghidra: every function to one `.c` |
| `extract-debugdata.py`, `annotate-plt.py`, `vp9hdr.py` (frame refs/refresh from an IVF) | MiniDebugInfo symtab; PLT names in an objdump listing |

`vp9/regmap-named.txt` is the register map. Decompiles and run outputs are
regenerated into `local/h713-lab/analysis/` (not tracked).

**The library exports every register shadow under a name carrying its offset**
(`vp9_func_ctrl_reg30`, `vp9_curframe_Ybuffer_reg90`, `vecore_*` for VE top),
so the register *map* came for free; the emulator recovers the *packing*; the
Ghidra decompile of the header parser names the *fields*.

## Register block

`getRegBase(ve, 5)` -- the group the vendor also uses for H.265: **VE+0x500**.
Offsets below are relative to it.

Addresses: **`reg = (phys >> 10) << 2`** (i.e. `phys >> 8`, 1 KiB aligned).

| off | name | content |
| --- | --- | --- |
| 0x04 | hdr_syn | see below |
| 0x08 | pic_size | `[13:0]` width, `[29:16]` height |
| 0x0c/10/14 | last/golden/altref pic size | same packing, from each ref's size |
| 0x18..0x2c | {last,golden,altref} scale0/scale1 | scale factors (x/y step, 14-bit ratios) |
| 0x30 | func_ctrl | `[2:0]`=7 IRQ enables; `|0x200` secondary output on; bit31 set when aligned width in 129..192 and height > 64 |
| 0x34 | trigger | write **7**, then **8** |
| 0x38 | status | bits 0..2 = finish/error/..., write-1-to-clear; bit 19 (`<<0xc` sign test) = bitstream DMA busy |
| 0x40/44/48/4c | bits base/offset/len/end | as H.265 |
| 0x50/54/58 | secondary output ctrl / Y / C | |
| 0x5c | segment_feature | per-segment 2-bit feature-enable pairs `[17:16]..[31:30]` |
| 0x60 | neighbor info addr | 0x1f4000-byte buffer |
| 0x64 | "entry point offset" addr | the 0x88000 prob/count/seg buffer: probs `+0` (0xc57 B), **counts `+0x4b00` (0x3398 B)**, segment ids `+0x8000` |
| 0x68/6c | first tile start/end | SB64 units, `[8:0]` col, `[24:16]` row, bit31 = single tile |
| 0x78 | col_mv addr | current frame's MV buffer |
| 0x84/0x8c | 10-bit first-output offset / config | |
| 0x90/94 | current frame Y/C | |
| 0x98/9c, a0/a4, a8/7c(!) | last, golden, altref Y/C | altref **C is at 0x7c**, not 0xac |
| 0xe0/e4 | SRAM port offset/data | offset 0: 8 words Y dequant + 8 words UV dequant per segment; offset 0x100: loop-filter level table, 2 words per segment (8 segs x 4 refs x 2 modes, 6-bit) |

### hdr_syn (0x04)

| bits | field (decoder-context offset) |
| --- | --- |
| 0 | more than one tile (`1<<log2_tile_cols<<log2_tile_rows > 1`) |
| 1 | inter frame (neither key nor intra-only) |
| 4:2 | bit depth, low 3 bits (8->0, 10->2) |
| 5,6,7 | ref_frame_sign_bias last/golden/altref |
| 8 | allow_high_precision_mv |
| 11:9 | interp_filter (4 = switchable) |
| 12 | filter_level != 0 && mode_ref_delta_enabled |
| 15:13 | sharpness |
| 16 | lossless |
| 17,18,19 | segmentation enabled / update_map / temporal_update |
| 22:20 | tx_mode |
| 24:23 | reference_mode |
| 25 | (ctx+0x1b4, TBD) |
| 26 | always 1 |
| 27 | !frame_parallel_decoding_mode |
| 31 | always 1 |

## Decoder-context fields (from the Ghidra decompile of the header parser)

`0x100/0x104` width/height · `0x178` profile low bit · `0x17c` profile ·
`0x180` bit depth · `0x188` key frame · `0x18c` intra_only · `0x198` show_frame ·
`0x1a0` show_existing_frame · `0x1ac` error_resilient · `0x1b0`
refresh_frame_flags · `0x1bc/0x1c0` subsampling x/y · `0x1c4`
frame_context_idx · `0x1c8` refresh_frame_context · `0x1cc` frame_parallel ·
`0x1d0` reset_frame_context · `0x1d4` filter_level · `0x1d8` sharpness ·
`0x1e0` mode_ref_delta_enabled · `0x1e8` base_q_idx · `0x1ec/0x1f8/0x1f4`
delta_q y_dc/uv_dc/uv_ac · `0x240` lossless · `0x244` tx_mode · `0x248`
allow_hp · `0x24c` compound allowed · `0x250` interp_filter · `0x258`
reference_mode · `0x268/0x26c` log2 tile cols/rows · `0x270/274/278`
segmentation enabled/update_map/temporal_update · `0x280` compressed header
size · `0x284` uncompressed header size · `0x2dc..0x2e4` sign bias ·
`0x308..0x31c` ref/mode deltas · `0x320..0x328` ref_frame_idx · `0x90c` color
space · `0x3cb8` active probability context (0xc57 B) · `0x490f + i*0xc57` the
four saved frame contexts · `0x85c` LF level table (64 B).

## Division of labour (matches V4L2 stateless VP9)

Compressed header parsing, forward probability updates, **backward adaptation
from the hardware's count buffer** (`VP9GetCounts`, `Vp9AdaptCoefProbs`,
`Vp9AdaptModeProbs`, `Vp9AdaptNmvProbs`), loop-filter level table and segment
dequant are all **CPU work** in the vendor library. That is the rkvdec/hantro
split; the kernel's `v4l2-vp9` helpers already implement the adaptation. What
remains vendor-specific is the **layout** of the 0xc57-byte probability
buffer and the 0x3398-byte count buffer.

## Probability buffer (0xc57 bytes, at +0 of the 0x88000 buffer)

Recovered by running the vendor's `Vp9ResetProbs` in the emulator and locating
every table of the kernel's `v4l2_vp9_default_probs` in the result
(emulated `Vp9ResetProbs`). Rows marked *pad4* are `[n][3]`
tables stored with a 4th pad byte.

| off | table |
| --- | --- |
| 0x000 | kf_y_mode `[10][10][9]` |
| 0x387 | segmentation tree probs `[7]` (from the uncompressed header) |
| 0x38e | segmentation pred probs `[3]` |
| 0x397 | kf_uv_mode `[10][9]` |
| 0x3fb | inter_mode `[7][3]` pad4 |
| 0x417 | is_inter `[4]` |
| 0x41b / 0x41d / 0x421 | tx8 `[2][1]` / tx16 `[2][2]` / tx32 `[2][3]` |
| 0x427 | 14 static bytes, never written by the parser (keep vendor values) |
| 0x435 | y_mode `[4][9]` |
| 0x459 | uv_mode `[10][9]` |
| 0x4b3 | kf_partition `[16][3]` pad4 |
| 0x4f3 | partition `[16][3]` pad4 |
| 0x533 | interp_filter `[4][2]` |
| 0x53b | comp_mode `[5]` |
| 0x540 | skip `[3]` |
| 0x543 | mv: joint`[3]` sign`[2]` class0_bit`[2]` fr`[2][3]` class0_hp`[2]` hp`[2]` classes`[2][10]` class0_fr`[2][2][3]` bits`[2][10]` |
| 0x588 | single_ref `[5][2]` |
| 0x592 | comp_ref `[5]` |
| 0x597 | coef `[4][2][2][6][6][3]` (dense, libvpx order) -> ends at 0xc57 |

## CORRECTION: the hardware sees a DIFFERENT layout

The table above is the vendor's *software* copy. The per-frame
`Vp9GetEntrypointOffset` builds the whole 0x88000-byte buffer from it in a
hardware-native layout (mapped by emulation with index-tagged probabilities,
`tools/re/vp9/hwprobmap.py`; 2049/2049 bytes
explained, no constants). Key-frame tables (kf_y_mode, kf_uv_mode,
kf_partition) and the 14 static bytes are **never uploaded** -- the engine
holds them. Identical for key and inter frames.

| field | hw off | dims | strides |
| --- | --- | --- | --- |
| tx8 | 0x4000 | [2][1] | 1 |
| tx16 | 0x4004 | [2][2] | 4, 1 |
| tx32 | 0x400c | [2][3] | 4, 1 |
| coef | 0x4014 | [4][2][2][6][6][3] | 576, 288, 144, 24, **4**, 1 (u32 per node triple) |
| skip | 0x4914 | [3] | 1 |
| inter_mode | 0x4918 | [7][3] | 4, 1 |
| interp_filter | 0x4934 | [4][2] | 4, 1 |
| is_inter | 0x4944 | [4] | 1 |
| comp_mode | 0x4948 | [5] | 1 |
| comp_ref | 0x4950 | [5] | 1 |
| single_ref | 0x4958 | [5][2] | 4, 1 |
| y_mode | 0x4970 | [4][9] | 16, 1 |
| uv_mode | 0x49b0 | [10][9] | 16, 1 |
| partition | 0x4a50 | [16][3] | 4, 1 |
| mv.joint | 0x4a90 | [3] | 1 |
| mv comp c | 0x4ac4 - 48*c | sign +0, class0_bit +1, class0_hp +2, hp +3, class0_fr +4 ([2][3], row 4), classes +0xc [10], bits +0x1c [10], fr +0x28 [3] | |
| seg_tree | 0x4af0 | [7] | 1 |
| seg_pred | 0x4af8 | [3] | 1 |

Buffer `+0x0000`: tile entry-point table, 16 bytes per tile after the first:
`{0, 0, start, end}` with start = `col_start/8 | (row_start/8) << 16 |
single-col-or-row << 31` and end = `(col_end-1)/8 | ((row_end-1)/8) << 16`
(MI units -> SB64). Counts stay at `+0x4b00`; the builder zeroes the whole
buffer each frame, which is also what resets the counts.

## Count buffer (0x3398 bytes, at +0x4b00)

Mapped exactly by running `vp9_update_counts` over a buffer tagged word by word
(3302/3302 words). All u32:

| hw off | table |
| --- | --- |
| 0x0000 | tx8p `[2][2]` |
| 0x0010 | tx16p `[2][3]` (v4l2 wants `[2][4]` -> copy) |
| 0x0028 | tx32p `[2][4]` |
| 0x0048 | eob_branch `[4][2][2][6][6]` |
| 0x0948 | coef `[4][2][2][6][6][4]` (`[3]` = EOB-model count) |
| 0x2d48 | skip `[3][2]` |
| 0x2d60 | inter_mode `[7][4]` |
| 0x2dd0 | interp `[4][3]`, intra_inter `[4][2]`, comp_inter `[5][2]` |
| 0x2e48 | comp_ref `[5][2]` |
| 0x2e70 | single_ref `[5][2][2]` |
| 0x2ec0 | y_mode `[4][10]`, uv_mode `[10][10]`, partition `[16][4]` |
| 0x31f0 | mv joints `[4]` |
| 0x3200 | mv comp **1**: sign`[2]` class0`[2]` class0_hp`[2]` hp`[2]` classes`[11]` bits`[10][2]` class0_fp`[2][4]` fp`[4]` (51 words) |
| 0x32cc | mv comp **0**: same |

v4l2 mapping: `coeff[..] = &coef[..][0]`, `eob[..][0] = &eob_branch[..]`,
`eob[..][1] = &coef[..][3]` (the helper forms `{eob[1], eob[0] - eob[1]}`).

## Other buffers

- **co-located MVs (0x78)**: ONE per stream, `ceil(w/64)*ceil(h/64)*640 + 0x4400`
  bytes rounded to 1 KiB (vendor logs it as "top" buffer); read and rewritten
  in place. `hdr_syn[25]` = **use_prev_frame_mvs** = !error_resilient && same
  size as last frame && !last_intra_only && last_show_frame -- the driver must
  track this itself (rkvdec does the same).
- **neighbour (0x60)**: 0x1f4000 bytes, per stream.
- **segment ids**: two maps of `ceil(w/64)*ceil(h/64)*32` bytes; the active one
  is copied through `+0x8000` of the prob buffer.

## Remaining register details (decompile + targeted emulation)

- **Bitstream**: wait for status bit 19 (bitstream DMA busy) to clear, then
  `0x40 = buf_phys >> 8 | 0x70000000`, `0x44 = (hdr bytes) * 8` -- the BIT
  offset from the buffer start to the tile data, past the uncompressed AND
  compressed headers, `0x48 = (frame_size - hdr bytes) * 8`, `0x4c =
  (buf_end_phys >> 10) << 2`. The hardware never parses a header.
- **Reference frames**: `0x98/0x9c` last, `0xa0/0xa4` golden, `0xa8/0x7c`
  altref, Y/C addresses of the ref-map entry named by ref_frame_idx[i].
- **Reference sizes** `0x0c/10/14`: ref width `[13:0]`, height `[29:16]`.
- **Scale** per ref: `scale0 = (x_scale_fp & 0xffff) << 5 | (x_step_q4 - 1)`,
  `scale1 = (y_scale_fp & 0xffff) << 5 | (y_step_q4 - 1)`, with `x_scale_fp =
  (ref_w << 14) / cur_w`, `x_step_q4 = x_scale_fp >> 10`; unscaled = 0x8000f.
  `0x1c` bit 28 is set on inter frames.
- **segment_feature (0x5c)**: bit `s` = SEG_LVL_REF_FRAME enabled for segment
  s, bit `8+s` = SEG_LVL_SKIP, `[17+2s:16+2s]` = the REF_FRAME feature value.
- **SRAM dequant**, per segment s (q = segment qindex, clamped 0..255):
  Y word `dc_q(q + delta_q_y_dc) | ac_q(q) << 16`, UV word `dc_q(q +
  delta_q_uv_dc) | ac_q(q + delta_q_uv_ac) << 16`, lookup tables per bit depth.
- **SRAM loop filter**, per segment: `lvl[intra][0] | lvl[last][0] << 16 |
  lvl[last][1] << 24`, then `lvl[golden][0] | lvl[golden][1] << 8 |
  lvl[altref][0] << 16 | lvl[altref][1] << 24` (6-bit levels; libvpx
  `lfi.lvl[seg][ref][mode]`).
- **Sequence per frame** (vendor): VE reset -> tile init -> build the 0x88000
  buffer -> VE-top regs -> frame regs -> `0x30` -> trigger 7, 8 -> IRQ ->
  write back `0x38` -> read counts -> adapt (if !error_resilient &&
  !frame_parallel) -> save frame context if refresh_frame_context.

## Open

- trigger 7 then 8: what each does (replicate as-is)
- VE_CTRL for mode 7: stock value `0xC0130007`
- secondary output (0x50-0x58) and 10-bit (0x84/0x8c): not needed for a first
  8-bit profile-0 decode
