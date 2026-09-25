# HDMI capture workstream

**Current milestone (2026-09-25):** A [bounded live preview](hdmi-evidence/2026-09-25-panel-preview/README.md)
showed the moving HDMI test pattern on the projector panel. The V4L2 bridge
captured 640×480 NV16, and userspace converted it to a centered 960×720 image
on the 1280×720 primary DRM plane. Two runs restored the console scanout and
HDMI HPD state. A subsequent [throughput comparison](hdmi-evidence/2026-09-25-preview-rate/README.md)
implicated scaling directly from mapped DMA-contiguous V4L2 buffers in the
original 10–11 frames/s preview. Reading complete frames into ordinary userspace
memory before conversion raised panel-feed throughput to about 16 frames/s
with full verification, or about 31 frames/s with experimental sparse checks
feeding a 20 frames/s player. A 120-frame moving-pattern capture through
buffered `read()` had no band-ID or stripe-position mismatches. Optical quality
of the faster panel run, latency, and reliable ring
handoff remain open. The projector writes 640×480 NV16 HDMI
input into a three-pair Y/UV ring in ARM-readable reserved DRAM. The plane
bases and full-frame geometry are [verified against the source
screenshot](hdmi-evidence/2026-09-25-corrected-frame/README.md). The
[removable V4L2 bridge](hdmi-evidence/2026-09-25-v4l2-capture/README.md)
now exposes `/dev/video1` and streams verified frames through FFmpeg or
`v4l2-ctl`. `python3 tools/hdmi/capture-v4l2.py` automates one bounded
HDMI1 window and saves the stream. Full-plane comparison is the default;
the opt-in [sparse-verified mode](hdmi-evidence/2026-09-25-v4l2-rate/README.md)
reached about 60 frames/s in one 100-frame trial. A
[moving-pattern test](hdmi-evidence/2026-09-25-motion-irq/README.md) then
checked 120 sparse frames and 60 full-comparison frames without a mixed ID
at three heights or a misplaced motion stripe. Firmware-side `cap-vde` and
`cap-vs` events are now traced through the `VIncap` MIPS IRQ decoder and
generic event dispatcher, but that path exposes no completed ring-pair index.
Their timing has not been correlated with ring ownership. Hardware
frame-completion signaling remains open.

**Earlier receiver timing milestone (2026-09-24):** With HDMI1 selected by the MIPS
source worker, the merged default kernel, and a live GPU output, a guarded
read-only MIPS DRAM probe observed port 1 advance to state 5 and record
640x480 active timing. Both dimensions cleared after disconnect. The
firmware populates these fields from its own HDMI wrapper byte reads. HPD,
EDID, and firmware timing detection are now demonstrated; an ARM-accessible
captured frame and a capture V4L2 node are still outstanding. See the
[`2026-09-24 signal evidence`](hdmi-evidence/2026-09-24-hdmi1-signal/README.md).
The next hardware milestone is to identify the producer that writes HDMI
pixels into ARM-visible memory, its DMA registers and buffer ownership, then
read one bounded frame before registering a capture device. The local Linux
source includes a Synopsys HDMI-RX V4L2 driver for RK3588, but its board
binding, PHY, clock, and DMA programming cannot be assumed to match H713.
An [offline capture-memory lead](hdmi-capture-memory-path.md) distinguishes
the firmware's `0x0694xxxx` capture-window controls from the still-unidentified
pixel-buffer destination and notes the `0x068cxxxx` memory-agent control path.

**Register-map correction (2026-09-24):** The historical sections below call
`0x050c0000` “THDMIRX” and interpret writes there as receiver enable. The
board-B MIPS firmware identifies that window as display DETN noise reduction;
`0x05000000` is display composition and `0x05040000` is a picture-quality
tap. Consequently the old `0x050c0000` readbacks do not report HDMI-RX
status, and the experimental initializer is disabled. The firmware uses
byte-wide MIPS helpers at `0x06800800`/`0x06840000`; safe ARM bus access and
the receiver core/PHY map remain to be established. See
[`2026-09-24-hdmi1-signal`](hdmi-evidence/2026-09-24-hdmi1-signal/README.md)
and the [correction and next trace](hdmi-register-map-pointer-trace.md).

Started 2026-09-17 on `codex/hdmi-capture`, based on video branch commit
`a3ce352`, in `/home/chris/Projects/h713-hdmi-capture`.

