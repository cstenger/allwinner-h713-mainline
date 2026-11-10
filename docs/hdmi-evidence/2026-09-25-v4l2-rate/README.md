# HDMI V4L2 copy-cost trial

The three-pair firmware ring changes about every 17 ms, but the initial
V4L2 bridge delivered about 20 frames/s because it copied 614,400 bytes and
compared the entire source pair a second time. Per-stream kernel
counters separated ring detection, buffer availability, copy attempts, and
copy/verification time. The tests used the same 640×480 GPU desktop and a
bounded 20-second HDMI1/EDID window.

| Module mode | FFmpeg 100-frame time | Mean copy/verify | Ring events | Copies rejected | Frames delivered to V4L2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full comparison (default) | 5.51 s, about 19 fps | 20.2 ms | 165 | 48/149 | 101 |
| Sparse stability probes (opt-in) | 1.68 s, about 60 fps | 8.0 ms | 103 | 0/103 | 103 |

The [module counters](kernel-stream-counters.log) are the delivered `dmesg`
values, which can exceed
FFmpeg's requested 100 frames slightly at stream shutdown:

```text
full:   polls=326 pair_events=165 no_buffer=0 copies=149 unstable=48 delivered=101 hash_us=380338 copy_us=3016570
sparse: polls=116 pair_events=103 no_buffer=0 copies=103 unstable=0 delivered=103 hash_us=150729 copy_us=827907
```

Both [full](full-100-summary.json) and [sparse](sparse-100-summary.json)
100-frame raw streams had 100 distinct CRC32 values, no blank bottom rows,
and exactly 61,440,000 bytes. The [FFmpeg logs](full-100-ffmpeg.log) and
[sparse FFmpeg log](sparse-100-ffmpeg.log) record the rates. The
[last sparse frame](sparse-frame-100.png) visually retains the full desktop.
All 100 sparse luma frames had at least 0.9998 correlation with a full-mode
wallpaper frame outside the top menu bar. This static scene cannot establish
that sparse mode never tears during rapid motion.
The later [moving-pattern trial](../2026-09-25-motion-irq/README.md) checked
120 sparse frames for agreement at three heights and found no mixed IDs.

```sh
python3 tools/hdmi/capture-v4l2.py --frames 100 --seconds 20 --sparse-verify
```

This loads the removable module with `verify_full=0`. It still
checks four 4 KiB interior pages in each Y/UV plane before and after copying
the predecessor pair, but does **not** compare every source byte a second
time. It relies on the observed 0→1→2 writer order and roughly 34 ms before
that pair is reused. This is an experimental throughput option, not proof of
hardware completion or tear-free motion. The default command retains full
comparison.

A separate [30-frame default-mode regression](full-regression-summary.json)
passed after adding the mode switch. Its [target](full-regression-target.log)
and [cleanup](full-regression-cleanup.log) logs record HPD/DDC restoration.
The board was left with `verify_full=Y`, TVCAP active, and the temporary SCP
trial module removed.

The V4L2 node now reports the measured nominal 60 Hz source interval via
`VIDIOC_G_PARM` and `VIDIOC_ENUM_FRAMEINTERVALS`. `VIDIOC_S_PARM` returns
the fixed actual interval when a caller requests another rate; a
[30 fps request](fixed-interval-set.log) returned 60 fps. The
[device report](../2026-09-25-v4l2-capture/v4l2-ctl.txt) shows 60/1 fps,
and a [subsequent FFmpeg run](timing-ffmpeg.log) reports 60 fps and 60 tbr
instead of guessing from startup timestamps. Its
[30-frame output](timing-summary.json) remained complete and distinct, and
the [cleanup log](timing-cleanup.log) records the restored pins. The actual
rate in full verification was about 22 fps in that run; the advertised
interval describes the input signal, not a promise to deliver every frame.
