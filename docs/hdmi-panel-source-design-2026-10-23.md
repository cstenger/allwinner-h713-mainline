# HDMI panel-source policy — design, October 23 (revision 2)

<!-- pipewire-acceptance:start -->
## Current PipeWire board reboot acceptance — completed October 27

**PASS with host-source qualifications.** Installed PipeWire audio passes
physical cold startup, all five orderly warm reboots and a synced abrupt
reset, including actual 440-Hz capture/codec-monitor content and operator
picture/colour/continuous-tone confirmation. Zero rejected frames/capture
xruns and no board service recovery on these runs. Repeated abrupt audio
checks remained healthy through 156 s; final same-boot health passed at 200 s.
No-source cold startup and same-boot reconnection functionally pass. The PC
needed one cable reseat after its first reconnect remained undetected;
unassisted first-reconnect/continuous-client hotplug are not qualified.
Five warm passes span two cold sessions due to the interruption after run 3.
Exact retired direct-consumer mechanism remains unisolated; A/V delay
calibration remains separate. Board powered down, host volume restored to
35%, test player/serial recorder stopped. Source/tests/evidence included in the requested commit; no push.
[Verdict, qualifications and evidence](hdmi-evidence/2026-10-27-audio-lifecycle-fix/acceptance/README.md).
<!-- pipewire-acceptance:end -->

**Status: design for review. Nothing is built, installed or tested on hardware.**
Every claim below cites evidence. Where the evidence runs out, it is listed
as an open question rather than assumed. Revision 2 folds in the review from
the user and the parent session. What it removes is listed in §10.

**Requirement (user, 2026-10-23,
[shared-startup plan](hdmi-shared-startup-plan-2026-10-23.md#panel-source-policy-user-requirement-october-23)):**
the default panel picture is the U-Boot logo, then the Linux console. When an
HDMI source is connected and video is actually coming through, HDMI video
becomes the panel's source. When the signal goes, the panel returns to the
console. Switching follows hot-plug and signal events, not polling and not a
boot-time choice. The same mechanism covers a cable plugged in at runtime and
a boot with the cable already in, cold or warm-shared.

**Typical source: a computer desktop.** The production EDID offers 1280×720p60
(preferred, VIC 4) and 640×480 (VIC 1), RGB only. So a PC renders its desktop
at the panel's native 720p and it is shown 1:1, with no scaling anywhere. The
design keeps it that way (§1.4).

## Summary

| Question | Answer |
| --- | --- |
| How does HDMI video reach the panel? | Not through the firmware's display path. That path exists in the silicon, but in our sessions the firmware leaves its AFBD source-0 fetch off, and it never drives the panel selector, which is ARM-owned (§1.6). The firmware writes NV16 into a capture ring in DRAM. The V4L2 bridge reads the ring and passes frames to stock GStreamer, which puts them on the KMS **video plane**. That plane is an exclusive mux over the RGB console. Shown at 59 fps with MIPS live at source 3 (09-27). |
| What decides "switch now"? | The capture driver. It is the only place that watches firmware lock state (§2), and it publishes that state twice: as standard V4L2 HDMI-RX events, which `v4l2src` handles itself, and as a sysfs attribute plus a `KOBJ_CHANGE` uevent, which udev and systemd use. |
| What starts and stops the picture? | A udev rule marks the capture device's systemd unit *ready* only while the signal is locked or held. `h713-hdmi-video.service` `BindsTo=` that device unit and runs one stock `gst-launch-1.0` line. **No custom daemon.** Restart and backoff are plain systemd settings. |
| How does the console come back? | When the signal is lost, the device becomes not-ready and systemd stops the unit. `gst-launch` exits and its DRM fd closes, so the kernel's fbdev client restores the console. A crash restores it the same way. Restore was seen on the panel 09-26 and 09-27. |
| Boot with the cable already in? | The driver samples once before it registers the video node, so the coldplug `add` event already carries `locked`. systemd starts the unit with no boot-time branch. |
| Mode changes (login, resolution change)? | Brief gaps are absorbed by a 1–2 s driver **HOLD** state, during which the driver delivers black frames. A real mode change raises `V4L2_EVENT_SOURCE_CHANGE`, and stock `v4l2src` (≥ 1.24; the board has 1.26.2) renegotiates without a restart. |
| Chroma for desktop text | v1 goal: scan out **NV16 directly** on the video plane, with no `videoconvert`. That keeps 4:2:2 chroma, avoids a second halving and a 60 fps CPU conversion, and is pending the AFBD format encoding (§1.5). The fallback is today's proven NV16→NV12. |
| Audio | The speaker uses a PipeWire loopback (installed October 27). Video does **not** go through PipeWire. Audio delay is configurable; measured A/V latency calibration (§5) is still pending. |

## 1. How HDMI video can reach the panel today

### 1.1 The firmware does not present HDMI on the panel in our configuration

* Every production cold boot since 10-14 runs `SetSource(3)` in U-Boot, with a
  source connected and transmitting, and shows logo then console. That
  includes the 10-18 session, which sampled 8 distinct moving 720p frames
  from the ring, and the 10-23 warm-shared boot
  ([10-18 live media](hdmi-evidence/2026-10-18-panel-initial-state-trial/live-media/README.md),
  [10-23 warm](hdmi-evidence/2026-10-23-warm-shared-live/README.md)).
* The firmware locks the input (port 1 state 3 → 5, timing 640×480 or
  1280×720) and fills a three-pair NV16 ring at `0x4c3ef000` + n·`0x1ff000`
  ([hdmi1 signal](hdmi-evidence/2026-09-24-hdmi1-signal/README.md),
  [coherent ring](hdmi-evidence/2026-09-25-coherent-ring/README.md)).
* AFBD `0x05600320/324` always holds the current Y/UV ring pair. Nothing in
  our stack writes it, and neither does any direct firmware store
  ([capture memory path](hdmi-capture-memory-path.md)). So some AFBD fetch
  state does follow the capture ring. Whether a firmware-native capture →
  AFBD → composition route sits under the console is **not established**
  (Q3). Earlier layer and AFBD pokes with the core alive were inert or wedged
  the fetch
  ([window layer](handoff-2026-09-04-mips-window-layer.md)), and live Linux
  `SetSource` calls hard-locked the board
  ([synchronized SetSource](hdmi-evidence/2026-09-22-synchronized-setsource/README.md)).
  This design does not depend on that route.

### 1.2 The route that works: capture ring → V4L2 → KMS video plane

| Date | Result | Evidence |
| --- | --- | --- |
| 09-25 | 640×480 HDMI on the panel; console → video → console | [panel preview](hdmi-evidence/2026-09-25-panel-preview/README.md) |
| 09-26 | Signal lost mid-stream: V4L2 fails closed (`EIO`), the panel returns to the console; re-enabling the source brings video back | [signal recovery](hdmi-evidence/2026-09-26-panel-signal-recovery/README.md) |
| 09-26 | RGB console restore after video is hardware-acknowledged (0137) | [RGB quiesce](hdmi-evidence/2026-09-26-rgb-quiesce-cleanup/README.md) |
| 09-27 | Native 1280×720 at 59.17 fps: NV16 → `videoconvert` → NV12 → `kmssink` on `video-0`. fbcon stays on `plane-0`, the console returns at EOS, MIPS stays live at source 3 | [60 fps](hdmi-evidence/2026-09-27-native-720-60fps/README.md), [presentation count](hdmi-evidence/2026-09-27-native-720-presentation-count/README.md) |

The video plane is an **exclusive mux** ([kms-display](kms-display.md)).
Enabling it stops the RGB fetch but keeps the console framebuffer in DRM
state. Disabling it restores RGB with the full `rgb_ctrl_active` word (0137).
So switching is a KMS plane on/off and nothing else.

### 1.3 What production is missing

The startup bundle doesn't ship the bridge or a video consumer
([completion plan §3](hdmi-completion-plan-2026-10-20.md)). The bridge
(`modules/hdmi-v4l2`) is a diagnostic. Its geometry comes from module
parameters. Its fast path (`source_cached=1 use_vmalloc=1 verify_full=0`) is
opt-in. It has no V4L2 events, input status or DV timings. Its no-frame
timeout is 3 s, and it is a self-registered platform device with no driver.
Its guards carry over unchanged: trace-page magic and canaries, the four
VIncap hook words, and reads limited to DRAM plus AFBD `+0x320/324`.
**Correction (stage 1, 10-23): the production cold path does *not* install
that hook.** Its words read `0` on a production boot, the capture counters
stay 0, and the bridge would refuse to load. The hook's source is in
`external/u-boot/arch/arm/mach-sunxi/h713_mips.c:1975-1997`, but only the
diagnostic builds used for the September trials applied it. Revision 2
therefore also needs one of:
* the hook added to the production cold path;
* a completion signal that doesn't need it.

### 1.4 Desktop source contract (keep it)

From `tools/hdmi/fixtures/hdmi-audio-edid.hex` (`edid-decode`):

* DTD 1 is 1280×720 at 60.000 Hz, 74.25 MHz. The CTA block lists VIC 4 and
  VIC 1. The range limits allow 59–61 Hz, so a 59.94 Hz source is valid.
* The CTA header byte `c1` declares underscan with basic audio, and **no
  YCbCr 4:4:4 or 4:2:2**. So the source sends RGB 4:4:4.
* The VCDB declares **QS=1** (RGB quantization selectable through the AVI
  infoframe Q bits). IT and CE content are declared always underscanned.
* Audio: 2-channel LPCM at 32, 44.1 or 48 kHz.

So a PC renders its desktop at 1280×720 and the panel shows it 1:1. Any mode
other than the EDID's two must not appear; if it does, the driver reports it
as UNSUPPORTED. Changing the EDID would re-pin the signal owner, so it is
outside this design. **HDCP:** desktops rarely enable it, and this receiver
doesn't advertise or implement it, so protected content stays the source's
problem. **No audio:** desktops often send none; the speaker then passes
silence, which is fine.

### 1.5 Chroma, range and conversion cost

* **The chain today:** RGB 4:4:4 (wire) → firmware → NV16 (4:2:2, chroma
  halved horizontally) → `videoconvert` → NV12 (halved vertically as well) →
  plane. The second halving puts visible colour fringes on coloured text and
  thin UI lines. It also costs a full 60 fps CPU conversion even for a static
  desktop (mean 3.9 ms, max 9.2 ms per frame on 09-27).
* **v1 goal: direct NV16 scanout.** That means `v4l2src ! kmssink` with no
  conversion. Stock `kmssink` 1.26.2 maps `NV16 ↔ DRM_FORMAT_NV16`
  (`gstkmsutils.c`). The H713 video plane today accepts only NV12, plus P010
  as an experiment; the known AFBD format bytes are `0` = RGB888, `3` =
  NV12, `6`/`7` = P010 ([[nv12-format-and-publish-latch]], [[p010-video-plane]]).
  **The 4:2:2 encoding is still unknown after the static pass (§1.6).** The
  firmware's only format writer is the decoder-frame programmer, and its
  resolver table contradicts our own hardware results for NV12, so it can't
  be read as a format list. The stage-1 snapshot records the format byte
  while the firmware sees a locked signal. The cheap test is a bounded
  stage-2 run on our own plane: a static NV16 test frame at the remaining
  untested bytes, 2 and 4 first. If no encoding turns up, NV16 → NV12 stays
  as the fallback. The pipeline differs by one caps element.
* **4:4:4/RGB capture** (open, Q11): the firmware has YUV444 capture formats
  and `kmssink` knows NV24. But selecting a capture format means CPU_COMM
  calls on the live firmware, which is the class that has hard-locked this
  board. Not for v1.
* **Quantization range** (open, Q12): with QS=1, the PC may send full or
  limited RGB and says which in AVI Q. Linux sources usually default to
  limited for CE VICs like VIC 4, through "Broadcast RGB" or the NVIDIA
  `ColorRange` setting. It is unknown whether the firmware's RGB→YUV honours
  AVI Q, and the video plane exposes no `COLOR_RANGE`. Stage 2 measures it
  with a grey ramp and black/white text at both host settings, and records
  the host's setting and AVI Q.
* **Zero-copy** (Q10): with NV16 scanout, two CPU copies remain: ring →
  vmalloc buffer → kmssink dumb buffer, about 2.5 ms each. Exporting ring
  slots as dma-bufs to the plane would remove both. It needs a slot-lifetime
  argument (three slots, a flip every frame) and IOMMU master-2 mapping of
  the carveout. Later work.

### 1.6 The firmware's own HDMI picture path (static RE, October 23)

**Question:** can the firmware's own hardware path put HDMI on the panel,
replacing V4L2, the copies and GStreamer?

Method: offline only, on display.bin SHA256 `4380f1b3…` with base
`0x8b100000` (`tools/mips/disasm.py`, `cfg.py`, `vtables.py`,
`block-map.py`), plus a whole-image lui/addiu cross-reference. Register
values come from existing production HDMI-session dumps
(`hdmi-evidence/2026-10-15-panel-blank/`,
`2026-10-16-uboot-kernel-dts/trial7-pl6-running-hdmi/`). No board access.

**What `EnterSignalSteady` does.** It belongs to `CAppTop`
(`app_top_projector.cpp`), the firmware's top-level state machine. The
states are:

| State | Entry | Behaviour |
| --- | --- | --- |
| 0 | `EnterIdle` | — |
| 2 | `EnterWaitingWindowsReady` | timeout one frame (10⁶/fps µs) |
| 3 | `EnterWaitingPipeLineReady` | timeout five frames |
| 4 | `EnterSignalSteady` (`0x8b107d5c`) | timeout 500 ms |

Idle and the two waiting states end with a call to `0x8b1082e0`. That
function hands the signal descriptor to the **MemoryAgent** and re-evaluates
which DMA engines run. `EnterSignalSteady` only sets state 4 and arms the
500 ms timer. When that timer fires, the thread loop (`0x8b109440`)
calls `CheckTcd3NonStdVHTotal` (`0x8b107e3c`), which handles the analogue
decoder's non-standard timing. **Nothing on the steady path un-mutes or
selects the picture.**

**MemoryAgent** (`memory_agent.cpp`, vtable `0x8b1fb818`) holds the DMA
on/off switches for the whole video path. `OnOff(mask, on)` is at
`0x8b153d7c`:

| Mask bit | Register written | Block |
| --- | --- | --- |
| `0x4` | `0x068c038c` (via helper) | memory-agent gate |
| `0x8` | `0x06940928/968` bit 31 | capture write DMA (forbidden window, firmware-only) |
| **`0x10`** | **`0x05600010[1:0]` + commit `0x05600014`** | **AFBD source 0, the same channel as our KMS video plane** |
| `0x20` / `0x40` | `0x05000178/1b8`, `0x05000278/2b8` bit 31 | composition-block NR Y/C fetch, channel B |
| `0x80`–`0x200` | `0x050c06f8/738/7b8`, `0x050c0478…678` bit 31 | DETN |

`update_onoff` (`0x8b153a20`) chooses the mask from the source's signal
status, a TCD3 type check, mode 6 and flag bytes `+0xb4..+0xb6`/`+0x14`.
With no signal it logs `"no signal, disable all memory agent without
tcd3."`. On its signal branches it enables bits 0–6, which include AFBD
source 0 and the NR fetch. The exact branch a locked HDMI input takes isn't
settled statically.

**What gates visibility.** Four independent gates:

1. **Firmware DMA.** In the recorded production HDMI sessions
   `0x05600010` reads `0x03000010`: source 0 is *off*. So the firmware has
   not switched its own fetch on, even with a locked source, and the capture
   ring is filled with no consumer except our bridge. Why it stays off is
   undetermined statically. The likely reason is that stock's ARM-side TV
   service drives windows and pipeline readiness (`THal_Vp_Wce_SetWindow`,
   the `SignalChange` callback path), and our boot never does.
2. **Panel output selector `0x051c006c`.** `0x29000000` = RGB/OSD,
   `0x39000000` = video. The firmware **never writes it**: there is no
   direct store, and no physical-write helper call resolves to it. Only
   LogoRegData sets the OSD value at boot, and our KMS driver writes the
   video value when it enables `video-0` (patch 0078,
   `H713_VIDEO_SELECTOR`). The decision "what is on the panel" is
   **ARM-owned**. The firmware will never move the panel to HDMI by itself.
3. **Blue-screen mute** (`blue_screen.cpp`, class `CBlueScreen`, vtable
   `0x8b1ed910`). A handle and flag stack drives hardware mute at three
   points:
   * the proc blender `0x05140d54`: bit 6 plus fields [2:0] and [5:3];
   * the panel `0x051c00b8`;
   * the panel after gamma `0x051c0364`.

   `THal_Vp_Enable/DisableBlackScreen` are this. Recorded values are
   `0x05140d54 = 0` and `0x051c00b8 = 0x38` (enable bit 6 clear), so no mute
   is asserted. This gate is open.
4. **Ownership of AFBD source 0.** The firmware's HDMI fetch and our KMS
   video plane are the *same* channel. Our KMS probe requires source 0 idle
   (`video_ctrl_idle == 0x03000010`, 0078) and would refuse to adopt a
   display where the firmware had already enabled it.

**Verdict.** The hardware route is real and the silicon has every piece of
it: capture DMA → ring → AFBD source 0 / NR → proc → panel mux. But using it
means **giving AFBD source 0 and the panel selector to the firmware**. That
is a different owner model, not a simplification of this design. Turning it
on needs one of two things:
* stock's ARM-side window/pipeline/callback calls on the live firmware, the
  CPU_COMM class that hard-locked in September;
* or flipping the memory agent and AFBD bits behind the firmware's back,
  which collides with the KMS driver's ownership of source 0.

It would remove the copies and GStreamer, but add firmware-state
dependencies and an unproven hand-over of source 0. It also leaves the
switching decision on ARM (gate 2) either way. Until stage 1 runs,
**revision 2 stays the v1 plan.** §1.7 holds the known-good reference and
§1.8 the trade-off.

**Corrections and loose ends from this pass:**
* The AFBD pair at `+0x320/324` is not written by any firmware store.
  Capture updates it in hardware (the bridge's VDE-correlated votes) even
  with source 0 off. A warm-path dump (no source 3) also holds a ring pair,
  so its presence says nothing about presentation.
* The firmware's only AFBD format writer is the decoder-frame programmer
  `0x8b1a4538`, through the resolver `0x8b1a31e8`. **(Superseded by §10.20:**
  the resolver's table is consistent with the hardware. The "3 = NV12"
  below came from the `0066` experiment; the video plane writes NV12 = 0.)
  That is PanelWinNode's
  dirty-bit-`0x800` path, fed by DECD's VideoInfo. Its table (input 6 → 3,
  14 → 7, 15 → 6) contradicts our hardware facts (Linux-written 3 = NV12,
  6/7 = P010) under both candidate enums: display.bin's `color_format_*`
  table at `0x8b1f4bb0`, and decd.ko's `kVideoDecoderColorFormat_*`.
  stock hwcomposer's `VideoTunnel::toDecFormat` (`0x2de60`) maps Android HAL
  formats into a third numbering. **No 4:2:2 byte can be read off it** (§1.5).

### 1.7 The known-good reference: stock Android HDMI, 10-07

On 10-07 stock Android showed a live 1920×1080 COSMIC desktop over HDMI.
The firmware log was captured at level 5
([10-07 evidence](hdmi-evidence/2026-10-07-android-audio/README.md),
`locked-elog/elog.bin`; also `idle-elog/`, `selected-elog/`, `final-elog/`).
The session was about audio, so **no display registers were dumped**. The
log decodes offline with `tools/mips/elog-parse.py`. In order (ticks are ms):

| Tick | Step | What the log shows |
| --- | --- | --- |
| 287978 | `THal_Vp_SetSource(3)` from ARM | `AppTopSetSource`; window manager `SetSignalInfo`; freerun lock `enter_stm_no_signal`; crtc `load_panel_timing` / `write_registers` (**the firmware touches the panel CRTC on a source change**, the [[mips-relaunch-rewrites-panel-timing]] trap); `update_onoff` (no signal) |
| 287979 | Receiver bring-up | Port 1 select, PHY reset, HPD event; `HDMIRX Send BlueScreen, bON=1` (muted) |
| 288293 | ARM `THal_Vp_DisableBlackScreen` | Clears the HAL's blue-screen handle (the receiver's own mute is separate) |
| 289300–289741 | Lock | Port states 3 → 4 → 5; TMDS detected; AVI infoframe **Y=0 (RGB), Q=2 (full range)**; timing 1920×1080, totals 2200×1126; `hdmirx set AV mute:1` throughout |
| 290042 | Signal valid | Unmute starts (`AV mute:0 1`); `SetSignal 0x20000`; `CallbackOfSignalChange`; signal info `b_full_range 1`, BT709 |
| 290061 | **The firmware sets the windows itself** | `UpdateWce` with `low_latency:1`; capture 1920×1080 → display 1280×720 |
| 290062 | Capture node | **Hardware downscale at capture**: `CapWinNode` in 1920×1080 → out 1280×720, ratio `0xaaaa`/`0xaaab`, `color_format:4`, Y/C line counts 720/720 (4:2:2) |
| 290063 | NR node | Writes its frames **compressed** (mode 1, ratio 15625, `color_format:2`, C lines 360 = 4:2:0) into DRAM; `m_afbd_source_mode : 1`, so AFBD fetches NR's compressed output |
| 290064 | Proc and panel nodes | 1:1 at 1280×720; panel windows at (49, 22); `WriteReg` for capture and NR; `update_onoff` (signal); `AV mute:0 0` (unmuted) |
| 290065 | Notify | HAL `NotifySignalChange`: HDMI_1, 1080P, `kHalColorFormat_RGB_101010`, full range |
| 290070 | ARM `THal_Vp_Wce_SetWindow` | — |
| 290229 | ARM `THal_Vp_DisableBlackScreen` | Again |

**What this settles:**
* On a signal change the firmware runs the whole picture path without ARM
  help: windows, scaling, NR, the AFBD read, mute and unmute.
* Stock's ARM side adds only `SetSource`, `Wce_SetWindow` (after the
  firmware has already laid out the windows), `DisableBlackScreen`, and
  picture-quality and backlight setters.
* The receiver handles a **1080p source with a hardware capture downscale**,
  and it reads the quantization range from the infoframe.

**What it doesn't settle:**
* Which register makes the video visible over or under Android's UI. No
  dump was taken, so stock's `0x051c006c` and blending state are unknown.
* Why our sessions stop short. Our boot also runs `SetSource(3)` and gets
  port state 5 and a filled ring, yet AFBD source 0 stays off. The stage-1
  log diff (§10.1) finds the first stock step that is missing from ours.

### 1.8 Firmware path vs GStreamer path

| | Firmware path (as stock runs it) | GStreamer path (revision 2) |
| --- | --- | --- |
| Code we carry | Removes GStreamer, V4L2 streaming, both copies, the conversion and the NV16 plane work. Adds whatever brings the firmware the last step (a call or a register; unknown until stage 1), a source-0 hand-over mode in the KMS driver, and the `0x051c006c` switch | Bridge driver, udev rule, two units, one `gst-launch` line |
| CPU and memory traffic | No ARM copies; the NR compression reduces DRAM traffic | ~2.5 ms × 2 copies per frame, plus conversion on the NV12 fallback |
| Latency | Firmware low-latency mode, frame-locked by freerun lock. Likely ≈ 1 frame (to be measured) | ≈ 2 frames; the 60 Hz source drifts against the 59.97 Hz panel (an occasional repeat or drop) |
| Input modes | 1080p via the capture downscaler. The EDID could then offer 1080p, which most PCs prefer. 720p 1:1 is kept | 720p 1:1 only (plus 640×480, Q9) |
| Range / chroma | Range from AVI Q; the firmware's picture-quality chain | Range unknown (Q12); 4:2:2 at best, 4:2:0 on the fallback |
| Mode changes / no signal | The firmware mutes to black and unmutes itself; the HOLD state comes free | HOLD built in the driver |
| Switching / events | ARM still owns the panel selector and needs a lock event (the same driver observer, §2) | same |
| Coexistence | KMS must release AFBD source 0 while HDMI shows. Local playback becomes a source switch (`SetSource` 1 ↔ 3) at runtime | Plain DRM plane ownership |
| Shown on this board | **Never**; stock only | Yes: 59 fps on the panel, console restore, signal-loss recovery |
| Risks | Possibly runtime CPU_COMM to the live firmware (Linux-side `SetSource` hard-locked in September); a firmware CRTC rewrite on source changes; closed and hard to debug | Low; everything is Linux-owned |

**Decision rule.** Let stage 1's log diff decide (§10.1):
* If the missing step is one the U-Boot cold path can do, or a register the
  KMS driver can own, the **firmware path wins**. GStreamer and the copies go
  away, and §3/§4 stay as they are with only the unit's action changing.
* If it needs runtime CPU_COMM traffic to the live firmware, keep
  **revision 2**, and treat the firmware path as research behind a separate,
  guarded test.

## 2. The event source

### 2.1 What exists, and why there is no interrupt

| Observable | Where | Meaning | Evidence |
| --- | --- | --- | --- |
| HDMI port 1 `state` | MIPS DRAM port object `+0xC0` (manager `0x4BAC1A70` → `+0x18` → `+0xEC`) | 1 = other ports; 2 = EDID clock not held; **3 = selected, no video**; **5 = live timing**; 4 never seen | [hdmi1 signal](hdmi-evidence/2026-09-24-hdmi1-signal/README.md), `read-mips-port-cache.py` |
| Active timing | port `+0x4E` H, `+0x48` V, `+0x64` repeat | Measured by the firmware; 0 with no video | same; 1280×720 in [native capture](hdmi-evidence/2026-09-26-native-720-capture/README.md) |
| VIncap counters | trace page `+0x84` IRQs, `+0x88` cap-vde, `+0x8C` cap-vs, `+0x90` mode change | A frame finished writing into the ring | [production gates](hdmi-evidence/2026-09-25-production-gates/README.md) |
| `HDMI_GetPortStatus` | CPU_COMM | Follows the EDID clock hold, **not lock** | hdmi1 signal |
| `MipsHalCallback_SignalChange` | MIPS → ARM CPU_COMM CALL | Stock's mechanism. Needs a callback registered with the live firmware and every CALL answered, on the path that hard-locked | [early TVCAP](hdmi-mips-early-tvcap.md) |
| HPD / +5 V | SCP payload / CPUS `0x07091xxx` | HPD is held high all session. +5 V is forbidden from ARM ([[cpus-arisc-mmio-hardlocks]]) | `modules/hdmi-signal` |

There is no ARM interrupt for lock. The receiver and capture interrupts go to
the MIPS, and `0x0694xxxx` is off-limits. The CPU_COMM msgbox RX interrupt
storms, so CPU_COMM RX itself is hrtimer-polled (`0014`,
`cpu_comm_msgbox_request_irq()`).

### 2.2 Decision: the capture driver is the only observer

A `delayed_work` samples port state, timing and the VDE counter: every 20 ms
while idle, and on every VDE while streaming (the stream thread already sees
each one). These are plain DRAM reads. This **is** sampling, of state the
firmware publishes, but it lives in one function. If a real interrupt appears
later, through a fixed msgbox RX IRQ or a hook that rings the msgbox, only
that function changes (Q1).

The driver publishes through:

* **The V4L2 HDMI-RX interface** that stock `v4l2src` consumes:
  - `ENUMINPUT` with `V4L2_IN_CAP_DV_TIMINGS` and status
    `NO_SIGNAL`/`NO_SYNC`.
  - `QUERY_DV_TIMINGS`: `-ENOLINK` for no signal, `-ENOLCK` while acquiring,
    otherwise the timings.
  - `G_DV_TIMINGS`, `S_DV_TIMINGS` (accepts the detected value),
    `DV_TIMINGS_CAP`.
  - `SUBSCRIBE_EVENT` for `V4L2_EVENT_SOURCE_CHANGE`
    (`v4l2_src_change_event_subscribe()`), raised on every mode change.
  - `G_FMT` follows the timings. `STREAMON` without a lock returns `-ENOLINK`.
