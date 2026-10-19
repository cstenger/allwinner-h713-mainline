# Historical October 18 script snapshots

These are exact text copies of the one-session scripts used for the already
recorded trial. They are evidence, not current deployment/reset/test entry
points. Their original names, byte lengths and SHA-256 values are recorded in
[the support manifest](../support-files.json). Local backup copies are under
`build/panel-support-review/originals/`.

| Snapshot | Recorded role | Review finding |
| --- | --- | --- |
| `install.sh.txt` | Write the identity-pinned U-Boot proper trial, then check readback and surrounding regions | Fixed board paths, image identity and outgoing flash preimages; not a general installer |
| `abnormal-reset-trigger.py.txt` | Verify the expected boot/services/PCMs, sync, then request immediate SysRq-b reset | Boot/PCM guards use Python assertions, which `-O` removes; not suitable as a reusable reset tool |
| `test-audio.py.txt` | Stop the speaker, run persistent-owner digital capture tests, then restore the speaker | Its unconditional `finally` can start the speaker even when the initial boot-ID precheck fails; recorder path and output location are session-specific |
| `test-video.py.txt` | Play the known host pattern and sample eight DRAM frames | Assumes a staged remote reader and local media; uses assertions and the process working directory for helper discovery; has no independent current-session preflight |
| `serial-capture.py.txt` | Reconnecting passive UART recorder used to collect the trial | Hard-coded output/device; output I/O errors could be mistaken for UART disconnects |

The useful passive recorder is now
[capture-panel-validation.py](../../../../tools/serial/capture-panel-validation.py).
It requires an explicit device and new output directory, exits on output
failures and reconnects after UART loss. Example from the repository root:

```sh
python3 tools/serial/capture-panel-validation.py \
  --port /dev/ttyUSB0 --output build/panel-serial-NEW
```

Ensure it is the only UART reader. It sets 115200-baud raw receive mode, never
sends serial data, and records both raw bytes and UTC host timestamps. It
stops on SIGINT/SIGTERM. Raw UART/log-write error handling is tested offline:

```sh
python3 tools/serial/test-panel-capture.py
```

The current build/rollback instructions remain in the
[panel runbook](../../../uboot-panel-initial-state.md). Use the existing
[ALSA capture test](../../../../tools/hdmi/run-alsa-capture-test.py) documentation
for its own prerequisites. Archiving the session wrappers does not extend the
original hardware result or authorize running them against a different boot.
