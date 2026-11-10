# Migrated U-Boot/environment: one warm reboot passes — October 31

## Latest endpoint — completed under operator authorization

**PASS: exactly one ordinary warm reboot, correct migrated environment load,
unattended Linux startup and normal desktop return.** Chris confirmed readiness
to watch and explicitly requested the one reboot. Host-visible service/PID/
sole-reader checks and immediate read-only current-boot/startup/filesystem/
latch preflight passed before launch. A detached, single-use request ran
`sync` then `systemctl reboot`; its marker and log are preserved.

Pre-boot ID: `85768624-6a6e-4637-a50f-f45b2c156f31`.
Returned boot ID: `b6849123-0398-4736-b06f-cfe25b19e593`.
UART contains one `reboot: Restarting system`, one expected SPL/proper sequence,
and:

```text
Loading Environment from MMC... Reading from MMC(1) at 0x93d80000... OK
```

The expected `g320a17f71d41-h713-b3b5f2d2` proper completed shared handoff and
booted Linux without a prompt hold, RAM script, CRC/default-env fallback,
manual latch arming or recovery. This was an observed warm reset, not a
shutdown-guard poweroff. The new ready boot returned within the bounded
three-minute window. No second reboot/reset was requested or observed.

Read-only post-checks pass: automatic startup, DSP 0/0 → 1/1, HDOK/GP7 zero,
zero service-recovery restarts/xruns/rejects, four bundle manifests, 56
file/metadata pins, both installed write regions and all eight protected
ranges. The full surrounding proper/environment regions match, both GPT
copies validate, environment CRC is valid and both copies remain identical.
Filesystem reports clean without recorded errors or new ext4/panic messages.

Initial signal was `none`; after return HDMI locked at 1280×720, with video
active. Chris reported: “It booted normally and then showed the host's desktop.”
This confirms display return in this run; it is not continuous-client,
movie/frame-rate/colour/audio acceptance. No host test player/source settings,
service recovery, `saveenv`, reflash or extra reset was used.

[Combined verdict](RUN-RESULT.json), [UART proof](UART-RUN-RESULT.json),
[excerpt](uart-warm-excerpt.txt), [post-boot storage/health](POST-LINUX.json),
[automatic startup check](POST-STARTUP.json).

The sole passive recorder remained active through the sequence with no
recorded disconnect/OPEN failure. After the checks completed, the host user
service was explicitly stopped; CAPTURE STOP and UART release were verified.
[Clean-stop receipt](RECORDER-STOP.json). No UART transmission occurred.
Board left powered on, healthy with desktop visible; no further action was
issued. Raw UART, storage snapshots, single-use request archive, source and
checksums remain under `local/recovery/2026-10-31-uboot-warm-validation/`.
No commit or push. Repeated/wider lifecycle, audio, save-path and hardware
rollback qualification remain separate.

## Earlier preparation endpoint

**Fresh passive recorder armed; read-only preflight PASS. No reboot issued.**
Chris requested a fresh reader and warm-validation preparation with the board
still powered on. The current no-source boot is
`85768624-6a6e-4637-a50f-f45b2c156f31`. Both installed write regions, all eight
protected ranges and 56 file/metadata pins match. Startup check passes, GP6 is
HDOK/GP7 zero, session ready, filesystem clean, and restart/xrun/reject counts
are zero. No cold-only diagnostic module is loaded. Preparation made no board
write, serial transmission, service change or reset/reboot.

The sole passive 115200-baud `/dev/ttyUSB0` reader is now supervised by host
user service `h713-uboot-warm-uart-20261031-01.service`, independent of tool
process lifetime. It does not auto-restart if the process fails; the recorder
itself logs/reconnects a lost UART. Logs and service receipt are durable under
`local/recovery/2026-10-31-uboot-warm-validation/`. Recheck the service MainPID,
host-visible UART ownership and fresh OPEN before any timed action.

[Arming receipt](ARMED.json), [preflight](PREFLIGHT.json), [test plan](PLAN.json).

## Proposed one-reboot sequence

1. Wait for the operator's ready. Confirm the same healthy pre-boot ID and
   fresh sole reader; record the raw UART byte offset as the test boundary.
2. Issue one detached ordinary `sync` and `systemctl reboot`. No SysRq,
   GP6/GP7 arming, U-Boot interruption, RAM script, environment save or service
   intervention. Do not stop at the prompt; allow installed unattended startup.
3. Capture shutdown, one new SPL/proper sequence, the expected build and
   `Reading from MMC(1) at 0x93d80000... OK`, shared handoff and Linux return.
   Confirm this was a warm reset, not the shutdown guard converting it to
   poweroff. Do not retry if the guard stops the sequence.
4. Read-only checks after return must show a different stable boot ID, ready
   current-boot session/handoff, automatic HDOK/GP7 zero, healthy DSP/startup,
   no service recovery or new errors, preserved manifests/files/calibration,
   both installed regions and all protected bytes intact.

Observe for up to three minutes and distinguish host Wi-Fi reconnection from
board boot failure using UART. On failure, preserve evidence and stop; no
blind reset, automatic retry, latch write, service restart or reflash. Leave
the board in the observed state pending review. With current signal `none`,
this qualifies no-source warm boot/environment recovery; picture/audio and
save-path qualification remain separate. No cold cycle is required for this
ordinary warm test, and no power-on or unplug action is requested now.

## Correction to the first-boot recorder status

The earlier PID lookup used the restricted tool process namespace and could
not see host PID 10696. A subsequent host-level check found that **the original
reader was still alive and was the sole UART owner**. Its argv and open log
descriptors matched the arming receipt. It was deliberately SIGTERM-stopped
before the fresh reader started; `CAPTURE STOP` and UART release were verified.
There was no simultaneous second reader and no reason to infer a recording
failure. The first-boot environment-load proof is unchanged.

[Host ownership and clean-stop evidence](prior-recorder-correction.json).
The old raw log hash is unchanged. Its timestamped file now includes the
graceful stop; the original archive preserves the earlier pre-stop snapshot.
First-boot current records explicitly correct the earlier interpretation;
older archived snapshots remain historical. No source commit or push.
