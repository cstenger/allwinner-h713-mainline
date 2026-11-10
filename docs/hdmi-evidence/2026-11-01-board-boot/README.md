# Board boot and HDMI detection recheck — November 1, 2026

**HDMI no-detection reproduced. Boot/startup health passes.**
The operator powered on once after the passive UART recorder was armed. The
board reached Linux normally, but HDMI remains `none`, with zero signal
transitions and video frames. The host's cached HDMI state is disconnected,
disabled and has zero EDID bytes. No connector probe or recovery was requested.

[Result](RESULT.json), [board summary](BOARD-SUMMARY.json),
[UART boot excerpt](uart-boot.txt), [startup check](startup-check.txt),
[cached host HDMI](host-hdmi.json), and [recorder completion](RECORDER-STOP.json).
Private raw capture and read-only evidence are under
`local/recovery/2026-11-01-board-boot-uart/`.

## Boot evidence

The continuous capture contains one SPL banner, one U-Boot proper banner,
the expected migrated U-Boot build, successful environment load from
`0x93d80000`, verified shared HDMI handoff and Linux login. There are no UART
disconnects or open failures. Duplicate Linux-version lines are early-console
duplication, not evidence of a second SPL/proper sequence.

Current boot: `afe48e93-6604-44de-a220-acb9416e8363`.
DT handoff is `48444d49000000008b8f275c`. The normal startup checker passes,
the session is ready, DSP initialization reports `0000/0000` followed by verified
`1/1`, and all 56 installed file/metadata pins match. Receiver clocks=4,
clients=2, EDID ready=Y, firmware pin=Y, init_error=0; signal owner ready=Y,
failed=N, restored=N, recovery=0. Old diagnostic/probe modules are absent.

Capture/signal/ring oneshots completed successfully; the speaker runs without
a restart. Video is inactive with success status, consistent with the ring's
no-signal gate. The capture-startup helper is a successful completed oneshot,
not a failed service. Frame rejection, guard and AFBD-invalid counters are zero.
This is startup-path health, not proof that a source detected the board.

Board journal wall-clock dates are unsynchronized. Boot IDs, kernel-relative
times and host UART timestamps establish this sequence; stale board calendar
dates do not indicate an old capture.

## Board-side read-only state

A bounded `O_RDONLY`/`PROT_READ` snapshot confirms the expected original SCP
code, checksum-valid HCP/H713 HDMI IN EDID payload, ready/backup magic and zero
exception/error/stop/done markers. SCP run/reset-control readback is `1` and
DDC mux readback is `0x222222`. Only established safe scalar controls, SCP SRAM
and validated MIPS DRAM were mapped. No ARM receiver MMIO or firmware IPC ran.

The retained active handoff words match the earlier failure: HPD control=0,
DDC config `00a0a0a0/07000007/00c0c0c0`, optional controls `3/0/18/18`, and
bank first-word records zero. These are existing setup-time SRAM records,
not a new live peripheral sample. The `readback ffffffff` log line is the
unused post-restore poison area; no restore occurred. Active-window zero EDID
reads have previously accompanied successful detection and do not prove loss.

MIPS port 1 has cached state 3 (selected/no video), count and dimensions zero;
the other ports have state 1. A single cache snapshot does not prove firmware
liveness. Whole SRAM differs from the prior boot in low SRAM and original
bank backups; code, staged payload, metadata, traps/scratch and mailbox match.
The old boot-bound SCP packet remains invalid and was not reused.

## Interpretation and endpoint

This reproduces the same no-input symptom after another ordinary board boot
with HDMI already connected, despite successful software setup. It does not
identify an electrical HPD/DDC fault or prove the host's detector is at fault.
No continuous host hotplug timeline was recorded during this boot, so these
checks cannot locate the instant detection failed or exclude an earlier brief
host detection before the Linux ring began monitoring.

Initial SSH access timed out while the host board-Wi-Fi link was disconnected.
It subsequently appeared connected to the saved board profile before any
connection-change command was issued, after which SSH succeeded. That access
delay was not evidence of a board boot failure.

The host recorder was stopped cleanly once the boot evidence was complete;
UART is released and no bytes were transmitted. Final read-only checks confirm
the same board boot, signal `none`, transitions=0 and frames=0. No board service
start/stop/restart, SCP injection, peripheral write, HPD pulse, reseat, extra
reset/reboot or environment save was performed. Preserve this fresh bad state
for further board-focused diagnosis; the cause remains unresolved.
