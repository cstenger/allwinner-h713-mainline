# HDMI capture workstream

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

- The source-side detection milestone has not passed: disconnected connector,
  zero-length EDID. Streaming bytes into an EDID-named register did not prove
  that DDC serves an EDID.
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
