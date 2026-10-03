# Audio underrun deadlock in mpv (2026-10-02)

**Status: FIXED in our mpv (`patches/mpv/0005`), hardware-validated
2026-10-02.**
- 0 freezes in 480 forced underruns, against 4 deadlocks for the pre-0005
  binary.
- The new start path was seen rescuing the stranded state.

Debian's `/usr/bin/mpv` (and upstream master) still has the bug. A separate,
rarer freeze, an underrun at a `--loop-file` seek, remains open (see "State").

## Symptom

Any mpv playback on this board can freeze for good after an audio underrun.
- Video stops, and mpv stays alive.
- Every mpv thread idles in a futex. No kernel stack is blocked, and dmesg is
  silent.
- The ALSA PCM sits in **`PREPARED` with `avail 0`**: a full buffer that was
  never started.

The log ends with:

```
[ao/alsa] attempt 1 to recover from state 'XRUN'...
[ao/alsa] audio end or underrun
[cplayer] Audio device underrun detected.
[cplayer] restarting audio after underrun
```

A healthy recovery would follow that with `[ao/alsa] starting AO`.

It was first misread as a GPU-path freeze (WP2,
[gpu-fallback-plan.md](gpu-fallback-plan.md)), because video is paced by the
audio clock. It affects every vo, the direct `vo=drm` path included.

## Reproducer

`tools/video/xrun-hammer.sh CLIP [AO] [N]` forces underruns by SIGSTOPping mpv
for 0.2–2 s, then checks that decoding resumes.

| mpv | AO | Result |
| --- | --- | --- |
| Debian 0.40.0 `vo=gpu` | alsa | froze at forced underrun #32 |
| Debian 0.40.0 `vo=gpu` | null | 40/40 recovered (control) |

A single forced underrun usually recovers. It is a race, not every underrun.

## Root cause (mpv 0.40.0, unchanged on master as of 2026-10-02)

mpv sets ALSA `start_threshold = INT_MAX`, so the device never auto-starts. It
must call `snd_pcm_start()`, and `audio/out/buffer.c:ao_play_data()` does that
**only right after a successful write**:

```c
if (samples) {
    ao->driver->write(...);
    if (!p->streaming) { ao->driver->start(ao); p->streaming = true; }
}
```

The race:
1. `ao_play_data()` reads the device state: `RUNNING`, with free space.
2. The underrun lands. `ao_alsa.c:audio_write()` runs its own
   `recover_and_get_state()`, sees `XRUN`, calls `snd_pcm_prepare()`, then
   **writes into the prepared PCM**. `p->streaming` is still true, so no start
   is issued.
3. The next pass reads `PREPARED` (not playing) and takes the eof path. That
   clears `p->streaming` and `p->playing`, and the core restarts audio.
4. The restarted `ao_play_data()` sees `free_samples == 0` (the buffer is full
   from step 2) and returns at `if (!space) return false;` before any write. It
   therefore never reaches the start.

The device is full and never started, and mpv waits for space that never comes.

Anything that delays the ao thread between steps 1 and 2 widens the window: a
SIGSTOP, a scheduling stall, or the GPU path's heavier CPU load.

## Fix

In `ao_play_data()`, when there is no space, the device is not playing but
holds queued data, and mpv is logically playing, not paused and not streaming:
start the device. That covers exactly the stranded state, and nothing else
reaches it. It is a downstream mpv patch (`patches/mpv/0005`).

- Debian's `/usr/bin/mpv` keeps the bug. The WP4 launcher should use the
  patched build, or `--ao=null` where there is no audio.
- This project pushes only to its own forks, so nothing is filed upstream from here. The
  analysis above is written so the operator can file it.

## State

