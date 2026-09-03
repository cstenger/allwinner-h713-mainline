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

---

# The three cheap checks — done 2026-09-02

## 1. Is the ARISC running? — UNANSWERED, and the check was invalid

A boot capture shows TF-A's banner and no "Suspend is available via SCPI" line,
which looks like "no SCP firmware detected". It proves nothing, because our own
platform file disables the code that would print it:

```make
# plat/allwinner/sun50i_h713/platform.mk
# Without a management processor there is no SCPI support.
SUNXI_PSCI_USE_SCPI   := 0
SUNXI_PSCI_USE_NATIVE := 1
ifeq (${SUNXI_PSCI_USE_SCPI}, 1)
    $(error "H713 does not support SCPI PSCI ops")
```

The detection is compiled out, so the message could never have appeared. Same
class of error as reading `clk_summary`'s refcount as a hardware gate: **check
that the instrument can show a positive before treating its silence as one.**

Worth flagging separately: that comment — "Without a management processor" —
is **wrong, or at least badly worded**. The H713 does have a management
processor; the peer disassembled its 172 KB firmware and located the routine
that writes the HPD register. Whoever ported this platform concluded otherwise,
and that belief is now baked into our boot chain. It should be corrected
regardless of whether the ARISC route is pursued.

### Redone by a valid method — NO ARISC FIRMWARE IS LOADED

Read SRAM A2 directly (`0x00104000`, size `0x20000` for H713 per our own
`sunxi_mmap.h`) and searched all 32768 words for the OR1K magic `0xb4400012`,
in both byte orders since the blob is stored word-reversed:

```text
magic b4400012 / 120040b4    NOT PRESENT anywhere in SRAM A2
non-zero                      31188 of 32768 words -- the SRAM is full
0x00104000 = 0xEA000016       an ARM branch, not OR1K
0x00104004 = 0x4E4F4765       "eGON"
0x00104008 = 0x3054422E       ".BT0"
```

**SRAM A2 holds `eGON.BT0` — our own boot0/SPL — and no SCP firmware.** The
ARISC is not running, which is what the invalid check guessed but could not
show. Note the read itself was the risk here, since SRAM A2 sits in the same
CPUS neighbourhood that hard-locked the board twice; it returned cleanly and the
board stayed up.

**One uncertainty, kept honest:** `SUNXI_SRAM_A2_SIZE = 0x20000` (128 KB) comes
from our own TF-A port and may have been inherited from H616 rather than
verified on H713. The vendor blob is 172 KB and does not fit in 128 KB, so
either that constant is wrong or the vendor loads the firmware somewhere else
entirely. Either way this bears directly on item 2 — **whoever takes that on
should start by establishing the real size and location of SRAM A2**, because
the "load address" question may partly be a "which memory" question.

## 2. Msgbox transport — MUCH cheaper than scoped

The ARISC listens on **User1 sub-block 0, port 3**, FIFO_STAT at `0x0300346c`.
Our `cpu_comm` driver already drives that exact hardware for the MIPS, and its
own documented layout predicts that address precisely:

```text
cpu_comm_hw.c:   +0x60 FIFO count + 4*port ,  +0x70 MSG data + 4*port
                 +0x20/24 RX IRQ en/status ,  +0x30/34 TX IRQ en/status
                 MIPS is port 1
sub-block base 0x03003400 + (0x60 + 4*3) = 0x0300346c   <- exactly the ARISC
```

Same block, same register layout, same driver — only a different sub-block base
and port number. **Item 4 drops from "write a msgbox driver" to "add a port to a
working, hardware-validated one".** Revise it from *medium* to *low*.

## 3. Re-read the HPD conclusion — it stands, and now has a mechanism

The conclusion was that `0x07091014` is unreachable from the ARM with power,
clock and reset all confirmed enabled. Nothing found here contradicts it, and
check 1 supplies the missing *why*: the peer's driver reaches that register from
ARM on a stack whose boot chain loads and starts the ARISC, while ours never
does. A block that answers only when its owning coprocessor is running fits
every observation — the hard-locks, the absence from both device trees, and
stock driving it from firmware.

That is a hypothesis rather than a proof, but it is the first one that explains
the peer's success and our hang with the same mechanism.

# Revised scope

| # | Piece | Was | Now |
| --- | --- | --- | --- |
| 1 | Extract the blob | low | low |
| 2 | Load address + reset release | **high** | **high — still the deciding unknown** |
| 3 | Load from SPL/U-Boot | medium | medium |
| 4 | Msgbox transport | medium | **low** — extend `cpu_comm` |
| 5 | BOP frame layer | low-med | low-med |
| 6 | `PullHotPlug 0x0211` | trivial | trivial |

Item 2 still dominates. But the transport half is now nearly free, and there is
a concrete cheap experiment outstanding: **read the SCP magic at the load
address to settle whether anything is running**, which check 1 failed to do.
