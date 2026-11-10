# The known-good scanout recipe is inert with the MIPS alive

2026-09-04, operator watching, board healthy throughout.

## The test

The exact pair that produced confirmed visible scanout on 2026-08-31 with the
MIPS **parked**:

```
0x05600010 = 0x03000013     source 0 enable, committed via 0x05600014
0x051c006c = 0x39000000     plane selector -> video
```

Run with the core **alive**, the source selected over CPU_COMM
(`hal_source_id: 1`, `AppTopSetSource`, `SetSignalInfo` all logged) and a frame
in the ring (Y/C/VideoInfo populated). Pulsed four times, ~8 s on / 3 s off, so
a mistimed glance could not miss it.

```
cycle 1..4 ON   src0=0x03000013  sel=0x39000000  core=0x00000001
restored        src0=0x03000010  sel=0x29000000  core=0x00000001
```

Every write took, the commit latch was consumed each cycle, the core stayed
alive, everything restored.

## Result: NEGATIVE. Steady black, all four pulses.

**Operator: nothing changed.**

This is not a "the write did not stick" null — the hardware accepted the
configuration every time and the latch was consumed. The registers that
demonstrably drive the panel with the core parked drive nothing with the core
alive.

## What it establishes

**The window layer holds the output stage.** Our AFBD/selector writes are
accepted by the hardware and not honoured on the panel while the MIPS is
running. That is the mirror of the 2026-09-04 finding from the RGB side — *MIPS
parked: ARM owns presentation; MIPS alive: the MIPS owns it* — now measured from
the **video-source** side as well, which is where the last hope of a
register-level shortcut lived.

So there is no route to the panel that goes around the WCE. With a live core the
only way a frame reaches the glass is for the window layer to decide to composite
it.

## And the WCE has not decided to

Everything needed for that decision is still missing, and the log says so
directly. `SetSource(1)` produced exactly one `SetSignalInfo` and then nothing:
no `UpdateWce`, no `CalcWindow`, no `PanelWinNode::WriteReg`. The window nodes
still hold their bring-up geometry and `PanelWinNode.cpp:328` still logs
`bypass`.

A selected source with no signal behind it does not make the WCE recompute. What
constitutes "signal" for source 1 (VideoDecoder) is the open question — the
VideoInfo descriptor carries width, height, stride and frame rate, but nothing
observed shows the firmware consuming it, and `THal_Vp_GetSignalInfo` is a known
stub.

## The remaining lead is the part we skipped

The peer's stock trace is a **12-call boot sequence** and a **12-call source
switch**, and we ran one call of each. The gate they identify is `Vp_Init`, which
we deliberately did not fire because our live routine table declares ParaCount 1
while stock sends 3 with `Para[2]` a staging address, and `Para[2] == 0` is the
call that corrupts memory.

Settling that parameter convention — from `cpu-comm-probe.c` and the peer's
`libhy310cpucomm`, off-hardware — is the next step. Poking AFBD is now closed:
this test was its last form.
