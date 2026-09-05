# What "signal" means for source 1 (VideoDecoder) — answered

Static RE plus live reads, no risky writes. This answers the single open
question left by
[handoff-2026-09-04-mips-window-layer.md](../handoff-2026-09-04-mips-window-layer.md).

## Signal is the VideoInfo descriptor, read by a signal *detector*

The firmware has a dedicated component: **`./vid_dec_signal_detector.cpp`**, log
tag **`vdd`**, class **`CVidDecSignalDetector : IDeviceVidDec`** (vtable
`0x8b1f8d78`, 10 slots). Its named pieces:

| symbol | role |
| --- | --- |
| `GetFrameInfo` | reads the VideoInfo pointer and validates it |
| `ConvertFrameInfo2SignalInfo` | turns frame info into SignalInfo |
| `EntrySTMNoSignal` / `EntrySTMSignalChanging` / `EntrySTMSignalValid` | a three-state machine |
| `"invalid frame info, buf_addr: 0x%x"` | the rejection message |

`GetFrameInfo` (body at `0x8b147834`..`0x8b1478c8`, vtable slot 6) is exactly the
routine that reads `0x05600098`:

```
v0 = readl(AFBD + 0x98 | 0x9c | 0xa0 | 0xa4)   ; slot chosen by index
if (v0 == 0)              return 0             ; no frame info
if (v0 <  0x40000000)     log "invalid frame info, buf_addr: 0x%x"; return 0
v0 = (v0 & 0x0fffffff) | 0xa0000000            ; -> kseg1, uncached
copy 0x90 bytes (144) into a local buffer
return 1
```

So the answer is concrete: **"signal" for source 1 is a valid VideoInfo
descriptor pointer in the AFBD slot registers.** Non-zero, at or above
`0x40000000`, with 144 readable bytes behind it. That descriptor carries the
geometry — 1280x720, stride 1280, 30000 = fps x1000 — decoded in
[videoinfo-descriptor-decoded](videoinfo-descriptor-decoded-2026-09-04.md).

`ConvertFrameInfo2SignalInfo` then produces the SignalInfo the window manager's
`SetSignalInfo` consumes, and the state machine moves NoSignal ->
SignalChanging -> SignalValid.

## And the descriptor is already valid on our board

Read live, core alive, this boot:

```
0x05600070  0xFFC00000     Y
0x05600084  0xFFCE1000     C
0x05600098  0x4D941000     VideoInfo   \
0x0560009c  0x4D941000                  |  all four slots populated,
0x056000a0  0x4D941000                  |  physical, >= 0x40000000
0x056000a4  0x4D941000                 /
```

`GetFrameInfo` would accept every one of those. The data is not the problem.

## The problem is that the detector never runs

```
vdd records this boot: 0
```

**Not one `vdd` log line**, against 2337 `cpucomm`, 629 `sys`, 190 `vnode` and
134 `wce_*`. `CVidDecSignalDetector` has never executed — so `GetFrameInfo` is
never called, the descriptor is never read, no SignalInfo is ever produced, and
the window layer has nothing to recompute against.

That is the whole gap, and it reframes everything: **we have been supplying the
signal correctly and nobody is looking at it.**

## Consistent with everything else observed

- `SetSource(1)` reached `AppTopSetSource` and one `SetSignalInfo` — the *plumbing*
  works, but with no detector running that call carried no real geometry.
- The WCE never recomputes: no `UpdateWce`, no `CalcWindow`, nodes at bring-up
  geometry, `PanelWinNode.cpp:328` still `bypass`.
- `vnode`/`FrameBuffer.cpp` shows the capture path at a placeholder
  `picture_win: [0, 0, 720, 240]`, not 1280x720 — the no-signal default.
- The panel is black because the window layer is emitting nothing, not because
  anything masks it (the blue-screen overlay was separately eliminated).

## What is not yet known

**What starts `CVidDecSignalDetector`.** Its constructor stores the vptr at
`0x8b147bc0` and has no direct `jal` callers, so it is created indirectly —
placement-new, a factory, or a device table. The likely trigger is whatever
"opens" the video-decoder device: note `THiDTVPro.cpp:57 "Enable VideoDeocer [1]"`
appears at bring-up, and `IDeviceVidDec : IDevice` implies a device-registration
framework with an open/start call.

That is the next thing to find, and it is static work:

1. Resolve `IDeviceVidDec`'s vtable and the `IDevice` base — the open/start slot.
2. Find the device table or factory that instantiates `CVidDecSignalDetector`.
3. Look for a CPU_COMM or app-level call that opens the decoder device; the
   peer's 12-call boot sequence still has picture-default calls we have never
   sent, and one of them may be what starts it.
