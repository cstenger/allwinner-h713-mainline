# HDMI audio capture handoff, 2026-10-08

Start here, then read [the updated plan](hdmi-audio-capture-plan.md),
[Android evidence](hdmi-evidence/2026-10-08-android-capture/README.md), and
[Linux direct-route evidence](hdmi-evidence/2026-10-08-linux-direct-capture/README.md).
Older October 7 notes are historical and contain superseded hypotheses.

## Latest: full OS poweroff from verified parked state passed

One normal `systemctl poweroff` completed from the previous validated terminal
state (boot f23247eb-1346-40ed-bc66-de720a4b7fb8, MIPS parked, audio/receiver
unloaded). Serial showed filesystem unmount/sync, display fetch quiesce and
`reboot: Power down`. A bounded serial watch observed no reboot for90 seconds.
The operator confirmed both lamp and fan off and the board stayed off.
See [poweroff evidence](hdmi-evidence/2026-10-14-full-poweroff/README.md).

The existing h713-off lamp/fan hook was used unchanged; no force, reboot,
GPIO experiment or persistent configuration change occurred. Serial capture
closed automatically. A Bluetooth HCI shutdown timeout appeared but did not
prevent poweroff. **Current board: OS off, lamp/fan off.** Physical cold cycle
is required before further firmware/DSP work. The SoC's known SYSTEM_OFF/main-
rail limitation remains: this validates OS halt and lamp/fan-off, not rail cut.
The combined live-recorder service stop passed earlier; poweroff from an active
HDMI recorder in the same single transaction has not been tested. Persistent
startup installation and suspend remain separate work.

## Latest: integrated automatic shutdown ordering passed on hardware

On a fresh parking-capable cold boot, the runtime capture service's combined
ExecStop passed with a real recording consumer(PID869). Stopping only the
backend caused systemd to stop its Requires/After consumer first, then verify
all22 DSP/15 TVFE restoration words, park MIPS and release/unload the receiver.
The journal verifies ordering and successful deactivation; no separate park
command was issued. Repeated combined shutdown was harmless.

Twenty-four Python guard tests and the target ordering fixture also pass.
See [shutdown evidence](hdmi-evidence/2026-10-14-shutdown-ordering/README.md).
Existing key/standby/hotspot and late lamp/fan poweroff hook configuration is
unchanged. This validates the service stop transaction, not a full-machine
poweroff/halt. Persistent installation and suspend remain unvalidated.

**Current board:** Linux responsive, MIPS parked/status0, module/bus MIPS gates
off, TVFE off and TVCAP still on under keep-tvcap-on. Audio/receiver/recording
and runtime units/drop-ins are removed. WirePlumber active, firmware path
restored; no signal helpers/listener. Physical cold cycle is required before
any new firmware/DSP initialization. No boot image/environment was modified.

## Latest: shutdown ordering implemented; fresh hardware transaction pending

Parking-capable cold boots now install a runtime-only ExecStop override for
`shutdown --terminal-shutdown`: verified audio restoration precedes parking
and receiver release. Capture consumers require/order after the backend; it
stops before the user manager and retains its bundle/state mounts until done.
Capture-only boots retain their original stop behavior. Existing key, standby,
hotspot and late lamp/fan poweroff hook configuration is unchanged.

Twenty-four Python guard tests pass. Target systemd unit verification and an
ordering fixture passed (consumer closes before backend, user manager active),
and the new shutdown CLI is harmless on the parked board. Runtime fixtures
were removed. See [shutdown evidence](hdmi-evidence/2026-10-14-shutdown-ordering/README.md).
Current board remains parked with audio/receiver unloaded. A physical cold
cycle is required before testing the combined ExecStop with a real ordered
recorder. Full system poweroff, persistent installation and suspend remain
unvalidated. No forced parking, warm initialization or GPIO action occurred.

## Latest: terminal MIPS parking and receiver release passed

The parking-capable cold coordinator, hardware live-client parking rejection,
three-rate capture (48/32/44.1kHz input, fixed48kHz output, zero XRUNs), full22
DSP/15 TVFE restoration and explicit terminal parking/owner removal passed.
All three CCU resets verified and MIPS hardware status reached0. MIPS clocks
are disabled, TVFE off and owner domain consumers removed. TVCAP stays on
under the existing keep-tvcap-on policy. Linux remained responsive.

