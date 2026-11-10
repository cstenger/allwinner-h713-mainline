# Panel-source stage 1 (read-only), October 23

The first live run for [the panel-source design](../../hdmi-panel-source-design-2026-10-23.md)
(section 10.1). It used a production cold HDMI session, boot
`799298ff-2063-4c9b-a7f5-f67de6f8e58c`: handoff present, capture, signal and
speaker services active, signal owner `ready=Y`. The source was this host's
`card1-HDMI-A-1`.

All board access was read-only (`tools/hdmi/panel-source-snapshot.py`,
`/dev/mem` opened `O_RDONLY`, word loads only). The run did not touch
`0x07091xxx`, `0x0694xxxx` or GP7. The only change was to the host:
`cosmic-randr disable/enable HDMI-A-1`. The sequence is in
[`events.jsonl`](events.jsonl), the derived diff in [`report.md`](report.md),
and the per-state files under `locked/`, `nosignal/` and `relocked/`. Raw
elog dumps (2 MiB × 2 per state) are in `local/hdmi-stage1/2026-10-23/`,
with their hashes in each `sha256.json`.

| Time (host) | Step | Board uptime | Port 1 | TCON `+0x1c/+0x20/+0x24` |
| --- | --- | --- | --- | --- |
| 00:34:15 | `locked` snapshot | 61 s | state 5, 1280×720 | `00000004 02F80550 02D00500` |
| 00:36:24 | host output **off** | | | |
| 00:36:32 | `nosignal` snapshot | 199 s | state 3, 0×0 | `00D00404 02F80550 02D00500` |
| 00:36:43 | host output **on** | | state 5 within one probe | |
| 00:36:51 | `relocked` snapshot | 219 s | state 5, 1280×720 | `00D00404 02F80550 02D00500` |

The loaded firmware config (its DRAM copy at `0x4be01000`) has elog
**mode 2, level 5**, so the log is comparable with the 10-07 stock log.

## Findings

1. **The firmware runs stock's lock sequence and still leaves its display
   DMA off.** Our log has the same steps as stock, through
   `NotifySignalChange`:
   * `SetSource(3)` at tick 307;
   * lock 4 → 5 at 22121;
   * the AVI infoframe, which reports RGB and full range;
   * `CallbackOfSignalChange` and `UpdateWce` (`low_latency:1`);
   * capture and NR `CalcWindow`/`WriteReg`;
   * `update_onoff` and `memory_agent_onoff`;
   * `AV mute:0 0`.

   The diff tool first marked capture `WriteReg` and `update_onoff` as
   missing. Both are present: they sat in cache-hole records, so the
   tool's matcher missed them.

   Even so, in every state:
   * `0x05600010 = 03000010`: AFBD source 0 off;
   * `0x05000178/1b8` bit 31 clear: NR fetch off;
   * `0x051c006c = 29000000`: the panel is on the console;
   * `0x05140d54 = 0` and `0x051c00b8 = 0x38`: no blue-screen mute.

   So the firmware itself chooses not to start its display path. What's
   missing compared with stock is everything ARM does there:
   * Android's HAL init (stock obtains three `hal` blue-screen handles at
     `ObtainBlueScreenHandle`; ours has none);
   * the ARM-side dispatch of `NotifySignalChange` (stock's `hal:` lines);
   * `Wce_SetWindow`;
   * `DisableBlackScreen`.

   Which of these gates the MemoryAgent decision is not yet established.
2. **Production U-Boot does not install the VIncap capture-completion
   hook.** The words at `0x4b100ba0/bac/c08` read `0` and `0x4b1863a4`
   reads `8c470008`; installed, they would be `27bdfff8/3c18ad98/0ac618eb`
   and `0ac402e8`. The source-path trace word at `0x4b1008e0` is installed,
   and the trace page's magic and canaries are intact. Capture counters
   `+0x84..+0x90` stay 0 throughout, yet the NV16 ring **is** being written:
   six probe-page hashes changed on every one of three reads, one second
   apart. The current V4L2 bridge refuses to load without this hook, so
   revision 2 needs either the hook in the production cold path or another
   completion signal.
3. **Signal events, with timings (for Q2).**
   * Host disable → port 5 → 3 at firmware tick 196276. One bounce follows:
     3 → 4 → 5 within 81 ms with `Set AVMUTE!`, then 5 → 3 at 196417.
   * Host enable → 3 → 4 at 215488 and 4 → 5 at 215498, `Clear AVMUTE` at
     215588, `Signal changed 0 → 0x20015` at 215908, `AV mute:0 1` and
     `CallbackOfSignalChange` at 216208. That is about 0.7 s from TMDS lock
     to a valid signal, and the firmware then re-runs `UpdateWce` and the
     window writes.
   * Every transition ends in `NotifySignalChange`: the firmware's own event
     toward ARM exists and fires on loss and on lock.
   * A disable produces a sub-second 5 → 3 → 5 → 3 bounce, which is the case
     the design's HOLD/grace state is meant to absorb.
4. **No presentation register changed across the three states.** The only
   differences are AFBD `+0x0b8/+0x0bc/+0x30c` and `+0x320/324` (capture
   pair bookkeeping), DETN `+0x83c`, and route `+0x168`. TCON timing
   `+0x20/+0x24` held at 720p (Q5: no timing rewrite on loss or lock).
   TCON `+0x1c` went from `00000004` to `00D00404` at the first loss and
   stayed there. Bits 7:0 are unchanged, and the meaning of the new upper
   bits is unknown.
5. **Operator observation:** the panel showed the Linux console the whole
   time, with no black and no flicker, through locked, host output off,
   host output on and re-lock. So the TCON `+0x1c` change in finding 4 has
   no visible effect.

## Not established

Why `update_onoff` leaves the display agents off. The next step is offline:
trace `update_onoff`'s inputs (the signal-status virtual at
`0x8b184334`→`+0x10`, flags `+0xb4..+0xb6`, `+0x14`) back to whichever ARM
HAL call sets them in stock. No live write was made.

## Follow-up reads (same boot, read-only DRAM)

These came out of the offline trace in design doc section 10.3:

* The DeviceManager table (root `0x4bac1a70`, object `0x8b827fd4`), giving
  `{source, field1, field2}` per source:
  * Dummy `0 → 5, 5`
  * VideoDec `1 → 3, 3`
  * HDMI 1–4 (`3..6`) `→ 1, 2`
  * CVBS (`7..9`) `→ 0, 1`
  * ATV `10 → 0, 0`
* The MemoryAgent (global `0x8b499b14` → `0x8b89d37c`, vptr `0x8b1fb818`):
  * `+0x4 = 1`, `+0x8 = 0`, `+0xc = 0x00020003`: the constructor values,
    never refreshed;
  * `+0xb4..b7 = 00 01 00 8b`, i.e. `+0xb5 = 1`, `+0xb6 = 0`.
