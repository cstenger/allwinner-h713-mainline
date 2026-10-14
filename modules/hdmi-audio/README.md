# H713 ALSA HDMI capture

The audio driver manages TVFE clock/reset setup and DSP initialization/graph
restoration by default. A firmware-lifetime `h713-hdmi-receiver` owner supplies
power, receiver clocks and EDID; the audio driver acquires it before hardware
setup and releases its client after teardown. All diagnostic power/EDID/TVFE/DSP
helpers are replaced. Guarded source3 boot remains explicit.

Capture-only card `H713HDMI`, device0, produces fixed48kHz stereoS16_LE from
HDMI inputs32/44.1/48kHz. All three rates and automatic DSP/TVFE restoration
passed with the receiver owner. Audio unload released its client while the
owner kept firmware power and EDID active. See
[current validation](../../docs/hdmi-evidence/2026-10-14-receiver-owner/README.md).
Earlier managed-DSP tests also passed same-open stalled-reader recovery.

## Driver ownership and lifecycle

`h713-hdmi-pcm.c` owns SPDI1, bridge ostream0, interrupts, audio clocks and
persistent64KiB coherent DMA with1KiB periods (256 frames,64 periods).
`h713-hdmi-dsp.c` owns the DSP command and real stock ownership windows.
`h713-hdmi-tvfe.c` owns the stock-order TVFE clock/reset sequence, preserving
the live firmware-owned TVFE control word.
The composite module remains `h713-hdmi-audio.ko`. TVFE setup precedes audio
IHB/AudioTop setup; its15 saved functional clock words and bus/reset state are
restored and checked after the DSP/audio resources are released.
The updated diagnostic DSP helper also claims these windows, so a competing
helper and managed driver cannot load together.

Before registering ALSA, the managed driver requests firmware
`h713/hdmi-audio-dsp.bin`. It requires exactly2896 bytes and SHA256
`8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5`.
No proprietary patch table is embedded. Missing/wrong firmware rejects module
loading before any DSP request. Both DSP versions must be0; externally
initialized state is refused. The driver verifies stock masked initialization,
sends the pinned724-pair patch, requires versions1/1, saves all22 graph words,
applies the proven chain and verifies every write. Only then does it set
`graph_ready` and register the capture card. Manual changes to `graph_ready`
are rejected in managed mode.

DSP reads use the validated stock busy-clear/request/done-set protocol under
the real05001530/34 ownership lock, with50ms bounded waits and no invented
clear-edge requirement. Any DSP command/readback failure latches `dsp_failed`;
no automatic retry or DSP restoration after that failure is attempted.
**Physical cold boot is required after a DSP timeout or partial initialization.**
Do not unload/reload to bypass the latch. The volatile patch has no inverse.

Prepare clears the ring and pulses the stock producer flush. START enables
SPDI1/period IRQs; STOP disables input and masks IRQs. Close synchronizes IRQ
callbacks before detaching the runtime. Progress comes from the hardware
pointer, including wrapped/coalesced periods; invalid pointers or an entire
ring-duration IRQ gap cause XRUN. Normal consumer overruns use ALSA recovery.
Read access is supported; mmap, pause and resume are not advertised.

On unload, ALSA closes first. While audio clocks remain held, the driver
restores all22 DSP graph words in reverse order with readback, releases DSP
resources, then restores SPDI1/bridge/AudioTop/IHB and audio clocks. A restore
failure stops DSP traffic and reports cold boot required, while peripheral
cleanup still proceeds. `manage_tvfe=0` preserves external TVFE-hold mode.
The receiver owner remains pinned while firmware is live. Its parked-only
release interface requires hardware MIPS status0 and no audio clients. The
audio driver never powers the receiver off just because capture unloads.

## Build and offline checks

Use the exact installed kernel6.18.38 #1, Oct7 18:57:16PDT2026:

```sh
make -C build/linux-6.18.38-2a2ced73e505c450215680f0427646c1e7d6432ee82a314344022264b082af23 \
  M="$PWD/modules/hdmi-receiver" ARCH=arm64 LLVM=1 W=1 modules
make -C build/linux-6.18.38-2a2ced73e505c450215680f0427646c1e7d6432ee82a314344022264b082af23 \
  M="$PWD/modules/hdmi-audio" ARCH=arm64 LLVM=1 W=1 modules
cc -Wall -Wextra -Werror tools/hdmi/test-pcm-ring.c -o /tmp/h713-test-pcm-ring
/tmp/h713-test-pcm-ring
cc -Wall -Wextra -Werror tools/hdmi/test-dsp-stock-response.c -o /tmp/h713-test-dsp-stock
/tmp/h713-test-dsp-stock
python3 tools/hdmi/test-alsa-capture-analysis.py
python3 tools/hdmi/test-alsa-reconnect-analysis.py
python3 tools/hdmi/test-tvfe-lifecycle.py
```

## Bounded bench setup

1. Physically cold boot and manually stop at U-Boot. No listener is needed.
   Follow the [handoff](../../docs/handoff-2026-10-08-hdmi-audio-capture.md) for
   a single guarded MIPS launch, live PID/source3 worker verification and
   preserved FIT with RAM-only bridge/AudIf IRQ115/113 correction. Never warm
   relaunch MIPS, flash a boot artifact or save the environment for this test.
