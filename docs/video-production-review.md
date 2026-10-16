# Video production-readiness review (2026-10-16)

Scope: the panel/display path from power-on to Linux (U-Boot `h713_disp`, the
guarded HDMI startup script, the `sun50i-h713-afbd` KMS driver), the boot
appearance, and the shipped playback stack (decode, planes, routing, the drift
gate). Decode correctness and endurance were reviewed from their own records
([decode-production-readiness.md](decode-production-readiness.md),
[gpu-fallback-plan.md](gpu-fallback-plan.md#routing)) and not re-measured.
Hardware facts below were taken on the bench board on 2026-10-15/16.

**Verdict.** Decode and playback are production-grade: bit-exact, soaked,
abuse-tested, and routed hardware-first with a GPU fallback. **The display's
boot path is not.** It depends on a U-Boot script that, until yesterday, left
the panel black on every cold boot, still leaves it black on every warm boot,
and visibly flashes while it brings the panel up. Fix the boot path (H1–H3)
before anything else.

## Findings, most severe first

### H1. Every warm reboot leaves the panel black — FIXED, verified 2026-10-16

The guarded startup script (`tools/hdmi/build-startup.py`) skips **every**
display/MIPS launch when the RTC GP6 latch is set, i.e. on every boot that is
not a physical cold cycle. Linux's afbd driver only *adopts* what U-Boot
brought up, so `reboot`, the WiFi crash-recovery reboot (`h713-wifi-recover`),
a watchdog reset and `reboot bootloader` all give a dark projector until
someone unplugs it. The pre-HDMI preboot (`h713_hdmi_previous_preboot`) ran
`h713_disp auto 0x34 logo` on every boot; the HDMI integration (7fba9fc)
dropped it from the warm path.

Evidence it is safe to restore: on 2026-10-15 a warm reboot *out of a live
HDMI-capture session* ran `h713_disp auto 0x34 logo`, `vendor-logo-chroma`
and then a normal boot; logo and Linux console both rendered
([evidence](hdmi-evidence/2026-10-15-panel-blank/README.md)). That is one
sample.

*Fix:* the warm branch now runs the logo bring-up when the MIPS status word is
zero, then boots the original FIT exactly as before. HDMI capture stays
disabled on warm boots (no handoff is published). A failed bring-up still boots.
Verified on a warm reboot: one clean logo, then the console
([evidence](hdmi-evidence/2026-10-16-boot-flashes/README.md)).

### H2. The cold path left the panel black — FIXED and verified

The MIPS relaunch in the cold path reprograms the panel TCON to 1080p; the
720p panel cannot lock. The script now re-latches 720p after the last
firmware call, with readback guards. Verified on a cold boot 2026-10-16
(logo + console seen, timing still 720p after 12 minutes, capture/speaker
active). Full record:
[hdmi-evidence/2026-10-15-panel-blank](hdmi-evidence/2026-10-15-panel-blank/README.md).

**Residual risk (Medium):** nothing in Linux checks the timing. Anything that
later makes the live firmware re-apply its project timing (a future
SetSource, an input mode change handled by the firmware) would blank the panel
again with every framebuffer register still "correct". *Recommended:* have
the afbd driver read `0x05880020/24` at adopt time and on each modeset, and
warn (or re-latch) when they disagree with the panel mode. Cheap, and it turns
the next occurrence from a session of bisection into one log line.

### H3. The boot flashes — ALL FIXED, verified 2026-10-16 (white field, dropout, reset-time lamp via L2)

From the slo-mo capture `local/lcd-photos/test_103/IMG_1048.mov` (30 fps
export of a slow-motion recording, so the times below are video seconds, not
real seconds):

| video time | what the panel does | cause |
| --- | --- | --- |
| 0–18.6 s | dim grey glow | lamp (PB5) on **from reset** (`CONFIG_H713_POWERON_LIGHT_FAN`), LCD not yet powered |
| **18.6–19.7 s** | **full white field** (luma 12 → 64) | `h713_disp` powers the panel (PF6/PH16) ~1 s before the MIPS starts LVDS; a powered LCD with no drive passes all the light |
| 19.7–21.3 s | logo | first launch, quiesce, 720p latch, logo committed |
| **21.3–24.3 s** | **logo fades out, panel dark** | `mips-comm-trace 0x34` relaunches the firmware, which writes 1080p timing |
| 24.3 s | logo back | the new 720p re-latch (H2) |
| ~25.7 s | brief dim | not yet attributed (bootm start or the latch pulse); needs serial timestamps |
| 34.3 s | console replaces logo, no blank | Linux afbd adopt + fbcon: clean |

The lamp is the shared fan/LED enable, so it may be off only briefly; the SoC
is cold at this point and U-Boot is idle.

*Fix (script, no bootloader reflash):* drive PB5 low immediately before the
display bring-up and high again once the final frame is latched, on both the
cold and warm paths; every failure branch turns it back on before returning to
the prompt or booting. The panel then appears once, already showing the logo.
The white field and the relaunch dropout both happen in the dark.
Verified on a filmed cold boot (`test_104`): the logo appears once and stays
until the console; peak luma 24 against 64 for the old white field; audio
works ([evidence](hdmi-evidence/2026-10-16-boot-flashes/README.md)).

*Left for a bootloader rebuild (L2):* the 0–18.6 s glow, which needs
`CONFIG_H713_POWERON_LIGHT_FAN` off. That is a bootloader flash, so it was
kept out of this change.

### M1. The video drift gate is red, and it is the gate that is wrong

`tools/video/check-video-stack.sh` exits `DRIFT`: `build.sh could not name a
tree` for `KERNEL_CONFIG=sysrq`. The installed `sunxi-cedrus.ko`
(`6b0e8793…`) comes from the 2026-10-06 16:23 build; every later build
produces `e9fb2453…`. The cedrus **source is identical** across those trees
(diffed), so the board is not behind. The gate is unusable as a pre-test check
until it can resolve the current tree and compare source identity, not binary
bytes. A gate that is always red gets ignored, and this one exists because a
silently stale module once cost weeks.

### M2. Brightness is not controllable, and userspace is told it is

`/sys/class/backlight/backlight` is the PB4/PWM2 node (patch 0032). Its PWM is
correct, but on this board it does nothing (`backlight-brightness-bringup`):
the light dims only on PWM-of-enable at PB5, which also powers the fan, and
PB5 has no PWM mux. A desktop brightness slider is therefore a silent no-op.
For production either (a) drop the PB4 node, or (b) solve dimming: move the
boost converter's enable to a PWM-capable pin (board change), or find the
converter's dim input. Until then, expose no brightness control.

### M3. The shipping kernel FIT carries two uncommitted EXPERIMENT patches

`patches/kernel/series` ends with `0180-EXPERIMENT-…` and `0181-EXPERIMENT-…`
(the speaker-PA gate). They are audio, not video, but the startup script pins
the FIT's exact size, so the display path's boot script is now coupled to an
uncommitted experimental kernel. Commit or drop them and rename 0181 out of
EXPERIMENT once its shutdown click is verified. Related: the locally built
`h713-hdmi-signal.ko` no longer matches the installed one, so the script-only
updater refused the stock bundle (worked around by bundling the installed
module). Rebuild-to-match or record the installed hash as the reference.

### M4. Production boot appearance is undecided

Today the panel shows the full kernel log, systemd `[ OK ]` lines, and a
serial-autologin root console. That is right for a bench and wrong for a
product. Decide: quiet boot (`quiet loglevel=3`, `vt.global_cursor_default=0`,
fbcon off or `fbcon=nodefer` with a held splash), and what owns the panel
after boot (the stock launcher / a kiosk session). The afbd handover is
already clean (no blank at adopt), so holding the logo until userspace draws is
a configuration change, not a driver one.

### M5. Status docs contradict the hardware

`status.md` (last updated 2026-10-06) still calls `CONFIG_H713_POWERON_LIGHT_FAN`
"bench-only" while it is shipping, and still describes PB4/PWM2 as the
brightness path "awaiting" panel init, which `backlight-brightness-bringup`
superseded. `decode-production-readiness.md` still lists mid-stream resolution
change as known-failing; DMA-BUF capture generations (libva 0018/0019, kernel
0151) made it bit-exact. Refresh both when this review closes.

### L1. Board wall clock is six months off

The board reads `2026-04-13` (the hotspot has no upstream NTP). It is harmless
to video, but it stamps every evidence log and backup file with the wrong date
(`h713-hdmi.scr.20260413T193847` is from 2026-10-15). Set it from the host in
the test harnesses, or ship a host-pushed time on connect.

### L2. Lamp on from reset, with a 5-second autoboot delay — lamp FIXED 2026-10-16

`bootdelay=5` plus the reset-time lamp gives ~5 s of grey glow before anything
happens. For production: `CONFIG_H713_POWERON_LIGHT_FAN=n` (Linux's PB5 hog
and the script both drive the lamp), and `bootdelay=0` with the existing
`reboot bootloader` mode as the way into the prompt. Both are bootloader/env
changes, deliberately deferred.

**Lamp done 2026-10-16:** U-Boot proper rebuilt from the installed source
(`320a17f`) with `CONFIG_H713_POWERON_LIGHT_FAN=n` and installed at `0x49ac00`
after first proving a FEL rescue path (which also fixed the long-standing
"FEL cannot reach U-Boot proper" gap: `env_init()` failing on the `eGON.FEL`
header). Warm and cold boots: lamp dark until the logo, audio works.
[plan](uboot-lamp-flash-plan.md), [evidence](hdmi-evidence/2026-10-16-uboot-lamp/README.md).
`bootdelay=0` remains open; with the lamp dark it now only costs boot time.

## What is production-ready and was not re-opened

Decode (H.264/HEVC/Main10/VP9/AV1/MPEG-2/VP8, 2–3 h soaks, 16/16 malformed,
3-client concurrency), the plane routes with letterbox/pillarbox/magnify
(2-h scope soak), the hardware mirror, auto-keystone, the VA driver (matches
the tree), and the GPU fallback for 10-bit, AV1-above-panel, subtitles and
rotation. These have their own gates and evidence; this review found nothing
that contradicts them.

## Not covered

Standby/resume of the display path; HDMI-input *video* to the panel (only the
audio route is in production startup); the LPDDR3 projector board.