An initial capture attempt saw no HDMI connection/ELD; reseating the cable
restored source detection and all passing captures used the same DSP load.
Twenty Python guard tests and the native policy matrix pass. Repeated stop
preserves the terminal latch; warm start/repeat park refuse without hardware
changes. See [parking evidence](hdmi-evidence/2026-10-14-parked-handoff/README.md).

**Current board:** Linux running, MIPS parked, audio/receiver modules and
runtime unit removed, no capture/player/signal helper/listener. WirePlumber
active and firmware path restored. A physical cold cycle is required before
any new firmware/DSP initialization. No persistent boot environment or image
was modified. System poweroff ordering, suspend, TVCAP power-off and persistent
startup integration remain unvalidated. Preserve existing IR/poweroff work.

## Latest: uninterrupted cold coordinator passed; parking candidate ready

The corrected coordinator completed cold parked MIPS to source3 to Linux to
runtime audio service without a guard stop or resume. Full22 DSP/15 TVFE
restoration, idempotent stop and warm-restart refusal passed afterward.
Current board audio is unloaded, runtime unit removed, receiver retained and
MIPS responsive. See [parking candidate evidence](hdmi-evidence/2026-10-14-parked-handoff/README.md).

New optional owner-locked terminal parking uses exclusive CCU reset handles
and MIPS clock holds from a volatile DT consumer. The exact-kernel W=1 build,
20 Python guard tests and native policy matrix pass; hardware parking is still
unvalidated. The target session requires persisted verified audio restoration
before parking. Next boot must use `--park-capable` to load the candidate owner
and its RAM consumer together. Do not upgrade the current live pinned owner.
A physical cold cycle is required. No persistent installation/poweroff/suspend
integration has been added, and no raw Linux reset writes were attempted.

## Latest: guarded runtime startup/stop passed (2026-10-14)

The new cold-U-Boot host coordinator stages a boot-ID-bound target session
and runtime-only systemd unit. Receiver/DSP/audio startup, healthy duplicate
start, busy-stop refusal, three-rate capture (48/32/44.1kHz input, fixed48kHz
output, zero XRUNs), full22-word DSP/15-word TVFE restoration, idempotent stop
and warm-restart refusal passed. Sixteen native guard tests passed.

The initial FDT guard exposed a hexadecimal-size assumption (`8319` means
0x8319 bytes). It stopped before Linux. After correcting the constant, a
verified source3 resume completed RAM boot without relaunching MIPS; this is
not an uninterrupted hardware run of the corrected cold coordinator.
See [lifecycle evidence](hdmi-evidence/2026-10-14-managed-lifecycle/README.md).

**Current board:** audio unloaded, receiver clients0/pinY/EDIDY/clocks4 and
both domains active; MIPS responsive, WirePlumber active, empty firmware path
restored. Runtime unit removed; no capture/player/transient helper/listener.
Physical cold boot is required for another managed audio initialization.
No persistent boot artifact/environment or service enablement was changed.

Actual MIPS parking, parked receiver release, system poweroff with consumers
and suspend remain unvalidated. Close capture clients before service stop.
Next: validate safe MIPS parking/receiver handoff before persistent startup
or integrating system shutdown. Preserve existing IR/suspend/poweroff work.

## Latest: repeated HPD recovery passed (2026-10-14)

Ten software HPD-loss recoveries after a baseline connection passed with one
capture PID1076, all eleven unique markers and tone windows, exact240-second
recording/11,520,000 stereo frames, zero overruns/new driver XRUNs, zero final
silence and clean helper restoration/removal on every window. No DSP reload
occurred between cycles. See [cycle evidence](hdmi-evidence/2026-10-14-hpd-cycles/README.md).
These are automated HPD transitions, distinct from repeated physical cable
endurance; a single physical unplug/replug passed earlier.

**Current board:** audio unloaded after all22 DSP graph words and15 TVFE clock
words/bus restored with verification; receiver clients0/pinY/EDIDY/clocks4,
init_error0, both domains active. MIPS responds, WirePlumber active, original
empty firmware path restored. No capture/player/transient helper/listener or
recovery remains. New managed audio initialization requires physical cold
boot to clear the volatile DSP patch. No boot artifact/environment was saved.

