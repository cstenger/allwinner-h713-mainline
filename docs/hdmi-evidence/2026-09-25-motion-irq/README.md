# Moving HDMI frames and capture-interrupt lead

`make-motion-pattern.py` creates a lossless 640×480, 60 Hz video. Each frame
contains an eight-bit frame number repeated in four horizontal bands and a
vertical stripe whose horizontal position depends on that number. COSMIC's
panel overlays the upper band on HDMI-A-1, so the analyzer checks the three
unobscured bands at rows 168, 312, and 456 plus stripe positions at rows 96,
240, and 384. A synthetic frame spliced halfway between two source frames
produced a [band and stripe mismatch](synthetic-tear-analysis.json), confirming
that this check detects that class of tear.

The first sparse-verification V4L2 run captured **120/120 patterned frames**
at about 59 fps. Every frame had the same ID in all three bands and a stripe
at the position encoded by that ID. Of 119 transitions, 117 advanced by one
source frame, one repeated, and one skipped an ID. See the
[analysis](sparse-analysis.json), [FFmpeg log](sparse-ffmpeg.log), and
[first](h713-motion-captured-first.png)/[last](h713-motion-captured-last.png)
previews. A second 120-frame sparse run also had zero band and stripe
mismatches; its [analysis](sparse-irq-analysis.json) recorded 115 adjacent
steps, one repeat, and three skips.

The full-comparison control captured **60/60 patterned frames** with zero
band or stripe mismatch. Its frame IDs skipped between captured frames as
expected at its roughly 22 fps delivery rate; see the
[analysis](full-analysis.json) and [FFmpeg log](full-ffmpeg.log). Both
[sparse](sparse-target.log) and [full](full-target.log) signal trials report
`peripheral_restored=1` and `edid_mismatch=0`, with DDC restoration in the
matching [sparse](sparse-cleanup.log) and [full](full-cleanup.log) cleanup
logs. These tests reject mixed frame IDs at the sampled heights. They do not
prove that every pixel of every future frame is tear-free, so full comparison
remains the normal V4L2 mode.

During the third sparse run, read-only ARM `/proc/interrupts` snapshots were
taken in [idle](irq-idle-a.log) and [video](irq-video-a.log) windows, with
second samples [here](irq-idle-b.log) and [here](irq-video-b.log). In both
windows only the existing timer, IPI, and MMC lines advanced. No distinct
ARM capture interrupt line appeared. This does not rule out an interrupt
delivered to the MIPS processor. The [delta summary](irq-delta.json) lists
each changed line.

Static inspection of the validated board-B `display.bin` (SHA256
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`)
found three capture event descriptors. The reproducible
[census](cap-irq-static.json) checks the firmware bytes and reports:

| Descriptor | Event ID | Status bit |
| --- | ---: | ---: |
| `cap-vde` | 2 | 0 |
| `cap-vs` | 3 | 1 |
| `cap-mode_change` | 4 | 2 |

The capture handler at MIPS VA `0x8b186388` reads `0xbb940100` and
`0xbb940008`, extracts bits 8–15, masks the status, then writes the low byte
of `0xbb940008` in an acknowledge sequence. These map to candidate ARM
physical addresses `0x06940100` and `0x06940008`; see the
[disassembly](cap-irq-handler-disasm.log). The firmware's dispatch table
points to this handler at `0x8b2322c8`. **No live reads or writes of those
capture registers were made.** Earlier ARM accesses to the capture domain
have locked the board, and the static labels alone do not establish whether
`cap-vde` or `cap-vs` means a particular ring pair is complete.

The next hardware-backed step is to correlate these MIPS events with the
observed 0→1→2 ring turnover using an isolated, read-only firmware-side
trace. Only after that correlation should the V4L2 bridge use an event to
select a buffer. The current software bridge remains available throughout.
