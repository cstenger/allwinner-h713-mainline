# Plan: U-Boot proper without the reset-time lamp (review L2)

Status 2026-10-16: step 1 done (rescue copy at `0x4a0c00`, verified). **Step 2 PASSED on attempt 5**: the FEL rescue SPL now marks the SRAM SPL header as an eMMC boot, and the unchanged installed U-Boot proper comes up from the rescue slot to a prompt (the first four attempts hung in `env_init()`, located with a debug-UART build). **Step 3 done**: lamp-off proper `41b1e1bd…` installed at `0x49ac00`, warm and cold boots verified (serial, board state, operator: lamp dark until the logo, audio works). **Complete.** See [evidence](hdmi-evidence/2026-10-16-uboot-lamp/README.md).

## What changes

`CONFIG_H713_POWERON_LIGHT_FAN=n`. U-Boot proper's `board_init()` stops driving
PB5 (lamp + fan) high at reset. The guarded startup script then turns PB5 on
once the logo is latched (already installed and verified), and Linux's PB5 hog
keeps it on. The lamp should come on exactly once, onto the logo.

Fan consequence: the fan starts when the logo appears instead of at reset,
roughly 10–15 s later in real time (the cold path spends that time in U-Boot,
mostly idle). The lamp is never lit without the fan; they remain one line.

**If the boot stops at the U-Boot prompt** (script failure, `bootdelay`
interrupt, `reboot bootloader`), the lamp and fan stay **off** until something
drives PB5. The script's failure branches already run `gpio set PB5`; a manual
`reboot bootloader` session does not. That matters for a sealed unit left at
the prompt: run `gpio set PB5` there, or keep the `bootloader` mode for the
bench.

## The build

| | |
| --- | --- |
| source | `external/u-boot` at `320a17f71d4`, as a worktree in `build/uboot-src-320a17f`. The installed image is `a1358432003c-dirty` built 2026-09-24 10:58:54; `320a17f` was committed 52 s later and is the only change on top (guarded trace counters). HEAD's `9d35a4e` (2026-09-25) has never been flashed and is excluded. |
| defconfig | `hy200_qz713df_a1_defconfig` (`config/versions.env`) |
| BL31 | `build/out/bl31.bin`, v2.15.0, Jul 27 (the version the installed SPL banner shows) |
| A (control) | `build/uboot-lamp-A/`: config unchanged |
| B (candidate) | `build/uboot-lamp-B/`: `# CONFIG_H713_POWERON_LIGHT_FAN is not set` |
| compiler | clang 23.1.1 (installed image: clang 22.1.8). Kernel builds already use 23. |

Inspection:

- U-Boot proper FIT = bytes `32768..` of `u-boot-sunxi-with-spl.bin`:
  **920,169 bytes for A and B, identical to the installed FIT header size**.
- A vs B, per symbol (`llvm-nm -S`): **only `board_init` differs**. Its
  disassembly loses exactly `gpio_request(37, …)` and
  `gpio_direction_output(37, 1)` (GPIO 37 = PB5) plus the frame setup they
  needed.
- SPL A vs B: 897 bytes differ, all build timestamp; identical symbols and
  sizes. **The SPL is not written.**
- Source identity: the printable-string tables of the installed proper and A
  differ only in the version banner, the linker version and code-byte noise;
  B vs A additionally lacks only the `"fan-bl-power"` GPIO label.
- The installed proper is the documented baseline: the 2026-10-07 audio
  trial restored "the exact original U-Boot" and verified it as
  `c882461d…` over the 1,798-sector region, which is what is on eMMC now.

| artifact | SHA-256 |
| --- | --- |
| `build/out/uboot-proper-lamp-off-1798.bin` (B, padded to 1,798 sectors) | `41b1e1bd8533e88853295071e4b34a5a77098dfcca2b556c46924ed385c9b9ff` |
| `local/h713-lab/uboot-backup-20261016/proper-installed-1798.bin` (rescue copy / rollback) | `c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7` |
| `build/out/h713-rescue-spl.bin` (FEL rescue SPL, with the header fix) | `dab3b1585a8d05d30d87a57795fa505409304ce7287cfa58d5c8deed1bcf75f0` |

## Backups already taken (read-only, from Linux)