## Isolation

Claude's checkout is `/home/chris/Projects/h713`, on
`h713-display-video-path`. Keep its files, build outputs, submodule checkouts,
and target hardware sessions untouched. This worktree has its own default
`build/` directory. Do not symlink writable source trees or build directories
from Claude's checkout. Submodules have not been initialized here yet.
The Git object store and refs are shared, as with any Git worktree.

The current video branch is the useful base: `main` lacks `docs/hdmi-in.md`
and receiver experiments 0087–0090. HDMI changes should be separate commits
so they can later be moved to main or integrated with the video branch.

## Established baseline and uncertainty

Read `hdmi-in.md` together with `arisc-route-scope.md`: both contain earlier
recommendations superseded by later results in those same files.

- Source detection passed on 2026-09-18: the GPU read the exact valid 128-byte
  test EDID and enabled 640x480 output during a reversible trial. See
  [the validation record](hdmi-source-detection-validation.md). Receiver lock
  and captured frames remain unproven.
- TVFE/TVCAP power must be established before receiver MMIO. Experiment 0087
  demonstrated access to receiver windows without claiming AFBD or GPIOs.
- ARM reads of `0x07091014` hard-locked the board. The clock/reset hypotheses
  were tested and did not solve access. Do not repeat that read.
- The scope document reports SRAM A2 contains our boot0/SPL rather than SCP
  firmware. That scan does not by itself rule out firmware in other memory.
- Stock's OR1K firmware contains an HPD writer. Starting the owning processor
  is a plausible explanation for the peer stack's successful ARM access;
  exclusive ARISC addressability is not demonstrated.
- The H713 TF-A platform explicitly disables SCPI PSCI. A missing SCPI boot
  message is therefore not evidence about whether firmware is resident, and
  loading firmware does not automatically enable compiled-out SCPI support.
- Working HDMI display output and ARM-accessible captured frames are separate
  milestones. Capture needs a proven producer, format, buffer ownership, and
  synchronization before exposing a V4L2 capture interface.

## Next offline investigation

Resolve the stock SCP memory layout and release-from-reset sequence before
adding a loader or transport. Local inputs can be read from Claude's checkout
without changing them:

- `local/allwinner-h713-linux/docs/re/arisc-firmware.md`
- `local/allwinner-h713-linux/docs/re/edid-protocol.md`
- `local/h713-lab/analysis/board-a-stock-20260622/boot-map/`

The board-A boot-map contains two extracted `scp.bin` copies reported identical
by `toc1-item-copy-compare.txt`. Its TOC1 lists SCP offset `0xacc00`, length
`0x2b004`; the peer document's `0xb0c00` belongs to a different image. Parse
metadata from the actual input rather than applying that offset blindly.
Establish whether TOC1 addresses represent ARM load addresses, coprocessor
addresses, or a staging area; firmware size exceeds the documented 128 KiB
SRAM A2 size. Do not infer the loader from file size alone.

The peer describes mailbox User1 sub-block 0 port 3, with FIFO status
`0x0300346c`, data `0x0300347c`, and doorbell `0x03003430`. This is a lead for
reusing the existing mailbox layout, not proof the MIPS transport can be used
unchanged. The documented generic TV command and direct dispatcher test frames
also differ; verify the actual HPD dispatch path before transmitting packets.

## Hardware milestones, when the board is available

1. Source detects the sink and reads a valid, checksummed EDID. Measure on the
   source; EDID write-port readback alone is insufficient.
2. Receiver locks to a known unencrypted test signal and reports its timings.
3. Obtain ARM-accessible frames with documented dimensions, pixel format,
   stride, DMA/IOMMU mapping, and producer synchronization.
4. Expose captured buffers through V4L2 and verify a saved frame against the
   source test pattern, then continuous capture and restart behavior.

Hardware tests, firmware startup, shared clock changes, and flashing must wait
for a hardware window that does not overlap Claude's video-driver tests.

## First session update

The owner confirmed the GPU-to-projector HDMI cable is connected and explicitly
authorized taking serial ownership. The serial port was free, so no process
needed closing. Read-only live checks and offline stock-monitor disassembly
are recorded in [hdmi-scp-loader-re.md](hdmi-scp-loader-re.md).