- [x] Root cause, from source and the PREPARED/avail-0 capture
- [x] Baseline: patched mpv (`/usr/local/bin/mpv`, direct `vo=drm`) froze at forced underrun **#2**, same PREPARED/avail-0 state
- [x] 0005 written (`patches/mpv/0005-audio-start-a-full-device-that-was-never-started.patch`), built with `tools/video/build-mpv.sh`, installed to `/usr/local/bin/mpv` (fix string verified in the binary)
- [x] Hammer with 0005, direct path. The PREPARED/avail-0 deadlock did not
  recur: the run reached #51, against #2 before. But **#51 froze
  differently**:
  - ALSA was **RUNNING** (delay 3984, avail 816), not PREPARED;
  - decoding had stopped (+0 frames);
  - threads were in futexes, including libavcodec's `av:h264:df*` workers.

  This is a second failure mode. The open question is whether the PCM's
  `hw_ptr` still advances (if not, the DMA stopped: a kernel/driver bug) or
  the stall is elsewhere in mpv. `xrun-hammer.sh` now takes two status
  snapshots 1 s apart plus the audio DMA IRQ count (`3002000.dma-controller`)
  to answer it.

  **Answered (#56 of a rerun): the audio side is healthy.** Over 1 s, `hw_ptr`
  advanced 48,240 frames (48 kHz), `appl_ptr` advanced as well, and the audio
  DMA took 12 IRQs. The mpv log at the stall ends at the **loop boundary**
  (`lavf EOF reached ... audio EOF reached ... XRUN`). Both second-mode
  freezes landed about 180–200 s in, on a 180 s clip, so this is a forced
  underrun colliding with `--loop-file`'s seek: a separate mpv issue, not a
  failure of 0005 and not the driver. Plain looping is known-good (the
  10-minute looped WP2 runs were clean).
- [x] 0005 alone: 4 x 40 underruns, each run kept short of the loop point.
  **160/160 recovered, but `rescued-by-0005: 0` in every run.** The fix never
  fired, so this does NOT show that 0005 fixes anything. Either the deadlock
  never arose in these 160 attempts, or 0005's condition misses the real
  stranded state.

  **Control, same protocol, pre-0005 binary
  (`/usr/local/bin/mpv.20261002-170447.bak`): it froze in 2 of 4 runs** (#28
  and #8), both PREPARED/avail 0, about one deadlock per ~55 underruns. At
  that rate a fix-less 160-run passes about 5% of the time, so 0005's 160/160
  is suggestive, not proof.
  - The instrument works: the hammer log carries buffer.c's verbose lines
    (9 "starting AO" in one run), so a rescue would have been counted.
  - **8 x 40 more on 0005: 320/320 recovered, `rescued-by-0005: 1`.** The
    new path fired on the real stranded state and playback continued.

  **Total with 0005: 480 forced underruns, 0 freezes, 1 rescue.** At the old
  binary's measured rate (4 deadlocks in all, one per ~30–55 underruns) a
  fix-less 480 would pass well under 0.1% of the time.

  One rescue is fewer than that rate predicts. The old rate rests on only 4
  events, so the deadlock is probably rarer than estimated. The freeze count,
  not the rescue count, is the measure.
- [x] Regression: `va-regress.sh dmabuf` 0 failing (its four mpv `--loop-file`
  lines run `/usr/local/bin/mpv`, i.e. 0005), and the direct path plays 720p
  for 30 s with 0 drops.
- [ ] **Open, separate:** a forced underrun at a `--loop-file` seek froze the
  direct path twice (#51 and #56 of long runs that crossed the 180 s loop
  point). Audio DMA was healthy and mpv kept feeding ALSA, but video
  decoding stopped. It is not the stranded-start state. Investigate with a
  short clip, so every few underruns cross a loop.

## PipeWire: the no-patch alternative (2026-10-02, validated)

The operator preferred a sound server over patching mpv. With one, mpv uses
`ao=pipewire`, a pull-based stream from a server that owns the device and keeps
it running, so mpv's ALSA recovery code (the race) never runs. Debian's mpv
already has the PipeWire output, and desktop Linux runs this way, which is
likely why upstream never sees the deadlock.

**Installed on the board** without `apt update`: no package lists, ~200 MB
free.
- 15 packages, ~20 MB: pipewire 1.4.2-1, pipewire-bin, wireplumber 0.5.8-2,
  their libraries, and libffado/roc/lua.
- They were resolved on the host against trixie, trixie-updates and security,
  minus the board's installed set. SHA-256 was checked against the index, and
  they were installed with `dpkg -i` (no `dpkg --audit` complaints).
- The board's existing libpipewire was already 1.4.2-1, pulled in by mpv.

**Runs as a dedicated user, not root.** Debian's units carry
`ConditionUser=!root`, which is upstream's intent.
- User `media` (uid 1000; groups audio, video, render; home `/var/lib/media`;
  no login shell), with lingering on, so its user manager starts PipeWire and
  WirePlumber at boot.
- Clients running as root reach it with
  `PIPEWIRE_RUNTIME_DIR=/run/user/1000`.
- WirePlumber exposes the codec as "Built-in Audio Stereo", with its software
  volume at 0.40 by default; the level is still to be checked against ALSA
  direct.
- Undo: `loginctl disable-linger media; userdel -r media`.

**Test void, then fixed.** The first 8 x 40 hammer on PipeWire reported
"FROZE after underrun #1" every time. In fact `/tmp`'s clip had been deleted
by `gpu-path-run.sh` and mpv never played. `xrun-hammer.sh` now refuses to
start (`INVALID`) unless the clip exists and mpv is decoding before the first
forced underrun.

**Result: stock Debian mpv with PipeWire recovered from 320 of 320 forced
underruns** (8 x 40, every run past the "mpv is playing" guard). The same
binary on ALSA froze at #32. No mpv patch is needed on this path.

| | ALSA direct | PipeWire |
| --- | --- | --- |
| Whole-board CPU, 720p `vo=gpu` playback | 11–14% | 18% |
| pipewire + wireplumber | — | 4.5% of one core |
| Codec PCM | 48 kHz, period 1200, buffer 4800 | 48 kHz, period 1024, buffer 32768 (PipeWire owns it) |

**Settled configuration** (on the board now, and in `tools/rootfs`):
- packages `pipewire` and `wireplumber`;
- user `media` (uid 1000) in audio, video and render, with lingering
  (`/var/lib/systemd/linger/media`);
- `PIPEWIRE_RUNTIME_DIR=/run/user/1000` in **/etc/environment**.
  `/etc/profile.d` alone is not enough: a plain `ssh board cmd` never reads it,
  and mpv then silently falls back to ALSA, the deadlock path. With it, stock
  mpv with no `--ao` option chooses `[pipewire]` by itself;
- the WirePlumber default sink volume set to 1.0
  (`/etc/wireplumber/wireplumber.conf.d/50-h713-default-volume.conf`).
  WirePlumber starts new devices at 0.4, and ALSA playback here never had a
  software volume (no alsa-utils; the codec mixer is at its kernel defaults),
  so 0.4 would have been a 60% cut.

**Confirmed after a cold boot (2026-10-02):**
- PipeWire and WirePlumber came up by themselves under `media`, with no login;
- no failed units;
- the operator heard the same 15 s of the Leota clip, ALSA direct and then
  PipeWire, at "roughly the same level".

**PipeWire is the fix; 0005 is not a reason to keep a patched mpv.** With
PipeWire running, mpv never runs `ao_alsa`, so it never reaches the code with
the race. 0005 only matters if someone forces `--ao=alsa`. If the direct path
(`patches/mpv` 0001–0004) is ever retired, the patched build can go with it;
that decision rests on the direct path's own merits (WP2).

**2026-10-02: the direct path was retired.** Playback is stock mpv with
PipeWire; 0005 is moot. A correction: the patched mpv had been built without
PipeWire support, so its "120/120 on PipeWire" loop-seek result is void (it
played without audio). The stock `vo=gpu` 120/120 on PipeWire stands.
