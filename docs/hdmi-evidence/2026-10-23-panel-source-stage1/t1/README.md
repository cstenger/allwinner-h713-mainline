# T1: NR memory agents on, via the firmware shell (10-23)

This is the guarded first live test from §10.5 of
[the design](../../../hdmi-panel-source-design-2026-10-23.md), run with the
user's approval and the operator watching the panel. It ran on the stage-1
boot `799298ff-2063-4c9b-a7f5-f67de6f8e58c`, uptime ≈ 2880–3075 s, with the
host source locked at 1280×720.

## Preconditions (all passed, read-only)

* MemoryAgent vptr `8b1fb818`, `+0xc = 00020003`, `+0xb4..b7 = 00 01 00 8b`
  (the §10.3 state).
* IOMMU bypass `00000058`: master 3 (NR) bypasses, master 2 (AFBD)
  translates.
* `0x05600010 = 03000010`, `0x051c006c = 29000000`; nothing has
  `/dev/video0` open.
* Firmware `<frame_buffer>` is `0x4bf41000` / `0x1A00000`, and Linux has
  `framebuf@4bf41000` with `reg = 4bf4100001a00000` and `no-map`.
* Port 1 in state 5, 1280×720; the host connector connected and enabled; no
  IOMMU fault lines in `dmesg`.
* Shell: the production copy at `/usr/lib/h713-hdmi/mips-shell.py`.
  `help memory_agent` answered "for memory_agent debug only".

## Sequence

All commands went through `mips-shell.py --cmd`; each was followed by a
read (`read-*.json`). Full snapshots are in `../t1-before`, `../t1-on` and
`../t1-after`.

| Step | Shell command | Change seen |
| --- | --- | --- |
| read `pre` | — | composition `0x178/0x1b8/0x278/0x2b8` = `6002021c/60020438/60020168/600202d0` |
| `en5` | `memory_agent en 5` | `0x05000178` → `e002021c`, `0x050001b8` → `e0020438` (bit 31, NR Y/C fetch). Nothing else |
| `en5-10s` | (10 s hold) | Unchanged. The capture ring is still written (`ringprobe-en5.txt`, all six probe pages change every second) |
| `en6` | `memory_agent en 6` | `0x05000278` → `e0020168`, `0x050002b8` → `e00202d0` (bit 31, channel B) |
| `en6-10s` | (10 s hold) | Unchanged |
| snapshot `t1-on` | — | Composition bits as above. AFBD source 0 untouched |
| `dis6`, `dis5` | `memory_agent dis 6`, `memory_agent dis 5` | All four words back to the `pre` values exactly |
| snapshot `t1-after` | — | Services active, signal owner ready, TCON `00D00404 02F80550 02D00500` |

Across the whole run:
* AFBD source 0 (`0x05600000–0x9f`) never changed. It kept `0x10 =
  03000010`, the inherited `0x20 = 043F077F`, and zero address slots.
* The selector stayed `29000000`, IOMMU bypass stayed `58`, TCON timing
  stayed at 720p, and no IOMMU or page-fault lines appeared.
* The only other registers that moved are counters and meters that move in
  every state: AFBD `+0x0b8/0bc/184/30c/320/324` and route `+0x168`.
* The firmware log gained only the `memory_agent_onoff` records. There was no
  window, frame-programmer or AFBD activity.

## Result (outcome row 2 of §10.5)

The NR agents can be switched on and off cleanly while HDMI is locked:
* no fault, no hang;
* capture unaffected;
* the panel selector and timing untouched;
* exact restoration afterwards.

**But turning NR on does not make the firmware program AFBD source 0.** The
geometry and addresses for NR's output must come from another trigger:
probably the frame programmer `0x8b1a4538` on the PanelWinNode dirty-bit
`0x800` path, or whatever stock's capture-mode (`m_afbd_source_mode 1`)
route uses. Nothing here shows whether NR actually produced frames: no
NR-side status register is identified, and NR's buffers aren't stored
anywhere we can read.

Operator observation: the Linux console the whole time during T1, with no
black and no flicker.
