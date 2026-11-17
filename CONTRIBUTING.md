# Contributing to allwinner-h713-mainline

Thank you for your interest in contributing to the Allwinner H713 mainline bring-up project!

## Reporting Issues and Test Results

When submitting bug reports, hardware test findings, or bring-up observations:
- **Specify the exact physical board variant**:
  - **Bench board**: `HY200_QZ713DF_A1` (DDR3, Samsung K4B2G 1 GiB)
  - **Projector board**: `HY200_QZ713_V2` (LPDDR3 1 GiB)
  *Note: DRAM training parameters differ between variants. Always specify which board variant was tested.*
- **Include UART console logs**:
  - Provide full serial logs from hardwired UART (`ttyUSB0`) starting from power-on / BROM.
  - If using USB-CDC console (`ttyACM*`), note any mode transitions.
- **Reference Project Documentation**:
  - Review [`docs/status.md`](docs/status.md) to check current subsystem status.
  - Review [`docs/build.md`](docs/build.md) for build environment and reproducible recipes.
  - Check [`docs/bringup-notes.md`](docs/bringup-notes.md) for known silicon quirks and driver findings.

## Submitting Pull Requests

1. **Licensing**:
   - All contributions must be compatible with **GPL-2.0-only**.
   - Include the standard SPDX header in new files:
     ```
     // SPDX-License-Identifier: GPL-2.0-only
     ```
   - Submodule updates or patches for upstream trees (U-Boot, TF-A, Linux kernel, sunxi-tools) should follow upstream formatting and commit conventions.
2. **Commit Hygiene**:
   - Write clear commit messages describing *what* changed and *why*.
   - Keep commits modular and bisectable.
   - For kernel patches, place them in `patches/kernel/` following the existing numbered patch sequence.
3. **Verification**:
   - Verify that builds pass via `tools/build/build.sh all` or the relevant stage.
   - If proposing hardware or driver changes, state the hardware verification results and tested board variant.

## Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.
