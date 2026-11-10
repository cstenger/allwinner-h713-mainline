# Startup timeline and parallel AIC startup — November 9

## Baseline cold timeline (boot `2b825f9d`)

Installed: single display-firmware launch (`d2e8cb7a`), `hpd-event-v1`,
source-power V4L2, global AIC8800 module loading. Passive UART plus the
board journal. The PC's HDMI output was disabled, so the source lock was not
measured. [Parsed result](baseline-cold-timeline.json).

| Milestone | Time |
| --- | ---: |
| U-Boot proper / startup script | SPL +1.95 / +2.15 s |
| Logo | SPL +6.16 s |
| Starting kernel | SPL +8.71 s |
| Kernel modules loaded (AIC8800 4.02-6.59 s inside) | Linux 6.75 s |
| sysinit.target | Linux 8.03 s |
| HDMI prepare | Linux 8.11-14.14 s |
| EDID/HPD ready | Linux 14.90 s |

The global AIC load held `systemd-modules-load` for ~2.7 s, and every HDMI
unit waits for sysinit behind it.

## Parallel AIC startup: qualified on three cold boots

The 11-05 change (`h713-aic8800-modules.service`, aliases blacklisted; see
[the experiment](../2026-11-05-parallel-wifi/README.md)) was reinstalled
unchanged (manifest `5a90c744`). It had been rolled back only to keep the
first-advert investigation clean, which closed with `hpd-event-v1`.
[Per-boot results](parallel-aic-qualification.json).

| Cold boot | HDMI prepare starts | EDID/HPD ready | Video active |
| --- | ---: | ---: | ---: |
| Baseline | 8.11 s | 14.90 s | ~16.3 s (expected) |
| 1 (`0f1cecc5`) | 4.60 s | 12.45 s | 13.87 s |
| 2 (`addba87b`) | 6.17 s | 13.83 s | 15.82 s |
| 3 (`648e97ae`, after a power cut) | 4.68 s | 12.49 s | 13.91 s |

All three: no failed units, hotspot up, `hci0` UP RUNNING, HDMI locked with
no re-advertise pulse. The shutdown of boot 1 under the new configuration
was clean. Operator view of boot 1: logo ~9 s and desktop ~25 s after power-on.

Boot 2 was slower because `systemd-growfs-root` took 1.70 s (usually
~0.15 s) and early tmpfiles waited behind it. The partition is already full
size; disabling the resize on the product image is a candidate follow-up.

The rootfs builder now emits this configuration by default.

## Early panel off (U-Boot 0005)

`h713_disp panel-off` enters the same verified off state as the 3 s hold
(MIPS parked, signals quiet, reset and supply read back) at the start of the
script; the logo step re-verifies it and waits only the remainder. The hold
is not shortened. The current series rebuilt reproducibly to the installed
proper (`7e7835d0`); the candidate is `33bc73c8`, same size, no new warnings.

Installed with the unchanged `install-single-launch.py` (proper, then a warm
reboot on the old script: healthy, then the script). Cold boot `888e9f1d`:

| From SPL | Before (parallel AIC boot 1) | Early panel off |
| --- | ---: | ---: |
| Panel off state entered | ~3.1 s | 2.25 s |
| Logo | 6.01 s | 5.26 s |
| Starting kernel | 8.56 s | **7.76 s** |

U-Boot reported the panel had been off for 0.837 s when the logo step reached
the hold, and waited 2.163 s more. Linux: no failed units, hotspot and `hci0`
up, EDID/HPD ready 12.48 s, locked 13.82 s, video 13.88 s, no re-advertise
pulse. Video starts about 21.6 s after the first SPL output.

## Root filesystem grown once, not every boot

`x-systemd.growfs` made systemd run a no-op online resize of the root before
local-fs on every boot (usually ~0.15 s; 1.70 s on parallel-AIC boot 2). The
release image is deliberately small, so growth is still needed once:
`h713-rootfs-grow-once.service` runs `systemd-growfs /` after local-fs, off
the critical path, then writes `/var/lib/h713-rootfs-grown`. A freshly
written image has no marker and grows on its first boot.