* **A `signal` sysfs attribute** on the parent platform device: `none`,
  `acquiring`, `locked 1280x720`, `holding 1280x720` or
  `unsupported 640x480`. It is created through the platform driver's
  `dev_groups`, so it already exists when the video node's `add` event
  fires. Every transition sends a `KOBJ_CHANGE` on the video node with
  `H713_HDMI_SIGNAL=` and `H713_HDMI_MODE=` in its environment.
* **Frame rate:** from the DV timings, never pinned in caps. The firmware
  gives active size only. Totals and pixel clock come from the matching CEA
  timing (74.25 MHz → 60/1). A 59.94 Hz source (74.176 MHz) is told apart
  by the VDE interval, timestamped by the stream thread over at least 4 s
  (Q13). With `sync=false` the caps frame rate doesn't pace anything:
  `v4l2src` uses the driver's monotonic buffer timestamps, and `kmssink`
  presents frames as they arrive.

### 2.3 Stock v4l2src behaviour (checked against source, offline)

Read from the GStreamer tags on GitHub, `subprojects/gst-plugins-good/sys/v4l2/`:

* **1.20 onward:** `v4l2src` queries `ENUMINPUT`. On
  `V4L2_IN_CAP_DV_TIMINGS` it calls `QUERY_DV_TIMINGS`, takes width, height
  and fps from the BT timings (`pixelclock / (htotal × vtotal)`), and locks
  them with `S_DV_TIMINGS`. On `NO_SIGNAL`/`NO_SYNC` status it posts a
  `"Signal lost"` warning. It subscribes to `SOURCE_CHANGE`.
* **1.24 onward:** `gst_v4l2src_handle_resolution_change()` runs inside
  `create()`. On a `SOURCE_CHANGE` with `V4L2_EVENT_SRC_CH_RESOLUTION`, it
  stops streaming, re-queries and locks the timings, renegotiates and
  restarts **in the same pipeline**. 1.20 and 1.22 don't have this
  function. Downstream, `kmssink` simply gets new caps.
* **The board runs GStreamer 1.26.2** (Debian trixie;
  [letterbox phase 1](reference/letterbox-phase1-2026-10-04.md),
  [video-decode](video-decode.md)). **Required: ≥ 1.24.** To verify offline,
  look for `Resolution change detected.` and `Using DV Timings:` in the
  rootfs image's `libgstvideo4linux2.so`, and read the trixie
  `gstreamer1.0-plugins-good` version from the rootfs build manifest. The
  behaviour itself can be checked on the host with the stock `vivid` driver,
  which emulates an HDMI input with DV timings, signal-loss controls and
  `SOURCE_CHANGE`: run the same `gst-launch` line, toggle the signal, change
  the timings, and watch for in-place renegotiation versus exit. That needs
  `modprobe vivid` as root on the host, and no board.
* **Signal loss: `v4l2src` does not exit by itself.** When signal goes, it
  renegotiates. It only gives up when `STREAMON` fails (`-ENOLINK`) or
  `DQBUF` returns `EIO` (`vb2_queue_error()`). The design makes systemd the
  primary stop (§4). The `EIO` path is a backstop.

## 3. State machine (driver)

| State | Entry | `signal` attr | Unit | Panel |
| --- | --- | --- | --- | --- |
| **NO_SIGNAL** | port state ≠ 5, or timing 0×0 | `none` | stopped (device not ready) | console |
| **ACQUIRING** | state 5 with timing, not yet stable for `N_lock` VDE events | `acquiring` | stopped | console |
| **LOCKED(m)** | stable for `N_lock` events (proposal 12 ≈ 200 ms) and `m` supported (v1: 1280×720, repeat 0) | `locked m` | running | **HDMI** |
| **HOLD(m)** | from LOCKED: no VDE for 100 ms, port leaves 5, or the mode counter moves | `holding m` | running | **black** (driver delivers black frames at the source cadence) |
| **UNSUPPORTED(m)** | stable, but `m` not supported (v1: 640×480; Q9) | `unsupported m` | stopped | console |

From HOLD:
* The same mode comes back stable within `T_grace` (proposal 1.5 s, inside
  the 1–2 s review range): back to LOCKED and real frames resume. No event
  and no restart.
* A different supported mode stabilises within `T_grace`: LOCKED(m′), with a
  `SOURCE_CHANGE` event, and `v4l2src` renegotiates in place.
* `T_grace` expires: NO_SIGNAL. The driver sends the uevent (device not
  ready), and systemd stops the unit. If a stream is still open 1 s later,
  the driver calls `vb2_queue_error()` as the backstop.

The four cases in the brief:

| Situation | Path | Panel |
| --- | --- | --- |
| No cable | NO_SIGNAL | console |
| Cable, no lock (source off, sleeping, mode-setting) | NO_SIGNAL ↔ ACQUIRING | console |
| Locked video | LOCKED | HDMI |
| Signal loss | LOCKED → HOLD → (back within 1.5 s) LOCKED, or → NO_SIGNAL | black for at most `T_grace`, then console |

So login and resolution-change mode-sets show a short black hold, not a
console flash, and systemd does not flap the unit. A real unplug or DPMS
sleep returns to the console after `T_grace`. A lock screen normally keeps
the mode, so the picture stays on HDMI. The gap lengths are measured in
stage 1 (Q2) before the numbers are fixed. HPD is always high and +5 V is
invisible, so "no cable" and "cable, no lock" share NO_SIGNAL. A 5 V field in
the port object would separate them, for diagnostics only (Q4).

## 4. Units and udev: standard pieces only

```
h713-hdmi-capture.service   receiver + audio owners (cold handoff)    [unchanged]
  └─ h713-hdmi-signal.service       EDID/HPD owner                     [unchanged]
       ├─ HDMI audio (PipeWire loopback; replaces h713-hdmi-speaker)   [parent's work]
       └─ h713-hdmi-ring.service    oneshot: guarded insmod/rmmod of the bridge  [NEW]
            └─ dev-h713\x2dhdmi\x2din.device   ready ⇔ locked|holding  [udev rule, NEW]
                 └─ h713-hdmi-video.service    one gst-launch-1.0 line         [NEW]
```

**`h713-hdmi-ring.service`** has the same `BindsTo=`/`After=`/`Before=shutdown.target`
and `ConditionPathExists=…/h713,hdmi-boot-v1` as the speaker.
`ExecStart` runs the guarded `insmod`; `ExecStop` runs `rmmod`. The bridge
takes no receiver client and owns no hardware, so receiver park and the hold
guard's module list don't change.

**`/etc/udev/rules.d/71-h713-hdmi-in.rules`:**

```
SUBSYSTEM=="video4linux", ATTRS{signal}=="?*", ATTRS{name}=="h713-hdmi-in", \
  SYMLINK+="h713-hdmi-in", TAG+="systemd", ENV{SYSTEMD_WANTS}="h713-hdmi-video.service"
SUBSYSTEM=="video4linux", ATTRS{name}=="h713-hdmi-in", \
  ATTRS{signal}!="locked*|holding*", ENV{SYSTEMD_READY}="0"
```

systemd acts on `SYSTEMD_WANTS` only when a device *becomes* active
(`systemd.device(5)`), so a bare `change` event would not restart anything.
The pattern here is: udev re-reads `signal` on every `add` and `change`.
`SYSTEMD_READY=0` makes the device unit inactive, and its going active is
what pulls in the Wants. Going inactive again stops every unit that
`BindsTo=` it.

**`h713-hdmi-video.service`:**

```
[Unit]
Description=H713 HDMI input on the panel
BindsTo=dev-h713\x2dhdmi\x2din.device h713-hdmi-ring.service
After=dev-h713\x2dhdmi\x2din.device h713-hdmi-ring.service
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
ExecStart=/usr/bin/gst-launch-1.0 -q v4l2src device=/dev/h713-hdmi-in io-mode=mmap \
  ! video/x-raw,format=NV16 \
  ! kmssink driver-name=sun50i-h713-afbd sync=false skip-vsync=true
Restart=on-failure
RestartSec=1
```

The NV12 fallback inserts `! videoconvert n-threads=4 ! video/x-raw,format=NV12`
before `kmssink`, which is the 09-27 pipeline. Nothing pins a frame rate or a
size.

* **Coldplug, no boot branch:** the driver samples synchronously before
  `video_register_device()`. If the cable is in and locked at boot, the `add`
  event already reads `locked`, the device unit is active at once, and the
  video unit starts. If the lock comes later, the `change` event does the
  same. Cold, warm-shared and runtime plugs all take this one path.
* **Loss:** the uevent makes the device inactive, `BindsTo` stops the unit,
  SIGTERM ends `gst-launch`, the DRM fd closes and the console returns. The
  1 s-later `EIO` backstop (§3) only matters if the stop didn't happen.
* **Failure:** a busy DRM master or a format refusal makes `gst-launch` exit
  nonzero. systemd restarts it after 1 s, at most 3 times a minute, and the
  next lock event clears the limit. The console stays up throughout.
* **Coexistence (Q7):** `ExecStartPre=/bin/sh -c '! fuser -s /dev/video0'`
  refuses while Cedrus is busy (Cedrus traffic plus live MIPS has hard-locked
  the board, [[display-yuv-fetch-closed]]). Which side wins is the user's
  decision.

## 5. Audio and A/V sync

**Today**, the speaker (`alsasrc` 40 ms buffer and 10 ms period → `alsasink`)
and any video would be independent processes. No common clock or latency
target is set.

**(a) One GStreamer A/V pipeline while LOCKED, with the speaker covering the
gaps.** Rejected. The HDMI PCM is exclusive, so every lock and every loss
would hand the device between two processes, leaving an audible gap and a
new failure path each time. With `sync=false` (needed for desktop latency) a
shared pipeline doesn't buy sync. With `sync=true` it adds latency, and it
would need the V4L2 and ALSA timestamps on one clock.

**(b) PipeWire for audio; video direct to KMS; sync by latency matching.**
Recommended.
* The HDMI ALSA source is a PipeWire node; WirePlumber already makes it the
  default source (M2, [[hdmi-normal-startup]]).
* The speaker becomes `libpipewire-module-loopback` from that node to the
  codec sink, with a small `node.latency` and a `target.delay.sec` that sets
  the audio latency. PipeWire's adaptive resampling absorbs the
  47,989-to-48,000 Hz clock difference (10-23 warm run), so audio latency
  stays constant.
* Video runs free, straight from capture to scanout. Both paths are timed by
  the same source, so there is no long-term drift. Sync is a single constant
  offset, measured once and set as the loopback delay. The remaining error
  is the vblank phase: 0–16.7 ms as the 60 Hz source slides against the
  59.97 Hz panel.
* Video through PipeWire (a v4l2 SPA node, then `pipewiresrc`) stays out.
  It adds a hop, and PipeWire's v4l2 plugin isn't known to handle DV timings
  or `SOURCE_CHANGE` (Q14).
* The speaker's mixer setup (DAC 43, Line Out 15) and "mute = DAC volume 0,
  never Speaker Switch 0" carry over ([[audio-bringup]]).

**Latency budget** (to be replaced by measurements):

| Stage | Video (NV16 direct) | Audio (PipeWire loopback) |
| --- | --- | --- |
| Capture until the frame/period is complete | ≤ 16.7 ms (VDE at frame end) | DSP + 10 ms capture period |
| Driver notice + ring copy | ~1 ms + 2.5 ms (09-27) | — |
| Conversion | 0 (NV12 fallback +3.9 ms mean, 9.2 ms max) | resampler, < 1 ms |
| Queue to output | kmssink copy 2.5 ms + 0–16.7 ms to vblank | 2 × quantum (e.g. 256/48 k = 5.3 ms each) + device buffer |
| Panel / amplifier | LCD response, unmeasured | ~0 |
| **Estimate** | **≈ 22–40 ms + panel** | **≈ 25–40 ms before `target.delay.sec`** |

**Measurement** (stage 4b):
* *Software.* Run the stock `GST_TRACERS=latency` tracer on the video
  pipeline (src→sink per buffer) and compare V4L2 buffer timestamps (VDE
  time) with the DRM flip-event time. Record median, p95 and max.
* *Glass to glass and sync.* The host plays the irregular flash+beep clip
  (`tools/video/make-avsync-clip.sh`) full-screen at 720p. A 240 fps phone
  films the host monitor and the projection together, with sound.
  Projection minus monitor gives video latency; beep minus flash on the
  projection gives sync. Calibrate the phone's own A/V offset with a visible
  clap.
* *Desktop feel.* Same camera: move the mouse and type, count frames between
  the monitor and the projection, at least 20 events, median and max.
* Keep `sync=false` and minimal buffering throughout. For desktop use,
  latency wins over lip sync: the loopback delay may *add* audio delay to
  match video, but video is never buffered to match audio.

## 6. Interaction with the warm shared startup

* **No special case.** On both cold and warm boots U-Boot runs logo → MIPS →
  source 3 → re-latch → handoff, and the same units start. Coldplug (§4)
  covers a cable that is already locked. The expected picture with the cable
  in is logo → console (~20 s until the services are up) → HDMI. Boot-time
  slimming will shorten the console gap without changing this design.
* **Reboot from HDMI.** `BindsTo`/`After` stop the video unit first, so the
  console is restored before the ring, signal and capture teardown and before
  the kernel's panel power-down (0184). Whether rebooting from video changes
  the panel-black odds hasn't been measured (Q6); record the state each warm
  reboot starts from.
* The GP6 health ack must not depend on video, because NO_SIGNAL is
  healthy. On the warm-guard or logo-only fallback there is no handoff, the
  units' condition skips them, and the console stays.

## 7. Hazards and guards

| Hazard | Guard |
| --- | --- |
| A firmware re-apply rewrites TCON to 1080p and the panel goes black ([[mips-relaunch-rewrites-panel-timing]]) | No MIPS calls and no source change here. Stage 1 reads `0x05880020/24` across lock and unlock (Q5) |
| Cedrus traffic plus live MIPS hard-locks the SoC | `fuser` refusal; Q7 |
| Two DRM masters | kmssink takes master; tools must drop it ([[wp4-plane-routes]]); the unit fails and restarts within its limit |
| IOMMU master-2 ordering ([[iommu-master2-flip-ordering]]) | Already handled by the KMS driver (0076); only kmssink commits |
| An NV16 plane is a new format path | Behind its own KMS patch with an atomic-check refusal. The unit falls back to the NV12 line until a stage-2 visual pass |
| Forbidden windows | The bridge reads DRAM (ring, trace page, port objects with vptr guards) and AFBD `+0x320/324` only. Never `0x07091xxx`, `0x0694xxxx` or GP7; no CPU_COMM; PB5 untouched |
| Console blanked by fbcon | Check `consoleblank` (Q8) |

## 8. Open questions

1. **Driver-side sampling as the v1 event source.** **Needs your decision.**
2. **`N_lock`, `T_grace` (1–2 s), the HOLD trigger and the idle period.**
   Measure in stage 1: host login, resolution change, DPMS sleep and wake,
   lock screen, unplug.
3. **Firmware path or GStreamer path** (§1.8). Stock's sequence is on
   record (§1.7). Stage 1's log diff (§10.1) finds what our boot lacks, and
   the decision rule in §1.8 follows from it. Still unknown and not on
   record: stock's display registers while HDMI shows (selector, blending).
   That needs a vendor boot with the operator, and only if the diff leaves
   it open. **The final choice is yours.**
4. **A 5 V field in the port object** (diagnostic only).
5. **Do lock and unlock events write TCON, composition or window state?**
6. **Panel-black after a reboot from video** ([[panel-black-2026-10-16]]).
7. **HDMI or local playback priority.** Proposal: HDMI wins while LOCKED,
   and Cedrus playback is refused during an HDMI session. **Needs your
   decision.**
8. **Console blanking:** make sure the console that comes back is visible.
9. **640×480.** A PC may deliberately pick it. The choices are: keep the
   console (v1 default); show it 1:1 centred, or pillarboxed to 960×720
   through the letterbox route (0161/0163); or drop VIC 1 from the EDID,
   which re-pins the signal owner. **Needs your decision.**
10. **Zero-copy ring import** and CPU/thermal cost alongside audio,
    including a static desktop still costing per-frame copies.
11. **4:4:4/RGB capture** (firmware YUV444 formats, `kmssink` NV24):
    needs live firmware calls. Later.
12. **Quantization range:** what the PC sends (host "Broadcast RGB" /
    `ColorRange`, AVI Q) and whether the firmware honours it. Stage 2.
13. **59.94 versus 60 Hz:** VDE-interval measurement accuracy, or a
    firmware timing field (RE of the struct filled at `0x8b140190`).
14. **PipeWire's v4l2 plugin with DV timings and `SOURCE_CHANGE`**, only if
    video in PipeWire is ever wanted.
15. **Mirror and keystone on the HDMI plane** (the plane rotation from
    `h713-mirror` should apply).

## 9. Implementation (after review; offline first)

1. **Capture driver** (`modules/hdmi-v4l2`):
   * Bind a proper platform driver with `dev_groups` (`signal`).
   * The state machine in §3, with HOLD and its black frames.
   * The V4L2 HDMI-RX interface and `SOURCE_CHANGE` from §2.2, a
     synchronous first sample before registration, and `KOBJ_CHANGE` on
     every transition.
   * The MIPS port-object read with vptr and range guards.
   * The fast-path defaults, and frame rate from the timings.
   * Keep the existing guards.
2. **KMS:** a separate patch adding `DRM_FORMAT_NV16` to the video plane,
   only once the AFBD 4:2:2 encoding is found (§1.5). It is out of series
   until stage 2 passes.
3. **System pieces:** the udev rule, `h713-hdmi-ring.service`,
   `h713-hdmi-video.service`, and a small `build-video.py`/`install-video.sh`
   modelled on the speaker's (manifest, checksums, `--update` with backup).
   No daemon source.
4. **Log diff helper** (`tools/mips/elog-sequence-diff.py`, for §10.1),
   built before stage 1. Self-test: stock `locked-elog` against stock
   `idle-elog` must report the source-3 steps (`AppTopSetSource`, `UpdateWce`,
   `CapWinNode`) as missing from idle, and stock against itself must report
   nothing.
5. **Offline tests:**
   * The driver's state function built for the host and fed the recorded
     traces (`port-cache*.json` 3→5→3, the 720p caches) plus synthetic
     mode-set gaps, flaps and stalls. Check the HOLD/grace outcomes and the
     uevent sequence.
   * `udevadm verify` on the rule and `systemd-analyze verify` on the units.
   * The `vivid` host test of the exact `gst-launch` line (§2.3): lock,
     resolution change in place, loss → systemd stop, and coldplug while
     locked.
   * Module and KMS patch build with W=1 against the validated kernel.
   * Installer tests.
   * Find the line in each test that would fail
     ([[passing-suites-that-cannot-fail]]).

## 10. Staged live test plan

Run against the existing production session (cold or warm-shared boot, services up,
source connected). Until stage 5, runtime units go in `/run/systemd/system`
and the rule in `/run/udev/rules.d`, so a reboot erases them; nothing is
installed. Each stage is announced, the turn ends, and the operator says
"ready" ([[operator-timed-tests-need-their-own-turn]]). Stop on an IOMMU
fault, any `0x05880020/24` change, lost SSH, or panel black. Coordinate board
and `/dev/ttyUSB0` use with the user first.

| Stage | What | Operator | Pass |
| --- | --- | --- | --- |
| **1. Observe only** (first live test) | `insmod` the driver from `/tmp`: no streaming, no rule, no DRM. Host actions: output off/on ×3, login, a resolution change 720p → 640×480 → 720p, DPMS sleep and wake, lock screen, one PC-end unplug and replug. Log driver transitions and VDE gaps against host connector timestamps. Take the read-only snapshot in §10.1 in NO_SIGNAL and in LOCKED. Then `rmmod` | Confirms the console never changed (no camera) | One correct transition per host action; gap lengths recorded (sets `T_grace`, Q2); TCON unchanged (Q5); AFBD diff recorded (Q3, NV16 lead) |
| **2. One switch by hand** | `gst-launch` in the foreground while LOCKED, with a 10 s `timeout`: NV12 line first, then the NV16 line if its patch exists. Host shows a grey ramp, black/white text and coloured text, at host Full and then Limited | Camera: console → HDMI → console; reads the ramp's ends and the text fringes | Picture 1:1; range identified (Q12); NV16 fringes ≤ NV12 fringes; console back; plane-0 fb unchanged |
| **3. Event-driven** | Runtime rule and units. Repeat the stage-1 host actions | Camera per action | Mode-sets show a short black hold and come back with no console flash; unplug and sleep → console after `T_grace`; no unit flapping (`NRestarts`) |
| **4. Coldplug and warm** | `udevadm trigger` while LOCKED; then a warm-shared reboot from HDMI, with the runtime units restaged after boot | Picture report | HDMI appears without a new event; reboot gives logo → console → HDMI |
| **4b. Latency and sync** | §5 measurements with the PipeWire loopback | 240 fps camera | Numbers recorded; a delay proposed for user sign-off |
| **5. Install** (**explicit approval**) | `install-video.sh`; cold and warm boots with and without the cable; audio running; 10-min desktop soak | Picture + sound | The §3 table holds on every boot; zero XRUNs; restarts within limits |

### 10.1 Stage-1 read-only snapshot

Take it once in NO_SIGNAL and once ≥ 2 s into LOCKED, and again after the
500 ms steady timer has had time to fire. Use `mmio-rw` and `/dev/mem`
reads only. Every window below has been read before in this project with
the display live. Diff the two states against each other and against the
10-15/10-16 production dumps.

| What | Address | Why (§1.6) |
| --- | --- | --- |
| Panel timing | `0x05880020/24` | Q5: no TCON rewrite on lock or unlock |
| Panel output selector | `0x051c006c` | Gate 2: expected `0x29000000` throughout |
| Blue-screen mute | `0x05140d54`, `0x051c00b0/b4/b8`, `0x051c0364` | Gate 3: does the firmware assert or clear mute on lock? |
| AFBD | `0x05600000-0x3ff` | Gate 1: source 0 enable and format byte `0x05600010`, mux `0x68`, the `0x300-0x33c` queue/pair; the 4:2:2 byte if the firmware ever programs one |
| NR / channel-B fetch enables | `0x05000178/1b8/278/2b8` (bit 31), NR window `0x05000804-085c` | MemoryAgent bits `0x20`/`0x40` |
| DETN fetch enables | `0x050c0478…678`, `0x050c06f8/738/7b8` (bit 31) | MemoryAgent bits `0x80`–`0x200` |
| Firmware log | MIPS DRAM `0x4b270000` + 2 MiB (read twice a few seconds apart and merged, since uncached lines show as holes), decoded with `tools/mips/elog-parse.py` | Diffed against the 10-07 stock log; see below |
| Port object | as §2.1 | state, timing |

**Log diff against stock (the decision input for §1.8):**
1. **Precondition:** the log must be buffered at a comparable level.
   * Stock has `mode 1 level 1` (`b3e6e8f6…`), which is what
     `local/mips-display/board-b-mips/display_cfg.xml` holds.
   * Our boot partition's copy was changed on 09-04 to `mode 2 level 5`
     (`f97eec07…`, `tools/stock/vendor-elog-cfg.sh`).
   * Hash the installed file read-only first. If it isn't `f97eec07…`, the
     log is empty or terse. In that case record the fact and stop the diff:
     enabling level 5 changes firmware assets and is its own approved step.
2. Extract the HDMI-source sequence from both logs, keeping only these tags:
   * `hal`, `app`, `mem_agn`, `bs`, `win_mgr`, `wce_*`, `hdmirx`,
     `hdmi_driver`, `frl`, `crtc`.
   For stock use `locked-elog`. For ours use the LOCKED snapshot. Drop ticks
   and keep record order. A small offline helper (`elog-sequence-diff.py`,
   §9) normalises the volatile values and prints the stock steps that ours
   lacks.
3. Read the first missing step against §1.7:
   * missing `UpdateWce` / `CapWinNode WriteReg` → the window layer never ran;
   * missing `update_onoff` after the lock → the MemoryAgent was never told;
   * present but source 0 still off → the gap is after the firmware (an
     agent mask branch, or the KMS driver).
4. Record all of it in that stage's README. **Absence is weak evidence.** A
   missing record can be cache or ring wrap, so a "missing" step must be
   absent from both merged reads before it counts.

### 10.2 Stage-1 result (10-23, read-only part)

[Evidence](hdmi-evidence/2026-10-23-panel-source-stage1/README.md), boot
`799298ff`. Snapshots were taken locked, then with no signal (host output
off), then locked again. The driver-event part of stage 1 waits for the
driver.

* **The log diff puts the gap on the ARM side.** Our firmware runs stock's
  whole lock sequence: windows, capture and NR writes, `update_onoff`,
  unmute, `NotifySignalChange`. It still leaves AFBD source 0 and the NR
  fetch off, and the panel selector stays on the console. What our boot
  never does is stock's ARM-side initialisation and responses:
  * HAL init (`ObtainBlueScreenHandle` ×3);
  * dispatch of `NotifySignalChange`;
  * `Wce_SetWindow`;
  * `DisableBlackScreen`.
* **Decision rule (§1.8): not decided yet.** U-Boot can already make
  firmware calls (it sends `SetSource(3)`). So if the gate is set by
  something U-Boot can do before Linux, such as `Vp_Init` or
  `DisableBlackScreen`, the firmware path is still reachable without
  runtime CPU_COMM. Next, offline: trace `update_onoff`'s inputs back to the
  stock HAL call that sets them.
* **Revision 2 gap:** production U-Boot doesn't install the capture hook
  (§1.3).
* **Q2 data:** loss is seen immediately (5 → 3), with an ~80 ms 5 → 3 → 5
  bounce during the host's disable. TMDS lock to a valid signal took
  ~0.7 s. The firmware fires `NotifySignalChange` on every transition.
* **Q5:** TCON timing stayed at 720p across loss and lock. `0x0588001c`
  went from `4` to `00D00404` at the first loss; its meaning is unknown.
  The operator saw the console the whole time, with no black and no flicker.

### 10.3 Why the firmware leaves its display DMA off (offline trace, 10-23)

Static RE of display.bin, the 10-07 stock log, and two read-only DRAM reads
on the stage-1 boot (`799298ff`).

**`update_onoff` (`0x8b153a20`), reconstructed.** Its inputs are:
* the MemoryAgent's stored config: `+0x8` source ID and `+0xc` signal ID,
  written only by its slot `0x14`;
* flags `+0xb5`/`+0xb6`;
* the picture mode `+0x4`;
* `S = DeviceManager.lookup(+0x8).field1`. This is a **static** per-source
  table: live, HDMI 1–4 → 1, VideoDec → 3, Dummy → 5, CVBS/ATV → 0.

There are two cases:
* Stored signal ID ∈ {`0x20002`, `0x20003`} ("no signal"): keep agents
  0–2, plus capture DMA (`0x8`) if `+0xb5`, and **disable everything else**.
* Any other stored signal ID: enable `0x78` (capture, AFBD source 0, NR Y/C
  and channel B), or `0x7f`, and disable DETN.

**The flags follow the live signal; the config doesn't.** On every HDMI
signal change, `CallbackOfSignalChange` (`0x8b1075bc`) posts the descriptor
to the `CAppTop` thread. For any source other than VideoDec, the thread
takes the `0x8b108644` → `0x8b1080a8` branch. That branch sets `+0xb5`
(= signal present) and `+0xb6` and calls `update_onoff`, **but it never
refreshes the stored config**. Only `EnterIdle(info)`,
`EnterWaitingPipeLineReady(info)` (through `0x8b1082e0`) and a reset helper
write slot `0x14`, and the thread reaches those only for VideoDec
(source 1) messages.

