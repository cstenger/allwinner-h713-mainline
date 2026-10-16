# Boot flashes: lamp gating and the warm-path logo

Review: [video-production-review.md](../../video-production-review.md) H1/H3.
Source capture: `local/lcd-photos/test_103/IMG_1048.mov` (slo-mo, cold boot
with the 720p re-latch but no lamp gating): white field at panel power-on
(18.6–19.7 s video), logo dropout across the MIPS relaunch (21.3–24.3 s).

Change (`tools/hdmi/build-startup.py`): PB5 (lamp + fan) low before the panel
bring-up and high once the final frame is latched, on both paths; every
failure branch re-lights it; the warm (GP6-latched) path runs
`h713_disp auto 0x34 logo` again when MIPS status is zero. 11 host tests,
mutation-checked. Installed script-only (`startup-install.log`), FAT SHA-256
`a8cf0522873a5a7d7dd4f8e5220081430c589b2b4a417ddbbf431119cdffde20`.

## Warm reboot (2026-10-16) — PASS

`warm-boot-serial.log` (host-timestamped): latch branch at 14.88 s, PB5=0;
panel power 15.83 s; 720p latched 16.62 s; logo committed and PB5=1 at
16.91 s (lamp dark 2.0 s); kernel 17.93 s; fbcon 19.76 s. Operator: panel went
dark briefly, the logo appeared once with no white flash, then the console.
Before this change a warm reboot left the panel black.

## Cold cycle (2026-10-16) — PASS, one residual

Boot `6a334ed4-d9fb-4166-8085-45d61c53161e`: `h713,hdmi-boot-v1` present;
capture, signal and speaker active; TCON 720p; PB5 lamp high. Operator: audio
works. Slo-mo `local/lcd-photos/test_104/IMG_1049.mov` (video seconds):
lamp on at 0.33 s (reset), off at 8.63 s (script), on at 22.63 s directly onto
the logo; logo steady until the console takes over; no frame-to-frame luma
jump above 2.5 afterwards; peak luma 24 (the white field in test_103 hit 64).
The white field and the relaunch dropout are gone.

Residual, as predicted: lamp on → off → on. The first "on" is U-Boot's
`board_init` (`CONFIG_H713_POWERON_LIGHT_FAN`), before the script runs. Review L2.