One-hour endurance and repeated-HPD tools/evidence are newer than commit
71dca46. Next driver integration work: automatic guarded source3 startup and
parked shutdown ownership; repeated physical cable endurance and suspend
remain unvalidated. Preserve existing IR/suspend/poweroff work.

## Latest: one-hour endurance passed (2026-10-14, after checkpoint71dca46)

One hour of48kHz stereoS16_LE input/output passed on the integrated driver:
120 unique timing markers and120 settled tone windows, exact172,800,000 frames
(691,200,000 raw bytes), zero overruns/new driver XRUNs, unchanged PID1402,
zero final silence and full helper restoration. Source-relative sample drift
was18.891ppm (~68ms/h), minimum correlation.99836 and maximum adjacent
interval change2.07 frames.119 board CLOCK_MONOTONIC_RAW samples separately
fit47,999.9983 frames/raw-second; this is not calibrated oscillator accuracy.
See [endurance evidence](hdmi-evidence/2026-10-14-audio-endurance/README.md).

**Current board:** audio unloaded, all22 DSP graph words and15 TVFE clock
words/bus restored with verification; receiver clients0/pinY/EDIDY/clocks4,
init_error0, both domains active. MIPS responds, WirePlumber active and original
empty firmware path restored. No capture, source player, transient helper,
serial listener or recovery remains. New managed audio initialization requires
physical cold boot to clear the volatile DSP patch.

The endurance test streams PCM to the host, uses bounded-memory source/analysis,
and has independent capture/HPD deadlines. Ordinary150-second HPD bounds and
10-second default remain; explicit `long_hold=1` allows at most3660 seconds
and host `--audio-endurance` excludes other diagnostic modes. New analysis/
runner/policy tests and plot/CSV are newer than commit71dca46. No persistent
boot or module installation changed. Next: repeated hotplug endurance and
source3 boot/parked shutdown integration; suspend remains unvalidated.

## Current recovery result (2026-10-14, after checkpoint8244151)

**Same-open recovery passed:** source48->32->44.1->48kHz changes used one
capture PID, fixed48kHz stereo output,8/8 fresh-signature windows, exact
48-second frame count and zero driver XRUNs. A separate physical HDMI1
unplug/replug was observed during a120-second capture: same PID/trigger while
unplugged and returned,17 initial tone windows followed by16 fresh swapped
windows, zero overruns/XRUNs and clean helper restoration. The first physical
operator window missed the action; the successful retry was observed and
confirmed. See [stream recovery evidence](hdmi-evidence/2026-10-14-stream-recovery/README.md).

**Current board:** audio unloaded after all22 DSP graph words and15 TVFE clock
words/bus restored with verification. Receiver clients0, pinY, EDIDY, clocks4,
init_error0, both domains active. MIPS responds, WirePlumber active, original
empty firmware path restored. No capture, transient helper or listener remains.
The volatile DSP patch requires physical cold boot before a new managed audio
initialization. No recovery or operator action is pending.

Next: hours-long capture/measured drift and repeated hotplug endurance, then
source3 boot/shutdown integration; suspend remains unvalidated. These recovery
changes are newer than checkpoint8244151.

## Driver implementation update (2026-10-14)

Latest: **firmware-lifetime receiver ownership replaces all diagnostic
power/EDID/TVFE/DSP helpers.** The managed audio driver requires a readiness
reference from `h713-hdmi-receiver`, then prepares/restores TVFE and DSP itself.
All three input-rate recordings passed; audio removal restored22 DSP words and
15 TVFE clock words/bus, dropped clients1->0, and left both receiver domains,
four clocks and EDID active with responsive MIPS. See
[receiver-owner validation](hdmi-evidence/2026-10-14-receiver-owner/README.md).

Current receiver module SHA256:
`49258d661f70cd211944dd652f0932b0eed071ebff3a23a20f8db03a494a20af`.
Current audio module SHA256:
`633a8e7bda3244eafd3256030c0a182b3493a8a6da72ef98201e34e22981b778`.
Sources are in `modules/hdmi-receiver` and `modules/hdmi-audio`. See
[receiver instructions](../modules/hdmi-receiver/README.md) and
[audio instructions](../modules/hdmi-audio/README.md).

