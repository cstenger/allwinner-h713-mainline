# Pre-logo control census — October 20, 2026

The [first paired trials](hdmi-evidence/2026-10-20-reset-comparison/README.md)
found the same five MIPS/latch controls after clean and abrupt resets. The next
bench image adds **22 control-window reads**, not a DSP protocol probe. It
cannot establish DSP versions, power-good, receiver readiness or safe recovery.

## Access audit

| Access | Source evidence and decision |
| --- | --- |
| CCU at `0x02001000` | The pinned U-Boot `h713_display_clocks_on()` identifies this control window as always clocked, distinct from gated peripheral blocks. Existing TVCAP preparation accesses `0x02001d6c/74/80/84/88`. The kernel CCU driver independently defines these gates. Read the controls without enabling or changing them. |
| TVFE/audio CCU at `0x02001d10..64` | `modules/hdmi-audio/h713-hdmi-tvfe.c` saves 15 functional words before applying stock clocks; demod bus/reset is a separate word at `0x02001d64`. Read those same control words, not `TVFE_PHYS_BASE=0x06e00000`. The words describe programmed controls, not downstream access safety. |
| SCP run/reset at `0x07000400` | Signal/SCP modules read the initial value before touching SRAM or releasing SCP; bit 0 is the run control. TF-A H713 maps this region as R_CPUCFG and uses neighboring CPU power controls. Add one read in proper only. This is source-based access justification; the new early-stage read still needs a cold hardware control. |
| DSP versions `0x80ff` | `h713_hdmi_dsp_prepare()` first claims the hardware lock and waits for busy-clear. `h713_dsp_stock_response()` writes a request to the command port, polls completion and consumes the response. A logical read changes protocol state. **Excluded.** No DSP port, busy/done, lock or graph access in this patch. |
| Receiver HPD/DDC/TVFE registers | Signal ownership uses SCP-side accesses; ARM direct receiver reads can hang without the full power/clock tree. **Excluded**, including the seemingly read-only HPD register. |
| SCP SRAM, vectors and mailbox markers | Signal initialization backs up/rewrites SRAM; an inherited running SCP may update it concurrently. Safe mapping/coherency and preboot modification boundaries are not established here. **Excluded.** Run/reset does not prove SRAM freshness. |

These are local source observations, not a silicon guarantee. SPL/BL31 and
earlier proper initialization precede the new census. It cannot identify
exact hardware reset-entry values or which stage changed a word. No new
access is performed by optional SPL probes.

## Implementation and evidence handling

[0003-proper-domain-controls.patch](../tools/hdmi/reset-trace/0003-proper-domain-controls.patch)
is opt-in, outside the production U-Boot patch series. Use
`prepare-reset-trace.py BASE OUTPUT --include-domains`. It retains the
existing `H713 RESET v1` records and emits one adjacent `H713 DOMAINS v1`
line for each proper-stage snapshot. It reads a complete vector before
printing it; the vector is sequential, and the preceding MIPS snapshot was
read earlier. UART output adds timing overhead. No firmware launch, clock,
reset, SRAM, RTC latch or saved-environment write is added by the probe.

The schema is a fixed ordered set: SCP reset; 15 TVFE functional clocks;
demod bus/reset; TVCAP TCD3, DMA, shared bus, HDMI-audio and bus/reset.
`cap_bus` is one raw word containing both bus-HDMI-audio and bus-CAP-300M
gates; do not interpret the shared word as one gate.

[analyze-domain-trace.py](../tools/hdmi/analyze-domain-trace.py) requires one
proper boot, a complete vector immediately following every proper marker,
and exact field names/order/hex widths. It refuses truncated, detached,
duplicate and mixed-boot evidence. It preserves repeated workspace stages
and reports differences/missing stages, always with recovery `unproven`.
Use it alongside the original reset analyzer, with one extracted raw
post-reset boot per method.

Offline checks compile and execute the actual patched header against a mock
MMIO allowlist; any additional/different address aborts. A separate SPL-path
check permits only the original four reads. Parser tests cover equal states,
differences, missing stages and malformed evidence. The normal preparer's
isolation checks still pass. These tests do not validate real hardware access.

## Prepared artifact and install boundary

The DDR3 build succeeded in `build/hdmi-reset-controls-2026-10-20/`, using
the normal pinned source plus the two proper-only bench patches and existing
BL31. No new probe warning was reported; existing U-Boot warnings remain.
Build/source/config/compiler hashes and fixture results are in the
[preparation record](hdmi-evidence/2026-10-20-reset-controls/preparation.json).
No LPDDR3 hardware/build qualification is claimed by this run.

The proper FIT is **960817 bytes**, padded to **961024 bytes / 1877 sectors**
at LBA `0x49ac00`. This extends the prior 1867-sector write by 5120 bytes.
Those bytes are zero-filled in the authenticated prior 2-MiB primary-region
image. The extent remains inside that region, before configured environment
LBA `0x49ec00` and rescue LBA `0x4a0c00`; active environment LBA `0x32ec00`
is elsewhere. The exact 1877-sector rollback restores the previous trace
plus those original zero bytes. Do not use an old 1867-sector rollback alone.

Candidate SHA-256:
`1b1f702fc7b52adf8246b124b8fbe209b7dadc651a37e53a600689810c45302e`.
Rollback SHA-256:
`dffd10fe06d32e329364fe53558786bd408ad1af42e5ef7ef800aa975e479317`.
Extracted BL31 and U-Boot DTB match the installed components byte-for-byte.
SPL is not installed. The local package checks both environment locations,
SPL, rescue, and the full 2-MiB primary region before/after writes. Mocked
sparse-disk fixtures passed argument refusal, environment-mismatch refusal,
installation/readback and exact rollback. No fixture touched a real device.

## Hardware sequence

Install only after those identity checks pass against the live board and
retain the exact rollback/rescue package. Orderly poweroff, then an
operator-confirmed fully disconnected cold cycle establishes the control
for the new reads. Require complete UART stages and healthy autonomous
startup before proceeding to another reset. Stop at any unexplained failure;
do not retry around a guard or clear GP6.

Then repeat the separate-cold clean and synced SysRq-b trials. Record the
immediate Linux boot ID through the same UART capture and complete the Linux
collector before ending the recording. Keep the capture through any later
power action, and explicitly record any gap. The previous usage-limit gap
must not recur as an implicit boot correlation.

The remaining DSP freshness question requires a separately reviewed access
protocol or firmware-side passive observation before logo initialization.
Clock-control equality alone cannot authorize a DSP command. Recovery design
and actual watchdog-expiry qualification remain pending.

## Hardware status

Subsequently installed and validated through one physical cold control and
one orderly reset. See the [live result record](hdmi-evidence/2026-10-20-reset-controls/README.md)
for boot IDs, exact readback and unchanged-region checks. The cold run passed
the new read boundary and autonomous startup checks; the clean reboot restored
all owners and skipped warm capture. The independently cold-started abrupt
comparison is pending. DSP freshness and automatic recovery remain unproven.
