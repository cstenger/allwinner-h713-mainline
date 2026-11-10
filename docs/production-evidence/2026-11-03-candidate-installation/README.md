# Rebuilt candidate installation — November 3, 2026

The candidate is installed. Hardware qualification is complete for the documented scope,
with the specific GF1 protective-drop finding closed by [engineering disposition](../2026-11-04-guarded-discard-disposition/README.md).
Historical failures and limits below remain part of the record.

All four packet writes completed once in root/FAT/proper/SPL order. UART CRC
checkpoints passed (128/2/1/1). A complete direct read of all 7,818,182,656 bytes
before first boot matched the sealed expected installed SHA-256
`bb665353bf41129f618eec2daff893c2f4d794884220c5059f1dabb3df825048`.
Every byte outside the four authorized extents, including Android, GPT, saved
environment and rescue artifacts, therefore matched the accepted baseline.

The first physical cold boot captured the November 3 rebuilt SPL, TF-A,
U-Boot and kernel. Chris confirmed normal desktop recovery without reseating
HDMI or restarting services. A read-only runtime audit passed 71 file and
metadata checks, exact package/configuration identity, raw SPL/proper/environment
hashes, all four HDMI manifests and startup checks. Seven HDMI services were
active with zero restarts. Linux grew the filesystem to the existing 2.75 GiB
partition; Android space was not reclaimed. Bluetooth was UP RUNNING, attached
on attempt one. Host timestamps and boot IDs are authoritative; board RTC is stale.

Preserved corrections and excluded results:

- UMS/fastboot function switching stalled before any initial write. A physical
  cold entry with fastboot first completed the write sequence; no UMS between
  phases. No failed or ambiguous flash was retried.
- A FAT prewrite synchronization attempt sent blank Enter, repeating the last
  harmless CRC command. The tested controller now sends an explicit echo.
- The initial audit hard-coded p26 major/minor 179:26; this kernel allocates
  259:18. It now compares the mounted device with p26 st_rdev.
- Initial decoder diagnostics ran on an HDMI boot, contrary to the documented
  local-playback isolation requirement. Their pixel/interrupt results are
  preserved privately but excluded from release acceptance. They must be
  repeated on a separate cold local-playback boot. The legacy HEVC script
  also skips VA when production omits vainfo; a temporary direct-decode variant
  removes that discovery gate without installing development tools.

Private raw transcripts, receipts, keys and temporary media are under the
November 3 production-install recovery directories. No production image,
hotspot credential, private backup or generated SSH private key is published.

Two ordinary synced warm boots also passed the full 71-file runtime audit,
all four bundle manifests and startup gates with zero service restarts. The
first warm-boot audit was requested before HDMI initialization finished;
its failed readiness result is retained alongside the subsequent natural
ready pass, without service intervention.

A separate physical cold entry used the existing logo-only path, with MIPS
explicitly quiesced (reset zero and changing nonzero raster samples). Linux
had no HDMI handoff, owner modules or session, all seven HDMI units were
inactive, and the supported local-playback policy permitted access. The same
71-file/package/configuration/raw-boot identity audit passed. Temporary media,
reference files and harnesses were SHA-verified before use.

On this isolated boot, five H.264 VA vectors, seven HEVC GStreamer vectors and
seven HEVC VA vectors passed bit-exact checks with positive hardware interrupt
counts and no skipped cases. This supersedes the excluded HDMI-boot diagnostics.
The temporary HEVC harness directly exercises VA rather than using the omitted
vainfo utility as a discovery gate. No development package was installed.

Chris confirmed normal local GPU picture/motion and continuous tone, every
mirror orientation and restoration, and manual keystone deformation/restoration.
mpv reported VA decoding, PipeWire audio, active keystone shader, zero rendered
or decoder frame drops and final AV sync error 0.118 ms. Mirror returned to
front; manual keystone restored the original automatic runtime configuration;
the persistent calibration bytes remained unchanged. Native-plane picture and
tone were also confirmed. Final logs and remaining tests are tracked privately.

Both 30-second native-plane AV passes completed: 1,800 frames, zero drops.
Short VP9 and AV1 checks also passed (16/16 exact frames and positive hardware
interrupt deltas; AV1 had zero new decoder errors). Plane-up magnification
rendered all 16 VP9 frames; VE downscaling rendered all 60 H.264 frames, both
with zero drops. These short extra cases are smoke coverage, not a full codec
conformance claim. The temporary target media, scripts, reference files and
IPC socket were removed after all players/decoder processes exited.

The physical case button entered standby and woke successfully. Chris observed
lamp/fan off, then lamp/fan/picture restoration. The Linux boot ID stayed the
same; CPU maximum changed from 1,296,000 to 480,000 kHz and restored exactly.
The key daemon recorded both toggles returning zero. The initial bounded
standby observer expired before the operator press; that timeout is preserved,
and the resulting standby state plus monotonic journal are recorded separately.
Wake was observed prospectively. The post-wake 71-file/configuration/package
identity and local-isolation audit passed, with no failed services.

