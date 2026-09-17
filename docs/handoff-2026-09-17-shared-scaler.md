# Handoff — H713 shared H.264 / HEVC scaler, 2026-09-17

**Current state for Claude:** patches 0116a, 0120, and 0121 are complete and
hardware validated. Both codecs share arbitrary-ratio scaling; rotation stays
out by user decision. Patch 0121 fixes the remaining compliance failure and
makes TRY_EXT_CTRLS free of format changes. Compliance is **49/49, zero warnings**.
See [the control validation record](reference/cedrus-controls-2026-09-17/README.md)
for the final 53-capture regression and installed module. The PSNR table below
records the preceding 0120 validation; all 51 common capture checks retain
byte-identical active pixels after 0121. No further implementation work is
needed to reach 49/49.

Patch **0120** replaces H.264's power-of-two SDROT scaling with the same
VE+0xf00 polyphase scaler used by HEVC. Rotation is no longer exposed for
either codec. The implementation is in the patch series, not in the local
`*.scaler-working` snapshots or the temporary development trees.

This supersedes the next-step recommendations in
[the September 16 handoff](handoff-2026-09-16-h265-scaler.md): H.264 can use this
block, a per-codec power-of-two quantizer is unnecessary, and keeping SDROT
for rotation is no longer a requirement.

## Why the previous H.264 experiment failed

The missing piece was routing, not the scaler coefficients or its geometry.
H713's `local/h713-lab/ve-extract/libs/libawh264.so` exports
`H264ConfigNewScaler` in `.dynsym` at Thumb address `0xdb71`, size 776.
Disassemble from `0xdb70`, with file offset `0xcb70` (VA minus `0x1000`).
The Thumb bit and ELF section/file offset distinction both matter.

Its route is:

| Register | H.264 polyphase setting |
| --- | --- |
| `H264_CTRL`, VE+`0x220` | clear bit 9 (SDROT), set bit 11, clear bit 8 (MC no writeback) |
| `VE_CHROMA_BUF_LEN`, VE+`0xe8` | set bit 29, select extended secondary format in bits 31:30 |
| `VE_PRIMARY_OUT_FMT`, VE+`0xec` | primary NV12 in bits 6:4, secondary NV12 in bits 2:0 |
| `VE_SECONDARY_FB_LINE_STRIDE`, VE+`0xcc` | luma pitch and half pitch for chroma |
| H.264 secondary addresses, VE+`0x244` / `0x248` | raw byte addresses; HEVC uses addresses shifted by 8 |

Key instructions: `0xdc0e` clears `0x200`, `0xdc16` sets `0x800`,
`0xdc1e` clears `0x100`, and `0xdc48` sets `0x20000000` in the global register.
The old experiment retained the SDROT route and produced roughly 11 dB.
With the recovered route, H.264 2× scaling measures 55.33 dB.

The shared block retains the already validated geometry: high half is width /
horizontal, low half is height / vertical; horizontal coefficients precede
vertical coefficients. The coefficient generator and generated table are
unchanged. Every picture programs its geometry, both coefficient banks, and
its context's line buffer, so concurrent codecs can share the hardware.

## Negotiation and storage

- On H713, H.264 and HEVC NV12 CAPTURE `S_FMT` select arbitrary even output
  dimensions between 1× and 4× downscale independently on each axis.
- `TRY_FMT` returns normalized sizes without changing the active selection.
  `ENUM_FRAMESIZES` exposes a stepwise range for NV12. Other raw formats retain
  their full-size primary output.
- `S_SELECTION(COMPOSE)` selects the active rectangle in the separately
  negotiated capture canvas. It preserves a larger canvas and pitch, supports
  LE/GE constraints, and rejects offsets and changes after buffer allocation.
- Scaled heights need only be even. Secondary pitches are aligned to 32 bytes.
  Full-size primary output retains the normal macroblock storage padding.
- Reconstruction stays full size in private per-capture buffers, including
  Main10 side data. A pre-allocation HEVC SPS refreshes both capture and
  reconstruction sizing when declaring bit depth.
- The new datapath is gated to the H713 root compatible, rather than assuming
  that every SoC using the H6 Cedrus DT compatible has this scaler.

**HEVC alignment discovery:** secondary chroma is corrupted when its base is
32 modulo 64. For example, 258×242 with pitch 272 gave U/V PSNR 9.22/5.32 dB;
258×244 or pitch 288 works. This affects 8-bit HEVC too. A 32-byte pitch and
even canvas height guarantee a 64-byte aligned chroma base. Main10's packed
2-bit pitch additionally uses `ALIGN(DIV_ROUND_UP(width, 4), 32)`; truncating
width/4 loses samples for widths such as 258.