**Live, on our boot:**
* The MemoryAgent at `0x8b89d37c` still holds its constructor values:
  `+0x4 = 1`, `+0x8 = 0`, `+0xc = 0x00020003` (no signal).
* Flags: `+0xb5 = 1` (signal), `+0xb6 = 0`.
* So the HDMI lock takes the no-signal case: `S = lookup(0) = 5`, `+0xb5`
  set, so it enables `0x8` and disables the rest.

That is exactly the stage-1 register picture: the capture ring is being
written while AFBD source 0 and the NR fetch are off.

**Stock gets past this by accident of history.** On 10-07 Android called
`SetSource(1)` and `Vp_Init` (184733–184789). A VideoDec signal
(`DTV_1280_720_P`, its decoder video tunnel) then arrived at 187331 and ran
`EnterWaitingWindowsReady` → `EnterWaitingPipeLineReady` (187377), which
stored **(source 1, signal present)** in the MemoryAgent. When HDMI was
selected 100 s later, `update_onoff` still used that stale VideoDec config:
`S = 3`, a signal-present ID, `+0xb5 = 1`, so it enabled `0x78`. Our cold
path launches the firmware straight into `SetSource(3)`, so no VideoDec
signal ever refreshes the config.

**So the gate is not a HAL call.** It is a firmware gap: the HDMI
signal-change path never refreshes the MemoryAgent's config, and stock is
masked by an earlier decoder signal. Making the firmware path work needs all
of the following; the first is now understood, the rest are open:
1. **Get the config refreshed** so that AFBD and NR are enabled on lock.
   The candidates are:
   * a U-Boot-installed trampoline (the cold path already patches
     display.bin for its traces) that makes the HDMI branch call
     `0x8b1082e0` with the new descriptor;
   * the firmware's own debug-shell commands `en <0-9|all>` /
     `dis <0-9|all>` (MemoryAgent slots `0x24`/`0x28`, reachable through
     the MIPS shell the session already uses for its liveness check). These
     only override until the next `update_onoff`;
   * one decoder signal before `SetSource(3)`, which is hard from U-Boot.
2. **AFBD source-0 programming for capture.** In our session source 0
   still holds the inherited 1920×1088 fallback geometry. Who programs it
   for NR's compressed output (`m_afbd_source_mode 1`) is not established.
3. **IOMMU.** Master 2 (AFBD) boots in bypass, and our kernel flips it to
   translation on first video use (0075/0080). Only the logo carveout is
   identity-mapped (0070). While master 2 is in bypass, firmware-programmed
   physical addresses work. After any video-plane use has flipped it, the
   firmware's addresses for NR's buffers in the MIPS carveout would fault.
   One fault wedges the AFBD fetch engine for the whole boot, console
   included ([[iommu-master2-flip-ordering]], [[display-yuv-fetch-closed]]).
   So before any test: read the master-2 bypass state read-only, and either
   keep it in bypass or identity-map the carveout. The two paths can only
   share a boot if that is solved.
4. **The panel selector** `0x051c006c` → video, owned by the KMS driver.

Revision 2's blocker is a single U-Boot change: install the capture hook.
The firmware path has four. Item 3 decides whether its first live test is
safe, and that check is a read.

### 10.4 IOMMU state on a production boot (read-only, 10-23)

Read on the same boot (`799298ff`, uptime 1519 s) with `busybox devmem`:

| Register | Value | Meaning |
| --- | --- | --- |
| `0x02010020` (enable) | `00000001` | IOMMU on |
| `0x02010030` (bypass) | **`00000058`** | bit set = bypass: masters 3, 4, 6 bypass; **0 and 1 (VE), 2 (AFBD/GE2D) and 5 (AV1) translate** |
| group 0 `reserved_regions` | `0x6c100000–0x6c8fffff direct` | only the logo carveout is identity-mapped |

The masters, from [iommu-port](iommu-port.md):
* 3 = `tvdisp@5000000`: the composition block / NR;
* 4 = `tvcap@6800000`: capture;
* 2 = `dec@5600000`: AFBD.

So on a production boot **AFBD already translates** (patch 0080 attaches the
display at probe, unlike stock, which bypasses master 2 until playback).
NR and capture run untranslated. Consequences:
* Enabling **memory agent 4 (AFBD source 0)** would fetch from addresses the
  firmware means as physical. Those are either 0 or inside the unmapped MIPS
  carveout, so it would fault and wedge the AFBD fetch engine, console
  included, for the boot. **Agent 4 is excluded** until the carveout is
  identity-mapped for master 2: a kernel DT `iommu-addresses` entry next to
  the logo one, covering the buffer range T1 identifies.
* **Agents 5 and 6 (NR Y/C, channel B)** run on master 3, which bypasses.
  They are the only agents a first test may touch.

### 10.5 T1 — guarded first live test (designed, not run; needs approval)

**Question:** does NR process the locked HDMI frames once its memory agent
is on? If it does, does the firmware then program AFBD source 0 for NR's
output (geometry, format, addresses)? Those addresses are the range item 3
of §10.3 has to map.

**Mechanism:** the firmware's own debug shell command `memory_agent en 5` /
`memory_agent dis 5`, from `debug/memory_agent_dbg.c`:
* the top-level shell entry at `0x8b20dd90` has handler `0x8b1536ac` and
  help "for memory_agent debug only";
* the subcommands are `en` (`0x8b154010`) and `dis` (`0x8b1540b8`); the
  argument `n` means mask `1 << n`, and `all` means every agent;
* it calls MemoryAgent slots `0x24`/`0x28`, which are `OnOff(mask, 1/0)`
  directly, with no `update_onoff`.

The command goes through `tools/mips/mips-shell.py --cmd`, the same DRAM ring
the capture service uses on every boot for `help win`. It is not CPU_COMM.

**Preconditions.** All are read-only; abort if any fails:
1. Production session healthy (`run-panel-source-stage1.py preflight`), port
   1 in state 5 at 1280×720.
2. MemoryAgent vptr `0x8b1fb818`, `+0xc = 0x00020003`, `+0xb5 = 1`: the
   §10.3 state.
3. IOMMU bypass has bit 3 set (NR untranslated).
4. `0x05600010 = 03000010` and `0x051c006c = 29000000`: video plane idle,
   console selected, no Cedrus user.
5. **NR's buffers stay inside the firmware's reserved frame-buffer pool.**
   Settled by the offline RE (10-23); see "NR buffer addresses" below. The
   per-run check is:
   * the firmware's loaded config copy (`0x4be01000`, read by the snapshot)
     declares `<frame_buffer>` address `0x4bf41000`, size `0x1A00000`;
   * Linux's `framebuf@4bf41000` reserved-memory node is present with that
     `reg` and `no-map`.

   Abort on either mismatch.

**NR buffer addresses (offline RE plus read-only DT check, 10-23).**
* **The firmware never writes a DRAM buffer base into the NR block.**
  `NRWinNode::WriteReg` (`0x8b1a48cc`, NRWinNode vtable slot 4) writes only
  composition `0x0f0`, `0x138`, `0x174/178`, `0x1b4/1b8`, `0x210/224`,
  `0x274/278`, `0x2b4/2b8` and the NR window `0x804–0x860`. Those are
  geometry and the line-buffer descriptors (rowbyte, level, line count) plus
  the agent enable bits. That matches the capture side, where no
  frame-buffer base store exists either ([capture memory
  path](hdmi-capture-memory-path.md)).
* **All of the firmware's frame buffers come from one configured pool.** At
  init, `0x8b19d4fc` reads `sys:frame_buf_addr` and
  `sys:frame_buf_virtual_addr` from display_cfg.xml. Board B's file declares
  `<frame_buffer>` at `0x4bf41000`, size `0x1A00000` (26 MiB, ending
  `0x4d940fff`). The function then reads the TV memory controller register
  `0x068c0394` through the firmware's physical-read helper and stores
  `(phys − virt) + (0x068c0394 << 4)` as the agents' address offset. So the
  memory agents address DRAM relative to a controller-held base inside the
  pool, not through per-buffer registers. `0x068c0380` bit 14 / `0x1000` is
  that controller's reset pulse (`0x8b19d5bc`, `0x8b19de88`). The observed
  capture ring (`0x4c3ef000 + n·0x1ff000`) lies inside the pool, and so does
  the V4L2 bridge's `H713_CARVEOUT`.
* **The pool is fenced off from Linux.** Live on `799298ff`:
  * `/proc/iomem` reserves `4b100000–4d960fff`;
  * reserved-memory `framebuf@4bf41000` has `reg = 4bf41000 01a00000` and
    `no-map`;
  * `mips-firmware@4b100000` (`0x0e41000`) and `decoder@4d941000`
    (`0x20000`) are also `no-map`.

  So NR DMA confined to the pool can't touch Linux memory.
* **What this doesn't prove:** the exact addresses NR uses. They are derived
  inside the memory controller and the firmware never stores them, so there
  is nothing to read back, from ARM or from the firmware shell. The residual
  risk is a firmware bug sending NR outside its own pool. That is the same
  firmware and configuration stock runs this path with (10-07). Accepted for
  T1, and listed under risks.
6. Operator present, watching the panel.

**Steps:**
1. Stage-1 snapshot `t1-before`.
2. `memory_agent en 5`. Read immediately and after 10 s:
   * `0x05000178/1b8` bit 31;
   * AFBD `0x05600000–0x9f`;
   * IOMMU fault lines in `dmesg`;
   * an elog delta.
3. Only if step 2 is clean: `memory_agent en 6`, with the same reads.
4. `memory_agent dis 6`, `memory_agent dis 5`. Verify bit 31 clears. Take
   snapshot `t1-after`.

**Never in T1:**
* agent 4 (AFBD), agents 7–9 (DETN), `dis all` (it would also stop agents
  0–3, including capture);
* `regw`, the panel selector, any CPU_COMM call, any firmware patch.

**Residual risks, accepted for T1:**
* NR DMA addresses are controller-derived and unverifiable (see above), but
  confined by design to a pool that Linux reserves `no-map`.
* NR runs on a firmware configuration our boots never ran before: the
  window writes happened at lock, but the fetch was off.
* The shell write is the first firmware-state change this design makes.

**Rollback:**
* `memory_agent dis 5/6`.
* Failing that, any HDMI signal change (toggle the host's output) re-runs
  the firmware's own `update_onoff`, whose no-signal mask disables 5 and 6.
* Failing that, an orderly reboot.
* Stop at the first IOMMU fault, panel change, or SSH stall.

**Pass / outcomes:**

| Observation | Meaning | Next |
| --- | --- | --- |
| bit 31 set, AFBD source-0 geometry/addresses programmed for 1280×720 | NR runs, and the firmware feeds AFBD itself | Map that address range for master 2 (DT patch), then T2 = agent 4 nonvisible, then T3 = selector flip, operator-confirmed |
| bit 31 set, AFBD untouched | NR runs; the AFBD source-0 programming has another trigger | RE the frame programmer's trigger for capture (`m_afbd_source_mode 1`) |
| bit 31 does not stick | Something rewrites the agents | Read the elog; stop |
| any fault or panel change | — | Stop, roll back, record |

### 10.6 T1 result (10-23)

[Evidence](hdmi-evidence/2026-10-23-panel-source-stage1/t1/README.md).

All preconditions passed. Then `memory_agent en 5` and `en 6` set bit 31 of
composition `0x178/0x1b8` and `0x278/0x2b8`. Both stayed set over 10 s
holds, and `dis 6`, `dis 5` restored the four words exactly:
* no IOMMU fault;
* capture kept writing the ring;
* panel selector, IOMMU bypass and TCON timing unchanged.

**AFBD source 0 never changed.** It kept the inherited geometry with zero
address slots, and the firmware logged nothing beyond the on/off records.

This is **outcome row 2**: the NR agents are safe to switch, but turning NR
on is not what programs AFBD for HDMI. The operator saw the console
throughout, with no black and no flicker.

**Next, offline:** find what drives the AFBD source-0 programmer for a
capture source (`0x8b1a4538` via PanelWinNode dirty bit `0x800`,
`m_afbd_source_mode 1`) and what stock's log shows around it. Agent 4 stays
excluded until the master-2 identity map exists.

### 10.7 What programs AFBD source 0 for HDMI (offline trace plus read-only DRAM, 10-23)

**The programmer and its gate.**
* The frame programmer `0x8b1a4538` has exactly one caller, at `0x8b1a4dc0`
  inside **`NRWinNode::WriteReg`** (`0x8b1a48cc`, NR vtable slot 4). It runs
  when the WriteReg mask has bit **`0x800`**, and it is passed the NR node.
  (The 08-31 note attributed this call to PanelWinNode; the call site and
  its `NRWinNode.cpp` log strings put it in NR.)
* It reads NR `+0x50` and `+0x4c` (FrameBuffer objects; the `+0x4c` branch
  sets AFBD `0x2c`/`0x50`/`0x54`), `+0x5c` (colour format, through the
  `0x8b1a31e8` resolver) and **`+0x60` = `m_afbd_source_mode`**.
* From those it writes AFBD `0x10[26:24] = 3`, `0x28`, mux `0x68` (`[5:4]`
  and `[1:0]` = 2, **bit 8 = (mode ≠ 1)**), `0x60[0] = 1`, **`0x10[4] =
  (mode = 2)`**, the format byte `0x10[15:8]`, and geometry through
  `0x8b1a40e0`.
* Back in WriteReg, it sets **composition `0x30[22] = (mode = 1)`**.
* No other firmware code writes AFBD source 0's geometry or format. Its
  address slots `0x70–0x90` have no firmware store at all; the capture side
  updates `+0x300–0x324` in hardware.

**Stock:** NR logged `m_afbd_source_mode : 2` for the decoder signal (187357)
and **`1` for HDMI (290064)**.

**Our boot, live** (heap scan of `0x4b100000–0x4bf40fff` for the NRWinNode
vptr `0x8b207a50`):
* NR node `0x8b89bfc0`: **`+0x60 = 1`**, `+0x5c = 4`, `+0x4c = 8b89bd40`,
  `+0x50 = 0`. This is the same HDMI configuration as stock.
* CapWinNode is at `0x8b89bf10`, PanelWinNode at `0x8b89c360`.

**But the registers show the programmer has not run since NR entered
mode 1.** It would have produced mux bit 8 = 0, `0x10` bit 4 = 0 and
composition `0x30` bit 22 = 1, and it would have rewritten the format byte
and geometry. Live:
* mux `0x05600068 = 0x122` (bit 8 = 1);
* `0x05600010 = 0x03000010` (bit 4 = 1, format 0);
* composition `0x30 = 0x00000C00` (bit 22 = 0);
* geometry still the inherited `043F077F`.

These are the boot-time and decoder defaults. Our KMS driver writes those
registers only on video-plane commits (`sun50i-h713-afbd.c:905/1128/1170/1196`),
and there have been none. So the NR `WriteReg` that ran at lock (logged at
tick 22863, as in stock at 290064) **did not carry bit `0x800`**, or never
reached that branch.

**Still open.** The WriteReg mask is computed at runtime by WCETop:
* the constant masks at `0x8b1a8b54…0x8b1a9758` (`0xffff`, `0x7e06`,
  `0x6e40`, `0x7e02`, …) all contain `0x800`;
* the lock-time call takes its mask from WCETop state (`refresh_node`, the
  dirty accumulation), which isn't recoverable offline at reasonable cost.

**Ways to settle it:**
1. **Static, large:** trace WCETop's dirty-mask accumulation for a
   `SetSignalInfo` → `UpdateWce` → `SetWindow` pass.
2. **Measured:** a trace trampoline at `NRWinNode::WriteReg` entry that
   records `$a1` into the trace page. The cold path already installs this
   kind of trampoline. It needs a U-Boot build and a test boot.
3. **The firmware's own levers, unproven:** the `win` shell table has `rn`
   ("set refresh node", `0x8b1ac788`). A forced window refresh might run
   NR `WriteReg` with `0x800`. But that would run the AFBD programmer while
   master 2 translates, which is the agent-4 hazard. So it waits for the
   carveout identity map too.

### 10.8 Measured route: a WriteReg mask trace (built and tested offline, 10-23)

**Already on record, read live on `799298ff`.** Production's comm trace
already installs the frame-programmer hook (stages `6101`–`6103`, retargeted
to page `0xad98`). Its last record is: stage `6103`, mask `0xffffffff`, **NR
mode 2**, control `0x03000010`, latches `1/1`. So the programmer last ran in
decoder mode, at boot, and never in capture mode. This confirms §10.7
independently. What's still unknown is the mask of the lock-time WriteReg.

**Why production lacks the capture hook.** `config/versions.env` builds
U-Boot from base `320a17f71d41`. The capture-completion hook landed one
commit later (`9d35a4ecbd6`, "trace H713 capture completion events").
Rebasing the series onto that commit is revision 2's fix. It's kept out of
this diagnostic so that only one thing changes.

**The trace.**
* `tools/mips/make-nr-writereg-trace.py` generates 36 patch words:
  * a 34-word cave at `0x4b100c40`, in the zero run `0x4b100c10–0x4b100fff`
    that the comm-trace table doesn't use;
  * a hook replacing the prologue pair at `0x8b1a48d0/48d4`
    (`lui v0,0x8b20` / `addiu v0,v0,0x7024`) with `j cave` / `nop`.
* The cave counts calls and records `$a1` (the mask) and `this+0x60` (source
  mode). It keeps the OR of all masks, a count of `0x800` hits, the last
  mask in mode 1, and a 16-entry ring at trace page `+0x100…+0x19f`. Then it
  re-executes the two displaced instructions and jumps to `0x8b1a48d8`.
* Only `t0`/`t1`/`t8`/`t9` are used.
* The page base is a direct `lui t8, 0xad98` and every store is at
  `≥ 0x100`, so `h713_mips_apply_comm_trace()`'s relocation counts (61/80 on
  the production base) and its pristine-word checks are unchanged. Its page
  `memset` already zeroes the slots.

**Offline checks (all pass; `--self-test`):**
* All 36 sites are pristine in display.bin `4380f1b3…`, the cave is in the
  free run, and nothing overlaps the comm-trace table of either the
  production tree or `external/u-boot`.
* No store falls in the relocated `≤ 0x90` range, and the page base isn't
  the relocatable `0xae34`.
* Every word decodes under capstone.
* **Unicorn emulation** of the patched and original prologue from
  `0x8b1a48cc` to `0x8b1a48d8`, for five (mask, mode) pairs:
  * all registers except the emulator's stop PC are identical, the stack is
    identical, and `v0 = 0x8b207024`;
  * every trace slot holds the expected value, with nothing written outside
    `+0x100…+0x19f`;
  * a 20-call run checks the counters and the ring wrap.
* Two mutations make the self-test fail: dropping a displaced instruction,
  and moving a store to `+0x44`.

**U-Boot.** `patches/u-boot/0002-h713-trace-nrwinnode-writereg-masks.patch`
(**not** in `series`; diagnostic only) appends the rows to
`h713_mips_comm_trace_patches`.
* Applied on a copy of the prepared production tree (`build/uboot-src-nrtrace`)
  and built for DDR3 (`build/uboot-ddr3-nrtrace/`).
* No new warnings in `h713_mips.c`. All 36 rows sit contiguously in the
  image.
