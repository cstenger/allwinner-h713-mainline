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
fastboot flash uboot u-boot-sunxi-with-spl-ddr3.bin   # raw first stage @ LBA 0x10
fastboot flash UDISK rootfs.simg          # rootfs (Android-sparse, see below)
```

`uboot` and `bootloader` are the same H713-specific raw fastboot target: LBA
`0x10`, size `0x1ff0` sectors, ending immediately before the persistent
environment at 4 MiB. The size guard rejects an oversized image. **Prefer the
`uboot` alias** — a slot-aware fastboot host silently rewrites `bootloader`
into the A/B slot name `bootloader_a` and writes the unused 36 MiB GPT
partition there instead of the LBA-0x10 first stage (a flash that "succeeds"
but changes nothing that boots). `uboot` is not a GPT partition name, so the
host passes it through verbatim. Both aliases are in U-Boot's default env
(`fastboot_raw_partition_{uboot,bootloader}`), and U-Boot injects them at
runtime when an older saved environment lacks them, so upgrading does not
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

### Fastboot RAM staging and lifecycle commands

U-Boot can point its fastboot download buffer at a bounded RAM window. This is
useful for repeatedly loading the display coprocessor firmware without writing
eMMC:

```
# in U-Boot: exact display.bin address and size
run serial_mode; fastboot -l 0x4b100000 -s 0x132b18 usb 0; run serial_mode

