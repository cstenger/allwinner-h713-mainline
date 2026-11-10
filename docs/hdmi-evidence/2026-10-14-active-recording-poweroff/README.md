# Full poweroff with active HDMI recording, 2026-10-14

## Latest: hangup-resilient relay passed the strict poweroff check

`reopen-boot/` and `attempt3/` record the successful rerun. A settled sample
verified real48kHz stereo HDMI tones. The UART request marker proves the
owned recorder was RUNNING at the exact normal poweroff request. Serial then
captured consumer stop, signal helper restoration/removal and stop, backend
stop beginning, the structured22 DSP/15 TVFE restoration result with
receiver_removed=true/phase=parked, backend successful stop and Power down.
The unchanged strict checker passed all ordered stages and observed90.03seconds
without reboot. See `summary.json` and `attempt3/result.json`.

The relay now stops before serial-getty and after the backend, and uses a
non-controlling UART writer that reopens on EIO/ENXIO and ignores SIGHUP.
Two native writer tests pass. The exact used source snapshot/hashes are under
attempt3/tested-sources and attempt3/tested-files.json. Target unit verification
passed before the test. Serial capture closed and the owned source player
finished/was cleaned up. No driver, firmware or persistent configuration was
changed. The operator confirmed both lamp and fan off and the board stayed off; that
confirmation is preserved in attempt3/operator-confirmation.json. The board
remains off.

Before this rerun, the persistent journal from attempt2 was retrieved. It
shows serial-getty stopped at64.393196s and relay exited1 at64.747119s, consistent
with console hangup; target getty uses TTYVHangup=yes. It also independently
confirms the complete recorder→signal→backend stop order and verified parking
in that previous run. See attempt2/persistent-journal-diagnostic.log and its
persistent-journal-assessment.json. Original strict failure results remain
unchanged. The following sections are historical attempt records.


## Latest rerun: UART routing fixed; relay lifetime still failed

`corrected-boot/` and `attempt2/` preserve the next cold-boot rerun. Real stereo
HDMI tones and recorder PID953 RUNNING were verified. The explicit /dev/ttyS0
request marker and initial service journal entries reached UART. After the
poweroff request the journal stream ended, while kernel messages continued.
The strict checker again failed to capture consumer/backend stop journal order.
This is not a passing relay rerun; its failed result remains unchanged.

Kernel serial still recorded all22 DSP/15 TVFE restores, MIPS status0, EDID
release and Power down. No reboot appeared for90seconds, and the operator
confirmed both lamp/fan off and board stayed off. Functional hardware outcome
and strict failure are separated in attempt2/assessment.json. The used sources
are preserved in attempt2/tested-sources and its tested-files.json.

The suspected remaining cause is console hangup during serial-getty teardown;
that has not yet been confirmed from the target's persistent journal. The
next candidate orders the relay to stop before serial-getty and uses a Python
UART writer that reopens after EIO/ENXIO, ignores SIGHUP and bounds retries to
five seconds. Two native controls pass for simulated hangup/partial writes and
missing-UART timeout (native-relay-tests.log). Candidate hashes are recorded in
relay-reopen-candidate-files.json. Hardware validation remains pending; a new
physical cold boot is required. The board is currently off. No automatic retry
or firmware/DSP restart was attempted.

## Earlier display-console relay attempt


The hardware poweroff succeeded from a live HDMI recording. Actual48kHz
stereoS16_LE source hardware parameters and a settled capture sample verified
left1kHz/right2kHz tones before the request. The saved SSH output proves
arecord PID946 was still RUNNING at the exact normal systemctl poweroff
request, with hw_ptr307900/appl_ptr307836 and healthy graph state.

Serial captured bounded SCP restoration, DDC removal, all22 verified DSP graph
restores,15 TVFE clock words/bus restored, audio removal, all three MIPS reset
lines asserted/verified, exact MIPS status0, EDID clock/reset release, filesystem
unmount/sync and `reboot: Power down`. No reboot appeared for90.03seconds after
Power down. The operator confirmed both lamp and fan off and the board stayed
off. No force/reboot, warm firmware/DSP retry or persistent install occurred.
The board remains off; the serial descriptor was closed automatically.

## Strict checker failure and evidence assessment

`attempt1/result.json` preserves the automated checker's failure. Its expected
request marker, service stop journal lines and structured shutdown JSON did not
appear on the UART: the test relay and marker wrote to /dev/console, while the
boot command line ends in console=tty0 after console=ttyS0,115200. That selects
the display for /dev/console. Kernel printk still reached the serial UART.

The test was not repeated. `assessment.json` separately checks the saved SSH
request's RUNNING state, the real tone sample, all22 kernel restore readbacks,
the ordered kernel teardown markers, powerdown and the90-second observation.
This supports a passing functional active-recording poweroff result. Exact
consumer stop timestamps and the receiver module-unload journal message were
not captured. Consumer closure before audio removal is inferred from successful
guarded teardown and removal; the normal recorder limit was90seconds and would
not have expired before the observed audio teardown. The previous hardware
ordering test independently verified the consumer-before-backend journal order.

The used scripts are preserved exactly under attempt1/tested-sources, with
hashes in tested-files.json. Future relay/marker routing was corrected to the
explicit /dev/ttyS0; that correction is syntax-checked but has not been tested
on hardware. relay-fix.json records the distinction. Raw source/capture audio
remains local and ignored. No failure result was overwritten.

## Test ownership and shutdown ordering

The recorder, bounded signal helper and journal relay were runtime systemd
units. Recorder Requires/After signal/backend, and signal Requires/After backend,
order recorder closure and signal cleanup before managed audio teardown.
The signal owner asserted HPD using the established saved/restored SCP payload
for45seconds. Its ExecStop waited for initialization to complete and verified
restoration before removing SCP and DDC. This deliberately added a wait to the
poweroff transaction; no DDC hold was removed beneath initializing SCP.

The relay was ordered to outlive backend teardown and stop before journald.
Target systemd-analyze verify passed for all three test units. The actual
integrated backend drop-in and receiver driver were unchanged. Bluetooth HCI
shutdown timeouts appeared, as in the prior test, without preventing poweroff.
The SSH connection timed out after hotspot shutdown; its request-state JSON
was saved before the connection closed. Serial provides the later hardware
shutdown evidence.

## Records and limits

- boot/: guarded cold source3 boot and integrated service startup.
- attempt1/tone-analysis.json and host-hw-params.txt: actual HDMI tone proof.
- attempt1/ssh-poweroff.log: recorder RUNNING at the request, then link loss.
- attempt1/serial-poweroff.log: hardware restoration/parking/powerdown trace.
- attempt1/result.json: strict journal-based checker failure, retained.
- assessment.json: separate primary-evidence functional result and limits.
- operator-confirmation.json: physical lamp/fan/stayed-off confirmation.

This tests a single full OS poweroff transaction beginning with real HDMI
recording. It does not establish main-rail cutoff: this board's known PSCI
SYSTEM_OFF implementation halts CPUs while the existing hook switches lamp/fan
off. Persistent installation and suspend remain separate work. A physical cold
cycle is required before another managed firmware/DSP initialization.
