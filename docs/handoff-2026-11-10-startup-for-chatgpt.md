# Handoff 2026-11-10: startup speed and display hand-over work

For ChatGPT, picking up from a Claude Code session that ran 2026-11-09 and
2026-11-10. Everything below is committed and pushed to
`cstenger/allwinner-h713-mainline` `main` (tip `3d60b474`), and the
working tree is clean. The board runs exactly what is described here.
Detailed evidence for every change is in
[production-evidence/2026-11-09-startup-and-parallel-aic/README.md](production-evidence/2026-11-09-startup-and-parallel-aic/README.md).

## 1. Where things stand

HDMI video now starts about **10.3-10.8 s** after Linux starts on a warm
or cold boot, down from ~14 s on 2026-11-09. Time from the first SPL
output is roughly +7.8 s on top of that. Most of the remaining spread is
the HDMI source PC's reaction to hot-plug (1.1-1.8 s after HPD goes up),
which the board cannot speed up.

Current boot timeline (warm, Linux monotonic):

| Step | Time |
| --- | ---: |
| Kernel start (after SPL) | ~7.8 s after first SPL output |
| `user@1000` active | ~6.8-7.0 s |
| HDMI prepare done (`h713-hdmi-prepare`) | ~8.6-8.7 s |
| Capture unit done (now a no-op) | +~0.06 s |
| EDID/HPD up (`h713-hdmi-signal`) | ~8.9-9.1 s |
| Source starts sending, signal locked | ~10.2-10.9 s |
| `h713-hdmi-video` started | ~10.3-11.0 s |

## 2. What changed in this session (commit order)

| Commit | Change | Effect |
| --- | --- | --- |
| `ecade877..ccd9e407` | `h713-letterbox` squashed into 10 topic commits on `main`; old history under `archive/*` tags | Clean `main` |
| `7f95eff7` | `build-startup.py` defaults to the single MIPS launch (U-Boot 0004) | |
| `c372e3ad` | AIC8800 WiFi loads alongside HDMI startup | |
| `1166ab3f` | U-Boot 0005: early panel-off, 3 s hold overlaps the loads | Kernel starts 0.8 s sooner |
| `932d1749` | Root filesystem grown once (`h713-rootfs-grow-once.service`), not every boot | Removes a 1.7 s outlier |
| `cdd33ffd` | HDMI prepare runs MIPS IPC checks in-process | Prepare 7.1 s -> 5.0 s |
| `afd611a1` | udev rule hides unused eMMC partitions from systemd | User session ready 2.3 s sooner |
| `196afed5` | Kernel: `# CONFIG_LEGACY_PTYS is not set` | User manager start 1.9 s -> 0.5 s |
| `6ce6d8dd` | Kernel patch 0190: cover the console <-> video route hand-over | No pale/green frame at switches |
| `386bc0cf` | Kernel builds pass `RUSTC=/dev/null/rustc`; host rustc can't reach `.config` | Reproducible kernel builds |
| `35cd38a7` | DSP patch (724 pairs) streamed on the busy handshake, no 1 ms per-pair sleep | Patch 824 ms -> 15 ms |
| `ca240e09` | Capture unit `ExecStart=/usr/bin/true`; `check-startup.sh` checks prepare | HPD ~0.4 s sooner |
| `3d60b474` | Bridge delivers black for all-zero capture slots | No green flash at video start |

Key findings worth remembering:

- **systemd device units are expensive here.** Every manager start or reload
  pays ~5 ms of CPU per device-unit name. 27 Android partitions (kept as
  reference, never mounted) and 256 legacy BSD ptys made ~800 units.
- **DSP write busy bit.** AudioTop `0x06144000` bit 4 is a real handshake:
  back to back, the DSP holds it ~19 us per word. The vendor's 1 ms
  per-pair sleep was margin on top of it. The other DSP writes still keep
  the 1 ms.
- **Route hand-over (0190).** The selector at `lvds+0x06c` picks the
  console or video route. The vblender cover (0165) only acts on the video
  route, and it blacks it out even with source 0 idle. So every switch now
  happens on the covered video route.
- **Empty capture slots.** Right after lock the capture pair counter runs
  ahead of the pixel data. With an empty ring (cold boot) the first 4-5
  copied frames are all zero, which shows as solid green.
  `h713_frame_empty()` in `modules/hdmi-v4l2` now shows them as black.

## 3. Board state

- Board: HY200 QZ713DF_A1 (H713, DDR3), reached over WiFi at
  `root@192.168.4.1`. Use the dedicated known_hosts:
  `local/recovery/2026-11-03-production-install-03/known_hosts`. The
  wrapper `local/recovery/2026-11-09-startup-timeline/b.sh` does this. Do
  **not** edit `~/.ssh/known_hosts`; it has a stale key.
- Kernel FIT `9d496308` (0190 + no legacy ptys + rustc-free config). Script
  cmd `2dd9adb1` / scr `4c2453a4`. Installed with
  `tools/hdmi/install-kernel-fit.py`.
- Audio module `45ba26fe` (DSP patch without the 1 ms sleep).
- Bridge `h713-hdmi-v4l2.ko` `b15d20e3` (committed source + empty-frame
  fix). It replaced a 2026-11-05 diagnostic variant
  (`reject-trace-power-v2`, `5de83b88`).
- Capture unit `35883a89` (`ExecStart=/usr/bin/true`); health
  `check-startup.sh` `299a4b0f`.
- Rollback records (each has a `RESUME.json` with the exact command):
  `local/recovery/2026-11-10-dsp-gap`,
  `local/recovery/2026-11-10-capture-noop`,
  `local/recovery/2026-11-10-first-frames`,
  `local/recovery/2026-11-09-green-switch`,
  `local/recovery/2026-11-09-legacy-ptys`,
  `local/recovery/2026-11-09-user-manager`. Backups of the replaced files
  live under `/var/lib/h713-hdmi-startup/` on the board.