The stock loader's split SRAM/DRAM copies and core-reset register have now been
identified. Startup parameters, caller behavior, memory reservation, and
firmware compatibility remain to be checked before a loader experiment.

## TVFE/TVCAP bring-up, 2026-09-17

The owner requested domain bring-up. A removable out-of-tree module now powers
both domains through existing kernel APIs, without flashing or rebooting.
Load/unload/reload were validated: domains switched on/off/on, and temporary
devices were removed on unload. The first eight known THDMIRX register reads
completed with the same values as experiment 0087.

The module is currently loaded, holding TVFE/TVCAP and four clock references.
Source-side HDMI remains disconnected with no EDID; HPD/DDC are the next
milestone. Details, build commands, rollback, and exact validation limits are
in [the module README](../modules/hdmi-bringup/README.md).

## Follow-up access failure

Although THDMIRX remained readable, the wrapper byte read at `0x068008f1`
returned a bus error and the following `0x068008fc` access likely hard-locked
the target. The owner recovered it with a physical power cycle. The failed state is
not used as a live baseline. See
[the failure record](hdmi-wrapper-access-failure.md) for exact observations,
the clock-definition discrepancy, and the restricted next experiment.

## Recovery and clock correction

The owner power-cycled the target. Vendor symbolized CCU descriptors resolved
bus-hdmi-audio to bit 31 and bus-cap-300m to bit 30 at register 0xd80.
Patch 0125 corrects both definitions. A private build and one-time FIT boot
passed, followed by power-module load/unload/reload and eight known THDMIRX
reads. See [the validation record](hdmi-tvcap-clock-validation.md).

The current target is on the transient #2 kernel with TVFE/TVCAP held active.
Normal boot storage and Claude's checkout are unchanged. The wrapper fault
remains unresolved, and HPD/DDC are still the next source-facing milestone.

## Bounded SCP test

A backed-up SRAM A2 program produced the expected marker and returned to
reset with restoration verified. A separately approved SCP-side HPD read
did not complete; subsequent marker tests failed despite ARM remaining
responsive. See [the probe record](hdmi-scp-probe-validation.md). No HPD
write, full firmware load, or source detection success is claimed.

Controlled ARM restart and the same temporary FIT recovered the SCP execution
test. The latest module passed with exception reporting enabled; TVFE/TVCAP
are held active again. The normal boot image remains untouched.

## EDID clock/reset and HPD-read milestone

Patch 0126 adds the missing EDID resources to an H713-specific R_CCU variant.
A one-time #3 kernel boot passed. The removable consumer held the clock at
24 MHz and released reset; the SCP-side HPD read then passed twice and
returned 7. Consumer unload restored the original zero register values.
See [the EDID clock validation](hdmi-edid-clock-validation.md). Current target
holds TVFE/TVCAP and EDID resources; SCP is stopped. Source detection/EDID
and captured frames remain unproven.

## Source detection milestone, 2026-09-18

Cold recovery, restaging, and the one-time #3 boot passed. A reversible SCP
EDID/HPD trial produced connected status, an exact valid EDID, and enabled
640x480 source output. Restoration returned the connector to disconnected.
Both trials after the payload guard passed; the second needed no optional
stock HPD control writes. See [the evidence](hdmi-source-detection-validation.md).
Next milestone: identify the actual receiver/PHY initialization and read
verified lock/timing status. The wrapper ARM access fault remains unresolved.

## Receiver clocks and IPC follow-up

A full U-Boot live-MIPS init and handshaken #3 boot succeeded, but the shell
ring was not consumed and read-only GetSource RPC timed out. No Vp_Init or
HDMI source-selection call was sent; ARM stayed responsive and was restarted.
See [IPC results](hdmi-mips-ipc-validation.md).

Vendor descriptors exposed missing receiver dividers/muxes and the wrong
MIPS parent order. Patch 0127 corrects five functional clock descriptions.
A one-time #4 boot and another exact source-EDID detection trial passed,
without shared PLL/rate writes. See [clock validation](hdmi-functional-clock-validation.md).

Current target: temporary #4, MIPS/SCP stopped, DDC pins unclaimed/input,
HPD/DDC restored, only TVFE/TVCAP and EDID holds loaded. Normal boot image
and persistent U-Boot settings remain unchanged. Receiver lock and frames
are still unproven; establish functional receiver control before selecting HDMI.

## MIPS resource isolation, 2026-09-18

