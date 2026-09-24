# HDMI receiver to memory: static lead after live timing detection

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
