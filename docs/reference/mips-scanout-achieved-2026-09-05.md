# MIPS → scanout: a frame on the panel through the window layer

2026-09-05. **Operator-confirmed: a frame appeared on the glass**, routed by the
MIPS window layer. First time in this project.

## What was on screen

> "I saw a frame, it was greyscale and didn't fill the screen."

Both symptoms have exact, already-known causes, and neither is a fetch or
routing defect:

**Greyscale** — `0x05140508` read `0x14000000`. Bits 23:16 are the chroma gain
and were `0x00`, which is the documented greyscale signature from the
2026-08-31 scanout work; colour needs `0x4C` there (`0x144C0000`). Set and
re-run for a second observation.

**Not filling the screen** — the WCE computed it that way. `CalcWindow`
produced `m_video_win_2: [49, 22, 852, 480]` inside the 1280x720 panel, and
`PanelWinNode` logged `right_width:428` and `bottom_width:240` — exactly
1280-852 and 720-480. The picture is where the firmware put it.

## The full state that produced it

```
h713_disp init 0x34                       # live, handshaken core
h713-kernel-decd-iommu-0076v3.fit         # dec okay, display disabled
sunxi-decd-budget.ko ring_writes_max=1    # one ring write, no 60 Hz rewrite
decd-client show ...                      # populates Y/C/VideoInfo
mips-shell.py --cmd "dtv get_fb"          # firmware reads the descriptor
0x051c006c = 0x39000000                   # route video to the panel
```

with the firmware having programmed, on its own:

```
0x05600010  0x03000013   video source enabled
0x05600030  0x01E00354   852 x 480
0x05000174  0x002B002B   scaler engaged, 43/64
```

## What this settles

- **The hardware scales** — `0x05000174` off unity, programmed by firmware.
- **The window layer will composite our frames** — given a descriptor it can
  read and a source it has been told about.
- **The LVDS selector is ours to flip after all.** Earlier the same write was
  inert; the difference is that nothing was composited behind it then. It was
  never the selector that was wrong.

## What is still open

- **The STM sits at 2 (`SignalChanging`), not 3 (`SignalValid`).** Repeated
  `dtv get_fb` does not advance it — that command reaches slot 14
  (`GetFrameInfo`), not slot 16 (the state machine), and nothing invokes slot 16.
- **The whole path depends on a debug command.** `dtv get_fb` is what makes the
  firmware read the descriptor. For a real pipeline the periodic poll has to be
  found, or the read triggered another way.
- **852x480 is not 1280x720.** Why the WCE chose that window is unexamined —
  aspect ratio, overscan, or a default with `b_par_valid: 0` and `afd: 0` in the
  signal info. It is a window-geometry question, not a scaling one.
- The selector flip is manual and does not persist.
