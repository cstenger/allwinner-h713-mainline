# Flashing

How to write images to the H713 eMMC. Neither board has an SD slot — boot media
is **eMMC or FEL only**. There is a hardware **FEL button** (recovery vector),
so a bad first stage is recoverable.

## eMMC layout (what goes where)

| Offset | Contents |
|--------|----------|
| sector 16 (8 KiB) | `u-boot-sunxi-with-spl.bin` (SPL + BL31 + U-Boot, <1 MiB) |
| 4 MiB | U-Boot environment (raw) |
| 12 MiB | vendor boot package (toc1, factory) |
| 36 MiB | first Android GPT partition |
| `UDISK` (p26) | Debian root filesystem |

`mmc1` is the eMMC in U-Boot; `mmc0` is disabled (no SD slot).

## Method 1 — from a running U-Boot over serial (`loady`)

No host root needed; works on the soldered UART. ~80 s for a 768 KiB image.

```
# in U-Boot:
loady 0x42000000
# host: send the file via YMODEM
tools/serial/ymodem_send.py u-boot-sunxi-with-spl-ddr3.bin --port /dev/ttyUSB0
# back in U-Boot — block count must ROUND UP (844417 B = 0x672 blocks):
mmc dev 1
mmc write 0x42000000 0x10 0x672
mmc read 0x43000000 0x10 0x672
cmp.b 0x42000000 0x43000000 0xce281   # use the exact file length
```

Prefer the CDC gadget (`tools/serial/load_fit.py`, ~171 KB/s) over the UART
(~11 KB/s) for anything large.

## Method 2 — expose the whole eMMC to the host (UMS)

```
# in U-Boot; if entered over ACM, keep this on one line because ACM disconnects:
run serial_mode; ums 0 mmc 1
# host: the eMMC appears as /dev/sdX with all 26 partitions
sudo dd if=u-boot-sunxi-with-spl-ddr3.bin of=/dev/sdX bs=512 seek=16 conv=fsync
```

Rootless host I/O is possible via udisks2 `OpenForRestore` (D-Bus) if you can't
`dd` as root. Stop UMS with Ctrl-C on UART; the console remains serial-only.

## Method 3 — fastboot

```
# in U-Boot (safe to issue from UART or as one line from ACM):
run fastboot_mode
# host:
fastboot flash bootloader u-boot-sunxi-with-spl-ddr3.bin
fastboot flash UDISK rootfs.simg          # rootfs (Android-sparse, see below)
```

`bootloader` is an H713-specific raw fastboot target: LBA `0x10`, size
`0x1ff0` sectors, ending immediately before the persistent environment at
4 MiB. The size guard rejects an oversized image. Do **not** substitute the
factory GPT name `bootloader_a`; that is a different partition at 36 MiB and
is not the BROM-loaded first stage. U-Boot supplies this target at runtime
when an older saved environment does not contain it, so upgrading does not
require resetting the rest of the environment.

- The fastboot **download buffer is 32 MiB** → images larger than that must be
  **Android-sparse** (`img2simg in.img out.simg`); the host tool chunks them
  (e.g. a ~220 MiB sparse rootfs uploads in ~7 chunks / ~155 s).
- `fastboot usb 0` fails `g_dnl -22` if ACM still owns the USB controller.
  `run fastboot_mode` selects serial-only consoles before registering fastboot
  and returns to serial-only mode if fastboot exits. The helper is also injected
  when an older saved environment does not contain it.
- U-Boot's current `g_dnl` gadget layer registers one USB function at a time,
  so ACM and fastboot intentionally appear as two successive USB devices rather
  than simultaneous interfaces in one composite device.
- Close the old ACM/fastboot/UMS handle before switching. Resolve each new
  device by VID/serial rather than a fixed path; if the host retains a stale
  `1f3a:1010` identity across a board reset, use a full power cycle.

## Method 4 — cold recovery via FEL

Hold the **FEL button** at power-on to enter the BROM's USB FEL mode, then use
`sunxi-fel` (from the `external/sunxi-tools` build). Note the H713 FEL BROM
stalls on large bulk transfers — our sunxi-tools carries the 16 KiB-cap fix that
makes loading a >~48 KiB SPL reliable (see [reference/h713-fel-notes.md](reference/h713-fel-notes.md)).

**Un-bricking a clobbered first stage:** the local-only recovery SPL
(`local/0001-...LOCAL-ONLY.patch`, embeds the vendor boot0 — never published)
FEL-loads once, rewrites the vendor boot0 to eMMC sector 16, and halts; power
cycle to boot the stock firmware. `git am` that patch into `external/u-boot` to
build it.

## Standalone boot (power-on → Debian)

To boot the kernel from eMMC with no host attached — flash the FIT to `boot_a`
and set a U-Boot `bootcmd` — see [standalone-boot.md](standalone-boot.md)
(`tools/flash-standalone.sh`).

## Safety

- Always name the board a flash ran on — feeding the projector's HY200 QZ713_V2 (LPDDR3) params to the
  HY200 (DDR3) board trains "OK" but reads hang.
- A full eMMC backup exists in `local/h713-lab` (do not commit — proprietary).
