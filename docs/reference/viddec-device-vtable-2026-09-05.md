# `CVidDecSignalDetector`'s vtable, and the poll that never runs

Static RE. Follows
[what-is-signal-for-source1](what-is-signal-for-source1-2026-09-05.md).

## `IDeviceVidDec` is abstract — resolve the concrete class instead

`IDeviceVidDec : IDevice` has a typeinfo (`0x8b1f8b9c`) but **no vtable of its
own**: it is a pure interface. The usable artifact is the concrete
implementation, `CVidDecSignalDetector`, vtable **`0x8b1f8d78`** (so an object's
vptr is `0x8b1f8d80`), 10 slots.

Slots named by the trace string each function passes to the logger — every one
carries the `vdd` tag:

| slot | vptr offset | address | name |
| --- | --- | --- | --- |
| 0 | `+0x00` | `0x8b1476f8` | lifecycle / `DbgCheckDtvStop` guard |
| 1 | `+0x04` | `0x8b14776c` | " |
| 2 | `+0x08` | `0x8b14775c` | " |
| **3** | **`+0x0c`** | **`0x8b147dd0`** | **`CheckSignal`** |
| 4 | `+0x10` | `0x8b147708` | " |
| 5 | `+0x14` | `0x8b147948` | `ConvertFrameInfo2SignalInfo` |
| **6** | **`+0x18`** | **`0x8b147834`** | **`GetFrameInfo`** |
| 7 | `+0x1c` | `0x8b147774` | " |
| 8 | `+0x20` | `0x8b1477d4` | `DbgEnableDtvStop` |
| 9 | `+0x24` | `0x8b147700` | " |

The slot numbering is self-confirming: `CheckSignal` dispatches
`GetFrameInfo` through `lw $v0, 0x18($v0)`, and `0x18 = 6 * 4`, matching slot 6
recovered independently from the vtable.

## `CheckSignal` is the poll we need, and it is one call away

```
CheckSignal(self):
    v0 = self->vptr[0x18]                  ; GetFrameInfo
    jalr v0        (self, self + 0xb0, 0)  ; read the VideoInfo descriptor
    if (v0 == 0) return                    ; no frame info -> nothing to do
    jal 0x8b147bd8 (self, self + 0xb0, self + 0x140)   ; compare against the
                                                       ; stored copy
    if (v0 == 0) goto <unchanged>
    copy self+0xb0 -> self+0x140, 16 bytes at a time   ; latch the new info
    ...
```

So the intended flow is exactly what we want: **`CheckSignal` -> `GetFrameInfo`
-> read `0x05600098` -> compare -> on change, convert and notify.** Object layout
falls out of it too: the working frame-info buffer is at `self + 0xb0` and the
last-latched copy at `self + 0x140`.

Nothing about this is blocked. `GetFrameInfo` would accept the descriptor sitting
in our slot registers right now. **The single missing act is that nobody calls
slot 3.**

## What still has to be found

**Who drives `CheckSignal`.** It is a virtual call at vptr `+0x0c`, so the caller
is whatever periodic task walks the `IDevice` list — the same pattern as the WCE
node walk, which dispatches `node->vtable[+0x10](node, mask)` from a handful of
internal sites.

Two approaches, both static:

1. Find the object. `CVidDecSignalDetector`'s constructor stores the vptr at
   `0x8b147bc0` and has no direct `jal` callers, so it is created indirectly.
   Locating the device table or factory gives the owner, and the owner will have
   the poll.
2. Find the call site. Scan for `lw $reg, 0xc(vt); jalr $reg` sequences and
   filter to those in the `vdd`/`dtv` region — the same technique that found the
   WCE apply dispatch.

A third, cheaper possibility worth testing before either: the detector may only
be started when the decoder *device* is opened, and
`THiDTVPro.cpp:57 "Enable VideoDeocer [1]"` at bring-up plus the untried
picture-default calls in the peer's 12-call boot sequence are the obvious
candidates for what does that.