Installed on the board (fstab backup under
`/var/lib/h713-hdmi-startup/growfs-once-*`) and checked over two warm
reboots: reboot 1 ran grow-once at 4.67-5.35 s ("Successfully resized"),
created the marker and started video at 13.97 s; reboot 2 skipped it by
condition and started video at 13.93 s. `systemd-growfs-root` no longer runs,
root stays `rw,noatime` at 2.7 GB, no failed units. In these boots sysinit
(~4.5 s) was gated by udev coldplug, so the typical saving is small; the
change removes the 1.7 s outlier and the per-boot resize.

## HDMI prepare: MIPS checks in-process (Fix A)

A profile of `h713-hdmi-prepare` (7.10 s) found that each of the five receiver
clock stages started a fresh Python interpreter for the MIPS `help win` IPC
check, the alive check and the trace snapshot. The firmware reply itself is
~0.44 s; the rest was interpreter start-up and module import. The session now
loads `h713-mips-shell.py` and `read-comm-trace.py` once and calls the same
functions in-process: the same `/run/lock/h713-mips-shell.lock` (refused,
not waited on, when busy), the same reply schema/completion checks, and the
same stop-on-failure. `read-comm-trace.py` was split into `open_trace`,
`sample` and `source_snapshot`; its CLI output is unchanged. A read-only check
on the live board gave the same trace snapshot through both paths.

Installed with `tools/hdmi/install-inprocess-ipc.py` (guarded like the
stage-1 installer; backup `inprocess-ipc-91c180e0...`). Warm reboot
`1f07d80d`:

| | Before | In-process |
| --- | ---: | ---: |
| HDMI prepare | 7.10 s | **5.03 s** (4.62-9.65 s) |
| Each clock stage | 0.7-0.9 s | 0.45 s |
| Video active | 13.9 s | 14.0 s |

No failed units; HDMI locked. Video did not move because capture is also
ordered `After=user@1000.service`, which became active at 11.49 s; inside it
`systemd --user` logged nothing from 8.44 s to 11.34 s (its generators take
~0.25 s). Prepare now finishes ~2 s before the user session, so the user
session is the next item on the critical path.

The historical installer tests now check frozen, content-addressed copies of
the payloads they deployed (`tools/hdmi/test-payloads/`), so later edits to
the live scripts no longer break them.

## User manager: device units for unused partitions

`systemd --user` sat silent for 2.5 s at start-up, and capture waits for
`user@1000.service`. A reload of either manager on an idle board took 2.1 s,
1.65 s of it user-space CPU in systemd (sampled PCs: `unit_name_is_valid`,
`string_table_lookup`, path hashing, i.e. per-name drop-in search). The cost
scales with device units: the 27 kept Android partitions, the whole disk and
boot0/1 gave ~300 units (about ten aliases each), and the 256 legacy BSD pty
slaves (`CONFIG_LEGACY_PTYS=y`) another ~500.

Hiding everything on `mmcblk0` except the root partition (partlabel `linux`)
from systemd with `99-zz-h713-unused-partitions.rules` (`TAG-="systemd"`,
after `99-systemd.rules`) leaves the `/dev` nodes and `/dev/disk` links in
place. Warm reboots `49946366` and `91ccacf6`:

| | Before | Rule |
| --- | ---: | ---: |
| `systemd --user` session open to default target queued | 2.90 s | 1.83 / 1.90 s |
| `user@1000` active | 11.49 s | 9.18 / 9.37 s |
| Video active | 13.99 s | **11.57 / 11.75 s** |

No failed units, root mounted, HDMI locked. Prepare (ends ~9.5 s) is the
critical path again. Hiding the legacy ptys as well brought an idle reload
to 0.83 s (user) / 1.11 s (system) in a runtime test.

