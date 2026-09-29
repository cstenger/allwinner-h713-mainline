# AV1 on the H713: the Google decoder IP

**Status: reverse-engineering in progress (started 2026-09-29).** The block is
alive under our kernel (patches 0140-0142) and its register map is fully
recovered; no decode yet.

## What the block is

`allwinner,sunxi-google-ve` at `0x01c0d000`, SPI 107, PPU domain 4, IOMMU
master 5. Core ID `0x0003b16d` (read on hardware by the 0141 probe, identical
to stock). It is Google's **combined encoder/decoder register file**
("taffel"), synthesised here as an **AV1-baseline decoder only**: register
`+0x004` reads `0x22` = `sw_decoder_cfg` (bit 1) + `sw_av1_baseline_cfg`
(bit 5), with `sw_vp9d_cfg` = 0. The vendor library `libawav1.so` also
carries VP9 entry points (the VP9DecContainer codebase was extended for
AV1), but this silicon does not decode VP9 -- the VE does
([[vp9-ve-register-interface]]).

Lineage: Hantro (On2 -> Google 2010 -> VeriSilicon 2014). Mainline's
Rockchip VPU981 (`drivers/media/platform/verisilicon/`) is a VeriSilicon
descendant and a sibling of this core.

## The register map is complete

`tools/re/av1/swregisters-bits.txt` (regenerate with `tools/re/av1/bitmap.py`): 794 fields (783
writable), 284 registers, every bit position recovered by emulating
`SwRegisters::ToByteArray` with one member set at a time (783/783 exact
widths). Names and widths come from the vendor's own debug printer,
`operator<<(ostream&, SwRegisters const&)`, which prints every field as
`sw_name (width) = value`. The image written by `AsicFlushRegs` is the MMIO
layout word for word (the 0141 probe's `+0x000 = 0x0003b16d`, `+0x004 =
0x22` both check out).

- Start: `AsicEnableHw` sets bit 0 of `+0x008` (`sw_enc_enable` -- a shared
  name; it is the start bit for decode too).
- The vendor's in-memory copy is `taffel::ctypes::SwRegisters`, 0x488 bytes
  = the 1168-byte image minus the two read-only ID words.
- `AsicRegisterMapWidth` returns 0x490 unless the ID's low half is `0xb16c`
  (the BigSea variant, 0x330) -- this die takes the 0x490 map.

**229 of VPU981's 344 AV1 register names occur verbatim** in this map. The
rest are VeriSilicon's post-processor (`pp_*`), AXI tuning, and renames, plus
real semantic differences: per-segment `quant_scale_idx_seg*`, per-segment
per-ref loop-filter deltas, tile sizes in registers
(`tile0..15_stream_size`), the stream's last 128 bits in a register
(`strm0_last_word`).

## Entropy tables: identical to VPU981

The vendor's CDF upload (`Vp9AsicProbUpdate`, AV1 branch) copies **0x2fe0
bytes** into the probability buffer, and **0x8a bytes** at `+0x890` for some
frames. Mainline's `sizeof(struct av1cdfs)` is 0x2fe0 (12256) and
`sizeof(struct mvcdfs)` is 0x8a (138). The CDF layout is VPU981's;
`rockchip_av1_entropymode.c` applies as is.

## Buffers (H713 register names)

rec_lum/rec_ch (current), ref0..6 lum/cb/cr, rec/ref*_sindex (compression
index), rec_lum_comp, prob_tab / prob_tab_out, ctx_counter, tile,
temporal_read / temporal_write / temporal1..3_read (MVs), vert_filt_read /
vert_filt_write, filter_ctrl_info_colbuf, filter_lr_params_colbuf,
filter_cdef_dir_colbuf, film_grain / film_grain_colbuf, global_model,
out_secondary_lu/cb/cr/colbuf (raster output), **pdec_config** (a
DRAM-resident configuration block the vendor fills with
`WritePdecRegsToDram` -- no VPU981 counterpart).

## Vendor code map (libawav1.so, 32-bit ARM, stripped but .dynsym is C++-mangled)

| function | size | role |
| --- | --- | --- |
| `Vp9AsicInit` | 22 KB | one-time setup, buffer allocation |
| `Vp9AsicInitPicture` | **247 KB** | per-frame register setup (fully inlined) |
| `Vp9AsicProbUpdate` | 5 KB | CDF upload |
| `Av1AsicSetCDEF/LR/FGS` | 4/0.3/8 KB | filters, film grain |
| `Av1DecodeObuHeaders`, `Av1DecodeFrameTag` | 3/5 KB | header parsing |
| `CreateAv1Decoder` | | plugin vtable: init, reset, set-sbm, fbm-num, fbm, decode, destroy |

The library also contains an HLS software model of the hardware
(`VP9DecEControl::Start` runs it in a thread; `sem_channel` types) -- not the
MMIO path.

## Stock register state during a real decode

`tools/re/av1/decode-dump.py` decodes a register dump (from
`tools/stock/stock-capture.sh`) into named fields. The two snapshots of stock
playing `av1b-720p30-testsrc2-30s.mp4` (`local/h713-lab/stock-capture-20260929/out/av1b-play-*`)
give a golden target:

- **References are compressed** (`sw_ref_compress_e = 1`, `rec_lum_comp`,
  `*_sindex`), with per-frame compressor entropy modes (`sw_fc_cur_*_entropy*`)
  derived from hardware statistics (`sw_fc_*_count`) by the vendor's
  `FcUpdateModes`/`FcSetModes*`. First target: run with compression OFF.
- **Display is the secondary output** (`sw_secondary_output_e = 1`, format 1):
  Y/Cb/Cr bases spaced as planar 4:2:0 (1280x768 luma, 640x384 chroma). Same
  architecture as VPU981: private references + a raster write to the capture
  buffer.
- Addresses are plain byte IOVAs (the `_msb` halves zero); the stream base is
  byte granular (`sw_out_stream0_base`), start bit in `sw_strm_start_pos`,
  length in `sw_stream_len`.
- Per-frame between the snapshots: stream start/len, `quant_base_qindex`,
  the `fc_*` modes. Everything else (sizes, scales, error detection, AXI
  bursts 0x20/0x100, `timeout_limit` 0x1000000) is constant.

## The register image is a packed bit vector

119 of the fields straddle 32-bit words, so mainline's `hantro_reg {base,
shift, mask}` cannot describe them. `tools/re/av1/gen-regs-h.py` emits
`H713_AV1_<FIELD> = H713_AV1_FIELD(bit offset, width)`; the driver sets fields
in a shadow image and writes all 292 words, as `AsicFlushRegs` does.

## The per-frame setup (Vp9AsicInitPicture)

Decompiles (Ghidra, `-Ddecomp.payload=1024`) to 26 k lines of packed bit
operations on the working image at **container+0x33550** (0x488 bytes, right
before `std::vector<SwRegisters>` at +0x339d8, one element per register set).
Container buffers: +0x28 pdec_config, +0x34 prob table, +0x58 tile info, +0x7c
global model, per-frame Y/UV/MV tables at +0x180/+0x318/+0x4b0 + idx*0xc.
`tools/re/av1/fieldmap.py` (differential emulation with named outputs) needs a
REALISTIC container: from a zeroed one the function computes garbage indices
and faults. Next step: build the container by running the vendor's own
`Vp9AsicInit` and header parser on a real stream in the emulator.

## Plan

A new variant in mainline's hantro/verisilicon driver, reusing the VPU981 AV1
decode logic (V4L2 stateless AV1 uAPI, CDF handling, film grain) with an H713
register-field table generated from the map above, and the vendor's
per-frame setup as the reference where the two cores differ (buffers,
`pdec_config`, output format). Open: reference/output frame format
(compressed? `*_sindex`) versus raster NV12 through the secondary output.