Current board: Linux and MIPS responsive, audio module unloaded and all graph/
audio/TVFE state restored. The new receiver owner remains loaded intentionally:
clients0, firmware_pinY, edid_readyY, clock_count4, init_error0, both domains
active. WirePlumber and the original empty firmware search path are restored.
All four legacy helpers are absent. No listener or recovery is pending.

Do not force receiver removal. Live-firmware release, module removal and clock
decreases were rejected before capture and after audio unload. The parked-only
release predicate is natively checked; actual parked power-down is unvalidated.
The owner never parks/resets MIPS and retains partial holds on startup failure.
The volatile DSP patch remains until physical cold boot; another audio load
requires fresh0/0 DSP versions. Never reload to bypass a DSP timeout.

For the next trial, physically cold boot/manual U-Boot stop, single guarded
MIPS launch/source3, preserved FIT and RAM-only IRQ correction as before. Stage
the receiver module and trace reader in board RAM, run
`prepare-source3.py --postboot-only --receiver-owner --trace-reader
/tmp/h713-linux-return/read-comm-trace.py`, then `load-managed-audio.py`.
The latter stages audio/firmware and verifies temporary search-path restoration.
Source3 automatic boot, parked shutdown, hours-long recording, physical hotplug,
open-stream rate changes and suspend remain pending. Two-minute recordings
are now validated in the sustained update below. No boot artifacts were
flashed, environment saved or modules installed persistently.

## Sustained validation passed (2026-10-14)

The integrated receiver/TVFE/DSP driver passed120-second recordings at48,32,
and44.1kHz input on one managed audio instance:165 sampled tone windows,
exact5,760,000-frame recordings, silence tails, no recorder overruns, zero new
driver XRUNs, clean PCM closure and transient-helper restoration. Audio unload
restored22 DSP graph words and15 TVFE clocks/bus, receiver clients0, both
domains active, MIPS responsive and WirePlumber restored. Current board remains
Linux with audio unloaded and the firmware-lifetime receiver owner active.
See [sustained evidence](hdmi-evidence/2026-10-14-sustained-capture/README.md).

Two harness problems were corrected and are recorded: a video-only EDID build
prevented audio enumeration; then an insufficient monitor deadline raced SCP
restoration after a successful recording. The isolated builder now accepts
validated `--edid` input, and cleanup requires completed SCP initialization and
successful removal before releasing DDC pins. Signal-monitor restoration
margin is60 seconds; helper hold maximum150 seconds, default10 unchanged.
The successful end-to-end sweep is `bench/capture-test3` in the evidence.

Use repository `tools/mips/read-comm-trace.py` with a sibling `mips-shell.py`
when staging the reader in `/tmp/h713-linux-return`; the historical PLL reader
has different trace opcodes and is rejected on this U-Boot. After receiver
preparation, stage `build/scp-sustained-audio/h713-scp-probe.ko` built with the
proven256-byte audio EDID; direct source-directory builds use video-only EDID.
See the audio README for exact build/capture commands. The sustained evidence
manifest covers the current test tools and tested modules. No DSP retry or
reinitialization occurred between the corrected test attempts.

Hours-long recording, sample-accurate drift, open-stream rate changes,
physical hotplug endurance, suspend, automatic source3 boot and parked
receiver teardown remain unvalidated. Any new managed audio initialization
requires a physical cold boot to clear the volatile DSP patch. No listener
or recovery is pending.

## Latest rate-sweep result (Codex, 2026-10-08)

The user requested testing the remaining advertised PCM rates before driver
work. The cold-boot rate sweep **48 ->32 ->44.1 ->48kHz passed**: each actual
host hardware rate was verified, and all12 tone-correlated private DMA rings
classified as48kHz capture. All four active-stream silence tails were zero;
channel RMS levels stayed within0.11% of the initial control. See
[rate-sweep evidence](hdmi-evidence/2026-10-08-audio-rate-test/attempt2/README.md)
and [the repeatable test](hdmi-audio-rate-test.md).

