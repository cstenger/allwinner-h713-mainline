# LPDDR3 projector bring-up plan (`HY200_QZ713_V2`)

_Drafted 2026-11-18. Supersedes the four bullets of roadmap Phase 3._

The bench board (`HY200_QZ713DF_A1`, DDR3 624 MHz) is qualified end to end.
The projector (`HY200_QZ713_V2`, LPDDR3 720 MHz, captures call it "board A")
has never run a byte of ours. That is also true of well0nez's tree: their
`boards/hy200-qz713-v2` is `profile-only`, which means a description and no
boot. So we are first on the LPDDR3 path of `dram_sun50iw12.c`.

## Status (2026-11-18, evening)

The projector board is in the bench rig with UART, the FEL button, USB, panel,
speaker, light, fan and IR attached. Nothing has been written to its eMMC.

- **Phase 1 done.**
  - A fresh adb capture is at `local/h713-lab/captures/board-a/board-a-mmcblk0-20261118.img`.
    It is 7 818 182 656 B, sha256 `debf1fea…`, and all 30 chunks verified on
    the board. boot0 and the GPT are identical to 06-22.
  - `adb reboot efex` reaches the BROM's FEL mode with no button: stock
    boot0 sees RTC GP2 `0x5aa5a55a` and branches to `0x20`.
  - SID `03400042:2c004818:01059514:5c821e57`.
- **Phase 2 step 1 done.**
  - The LPDDR3 SPL over FEL prints `DRAM: 1024 MiB`.
  - A 32 MiB random pattern written over FEL read back identical at
    `0x42000000` and `0x7c000000`.
  - Rule: run one `sunxi-fel spl` per FEL session. The return to FEL leaves
    the BROM at EL1, and the next SPL hangs.
  - Read DRAM back in pieces of 1 MiB or less: one 32 MiB read failed in
    libusb and wedged FEL.
- **Reboot to FEL on our stack.**
  - U-Boot 0008 and kernel 0029 add `reboot fel` / `reboot efex`.
  - The SPL hook was FEL-tested on this board. The Linux end-to-end path
    waits for Phase 4.
- **U-Boot proper over FEL works (2026-11-19).** That was the H713 "known
  gap" in `docs/flash.md`.
  - `tools/fel-uboot.sh build/out/h713-v2-felrescue.bin` gets from a fresh
    FEL session to the `=>` prompt, all in RAM.
  - The sequence: the rescue SPL (U-Boot 0009) trains DRAM, then
    warm-resets the core. Stock boot0's efex flag returns the board to FEL
    at EL3. The script writes the SRAM eGON header (the BROM zeroes it),
    loads BL31 and proper, and runs `reset64`.
  - Proper reports `DRAM: 1 GiB` and the V2 model, and falls back to the
    default environment on a bad CRC. Never `saveenv` there.
  - A fresh FEL session without the button: write GP2 `0x5aa5a55a`, then
    reset with the watchdog (`0x02051010`/`14` = `0x16aa0001`, `0x0205100c`
    = `0x14af`).
  - `mtest 0x40100000 0x7ae00000 0 1` (alternate test with bit-flip, 939
    MiB) ran on 2026-11-19: **1 iteration, 0 errors**, in 16 min. The
    rescue proper is built with `CMD_MEMTEST` + `SYS_ALT_MEMTEST`.
  - Phase 2 still needs reliable DRAM init across 5 or more cold boots, and
    a long stress run (`memtester` in Phase 3).
  - From the FEL U-Boot prompt, `mw.l 0x07090108 0x5aa5a55a; reset` gives
    a fresh FEL session with no button.
- The black panel under stock was a disconnected ribbon cable, now fixed.

## What we already know (offline, from the 2026-06-22 capture)

Each item was checked on 2026-11-18 against
`local/h713-lab/captures/board-a/` and the matching bench capture.

