# Driver-managed DSP capture, 2026-10-13

**PASS: automatic DSP setup, three-rate ALSA capture, same-open XRUN recovery,
and automatic22-word graph restoration on driver removal.** See
[summary](summary.json) and [build manifest](build-manifest.json).

`h713-hdmi-audio.ko` is now composite: `h713-hdmi-pcm.c` retains the proven PCM
implementation; `h713-hdmi-dsp.c` handles firmware and graph ownership.
`manage_dsp` defaults true. Receiver/source3 initialization and TVFE/power/EDID
holds remain explicit prerequisites; no persistent boot integration was added.

## Implementation

Before audio clock changes, the driver reserves the DSP command and real stock
ownership windows. The updated diagnostic helper also reserves them, preventing
coexistence. After audio clock setup the driver requests
`h713/hdmi-audio-dsp.bin`, requires2896 bytes and pinned SHA256
8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5,
then requires cold versions0/0. It verifies stock masked initialization, writes
the724-pair volatile patch, requires versions1/1, saves all22 graph words and
verifies the applied graph. Only then does it set `graph_ready` and register
ALSA. No proprietary patch bytes are embedded in source.

Reads use the validated stock completion protocol, with bounded waits and
real ownership. Any DSP command/readback failure latches `dsp_failed` and
prevents further DSP commands, including restoration after a failure.
Physical cold boot is required after a timeout or partial initialization.
No automatic timeout retry or failure-latch reset exists.

On removal, ALSA closes first; graph words restore in reverse order with
readback while audio clocks remain held. Then DSP resources and PCM/audio
peripheral state release. `manage_dsp=0` retains external-helper diagnostics;
managed mode rejects manual `graph_ready` writes.

## Measured checks

The initial integrated build SHA256
1e04f8fe43f42f3a0f691a5b00258783408edc8e56d39fbe59396e8d5eca0876 passed:

- Missing firmware and a2896-byte all-zero wrong-hash file rejected loading,
  without DSP requests. [Results](firmware-rejection.json).
- Automatic stock patch and22-word graph setup, `manage_dsp=Y`,
  `graph_ready=Y`, `dsp_failed=N`. [Load](load.log).
- Competing DSP helper rejected with EBUSY and manual readiness override
  rejected with EPERM. [Ownership](ownership.log).
- Separate16-second captures at actual HDMI inputs48/32/44.1kHz; each produced
  768,000 frames at48kHz stereoS16_LE. Tones, silence tail, closed/reopened PCM
  and process exits passed, with zero driver XRUNs. [Capture summary](capture-test/summary.json).
- Automatic22-word restoration and peripheral cleanup on unload, MIPS
  responsive. [Restoration](first-unload-restored.log).

WirePlumber held the ALSA control device after capture closed, so the first
ordinary removal correctly returned EBUSY. Its service was temporarily stopped
to release that control handle, then restarted on exit. No forced removal was
used. This is normal module-reference behavior, not a DSP restoration failure.

The patch survived removal. A subsequent load correctly refused versions1/1;
no patch overwrite or graph application occurred. The attempted recovery test
therefore stopped at preflight and never recorded. The user then physically
cold-cycled and manually stopped at U-Boot for final validation.

The final build SHA256
7d3a110acd25e6d58305e220a44e5ee6fd8d2fa4ed10557ab8e659c0681417eb adds earlier
DSP resource reservation, formatting and accurate readiness logging. A no-MMIO
resource-owner test proved that a conflicting reservation rejects initialization
before audio setup, with unchanged kernel log. Its source is retained as
[the standalone test module](../../../modules/hdmi-dsp-resource-test/h713-dsp-resource-owner-test.c).
It preserves the original command-range reservation; build instructions and
offline checks are in the [helper guide](../../hdmi-capture-test-helpers.md).
[Historical result](early-resource-rejection.log); no new hardware test was
performed during the source move.

On the new guarded boot, the final build automatically initialized DSP from0/0,
verified1/1 and all22 graph words. A16-second capture at48kHz input deliberately
stalled its reader for one second: ALSA reached XRUN, recovered with the same
owner/open PCM, and passed the expected tone, exact frame count and silence
tail checks. [Final load](final-boot/load.log),
[recovery summary](final-boot/stalled-reader/summary.json).
Automatic restoration again verified all22 words, then peripherals and TVFE
restored and MIPS responded. [Final teardown](final-boot/unload-cleanup.log).

Exact-kernel LLVM W=1 builds passed. Native ring arithmetic and synthetic
capture/reconnect analysis checks passed. The shared stock-response helper
retains its native immediate/delayed-completion and bounded-timeout controls.

## Final state and limitations

DSP/ALSA/TVFE diagnostics are unloaded. Receiver power/EDID holds remain;
all graph words/peripherals are restored, MIPS responds, and WirePlumber is
active again. The temporary firmware search path is verified restored to its
original empty value. An early test script wrote zero bytes when restoring an
empty value, which left the path set; the final cleanup corrected it by writing
a newline and verifying emptiness. No persistent configuration was changed.
See [path verification](final-boot/firmware-path-restored.log) and
[service verification](final-boot/service-restored.log).

The volatile DSP patch remains until physical cold boot. Another managed load
requires fresh versions0/0; it intentionally refuses already-patched DSP state.
No serial listener ran, no boot artifacts were flashed and no U-Boot environment
was saved. Firmware, modules and recorder were staged in board RAM only.

Automatic receiver boot/TVFE ownership, long-term capture, repeated physical
hotplug, open-stream source-rate changes and suspend remain future work.
