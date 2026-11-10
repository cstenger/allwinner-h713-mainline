# Handoff — H.265 hardware scale-down, 2026-09-16

**Update 2026-09-17:** [The shared-scaler handoff](handoff-2026-09-17-shared-scaler.md) supersedes
the H.264 routing, power-of-two quantization, and rotation recommendations
below. Patch 0120 uses this polyphase block for both codecs and removes rotation.

Branch `h713-display-video-path`, series head `179a6b5`, pushed and in sync.
Working tree clean. 85 patches in `patches/kernel/series`.

## What this session did

H.265 hardware scale-down went from "hangs the VE every time" to landed and
validated. The blocker was a wrong model: everyone assumed the H.265 secondary
output was the H.264 SDROT recipe at different register offsets, because that
is what mainline's dead defines describe. It is not.

**The scaler is a different block: "VE/Top1 Level", vendor register group 7, at
VE + 0xf00.** It is a 4-tap/32-phase polyphase scaler with loadable
coefficients, and it lives inside cedrus's existing register window — no DT
change, no separate driver. The vendor's decoder picks it for any real
downscale and leaves `reg50.scale_precision` at zero. Setting
`write_sc_rt_pic` without configuring it is exactly the timeout that had been
seen for months.

Found by reading **H713's own vendor blob**,
`local/h713-lab/ve-extract/libs/libawh265.so`: `.symtab` is stripped but
`.dynsym` exports every function and every register shadow, so
`readelf --dyn-syms` gives the whole map. No hardware and no booting the vendor
stack was needed. H6-CedarC could never have answered it — its register-group
enum stops at 6.

## Committed

| patch | what |
| --- | --- |
| 0115 | recon buffer sized for 10-bit side data (latent bug, found on the way) |
| 0116 | 10-bit primary offsets from `recon_fmt`, not `dst_fmt` (latent bug) |
| 0117 | H.265 has **no rotate field in silicon** — measured, not inferred |
| 0118 | **the scaler**, 8-bit and Main10 |
| 0119 | `VIDIOC_ENUM_FRAMESIZES` |

Plus `tools/video/gen-scaler-coef.py` and two reference docs. The full technical
record — register map, disassembly, every dead end — is
`docs/reference/h265-scaler-is-a-separate-block-2026-09-16.md`. Read that before
touching the block.

### Results, all on hardware

Luma PSNR against a software rescale of the same frame:

| case | ours | for comparison |
| --- | --- | --- |
| 1280x720 -> 640x360 | **55.45 dB** | H.264's shifter: 46.10 |
| 1280x720 -> 320x180 | **45.01 dB** | H.264's shifter: 46.42 |
| 1280x720 -> 640x180 | **47.85 dB** | |
| Main10 640x480 -> 320x240 | **53.62 dB** | chroma U 36.10, V 31.15 |

All seven HEVC vectors decode clean scaled and unscaled. H.264 unaffected.
v4l2-compliance 48/49, unchanged (the one failure is the pre-existing
`TRY_EXT_CTRLS`).

### The coefficients are ours

The vendor ships a table; copying it would put proprietary data in a GPL tree.
`tools/video/gen-scaler-coef.py` generates an equivalent one from standard
kernels (cubic B-spline and triangle), and it measures **better** than the
vendor's on every case. Only 2 of 480 words coincide, which is what two
independent cubic designs look like. Regeneration is deterministic.

## Next steps, in the order I would take them

### 1. Move CAPTURE sizing to `S_FMT` (the spec's mechanism)

The stateless decoder interface
(`Documentation/userspace-api/media/v4l/dev-stateless-decoder.rst`) says
`ENUM_FRAMESIZES` for discovery (step 3) and a CAPTURE `S_FMT` whose width and
height may differ from `G_FMT` "if the hardware supports composition and/or
scaling" (step 5). COMPOSE does not appear in that flow at all. We use COMPOSE.

0119 added the discovery half. The selection half is still on the selection API.
This needs a per-codec fork, because H.264's shifter and H.265's polyphase block
have different reachable sets.

Evidence this matters: v4l2-compliance reports `Composing: Not Supported` and
`Scaling: Not Supported`, because it probes the default context where the OUTPUT
format is MPEG-2 and `cedrus_s_selection()` refuses. Our scaler is invisible to
the standard tool.

### 2. Stop quantising to powers of two, for H.265

`cedrus_compose_shift()` only ever emits power-of-two ratios, because that is
all the H.264 shifter can express. The VE+0xf00 block has no such limit and
**arbitrary ratios are proven on hardware**: 44.06 dB at 1.333x and 43.11 dB at
1.5x, the latter exercising all 32 phases across two coefficient sets.

This is the highest-value item and it is not really an API nicety. The display
path currently has the VE emit 960x544 and the display proc upscale to
1280x720, purely because 1920->1280 is 1.5x and the quantiser cannot say it.
That second stage is patches 0098, 0103, 0106, 0108, 0111 and the
grey-streak / phase-window / route-window bug class that consumed most of this
project's bench time. **If the VE does 1.5x directly, the display-side scaler
leaves the video path entirely.**

