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
`sunxi-fel` (from the `external/sunxi-tools` build). Note the H713 FEL BROM
stalls on large bulk transfers — our sunxi-tools carries the 16 KiB-cap fix that
makes loading a >~48 KiB SPL reliable (see [reference/h713-fel-notes.md](reference/h713-fel-notes.md)).

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

Requires the `fel_lib` stall fix in `external/sunxi-tools` (commit "survive
zero-progress bulk stalls"); without it the 64 KiB upload aborts part-way and
the SPL runs half-loaded, hanging right after its first print.

**Known gap — `sunxi-fel uboot` does not work on H713 (2026-07-29).** Loading
the SPL alone is reliable (`sunxi-fel spl ...` returns and FEL still responds
afterwards), but transferring U-Boot proper fails: the upstream build reports
`usb_bulk_recv() ERROR -8: Overflow` and even our patched build times out with
`usb_bulk_send() ERROR -7` partway through the ~790 KB payload. `exe` and
`reset64` at `CONFIG_TEXT_BASE` do not start it either. Even with the stall fix
the transfer completes but the SPL still sits at "Trying to boot from FEL", so
the **post-SPL handoff itself is broken**, not just the transfer. Use the
restore SPL above instead. Worth revisiting if anyone wants `uboot` working:
the `fel_stash` continuation path, which is what should resume the SPL after
the host writes U-Boot.

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

## Safety

- Always name the board a flash ran on — feeding the projector's HY200 QZ713_V2 (LPDDR3) params to the
  HY200 (DDR3) board trains "OK" but reads hang.
- A full eMMC backup exists in `local/h713-lab` (do not commit — proprietary).