2. Verify Linux identity and stage `h713-hdmi-receiver.ko` plus the matching
   trace reader in board `/tmp/h713-linux-return`. Do not load the diagnostic
   power, EDID, TVFE or DSP helpers. On the host:

   ```sh
   python3 tools/hdmi/prepare-source3.py --postboot-only --receiver-owner \
     --trace-reader /tmp/h713-linux-return/read-comm-trace.py
   ```

   This verifies source3/canaries, loads the firmware-lifetime owner, enables
   receiver clocks one step at a time with MIPS IPC checks, and verifies EDID.
3. Run the host bench loader after building this driver:

   ```sh
   python3 tools/hdmi/load-managed-audio.py /tmp/h713-driver-load
   ```

   It stages this module and the pinned patch in board RAM, verifies base
   prerequisites, and loads with `armed=1 live_source3=1 receiver_powered=1`.
   It restores and verifies the original firmware search path in finally,
   including an originally empty value. Require automatic TVFE/patch/graph
   verification, `manage_tvfe=Y`, `manage_dsp=Y`, `graph_ready=Y`, `dsp_failed=N`
   and the ALSA card. Do not write `graph_ready`. No proprietary patch is
   embedded; deployment needs the pinned file in the normal firmware directory.
4. Run the host acceptance test:

   ```sh
   python3 tools/hdmi/run-alsa-capture-test.py --recorder /tmp/h713-linux-return/arecord /tmp/h713-managed-capture
   ```

   It verifies actual hardware input rates, three separate16-second captures,
   768,000 frames each, expected stereo tones, zero silence tails, successful
   exits and closed/reopened capture. `--stall-reader` instead tests one-second
   consumer stall, XRUN and recovery on the same open PCM. The reconnect
   runner also supports managed mode.
5. After all capture and control clients close, unload the driver. WirePlumber
   can retain a control handle even when capture is closed; temporarily stop
   and then restore its service if needed for this bounded unload test. Require all22 restore readbacks
   and the final restoration success log, then verify MIPS. The integrated TVFE restoration must verify all15 saved
   clock words and the bus. Require receiver clients0, firmware pinY, EDID readyY, four clocks and both
   domains active after audio removal. The receiver owner remains loaded.
   Preserve capture, firmware validation, resource ownership and cleanup logs.

`require_receiver_owner=0` explicitly permits the old diagnostic power/EDID
holds. `manage_dsp=0` preserves the older external-DSP-helper workflow for diagnostics.
Use `manage_tvfe=0` as well when the standalone TVFE hold is required.
That mode alone permits explicit `graph_ready` acknowledgment after externally
verifying the patch/graph. Restore the external graph before removing audio
clocks, as documented in the historical evidence. Use the updated helper;
older helper binaries did not reserve the DSP windows.

Source3 boot integration, parked receiver shutdown, long-term recording, repeated physical
hotplug, open-stream source-rate changes and suspend remain future work.

## Sustained capture test (validated on hardware)

The120-second sweep passed all three input rates,165 sampled tone windows,
zero driver XRUNs and full audio teardown. See
[sustained evidence](../../docs/hdmi-evidence/2026-10-14-sustained-capture/README.md).

`run-alsa-capture-test.py --seconds 120` records two minutes at each of the
three input rates. It checks channel-separated tones every two seconds across
the settled tone interval, exact output format/frame count, a zero-filled last
second, no recorder overrun, advancing driver counters and zero new driver
XRUNs. This samples signal continuity; it does not establish sample-accurate
clock drift. The original16-second sweep and stalled-reader test remain
available unchanged.

Build the extended helper with the proven audio EDID (the source-directory
header is a video-only diagnostic EDID and must not be used for audio):

```sh
python3 tools/hdmi/build-scp-probe.py \
  --kernel-build build/linux-6.18.38-2a2ced73e505c450215680f0427646c1e7d6432ee82a314344022264b082af23 \
  --edid tools/hdmi/fixtures/hdmi-audio-edid.hex \
  --output build/scp-sustained-audio
```

The builder uses `ARCH=arm64 LLVM=1 W=1`. The HPD helper now permits at most150 seconds;
its default10-second hold and save/restore sequence are unchanged. After
`prepare-source3.py` (which copies the older canonical diagnostic helper),
stage `build/scp-sustained-audio/h713-scp-probe.ko` to board
`/tmp/h713-scp-probe.ko`, without replacing the canonical copy on storage.
Then load managed audio and run on the host:

```sh
python3 tools/hdmi/run-alsa-capture-test.py /tmp/h713-sustained-capture \
  --recorder /tmp/h713-linux-return/arecord --seconds 120
```

Each remote recorder has an independent INT/KILL deadline. The signal monitor allows60 seconds beyond the requested hold for scheduling
and restoration. Cleanup requires the SCP module to have finished initialization
and removes it successfully before dropping DDC pin ownership. It then verifies
peripheral restoration and removes the transient helpers.
Finish with the established audio unload/restoration checks; keep the
firmware-lifetime receiver owner active. A fresh cold DSP boot is required
before managed audio initialization.
