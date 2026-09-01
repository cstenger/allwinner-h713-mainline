# Remaining writable cross-stack candidates eliminated, 2026-08-31

The fifteen unresolved writable differences from the stock-versus-Linux block
comparison were forced together from the accepted Linux playback state onto
stock Android during live playback. The panel showed no visual change.

This closes the entire remaining writable set from the captured windows. The
calibrated chroma gain at `0x05140508` is the only writable defect found by the
comparison; it remains real but is already known not to explain the missing
picture by itself.

## Apparatus and admissibility

- Board: vendor Android, slot A, reachable over authenticated adb.
- Player: `com.softwinner.TvdVideo/.TvdVideoActivity`.
- Input: the 600-second 1280x720 H.264 clip at media id 36.
- Writer: `/data/local/tmp/hidtvreg-replay`.
- Value list: `/data/local/tmp/ours-untested15.txt`, byte-identical to
  `tools/display/ours-untested-writable-2026-08-31.txt`, SHA-256
  `104cbb30ef27d012d64d992515031264de155e4a7ef4a561cc203afb230d6036`.
- Command: `hidtvreg-replay /data/local/tmp/ours-untested15.txt 14`; the final
  argument is hexadecimal, so the hold was 20 seconds.
- All fifteen writes were accepted exactly on immediate readback.
- All fifteen original stock values were restored exactly after the hold.
- `QueueBufferToShow` advanced continuously once per second from PTS 0.067
  through PTS 48.000 around the run. There was no `onCompletion` event.
- Operator report immediately after the run: “I didn't notice a visual
  change.”

The continuous decoded-frame evidence rules out the failure mode from earlier
stock tests where the clip had ended before or during the observation.

## Exact replay

| address | stock before/restored | Linux value held |
| --- | --- | --- |
| `0x05000604` | `0x007B0A08` | `0x007B0A18` |
| `0x05000610` | `0x0304200D` | `0x0304100C` |
| `0x05000900` | `0x00800D47` | `0x00800D44` |
| `0x05000914` | `0x0004000E` | `0x00044004` |
| `0x05000920` | `0x70248077` | `0x50241488` |
| `0x05000924` | `0x00000007` | `0x00000002` |
| `0x05000930` | `0x50074022` | `0x400F4022` |
| `0x05000934` | `0x84081008` | `0x84081010` |
| `0x0500093c` | `0x84804692` | `0x84804691` |
| `0x05000974` | `0xC000D021` | `0xFF00D021` |
| `0x05140540` | `0xD4146088` | `0xD41C6088` |
| `0x05140544` | `0x00000001` | `0x00000003` |
| `0x05140548` | `0x00002020` | `0x00002820` |
| `0x051405b0` | `0xFFFE2F17` | `0xFFFE2F1B` |
| `0x05140c4c` | `0x78800888` | `0x78000800` |

## Scope of the result

This is a combined-set negative, not fifteen independent observations. It is
strong evidence that none of these differences is required for stock's visible
video: every register took the Linux value simultaneously and stock continued
displaying normally. A cancellation between multiple forced differences is
logically possible but has no positive evidence and is not worth bisecting a
null result.

The next experiment remains the one-register positive transfer in the other
direction: set `0x05140508` to `0x144C0000` on the Linux DECD stack and submit a
bounded frame.
