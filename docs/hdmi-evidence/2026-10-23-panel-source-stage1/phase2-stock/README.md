# Phase 2: stock round trip (10-23)

§10.21.3 Phase 2 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).
The lab folder for this session is `local/h713-lab/stock-capture-20261023/`.

## Prep (done, before `switch_vendor`)

**Read-only eMMC checks**, from our Linux (boot `34ee92bd…`, root
`mmcblk0p26`):

| Check | Result |
| --- | --- |
| Board LBA 16 first stage (eGON.BT0, 32768 B, `cb9da874…`) inside `build/out/h713-restore-spl.bin` | **yes**: the FEL restore puts back exactly what runs now |
| LBA 256 vendor boot0 = `local/stock-boot/boot0-board-b-emmc-sector16.bin` (`b769a415…`) | **yes** |
| U-Boot proper, LBA `0x49ac00` × 1877 | `1b1f702fc7b5…` (the expected production build); re-check after return |
| `super` (p9) +4096 | `gDla` |
| `boot_a` (p5) / `vendor_boot_a` (p7) | `ANDROID!` / `VNDRBOOT` |
| UDISK (p27) | f2fs magic `10 20 f5 f2`, not mounted |
| `misc` (p10) | RescueParty left-over (`recovery --prompt_and_wipe_data --reason=RescueParty`), as on 10-01. If recovery appears: **Try again**, never Factory data reset |

**Host side:**
* `adb` is present, and `sunxi-fel` and `h713-restore-spl.bin` (Aug 26) are
  in place.
* `hidtvreg-read` (`a3d0f6f2…`) and `hidtvreg-raw` (`f9e793e2…`) are
  copied into the lab folder. They're identical to the 09-29 and 10-01
  session binaries.
* `capture-session.sh push-tools` pushes only the readers and
  `stock-capture.sh` (no media).

**Vendor elog** (approved): `tools/stock/vendor-elog-cfg.sh on`, giving
stock → elog (verified by hash). **Revert with `off` after the return.**

**Host display:** HDMI-A-1 is now `1280x720 @ 60.000 Hz (current)
(preferred)` under our EDID. Under stock's EDID the default may differ
(10-07: 1080p). S2 forces 1280×720; restore to whatever stock's default
was afterwards. Under our EDID, 1280×720 is the default again.

## Session log

1. **Reboot to the prompt:** `systemctl reboot` over ssh (a plain reboot;
   GP7 untouched), plus `reboot-to-uboot.py --wait-for-power-cycle`
   (keys only). U-Boot `2026.07-rc5-g320a17f71d41`, `gp7=00000000`,
   prompt caught (`uart-reboot-to-uboot.log`).
2. **`switch_vendor`**, the definition printed first
   (`uart-printenv-switch_vendor.log`): `mmc read 0x100 → itest eGON →
   mmc write 0x10`. Result: `VENDOR FIRST STAGE INSTALLED`
   (`uart-switch_vendor.log`).
3. **Verified with reads only** (`uart-verify-lba16.log`): LBA 16 and
   LBA 256 compare equal over all 32768 bytes; LBA 16 crc32 `0c95afa2`
   equals the reference vendor boot0's crc32 (`0c95afa2`).
4. **Operator cold boot** (serial and USB unplugged, at least 1 minute
   off, HDMI connected). The Android logo appeared; adb (`ADT_3`) was up
   at 187 s with the boot animation running, then `sys.boot_completed=1`.
   No recovery screen.
5. **check / push-tools:**
   * fingerprint `ADT-3/adt3/adt3:11/RP1A.201005.006/projector.20250922.093247`;
   * `/dev/hidtvreg` is `crwxrwxrwx`;
   * `/data` has 678 MB free;
   * pushed hashes `a3d0f6f2` (read), `f9e793e2` (raw), `02a60144`
     (`stock-capture.sh`).
6. **Baseline:** firmware text == board-B `display.bin`; loaded cfg
   `mode 2 / level 5` (elog live). Idle samples are in `out/idle-*`.
7. **S0** (launcher, no HDMI source): `sweep S0-a`, `S0-b`, about 6 s
   each.
   * A 5504, A′ 188, B 272 words, the same counts as ours; list B read
     cleanly on stock for the first time.
   * C 14 946 304 bytes (`bdcedd14…`, `1de6db98…`).
   * Pulled to `local/h713-lab/stock-capture-20261023/out/`.
   * The host reads HDMI-A-1 `disconnected` until stock selects HDMI1
     (as on 10-07).
8. **HDMI1** selected by the operator (AwSource).
   * Host HDMI-A-1: stock EDID `PNP(WSX) SGD SX8`, **1920×1080 @ 60 Hz**
     (preferred).
   * COSMIC had dropped the chart wallpaper (new monitor model). The
     operator set it again.
   * **Operator: the colour is correct, unlike any of our tests.**
9. **S1** sweeps `S1-a`, `S1-b` (`9c88e5f1…`, `db3da0cc…`), pulled.

## Finding: stock does not use the firmware's capture route

