# HDMI regression checks — November 2, 2026

**Host reboot: PASS. Long session: PASS. Reconnect: functional PASS, with
unmeasured reconnect latency.** Board remains on with HDMI active; both
bounded temporary recorders have finished. No board reboot, manual HDMI
service recovery, forced detection or extra cable reseat occurred.

## Host reboot with board powered

The host changed from boot `c7a3a471` to `c849164e`; the board remained on
boot `0d1179fa`. The continuous recorder saw locked input, holding, no source,
then 1280×720 lock. One automatic re-advertise cycle occurred. The operator
confirmed the desktop returned normally without intervention. All 59 file
checks and the full startup check pass; owner service start identities are
unchanged and sampled errors/automatic restart counts remain zero.

[Host-reboot result](HOST-REBOOT-RESULT.json).

## Long session before physical unplug

The initial two-hour gate passed with 7,455.39 seconds, 1,448 samples and
59.708 captured fps. Input continued until the operator unplugged HDMI;
complete retained observation establishes **13,113.19 seconds (3 h 38 min)**
of continuous 1280×720 input at 59.708 fps, zero rejected frames, capture
xruns, bad guards or invalid AFBD observations, with unchanged owner services.
All 59 file checks passed before unplug.

[Initial soak](SOAK-RESULT.json) and
[full pre-unplug session](PRE-UNPLUG-SESSION-RESULT.json).

## Physical reconnect

The operator unplugged at the host and kept the board powered. Host cached
state confirmed disconnected with zero EDID bytes; board snapshot and log
confirmed `none`, same boot and zero errors. The same cable/port was
reconnected, and the operator confirmed a normal desktop return. The board
journal records video stopping at uptime 16327.754080 and automatically
starting at 18114.623337. Five scheduled re-advertise cycles completed during
the long unplugged interval; no manual HDMI recovery was performed.

Final observation verifies 15.48 stable seconds at 59.690 captured fps,
1280×720 lock, advancing frames, zero errors, no automatic service restart,
unchanged owner service start identities, all 59 file checks and full startup
checks passing. The video service itself is intentionally stopped/restarted
by the signal policy. Host EDID again matches the expected 256-byte payload.

**Timing qualification:** the original four-hour board sampler and bounded
15-minute host monitor expired while the cable remained unplugged. Thus
physical reconnection and the initial transition back to video are supported
by the retained service journal, final snapshots and operator confirmation;
continuous sampling across that transition and exact plug-to-picture latency
are unavailable. This is functional acceptance, not a measured latency gate.

[Reconnect result](RECONNECT-RESULT.json), [final file checks](reconnected-files.json),
[startup check](reconnected-startup.txt), and [stable-video samples](recovered-stability.jsonl).

Full raw samples, host/board journals, initial state and source snapshots are
private under `local/recovery/2026-11-02-hdmi-regressions/`, sealed with recursive
SHA256SUMS. The quiet heartbeat was deleted after the soak passed. Board
calendar timestamps remain unsynchronized; host timestamps, unchanged boot
IDs and monotonic board uptime establish order. No commit or push requested.
