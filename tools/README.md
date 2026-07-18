# Hardware tools

`serial/` — talk to the board over the console and load images:
- `acm.py CMD --port <tty>` — run one U-Boot command, print reply.
- `load_fit.py FILE --port <tty>` — single-fd `loady` + YMODEM (big FITs).
- `ymodem_send.py` — standalone YMODEM sender.
- `boot_kernel.py` — setenv + bootm + capture kernel console.
- `wr_cycle.py` — autonomous eMMC write-path test (boot → write → verify).

Resolve the board's CDC tty by USB vendor id `1f3a` (it renames across
re-enumeration); the UART is `/dev/ttyUSB0`. See ../README.md gotchas.

`rootfs/` — `customize.sh` is the mmdebstrap customize-hook for the arm64
Debian rootfs (root user, serial getty, fstab). Full recipe in
[../docs/rootfs.md](../docs/rootfs.md).
