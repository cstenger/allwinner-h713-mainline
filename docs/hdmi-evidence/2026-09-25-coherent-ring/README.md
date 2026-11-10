# HDMI frame-ring order and verified snapshots

The corrected NV16 frame bases are six planes in a three-pair ring: Y/UV
0/3, 1/4, and 2/5. A 3 ms read-only probe hashed four interior 4 KiB pages
per plane while the source supplied 640×480 video. Its
[`ring.json`](ring.json) contains 600 samples over 1.799 seconds. Grouping
successive changes in both planes of each pair produced 108 write runs in the
unbroken order **0 → 1 → 2 → 0**. A pair became active about every 17 ms;
the median return to the same pair was 51 ms. The
[`idle-ring.json`](idle-ring.json) control has zero changes in all six planes
over the same 1.799 seconds with HDMI disconnected. The preceding full-plane
CRC probe took 18 ms per sweep and could not resolve the order; sparse reads
were necessary.

`tools/hdmi/read-coherent-frame.py` uses that measured order without touching
receiver registers. Once both Y and UV pages of pair *n* change, the reader
copies the preceding pair `(n - 1) % 3` twice. It accepts the frame only if
the two complete 614,400-byte copies match and the probed pages did not
change across the reads. It fails instead of returning a stale frame when
there are no ring changes; the disconnected control returned no output after
one second.

One bounded 15-second HDMI window returned four distinct verified frames,
recorded in [`coherent.json`](coherent.json). The selected pairs were
**1, 0, 2, 1**; each pair was copied and compared in 13.3–14.6 ms, and each
frame has a distinct CRC32. The four raw samples are
[`01`](coherent-01-nv16.bin), [`02`](coherent-02-nv16.bin),
[`03`](coherent-03-nv16.bin), and [`04`](coherent-04-nv16.bin).
The [first frame preview](coherent-01-nv16.png) is full 640×480 NV16
conversion with no rotation or crop. All four decoded frames have wallpaper
RGB correlation about 0.998 with the earlier
[source-side screenshot](../2026-09-25-row-alignment/source-hdmi-output.png),
including valid bottom rows. The source was a mostly static desktop, so the
different CRCs primarily establish fresh writes, not motion fidelity.

`capture-once.py` now uses this verified reader by default. Its separate
end-to-end check returned one frame from pair 0 on the first attempt; see
[`capture-once.json`](capture-once.json). The bounded trials reported
`peripheral_restored=1` and `edid_mismatch=0` in the
[`ring`](ring-target.log) and [`burst`](burst-target.log) target logs;
the matching cleanup logs record DDC pin restoration. No kernel or firmware
was changed. This is still a **software-validated snapshot**, not a hardware
frame-completion interrupt or a V4L2 stream. A production capture interface
will need explicit buffer ownership, timing, and stream/restart behavior.