`local/h713-lab/uboot-backup-20261016/`:

| file | source | SHA-256 |
| --- | --- | --- |
| `proper-lba49ac00-2MiB.bin` | LBA `0x49ac00`, 4096 sectors (FIT 920,169 B + zeros) | `27a685f4…` |
| `spl-lba10.bin` | LBA `0x10`, 64 sectors | `cb9da874…` |
| `env-lba49ec00.bin` | LBA `0x49ec00`, 128 sectors | `de2f2560…` |

The on-board SPL stash at `0x49cc00` (`b4ff1867…`) is **older** than the live
SPL; do not use it as a recovery source.

## Write procedure (the established one, as on 2026-09-23/24)

All from the board's Linux, the same path used for every U-Boot proper since
the split layout:

0. Stage B's proper (`B[32768:]`, padded to 1,798 sectors) on the board; verify
   its SHA-256 there.
1. **Rescue copy.** Write the *installed* proper (first 1,798 sectors of the
   backup) to the spare slot **LBA `0x4a0c00`** (`empty` + 12 MiB; verified all
   zeros, inside `empty`, which ends at `0x4a2400`). Read back and compare.
2. **Prove the rescue before relying on it** (operator, below). Only then
   continue.
3. Write B's proper: 1,798 sectors at LBA `0x49ac00`, `conv=fsync`. Read back
   and compare to the padded image. Nothing at `0x10`, the env or the kernel
   is touched.
4. Warm reboot with serial captured: banner must read
   `g320a17f71d41`, and `gpio` / `h713_disp` / startup script must behave as
   in today's `warm-boot-serial.log`. Then a filmed cold cycle.

## Recovery

| failure | recovery | proven? |
| --- | --- | --- |
| B boots but misbehaves | from Linux or B's prompt, write the backup proper back to `0x49ac00` (same procedure) | yes, procedure used before |
| B's U-Boot proper does not start (SPL prints `Trying to boot from MMC2`, then nothing) | **FEL rescue SPL** (`build/out/h713-rescue-spl.bin`): our SPL with `CONFIG_H713_SPL_FORCE_MMC=y`, the new `CONFIG_H713_SPL_RESCUE=y` (skips the sector-16 restore-and-halt hook; [patch](reference/uboot-h713-spl-rescue.patch), worktree only) and `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x4a0c00` (confirmed in `spl_mmc_load_image`'s disassembly). It writes nothing. Hold FEL, `sunxi-fel -p spl build/out/h713-rescue-spl.bin`: the SPL loads the **installed** proper from the rescue slot → known-good prompt → `mmc read 0x42000000 0x4a0c00 0x706; mmc write 0x42000000 0x49ac00 0x706` → reset | **yes, 2026-10-16** (attempt 5: installed proper from the rescue slot to a prompt; read half of the restore rehearsed and compared) |
| SPL itself damaged | not possible from this plan (LBA `0x10` is never written); if it happens anyway, the documented restore SPL (`docs/flash.md` Method 4) | yes, 2026-07-29 and 2026-09-29 |

Why a new rescue path: `sunxi-fel uboot` does not work on H713, the restore SPL
only rewrites sectors 16..79, and the vendor round trip reaches Android
without root, which cannot write raw eMMC. Without the rescue slot, a
non-starting proper would have no proven way back.

### Step 2, the rescue rehearsal (operator)

Needs a USB cable from the host to the board's OTG port and the FEL button.

1. Board powered off; serial connected.
2. Hold FEL, apply power, release. Host: `sunxi-fel version` shows the H713.
3. Host: `sunxi-fel -p spl build/out/h713-rescue-spl.bin`.
4. UART must show the rescue SPL banner (`g320a17f71d41-dirty`, Oct 16), then
   `U-Boot 2026.07-rc5-ga1358432003c-dirty (Sep 24 2026 - 10:58:54 -0700)` —
   the copy from the rescue slot — and a prompt.
5. `reset` (USB unplugged first, as always for a cold path) → normal boot.

Pass = the installed U-Boot came up from `0x4a0c00` over FEL. Only then step 3.

## Rollback of the whole change

Write `proper-lba49ac00-2MiB.bin`'s first 1,798 sectors back to `0x49ac00`.
The startup script's lamp gating is independent and stays.
