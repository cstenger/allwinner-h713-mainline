# Capture test helpers

These helpers support offline recording analysis and a narrowly scoped bench
resource-ownership test. The original sources lived under October 13 evidence
directories; reusable versions now live under `tools/` and `modules/`.

## Recording continuity screen

[check-continuity.py](../tools/hdmi/check-continuity.py) requires Python 3,
NumPy, explicit capture WAVs and a new JSON output path:

```sh
python3 tools/hdmi/check-continuity.py \
  --output build/continuity-review.json \
  docs/hdmi-evidence/2026-10-13-alsa-driver/attempt3/capture-test/1-48000/capture.wav \
  docs/hdmi-evidence/2026-10-13-alsa-driver/attempt3/capture-test/2-32000/capture.wav \
  docs/hdmi-evidence/2026-10-13-alsa-driver/attempt3/capture-test/3-44100/capture.wav
```

The ignored WAVs must be present locally. Files must contain at least nine
seconds of 48-kHz stereo S16_LE PCM, with the established left 1-kHz/right
2-kHz test stimulus settled during seconds 3–9. This is the capture rate;
the HDMI source may have been at a different rate before DSP resampling.

For each channel, the screen correlates 960-frame blocks with the expected
tone. It reports the largest residual block-to-block phase increment after
subtracting the median increment (radians), and minimum block amplitude
relative to median amplitude. Subtracting the median accommodates steady
clock drift. Input files are identified by full path so trials with the same
parent name do not overwrite each other in the report.

Exit zero means analysis completed, not that capture passed an acceptance
threshold. The screen neither verifies tone presence nor detects every
possible drop/repeat: a whole number of periodic tone cycles can be invisible.
It complements the tone, frame-count, silence-tail and driver-counter checks
in the [ALSA capture test](../tools/hdmi/run-alsa-capture-test.py); it is not a
long-term continuity proof.

No input files, malformed/short/truncated WAVs, unusable zero median amplitude,
duplicate inputs and existing output files are errors. The tool preserves
inputs and existing reports. It uses explicit error checks under Python `-O`
and writes finite JSON only after all inputs have been analyzed. The original
[October 13 report](hdmi-evidence/2026-10-13-alsa-driver/attempt3/continuity-analysis.json)
remains a historical result; reanalysis writes to the selected new path.

Run the independent clean-tone, drift, phase-step, silence-gap and input/error
controls with:

```sh
python3 tools/hdmi/test-continuity.py
```

## DSP resource-owner module

[The test module](../modules/hdmi-dsp-resource-test/h713-dsp-resource-owner-test.c)
reserves the DSP command range `0x06144000–0x0614401b` through Linux's resource
registry. It never maps the range, accesses registers, changes clocks, issues
DSP commands, or reserves the separate DSP lock range. This preserves the
original `resource-owner-test.c` experiment's command-range collision.

An explicit, read-only `armed=1` parameter is required. Loading fails with
`EPERM` when unarmed or `EBUSY` when the range is already reserved; successful
unload releases the reservation. Registry ownership only excludes clients
that request the same resource; it cannot block raw MMIO access.

Build against the prepared matching ARM64 kernel tree:

```sh
make -C /absolute/path/to/kernel ARCH=arm64 LLVM=1 \
  M="$PWD/modules/hdmi-dsp-resource-test" W=1 modules
```

On an explicitly prepared bench board with other DSP owners unloaded, manual
loading would use `insmod h713-dsp-resource-owner-test.ko armed=1`; unload with
`rmmod h713_dsp_resource_owner_test` after the competing-driver rejection test.
The helper only provides the reservation: it does not automate loading the
audio driver or prepare hardware. The prior
[early resource-rejection result](hdmi-evidence/2026-10-13-managed-dsp/early-resource-rejection.log)
records the original hardware experiment. No new board load/rejection test
was performed during this source cleanup.

Run the actual module source against a fake native resource registry with:

```sh
python3 modules/hdmi-dsp-resource-test/test-resource-owner.py
```

That test checks the unarmed path, existing ownership, exact range reservation,
competing ownership while loaded, and release on successful unload. It provides
no MMIO API. It does not execute the production audio driver.

## Cleanup validation

Six continuity test cases and the native module test pass. Reanalysis of the
three retained local October 13 WAVs reproduces all six historical channel
metrics within `1e-12`. The standalone ARM64 module builds against Linux
6.18.38 with `W=1`; the host compiler reports only a patch-version difference
from that kernel's original compiler (clang 23.1.3 versus 23.1.1).
Raw captures remain local, and the original source copies are retained under
`build/capture-helper-review/originals/`. No hardware was accessed during
cleanup, and historical acceptance claims have not been expanded.