**Coded size is not visible size:** the VA shim configures the 1080p H.264
vector as 1920×1088 from its allocated surfaces. Asking for 1920×1080 therefore
scales, rather than exercising the unscaled path. Scaling that source to
1280×720 includes the coded padding. Input crop negotiation and playback
metadata remain separate work; do not call this a crop-aware display pipeline.
The regression tool's unscaled mode performs no sizing ioctls and compares the
visible planes from the full coded canvas.

## Series repair and build

A clean build of the previous series failed at 0117: the retained development
tree contained HEVC secondary-output prerequisites that were never in the
series. **0116a** recovers those prerequisites before 0117. One extra blank
context line in 0118's allocation hunk was corrected. Its implementation was
not otherwise changed. With 0121, the series contains **88 resolving entries**.

`JOBS=12 tools/build/build.sh kernel` applies the entire series from the pinned
6.18.38 tarball and builds Image, both DTBs, all modules, and the bench FIT.
The final tree is:

```text
build/linux-6.18.38-2aa602684a789bcb98086f3365e656d2d013baa10186142d98e9d198aa877463
```

The final installed and loaded module MD5 is
`772c6a46b668baafb98dcf00ddb15429`. No kernel reboot or FIT flash was needed.
The preceding 0120 module (`b167f116f54201bf2069c2a96d122722`) and its
`build/linux-6.18.38-23b53a9c740b61e2c06ab0e904d16726f688219b201e3cd96b426211db861334`
tree are retained for rollback. `build/scaler-dev` and the intermediate clean
build were removed; all build trees are derived artifacts, not source of truth.
The installer kept rollback modules under `/mnt/media-data/h713-module-backups`.
The pre-session module is also saved on the host as `/tmp/h713-pre-scaler.ko`,
MD5 `049f5713e5de562c3b063d3e009504d3`.

## Validation

Hardware results use raw NV12 software references, with stride and canvas
height accounted for, and score all three planes. These numbers measure
agreement with software bicubic scaling, not an absolute quality benchmark.

| Case | Y / U / V PSNR, dB |
| --- | --- |
| H.264 1280×720 → 640×360 | 55.33 / 49.97 / 43.48 |
| H.264 → 320×180 | 45.02 / 41.28 / 33.02 |
| H.264 → 640×180 | 47.85 / 44.65 / 38.18 |
| H.264 → 960×540 | 43.88 / 43.65 / 36.86 |
| H.264 → 854×478 | 42.98 / 38.20 / 35.73 |
| H.264 coded 1920×1088 → 1280×720 | 45.60 / 99 / 99 |
| HEVC 1280×720 → 640×360 | 55.41 / 49.96 / 43.51 |
| Main10 640×480 → 320×240 | 51.77 / 48.34 / 42.37 |
| Main10 → 258×242, pitch 288 | 35.59 / 29.32 / 28.37 |
| Generated H.264 I/P stream, frame 60 → 854×478 | 42.79 / 36.89 / 35.20 |
| Generated Main10 I/P stream, frame 60 → 258×242 | 35.05 / 28.25 / 27.42 |

The 4× filter is not a universal quality improvement: the old H.264 shifter
measured 46.42 dB on that case, versus 45.02 here. Consolidation gives better
2× filtering and arbitrary ratios, with no rotation path to maintain.

`cedrus-scaler-api-test.c` passes format/selection state isolation, LE/GE,
invalid rectangles, larger pitch, buffer-busy guards, codec reset, early
Main10 sizing, and absence of the rotate control. Final compliance with 0121 is
**49/49, zero warnings**. `cedrus-control-test.c` passes valid fresh SPS defaults,
pure Main10 TRY, busy-depth guards, committed sizing, and invalid SPS rejection.
The two control bugs were reproduced independently before fixing them.

The preceding 0120 51-capture pixel matrix passed with no DMA overruns or kernel faults.
All unscaled 8-bit vectors are bit-exact. Three additional Main10 captures
validate sizing API equality and a later P-frame; these also pass. The reusable
tool combines those checks into one run (53 captures, avoiding the repeated
Main10 format capture).

The final 0121 **53-capture** matrix passes with no DMA overruns or kernel faults.
Current logs and results are in [the control validation record](reference/cedrus-controls-2026-09-17/README.md),
with compressed captures at `/mnt/media-data/cedrus-control-fix/scaler`.
The pixel matrix covers five H.264 and seven HEVC vectors scaled and unscaled,
S_FMT/COMPOSE pixel equality, non-macroblock sizes, larger pitches, concurrent
H.264/HEVC contexts, and a later P-frame reconstruction check. It enables
64 KiB DMA guards and restores their previous setting afterwards. Logs,
JSON measurements, and losslessly compressed `.nv12.gz` captures are under `/mnt/media-data/scaler-final-tests`
and `/mnt/media-data/scaler-main10-final`. [Preserved measurements and logs](reference/shared-scaler-2026-09-17/README.md)
are also stored in the documentation directory.
A true unscaled 1080p H.264 capture also matches the saved baseline byte for
byte; active-plane MD5 `405c1695b95450fac7a01fccd28e4b25`.