First ALSA driver scope: fixed48kHz stereoS16_LE capture; HDMI input at
32/44.1/48kHz is now tested. Native32/44.1kHz capture, other bit depths,
multichannel and compressed formats are not established. Long-term drift and
continuous-stream source format changes remain untested.

All22 original DSP graph words restored with readback. DSP/bridge/TVFE
diagnostics unloaded, peripheral state restored, MIPS responds. The remaining
volatile patch still requires physical cold boot before another DSP trial.
No serial listener remains (user requested manual U-Boot stop). An earlier
setup attempt failed at0012 completion-clear; its records remain beside the
successful attempt. No further DSP commands were issued after that timeout.

## Current state and authorization

The user authorized the Android comparison, return to preserved Linux, bounded
capture diagnostics with restoration, and this documentation commit. On the
latest message the board has been physically power-cycled and stopped at U-Boot.
That cold boot was subsequently used for a guarded first MIPS launch, source3,
and corrected RAM-DT Linux boot. The stock processing-graph comparison is now
complete and restored; board is currently at Linux, MIPS responsive. The new
volatile DSP patch remains until another physical cold boot. See the latest
result below before using the resume recipe.
Preserve Claude's IR/suspend/poweroff work and unrelated dirty files. Do not
reflash U-Boot, replace the kernel, save environment, or use a warm MIPS relaunch.
No ongoing serial keypress spam or capture process remains.

## What Android proved

- Foreground AudioRecord app with RECORD_AUDIO, MODIFY_AUDIO_SETTINGS and
  FOREGROUND_SERVICE permissions selected HDMI input id7/type9 and verified
  the routed device. Setting normal HAL parameter
  `audio_devices_out_active=AUDIO_A2DP` made stock HAL use Trident card4/device0.
  No Bluetooth pairing, root, direct DSP writes or system replacement needed.
- Captured 862080 stereo S16_LE frames at 48kHz (17.96s), 3448320 bytes.
  Left 1kHz, right 2kHz, expected-tone energy fractions .9999999416 and
  .9999998893. The signal is channel-separated, not generic nonzero noise.
  See a2dp-tone.pcm, a2dp-tone-analysis.json, a2dp-app-result.txt and HAL/state logs.
- The same app in AUDIO_SPEAKER mode actually captured codec card0 DC/noise,
  despite Android's HDMI device label. See tone-capture.pcm/tone-analysis.json.
  Device labels and nonzero data cannot be the capture success criterion.
- Proven capture: Trident RUNNING, period480 frames/buffer1920, bridge SPI115
  advanced 617->3327, AudIf SPI113 stayed zero. SPDI1 status and AudIf status
  stayed zero. Stock speaker playback was heard by the operator while codec
  RXCNT remained zero/FSTA100/ISTA0. Withdraw earlier zero-status/RXCNT gates.
- App released capture, restored AUDIO_SPEAKER with rc0 and query verification,
  both card0/card4 captures closed, temporary app uninstalled. Temporary
  /data/local/tmp/cap tools remain; no Android system files were replaced.

## Stock register and code results

Android baseline: SPDI1 ctl90000000/3000; AudioTop700/011a5e00;
ostream0 CONFIG2207, START4000, END4fff, BLOCK40, address-high0;
bridge global enable1/mask10, AudIf mask003007d2. Private Linux DMA must use
its own allocation: never copy stock physical40000. Zero SPDI/AudIf status is
compatible with this verified PCM baseline.

Stock snd_alsa_trid.ko SHA65a8bdbbe9463aff2ae462a27fce3de1862a8039c52a22df2553fb6cd78794f5.
audbrg_ostream_config bounds mode0..2, shifts mode by12, channels by8,
addresses and byte block size by4. Stock mode2 yields2207; previous3207 was
outside accepted mode range. `stock-ostream-config.asm` preserves instructions.
The initial Linux DT had bridge/AudIf IRQs swapped; source patch now fixes them
but installed FIT is still old. Probe guards against the wrong DT.