Caveats: the quantiser must stay for H.264; only two arbitrary ratios have been
measured; min/max ratio and output alignment limits are inferred from field
widths, not probed; and arbitrary ratios use the bucket-averaged coefficient
sets (43-44 dB) rather than the exact-ratio solutions (45-55 dB).

### 3. `H264ConfigNewScaler` — optional

Driving this block from the H.264 engine was tried and failed: 11.08 dB garbage
at 2x/2x and a decoder wedge at 2x/4x. The vendor does do it, via
`H264ConfigNewScaler` (776 bytes), which touches context state at `[r1,#0x44]`,
`[r1,#0x48]` and `[r0,#0x20]` before any register write, plus
`H264ComputeScaleRatio` (40 bytes) and `H264DecoderSetExtraScaleInfo` (100).
About an hour of static RE on a blob we already have.

Worth doing only if H.264 arbitrary ratios are wanted. It does **not** enable
consolidation: rotation is absent from H.265 silicon, so SDROT survives either
way, and the result is two paths regardless. If it is pursued, make it additive
— H.264 uses the new block only for ratios the shifter cannot express — rather
than a migration that risks the one video path that has never given trouble.

### Smaller, noted but not acted on

- `ENUM_FMT` on CAPTURE is not filtered by the active OUTPUT format, which the
  spec states as a "must". This is upstream cedrus behaviour and I found no case
  where the raw set actually varies on this hardware.
- We still advertise MPEG-2 and VP8, which have never been validated on H713.
- `+0x00` (5-bit) and `+0x04` (1-bit) in the scaler block remain unexplained.
  Neither is written by the codec blob; bit 0 of `+0x00` breaks the pipeline,
  the rest do nothing observable.

## Traps. Please read these before measuring anything.

Every one of these produced a confident wrong answer during this session.

**`install-kernel-module.sh` reports "loaded" when the `scp` before it failed.**
The board's rootfs hit 100% and several builds were silently never installed —
one probe returned an "impossible" result because it was measuring a stale
module. **Always verify the board's module md5 against the one just built.**
There is a wrapper pattern in the doc; use it. `journalctl --vacuum-size=40M`
freed 232M. Board is currently at 93% with `/var/tmp` (~100M of prior-session
artifacts) and `/root/fits` (211M) as the remaining candidates — both are the
operator's to judge.

**`ffmpeg -pix_fmt gray` applies a limited->full range expansion.** Every PSNR
measured against it is junk. Take the luma plane raw from `-pix_fmt yuv420p`
instead. **Validate the yardstick with an unscaled control**: a hardware HEVC
decode must be bit-exact against software. `gray` gave 28.7 dB; raw luma gave
99.0 dB.

**A symmetric ratio cannot validate a scaler.** Two separate bugs — the H/V
field order in the geometry registers, and which coefficient bank drives which
axis — are both invisible at 2x/2x because the two axes hold identical values.
Fixing one of them alone produced a perfect-looking symmetric result and
**5.38 dB** asymmetric. Always test an asymmetric ratio.

**A null result from a test that cannot discriminate is not evidence.** An early
test of coefficient bank order moved 0.2 dB and read as "order does not matter".
It was run with bucket-averaged coefficients, where both banks held nearly the
same filter. With sharply different banks the same test showed a 12.8 dB swing.

**Check chroma, not just luma.** A wrong `OFFSET_ADDR_SECOND_OUT` puts the
10-bit 2-bit plane inside the chroma plane, which luma-only PSNR cannot see.

**Verify what you saved is what you tested.** The working sources kept in
`local/.../*.scaler-working` had accumulated probe scaffolding — a 2.5 MB
byte-by-byte poison scan on every fourth decode, writes to four unused address
registers, and stale comments that would have silently reverted patch 0117.
Diffing against the series head before generating 0118 caught all of it.

## Reproducing the measurements

Board is reachable at `192.168.4.1` over its own WiFi AP. VAAPI needs
`LIBVA_DRIVER_NAME=v4l2_request LIBVA_DRIVERS_PATH=/usr/lib/aarch64-linux-gnu/dri`
or `vaInitialize` fails with a misleading `Device creation failed: -5`.
Test clips are in `/root/video-test`; `tools/video/cedrus-compose-probe.c`
injects a compose rectangle and dumps a completed buffer — rebuild it on the
board from the tree copy, the one there goes stale.

Kernel builds are `ARCH=arm64 LLVM=1` (clang). There is no
`aarch64-linux-gnu-gcc`, and trying it wipes `include/config/auto.conf`.

The build tree under `build/` is a derived artifact keyed by a digest of the
patch inputs; it currently predates 0115-0119 and will be regenerated by the
next `tools/build/build.sh kernel` run.
