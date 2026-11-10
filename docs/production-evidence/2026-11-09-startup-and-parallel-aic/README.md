# Startup timeline and parallel AIC startup — November 9

## Baseline cold timeline (boot `2b825f9d`)

Installed: single display-firmware launch (`d2e8cb7a`), `hpd-event-v1`,
source-power V4L2, global AIC8800 module loading. Passive UART plus the
board journal. The PC's HDMI output was disabled, so the source lock was not
measured. [Parsed result](baseline-cold-timeline.json).

| Milestone | Time |
| --- | ---: |
| U-Boot proper / startup script | SPL +1.95 / +2.15 s |
| Logo | SPL +6.16 s |
| Starting kernel | SPL +8.71 s |
| Kernel modules loaded (AIC8800 4.02-6.59 s inside) | Linux 6.75 s |
| sysinit.target | Linux 8.03 s |
| HDMI prepare | Linux 8.11-14.14 s |
| EDID/HPD ready | Linux 14.90 s |

The global AIC load held `systemd-modules-load` for ~2.7 s, and every HDMI
unit waits for sysinit behind it.

## Parallel AIC startup: qualified on three cold boots

The 11-05 change (`h713-aic8800-modules.service`, aliases blacklisted; see
[the experiment](../2026-11-05-parallel-wifi/README.md)) was reinstalled
unchanged (manifest `5a90c744`). It had been rolled back only to keep the
first-advert investigation clean, which closed with `hpd-event-v1`.
[Per-boot results](parallel-aic-qualification.json).

| Cold boot | HDMI prepare starts | EDID/HPD ready | Video active |
| --- | ---: | ---: | ---: |
| Baseline | 8.11 s | 14.90 s | ~16.3 s (expected) |
| 1 (`0f1cecc5`) | 4.60 s | 12.45 s | 13.87 s |
| 2 (`addba87b`) | 6.17 s | 13.83 s | 15.82 s |
| 3 (`648e97ae`, after a power cut) | 4.68 s | 12.49 s | 13.91 s |

All three: no failed units, hotspot up, `hci0` UP RUNNING, HDMI locked with
no re-advertise pulse. The shutdown of boot 1 under the new configuration
was clean. Operator view of boot 1: logo ~9 s and desktop ~25 s after power-on.

Boot 2 was slower because `systemd-growfs-root` took 1.70 s (usually
~0.15 s) and early tmpfiles waited behind it. The partition is already full
size; disabling the resize on the product image is a candidate follow-up.

The rootfs builder now emits this configuration by default.

## Early panel off (U-Boot 0005)

`h713_disp panel-off` enters the same verified off state as the 3 s hold
(MIPS parked, signals quiet, reset and supply read back) at the start of the
script; the logo step re-verifies it and waits only the remainder. The hold
is not shortened. The current series rebuilt reproducibly to the installed
proper (`7e7835d0`); the candidate is `33bc73c8`, same size, no new warnings.

Installed with the unchanged `install-single-launch.py` (proper, then a warm
reboot on the old script: healthy, then the script). Cold boot `888e9f1d`:

| From SPL | Before (parallel AIC boot 1) | Early panel off |
| --- | ---: | ---: |
| Panel off state entered | ~3.1 s | 2.25 s |
| Logo | 6.01 s | 5.26 s |
| Starting kernel | 8.56 s | **7.76 s** |

U-Boot reported the panel had been off for 0.837 s when the logo step reached
the hold, and waited 2.163 s more. Linux: no failed units, hotspot and `hci0`
up, EDID/HPD ready 12.48 s, locked 13.82 s, video 13.88 s, no re-advertise
pulse. Video starts about 21.6 s after the first SPL output.

## Root filesystem grown once, not every boot

`x-systemd.growfs` made systemd run a no-op online resize of the root before
local-fs on every boot (usually ~0.15 s; 1.70 s on parallel-AIC boot 2). The
release image is deliberately small, so growth is still needed once:
`h713-rootfs-grow-once.service` runs `systemd-growfs /` after local-fs, off
the critical path, then writes `/var/lib/h713-rootfs-grown`. A freshly
written image has no marker and grows on its first boot.

Installed on the board (fstab backup under
`/var/lib/h713-hdmi-startup/growfs-once-*`) and checked over two warm
reboots: reboot 1 ran grow-once at 4.67-5.35 s ("Successfully resized"),
created the marker and started video at 13.97 s; reboot 2 skipped it by
condition and started video at 13.93 s. `systemd-growfs-root` no longer runs,
root stays `rw,noatime` at 2.7 GB, no failed units. In these boots sysinit
(~4.5 s) was gated by udev coldplug, so the typical saving is small; the
change removes the 1.7 s outlier and the per-boot resize.
