# HDMI receiver to memory: static lead after live timing detection

**Later result (2026-09-25):** Read-only DRAM sampling found complete 640×480
NV16 frames in a [three-pair ring](hdmi-evidence/2026-09-25-coherent-ring/README.md).
The static investigation below remains a record of the earlier search for the
producer's register controls and hardware completion signal.

The 2026-09-24 signal trial proved that the board-B MIPS receiver records a
live 640x480 HDMI1 timing. It has not located an ARM-visible pixel buffer.
This note records the next static lead without making any hardware accesses.
The image is `local/mips-display/board-b-mips/display.bin` in the main
checkout, SHA256
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
Virtual addresses below use its verified `0x8b100000` load base.

`tools/mips/block-map.py` previously scanned only the MIPS `0xbaxxxxxx`
aperture, excluding the capture `0xbbxxxxxx` aperture. With both apertures
included, it finds direct accesses to 21 candidate register offsets in
physical `0x06940000..0x0694ffff`. The important `CapWinNode::WriteReg`
sequence at `0x8b1a07fc..0x8b1a08ec` writes `0x06940858..0x0694087c`:
it inserts capture scaling ratios and geometry derived from the node's
configuration. These are capture-side *window controls*, not identified DRAM
buffer addresses. The prior [scaler census](reference/scaler-census-2026-09-11.md)
independently identified this node and found no 32-bit framebuffer-base store
in this block.

The firmware's `memory_agent_onoff` logging string is at `0x8b1fb7c8`.
The routine at `0x8b153d7c` uses its mask argument to toggle several block
gates. Its mask bit `0x8` controls bit 31 of `0x06940928` and `0x06940968`
(`0x8b153e14..0x8b153e2c`). The adjacent helpers at `0x8b153cdc` and
`0x8b153d2c` pass physical `0x068c00b8/c4/d0` and `0x068c00dc/e8/f4` to
the firmware's masked-write helper. These show control relationships, but
none identifies a frame destination or buffer ownership. Other physical
`0x068cxxxx` constants occur throughout the HDMI code and require separate
decoding.

The register scanner is a linear candidate finder. For example, it prints a
write to `0x06941068` at `0x8b1a08fc`, but the preceding branch can reach
that instruction with `0xbb940000` in `$v0`; the linear scan carries the
`0xbb940800` value from an earlier, different branch instead. The actual
write is to `0x06940868`. The scanner also misses MMIO accesses
through helper calls such as `0x8b180638`. Confirm every candidate from its
actual control flow and accessor before using it in a driver.

Next, trace the capture producer's DMA or memory-agent descriptor setup from
the MIPS call graph, including any physical addresses passed to masked-write
helpers. Identify an actual destination address, stride, format, and frame
completion signal before reading a buffer or registering V4L2 capture.

## Static producer-index follow-up, 2026-09-26

Constant propagation across calls to the firmware's physical-write helpers
(`0x8b1805f0` and `0x8b180638`) resolves 274 call sites. The additional
capture-domain results are routing/control fields at `0x06940858` and
`0x0694085c`; the `0x068cxxxx` results are memory-agent gate, reset, and delay
controls. None carries a ring address or producer index. This also confirms
that the earlier linear-scan candidate `0x06941068` is the real
`0x06940868` access reached with a different base. The direct and helper-call
MMIO census therefore has not found a capture-engine producer register.

There is, however, a stronger read-only cross-block lead. Retained AFBD dumps
show `0x05600320/0x05600324` holding an exact Y/UV pair from the capture ring:

```text
Y:  0x4c3ef000  0x4c5ee000  0x4c7ed000
UV: 0x4c9ec000  0x4cbeb000  0x4cdea000
```

The two rows have the same `0x1ff000` step. Historical dumps observed pair 1
and pair 2, and the selected pair moved when the firmware's allocation order
changed. The window is AFBD/display-fetch state, not capture-engine MMIO:
stock `decd.ko` supplies four source-0 address slots at AFBD `+0x70..+0x90`,
while `+0x320/+0x324` is populated without a direct firmware store and is
consistent with downstream/current-address state. That distinction matters:
the pair may be a safe completed consumer buffer, a lagged display buffer, or
a stale value. Static evidence alone does not establish which.

The V4L2 bridge now contains telemetry-only sampling for this hypothesis. On
each single `cap-vde` increment it brackets the UV read with two Y reads,
accepts only one of the three exact ring pairs, and increments one of three
`(pair - cap_vde) mod 3` counters exposed as module parameters
`afbd_phase0`, `afbd_phase1`, and `afbd_phase2`. It also exposes sample,
invalid, and last-address values. **These reads do not select a capture
buffer.** A bounded hardware run must first show one dominant phase bin across
static and moving input, with valid pair rotation and no integrity regression.
An even histogram means the register is fixed/stale; a split phase means its
update is asynchronous and it is not a safe permanent completion ABI.
