# Native U-Boot save-path validation — November 2, 2026

**PASS.** Two native saves and two ordinary synced warm reboots prove the
installed U-Boot writes the corrected 64 KiB environment slot at LBA
`0x49ec00`, reloads the saved temporary marker, and removes it successfully.
The board is left running Linux with HDMI locked at 1280×720; UART is released.

## Results

- Probe: native `env save` reports `Writing to MMC(1)... OK`; Linux bytes have
  valid CRC and exactly the captured RAM semantics plus the unique marker.
- Cleanup: the second U-Boot entry loads the corrected slot with `OK` and
  observes the exact marker before deletion. One native cleanup save succeeds;
  Linux verification finds 72 entries and no marker.
- Both phases preserve startup guards, calibration, nine protected regions,
  all 59 installed file/metadata checks, and every captured byte outside the
  mutable slot (including its 64 KiB margins). The old environment in `super`
  is unchanged. All four installed bundle manifests pass.
- Final health: six original HDMI services and the re-advertise service are
  active without automatic restarts; video is running, with zero rejected
  frames and zero capture xruns. Normal startup checks pass after both phases.
- Accepted cleanup SHA-256:
  `89862e4ba5304fcae54affe09d87ff7da026316c80c8b4a5a17d7a44eb3ce206`.
  Whole-image UART CRC32: `151b22a3`. This is the new accepted environment,
  not a byte-identical restoration: only permitted `fdtcontroladdr` metadata
  differs semantically from the original.

## Qualification and controller correction

The first countdown interrupt reached the expected U-Boot prompt, but the
controller rejected its ANSI erase-line/repeated-label redraw. It stopped
before any environment edit or save. The already-authorized PB5 shared
lamp/fan line was set high and read back. The operator explicitly approved
continuing from that held prompt after review; no extra reboot or save retry
occurred. Offline replay validates the exact prior UART transcript and its
zero-save receipt before allowing the continuation.

The parser now retains partial countdown output and accepts only the known
erase-line/repeated-label sequence, while rejecting unrelated output and
other ANSI commands. The sealed packet supports the precisely pinned
52-file backend generation added by the November 2 HDMI fix; the additional
seven system unit checks bring the external count to 59. All other original
file pins and raw storage backups are retained. **49 controller tests pass,
including real synthetic PTY sessions; all 12 mutation checks are caught.**
Host Wi-Fi needed reconnection after the first reboot; this changed no board
service or startup state. Initial post-cleanup polling preceded service startup;
the later complete storage/startup/file capture passes all readiness gates.

## Evidence and limits

[Machine-readable result](RESULT.json), [test output](controller-tests.txt),
[mutation output](controller-mutations.txt), [probe UART excerpt](probe-continuation-uart-excerpt.txt),
[cleanup UART excerpt](cleanup-uart-excerpt.txt), and
[outside-slot comparison](outside-slot-comparison.json).

Private raw captures, full RAM maps, accepted environment bytes, exact packet,
recovery inputs, continuation script and source snapshots remain under
`local/recovery/2026-11-02-uboot-savepath/`, sealed by recursive SHA256SUMS.
Do not publish those private artifacts. Host time/boot IDs establish chronology;
the board's calendar is still unsynchronized. No independent post-cleanup
reload, hardware rollback, power-loss test, commit or push was performed.
