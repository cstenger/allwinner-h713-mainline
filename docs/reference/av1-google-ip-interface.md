# AV1 on the H713: the Google decoder IP

**Status (2026-09-29): the block DECODES under our kernel.** The first frame of
the stock test clip, programmed exactly as the vendor library programs it,
came out bit-exact (luma and chroma identical to libdav1d) in 1.6 ms. No
driver yet -- this was a replay of the vendor's own register image and
buffers.

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

## Running the vendor decoder, and replaying it on the hardware

`tools/re/av1/vendor-decode.py` runs the whole vendor plugin in the emulator
on an IVF stream: CreateAv1Decoder, init, set-sbm, decode loop, with the
CedarC services faked in Python (memory adapter with identity physical
addresses, VE ops whose getRegBase returns a window preloaded with the ID
words, a frame-buffer manager, a stream ring). It intercepts
`VP9DecEControl::Start` -- the hand-off to the thread that would flush the
registers -- and writes, per frame, the register image and every allocation a
`*_base` field points into, with a relocation manifest. The vendor's packed
struct is **image[0:0x488]** (the two dropped words are at the end, not the
IDs). Its images match stock's live registers field for field, apart from
per-frame content.

`tools/re/av1/mkreplay.py` packs a frame; the probe module's debugfs replay
(patch 0141) allocates the buffers at real IOVAs (IOMMU master 5,
translating), relocates, writes all registers with start held back, starts,
and waits for SPI 107.

Findings from the first replay:

- **PLL_VE must be <= 432 MHz for this core.** At 600 MHz (cedrus's rate)
  it stalls: status bit 2 (timeout) after `timeout_limit` = 0x1000000 cycles,
  28 ms. At stock's 432 MHz the same frame finishes in 1.6 ms, status 0x52
  (mode_dec | frame_ready | irq) -- stock's exact post-decode value. The VE
  module clock is shared with cedrus, so the driver has to clamp it.
- **Secondary output format 1 is NV12**: Y at `out_secondary_lu_base`,
  interleaved UV at `out_secondary_cb_base`; `out_secondary_cr_base` is
  unused.
- Frame 0 (key frame) uses no pdec_config; the vendor adds it from frame 1.
- Replaying later frames standalone is not meaningful: their references and
  the vendor's CDF/compression state come from the hardware's outputs, which
  the emulation does not have.

## Hardware lessons from the replays

- **ref_compress_e = 0 hangs the core** -- no interrupt at all, not even its
  own timeout; the start bit stays set. Compression is part of the working
  configuration, not an option: follow stock and port the vendor's
  compressor-mode logic (`FcUpdateModes`, `FcSetModesCurrent/Ref*`).
- **Never write registers into a busy core** (start bit still set): that
  wedged the SoC. After a timeout the block must be reset first; the 0141
  replay now refuses while busy and resets on timeout.
- PLL_VE and every clock register: read the live value, change one field.

## Buffer sizes (vendor `Vp9AsicAllocatePictures`, compression on)

Per frame, with `sb = ceil(w/64) * ceil(h/64)`:

| buffer (register) | size |
| --- | --- |
| reconstruction (`rec_lum`) | `sb * 0x2400`, 4 KiB aligned -- compressed luma+chroma |
| compression header (`rec_ch` = `rec_lum_comp`) | `ceil(sb_cols/8) * ALIGN(h,64)/2 * 0x40`, 4 KiB aligned |
| temporal MVs (`temporal_write`, later `temporal*_read`) | `sb * 0x400` |
| raster output (`out_secondary_*`) | NV12, `w*h*3/2` |

(1280x720: 2211840 / 73728 / 245760 -- the captured allocation sizes.)

## Driver plan

An H713 variant in mainline's hantro/verisilicon driver:

- `V4L2_PIX_FMT_AV1_FRAME` in; NV12 out as a **post-processed** format, so
  hantro keeps the native (compressed) reference frames in its auxiliary
  buffers -- the same split as VPU981's post-processor, and as stock.
- Registers: VPU981's AV1 decode logic (`rockchip_vpu981_hw_av1_dec.c`) ported
  onto a shadow copy of the packed H713 image (generated field table,
  `tools/re/av1/gen-regs-h.py`), written out whole; start bit last.
- Reused as is: `rockchip_av1_entropymode.c` (identical CDF layout),
  `rockchip_av1_filmgrain.c` (to be checked against `Av1AsicSetFGS`).
- Clocks: the node claims `bus_av1`, `mbus_av1` and `reset_av1` only. The VE
  module clock, `bus_ve` and `reset_ve` belong to cedrus; a runtime-PM device
  link (AV1 consumer, VE supplier) keeps them up while AV1 runs, and cedrus's
  H713 module rate drops to 432 MHz so one rate serves both cores.
- Validation without risking the SoC: a dry-run mode that builds each frame's
  register image and compares it, field by field, with the vendor's capture
  of the same stream (`vendor-decode.py`), before the core is ever started.
- To port: the compressor-mode state (`fc_*`), and `pdec_config` -- a DRAM
  register block the vendor writes from frame 1 (`WritePdecRegsToDram`; its
  field names are in the vendor's `operator<<(PdecSwRegs)` printer).
