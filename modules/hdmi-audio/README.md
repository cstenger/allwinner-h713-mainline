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

## Open-stream recovery tests

Both source-rate transitions and physical unplug/replug passed with unchanged
capture ownership, fresh returned audio and zero driver XRUNs. Full DSP/TVFE
teardown then passed. This establishes one cable cycle; repeated endurance
remains untested.

`run-alsa-rate-transition-test.py` holds one70-second HPD window and one
48-second fixed48kHz capture while host playback changes48->32->44.1->48kHz.
It verifies actual host hardware rates, unchanged capture owner/format and
RUNNING state between phases. Alternating channel signatures and capture
pointer-indexed recording windows require fresh audio after each transition;
the final silence tail, exact frame count, no overruns, zero new driver XRUNs
and helper cleanup are also required.

`run-alsa-physical-reconnect-test.py` holds HPD for one150-second window and
records120 seconds. After the first tone, stdout requests physical unplug,
then reconnect. Unplug has a70-second deadline and return has20 seconds. The operator should
unplug HDMI for about5 seconds and reconnect, leaving board power/USB intact.
The runner observes source connector loss, requires the same capture PID to
stay RUNNING while unplugged, and verifies fresh swapped-channel audio after
return. A deadline failure retains evidence and waits for bounded restoration.
These tests use the already initialized driver; neither loads modules nor
issues DSP commands. Results and current validation status belong in the
[stream recovery evidence](../../docs/hdmi-evidence/2026-10-14-stream-recovery/README.md).

```sh
python3 tools/hdmi/run-alsa-rate-transition-test.py /tmp/h713-rate-transitions \
  --recorder /tmp/h713-linux-return/arecord
python3 tools/hdmi/run-alsa-physical-reconnect-test.py /tmp/h713-physical-return \
  --recorder /tmp/h713-linux-return/arecord
python3 tools/hdmi/test-alsa-rate-transition-analysis.py
```

## Endurance and drift test (one hour validated)

One hour at48kHz input/output passed:120 markers and tone windows, exact
172,800,000 stereo frames, zero driver XRUNs and full DSP/TVFE teardown.
Measured source-relative sample drift was18.89ppm.

`run-alsa-endurance-test.py` streams raw PCM to the host rather than storing
hours of audio in board RAM. It generates unique markers every30 seconds,
fits their source/capture sample positions for relative drift, checks settled
channel tones after every marker, and separately samples capture cadence
against board CLOCK_MONOTONIC_RAW. Native controls verify known drift and
reject replayed/missing/displaced markers. See
[endurance evidence](../../docs/hdmi-evidence/2026-10-14-audio-endurance/README.md)
for acceptance limits and current status.

Build/stage the updated SCP helper with the canonical audio EDID after
receiver preparation. Its150-second ordinary limit remains; only explicit
`long_hold=1` enables the3660-second maximum. The runner selects this opt-in
through `run-detection-trial.py --audio-endurance`; other diagnostic options
are excluded in that mode.

```sh
python3 tools/hdmi/run-alsa-endurance-test.py /tmp/h713-endurance-qualification \
  --recorder /tmp/h713-linux-return/arecord --seconds 90
python3 tools/hdmi/run-alsa-endurance-test.py /tmp/h713-endurance-hour \
  --recorder /tmp/h713-linux-return/arecord --seconds 3600
python3 tools/hdmi/test-audio-endurance-analysis.py
```

A completed hour consumes about692MB capture plus690MB source on the host.
Do not reload DSP between qualification and endurance. Finish with audio
unload and full DSP/TVFE restoration checks, keeping the receiver owner active.

## Repeated HPD recovery (ten recoveries validated)

Ten recoveries passed on one capture PID, with all eleven unique markers/
channel windows, zero XRUNs and full DSP/TVFE teardown.

`run-alsa-hpd-cycle-test.py --cycles 10` keeps one capture open across an initial
baseline window and ten subsequent source returns. Each saved/restored HPD
window is12 seconds, with3-second disconnected gaps. Actual source hardware
format, unchanged capture PID/RUNNING state during loss and return, advancing
capture pointer and healthy DSP state are required. Each return contains a
unique filtered-noise marker and alternating channel tones, so repeated or
cached prior-cycle audio is rejected. Capture streams directly to the host;
exact frame count, zero silence tail, no overruns/new driver XRUNs and all
helper cleanup checks are required. These are automated software HPD cycles;
physical cable endurance remains a separate test.

