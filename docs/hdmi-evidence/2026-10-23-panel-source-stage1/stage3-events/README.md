# Stage 3 (2026-10-24): staged rule + units — FAILED, root cause fixed

Video: local/lcd-photos/test_110. `board.log` = transitions, unit journal, udev state.

* Staging worked: the bridge loaded locked, its `add` event made the device
  unit ready, systemd started h713-hdmi-video.service 64 ms later, 60 fps,
  desktop on the panel (operator saw it).
* First "output off": signal none at 7244.6, but the unit was NOT stopped;
  the bridge's 1 s EIO backstop ended the stream (7245.6). systemd restarted
  gst 3 times during no-signal (STREAMON -ENOLINK, "Buffer pool activation
  failed"), hit StartLimitBurst=3, and refused every later lock: the panel
  stayed on the console for the rest of the run.
* Root cause: the rule used ATTRS{name} (video node) together with
  ATTRS{signal} (parent). udev requires all ATTRS{} keys of a rule to match
  on ONE device, so neither READY line ever matched; `udevadm info` showed
  no SYSTEMD_READY at all.
* Fix: ATTR{name} for the node; READY=0 unconditionally, then READY=1 when
  ATTRS{signal} is locked*/holding*. Verified on the board (rule only, no
  units, no panel change): SYSTEMD_READY=1, device unit active/plugged.
* The bridge's own transitions were correct throughout (same pattern as stage 1).