| Fact | Evidence | Consequence |
| --- | --- | --- |
| The GPT is **byte-identical** to the bench's. | `sgdisk -p` on both full images | The same layout, slots, `switch_vendor` scheme and UDISK rootfs location apply. |
| boot0 at LBA 16 is `eGON.BT0` with `dram_clk 720`, `type 7`. | Header decode | Matches `hy200_qz713_v2_defconfig`. well0nez's independent 2025-07-10 image agrees word for word (issue #3). |
| The stock DTBs (TOC1 and `vendor_boot_a`) differ from the bench's in **three places only**. | `dtc` diff, 20 lines | See the next table. Everything else, including the audio, HDMI, IR, Wi-Fi, accelerometer, PWM and regulator nodes, is the same. |
| `display.bin` is a **third build**: 1 256 216 B, `16c74a28…`. | `bootloader_a` FAT | Not the bench's `4380f1b3…` (1 255 696 B), and not well0nez's 2025-07-10 `4628cbaf…`. `LogoRegData.bin`, `database.TSE` and `ProjectID_0x0034.TSE` also differ. `projecttable.TSE` is the same. |

The stock device-tree deltas:

| Signal | Bench (A1) | Projector (V2) | Our tree today |
| --- | --- | --- | --- |
| `panel_power_en` | PF6 | **PH19** | The shared dtsi says PH19 (an HY310 inheritance), and bench patch 0183 overrides it to PF6. **U-Boot hard-codes `SUNXI_GPF(6)`** in `h713_mips.c` (~5 sites). |
| Fan tach `fg-gpio` | PH13 | **PH17** | The dtsi says PH17, and the bench overrides it. |
| `motor_ctr` | okay | disabled | 0214 already defaults it to disabled. |

The V2 hardware is therefore the bench plus two pin moves. The V2 kernel DTS
should be the A1 DTS without those two overrides. It should not be the bare
12-line dtsi wrapper we have now.

**Provenance trap:** `local/mips-display/research/bootloader_fat/` holds the
*projector's* `LogoRegData`, `database.TSE` and `ProjectID_0x0034.TSE`
(the hashes match board A), and the bench's own are in `board-b-mips/`. Before
reusing a conclusion from early display research, check which set it read.

## Lessons from well0nez's multi-board tree (`40cb040`, 2026-11-17)

They now describe ten boards. Their structure in brief:

- **`boards/<id>/`** holds `board.env` (machine-readable facts: status, DTB,
  U-Boot base and image name), `uboot.config` (the DRAM words as a fragment)
  and a `README.md` that gives a **source for every number**. Variants
  (`variants/<fw>/variant.env`) cover one PCB that shipped with different
  stock firmware (DRAM clock, `display.bin`).
- **U-Boot uses a base defconfig per board plus role fragments**
  (release/installer/probe) merged on top, so boards cannot drift in layout.
  Their README notes that **our** `hy200_qz713_v2_defconfig` is still a
  bring-up config: environment at `0x400000`, no U-Boot sector, no display.
- **Status follows an honesty rule** (`verified` / `profile-only` /
  `partial`, and `verified` requires a named person, board and date).
  `boards/check.sh` enforces it mechanically and also checks that the
  fragment's DRAM clock matches the profile.
- **The `h713_probe` FEL payload is read-only.** It prints the boot0 DRAM
  header from the device itself. This is how they take DRAM words from the
  unit and never from its name. They note that `para2`/`tpr13` are patched by
  the flashing tool, so only an on-device boot0 is authoritative. Ours came
  from the device, so it is.
- **Test images are pinned to a board** (`test_for`), and the installer
  refuses them on any other board.
- **Their timing review of our LPDDR3 words:** they are LPDDR3 at 720 MHz field
  by field, but tRP is 19.4 ns, below the 21 ns all-bank minimum, and tREFI is
  0.3 % long. These words are the device's own, so they are not a reason to
  change anything. They are a reason to run a real memory stress test, not just
  check for `DRAM: 1024 MiB`.

