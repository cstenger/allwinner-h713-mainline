# Stage 3 rerun (2026-10-24): event-driven switching PASS

Fixed rule (ATTR{name} + default READY=0, READY=1 on locked*/holding*).
`board.log`: signal transitions, video-unit journal, status, unstage.
No recording; operator did every host action (output off/on x3,
720p -> 640x480 -> 720p, DPMS sleep/wake, lock screen, unplug/replug) and
reports the panel behaved correctly throughout.

* 28 signal transitions; video unit started 7 times (one per lock) and
  stopped cleanly on each loss; NRestarts 0; no failures, no gst errors;
  the bridge's 1 s EIO backstop never fired (systemd always stopped first).
* Unstaged afterwards: bridge unloaded, nothing left in /run.
