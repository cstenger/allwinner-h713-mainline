# HDMI audio capture handoff, 2026-10-08

Start here, then read [the updated plan](hdmi-audio-capture-plan.md),
[Android evidence](hdmi-evidence/2026-10-08-android-capture/README.md), and
[Linux direct-route evidence](hdmi-evidence/2026-10-08-linux-direct-capture/README.md).
Older October 7 notes are historical and contain superseded hypotheses.

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