Testing notes: `TAG-=` removes only the current tag; the sticky `TAGS` and
`/run/udev/tags/systemd` entry stay, but systemd skips the device ("not
tagged with systemd"). Moving tag entries aside measures nothing once the
units already left; measure from a reboot or the second reload.

## Legacy BSD ptys disabled in the kernel

`# CONFIG_LEGACY_PTYS is not set` in the board defconfig removes the 256
unused `/dev/ptyp*`/`/dev/ttyp*` pairs (and their ~500 systemd device units).
The release kernel stage, rebuilt with the release epoch and identity,
reproduced the installed FIT byte-for-byte (`6ccf040a`). The candidate
(`b4fd5939`, 7613352 bytes) differs from it only in `CONFIG_LEGACY_PTYS` and
`CONFIG_LEGACY_PTY_COUNT`: identical `Module.symvers`, kernel release and
board DTB, so the installed modules are unchanged. The startup script changes
only in the two lines that pin the FIT size (`0x7428ec` -> `0x742ba8`).

`tools/hdmi/build-kernel-fit-bundle.py` enforces those checks;
`tools/hdmi/install-kernel-fit.py` replaces the FIT and every script copy as
one guarded transaction (bundle copies first, then FIT, then the FAT script;
any failure restores all originals). Installed from boot `91ccacf6`; backup
`kernel-fit-1d36583a...`.

| | Partition rule | + no legacy ptys (warm `fcdec2f1` / cold `06098456`) |
| --- | ---: | ---: |
| `systemd --user` session open to default target queued | 1.83-1.90 s | 0.51 / 0.55 s |
| `user@1000` active | 9.18-9.37 s | 6.83 / 6.91 s |
| Idle reload (user / system) | 2.1 / 2.1 s | 0.73 / 0.96-1.27 s |
| Video active | 11.57-11.75 s | 11.58 / 11.59 s |

The cold boot carried the `h713,hdmi-boot-v1` handoff, so the script's
image-size check accepted the new FIT. No failed units; WiFi, `hci0` and HDMI
lock normal. Video did not move: `h713-hdmi-prepare` (ends ~9.44 s) is now
the critical path, ~2.5 s after the user session.

## Console <-> video hand-over without a bad frame (kernel 0190)

The operator saw a green frame at the boot switch from the console to HDMI.
It was not the closed green stall (stall words 0, latches toggling). 120 fps
video of video-service restarts (`local/lcd-photos/test_112`) showed one
flat pale frame at every switch in both directions: the driver stopped the
selected route's source before moving the selector (`lvds+0x06c`), so the
panel showed a route with its source off (pale), or source 0 enabled with
nothing fetched yet (green).

Two live register tests decided the fix. The 0165 vblender cover has no
effect while the console route is selected (`test_112`). With the cover on,
selecting the video route while source 0 is idle shows black, and switching
the selector into and out of it is clean (`test_113`). Patch 0190 therefore
carries every hand-over on the covered video route: cover, wait one vblank,
select the video route, wait one vblank, then the existing source switch,
and uncover once source 0 has latched. On the way back: cover while the
video route is still selected, stop source 0, keep the cover through the
window-layer restore, restore and select RGB, wait one vblank, uncover.

Built against the installed kernel (`b4fd5939`): identical `.config`,
`Module.symvers`, release and DTB, and of 2370 objects only
`sun50i-h713-afbd.o` differs in its allocated sections. Installed as FIT
`d4cb9c95` with script `349a8c74` (backup `kernel-fit-ae78b3d1...`).

- Warm boot `ccb84903`: no failed units, no driver warnings; three restart
  cycles (`test_114`) show every switch dipping to black for ~25 ms, no pale
  or green frame. The frame check that finds nothing here flags the known
  flashes in `test_112` and `test_113`.
- Cold boot `096e9358`: `hdmi-boot-v1` handoff present, video 12.3 s;
  `test_115` shows console, the cover scanning down, then video.

Build note: Kconfig probes `rustc` even with `CONFIG_RUST` off and writes the
result into `.config`, which IKCONFIG embeds in the FIT. rustup was removed
from the build host on 2026-11-09, so this kernel was built with the
remaining rustc 1.99 toolchain on `PATH` to reproduce the installed config.
Closed below.

## Kernel config no longer depends on host rustc

Kconfig probes `$(RUSTC)` with `CONFIG_RUST` off and writes eight lines into
`.config`. With rustc 1.99 they are `RUSTC_VERSION=109900`,
`RUSTC_LLVM_VERSION=230101`, five `RUSTC_HAS_*=y` and
`HAVE_CFI_ICALL_NORMALIZE_INTEGERS_RUSTC=y`; without rustc they are `0`, `0`
and absent. IKCONFIG embeds `.config` in the FIT, so having rustc on `PATH`
changed the image. No C code reads these symbols.

Pinning rustc as a release toolchain would have made a tool the kernel does
not use a required input. Instead `tools/build/build.sh` passes
`RUSTC=/dev/null/rustc` (a path that cannot exist) to every kernel `make`
(`kernel_make`), so the probe always finds no rustc. It rejects
`CONFIG_RUST=y` and fails if a rustc result reaches `.config`, both after
configuration and after the build. `tools/release/build.py` refuses
`H713_KERNEL_RUSTC` and checks the built `.config` again.

Checks:
- `tools/build/test-kernel-rustc-probe.py` (about 20 s, own build directory)
  runs `build.sh kernel-config` with the production fragment twice: once
  with a fake rustc 1.99 first on `PATH`, once with no rustc. Both `.config`
  files are identical, with `RUSTC_VERSION=0`. A control run with
  `H713_KERNEL_RUSTC=<fake>` gives exactly the eight rustc 1.99 lines above,
  so the fake is really probed.
- `tools/release/test-release.py` (`rustc_probe_leaks`) and
  `tools/hdmi/test-kernel-fit-bundle.py` cover the release check and the
  bundle transition.

### Transition (not done yet)

Every installed FIT (`d4cb9c95` now) embeds rustc 1.99's probe results, so
the new default build cannot reproduce it. The next kernel bundle carries the
change:

1. Baseline: the installed sources with
   `H713_KERNEL_RUSTC=$HOME/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin/rustc`.
   This is the only remaining use of that toolchain, and it must stay on the
   host until the transition FIT is installed.
2. Candidate: the default build, with no override.
3. `build-kernel-fit-bundle.py --rustc-probe-transition` (plus any real
   `--config-diff`). It requires exactly those eight symbols to go from the
   rustc 1.99 values to "none", and still refuses any other config change.

After it is installed, baselines build without rustc and the 1.99 toolchain
can be deleted.

Built 2026-11-10 as a config-only bundle of the installed sources
(`local/recovery/2026-11-10-rustc-probe`, same kernel tree digest
`f49750b0` as the installed build). Installed the same day from boot
`096e9358` (backup `kernel-fit-a3fb1362...`). Warm boot `8a6014a4`:
`/proc/config.gz` is byte-identical to the candidate `.config`
(`RUSTC_VERSION=0`); `running`, no failed units, video active at 11.8 s,
WLAN and `hci0` up. Cold boot `4a122258` (serial and USB unplugged): the
`h713,hdmi-boot-v1` handoff is present, so the script's image-size check
accepted the new FIT. Same config, no failed units, video active at 11.8 s.
The bundle tool's `INSTALLED_*` defaults now name this FIT, and later
baselines build without rustc. The rustc 1.99 toolchain and the two build trees were
deleted afterwards, so FITs from before this change can no longer be
rebuilt on this host.

- The baseline with `H713_KERNEL_RUSTC` reproduces the installed FIT
  `d4cb9c95` byte for byte.
- The candidate FIT is `9d496308`, with script cmd `2dd9adb1` / scr
  `4c2453a4`. `--rustc-probe-transition` passed, and the installer's
  `load_bundle` accepts the bundle.
- `.config` differs only in the eight rustc lines. `Module.symvers`, the
  kernel release and the board DTB are identical.
- Of 2474 `.o`/`.ko` files only `kernel/configs.o` differs (the IKCONFIG
  blob, 64 bytes less `.rodata`), plus the link-stage `vmlinux.o` and
  kallsyms objects. No text symbol moves. The 5526 `.rodata` symbols after
  the blob move down 58 bytes, so the instructions that reference them
  change. Section sizes are unchanged.

## DSP patch without the per-pair 1 ms settle

HDMI prepare spent ~0.82 s streaming the 724-pair DSP patch, 1 ms per pair.
That gap is the vendor's: re-running stock `msp_download_sxl` offline
(with `awemu`'s built-in `usleep` stub renamed so the call is recorded; the
default stub swallows it) shows 200 ms after `fff7=0`/`0000=0`, then 1 ms
before every pair. The write routine itself only waits for AudioTop
(`0x06144000`) bit 4.

An instrumented build (`local/recovery/2026-11-10-dsp-gap`; unmodified
sources rebuilt byte-for-byte to the installed modules first) timed bit 4
after every patch write and a DSP read round trip:

| | 1 ms gap (1 warm) | no gap (4 warm, 1 cold) |
| --- | ---: | ---: |
| Patch stream | 824 ms | 14.9-15.4 ms |
| Bit 4 still set after the write | 229 of 724, <= 8.5 us | 693-724 of 724, mean ~19 us, max 39 us |
| Read round trip | 19 us mean | 17-24 us mean, max 33 us |
| Versions / graph / tone check | 1/1, 22 words, pass | same, every boot |

Bit 4 is the write handshake: back to back, the DSP holds it for about one
read round trip per word and the next write waits for it; after a 1 ms idle
the DSP has already taken the word. The tone check
(`tools/hdmi/run-pipewire-tone-check.py`: this PC plays 1 kHz/2 kHz over
HDMI at 48/32/44.1 kHz, the board records its PipeWire HDMI source) rejects
swapped channels and a 1 s dropout.

`h713-hdmi-dsp.c` now posts the patch pairs without the settle (`dsp_post(...,
false)`); the masked init, prefix and graph writes keep it, as does the
100 ms wait before the version check. Installed module `45ba26fe`, warm boot
`676a12bc`: versions to verified 122 ms (was 931 ms), tone check 3/3,
prepare done 8.73 s (was 9.50 s), video 10.87 s (was 11.69 s).

## HPD sooner: capture unit no longer re-runs the session

From prepare done to video was ~2.1 s: capture 0.41 s, signal 0.33 s, then
the source PC's reaction to hot-plug (1.1-1.8 s, outside the board's
control). `h713-hdmi-capture.service` re-ran `h713-hdmi-session.py start`
only to report "already ready": its checks take ~10 ms; the rest was
interpreter start-up (~104 ms), imports (~140 ms) and argparse (23 ms).
Prepare already verifies and saves "ready" before capture can start, so
capture's `ExecStart` is now `/usr/bin/true`. Its role is unchanged: it owns
the session teardown, and the signal unit still starts after it so it stops
before that teardown.