Remote IR Power also entered standby and woke successfully. Raw sunxi-ir
records show scan 0x14 / KEY_POWER for both actions, the same Linux boot,
lamp power 4 then 0, and CPU maximum 480,000 then 1,296,000 kHz. Chris confirmed
lamp/fan off then lamp/fan/picture returned. Mute was separately confirmed as
scan 0x01 / KEY_MUTE; the initial suspected Power press was clarified as the
wrong button. The active map matched the pinned source and was not changed.
Final local health passed with no failed units or key-daemon restarts.

The subsequent normal cold HDMI boot passed the complete runtime/startup
audit again on boot b1592dff-0165-4071-8c9e-0b7a97a19691. Chris confirmed
normal desktop return without intervention. Host EDID matches the accepted
256-byte payload. A separate temporary observer is running under /run for
host-reboot, continuous-input and reconnect checks; these remain pending.

Host reboot regression passed on the rebuilt candidate: the host boot ID
changed, board boot b1592dff-0165-4071-8c9e-0b7a97a19691 remained unchanged,
and the independent observer recorded source loss and stable 720p recovery
with zero errors. Chris saw the host boot screen and desktop on the projector.
All 71 runtime checks plus manifests/startup passed afterward. The temporary
packet read-only host rule disappeared with reboot as intended. Continuous
input starts at board uptime 451.61, targeting 7651.61; completion and the
physical reconnect remain pending.

The first candidate soak interval was interrupted: the video renderer stopped
at board uptime 820.393 and restarted at 822.086, resetting its frame counter.
Five-second signal snapshots missed this brief transition; owner services and
error counters remained healthy. This is not a continuous-input pass. Cause
is under investigation, with operator clarification pending. The local soak
analyzer now rejects renderer identity changes and frame-counter resets even
when signal samples remain locked and aggregate frame rate could exceed the
threshold; five analyzer tests pass. The read-only board observer is unchanged.

Chris subsequently reported that the host desktop crashed and all applications
were closed when it returned. This resolves the source-session interruption
classification without asserting a GPU-driver root cause. The original
interrupted window remains invalid. We explicitly selected the first recorded
stable sample after that recovery, uptime 822.65, and validated all existing
continuous observations through uptime 11475.6. That post-crash
window passed 10652.95 seconds (2 h 57 min), at 59.708 fps,
with zero errors, no renderer identity changes or counter resets, unchanged
owner services and the same board boot. The post-soak runtime audit passed
all 71 files plus package/configuration/raw-boot/manifests/startup checks.
Prospective quarter-second host/board reconnect recorders are armed; their
clock-correlation uncertainty is preserved. The physical cable test is pending.

Physical unplug/no-source/reconnect completed on the same board boot. Chris
confirmed normal desktop recovery and a steady, clear HDMI-fed speaker tone.
Kernel signal lock returned at uptime 21221.120 and the renderer started at
21221.170 without manual recovery. Stable post-reconnect video and all 71
runtime/manifests/startup checks passed. Timing snapshots and clock bounds
are preserved; the actual host polling gap reached 3.20 s, so no precise
physical cable-insertion latency is claimed.

**Open qualification anomaly:** later in the extended run, after the defined
2 h 57 min passing soak and before unplug, frames_rejected rose once at
uptime 19154.59. Stream-stop statistics confirm one unstable copy discarded
out of 1,211,737 completions, with no renderer restart at the event. The exact
trigger is not established. The strict zero-error recovery analyzer therefore
failed on the preexisting counter; that failure is retained, not waived. The
normal reconnect started a new stream and reset its counters; subsequent
counters stayed zero. Functional recovery is a pass, while the anomaly and
recovery-route rehearsal keep the release unqualified.

Final board logs and sources were copied and matched all four stopped-device
SHA-256 hashes. Only the two temporary observer units and host recorder were
stopped; their /run files were removed after preservation. Production HDMI
services and configuration were not restarted or changed.

The non-writing FEL recovery-entry/access rehearsal and cold return to the
installed candidate now pass, including 20 USB identity/size gates and four
protected boot/environment/rescue CRC checkpoints. Chris confirmed normal
desktop return and the 71-file runtime audit passed again. This did not
exercise rollback writes. See [recovery-entry evidence](../2026-11-03-recovery-entry/README.md).
The candidate remains unqualified pending disposition of the extended-run
guarded frame discard; no binary or acceptance threshold was changed to hide it.

## November 4: remaining finding resolved

GF1 is closed by an explicit engineering disposition, not a driver change or
rewrite of the strict zero-error failure. The actual-source race tests prove
that both possible guard paths discard the attempted copy and continue with
a valid frame; the guard-bypass negative control is caught. The bounded load
diagnostic and final 71-file/runtime audit show normal recovery and unchanged
production identities. Exact historical timing was not captured. See the
[complete disposition](../2026-11-04-guarded-discard-disposition/README.md).

The required hardware checks are complete for the tested DDR3 board and pinned
candidate, with that reviewed protective drop documented. No full rollback
write or exhaustive codec-conformance claim is made. The immutable candidate
and installation packet were not edited; this external evidence records the
qualification decision. No commit, push or release publication was performed.
