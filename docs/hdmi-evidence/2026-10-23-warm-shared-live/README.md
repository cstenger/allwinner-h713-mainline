# First warm shared-startup test — live, October 23

**PASS: HDMI capture and audible audio came back on a warm reboot, with
no cold cycle.** The warm boot ran the installed cold startup sequence
unchanged, from RAM, once. Production FIT, modules and services were
unchanged, and nothing was installed.
[Preparation](../2026-10-23-warm-shared-preparation/README.md),
[plan](../../hdmi-shared-startup-plan-2026-10-23.md).

| | Cold session | Warm session |
| --- | --- | --- |
| Boot | `2998fe6a-fd78-4431-98a5-1f864c2fe418` (fresh power-on, all-zero preboot) | `6e1c3d14-577c-4ae7-9770-d5a9119c3ac5` |
| U-Boot path | installed cold branch, unattended | one interrupt, census OK, one `source` of `warm-shared.scr` |
| `check-startup.sh` | PASS | PASS (uptime 19.7 s) |
| DSP | `0000/0000` → `1/1` | `0000/0000` → `1/1` |
| Capture / speaker | RUNNING, owned by hdmi-speaker, 0 xruns | capture 47,989 Hz, playback 48,000 Hz, 0 xruns |
| Audio content | — | 440 Hz tone at 0.2047 RMS (−0.3 dB of expected), heard by operator |
| Picture | logo → console | logo → console (operator) |

Timeline (UTC): reboot requested 01:07:12 → warm prompt caught 01:07:22 →
`source` 01:07:49 → handoff/kernel/login 01:08:12 → SSH 01:08:15 → warm
health PASS 01:08:23. The warm prompt census showed GP6 `48444d49`, GP7 0,
MIPS 0 and PPU bus 0. The bootcmd was unchanged and the on-media FIT CRC
matched. UART markers: re-latch, `WARM-SHARED startup handoff verified`,
kernel, login; no failure text and no extra reset. Checked production
poweroff at 249.6 s with no hold-guard message (modules unloaded in
order).

## Deviations, recorded as they happened

1. **The first cold-health check failed because of a checker defect, not
   the board.** It recorded through PipeWire, but production's
   `hdmi-speaker` owns the HDMI PCM, so the recording held no data. The
   runner stopped before any reboot, as designed. The checker was fixed and
   validated read-only on the same session, then committed (`64a33bf`).
   `resume` continued the **same untouched cold boot**; no reboot or launch
   had happened. Diagnostic SSH reads and three short `pw-record`
   attempts against the PipeWire node (in error state) ran in between.
   The first result is kept as `cold-*-attempt1.json`.
2. **No tone was heard at first because the host was sending no audio**
   (no playback streams; every HDMI sink suspended). The capture held exact
   digital zeros, which is correct. After the run, the speaker was stopped
   for ~3 s twice to record the capture directly. With a 0.3 sine played to
   the host's `H713 HDMI IN` output, the warm session carried the tone at
   the expected level and frequency, and the operator heard it. See
   `audio-content.json`.

## Open questions

* **HDMI video on the panel.** Both boots showed logo then console. The
  startup docs describe only the audio capture path, so this matches the
  build as far as they say. Whether a cold boot shows HDMI video should be
  confirmed before treating "live video" as met.
* **Panel black did not occur** on this warm reboot (it does ~80% of the time
  after a cold-path boot with the cable in). One sample.
* **One trial.** Repeats (orderly and SysRq-b) come next, per the plan.
