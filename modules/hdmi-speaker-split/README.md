# HDMI speaker-split bench diagnostic

This opt-in diagnostic routes stock MSP DSP I2S output directly into the codec
DAC. It is separate from the normal ALSA HDMI capture and persistent speaker
consumer. It changes live DSP, internal-I2S and DAC-source state; it does not
install a kernel, start firmware or change the computer's default audio route.

Use it only on the prepared bench boot, after the operator authorizes the
audible trial. Stop the normal speaker/capture/signal services and exclude
other ARM DSP diagnostics before preparing this route. The stock DSP patch,
receiver, register-window power/clocks and bounded HPD trial prerequisites must
already be established. Loading requires both `armed=1` and
`lock_window_ready=1`; the latter acknowledges those power/ownership checks,
it does not perform them. Do not use it as a production audio service.

The module uses the shared stock DSP lock at `0x05001530/34`, saves seven DSP
words and nine internal-I2S registers, then applies route 0x89 and the stock
I2SIN1/I2SOUT1 settings. Internal I2S is changed only after all DSP writes and
readbacks succeed. Each command claims/releases the cross-processor lock;
the module mutex serializes its own sysfs/teardown operations. This lock does
not arbitrate independent ARM diagnostics.

Unload restores DAC-source bits and internal-I2S configuration, then restores
DSP words in reverse order while commands remain healthy. A lock/command or
readback failure stops further DSP commands. Inspect the kernel log and use a
physical cold restart before another DSP trial after failure; do not assume
unload restored the DSP in that case.

Build against the prepared kernel tree, for example:

```sh
make -C /absolute/path/to/kernel ARCH=arm64 LLVM=1 \
  M="$PWD/modules/hdmi-speaker-split" modules
```

Once the module is loaded and the prepared bench is ready:

```sh
python3 modules/hdmi-speaker-split/run-split-test.py \
  --output docs/hdmi-evidence/NEW-speaker-split-trial
```

The output directory must be new. The runner uses the helper scripts in this
checkout, SSH/SCP to `root@192.168.4.1`, target `pw-play` and
`/root/hdmi-safe-trace/read-mips-audio-cache.py`, plus host ALSA `aplay` and a
single matching valid `H713 HDMI IN` ELD. It also checks the canonical EDID and
receiver state 5 at 1280x720 before switching the DAC source. The host PCM
finder uses the HDA ELD grouping convention; other sound-card layouts require
separate verification. Board playback must remain alive while the DAC uses I2S.

Cleanup attempts each step even if another fails: stop the host tone, restore
the DAC source, stop only this run's uniquely named board playback, remove its
remote control WAV, and wait for the bounded HPD trial's own restore path.
It preserves receiver snapshots and `cleanup.json` on exceptions and reports
cleanup failures. An HPD wait timeout is a failure, not proof of restoration;
the child is left to finish its own bounded cleanup. The runner does not
unload the split module: inspect its restoration log when unloading afterward.

Historical [October 8 output-enabled evidence](../../docs/hdmi-evidence/2026-10-08-speaker-output-enabled/README.md)
records the control beep only, zero codec I2S receive counts, successful route
readbacks and verified restoration. It does not establish working DSP speaker
playback. The additional runner and failure-handling changes in this cleanup
have only been checked offline.

Local validation:

```sh
python3 modules/hdmi-speaker-split/test-split.py
python3 tools/hdmi/test-dsp-lock.py
```

The tests inject SSH/process/restore failures and exercise the actual DSP
wrapper/restore C functions with mocked hardware. ARM64 module compilation
also passes against the local Linux 6.18.38 tree (`W=1`); the host clang patch
version differs from that tree's original compiler (23.1.3 versus 23.1.1).
No new hardware or acoustic test was performed during this cleanup.
