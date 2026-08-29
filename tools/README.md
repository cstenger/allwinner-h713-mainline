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
  `-EFAULT` on a perfectly healthy board.
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