Offline execution of exact HAL SHA97c26ec48aefeb3f0f77d443b0c41e6ef198de921aa63ad578133517d0e6497f:
HDMI source1/A2DP sink3 selects Sound_Connect(0x8f); speaker sink1 selects0x89.
Sound_Connect entry and terminal effects/unmute are intercepted: branch intent,
not a fake fully initialized HAL or live DSP readback. Tool:
`tools/stock/decode-hdmi-capture-route.py`; output hal-route-selection.json.

Preset route8f uses processing graph (9600 input to8400, outputs9009/900a
and8f01/8d01 edges); routebd directly connects9600 to9500/DTVOUT1.
`routes-8f-bd.json` records exact edges and preset hash. Linked stock emulation
`tools/stock/decode-speaker-init.py --route 0x8f` records Sound_Path_Init,
Sound_Path_Connect and four input API calls in capture-init-code.json.
Hardware/timing/read imports are explicit stubs: do not replay the990 emitted
initialization writes wholesale. `capture-graph-selected-words.json` folds
selected writes with known-bit masks for cold-state comparison:

| Word | Known mask | Stock code value (unknown bits shown zero) |
| --- | --- | --- |
| 0003 | 0f00 | 0300 |
| 0012 | a3ff | 8180 |
| 0017 | ff00 | 2000 |
| 004d | ffff | 696a |
| 0077 | ffff | 1617 |
| 00ac | ffff | 0000 |
| 0130 | ffff | 696a |
| 800c | 00f8 | 0080 |
| 800d | 00ff | 0000 |
| 801a | 0002 | 0000 |
| 8059 | 00ff | 007c |
| 805a | 00ff | 007d |

DTVOUT1=696a is stock initialization code intent, not measured Android selector.
Direct bd=1617 differs. Input API evidence: interface9600 enable bit15,
format01800000 ->0012 mask23ff value0180, prescale32 ->0017 maskff00 value2000,
DTV channel0 ->801a bit1 clear. Runtime Android HAL also logs prescale0.334966;
the fixed init prescale is not necessarily its final runtime gain.

## Return and preserved boot artifacts

FEL return used existing 64KiB build/out/h713-restore-spl.bin, SHA
02147d8e5edb6a2810e67066d1986f5663cdb73e35d51dd30c4ebe550e349276.
Exact current32KiB SPL is embedded at28732. Whole restoration program and SPL
are different files. Restore program hangs by design after writing; do not infer
completion solely from that hang. After physical cold boot read-only UDisks2
OpenForBackup verified actual installed bytes against saved files:

| Artifact | Location/size | SHA256 |
| --- | --- | --- |
| Linux SPL | LBA16,32768 | cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec |
| Linux U-Boot proper | LBA4828160,920576 | c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7 |
| Vendor boot0 | LBA256,32768 | b769a41514fe784ead77ff59738a88c97588784a5d425f879c84cfd84a39a817 |
| Installed kernel FIT | h713-kernel.fit | a298eeb8c131aa045c94279c2e89de73dcec3091173fff8d4fa0d25e948d399b |

Backups and fel-return-verified.json are in Android evidence. The installed
FIT copy is locally retained as installed-linux-kernel-before.fit (ignored
build artifact); same bytes as build/out/h713-kernel.fit. Linux kernel is
6.18.38 #1 SMP Wed Oct7 18:57:16 PDT2026. Both OS partitions, kernel and
persistent environment preserved. Vendor boot0 switch affected only LBA16;
exact SPL restored afterward. No need to switch to Android again just to
re-establish the successful baseline.

## Linux trial already completed and restored

Cold version0/0 -> fixed stock724-pair volatile patch ->version1/1 succeeded.
Correct ownership is peer05001530, own05001534; claim55, recheckpeer, releaseaa,
10ms bounds, no peer writes. tools/hdmi/test-dsp-lock.py passes contention,
racing peer, timeouts, stale claim/latches and1000 cycles. Never reset the module
failure latch by reloading after hardware timeout: physically cold boot.

Direct bd trial saved/readback five words: 0130 0000->1617,0012 0000->8180,
0017 2000 unchanged,801a0000 unchanged,8017 0001->0000. Initial prescale was
already32; its omission from old probe did not mean hardware gain was zero.
Bridge CONFIG2207/private64KiB DMA at76c60000; host10s stereo tone succeeded,
receiver video state5/1280x720. Four DMA buffers entirely0xa5, bridge IRQ0.
Cached N6144/CTS74250 but cached rate/APLL history0; ARM DRAM cache incoherency
makes zeros inconclusive. Before-tone cache snapshot was during acquisition.
This does not isolate route vs receiver readiness vs other initialization.

