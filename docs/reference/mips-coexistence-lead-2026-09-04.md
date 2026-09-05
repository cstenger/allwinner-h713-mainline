# Why our MIPS release locks the SoC — a strong lead from the peer tree

Written 2026-09-04 after four locks. **Not yet tested.** Sourced from the peer
H713 port in `local/allwinner-h713-linux/`, which is an RE port rather than
vendor source ([[local-tree-is-a-peer-re-port]]), so treat its claims as leads
to verify rather than established fact. But it explains our failure better than
anything we have generated ourselves.

## The peer project boots Linux with the MIPS alive, and it works

`docs/subsystems/mips.md` there:

> **Status**: working. Firmware loads, all 81 routines register, state machine
> reaches state 5 (Running) [...] **U-Boot loads** `display.bin` [...] and starts
> MIPS execution. **By the time Linux runs, MIPS is already alive.**

That is the configuration we have failed at four times, running on the same SoC.
It is a direct counterexample to any "these cannot coexist" reading, and it
means our lock is a defect with a fix, not a wall.

## The mechanism they name, which matches our symptom exactly

> **State 3 → 4** needs `Vp_Init` to be called with `Para[2] != 0`. Para[2] is
> used by MIPS as a phys-addr pointer for a 55 KB factory-PQ memcpy. With
> `Para[2] = 0` (mistake we made for many sessions), MIPS faults with a **NULL
> memcpy, BG_Thread breaks, kernel-MM corruption cascades into unrelated
> processes**.
>
> **Fix**: `Para[2] = SHMEM_PHYS_BASE + 4 MB = 0x4E700000`.

**A running MIPS that has not been initialised correctly by the ARM performs a
wild memcpy into DRAM.** That is precisely the shape of what we see: the SoC
dies with no oops, no panic and no serial, at whatever the kernel happens to be
doing, regardless of ordering or which drivers are bound.

## Why this fits our four failures better than the IOMMU idea

Our releases have all been *cold restarts of the firmware with no ARM-side
handshake afterwards*. The `mw.l` replay writes the boot address and the reset
stages and nothing else; nothing then performs the CPU_COMM readiness dance or
calls `Vp_Init`. The firmware comes up, its background thread advances, and
finds the pointer it needs is zero.

Note what U-Boot's own preboot does by contrast, from its boot log:

```
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
H713 MIPS: firmware readiness proven by MIPS READY
H713 MIPS: application readiness proven
H713 panel: MIPS core quiesced, display clocks retained
```

**U-Boot does the whole handshake — and then parks the core.** Every experiment
we have run re-released it *afterwards*, which restarts the firmware into a
fresh, un-handshaken state. We have never once had a live MIPS that was also
correctly initialised.

This also explains why the release is harmless at the U-Boot prompt but fatal
once Linux runs: at the prompt nothing else is using DRAM, so a wild write lands
somewhere idle and we see a working prompt. Under Linux it lands in the kernel.

## The experiment this suggests, and it needs no new code

`h713_disp logo-live <id>` already exists in `h713_mips.c` — the `auto <id> logo`
sequence **without** the quiesce ([status.md](../status.md)). It performs the
full bring-up, including the handshake and readiness proof, and leaves the core
running healthy rather than restarting it cold.

So the untried configuration is:

1. cold boot, interrupt autoboot
2. `h713_disp logo-live <id>` — bring the MIPS up *properly*, core left running
3. boot Linux

That is materially different from all four failures, which were cold re-releases
of an already-quiesced core. **Check first whether the flashed bootloader
actually has `logo-live`** — it was added to the working tree and the board may
predate it; `h713_disp` with no arguments prints its usage.

If it still locks, the next thing to try is an ARM-side `Vp_Init` with
`Para[2] = 0x4E700000` early in boot, which is what the peer project's
`hy310-hdmird` does and what our CPU_COMM client work
([cpu-comm-client-plan.md](../cpu-comm-client-plan.md)) was heading towards.

## Also worth capturing while on the vendor stack

- **Is the MIPS actually alive under Android?** One read of `0x0306101c`. The
  whole coexistence premise rests on this and we have inferred it, never
  measured it.
- The vendor kernel's boot log: probe order, and what `sunxi-mipsloader`
  (`CONFIG_SUNXI_MIPSLOADER=y`, built-in) does at probe. The peer notes say it
  "writes the SharedMem base address to the CCU share registers" — which is
  exactly the `publish_shmem` step our `mw.l` replay omits.