**What we take from this:** a lightweight `boards/` layer and the
base-plus-fragment U-Boot config. We also take a board-identity check in every
installer, so that no bench-pinned bundle can land on the projector.
**What we skip:** installer profiles, release images and the variant machinery.
We have two boards and no strangers' units.

## Constraints that carry over

- Brick avoidance comes first. Nothing is written to the projector's eMMC
  until our SPL and U-Boot have run from FEL on *that* board, a fresh full
  capture exists, and a restore SPL **embedding the projector's own boot0**
  has been proven by FEL. The bench restore SPL embeds the DDR3 boot0, and
  writing it to the projector is the classic "trains OK, reads hang".
- Keep Android bootable as a reference until the project ends
  (`switch_vendor` scheme, vendor boot0 at LBA `0x100`).
- A cold boot means unplugging the serial adapter and all USB, then leaving
  the power off for at least 1 minute.
- Every result names the board it ran on.

## Phases

### Phase 0: offline preparation (no projector needed)

1. **Board layer.** Add `boards/hy200-qz713df-a1/` and
   `boards/hy200-qz713-v2/`, each with `board.env`, `README.md` (sources) and
   the vendor-input manifest (the counterpart of `config/production-vendor.json`).
   `BOARD=ddr3|lpddr3` stays as aliases. Add a `check.sh` that verifies the
   defconfig DRAM type and clock against the captured boot0, and the DTB name
   against the board.
2. **U-Boot config de-drift.** Make V2 = the shared H713 base + a V2 fragment
   holding only the DRAM words and the DT. Today V2 is missing `ENV_OFFSET`
   `0x93d80000` (it would `saveenv` to 4 MiB), the `U_BOOT_SECTOR` `0x49ac00`
   layout, `H713_MIPS_BOOT`, `H713_POWERON_LIGHT_FAN`,
   `H713_VENDOR_CHAINLOAD`, `PREBOOT` (the fastboot/bootloader-hold RTC
   handshake and `h713_disp auto 0x34 logo`), `CMD_GPIO`/`CMD_POWEROFF` and
   fastboot `oem poweroff`.
3. **U-Boot panel power from the DT.** Replace the hard-coded `SUNXI_GPF(6)`
   with the `panel_power_en` lookup (U-Boot already consumes the kernel DTS).
   Bench behaviour must stay byte-identical; prove it on the bench.
4. **V2 kernel DTS.** Factor the A1 board content into a shared
   `sun50i-h713-hy200-qz713.dtsi` and keep A1 and V2 as thin files that differ
   only in panel power, fan tach and model/compatible. Build both and diff the
   DTBs: the only differences should be those pins.
5. **Recovery binaries for V2.** Build the LPDDR3 FEL SPL, a **V2 restore SPL**
   embedding board A's boot0 (from the capture, verified by header and
   checksum), and a V2 rescue SPL. Add a guard that refuses to build a restore
   SPL whose embedded boot0 DRAM type disagrees with `BOARD`.
6. **Board identity in installers.** `tools/hdmi/*` and the FIT/startup
   installers pin bench hashes. Add a check of the DT `compatible` plus the
   on-eMMC boot0 DRAM type, and refuse on mismatch, before any guarded write.
7. **The `display.bin` decision prep.** Our U-Boot MIPS patches (stability
   trampolines, comm-trace caves) are keyed to `4380f1b3…`, with an
   expected-word check per site. Confirm what U-Boot does on a mismatch: it
   should refuse the patch set and still launch. It must not abort or hang. Then
   list the options:
   - (a) Run the bench `display.bin` on the projector with the projector's own
     TSE/LogoRegData/`panel_config.ini`. All patch sites carry over.
   - (b) Run the projector's own `16c74a28…`. The patches need re-locating.
   The test in Phase 4 decides between them. Diff the two binaries now to size
   option (b).

