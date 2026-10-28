# GP7 orderly warm trial, October 24: PASS

User approved checked poweroff (confirmed separately), disconnected cold cycle
and this trial by saying ready. Prepared source and tool/FIT/script hashes
verified against build/hdmi-warm-shared-gp7-2026-10-24/manifest.json. Host tty
ownership precheck was empty; HDMI disconnected. Started the reviewed GP7
gated wrapper detached; events.log confirms OPEN. Wrapper saved alongside.
Host console log: build/hdmi-warm-shared-source-2026-10-24/gp7-runner.log.

Next: operator serial-first then mains, USB remains disconnected. Cold source
confirmation and health gate precede one kernel bootloader reboot request.
GP7 remains reserved for existing reboot-mode use; no manual interrupt needed.
Detailed approved sequence: ../2026-10-24-warm-shared-gp7-preparation/README.md.
Final outcome and acceptance evidence follow below.

Cold boot reached login and source gate, boot ID
c58dd5cc-610f-4669-a38b-6b791bb3220b. Host HDMI auto-enabled 1280x720 60 Hz.
Started prepared clip fullscreen on HDMI-A-1 with explicit projector audio.
host-source-cold.json records unpaused playback, sink 632 RUNNING and stream
639 routed to it. Cold source was then confirmed by the operator; see final results below.


## Final result

**PASS for this one RAM-only orderly warm recovery trial:** operator saw Linux
console -> host desktop -> test video and heard tone after warm reboot; digital
cold/warm comparison passed. No panel-black reported. This is one repetition,
not the full warm-recovery release acceptance (abrupt reset and soak remain).

| Check | Cold | Warm |
| --- | --- | --- |
| Boot ID | c58dd5cc-610f-4669-a38b-6b791bb3220b | cf0c32a3-3099-4654-acd1-7129c73631a6 |
| DSP | 0000/0000 -> verified 1/1 | 0000/0000 -> verified 1/1 |
| Audio capture/playback | 48008.8 / 47998.2 Hz | 48016.6 / 48006.0 Hz |
| New audio xruns | 0 | 0 |
| Signal | locked 1280x720 | locked 1280x720 |
| Delivered frames/sample | 184 / 3.0944 s (~59.46 fps) | 184 / 3.0771 s (~59.80 fps) |
| New rejected frames | 0 | 0 |
| Video service start after kernel | 21.598 s | 21.255 s |
| Video NRestarts | 0 | 0 |
| Operator | video and sound working | console -> desktop -> video and tone |

Both PCMs RUNNING and owned by hdmi-speaker. Complete unit status, monotonic
journal, bridge dmesg, counters, startup output and DSP evidence are in
cold-health.json / warm-health.json; evaluations and compare.json pass.
Colour accuracy was not separately reported on this trial (prior route B
on-glass colour validation remains the record).

## Reset/launch evidence

One orderly bootloader request at 06:29:20 UTC. One warm SPL at 06:29:28;
proper_preboot GP6=48444d49, GP7=b007c0de, MIPS clock/reset/status zero.
U-Boot prompt reached 06:29:30 **without an interrupt key**. Prompt census
confirms same bootcmd/preboot, volatile bootdelay=-1, GP7 consumed to zero,
GP6 unchanged, MIPS status=0 and PPU bus=0. FIT size/CRC verified before transfer.
RAM script: 4062 bytes, CRC32 b4a0cbfa verified. Exactly one source sent at
06:30:02. Timing re-latch and warm handoff at 06:30:09; kernel at 06:30:10;
login at 06:30:25. New warm boot ID confirmed. No extra reset/failure marker.
See raw UART, events.log, warm-prompt-census.json, script-transfer.log and
launch-attempted. No production image/environment change or manual GP6 write.

## Host-source timing limitation

Cold player was intentionally stopped during reset, then restarted explicitly
on HDMI-A-1 with projector audio after hotplug. Actual sink routing was checked
(host-source-warm.json) before warm health. The host desktop preceding the clip
is expected from that procedure. Service start time is digitally measured;
this trial does not measure uninterrupted source recovery or glass-to-glass
latency, nor does it establish an exact power-on-to-picture time.

## Checked shutdown and remaining work

After operator warm confirmation, stopped only test player to prevent host
audio fallback. One approved final poweroff; UART reboot: Power down at board
uptime 123.828530 s, host 06:32:14 UTC (October 24 23:32:14 PDT). Reader closed
normally. See uart-poweroff.log / host-poweroff.log / events.log. Board is
powered down; no further boot or GP7 request. No commit/push.

Next: prepare a separately reviewed boot-stop arming path for SysRq-b, which
skips restart notifiers; run that operator-approved abrupt trial. Production
GP6 shared branch/health-ack, install approval and repeated soak still remain.
The earlier serial capture-loss cause is unresolved; this complete GP7 run
succeeded, but does not prove that transport issue fixed.
