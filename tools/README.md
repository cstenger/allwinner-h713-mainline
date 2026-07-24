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

`flash-standalone.sh` — flash the kernel FIT to the `boot_a` partition (via
fastboot) and print the U-Boot `bootcmd` for power-on → Debian. See
[../docs/standalone-boot.md](../docs/standalone-boot.md).

`cpufreq-thermal-validate.sh` — runs **on the target** to validate the
voltage-scaling CPU OPP table and its thermal cooling-device binding. It sweeps
every OPP in both directions while reporting VDD-CPU, restores the original
frequency and governor on every exit, and can run a bounded maximum-frequency
stress test with an 85 C default stop threshold. It changes voltage only via
cpufreq and never writes a regulator or thermal trip point directly. See
[../docs/status.md](../docs/status.md).

`crypto-rng-validate.sh` — a **target-side** validator for the Crypto Engine
(`sun8i-ce`) and its RNG, retained for a **future re-attempt**. The CE is
currently disabled because mainline `sun8i-ce` cannot drive the H713 (see
[../docs/status.md](../docs/status.md)), so it has nothing to check on today's
kernel — it only exercises a kernel that re-enables `sun8i-ce`. It is read-only
with respect to hardware (no register/tunable writes); `--rng-bytes N` sets the
RNG sample size and `--rngtest` runs the FIPS stream test (`rng-tools5`).
**Known limitation to fix before relying on it:** it currently treats
`/proc/crypto`'s `selftest: passed` as the correctness gate, but that field is a
vacuous default unless `CONFIG_CRYPTO_SELFTESTS=y` — the real gate is a
known-answer test against the live engine (`kcapi-dgst`/`openssl` for hashes and
ciphers, `kcapi-rng`/`/dev/hwrng` for the RNG).

`rootfs/` — `build.sh --ssh-key FILE` builds the signed Debian arm64 rootfs,
installs matching kernel modules, validates the ext4 image, and emits an
Android-sparse fastboot image. `customize.sh` performs target customization
without executing target binaries. Full recipe in [../docs/rootfs.md](../docs/rootfs.md).
