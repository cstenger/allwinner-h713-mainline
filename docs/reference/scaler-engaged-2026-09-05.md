# The firmware enabled the video source and ENGAGED THE SCALER

> **HEADLINE REFUTED 2026-09-10 —
> [composition-ratio-registers-are-line-buffers-2026-09-10.md](composition-ratio-registers-are-line-buffers-2026-09-10.md).**
> `0x05000174` is not a ratio register: it is `{[27:16] C LineBufLevel,
> [15:0] C Rowbyte}`. Rowbyte is **linear in the picture width**, so any two
> widths give a value ratio equal to the width ratio whether or not anything
> scales — which is all "43/64 ≈ 852/1280" ever showed. The `wce_panel` line in
> this document's own capture is the counter-evidence: borders of exactly
> `1280-852 = 428` and `720-480 = 240`. The firmware **letterboxed** the 852x480
> picture at native size.
>
> **What still stands, and is still the real result:** the firmware read our
> VideoInfo descriptor, advanced its state machine, and ran the full window
> pipeline off our frame for the first time.

2026-09-05, live core. The plan's central unproven assumption — *does this
hardware scale* — is answered **yes**, by the firmware's own programming.

## The sequence that did it

```
cold boot -> h713_disp init 0x34            # core alive, handshaken
boot h713-kernel-decd-iommu-0076v3.fit      # dec okay, display disabled
insmod sunxi-decd-budget.ko ring_writes_max=1
insmod hy310-cpu-comm-next.ko
decd-client show /root/decd-test-frame.nv12 2000
mips-shell.py --cmd "dtv get_fb"
```

No `Vp_Init`, no `SetSource` this boot. The ring got exactly **one** write.

## The firmware read our descriptor and moved its state machine

```
THidTVPro  state +0x5a0 : 1 -> 2         (NoSignal -> SignalChanging)
detector   +0x0b0 : 61770000 00000002 00000500 000002d0 ...
           +0x140 : 61770000 00000002 00000500 000002d0 ...
```

Both detector buffers now hold **our VideoInfo descriptor** — header
`0x61770000`, `0x500` = 1280, `0x2d0` = 720. Previously both were all zero.
`GetFrameInfo` accepted it and `CheckSignal` latched it.

The elog agrees: `video_dec.pic_size.h_size: 1280`, `v_size: 720`,
`frame_rate_orig: 0x30004`.

## And the window layer ran its full pipeline

For the first time in this project:

```
I/wce_top    SetWindow : EXIT
I/wce_nr     NRWinNode.cpp 400  WriteReg : ENTER
I/wce_nr     y:1280, c:1280
I/wce_nr     y_width:852, c_width:852, v_size:480
I/wce_nr     WriteReg : EXIT
I/wce_proc   WriteReg : ENTER / EXIT
I/wce_panel  WriteReg : ENTER
I/wce_panel  top_width:0, bottom_width:240, left_width:0, right_width:428
I/wce_panel  WriteReg : EXIT
```

`CalcWindow` produced `m_video_win_2: [49, 22, 852, 480]` inside the 1280x720
panel, with borders of exactly 1280-852=428 and 720-480=240.

## The hardware, and the headline

```
0x05600010  0x03000013   video source ENABLED  <- the firmware set this itself
0x05600030  0x01E00354   source size 852 x 480
0x05000174  0x002B002B   scaler ratio -- NOT unity (unity is 0x00400040)
0x05000274  0x002B002B
0x051c006c  0x29000000   LVDS selector still on RGB/OSD
0x051c0138  0x08010000   panel down-scaler still bypassed
```

**`0x05000174` reads `0x002B002B`.** That register sat at `0x00400040` — unity —
through every experiment in this project, and two sessions concluded from its
silence that the block was not in our path. It is now at 43/64 = 0.672, and
852/1280 = 0.666. **The NRWinNode scaler is engaged and downscaling.**

We never wrote it. The firmware programmed it, from our frame.

### What that retires

- *"Does this hardware scale at all"* — the plan's unproven item 1, and the
  reason several negatives were hard to interpret. **Yes, it scales.**
- The long run of nulls on `0x05000174` was never evidence the block was
  unreachable; it was evidence nothing had ever given the window layer a reason
  to program it.

## What is still missing for scanout

The **LVDS selector is still `0x29000000`** — the RGB/OSD source, not video
(`0x39000000`). So the composited video is not routed to the panel yet, and the
panel down-scaler remains bypassed.

The state machine is at **2 (SignalChanging)**, not 3 (SignalValid). The obvious
next step is whatever advances it — another `dtv get_fb`, or the poll that
should be driving it — and to watch whether the firmware then flips the selector
itself, as it owns that mux.