```sh
python3 tools/hdmi/run-alsa-hpd-cycle-test.py /tmp/h713-hpd-cycles \
  --recorder /tmp/h713-linux-return/arecord --cycles 10
python3 tools/hdmi/test-alsa-hpd-cycle-analysis.py
```

See [cycle evidence](../../docs/hdmi-evidence/2026-10-14-hpd-cycles/README.md)
for the current outcome. No DSP reload occurs between cycles.

## Guarded runtime service

`tools/hdmi/boot-managed-audio.py OUTPUT --cold-boot-confirmed` coordinates the
proven cold-U-Boot source3 launch, RAM-only FDT IRQ correction and Linux boot,
then stages the target session and a runtime-only systemd unit. It requires a
physical cold cycle with autoboot stopped. It never flashes or saves boot
environment. The existing FIT and matching modules must already be built.

The host binds its cold/source3 proof to the resulting Linux boot ID. The
session checks firmware size/hash, kernel/module ABI, source trace guards and
receiver ownership before loading managed audio. Healthy repeated starts are
read-only; stop or failed initialization latches out another initialization
on that boot. No retry may bypass a DSP timeout or this latch.

Close capture clients before `systemctl stop h713-hdmi-capture.service`.
Consumers should order themselves `After=h713-hdmi-capture.service` so they
stop first. Stop verifies all22 DSP graph words and15 TVFE clock words/bus,
restores the previous WirePlumber state and retains the live receiver owner.
Normal service stop retains firmware-owned power holds. The separate explicit
`h713-hdmi-session.py park --terminal-shutdown` handoff passed on a cold
`--park-capable` boot after verified audio stop. Actual system poweroff and
suspend integration remain unvalidated; the unit is staged
under `/run/systemd/system`, with no persistent enablement.

See [lifecycle evidence](../../docs/hdmi-evidence/2026-10-14-managed-lifecycle/README.md).

## Automatic shutdown ordering (hardware validated)

A parking-capable cold boot now stages `h713-hdmi-capture-shutdown.conf` as a
runtime drop-in. It replaces ExecStop with `shutdown --terminal-shutdown`,
which restores/verifies audio before terminal parking and receiver release.
This also makes a manual stop of that service terminal for the current boot;
its warm restart remains deliberately refused. Capture-only boots do not
install the drop-in and retain their receiver holds on stop.

Managed recorder services must specify both:

```ini
[Unit]
Requires=h713-hdmi-capture.service
After=h713-hdmi-capture.service
```

The consumer then closes first when the backend is stopped. The backend stops
before user@1000.service, preserving WirePlumber access during restoration;
explicit mount dependencies keep its /tmp bundle and /run state available.
Busy clients and restoration failures prevent parking. Failure is logged and
holds are retained; an ExecStop failure does not cancel the system shutdown.
The existing late lamp/fan poweroff hook is unchanged. Suspend is not wired
into this terminal operation.

Twenty-four native Python tests, a target systemd ordering fixture and a fresh
hardware transaction pass. Stopping only the backend closed a real recorder
first, then automatically restored22 DSP/15 TVFE words, parked MIPS and removed
the receiver. Repeated shutdown is harmless. Full-system poweroff, suspend and
persistent installation remain separate validation.
See [shutdown integration evidence](../../docs/hdmi-evidence/2026-10-14-shutdown-ordering/README.md).


Full OS poweroff subsequently passed from the verified parked/unloaded state:
normal systemctl poweroff reached `reboot: Power down`, no reboot appeared for
90seconds and the operator confirmed lamp/fan off. The original late poweroff
hook was unchanged. This is separate from a single poweroff transaction with
an actively recording consumer. Main-rail cutoff, persistent installation and
suspend remain outside the validated scope. See
[poweroff evidence](../../docs/hdmi-evidence/2026-10-14-full-poweroff/README.md).
