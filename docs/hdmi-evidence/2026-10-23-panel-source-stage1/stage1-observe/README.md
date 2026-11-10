# Stage 1 observe (2026-10-24): bridge alone, host actions, no panel change

`COMPLIANCE=1 stage-hdmi-video.sh observe 300` with bundle module `582d16ac`.
`observe.log` = the host-side copy (cut at ~25 s when the Claude session
restarted); `board-dmesg.log` = every transition from the kernel log.

* Load: `initial signal locked 1280x720 after 11 samples`; QUERY_DV_TIMINGS =
  CEA VIC 4, 60.00 fps; v4l2-compliance 48/48, 0 failed, 2 warnings
  (DV_RX_POWER_PRESENT control, CREATE_BUFS).
* 31 transitions, `sig_bad_guard` 0, no IOMMU fault, unloaded clean.

| Host action (operator order) | Board time | Transitions |
| --- | --- | --- |
| output off/on #1 | 6228.8–6234.6 | holding → none (+1.54 s) → acquiring → locked (+0.22 s, source change) |
| output off/on #2 | 6239.9–6243.9 | same; one 28 ms acquiring/none flicker at turn-on |
| output off/on #3 | 6247.9–6252.0 | same |
| log out / in | 6272.9–6273.5 | holding → locked, 0.56 s, no event: HOLD absorbed it |
| 720p -> 640x480 | 6302.9–6303.1 | holding → unsupported 640x480 |
| 640x480 -> 720p | 6308.2–6308.5 | none → acquiring → locked (source change) |
| DPMS sleep / wake | 6317.1–6327.1 | holding → none; wake: acquiring → locked, then a 0.46 s re-modeset absorbed by HOLD |
| lock screen | — | no transition (mode kept) |
| unplug / replug | 6356.3–6362.3 | holding → none; acquiring → locked (source change) |

Longest same-mode gap: 0.56 s + hold_ms (0.1 s), inside grace_ms (1.5 s).
The script died with the ssh session (SIGHUP, untrapped) and left the
bridge loaded; it was unloaded by hand. Traps now include HUP.