* Proper `build/uboot-ddr3-nrtrace/proper.bin`: 955 665 bytes (1867
  sectors, the installed slot's size), SHA-256 `c68b78d7…59b82`.

**Reader.** `tools/mips/read-nr-writereg-trace.py` runs on the board,
read-only. It checks that the hook words, the cave words and the page guards
are present before interpreting anything, and prints the counters, the ring
and the existing frame-programmer record. Against today's production boot it
refuses (`NR_WRITEREG_TRACE_ABSENT`), which also confirms live that the hook
site holds the expected originals and the cave is zero.

**T2 preparation (done 10-23; see
[t2-preparation](hdmi-evidence/2026-10-23-panel-source-stage1/t2-preparation/README.md)).**
* The installed proper is actually the 1877-sector 10-20 reset-controls
  build `1b1f702f…`. So the trial was rebuilt from that exact source tree
  plus `0002`: `proper-trial-1877.bin`, `cb8e417a…`.
* A control build of the same tree matches the installed image except for
  10 timestamp bytes.
* Backups, the exact rollback and the guarded `t2.sh`
  (`check`/`install-dry`/`install`/`rollback`) are staged and verified in
  `/root/panel-source-t2/`.
* During guard testing, one flawed negative test **wrote the trial proper
  by mistake**. It was rolled back and verified within a minute, with no
  reboot, so the trial never ran. Negative tests now use `install-dry` only.
* **Steps 1–2 below now read 1877 sectors and `1b1f702f`.**

**T2 — delivery and run (needs approval; not done).** This follows the
10-18 precedent ([U-Boot panel initial state](uboot-panel-initial-state.md)).
1. **Back up first.** Read the installed proper (LBA `0x49ac00`, 1867
   sectors) and check it against `4391dfa0…`. Stage `rollback.sh` with that
   exact image. The FEL rescue (`h713-rescue-spl.bin` → rescue slot
   `0x4a0c00`) stays the fallback; its slot is not written.
2. **Install** the trial proper in the same 1867 sectors, with a full
   direct-I/O readback and checks that the surrounding regions are
   unchanged. Then do a cold boot (operator: serial and USB unplugged, ≥ 1
   min off) with HDMI connected, so the normal cold path installs the comm
   trace and the new rows.
3. **Read** right after Linux is up, before lock if possible, then after
   lock. Then turn the host output off and on once and read again.
   Everything is read-only, plus the host-side `cosmic-randr` toggle.
4. **Restore** the original proper with `rollback.sh`, verify the readback,
   and do a normal boot.

**What the result decides:**

| Lock-time masks (mode 1) | Meaning | Next |
| --- | --- | --- |
| No call in mode 1 carries `0x800` | WCETop never asks NR to reprogram AFBD for capture on our boot | Compare with stock's order (a VideoDec pass first). Candidate fixes: one forced refresh (`win rn`) after the identity map, or a firmware patch that ORs in `0x800` when the mode changes |
| A mode-1 call carries `0x800` | The programmer was asked for, but its result was overwritten or didn't take | Read the `6101`–`6103` record from the same boot, then RE the programmer's early exits |
| No WriteReg calls in mode 1 at all | The lock path doesn't reach NR WriteReg as logged | Elog/trace mismatch: stop and re-check the hook |

### 10.9 T2 result (10-23)

[Evidence](hdmi-evidence/2026-10-23-panel-source-stage1/t2-run/README.md).
The trial was installed, run on one cold boot, and rolled back to
`1b1f702f` and verified.

* At init the firmware runs two full refreshes: `refresh_node:2` (NR mode 1)
  and then `refresh_node:1` (mode 2).
* Each HDMI lock or re-lock runs only `refresh_node:0`, mask **`0x100`**, so
  the AFBD programmer never runs in capture mode.
* Stock shows the same order, so stock's visible HDMI picture comes from
  something other than this lock-time path. Open.

**Next candidates:**
* the firmware shell `win rn 2` (set refresh node) before a signal change,
  which would make the lock refresh run the full mask in mode 1, with agent 4
  still off and the panel selector untouched (read the AFBD registers only);
* or RE of what `refresh_node` and its consumers decide.

### 10.10 The `refresh_node` lever and T3 (offline RE, 10-23; designed, not run)

**What `refresh_node` is.**
* `TWindowManager` (vtable `0x8b208920`, global `0x8bac4bf0` via
  `0x8b1ac5f8`) keeps a persistent requested refresh node at `+0x150`.
* `UpdateWce` (`0x8b1ab7fc`) passes it to WCETop (`0x8b1a8750`, which logs
  `refresh_node:%d` and stores WCETop `+0x12c`). WCETop's `SetWindow` reads
  it at eight sites (`0x8b1a8b30…0x8b1a9730`) to pick its node WriteReg masks
  (`0xffff`, `0x7e06`, `0x6e40`, …).
* At init the window manager sets `+0x150 = 2` (`0x8b1ac024`); the full
  init refreshes in T2 used 2 and 1. At HDMI lock it held 0, giving the
  partial `0x100` mask.

**The firmware's own lever.**
* The `win` shell table entry `rn`, `win_dbg_cmd_set_refresh_node`
  (`0x8b1ac788`, `debug/win_dbg_cmd.cpp`), calls:
  * window-manager slot `0x08` = `SetRefreshNode(N)` (`0x8b1aaefc`: stores
    `+0x150`, logs `node:0x%x`);
  * then slot `0x30` = `Refresh(1)` (`0x8b1ac2c8`, which calls `UpdateWce`).
* So `win rn 2` with HDMI locked should run one full window update in the
  current (capture) mode: NR WriteReg with the full mask in mode 1, and so
  the AFBD source-0 programmer in capture mode.
* It goes through the same DRAM shell ring as T1 (no CPU_COMM).

**Static safety checks.**
* The frame programmer doesn't write source 0's enable bits `0x10[1:0]`
  (only `[26:24]`, `[4]`, `[15:8]`, `[31]`) or its address slots. Agent 4
  stays off, so AFBD won't fetch and the translating master 2 isn't exposed.
* The firmware has no direct reference to the TCON block `0x0588xxxx`. The
  window path logs "No need to enable panel crtc timing" for our 720p 1:1
  case (`b_crtc_timing:0`). So a full refresh is not expected to rewrite
  panel timing, the [[mips-relaunch-rewrites-panel-timing]] trap. **Not
  proven.** T3 reads TCON before and after.
* The panel selector `0x051c006c` is never written by the firmware, so the
  panel stays on the console.

**T3 (needs approval; the board is down).** A production cold or
warm-shared session with HDMI locked; the original proper is fine, since
the frame-programmer record `+0x40…+0x54` is already in production's comm
trace.
1. Preconditions as T1, plus TCON `0x05880020/24` = 720p. Stage-1 snapshot
   `t3-before`.
2. `win rn 2`. Read immediately and after 5 s:
   * AFBD `0x05600000–0x9f`;
   * composition `0x030`/`0x178`/`0x1b8`;
   * mux `0x05600068`;
   * the frame-programmer record (`trace+0x40…+0x54`): expect stage `6103`
     with **mode 1**;
   * TCON `0x05880020/24`;
   * IOMMU fault lines;
   * the elog delta.
3. `win rn 0` (restores the lock-time value; runs one partial refresh).
   Snapshot `t3-after`.
4. Operator: confirm the console throughout. No camera needed.

**Stop and recover:**
* If TCON changes, recover by a reboot (U-Boot re-latches 720p on both
  paths).
* If an IOMMU fault appears: stop and reboot.
* Never `memory_agent en 4` in T3.

**What T3 tells us:**
* AFBD's capture-mode configuration: the source-0 **format byte for the
  firmware's NV16/compressed input** (the 4:2:2 question of §1.5), the
  geometry, mux bit 8 = 0 and composition `0x30` bit 22 = 1.
* Whether the programmer fills address slots `0x70+` or relies on the
  hardware pair at `+0x320`. That is the range §10.3 item 3 has to
  identity-map.
* If the result is clean, the next step is the IOMMU identity map (kernel DT,
  offline), then T4 = agent 4 nonvisible, then the selector flip.

### 10.11 T3 result (10-23): the firmware programs AFBD for HDMI on request

[Evidence](hdmi-evidence/2026-10-23-panel-source-stage1/t3/README.md).
`win rn 2` with HDMI locked ran NR WriteReg with mask `0x7e02` in mode 1,
and the frame programmer configured AFBD source 0 for capture:
* mux `0x022`, `0x10` bit 4 clear, composition `0x30` bit 22 set;
* 1280×720 with strides `0x500`;
* chroma lines 720 (4:2:2);
* **format byte `0x02`**;
* no address slots: the addresses come from the hardware capture pair
  `+0x320/324`.

Source 0 stayed disabled. There were no faults, TCON timing and the
selector were unchanged, the console showed throughout, and `refresh_node`
went back to 0.

What this settles:
* **§1.5:** the AFBD 4:2:2 format encoding is **2**, observed. This is the
  direct NV16 scanout candidate for revision 2's KMS plane too.
* **§10.3 item 2** is solved by the firmware's own lever.
* **§10.3 item 3:** the master-2 identity map needed is the capture ring in
  the frame-buffer pool (`0x4bf41000–0x4d940fff`).

**Remaining for the firmware path:**
1. A kernel DT `iommu-addresses` entry identity-mapping the pool for the
   display (offline, then a boot).
2. T4: memory agent 4 (source 0 enable) with the selector still on the
   console, nonvisible, checking for no fault and the fetch running.
3. T5: flip the selector `0x051c006c` to video, operator-confirmed. That's
   the first HDMI picture through the firmware path.

Then the event wiring: on LOCKED, `win rn 2`, `memory_agent en 4/5/6`, and
the selector; on loss, the reverse.

### 10.12 IOMMU identity map for the pool, and T4 (built offline, 10-23; not run)

**The change.** Same mechanism as 0080 (logo carveout) and 0126 (the VE's
IOVA reservation). The display, VE and AV1 share IOMMU group 0, and the
first device to initialise the domain (the VE) populates the IOVA allocator.
* `framebuf@4bf41000` gets `iommu-addresses = <&display 0x4bf41000 0x1a00000>`,
  and the display lists it in `memory-region` as `"mips-framebuf"`. The
  driver allocates by the name `"framebuffer"`, so that is unchanged.
* A new reg-less `iova-reserve-mips-framebuf` node,
  `iommu-addresses = <&ve 0x4bf41000 0x1a00000>`, is listed by the VE. Cedrus
  looks up its pool by the name `"pool"`, so that is unchanged.
* `of_iommu_get_resv_regions()` therefore yields DIRECT for the display
  (reg equals IOVA) and RESERVED for the VE.

**Production form:**
`patches/kernel/0188-arm64-dts-h713-identity-map-the-mips-frame-buffer-pool.patch`
(**not in `series`** until tested).
* It applies to the current kernel tree. Both board DTBs compile with the
  four properties: bench 34 806 bytes, projector 33 477 bytes.
* It changes only the DTS; the U-Boot DTS sync picks it up at the next
  U-Boot build and ignores the properties.

**Test artifacts (single change against the installed boot):**
* `tools/display/make-pool-identity-dtb.py` derives the T4 DTB from the
  **installed FIT's own fdt-1** (`4c4fe0c5…`). Its decompiled diff is
  exactly the four edits (new phandles `0x37`/`0x38`): `build/t4-fit/fdt-pool.dtb`
  (34 806 bytes, `6407105d…`).
* `build/t4-fit/h713-kernel-t4.fit`: 7 795 808 bytes, `8a230590…`.
  * Kernel `Image.gz` hash `0d2410f7…` is unchanged from the installed FIT.
  * The installed FIT is `build/out/h713-kernel.fit` `0877293b…`, verified
    byte-identical to the board's FAT copy.
  * A control FIT packed the same way from the original DTB is exactly
    7 795 668 bytes, the installed size.
* `tools/hdmi/build-t4-script.py` (self-test passes) builds
  `build/hdmi-t4-2026-10-23/`:
  * `warm-shared.scr`: build-warm-shared's output, in the format the runner
    expects;
  * `t4-cold.scr`: the installed script, whose source is byte-identical to
    the board's `h713-hdmi.scr` `391835c5`.
  * Both carry only four substitutions in `hdmi_image`: the FIT load
    `fatload mmc 1:2 … h713-kernel.fit` becomes
    `ext4load mmc 1:1a … /root/panel-source-t4/h713-kernel-t4.fit` (the FAT
    has only ~3.3 MB free, too little for a second 7.8 MB FIT),
    `filesize == 76f460`, `fdt_size == 87f6`, `fdt_end -le 5076f460`.
  * The installed script, FIT and services are untouched.

**T4 (needs approval).** The source-0 fetch, nonvisible.
1. **Stage:** copy `h713-kernel-t4.fit` and `t4-cold.scr` to
   `/root/panel-source-t4/` on the ext4 root (p26) and verify their hashes.
   The FAT is not touched; nothing installed is replaced. Removal is one
   `rm -r`. (Staged and verified 2026-10-23: `8a230590…`, `8fc4e7c5…`.)
2. **Boot the T4 FIT on the cold path** (recommended: it avoids the
   warm-reboot panel-black risk).
   * Operator cold power-on, then replug serial to stop autoboot at the cold
     prompt (GP6 0, MIPS 0).
   * `tools/serial/run-t4-cold.py` requires the `=>` prompt and a cold
     census (MIPS `0x0306101c` and GP6 `0x07090118` both 0, `md.l` reads
     only), YMODEMs `t4-cold.scr` to `0x52000000` (CRC-verified), and sends
     `source` exactly once, with no retry.
   * Alternative: `run-warm-shared.py run --prepared build/hdmi-t4-2026-10-23`
     from a production cold session.
3. **Check the DT took effect**, read-only:
   * `framebuf@4bf41000/iommu-addresses` exists;
   * group 0 `reserved_regions` shows `0x4bf41000-0x4d940fff direct`, plus
     the reserved entry;
   * services healthy; no IOMMU fault lines.
4. **With HDMI locked:** `win rn 2`, then check AFBD's capture configuration
   as in T3.
5. **`memory_agent en 4`** (source 0 enable). The selector stays on the
   console. Read:
   * `0x05600010[1:0]` and the commit;
   * AFBD status and counters;
   * the `+0x320/324` pair cycling;
   * IOMMU fault lines, **which must stay 0**;
   * a stage-1 snapshot.

   If AFBD doesn't fetch, add `memory_agent en 5/6` (NR, proven safe in T1),
   because the firmware's own signal set is `0x78`.
6. **Restore:** `memory_agent dis 4` (and 5/6), `win rn 0`. The next normal
   boot uses the untouched production FIT. Keep or delete the T4 FIT
   depending on T5.

**Stop rule.** Any IOMMU fault line, or a change on the panel, means
`memory_agent dis 4` at once, then a reboot. A master-2 fault wedges the
AFBD fetch engine, and with it the console, until reboot.

**What T4 tells us:** whether source 0 fetches the capture ring cleanly
through the identity map, the last unknown before T5's selector flip.

**Not read:** `0x06940928/968` (capture DMA, inside the forbidden
`0x0694xxxx` window; inferred from the VDE counter instead),
`0x07091xxx`, GP7. Nothing in this snapshot writes anything.

### 10.13 T4 result (2026-10-23): source 0 fetches through the identity map

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/t4/` and
`t4-run/`.

* **Boot.** Cold boot `34ee92bd…`; `run-t4-cold.py` sourced `t4-cold.scr`
  once, which loaded the pool-identity FIT from ext4. Group 0's
  `reserved_regions` gained `0x4bf41000 0x4d940fff direct`. Services were
  healthy and there were no fault lines.
* **`win rn 2`** reproduced T3's capture programming exactly.
* **`memory_agent en 4`:**
  * set `0x10[1:0] = 3`;
  * AFBD `+0x58`/`+0x5c` went from a constant 0 to continuously varying
    values (`0x47–0x69`, `0x3b–0x4b`), and froze at once on `dis 4`. They
    track source 0's fetch progress, so **AFBD fetched**.
  * IOMMU interrupt status and error registers stayed 0, there were no
    kernel fault lines, the selector stayed on the console, and TCON stayed
    at 720p. NR agents 5/6 weren't needed.
* **Restore:** `dis 4` and `win rn 0`. Source 0 is off; the capture
  configuration persists, which is harmless.
* **Panel:** not watched during the steps; it showed the Linux console
  afterwards. The selector register stayed `29000000` throughout.

**Next (T5, needs approval):** with source 0 fetching, flip the selector
`0x051c006c` to `0x39000000`, watching the panel. Revert by writing
`0x29000000`. T5 answers whether the 4:2:2 format `0x02` picture is
correct on glass, including range. Kernel `0188` is now proven on hardware
as a test FIT; it isn't in the series yet.

### 10.14 T5 design: the selector flip (visible)

T5 asks the last question before event wiring: **with source 0 fetching
the capture ring, does selecting the video route put a correct HDMI
picture on the panel?** It is the first visible step. It needs the operator
watching and filming, so it gets its own turn and a "ready".

**What the panel route needs.** The KMS video plane is the only Linux code
that ever selects video (`sun50i-h713-afbd.c`, `atomic_update`). Besides
programming source 0, it makes exactly two route writes:

* the selector `0x051c006c = 0x39000000`;
* the YUV chroma gain `0x05140508 = 0x144c0000`. Bits 23:16 are a linear
  chroma gain; 0 is greyscale (register index, DECD 08-31).

On `stop` it puts both back to their probe values. On this boot the gain
reads **`04000000`** (chroma gain 0), so the selector alone shows a
greyscale picture. T5 uses that as a free intermediate stage: luma
first, then colour. A greyscale picture that's otherwise right separates
fetch, format and geometry problems from colour and range problems.

The KMS driver touches neither register unless a client commits to the
video plane. The board has no DRM clients and `h713_geometry` reports
`video off`, so nothing races the test.

**Tooling** (offline-tested, nothing run on the board):

* `tools/hdmi/t5-board.py` runs on the board as the transient unit
  `h713-t5` (`systemd-run`), so the revert doesn't depend on ssh.
  * **Allowlisted writes only:** selector `29000000`↔`39000000`; gain
    `gain_idle` (read at start)↔`144c0000`; shell `memory_agent en 4` /
    `dis 4`.
  * Its reader refuses `0x07091xxx`, `0x0694xxxx` and GP7.
  * The revert sits in `finally` on every path: gain back, then selector
    back to the console, then `dis 4`. On a clean board it's idempotent.
  * The self-test covers the happy-path write order, six of the nine preconditions
    refusing with no write and no shell command, a no-fetch abort before
    the selector, an IOMMU-status abort, a new-fault-line abort, an
    exception mid-run, the allowlist and forbidden reads, and an idempotent
    revert. It passes 8/8. Four mutations (revert, hold, IOMMU guard, a
    precondition) each make it fail.
* `tools/hdmi/run-panel-source-t5.py stage | check | run | revert` is the
  host side. It verifies the staged script's hash before every use, and
  collects the unit's JSON events.

**Preconditions** (checked by the script; any failure refuses with no
write):

1. The boot carries `0188`'s map: group 0 `reserved_regions` has
   `0x4bf41000 0x4d940fff direct`. Today that means the T4 cold path (boot
   `34ee92bd…` still qualifies).
2. HDMI locked (MemoryAgent `+0xb5 == 1`), host output connected.
3. Bypass `0x58` (master 2 translates), selector `29000000`, KMS video
   plane off.
4. AFBD `0x10 == 03000200`: source 0 in the `win rn 2` capture
   configuration, disabled. (If a reboot cleared it, run `win rn 2` first,
   as in T4.)
5. TCON 720p words, IOMMU interrupt status 0, no kernel fault lines.

The operator sets up beforehand: the PC shows a known still image
full-screen, ideally colour bars with a greyscale ramp from black to white,
plus some text. Don't move the projector (keystone/ceiling stays put).
Film the panel on a phone.

**Sequence** (one "ready" runs it all, about 40 s):

| t | Step | Panel expectation |
| --- | --- | --- |
| 0 | `memory_agent en 4`; require `0x10[1:0] = 3`, `+0x58/+0x5c` moving, guards clean (else abort) | console, unchanged |
| ~5 s | **Stage A:** selector → `39000000`; hold 15 s, guards every 250 ms | **greyscale** PC picture |
| ~20 s | **Stage B:** gain → `144c0000`; hold 15 s | **colour** PC picture |
| ~35 s | **Revert:** gain → idle, selector → `29000000`, `dis 4` | console |

Snapshots are taken at `pre`, `en4`, `A-grey`, `A-grey-end`, `B-colour`,
`B-colour-end` and `reverted`. Each records the selector, gain, `0x10`,
the fetch tell, the `+0x320` pair, bypass, IOMMU status, TCON, mirror,
the blue-screen words (`0x05140d54`, `0x051c00b8`, `0x051c0364`) and the
fault count.

**Stop rule.**

* **Automatic.** Any of the following reverts at once (gain, selector,
  `dis 4`) and skips the remaining stages:
  * an IOMMU interrupt-status bit;
  * a new kernel fault line;
  * a TCON 720p word changing;
  * the panel mirror word changing;
  * source 0 not fetching before stage A.

  A TCON change won't come from the selector. If one does, it's recorded,
  and the 720p re-latch is done from the startup script's own sequence,
  never improvised.
* **Manual.** `run-panel-source-t5.py revert`, at any time.
* **If the board stops answering** (ssh gone, panel stuck):
  * Don't warm-reboot with HDMI connected, because of the 10-16
    panel-black risk.
  * Recover with a cold power cycle: serial + USB unplugged, at least
    1 minute off.
  * The next boot uses the production FIT, so the identity map and agent
    4 are gone.

**What to look for** (operator, from the video):

| Seen in stage A | Meaning |
| --- | --- |
| Steady greyscale PC picture, full panel, text sharp | fetch, format `0x02` and geometry right; go on to stage B |
| Black | route not passing (blue-screen mute, or selector ineffective): compare the blue words in `A-grey` |
| Green or flat field | fetching nothing usable (NV12 lesson: green = no data) |
| Shear, diagonal tearing, repeated strips | stride or geometry mismatch |
| Picture squashed into half height, or doubled | 4:2:2 vs 4:2:0 chroma lines |
| Rolling, flicker, torn frames | ring/address handoff between capture and AFBD |
| Frozen picture (move the mouse on the PC) | `+0x320` pair not advancing for AFBD |
| Offset or cropped | NR window placement (49,22 origin) |

| Seen in stage B | Meaning |
| --- | --- |
| Correct hues on the bars | CSC right |
| Blue↔orange or red↔cyan swapped | Cb/Cr order swapped |
| Washed-out blacks (black looks grey), bars dull | limited-range video shown as full |
| Crushed blacks, clipped whites, bars over-saturated | full-range video shown as limited (stock had AVI Q=2 → `b_full_range=1`) |
| Too much or too little saturation, hues right | gain value, not route |

Also note: latency when moving the mouse (rough), and whether HDMI audio on
the speaker is unaffected.

**Result handling.** A correct picture in both stages closes the
"firmware path works" question. The remaining work is product wiring:
`0188` into the series, the MemoryAgent config gap, the `win rn 2` / agent /
selector / gain sequence driven from the signal event, and the revert on
signal loss (§3, §9). Any defect in the table above becomes a focused
offline investigation before another visible run.

### 10.15 T5 result (2026-10-23): a live picture; chroma at half rate

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/t5/` (register
record, video analysis). The video is `local/lcd-photos/test_105/`.

* **Run:** clean. All 9 preconditions passed. Both 15 s stages held, the
  revert completed, and there was no abort. IOMMU status stayed 0, there
  were no new fault lines, and the 720p timing and the mirror and
  blue-screen words didn't change.
* **Stage A (greyscale):** the host desktop, live, full panel, sharp, and
  steady. Every luma feature of the test chart reproduces in place.
  **Fetch, luma format and geometry are right.**
* **Stage B (colour):** display line *y* takes chroma from source line
  *y/2*. The hue squares' colours land on the two rows below them, the
  gradient bars' green and blue land on the hue row, and the lower half of
  the picture has no colour. Hue order is correct, so Cb/Cr are not
  swapped. Range can't be judged yet.

**Reading.**

* AFBD, as `win rn 2` programmed it (format `0x02`, chroma lines `720`),
  reads the NV16 capture ring with a 4:2:0 chroma step.
* Stock never shows that ring directly. NR (agents 5/6, inside the
  firmware's own `0x78` signal set) stores frames as mode 1 / colour
  format 2, and AFBD reads NR's frames.
* So T4/T5's "agent 4 only" route is a partial pipeline, and format `0x02`
  is most likely NR's output format. **(Corrected in §10.16:** format
  `0x02` is the firmware's code for the 4:2:2 capture input, and AFBD
  reading the ring is the stock route. The missing piece is NR's history
  DMA.)

**Next, offline first:**

1. From the frame programmer `0x8b1a4538` and the stock elog, establish
   where AFBD's addresses come from when NR runs, and what format `0x02` /
   compression mode 1 mean for the source-0 fetch.
2. Then T6: T5 with `memory_agent en 5 6` before the selector (both were
   safe in T1). This also needs NR's buffers inside the identity-mapped
   pool, which is to be checked offline.

A direct 4:2:2 AFBD format code on the raw ring is the fallback, not the
first choice. It would bypass the firmware's NR (and its deinterlace and
noise reduction), and it means writing AFBD under the firmware.

### 10.16 Where AFBD's addresses and format come from with NR running, and T6 (offline RE, 10-23)

Sources: `display.bin` (`4380f1b3`) disassembly, the stock 10-07 level-5
elog, the 08-31 stock and Linux block sweeps, and read-only DRAM/register
reads on boot `34ee92bd…`. Evidence: `t5/nr-history-regs.txt`.

**1. AFBD reads a capture frame, by design.**

* NR's CalcWindow (vtable slot 8, `0x8b1a36fc`) takes the incoming frame
  buffer from the window info (`+0x30`) and stores it twice:
  * `+0x4c = dynamic_cast<TVsFrameBuffer*>(fb)`;
  * `+0x50 = dynamic_cast<TAfbdFrameBuffer*>(fb)`.

  `0x8b1acb3c` is `__dynamic_cast`, with typeinfos `0x8b20770c` and
  `0x8b20772c`.
* Exactly one of the two is non-null, and the frame programmer
  `0x8b1a4538` branches on that:
  * a `TAfbdFrameBuffer` (decoder output) takes the compressed branch
    (`0x8b1a3e60`, AFBD `0x2c/0x50/0x54`);
  * a `TVsFrameBuffer` (capture) clears those fields and runs
    uncompressed.
* On our boot the frame is a `TVsFrameBuffer` named "none": 1280×720,
  colour format 4, no compression. Its addresses aren't in the object;
  AFBD takes them from the hardware pair `+0x320`.
* Stock HDMI is the same (`m_afbd_source_mode 1`, CapWinNode colour format
  4, chroma 720 lines). **AFBD reading the NV16 capture ring is the stock
  route, not a shortcut.**
* The format byte is `resolver(NR +0x5c = 4) = 2`. The resolver maps
  colour formats 0/2/4/6/8,11/9,12/14/15 to AFBD 0/1/2/3/4/5/7/6. The
  stock decoder plays at 0 (NV12, as does KMS) and P010 is 6/7.
* AFBD's own registers are consistent for 4:2:2: format 2, chroma rows
  `0x4c = 720`, strides 1280.
* **§10.15's guess that format `0x02` is NR's output format was wrong.**

**2. NR's compressed 4:2:0 frames are its own temporal-NR history, not
AFBD's source.**

* NR also holds a second `TVsFrameBuffer` (`+0x58`): compression 1, ratio
  15625, colour format 2 (4:2:0, chroma 360 lines). That's the "Compression
  mode 1, C 0x168" buffer in the stock elog.
* `NRWinNode::WriteReg` (`0x8b1a48cc`) fills two composition DMA
  descriptors from that layout, each a rowbyte word plus a line-count word:
  * mask bit `0x4`: `0x174/0x178` (C) and `0x1b4/0x1b8` (Y);
  * mask bit `0x2`: `0x274/0x278` (C) and `0x2b4/0x2b8` (Y).
* MemoryAgent `OnOff` (`0x8b153d7c`) turns them on with bit 31 of the
  line-count words:
  * **agent 5 (`0x20`)** → `0x178`/`0x1b8`;
  * **agent 6 (`0x40`)** → `0x278`/`0x2b8`.

  (For completeness: agent 4 (`0x10`) is AFBD `0x10[1:0]` plus a commit;
  agent 3 (`0x08`) is capture DMA bit 31 at `0x06940928/968`.)
* No firmware code writes a DRAM address into composition `0x100–0x3ff`.
  The history addresses are already in place on both stacks (16-byte
  units), identical in the stock and Linux 08-31 sweeps and on this boot:

  | Pair | Y (`0x140`/`0x144`, `0x240`/`0x244`) | C (`0x180`/`0x184`, `0x280`/`0x284`) |
  | --- | --- | --- |
  | Address | `0x4D35A000`, `0x4D4F3000` | `0x4D028000`, `0x4D1C1000` |

* **Stock runs with both history DMAs on.** The enable bits are set
  (`0x178 = E002021C`, `0x278 = E0020168`) even during decoder playback,
  and the firmware's own signal set is `0x78` (agents 3–6).
* Ours has them off (`6…`). **T4/T5 ran AFBD and the panel with NR's
  temporal-NR history disabled**, a configuration stock never uses.

**3. Identity map: not needed for NR.**

* The history buffers span `0x4D028000–0x4D68BFFF`, inside the `no-map`
  frame-buffer pool (all display buffers come from `display_cfg.xml`'s
  single 26 MB pool), so Linux never owns them.
* NR is IOMMU master 3, which the bypass `0x58` exempts. Only AFBD
  (master 2) translates, and its source, the capture ring, is in the map
  (T4/T5).
* T1 enabled agents 5 and 6 on a production boot with no faults and no
  panel change.

**4. Hypotheses for the half-rate chroma, ranked.**

* **(H1, leading) NR's chroma path is 4:2:0 and expects its history
  DMAs.** NR's TNR works at 4:2:0 (history format 2, chroma 360 lines).
  With the history DMAs off, its 4:2:2 input chroma is consumed at 4:2:0
  line rate, so display line *y* gets input chroma line *y/2*. Luma, which
  has no 4:2:0 step, comes through intact, as T5 showed. The test: turn
  the history on, as stock does.
* **(H2) A composition or proc input-format setting left at the decoder's
  4:2:0 value.**
  * Proc's `mb_420_format` (node `+7`) only offsets the line-enable start;
    it isn't a register bit, so proc is unlikely.
  * Stock's HDMI lock never runs proc's WriteReg either.
  * No stock register capture exists under HDMI to diff against.
* **(H3) AFBD format 2 isn't plain NV16 in hardware.** It's the
  firmware's own code for this input and the stock route uses it, so it's
  least likely. The fallback test is format 4.

**T6 (needs approval): T5 with NR's history on.** Same runner, same
operator procedure, one flag: `run-panel-source-t5.py stage`, then
`check --with-nr`, then `run --confirm-t5 --with-nr --output …/t6`.

* **Extra preconditions** (refuse with no write):
  * the four history addresses equal the stock values above;
  * all four enable bits are clear.
* **Sequence:**

  | t | Step |
  | --- | --- |
  | 0 | `memory_agent en 5`, `en 6`; require bit 31 in `0x178/0x1b8/0x278/0x2b8`, guards clean (else abort: `dis 6`, `dis 5`) |
  | ~1 s | `en 4` (as T5) |
  | ~6 s | stage A greyscale, 15 s |
  | ~21 s | stage B colour, 15 s |
  | ~36 s | revert: gain, selector, `dis 4`, `dis 6`, `dis 5` |

* **Tooling:** `t5-board.py --with-nr`.
  * The allowlist gains only `en`/`dis 5` and `6`, and T5 mode still
    refuses them.
  * The self-test passes 12/12. It adds the T6 order, the NR-enable abort
    before agent 4, the NR preconditions, and T5 refusing the NR commands.
  * Four new mutations each fail it.
* **Stop rule:** as §10.14 (IOMMU status, new fault lines, TCON, mirror,
  manual `revert --with-nr`). A wedge means a cold power cycle, never a
  warm reboot with HDMI connected.
