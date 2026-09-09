# The signal state machine, confirmed live — enabled, ready, never polled

> Correction, 2026-09-08: the state-machine callback is registered under event 8
> through a secondary-vtable thunk. GetFrameInfo writes a caller-supplied buffer,
> so zero persistent buffers do not prove it never executed. ARM reads also
> require a MIPS cache-visibility qualification. See
> [the new dispatch trace](dispatch-trace-2026-09-08.md).

2026-09-05, read-only, core alive. Confirms
[viddec-signal-chain](viddec-signal-chain-2026-09-05.md) against live memory
rather than against absence of log records.

## The object graph is real and matches the RE

`THidTVPro`'s singleton pointer lives at a fixed global, MIPS `0x8b27266c` ->
ARM **`0x4b27266c`** (from the lazy getter at `0x8b147680`). Reading it:

```
THidTVPro ptr (MIPS)  = 0x8b83084c   -> ARM 0x4b83084c
  vptr        +0x000  = 0x8b1f8bdc   <- matches the recovered vtable exactly
  STM state   +0x5a0  = 0x00000001
  enable flag +0x5a4  = 0x00000001
  detector    +0x5a8  = 0x8b830ea8

CVidDecSignalDetector -> ARM 0x4b830ea8
  vptr        +0x000  = 0x8b1f8d80   <- matches the recovered vtable exactly
  frame-info buffer  +0x0b0 : all zero
  last-latched copy  +0x140 : all zero
```

Both vptrs match the vtables recovered statically, on a running system. The
class identification is no longer an inference.

## What the values say

**The state is 1, not 0.** An earlier reading of the constructor suggested the
STM might be stuck at state 0, which has no case and returns immediately. It is
not: `Enable VideoDeocer` ran at bring-up and did exactly what the disassembly
said — the write at `0x8b146eb0` set `+0x5a0`. State 1 is a real case
(`beq $v0, 1 -> 0x8b1474c8`) and that path calls `CheckSignal`.

**The enable flag is set** (`+0x5a4 = 1`) and **the detector is allocated**
(`+0x5a8` non-NULL, correct vptr).

**And both frame-info buffers are entirely zero.** `GetFrameInfo` writes into
`+0xb0` on every successful read and `CheckSignal` latches into `+0x140` on
change. Zeroes there prove, from memory rather than from missing log lines, that
**neither has ever executed**.

## So the gap is exactly one call

Everything is constructed, enabled, in a valid state, and pointed at a valid
VideoInfo descriptor:

| link | state |
| --- | --- |
| VideoInfo in the AFBD slots | valid — `0x4D941000`, Y/C populated |
| `THidTVPro` constructed, enabled | yes — flag 1 |
| STM state | **1 (NoSignal)** — a live case that polls |
| detector allocated | yes, correct vptr |
| detector ever run | **no** — both buffers zero |

**Nothing invokes `THidTVPro` slot 16 (`+0x40`).** The machine is armed and no
one turns the handle.

## The caller hunt, and why the scans failed

Not found. Recorded so the next attempt does not repeat it:

- No direct `jal` to `0x8b147390` exists anywhere; it is reached only through
  the vtable.
- Scanning for `lw $reg, 0x40(vt); jalr $reg` yields 15 sites across the image.
  Two are stack loads. The identifiable ones belong to other classes — e.g.
  `0x8b13478c` is HDMI-RX (`THDMIRx_DisplayModuleCtx.cpp`, `GetVideoFormat`),
  and `0x8b1a7420` uses slot `0x40` as an object *getter* whose result is
  immediately dispatched again.
- The singleton field `container + 0x266c` has exactly **one** reader, the
  getter itself, and the getter has exactly **one** caller (`0x8b1839fc`), which
  stores the pointer into an aggregate at `+0x14` alongside three other
  singletons.

That shape says the poll does not come through a named field at all: the device
is registered into a framework — the `BaseDev` strings in slots 3, 4, 9 and 10,
and `IDeviceVidDec : IDevice` — and the framework walks a list. A pattern scan
cannot isolate that; the aggregate at `0x8b1839fc` and what consumes it is the
thread to pull.

## Cheap live experiment this enables

The STM is a virtual call on a known live object. Its state word is at ARM
`0x4b83084c + 0x5a0` and the detector at `0x4b830ea8`. That means a future test
can **watch** `+0x140` for a non-zero latch as proof the machine ran, without
needing the log at all — a much tighter signal than grepping elog tags.