- Leftovers in `/root` on the board, all diagnostic and safe to delete:
  - swap and install scripts: `swap-*.sh`, `install-capture-unit.sh`;
  - zeroing test: `zero-ring.py`, `h713-zero-ring.service`;
  - live register tests: `selector-cover-test.py`, `vblend-cover-test.py`;
  - staged modules and units: `h713-hdmi-v4l2-*.ko`, `*.new`;
  - old packages: `*-package` and `*-bundle` directories.

  Keep the `/var/lib` backups until the next release build supersedes them.

## 4. Open work, in suggested order

1. **Signal service start-up (~0.25 s before HPD).** `h713-hdmi-signal.py
   start` spends most of its ~0.33 s on Python start-up and imports
   (`argparse`, `subprocess`, ...). Profile with `python3 -m cProfile` on
   the board and trim or defer imports. HPD then comes up sooner, which is
   the only lever before the PC's reaction time.
2. **Stale first frames on warm reboot (theoretical).** On a warm reboot the
   first 4-5 slots after lock hold the previous boot's last picture. The
   zero check can't catch that. Nobody has seen it, but it may show as a
   brief old-picture flash. A proper fix would skip slots until capture
   has written them once.
3. **Remaining prepare time (~4 s).** Five receiver clock stages, each
   followed by a MIPS `help win` IPC check (~0.45 s, the firmware's reply
   time), then the audio module (~0.2 s now). Whether every stage needs its
   own IPC check has not been examined.
4. **Release.** The final release build (run twice for reproducibility),
   deployment packet, lifecycle regression and qualification are still
   pending. The release build (`tools/release/build.py`) now produces all
   of the above from source. Rebuild and re-pin anything that pins the old
   installed hashes.

## 5. How to work safely on this board

- **Commit or push only when the user asks.** Push only to `cstenger/*`.
  `git push` needs to run outside the sandbox (1Password SSH agent).
- **The HDMI source PC runs the assistant.** Never log out or reboot it.
  Board commands that outlive the ssh session must be detached.
- **Cold boot** means: unplug serial and USB, power off for at least 1
  minute, then power on. The user does this; shut the board down first
  (`systemd-run --on-active=1 systemctl poweroff`) and confirm it's down
  (ping) before asking. Operator-timed tests get their own turn: ask, then
  wait for "done".
- **Warm reboot** from the host: `systemd-run --on-active=1 systemctl
  reboot`, then poll for a new `/proc/sys/kernel/random/boot_id`. It resets
  the DSP (versions 0/0), so it's the cheap test loop for DSP/startup work.
- **Health:** every boot must end `running` with no failed units.
  `h713-hdmi-health-ack` must set RTC GP6 to `HDOK`; U-Boot's crash-loop
  guard reads it.
- **Verify boot-critical changes on a cold boot.** U-Boot's image-size
  check and the `h713,hdmi-boot-v1` handoff only run on the cold path.
- **Hard locks:** never read `0x07091000` (CPUS/ARISC) or `0x06940000`.
  `0x05001530` wedges the SoC on the logo-free path.
- **Rebuild baselines byte-for-byte first.** Before changing a module or
  kernel, rebuild the unmodified source and match the installed hash; only
  then is a diff evidence. Recipes:
  - kernel: `local/recovery/2026-11-09-legacy-ptys/kbuild.sh` (release
    epoch 1793693083, `KERNEL_CONFIG=production`);
  - audio module: `local/recovery/2026-11-10-dsp-gap/mbuild.sh`;
  - bridge: `local/recovery/2026-11-10-first-frames/vbuild.sh`.
- **Kernel/script installs** go through `tools/hdmi/build-kernel-fit-bundle.py`
  (checks config diff, `Module.symvers`, release and DTB) and
  `tools/hdmi/install-kernel-fit.py` (guarded, FIT before script, full
  rollback).
- **Audio check:** `tools/hdmi/run-pipewire-tone-check.py <new-dir>` plays
  1 kHz/2 kHz from the PC over HDMI at 48/32/44.1 kHz. The board records
  through PipeWire, with the speaker muted during the test. The rootfs has
  no `arecord`.
- **Panel checks need the user's slow-motion recordings** (`local/lcd-photos/test_*`,
  4x slow motion, so 1 s of video = 0.25 s real). Scan them per frame
  (`ffmpeg -vf scale=64:36 -f rawvideo -pix_fmt rgb24`) and look at the
  frames. The boot logo's text and the console text are green-tinted, so a
  "green" flag there is not a flash.

## 6. Traps that cost time in this session

- **Results that can't fail.** Each of these produced a false all-clear:
  - `tools/re/awemu.py` silently swallows `usleep`, `malloc`, `memcpy`,
    `free` and a few more before user hooks run. It gave "stock has no
    sleeps", which was false; rename the stub to record it.
  - `llvm-objcopy ... /dev/stdout` writes nothing, so section hashes of
    empty output all matched.
  - `mmap.flush()` on a `/dev/mem` mapping raises EINVAL. It came after
    the writes, so the writes did happen; don't misread the error as "no
    write".

  Always find the line that would have failed, or prove the check catches
  a known-bad input.
- **Units are a chain.** Capture owns the session teardown, and the signal
  unit starts after it so it stops first at shutdown. Don't reorder; change
  only `ExecStart`.
- **The release's module tests compile real C.**
  `tools/hdmi/test-frame-discard-contract.py` extracts the bridge's capture
  loop and builds it against stubs. A new helper in that loop must be added
  to its extraction.
