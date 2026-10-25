# Handoff: HDMI-in on the panel (route B + event-driven switching), 2026-10-24

For whoever picks this up (ChatGPT or a later Claude session). Keep this file
updated as work lands. The full record is
[hdmi-panel-source-design-2026-10-23.md](hdmi-panel-source-design-2026-10-23.md)
§10.25–§10.26; this file is the short version.

## Goal (user requirement)

The panel shows the U-Boot logo, then the Linux console. When an HDMI source is
connected and actually sending video, HDMI becomes the panel's picture. When the
signal goes, the panel returns to the console. Switching is event-driven
(no polling loop in userspace, no boot-time choice), and the same path covers
cold boot, warm boot and runtime plugging.

## Hard rules (do not break)

* Never read `0x07091000`–`0x07091fff` from ARM: a read wedges the SoC.
  Never touch `0x06940000`. Never write RTC GP7 (GP6 is the startup latch).
* PB5 is the lamp and the fan: never hold it low for long.
* After any MIPS source change, re-latch the 720p TCON timing (`0x05880020/24`).
  (Route B makes no MIPS calls.)
* **The HDMI source PC is the machine running the assistant.** Logging out or
  rebooting it kills the assistant and its ssh to the board. Run long board
  commands detached (`setsid nohup … > /root/log 2>&1 &`) and never ask for a
  host logout while a board command depends on the session.
* Operator-timed tests: announce, end the turn, wait for "ready". A cold boot
  means serial + USB unplugged and power off ≥ 1 min.
* Board root fs has ~170 MB free: never stream frames to a file there.
* Nothing is installed; staging goes under `/run` (reboot erases it).
  Production install needs explicit user approval. Only push to `cstenger/*`.
  Route B + event-driven switching are committed as `3a797cc` on
  `h713-letterbox` (not pushed). The earlier panel-source phases (T4–T6, Test
  1–3 tools/evidence, patches 0188/0189) are still uncommitted.

## How HDMI reaches the panel (route B, proven on glass 10-24)

The MIPS firmware writes the HDMI input as NV16 into a 3-slot ring in DRAM
(Y slots at `0x4c3ef000 + n·0x1ff000`, C slots 3 slots later). The bridge
module `modules/hdmi-v4l2/h713-hdmi-v4l2.c` (V4L2 node `h713-hdmi-in`) copies
the finished slot, converts it to NV12 (copy Y, average chroma row pairs:
`h713-nv12.h`) and exports dmabufs. Stock GStreamer puts it on the KMS NV12
video plane:

```
gst-launch-1.0 -e -q v4l2src device=/dev/h713-hdmi-in io-mode=dmabuf ! video/x-raw,format=NV12 ! kmssink driver-name=sun50i-h713-afbd sync=false skip-vsync=true
```

* Frame completion: AFBD `0x05600320` names the slot **being captured**; the
  finished frame is `(idx + 2) % 3` and stays still until the pair moves.
  A copy is accepted if the pair is unchanged afterwards. (Production has no
  VIncap hook, so `completion=pair`.)
* Result: 59.5–59.7 fps, 0 rejected, ~3 ms CPU per frame; colours correct on
  glass (band chart, video `local/lcd-photos/test_109`).
* `kmssink` needs `driver-name=sun50i-h713-afbd`.
* If the board cold-boots while the PC has dropped its HDMI output, the ring
  stays frozen; reseat the cable at the PC.

## Event-driven switching (built 10-24)

* `modules/hdmi-v4l2/h713-signal.h`: the state machine, shared by the module
  and the host tests. Live = port 1 state 5 + non-zero size + ring moving
  (sampled every 20 ms; port object read through guarded pointers in MIPS DRAM
  `0x4B100000–0x4BF41000`). States: none → acquiring → locked (200 ms stable,
  1280×720) or unsupported (anything else; 640×480 needs `allow_480p=1`).
  locked → holding after 100 ms without the signal (bridge sends black frames)
  → locked again, or none after 1.5 s.
* The bridge publishes the state as the `signal` attribute of
  `/sys/devices/platform/h713-hdmi-ring/`, a `change` uevent per transition,
  `V4L2_EVENT_SOURCE_CHANGE` on a new locked size, and the DV-timings ioctls.
  `STREAMON` returns `-ENOLINK` unless locked.
* `tools/hdmi/71-h713-hdmi-in.rules`: device ready only while
  locked/holding. `h713-hdmi-ring.service` loads the bridge;
  `h713-hdmi-video.service` runs the pipeline above and `BindsTo=` the device.
* `tools/hdmi/stage-hdmi-video.sh` (on the board, from `/root/hdmi-video/`):
  `observe SECS` (bridge alone, no panel change), `ARMED=yes … stage`,
  `status`, `unstage`.
* Build: `python3 tools/hdmi/build-hdmi-video.py build/route-b/bundle`
  (module built separately against the production tree
  `build/linux-6.18.38-edffad3c…` with `make … ARCH=arm64 LLVM=1 W=1`).
* Offline tests: `tools/hdmi/test-signal-state.c` (18 scenarios; 18
  mutations all caught), `tools/hdmi/test-signal-traces.py` (replays
  recorded firmware captures), `tools/hdmi/test-nv12-convert.c`.

## Where it stands

| Stage | Result |
| --- | --- |
| Route B on glass | PASS (§10.25.6) |
| 1. Observe (bridge alone, host actions) | PASS (§10.26.1): correct transitions for every action; compliance 48/48; longest mode-set gap 0.56 s |
| 3. Staged rule + units | First run failed on a udev rule bug (§10.26.2: `ATTRS{}` keys must match on one device). **Rerun with the fixed rule: PASS** (§10.26.3): 7 starts / clean stops, `NRestarts` 0, every host action correct per the operator |
| 4. Coldplug | Seen working at the start of stage 3 (unit started 64 ms after load) |
| 5. Install | **INSTALLED on the board 2026-10-24** (approved). Cold boot with cable: logo → console → HDMI at 20.85 s, PASS. Warm reboot: console only, because the production U-Boot warm path doesn't set `/chosen/h713,hdmi-boot-v1`, so the whole HDMI backend is skipped (expected per §6; needs the shared warm-startup U-Boot work). Second cold boot: PC re-enabled its output on hotplug, HDMI at 21.25 s; 13-min soak 59.7 fps, 0 rejected, `NRestarts` 0, speaker active. **Stage 5 PASS on cold boots** |

**Board now:** the event-driven HDMI video is INSTALLED (`/usr/lib/h713-hdmi-video`,
units in `/etc/systemd/system`, rule in `/etc/udev/rules.d`). Revert with
`sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --remove`. After a warm
reboot HDMI stays off until a cold boot (U-Boot warm path).

## Next steps

1. ~~Rerun stage 3~~ done, PASS (§10.26.3).
2. Stage 5 install (approval): `cd /root/hdmi-video && sh install-hdmi-video.sh`
   (bundle already on the board; `--dry-run` passed). Then cold boot with the
   cable, warm reboot from HDMI (watch panel-black), cold boot with PC output
   off then on, 10-min soak. Revert: `sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --remove`.
   Installer test: `sh tools/hdmi/test-install-hdmi-video.sh build/route-b/bundle`.
3. Open user decisions: Q7 (HDMI vs local Cedrus playback priority), Q9
   (640×480: console, show 1:1, or drop from the EDID).
4. Later: 1080p50 sources drop about a third of frames in capture;
   interlaced input untested; the PipeWire audio loopback and A/V sync (§5).