* **Reading the result:**

  | Seen | Meaning | Next |
  | --- | --- | --- |
  | Colour lines up (squares coloured in their own row; hue row free of the bars' green/blue; wedge neutral) | H1: NR history is part of the picture path | Product sequence = the firmware's own `0x78` (agents 3–6) plus selector and gain; then range check and event wiring |
  | Same y/2 picture | H1 out | Stock HDMI register capture (vendor stack, read-only sweep of AFBD, composition `0x000–0x2ff`, proc, route `0x500–0x5ff`) to diff against ours, before any further visible test |
  | Ghosting, smear on motion, frozen or torn picture | history running against stale or mismatched buffers | Revert; check the history addresses and line counts against the stock sweep offline |

### 10.17 T6 result (2026-10-23): NR history changes nothing

* **Run:** clean. NR history on (all four enable bits `e…`), then agent 4,
  both stages held 15 s, and the full revert. IOMMU status 0, no fault
  lines, TCON unchanged.
* **Operator:** stage B looked the same as T5. **H1 is out.** The half-rate
  chroma isn't caused by NR's history DMA being off.
* **Remaining hypotheses:** H2 (a downstream 4:2:0 setting left from the
  decoder configuration) and H3 (AFBD format 2 isn't plain NV16).
* **Next:** stop guessing from phone video. §10.18 adds a pristine
  measurement of the frame at known points in the pipeline.

### 10.18 Pristine measurement instead of phone video (plan, 10-23)

**What the hardware offers.** `display.bin` has no display writeback or
frame-dump path:
* the `wb_*` strings are white balance;
* `dump_*` / `DbgDump*` print parameters, not pixels;
* the panel-side output (after AFBD → composition → proc → panel) can't be
  read back by any firmware or ARM path we know of. Only external LVDS
  capture hardware could, which isn't worth it.

So the measurement brackets the defect from both ends instead.

1. **Source, pristine (read-only, ready now).**
   * `tools/hdmi/read-coherent-frame.py --width 1280 --height 720` copies
     a completed NV16 frame from the capture ring that AFBD reads. It
     copies the frame twice and accepts it only if both copies are
     byte-identical and the probe pages are unchanged.
   * Convert it on the host (`ffmpeg -f rawvideo -pix_fmt nv16 -s 1280x720`).
   * Compare it with the test chart rendered at 1280×720: per-plane PSNR,
     plus a **row cross-correlation of the chroma plane** against the
     reference. That gives the chroma row mapping as a number: 1:1 = the
     ring is right, *y/2* = the defect is already in the capture.
   * This tells us whether the input really is NV16 with chroma in place,
     the assumption T5/T6 rest on. It needs no writes and no panel change.
     If `VideoFreeze` is ever needed for a still ring, it's a firmware
     call (`THal_Vp_EnableVideoFreeze`), not used here.
2. **Panel, made unambiguous (one filmed frame, no judgement).** A
   diagnostic chart built for this question replaces the general test
   chart:
   * luma carries large row labels every 45 lines (0–15);
   * chroma carries 16 flat colour bands of the same height, in a known
     hue order.
   * One still frame from the phone then reads off the mapping directly:
     the band colour behind label *n* names the source row band. Expected:
     *n* → *n* if right, *n* → *n*/2 for the T5/T6 defect. That's robust
     to camera colour and exposure, because only band identity matters.
3. **Known-good control on the same panel.** The KMS NV12 plane (AFBD
   format 0) is proven correct. Showing the same diagnostic chart through
   it (an NV12 still via `h713-play`/kmssink, no HDMI) gives a reference
   photo of each band's colour, under the same camera and panel.

**What each outcome means.**

| Ring (1) | Panel (2) | Defect is in | Next |
| --- | --- | --- | --- |
| 1:1 | *n* → *n*/2 | AFBD format 2 handling or downstream (H2/H3) | stock HDMI register capture to diff against ours; offline: which composition/proc words differ between the decoder (4:2:0) and capture (4:2:2) states |
| *y/2* already | *n* → *n*/2 | capture/write side (CapWinNode, colour format 4 vs what the DMA writes) | CapWinNode's own fields in DRAM, offline. Its registers sit in the forbidden `0x0694xxxx` window, so they're never read |
| 1:1 | *n* → *n* | fixed (whatever changed) | range and colour check |

### 10.19 Ring readback result (2026-10-23): the input is right

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/ring-readback/`.

* All three ring pairs were read twice each, read-only. The copies differ by
  at most 1 LSB (capture noise).
* Scored against the chart at 1280×720, the ring's **chroma maps 1:1 at
  offset 0** (mean error 1.63). The best *y/2* map scores 29.09. Luma is
  also 1:1 (4.49 against 59.85).
* The ring frame renders as the chart exactly.
* **So the defect is after the ring:** AFBD's format-2 fetch, or a
  downstream 4:2:0 setting (H3 or H2). The capture side and NR history
  (T6) are cleared.

**Next, ranked:**

1. **Offline, free:** diff every AFBD/composition/route/proc word we have
   in two states:
   * the decoder state: KMS NV12 playing correctly (letterbox baselines
     and 08-31 sweeps);
   * our capture state (`t3-after`, `t4-en4`).

   Look for the words that differ outside geometry, and for any whose
   meaning tracks 4:2:0. It needs no board time.
2. **Known-good diff:** a read-only register capture of stock Android
   playing HDMI (vendor stack, same addresses as the 08-31 sweep). It's the
   only reference for the real HDMI configuration. It costs an Android
   round trip.
3. **Discriminating write test (needs approval):** the T5 sequence with
   AFBD format byte 2 → 4 (the 08-30 note: format 4 doubles the chroma row
   accounting, i.e. 4:2:2), written after `win rn 2`. A fixed picture
   proves H3. It means writing AFBD under the firmware, so it comes after
   1 and 2.

### 10.20 Offline register diff: KMS NV12 (correct) vs capture (y/2) (10-23)

**Inputs** (no board time):
* `docs/reference/letterbox-baseline-2026-10-04/native-720p.txt`: the KMS
  NV12 plane at 1280×720, correct on the panel;
* `console.txt`: the same boot, console;
* `t4-en4/t4-en4-regs.txt`: our capture state with source 0 fetching.

All three come from the same 1182-word set: AFBD 256, comp 222, route 390,
proc 130, LVDS 104, DETN 51, vblend 32.

**Every difference is accounted for:**

| Word(s) | NV12 → capture | Explained by |
| --- | --- | --- |
| AFBD `0x10` format byte | `00` → `02` | resolver: yuv420_888 → 0, **yuv422_888 → 2** (below) |
| AFBD `0x4c` chroma rows | 360 → 720 | 4:2:0 → 4:2:2 accounting, correct for the ring |
| AFBD `0x68` bit 8 | 1 → 0 | programmer: bit 8 = (mode ≠ 1) |
| AFBD `0x70–0xa4` | KMS queue → 0 | capture mode takes addresses from the `+0x320` pair |
| comp `0x030[11:10]`, `0x040[7]`, `0x040[3]` | `c00`/`0`/`1` → `0`/`1`/`0` | `0x8b1a43f0`: the firmware's source-mode / V-mirror router (mode 2 decoder vs mode 1 capture) |
| comp `0x030[22]` | 0 → 1 | NR WriteReg: (mode = 1) |
| comp `0x178/0x1b8` | 540/1080 → 360/720 | NR history descriptors (4:2:0 history, correct) |
| comp `0x434/0x438`, `0x534/0x538` | rowbyte 45 / 240 lines → 80 / 720 | capture-side line buffers for the 4:2:2 1280×720 frame (CapWinNode's rowbyte 80, 720 lines) |
| proc `0x050/0x150` start | 27 → 26 | proc's line-enable start: `mb_420_format` 1 → 0 (stock HDMI logs exactly 26) |
| route `0x508` | `144c0000` → `04000000` | chroma gain; T5/T6 set `144c0000` for stage B |
| LVDS `0x06c` | video → console | snapshot taken with the selector on the console |
| route `0x57c–0x5b8`, AFBD `0x58/0x5c/0xb8/0xbc/0x184/0x30x`, DETN `0x83c`, LVDS `0x170`, route `0x168/0xe00` | content-dependent | statistics, counters and status (none has a firmware writer) |

**No 4:2:0 leftover in the covered words.** A scan of the capture state
for any 12- or 16-bit field still holding a half-height value (`0x168` ±1,
`0xb4`, `0x2d`) finds only:
* NR's history descriptors (`0x178`, `0x278`), which are legitimately
  4:2:0;
* DETN `0x048` and vblend `0x014`, the same in both states (not
  format-related).

**The AFBD format enum, resolved.** `display.bin`'s own colour-format table
(`0x8b1f4bb0`) names the resolver's inputs:
* yuv420_888 → 0
* yuv420_101010 → 1
* **yuv422_888 → 2**
* yuv422_101010 → 3
* yuv444_888 / rgb_888 → 4
* yuv444_101010 / rgb_101010 → 5
* P010 high / low → 6 / 7

That matches every hardware fact: the KMS NV12 plane writes 0 and is
correct on the panel (`03000013`); P010 is 6/7; and the 08-30 note had
format 4 doubling the chroma rows (4:4:4 is full-height).

**§1.6's "Linux-written 3 = NV12" is stale.** It comes from the
`0066` experiment (`AFBD_FMT_NV12 3`). The video plane has written 0 since
`0149`. So format 2 is the firmware's correct code for the 4:2:2 ring, and
**H3 is now unlikely.**

**What's left.** The covered words show the firmware's capture
configuration applied coherently, and that's presumably also what stock
runs. The y/2 must come from one of:
* (a) a word outside the 1182-word set;
* (b) a configuration stock gets from the ARM HAL or the boot that ours
  doesn't (stock's HDMI path follows `THal_Vp_SetTNR/SetSNR` and friends
  over CPU_COMM, and our boot applies the logo's NV12 LogoRegData);
* (c) AFBD's 4:2:2 handling needing something the firmware doesn't set
  (least likely now).

**Next, ranked:**

1. **Stock HDMI register capture** (§10.19 step 2), now clearly the best
   value.
   * A read-only sweep of the same blocks as the 08-31 stock sweep (full
     AFBD, composition `0x000–0xfff` minus the `0x0500153x` lock window,
     route, proc, LVDS, DETN, vblend), taken while stock shows a live HDMI
     desktop with correct colour.
   * Diff it against an equal sweep of ours in the T5 state. The first
     word that differs outside geometry and statistics is the answer, and
     it settles (a) to (c).
2. **Discriminating write test, if the stock capture is impractical**
   (needs approval). In the T5 state, set AFBD format 2 → 0 (4:2:0) with
   `0x4c` 720 → 360.
   * If the halving is downstream, the picture's chroma goes to *y/4*.
   * If AFBD already halves format 2, the picture is unchanged.
   * Either way it places the defect, from one filmed still with the
     §10.18 band chart.

### 10.21 Plan: stock HDMI register capture, plus a matching sweep of ours (design only, 10-23)

**Goal.** One known-good reference for the real HDMI picture path:
* stock Android showing a **correctly coloured** HDMI desktop, swept with
  the same address list as ours;
* ours swept in the T5 state (chroma *y/2*).

The first word that differs outside geometry and statistics is the
candidate for the half-rate chroma (§10.20 (a)–(c)). DRAM node dumps on
both sides also cover (b), configuration that never shows up as a
register.

#### 10.21.1 What gets read

**List A: proven on both stacks.** Read on stock and on our MIPS-live
Linux on 08-31, and the panel block on 10-01. This is
`stock-capture.sh display` unchanged:

| Block | Range | Words |
| --- | --- | --- |
| composition | `0x05000000–0x05000ffc` | 1024 |
| (block at) | `0x05040000–0x05040ffc` | 1024 |
| DETN | `0x050c0000–0x050c0ffc` | 1024 |
| route | `0x05140000–0x05140ffc` | 1024 |
| proc | `0x05180000–0x05180ffc` | 1024 |
| panel/LVDS | `0x051c0000–0x051c03fc` | 256 |
| AFBD | `0x05600000–0x056001fc` | 128 |

**List A′: proven on both stacks by the 08-28 stock / 08-29 Linux block
sweeps** (`docs/reference/stock-android-block-sweep-2026-08-28.txt`; same
windows, same tool format). Added after a coverage review against every
earlier sweep. Before the review, the plan missed these:

| Block | Range | Why it matters here |
| --- | --- | --- |
| TVTOP | `0x05700000–0x057000bc` | display routing that U-Boot's `h713_display_prepare` writes. A routing or mux difference between stacks would never show up in the window-layer pages |
| MIXER | `0x0525c000–0x0525c07c` | video/OSD mixer: the stage after the selector; a format or colour setting here was never compared |
| DE_OSD | `0x0524c000–0x0524c07c` | OSD path, for completeness of the mix |
| (`0x05240000`) | `0x05240000–0x0524003c` | the 08-28 sweep's unlabelled window next to DE_OSD |
| LAYER | `0x05280080–0x052800bc` | layer controls |
| PLL | `0x058c0010–0x058c002c` | display PLL (pixel clock, for timing parity) |
| MIPS status | `0x03061010–0x0306101c` | firmware run state (`0x0306101c` = 1 when alive) |

Plus `stock-capture.sh snap` per state: the CCU page `0x02001000` and the
PPU `0x07001000`, both always-on and proven. It's cheap context for
clock-gate differences.

**List B: extended.** Read routinely on ours, new on stock. B runs after A
in the same call, so a problem can't cost A's data.

| Block | Range | Why |
| --- | --- | --- |
| AFBD | `0x05600200–0x056003fc` | capture pair `+0x300–0x33c`, OSD `+0x140` page tail; ours reads all 256 words in every snapshot |
| vblend | `0x05200000–0x0520007c` | the 32 words our snapshot set reads |
| TCON | `0x05880000–0x058800fc` | panel timing (ours reads `0x1c–0x24` routinely; the cold script writes `0x0c–0x30`) |
| IOMMU | `0x02010000–0x0201013c` | stock's bypass and master configuration (ours: `0x58`) |

**List C: DRAM, raw** (`hidtvreg-raw` on stock, `/dev/mem` on ours):
* the MIPS image `0x4b100000 + 0xe41000`: code, heap, the window-layer
  nodes and MemoryAgent;
* the loaded `display_cfg.xml` at `0x4be01000`;
* the elog `0x4b270000 + 2 MiB` (inside the image; parsed separately).

Offline, a vptr scan finds NRWinNode (`0x8b207a50`), CapWinNode,
ProcWinNode, PanelWinNode, MemoryAgent (`0x8b1fb818`) and the
frame-buffer objects (vptrs `0x8b207740`/`0x8b207754`). The fields are
compared side by side: NR `+0x4c/+0x50/+0x58/+0x5c/+0x60`, MemoryAgent
`+0x8/+0xc/+0xb5`, Proc `+7`, and the rest. Stock's heap addresses differ
(10-07: the HDMI object sat 8 bytes off ours), so the dump is found by
vptr, never by fixed address.

**Deliberate gaps.** These stay unread; if A–C find nothing, they're
what's left:
* **composition beyond `0x05000fff`.** The next page holds the
  `0x0500153x` lock window; pages above it have never been read on either
  stack.
* **the capture block `0x0694xxxx`.** Forbidden. Its configuration is
  covered indirectly by CapWinNode's fields in the DRAM image, and the ring
  itself is proven correct (§10.19).
* **the receiver and its wrapper.** Forbidden. The AVI/colour information
  it acts on is in the elog and the DRAM image.
* **any block never read on either stack.** A first read on stock risks a
  wedge mid-session, so it would need its own powered/gated check and its
  own approval.

**Exclusions** (both sides; the readers refuse them, and each has a
self-test):
* `0x069xxxxx` (including capture DMA `0x0694xxxx`);
* `0x0709xxxx` (RTC GP6/GP7 and the CPUS window `0x07091xxx`);
* the composition page `0x05001xxx` (the `0x0500153x` lock window);
* the VE/AV1 blocks (not needed; `stock-capture.sh` gates them anyway);
* every receiver/wrapper register.

No writes on either side: `hidtvreg-read` / `hidtvreg-raw` only on stock,
and a read-only `/dev/mem` mapping on ours.

**Two samples per state, 5 s apart.** Words that differ between a state's
own two samples are statistics or counters, and are filtered out before
any cross-stack comparison.

#### 10.21.2 States

| State | Stack | Picture | Purpose |
| --- | --- | --- | --- |
| O1 | ours (T4 boot, now) | console, source 0 off, capture config from `win rn 2` | our baseline |
| O2 | ours | **T5 stage B** (agent 4, selector video, gain `144c0000`), *y/2* chroma | the defective state |
| S0 | stock | launcher, no HDMI source | stock baseline (decoder/OSD config) |
| S1 | stock | HDMI1, host at stock's EDID default (10-07: 1920×1080), test chart full-screen | known-good, as stock is normally used |
| S2 | stock | HDMI1, host forced to **1280×720** on HDMI-A-1, same chart | known-good with **input timing matched to ours**: the primary comparison against O2 |

**Comparisons**, by a new `tools/hdmi/diff-display-sweeps.py`:
* **S2 vs O2 (primary).** Remaining differences are ranked by block, with
  geometry words recognised from the letterbox table.
* **S1 vs S2:** which words follow the input timing, so 1080p-specific
  differences don't mislead.
* **S0→S2 vs O1→O2:** stock's decoder→capture transition against ours
  (and §10.20's NV12→capture).

The operator photographs the chart in S1 and S2, and confirms the colour
is right in both. If stock's colour isn't right, the reference is void and
the plan stops there.

#### 10.21.3 Order and procedure

**Phase 0: offline, no board.** Build and self-test:
1. `tools/hdmi/display-sweep.py` (ours, `/dev/mem`). It reads lists
   A+B+C with output byte-compatible with `hidtvreg-read`
   (`aaaaaaaa 0xVVVVVVVV`). Its self-test checks:
   * its list A equals `stock-capture.sh`'s `DISPLAY_BLOCKS` exactly;
   * its list A′ equals the 08-28 sweep's eleven windows line for line;
   * every exclusion refuses.
2. `stock-capture.sh sweep <label>`: `snap`, then lists A, A′, B, then C (raw), with
   the same exclusion guards. A dry run under `dash` on our Linux checks
   that its address list matches (as on 10-01).
3. `t5-board.py --hold-b SECONDS` (bounded to 120 s), so O2 can be swept
   twice during stage B. The self-test grows to cover the bound and the
   revert after a long hold.
4. `diff-display-sweeps.py` and an offline node walker
   (`tools/mips/walk-wce-nodes.py`). The diff's self-test runs on the 08-31
   stock and Linux sweeps, and must reproduce their known DECD differences.

**Phase 1: ours, in the current boot** (no cold boot needed; the board is
already T5-ready):
* O1: `display-sweep.py` twice.
* O2: `run-panel-source-t5.py run --hold-b 60`, with `display-sweep.py`
  twice during stage B.
* No operator look needed. The picture is the known T5 *y/2* one, the
  stop rule is §10.14's, and the revert is automatic.
* This step runs the visible T5 sequence again, so it needs its own
  approval.

**Phase 2: round trip to stock** (`docs/flash.md` Methods 5–6;
`docs/stock-capture-operator-sheet.md` §0–2). Every operator action is its own turn, and Claude waits for
"ready" or "done".
1. **Host checks (read-only):**
   * board LBA `0x10` against the payload inside
     `build/out/h713-restore-spl.bin` (never against `build/out`'s U-Boot
     image);
   * vendor boot0 at LBA `0x100`;
   * `super` / `boot_a` / `vendor_boot_a` / UDISK (f2fs);
   * `misc` (the RescueParty left-over);
   * record U-Boot proper's hash at LBA `0x49ac00` (expect `1b1f702f`).
2. **Decision: the vendor elog.** `tools/stock/vendor-elog-cfg.sh on`
   writes two bytes of the vendor FAT's `display_cfg.xml`, reverted `off`
   after the session.
   * With it: the HAL/CPU_COMM calls and window-layer decisions of S0–S2,
     aligned with the registers. It covers (b).
   * Cost: about a 3-minute Android boot.
   * Recommended; it needs explicit approval because it writes the vendor
     FAT.
3. **Switch:**
   * Claude: `reboot-to-uboot.py`, then `console.py 'run switch_vendor'`,
     which copies the vendor boot0 to LBA 16. This is the only eMMC write
     besides 2.
   * Operator: **unplug serial and all USB, power off for at least 1
     minute**, power on with HDMI connected. Replug serial only after the
     Android logo, so it can't interrupt the vendor boot. Wait for the
     launcher. If recovery appears: **Try again, never Factory data
     reset.** Then plug USB in.
4. **Stock capture:**
   * Claude: `capture-session.sh check`, `push`, then `baseline`, which
     proves the firmware text is board-B `display.bin` and the cfg is
     `mode 2 / level 5`.
   * **S0:** `stock-capture.sh sweep S0-a`, then `S0-b`.
   * **Operator:** select HDMI1 in AwSource. The host shows the test chart
     full-screen on HDMI-A-1. Operator photo, plus a "colour correct?"
     check.
   * **S1:** sweep `S1-a`, `S1-b`.
   * **Claude:** set HDMI-A-1 to 1280×720 on the host (`cosmic-randr
     mode`, reverted after).
   * **Operator:** photo and colour check.
   * **S2:** sweep `S2-a`, `S2-b`, then `capture-session.sh pull`.
   * **Risky tiers 1–4** (§10.21.4), each streamed to the host, still in
     S2. Only after the pull. A hang here is expected and harmless: go to
     step 5.
5. **Return:**
   * Operator: FEL button.
   * Claude: `sunxi-fel version`, then `sunxi-fel -p spl
     build/out/h713-restore-spl.bin`; expect `RESTORED-OK` on UART.
   * Operator: cold boot (serial and USB unplugged, at least 1 minute
     off).
   * Claude:
     * verify LBA 16 and U-Boot proper's hash against step 1;
     * check that the production cold boot reaches HDMI handoff;
     * `vendor-elog-cfg.sh off`, verified;
     * restore the host's HDMI-A-1 mode.

**Phase 3: offline.** Run the three comparisons and the node diff; write
§10.22 with the candidate word(s) and a guarded test for the next turn.

**Budget:** Phase 0 is offline work. Phase 1 takes about 3 minutes.
Phase 2 is about 1–1.5 h of wall time, including the 3-minute elog boot,
with about six operator turns.

**Risks and guards:**

| Risk | Guard |
| --- | --- |
| Board stuck on the vendor stack | restore SPL checked byte-for-byte against the board before switching; FEL restore proven 08-26, 09-29, 10-01 and 10-07 |
| A read wedges the SoC | lists A/B/C only; A is proven on both stacks; exclusion self-tests; B after A; a wedge costs a power cycle, no data |
| Android state loss | never Factory data reset (adb authorisation lives in UDISK) |
| Back-powering through USB | unplugged before every cold boot |
| Reference not actually correct | operator colour check in S1/S2; void if wrong |
| Timing confound (stock 1080p vs ours 720p) | S2 matches ours; S1 vs S2 isolates timing-only words |
| Leaving the vendor FAT modified | `vendor-elog-cfg.sh off` is part of the return checklist, and verified |

#### 10.21.4 Risky reads, last (added at the user's suggestion)

The stock session ends in a FEL restore and a cold boot anyway, so a SoC
wedge **as the very last step** costs only a power cycle. A read can't
change persistent state; the real brick risks are the eMMC writes (switch
and restore), and those are unchanged. So the session closes with the
reads we never risk on our own stack, ranked by how likely they are to
find the half-rate step.

**What the ranking rests on.**
* §10.19 puts the defect after the capture ring, and between AFBD and the
  panel every block has only ever been read as its **first page**.
* A static scan of every directly addressed MIPS register access in
  `display.bin` (266 words, 14 pages) finds everything in the display path
  already inside lists A/A′/B. The remainder are the forbidden capture page
  (22 words), a UART-area page and scan artefacts.
* Most firmware accesses go through base pointers the scan can't follow,
  so the unread pages remain the gap.
* LogoRegData only touches the panel prologue (LVDS lane, TCON, PLL), not
  the video path.

**Tiers** (`RISKY=1 stock-capture.sh risky N`, run through `adb exec-out`
so every line streams to the host as it's read):

| Tier | Reads | Why |
| --- | --- | --- |
| 1 | composition page 2 `0x05001000–0x05001ffc` (1 page), including the `0x0500153x` lock word | the NR/composition block sits between AFBD and proc and is the prime suspect for a 4:2:0 step; the lock word reads fine MIPS-live with routing, which stock is |
| 2 | pages 2–64 of each video-path block: comp, `0x05040000`, DETN, route, proc, LVDS, vblend, plus AFBD pages 2–16 (455 pages) | each block's later pages are unread on both stacks |
| 3 | one 4-word probe per unexplored 64 KiB in `0x05000000–0x05ffffff` (242 probes) | finds live blocks nobody has mapped, for a later full read |
| 4 | the capture page `0x06940000` | forbidden on ours (wedges when unpowered); powered on stock HDMI. Lowest value, since the ring is proven correct |

**Guards.**
* The mode refuses to run without `RISKY=1`.
* Its own guard still refuses `0x0709xxxx` (GP7 is never touched;
  `0x07091000` always wedges and answers nothing), VE and AV1, and allows
  only `0x05xxxxxx` and the capture page.
* Each read is announced (`## READ addr`) before it happens, so after a
  wedge the stream's last line names the address that did it. That's
  useful knowledge in itself.
* It runs only after `capture-session.sh pull` has the safe phases on the
  host.
* A wedge goes straight to the FEL restore (power cycle with the FEL
  button). Nothing from the tiers needs another Android boot.

Tiers run one per command, in order. The operator only needs to know that
a hang at this point is expected and harmless. Anything a tier finds is
read on our side later only as specific words, with its own approval.

#### 10.21.5 Phase 0 result (2026-10-23): tools built and self-tested offline

| Tool | Self-test | Mutations caught |
| --- | --- | --- |
| `tools/hdmi/display-sweep.py` (ours, `/dev/mem` read-only; A, A′, B, C) | passed: 20 entries, 5964 words + 14.9 MB raw; A = `DISPLAY_BLOCKS`, A′/B/C = the shell lists, A+A′ ⊇ the 08-28 sweep, every exclusion and page crossing refused | 4/4 |
| `stock-capture.sh sweep` | **dash dry run on the board** (stdin, `DRY=1`, no reads, no files): 20 plan lines, identical to `display-sweep.py --dry`; injected `06940928` and a page crossing both refused | — |
| `stock-capture.sh risky` (§10.21.4) | dash dry run per tier: 1 / 455 / 242 / 1 reads; refuses without `RISKY=1`; an injected GP7 address is refused | — |
| `t5-board.py --hold-b` (15–120 s) + host passthrough | 14 groups, including the bounds and an IOMMU fault 1.5 s into a long stage B (abort, full revert, no "held") | 4/4 |
| `tools/hdmi/diff-display-sweeps.py` | passed: letterbox table parsed from the driver (42 words); synthetic classes; the 08-28/08-29 AFBD count (37) reproduced; snapshot format parsed | 3/3 |
| `tools/mips/walk-wce-nodes.py` | passed: find by vptr (incl. odd word index), pointer-by-pointee comparison, a real field difference, object-count mismatch | 3/3 |

On real data, the diff tool reproduces §10.20's table, KMS NV12 vs capture:
34 CONFIG, 2 geometry, 15 queue. It also files `comp+178/1b8`
(NR history) under CONFIG, because the KMS table doesn't program them.

Nothing was written to the board. The dry runs went over ssh stdin, and the
only board-side activity was the `dash` process. **Next: Phase 1 (ours,
needs approval).**

#### 10.21.6 Phase 1 result (2026-10-23): our sweeps taken

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/phase1-sweeps/`
(and the T5 run in `phase1-o2/`).

* **O1:** console. **O2:** T5 stage B, held 60 s. Both were sampled twice.
  All four sweeps are complete (A, A′, B and the 14.9 MB MIPS image), each
  about 0.3 s on the board.
* The T5 run ended `ok` with no aborts, IOMMU status 0 throughout, and a
  full revert.
* O1 vs O2: 49 CONFIG words out of 5964 (205 statistics filtered out).
* **New lead from the full composition page:** `comp+ac0–ad4` carry luma-
  and chroma-sized counts, and the chroma ones are about half the luma
  ones (`0xe100`/`0x38400` vs `0x70d0`/`0x1c360`), consistent with 4:2:0
  accounting at the composition input. The stock S2 values decide whether
  that's the defect or normal.

**Next:** Phase 2, the stock round trip. It needs the operator, plus
decisions on the vendor elog and the host's 720p mode for S2.

### 10.22 Stock HDMI capture result (2026-10-23): stock never uses the firmware capture route

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/phase2-stock/`.
Raw sweeps, images and risky-tier streams are in
`local/h713-lab/stock-capture-20261023/`. The round trip was clean: FEL
restore, cold boot, every hash identical, vendor elog off again.

**The known-good reference.** The operator confirmed stock's HDMI picture
correct at 1080p (S1) and at 720p (S2, timing matched to ours): "none of
our tests made it look like this".

**What stock does:**
* AFBD source 0 runs the **decoder configuration**: format 0 (NV12 4:2:0),
  chroma rows 360, comp `0x030 = 0xC00`, and every IOMMU master translating
  (`0x02010030 = 0`).
* It reads **1280×720 NV12 frames at IOVAs** that alternate between
  `0x00200000`, `0x00400000` and `0x00600000`, with C = Y + `0xE1000`.
* The capture ring keeps cycling underneath.
* The GPU interrupt rate goes from about 5/s (launcher) to about 440/s
  (HDMI). SurfaceFlinger runs at 45 % CPU and `awtvinputservice` at 29 %.
* **So stock GPU-composites the TV-input layer into NV12 frames and
  presents them through the decoder path**, the same route it uses for
  file playback (10-01) and for its whole UI (the launcher is on the video
  plane too).
* The firmware's own NR node is in capture mode 1 with colour format 4 on
  stock as on ours, but its frame programmer never takes AFBD over.

**Consequences for this design:**
1. The firmware mode-1 route (T3–T6: `win rn 2`, agent 4, format 2, the
   selector) is a path stock **does not use**. Its half-rate chroma is not
   a missing setting that stock supplies, and further work on it means
   reverse-engineering an unused path. **Recommendation: stop pursuing it
   as the product route.** T3–T6 remain the record of what it does.
2. **Stock's route is revision 1's shape:** the capture ring → a 4:2:2 →
   4:2:0 conversion → AFBD as an NV12 video plane. Our KMS NV12 plane is
   already proven correct on the panel. The open design question is the
   conversion engine. Stock uses the GPU; our candidates are the GPU
   (Panfrost, as in the GPU fallback plan), the VE, or GE2D
   (`0x05240000`, active on stock but not for HDMI).
3. The §10.20 lead `comp+ac0–ad4` (chroma counts about half luma) is
   normal 4:2:0 accounting: stock has `0x000E1000` / `0x00070800` there.

**Risky tiers (operator's suggestion): no hang anywhere.** On stock with
HDMI live:
* composition page 2 and the lock words read fine;
* 127 live pages beyond the first page of each block;
* 24 previously unmapped live 64 KiB blocks;
* the capture page reads fine (117 words).

This maps the display address space for later work. It isn't needed for
the conclusion above.

### 10.23 Plan: characterise the firmware path before choosing a route (design only, 10-23)

**Why.** §10.22 shows stock uses the GPU route, but T5/T6 put a live,
sharp, correctly sized picture on the panel through the firmware path with
no ARM work at all. The final route will be whichever is most efficient
and beneficial, and that needs the firmware path's capabilities measured,
not inferred.

**Measurement points.**
* **The capture ring:** pristine, byte-exact, read-only (§10.19). Both
  routes start here, so anything learned here helps either one.
* **The panel:** no readback path exists (§10.18). It's measured by
  filmed stills of purpose-built charts, judged by band identity rather
  than colour accuracy, so camera colour and exposure don't matter.

#### 10.23.1 Test 1: capture front end, read-only (do first)

Tool: `tools/hdmi/characterise-capture.py` (to build, offline-tested
first). For each host mode on HDMI-A-1:
1. set the mode with `cosmic-randr`;
2. wait for lock: the firmware log (`EnterSignalSteady`) and the ring pair
   cycling;
3. read a ring frame twice and accept it only if both copies are equal
   within ±1 LSB (§10.19's method);
4. read the CapWinNode / NR / MemoryAgent fields with the walker, and the
   elog window;
5. compare the frame with the chart, rendered on the host at that mode.

Restore the host mode at the end.

**Modes:** 640×480; 720×480 and 720×576 (if offered); 1280×720 @ 60 / 50;
1920×1080 @ 60 / 50 / 24; 1080i if the host offers it. Only modes in the
EDID the host reports are used.

**What it reports, per mode:**

| Feature | How |
| --- | --- |
| Capture scaling (does 1080p arrive as 1280×720, as stock's elog shows, CapWinNode ratio `0xaaaa`?) | the ring's geometry, the CapWinNode window fields, and PSNR / edge sharpness against the chart scaled the same way |
| Colour conversion | least-squares fit of the RGB → YUV matrix (BT.601 vs BT.709) and offsets / range (full vs limited) from the chart's known patches |
| Chroma siting and filtering | chroma-edge position and width at the hue-square boundaries |
| Interlaced input | field order and weave vs single field in the ring for 1080i |
| Frame cadence | ring slot rotation against the input rate (24 / 50 / 60), from timed reads of the `+0x320` pair |
| Input range limits | whether the ring and the firmware windows follow modes smaller than the panel (640×480) |

**Safety:** reads only (`/dev/mem` O_RDONLY, the §10.21 exclusions). The
only state change is the host's own HDMI output mode, as in stage 1. No
panel change, no operator look.

**Value:** it tells us what the hardware gives for free before any
conversion engine (scaling, CSC, deinterlace). That cuts the work of the
GPU / VE / GE2D route as much as it informs the firmware path.

#### 10.23.2 Test 2: locating the half-rate chroma (needs approval)

A 2×2 on the T5 runner, on the 4:2:2 ring, in T5's stage-B state. Each
cell changes one or two words, then the operator films one still of the
§10.18 band chart (luma row labels 0–15, 16 flat colour bands):

| | AFBD format 2 (yuv422_888), `0x4c` = 720 | AFBD format 0 (yuv420_888), `0x4c` = 360 |
| --- | --- | --- |
| **capture routing** (comp `0x030 = 0x00400000`, `0x040[7] = 1`, `[3] = 0`) | T5 as measured: *y/2* | *y/4* means the halving is downstream of AFBD; *y/2* means AFBD halves |
| **decoder routing** (comp `0x030 = 0x00000C00`, `0x040[7] = 0`, `[3] = 1`; stock's values) | **correct colour means the capture routing is the culprit, and the firmware path is viable with that routing** | *y/2* expected (4:2:0 read of 4:2:2 data) |

The routing values come from the firmware's own router `0x8b1a43f0`
(§10.20) and match stock S1. Every word in the matrix is one the firmware
or the KMS driver already writes. A cell is applied after `win rn 2` and
`en 4`; the revert writes back the T5 values, then `dis 4`. The runner
extension:
* adds an allowlist of exactly these words and values;
* reuses §10.14's guards (IOMMU status, fault lines, TCON, mirror);
* holds each cell for 15 s;
* is self-tested with the fake board, as `t5-board.py` is.

**Reading:** the band behind row label *n* names the source band, so the
mapping (*n*, *n*/2, *n*/4) is read straight off one still.

#### 10.23.3 Test 3: cross-route comparisons (once a second route exists)

These only mean something side by side, so they run identically on each
route:

| Comparison | Method |
| --- | --- |
| Latency, glass to glass | a host-side flashing marker; the host monitor and the panel in one 240 fps shot; delay in frames |
| ARM / GPU / VE cost | `/proc/stat` CPU, interrupt rates (GPU, VE, GE2D, `dec`, `osd-afbd`) over 30 s |
| DRAM traffic | AFBD fetch counters plus the ring and NR history sizes, per frame |
| Tearing and pacing | a moving vertical bar at a known speed; stills for tears, slo-mo for judder |
| Temporal NR | a noisy, high-motion clip with agents 5/6 on and off: noise against ghosting |
| Small inputs | 640×480 / 720×576: does the route letterbox / upscale to the panel by itself (proc upscaler, window layer) |
| Audio sync | the same marker with an audio click, against the measured video latency |

**Expected shape:**
* The firmware path should be close to zero ARM cost, with low latency
  (capture → AFBD direct, no conversion pass), if its colour can be fixed.
* A conversion route costs GPU or VE time and at least one frame of
  latency per pass, but runs on the proven KMS NV12 plane.

#### 10.23.4 Order and approvals

1. Build `characterise-capture.py` and its self-test offline, using the
   ring and node data we already hold (Phase 1 / §10.19).
2. Run Test 1. It needs the T4-style boot only if the walker's fields
   matter. The ring itself is readable on the production boot, read-only,
   with no approval beyond "board time".
3. Build the Test 2 runner extension and the band chart, then run Test 2
   (approval, operator stills).
4. Test 3 once a conversion route has a prototype.

#### 10.23.5 Test 1 tool: built and self-tested offline (2026-10-23)

**`tools/hdmi/capture-probe-board.py`** (board side, fed over ssh stdin,
`/dev/mem` O_RDONLY, guard on `0x069xxxxx`/`0x0709xxxx`):
* **`state`:** the lock flag; the NR node by vptr and its input
  `TVsFrameBuffer` (w, h, compress, colour); CapWinNode's 0x50 words; the
  capture pair.
* **`frame H SPAN`:** copies the slot finished just before the current
  one, twice. It accepts only copies within ±1 LSB and retries if the
  writer reaches the slot. The slot must be inside the pool.
* **`cadence S`:** a timeline of capture-pair changes.

**`tools/hdmi/characterise-capture.py`** (host): `plan | run --out DIR
[--modes …] [--chart FILE] | analyse DIR | --self-test`.
* For each mode: set it with `cosmic-randr`; wait for lock (flag, stable
  geometry, cycling ring); take the reference as a `cosmic-screenshot`
  cropped to HDMI-A-1, deleting the full screenshot at once (or `--chart`).
* Then the frame, the cadence and the analysis: stride by row
  correlation; PSNR; the colour fit against BT.601/709 × full/limited
  (coefficients and offsets judged separately); row maps for Y and C;
  chroma shift; line doubling / comb; cadence against refresh.
* The host mode is restored in `finally`, even when a mode fails or the
  run aborts.

**Self-test, 7 groups, passed:**
1. The colour fit recovers all four standards from synthetic NV16
   (coefficients within 0.01, offsets within 1.5 codes).
2. Stride 544 is found inside a 640 span, and the planes split back
   exactly.
3. Line doubling is detected; noise is not.
4. On the **held 10-23 ring frame** against the chart: stride 1280, Y and
   C rows 1:1 (C error 3.5 against 29.4 for *y/2*), PSNR Y 40.8 dB,
   nearest BT.709 limited. The fit on held data is informational, since the
   chart file isn't COSMIC's rendering.
5. The probe on the **held O2 MIPS image**: locked, NR `8b89bfc0`,
   `fb_in` 1280×720 colour 4, CapWinNode found. `frame` returns exactly
   the named slot; copies differing by 5 are refused and 1-LSB noise is
   accepted; a stuck pair is refused; the forbidden-window guard is in
   place.
6. The randr parse, mode choice (no refresh the host doesn't offer) and
   screenshot crop box.
7. The host mode is restored after a failing mode and after an abort.

**Mutations:** 7 of 8 caught (restore, stride, the 1:1 row map, the copy
tolerance, no-signal, refresh tolerance, …). The probe's "writer reached
the slot" retry survives. It's a redundant guard behind the double copy,
and the fake board's data can't race, so it's recorded as untested.

**Limit found by `plan` (read-only):** under our HDMI-in EDID the host
offers only **640×480 @ 59.94 and 1280×720 @ 60**. Characterising 1080p,
50 Hz, 24p or interlaced input needs the EDID served by `h713-hdmi-signal`
to advertise those modes. That's a board-side change and a decision,
separate from this read-only test.

#### 10.23.6 Test 1 result (2026-10-23): the capture front end is clean BT.709-limited 4:2:2

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/test1-capture/`.
Production boot, read-only. Only the two modes our EDID offers.

* **1280×720 @ 60:** a 1280×720 ring; luma PSNR **54.9 dB** against the
  host's actual output; Y and C rows 1:1; no chroma shift; **BT.709
  limited** (coefficients ±0.002, offsets ±0.33 codes); progressive; a
  3-slot rotation at the input rate.
* **640×480 @ 59.94:** a **640×480 ring** (no capture scaling; the
  firmware's input buffer follows the input); 54.2 dB; 1:1; also **BT.709
  limited**.

**Implications for both routes.** The input to any route is a clean,
full-resolution 4:2:2 frame in BT.709 limited range.
* The **firmware path's** only known defect is presentation (the y/2 chroma
  of §10.15), not capture.
* A **conversion route** needs only 4:2:2 → 4:2:0 (and scaling for inputs
  other than 720p). No colour conversion is needed, as long as the NV12
  plane is presented as BT.709 limited.
* Small inputs reach the ring at native size, so their scaling to the
  panel is downstream work in either route.

**Not yet measured** (needs the EDID to offer them): 1080p (stock
downscales at capture), 50 Hz / 24p, interlaced. **Next by plan: Test 2**
(the 2×2 locating the y/2, needs approval and operator stills).

### 10.24 Widening the HDMI-in EDID for Test 1 (built offline, 10-23; install needs approval)

**Why.** Under the production EDID the host offers only 1280×720 @ 60 and
640×480 (§10.23.5). Test 1's remaining questions (capture downscaling of
1080p, 50 Hz, 24p, interlaced) need the host to be offered those modes.

**Where the EDID lives.** It's the 256-byte `edid_trial_data` array in
`h713-hdmi-signal.ko`. The module's SCP (CPUS/OR1K) payload copies it into
the receiver's EDID RAM; `tools/hdmi/make-edid-trial-code.py --edid`
generates the header. The program is identical for any valid EDID
(verified), so this is a **data-only** change. The production EDID is
`tools/hdmi/fixtures/hdmi-audio-edid.hex` (`edab9bfc…`, every audio and
recovery bench since 10-08).

**The widened EDID:** `tools/hdmi/fixtures/hdmi-wide-edid.hex`
(`a78b6946…`), made by `tools/hdmi/make-wide-edid.py`.
* **Base block:** byte-identical except the range-limits descriptor, now
  23–61 Hz V, 15–68 kHz H, 150 MHz (was 59–61 / 31–46 / 80).
* **DTD 1 is still 1280×720 @ 60 and preferred**, so a host that isn't
  forced still picks 720p.
* **CTA block:** the audio, speaker, HDMI VSDB and video-capability blocks
  are byte-identical and in the same order. Only the Video Data Block
  grows: VIC 4, 1, **16, 31, 32, 34** (1080p 60/50/24/30), **19** (720p50),
  **5, 20** (1080i 60/50), **2, 3** (480p), **17, 18** (576p).
* **No 4K.** 148.5 MHz is the ceiling. Stock offers 4K30, but our receiver
  path has only run 720p.
* **Self-test passed** (`make-wide-edid.py --self-test`):
  * `edid-decode --check` reports **conformity PASS** and lists every
    mode;
  * the preferred mode is 720p;
  * the non-video CTA blocks are identical;
  * the generator emits identical code for both EDIDs and reproduces the
    production header exactly.

  Three mutations each fail it.

**The module: binary-swap the EDID, don't rebuild.**
* A control rebuild of the production module isn't byte-identical to the
  installed `0a6987ce…`: the host's clang moved from 23.1.1 to 23.1.3 after
  the validated 10-16 build. So `tools/hdmi/patch-signal-edid.py` copies the
  **installed module** with exactly the 256 EDID bytes replaced.
* The production EDID occurs exactly once, at `0x23c0`, and modules aren't
  signed (no `CONFIG_MODULE_SIG`).
* Result: `build/edid-wide/h713-hdmi-signal-wide.ko` = **`d221c5ef…`**.
  The self-test checks that only the window changed, that the inverse patch
  restores `0a6987ce` exactly, and that duplicate, absent and
  bad-checksum EDIDs are refused.
* Cross-check: the two compiler builds (production and wide EDID) differ
  only in 51 bytes, the EDID data plus the build-id note.

**The install bundle:** `build/edid-wide/bundle/` (`SHA256SUMS`
`4e5f3c2e…`).
* `build-startup.py` output, with the wide module swapped in and the
  **installed** `h713-hdmi-hold-guard` (`9140e310`) kept.
* The repo's newer hold guard (`96f37655`, from the DSP-bench work, never
  deployed) is deliberately left out, so this update changes nothing else.
* Read-only comparison with the board's installed generation: **exactly
  one file would change, `h713-hdmi-signal.ko`**. Every out-of-scope file
  matches, so `update-signal-owner.sh` will accept it.

**Install, verify, run, revert** (each phase needs approval; nothing done
yet):
1. Copy the bundle to `/root/edid-wide-bundle/` and run its
   `update-signal-owner.sh`.
   * It keeps a backup of the replaced files in
     `/var/lib/h713-hdmi-startup/signal-owner.*`.
   * The running owner keeps its in-memory module; the new EDID takes
     effect at the **next cold boot**.
2. Operator cold boot (serial and USB unplugged, at least 1 minute off,
   HDMI connected).
3. **Verify:**
   * the installed module is `d221c5ef`;
   * the host's `card1-HDMI-A-1/edid` decodes to the wide EDID;
   * the host still defaults to 1280×720 @ 60;
   * the startup handoff, `h713-hdmi-signal` ready and the speaker service
     are all healthy.
4. **Test 1** over the new modes (`characterise-capture.py run`). The host
   mode is restored afterwards.
5. **Revert or keep.** Revert = the same procedure with a production
   bundle (`0a6987ce`), then a cold boot.

**Risks:**
* **Untested on our stack at 148.5 MHz.** The receiver and MIPS firmware
  handle 1080p on stock (same hardware, same `display.bin`), but our Linux
  stack has only locked 720p.
* **HDMI audio clock recovery** (N/CTS) has been validated only at 74.25
  MHz.
* **Sources that ignore "preferred".** Some sources pick the highest mode
  (consoles, TV boxes). With the wide EDID installed permanently, they
  would arrive at 1080p, which affects the unvalidated audio path.

**Recommendation:** keep this a **bench change**. Install, run Test 1,
then revert to the production EDID until audio at 1080p has its own
validation.

#### 10.24.1 Wide-EDID Test 1 result (2026-10-23)

Evidence: `test1-capture/README.md` (wide-EDID section) and `test1-capture/wide/`.

* **Capture-side colour conversion follows the input format:** BT.601
  limited for 480p/576p, BT.709 limited for 640×480 and HD (fits within
  0.0024).
* **1080p is downscaled to 1280×720 in hardware at capture** for all four
  1080p rates, with rows 1:1 and chroma correct, as stock does. SD and 720p
  arrive at native size.
* **1080p50 loses about a third of its frames:** about 30–34 distinct
  frames per second, against about 51 for 720p50 and 576p50. The capture
  pair advances on 60 Hz ticks for every input. So a route fed from the
  ring sees judder on 1080p50 sources unless the capture's frame-lock
  behaviour can be changed. This is open.
* **Interlaced:** not testable from this host (COSMIC hides the 1080i
  VICs).
* **Reverted:** the installed files are byte-identical to pre-session; the
  production EDID returns at the next cold boot.

**For the route decision:**
* Both routes get, for free: correct BT.601/709 limited 4:2:2, and a
  1080p → 720p hardware downscale.
* Neither route has scaling up to the panel for SD inputs: they arrive at
  native size.
* The 1080p50 judder applies to anything reading the ring.

#### 10.23.7 Test 2: built offline (2026-10-24); run needs approval

**Runner:** `t5-board.py --matrix` (host: `run-panel-source-t5.py run
--confirm-t5 --matrix`).
* It runs the T5 sequence (agent 4, selector, gain), then from the stage-B
  state reads the **cell baseline** (comp `0x030`/`0x040`, AFBD
  `0x10`/`0x4c`).
* It steps through five cells, 15 s each:

  | # | Routing | AFBD format / chroma rows | Expected if… |
  | --- | --- | --- | --- |
  | 0 | capture | 2 (4:2:2) / 720 | T5 picture, *y/2* (positive control) |
  | 1 | capture | 0 (4:2:0) / 360 | *y/4* → halving is downstream of AFBD; *y/2* → AFBD halves |
  | 2 | decoder | 2 / 720 | **correct** → the capture routing in composition is the culprit |
  | 3 | decoder | 0 / 360 | *y/2* expected |
  | 4 | capture | 2 / 720 | back to the T5 picture (shows the run is in sync with the video) |

* **Words per cell:**
  * comp `0x030` bits 22/11/10 and comp `0x040` bits 7/3, read-modify-write
    from the baseline, using the firmware router `0x8b1a43f0`'s two
    settings;
  * AFBD `0x10[15:8]` and `0x4c`;
  * then the publish latches `0x6c` = 1 and `0x14` = 1, as the firmware
    programmer ends.
* AFBD's mode bits (mux `0x68` bit 8, `0x10` bit 4) **stay in capture
  mode**. Stock sets them for decoder routing, but here they would make
  AFBD read its empty queue slots (address 0, an IOMMU fault). The
  allowlist refuses any write to `0x68`.
* **Revert:** the cell words go back to the baseline first (with their own
  publish), then the T5 revert (gain, selector, `dis 4`). It runs on every
  path, including aborts. The guards are §10.14's, checked every 250 ms.
* **Self-test, 17 groups:**
  * the exact write sequence for every cell;
  * the end state equals the baseline with source 0 off;
  * one publish per cell;
  * no `0x68` write;
  * an IOMMU fault in the decoder cell aborts and restores everything;
  * the allowlist refuses the mux, arbitrary routing and odd formats;
  * T5 mode writes no cell words.

  Four mutations each fail it: the cell restore removed, the publish
  removed, wrong decoder routing bits, and the restore method disabled.

**Chart:** `tools/hdmi/make-band-chart.py`, 1280×720 with 16 flat bands of
45 lines.
* Each band carries a row label 0–15, drawn black with a white outline in
  luma, three times across.
* Hue order (by search): every (*n*, *n*/2), (*n*, *n*/4) and (*n*/2,
  *n*/4) pair is at least 67.5° apart, so the three mappings look clearly
  different. The self-test checks that.
* Output: `local/panel-source-t5/test2/band-chart.png`. Set it as the
  HDMI-A-1 wallpaper (1280×720, no scaling).

**Board prerequisites:** the T4 cold path (`run-t4-cold.py`, the `0188`
identity-map FIT staged in `/root/panel-source-t4/`), HDMI locked,
`win rn 2` run (AFBD in capture config, `0x10 == 03000200`), selector on
the console. These are the T5 preconditions.

**Operator:** one "ready" for the whole run, filming throughout. It takes
about 2 minutes: a 15 s greyscale stage, a 15 s colour stage, five 15 s
cells, then the revert. For each cell, the band colour behind three or four
labels (for example 4, 8, 12, 15) gives the mapping.

#### 10.23.8 Test 2 result (2026-10-24): the AFBD format doesn't matter; decoder routing needs queued frames

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/test2-run/`.
The video is `local/lcd-photos/test_106/`. The run was clean: all writes
read back, no faults, a full revert. The panel showed the earlier test chart
(the band chart wasn't applied as the wallpaper), which reads the mapping
just as well.

* **Capture routing, AFBD format 4:2:0 / 360 chroma rows (cell 1):
  identical to T5** (*y/2*). The format fields don't drive the
  capture-routed picture.
* **Decoder routing (cells 2/3):** a broken picture (the chart tiled into
  narrow columns across the top third, the rest flat green or
  green/yellow). Composition in decoder routing expects AFBD in
  queue-address mode with frames in its address queue, as KMS and stock
  run it. That's the conversion route.

**Where this leaves the firmware path.**
* It gives correct luma, size and timing with no ARM work, but vertical
  chroma at half rate.
* Neither AFBD's format fields nor NR history (T6) change that.
* The remaining unexplored lever is the capture-side words at AFBD
  `+0x300–0x33c`, which differ from stock's.
* Everything shows this path isn't how the hardware is meant to present
  HDMI (stock never uses it).

**Recommendation:** one last read-only look, then stop. Decode the
`+0x300–0x33c` words offline against stock (the S1/S2 sweeps hold stock's
values) and see whether a 4:2:0/4:2:2 bit stands out. If one does, it's a
single-word Test 3; if not, close the firmware path and move to the
conversion route. Test 1 has already characterised its input: clean
4:2:2, BT.601/709 limited, hardware 1080p → 720p.

#### 10.23.9 AFBD `+0x300–0x33c`, ours vs stock (offline, 10-24): no format knob; firmware path closed

Data: ours O1/O2 (Phase 1 sweeps), stock S0/S1/S2 (two samples each), and
the stage-1 / T3 / T4 / letterbox snapshots, which hold AFBD's full page.

| Word | Ours | Stock | Verdict |
| --- | --- | --- | --- |
| `0x300` | `0080x2x0`, toggles within a state | the same, toggles | channel status |
| `0x304` | `00800000` (source 0 off) / `00804000` (on) | `00804000` | bit 14 = source-0 fetch active |
| `0x308` | `00800210` | `00800210` | identical |
| `0x30c` | active `…4258/c258` (console, and source 0 in capture-address mode) | idle `00800210` | channel status; idle when AFBD runs in queue mode (KMS NV12 baseline, all stock states) |
| `0x310` | `00800210` / `00a00210`, toggles | `00a00210` | status |
| `0x320/324` | ring pair | ring pair | the capture pair |
| `0x338` | **0** in the stage-1 / T3 / T4 snapshots (before and after `win rn 2`, source 0 on); **1** in Phase 1, later the same boot | 0 | a **sticky status flag**, set sometime after T4. There is no firmware (`0xba60`-relative), KMS or LogoRegData writer, and it was 0 in the T4 state, so it doesn't explain the *y/2* |
| `0x33c` | `10101010` | `10101010` | identical |

No word in this window is a 4:2:0/4:2:2 configuration bit: every
difference is status that tracks the AFBD address mode or the fetch
activity.

**The firmware path is closed as a product route.** What it's been shown
to do:
* **Works:** a live, correctly sized, sharp HDMI picture on the panel with
  zero ARM work, and luma exact.
* **Defect:** vertical chroma at half rate in capture routing. It doesn't
  respond to the AFBD format fields (Test 2), NR history (T6), or anything
  in the registers that differ from stock (§10.20, this section).
* **Decoder routing** needs AFBD fed from its queue by the ARM, which is
  the conversion route.
* **Stock never uses it** (§10.22).

**Next: the conversion route.** Capture ring (clean 4:2:2, BT.601/709
limited, 1080p already downscaled to 720p; Test 1) → a 4:2:2 → 4:2:0
conversion → the proven KMS NV12 plane. Candidate engines: GPU (Panfrost),
VE, GE2D. Open issue to carry: 1080p50 sources lose about a third of their
frames at capture (§10.24.1).

### 10.25 The conversion route: capture ring → 4:2:0 → KMS NV12 (plan, 10-24)

**What's already fixed.**
* **Input (Test 1):** a 3-slot NV16 ring at `0x4c3ef000`. It carries clean
  4:2:2, BT.601 limited (SD) or BT.709 limited (VGA/HD), with 1080p already
  downscaled to 1280×720 in hardware. SD arrives at native size. 1080p50
  loses about ⅓ of its frames at capture, for every route.
* **Output:** the KMS video plane (AFBD source 0, queue mode, decoder
  routing), proven on glass for NV12 and P010.
  * It magnifies smaller NV12 sources up to 4× per axis through proc (the
    letterbox plan, 0161–0165), which covers SD inputs.
  * It accepts only NV12/P010: chroma rows `h/2`, and the letterbox table
    is NV12-only away from native.
* **Ring to userspace:** `modules/hdmi-v4l2` (`/dev/video1`, NV16)
  **copies** each frame with `memcpy` from the no-map, uncached-by-default
  ring into vb2 MMAP/READ buffers. That's about 110 MB/s at 60 Hz, with no
  dmabuf export.

**Engines compared:**

| Option | Conversion | Copies | GPU | Latency (est.) | Unknowns / work | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **A. Direct NV16 scanout** | none: AFBD format 2 (yuv422_888, the firmware's own code) in queue mode | **0** (AFBD reads the ring slot) | idle | about 1 frame | Does AFBD plus the decoder-routed chain present 4:2:2 correctly in queue mode? Never tested; stock and KMS only ever show 4:2:0. Needs: an NV16 plane format, chroma rows = `h`, and ring slots as plane sources (following the `+0x320` pair) | **test first**: if it works, it's the best route on every axis |
| **B. Bridge emits NV12** | in `h713-hdmi-v4l2`: copy Y, average CbCr line pairs | 1 (CPU, already there) | idle | about 1–2 frames | add NV12 output and dmabuf export (vb2 dma-contig + `VIDIOC_EXPBUF`) so `v4l2src ! kmssink` imports without a second copy; use the cacheable ring mapping for speed | **fallback**: modest, all-stock GStreamer, proven plane |
| **C. GPU (Panfrost)** | GL: import NV16 (EGL dmabuf), render NV12/RGB | 1 (bridge) plus a GPU pass | busy | about 2–3 frames | GL pipeline (`glupload ! glcolorconvert` or a shader); stock GStreamer / `gstreamer1.0-gl` | **needed anyway when keystone ≠ 0** (keystone plan: no hardware warp), and for OSD over video; stock's own route |
| D. VE | — | — | — | — | no standalone converter: its scaler is a decode-output stage | out |
| E. GE2D | — | — | — | — | a display controller, not a 2D engine (README §3) | out |

**Plan (offline first, then one discriminating test):**

1. **Test 3: does AFBD present 4:2:2 in queue mode?** Done the proper
   way, through KMS rather than raw registers.
   * An EXPERIMENT kernel patch, like `0149`'s P010 one, adds
     `DRM_FORMAT_NV16` to the video plane: AFBD format 2, chroma rows `h`,
     native geometry only at first.
   * A known NV16 chart goes into a dumb buffer, on a RAM-sourced test FIT
     (the T4 method; nothing installed).
   * Show it, and compare with the same chart as NV12. It's a static still,
     with no ring, capture or firmware routing involved.
   * Pass = the chroma lines up; read from the band chart's mapping.
2. **If Test 3 passes, build route A.**
   * Expose the ring slots to KMS: either a dmabuf export of the reserved
     pool from the bridge, which KMS imports as framebuffers, or a plane
     property that follows the `+0x320` pair in-kernel.
   * Frame pacing follows the capture pair, and the 3 slots give a
     completed-frame margin.
   * Then the cross-route tests (§10.23.3: latency, cost, tearing).
3. **If Test 3 fails, build route B**: NV12 output and dmabuf export in the
   bridge.
4. **Route C is kept for keystone ≠ 0 and OSD overlay** in either case.
   The design's pipeline switch picks C only when a warp or overlay is
   active.

**Out of scope here:** the 1080p50 capture drop (a capture-side frame-lock
question), and interlaced input (untestable from this host).

#### 10.25.1 Test 3: built offline (2026-10-24); board run needs approval

**Kernel patch:** `patches/kernel/0189-EXPERIMENT-drm-h713-afbd-nv16-video-plane.patch`
(not in the series; it applies to the production tree `linux-6.18.38-edffad3c…`).
* Adds `DRM_FORMAT_NV16` to the video plane: AFBD format 2, chroma line
  budget = picture height.
* NV16 is limited to native, unmirrored and linear: the letterbox path
  already refuses non-NV12, and mirroring is refused for NV16.
* Nothing downstream of AFBD is changed.
* The patched object carries the format list NV12, P010, NV16; the
  production object doesn't.

**Test kernel:** built in a reflink copy of the production tree
(`build/test3-kernel/`); the production tree is untouched.
* The production tree's `Image.gz` is byte-identical to the installed
  FIT's kernel.
* The host's clang is now 23.1.3, against 23.1.1 for production, so this
  is a full rebuild with the newer compiler.
* That's acceptable for a RAM-only test kernel: there's no
  `CONFIG_MODVERSIONS` or module signing, so the installed out-of-tree
  modules load on vermagic (`6.18.38 SMP mod_unload aarch64`).

**Test FIT:** `build/test3-fit/h713-kernel-test3.fit`, **`273a4592…`**,
7,795,708 bytes.
* The kernel is the experiment Image; fdt-1 is the **production** DTB
  (`4c4fe0c5`, 34,666 bytes).
* No identity map: KMS dumb buffers go through the IOMMU as normal.

**Boot script:** `build/hdmi-test3-2026-10-24/t4-cold.scr` (`75844258…`),
from `build-t4-script.py --path /root/panel-source-test3/h713-kernel-test3.fit`.
* Only `hdmi_image` differs from the proven T4 cold script (`ext4load`
  from that path, size `0x76f3fc`). The production FDT size `0x876a`
  pins correctly.
* `run-t4-cold.py --prepared build/hdmi-test3-2026-10-24` drives it.

**Display tool:** `tools/display/kms-yuv-still.c`. It shows raw 1280×720
NV12/NV16 stills (format from the file extension) on the video plane, one
after another, each in its own dumb buffer.
* It prints AFBD `0x10` (format byte) and `0x4c` (chroma rows) after each
  commit.
* It disables the plane at the end and on SIGINT/SIGTERM, and requires
  `ARMED=yes`.
* It compiles cleanly on the host; the board has gcc and libdrm to build
  it there.

**Stills:** in `local/panel-source-t5/test3/`, BT.709 limited (ffmpeg):
`band.nv12` / `band.nv16` (the 16-band chart) and `chart.nv12` /
`chart.nv16` (the 10-23 test chart).

**Board procedure (needs approval):**
1. **Stage.** Copy the FIT and `t4-cold.scr` to `/root/panel-source-test3/`
   and verify the hashes. Copy `kms-yuv-still.c` and the four stills to
   `/root/panel-source-test3/` and build the tool there.
2. **Power off.** Arm the space-sender catcher before power-on (the
   method that worked for Test 2). Operator cold boot.
3. **Boot.** `run-t4-cold.py --prepared build/hdmi-test3-2026-10-24`.
   Check `uname -v`/`/proc/version` shows clang 23.1.3 and the plane
   advertises NV16.
4. **Run.** The operator films; one "ready" runs
   `ARMED=yes kms-yuv-still 15 band.nv12 band.nv16 chart.nv12 chart.nv16`
   (60 s), then the console returns.
5. **Read.**
   * NV12 is the control: it must look right, as KMS NV12 always has.
   * **NV16 right means route A works** (chroma lines up: band colours
     behind their own labels, hue squares coloured only in their own row).
   * NV16 showing *y/2*-like or other errors means route B.
6. **Return.** Cold boot back to production; nothing is installed.

#### 10.25.2 Test 3 result (2026-10-24): format 2 isn't linear NV16; NV12 shows a horizontal chroma shift

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/test3-run/`.
The video is `local/lcd-photos/test_107/`. The run was clean: every commit
went through, with the intended format bytes and chroma rows, and no
faults.

* **NV16 (AFBD format 2, chroma rows 720):** a scrambled picture,
  identical in character to Test 2's decoder-routing cells (tiles across
  the top third, then flat green). Format 2 in queue mode fetches a layout
  other than linear semi-planar 4:2:2. **Route A doesn't work as-is.**
  Finding what format 2 does expect, or whether another code is linear
  NV16, would be research, not a quick fix.
* **NV12 (format 0), the control:** chroma is vertically correct, but
  sits about 100 px to the **right** of luma, wrapping within the line.
  * Squares show their left neighbour's colour, and the first square
    shows the last one's.
  * The band labels' neutral chroma appears as smudges one square to the
    right, plus wrapped copies at the far left.
  * The still files decode correctly on the host, so this is the
    display's chroma fetch: about 100–128 bytes early.
  * **Every NV12 client of the plane is affected.** It's unknown whether
    production shows it too; earlier NV12 checks judged bar order and
    geometry, not chroma at edges.

**Consequences for the plan:**
1. **Route A is shelved.** NV16 isn't accepted as linear by AFBD format 2.
2. **Route B still stands, but its output plane has a defect to fix
   first:** the horizontal chroma offset on NV12. That's a KMS driver /
   AFBD chroma-address question, the same kind as the earlier "VE-scaled
   chroma offset" and "pitch alignment" fixes.
3. **Next check (cheap, decisive):** the same NV12 stills on the
   **production** kernel. One filmed run after the cold boot back to
   production, which is needed anyway.
   * If production shows the same shift: a long-standing plane defect,
     to fix in the driver (find the chroma-address offset; a test sweep of
     the C slot address by ±128 bytes on a still would locate it).
   * If not: something about the test kernel or the dumb-buffer path.

#### 10.25.3 Production NV12 check (2026-10-24): the plane is fine; the shift was the test kernel

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/test3-production-nv12/`.
The video is `local/lcd-photos/test_108/`.

* The same NV12 stills, the same tool, and **identical AFBD register
  values** (format 0, 360 chroma rows) on the **production** kernel:
  **correct chroma**. Each hue square carries its own colour and the bars
  are dark at the left.
* The ~100 px horizontal chroma shift of §10.25.2 is therefore specific to
  the Test 3 kernel: patch `0189`, or more likely the full rebuild with
  clang 23.1.3 (production is 23.1.1). It's unproven which; a no-patch
  control build would decide. Any future kernel experiment built with the
  new compiler should check NV12 chroma first.
* The NV16 verdict stands: format 2 isn't linear NV16 (the same scramble
  appears in Test 2, on the production kernel Image).

**Route decision:**
* **Route B: the V4L2 bridge emits NV12.** It writes NV12 (copy Y,
  average CbCr line pairs), uses the cacheable ring mapping, and adds
  dmabuf export (vb2 dma-contig and `VIDIOC_EXPBUF`), so stock
  `v4l2src ! kmssink` puts frames on the production NV12 plane, which is
  proven correct, including chroma.
* **Route C (GPU)** stays for keystone ≠ 0 and OSD overlay.
* **Route A** is shelved (§10.25.2).

#### 10.25.4 Route B: built offline (2026-10-24); board run needs approval

**Conversion** (`modules/hdmi-v4l2/h713-nv12.h`, one header shared by the
module and the host test, so the tested code is the shipped code):
* Luma is copied. NV12 chroma row r = rounded average of NV16 chroma rows
  2r and 2r+1 (interstitial siting, what the KMS NV12 plane assumes).
* Eight bytes at a time with `(a|b) - (((a^b) & 0xfe..fe) >> 1)`, exact for
  every byte pair; a scalar tail covers widths that aren't a multiple of 8.
* `h713_nv12_matches()` is the `verify_full` check for converted frames.

**Host self-test** (`tools/hdmi/test-nv12-convert.c`, against the held
ring frames `local/panel-source-t5/ring/ring3.nv16`): passed.
* All 65,536 byte pairs; tail widths 1–40 with no overrun.
* 3 real frames equal an independent plain conversion; the verifier accepts
  them and refuses a 1-bit luma and a chroma corruption.
* End to end, NV12 vs NV16 decoded the same way: 43.23 dB, with differences
  only on the 21 rows at colour edges (the expected 4:2:0 cost).

**Bridge** (`modules/hdmi-v4l2/h713-hdmi-v4l2.c`):
* Formats: index 0 NV16 (the ring, copied), index 1 NV12 (converted).
  `S_FMT` picks one; the size follows.
* `completion=auto|hook|pair`. `pair` polls AFBD `+0x320/+0x324` every
  0.5–1 ms and, when it changes, copies the slot before the one it names
  (corrected on the board, §10.25.5). It needs no firmware hook, which the
  production U-Boot doesn't install, so `auto` falls back to it there.
  A torn read counts as no change; 3 s without a frame errors the queue.
* `source_cached=1`: ring mapped write-back with explicit invalidation.
* dmabuf: `VIDIOC_EXPBUF` plus `VB2_DMABUF`, on the existing vb2
  dma-contig buffers, so `v4l2src io-mode=dmabuf` hands CMA-contiguous
  buffers to `kmssink`.
* Fixes found while building: the AFBD pair is mapped before
  `v4l2_device_register`, with an `unmap_pair` error label (it leaked on that
  failure). Both capture threads now park until `kthread_stop()` after the
  no-frame error instead of returning; returning first made the later
  `kthread_stop()` a use-after-free. The hook thread had the same bug before
  this change.
* Built against the production tree, `W=1`, clean:
  `build/route-b/module/h713-hdmi-v4l2.ko`, vermagic
  `6.18.38 SMP mod_unload aarch64`.

**Not tested offline:** the pair-polling thread, the dmabuf import by the
display, and the copy cost per frame. Those are what the board run measures.

**Bench** (`tools/hdmi/route-b-bench.sh`, on the board as root; refuses if
the bridge is already loaded; unloads on exit):
1. `route-b-bench.sh check DIR`: load `width=1280 height=720
   completion=pair source_cached=1`, list formats, set NV12, stream 300
   frames with `v4l2-ctl` (first frame kept as `DIR/frame0.nv12`), print the
   frame rate and counters. No panel change. Pass: about 60 fps at 720p60,
   `frames_rejected` near 0, and `frame0.nv12` decodes to the chart on the
   host.
2. `ARMED=yes route-b-bench.sh show SECS`: `v4l2src io-mode=dmabuf !
   NV12 1280x720 ! fpsdisplaysink(kmssink plane-id=38 skip-vsync=true)`.
   Visual, operator films. Pass: live desktop on the panel with correct
   chroma (band chart squares coloured in the top row only), smooth motion,
   and the rendered rate printed. Stop: Ctrl-C or the timeout; the plane is
   released and the console returns.

#### 10.25.5 Route B check on the board (2026-10-24): 59.7 fps, nothing rejected

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/route-b-check/`.
Production kernel, no panel change.

* **The pair names the slot being captured, not the finished one.** The
  first build copied the named slot and rejected all 4,968 frames.
  `tools/hdmi/ring-timeline.py` (read-only, rows of each Y slot sampled
  every 0.26 ms against the pair) showed:
  * the pair advances by +1 every 16.75 ms;
  * slot k is still written for up to ~14 ms after the pair reaches k, and
    slot k+1 starts filling from ~0.8 ms;
  * slot k−1 never changed (0 of 954 row changes).
  So the finished frame is `(idx + 2) % 3`, stable for the whole period.
  Test 1's "latest completed slot" reading was wrong.
* **Full verify can't run in pair mode.** It re-reads the whole destination,
  and vb2 dma-contig buffers are uncached, so verify took 19 ms per frame,
  longer than a period, and the slot had moved on. The guard is now the pair
  itself: a copy is accepted when the pair still names the same slot after
  it. That is exact by the timeline above, and the sparse hash brackets
  stay. `verify_full` is now −1 (auto), which means off in pair mode and on
  in hook mode.
* **Result:** 300/300 frames delivered, 0 rejected, 0 overwritten,
  **59.7 fps**, **3.0 ms per frame** for copy, convert and hashes (about 18%
  of one core at 60 Hz). The first NV12 frame decodes to a clean,
  correctly coloured desktop (`frame0.png`).
* An early bench run streamed 300 frames to a file and filled the root
  filesystem (deleted at once; nothing failed). The bench now keeps one
  frame and streams the rest to `/dev/null`.

#### 10.25.6 Route B on glass (2026-10-24): PASS

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/route-b-show/`
(`ring-input.png` is the band chart read from the ring just before the run).
The video is `local/lcd-photos/test_109/`.

* `ARMED=yes route-b-bench.sh show 60` on the production kernel (bridge
  module `0a63ac9e`, `completion=pair source_cached=1`):
  `v4l2src io-mode=dmabuf ! NV12 1280x720 ! kmssink
  driver-name=sun50i-h713-afbd plane-id=38 skip-vsync=true`.
* **Operator:** every stripe flat and matching its label, so chroma lands on
  the right rows with no bleed or horizontal shift. Motion was smooth.
* **Counters:** 3,567 of 3,568 frames delivered (59.5 fps), 0 rejected,
  1 overwritten, 2.9 ms per frame for copy and convert (about 17% of one
  core). The bridge unloaded and the console returned.
* **Bench fix:** `kmssink` needs `driver-name=sun50i-h713-afbd`; without it,
  it can't find the display card ("Could not open DRM module").
* **Operational note:** a cold boot with the PC's HDMI output gone (COSMIC
  dropped HDMI-A-1) leaves the ring frozen. The bridge then reports "no
  completed frame for 3000 ms" and parks cleanly. Reseating the cable at
  the PC brought the 60 Hz pair back.

**Route B is proven end to end with stock GStreamer and no GPU.** Next:
* package the bridge;
* the event-driven policy (§1–§9: lock → SOURCE_CHANGE → the video
  service);
* 1080p50 and other modes through this path;
* interlaced input.

### 10.26 Event-driven switching on route B: built offline (2026-10-24); board stages need approval

The §2–§4 design, built on the route B bridge. Changes from §2–§4, with the reason for each:

| §2–§4 said | Route B build | Why |
| --- | --- | --- |
| Frame activity from the VIncap VDE counter | The ring is "moving" when AFBD `+0x320` changed since the previous 20 ms sample | Production has no hook (§1.3); the pair advances once per frame and freezes with no source (§10.25.5–.6). At 20 ms it moves 1–2 slots between samples, never 3, so it can't alias to "no change" |
| `N_lock` in VDE events | `lock_ms` = 200 ms of live samples | Same intent, time-based |
| NV16 direct, NV12 fallback | NV12 only, `io-mode=dmabuf`, no `videoconvert` | Route B (§10.25.6) |
| `completion` unspecified | `completion=pair` forced in the unit | The hook thread has no HOLD handling; a diagnostic U-Boot that installs the hook must not change product behaviour |
| `SYSTEMD_READY=0` only when not ready | `SYSTEMD_READY` set to 1 or 0 on every event | udev can carry properties over from the previous event |
| `ExecStartPre` `fuser` Cedrus refusal | Not included | Q7 (who wins) is still your decision; easy to add |
| "the next lock event clears the start limit" | Not true of systemd | After 3 failures in 60 s, starts are refused until the interval has passed; a later ready event starts the unit again |

**State machine** (`modules/hdmi-v4l2/h713-signal.h`, shared by the module and the host test):
* **Live** means all of: the port-object guards pass, port 1 state 5, a non-zero size, and the ring moving.
* **States:** NONE → ACQUIRING (first live sample) → LOCKED (same size for `lock_ms`, supported) or UNSUPPORTED.
* **LOCKED → HOLD** after `hold_ms` (100) without the locked signal.
* **Leaving HOLD:**
  * the same mode back → LOCKED, no event;
  * a new supported mode → LOCKED with `SOURCE_CHANGE`;
  * a new unsupported mode → UNSUPPORTED;
  * `grace_ms` (1500) elapses → NONE.
* **Supported sizes:** 1280×720 only. 640×480 is supported only with `allow_480p=1` (Q9 default: the console stays).
* **Events:** every transition sets `H713_SIG_EV_STATE`; a new locked size also sets `H713_SIG_EV_SOURCE`.

**Bridge** (`modules/hdmi-v4l2/h713-hdmi-v4l2.c`):
* **Sampling:** a delayed work runs every 20 ms.
  * It reads port 1 through the guarded chain of `read-mips-port-cache.py`: the manager and receiver vptrs, port id 1, link base `0x06840000`, and every pointer inside a separate WC mapping of `0x4B100000–0x4BF41000`, the MIPS DRAM below the carve-out, which never aliases the cacheable ring.
  * It then reads the AFBD pair and steps the machine.
* **Coldplug:** the bridge samples synchronously (up to 300 ms) before it registers the video node, so the node's `add` event carries a settled state.
* **Published state:**
  * a `signal` attribute on the parent platform device (`none`, `acquiring`, `locked 1280x720`, `holding 1280x720`, `unsupported 640x480`), present before the `add` event;
  * a `KOBJ_CHANGE` on the video node with `H713_HDMI_SIGNAL=` and `H713_HDMI_MODE=`;
  * `V4L2_EVENT_SOURCE_CHANGE` (resolution) when a new size locks;
  * a `pr_info` per transition.
* **V4L2 HDMI-RX interface:**
  * `ENUMINPUT` sets `V4L2_IN_CAP_DV_TIMINGS` and reports `NO_SIGNAL` or `NO_SYNC`.
  * `QUERY_DV_TIMINGS` returns `-ENOLINK` (none), `-ENOLCK` (acquiring), `-ERANGE` (unsupported), or the CEA 720p60 / DMT 640×480 timings.
  * `G/S/ENUM_DV_TIMINGS` and `DV_TIMINGS_CAP` are implemented.
  * The frame interval comes from the timings (60/1 for 720p).
  * `G_FMT` follows a new lock while the queue is idle.
  * `STREAMON` returns `-ENOLINK` unless LOCKED at the configured size.
* **Stream thread:**
  * LOCKED at the stream's size: copies finished slots, as in §10.25.5.
  * HOLD, or LOCKED at another size: black frames at about 60 Hz, so the panel shows black, not a frozen frame, during a host mode-set.
  * NONE, ACQUIRING or UNSUPPORTED for 1 s, or another size for 2 s: `vb2_queue_error()` (EIO backstop).
* **Defaults:** `source_cached=1`, geometry 1280×720 until the first lock. The node is named `h713-hdmi-in`.
* **Counters:** `sig_transitions`, `sig_bad_guard`.
* **Build:** clean with `W=1` against the production tree.

**System pieces** (`tools/hdmi/`):
* `71-h713-hdmi-in.rules`: the `/dev/h713-hdmi-in` symlink, the systemd tag, `SYSTEMD_WANTS=h713-hdmi-video.service`, and `SYSTEMD_READY` set from `ATTRS{signal}` (`locked*|holding*` → 1).
* `h713-hdmi-ring.service`: a oneshot that runs `insmod … completion=pair` and `rmmod` on stop. It is bound to the signal and capture units, under the same `hdmi-boot-v1` condition as the speaker.
* `h713-hdmi-video.service`: `BindsTo=` the device and ring units. It runs `gst-launch-1.0 -e -q v4l2src device=/dev/h713-hdmi-in io-mode=dmabuf ! video/x-raw,format=NV12 ! kmssink driver-name=sun50i-h713-afbd sync=false skip-vsync=true`, stopped with `KillSignal=SIGINT`, with `Restart=on-failure`, `RestartSec=1` and 3 starts per 60 s.
* `stage-hdmi-video.sh`: `observe`, `stage` (`ARMED=yes`), `status` and `unstage`, with everything under `/run`.
* `build-hdmi-video.py`: the bundle plus `SHA256SUMS`, written to `build/route-b/bundle/`.

**Offline results:**
* **`tools/hdmi/test-signal-state.c`:** 18 scenarios pass:
  * no cable; lock; login gap; unplug; a gap at exactly grace;
  * 720p → 480p, with and without `allow_480p`; a 1080p source; a mode switch with no gap;
  * flapping; ring stall at port state 5; guard failure; a stale size at port state 3;
  * a dropout during a HOLD relock; unsupported straight to 720p; single missed samples; sampler jitter; an unstable HOLD candidate.
* **Mutations:** 18 one-line changes to the header (thresholds, each event bit, each condition of "live", each candidate reset, HOLD timeout) are all caught. Three survived the first version of the suite, and the three scenarios added for them now catch them.
* **`tools/hdmi/test-signal-traces.py`:** replays the 5 recorded port-cache captures (09-24 corrected, 09-25 ×2, 10-08 ×2). Each gives the expected sequence at the exact sample: 640×480 → UNSUPPORTED → none; 1280×720 → LOCKED with `SOURCE_CHANGE` → holding → none. A grace mutation fails it.
* **Other checks:**
  * `udevadm verify` passes on the rule; `systemd-analyze verify` passes on both units.
  * The board has `/sbin/insmod`, `gst-launch-1.0` 1.26.2, systemd 257, `v4l2-ctl` and `v4l2-compliance`.
  * The NV12 self-test still passes.

**Not tested offline:**
* The port-object read on the live firmware; this production boot hasn't been read with the new reader.
* udev and systemd acting on the real device.
* `v4l2src` against this driver's DV timings and `SOURCE_CHANGE`.
* Black frames on glass.

The stock `vivid` host test (§2.3) needs root on the host, so it hasn't been run: `sudo modprobe vivid`, then the same `gst-launch` line against the vivid HDMI input.

**Board stages** (each announced; operator says "ready"; stop rules as §10):

| Stage | What | Panel | Pass |
| --- | --- | --- | --- |
| **1. Observe** | `COMPLIANCE=1 stage-hdmi-video.sh observe 300`: the bridge alone, `v4l2-ctl` DV timings, input and format, `v4l2-compliance` (no streaming), then the transition log. Host actions: output off/on ×3, login, 720p → 640×480 → 720p, DPMS sleep/wake, lock screen, unplug/replug | Unchanged (console) | `initial signal locked 1280x720` with the cable in; one sensible transition sequence per host action; `sig_bad_guard` 0; gap lengths recorded (sets `hold_ms`/`grace_ms`, Q2); no `v4l2-compliance` failures on the implemented ioctls |
| **3. Event-driven** | `ARMED=yes stage-hdmi-video.sh stage`, then the same host actions; `status` after each | Camera | Lock → HDMI on the panel without a command; a mode-set shows black, then the picture with no console flash; unplug or sleep → console after about 1.6 s; `NRestarts` 0 |
| **4. Coldplug** | With the cable in and locked: `unstage`, then `stage` again (the bridge loads while locked) | Camera | HDMI appears with no change event (the `add` event carried `locked`) |

Stage 2 (one switch by hand) is §10.25.6. A boot with the cable in, cold and warm-shared, needs the units installed (stage 5) and stays behind your approval.

#### 10.26.1 Stage 1 result (2026-10-24): every host action gives the right transitions

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/stage1-observe/`.
The bridge ran alone (no rule, no units); the panel stayed on the console.

* **Load:** `initial signal locked 1280x720 after 11 samples`. `QUERY_DV_TIMINGS` returns CEA VIC 4 at 60.00 fps, and the input reads "HDMI1: ok".
* **`v4l2-compliance`:** 48 tests, 48 passed, 0 failed. Two warnings: no `V4L2_CID_DV_RX_POWER_PRESENT` control (+5 V is invisible from ARM, Q4) and no `CREATE_BUFS`.
* **Guards:** 31 transitions, `sig_bad_guard` 0, so every port-object read passed. No IOMMU fault; the bridge unloaded clean.
* **Host actions**, matched in the operator's order:
  * **Output off, three times:** HOLD at 100 ms, then none 1.54 s later.
  * **Output on:** acquiring, then locked 0.22 s later with `SOURCE_CHANGE`. One turn-on had a single 28 ms acquiring/none flicker, which the lock timer absorbed.
  * **Log out and in:** holding → locked after 0.56 s, with no event. HOLD absorbed it, so the panel would show black and come back, never the console.
  * **720p → 640×480:** UNSUPPORTED 640×480 (console under Q9's default). **Back to 720p:** none → acquiring → locked with `SOURCE_CHANGE`.
  * **DPMS sleep:** none after grace. **Wake:** locked, then a 0.46 s re-modeset that HOLD absorbed.
  * **Lock screen:** no transition; the mode was kept, as §3 expected.
  * **Unplug and replug:** none; then locked with `SOURCE_CHANGE`.
* **Q2 answered:** the longest same-mode gap was 0.56 s, plus `hold_ms`. That is well inside `grace_ms` = 1.5 s, so the defaults stand. Turning the output off reaches the console about 1.6 s after the source stops.
* **Tool fix:** the run's SSH session ended when the Claude session restarted. The remote script died on SIGHUP, which neither bench script trapped, so the bridge stayed loaded until it was removed by hand. Both scripts now trap HUP. Longer board runs should be started detached (`setsid`, logging to a board file). The source PC is the host that runs Claude, so logging out ends Claude's session. Stage 3 runs the board side detached and leaves logout out, or does it last, with the results collected afterwards.

Stage 3 (rule and units staged, camera) is next and needs approval.

#### 10.26.2 Stage 3 result (2026-10-24): FAILED on a udev rule bug, now fixed (rerun needed)

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/stage3-events/`; video `local/lcd-photos/test_110`.

* **What worked:** staging. The bridge loaded locked, its `add` event made the device ready, and systemd started the video unit 64 ms later. The desktop showed on the panel at 60 fps. This is also the coldplug case (stage 4).
* **What failed:** at the first "output off" the signal went to none, but systemd didn't stop the unit. The bridge's 1 s EIO backstop ended the stream instead. `Restart=on-failure` then restarted `gst-launch` three times during no-signal. Each attempt got `STREAMON -ENOLINK` ("Buffer pool activation failed"), so `StartLimitBurst=3` was used up and every later lock was refused. The panel stayed on the console for the rest of the run.
* **Root cause:** the rule matched `ATTRS{name}` (the video node) and `ATTRS{signal}` (its parent) together. udev requires every `ATTRS{}` key in a rule to match on **one** device, so neither READY line could ever match, and the device stayed ready whatever the signal did. `udevadm info` showed no `SYSTEMD_READY` at all.
* **Fix** (`tools/hdmi/71-h713-hdmi-in.rules`): `ATTR{name}` for the node's own attribute. READY is set to 0 unconditionally, then to 1 when `ATTRS{signal}` is `locked*|holding*`, so no negative `ATTRS{}` match is needed.
* **Verified on the board** with the rule only (no units, no panel change): `SYSTEMD_READY=1`, and the device unit is active/plugged. Losing the signal (READY=0) needs the rerun.
* The bridge's transitions were correct throughout, matching stage 1.
* **Open:** a failure loop can still exhaust the start limit, after which locks are refused for 60 s. With the rule fixed, systemd stops the unit cleanly on signal loss, so the loop shouldn't arise. If it does, `RestartPreventExitStatus=` or a longer `RestartSec` would stop it.

**Next:** rerun stage 3 with the fixed bundle (already built; copied to `/root/hdmi-video/` on the board), using the same host actions and no logout.

#### 10.26.3 Stage 3 rerun (2026-10-24): PASS

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/stage3-rerun/`. There is no video; the operator reports the panel did the right thing at every step.

* **Fixed rule, same host actions** (no logout): output off/on ×3, 720p → 640×480 → 720p, DPMS sleep/wake, lock screen, unplug/replug.
* **Board record:** 28 signal transitions. The video unit started 7 times, once per lock, and stopped cleanly on every loss. `NRestarts` 0, no unit failures, no GStreamer errors. The bridge's EIO backstop never fired, so systemd always stopped the unit first.
* **Coldplug** (stage 4) was shown at staging: the bridge loaded already locked and the unit started from the `add` event. A real boot with the cable in needs the install.
* **Unstaged afterwards:** the bridge is unloaded and nothing is left in `/run`.

**Event-driven switching works on the board.** Next: install (stage 5), which needs explicit approval, then cold and warm boots with and without the cable. Q7 and Q9 are still open.

#### 10.26.4 Stage 5 installer: built and tested offline (2026-10-24); install needs approval

`tools/hdmi/install-hdmi-video.sh` follows the speaker installer's pattern and is part of the bundle (`python3 tools/hdmi/build-hdmi-video.py build/route-b/bundle`).

* **Modes:** plain install (or an identical reinstall), `--update` (backs up the installed generation under `/var/lib/h713-hdmi-video/backup.*`), `--dry-run [--update]` (every check of that mode, no writes), and `--remove` (disables, stops and removes everything; backups are kept).
* **Checks, all before any write:**
  * the HY200 board;
  * the bundle's checksums;
  * module vermagic against `uname -r`;
  * `gst-launch-1.0`, `v4l2src` and `kmssink` present;
  * the signal and capture owners installed;
  * no runtime staging in `/run`;
  * no bench bridge loaded;
  * an installed generation must pass its own checksums and match its recorded unit and rule copies;
  * a different generation needs `--update`.
* **Installs:**
  * the module and copies into `/usr/lib/h713-hdmi-video/`;
  * both units into `/etc/systemd/system/`;
  * the rule into `/etc/udev/rules.d/`.

  Then it reloads systemd and udev, runs `systemd-analyze verify`, and runs `enable --now h713-hdmi-ring.service`. The video unit is not enabled; udev pulls it in. With a locked source, the panel switches to HDMI as soon as the ring unit starts.
* **Offline test** (`tools/hdmi/test-install-hdmi-video.sh BUNDLE`, a fake root with stubbed system commands): 16 cases pass. Every refusal also proves the fake root's files didn't change. Four guard mutations (the vermagic check, the `--update` guard, the backup, `enable --now`) are all caught. The first version of the test's file fingerprint was itself unstable; it was fixed before the results above.
* **Board dry run** (bundle in `/root/hdmi-video/`): `dry run OK`. Nothing was installed.

**Proposed stage 5 run** (needs approval):
1. `cd /root/hdmi-video && sh install-hdmi-video.sh`, with a locked source, so the panel switches at once.
2. A cold boot with the cable in: logo → console (~20 s) → HDMI with no command.
3. A warm reboot from HDMI: the console comes back before shutdown; after boot, HDMI again. Watch for panel-black (Q6).
4. A cold boot with the PC output off: console. Then output on: HDMI.
5. A 10-minute desktop soak: `NRestarts` 0, speaker unaffected.

Revert at any point: `sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --remove`.

#### 10.26.5 Stage 5 result (2026-10-24): installed; cold boots PASS; warm reboots stay on the console

Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/stage5-install/`.

* **Installed** (approved) with a locked source: the panel switched at once, at 61 fps.
* **Cold boot with the cable in:** logo → console → HDMI with no command. Video started at 20.85 s, 0.5 s after the signal lock.
* **A second cold boot** (meant to start with the PC output off): the PC re-enabled its output on the board's hotplug, so HDMI came up at 21.25 s, the same path again. The console-until-output-on case was already shown at runtime in stage 3.
* **Soak:** 13 minutes at 59.7 fps, 0 rejected, `NRestarts` 0, and the speaker kept running.
* **Warm reboot from HDMI:** the video stopped first and the console showed during shutdown, as designed. After boot the panel stayed on the console. The production U-Boot warm path doesn't set `/chosen/h713,hdmi-boot-v1`, so the capture owner, signal owner, speaker and bridge all skip. That is the §6 warm fallback, not a fault in this stack. No panel-black (Q6). HDMI after a warm reboot needs the shared warm-startup work in U-Boot.
* **Revert:** `sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --remove`.

#### 10.26.6 Warm recovery repeat preparation (2026-10-24): offline only

The two RAM-only repeats are prepared, **not run**. See the
[exact runbook, validation and pinned artifacts](hdmi-evidence/2026-10-24-warm-shared-repeat-preparation/README.md).
The runner supports orderly reboot and a boot-ID/health-guarded, synced
SysRq-b reset without driver teardown. `--require-video` checks both boots
for locked 720p, active ring/video units and advancing bridge counters with
no added rejects. Health evidence includes unit status/start timestamps,
monotonic journals and bridge dmesg. Existing DSP/audio flow checks remain;
audible tone and a moving picture require operator confirmation.

32 offline tests pass; eight deliberate code mutations were caught, covering
all six new tests. The RAM image matches the October 23 image byte for byte.
No board access, installation, production GP6 policy change, commit or push.
Panel-black remains a separate release blocker. Next: approved operator-timed
orderly trial, then a separately approved SysRq-b trial.

#### 10.26.7 Orderly warm trial (2026-10-24): inconclusive, host runner stopped

[Evidence](hdmi-evidence/2026-10-24-warm-shared-repeat-orderly/README.md).
Cold picture/tone were confirmed by the operator and digital health passed.
One orderly reboot reached warm SPL, then host os.read raised transient
EAGAIN despite select readiness. Runner stopped before census/transfer/source;
no warm startup acceptance result. Operator reported catching U-Boot; no
recovery command or further board action was sent.

Offline reader fix continues on BlockingIOError, preserving fatal I/O errors.
33 tests pass; reverting the fix fails the added regression test. The host
player was stopped after HDMI disappeared and PipeWire moved its audio to
host speakers. Retry needs fresh approval, new evidence/tool pins and source
routing verification after reconnect. Production startup remains unchanged.

#### 10.26.8 Orderly retry 1 (2026-10-24): inconclusive, missing UART bytes

[Evidence](hdmi-evidence/2026-10-24-warm-shared-repeat-orderly-retry1/README.md).
Cold moving picture/colour/tone confirmed; cold digital checks pass (~59.5
delivered fps, zero rejected, zero new audio xruns, video start 20.908 s).
One orderly reboot issued. Warm raw capture lacks SPL/preboot markers and
contains visibly truncated lines, though five autoboot countdown strings
are present. No interrupt, census, transfer or RAM source was sent. Installed
warm fallback booted Linux; read-only SSH confirms absent handoff and inactive
HDMI units. No operator manual interruption was expected.

Host runner and source player stopped; board left running without further
board writes. This does not test shared warm startup. Cause of capture loss
remains unresolved; a snapshot found only the runner owning the tty and a
host kernel USB/serial journal filter found no matching errors. Investigate
capture reliability before asking for another cold-cycle trial.

#### 10.26.9 GP7 boot-stop orderly runner (2026-10-24): prepared offline

User clarified that GP7's established one-shot bootloader-stop use is allowed;
it remains reserved for reboot-mode handoff. `--boot-stop gp7 --reset orderly`
uses the installed kernel nvmem reboot-mode driver through the bootloader reboot
argument. No raw GP7 writes, GP6 change, saved environment change or timed key.
U-Boot consumes GP7 and waits at the prompt. Runner requires full reset evidence,
checks early GP7 magic, then consumed GP7=0, unchanged preboot/bootcmd and
volatile bootdelay=-1 before existing census/FIT/one-launch gates.

39 offline tests pass; 11 GP7 mutations and 8 earlier mutations caught.
RAM startup image is unchanged. [Artifacts and revised live sequence](hdmi-evidence/2026-10-24-warm-shared-gp7-preparation/README.md).
No board access during preparation. UART byte-loss cause remains unresolved;
incomplete evidence stops rather than bypassing guards. SysRq-b+GP7 is refused
because the abrupt reset skips reboot notifiers; its arming needs separate work.

#### 10.26.10 GP7 orderly warm trial (2026-10-24): PASS on glass and digitally

[Complete evidence](hdmi-evidence/2026-10-24-warm-shared-gp7-orderly/README.md).
One orderly reboot with kernel bootloader argument stopped automatically at
U-Boot; early GP7=b007c0de was consumed to zero, GP6 retained, MIPS parked,
bootcmd/preboot unchanged and volatile bootdelay=-1. All census/FIT/CRC checks
passed; exactly one RAM shared-startup source, re-latch and handoff succeeded.

Both boots passed DSP 0000/0000 -> verified 1/1, active audio/video and flow
checks. Warm video delivered ~59.8 fps, zero new rejected frames, NRestarts=0,
service start 21.255 s after kernel; audio capture/playback ~48 kHz, zero new
xruns. Operator confirmed Linux console -> host desktop -> video and audible
tone after warm boot; no black reported. Colour was not separately reported.
Host player was stopped across reset and restarted explicitly after hotplug,
so continuous-source recovery timing was not measured. This is one orderly
RAM-only repetition, not the complete release criterion.

Checked final poweroff confirmed on UART; host player stopped and board left
powered down. No install, saved environment change, commit or push. Next:
separately reviewed GP7 arming for SysRq-b and its operator-approved trial;
production GP6 guard/health-ack, installation approval and soak remain.

#### 10.26.11 SysRq-b with GP7 stop (2026-10-27): prepared offline, not run

[Runbook, trigger example, tests and artifact pins](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq-preparation/README.md).
User authorized offline preparation using GP7 for its existing boot-stop
purpose; board reported off. No board access or actions during preparation.
`--reset sysrq-b --boot-stop gp7` now syncs storage, pins the RTC nvmem
provider/cell and boot ID/HDMI health, requires expected GP6 and zero GP7,
then writes exactly four bytes at nvmem offset 0x1c. Readback must prove GP7
magic and unchanged GP6; health is checked again before UART acknowledgement
and SysRq-b. No service stop, driver teardown, ordinary reboot or raw MMIO.

Any failure after the write leaves GP7 potentially armed; stop/report with
no automatic retry, clear or recovery. U-Boot stream still requires full
census and consumes GP7 before prompt checks, FIT/CRC and one RAM launch.
45 offline tests pass; all 12 new mutations caught, covering six new tests
using fake sysfs/proc and local fixture nvmem only. RAM image unchanged.
Await operator cold-cycle ready and OPEN before serial/mains. Live abrupt
acceptance, production GP6/health-ack, installation and soak remain pending.

#### 10.26.12 SysRq-b trial cold baseline (2026-10-27): paused for inaudible audio

[Evidence and captured samples](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq/README.md).
Complete cold UART, live video and correct colour confirmed. No audible tone,
including after host projector sink changed from 35% to 100%. Mixer read-only
values are DAC 43, Line Out 15, switches enabled; both PCM pointers advance.
Host software monitor has tone-level content. Operator-approved diagnostic
briefly stopped speaker, captured incoming ALSA samples and restored speaker
in finally. Captured stereo 440 Hz, RMS 0.204677 / peak 0.289490, matching
prior successful content. Source/receiver/capture provide nonzero tone; the
downstream audibility cause remains open. Speaker restored active with both
PCMs RUNNING. No module/mixer change, GP7 arm or reset; cold gate stays closed.
Await operator report, and do not equate digital samples with audible output.
Operator then confirmed audible tone after service restoration. Current audio
baseline is restored; initial cold-boot silence remains unexplained. SysRq-b
stays paused under the latest user instruction, with no gate release or reset.

#### 10.26.13 SysRq-b attempt (2026-10-27): held at U-Boot, acknowledgement truncated

[Live evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq/README.md).
User resumed after audible audio returned. Fresh cold health passed; one
GP7-armed SysRq-b reached prompt with GP6 preserved, GP7 magic and parked MIPS
in the early census. UART acknowledgement ended at `gp7=b` immediately before
sysrq: Resetting. The complete-marker guard stopped census/transfer/source;
no warm shared launch or recovery PASS. Host reader/player stopped, board
left held at U-Boot with no further action. Earlier speaker restart is retained
as a diagnostic intervention, not hidden as an untouched cold-start success.

Likely reset overtook queued UART output; added explicit tty drain after
stream flush and before SysRq-b offline. [Fix evidence](hdmi-evidence/2026-10-27-warm-shared-sysrq-uart-drain/README.md):
46 tests pass and omitting drain fails its new regression. No hardware run of
the fix; no general claim that serial capture loss is resolved. Further board
continuation/retry requires approval. Initial cold audio silence remains open.

#### 10.26.14 Approved held-prompt continuation (2026-10-27): warm digital PASS

User approved fresh live prompt/census verification followed by the first
RAM-only startup, with no further reset. All GP6/consumed-GP7/MIPS/PPU,
preboot/bootcmd/volatile-delay and FIT/CRC checks passed; one RAM source
produced re-latch, handoff and new Linux boot. Warm health/comparison PASS:
DSP 0/0 -> 1/1, ~48 kHz capture/playback, zero new xruns, video ~59.76 fps,
zero rejects, NRestarts=0, video service start 22.000 s. Await operator warm
picture/colour/tone report. [Evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq/README.md).

One SysRq-b total, not repeated. Original reset ACK still truncated; the
offline drain fix was not exercised in another reset. Approximately six
minutes held at U-Boot may affect panel-black settling; earlier cold speaker
restart and explicit host-source restart remain documented. This does not
establish unattended or uninterrupted-source recovery behavior.

#### 10.26.15 Abrupt warm continuation: on-glass acceptance and checked poweroff

October 27 operator confirmed moving warm picture, correct colour and audible
tone. Functional recovery after the single SysRq-b and single RAM startup is
proven with §10.26.14 limitations. No warm speaker restart or mixer change was
needed. Initial cold silence remains unresolved; this is not a clean cold-audio
or unattended-runner PASS. Need fresh live UART-drain validation without the
six-minute prompt hold before extrapolating prompt recovery/panel-black behavior.

Host projector volume restored to prior 35%, test player stopped, checked final
poweroff confirmed on UART at 09:24:09 UTC. Board powered down. [Final evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq/README.md).
No production install, GP6 policy change, commit or push. Remaining work:
UART-drain abrupt repeat, cold audio diagnosis, production shared branch and
health acknowledgement, install approval and soak.

#### 10.26.16 Clean GP7/SysRq-b repeat with UART drain (2026-10-27): PASS

[Complete evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq-clean/README.md).
Fresh cold cycle, full cold census/handoff; operator confirmed picture,
colour and tone without diagnostic restart. Fresh cold health passed.
One synced GP7-armed SysRq-b produced the complete drained acknowledgement
including expected boot ID before reset, one SPL/early census and automatic
prompt/census/FIT/CRC/one-RAM-source sequence. No manual continuation or long
diagnostic hold (normal census/transfer 31.52 s). GP7 consumed, GP6 preserved.

Warm DSP 0/0 -> 1/1, audio ~48 kHz with zero new xruns, video ~59.8 fps with
zero rejected frames, NRestarts=0 and service start 21.279 s. Operator confirmed
warm moving video, correct colour and audible tone. No board speaker restart
or mixer writes on either boot. UART-drain fix validated on this clean run;
earlier unrelated serial loss and isolated cold silence are not erased.

Host source was explicitly restarted after HDMI hotplug, so uninterrupted
source timing is not claimed. Host volume restored to 35%, player stopped;
checked poweroff confirmed 10:04:05 UTC, board powered down. No production
install, saved environment/GP6 policy change, commit or push. Required orderly
and abrupt RAM repeats pass. Next: offline production shared branch/four-state
GP6 guard and health ack, explicit policy/install approval, repeated warm soak.

#### 10.26.17 Production shared branch/GP6 guard/health ack: offline (2026-10-27)

**Final checked poweroff completed:** user explicitly requested poweroff.
Expected boot ID verified at uptime 28794.51 s; capture/signal/speaker/video/
health units all active/success/NRestarts=0. One sync and detached systemctl
poweroff, no retry/reset/GP7/GP6 write. Passive UART confirms
`[28803.057353] reboot: Power down` (~8 h 0 min uptime). Host test player
stopped; passive UART recorder closed. Board now powered down. Saved host
projector volume is 35% (raw 22937), but restoration failed because HDMI sink
vanished at shutdown; restore that exact endpoint on its next connection,
without changing other audio devices. No periodic automation was created.
[Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Quiet runtime interval ended, ~11:27 PDT October 27:** same warm boot now
~7 h 46 min uptime, ~7 h 37 min after silent baseline. Final read-only checks:
~59.6 fps, zero cumulative rejected frames/capture xruns, five units healthy
with NRestarts=0; host still playing on projector at software volume zero.
15-minute scheduled checks were not established, so this is baseline/final
long-run evidence, not fully monitored soak or repeated-reset acceptance.
No further waiting. Board left on and silent; no new reset/service mutation.
[Result and limitations](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Operator warm confirmation received:** moving video, correct colour and audible tone. First installed orderly warm boot is a functional digital/on-glass PASS after host-only player restart. Soak remains paused for host hotplug investigation; board stays on, no further board commands/reset. [Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**First installed orderly warm boot: digital PASS, soak paused for host source:**
one ordinary reboot from HDOK completed unattended through installed startup,
with no GP7 stop/RAM source. New boot `23410156-c962-4d95-99b5-ac5e2dd6e562`;
early GP6 HDOK/GP7 zero, HDMI latched before firmware, shared source/re-latch/
handoff complete. Automatic ack wrote HDOK at 21.011 s; no board service
restart/manual ack. DSP 0/0→1/1, audio ~48 kHz/zero xruns, video ~59.84 fps/
zero rejects; cold/warm comparison PASS. Host mpv lost its HDMI window report
and PipeWire moved its stream to SoundSticks while HDMI disappeared. Endpoint
returned but routing/window did not self-recover. Further reboots stopped;
host-only restoration attempts exited mpv, then a fresh host player restored
verified HDMI video/audio routing. Await operator warm picture/colour/tone.
This is functional digital recovery, **not** uninterrupted-source acceptance.
Board remains on; UART/new host player running. Four remaining ordinary runs,
SysRq-b and no-source trial not executed; fix host harness before clean soak.
[Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**First installed cold boot now digitally PASS (operator confirmation pending):**
boot `a0cdeb59-4933-41e6-bafd-b31dad5a96ca`, shared handoff/re-latch verified and automatic
GP6 HDMI→HDOK at 20.877 s, GP7 zero. Health unit active/exited/status 0/no
restarts; dry-run observes HDOK without writing. DSP 0/0→1/1, audio ~48 kHz
zero xruns, video ~59.44 fps/zero rejects. No manual ack or board service
restart. Host player was relaunched after this physical cold cycle; no
uninterrupted-source timing claim. UART/player running; await operator cold
picture/colour/tone before any installed warm reboot. [Live evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Installation now complete, first new cold boot pending:** approved delta
installed once and verified; health unit enabled but inactive, GP6 HDMI/GP7
zero. Exact backup `/var/lib/h713-hdmi-startup/shared-20260413T194157-c5fec89a`
is copied/checksummed on host; rollback dry-run passed. FIT and saved environment
unchanged (active CRC-valid environment is documented LBA 0x32ec00, not configured
0x49ec00). Final current-boot health passed and checked poweroff confirmed on
UART at 2026-10-27 10:34:27 UTC. Reader closed. Await disconnected >=1 minute
cold cycle/ready, then fresh OPEN before power. New startup/automatic HDOK and
warm soak remain untested. [Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Installation trial now authorized/in progress:** user approved production
install and GP6 policy and completed the ≥1 minute disconnected cold cycle.
UART OPEN preceded power; old cold digital baseline passes, GP6 HDMI/GP7 zero,
18 backend checksums match. Host video/tone routed to projector; awaiting
operator cold picture/colour/tone before installation. No install/reset/latch
write yet. [Live evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

[Evidence, artifact pins and proposed install/test sequence](hdmi-evidence/2026-10-27-shared-startup-production-preparation/README.md).
Offline production changes authorized; no board access or installation.
`build-startup.py` accepts GP6 0/HDOK and writes HDMI before firmware only
after MIPS status/clock/reset, GP7 and PPU census pass. HDMI/unknown retain
existing logo-only fallback. Image/record stages and source-3/TCON/handoff
operations retain installed behavior (source diagnostic message updated).
The acknowledgement unit follows/requires capture and signal, verifies this
boot's handoff/session and existing startup checker, validates RTC identity,
then writes exactly GP6 HDOK through nvmem and verifies unchanged GP7.
Signal lock and video/speaker consumers are not health prerequisites; no
retries, resets, GP7 writes or new shutdown actions. This guard acknowledges
startup health; a crash after HDOK permits a new launch on the next boot.

Dedicated delta builder/updater pins the installed predecessor and FIT,
verifies backend checksums, backs up the old transaction, fsyncs/stages health
files, enables its unit without starting it, and activates FAT last. Only
script/cmd entries in the old manifest change; existing modules/firmware/units
stay installed. Both builder entry points now emit the same delta to avoid
pairing the shared script with a legacy installer lacking acknowledgement.
Failures leave an INCOMPLETE marker; tested rollback validates known hashes
and restores old files without RTC writes. Cold cycle required after install
and rollback. Arbitrary power-loss boundaries have not been exhaustively tested.

70 tests PASS (11 + 46 + 13), 17 implementation mutations caught covering
every new test, combined systemd unit verification exit 0 and bundle hashes
PASS. No real guard-state injections: all negative tests use fake roots or
dry-run. Bundle `build/hdmi-shared-startup-production-2026-10-27`, script hash
`fcea3a9589432f9b44781178d70433486aac5872a618970039b3326744e7fe7b`.
No production acceptance claimed: explicit GP6-policy/install approval and
operator-ready gate remain. Proposed soak is five orderly and one synced
SysRq-b reboot through installed startup (no GP7 stop/RAM source), plus a
no-source cold boot and runtime reconnect. Track prior panel-black/cold-audio
observations; no service restarts may mask an acceptance failure. No commit/push.

## 11. Deleted relative to revision 1

* The custom `hdmi-video.c` policy daemon and its event loop
  (subscribe-then-query, DQEVENT handling). Replaced by udev
  `SYSTEMD_READY` + `BindsTo=` and stock `v4l2src` event handling.
* The daemon's pipeline state machine (IDLE/STARTING/PRESENTING/STOPPING/
  BACKOFF) and "3 starts per lock episode". Replaced by systemd `Restart=`,
  `RestartSec=` and `StartLimitBurst=`.
* `ExecStartPre` insmod and `ExecStopPost` rmmod in the video unit. Moved to
  `h713-hdmi-ring.service`, because the device must exist while unlocked.
* `framerate=60/1` and fixed `width/height` in caps. These now come from the
  DV timings.
* `T_loss` = 100 ms straight to the console. Replaced by HOLD with
  `T_grace` ≈ 1.5 s.
* The policy simulation against a fake V4L2 event source. Replaced by udev
  and unit verification plus the `vivid` test.
* `videoconvert` as the default path. It is now the fallback; direct NV16 is
  the v1 goal.

## October 27 reboot acceptance continuation: cold audio failure

New evidence: [reboot acceptance](hdmi-evidence/2026-10-27-reboot-acceptance/README.md).
Fresh physical cold boot e8ebd15e-a1c5-4c95-afb5-e814c8fb1b0a passed digital
startup/video/audio-flow gates and automatic HDOK (~21.15 s), but operator
reported moving video with no tone. Host/stream/board were unmuted; raising
only host projector endpoint 35% to 100% did not restore audibility. Board
mixer 43/15, line/speaker switches on, PA GPIO high, PCMs RUNNING.
Bounded consumer-only stop/capture/restore produced nonzero stereo tone
(RMS 0.20468, peak 0.28949). Operator confirmed tone after restoration.
No firmware restart, mixer change or reset in this diagnosis. Cold audibility
FAIL remains open; do not call this an intervention-free cold acceptance.
Proceeding with requested warm acceptance from recovered audible baseline,
with this deviation explicit. Root cause remains unresolved.

## October 27 installed orderly acceptance progress

Four remaining installed orderly reboots now digitally pass (warm-02..05):
59.36–59.80 fps, zero cumulative rejected frames/capture xruns; automatic
HDOK and GP7 zero each boot, DSP/startup/audio/video checks pass, no board
service recovery, prompt holds, RAM launches or GP7 writes. Operator has
confirmed picture/colour/tone for warm-02..04; warm-05 confirmation pending.
The prior installed warm-01 passed in the production-install record. Host
fixture now explicitly recreates only the player's outputs after hotplug
(ao-reload, vo=null→gpu, loadfile), with actual HDMI routing/window verified.
This tests board recovery with a managed host source, not uninterrupted
client recovery. Cold audibility failure on this run remains unresolved.
[Evidence](hdmi-evidence/2026-10-27-reboot-acceptance/README.md).

## October 27 installed abrupt-reset result: digital PASS

All five installed orderly warm boots now have operator picture/colour/tone
confirmation (warm-01 in prior install record; warm-02..05 in current record).
One synced SysRq-b from warm-05 reached ccf94dbb-b82a-4b51-9ffb-2f1c812e07ac
through the installed startup without service teardown, GP7 arm, prompt hold
or RAM launch. Complete UART sync marker drained before reset. Digital gates
PASS: ~59.48 fps, zero cumulative rejected frames/capture xruns; DSP 0/0→1/1,
automatic HDOK, GP7 zero, units healthy/NRestarts=0. Abrupt operator confirmation
pending; no-source cold/reconnection still pending. Managed host output recreation
remains explicit, not continuous-client acceptance. Initial cold-audio silence
still unresolved and prevents claiming complete release acceptance.
[Evidence](hdmi-evidence/2026-10-27-reboot-acceptance/README.md).

## October 27 final acceptance result: FAIL — audio lifecycle

**HDMI reboot acceptance is NOT complete/passing.** Four remaining installed
orderly reboots warm-02..05 pass digital checks and operator picture/colour/
tone (prior warm-01 passed in the installation record). Managed host source
recreation is explicit; uninterrupted host-client recovery is not qualified.

Installed synced SysRq-b reached ccf94dbb-b82a-4b51-9ffb-2f1c812e07ac with
complete drained sync marker, expected HDOK/zero GP7/reset census and automatic
HDOK acknowledgement; ~59.48 fps, zero rejected frames/capture xruns, no
board service recovery. **Operator abrupt audio FAIL:** picture and colour
correct, tone started/stopped twice and then never returned. Digital flow
PASS is not acoustic PASS. Host HDMI monitor while silent has RMS 0.20993,
peak 0.29999 with exact projector routing/unmuted 100% source. Both board
PCMs RUNNING, mixer 43/15 and switches on, PA GPIO high, speaker NRestarts=0.
Saved silent PCM/mixer/GPIO, codec control registers and audio clock state.
Kernel denied the bounded read-only capture DRAM /dev/mem inspection; no
protection change or alternate raw-memory probe followed.

Initial cold boot also failed audibility until a documented consumer-only
stop/capture/restore. Incoming diagnostic tone was captured after reopening
the capture PCM and cannot establish original silent-buffer content. Root
cause remains open across capture/consumer/codec lifecycle. Do not mask this
with an automatic speaker restart or claim startup fixed.

Per stop-on-failure runbook, no further reset/poweroff/speaker restart was
issued. **No-source cold/reconnection case remains unrun.** Board left powered
on in the current silent failure, host player and sole passive UART recorder
running for diagnosis. Host projector test endpoint is 100%; saved original
35% (raw 22937) still needs restoration when testing finishes. No commit/push.
Next: diagnose/fix audio lifecycle, then requalify fresh cold/abrupt audibility
and execute the final no-source cold/reconnection case.
[Evidence and machine-readable verdict](hdmi-evidence/2026-10-27-reboot-acceptance/ACCEPTANCE-RESULT.json).

## October 27 PipeWire speaker fix installed; requalification pending

The direct consumer was replaced by the planned PipeWire loopback after
read-only volume inspection excluded a stuck fade/mute and a PCM re-prime
restored audibility. Exact old GStreamer/ALSA mechanism remains unisolated.
11 lifecycle tests / 17 mutations plus 46 existing warm tests pass. New route
passed stop/start capture closure, 600-ms client-pause recovery, actual capture
and codec-monitor 440-Hz content, updated graph/PCM ownership checks and
operator picture/tone. No backend/firmware/kernel/startup change. Backup
/var/lib/h713-hdmi-speaker/backup.AaUgab saved on host. Physical cold and full
reboot/no-source requalification remain pending; no PASS claimed yet.
[Evidence](hdmi-evidence/2026-10-27-audio-lifecycle-fix/README.md).
