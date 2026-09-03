# Scoping the ARISC route to HPD

Written 2026-09-02, after every ARM-side explanation for `0x07091014` was
eliminated (see [hdmi-in.md](hdmi-in.md)). HPD is the sole blocker on HDMI
input, and the ARISC is the only remaining way to reach it. This is a scope, not
a plan of record — the point is to size it honestly before anyone starts.

## What the ARISC is

A third CPU beside the ARM and the MIPS: an **OR1K big-endian SCP**, firmware
**172 KB**, which owns power management, the HPD pin, and the HDMI-RX handoff.

```text
ISA           OpenRISC 1000, big-endian, entry at 0x100
Source        bootloader_a.bin, TOC1 item "scp", offset 0xb0c00
              (word-byte-reversed in storage)
Loaded by     BL31 / U-Boot, BEFORE Linux
0x121e4       HPD pin writer -- writes 0x07091014, the register we cannot reach
0x12490       SCPI/HDMI dispatcher, 9 cases
```

## The load problem is the real work

**Our boot chain does not load it, and mainline TF-A cannot.**

TF-A has SCP support, but for a different thing. It expects SCP firmware in
**the last 16 KiB of SRAM A2** (`SUNXI_SCP_BASE = BL31_LIMIT`), *detects*
whether something was already loaded there by checking the first instruction,
and uses SCPI PSCI if so — falling back to native PSCI otherwise. It never
loads the blob itself; on stock, boot0 does.

Two consequences:

1. **16 KiB vs 172 KB.** The vendor blob is more than ten times TF-A's SCP
   slot, so it does not live there and this is not a matter of dropping a file
   into an existing mechanism. The vendor arrangement is different and its load
   address is not yet known.
2. **We would be adding a proprietary blob to the boot path.** The project
   already ships firmware blobs where unavoidable (aic8800), so that is not
   new in principle — but the boot path is where a mistake costs a FEL
   recovery rather than a reboot.

## Components, in dependency order

| # | Piece | Effort | Notes |
| --- | --- | --- | --- |
| 1 | Extract the blob | **low** | Location and byte-swap are documented |
| 2 | Find its load address + release-from-reset sequence | **high** | Not documented; needs boot0 RE or a stock boot trace |
| 3 | Load it from our SPL/U-Boot | **medium** | Boot-path change, brick risk, FEL recovery |
| 4 | Msgbox transport | **medium** | H713 layout is incompatible with mainline `sun6i-a31-msgbox`; our `cpu_comm` already drives the msgbox at `0x03003000` for the MIPS, so check whether the ARISC uses the same block on another port before writing anything new |
| 5 | BOP frame layer | **low-medium** | Well documented: marker `0xA5`, rotating seq, type, length, then `sub_cmd_lo/hi, arg1, arg2, data` |
| 6 | Send `PullHotPlug 0x0211` | **trivial** | Once 1-5 work |

Item 2 is the one that decides whether this is weeks or days, and it is the one
nobody has data for yet.

## The hazard nobody should discover the hard way

**The ARISC owns power management.** TF-A currently uses its *native* PSCI
implementation precisely because no SCP is present. Loading vendor ARISC
firmware puts a second power manager on the system, and TF-A would then detect
SCPI and switch to it. That is a change to how the whole board suspends,
resumes and hotplugs CPUs, on a board with no watchdog.

Do not treat this as "load a blob and gain a register". It is a boot
architecture change whose blast radius includes PSCI.

## Cheaper things to do first

Before any of the above:

1. **Check whether the ARISC is running at all right now.** If our boot chain
   happens to leave stock firmware resident, or if the core is halted, that
   changes the problem completely and costs one boot log to find out. TF-A
   prints whether SCPI is available.
2. **Confirm the msgbox situation.** If `cpu_comm` already reaches the same
   msgbox hardware the ARISC uses, item 4 shrinks from a driver to a port
   number.
3. **Re-read the HPD conclusion once**, since everything here rests on it.
   `0x07091014` is unreachable from the ARM with power, clock and reset all
   confirmed enabled — that is solid, but it is load-bearing for a large
   project and deserves one skeptical pass before the project starts.

## Honest recommendation

This is the only route to HDMI input, and HDMI input is a headline feature of
the board. But it is a multi-week effort with a boot-path change, a PSCI
architecture change, and one unknown (item 2) that could dominate everything
else.

It should not be started casually, and it should not be started at all until
items 1-3 above are done, because any of them could change the shape of it.

If the goal is visible progress rather than this specific feature, the video
plane work is finished and unblocked at the userspace level — an ffmpeg/mpv
with the `v4l2request` hwaccel would make decoded video playable through the
existing NV12 KMS plane, with no kernel work at all. That is a far better
effort-to-result ratio than starting here.
