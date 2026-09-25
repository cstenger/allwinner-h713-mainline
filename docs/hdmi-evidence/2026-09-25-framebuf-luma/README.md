# First recovered HDMI input pixels

On the unchanged merged 6.18.38 kernel, U-Boot had selected source 3 and the
TVFE/TVCAP domains and four receiver clocks were held. One bounded 15-second
SCP HPD/EDID window made the connected GPU enable 640x480 output at 2.86 s.
The same EDID and MIPS port-state/timing behavior had just been reproduced in
the [restart trial](../2026-09-25-source3-restart/README.md).

The read-only page probe hashed the 26 MiB reserved `framebuf@4bf41000`
carveout before, three times during GPU output, and after disconnect. Exactly
438 pages differed from the pre-video snapshot on each later sample. They fell
into six regions spaced by 511 pages (`0x1ff000`) beginning at physical
`0x4c3f0000`, `0x4c5ef000`, `0x4c7ee000`, `0x4c9ed000`, `0x4cbec000`, and
`0x4cdeb000`. The same 438 pages changed between each consecutive live sample.
This makes six regularly spaced candidate frame slots; page hashes alone do
not establish the allocator or completion signaling.

A fixed, read-only 320 KiB sample from the first region at 4.71 s was saved
as [`candidate-1.bin`](candidate-1.bin). Its first **307,200 bytes** have
the layout of contiguous 8-bit 640x480 luma, though the final 4 KiB page is
unwritten. The resulting
[`captured-luma.png`](captured-luma.png) visibly shows the HDMI-connected
computer's desktop. A second sample at 10.27 s had the same recognizable
image; 79,680 luma bytes differed from the first, all by exactly one level.
The remaining bytes of the 320 KiB diagnostic sample were zero. A later
read-only scan of the first full candidate slot found nonzero data only in its
first 303,104 bytes, plus one trailing 4 KiB page near the end of the slot.
No chroma plane was identified *in that first region*. The follow-up
[color capture](../2026-09-25-nv16-capture/README.md) found matching UV data
in the fourth region. The raw dump and PNG are retained so
the interpretation can be independently checked; `tools/hdmi/luma-to-png.py`
does the conversion without image libraries.

The probe and sample read reserved DRAM through `/dev/mem`; they did not touch
receiver registers or modify hardware. SCP reported peripheral restoration
and zero EDID mismatch, and DDC pins were released. MIPS, Linux, and SSH
remained responsive. This establishes **HDMI input pixels in accessible DRAM**
and a usable grayscale snapshot. The follow-up established an NV16 color
candidate; frame boundary, ring index, final-page completion, and V4L2 remain
unresolved.
