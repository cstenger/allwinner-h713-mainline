# Stage 5 install (2026-10-24)

* install.log: `sh install-hdmi-video.sh` on production boot; ring enabled,
  video unit started by udev, 61 fps; panel switched to HDMI.
* cold-boot-cable.log: cold boot with the cable in -> logo, console, HDMI
  (operator). signal owner done 19.4 s, bridge 19.9 s (no signal yet),
  locked 20.8 s, video unit 20.85 s; NRestarts 0; speaker active. PASS.
* warm-reboot.log: `systemctl reboot` from HDMI. Shutdown: video stopped
  first, console flashed back (operator), panel off. Boot: logo + console,
  no HDMI: U-Boot's production warm path does not set
  /chosen/h713,hdmi-boot-v1, so capture/signal/speaker/ring all skip
  (ConditionPathExists unmet); port 1 state 1; PC dropped HDMI-A-1. As
  design 6 expects for the warm fallback; HDMI after a warm reboot needs the
  shared warm-startup work in U-Boot. No panel-black.
* cold-boot-output-off.log: cold boot meant to start with the PC output off,
  but the PC re-enabled HDMI-A-1 itself on the board's hotplug: bridge 20.4 s,
  locked 21.2 s, video 21.25 s (same as the cable-in case). The
  console-until-output-on path was shown at runtime in stage 3 instead.
* Soak: 768 s of video since boot, 45863 frames (59.7 fps), 0 rejected,
  2 overwritten, NRestarts 0, speaker active. PASS.