On #4 with AFBD blacklisted, MIPS shell responds before/after CPU_COMM adoption,
and a read-only RPC completes in ~75ms. TVFE-only attachment preserves both.
Adding TVCAP stops shell consumption, even with no receiver clocks enabled;
enabling clocks first also fails. See [the resource isolation](hdmi-mips-resource-isolation.md).
The earlier IPC timeout followed a full receiver power hold, so it did not
locate the failure at Linux boot or CPU_COMM. No source selection was sent.

Current restored state: #4 with live MIPS, TVFE-only hold and CPU_COMM loaded,
TVCAP off, SCP stopped, EDID/DDC modules absent. Full shell/RPC restoration
passed. No persistent boot/firmware changes; Claude's checkout remains clean.
Next: obtain a firmware execution/exception witness around TVCAP power-on.

## TVCAP retention and live source boundary, 2026-09-22

A guarded timer/exception witness showed that TVCAP off-to-on freezes ThreadX
without an exception and that TVCAP power-off resumes it. Private #5 retained
TVCAP continuously from U-Boot. The MIPS timer, shell, and CPU_COMM stayed
healthy with TVCAP active and after adding TVFE plus four receiver clocks.

Source detection again produced the exact EDID and enabled 640x480. `Vp_Init`,
three stock HDMI port maps, and the HPD interval completed under the witness.
A live `SetSource(3)` did not return and was followed by loss of SSH, ping, and
serial. See [the retained-TVCAP record](hdmi-mips-early-tvcap.md). Do not repeat
live SetSource using only the minimal init sequence.

## Callback delivery and full SetSource boundary, 2026-09-22

Patch 0129 supplies CPU_COMM callback `read`/`poll` queues and the missing
MIPS-to-ARM dispatch channel. The full stock-equivalent pre-source daemon
sequence completed under the witness, and the kernel delivered a hot-plug
callback into the daemon's queue. A live callback-aware `SetSource(3)` still
blocked before returning or emitting `SignalChange`, then the board lost SSH,
ping, and serial. The independently bounded SCP EDID trial restored cleanly.
See [the updated retained-TVCAP record](hdmi-mips-early-tvcap.md).

The next isolated test is the successful peer driver's Synopsys controller
sequence, now packaged in `tools/hdmi/h713-thdmirx-init.c`. It touches only
`0x050c0000`; wrapper and CPUS HPD access stay with MIPS/SCP. The board needs a
physical power cycle before that module can be tested.

## THDMIRX controller gate, 2026-09-22

After the power cycle, the opt-in controller module applied the peer sequence
and changed `GLOBAL_SWENABLE` from zero to `0x00203901`. Its timer, CMU, PHY,
deframer, and CED settings latched. The MIPS witness and shell remained healthy,
and the complete callback-capable initialization passed without source
selection. This establishes the THDMIRX sequence as stable under the retained
TVCAP setup.

The first follow-up source trial was mistimed, so the harness was changed to
start the daemon as soon as the GPU output became enabled. The synchronized
trial then started the daemon 2.606 seconds after HPD assertion, with roughly
27 seconds left. The exact EDID was present, the GPU was enabled at 640x480,
all pre-source calls returned, and the hot-plug callback reached userspace.
`SetSource(3)` still produced no RETURN; CPU_COMM timed out session `0x16`,
then SSH, ping, and serial all stopped.

The next run uses the U-Boot firmware source-worker trace already present in
the flashed diagnostic build. Its markers distinguish callback queueing,
worker dequeue, unchanged-source handling, and completion of the general
source transition. `tools/mips/read-comm-trace.py` performs guarded, read-only
sampling of that mailbox. See [the synchronized evidence](hdmi-evidence/2026-09-22-synchronized-setsource/README.md).

## Merged newer-kernel baseline, 2026-09-24

The isolated HDMI branch now includes the newer video-decode branch through
`ad3ffac`. The merged FIT and rebuilt HDMI modules passed a one-time normal
boot with Cedrus, AFBD, TVCAP retention, SSH, and HDMI power/EDID module
load-unload checks. Future HDMI trials can use that single kernel codebase;
see [the merged-kernel validation](hdmi-evidence/2026-09-24-merged-kernel/README.md).
The owner approved installing that validated FIT as the default, and the
normal boot plus on-disk checksum check passed. The prior FIT is backed up
on the board's root filesystem.
