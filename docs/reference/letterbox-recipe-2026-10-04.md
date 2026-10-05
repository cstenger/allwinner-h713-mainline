# Letterbox recipe: how the window layer places a smaller picture (2026-10-04)

Phase 0 of [letterbox-plan.md](../letterbox-plan.md). Static RE of
`display.bin`, plus a read-only register baseline on the board. No writes.

**Inputs:**
- firmware `local/mips-display/board-b-mips/display.bin`, base `0x8b100000`; MIPS address = ARM + `0xB5000000`;
- tools `tools/mips/{disasm,cfg,block-map,vtables}.py`;
- baseline `letterbox-baseline-2026-10-04/` from `tools/display/letterbox-baseline.py`;
- recipe `tools/display/letterbox-recipe.py`.

## Headline

1. **Placement is a timing offset introduced at the NR (composition) output,
   not a panel register.** Every window downstream of NR is in panel-timing
   coordinates, with the active area starting at (49, 22).
   - Moving NR's output window by (dx, dy) moves the picture.
   - Proc copies its input position to its output.
   - The panel's program window is computed as `stream.x − out.x`, so it stays at (49, 22).
   - The bars are drawn by a **border overlay in the vblender block `0x05200000`**, not in the panel block.
2. **The 2026-09-12 shear is explained.** NR's *fetch window* (`0x05000804`,
   `0x844`, `0x85c`) reads 1280 wide on the live board. That is the
   "consumer steps 1280 pixels per output line" which the shear measured
   exactly. The 09-12 dump stopped at `comp+0x2ff`, so these registers were
   **never dumped or poked**. 0106's negative therefore does not speak to H1.
3. **The model reproduces the live native state.** 42 registers, 67 fields,
   in every block the recipe touches. It also reproduces the firmware's own
   852x480 numbers. The self-test fails under each of five mutations, so it
   can fail.
4. **The firmware brackets geometry writes with a hold/release handshake**
   (`0x05000040[25]`, `0x05000860[17]`, `0x05000138[27]`, `0x0500082c`).
   `decd-scale-test.sh PHASE=scale`, which wedged the panel twice, wrote
   descriptors without it.

## The pipeline, as the firmware computes it

WCETop's node table, in pipeline order
(`mips-wce-window-layer-2026-09-04.md`): Cap `+0x68`, NR `+0x6c`, DETN `+0x70`,
Proc `+0x74`, Panel `+0x78`. Each node's `WriteReg` (vtable slot 4) takes a
flag word that selects which register groups it writes.

**Window structs** are stored `{x, w, y, h}` (offsets +0, +4, +8, +0xc) and
printed `[x, y, w, h]`. `PanelWinNode::DbgDump` at `0x8b1a4e7c` loads
`+0x54, +0x58, +0x5c, +0x60` for `m_video_win_2` and prints them in the order
0, 8, 4, 0xc.

### NR (composition `0x05000000`): where the offset enters

- WCETop computes NR's output origin:
  - `0x8b1a87f0`: `hde = hs_size + h_back_porch − 28 (− delays) + x_off`, adding `x_off` only when it is > 0;
  - `0x8b1a8928`: `vde = vs_size + v_back_porch (− 1 if interlaced) + y_off`.
- That origin becomes `NRWinNode.m_out_win.{x,y}` (the call at `0x8b1aa47c`/`0x8b1aa498`).
- `NRWinNode::CalcWindow` (`0x8b1a3704`) then sets `m_read_fetch_win = {out.x, crop.x+crop.w, out.y, crop.y+crop.h}` (`0x8b1a3974`–`0x8b1a39a4`).
- The live board has `hs_size 20`, `h_back_porch 57`, `vs_size 2` and `v_back_porch 20` (elog 2026-09-04), so the origin is **(49, 22)**. `proc+044 = 0x31` and `lvds+0c0[15:0] = 0x16` read it back.

`NRWinNode::WriteReg` (`0x8b1a48cc`), with each group under its own flag bit:

