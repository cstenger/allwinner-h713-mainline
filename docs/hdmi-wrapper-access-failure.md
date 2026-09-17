# Wrapper access is not safe with the current power hold

2026-09-17, following the successful TVFE/TVCAP load/unload/reload test.

The default module successfully powers both PPU domains, and the first eight
THDMIRX words at `0x050c0000` remain readable. That does **not** establish that
all HDMI-related register windows are accessible in this boot state.

## Live failure

A read-only SSH batch confirmed:

- Power-hold module loaded; TVFE/TVCAP `on`, with both hold devices `active`.
- Target model `HY200 QZ713DF_A1 (Allwinner H713)`.
- All eight THDMIRX reads returned the previous values.

The next command was `/root/mmio-rw rb 68008f1`. It terminated with `Bus error`
(Shell identified PID 6126). The shell batch did not use fail-fast behavior,
so it proceeded to `/root/mmio-rw rb 68008fc`. Nothing further was printed.
A subsequent newline on serial produced no prompt, and a fresh SSH connection
timed out. The target therefore appears hard-locked. The second read is the
likely lock site, but we do not have an instruction-level trace proving that.

The later planned reads at `0x05000040`, `0x05000044`, `0x05000064`, and
`0x050c0300` did not produce output. They have not been revalidated in this
session. No receiver writes were issued.

The owner was asked to physically power-cycle the projector. The temporary
module is not configured to autoload, so recovery will leave the domains off
unless something else owns them. Check state before any further accesses.

## Why the earlier notes are insufficient

`hdmi-in.md` reports the wrapper reachable on 2026-09-02 after experiment
0087. Today's code holds the same four clock references, but today's boot
state differs. A successful historical read is not a blanket guarantee.

There is a concrete initialization discrepancy to investigate offline:

| Register | Current driver/helper | Recovered stock fastlogo |
|---|---|---|
| `0x02001d80` | CCU models bus HDMI audio at bit 0 and cap-300m at bit 1 | Writes `0xc0000000` |
| `0x02001d6c` | Power hold does not acquire TCD3 | Writes `0x80000305` |
| `0x02001d84` | Power hold does not acquire HDMI audio | Writes `0x80000000` |
| `0x02001d88` | Power hold acquires bus clock, performs no reset operation | Writes `0x00010001` |

The current U-Boot helper also ORs low bits 0/1 at `0x02001d80`, whereas the
stock fastlogo transcription uses high bits 30/31. The cap-300m reference
count became 1/1 in the initial test while its hardware-enabled column stayed
`N`. These observations support investigating incomplete clock/reset setup;
they do not yet identify which bit maps to each clock or prove the lock's cause.

Relevant local sources:

- `build/kernel-runtime/drivers/clk/sunxi-ng/ccu-sun50i-h713.c`, definitions
  of `bus_hdmi_audio_clk`, `bus_cap_300m_clk`, `tcd3_clk`, and `hdmi_audio_clk`.
- `/home/chris/Projects/h713/external/u-boot/arch/arm/mach-sunxi/h713_mips.c`,
  `h713_tvcap_prepare()`.
- `mips-display-recovery.md`, sections "TVCAP: the ARM does enable it, with
  specific values" and "Stock fastlogo, transcribed".

Do not replay the entire stock initialization: its PLL_PERIPH0 write is
already documented to power off this bench board under our boot context.

## Next experiment

After recovery, collect only sysfs/debugfs and the known CCU register state.
Resolve the actual gate/reset definitions against stock code before accessing
`0x068xxxxx` again. Do not use a generic register sweep or a batch that continues
past a bus error. `tools/hdmi/check-power.sh` now defaults to sysfs/debugfs only;
its opt-in read list contains only the eight revalidated THDMIRX words and
stops on the first process failure.

The SCP startup path remains an independent offline investigation. Further
monitor disassembly shows both probe entry points write the caller's w0 to
`0x0709010c` before invoking the loader, then initialize the mailbox and wait
for readiness. The monitor's on-disk 128-byte startup parameter area includes
a build identifier followed by zeros, so it must not be blindly treated as a
fully initialized runtime configuration.
