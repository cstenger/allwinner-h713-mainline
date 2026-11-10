# Blank panel on the cold HDMI startup path

Symptom: after integrating HDMI capture into cold startup (7fba9fc), the panel
showed only a dim black glow — no boot logo, no Linux console.

## Isolation (2026-10-15)

- Linux side healthy: 11/12 handoff registers matched the 2026-08-07 capture;
  the AFBD source `0xffc00000` is the expected IOVA. PF6/PH16 high, PB5 lamp high.
- TCON chroma generator (`panel-test 0x34 tcon-chroma`): **visible** → panel,
  LVDS, power and timing hardware fine.
- `vendor-logo-chroma` in U-Boot: **visible** → framebuffer path fine.
- Warm path Linux (no MIPS relaunch / SetSource): console and red fill
  **visible** (`warm-working.txt`).
- Cold path dump (`cold-blank.txt`) differs in the TCON timing block:

| reg | working | blank |
|---|---|---|
| 0x0588001c | 00000004 | 00000002 |
| 0x05880020 | 02F80550 (1360x760) | 04650898 (2200x1125) |
| 0x05880024 | 02D00500 (1280x720) | 04380780 (1920x1080) |
| 0x05880028..30 | 720p porches | 1080p porches |

The live MIPS firmware relaunched by `mips-comm-trace 0x34` / SetSource(3)
reprograms the TCON to 1080p; the 720p panel cannot lock. U-Boot's logo path
re-latches 720p only after quiescing the firmware, and the cold path never
re-latched after relaunch.

Live confirmation: replaying `h713_disp_latch_panel_timing()` from Linux on the
blank board made the red fill visible immediately; capture and speaker stayed
active.

## Fix

`tools/hdmi/build-startup.py`: the `source` stage re-latches 720p (mode[2:0]=4,
timing, +0x0c bit-0 pulse) after the last firmware call and before `bootm`,
with readback guards. Arithmetic-only `setexpr`. Chain tested at a real U-Boot
prompt from a simulated 1080p state. Installed script-only
(`startup-install.log`; the bundle took the installed `h713-hdmi-signal.ko`
because the local rebuild differed). FAT script SHA-256
`3539932ea88ae862124c49a22305415c8d302f4a09e9dbbcce15f4f9b5452543`.

## Cold-boot verification (2026-10-16)

Boot `8cc0f590-026e-4734-b111-a113063a9a37`: operator saw logo and console;
`h713,hdmi-boot-v1` present; capture/signal/speaker active; TCON still 720p
at 12 min uptime. Operator reports the logo flashing in and out during boot
(slo-mo `local/lcd-photos/test_103/IMG_1048.mov`) — tracked separately.
