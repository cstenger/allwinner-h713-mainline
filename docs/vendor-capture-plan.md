# Vendor-stack capture session — plan (written 2026-10-01, for the next session)

Boot the stock Android stack, play a prepared set of files, and record what the
vendor programs for **scaling, letterboxing, rotation and orientation**. Then
return to our Linux. Read-only throughout: nothing is written to any register
under stock.

Why now: three open questions can only be answered by watching the vendor
drive the hardware, and each blocks a plan.

| Question | Blocks |
| --- | --- |
| How does stock fit sub-720p video, and with which registers (AFBD source size, composition line buffers, proc upscaler, panel border overlays, picture position)? | `docs/letterbox-plan.md` Phases 0–3: a known-good recipe instead of hand-derived values |
| Does stock show **1080p AV1** on the 720p panel, and what scales it? A VE interrupt that ticks while only the AV1 core decodes would reveal a memory-to-memory VE path | AV1 above 720p (today: impossible on our stack) |
| How does stock **rotate** (file rotation metadata) and **flip/mirror** (projector orientation menu)? What does `VideoEngineRotatePicture` drive? | rotation for VP9/AV1/HEVC (ours is H.264-only); ceiling/rear projection |
| What does stock program for **VP9 scaling** (`libawvp9HwAL.so` has `VP9ScaleCopyCoef`, `CheckSecScaleValid`)? | VP9 1080p → 720p on cedrus, the cheapest remaining win |

## What already works (2026-09-29 round trip — reuse it)

- The partitions coexist: p26 `linux` (Debian, ext4), p27 `UDISK` (Android
  userdata, f2fs), `boot_a` = `ANDROID!`, `vendor_boot_a` = `VNDRBOOT`
  (re-checked read-only 2026-10-01). Booting Android destroys nothing.
- To stock: `run switch_vendor` at our U-Boot prompt, then a power cycle
  (`docs/flash.md` Methods 5/6, `tools/boot-switch.sh`).
- Back: FEL button + `external/sunxi-tools/sunxi-fel -p spl build/out/h713-restore-spl.bin`,
  then a power cycle.
- Capture: `adb` with **no root**. `/dev/hidtvreg` is world-rw, and
  `tools/display/hidtvreg-read.c` (static ARM) reads any address, DRAM included.
  `tools/stock/stock-capture.sh` does gated snapshots (`snap`, `logs`, `irq`,
  `ir`). Results so far: `local/h713-lab/stock-capture-20260929/`.
- Playback: `am start -n com.softwinner.TvdVideo/.TvdVideoActivity -a android.intent.action.VIEW -d file:///sdcard/Movies/<f> -t video/<type>`
  (fall back to the `content://media/...` URI if `file://` is refused).

## Prep — host side, before touching the board (do all of it first)

1. ~~Regenerate the FEL restore SPL. It is STALE as of 2026-10-01.~~
   **Corrected 2026-10-01 (prep run): the restore SPL is NOT stale — do not
   regenerate it.** The check below compares against `build/out`, and the
   Aug 29 SPL there was never installed. The test that matters is whether the
   restore returns the board to what runs now, and it does: LBA `0x10` read
   from the board is byte-identical to the payload embedded in
   `build/out/h713-restore-spl.bin` (Aug 25 SPL, the one that brought Debian
   back on 08-31 and 09-29). Regenerating from `build/out` would install a
   *different*, never-run SPL — the warning in `handoff-2026-08-29.md`.
   ```bash
   # the right check: board LBA 0x10 vs the restore payload
   ssh root@192.168.4.1 'dd if=/dev/mmcblk0 bs=512 skip=16 count=64 2>/dev/null' > lba10.bin
   python3 -c "print(open('lba10.bin','rb').read() in open('build/out/h713-restore-spl.bin','rb').read())"
   ```
