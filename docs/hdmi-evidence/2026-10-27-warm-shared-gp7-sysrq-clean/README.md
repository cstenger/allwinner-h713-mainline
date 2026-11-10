# Clean GP7 SysRq-b repeat with UART drain, October 27: PASS

**Final result:** cold and warm moving video, correct colours and audible tone
confirmed; digital comparison passes. Full UART acknowledgement/drain, one
GP7-armed synced abrupt reset and one automatic RAM source. No manual
continuation, long diagnostic hold, speaker restart or board mixer changes.
Checked final poweroff complete; board powered down.

Operator explicitly approved a clean repeat, reported board off, and asked
for unplug instructions/OPEN before next power. Instructed disconnect board
power/serial/USB >=1 minute, keep HDMI and host serial adapter connected.
Host tty free, HDMI disconnected; fixed tool/FIT/script hashes match
build/hdmi-warm-shared-gp7-sysrq-drain-2026-10-27/manifest.json.

Reviewed wrapper copies existing cold/warm source gates, uses fixed candidate,
and fresh output directory. Detached sole UART reader OPEN (events.log).
Host console build/hdmi-warm-shared-sysrq-source-2026-10-27/clean-runner.log.
No boot result/reset/arm yet. Operator must finish >=1 minute disconnected
before serial-first then mains, USB stays disconnected. No manual key needed.

Goal: complete acknowledgement/drain, one GP7-armed synced abrupt reset,
automatic census/transfer/one RAM launch without the earlier long U-Boot hold.
Cold audible baseline must pass without a speaker diagnostic restart for a
clean result. Host test volume may be set 100%, preserving prior 35% for final
restoration; no board mixer changes. Any failed/uncertain stage stops with no
retry. Operator warm picture/colour/tone report precedes checked final poweroff.
No production installation/GP6 change/commit/push. No result claimed yet.

Operator confirmed >=1 minute unplugged, board powered, USB disconnected.
Complete cold markers/census/re-latch/handoff/login captured; boot ID
6a1c0d18-2271-49ec-b8db-0e20ed1880d7. Host Wi-Fi spirits explicitly reconnected;
HDMI auto-enabled 1280x720 60 Hz. Host projector volume prior value saved,
test level set to 100%, moving pattern/tone started and actual routing verified
(host-source-cold.json). Waiting for operator cold picture/colour/tone;
cold reset gate closed. No speaker restart, mixer changes, GP7 arm or reset.


Clean cold on-glass picture/colour/tone confirmed, no speaker restart/mixer
changes. Fresh cold health PASS. One GP7-armed synced SysRq-b at 10:01:13 UTC;
**complete** UART acknowledgement includes GP7/GP6 and the expected cold boot
ID before sysrq: Resetting. One warm SPL, complete early census, automatic
prompt at 10:01:16. Prompt GP7 consumed to zero, GP6 preserved, MIPS/PPU zero,
preboot/bootcmd unchanged and volatile bootdelay=-1. FIT/script CRC passed;
source sent once 10:01:47.821 (31.52 s normal automated census/transfer after
prompt, no manual hold). Warm re-latch/handoff 10:01:55, kernel then login
10:02:10. No manual continuation or second reset.

Warm boot 57f6df2f-e9a9-44ff-a965-00cf5b5ab697; host source restarted with
verified projector route and 100% test volume, Wi-Fi reconnected. Warm health
and cold/warm comparison PASS: DSP 0/0 -> 1/1, audio ~48 kHz, zero new xruns,
video locked 720p, 184 delivered / 3.07784 s (~59.78 fps), zero rejected,
NRestarts=0, service start 21.279 s. See health/evaluation JSON and compare.json.
No board speaker restart/mixer writes on either boot. Await operator warm
picture/colour/tone report before declaring on-glass PASS and final poweroff.


## Final operator acceptance and shutdown

Operator explicitly confirmed warm moving video, correct colour and audible
tone (operator-warm.txt). This validates the clean abrupt repeat with the
UART-drain fix on this run. Cold audio also worked without restarting its
consumer. The earlier isolated cold-audio silence remains an open observation,
not disproven by this clean pass. Ordinary orderly repeat passed October 24;
the two requested RAM-only reset variants now have on-glass/digital passes.

Host projector volume restored from test 100% to prior 35%; test player stopped.
One checked final poweroff: UART reboot: Power down at board uptime 129.256017 s,
host receipt 2026-10-27 10:04:05.393 UTC (03:04:05 PDT). Reader closed normally.
Evidence in host-hdmi-volume-restored.log, host-poweroff.log, uart-poweroff.log
and events.log. No additional reset, GP7 write, install, saved environment or
GP6 policy change. No commit or push.

This is the RAM-only test path, not production warm-startup adoption. Host
playback was restarted explicitly after HDMI hotplug; unattended board boot
and automatic RAM launch were verified, but uninterrupted HDMI-source timing
and power-on-to-picture latency were not measured here. Normal automated
prompt verification/transfer took 31.52 s; no operator pause at U-Boot.

Next: offline production shared cold/warm branch with four-state GP6 crash-loop
guard, health-ack unit and mutation-tested acceptance. GP6 software policy and
production install still require explicit approval; then repeated warm soak
and continued tracking of cold-audio/panel-black observations.
