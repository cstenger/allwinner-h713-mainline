# DDR3 bench hardware results — November 14, 2026

The selected follow-ups passed the tests below on **HY200 QZ713DF_A1,
DDR3**. The candidate remains installed. The temporary no-USB-preboot
environment was restored byte for byte, and final startup health passes.
This record describes hardware verification completed before publication.

## Installed candidate and reproducible baseline

Before installation, release-equivalent rebuilds reproduced the installed
baseline FIT (`9d49630823d0…`) and Cedrus module (`653181f3bd53…`) byte for byte.
The candidate has the same configuration, kernel release and Module.symvers.
The DTB comparison allows exactly the PIO parent-interrupt list change from
SPI 54–62 to SPI 54–60; unrelated DT changes are refused.

| Installed file | SHA-256 |
| --- | --- |
| Kernel FIT | `22ee12d4bef763a6ee60e5c679e41262acfae19c2567b5c93abde3332e96cd83` |
| Cedrus module | `1c8c87bae78ad6fce0522faa89b37d02bda511af1535b669dcb655a85ce0d3f2` |
| Startup script | `79c039acb7e77087ec143f9f1214c877b5567a926f65c7a43a4b3a4ffc11badd` |

Cedrus is a loadable module: a FIT-only update would not test the VP9/HEVC
driver changes. The guarded installer was extended to include this optional,
baseline-reproduced module in the same backup, staging, failure restoration
and rollback scope. Twelve installer tests and six bundle-builder tests pass.

## Valid decode: seven vectors, 748 frames

Each stream passed a software-control decode on the board against the
host-generated raw NV12 hash. GStreamer was then forced through the named
V4L2 hardware decoder. Hardware output had to match both byte count and
SHA-256, and the VE interrupt delta had to cover every displayed frame.

| Vector | Codec | Frames | VE IRQ delta | Result |
| --- | --- | ---: | ---: | --- |
| h01, 640×480 Main | HEVC | 25 | 25 | Bit-exact |
| h04, default scaling lists | HEVC | 25 | 25 | Bit-exact |
| h05, custom scaling lists | HEVC | 25 | 25 | Bit-exact |
| h06, lossless | HEVC | 25 | 25 | Bit-exact |
| Native 1280×720 | HEVC | 300 | 300 | Bit-exact |
| Native 1280×720 | VP9 | 300 | 308 | Bit-exact |
| Short GOP, 640×360 | VP9 | 48 | 48 | Bit-exact |

## Malformed HEVC controls and recovery

A process-local ioctl interposer changed one inter-picture control in each
test pipeline. No global preload configuration was changed.

| Injected fault | Observed rejection | Subsequent clean decode |
| --- | --- | --- |
| Active L0 count minus one = 255 | V4L2 control submission returned `EINVAL` | 25 frames, bit-exact |
| L0 reference index = 255 | Cedrus setup returned `-EINVAL` | 25 frames, bit-exact |
| Temporal-MVP collocated index = 255 | Cedrus setup returned `-EINVAL` | 25 frames, bit-exact |

No new IOMMU faults, frame-processing timeouts, kernel warnings or oopses were
observed in these test windows. This exercises deliberate validation failures,
not every form of damaged bitstream or general decoder fault recovery.

The first harness incorrectly required the whole GStreamer pipeline to return
nonzero after a rejected job. GStreamer returned zero for the invalid-reference
case even though the kernel logged its `-22` rejection. That run is preserved.
The corrected harness requires the appropriate ioctl/kernel rejection and a
bit-exact clean decode afterward; all three cases pass under that criterion.

## PH17 interrupt delivery

PH17 was confirmed unclaimed and bias-disabled before the test. A bounded
test module requested it as an **input** with both edge triggers, then changed
only weak pull bias through the GPIO configuration API. It received exactly
**eight hardware IRQs: four rising and four falling**, Linux IRQ 230, without
a storm or loss of system progress. It then freed the IRQ, restored input
bias-disabled, released the line and was unloaded. Final pinctrl readback
confirms PH17 is unclaimed with its original bias.

An earlier character-device reconfiguration trial produced no event and was
restored; that trial is not counted as a pass. The kernel GPIO-configuration
trial provides the positive hardware edge evidence. No GPIO was driven as an
output, and the adjacent panel-reset pin was not changed.

## Cold USB host enumeration

Warm enumeration first identified the SanDisk Extreme SSD (`0781:55ae`) on
the board at **480 Mb/s**. It was kept unmounted and set read-only.

For the independent cold test, only the trailing `; usb start` was removed
from saved U-Boot `preboot`. Board identity, eMMC identity, original bytes and
environment CRC were checked; the original 64 KiB environment was backed up
and fsynced before writing. The board was shut down, and the operator performed
the requested full power/USB disconnection and cold cycle.

On cold boot `0fa73d3d-eb1b-47e1-9e21-d494f68d2df9`:

- All three EHCI and three OHCI root controllers registered.
- The SSD enumerated at **480 Mb/s** on EHCI0 (`0x04101000`), as USB `6-1`,
  and appeared as the expected approximately 1 TB block device.
- Readback of saved environment still matched the temporary no-`usb start`
  hash, establishing that the intended test setting was active.
- The SSD was unmounted and set read-only; no test wrote its data.

USB bus numbers differed from the warm boot; controller identity, rather than
bus number, identifies the tested physical port. This verifies that socket's
cold Linux host initialization without the usual preboot command. It does not
qualify peripherals on every unwired controller, full/low-speed devices, or
Linux gadget operation (the device-side DT node is intentionally disabled).

## Restoration and current state

After the interrupted host session, work resumed on boot
`2f81b106-80ae-4fee-8883-d026a724f770`. The exact temporary environment was
verified again, then the original was restored and read back:

`e6a56d4c6f2703c9360c29da4d1e1aec2d35bafd57bc6ca8232896e0296bc3ab`

Final checks confirm the candidate FIT/script/module hashes, PH17 restoration,
test-module absence, SSD at 480 Mb/s/read-only/unmounted, all four startup IPC
gates, successful health acknowledgement, `running`, and no failed units.
The original `usb start` boot behavior is restored for subsequent boots.

Raw evidence, harness sources, exact backups and rollback instructions remain
local under `local/recovery/2026-11-14-kernel-followups/`. Environment bytes and
raw UART/storage captures are not redistributed. The paired kernel/module
backup is `/var/lib/h713-hdmi-startup/kernel-fit-74b3f9c8971d48cd9a5efe475b568547`.

The physical R_PIO power-key/SDIO-host-wake stimulus tests, other boards,
10-bit decode vectors, broad damaged-stream stress and long-duration
reliability were not added to this bounded run. Wi-Fi, the existing power-key
IRQ binding and ordinary startup remained functional, but those observations
do not substitute for those separate tests.
