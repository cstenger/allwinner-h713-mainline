# Stock capture session — operator sheet (2026-10-01)

The run order for [vendor-capture-plan.md](vendor-capture-plan.md). **Who** says
who acts: *Claude* runs commands on the host, the *operator* touches the board.
Every operator look or touch is its own turn: Claude asks, stops, and waits
for "ready"/"done" before running anything else.

Host tools: `tools/stock/capture-session.sh` (adb driver),
`tools/stock/stock-capture.sh` (runs on the board, read-only),
`tools/stock/capture-summary.py` (prints each case's result straight away),
`tools/mips/elog-parse.py` (decodes the firmware log).
Everything lands in `local/h713-lab/stock-capture-20261001/`.

## 0. Prep — done on the host 2026-10-01

| Check | Result |
| --- | --- |
| Restore SPL returns the board to what runs now | **yes**: LBA `0x10` on the board is byte-identical to the payload inside `build/out/h713-restore-spl.bin` (Aug 25 SPL). The plan's "STALE" came from comparing against `build/out/u-boot-sunxi-with-spl-ddr3.bin` (Aug 29), which was **never installed** — do **not** regenerate from it |
| Vendor boot0 at LBA `0x100` | intact, byte-identical to `local/stock-boot/boot0-board-b-emmc-sector16.bin` |
| `super` / `boot_a` / `vendor_boot_a` / UDISK | `gDla` at +4096 / `ANDROID!` / `VNDRBOOT` / f2fs |
| `misc` | A/B control block plus a **left-over RescueParty request** (`--prompt_and_wipe_data`, command field empty). See §2 |
| Panel block `0x051c0000` | 1 KiB of registers (everything from `+0x400` reads zero), read cleanly on our Linux |
| New capture modes | dry-run on our Linux under `dash`: address lists line-for-line identical to the 08-31 stock reference; gating skipped the powered-down VE/AV1 |
| elog under stock | **not enabled.** The vendor FAT (`bootloader_a`) still has `mode=1 level=1`; only ours (`bootloader_b`) has `mode=2 level=5`. Same `display.bin` on both. Needs the decision in §1 |

## 1. Decision before switching: enable the elog on the vendor side

Two bytes in `bootloader_a:/mips/display_cfg.xml` (byte 4642 `'1'→'2'`, byte
4668 `'1'→'5'`, 0-based), written from our Debian, reverted the same way
after the session. That is exactly our own proven setting, on the same
firmware binary. Without it the window layer's account of every case
(`wce_panel` border widths, `wce_proc` ratios, `win_mgr` aspect handling)
is not captured — only registers.

Proof it took: `capture-session.sh baseline` reads the cfg the firmware
received back from DRAM (`0x4be01000`) and prints `mode`/`level`.

## 2. Switch to stock

1. *Claude*: confirm our Linux is up and the console is on the panel
   (positive control). Then `tools/serial/reboot-to-uboot.py`, and
   `tools/serial/console.py 'run switch_vendor'` — watch it print the eGON
   guard result.
2. *Operator*: **unplug the USB OTG cable** (it back-powers the board), then
   power-cycle. Wait for the Android launcher on the panel. Say "launcher".
   - If the panel shows Android **recovery** ("Can't load Android system /
     Try again / Factory data reset") — that is the RescueParty left-over in
     `misc`. Choose **Try again**. **Never Factory data reset**: it wipes
     UDISK's Android state, including the adb authorisation this session
     depends on.
3. *Operator*: plug USB back in. *Claude*: `capture-session.sh check`.

## 3. Baseline

*Claude*: `capture-session.sh push`, then `capture-session.sh baseline`.
Expect `loaded cfg: mode 2 / level 5` (if §1 was approved) and
`firmware text == board-b display.bin: True`. If the firmware is **not** the
FAT one, the elog address is unproven: keep capturing registers, ignore elog.

## 4. Files — per file, two turns

| Turn | Who | What |
| --- | --- | --- |
| a | Claude | `capture-session.sh case <file>`: starts it, takes an early elog at 3 s, then two full samples 5 s apart around the interrupt window, and prints the summary |
| b | Operator | photograph the **whole** projected picture, all four card borders in frame, roughly head-on (the measurement rectifies keystone and angle away). Say "done" |
| — | Claude | `capture-session.sh stop` |

Clips run 180 s, so a slow turn is fine. **The stock player auto-advances
through `/sdcard/Movies`** when a clip ends (found 2026-10-01: it walked
unattended into the rotation set), so after 180 s the panel shows the *next*
file. Claude announces each case *before* starting it, so the operator is in
the room, and stops the player after the photo. Photos are matched to cases by
time (`out/cases.log`); drop them in `local/h713-lab/stock-capture-20261001/photos/`.

**Tier A — the questions that block plans. Do these first.**

| # | File | Question |
| --- | --- | --- |
| A1 | `1b-h264-1280x720.mp4` | native control: must reproduce the 08-31 values |
| A2 | `05-av1-1080.mp4` | **does stock show 1080p AV1, and what scales it?** `cedar_dev` rate > 0 while `sunxi_go_ctx` decodes = a VE memory-to-memory path |
| A3 | `04-vp9-1080.webm` | VP9 1080p downscale: VE TOP1 (`+0xf00`) programming |
| A4 | `01-h264-1080.mp4` | H.264 downscale reference against our 0098-0111 route |
| A5 | `11-h264-852x480.mp4` | the firmware's known 852x480 recipe, now on stock |
| A6 | `13-h264-352x288.mp4` | 4:3 → borders left/right: `wce_panel` widths, centring |
| A7 | `10-h264-640x360.mp4` | exact 2x upscale |
| A8 | `20-vp9-rc.webm` | size change mid-stream: run `case`, then `state 20-vp9-rc-s2` at ~40 s, `-s3` at ~70 s, `-s4` at ~90 s (segments 640x360 / 1280x720 / 352x288 / 640x360 at 0-30-60-75-105 s) |
| A9 | `30-h264-720-rot90.mp4` | rotation: which block rotates |
| A10 | `32-vp9-720-rot90.mp4`, `33-av1-720-rot90.mp4` | rotation for the codecs ours cannot rotate; `cedar_dev` rate on the AV1 one |

**Tier B — if time allows.** `02-hevc-1080`, `03-hevc10-1080`,
`06-av110-1080`, `12-h264-960x540`, `14-h264-640x480`,
`15-h264-720x576-sar16x15`, `16-h264-1000x600`, `17-h264-2560x1080`,
`18-h264-1440x1080`, `19-vp9-852x480`, `1a-av1-852x480`, `21-hevc-r01`
(segments at ~0/24/48 s), `31-hevc-720-rot90`, `40-hevc10-hdr10-720`,
`41-av110-720`.

**Tier C.** The remaining rotations (`rot180`, `rot270` for each codec),
`07-mpeg2-1080i.ts` (the player may refuse it; a refusal is a result).

## 5. Menus — one 16:9 and one 4:3 file

With `11-h264-852x480.mp4`, then `14-h264-640x480.mp4` playing:

1. *Operator*: note the **starting** picture-aspect mode, projector
   orientation and keystone, to restore them at the end.
2. For each aspect mode the player or settings offer (Auto / 16:9 / 4:3 /
   Zoom / Full or similar): *operator* selects it and says which;
   *Claude* `capture-session.sh state <file>-aspect-<mode>`; *operator*
   photographs.
3. Projector orientation: front, rear, ceiling, rear-ceiling — same loop,
   tag `orient-<name>`.
4. One keystone step — tag `keystone-1`.
5. *Operator*: restore the starting settings.

## 6. Wrap-up on stock

*Claude*: `capture-session.sh logs final`, `capture-session.sh pull`.

## 7. Return to our stack

1. *Operator*: power off, **USB OTG plugged in**, hold the **FEL button**
   while powering on, release. Say "FEL".
2. *Claude*: `external/sunxi-tools/sunxi-fel version`, then
   `external/sunxi-tools/sunxi-fel -p spl build/out/h713-restore-spl.bin`.
   The UART must show `=== H713 SPL RESTORE ===` and `wrote 64/64 RESTORED-OK`.
3. *Operator*: **unplug USB**, power-cycle.
4. *Claude*: Debian up over ssh, console on the panel, `/dev/dma_heap/system`
   present, LBA `0x10` byte-identical to the restore payload again.
5. *Claude*: if §1 was applied, revert the two bytes in `bootloader_a` and
   read them back.

## Rules (from the plan)

- Read-only under stock: no `hidtvreg-poke`/`-fill`/`-replay`, no writes to
  `/dev/hidtvreg`. The MIPS shell is not used under stock (it writes a ring).
- Never read `0x069xxxxx` or `0x0709xxxx`.
- `tools/reclaim-android.sh` must not run.