All five route words restored reverse order with readback, bridge/SPDI/AudioTop
and TVFE trial state restored, diagnostics unloaded, MIPS help win responded.
Only base receiver-power/EDID holds remained. User's latest physical cold boot
cleared the earlier volatile patch and runtime holds before the subsequent
stock-graph comparison described below.

## Latest stock-graph comparison (after the initial handoff commit)

Android handoff/evidence was committed first as b27e345. Then the requested
Linux test used a new fixed `stock_graph` parameter in the optional DSP build,
saving13 exact decoded logical words, preserving unknown bits, verifying every
write, and reverse-restoring them. Source file/parameter remains mutually
exclusive with capture_route/dtvout_second. Exact masks and cold saved values
are recorded in [stock graph evidence](hdmi-evidence/2026-10-08-linux-stock-graph/README.md).

Result: all four64KiB snapshots became entirely zero (instead of sentinel),
and bridge IRQ samples advanced3029->3587->4124->4684. Playback/signal helper
both returned0, receiver video1280x720. This is concrete transport progress
relative to directbd, but zero PCM is not HDMI capture success. Cached N/CTS
were6144/74250; rate/APLL history remained0, inconclusive due to cache coherence.
The graph subset omitted other stock initialization/effects/gain controls.

All13 original words restored with readback; DSP, bridge and TVFE trial modules
unloaded, peripherals restored, MIPS help win responds. Current board: Linux,
base receiver-power/EDID holds remain, volatile DSP patch still present. Before
any new DSP experiment, physically cold boot and stop at U-Boot again. The RAM
IRQ correction disappears on that boot; reapply before bridge trial.

Next offline comparison should trace controls feeding8400/8f01/8d01 and
9009/900a outputs, and distinguish missing processing setup from receiver audio
readiness using positive evidence. Do not repeat directbd or the unchanged
13-word graph subset without a new discriminator. No PLL reflash/word writes.

## RESULT (Claude, 2026-10-08): Linux captures HDMI audio

Attempt 2 of the 22-word `graph_chain` trial put the host's L 1 kHz / R 2 kHz
tone into the private bridge DMA buffer: 97-99 % of each channel's energy in
its own tone, crosstalk ~1e-5, and a level that matches stock. Cold values
show two breaks in the 13-word trial: 8500 -> 8f01 was unwired and its mixer
gains were 0, and 9009/900a were user-muted (0059/005a = 8000). All restored;
board at Linux with diagnostics unloaded. See
[the capture evidence](hdmi-evidence/2026-10-08-linux-graph-chain/attempt2/README.md).
Next: turn the probe sequence into a real ALSA capture driver.

## Offline follow-up (Claude, 2026-10-08): the missing chain

The zero PCM has a concrete code-level explanation. Stock route 8f carries HDMI
as 9600 -> 8400 -> 8500 -> 8f01 in2/3 -> 9009/900a -> DTVOUT1. The 13-word
trial never wired 8400 -> 8500 -> 8f01 (007c/007d/007e, 8102/8103) and never
set the 8f01 input-2/3 mixer gains (0102/0103). Stock init also leaves 9009/900a
user-muted (0059/005a bit 15), which only the HAL's runtime unmute clears. See
[graph-chain evidence](hdmi-evidence/2026-10-08-graph-chain-offline/README.md).
The probe now has load-time `graph_chain=1` (22 words). It is built and its
table is checked, but it has not been run. Next trial = the stock-graph recipe
with `graph_chain=1`, after a physical cold boot. Only this one parameter
differs from the recorded trial.

Attempt 1 (same day) aborted: the DSP probe's own 100-us completion-clear check
timed out reading back 0077. Stock allows 50 ms. The probe now keeps the clear
check but within stock's 50 ms budget (build 8b5c8e64...). See
[attempt 1](hdmi-evidence/2026-10-08-linux-graph-chain/README.md). The board is at
Linux, diagnostics unloaded, partial DSP graph present. Cold boot before retrying.
Host /tmp is not durable: rebuild TVFE/bridge modules (they reproduce bit-exact).

