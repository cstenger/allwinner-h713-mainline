# T3: `win rn 2` makes the firmware program AFBD for HDMI (10-23)

T3 from §10.10 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).
It ran on a production cold boot `564430ad-6197-49be-a0a5-985e40a2cbae` with
the original proper `1b1f702f`, the operator watching. The PC end of the HDMI
cable had to be reseated once before the host detected the projector (the
09-25 first-HPD-window behaviour). After that, port 1 was in state 5 at
1280×720.

## Preconditions (read-only, all passed; `read-pre.json`)

* MemoryAgent `+0xc = 00020003`, `+0xb5 = 1`.
* IOMMU bypass `58`; selector `29000000`; TCON `00000004 02f80550 02d00500`
  (720p).
* AFBD source 0 off, in its decoder configuration: `0x10 = 03000010`,
  `0x20 = 043f077f`, mux `0x68 = 122`; composition `0x30 = 00000c00`.
* Frame-programmer record stage `6103`, mask `ffffffff`, mode 2.
* Pool `4bf41000/01a00000` with `no-map`; no IOMMU fault lines; no Cedrus
  user.

## Steps

All commands went through `/usr/lib/h713-hdmi/mips-shell.py --cmd`.

| Read | Command | AFBD `0x10` | geometry `0x20` | mux `0x68` | comp `0x30` | FP record (stage mask mode ctrl) | TCON | faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pre` | — | `03000010` | `043f077f` | `122` | `00000c00` | `6103 ffffffff 2 03000010` | `4 / 02f80550 02d00500` | 0 |
| `rn2` | `win rn 2` | **`03000200`** | **`02cf04ff`** | **`022`** | **`00400000`** | **`6103 00007e02 1 03000200`** | `00d00404 / 02f80550 02d00500` | 0 |
| `rn2-5s` | (5 s) | same | same | same | same | same | same | 0 |
| `rn0` | `win rn 0` | same | same | same | same | same | same | 0 |

Also after `win rn 2`:
* AFBD `0x24` → `002c004f`, Y/C strides `0x40/0x44` → `00000500`, `0x4c` →
  `02d00500`.
* Composition `0x178/0x1b8` changed line-buffer counts; bit 31 stayed clear.
* Address slots `0x70–0x9c` stayed zero.
* The window manager's `+0x150` read **0** after `win rn 0` (`winmgr-after.txt`).
* Full snapshots are in `../t3-before` and `../t3-after`.

TCON `+0x1c` going `4 → 00d00404` is the same status change stage 1 saw at
its first signal loss; the timing words didn't change.

## Result

**The lever works.** One forced full window refresh while HDMI is locked
ran NR WriteReg with mask `0x7e02` in **mode 1**, and so the AFBD source-0
programmer in capture mode:

* **Source mode 1:** mux bit 8 cleared (`122 → 022`), `0x10` bit 4 cleared,
  composition `0x30` bit 22 set. These are exactly the §10.7 predictions.
* **Geometry 1280×720** (`0x20 = 02cf04ff`), strides 1280.
* **Chroma line count 720** (`0x4c = 02d00500`, i.e. 4:2:2: full-height
  chroma).
* **Format byte `0x02`** (`0x10[15:8]`): the firmware's own encoding for
  this input. It matches the decoder-enum reading of the `0x8b1a31e8`
  resolver (`Yuv422_888 → 2`). **This is the 4:2:2 encoding open in §1.5**,
  observed on hardware rather than inferred.
* **No address slots:** in capture mode source 0 takes its addresses from
  the hardware capture pair at `+0x320/324` (the NV16 ring at `0x4c3ef000`,
  `+n·0x1ff000`). So the IOMMU identity map master 2 needs is the **capture
  ring inside the frame-buffer pool**, `0x4bf41000–0x4d940fff`.
* Source 0's enable bits stayed `0` (memory agent 4 off), so there was no
  fetch, no IOMMU exposure and no fault. The selector never moved; the
  operator saw the console throughout.

The AFBD capture configuration persists after `win rn 0`, because the
partial refresh doesn't reprogram it. That's harmless: source 0 is
disabled, and the next boot resets it.

Operator observation: the Linux console throughout, as expected (no
selector change).