Reproduce on the board after copying the four tools:

```sh
cc -shared -fPIC -O2 -Wall -Wextra -Werror -o cedrus-compose-probe.so cedrus-compose-probe.c -ldl
cc -O2 -Wall -Wextra -Werror -o cedrus-scaler-api-test cedrus-scaler-api-test.c
./cedrus-scaler-api-test /dev/video0
cc -O2 -Wall -Wextra -Werror -o cedrus-control-test cedrus-control-test.c
./cedrus-control-test /dev/video0
v4l2-compliance -d /dev/video0
python3 cedrus-scaler-check.py --probe "$PWD/cedrus-compose-probe.so" \
  --expected-md5 772c6a46b668baafb98dcf00ddb15429
```

The LD_PRELOAD adapter is a headless measurement tool: VA surfaces still carry
their original coded metadata. Do not hwdownload or display its scaled
surfaces. Actual players must negotiate and propagate the scaled dimensions.

## Next work

1. **Integrate real scaled surfaces into playback.** Start in the seven-patch
   `patches/libva-v4l2-request/series` and three-patch `patches/mpv/series`.
   Negotiate CAPTURE size/COMPOSE before allocating buffers, and propagate actual
   dimensions, pitch, plane offsets, and visible rectangle through VA export,
   FFmpeg's DRM_PRIME descriptor, mpv, and the KMS framebuffer. Keep coded SPS/DPB
   geometry full size. The measurement LD_PRELOAD adapter is not a player solution.
   First target H.264 1080p to the 1280×720 panel, then HEVC/Main10.
2. **Resolve coded padding and crop.** H.264's 1920×1088 storage versus 1920×1080
   visible image is the known trap. Establish whether the hardware scaler can
   honor input crop; do not assume this driver exposes it. Validate aspect ratio
   and the bottom edge on actual panel output. Preserve headless pixel controls.
3. **Validate playback, then simplify the display path.** Require operator
   `ready`/`watching` before panel tests. Check picture, sound/sync, long playback,
   seeks, resolution changes, and return to the console. Only after that retire
   display-side scaling patches 0098/0103/0106/0108/0111 where dependencies permit;
   they remain in the series today. Do not remove them merely because headless
   scaler tests pass. The 1×–4× range remains until other ratios are validated.
4. **Prepare upstreamable changes separately.** Split the generic SPS/TRY fix
   from H713 scaler routing and downstream playback policy, with the current
   compliance reproduction and measurements. Do not infer support on other SoCs
   from their shared H6 DT compatible.

## Decisions and limits to preserve

- Rotation remains disabled for both codecs by explicit user choice. Do not
  revive SDROT or invent a composite rotation workaround.
- SPS support already exists: userspace parses SPS and submits stateless controls.
  0121 repairs its default and state handling; it does not add a kernel parser.
- Keep 4:2:2 unsupported. [The vendor-library assessment](reference/chroma-422-assessment-2026-09-17.md)
  shows HEVC rejection and H.264's constant 4:2:0 hardware setting. This is not
  proof of silicon impossibility; do not rewrite it as such. 4:2:2 is unnecessary
  for scaling or compliance, and no board probe was performed.
- The 4× filter is slightly worse than the old shifter on one measured case;
  consolidation and arbitrary ratios are the benefit, not universal PSNR gains.

## Resume and board state

Use the patch series as source of truth. The old ignored `*.scaler-working`
snapshots contain obsolete probe scaffolding. Read the measurement traps in
the September 16 handoff before devising new experiments. Installer success
alone is insufficient: compare installed module identity and successful reload.

Board: `root@192.168.4.1`, bench DDR3, kernel 6.18.38, decoder idle,
`dma_guard=0`, rootfs 93% used. Always use `ssh -F /dev/null` and
`scp -F /dev/null`; the host's default SSH configuration fails permissions checks.
In this session `/mnt/media-data` was **on rootfs**, not a separate mounted
filesystem. Check `findmnt` and `df` rather than trusting older mount notes.
Keep raw captures losslessly compressed. `/var/tmp` and `/root/fits` are possible
cleanup candidates, but were not deleted. No FIT was flashed or reboot requested.
Warm display reboot limitations from prior handoffs still apply.

The documentation, patches, tools, and compact evidence logs are committed;
proprietary vendor binaries and bulky generated captures remain ignored/local.
To resume, check `git status`, verify the series and current module identity,
then pursue playback integration instead of rerunning the completed matrix.
