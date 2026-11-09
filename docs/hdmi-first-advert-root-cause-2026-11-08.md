# First HDMI advert after a source PC boots: cause and event-driven fix

November 6–8, 2026. DDR3 board (HY200 QZ713DF_A1), NVIDIA source PC (open
driver 615.78.08, COSMIC/Wayland). Evidence and resume files are under
`local/recovery/2026-11-0{6,7}-*` and `2026-11-08-hpd-event-rearm`.

## Result

The release signal owner is now `hpd-event-v1`: the SCP watches the DDC lines
from owner ready and the re-advertise policy pulses HPD as soon as a source's
EDID read fails, instead of waiting a fixed time. On a freshly booted source,
video now locks **2.12 s after owner ready (was ~4.6 s)**; a source that reads
the EDID normally is never pulsed.

| Test (hpd-event-v1) | Runs | Result |
| --- | --- | --- |
| Fresh source (PC rebooted, board off) | 3 | failed read seen, pulse at owner +0.69–0.70 s, lock +2.12 s |
| Primed (board power cycle only) | 2 | real read, no pulse, lock +1.35–1.36 s |
| Source PC reboot with the board on | 2 | pass (second run with re-arm-on-loss) |
| Cable unplug/replug | 1 | pass, no pulse needed |
| 5-minute stream | 1 | 59.71 fps, 0 overwritten, 0 rejected |

## What actually happens on the first advert

Each step below was measured on the board and the source.

1. **The source does read the EDID.** It drives DDC traffic ~0.50 s after the
   first HPD rise, and again ~0.49 s after a pulse (SCP DDC-line watch, n=4).
   The earlier "NVIDIA ignores the first HPD rise" was wrong.
2. **Our EDID slave does not answer that read.** In the failed state (pulse
   disabled for one boot) `i2cdump -y 1 0x50` from the PC returns all `XX`, twice.
   The failed transfer lasts ~7.5 ms with ~2.6 ms of line activity — the source
   retrying an address that is never acknowledged — against ~108 ms / ~65 ms for
   a real read. So the slave was already refusing; the read did not wedge it.
3. **The source then correctly sees nothing.** With `drm.debug=0x6` the host
   logs no hotplug and no probe on the first advert: NVKMS read DDC, got NAKs,
   and reported no display. After a pulse the read and nvidia-drm's
   `generating hotplug event` land in the same millisecond.
4. **Only an HPD edge clears the slave**, and the cause is invisible to us:
   * all 768 words of the SCP-owned receiver block `0x07091000–0x07091bfc` are
     identical failed vs recovered (only 8 are non-zero);
   * the 12 stock-accessed receiver registers do not change from owner ready
     through the failed read and the pulse;
   * the MIPS firmware's log (`elog`, DRAM `0x4b270000`) is identical up to the
     advert in failing and passing boots (HDCP/DDC reset released at tick 12990
     in both), and the MIPS does nothing during the read or the pulse;
   * pin mux (PL10–15 fn2) is unchanged;
   * the whole MIPS HDCP/DDC wrapper `0x06840000–0x06840fff` (4096 bytes,
     SCP byte reads, 2026-11-09) carries no NAK indicator. Failed vs recovered
     differs in 64 bytes, nearly all the receiver's measurement of incoming 720p
     video (e.g. `+0x28..0x3e` = 1280/1650/110/370/220/40, 720/750/5/30/20/5).
     A control with the EDID answering (PC `i2cdump` returns the EDID) but the
     PC's output disabled leaves only bytes that latch once video has run and
     stay set after it stops (`+0x05/08/0e/0f/11/13/79/9b/1ad`); the failed
     state is the only one in which video never ran, so they cannot separate
     the NAK from "no video yet". The HDCP/DDC reset byte `+0x1b` (00), i2c
     busy `+0x95` and DDC lines `+0x96` are identical in all three states.
     The scans did not clear the NAK (`XX` afterwards). Evidence:
     `local/recovery/2026-11-08-wrapper-scan/`.

   The register-level investigation is **closed**: without probing the DDC
   pins there is nothing left to read. The NAK is a known limit of this board;
   the event-driven pulse below is the accepted fix.

   The source does not need to be freshly booted: a board power-on after an
   overnight off, with the PC left running, also hit the failed read (busy 36)
   and was recovered by the event pulse. No single
   standard DDC transaction from the PC's userspace (0x50/0x37/0x3a/0x54/0x30,
   segment write) reproduces the stuck state.
5. **Stock does the same.** The vendor SCP re-raises HPD on a timer
   (`hpd %d up by timer`), so later HPD edges are part of the vendor design.

## The fix

* **Signal module** (`make-edid-trial-code.py --verify-restore --readvertise
  --hpd-pulse --scan-bytes`, `MODULE_VERSION("hpd-event-v1")`): HPD-only 150 ms
  pulse request (DDC never written) plus an SCP scanner reading the MIPS
  wrapper bytes `0x06840094..97` from owner ready. `0x06840096` bits 4/5 dip only
  while the source drives DDC. Per arm it keeps `act` (first toggling pass),
  `last` and `busy` (toggling passes, ~57 µs each). Read-only; the SCP never
  writes the wrapper.
* **Policy** (`h713-hdmi-readvertise.py`, 0.1 s polls for this owner): a failed
  read is `act` set, `busy < 120`, no new activity for 0.1 s, signal still
  `none` → re-arm and pulse at once. At most 2 event pulses per fresh period,
  1 s apart; the timed schedule (2, 10, 20, 40, 80, 160 s) remains the
  backstop. The watch is re-armed when a streaming source is lost or its power
  returns, so a returning source's read is judged on its own.
* **Release**: `tools/release/build.py` `SIGNAL_SCP_FLAGS`; the module built
  from release inputs matches the qualified binary (SHA-256 `ee84947d…`).

Thresholds come from the board (failed 40–46 passes, real reads 1148–3129).
A 128-byte read at 100 kHz is ~200 passes, so 120 sits between them; a source
using fast-mode DDC would be misread as failed and get one harmless extra
pulse.

## Separate open issue: green picture (AFBD stall)

On 1 of 9 boots in this work the picture was green with magenta highlights —
luma being fetched as chroma. Capture, our NV12 frames (read back through
V4L2), the KMS framebuffer, the AFBD Y/C addresses, strides, format, IOMMU
bypass `0x58`, panel selector and chroma gain were all correct. A green vs good
display-register sweep shows the AFBD stalled: publish latches `0x05600014` and
`0x0560006c` stuck at 1, `0x05600038=0x10`, `0x05600338=0x01000001`,
`0x056001cc/0x056001fc` set. A pipeline restart does not clear it; a power
cycle does. No link to the HPD change is established. Per-boot check:
`local/recovery/2026-11-07-hpd-event/qual-check.sh` (latches sampled 50x).

## Tools added

* `tools/hdmi/host-first-advert-capture.sh` — host-side NVKMS/DRM debug
  capture, restored on exit (`test-host-first-advert-capture.py`).
* `tools/hdmi/host-ddc-wedge-probe.sh` — one-at-a-time DDC probes from the PC.
* `make-edid-trial-code.py --scan-ddc / --scan-bytes / --scan-words` —
  read-only SCP scanners (DDC block words, MIPS wrapper bytes, receiver block).
* `tools/mips/elog-parse.py` on a DRAM dump of `0x4b270000` reads the MIPS log
  safely from the ARM side; the MIPS shell `regr` prints to UART4 and is blind.