Exit: both boards build from one tree, the bench is unchanged (DTB and U-Boot
regression on hardware), and the V2 artifacts and guards are in `build/out/`.

### Phase 1: access and a read-only look at the projector

1. **Physical access.** Can we reach UART pads, the FEL button and the USB OTG
   port without opening the case? This decides the rest of the route.
2. **If the projector is sealed: FEL by software.** Allwinner's vendor U-Boot
   normally honours `reboot efex` (PhoenixSuit's entry). Prove `adb reboot efex`
   on the **bench running the vendor stack** first, then on the projector. The
   fallback is the OTA → `env_b` lever (AOSP testkey, see memory), which again
   is proven on the bench first.
3. **FEL identity.** `sunxi-fel version` and SID. Then run a read-only probe
   that reads LBA 16 and confirms boot0 is still the 06-22 capture. Use our own
   probe or adapt `h713_probe`.
4. **Fresh full eMMC capture** over `adb` (the proven route), because the
   06-22 image predates five months of Android use. It goes to `local/` only.

Exit: a known recovery vector on this unit, a fresh capture, and nothing
written.

### Phase 2: DRAM over FEL

1. FEL-load the LPDDR3 SPL. Look for `DRAM: 1024 MiB` and its training log,
   and compare against stock boot0's `DRAM simple test OK`.
2. FEL-load U-Boot proper (the rescue-SPL path). Run `mtest` over a few
   hundred MiB.
3. If training fails: re-read the boot0 header off the device. Then bisect only
   `tpr13` bit 1 (packed versus computed timings) and the pad settings. Never
   borrow DDR3 values.

Exit: reliable DRAM init across five or more cold boots from FEL.

### Phase 3: Linux from RAM, still no eMMC writes

1. Boot the V2 FIT with an initramfs over FEL or `fastboot boot`. Console,
   eMMC detection at HS400 (read-only), USB and `memtester` over about 800 MiB
   for 1 hour or more.
2. cpufreq and thermal: re-check the 1296 MHz ceiling. The 1416 MHz corruption
   on the bench may have been DRAM-related, so it is worth retesting there.
   Do not raise the limit without a long stress run.

Exit: memtester clean, and no kernel errors across a cold and a warm boot.

### Phase 4: install, then the display

1. Install the bench layout: our boot0 at LBA 16, vendor boot0 at `0x100`,
   U-Boot at `0x49ac00` plus the spare at `0x4a0c00`, Debian on UDISK. Read
   every region back after writing. First prove `switch_vendor` → Android →
   FEL restore on this board.
2. Display. Panel power on PH19, then the console on the panel, then the MIPS
   launch and logo. Run the `display.bin` option (a) and (b) test from
   Phase 0.7 here: one cold boot each, comparing the MIPS state and the logo.
3. Then the production stack: startup/health scripts, video planes,
   letterbox/mirror, VE decode matrix (AV1 at PLL_VE ≤ 432 MHz). The DRAM
   bandwidth differs, so rerun the eMMC 0206/0207 loaded-read bench. It is
   DRAM-contention sensitive.

### Phase 5: the remaining hardware

In order: fan (tach PH17; PB5 also powers the fan) → audio and speaker (the
zero-pop requirement and mic rig) → HDMI input and audio capture → IR/keys →
Wi-Fi/BT → accelerometer and auto-keystone (the node matches stock; verify
SC7A20 on TWI1 `0x18`) → standby. **Re-qualify standby completely:** any path
that puts DRAM into self-refresh is DRAM-type-specific. Finish by running
`docs/production-qualification-plan.md` on V2, then mark the board `verified`
with date and boot ID.

## Open questions for Chris

1. How physically accessible is the projector (UART, FEL button, USB OTG)?
   Can it be opened? This picks the Phase 1 route.
2. Is it still on stock Android with `adb` available, unchanged since 06-22?
3. Is it acceptable to leave its Android removable at project end, as on the
   bench?
