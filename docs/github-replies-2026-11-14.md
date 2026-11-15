# Responses to well0nez — 2026-11-14

Fixes and evidence are published in [aed24b42](https://github.com/cstenger/allwinner-h713-mainline/commit/aed24b42e6254f981bae5a1fc8925a490d840d3c).
All four comments were posted and their bodies read back and verified.
The comments below include the source investigation and completed DDR3 hardware tests.

- [Issue #1 posted response](https://github.com/cstenger/allwinner-h713-mainline/issues/1#issuecomment-6887251866)
- [Issue #2 posted response](https://github.com/cstenger/allwinner-h713-mainline/issues/2#issuecomment-6887252180)
- [Issue #3 posted response](https://github.com/cstenger/allwinner-h713-mainline/issues/3#issuecomment-6887252466)
- [Issue #4 posted response](https://github.com/cstenger/allwinner-h713-mainline/issues/4#issuecomment-6887252759)

## Issue #1 — Nice work Mate

https://github.com/cstenger/allwinner-h713-mainline/issues/1

Thanks for this, and sorry for leaving it unanswered for so long. Your drivers and reverse engineering gave this project a substantial head start, and the attribution matters.

There is a useful answer now to the arm64 CPU_COMM question: the bench completes CALL → CALL_ACK → RETURN → RETURN_ACK. The shared structures stayed 32-bit; the driver uses `cc_ref` to distinguish shared physical references from driver-local references instead of truncating host kernel pointers. That also exposed pointer-width bugs in list and slot handling, and an initialization path that would wipe queues belonging to a running MIPS.

The [August 31 results](https://github.com/cstenger/allwinner-h713-mainline/blob/10af96af825dfef18b51f22b949f2f204ca9047f/docs/handoff-2026-08-31.md) record Linux round trips at roughly 17–30 ms. The later [transport notes](https://github.com/cstenger/allwinner-h713-mainline/blob/10af96af825dfef18b51f22b949f2f204ca9047f/docs/board-bringup-sequence.md#7-cpu_comm-transport-state-engine) cover the shared-ring initialization and acknowledgement lifecycle too. Those are bench results with our firmware, rather than a diagnosis of your 19-ACK/zero-RETURN case.

If you still have them, the most useful notes would be the HY310 CPU_COMM traces and firmware identity, plus HDMI-RX/EDID and audio initialization ordering, especially anything that depends on vendor U-Boot having run first. Links or rough notes would be welcome; there is no need to turn them into a polished port or commit to sustained work.

## Issue #2 — Archived cpu_comm and the doorbell question

https://github.com/cstenger/allwinner-h713-mainline/issues/2

Thanks for explaining the two copies. I should have checked the live driver before reconstructing the register map. The corrected transport is now on `main`: RX count/data at `0x164/0x174`, TX count/data at `0x864/0x874`, a `0x1000` mapping, and a TX IRQ-enable pulse at `0x830`, `BIT(3)` for MIPS port 1.

On the packing question, I checked the actual dispatcher bytes again and ran them in Unicorn. With our current research firmware, SHA-256 `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`, inputs `0..3` reach CALL/RETURN/CALL_ACK/RETURN_ACK respectively; `4` and all four `0x00020000..0x00020003` inputs return without dispatching. The emulator stubs logging and stops at handler entry, so this tests parsing, not mailbox delivery. This is also a different image from the `a79017e5...` image mentioned when this issue was opened. Our working sender uses the bare type and TX_IRQ_EN pulse, and the existing Linux bench results establish full round trips with that transport. Your newer 0014f also qualifies the pulse explanation: the vendor uses TX_IRQ_EN as an ISR-managed level, and the old pulse experiment was confounded by a parked MIPS. We should keep the working sequence while testing whether the pulse is necessary; the emulator settles encoding, not that hardware mechanism.

There is a useful update on your side too: your current [0014a patch](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0014a-soc-sunxi-cpu-comm-der-h713-stand-vom-04-09.patch) already sends `type & 3`, with callers passing `0 /*sender=ARM*/` in the first argument. The older local driver snapshot I checked also passes sender zero at both remote send sites. So the encoder's argument name alone does not establish that those calls wrote `0x0002xxxx`. That does **not** establish where your historical 19 ACKs came from: we still need the exact build and firmware identity, actual TX/RX FIFO words, and shared ACK metadata to settle that particular result.

There are also independent ways to get ACK without RETURN: the ARM-local staging FIFOs must be initialized, pre-populated free rings need the expected `peak_count`, and ACK publication bits and RETURN_ACK metadata must be consumed correctly. The [transport lifecycle notes](https://github.com/cstenger/allwinner-h713-mainline/blob/10af96af825dfef18b51f22b949f2f204ca9047f/docs/board-bringup-sequence.md#7-cpu_comm-transport-state-engine) document these findings.

[Source checks and firmware-emulation details](https://github.com/cstenger/allwinner-h713-mainline/blob/aed24b42e6254f981bae5a1fc8925a490d840d3c/docs/github-issue-investigation-2026-11-14.md) are published with the exact test limits.

Agreed on ge2d: our negative results should stay tied to the tested firmware and board. Your port and notes would be useful, particularly the successful call sequence and binary-specific offsets. The firmware hash and differences in initialization order would be a good starting point.

## Issue #3 — HY260_QZ713_V3.1 and USB host

https://github.com/cstenger/allwinner-h713-mainline/issues/3

Thanks for the boot log, the corrected on-device parameters, and the USB investigation. Your result establishes a third board variant: HY260_QZ713_V3.1, DDR3, 1 GiB, booting with `CONFIG_DRAM_CLK=792` and the bench configuration's remaining DRAM parameters. The README's wording is too broad: the two entries describe our own boards, and being inside a projector does not imply LPDDR3.

For our QZ713_V2, I went back to the captured stock boot0 bytes rather than just the config comment. The Board A image, SHA-256 `f8ac16e44a83869c8fa7193531bc3a8b228235428a99ac426daa0902026c9f0f`, has `dram_type=7`, 720 MHz, ZQ `0x003f3ffb`, and ODT `0x31` in the parameter block at offset `0x38`. Those match [the pinned LPDDR3 defconfig](https://github.com/cstenger/u-boot/blob/320a17f71d41ed0d4be7aab25947ce015c98c48e/configs/hy200_qz713_v2_defconfig). The saved bench eMMC boot0 independently decodes as type 3 at 624 MHz. The profiles therefore have captured-boot0 provenance; they were not selected solely from board names. That still does not validate our LPDDR3 SPL on hardware. I have no new chip-marking confirmation or bench result at 792 MHz. Your speed-bin caveat is right; your board's stock clock does not establish a safe clock for our Samsung parts.

I also checked [U-Boot PR #1](https://github.com/cstenger/u-boot/pull/1). It was closed without a merge, so I should not describe those six commits as integrated. Checking the prepared build gives a more specific status: the generated H713 CCU table now uses `0xa78` for port 1 and `0xa80` for port 2, and the shared DT contains R_PIO and the EHCI/OHCI nodes. H713 currently binds to the D1 PHY configuration, which **does** set `hci_phy_ctl_clear = PHY_CTL_SIDDQ`; the initialization path clears it. That configuration still exposes only two PHYs. I initially flagged the missing `pmu_enable_bit0` field too, but the full code review found that `sun4i_usb_phy_passby()` already sets PMU-base bit 0 as `SUNXI_ULPI_BYPASS_EN` for host PHYs, so that is not a demonstrated missing operation. On the Linux side, your 0005a adds a genuinely missing HCI SIDDQ clear to our H713 configuration and removes dependence on bootloader initialization; it is now integrated as patch 0192, with your attribution. The old unchecked `board_init()` PB5 path is disabled in our prepared DDR3 config, which now has separate display power handling. We have since cold-tested the Linux USB fix on our DDR3 bench with saved preboot `usb start` temporarily omitted: the SanDisk SSD enumerated at 480 Mb/s on EHCI0, with all six root controllers registered. The saved test setting was verified and the original environment restored byte for byte. This tests our socket, not HY260 VBUS/fan behavior or every controller.

The [DDR3 hardware record](https://github.com/cstenger/allwinner-h713-mainline/blob/aed24b42e6254f981bae5a1fc8925a490d840d3c/docs/reviews/well0nez-2026-11-14/hardware.md) includes exact artifact hashes, test conditions and restoration evidence.

Thanks also for the LLVM and GnuTLS build notes. The historical LLVM 22 documentation pin records a known-good build, not a minimum requirement (the production rebuild here used LLVM 23.1.4); your LLVM 20 result is useful evidence. The current toolchain instructions target Arch/CachyOS, so the Debian package name `libgnutls28-dev` belongs in distro-specific instructions.

## Issue #4 — HY310 fixes

https://github.com/cstenger/allwinner-h713-mainline/issues/4

Thanks for publishing these separately and retaining the provenance. I checked them against our series and have now integrated the PIO and Linux USB fixes. Several other findings below remain outstanding.

I have committed and pushed the PIO lookup/DT pair and Linux HCI SIDDQ fix, alongside your VP9 stack reduction and the HEVC validation work, as [patches 0191–0197](https://github.com/cstenger/allwinner-h713-mainline/blob/aed24b42e6254f981bae5a1fc8925a490d840d3c/docs/reviews/well0nez-2026-11-14/integration.md), retaining authorship and pinned source links. The default and production kernel builds pass, as do source-bound host tests and both compiled GPIO DTBs. On our DDR3 bench, seven valid HEVC/VP9 vectors (748 displayed frames) are bit-exact with positive VE IRQ counts, and all three deliberately invalid HEVC control cases are rejected with bit-exact clean decode afterward. The [full hardware results and limits](https://github.com/cstenger/allwinner-h713-mainline/blob/aed24b42e6254f981bae5a1fc8925a490d840d3c/docs/reviews/well0nez-2026-11-14/hardware.md) also record the PH17 and cold USB tests below.

- **Pinctrl:** I reproduced the mismatch from our actual IRQ-bank map, DT list, and lookup expression: PF/PG/PH select SPI **59/60/61**, where lookup by IRQ-bank index selects **58/59/60**. That also puts PG's handler on PH's SPI 60, matching your failure mechanism. Your 0143/0144 pair addresses the source defect; the lookup fix must precede trimming the DT list. I then tested PH17 on the candidate: changing weak input pull bias through the GPIO API produced exactly eight hardware interrupts, four rising and four falling, with no storm. The test module released the IRQ and restored the original input/bias-disabled state.
- **Linux USB:** your 0005a is committed as 0192. On a physical cold cycle with preboot `usb start` omitted, our SSD enumerated at 480 Mb/s on EHCI0. It remained unmounted/read-only, and the original saved environment was restored exactly. Other ports and Linux gadget operation are not qualified by this test.
- **CPU_COMM:** I independently checked our saved stock DT: the msgbox interrupt list is `0x2e/0x6d/0x6c`, or **46/109/108**, matching your report. Our register window is already `0x1000`, but the DT still incorrectly names SPI 21. The driver defaults to polling, so our round trips never validated that IRQ. Your later 0014c ownership fix matters too: the ARM driver should request the line of its own inbox, not all three lines. One qualification: our saved stock DT puts OWA0/S/PDIF at SPI 23, although our current DTS says 21, so I would not treat ownership of SPI 21 as settled by that label. The msgbox correction is independently supported. Existing SPI-53 storm notes describe the old SPI-21 configuration, not a test of SPI 46; IRQ-driven operation still needs bench validation.
- **U-Boot environment:** this is fixed in our build now by [the full-width fallback patch](https://github.com/cstenger/allwinner-h713-mainline/blob/10af96af825dfef18b51f22b949f2f204ca9047f/patches/u-boot/0003-env-mmc-preserve-configured-offset-width.patch). I reran the source-based regression suite: **13 cases pass**, and all **nine** tested source mutations are caught, including restoration of the original narrowing. The patch preserves the configured 64-bit fallback while retaining signed DT-property behavior. On our bench, the environment moved from unintended LBA `0x32ec00` to configured LBA `0x49ec00` through a paired migration. [Storage verification and cold/warm boot evidence](https://github.com/cstenger/allwinner-h713-mainline/blob/10af96af825dfef18b51f22b949f2f204ca9047f/patches/u-boot/README.md) are linked in the series README. Existing installations need the migration as well as the corrected U-Boot image.
- **Smaller fixes:** the focus-motor description and the AFBD probe's 1280×720 restriction remain in our series. Removing the probe restriction alone would not establish a fully working 1080p video path; the remaining geometry assumptions need review too. The kernel series loops skip empty lines but still lack comment handling.

The PIO and Linux USB follow-ups are now on `main` with your attribution. A focused CPU_COMM interrupt correction and your board-specific test evidence would still be welcome. The existing patch files are also enough to start from; there is no need to duplicate the environment fix. Please retain your authorship and the hardware evidence in the commit messages. Thanks again for making these findings available.

