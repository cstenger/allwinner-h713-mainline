# Audio underrun deadlock in mpv (2026-10-02)

**Status:** root cause found in mpv's source. Fix: `patches/mpv/0005` (in
progress; see "State" at the end). This file is the handoff if the session ends
mid-way.

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
- [ ] Hammer: 0 freezes over a long run with 0005
- [ ] Regression: direct path still plays (va-regress loop lines, a 720p clip)
