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

`rootfs/` — `customize.sh` is the mmdebstrap customize-hook for the arm64
Debian rootfs (root user, serial getty, fstab). Full recipe in
[../docs/rootfs.md](../docs/rootfs.md).
