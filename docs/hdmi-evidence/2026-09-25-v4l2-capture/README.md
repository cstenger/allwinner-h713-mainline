# HDMI1 V4L2 capture on board B

The removable `h713-hdmi-v4l2` module exposes the firmware's HDMI1 frame
ring as `/dev/video1`. It advertises one input and one capture format:
640×480, NV16 (Y/UV 4:2:2), 614,400 bytes per frame. It reports the
observed 60 Hz input interval; delivery can be slower when frames fail
software verification. See
[`v4l2-ctl.txt`](v4l2-ctl.txt). This is a software bridge over the reserved
DRAM frame ring, not a receiver register driver or a hardware completion IRQ.

The module reads four interior pages in each of six planes to detect the
observed 0→1→2 writer order. When a new pair starts changing, it copies the
previous pair into a V4L2 buffer. Full Y and UV planes must compare equal
on a second read, and the sparse hashes must remain unchanged, before the
buffer is returned. A stream with no changing ring times out with an I/O
error after three seconds. The board-compatible check prevents loading on
other device trees. Loading the module does not touch HDMI registers or
change the installed kernel.

Build against the **running** board-B kernel's matching build tree. The
validated build used `6.18.38 #1 SMP Thu Sep 24 01:45:24 PDT 2026` and
Clang 22:

```sh
mkdir -p build/hdmi-v4l2
cp modules/hdmi-v4l2/{Makefile,h713-hdmi-v4l2.c} build/hdmi-v4l2/
make -C build/linux-6.18.38-951dd7e64a927e576a0f5a1dfdd4f66490460caa9cb17beb42a63983bb68ee4c \
  M="$PWD/build/hdmi-v4l2" ARCH=arm64 LLVM=1 W=1 modules
python3 tools/hdmi/capture-v4l2.py --frames 30 --seconds 20
```

The last command checks the exact running kernel, prepares source 3 if
needed, stages and reloads the module, enables HDMI1 for one bounded window,
records through FFmpeg with frame-rate passthrough, and saves a raw NV16
stream and first/last PNG previews under the printed `/tmp/h713-hdmi-trial-*`
directory. It restores HPD/DDC after the window. With the module already
built, the command is the repeatable capture entry point. The module is
removable and is not installed for automatic loading.

The end-to-end command captured **30/30 distinct frames** in 18,432,000
bytes, with no blank bottom rows. The [summary](v4l2-summary.json),
[FFmpeg log](v4l2-ffmpeg.log), [first](v4l2-frame-001.png) and
[last](v4l2-frame-030.png) frame previews are preserved here. The
[target log](target.log) reports `peripheral_restored=1` and
`edid_mismatch=0`; [cleanup](cleanup.log) records DDC restoration.

Earlier direct `v4l2-ctl` tests captured 12, then 100 consecutive frames,
followed by a fresh 20-frame stream after reopening the device. All 132
frames had distinct CRC32 values and valid bottom rows. The
[100-frame](h713-v4l2-long.log) and [restart](h713-v4l2-restart.log) logs
show contiguous sequence numbers. Typical delivered intervals were about
36 ms, with occasional intervals around 110 ms, so this software bridge
currently delivers roughly 20 frames/s rather than every source frame.
It reports capture-copy timestamps; it has no hardware frame timestamp.

Current scope: board B, HDMI1/source 3, fixed 640×480 NV16, and the
validated kernel build. HDMI audio, HDCP, mode changes, and hotplug are
outside this interface. Source-3 preparation still needs the existing
bootloader/MIPS path after a cold boot. The bounded HPD window and source
GPU remain necessary for a live stream.
