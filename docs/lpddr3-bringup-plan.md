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
- **Phase 3 step 1: Linux from RAM over FEL boots (2026-11-19).**
  - `tools/build-ram-initramfs.sh` builds a busybox initramfs from a release
    `rootfs.tar`.
  - `EXTRA=` in `tools/fel-uboot.sh` loads the kernel FIT, the initramfs and
    the V2 DTB alongside U-Boot. All five images read back identical, in
    46 s.
  - `bootm` with the V2 DTB reaches a shell:
    - Linux 6.18.38, `HY200 QZ713_V2`, 4 CPUs, `MemTotal` 954 496 kB.
    - eMMC at **HS400** (`FNX2MB`, 7.28 GiB, all 26 partitions seen,
      nothing mounted).
    - The kernel feeds the 16 s watchdog until userspace opens it.
    - CPU 50 °C at idle.
  - The only errors are expected: no display (`h713_disp` was not run), the
    Wi-Fi device-link notice, and no `regulatory.db`.
  - **Kernel memtest passes (2026-11-19).**
    - Built with `KERNEL_CONFIG=memtest tools/build/build.sh kernel`
      (`patches/kernel/board/memtest.config`, `CONFIG_MEMTEST=y`). Booted
      over FEL with `memtest=17`.
    - Result: 17 patterns × 11 free ranges, **948.8 MiB of 1024 MiB per
      pattern**, 0 `bad mem` reports. It took about 54 s, and available
      memory was the same as without memtest.
    - This tests stuck bits and patterns at boot, not timing margin under
      load. That is the `memtester` run below.
  - **memtester passes (2026-11-19).**
    - Debian trixie `memtester_4.7.1-1_arm64.deb`, checked by signature
      (InRelease, Debian 13 release key) and hash chain (Packages.xz, .deb).
      Copies and hashes are in `local/recovery/2026-11-18-v2-bringup/memtester/`.
    - Added to the initramfs with `BIN=... tools/build-ram-initramfs.sh`;
      normal (non-memtest) kernel, booted over FEL.
    - `memtester 800M` (800 MB locked): **3 full loops plus most of a 4th in
      66 min, 0 FAILURE**, no kernel errors. About 20 min per loop.
    - CPU 45.8 °C at start, settling at 56–57 °C, peak 60.1 °C.
    - Log: `local/recovery/2026-11-18-v2-bringup/linux-ram-uart.log`.
    - Phase 3 item 1 is met.
  - **Cold boot of the RAM kernel passes (2026-11-19).** Power, serial and
    USB off for 1 min or more, then FEL button. `tools/fel-uboot.sh` trained
    DRAM, re-entered FEL and verified every image. The U-Boot prompt came up,
    and `bootm` reached the shell about 13 s later (954496 kB, 4 CPUs, HS400
    eMMC, CPU 46.6 °C). dmesg has only the three expected errors above (no
    display, Wi-Fi device link, `regulatory.db`).
    Log: `local/recovery/2026-11-18-v2-bringup/linux-ram-cold-uart.log`.
  - **Warm boot of the RAM kernel passes (2026-11-19).** From that shell,
    `devmem 0x07090108 32 0x5aa5a55a; reboot -f`: stock boot0 printed
    `rtc[2] value = 0x5aa5a55a` and jumped to FEL, no button. The same
    `fel-uboot.sh` load and `bootm` reached the shell (HS400 eMMC, 46.7 °C)
    with the same three expected dmesg errors and nothing else. Same log.
  - **Phase 3 exit is met:** memtester clean, and no new kernel errors across
    a cold and a warm boot. Item 2 (re-check the 1296 MHz ceiling) is still
    open.
  - **1296 MHz all-core stress: silent reset at about 17 min (2026-11-19).**
    - Load: four `memtester 190M`, one pinned to each core,
      `scaling_min_freq=1296000`, RAM kernel after the warm boot. One sample
      a minute: temperature, frequency, vdd-cpu, FAILURE count.
    - 1296 MHz / 1058 mV until 72 °C. From then the 75 °C passive trip
      throttled the CPU across 1104/1200/1296 MHz (960/999/1058 mV) at
      73–76 °C. memtester: 0 FAILURE in 56 passed subtests.
    - Last sample 03:02:03 (1104 MHz, 73.4 °C). Stock boot0 started at
      03:03:00. Nothing in between: no oops, no panic (`panic=0` would have
      halted), no thermal message. That fits a hard hang caught by the
      16 s watchdog, or a supply reset.
    - Not yet known which. One candidate: our `regulator-ramp-delay = <2500>`
      (µV/µs, kernel 0028) against stock's `<0x19>` (25) for the same PWM
      buck. If the filtered PWM rail really settles in milliseconds, each
      upward DVFS step runs the new frequency on the old voltage for a
      while. Throttling made those steps frequent here; the 66-min
      single-core memtester stayed at 1296 MHz with none.
    - n=1. Log: `local/recovery/2026-11-18-v2-bringup/linux-ram-cold-uart.log`.
  - **Ramp-delay arms (2026-11-19): ramp delay is not the cause.** RTC GP2
    was armed before each run, so any reset lands in FEL and the next arm
    runs unattended.
    - A, repeat (ramp 2500, read back as `00 00 09 c4`): reset again after
      about 9 min. Last sample 1296 MHz, 72.8 °C, 0 FAILURE in 28 subtests.
    - B, stock ramp 25 (read back `00 00 00 19`, so a 98 mV step waits
      3.9 ms instead of 40 µs): reset about 8 s after the load started,
      while the CPU was still cool. The reset cut a console line mid-character
      and boot0 started in the same second. That is an immediate reset, not
      a hang followed by the 16 s watchdog.
    - Every time, boot0 found the GP2 flag and went to FEL. The RTC domain
      kept its power, so this was not a whole-board power loss.
    - Three resets at 17 min, 9 min and 8 s, from 50 to 76 °C, with
      memtester never reporting an error. That points away from DRAM, heat
      and the DVFS ramp, and towards a supply or reset event when all four
      cores are loaded. The 66-min single-core run never reset.
  - **Four cores fixed at 1008 MHz survive (2026-11-19).** Arm C: same load
    with `scaling_min_freq = scaling_max_freq = 1008000` (939 mV), so there
    were no DVFS steps. 35 min clean: 0 FAILURE in 112 passed subtests,
    65–72 °C (under the 75 °C trip, so no throttling), then a clean
    `reboot -f` into FEL.
    - So four-core load as such is fine at 1008 MHz. The resets need the
      1104–1296 MHz points, DVFS steps, or both. Arm B (reset 8 s after
      stepping up to 1296 MHz) suggests 1296 MHz under four-core load is
      enough on its own.
  - **Four cores at 1200 MHz survive (2026-11-19).** Arm D: `scaling_min_freq
    = scaling_max_freq = 1200000` (999 mV). 35 min clean: 0 FAILURE in 112
    subtests, 70–75 °C. The 75 °C trip stepped it down to 1104 MHz (960 mV)
    in at least 4 of 35 samples and back up to 1200, so 1104↔1200 DVFS steps
    were exercised too. Clean `reboot -f` into FEL.
  - **Conclusion so far:** on this projector, four-core load resets the
    board only when 1296 MHz (1058 mV) is in use. 1200 MHz holds, including
    with throttle steps. The **ceiling is 1200 MHz** until 1296 is shown safe.
    1296 at 1060 mV is the stock table's value too, so this unit may just
    lack margin there. A 1296 MHz arm at 1100 mV (the stock 1392 MHz
    voltage, under the bench's 1.127 V measured peak) would tell undervolt
    from something else.
  - **More voltage does not save 1296 MHz (2026-11-19).** Arm E: the V2 DTB
    with only `opp-1296000000` changed to 1100000 µV (read back 1100 mV
    on the board), min = max = 1296 MHz. It ran 1296 MHz for about 3 min,
    then the 75 °C trip cycled it through 1104/1200/1296. It **reset after
    17 min** (last sample 1200 MHz, 74.2 °C, 0 FAILURE in 56 subtests),
    and boot0 found the GP2 flag and went to FEL.
    - Arm D cycled through 1104/1200 for 35 min without a reset. Arm E, the
      same plus 1296 MHz with 42 mV more, reset. The fault follows the
      **1296 MHz point**, and 1058 → 1100 mV does not move it. Undervolt at
      1296 is unlikely; something tied to running at, or stepping to,
      1296 MHz (PLL_CPU setting, CPU/AXI divider) is more likely. Not
      diagnosed.
  - **⚠ Supply not controlled (noted 2026-11-19 afternoon).** The projector
    was probably on USB power, not its power block, for arms A–E (not
    certain). On USB power the bench reset-looped with this exact signature:
    an instant reset with no kernel message, at a current spike (AIC8800
    firmware load). The arm results also fit a supply limit: every reset arm
    drew the most current (1296 MHz; 1100 mV draws more than 1058 mV), and
    the lower-current arms (1200, 1008) held. **The 1200 MHz ceiling is
    unproven.** Rerun the 1296 MHz arm on the power block before changing
    any OPP.
  - **Bench arm at 1296 MHz: no reset, but not a test of 1296 (2026-11-19).**
    QZ713DF_A1 on its power block, booted from its eMMC (our 6.18.38 install),
    driven over UART only. memtester sent as base64 and its sha256 checked
    (`e4bd807b…`). Four `memtester 170M` (827 MB available under systemd),
    min = max = 1296 MHz, ramp 2500. 35 min, 0 FAILURE in 112 subtests,
    no reset.
    - But it reached 81.6 °C within 2 min, then ran at **85–92 °C**,
      throttled by the 85 °C trip to **480–1008 MHz** for nearly the whole
      run. 1296 MHz appears in one sample. Trips are 75/85/105 °C. Idle
      after the stop was still 82 °C. The bench fan was unplugged, but it
      sits on the lamp's cooling block and does little for the SoC, so the
      bench simply has less SoC cooling than the assembled projector.
    - So neither board has a valid 1296 MHz result yet: the projector's
      supply was not controlled, and the bench was thermally limited. A valid
      bench arm would need added SoC cooling (a heatsink or airflow on the
      SoC), not the fan.
  - **On its power block the projector holds 1296 MHz: arms A–E were the
    supply (2026-11-19).** Arm F repeats arm A exactly (stock V2 DTB,
    1296 MHz / 1058 mV, ramp 2500, four `memtester 190M`, GP2 armed) with
    the projector on its power block. **35 min, no reset**, 0 FAILURE in 112
    subtests, 58–76.5 °C. The 75 °C trip cycled it through 1104/1200/1296
    (1296 MHz in 12 of 35 samples), the same pattern arm A reset under after
    9 min. Clean `reboot -f` into FEL.
    - The resets in arms A, B and E were the USB supply, not 1296 MHz. That
      also explains why the higher-current arms reset and the lower ones did
      not. **The 1296 MHz ceiling stands; no OPP change.**
    - **Phase 3 item 2 is met** (n=1 on proper power): memtester clean at the
      1296 MHz ceiling, with throttle steps, on the power block.
    - **Rule for these boards: run stress tests on the power block, and
      record the power source with the result.** USB power cannot carry
      four cores plus DRAM traffic at 1296 MHz, nor the bench's AIC8800
      firmware load.
  - Linux → FEL with no button: `devmem 0x07090108 32 0x5aa5a55a; reboot -f`
    (stock boot0 is still the first stage).
  - Still to do: a cold boot and a warm boot of the RAM kernel.
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

**Gate before the first eMMC write (checked 2026-11-19):** done — our SPL and
U-Boot from FEL on this board, the fresh capture, and the V2 restore SPL
(below), proven on this board, and the Phase 0.2 V2 config de-drift (U-Boot
0011: shared `configs/hy200_h713.config`; bench `.config` identical; V2 env at
`0x93d80000`, proper at `0x49ac00`, chainload, handshake; no display yet).
Also done, Phase 0.6 installer board guards (2026-11-19):
`tools/board-guard.py` plus `boards/<id>/board.env` for both boards, wired into
every host installer (see `tools/README.md`). `boot-switch.sh` is bench-only.
The projector's `UBOOT_SERIAL` (`034000425c821e57`) is computed from its SID,
so confirm it with `fastboot getvar serialno` at the first install. Also done,
the Phase 2 five-cold-boot DRAM check (below). **The gate is met.**

**Five cold boots from FEL (2026-11-19, Phase 2 exit met).** Boots 1 and 2 were
the earlier FEL DRAM runs and the cold RAM-kernel boot. Boots 3–5 used
`tools/fel-dram-check.sh` with the SPL that will be installed: the current V2
build including 0011 (`build/out/u-boot-sunxi-with-spl-lpddr3-3e88ce00.bin`,
sha256 `a394bda0…`). Each boot: serial and USB unplugged, power off for 1 min
or more, FEL button. Each printed `DRAM: 1024 MiB`, and 32 MiB random patterns
at `0x42000000` and `0x7c000000` read back identical, in 1 MiB pieces (17:42,
17:52, 18:20). Logs: `local/recovery/fel-dram-check/cold{3,4,5}-*.log`.

**V2 restore SPL built (2026-11-19).** U-Boot 0010
(`CONFIG_H713_SPL_RESTORE_BOOT0`) plus `tools/build-v2-restore-spl.sh
local/h713-lab/captures/board-a/board-a-mmcblk0-20261118.img` gives
`build/out/h713-v2-restore-spl.bin` (65 536 B, sha256 `77e3610f…`).
- The payload is the projector's stock boot0 from the capture, LBA 16..79:
  `eGON.BT0`, 32 768 B, checksum ok, DRAM type 7 at 720 MHz, sha256
  `f8ac16e4…`. It is byte-identical to the capture and embedded in the
  SPL's read-only data.
- It runs only from the FEL load path (`spl_board_load_image` calls
  `h713_restore_boot0`). It brings the eMMC up as the SPL's MMC2 loader
  does (`mmc_initialize`, device 1), refuses an SD card, reports whether
  LBA 16..79 already match, writes, reads back and compares, then halts.
  Unlike the bench hook it needs no U-Boot of ours on the eMMC.
- Both DRAM-type guards were checked: the tool refused the bench DDR3
  defconfig with this boot0 ("type 7, board config wants 3"), and a forced
  type-7 payload in a DDR3 build stopped at the `#error`.
- **Proven on the projector (2026-11-19, 17:05).** This was the first write
  to its eMMC. In a fresh FEL session (the efex jump after arm F),
  `sunxi-fel -p spl build/out/h713-v2-restore-spl.bin` printed
  `DRAM: 1024 MiB`, `mmc1: eMMC, 15269888 sectors`, `before: already
  identical`, `wrote 64/64, read back identical: RESTORED-OK`. sunxi-fel
  times out (exit 124) because the SPL halts and never returns.
  - After a power cycle without the FEL button, stock boot0 ran from the
    rewritten sectors (`DRAM Type = 7`, 720 MHz, `simple test OK`) into
    stock U-Boot 2018.05. Android booted to `sys.boot_completed=1` with the
    same fingerprint. LBA 16..79 read on the board hashes to `f8ac16e4…`.
  - Log: `local/recovery/2026-11-18-v2-bringup/restore-proof-uart.log`.
- **Stock power-on gate:** after a cold plug-in, stock U-Boot stops silently
  after `[SCP] :sunxi-arisc driver v1.10 is starting` and waits in standby
  for the **power button**. Pressing it continues to the kernel. The
  "wedged stock U-Boot" after the first 1296 MHz reset (03:03) was this
  gate, not a hang.


1. Install the bench layout: our boot0 at LBA 16, vendor boot0 at `0x100`,
   U-Boot at `0x49ac00` plus the spare at `0x4a0c00`, Debian on UDISK. Read
   every region back after writing. First prove `switch_vendor` → Android →
   FEL restore on this board.
2. Display. Panel power on PH19, then the console on the panel, then the MIPS
   launch and logo. Run the `display.bin` option (a) and (b) test from
   Phase 0.7 here: one cold boot each, comparing the MIPS state and the logo.
   See the [V2 RAM-only FEL display test](#v2-ram-only-fel-display-test-2026-11-21)
   for the first visible-output result and the
   [native V2 firmware follow-up](#native-v2-display-firmware-over-fel-2026-11-21)
   for the timing comparison.
3. Then the production stack: startup/health scripts, video planes,
   letterbox/mirror, VE decode matrix (AV1 at PLL_VE ≤ 432 MHz). The DRAM
   bandwidth differs, so rerun the eMMC 0206/0207 loaded-read bench. It is
   DRAM-contention sensitive.

### Phase 4 step 1 runbook (stage 1 done 2026-11-19)

Three stages, each ending somewhere safe. Every write is read back and
compared before the next. Every stage's first step is a read-only check that
the board still looks as expected. Writes are made from the FEL U-Boot
(`tools/fel-uboot.sh`, in RAM), which works whatever is on the eMMC. That is
also the route back.

**Facts this relies on**, from the 2026-11-18 capture: LBA 16 and 0x100 hold
the stock boot0 (type 7, 720 MHz, identical); `empty` (LBA `0x49ac00`, 15 MiB)
is all zeros; `bootloader_b` is the vendor's FAT16 B copy (`BOOTLOGO.BMP`
etc.); `UDISK` is Android's f2fs userdata. V2's default environment has
`bootdelay=2`, `bootcmd=run distro_bootcmd` and `switch_vendor`.

**Stage 1 — our U-Boot on eMMC, Android untouched except LBA 16.**
1. Build: `BOARD=lpddr3 tools/build/build.sh uboot` (tree with 0011), and a
   rescue SPL plus proper rebuilt from the same tree. Split the image into the
   SPL (first 32 KiB) and the proper, as `boot-switch.sh split_ours` does.
   Record the hashes.
2. Fresh FEL session. `tools/fel-uboot.sh` with `EXTRA` loading the SPL and
   proper into RAM, then stop at the `=>` prompt.
3. Read-only checks at the prompt: `part list mmc 1` is the 26-entry
   layout; CRC32 of LBA 16 and 0x100 equals the stock boot0's; CRC32 of the
   `empty` region equals that of zeros. Any mismatch: stop.
4. Writes, in this order, each followed by `mmc read` to another address and
   `cmp.b`:
   1. proper → LBA `0x49ac00`;
   2. spare proper → `0x4a0c00`;
   3. our SPL stash → `0x49cc00`;
   4. **our SPL → LBA `0x10` (last)**.
   Until step 4 the board still boots stock exactly as before.
5. Cold boot (no FEL button): our SPL, then U-Boot from `0x49ac00`. Stop
   autoboot within 2 s. Check the banner, `DRAM: 1 GiB`, the V2 model, and
   the bad-CRC fallback to the default environment. Then `saveenv` (the
   environment goes to `0x93d80000`, inside `empty`) and `fastboot getvar
   serialno`, which must equal `boards/hy200-qz713-v2` `UBOOT_SERIAL`
   (computed so far).
6. Prove the round trip: `run switch_vendor`, power cycle, stock boot0,
   Android (press the power button at the gate). Back: FEL, then the FEL
   U-Boot writes our SPL from RAM to LBA `0x10`; cold boot to ours.
   **Fallback if our SPL ever fails to boot:** FEL, then the V2 restore SPL
   (proven) puts stock boot0 back.

**Stage 1 result (2026-11-19, 18:33–19:15): done.** Image
`build/out/u-boot-sunxi-with-spl-lpddr3.bin` (tree `3e88ce00`, with 0011;
SPL crc32 `a784a750`, proper 0x675 sectors crc32 `0df4c805`; manifest in
`build/out/v2-install/MANIFEST.txt`).
- Pre-write checks at the FEL U-Boot (the same proper being installed): 26
  partitions; LBA 16 and 0x100 crc32 `8ec0d62f` (stock); `empty` crc32 that
  of zeros.
- The writes in order (proper, spare, stash, SPL at LBA 16) each read back
  identical.
- First boot from eMMC: our SPL, then BL31 and proper from `0x49ac00`, the
  V2 model, 1 GiB. `saveenv` wrote LBA `0x49ec00`, and the next reset loads
  it (`Reading from MMC(1) at 0x93d80000... OK`).
- **U-Boot's serial# is `034000427a29544e`**, not the value computed as
  sid[0] sid[3]. U-Boot replaces sid[3] with crc32 of sid[1..3].
  `boards/hy200-qz713-v2/board.env` and the guard's FEL mode are fixed. The
  guard over fastboot confirms V2 and refuses the bench on the real board.
- Round trip: `run switch_vendor` put stock boot0 at LBA 16 (crc32
  `8ec0d62f`); power cycle, then the power button at stock's gate, then
  Android `boot_completed=1` with LBA 16 sha `f8ac16e4…`. Back: `adb reboot
  efex`, then the FEL U-Boot copied the on-board stash (`0x49cc00`, still
  identical) to LBA 16. A reset boots ours with the saved environment.
  0x100 and the proper were unchanged throughout.
- **Board whine (not ours):** a ~4.4–4.7 kHz tone, +8–17 dB over its
  surroundings, at our U-Boot prompt **and** at stock U-Boot's power gate,
  gone when unplugged, and masked by the fan in Android. It is unchanged with
  PB5 floating or driven low, and its pitch moves when USB is plugged in.
  Likely a regulator's light-load pulse-skipping coil whine. Recordings in
  `local/recovery/whine/`. To do once Linux boots from eMMC: record the
  production states (running, idle, light standby, s2idle) with the same
  rig. Light standby turns the fan off, so it is the likely audible state.
- Log: `local/recovery/2026-11-18-v2-bringup/install-stage1-uart.log`.

**Stage 2 — kernel and Debian (layout decided 2026-11-19).** This board is
production and needs no working Android, so Linux reuses existing Android
partitions and the 26-entry GPT is never rewritten. **Single slot, with FEL
as the recovery path** (decided 2026-11-19, after a best-practice review): a
paired A/B root would have needed `UDISK` split now, and kernel-only A/B adds
complexity without real protection, because the modules live in the root.
The rootfs is 1.4 GiB.

| partition | LBA / size | Linux role |
| --- | --- | --- |
| `boot_a` p5 | `0x32400`, 64 MiB | kernel FIT, raw |
| `super` p9 | `0x92400`, 2 GiB | **rootfs**, ext4, **read-only** |
| `UDISK` p26 | `0x54c400`, 4.63 GiB | data: `/data`, `/media`, `/var`, `/etc` overlay upper |
| `boot_b` p6 | `0x52400`, 64 MiB | unused (left as is) |

Recovery when the installed system will not boot: FEL, then the FEL U-Boot
(`tools/fel-uboot.sh`) rewrites any region from RAM. If our SPL itself is
broken, the V2 restore SPL puts stock boot0 back (both proven on this board).

Fixes from the review (sources in the 2026-11-19 session notes), all part of
this stage:
1. **Boot command built into U-Boot's default environment.** Production
   `bootcmd` (`mmc dev 1; mmc read 0x50000000 0x32400 0x8000; bootm
   0x50000000`) and `bootargs` go into the V2 default environment (a U-Boot
   patch), so a corrupt saved environment still boots Linux rather than the
   distro scan.
2. **Redundant environment.** `CONFIG_SYS_REDUNDAND_ENVIRONMENT` with
   `ENV_OFFSET_REDUND = 0x93d90000` (right after the 64 KiB primary, still
   in `empty`), so a power cut during `saveenv` leaves one good copy. Bench
   config is checked separately (its resolved `.config` must stay as is unless
   decided otherwise).
3. **Read-only root.** `super` mounted `ro`; `/var` (including `/var/tmp`,
   which must survive reboots) on the data partition; an overlay over the
   parts of `/etc` that change, with the upper layer on the data partition.
   `/tmp` stays tmpfs in RAM: the release rootfs (Debian 13) already enables
   systemd's `tmp.mount` (`size=50%`, about 466 MB here). Cap it lower
   (128–256 MiB) with a `tmp.mount` drop-in so a runaway `/tmp` cannot squeeze
   video decode on a 1 GiB board. Handle systemd's
   machine-id (generate at image build, or bind from data).
4. **`PARTUUID` naming.** `root=PARTUUID=<super>` on the command line and the
   same in fstab (the release fstab says `/dev/mmcblk0p26`, which is now
   wrong for V2). Renaming partitions keeps their GUIDs.
5. **A V2 kernel FIT. DONE (build side, 2026-11-19).** The FIT now carries
   both DTBs: `conf-1` (bench, still the default, so the bench's `bootm
   0x50000000` is unchanged) and `conf-v2` (projector). V2's `bootcmd` must
   say `bootm 0x50000000#conf-v2`; a bare `bootm` on V2 would boot the bench
   DTB. Consider LZ4 for the kernel (today gzip, 7.4 → 16.8 MiB) for faster
   decompression; measure first.
6. **Kernel config for the read-only root. DONE (build side, 2026-11-19).**
   The defconfig adds EROFS (lz4, lzma, zstd), SquashFS (zstd, per-CPU
   decompressors) and `OVERLAY_FS`, all built in. EROFS is the intended root;
   SquashFS is the comparison control and is dropped once the root is chosen.
   The read-only layout is `tools/rootfs/ro-root.sh`: the kernel runs
   `init=/usr/lib/h713/preinit`, which checks and mounts the data partition at
   `/data` (`h713.data=`, default `/dev/mmcblk0p26`; `PARTUUID=` works), puts
   an overlay on `/etc` with its upper layer in `/data/overlay/etc`, seeds
   `/data/var` from the image on first boot and binds it over `/var`, then
   execs systemd. If the data partition cannot be mounted it boots on a
   volatile tmpfs `/data` and says so on the console. `/tmp` is systemd's
   tmpfs capped at 256 MiB; the empty `machine-id` is filled through the
   overlay on first boot. `tools/rootfs/make-ro-images.sh ROOTFS_TAR` turns
   any `rootfs.tar` into the four comparison images (ext4 ro, EROFS plain,
   EROFS lz4hc, SquashFS zstd). Sizes, fresh production rootfs (2026-11-19,
   new kernel, `build/out/ro-root/`, source tar `658499ac`):

   | image | size | fits a 1 GiB A/B slot |
   | --- | --- | --- |
   | ext4 ro | 1292 MiB | no (single slot only) |
   | EROFS uncompressed | 1073 MiB | no (single slot only) |
   | EROFS lz4hc | 555 MiB | yes |
   | SquashFS zstd | 338 MiB | yes |

   The 11-18 release rootfs (with its overlay) gives the same within 5 MiB.
   So an A/B layout means a compressed root: uncompressed EROFS cannot be the
   "match ext4" answer. Owners, groups and all 16 setuid/setgid files match
   the source tar in every image (`dump.erofs` hides the setuid bit; an
   extraction shows it). **Not yet run on hardware.**
7. Optional, not required: `WATCHDOG_AUTOSTART` in U-Boot, so a hang before the
   kernel arms its watchdog still resets the board. With one slot, a reset only
   helps transient hangs.

**Stage 2 step 3 first pass (2026-11-19/20, log `install-stage2-uart.log`):**
- `super` holds `root-lz4hc.erofs` (555 MiB, sha256 `a82188ed`). Written
  over UMS with `tools/v2-root-write.sh`; the host's direct read-back found
  a difference. U-Boot `mmc read` + `crc32` per 16 MiB, then per MiB, 64 KiB
  and 4 KiB, located **four bad 4 KiB pages in MiB 526** (two 8 KiB runs at
  image offsets `0x20e78000` and `0x20e96000`) holding foreign data, found
  neither in the image nor in the 11-18 capture. The console printed
  `musb-hdrc: peripheral reset irq lost!` during UMS. Repaired with
  `fastboot stage` of that MiB (crc32 checked in RAM) and `mmc write` at LBA
  `0x199400`; the whole image read from eMMC then gives crc32 `de510f0a`, as
  on the host. (First read as a UMS bug; it is not, see below.)
- **eMMC write faults (2026-11-20, on the power block).** A UMS stress test
  (`tools/ums-stress.sh`, random data into `super`'s unused tail) reproduced
  the 8 KiB runs, and the same foreign pages recurred. U-Boot reads of those
  LBAs return a `4d03034d` structure whose counter rises with every read
  (reset to `0x49` at power-up) or all-`0xff`: the eMMC (Samsung `FNX2MB`,
  fw rev 6, 07/2019, wear `0x01/0x01`, pre-EOL normal) maps them to its own
  RAM. The foreign pages are in neither the board's DRAM nor the host. Pass 3
  hung the gadget. After a power cycle Linux multi-block writes fail after
  2–7 MiB at HS400, HS200 and DDR52 (`data error cmd25`, all interrupt
  status zero, stop fails, `cache flush error -110`); single-block ioctl
  writes, flushes and CMD13 (`tran`, no error bits) are fine; reads are fine
  everywhere. EXT_CSD: WR_REL_SET `0x1f`, 64 MiB cache, BKOPS_EN `0`. Root,
  FIT, SPL and stock boot0 verified intact by crc32. The data partition does
  not mount (preinit's volatile fallback works).
- **Fixed (2026-11-20): it was the eMMC out of free blocks.** Nothing had
  been discarded after the 4.6 GiB format, the root and ~4 GB of stress data,
  and BKOPS was off, so garbage collection ran inside writes. Fix:
  `BLKDISCARD` of `super` +640 MiB..end and `blkdiscard` of UDISK, auto-BKOPS
  on (CMD6 set-bits, BKOPS_EN `0x02`, AUTO_EN only; the OTP manual bit is
  untouched), 5 minutes idle. Then: five 8 MiB writes at DDR52 with 0 errors
  (two slow, 2.6–3.4 MB/s, still completing); at HS400 four 128 MiB raw
  writes read back identical, 256 MiB through ext4 at 34.9 MiB/s identical
  after remount and cache drop, `fstrim` 4.2 GiB, `e2fsck` clean, 0 kernel
  errors. The live-counter LBAs read stable after being rewritten. Root
  (sha256 `a82188ed88a6ae6c`) and FIT (`5dc0347e`) unchanged.
  **Production requirements:** discard before writing a new root image into
  `super` (stock `blkdiscard`, now in `tools/v2-root-write.sh`); trim on
  `/data` is already there: Debian's `fstrim.timer` is enabled in the image
  (weekly, `--listed-in /etc/fstab:/proc/self/mountinfo`, so it covers the
  preinit-mounted `/data`) and `mkfs.ext4` discards by default; auto-BKOPS
  enabled at boot if it does not survive a power cycle (not yet checked; the
  stock tool is `mmc bkops_en auto` from Debian's `mmc-utils`); verify every
  bulk write on the board. UMS itself was never the fault.
- `UDISK` was formatted on the board (`mkfs.ext4 -L data`, from the booted
  system, no USB in the path); `e2fsck -fn` clean. GPT name and PARTUUID
  (`a0085546-4166-744a-a353-fca9272b8e5e`) unchanged.
- Boots with the FIT loaded into RAM by `fastboot stage` (crc32 checked),
  `bootm 0x42000000#conf-v2`, `root=/dev/mmcblk0p9 rootfstype=erofs ro
  init=/usr/lib/h713/preinit`; `boot_a` is not written yet.
  1. UDISK still f2fs: preinit fell back to the volatile `/data` and said so;
     systemd `running`, no failed units; 3.1 s kernel + 9.9 s userspace.
  2. After the format: `/data` ext4 rw, `/var` bound from it, `/etc` overlay;
     the first boot wrote machine-id and ssh host keys into the overlay;
     13.9 s (includes seeding `/var`).
  3. Next boot: same machine-id and host keys, no reseed, no failed units;
     2.3 s kernel + 8.4 s userspace = 10.7 s (single sample, warm reboot, not
     the power-on measurement).

**Single slot vs A/B: measure before deciding (2026-11-19).** If an A/B
split of `super` (two 1 GiB slots, the second by repurposing the
`vbmeta_vendor_b` GPT entry so the count stays 26) boots as fast as the single
slot, A/B costs little. The runtime is identical; what differs is the root
filesystem (ext4 in 2 GiB versus a compressed image in 1 GiB) and a few
U-Boot env writes for slot choice and boot counting. Measure on the
projector, one FIT, the root chosen by U-Boot `bootargs`
(`root=/dev/mmcblk0p9 rootfstype=… ro rootwait init=/usr/lib/h713/preinit`),
at least five boots each from power-on (UART timestamps to the shell and to
`multi-user.target`, `systemd-analyze`), plus cold-cache runtime tests (start
of `mpv`/GStreamer, `find /usr`, a package-sized read):
1. ext4 ro (single-slot baseline);
2. EROFS uncompressed (single slot only: 1073 MiB);
3. EROFS lz4hc;
4. SquashFS zstd (control);
5. the winner with U-Boot slot logic (bootcount env writes) added.
A second-half placement test needs the GPT edit, so it runs only if A/B
wins. All variants need `UDISK` reformatted ext4 and `super` written, i.e.
stage 2 step 3 approved first.

**Root filesystem timing (2026-11-20, power block, HS400).** One FIT, one
data partition; each image installed from U-Boot by
`tools/v2-uboot-write-super.sh` (since replaced by `tools/v2-ab-install.sh`) (fastboot erase + flash, crc32 read-back
from the eMMC), then `tools/boot-timing.sh`: `systemctl reboot` x6, the first
a warm-up, 5 measured. A reboot clears Linux's page cache like a power-on;
power-on only adds the fixed SPL + DRAM training ahead of U-Boot, the same for
every variant. Logs in `local/recovery/boot-timing/`.

| root | size | systemd total (kernel + userspace), mean [min..max] | U-Boot banner → autologin |
| --- | --- | --- | --- |
| EROFS lz4hc | 555 MiB | **10.63 s** (2.28 + 8.35) [10.55..10.72] | 15.80 s |
| EROFS uncompressed | 1073 MiB | 10.74 s (2.28 + 8.45) [10.63..10.88] | 15.84 s |
| ext4 read-only | 1292 MiB | 10.87 s (2.31 + 8.56) [10.68..11.00], one outlier of 16.95 s excluded | 15.94 s |
| SquashFS zstd | 338 MiB | 11.43 s (2.57 + 8.85) [11.25..11.60] | 16.48 s |

U-Boot → "Starting kernel" is 3.9 s in every case (2 s of it `bootdelay`).
**EROFS lz4hc is at least as fast as the single-slot ext4 baseline and fits a
1 GiB A/B slot**, so splitting `super` into A/B slots costs no boot time from
the root filesystem. SquashFS is 0.8 s slower (decompression in the kernel
and userspace start). Not yet measured: U-Boot's slot selection and boot
counting (a few env reads and one write per boot); true power-on boots.

**A/B with RAUC: installed and tested (2026-11-20).** Decision: U-Boot's own
`bootmeth_rauc` plus Debian's `rauc` (no custom slot code). Layout: the GPT
keeps 26 entries; p9 `super` became `root_a` (0x92400, 1 GiB) and p16
`vbmeta_vendor_b` became `root_b` (0x292400, 1 GiB) (`tools/v2-gpt-ab-split.py`,
originals in `local/recovery/2026-11-20-v2-ab/`). A slot is a vfat boot
partition (`boot_a`/`boot_b`: FIT + `boot.scr`, `tools/v2-boot-image.sh`) and
an EROFS root. U-Boot 0012: `BOOTMETH_RAUC` (`"5,9 6,16"`, 3 tries, refill
when all run out), `BOOTSTD_FULL`, redundant environment at 0x93d90000,
boot device and method declared in the V2 `-u-boot.dtsi` bootstd node
(`bootdev-order = "mmc1"`, a single `rauc` bootmeth node), so `bootcmd` is
Standard Boot's default `bootflow scan -lb`; V2 drops the deprecated
`DISTRO_DEFAULTS`, and `sunxi-common.h` includes the `distro_bootcmd`
environment only for boards that keep it (its `boot_targets`, `fel mmc_auto
usb0 pxe dhcp`, overrides any devicetree order and names nothing bootable
here). Why not `bootflow scan -lb mmc1` with `bootmeth order rauc`: U-Boot
refuses any label while a bootmeth order is set (`bootmeth_setup_iter_order()`
returns `-EPERM` when global bootmeths are skipped, and the command prints
nothing). A scan hang seen once with the non-`BOOTSTD_FULL` build did not
reproduce from RAM (that configuration is not used). (The first install used
`setenv boot_targets mmc1; bootmeth order rauc; bootflow scan -lbH`.)
Linux: `rauc` + `rauc-service`, `/etc/rauc/system.conf` (two raw
rootfs + two vfat boot slots, status in `/data/rauc`), a meta-rauc-style
`rauc-mark-good.service` (Debian ships none), `fw_env.config` naming the
environment by partition (`/dev/disk/by-partlabel/empty` +0x800000/+0x810000):
libubootenv (0.3.5 in Debian 13, unchanged on upstream master) stores
`lseek()`'s 64-bit result in an `int` in `fileread()`/`filewrite()`, so any
offset at or past 2^31 fails before the read or write. Found with a
syscall trace on the board (`lseek(fd, 0x80000000) = 2147483648`, then no
`read`); 0x7ffe0000 works, 0x80000000 fails, on a plain file too. `/var`
is now an overlay like `/etc` (image below, `/data/overlay/var` above), so
the package database follows the image. Installed with
`tools/v2-ab-install.sh` (fastboot from U-Boot, crc32 read-back of every
region).
- Unattended boot: defaults → `bootmeth_rauc` takes an attempt from A →
  `boot.scr` (FIT 7.9 MB in 0.52 s) → `root=PARTUUID` of `root_a`,
  `rauc.slot=A` → `/data`, `/etc` and `/var` overlays → `rauc-mark-good`
  refills A. `rauc status`: booted A, both good. 11.24 s systemd total (one
  sample, first boot of the `/var` overlay; not yet re-timed).
- Slot B: `rauc status mark-active other` → `BOOT_ORDER=B A` → boots
  `root_b` with `rauc.slot=B`; the environment alternates copies.
- Fallback: with mark-good disabled, B was tried 3 times (B 2→1→0) and the
  fourth boot fell back to A by itself. Restored afterwards (A active, both
  good, mark-good enabled; the `/etc` overlay's wants directory checked
  identical to the image's).
- **The eMMC fault recurred during the install:** one 1 MiB region of
  `root_b` (6 pages, the same `00/ff` bitmap and live-counter structure)
  after ~1.4 GB of writes, despite the discard fix. Caught by the
  read-back, repaired, everything re-verified; a second full slot rewrite
  verified clean. Every bulk write on this part must be verified; whether
  the part is fit for production is open.
- Not yet tested: a slot that hangs (needs a watchdog: U-Boot
  `WATCHDOG_AUTOSTART` and systemd `RuntimeWatchdogSec`); a RAUC bundle
  install (needs signing keys); power-on timing with the A/B layout.

Steps:
1. **U-Boot.** Patch for items 1 and 2; rebuild; install the new proper and
   SPL from the FEL U-Boot as in stage 1 (stash and spare too), read back.
2. **Kernel.** Write `h713-kernel.fit` raw to `boot_a`, read back.
3. **Partitions.** Over UMS from our U-Boot (`ums 0 mmc 1`), with a V2-only
   script (the bench tools assume its 28-entry GPT) run with
   `H713_BOARD=hy200-qz713-v2`: `mkfs.ext4` `super` and `UDISK`; rename them
   off their Android names (stock finds userdata by the name `UDISK`, and
   reformatting `super` makes Android unbootable); unpack the rootfs into
   `super`; set up fstab, the `/etc` overlay and the data mounts; read back.
4. **First boot from eMMC**, console only: dmesg against the RAM-kernel
   boots; root mounted `ro` from `super`, data `rw` from `UDISK`; `fastboot` and
   `reboot fel` work from the installed system. Then a deliberate power cut
   during `saveenv`, to show the redundant environment recovers.
5. Android's old contents remain recoverable from the 11-18 capture.

**Stage 3 — display** is Phase 4 step 2 (PH19 panel power, `H713_MIPS_BOOT`
on V2, the `display.bin` (a)/(b) test).

**Not covered by this runbook:** `tools/release/prepare-install.py` (the
production packet) is DDR3-only (`MODEL` pinned), so V2 production installs
need it extended once Stage 2 is proven by hand.

### V2 RAM-only FEL display test (2026-11-21)

1. Confirmed the V2 SID in FEL and used `tools/fel-uboot.sh` to load and
   read back BL31, the V2 U-Boot candidate, and a FAT image of the known
   DDR3 bench display assets in RAM. The test build had autoboot disabled.
   Its device tree supplied the panel power GPIO on PH19 and the active-low
   reset on PH16. The asset image was mounted in U-Boot through `blkmap`.
2. Ran `h713_disp auto 0x34 logo` and manually enabled the shared lamp and
   fan line on PB5 and the brightness PWM on PB4 at the stock 75% duty.
   Read-back showed PH19 high and PH16 released. The 1280×720 framebuffer
   CRC32 matched the source logo (`e906064c`), and the raster counter advanced.
   The operator saw the boot logo on the screen.
3. With illumination steady, alternated the panel's internal source
   between black and white twice. The operator saw the projected field
   switch between bright and black, then saw the logo return after the
   original registers were restored.
4. Turned off illumination, ran `h713_disp teardown`, and reset into the
   installed bootloader. The projector booted slot A and RAUC marked it
   good. Full SHA-256 read-back matched the pre-test baseline for the
   installed SPL and U-Boot region and for `boot_a`, `root_a`, `boot_b`,
   and `root_b`. The final boot order was `A B` with three tries per slot.

This verifies visible output on the V2 with the bench asset set. At the
time of this test the loader accepted only the bench firmware revision.

Local evidence is under `build/v2-display-bringup/fel-panel-test/` in
`pattern-fel-load.log`, `framebuffer-verify.log`, `pattern.log`,
`optical-observation.md`, `pattern-return-a-uart.log`, and
`pattern-after.log`.

### Native V2 display firmware over FEL (2026-11-21)

The loader selects the firmware length, SHA-256 digest, and guarded
initialization patch by board compatible. For V2 project `0x34`, it reads
the stock assets from `mmc 1:2` and checks the native register table before
using it. The native V2 `display.bin` was 1,256,216 bytes with SHA-256
`16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9`.
The RAM-only U-Boot candidate ran with autoboot disabled.

| Timing used with native V2 firmware | FEL result |
|---|---|
| Native V2 timing, with the corrected table boundary | The firmware reported application readiness, the display counter at `0x05880000` advanced, and the committed 1280×720 framebuffer had CRC32 `e906064c`. The lamp was on and the operator saw a black screen. |
| A1 timing block 6, staged in RAM | The operator saw a recognizable boot logo. The loader kept the native V2 firmware, configuration, project data, prologue, display engine records, and bitmap. |
| Native V2 timing plus one display PLL restart | The operator saw a recognizable boot logo on both the isolated diagnostic run and the final FEL build. The final build used the V2's own display files and had no A1 timing data staged in RAM. The framebuffer CRC32 was still `e906064c`. |

The full A1 PLL startup sequence also restored the logo with the rest of
the V2 timing block in place. A follow-up test after a fresh FEL boot
isolated the sufficient change to one pulse. The loader now clears and
sets bit 31 at `0x058c0014` after the native 20 µs setup delay and before
the routing records at offset `0x1684`. It preserves the native clock
register values, delays, and reset sequence.

The A1 timing override remains available as an explicit bench option.
Stage the 648-byte block at offset `0x1654` in the A1 `LogoRegData.bin`
at address `0x60000000` over FEL. Set `h713_v2_a1_timing=yes` in the
RAM environment and run `h713_disp auto 0x34 logo`. The loader verifies the
staged block's SHA-256 before using it. Lamp and brightness were
controlled manually in these timing tests.

After the final run and panel teardown, the projector booted normally
from the installed bootloader into slot A and RAUC marked it good.
SHA-256 read-back matched the pre-test baseline for SPL, the installed
U-Boot region, and all four slot partitions (`boot_a`, `root_a`,
`boot_b`, and `root_b`). Boot order was `A B` with three tries per slot.

Local evidence for the initial comparison is under `build/v2-native-display/` in
`corrected-native-panel.log`, `corrected-native-scanout.log`,
`timing-panel.log`, `final-fel-load.log`, `final-panel.log`,
`final-scanout.log`, `final-return-a-uart.log`, `baseline.log`,
`after.log`, and `after-mark-good.log`.
Evidence for the single-pulse fix is under `build/v2-native-display/minimal/`
in `optical-observations.md`, `variant-2.log`, `variant-3.log`,
`final-fel.log`, `final-panel.log`, `final-regs.log`, `return-uart.log`,
`baseline.log`, `after.log`, and `after-good.log`.

### Automatic V2 boot-logo illumination over FEL (2026-11-21)

The V2 normal-boot `PREBOOT` runs `h713_disp auto 0x34 logo` using the
compiled policy even when the saved RAUC environment contains the old
`preboot` value. The loader keeps the shared PB5 lamp and fan enable low
while it initializes the panel and commits the logo. It then starts PWM2
on PB4, checks that the programmed duty and advancing counter read back,
and raises PB5. Teardown lowers PB5 and disables PWM2 before dropping the
panel supply.

The setting comes from the extracted stock V2 device tree. It declares
PWM2 at 25 kHz, active high, and `panel_backlight = 75` on a 0–100 scale.
The FEL test confirmed 720 active cycles out of 960 in our loader. The
stock A1 U-Boot trace recorded a runtime request for PWM5 that failed,
so the device-tree default alone leaves the shipping V2 runtime waveform
unverified. The V2 FEL test verified the projected logo and PWM register
state. Optical dimming from PWM2 remains unverified.
[Stock PWM investigation](backlight-investigation.md#0-the-answer-from-the-vendors-own-u-boot)

FEL loaded BL31 and the V2 U-Boot candidate into RAM. UART stayed passive
through the optical check. The operator saw a recognizable boot logo
without any console commands, using the native V2 timing with the single
PLL restart. UART recorded the logo commit, PWM2 setup, and PB5 enable in
that order. The framebuffer CRC32 was `e906064c`. This test build held
the image in U-Boot for inspection. The
[Linux handoff test](#v2-linux-display-handoff-over-fel-2026-11-21) followed.

After teardown and reset, the installed bootloader started slot A, and
RAUC marked it good. Before-and-after SHA-256 read-back matched for SPL,
the installed U-Boot region, and `boot_a`, `root_a`, `boot_b`, and
`root_b`.

Local evidence is under `build/v2-native-display/automatic-lamp/` in
`optical-observation.md`, `fel-load.log`, `boot-uart.log`,
`display-readback.log`, `return-uart.log`, `baseline.log`, `after.log`,
and `after-good.log`.

### V2 Linux display handoff over FEL (2026-11-21)

The RAM-loaded V2 U-Boot candidate showed the native logo in `PREBOOT`
and booted the installed slot A through the normal RAUC boot path with
passive UART capture. The test build suppressed U-Boot's MMC environment
save so its updated `preboot` stayed in RAM. Linux 6.18.38 logged that
`sun50i-h713-afbd` adopted the 1280×720 framebuffer at `0x6c100000` with
a 5120-byte stride. Debian reached the login prompt, and RAUC marked
slot A good.

On the repeat boot, the operator saw the logo give way to the live Linux
console with no perceptible blackout and no visible green flash. A black
frame too brief to register remains possible.

Before-and-after SHA-256 read-back matched for SPL, the installed U-Boot
region, and both slots' boot and root partitions (`boot_a`, `root_a`,
`boot_b`, and `root_b`). The saved `preboot` and `bootdelay` values also
matched.

Local evidence is under `build/v2-native-display/linux-handoff/repeat/`
in `optical-observation.md`, `timeline.log`, `boot-uart.log`,
`baseline.log`, `after.log`, `after-good.log`, and `storage-check.log`.

### Installed V2 U-Boot display handoff (2026-11-21)

Before installing the production build, backed up the entire 15 MiB
bootloader region (`empty`, `/dev/mmcblk0p18`), the installed SPL at LBA
`0x10`, and vendor boot0 at LBA `0x100`. Verified those files against
`backup.sha256`. Wrote the production FIT to the primary U-Boot at LBA
`0x49ac00` and verified the write by reading back the whole bootloader
region. The previous spare U-Boot at LBA `0x4a0c00` remained in place.

After a clean Linux shutdown, the operator disconnected projector power
for approximately 10–15 seconds and restored it. The runbook's one-minute
discharge interval was longer than this test's power-off interval. UART
confirmed that the installed SPL loaded U-Boot from eMMC, the native logo
was committed, and slot A booted. The operator saw the logo stay visible
until the Linux console appeared. Linux adopted the 1280×720 framebuffer
at `0x6c100000`, and RAUC marked slot A good.

Post-boot read-back verified the new primary U-Boot and the unchanged
spare. Before-and-after SHA-256 hashes matched for SPL, vendor boot0, and
`boot_a`, `root_a`, `boot_b`, and `root_b`.

The backups and evidence are under `build/v2-native-display/installed-handoff/`
in `boot-region-before.bin`, `spl-before.bin`, `stock-boot0-before.bin`,
`backup.sha256`, `write.log`, `timeline.log`, `optical-observation.md`, and
`cold-storage-check.log`.

### V2 local 720p H.264 playback on slot A (2026-11-21)

On the installed V2 bootloader and slot A, played a 77.344-second
1280×720 H.264 High clip from tmpfs. The video-only clip ran at
30000/1001 fps. `h713-play` selected `plane-native`
(`v4l2slh264dec` → `kmssink`). The player held Cedrus (`/dev/video0`),
and the video engine recorded 2,318 interrupts during playback. DRM
showed an active 1280×720 NV12 framebuffer on the video plane.

The sink rendered all 2,318 frames with zero drops. The operator saw
smooth playback without visible glitches and confirmed that the live
Linux console returned at end of file. The display IOMMU and Panfrost
MMU interrupt counters stayed at zero, and the kernel journal had no
new entries during the test. The active VT was `tty1`, and the KMS state
after playback matched the initial console state.

Before-and-after SHA-256 hashes matched for all four slot partitions
(`boot_a`, `root_a`, `boot_b`, and `root_b`). The SPL and U-Boot
read-back hashes also matched. The staged clip and temporary logs were
removed from the projector's RAM after evidence collection.

Local evidence is under `build/v2-native-display/playback-720p/` in
`optical-observation.md`, `live-decoder.log`, `playback.log`,
`kernel-during.log`, `kms-before.log`, `kms-after.log`, `baseline.log`,
and `after.log`.

### V2 local 1080p H.264 playback on slot A (2026-11-21)

On the installed V2 bootloader and slot A, played a 77.344-second,
video-only 1920×1080 H.264 High clip at 30000/1001 fps from tmpfs.
`h713-play` selected `plane-ve` (`vah264dec` → `kmssink`). The VA-API
driver used Cedrus (`/dev/video0`) for hardware decoding, cropped the
coded 1920×1088 frame to 1920×1080, and used the video engine scaler to
output 1280×720 NV12. DRM scanned out that buffer on the video plane.
The video engine recorded 2,318 interrupts, and the sink rendered all
2,318 frames with zero drops.

The operator saw smooth playback with no visible glitches and confirmed
that the live Linux console returned at end of file. The display IOMMU
and Panfrost interrupt counters stayed at zero, and the kernel journal
had no new entries during playback. The active VT was `tty1`, and the
KMS state after playback matched the initial console state.

Before-and-after SHA-256 hashes matched for all four slot partitions
(`boot_a`, `root_a`, `boot_b`, and `root_b`), SPL, and U-Boot. Boot
order and the remaining tries for both slots also matched.

Local evidence is under `build/v2-native-display/playback-1080p/` in
`optical-observation.md`, `player.log`, `playback.log`, `irq-before.log`,
`irq-after.log`, `kernel-during.log`, `kms-before.log`, `kms-during.log`,
`kms-after.log`, `baseline.log`, and `after.log`.

### Phase 5: the remaining hardware

In order: fan (tach PH17; PB5 also powers the fan) → audio and speaker (the
zero-pop requirement and mic rig) → HDMI input and audio capture → IR/keys →
Wi-Fi/BT → accelerometer and auto-keystone (the node matches stock; verify
SC7A20 on TWI1 `0x18`) → standby. **Re-qualify standby completely:** any path
that puts DRAM into self-refresh is DRAM-type-specific. Finish by running
`docs/production-qualification-plan.md` on V2, then mark the board `verified`
with date and boot ID.

#### V2 slot A fan and shared lamp enable (2026-11-21)

Verified on the HY200 QZ713 V2 running Linux 6.18.38 from slot A
(boot ID `a7bdc760-9370-4270-a5a5-0b323379c159`). With the board idle,
sampled PH17 as a GPIO input at approximately 2 kHz with its bias left
unchanged. With `lamp/bl_power=0`, Linux reported PB5 high and PH17
showed 511 rising and 511 falling transitions over three seconds, with
a median pulse frequency of 168.8 Hz.

Writing `4` to `/sys/class/backlight/lamp/bl_power` drove PB5 low for
five seconds. PH17 pulses slowed during fan coast-down, then the signal
stayed high with zero transitions in the final two-second window.
Writing `0` drove PB5 high again. After spin-up, PH17 showed 512 rising
and 511 falling transitions over three seconds, with a median pulse
frequency of 168.9 Hz. This confirms that the lamp driver's PB5 output
also switches fan power and that PH17 carries the fan tach signal.

The test left the lamp enabled with the original 75% dimmer setting.
PH17 was released and returned to its original unclaimed, bias-disabled
state. The board stayed on the same slot A boot, and the kernel journal
had no new entries during the test.

Local evidence is under `build/v2-native-display/fan-slot-a/` in
`preflight.log`, `probe.py`, `probe.log`, and `after.log`.

#### V2 slot A internal speaker and pop test (2026-11-21)

The installed slot A device tree leaves `/soc/codec@2030000` disabled.
The built-in `sun4i-codec` driver was present, but ALSA showed no cards
and PipeWire had no audio sink. Patch 0082 enables the codec on the A1
bench DTS. To test V2, U-Boot verified and copied the slot A FIT's V2
DTB to RAM, set the codec status to `okay` in that copy, and booted the
same kernel and slot A root. The temporary boot (`e1655477`) registered
`H713 Audio Codec`, one playback PCM, and a PipeWire sink for the speaker.

Recorded Scarlett 2i2 input 1 at 48 kHz with the microphone by the
speaker and the fan running. The first take clipped on the playback
tone and had transients in quiet windows. Repeated the full matrix with
a lower playback tone and fixed mic gain. The repeat peaked at −5.0 dBFS.
The mic picked up 1 kHz in all three faded playback runs at −12.6 to
−12.4 dBFS, versus −78.3 to −62.9 dBFS at 1 kHz in the quiet windows.

Using the [speaker pop test](speaker-pop-evidence/2026-11-17/README.md#rig)
and its 3.5 threshold, all three deliberate 0.5 FS impulse controls
flagged (37.2–47.9). Zero of twelve ordinary trials flagged. The quiet
windows scored up to 2.2.

| Event | Trials | Max pop score | Flagged |
| --- | ---: | ---: | ---: |
| Faded PipeWire playback start and end | 3 | 2.1 | 0 |
| 48 kHz ALSA PCM stop and immediate close, digital silence | 3 | 2.4 | 0 |
| `Speaker Power` off and on, three round trips | 6 | 2.4 | 0 |

PL2 stayed high during playback and PCM close and changed state on every
explicit amplifier power command. A 1.1–6 kHz check around PCM close and
power transitions also stayed within the quiet reference range. These
measurements cover awake local playback and amplifier power transitions.
Cold boot, mains power-off, standby, and HDMI audio remain pending on V2.

Restored the mixer settings and rebooted normally into slot A (`eea82965`).
UART confirmed the installed codec status was again `disabled`, the test
files in `/run` were gone, and the boot order was `A B` with three tries
per slot. The codec enable was confined to the temporary boot.

Local evidence is under `build/v2-native-display/audio-slot-a/` in
`diagnostics.log`, `uart-codec-boot.log`, `routing.log`, `run-2/board.log`,
`run-2/score.json`, `run-2-playback.log`, `run-2-edges.log`, and
`uart-return-check.log`. The mic recordings are kept locally.

#### V2 slot A HDMI input and audio capture preflight (2026-11-22)

Checked the installed V2 slot A boot (`eea82965`, Linux 6.18.38). HDMI
video and audio capture were blocked by missing startup and capture
components. The HDMI prepare, capture, signal, ring, and video services
were absent, along with the receiver, V4L2 capture, and HDMI audio
modules and the audio DSP firmware. The existing production HDMI build
targets the [DDR3 A1 bench](production-qualification-plan.md).

- **Video input:** `VIDIOC_QUERYCAP` identified `/dev/video0` as Cedrus
  and `/dev/video1` as the H713 AV1 decoder. Both are memory-to-memory
  devices. There was no standalone HDMI V4L2 capture endpoint, so no
  HDMI mode lock or frame capture was verified.
- **Audio capture:** ALSA listed no sound cards. Opening the expected
  capture PCM, `hw:H713HDMI,0`, returned `ENODEV` (`-19`). No HDMI audio
  samples were captured.

The host HDMI connector reported `disconnected` and the host had no
projector audio ELD. Cable presence and HDMI signal lock remain
unverified. The measurements require a V2 HDMI startup and capture
bundle and a source with a confirmed link. This preflight used the
installed image without changing it or rebooting the board.

Local evidence is under `build/v2-native-display/hdmi-slot-a/` in
`preflight.log`, `receiver-diagnostics.log`, `startup-units.log`,
`endpoints.log`, and `host-source.log`.

##### HDMI device-tree comparison (2026-11-22)

Compared the live V2 slot A FDT with the A1 production FIT's DTB and
the stock Android `vendor_boot_a` DTBs extracted from both boards'
eMMC captures. The stock A1 and V2 trees differ only in fan tach,
focus motor settings, and panel power. Their HDMI-related descriptions
match, including the audio bridge and its SPI 115 and SPI 113 IRQs.

| HDMI startup resource | Live V2 slot A | A1 production FIT |
| --- | --- | --- |
| DDC pinmux owner and EDID clock/reset consumer | Absent | `h713-ddc-pins` for PL10–PL15, and `h713-edid-clock-hold` |
| TVCAP power retention across Linux boot | No `allwinner,keep-tvcap-on` | Property set on the PPU |
| MIPS trace buffer | Absent | `hdmi-trace@4d980000`, 256 KiB, `no-map` |
| Audio bridge and TVTOP nodes | Both `okay` | Both `disabled`, with the capture stack managing these resources |
| Audio bridge and AudIf IRQ order | SPI 115, SPI 113 | SPI 115, SPI 113 |

The A1 HDMI boot script also adds `/chosen/h713,hdmi-boot-v1` after
verifying the live MIPS source 3 transition, and adds
`/soc/hdmi-mips-shutdown` with the clocks and resets used for receiver
parking. The live V2 FDT has neither, and the installed V2 display
boot quiesces MIPS after committing the logo. A V2 capture boot needs
the HDMI resources, the live MIPS handoff, and the capture modules and
firmware identified in the preflight. The internal speaker codec at
`0x02030000` is a separate path. [A1 startup script](../tools/hdmi/build-startup.py)

The extracted trees and diffs are under
`build/v2-native-display/hdmi-slot-a/dt/`. This comparison used the
running board and local images without changing the device tree on disk.

##### V2 HDMI test candidate (2026-11-22)

Added an [offline DTB builder](../tools/hdmi/prepare-v2-capture-dtb.sh)
and an [opt-in overlay](../tools/hdmi/v2-capture.dtso). The overlay adds
the DDC and EDID resources, TVCAP retention, MIPS trace reservation, and
receiver shutdown resources. It leaves the display, USB, internal codec,
and boot arguments from the base DTB in place. The builder was tested on
the V2 DTB extracted from the installed slot A FIT. It checks the board
compatible, bridge IRQs, and trace reservation boundaries.

The receiver, DDC, signal, HDMI audio and V4L2 modules built against the
kernel tree whose `Image` byte-matches the installed slot A FIT's
decompressed kernel. The candidate also includes the pinned A1 DSP
payload for evaluation. The files are staged locally under
`build/v2-native-display/hdmi-slot-a/candidate/` in `v2-hdmi-test.dtb`
and `runtime-files/`. The overlay and module build did not change the
board or its installed boot path.

##### Native V2 MIPS handoff port (2026-11-22)

U-Boot patch 0018 selects a trace table for the authenticated native V2
`display.bin` (`16c74a28…`). It relocates the CPU_COMM and source worker
hooks and the firmware channel-table pointer. All 446 expected words
match the native image, and the existing scratch-register liveness tool
found zero unsafe sites across 61 hooks. The Linux trace reader selects
the V2 offsets using the board compatible and rejects A1 words on V2.

The explicit `h713_disp hdmi-source-v2` command checks the live channel
table, waits for CPU_COMM RETURN and a fresh source 3 worker completion,
and verifies the trace page guards before exporting the handoff PID.
The FEL candidate builds successfully and pauses at UART, leaving the
installed boot path in place. Offline evidence is under
`build/v2-native-display/hdmi-slot-a/candidate/` in `trace-map.txt`,
`v2-liveness.log`, `uboot-ram-build.log`, and `handoff-baseline.log`.

The host HDMI cable was connected for the trial. The USB connection
check did not see a configured gadget, so live handoff and capture
verification are pending the FEL data connection. A normal reboot
restored the slot A USB host role after the temporary gadget probe.
Before-and-after SHA-256 read-back matched for SPL, the checked U-Boot
region, and all four slot partitions. RAUC still reported boot order
`A B` with three tries per slot. See `normal-boot-storage.log`.

##### Live V2 HDMI handoff and capture over FEL (2026-11-22)

`reboot fel` from slot A entered BROM FEL, and
[`fel-uboot.sh`](../tools/fel-uboot.sh) loaded the U-Boot 0018 RAM
candidate and `v2-hdmi-test.dtb`. From the U-Boot prompt, the single
logo launch with comm-trace and `h713_disp hdmi-source-v2` completed
source 3 (PID `8b8f261c`). The RAM boot script then set
`/chosen/h713,hdmi-boot-v1` and booted the installed slot A FIT and
root. The installed boot path was not written.

Linux read the handoff trace with both guards intact. It showed a
source 3 transition with callback event 0 and worker event 0, which
completed from `00000000` to `00000003`. The receiver, DDC, signal, and
HDMI audio modules loaded from the staged runtime files, and each file
matched its build hash. EDID and HPD came up, and after one HPD pulse
the host reported the projector ELD (`H713 HDMI IN`, 2-channel LPCM at
32, 44.1, and 48 kHz).

- **Audio:** `hw:H713HDMI,0` captured a 48 kHz host tone at
  2954 periods with zero xruns. All three tone windows passed the rate
  check (tone fraction 0.9999996 at 48 kHz), and the final second
  after the host stopped was all zero.
- **Video lock:** The first V4L2 build used the A1 port-object offsets
  and never saw a signal. In native V2 firmware the port's state,
  flags, link, and power-cache fields sit 4 bytes earlier (`+0xbc`,
  `+0x514`, `+0x51c`, `+0x52c`), and the port root and vtables move.
  The bridge now selects a V2 port layout from the board compatible and
  refuses to load on V2 unless the power-reader code CRCs match and the
  handoff property is present. The rebuilt module locked 1280×720
  after 11 samples and exposed `/dev/video2` (`h713-hdmi-in`).
- **Frame capture:** With the host playing the 60 Hz frame-ID pattern,
  seventeen 120-frame captures from `/dev/video2` had every frame
  patterned and zero band or stripe errors. In each one, the driver
  delivered every completion with zero unstable copies. Run 6 is
  excluded: its two-output FFmpeg consumer could not keep up
  (`no_buffer` 195). In the
  low-overhead NUT run, which kept the buffer timestamps, all 480
  completion gaps were 16.0–17.7 ms. The three skipped IDs in that run
  each arrived about 17.0 ms after the previous frame, so the skipped
  frames never reached the wire. They are host compositor drops, not
  missed completions. The 1280×720 frame shows the red and cyan edge
  columns, so the crop is full width.
- **Panel route B:** The A1 product pipeline (`v4l2src io-mode=dmabuf`
  → NV12 → `kmssink driver-name=sun50i-h713-afbd`) ran for 19.4 s and
  delivered 1159 frames (59.6 fps, 2 `no_buffer`, 0 unstable). DRM
  showed a 1280×720 NV12 framebuffer on `video-0`, and its id changed
  between snapshots. The IOMMU and Panfrost MMU counters stayed at zero,
  and the console plane returned when the pipeline stopped. In a
  27.5-second repeat (1637 frames, 59.6 fps, 0 unstable), the operator
  saw the moving pattern on the panel. Motion was smooth and the image
  was correct.

Evidence is under `build/v2-native-display/hdmi-slot-a/candidate/`:
`fel-load-live.log`, `fel-uart.log`, `v2-handoff-uart.log`,
`live-*.log`, `live-audio-analysis.json`, `video-capture/` (runs 1–7,
raw NV16 zstd-compressed; `run-7-nut` has the timestamps),
`panel-route-b/`, and `panel-optical/`.

#### V2 HDMI input at normal boot (2026-11-22)

The FEL bench path is now the normal boot path. Four pieces are involved:

- **Device tree (kernel 0218).** The V2 tree carries the HDMI resources the
  bench tree already has: the trace reservation, the EDID clock hold, the
  DDC pin owner, TVCAP retention, the receiver's MIPS parking node, and
  the Audio Bridge and TVTOP left to the guarded drivers. It matches the
  FEL test overlay apart from overlay label symbols.
- **U-Boot (0019).** PREBOOT runs `h713_disp boot-v2` in place of the
  logo-only sequence. It uses the bench board's RTC GP6 latch
  (`0x07090118`). After power loss (0) or a boot whose HDMI start Linux
  acknowledged (`HDOK`), U-Boot writes `HDMI` and verifies it. It then
  runs the single firmware launch with the CPU_COMM trace, refreshes the
  channel table, and selects source 3. Any other latch value, or a
  running MIPS core, takes the existing logo-only path. A failure after
  the latch is set resets the SoC, and the latch makes the next boot
  logo-only. PREBOOT runs before `bootmeth_rauc`, so no slot attempt is
  spent. `ft_board_setup()` publishes `/chosen/h713,hdmi-boot-v1` into
  the slot's own FIT DTB, so `boot.scr` is unchanged. The PID never
  enters the environment that `bootmeth_rauc` saves.
- **Older slots.** While the trace is installed, the firmware keeps
  writing its trace page. A slot tree without the 0218 reservation gets a
  `/memreserve/` for `0x4d980000`–`0x4d9bffff` and no handoff, so its
  HDMI services stay off.
- **Root image.** `tools/hdmi/build-v2-overlay.py` builds the five HDMI
  modules against the slot kernel. It assembles the same runtime the
  bench release ships through `tools/release/build.py`'s
  `hdmi_payload()`: session, signal owner, capture bridge, health ack,
  speaker, hold guard, and udev rule. `tools/rootfs/build.sh
  --release-overlay` installs it. The V2 needs no startup script. The
  speaker delay is the bench board's 0.115 s until the V2 is measured.
- **Codec (kernel 0219).** The V2 tree left `codec@2030000` disabled, so
  the speaker service had no ALSA card and restarted indefinitely. 0219
  enables it, which is the change the 2026-11-21 speaker test made in a RAM
  copy of the tree.

**Results.** All tests used the HDMI cable from the host GPU's
`HDMI-A-1` port.

1. **FEL, old slot A tree.** The RAM U-Boot set the latch, completed
   source 3 (PID `8b8f261c`) and added the `/memreserve/` without a
   handoff. Linux reserved `0x4d980000`–`0x4d9bffff` and RAUC kept A good.
2. **Old installed U-Boot, new slot B.** The logo-only path ran (MIPS was
   parked at entry even though the last boot had left it running). Every
   HDMI unit skipped on its `ConditionPathExists`, and B was marked good.
3. **FEL, slot B with 0219.** The handoff reached Linux. Prepare,
   capture, signal, ring, readvertise, speaker and video were active, and
   `check-startup.sh` passed. The health ack wrote `HDOK` and the system
   state was `running`. Video locked 1280×720 on `/dev/h713-hdmi-in`. During a
   host tone, the HDMI capture and the codec playback ran in step at 48 kHz
   with zero xruns.
4. **Installed U-Boot.** The 15 MiB region, SPL and boot0 were backed up
   first (copy in `local/recovery/2026-11-22-v2-hdmi-uboot`). The new FIT
   (976,384 bytes) was written to the primary at LBA `0x49ac00`, and the
   whole region read back as expected. SPL, boot0 and the spare at
   `0x4a0c00` were unchanged.
5. **Warm reboots on the installed U-Boot (2).** Both took the HDMI path
   with the latch at `HDOK`, published the handoff and acknowledged
   again.
6. **Cold boot.** After a power cut with serial and USB unplugged, GP6
   read 0. U-Boot launched HDMI, video reached the panel at 12 s and
   `check-startup.sh` passed. The operator saw the correct picture.

Slot A keeps the pre-HDMI `2026.11.21.0842` image as the fallback. Slot B
holds `2026.11.22.1048-40489d5a` (root `e7077fad…`).

**Green stall seen again.** On the step 3 FEL boot the operator saw the
bench board's green/magenta picture. It had the same four AFBD status
words: `0x05600038=10`, `0x338=01000001`, `0x1cc=02cf0130` and
`0x1fc=02cf04f0`, all 0 when healthy
([closed A1 write-up](hdmi-first-advert-root-cause-2026-11-08.md)).
A video service restart and a plane stop/start did not clear it, but a
warm reboot did. It is not tied to an early video start: the next boot
held video for a minute and the one after started it automatically, and
both were clean, as was the cold boot. The first green-versus-good diff
suggested the firmware had set up composition for another input format.
Three healthy sweeps rule that out. The flagged composition words
(`0x05000a2c`/`a34` and bit 3 of `0x05000a18`–`a20`) also change on a
healthy boot. The firmware never writes them: it reads `a34 & 7` in a
status poller, and `0x05000a00` is an interrupt-status page. Of the
registers that are stable when healthy, the green state differs mainly in
picture statistics. Two configuration-like differences have no direct
firmware writer: `0x050c0c94` bit 30 (set when good) and `0x05040814`.
A1's green boot captured correct NV12 frames, so the stall is on the
display fetch side, where AFBD stops at line 719. Evidence is in
`build/v2-hdmi-normal/green-stall/`.

**Open items.**
- **Firmware log level: CLOSED, not needed (2026-11-22).**
  `h713-mips-elog-level` is not shipped on the V2. The V2 boots the
  vendor's `display_cfg.xml` (`b3e6e8f6…`). Its `elog_init_setting` is
  mode 1 (async) at level 1. The firmware's `elog_init`
  (`0x8b15102c`) stores that level at `0x8b48bd9c`, and the `-l` arm
  stores there too. The live readback was 1 (the loaded copy at
  `0x4be01000` is the same file), so the readback was correct. The bench's
  mode 2 (buf) at level 5 (`f97eec07…`) was our 2026-09-04 debugging
  edit, and it reached the A1 production inputs. Only buf mode has the
  2 MiB ring whose flush stalled CPU_COMM. On the V2, `elog -l 2` would
  raise the level.
- **Release gate.** `verify_rootfs` rejects V2 images because they ship
  the AV1 probe module. V2 kernels use the plain defconfig, not the
  `production` fragment, and the existing V2 images ship it too.
- **Shutdown hold guard.** The guard is inherited from the bench board.
  If HDMI teardown fails, it turns a reboot into a poweroff. On the
  sealed projector that needs a power-button press.
- **Latch timing.** As on the bench board, a reboot before the health
  ack (about 10 s into userspace) gives a logo-only boot. After a failed
  start, HDMI stays off until power is removed.

Evidence is under `build/v2-hdmi-normal/`: `fel-slot-a/`, `old-uboot-b/`,
`fel-slot-b2/`, `uboot-install/`, `green-stall/`, and `cold-boot/`.

#### V2 boot qualification (2026-11-22, in progress)

This repeats the A1 sign-off matrix (2026-11-17 candidate, steps 9–16) on
slot B (`2026.11.22.1048-40489d5a`). It uses the same guarded
`tools/hdmi/startup-qualification.py`, whose checks pass unchanged on the
V2: unit states, zero error counters, 720p lock, both PCMs running, four
`cmds` IPC probes (917-byte reply), the HDOK acknowledgement, and the
shutdown order and restoration.

- **Identity audit.** `tools/hdmi/make-v2-runtime-audit.py` replaces the
  A1 audit, which needs a sealed release. The V2 root is read-only, so it
  pins whole slots instead of files. The root and boot partitions must
  hash to the bundle manifest, the U-Boot primary at `0x49ac00` must hash
  to the installed FIT, `/` must be `root_b`, and nothing in the `/etc`
  overlay may shadow the HDMI runtime. It takes 7.5 s on the board. A
  wrong rootfs hash, a wrong primary hash and a shadow rule that matches
  each failed it.
- **Driver.** `tools/hdmi/v2-qualification-run.py` chains runs. After each
  one it reads the AFBD stall words and `0x050c0c94`/`0x05040814`, and it
  stops on a stall or a failure without rebooting. Pins and known_hosts
  are in `local/recovery/2026-11-22-v2-boot-qualification/`, and the runs
  are in `build/v2-boot-qualification/`.

| Run | Boot | Video active | Boot time | Frames / 36 s | AFBD | `0x050c0c94` | `0x05040814` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | `2af685ed` | 11.96 s | 14.143 s | — | clean | `40282804` | `00666000` |
| warm-01 | `78ea1ea4` | 11.75 s | 13.895 s | 2449 | clean | `00282804` | `00666000` |
| warm-02 | `e41fa6d8` | 11.49 s | 13.737 s | 2465 | clean | `40282804` | `006e6000` |
| warm-03 | `1b4336d7` | 11.73 s | 13.793 s | 2468 | clean | `00282804` | `006e6000` |
| warm-04 | `6f5db755` | 11.70 s | 13.942 s | 2462 | clean | `40282804` | `00666000` |
| warm-05 | `6b0870ec` | 11.47 s | 13.661 s | 2465 | clean | `00282804` | `006e6000` |

All five warm runs passed: PASS digital at 59.7 fps, no re-adverts, and a
correct shutdown order before each boot. The green stall is now 1 in 10 V2
boots. **The two candidate words do not separate green from good.** Bit 30
of `0x050c0c94` was clear on 3 of 6 healthy boots, and `0x05040814` changes
between healthy boots. Record them on a stall, but don't treat either as
the cause.

**4-hour soak: PASS.** `regression-observer.py watch` ran detached
(transient unit `h713-v2-soak`, log on `/data/qual/`) on boot `6b0870ec`
after warm-05. `soak` PASS for 7200 s and for the whole 14,397 s (2,795
samples, 5 s apart). It stayed locked at 1280×720 with at least 50 frames/s.
Rejected, xrun, guard and AFBD-invalid counters stayed at 0. There were no
service restarts or start changes and no re-adverts. Afterwards the AFBD
words were clean (`0x050c0c94` = `00282804`, bit 30 clear on a healthy
boot) and dmesg had no CPU_COMM timeout, desync or quarantine. Evidence:
`build/v2-boot-qualification/soak/`.

**Found during the soak: no CALL channel on the V2.** Every V2 boot, back
to the first FEL boots, logs `cpu_comm: firmware reader self-test failed
(00a08025 00809025, expect 03e00008 24020001)`. The self-test pins
`getCurCPUID` at its A1 address `0x8b1227b4`, so `cc_discover_channel()`
skips the table and `channel_pid` stays 0. HDMI does not depend on it
(U-Boot selects the source, and Linux uses the MIPS shell ring). Any
kernel CALL on the V2 would still be acknowledged and then never
dispatched. The driver's `MIPS elog staying on Mode 1 (ring buffer)` line
is an old label: in `display_cfg.xml`, mode 1 is async. Fixed by kernel
0220 (see "V2 CPU_COMM channel discovery" below), which also found that
0014's elog addresses were the V2 build's, not the A1's.

**Slot A (kernel 0220) cold and warm boots: PASS.** The CPU_COMM session
installed `2026.11.22.1229-4c5ff9c3-0220` into slot A (root `3e10f301…`,
the same boot image as slot B, with only `hy310-cpu-comm.ko` different), and
the board boots A first. The remaining runs therefore qualify A, the image
to ship. `make-v2-runtime-audit.py --slot A` matches that session's audit
byte for byte. Each cold boot started with a guarded poweroff
(`v2-qualification-run.py --poweroff`), and the previous journal ends in a
normal shutdown. The operator then unplugged serial and USB, left the power
off for at least a minute and powered on. `--cold N --previous-boot`
collected each boot.

| Run | Boot | Video active | Boot time | AFBD | `0x050c0c94` | `0x05040814` |
| --- | --- | --- | --- | --- | --- | --- |
| cold-01 | `35eb8c65` | 9.91 s | 12.168 s | clean | `40282804` | `00666000` |
| cold-02 | `10ea1a4e` | 10.14 s | 13.034 s | clean | `40282804` | `00666000` |
| cold-03 | `d907150d` | 9.86 s | 11.866 s | clean | `40282804` | `00666000` |
| warm-06 | `b227df38` | 10.20 s | 12.508 s | clean | `00282804` | `006e6000` |
| warm-07 | `7dc9e77b` | 9.86 s | 11.914 s | clean | `40282804` | `00666000` |
| warm-08 | `0e69035f` | 9.83 s | 11.947 s | clean | `00282804` | `006e6000` |
| warm-09 | `dc3b7221` | 10.79 s | 13.901 s | clean | `40282804` | `00666000` |
| warm-10 | `8e1361fd` | 9.87 s | 11.824 s | clean | `00282804` | `006e6000` |

All 8 runs passed: PASS digital, 59.7 fps, no re-adverts, the shutdown
order and restoration of the boot before, and channel row 0 found with the
handoff PID on every boot. Video starts about 1.6 s earlier on slot A than
in the slot B warm runs. That has not been explained: 0220 changes only
channel discovery.

The green stall is now 1 in 18 V2 boots. **Bit 30 of `0x050c0c94` flips
on almost every warm reboot** and is set after every cold boot. On slot A
it also moves with `0x05040814` (`666000` with bit 30 set, `6e6000` with
it clear). It looks like a buffer or phase bit carried across a warm
reboot, not a fault flag. The A1 green boot happened to read with it
clear.

**HDMI unplug/replug at the board: PASS, automatic.** This was on slot A
boot `8e1361fd`, with a detached observer (`h713-v2-replug`, 27 samples).
The operator unplugged the cable at the board for about 30 s:
- At 223.6 s `source power: absent`, at 225.3 s `signal none`, and the
  video unit stopped by design.
- At 235.4 s the timed schedule sent an HPD pulse (1/5) to an empty port.
- After the replug, at 255.6 s: `failed EDID read (busy 2 passes)`, then
  an event pulse. At 257.1 s `signal locked 1280x720 (source change)`,
  the video unit restarted, and at 257.5 s `source power: present`.

There was no manual step. This unplug did log `source power: absent`,
unlike the A1 rerun on 2026-11-17, so it exercises on hardware the
stale-absent case that the ungated readvertise fixed. The owner units have
0 restarts, the startup check passes, there are no failed units, and AFBD
is clean afterwards. `regression-observer.py recovery` first refused:
`frames_produced` restarts with the stream, one sample after the lock (it
read 12439 while stale, then 281), and the check compared across that
restart. The analyzer now measures from the last counter restart. On this
file the old analyzer fails, and the new one passes over 134 s. Cut off
before the restart (`--end 262`), the new one still fails. Evidence:
`build/v2-boot-qualification/replug/`.

**No-source boot: PASS.** HDMI was unplugged at the board, the board
logged `source power absent`, and then took a guarded reboot (the guard
required `signal none`). On boot `1d2723b3` (slot A), all owner units were
active with 0 restarts, video was waiting, the owner was ready, HDOK was
written and the startup check passed. The fresh schedule sent exactly 6
pulses, at 2, 10, 20, 40, 80 and 160 s without a source (the last at
322.3 s), and then stayed quiet. With the schedule used up, the operator
plugged HDMI in. At 532.98 s: `failed EDID read (busy 2 passes)`, then an
event pulse. At 534.50 s `signal locked 1280x720 (source change)`, the
video unit started, and both PCMs ran. That gave 59.7 frames/s, zero
counters, 0 restarts, a passing startup check and clean AFBD. Evidence:
`build/v2-boot-qualification/no-source/`.

**But the panel stayed black (operator, about 4 min after the lock): a
FAIL that the digital checks cannot see.** The host was sending its
extended COSMIC workspace (screenshot of `HDMI-A-1`: wallpaper and panel
bar). Read-only state on boot `1d2723b3`:
- The capture ring holds that exact picture: one frame from
  `read-coherent-frame.py --copies 1`, with the live clock. Capture is
  correct.
- AFBD is as on healthy boots: format `0x03000013`, geometry, enable, the
  address queue advancing, all stall words 0. TCON 720p timing is the
  same and its counter runs. Backlight 75/100, lamp on, LVDS DPMS on.
  Route blue screen `0x05140d54`, panel blue screen
  `0x051c00b0–b8`/`0x364` and panel selector `0x051c006c` all equal good.
- The display sweep diff (`display-sweep.py --no-raw` ×2 against good2
  and good3 from `2af685ed`, `diff-display-sweeps.py`) has 105 CONFIG
  words. These words are equal on two separate healthy boots and on the
  green boot, but differ here: `0x050c0824` (`910`→`8f0`), `0x050c08d4`,
  `0x050c08e8`, `0x050c0970` (`00000006`→`FFFF0006`),
  `0x050c09c4/9c8/9d0/9d8`, `0x05140e68` (`14`→`1104`), and LVDS
  `0x051c0168/16c`. The DETN counters `0x050c0884/894/8ac/914/918/92c/930`
  read 0. The route status bit `0x05140614` bit 0 is 0 (read-only, 1 on
  stock and on healthy boots).
- What sets this boot apart from every healthy V2 boot: U-Boot's
  `boot-v2` started HDMI (source 3) with **no source connected**, and the
  source first appeared 534 s later.

So the picture is lost after the AFBD fetch, in the firmware-owned
processing path (the `0x050c0000` block and the route), which looks like
the firmware's no-signal state never cleared.

Discriminating tests on the same boot, with the operator watching the
glass each time:
- On the source-present boot `8e1361fd`, the replug recovered the
  picture. So it fails only when the boot **starts** without a source.
- `systemctl restart h713-hdmi-video` (plane set up again, frames
  flowing): still black, and the words above unchanged. The cause is not
  Linux's plane setup.
- An HDMI unplug for about 10 s and replug (1325.1 s `signal none`,
  failed-EDID event pulse, 1330.8 s relock, video restarted): still black,
  words unchanged. A source cycle does not clear the state set at
  start-up.

- A guarded **warm reboot with HDMI connected** (boot `fb29d7c8`, locked
  720p, every check normal): **still black**. The state survives a warm
  reset, like A1's lit-but-black episode of 2026-10-16, which only a long
  power-off cleared. The firmware port object (state 5, 1280×720) is the
  same as on `1d2723b3`. Its dumps (`build/v2-boot-qualification/good-ref/`)
  were meant as a good reference but are a second black state. Do not use
  them as good.

So the no-source boot left something black that a warm reset does not
clear. The panel, the LVDS PHY or an always-on domain are candidates. The
last confirmed picture was `8e1361fd` (warm-10, after the replug).

**Localised to the panel's power state (2026-11-22).** The operator
confirmed the glass at each step:
- A cold power cycle with HDMI connected (`146d6ecd`) brought the picture
  back.
- A cold power-on **without** a source, then a plug-in at 149 s
  (`760d300a`): desktop. Starting without a source is not the trigger.
- A **warm reboot taken while unplugged**, then a plug-in at 68 s
  (`0b84940f`): **black**, with the same read-only signature (DETN counters
  0, `0x05140614` bit 0 = 0). This reproduces it.
- The TCON test pattern (`0x0588000c/1c/38/3c/40`, the October trial 26
  values, read first and restored exactly): still black. The fault is after
  the TCON: LVDS or the panel. The panel is physically the same one the
  bench used.
- Panel pins (bank stride 0x30): PH19 (supply enable, U-Boot's V2
  `vcc-panel`) output high, PH16 (reset, active low) output high, PF6
  disabled. All three are unclaimed by Linux: **the V2 kernel tree has no
  `vcc-panel` or panel reset**, unlike A1's 0183/0184.
- **An ordered supply cycle from Linux cleared it live:** save and quiet
  the LVDS words (`0x051c00d4–e0`, `0x051c0014`, `0x051c0028`,
  `0x05140054`), PH16 low, 75 ms, PH19 low, **5 s**, PH19 high, 2 ms, PH16
  high, then restore the LVDS words (read back equal). The operator saw the
  desktop.

So this is A1's October latch-up on the V2 board. U-Boot's initial-off hold
(0001: PH19 off **3 s** on every boot) does not clear it there. Evidence:
`build/v2-boot-qualification/warm-unplugged/` and
`build/v2-boot-qualification/black-panel/` (sweeps, diff, frame). A further
repro attempt (`38b3607c`) came up good, so the trigger is intermittent:
black on 2 of 3 warm reboots taken while unplugged.

**The missing half of the bench fix: kernel 0221 (2026-11-22).** The bench
is protected twice: U-Boot's initial-off hold (0001), and the display
driver's ordered panel power-down at shutdown (0184), which runs only when
the tree describes the panel. The V2 tree described neither supply nor
reset, so 0184 never ran on the V2: every warm reboot reset the SoC with
the panel powered and the LVDS lanes driven. Kernel 0221 gives the V2 tree
`vcc-panel` on PH19 (`regulator-boot-on`, 250 ms off delay),
`panel-reset-gpios` on PH16 and `backlight = <&lamp>`, as 0183 does on the
bench. U-Boot 0020 makes its V2 `-u-boot.dtsi` use that node without
`regulator-boot-on`. A V2 U-Boot build from the series has one PH19
regulator, no boot-on and the display wired to it, so the installed U-Boot
already behaves the same and was not reinstalled.

Install: bundle `2026.11.22.2314-1f15ffa6-0221`, made of slot A's root
`3e10f301…` (0220) and a new boot image `058f681b…`. Its kernel Image
differs from slot A's only in the 41-byte build timestamp, and the V2 DTB
adds only the panel nodes. `root_b` and `boot_b` were blkdiscarded before
`rauc install`, and both read back equal to the manifest. Slot A keeps
0220.

Results on slot B, with the operator confirming the glass each time:
- First boot `906daf54` (warm, from slot A, HDMI connected): PASS digital
  (slot B audit, video 9.70 s), and `vcc-panel` claimed (use count 1),
  with PH19/PH16 still high at 70 s. The glass was **black**, because the
  latch was inherited from slot A's shutdown, which has no ordered
  power-down. The live PH19 cycle cleared it.
- From there, 3 warm reboots taken while unplugged, each followed by a
  plug-in: **desktop 3/3** (`7dd6fade` lock 70.1 s, `8be792b4` 48.9 s,
  `f153ab23` 48.6 s; startup check PASS). Before the fix it was black on 2
  of 3. At that rate, three good results by chance would be about a 4% event.

0184's power-down runs after journald stops, so its log reaches only the
serial console. The evidence is the glass. Evidence:
`build/v2-panel-0221/`.

**0221 is necessary but not sufficient (same day).** The same bundle was
installed in slot A (`root_a`/`boot_a` blkdiscarded, both read back
equal), with `BOOT_ORDER=A B`. Warm reboots **with HDMI connected** from a
0221 slot came up black 2 of 2 (`615aa675`, then `5de2b3ed`, the second
after the live PH19 cycle had restored the desktop). A serial capture
(`build/v2-panel-0221/serial-reboot-1/`, console at `dmesg -n 8`) shows
the whole sequence running. 0184 logs `panel powered down: supply off,
reset line 0, PHY 18000000/00000030, route 40000000` 13 ms before `reboot:
Restarting system`. U-Boot then logs `initial supply off… 3000000 us`,
`restarted PLL during native V2 timing`, `FIFO status 0x00000002; reset
applied`, the 550 ms pre-delay and `supply on, reset released`, then the
logo, the single launch, and source 3 with 720p latched twice. On a
watched repeat (`serial-reboot-2/`) the operator saw the panel **never
light** and saw no logo. The failure was already present during U-Boot,
after the ordered power-down and a 3 s off hold.

**U-Boot 0021 and 0022 follow-up.** The A1 PLL startup passed three
HDMI-connected warm FEL boots. Installed 0021 still failed on the third
normal warm reboot (`6ac287a1`, lamp on, no logo). The live ordered PH19
cycle restored the desktop on that boot. U-Boot 0022 waits until MIPS has
selected HDMI source 3 and U-Boot has latched final 720p before powering
the panel. It passed three warm FEL boots with the logo and, after a
guarded install with verified readback, three normal warm reboots with
the desktop. Stock 0022 remains installed. Both RAUC slots retain kernel
0221.

**0022 optical qualification complete (2026-11-22).** Seven more
operator-observed normal warm reboots from Linux with HDMI connected
(boots `397aed2a`, `8221795a`, `c5fd5b2d`, `1ddd0e21`, `3eed8cea`,
`ec6e74d0`, `06d93cce`) and one true cold boot (`249c4de1`: guarded
poweroff, serial and USB unplugged, at least 1 min off) all showed lamp,
logo and desktop. That is **10/10 warm and 1/1 cold** on installed 0022.
Each warm boot had the kernel's ordered panel power-down on UART, then
0022's order: 3 s off with reset held, source 3 and the 720p latch, then
supply and reset release. Every boot passed the startup check (59.7 fps,
no re-advert, slot A and the 0022 primary audited). The cold boot's AFBD
words were clean. If 0022 still failed at 0021's observed 1-in-3 rate,
ten straight passes would have had about a 2% chance. That rate came from
three boots, so this is strong evidence, not proof. 0022 is the
production U-Boot. Evidence is in
`local/recovery/2026-11-22-v2-uboot-0022.EZo6qV/optical-observations.md`
and `qual-linux/`.

A RAM-only 0022 diagnostic held the LVDS PHY and route registers in their
off state after the final latch through panel power-up and reset release,
then restored the saved words before the lamp. HDMI stayed connected and
the existing power and reset delays were preserved. All three trials
showed the logo and had matching register checkpoints. Pad-level behavior
and any reliability benefit beyond 0022 remain unverified. PH10–PH13 and
SPI1 were inactive over the sampled instrumented 0022 and 0021 startup
windows. No black boot was captured in those runs.

See [the current handoff](handoff-2026-11-22-v2-panel-latch-for-chatgpt.md)
for per-boot optical results, evidence paths and a plan if black recurs.

**Source-PC reboot with the board left on: PASS (2026-11-22, one run).**
The board stayed on cold boot `249c4de1` while the NVIDIA host
rebooted (host boot `55859037`). A detached transient unit
(`h713-v2-host-reboot`, script and log in `/run`) sampled HDMI every 5 s.
The board saw one drop: `signal none` 8 s after the host journal ended.
The video unit stopped by design, and the signal owner sent one HPD
pulse 10 s later, during host firmware. `signal locked 1280x720 (source
change)` came 0.7 s after host nvidia-drm loaded, about 18 s after the
drop, and the video unit restarted. The greeter and login caused no
further drop. `regression-observer.py recovery` PASS (101 samples, 515 s,
counters 0, no board reboot), with 0 unit restarts and no failed units.
Chris saw the desktop come back with the cable untouched. The A1's
first-advert miss after an NVIDIA host boot did not occur, and this run
cannot tell whether the HPD pulse helped. Evidence:
`local/recovery/2026-11-22-v2-host-reboot/`.

**Green-stall catch chain: clean, 0 in 61 (2026-11-22).** An unattended
`v2-qualification-run.py --baseline --warm 60` ran from 21:36 to 23:11 on
installed 0022 and kernel 0221, with HDMI connected. It covered baseline
`249c4de1` and 60 guarded warm reboots from Linux. All 61 boots were PASS
digital at 59.7 fps, with readvertised 0 and video starting 9.61–10.16 s
after boot. All four AFBD stall words (`0x05600038/338/1cc/1fc`) read 0 on
every boot. The chain would have stopped on a stall without rebooting the
board. Zero in 61 puts the stall rate on normal warm reboots below about
4.9% (95%). The two candidate words varied on healthy boots:
`0x050c0c94` bit 30 was set 40 times and clear 21 times, and `0x05040814`
read `00666000` 39 times and `006e6000` 22 times. So they are not
markers. A register lookup found no writer of the four words in stock
`decd.ko`, our KMS driver, or the 29 AFBD sites in V2 `display.bin`. They
look like hardware status, and nothing supports clearing them by writing
them back. Both known stalls followed unusual starts: on the A1 the stream
came up late through an HPD pulse, and on the V2 the board had booted over
FEL. The next arm would copy those starts (HDMI plugged in late after
boot, or FEL boots) and needs the operator. Evidence, kept locally:
`build/v2-green-chain/2026-11-22/` (`chain.log`, `README.md`,
`healthy-sweeps/`, `afbd_scan.py`).

#### V2 CPU_COMM channel discovery (2026-11-22)

**Problem.** Every V2 boot logged `cpu_comm: firmware reader self-test failed
(00a08025 00809025, expect 03e00008 24020001)`. `cc_discover_channel()` (0014)
pinned the A1 firmware: `getCurCPUID` at `0x8b1227b4` and the `pcpu_comm_dev`
pointer at `0x8b22efe4`. The V2 runs its native `display.bin` (`16c74a28…`),
which is the same source relinked, so `channel_pid` stayed 0. A kernel CALL
would have been acknowledged and then never dispatched. HDMI was not
affected, because U-Boot selects the source and Linux uses the MIPS shell ring.

**Mapping, from code.** `tools/mips/map-fw-pins.py A1 V2 --cpu-comm` finds the
code around every A1 reference in the V2 image. It masks only relocations, and
it reads the address that the matching V2 instruction forms.

| Pin | A1 (`4380f1b3`) | V2 (`16c74a28`) | Evidence |
| --- | --- | --- | --- |
| `getCurCPUID` (self-test) | `0x8b1227b4` | `0x8b122688` | all 40 `jal` sites map; body identical |
| `pcpu_comm_dev` pointer | `0x8b22efe4` | `0x8b22f1f4` | 42 of 46 loads accepted, all agree (+0x210) |
| channel walk at `dev + 0xa8` | `0x8b11e378` | `0x8b11e24c` | identical code |
| elog mode byte | `0x8b48beaf` | `0x8b48be9b` | `elog -m` handler stores sync=0, async=1, buf=2 |
| elog buf enable, write offset, ring | `…c2c1`, `…c2cc`, `0x8b28bdb0` | `…c2ad`, `…c2b8`, `0x8b28bd9c` | 2/2, 7/7, 2/2 refs (−0x14) |

U-Boot 0018 already uses the same V2 reader and pointer. A correction to
earlier notes, which said the driver's elog reads used A1 offsets: the elog
addresses in 0014 were the **V2** build's,
and on the A1 they read bytes 0x14 too low. That is why every A1 log shows
`mode=0`, while the V2 correctly shows mode 1, as `display_cfg.xml` sets
(0 sync, 1 async, 2 buf). The VP route IDs that 0014 registers start at the
same addresses in both builds.

**Kernel 0220.** cpu_comm keeps a table of both builds and picks the one
whose code matches at three sites: `getCurCPUID`, a `lui/lw` pair loading the
pointer, and the `lui/sb` pair in `elog -m sync`. Each pair must also form
its table address. An unknown firmware is refused, so the self-test still
guards the reads. The elog readout uses the same table, reports the mode by
name and writes nothing.

`tools/mips/test-cpu-comm-fw-identity.py` compiles the patched code against the
images. A1 and V2 are recognised. Empty DRAM, the stock Android build
(`22a7df11`) and four one-word corruptions are refused. The existing
cpu_comm host tests still pass.

**Install.** The 0220 tree differs from slot B's build only in
`hy310-cpu-comm.ko`. The Image differs only in its 45-byte build timestamp, and
System.map, the V2 DTB and the other 30 modules are identical. The bundle
`2026.11.22.1229-4c5ff9c3-0220` therefore combines slot B's `boot.vfat`
(unchanged, `d94e684f…`) with slot B's `rootfs.tar` carrying the new module.
Extracting both EROFS roots shows that one file differs; the new root is
`3e10f301…`. `rauc install` wrote slot A, replacing the 11-21 fallback, and
slot B remains the qualified image.

**Result (warm reboot into slot A, boot `109baa24`).**
- The dmesg identity line names the V2 build (`getCurCPUID 0x8b122688`,
  `dev_ptr 0x8b22f1f4`). Channel row 0 is live with chan 0, pid `0x8b8f261c`
  and key `0xb8f261c0`, matching `/chosen/h713,hdmi-boot-v1` bytes 8–11.
  The elog readout is mode 1 (async).
- One read-only `THal_Vp_GetSource` CALL through `/dev/cpu_comm` returned
  `nret=1 ret=0` in 10.7 ms. The driver logged the RETURN and sent
  RETURN_ACK. Its handler always returns 0 (2026-08-31 handoff).
- `check-startup.sh` passed before and after the CALL, with video locked at
  1280×720. There were no failed units and no CPU_COMM timeout, desync or
  quarantine. The slot A identity audit (`make-v2-runtime-audit.py
  --slot A`) passed.

Evidence is in `build/v2-cpucomm-0220/` (`before/`, `after/`, `rauc-install.log`).

#### USB port roles (2026-11-20)

The V2 has one USB-A socket, SoC port 0. Its 5 V is hard-wired on, and it
has no ID pin and no VBUS sense (the PHY's VBUS comparator reads 0). So
nothing can tell a PC from a stick, and the role is chosen, never detected.
Stock does the same thing: `persist.sys.usb0device` picks host or device by
hand. Never drive PL5 low: it hard-hung the board. PL3 is a power latch.

- **Kernel 0215.** It enables musb with `dr_mode = "otg"` on V2 only. With no
  `id_det` GPIO the PHY polls nothing; the role changes only through musb's
  `mode` attribute (`phy_set_mode`), and the PHY's route bit (OTGCTL bit 0)
  sends the port to musb or to ehci0/ohci0. At probe ehci0/ohci0 set it to
  host (`usb_add_hcd` → `phy_set_mode(HOST)`, "Changing dr_mode to 1"), so
  the port boots as a host whatever the probe order. The patch also adds the
  configfs NCM and ACM functions to the defconfig, and a `usbdev` reboot
  magic, `0x05bdb007`.
- **Kernel 0216.** sunxi's musb glue dropped a mode change written while the
  controller was disabled (no gadget bound): `echo host > mode` returned
  success and did nothing, and a repeat was a no-op. Found on hardware;
  fixed in the glue.
- **`h713-usb host|device [--persist]`** (`tools/usb/h713-usb`,
  `h713-usb.service`).
  - Device mode is a configfs NCM + ACM gadget. The interface is named
    `usbdev0`, never `usb0`, so DHCP is never served on a phone's tethered
    `usb0` in host mode.
  - The board is `192.168.7.1`; dnsmasq hands the PC an address in
    `.2–.20` with no router and no DNS, so the PC keeps its own default route.
  - There is an autologin getty on `ttyGS0`.
  - udev starts the DHCP server and the getty when the gadget's interface
    and tty appear; systemd stops them when they go.
  - The role sticks when the cable is pulled.
  - The boot role is `h713.usb=` on the command line, then
    `/etc/default/h713-usb`, then host.
- **`reboot usbdev`** (`systemctl reboot --reboot-argument=usbdev`) gives
  one boot in device mode. boot.scr reads and clears GP7 itself:
  bootmeth_rauc saves the environment before the script runs, so a variable
  set in PREBOOT would persist into every later boot.
- **Measured 2026-11-20** (0215 kernel RAM-booted on root_a, A-to-C cable
  into the PC):
  - The PC enumerated `1d6b:0104` and bound `cdc_ncm`.
  - DHCP gave the PC `192.168.7.7` and its default route was unchanged.
  - The SSH host key was checked over the UART.
  - Over SSH, 128 MiB went in at 12.1 MiB/s (sha256 match) and came out at
    14.7 MiB/s.
  - Switching back to host with the gadget bound worked; with it unbound it
    did not, which led to 0216.
  - Leaving host mode prints one `VBUS_ERROR in b_idle`: musb's own host
    side started a session it cannot see VBUS for, because the port is
    routed to ehci0. It looks harmless.
  - With 0216, `h713-usb` was run from `/run` with the customize.sh units
    under `/run/systemd` and `/run/udev`. Results:
    - host → device → host all switch, whether or not a gadget is bound.
    - udev started `h713-usb-net` and the `ttyGS0` getty on device, and
      both stopped on host.
    - The PC got `192.168.7.8`, and the ACM console answered on the PC's
      `ttyACM1`.
    - `h713-usb host` run inside the SSH session dropped the link and
      completed (route bit back to 0).
  - The ACM getty first ran without `--wait-cr`, and the PC's ttyACM, open
    in cooked mode, echoed the shell's output back as input. The root shell
    ran fragments of its own output as commands. With `--wait-cr` nothing is
    printed until a CR arrives; a terminal program in raw mode then gets a
    clean shell.
  - **Slot B install (2026-11-20).** A production rootfs with these units
    went to root_b (EROFS lz4hc, 556 MiB) and the 0216 FIT and new boot.scr
    to boot_b, with `STEPS=slots SLOTS="boot_b root_b" tools/v2-ab-install.sh`.
    Both were verified by crc read back. Slot A was not touched. Results:
    - B booted and RAUC marked it good.
    - `h713-usb.service` applied host by default.
    - After `h713-usb device --persist` and a reboot, the port came up as a
      device with nothing typed, and the PC had DHCP before login.
    - After `h713-usb host --persist` and `systemctl reboot
      --reboot-argument=usbdev`, the command line had `h713.usb=device`, the
      port was a device, and GP7 read 0. The next plain reboot came back as
      host.
    - The saved environment holds `h713_usbargs` empty. Each boot.scr clears
      it before anything else, so it cannot leak device mode, but what saves
      it is not yet understood.
  - **Trap found: `bootdelay=-1` can be saved.** PREBOOT answers `reboot
    bootloader` with `setenv bootdelay -1`. Any `saveenv` at that prompt
    stores it, and so does typing `boot`, because bootmeth_rauc saves the
    environment on every boot. Every later boot then stops at the U-Boot
    prompt, which on a sealed projector means it never boots again. It
    happened here once and was repaired with `env default -f bootdelay;
    saveenv`. **Fixed by U-Boot 0013:** PREBOOT starts with `env default -f
    bootdelay`, before autoboot reads it. Tested: `-1` saved at the held
    prompt, and the next boot still counted down 2 s and booted slot B.
  - **UEFI boot cost (2026-11-20), the systemd-sysupdate question.**
    systemd-boot needs U-Boot's UEFI path, so its cost was measured without
    systemd-boot: the same slot B kernel started through `bootefi` (the
    kernel's EFI stub) instead of `bootm`, from a boot.scr variant. The
    variant reads the gzip kernel's data from the FIT with `fdt get addr`
    (`imxtract` will not extract a compressed image without a destination,
    and `CONFIG_SYS_XIMG_LEN` is only 8 MiB), runs `unzip`, then `bootefi
    addr:size fdt`. `EFI_LOADER`, `CMD_BOOTEFI` and the kernel's `EFI_STUB`
    were already on. Five measured rounds each, `tools/boot-timing.sh`
    (`local/recovery/boot-timing/v2-slotb-{bootm,bootefi}.csv`):

    | path | U-Boot→login s | kernel s | userspace s | systemd total s |
    | --- | --- | --- | --- | --- |
    | bootm | 15.08 [14.10..15.50] | 2.34 [2.27..2.37] | 8.91 [8.76..9.17] | 11.25 |
    | bootefi | 14.92 [14.40..15.70] | 2.47 [2.44..2.52] | 9.24 [8.81..9.60] | 11.71 |

    - Time to login is the same within noise.
    - systemd's kernel phase is about 0.13 s longer every time (the ranges
      do not overlap): the EFI stub and EFI runtime services.
    - Userspace is about 0.3 s longer on average, but the ranges overlap.
    - The U-Boot side is somewhat shorter, because the variant skipped the
      FIT's sha256 check.
    - All memory reservations matched, and the EFI runtime services came
      up.
    - One EFI boot had extra Bluetooth timeouts; the other six matched
      `bootm` exactly, so this is not the EFI path.
    - Not covered: systemd-boot itself (an ESP, entry scan, and a FAT rename
      per boot), and the display carveouts, because V2 U-Boot does not
      draw the display yet. Recheck both once Phase 4 step 2 lands.
    - boot_b was restored to the `bootm` image afterwards.
  - **Host mode with a stick after a switch (2026-11-20): failed, then
    fixed.** Two hangs, both from an owner that was never told the hardware
    had moved on:
    - Routing the port to musb silently cuts EHCI off (the PHY's passby).
      EHCI never saw a disconnect and kept the stick (`sda`) as present.
      Back in host mode it timed out resetting it (`port 1 reset error
      -110`, then `unable to enumerate`).
    - Removing the gadget blocked for good in `gserial_free_port`: removing
      the ACM function waits for `ttyGS0` to close, and the getty held it
      open. With a PC attached, the unbind hangs the tty up and the getty
      exits; with none, nothing does. This was the hang in the first try.
    - Fix in `h713-usb`: every role change is an explicit handover.
      1. Stop the gadget's users (the `ttyGS0` getty, `h713-usb-net`)
         before removing the gadget.
      2. Unbind ehci0/ohci0 (`4101000.usb`, `4101400.usb`) before routing
         the port to musb.
      3. Bind them again after routing back to host. A fresh EHCI probe sets
         the PHY to host itself and enumerates from scratch.
    - Tested with the stick in and no PC: one traced device → host switch,
      then three more full cycles. In device mode `sda` was gone every time;
      in host mode it was back every time and read 16–64 MiB (37 MB/s).
      No reset errors.
    - Not yet run: the new script in the image (it was uploaded to `/run`
      over the UART), and device mode with a PC since this change.
- **Back-feed.** The 5 V is on in both roles. In device mode use an A-to-C
  cable into a compliant USB-C port (measured: it sources nothing to this
  plug) or a VBUS-cut cable. A plain A-to-A cable ties the board's 5 V to the
  PC's. Software cannot prevent this.
- **Not done:**
  - U-Boot keyboard input (host mode at power-on, `usb start`, usbkbd).
  - RAUC bundles over USB, which need signing keys.

## Open questions for Chris

1. How physically accessible is the projector (UART, FEL button, USB OTG)?
   Can it be opened? This picks the Phase 1 route.
2. Is it still on stock Android with `adb` available, unchanged since 06-22?
3. Is it acceptable to leave its Android removable at project end, as on the
   bench?