| Word | Ours O2 (y/2 chroma) | Stock S1 (correct) | Stock S0 (launcher) |
| --- | --- | --- | --- |
| AFBD `0x10` | `03000203` (format 2, mode-1 capture) | **`03000013` (format 0 = NV12 4:2:0)** | `03000013` |
| AFBD `0x4c` chroma rows | 720 | **360** | 360 |
| AFBD queue `0x70` (Y) / `0x84` (C) | 0 (capture pair) | **`0x00400000` / `0x004E1000`, then `0x00600000` / `0x006E1000`**: NV12 frames at IOVAs, C = Y + `0xE1000` | `0x00200000` |
| AFBD VideoInfo `0x98` | 0 | `0x4D947000` / `0x4D95C000` | — |
| comp `0x030` | `00400000` (mode-1 routing) | **`00000C00` (decoder routing)** | `00000C00` |
| comp `0x178` / `0x278` | `6…` (NR history off) | `E…` (on) | `E…` |
| IOMMU `0x030` bypass | `0x58` | **`0x00`** (every master translates) | — |
| selector / chroma gain | `39000000` / `144C0000` | `39000000` / `044C0000` | `39000000` |
| capture pair `+0x320` | cycling | cycling (capture still writes the 4:2:2 ring) | — |

**Interrupts and CPU, S0 → S1:**
* `1800000.gpu` goes from about 5/s to about **440/s**.
* SurfaceFlinger runs at 45 % CPU, `awtvinputservice` at 29 %, and the
  `mali_jd` worker is active.
* `dec` and `osd-afbd` tick at 60 Hz in both states. `5240000.ge2d` (the
  unlabelled `0x05240000` window is **GE2D**) runs at about 135/s in both,
  so it has nothing to do with HDMI.

**Firmware state on stock (node walker, S1 image):**
* NRWinNode `afbd_source_mode = 1`, colour format 4: the **same** as ours.
* MemoryAgent source 1, signal `0x20077` (ours: 0, `0x20003`).

So the firmware sits in capture mode on stock too, but its frame
programmer never takes over AFBD. The hardware is driven by the ARM
decoder path.

**Conclusion:**
* Stock shows HDMI by **GPU-compositing the TV-input layer (SurfaceFlinger,
  Mali) into 1280×720 NV12 frames** and presenting them on AFBD source 0
  in the **decoder configuration** (format 0, mode 2 routing, IOMMU
  translating). This is the same route stock uses for file playback (10-01)
  and for its whole UI (S0 also runs on the video plane).
* The firmware's mode-1 capture route that T3–T6 drove (`win rn 2`, agent
  4, format 2) is **never used by stock**. Its half-rate chroma is a
  property of an unused path, not a missing setting that stock applies.
* The `comp+ac0–ad4` "half chroma count" lead from Phase 1 is normal 4:2:0
  accounting: stock S0/S1 hold `0x000E1000` / `0x00070800` there.

## S2 and the risky tiers

10. **Host HDMI-A-1 → 1280×720 @ 59.943 Hz** (`cosmic-randr mode`; the
    `--test` dry run reported a failure but the real apply worked).
    **Operator: chart full-screen, colour correct**, photo taken.
11. **S2** sweeps (`86fbd4e8…`, `0f27e0a7…`): the same decoder path
    (format 0, NV12 at IOVAs `0x400000` / `0x200000`, chroma rows 360,
    comp `0x030 = 0xC00`). The capture pair cycles. Everything was pulled
    (`capture-session.sh pull` also brought older sessions' files still on
    the Android side; harmless).
12. **Risky tiers**, `RISKY=1 stock-capture.sh risky N` through
    `adb exec-out`, streamed to
    `local/h713-lab/stock-capture-20261023/risky/tier{1..4}.txt`.
    **All four completed; no hang.** The board was alive after each.

| Tier | Reads | Result |
| --- | --- | --- |
| 1 | composition page 2 | 64 non-trivial words; lock words `0x05001530–153c` = `0 0 0 80000000` |
| 2 | 455 pages | 127 non-trivial: `0x05040000` (63 pages), vblend `0x05200000` (60, several mirrors), proc `0x051be000/051bf000`, route `0x0514f000`, LVDS `0x051cf000`. Composition pages 3+ are all trivial |
| 3 | 242 probes | 24 live 64 KiB blocks: `0x05050000–0x050b0000`, `0x05210000–0x05230000`, `0x052c0000`, `0x05800000–0x05870000`, `0x058a0000`, `0x058d0000–0x05900000` |
| 4 | capture page `0x06940000` | 117 non-trivial words; read fine on stock with HDMI live |

## Return (done)

13. **FEL:** the operator held the FEL button with USB and serial
    connected. `sunxi-fel version` reported `AWUSBFEX soc=00001860(H713)`
    (`fel-version.log`).
14. **`sunxi-fel -p spl build/out/h713-restore-spl.bin`:** the UART shows
    `=== H713 SPL RESTORE ===`, `wrote 64/64 RESTORED-OK`,
    `power-cycle now` (`uart-fel-restore.log`). The SPL's trailing
    `Please RESET` is its designed halt. The waiting `sunxi-fel` was
    stopped.
15. **Operator cold boot** (serial and USB unplugged, at least 1 minute
    off, HDMI connected) into our Linux: boot `24837bd8-0e00-46f7-a277-45d2e75be6f6`,
    root p26.
16. **Verified:**
    * LBA 16 `cb9da874…`, U-Boot proper `1b1f702f…` and LBA 256
      `b769a415…`, all identical to the prep checks;
    * no failed units;
    * `/chosen/h713,hdmi-boot-v1` present and `h713-hdmi-signal` ready
      (the production cold path).
17. **`vendor-elog-cfg.sh off`:** elog → stock (verified); status `stock`.
18. **Host HDMI-A-1** is back to `1280x720 @ 60 Hz` under our EDID (`H713
    HDMI IN`) by itself.

The board and the vendor FAT are exactly as before the session.