| flag | registers | content |
| --- | --- | --- |
| `0x4` | `0x0f0`, `0x174`/`0x178`, `0x1b4`/`0x1b8` | channel A Rowbyte / LineBufLevel / LineNumber (A's line numbers take the hardcoded 1080/540 path) |
| `0x2` | `0x210`, `0x224`, `0x274`/`0x278`, `0x2b4`/`0x2b8` | channel B descriptors, picture size `{h, w}` |
| `0x400` | `0x804`, `0x808`, `0x80c` | fetch window `{x−5, even w}`, x, `{y, h}` |
| `0x1000` | `0x854`, `0x858`, `0x85c`, `0x860` | vs/hs delay, `{?, y}`, `{crop.w, x}` |
| `0x2000` | `0x844` | `{even(read_fetch.w), read_fetch.x − 1}` (`0x8b1a4cb4`) |
| `0x4000` | `0x840` | `{read_fetch.h + 1, read_fetch.y − 1}` (`0x8b1a4d04`) |
| `0x10000` / `0x8000` | `0x040[25]` | clear / set |
| `0x80` / `0x100` | `0x860[17]` | set / clear |
| `0x40` / `0x20` | `0x138[27]`, (`0x82c[15:0] = 1` with `0x20`) | set / clear |

The three `GetPsuPfuWin` calls (`0x8b1a3abc`/`3ae8`/`3b0c`) all take the
**same** frame buffer (`node+0x58`), so channels A and B get identical
Rowbyte/LineBufLevel values.

### The write protocol

The window-update handlers (`0x8b1a8cbc`, `0x8b1a8df4`) call the nodes in this
order:

```
NR    0x000100c0   hold:     040[25]=0, 860[17]=1, 138[27]=1
DETN  0x00080000
NR    0x00007e06   geometry: A+B descriptors, 804-80c, 854-860, 844, 840
NR    0x00008120   release:  040[25]=1, 860[17]=0, 138[27]=0, 82c=1
DETN  0x00260000
Proc  0x00400000   route + proc
Panel 0x00800000   lvds windows + vblender borders
```

The live board is in the released state: `comp+040 = 0x02090208` (bit 25
set), `+860 = 0x71` (bit 17 clear), `+138 = 0x04FFFFFF` (bit 27 clear),
`+82c = 0x00010001`.

### AFBD source 0 (`0x05600000`): the firmware's geometry

Writers `0x8b1a40e0`, `0x8b1a418c` and `0x8b1a4220`; already in
`small-source-shear-2026-09-12/RESULT.md` and confirmed here:

| reg | field | value |
| --- | --- | --- |
| `+0x020` | [12:0], [28:16] | `ALIGN16(W) − 1`, `ALIGN16(H) − 1` |
| `+0x024` | [8:0], [24:16] | `ALIGN16(W)/16 − 1`, `ALIGN16(H)/16 − 1` |
| `+0x030` | [12:0], [28:16] | `even(W)`, `H` |
| `+0x040`/`+0x044` | [15:0] | `ALIGN16(stride in samples)` |
| `+0x048` | [15:0], [28:16] | `ALIGN4(W)`, `H` |
| `+0x04c` | [15:0], [28:16] | `ALIGN4(W)`, `H/2` (4:2:0) |

Two consequences for any producer:
- **The stride must be a multiple of 16 samples**, or AFBD steps a different pitch from the buffer's and shears. Cedrus pitches are 32-aligned (0125).
- **AFBD reads whole 16×16 blocks**: `ALIGN16(W) × ALIGN16(H)`. A 1280x536 picture is fetched as 1280x544, so the buffer must cover 544 lines of luma and 272 of chroma, or the fetch runs past it (an IOMMU master-2 fault).

### Proc (route `0x05140000`, scaler `0x05180000`)

- `ProcWinNode::CalcWindow` (`0x8b1a62c4`) sets `m_in_win` and `m_out_win` to the **input stream's** x/y (`0x8b1a6494`–`0x8b1a64c8`), with sizes from `in_win_size`/`out_win_size`.
- Every route window starts at (0, 0): source `+0x104/108`, picture `+0x124/128`, out `+0xd40/d44`.
- The stream position appears only as `proc+044 = stream.x` and `proc+02c[31:16] = stream.x + 4` (`0x8b1a6504`), plus `proc+050[31:16] = in_vs_delay + 1 + vde_start + mb_420`.
- At unity, proc just carries the offset picture through.

### Panel (`0x051c0000`) and vblender (`0x05200000`)

`PanelWinNode::CalcWindow` (`0x8b1a52d4`) takes `out_win` from the window
manager. That is the picture's offset inside the panel.
- Its program window is `{stream.x − out.x, panel_w, stream.y − out.y, panel_h}` (`0x8b1a5410`–`0x8b1a5434`), so for a correctly offset stream it stays at (49, 22).
- `WriteReg` (`0x8b1a5a38`, flag `0x800000`) writes:
  - the program window, `0x0bc = {w, x−1}` and `0x0c0 = {h, y}`;
  - `video_win_2` **sizes only**, `0x03c/0x040/0x0a4/0x0a8 = {size, 0}`;
  - the 21:9 window `0x204`;
  - the crtc window `0xfe00/0xfe04`, reached via `ori 0xfe00`, which `block-map.py` cannot see. It follows the program window while `lvds+010[31]` is clear, as it is on this board.

`WriteBorderOverlay1` (`0x8b1a55d8`) computes:

```
left   = out.x                         top    = out.y
right  = border.w − out.x − video_win_2.w
bottom = border.h − out.y − video_win_2.h
0x05200000 = right[11:0] | top[3:0]<<12 | left<<16 | top[7:4]<<28
0x05200004 = bottom[11:0] | top[11:8]<<12 | 1<<30        (bit 30: enable)
0x0520000c/010 = border window {w, x} / {h, y}           (live: {1280,49} / {720,22})
```

It also clears `lvds+034`, `+038[23:0]` and `+1bc` and sets `+038[25]`, all
already in that state on the board. `WriteBorderOverlay2` (`0x8b1a57c0`) only
writes the border window again, at `0x05200020/024`.

**The border colour is not programmed anywhere.** No firmware routine writes
`0x05200008` or `0x014`–`0x01c`. Nor does `LogoRegData.bin`. So the bars are
whatever the hardware fills with. Phase 1 has to look at them.

### DETN (`0x050c0000`) is not in our path

`DETNWinNode::WriteReg` (`0x8b1a1a64`) writes window geometry at
`0x050c0040`–`0x074`. On the live board those hold a **720-wide** capture
configuration: `detn+074 = {49, 720}`, `+070 = {22, 720}`, `+6a4 = {480, 720}`.
A full 1280x720 picture is on the glass, so the DETN windows cannot be in our
raster's path. They are left out of the recipe.

## Baseline (read-only, 2026-10-04)

`tools/display/letterbox-baseline.py` reads two sets of registers:
- the ranges `blockdump.py` had already mapped;
- beyond those, only registers the firmware itself loads or stores.

It never touches `0x07091000` or `0x06940000`. It was run twice, with native
720p playing (`gst-plane-play`, `v4l2slh264dec`) and with the console: 1182
words each, no kernel messages. During the video dump the source was enabled
(`0x05600010 = 0x03000013`) and `video-0` sat on crtc-0 with a changing fb id.

- `native-720p.txt`: the reference the recipe is diffed against.
- `console.txt`: taken *after* a video session, so source-0 registers keep the last video geometry. On a fresh boot, before any video, AFBD source 0 holds U-Boot's logo configuration: `+020 = 0x043F077F`, `+024 = 0x00420077`, strides `0x780` (1920x1088). This is from an earlier run the same day.

Between console and video, the only differences are:
- AFBD's own control, slot-address and status words (`+010`, `+058/05c`, `+070`–`+0a4`, `+0b8/0bc`, `+140`, `+184`, `+300`–`+310`);
- `route+508` (gain);
- `lvds+06c` (selector).

Every window register in the recipe is identical in both. It is static state
left by U-Boot's firmware run, and the driver never touches it.

## The recipe

`tools/display/letterbox-recipe.py --live native-720p.txt WxH [X,Y|centre]`
prints every register as `old → new`, field by field, with provenance.
- **`abs` fields:** the firmware formula, checked against the live state.
- **`rel` fields:** `live + f(new) − f(native)`. These are timing positions whose fixed per-register delays are not all derived: `0x804[31:16]`, `0x808`, `0x80c`, `0x858[15:0]`, `0x85c[15:0]`, `proc+02c[31:16]`, `proc+044` and `proc+050[31:16]`.

It refuses:
- odd sizes;
- odd x offsets;
- off-panel placement;
- a stride that is not a multiple of 16 samples, or is below `ALIGN16(W)`.

It prints the buffer coverage required and the write order.

**Line-buffer descriptors.** Rowbyte = LineBufLevel = `ceil(W/20)` on both
channels, and channel B's line numbers are H and H/2. This is
`GetPsuPfuWin`'s compressed branch, `((x<<3)+0x7f)>>7`, with 0.8 bytes per
pixel. It reproduces the live 1280 → `0x40` **and** the firmware's own
852 → `0x2B`, which the firmware computed from *our* VideoInfo descriptor on
2026-09-05. The uncompressed branch (`CalcRowByteLineBufLevel` at
`0x8b1a224c`, ratio 10000) would give `W/16 = 0x50` at 1280. The board does
not run with that value.

Self-test: `--self-test` passes on both dumps (42 registers, 67 fields).
Five deliberate formula mutations each fail it (rowbyte, C line number, a
border, block count, a panel size).

**Example, 852x480 centred, stride 864:** borders 214/214/120/120.
- AFBD `0x020=0x01DF035F`, `0x024=0x001D0035`, `0x030=0x01E00354`;
- descriptors `0x002B002B`;
- fetch window `0x844=0x03540106`, `0x840=0x01E1008D`;
- proc `0x044=0x107`, `0x050=0x009301E0`;
- vblender `0x000=0x70D680D6`, `0x004=0x40210078`.

## Open items, in order of risk

1. **Border colour:** hardware default; unknown until seen. If it is not black, look for a fill register in the vblender before Phase 2.
2. ~~**`0x05000858[31:16]`**~~ **RESOLVED 2026-10-05 on hardware:** it is the picture height (`para[0]`). Left at 720, it clipped every vertically offset picture. The recipe now writes H. See `letterbox-phase1-2026-10-04.md`, bisect set 3.
3. **The descriptor formula is fitted to two firmware-produced points.** It is not derived for every format. P010 is not covered: the firmware's own 10-bit branch takes formats 14/15, and the descriptors there are underived.
4. **AFBD budget with stride ≠ width.** The firmware writes `H` into `+030/+048[28:16]`. The driver's `pitch × H / line` agrees only when stride equals width. The recipe follows the firmware, and P010 doubles it, as measured on 2026-09-30.
5. **The `SetAspectRatio` caller rectangle is untyped.** The offset arguments at `0x8b1aa47c`/`0x8b1aa498` come from `sp+0xa4`/`sp+0xac` of the window-update frame. The mechanism (positive offsets added to hde/vde) is established; the name of the rectangle is not.
6. **Upscaling (Phase 3) is not in the recipe.** It needs proc ratios and phases, and in/out windows that differ. The retired chain 0098–0111 has them.

## What this changes in the plan

- **H1 now has a specific mechanism to test.** A sub-panel raster needs the fetch window and descriptors sized with it, inside the firmware's hold/release bracket. 09-12 never did either.
- **No stock HDMI-in capture is needed.** Placement is resolved statically and reproduces the live state. The only thing a capture would add is the border colour, and Phase 1 shows that directly.
- **Geometry from photos** must use a fixed camera and a full-panel control shot, because no colour can be programmed into the bars.
- **Phase 1 should step one axis at a time:**
  1. 1280x536 at (0, 0): height only;
  2. 1280x536 at (0, 92): vertical offset;
  3. 852x480 centred, stride 864: width and horizontal offset.