## Resume recipe and next test

1. Verify current U-Boot prompt over tools/serial/console.py auto (Allwinner CDC
   ACM lookup); do not start a continuous keypress monitor. First cold MIPS
   launch: `h713_disp mips-comm-trace 0x34`. Verify firmware/canaries/readiness.
   Query `h713_disp commtrace`, obtain current channel0 pid, then guarded
   `h713_disp commcall eaf13de5 chan=0 pid=<CURRENT_PID> 3`. Never reuse old pid
   8b8f275c without confirming it. Require source3 worker completion.
2. Load preserved FIT and change only copied RAM DT before boot:

   ```
   fatload mmc 1:2 0x50000000 h713-kernel.fit
   fdt addr 0x50000000
   fdt get addr hdmi_trial_fdt /images/fdt-1 data
   cp.b ${hdmi_trial_fdt} 0x4f000000 0x8319
   fdt addr 0x4f000000
   fdt resize 0x1000
   fdt set /soc/audio-bridge@203042c interrupts <0 115 4 0 113 4>
   bootm 0x50000000 - 0x4f000000
   ```

   Check current embedded DT size8319 before copying if FIT changed.
3. SSH root@192.168.4.1; host WLAN spirits profile may need reconnect. Stage
   matching tools/mips/read-comm-trace.py under/tmp/h713-linux-return. Original
   root reader expects a different temporary audio-dispatch patch. Current
   U-Boot normal jump at4b12052c is0ec40190, not0ec54252. Do not weaken guard;
   `prepare-source3.py --postboot-only --trace-reader <matching staged path>`.
4. Exact kernel build is build/linux-6.18.38-2a2ced73e505c450215680f0427646c1e7d6432ee82a314344022264b082af23.
   Prior known modules: /tmp/h713-capture-tvfe, /tmp/h713-stock-lock-dsp,
   /tmp/h713-stock-irq-bridge. TVFE source is in the other checkout
   /home/chris/.codex/worktrees/hdmi-capture-current/h713/modules/hdmi-tvfe-hold.
   Build optional DSP patch with tools/hdmi/build-dsp-probe.py and exact
   audio-dsp-patch.bin (2896bytes, SHA8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5).
5. Cold post-patch selected graph values have now been recorded by stock_graph;
   most are0, input prescale2000 and mute0001. Existing dsp_word allowlist is
   small; extend only exact reviewed logical words with bounded reads. The
   fixed13-word stock_graph trial now exists and yielded only zero PCM; choose
   a new decoded prerequisite/discriminator before another trial.
   Receiver positive audio readiness must also be assessed; zero cache/status
   is inconclusive. Do not add PLL writes/reflash to force an assumed prerequisite.
6. Bridge arguments from passed trial: armed=1 live_source3=1 receiver_powered=1
   init_audio_top=1 stock_audio_ihb=1 open_spdi1=1 activate_spdi1=1
   configure_audbrg=1 audbrg_stage=4 snapshot=1. DSP load additionally needs
   audio_ready=1 lock_window_ready=1. stock_patch is sysfs-only one shot.
   `/sys/devices/h713-hdmi-audbrg-dma/capture` exposes only private coherent
   DMA, read-only; raw snapshots may cross ring wrap. Require expected tone
   correlation, not bytes/IRQs alone. Existing run-trial.py is an executed
   snapshot of direct trial, not automatically the next graph trial.
7. Restore DSP route before removing audio/TVFE holds. Then unload DSP, bridge,
   TVFE trial modules, verify MIPS, gather restoration evidence; physical cold
   boot clears patch. Record every new outcome here or in a new evidence README.

Safety stop list remains: no ARM0694xxxx/07091000/undocumented receiver reads;
no live MIPS relaunch; no PLL reflash/word writes; no Speaker Switch0 or PB5 low;
no copying Android fixed DMA addresses; no repeated DSP commands after timeout.
Unrelated docs/reference/vp9-scaler-2026-10-06.md and compile objects are outside
this documentation/evidence commit.
