# Hardware tools

`serial/` — talk to the board over the console and load images:
- `acm.py CMD [--port <tty>]` — run one U-Boot command, print reply.
- `load_fit.py FILE [--port <tty>]` — single-fd `loady` + YMODEM (big FITs).
- `ymodem_send.py` — standalone YMODEM sender.
- `boot_kernel.py` — setenv + bootm + capture kernel console.

The CDC tools default to `--port auto`, resolving the board by USB vendor ID
`1f3a`; pass `/dev/ttyUSB0` explicitly for the hardwired UART. Historical
destructive and local-artifact-dependent runners live under ignored `local/`,
not in the supported tool set. See ../README.md gotchas.

`display/` — read and probe display registers on the target. Two families,
because the two software stacks reach MMIO differently:

- **Our arm64 Linux**, through `/dev/mem` (root). `devmem32.c` takes individual
  addresses and defaults to the display handoff set with expected values.
  `mmio-read.c` takes an address and word count, so a new window needs no
  rebuild. Both use `mmap`, never `read()`: on arm64 the `/dev/mem` read path is
  gated by `valid_phys_addr_range()` and MMIO is not memory, so `read()` returns
  `-EFAULT` on a perfectly healthy board. `mmio-rw.c` adds writing and dumping
  to the same interface, for poking one register during bring-up.
  `frame-stage-watch.c` is the crash-resistant special case for MIPS/DECD work:
  it busy-polls the shared frame-stage marker, synchronously persists the full
  composition page at each transition, and exits at stage `0x6103`. It is
  freestanding and syscall-only, and is meant to be run `SCHED_FIFO` on a pinned
  CPU, because a shell watcher is not reliably scheduled after a risky submit —
  the first unprotected attempt hard-locked and left a zero-length file.
- **Stock Android**, through the vendor's `/dev/hidtvreg`, which is world
  accessible so no root is needed. Build these as 32-bit ARM — stock userspace is
  `armv7l`. `hidtvreg-dump.c` captures the fixed AFBD/mixer/TVTOP window used for
  diffing, `hidtvreg-read.c` takes an arbitrary address and count, and
  `hidtvreg-poke.c` writes a value, polls to prove it *persisted*, then restores
  what it read, so a probe that blanks the panel recovers by itself.

Two rules worth reading before using them. **Writes to the AFBD block are inert
until the per-register commit latch is pulsed** — control at `+0x00`, latch at
`+0x04`. An uncommitted write lands in the register, reads back, holds
indefinitely and does nothing, so readback proves nothing there. And
`mmio-read.c` and `hidtvreg-read.c` deliberately emit a **byte-identical output
format** so captures from the two stacks diff line-for-line; the first stock
capture of this project used a different case convention and 90 of 150 lines came
back as changed on formatting alone. Do not tidy the formatting. Results in
[../docs/handoff-2026-08-29.md](../docs/handoff-2026-08-29.md).

`page-sample.sh` and `page-classify.py` are the pair for comparing a window
between the two stacks. The script runs on either board and takes four samples
— twice in a resting state, twice in the state under test — and the host
classifier turns those into static / state-driven / free-running before diffing
the two stacks against each other. **Four samples, not two, whenever the window
might contain telemetry.** The firmware-owned composition page at `0x05000000`
mixes configuration with counters that change between reads a second apart, so a
one-sample-per-stack diff of it reports noise and configuration
indistinguishably. Sampling twice in *both* states also catches registers that
free-run in only one — AFBD's buffer ring is still at idle and cycles during
playback, and a single idle pair would misfile it as state-driven.

The same directory holds the CPU_COMM side, for calling routines in the MIPS
display firmware from Linux:

- `cpu-comm-probe.c` — guarded client for `/dev/cpu_comm`. Resolves routine
  names from `/proc/cpu_comm/routines` rather than taking hex, refuses an
  ambiguous prefix instead of picking one, requires `--id` for a raw id, and
  **blacklists `0x0152f134` (`THal_Vp_EnableScreenCover`) by resolved id** —
  that call wedges CPU_COMM and needs a physical power cycle, so the refusal
  belongs in the binary and not in anyone's memory. It also zeros the result
  area before every call, because the kernel only writes it for a returned count
  of `<= 10` and any other count leaves a client reading its own stack.
- `cpu-comm-enable.c` — one-shot test shim (`Kbuild`) that flips the DT `status`
  on `/soc/cpu-comm@3003000`, so the driver can be loaded on a board whose
  running DTB still says `disabled`, with no reflash. Re-running it returns
  `-ENODEV` because the node stays `OF_POPULATED`; to iterate on the driver,
  `rmmod hy310_cpu_comm` and re-insmod it alone.
- `cc-addr-check.c` — bench module for the `cc_ref()` physical-reference
  conversion. It reproduces both driver-private allocations and prints
  `virt_to_phys()` beside a page-table walk, because a module lives in the
  vmalloc region on arm64 and `virt_to_phys()` there takes its
  `__kimg_to_phys()` branch and returns an address that is not the data's.

Protocol, hazards and the read-only calls worth making first are in
[../docs/cpu-comm-client-plan.md](../docs/cpu-comm-client-plan.md).

`mips/` — static analysis of the display firmware. `disasm.py` disassembles a
window and exists to centralise one fact that has already gone wrong once (the
base is `0x8b100000`); `--self-test` fails loudly on a wrong base rather than
describing unrelated code confidently. `block-survey.py` counts `lui` sites into
the display aperture to answer which blocks the firmware addresses at all — it
is how the mixer was closed structurally, and how three firmware-driven blocks
that appear nowhere in `docs/` were found. Both take the raw `display.bin`.

`flash-standalone.sh` — flash the kernel FIT to the `boot_a` partition (via
fastboot) and print the U-Boot `bootcmd` for power-on → Debian. See
[../docs/standalone-boot.md](../docs/standalone-boot.md).

`boot-switch.sh` — move the board between our stack and the vendor's, and flash
ours. Only the 32 KiB first stage at LBA `0x10` is contended; both chains stay
resident. `install --via fastboot` is the least troublesome path (the `--dev`
route needs root for `dd`). Note `sunxi-fel -p uboot` does **not** work on this
SoC — it loads everything and then fails the AArch64 warm-reset handoff, going
silent — so FEL recovery is `-p spl` with the restore SPL, which is a 32-bit SPL
running in SRAM. See [../docs/flash.md](../docs/flash.md).

`split-udisk.sh` — split the factory `UDISK` into a Debian partition and an
Android `UDISK`, so the vendor stack stays bootable for register captures rather
than being something a reflash trades away. Read-only checks by default; needs
`--apply` to write.

`cpufreq-thermal-validate.sh` — runs **on the target** to validate the
voltage-scaling CPU OPP table and its thermal cooling-device binding. It sweeps
every OPP in both directions while reporting VDD-CPU, restores the original
frequency and governor on every exit, and can run a bounded maximum-frequency
stress test with an 85 C default stop threshold. It changes voltage only via
cpufreq and never writes a regulator or thermal trip point directly. See
[../docs/status.md](../docs/status.md).

`rootfs/` — `build.sh --ssh-key FILE` builds the signed Debian arm64 rootfs,
installs matching kernel modules, validates the ext4 image, and emits an
Android-sparse fastboot image. `customize.sh` performs target customization
without executing target binaries. Full recipe in [../docs/rootfs.md](../docs/rootfs.md).