`check-startup.sh` (run by health-ack, which acknowledges U-Boot's RTC GP6
crash-loop guard) looked for `--boot-handoff` in capture's start; the first
warm boot ended degraded until it checked prepare instead (and requires
prepare active). Fixed and re-acknowledged in that boot.

| | Before | Warm 1 / 2 | Cold |
| --- | ---: | ---: | ---: |
| EDID/HPD up | 9.49 s | 9.10 / 8.96 s | 9.04 s |
| Video active | 10.87 s | 10.53 / 10.79 s | 10.45 s |

Shutdown teardown ran cleanly ("Deactivated successfully"); health-ack
passed on its own; tone check 3/3 on every boot.

## Empty capture slots shown as black, not green

After the capture-unit change a cold boot showed a green flash at video
start (not the closed green stall: stall words 0). Two recorded cold boots
(`test_115`, `test_116`) were clean. A logging-only bridge build (the
installed variant, rebuilt byte-for-byte first) sampled the first six frames
copied after lock; a one-boot unit zeroed the six capture planes at
shutdown, after the capture teardown, to give a warm boot a cold boot's
empty ring. Right after lock the pair counter runs ahead of the pixel data:
with the ring empty the first 4-5 copied frames are entirely zero, and
all-zero NV12 is solid green. On a warm reboot those slots hold the last
picture instead, which is why only cold boots showed it, and HPD coming up
sooner made the stream start close enough to lock to catch them.

No source colour converts to U=V=0, so `h713_frame_empty()` samples each
copied frame (~900 points per plane, full height) and the pair thread
delivers its black fill when all are zero, logging the count per lock. With
the ring zeroed at shutdown, four of four warm boots logged "4 (or 5) empty
frames after lock shown as black". Cold boot `2ce6b9f5` (`test_117`): no
empty frames that time, no green, switch console -> one covered frame ->
video. `test-frame-discard-contract.py` now compiles the real check, adds an
empty-slot case, and a mutant without the check fails it.

The board had been running a 2026-11-05 diagnostic bridge variant
(`reject-trace-power-v2`); it now runs the committed source with this fix.
