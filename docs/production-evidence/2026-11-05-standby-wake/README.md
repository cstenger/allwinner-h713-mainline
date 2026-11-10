# Standby wake resets at lamp/fan enable — November 5, 2026

The failure was reproduced over SSH without pressing any physical button and
isolated to the lamp-enable write. The reset is real; its electrical mechanism
has not yet been measured. No persistent board configuration was changed.

The installed standby script exactly matches the repository version. Effective
logind settings ignore both short and long power-key actions. The key daemon
only invokes standby toggle. The original recorded journal has standby entry
but no completed wake or orderly shutdown. UART has a fresh SPL without a
captured panic. The operator reports a flash lasting at most about one second,
a second press a few seconds later, and no hardware/supply/connector changes.
Fan startup and press duration were not confirmed.

In the first controlled cycle, standby completed at uptime278.25s. HDMI remained
locked and active while CPU frequency was capped at480MHz and lamp/fan were off.
Sampled temperatures were about55–56C. After five seconds, a UART marker before
normal wake was recorded at02:35:16.292572UTC; fresh SPL followed at
02:35:16.479015UTC, about0.186s later. No after-wake marker was recorded.

In the second cycle, wake was split into lamp enable, a three-second delay,
and CPU maximum-frequency restoration. The marker before writing0 to
`/sys/class/backlight/lamp/bl_power` arrived at02:36:26.931744UTC; fresh SPL
followed at02:36:27.090126UTC, about0.158s later. The after-lamp marker never
arrived and the CPU-restoration stage was not reached. Thus the physical
button and CPU-frequency restoration are unnecessary to reproduce the reset.

PB5 enables the lamp boost converter and powers the fan. An electrical transient
when these loads start is a leading hypothesis; supply dip, rail/reset coupling,
and the underlying electrical cause remain unmeasured. There is no evidence
here proving a brownout. Runtime systemd watchdog is disabled; the exposed
watchdog bootstatus and pstore paths were unavailable. The short reset latency
and absence of panic/shutdown are evidence, not a reset-cause register.

There is also a standby integration gap: stop_players only targets h713-play,
gst-plane-play and mpv. It leaves gst-launch HDMI video and the HDMI audio path
running while the fan is off and CPU is capped. Earlier successful November3
standby tests used media playback and do not validate this HDMI-active condition.
Whether that load contributes to lamp startup reset requires a controlled
comparison; no causal claim is made from the code alone.

After the second reset the board stopped at the guarded U-Boot prompt.
Read-only inspection: GP6=48444f4b, GP7=0, MIPS status/clock/reset=0, but
0x070101ac=00010001 where hdmi_launch requires0. No guard was cleared and no
failed launch was retried. Full power removal is the recovery step. The passive
UART recorder remains running for recovery. The previous power-control observer
ended at the original reported reboot and was not reused for these cycles.

Evidence: [structured result](RESULT.json), [normal cycle](ssh-cycle.log),
[normal-cycle trace](ssh-cycle.stderr), [state samples](ssh-cycle-samples.log),
[split cycle](split-cycle.log), [UART](uart-through-held-prompt-timestamped.log).

Next: recover by full power removal. If further tests are authorized, compare
lamp wake with HDMI consumers stopped versus active and measure supply/CPU/reset
rails during the PB5 rising edge. Do not repeatedly exercise the reset while
assuming a software delay fixes an unmeasured electrical fault.

## Cold recovery completed

After the operator removed supply and UART/USB for30seconds, a fresh UART
OPEN was verified before applying board supply. Cold startup completed with
shared HDMI handoff verified; new boot `d636b84a-9db9-486b-87b0-67bf8ff04bae`
is locked1280x720 with lamp enabled, V2 loaded, and zero HPD retries.
The74-file runtime/kernel/bootloader/startup audit passed. Physical desktop
confirmation remains pending. No further standby cycle was attempted; the
lamp-enable reset remains unresolved. This source host was already primed,
so the recovery is not a fresh-source first-advertisement result.
[Recovery result](recovery-result.json), [audit](recovery-audit.json).

Operator subsequently confirmed the desktop is visible and left the board
running with HDMI and UART/USB connected. Cold recovery is visually confirmed.
