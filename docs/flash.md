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
# back in U-Boot — block count must ROUND UP (e.g. 844377 B = 0x673 blocks):
mmc dev 1
mmc write 0x42000000 0x10 0x673
cmp.b 0x42000000 <readback> <len>     # verify
```

Prefer the CDC gadget (`tools/serial/load_fit.py`, ~171 KB/s) over the UART
(~11 KB/s) for anything large.

## Method 2 — expose the whole eMMC to the host (UMS)

```
# in U-Boot — release the ACM console first (it holds the USB controller),
# as ONE line over the CDC console:
setenv stdout serial; setenv stderr serial; setenv stdin serial; ums 0 mmc 1
# host: the eMMC appears as /dev/sdX with all 26 partitions
sudo dd if=u-boot-sunxi-with-spl-ddr3.bin of=/dev/sdX bs=512 seek=16 conv=fsync
```

Rootless host I/O is possible via udisks2 `OpenForRestore` (D-Bus) if you can't
`dd` as root. `reset` restores the ACM console afterward.

## Method 3 — fastboot

```
# in U-Boot (release the ACM console as above, then):
setenv stdout serial; setenv stderr serial; setenv stdin serial; fastboot usb 0
# host:
fastboot flash bootloader_a u-boot-sunxi-with-spl-ddr3.bin
fastboot flash UDISK rootfs.simg          # rootfs (Android-sparse, see below)
```

- The fastboot **download buffer is 32 MiB** → images larger than that must be
  **Android-sparse** (`img2simg in.img out.simg`); the host tool chunks them
  (e.g. a ~220 MiB sparse rootfs uploads in ~7 chunks / ~155 s).
- `fastboot usb 0` fails `g_dnl -22` if the ACM console still holds the USB
  device controller — hence releasing it in the same line first.

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

- Always name the board a flash ran on — feeding HY310 (LPDDR3) params to the
  HY200 (DDR3) board trains "OK" but reads hang.
- A full eMMC backup exists in `~/Projects/h713-lab` (do not commit — proprietary).
