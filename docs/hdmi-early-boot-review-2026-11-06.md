# Initial HDMI detection: early boot review, November 6, 2026

The review found a real difference from the stock firmware's resource startup,
but no established cause of the missed first advertisement. The captured boot
does not show an earlier working EDID advertisement. Its EDID block was still
in reset at Linux receiver setup, and its DDC pins were disabled immediately
before the Linux signal owner claimed them. Those observations cannot exclude
an earlier transient or establish the physical HPD voltage.

This review used the saved complete UART capture, the current board's installed
command script, the matching prepared U-Boot source, kernel/module sources and
the original board-B display firmware. Only the command script and current
runtime identity were read from the board. No firmware, boot script, clock,
pin state, module, service or power state was changed on the board.

## Identity and evidence

- Source boot: `9df6717c-ea4b-4585-b53f-270178c13431`.
- Board boot: `d50d994e-b1f6-4afc-8b84-dccf6483c1b5`.
- U-Boot UART version: `2026.07-rc5-g320a17f71d41-h713-b3b5f2d2`.
- Matching prepared source cache: `build/uboot-src-b3b5f2d2575fedc5016774e92caa14772d4f8ec7f1c25bf8c71510a8430f8396`.
- That tree's `h713_mips.c`: SHA256 `3c44fc5af23eaa55a698fbc1e5e509cb23cff76382c4d5425b1d178cc829b450`.
- Installed command script read back: SHA256 `33677778d4ce232d31d94ff36c6082583229cc41a02ec4319c37a88b02f46c8b`.
- Board-B `display.bin`: SHA256 `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
- The existing audit verified raw SPL, proper and saved environment against
  their installed pins; it is not a new binary-to-source equivalence proof.
- Raw evidence: `local/recovery/2026-11-05-ddc-hpd-isolation/cold-01-uart/`.
- Readback, focused offline disassembly and prepared observations:
  `local/recovery/2026-11-06-early-hdmi-review/`.

## Observed boot sequence

| Stage | What runs | What it establishes |
| --- | --- | --- |
| SPL / BL31 | Native boot chain, followed by U-Boot proper | UART contains no stock SCP startup; the reviewed TF-A platform disables SCPI. This alone is not proof of all reset-line history. |
| U-Boot preboot | GP7 mode handling and USB startup | Saved `preboot` no longer runs the display firmware unconditionally. |
| Guarded HDMI script | Kernel/FDT validation, GP6 guard, lamp off | This precedes the two display-firmware runs. Existing crash-loop guard remains important. |
| First MIPS run | `h713_disp auto 0x34 logo` | Loads and authenticates the vendor firmware, defeats its HDCP key-load wait, runs it to readiness, then quiesces MIPS and publishes the logo. |
| Second MIPS run | `h713_disp mips-comm-trace 0x34` | Reloads the firmware/workspace, applies the CPU_COMM trace and runs MIPS to readiness again. |
| Source selection | CPU_COMM `eaf13de5`, argument 3 | Trace proves the source worker completed the transition; the script restores the panel's 720p timing and passes its handoff to Linux. This does not prove source detection. |
| Linux, 11.620276 s | Receiver EDID resource driver | Enables the 24 MHz EDID clock and releases reset. It explicitly reports `was_asserted=1`. |
| Linux, 14.856091 s | DDC pin helper | Changes PL10–PL15 from `ffffff` (I/O disabled) to `222222` (DDC pin functions). |
| Linux, 14.876294 s | SCP signal owner's original-state snapshot | HPD force-low control `7`, DDC enable word `07000000`, sampled optional I/O controls zero. These are samples at owner entry, not measurements throughout boot. |
| Linux, 14.876588 s | Signal owner ready | EDID written/verified; active HPD control `0`, DDC `07000007`. Register state is not a physical HPD waveform. |

The Linux times above are the saved journal's monotonic timestamps. They are
not timestamps of electrical transitions at the connector.

## What the earlier code does, and does not, control

The U-Boot ARM logo-table walker allows CCU/PIO/MIPS-control and display/capture
addresses below `0x07000000`; it does not allow the `0x0709xxxx` HPD/EDID
aperture. The reviewed `h713_mips.c` has no direct HPD/EDID register setup or
DDC pin claim. This does not exclude accesses by the running vendor MIPS code.

Board-B firmware disassembly identifies `HdmiRx_SendHPDCMD` at `0x8b13d5d4`.
It combines port/command arguments and calls `0x8b13b518`, which forms an
`a5`-prefixed packet and sends it via `0x8b12199c`. That routine accesses the
mailbox registers. This is a mailbox request path, not a direct write to
`0x07091014`. Static code presence does not establish when a particular request
was sent during either captured startup run. No mailbox command was injected
in this review.

The stock SCP message dispatcher is not part of our signal payload. Our owner
also refuses startup if the SCP reset-release bit is already set, then stages
and starts its own fixed program. That bounds SCP state at owner entry; it
does not prove its state at every earlier boot stage. Running the stock SCP
alongside this owner would conflict with ownership and is not the next test.

## Stock startup comparison: useful, with a board identity limit

The available board-A stock SCP image is pinned as
`93adf8a90fb190fc567fafcccbc5959e6514aa8cff6d4a6ed15981f08666dfa1`.
Its focused instruction review around file offset `0x12100` shows:

1. Write zero to EDID reset `0x07010120`, call a delay helper with argument 5,
   then write `00010000` to release reset.
2. Write `80000000` to EDID clock `0x07010124`.
3. Preserve the low byte of the PL8–PL15 mux register and set the upper six
   fields to `222222`, enabling the three DDC pairs.
4. Configure receiver DDC registers and call stock policy helpers.

Do not label the delay argument as milliseconds without verifying its helper.
Do not transplant this whole routine: it is board-A firmware, includes more
policy than a clock/pin setup, and was not shown identical to board B.
Historical peer notes contain receiver-map claims superseded by our later
hardware work; those claims were not adopted here.

The actionable difference is ordering: stock groups EDID reset/clock/pin setup
in its SCP initialization. Our path enables the EDID block in Linux, then
claims DDC pins about 3.24 seconds later and installs our EDID/HPD program.
That difference is a hypothesis to test, not evidence that it causes the fault.
The failed 100 ms settle and 2 s initial DDC hold experiments occurred later,
inside the signal owner's sequence; they did not instrument this earlier gap.

## Next capture prepared

[`prepare-early-hdmi-observe.py`](../tools/hdmi/prepare-early-hdmi-observe.py)
generates an offline variant of the exact installed script. Seven tagged
checkpoints sample only:

- `0x07010120`: EDID reset.
- `0x07010124`: EDID clock.
- `0x07022004`: PL8–PL15 mux, including the DDC pins.

Checkpoints are at script entry, before/after the logo run, after the relaunch,
before/after source selection, and immediately before Linux. The generator
verifies that removing its observations restores the exact original bytes.
The legacy script header CRC, payload CRC and length checks pass.

The candidate is **not installed or hardware qualified**. No bootloader binary
change is required for these observations. Serial printing adds boot time, so
one successful observed boot would not by itself qualify a timing fix.

If all checkpoints remain at reset/disabled state, the next controlled candidate
should investigate resource initialization and pin-connection ordering around
the first advertisement, using the owned resource drivers. If a stage changes
them, instrument that specific stage before changing initialization. These
snapshots cannot establish an HPD voltage or exclude activity within a stage;
further SCP instrumentation would need a separately reviewed ownership design.
