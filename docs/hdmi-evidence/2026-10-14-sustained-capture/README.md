# Sustained managed HDMI audio capture, 2026-10-14

**PASS:** two-minute recordings at48,32 and44.1kHz HDMI input, followed by
verified audio teardown. Output remains fixed48kHz stereoS16_LE. Each recording
has5,760,000 frames,55 sampled tone windows with left1kHz/right2kHz, a zero-filled
last second, no recorder overrun and zero new driver XRUNs. All playback,
recording and signal-helper processes exited0, each PCM closed, and transient
SCP/DDC helpers were removed. The same managed audio instance served all rates.

| Input rate | Recording | Tone windows | New driver XRUNs |
| --- | --- | --- | --- |
| 48kHz | 120 seconds | 55/55 pass | 0 |
| 32kHz | 120 seconds | 55/55 pass | 0 |
| 44.1kHz | 120 seconds | 55/55 pass | 0 |

[Successful sweep](bench/capture-test3/summary.json),
[teardown](bench/audio-unload.log), [complete summary](summary.json),
[build hashes](build-manifest.json).

## Setup and corrections

The user physically cold-cycled and stopped U-Boot. A single guarded MIPS
launch and verified live PID/source3 transition preceded the preserved FIT
boot, with audio IRQ115/113 corrected only in RAM. Receiver owner clocks and
EDID passed IPC checks. Managed TVFE/DSP initialized automatically and the
original empty firmware search path was restored. No persistent boot/module
installation or storage flash occurred; no serial listener was started.

The first staged trace reader was from a different historical experiment;
its missing local dependency and then opcode mismatch rejected preparation
before receiver setup. The matching repository `tools/mips/read-comm-trace.py`
was staged and passed all guards. No firmware relaunch or trace patch bypass
was used.

Attempt1 (`bench/capture-test`) used the source-directory video-only EDID
header. Audio ELD was absent, so no recorder/player started. The bounded HPD
trial restored cleanly. The isolated builder now accepts `--edid`, validates
both blocks, and preserves the exact previously proven256-byte audio EDID
(SHA256 edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34).
The extended helper SHA256 is
325e74d77bd6ddc9d3b0558add6011f68cc95e8d4aae15818338d67f494c92ae.
Its150-second maximum changes only the bounded hold ceiling; default10 seconds
and the save/restore payload remain unchanged.

Attempt2 (`bench/capture-test2`) recorded120 seconds at48kHz and passed all
signal checks, but the old signal-monitor deadline killed its SSH command
before the SCP module finished initialization/restoration. Ordinary removal
was refused; the old cleanup then released DDC pins prematurely. The module
subsequently reported peripheral/SRAM restoration and mismatch0. After
verifying those flags and live initialization state, it was removed normally;
MIPS responded, DSP failure remainedN, and driver XRUNs remained0. No DSP
reinitialization was attempted. See [recovery](bench/cleanup-recovered.log).

The monitor now allows60 seconds beyond the requested hold for scheduling and
restore, and cleanup fails closed unless SCP initialization has finished and
module removal succeeds **before** DDC ownership is released. Attempt3 passed
all three rates including helper cleanup. Earlier failed attempts are retained
rather than counted as successful end-to-end tests.

## Final state and limits

Audio unload restored all22 DSP graph words with readback, SPDI1/bridge/
AudioTop/IHB, and15 TVFE clock words plus bus/reset. Receiver clients returned
to0; firmware_pinY, edid_readyY, clock_count4, init_error0; both receiver domains
remain active and MIPS responds. WirePlumber is active. Audio and transient
helpers are absent. No background capture or listener remains.

The volatile DSP patch remains until physical cold boot; a new managed audio
initialization requires cold versions0/0. Do not force receiver removal or
reload to bypass a DSP timeout.

This establishes two-minute recording at each input rate, with sampled signal
continuity and same-instance close/reopen. It does not establish hours-long
endurance, sample-accurate clock drift, open-stream rate transitions, physical
hotplug endurance, suspend, automatic source3 boot or parked receiver teardown.

## Commit checkpoint

Text logs, analyses and summaries are versioned; raw WAV captures and built
modules remain local. The canonical test EDID is preserved as
`tools/hdmi/fixtures/hdmi-audio-edid.hex`, byte-identical to the EDID observed
in the successful run. The generator now also accepts this text form, so its
offline test and future helper builds do not depend on an ignored binary.
Those post-run packaging changes passed offline payload/analysis tests; the
build manifest above remains the snapshot of the hardware-tested run.