2. **Check `super`'s LP magic** (`gDla` at +4096) and that `misc` is unchanged
   since 09-29, read-only from our Linux.
   *Done 2026-10-01:* `gDla` present, `boot_a`/`vendor_boot_a` intact, UDISK
   f2fs. `misc` is no longer all zeros (it was on 08-26): A/B control block
   at `+0x800`, virtual-A/B message at `+0x8000`, and a **left-over
   RescueParty request** at `+0x40` (`recovery --prompt_and_wipe_data
   --reason=RescueParty`) with an empty command field. No 09-29 logcat
   mentions RescueParty, so it predates or postdates those captures. If
   stock boots into recovery: **Try again, never Factory data reset**.
3. **Build the media set** (`tools/stock/make-capture-media.sh`, new). Every file
   **needs an audio track**: `TvdVideo` rejects files without one. Use a
   geometry card (border ruler, circles) so panel photos measure position and
   scale, and make each clip ≥ 40 s so snapshots land in steady state.

   | Group | Files |
   | --- | --- |
   | Downscale | 1080p H.264, HEVC Main, HEVC Main10, **VP9**, **AV1 8-bit**, **AV1 10-bit**; MPEG-2 1080i if the player takes it |
   | Fit / letterbox | 640x360, 852x480, 960x540 (16:9); 352x288, 640x480 (4:3); 720x576 PAL with SAR 16:15; 1000x600; 2560x1080 (21:9); 1440x1080 (4:3 HD) |
   | Size change | `vp9-rc.ivf` remuxed to WebM with audio and segments stretched to ≥ 15 s; HEVC `r01` as MP4 with audio |
   | Rotation | MP4 with rotate 90/180/270 display matrices for H.264 and HEVC; MKV/MP4 VP9 and AV1 with the same |
   | 10-bit / HDR | HEVC Main10 HDR10 720p; AV1 10-bit 720p (`hbd720` with audio) |

4. **Extend `stock-capture.sh`** with two read-only modes. Keep its rule:
   gated blocks only when the PPU domain, bus gate and reset all say powered,
   and never `0x069xxxxx` or `0x0709xxxx`.
   - `display <label>`: the windows already read safely under stock on
     2026-08-31 (`docs/reference/stock-firmware-blocks-4sample-2026-08-31.txt`):
     composition `0x05000000`, `0x05040000`, `0x050c0000`, route `0x05140000`,
     proc `0x05180000` (4 KiB each), AFBD `0x05600000` (512 B), plus the live
     VideoInfo page (`0x05600098` → address → 65 words).
   - **The panel block `0x051c0000` was NOT in that capture.** Its border
     overlays are the main target, but only the down-scaler
     (`0x0120`–`0x0138`) and selector (`0x006c`) have been read under stock.
     Size it with `tools/mips/block-map.py` and the `PanelWinNode::WriteReg`
     offsets, read that window on **our** Linux first (our driver maps the
     block and reads it every boot), and add only that window to `display`.
   - `ve <label>` (gated on VE power): VE top, the H.265/VP9 engine `+0x500`,
     the **TOP1 scaler `+0xf00`**, and H.264 SDROT `+0x40..+0x48`.
   - `elog <label>`: the MIPS window-manager log ring in DRAM near
     `0x4b272000` (`docs/handoff-2026-09-04-mips-window-layer.md`).
     **This log is the single most valuable artifact**: `wce_panel` prints the
     border widths and windows outright.
     **Corrected 2026-10-01: elog is NOT enabled for the vendor.** The
     09-04 change lives in *our* FAT (`bootloader_b:/mips/display_cfg.xml`,
     `mode=2 level=5`); the vendor's U-Boot loads `bootloader_a`'s copy, which
     still says `mode=1 level=1`. Same `display.bin` on both, so the buffer
     address carries over (it is static data; `display.bin` maps 1:1 onto
     DRAM from `0x4b100000`). Enabling it is a two-byte edit to the vendor
     FAT — an operator decision, see `docs/stock-capture-operator-sheet.md` §1.
     The firmware's received cfg is readable at `0x4be01000` (`fw` mode), so
     the capture proves which setting was live.
   - Dry-run every new mode on **our** Linux first, with `mmio-read`, to check
     that addresses and output format match (the two tools emit byte-identical
     formats on purpose).