# host: download directly to 0x4b100000, then leave fastboot WITHOUT resetting
fastboot stage display.bin
fastboot continue
```

**Exit staging with `fastboot continue`, never `fastboot reboot bootloader`.**
`continue` trips `g_dnl_detach()`, so `do_fastboot` returns, the rest of the
`;` sequence runs, and the board lands at the prompt with DRAM untouched.
Ctrl-C on UART breaks the same loop and is an equally clean escape.

A warm reset does **not** preserve staged RAM on H713, contrary to what this
section previously claimed: SPL re-runs DDR3 init and training, and
`0x4b100000` comes back as uninitialized DRAM. Bench-verified 2026-07-28 —
after `fastboot reboot bootloader` the window read `a41ef7f5 effffeff …` and
`h713_mips verify` reported SHA-256 `991c1364…`, the hash of noise. The same
stage exited with `fastboot continue` verified as the pinned `16c74a28…`.

This failure is quiet and dangerous: the staged region hashes to a plausible
value rather than reading back empty, so any experiment that skips
verification silently runs against garbage. Always `h713_mips verify` after
staging and before `start`, `probe-ready`, or `probe-trace`.

The lifecycle verbs below still reset by design. `fastboot reboot bootloader`
writes the same one-shot `0xb007c0de` marker to RTC GP7 (`0x0709011c`) as Linux
`reboot bootloader`; preboot consumes and clears the marker, disables autoboot,
and leaves the board at the U-Boot prompt. Use it to *reach* a prompt, not to
preserve anything in DRAM.

Power the board down through the same PSCI path used by Linux:

```
fastboot oem poweroff
```

The command acknowledges the host before powering off. A physical power cycle
is required afterward.

## Method 4 — cold recovery via FEL

Hold the **FEL button** at power-on to enter the BROM's USB FEL mode, then use
`sunxi-fel` (from the `external/sunxi-tools` build).

**The H713 FEL BROM does not stall on large bulk transfers** (corrected
2026-07-29). That earlier conclusion was a misdiagnosis, and the chunking
workarounds built on it have been removed. Measured on hardware: 48 KiB in a
single bulk request, 92.4 ms, ~530 KB/s, read back byte-identical. The link is
full-speed USB 1.1 with **64-byte** bulk packets, not high-speed 512.

What actually caused the "stalls": a raw `sunxi-fel write` bypasses the
swap-buffer relocation the SPL loader does, so a write based at `0x104000` runs
through the BROM's own IRQ stack (`0x105000`) and BSS (`0x10b300`). That kills
the BROM's USB stack mid-transfer and looks exactly like a bulk stall — timeout,
device still in `lsusb`, every later command hangs. `sunxi-fel` now refuses such
writes with an explicit error (see [reference/h713-fel-notes.md](reference/h713-fel-notes.md)).

### Recovering a clobbered first stage (verified 2026-07-29)

This is the procedure that works. It needs only a 64 KiB FEL transfer and no
host-side U-Boot upload.

1. Regenerate the payload — our own SPL, the first 32 KiB of the image whose
   U-Boot proper is already on eMMC:

   ```
   python3 - <<'EOF'
   d = open('build/out/u-boot-sunxi-with-spl-ddr3.bin','rb').read()[:32768]
   with open('external/u-boot/arch/arm/mach-sunxi/h713_spl_payload.h','w') as f:
       f.write("static const unsigned char h713_spl_payload[] = {\n")
       for i in range(0, len(d), 12):
           f.write("\t" + " ".join(f"0x{b:02x}," for b in d[i:i+12]) + "\n")
       f.write("};\n")
   EOF
   ```

2. Build the restore SPL:

   ```
   build/uboot-build.sh "$PWD/build/uboot-felmmc" hy200_h713_felmmc_defconfig spl/sunxi-spl.bin
   cp build/uboot-felmmc/spl/sunxi-spl.bin build/out/h713-restore-spl.bin
   ```

3. Power on holding the **FEL button**, then:

   ```
   external/sunxi-tools/sunxi-fel version
   external/sunxi-tools/sunxi-fel -p spl build/out/h713-restore-spl.bin
   ```

   UART should show `=== H713 SPL RESTORE ===`, the mmc scan, and
   `wrote 64/64 RESTORED-OK`.

4. Power-cycle. The board boots from eMMC again; reflash the full image with
   `run fastboot_mode` + `fastboot flash uboot ...`.

Why it works: sectors 16..79 are the only range a first stage occupies, and
U-Boot proper at sector 80 survives, so restoring the SPL reconnects an intact
chain. The hook runs after the SPL framework has already brought eMMC up, and
picks the device by scanning for a non-zero `lba` — **mmc0 is the absent SD
slot here**, and using it fails with "Card did not respond to voltage select".

The 64 KiB upload goes through the SPL loader, which relocates around the
BROM-reserved regions, so it is unaffected by the raw-write hazard above.

**Known gap — `sunxi-fel uboot` does not work on H713.** Loading the SPL alone
is reliable (`sunxi-fel spl ...` returns and FEL still responds afterwards), but
transferring U-Boot proper fails, and the transfer completes yet the SPL still
sits at "Trying to boot from FEL" — so the **post-SPL handoff itself is broken**,
not just the transfer. `exe` and `reset64` at `CONFIG_TEXT_BASE` do not start it
either. Use the restore SPL above instead. Worth revisiting if anyone wants
`uboot` working: the `fel_stash` continuation path, which is what should resume
the SPL after the host writes U-Boot.

Two of the symptoms once cited here have since been explained and should not be
read as evidence about the handoff (2026-07-29): the `usb_bulk_recv() ERROR -8:
Overflow` was an undersized bulk IN buffer, now fixed; and the
`usb_bulk_send() ERROR -7` timeouts came from the raw-write hazard above.
**This gap has not been retested since those fixes landed** — do that first
before investigating `fel_stash`, because the transfer half of the problem may
already be gone. U-Boot proper also lands in DRAM, which is its own unresolved
issue on this board.

**Un-bricking a clobbered first stage:** the local-only recovery SPL
(`local/0001-...LOCAL-ONLY.patch`, embeds the vendor boot0 — never published)
FEL-loads once, rewrites the vendor boot0 to eMMC sector 16, and halts; power
cycle to boot the stock firmware. `git am` that patch into `external/u-boot` to
build it.

The same tool recovers **our** first stage instead, which is usually what you
want: replace `board/sunxi/h713_vendor_boot0.h` with an `xxd -i`-style array of
the first 32 KiB of `u-boot-sunxi-with-spl-ddr3.bin` and build
`hy200_h713_recovery_defconfig`. That range is sectors 16..79, and U-Boot proper
lives at sector 80 (`CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x40` plus
`DATA_PART_OFFSET=0x10`), so restoring only the SPL reconnects an otherwise
intact chain. Apply the patch with `git apply`, not `git am`, so the vendor blob
never reaches a commit.

**Do not restore stock boot0 alone.** It comes up and inits DRAM correctly but
then reports `bad magic` / `Loading boot-pkg fail(error=4)`: it looks for its
payload at an offset inside the range our own writes occupy, and it also finds
its MMC info region damaged (`region magic is not right`). Restoring stock needs
the whole original boot region from a pre-flash capture, not just sector 16.

## Standalone boot (power-on → Debian)

To boot the kernel from eMMC with no host attached — flash the FIT to `boot_a`
and set a U-Boot `bootcmd` — see [standalone-boot.md](standalone-boot.md)
(`tools/flash-standalone.sh`).

## Method 5 — boot stock temporarily, to read its U-Boot console

Worked out 2026-08-05. The goal is **not** to run Android — it is to see the two
seconds of stock U-Boot output that say whether the vendor's own backlight setup
succeeds (`Display fastlogo finish!`) or fails (`Pwm enable fail:%d`,
`backlight enable fail:%d`, `Create backlight instance fail!`).

### ⚠ Prerequisite that does NOT hold as of 2026-08-05

This method was first written assuming stock's boot package was still intact
below the GPT, making it a single 32 KiB write. **That assumption is false on
this unit.** Bench-checked, all with `mmc dev 1;` prefixed on the same line:

| sector | expected | actually contains |
| --- | --- | --- |
| `0x6000` (12 MiB) | `sunxi-package` | high-entropy data, unidentified |
| `0x8020` (32800, the Allwinner standard) | `sunxi-package` | records `1,3,4,0x202` / `1,3,4,0x7d`, unidentified |
| `0x10000` (32 MiB) | `sunxi-package` | all zeros |

Those three sectors are the only ones stock `boot0` references as literals
(offsets `0x5d80`, `0x5e68`, `0x5e6c` in `boot0_sdcard.fex`; the pair 32800 /
24576 is `{start_sector, max_size_sectors}` — the 24576 is a **size**, 12 MiB,
which is where this document's original "12 MiB boot package" claim came from
and it was a misreading).

So restoring stock now requires writing **both** `boot0_sdcard.fex` (sector 16)
**and** `boot_package.fex` (sector 32800, inferred), the latter over data of
unknown purpose. **Take a real backup first** — see the warning below about how
easy it is to produce a fake one.

### The 12 MiB figure below is retained only for the layout argument

Stock's layout puts **boot0 at sector 16** and the boot package somewhere in the
reserved region ahead of the GPT. Our own image occupies sector 16 for ~940 KiB,
so:

| region | state |
| --- | --- |
| sector 16, first 32 KiB | **ours** — this is all that must change |
| 12 MiB boot package | **stock, untouched** — we have never written there |
| `boot_a`, `super`, `vendor_boot_a`, `dtbo_a`, `vbmeta*` | **stock, untouched** |
| `UDISK` (last partition) | our Debian rootfs |

So restoring stock boot0 is enough: it loads stock U-Boot from the intact boot
package, which runs fastlogo and prints what we need.

### Always put `mmc dev 1;` on the same line

The current MMC device resets to slot 0 between commands, and slot 0 is disabled
on this board (no SD). A bare `mmc read` then fails with `MMC Device 0 not
found` — but `md` afterwards happily prints whatever was already in DRAM, which
looks like plausible data. This wrecked three separate results on 2026-08-05,
including a `cmp.b` verify and, worse, a **backup**:

```
mmc read 0x48000000 0x8020 0x980     <- failed, device 0 not found
fatwrite mmc 1:2 0x48000000 backup_8020.bin 0x130000
1245184 bytes written in 95 ms       <- wrote 1.2 MB of uninitialised DRAM
```

That file is not a backup and restoring from it would destroy the region it
claims to protect. Always:

```
mmc dev 1; mmc read <addr> <lba> <cnt>; md.b <addr> 0x20
```

and confirm the `MMC read: ... blocks read: OK` line before trusting the dump.

### Do this first

Confirm the Android partitions really are intact — read-only, costs nothing:

```
part list mmc 1
```

**Verified 2026-08-05:** all 26 partitions present and matching
`sys_partition.fex` exactly (`bootloader_a` at LBA `0x12000`, `boot_a` 131072
sectors, `super` 4194304 sectors, `UDISK` last). Note `mmc 1:2` is
`bootloader_b`, which this project has repurposed to hold the MIPS artifacts, so
the stock B-slot resource is already gone.

Expect `boot_a`, `super`, `vendor_boot_a`, `misc`, `UDISK` and friends. If they
are gone, stop; stock will not boot and this method does not apply.

### To stock

`local/stock-boot/boot0_sdcard.fex` (32768 B, `eGON.BT0`), extracted from the
OTA package — see the evidence log for provenance.

```
run fastboot_mode
```

```
fastboot flash uboot local/stock-boot/boot0_sdcard.fex
```

Use the `uboot` alias, not `bootloader`, for the reason in Method 3. Then power
cycle — **not** `fastboot reboot bootloader`, whose RTC marker is consumed by
*our* preboot, which will no longer be there.

**Capture the UART from the first byte.** The interesting lines appear within
about two seconds, before Android starts.

### Then power off, and do not let Android settle

Once `Display fastlogo finish!` or a `Pwm enable fail` has been printed, cut the
power. Letting stock Android boot fully risks it reformatting `UDISK` — where
the Debian rootfs lives — and touching `misc`/`metadata`. Nothing in this test
needs userspace.

### Back to ours

Stock boot0 is now at sector 16, so our U-Boot is not running and its fastboot
is unavailable. Return via the **FEL button** and the procedure in Method 4,
which is verified, then rewrite:

```
fastboot flash uboot build/out/u-boot-sunxi-with-spl-ddr3.bin
```

Equivalently `mmc write 0x42000000 0x10 0x72d` after a `loady`, per Method 1.

### Risks, stated plainly

- **No eMMC backup exists on this machine** (see below), so the return path is
  "rebuild our image", not "restore a byte-exact copy". That is fine for the
  boot region, which is reproducible from source, and is *not* fine for anything
  else — so touch nothing else.
- If stock boot0 does not find a boot package it will hang. FEL recovers it.
- Android booting to completion is the one outcome that can lose real data. Pull
  power early.

## Safety

- Always name the board a flash ran on — feeding the projector's HY200 QZ713_V2 (LPDDR3) params to the
  HY200 (DDR3) board trains "OK" but reads hang.
- **There is no full eMMC backup on this machine.** This document previously
  claimed one existed in `local/h713-lab`; it does not, and nothing over 200 MB
  is there (checked 2026-08-05). The retail OTA package at
  `~/Documents/projector_firmware/H713 Magcubic projector.20250922.093247/update.img`
  is currently the only source of stock images. Taking a real backup before the
  next destructive operation would be cheap insurance.
