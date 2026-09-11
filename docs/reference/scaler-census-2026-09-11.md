# 0x050c0000 characterised — and a complete scaler census

Static RE, no board time.

## 0x050c0000 is DETN: noise reduction, not scaling

`0x050c0000` is `DETNWinNode`'s block. 224 accesses across 7 code regions, but
160 of them (48 of the 51 registers) are in one region, `0x8b1a1400..0x8b1a1d00`.

Its members, from the `DbgDump` format strings:

```
m_out_win  m_detn_win  m_video_win  m_picture_win
m_motion_win  m_motion_win_1  m_motion_win_2  m_motion_win_3
```

Four **motion** windows — motion estimation. This is a temporal noise-reduction
stage. Its two register writers are named in the image: **`WriteDETNPFU`**
(Picture Fetch Unit) and **`WriteDETNPSU`** (Picture Store Unit).

Three independent checks say it has no scaler:

1. **It calls `FrameBuffer::GetPsuPfuWin` four times** (`0x8b1a13f4`,
   `0x8b1a1484`, `0x8b1a1604`, `0x8b1a1950`). That is the function whose own log
   line names its six outputs *Rowbyte, LineBufLevel and LineNumber* — so DETN's
   geometry registers are the same **line-buffer descriptor** as the composition
   block, which is exactly the thing mistaken for a scaler on 2026-09-09.
2. **The unity constant `0x8b206dac` is never loaded anywhere in the DETN
   region.** No 16.16 ratio arithmetic happens here.
3. **No 22-bit ratio field is inserted anywhere in the block** — see the census
   below.

> `0x050c0000` is a noise-reduction / motion-detection stage with its own
> fetch and store line buffers. **No scaler.**

## The census — every scaler in the firmware

Both confirmed ratio registers are written with the same instruction shape:
`ins rt, rs, 0, 0x16` — a 22-bit field at bit 0. Scanning the **entire image**
for that signature finds exactly **six sites, in three blocks**:

| sites | block | what it is | status |
| --- | --- | --- | --- |
| `0x8b1a0874`, `0x8b1a08c0` | **`0x0694087c` / `0x06940864`** | `CapWinNode`, two-axis, `m_scale_ratio_h` / `m_scale_ratio_v`, via `CalcScalingRatio_1` | **capture path — see hazard** |
| `0x8b1a597c`, `0x8b1a5a1c` | `0x051c0138` | panel down-scaler, **vertical only** | video side untested with the stage on |
| `0x8b1a6758`, `0x8b1a6764` | `0x05180008` / `0x0518003c` | proc scaler, two-axis | **upscale only — closed 2026-09-11** |

That is the whole population. There is no fourth scaler waiting to be found, and
no scaler at all in composition (`0x05000000`), DETN (`0x050c0000`), route
(`0x05140000`) or AFBD (`0x05600000`).

## The capture scaler: real, two-axis — and not a route

`CapWinNode::WriteReg` addresses `lui 0xbb94` → ARM **`0x06940000`**, outside the
display range entirely. It is the only two-axis ratio pair besides the proc
scaler, and `CalcScalingRatio_1` computes both axes for it.

**Do not read `0x06940000` casually.**

- It has never been read on this project — no hit anywhere in the tree.
- The capture block is behind the **TVFE/TVCAP power domains, which are off at
  boot** (`pm_genpd_summary`: `TVCAP off-0, TVFE off-0`, per
  [hdmi-in.md](../hdmi-in.md)).
- Reading an ungated block in this neighbourhood is the documented way to wedge
  this SoC — a plain read of `0x07091000` requires a power cycle.

And it would not help even if powered: it scales data arriving from the **capture
front end**, not data fetched from DRAM. Our video is Cedrus → DRAM →
AFBD/DECD fetch → display, which never passes through capture. Fetch-side
scaling is what 1080p playback needs.

## Where this leaves the no-GPU downscale search

The search is now **exhaustively enumerated** rather than open-ended:

- composition, DETN, route, AFBD — **no scaler exists**
- proc scaler — **upscale only**
- capture scaler — **wrong path, and behind an unpowered domain**
- panel down-scaler — **vertical only**, and its video-side test with the stage
  actually enabled has still never been run

So exactly one untried no-GPU experiment remains, and it cannot be a complete
answer by itself: the panel down-scaler is vertical-only, so at best it delivers
`1080 → 720` vertically and leaves `1920 → 1280` horizontally unsolved.

**If that comes back negative, the no-GPU options are exhausted** and the GPU
path is what remains — which is the first time in this project that statement
can be made from an enumeration rather than from a run of individual nulls.