5. **Write the operator sheet**: the order of files and menu changes, what to
   look at, and when to say "ready". Every look gets its own turn.

## The session

Budget about 3 hours with the operator present. Cold boots are done with USB
**unplugged** (it back-powers the board); plug it in once Android is up.

1. Our Linux: positive control (console visible), then `run switch_vendor` at
   U-Boot, unplug USB, power cycle. Wait for the launcher.
2. Plug in USB: `adb devices`; push `hidtvreg-read`, the extended
   `stock-capture.sh` and the media (`/sdcard/Movies/`). Capture `idle` once
   (`snap`, `display`, `elog`) as the baseline.
3. For each file, in the sheet's order:
   - start it (`am start ...`) and wait about 8 s for steady state;
   - run `snap`, `display`, `ve`, `elog` twice, 5 s apart (two samples show
     which values move per frame), plus `irq 5` (VE `1c0e000` and AV1
     `1c0d000` interrupt deltas);
   - the operator photographs the panel for geometry
     (`tools/display/measure-panel-photo.py`);
   - stop playback, wait for idle, `snap` again.
4. Questions that need a reading, not just a capture:
   - **AV1 1080p:** if the VE's interrupt count rises while only the AV1 core
     decodes, the VE is post-processing AV1 output, and that is the
     memory-to-memory path we are looking for. Record AFBD's source size: if
     it is 1920x1080 and the panel shows the whole picture, there is a display
     downscaler the scaler census missed.
   - **Rotation:** the same interrupt test for VP9/AV1 rotated files, plus VE
     SDROT/`+0x50` state for H.264/HEVC.
   - **Size change:** `display` + `elog` snapshots inside each segment of
     `vp9-rc` and `r01`.
5. **Menus**, one 16:9 and one 4:3 file: every picture aspect mode the vendor
   menu offers (Auto/16:9/4:3/Zoom/Full or similar), then projector
   orientation front/rear/ceiling/rear-ceiling, and one keystone step. Take a
   `display` + `elog` snapshot after each change, and photograph the panel.
6. `logs` once at the end (logcat, codec state). Then pull everything:
   `adb pull /data/local/tmp/cap/out local/h713-lab/stock-capture-<date>/`.
7. Return: FEL button + the **regenerated** restore SPL, power cycle with USB
   unplugged. Confirm Debian boots, the console is visible, and
   `/dev/dma_heap/system` exists.

## After the session (desk work)

- `docs/reference/stock-capture-<date>/README.md`: for each case, a table of
  what moved and its value, with the `wce_*` log lines beside the registers.
- Feed the letterbox plan's Phase 0 directly: border overlay registers and
  colour, line-buffer descriptors per width, proc programming per ratio, and
  picture position. The formulas then have to reproduce these captures
  before anything is written on our stack.
- VP9 scaling recipe vs our HEVC TOP1 programming (kernel 0118/0120): the
  diff is the patch.
- An AV1 verdict: a scaling path exists (and where), or stock does not scale
  1080p AV1 either.
- Rotation and flip: which block does each, and whether VP9/AV1 rotation is
  reachable.

## Risks and rules

- **Read-only under stock.** No `hidtvreg-poke`/`-fill`/`-replay`.
- Never read `0x069xxxxx` (unpowered capture domain) or `0x0709xxxx`
  (`0x07091000` hard-locks the SoC on a read). Gated blocks only when powered.
- The 2026-08-26 attempt failed before UART with a stale restore SPL; FEL
  recovery itself is verified. Do not start without prep step 1 printing
  `True`.
- `tools/reclaim-android.sh` must **not** run — Android stays as a reference
  until the project ends (operator's decision, 2026-09-29).
- Projector orientation and keystone are user settings stored by Android;
  set them back to the starting values before leaving stock.
