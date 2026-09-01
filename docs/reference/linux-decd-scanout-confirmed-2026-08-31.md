# Linux DECD scanout confirmed, 2026-08-31

Linux displayed the synthetic 1280x720 NV12 test frame correctly on the
projector panel.  The image had the expected single-frame geometry, full
colour, vertical colour fields, diagonal line, and checker pattern.  The boot
logo returned after the bounded test.  This closes the central question of the
DECD investigation: a frame submitted through the reconstructed Linux DECD
stack can reach the physical display.

The successful state was reached by combining the firmware-submitted frame
with six missing display-state corrections:

```
05600020  02CF04FF    source size, 1280x720 minus one
05600024  002C004F    source block size
05600040  00000500    Y stride, 1280 bytes
05600044  00000500    C stride, 1280 bytes
05600010  03000013    source 0 enabled, format 0
05600014  00000001    source 0 commit (consumed to zero)
05140508  144C0000    stock YUV chroma gain
051C006C  39000000    stock plane-1 downstream selector
```

The other source geometry words were already correct and were not changed:

```
05600030  02D00500
05600048  02D00500
0560004C  01680500
```

OSD1 was deliberately left at the Linux value `0x03001901`.  Therefore the
stock OSD1 control `0x83001900` is not required for DECD scanout.

## Controls leading to the result

The successful transfer was not a broad replay.  It followed a sequence of
bounded, reversible controls:

1. With the logo visible, changing only `0x051C006C` from `0x29000000` to
   `0x39000000` blanked the logo.  Restoring `0x29000000` restored it.  A DECD
   submit with only the stock selector remained blank.  The register is causal
   but not sufficient.
2. Setting the stock OSD1 control together with the stock selector did not
   produce a frame.
3. Setting source 0 to `0x03000013`, OSD1 to the stock control, and the selector
   to `0x39000000` produced a distorted, repeated, greyscale test image.
4. Repeating that test while leaving OSD1 unchanged produced the same class of
   visible image.  This isolated the minimum routing pair to source-0 enable
   plus `0x051C006C`.
5. A no-route preflight sampled the source registers one second after a live
   corrected-client submit.  They still held the inherited fallback state:

   ```
   05600020  043F077F    1920x1088 minus one
   05600024  00420077
   05600040  00000780    stride 1920
   05600044  00000780
   ```

   The DECD IRQ advanced `50196 -> 50495`, proving the frame service remained
   live.  This explains the repeated/banded photograph without appealing to a
   timing race: 1280x720 buffer content was being scanned with a 1920-byte
   source layout.
6. The final test corrected those four geometry words, applied the already
   calibrated chroma gain, committed source enable, and selected the stock
   downstream path.  Hardware consumed `0x05600014` to zero.  The active-state
   readback matched every value above, and IRQ 331 advanced from `58810` before
   the eight-second observation hold to `59467` after restoration.

The operator photographed the successful result as `IMG_0741.JPEG`: a single,
full-panel, full-colour rendering of `decd-test-frame.nv12`.  The previous
minimal-pair result, `IMG_0739.JPEG`, showed two horizontally repeated copies
and greyscale output, matching the fallback geometry and zero chroma gain.
The photographs remain operator-owned files outside this repository.

## Restoration

The test restored, in a shell trap as well as on the normal path:

```
051C006C  29000000
05600010  03000010
05600020  043F077F
05600024  00420077
05600040  00000780
05600044  00000780
05600014  00000001    consumed to zero
05140508  04000000
```

Every write read back, the client returned zero, and the logo reappeared.  The
transition is therefore reversible on this cold-boot display instance.

## What is proved, and what remains

Proved:

- the Linux DECD ABI reconstruction submits a valid NV12 frame;
- the MIPS display service fetches it and the panel can scan it out;
- format 0 is correct for this NV12 path;
- source geometry and strides must describe the real 1280x720 allocation;
- source enable and the plane-1 downstream selector are both load-bearing;
- `0x05140508[23:16] = 0x4c` restores the expected chroma;
- the stock OSD1 control is not part of the minimum video path.

Still to implement:

- move the four source-geometry values into the normal frame-programming path
  instead of post-submit MMIO writes;
- give one kernel owner responsibility for the source enable/commit, chroma
  gain, and plane-1 selector during video-plane transitions;
- restore the logo/OSD route when video stops without resetting the shared
  display block;
- validate production-rate playback and long-run fence cadence.

## Changing-frame cadence control

The first positive was followed by six separate submissions alternating the
solid NV12 files `decd-red.nv12` and `decd-green.nv12`, with an 800 ms dwell per
frame.  After each `FRAME_SUBMIT`, the same verified geometry and route were
applied.  All six submits returned zero and each returned fence fd 7.  DECD IRQ
331 advanced `82236 -> 82542` during the sequence.

The operator saw red and green alternate on the panel, then saw the logo return
after restoration.  This proves visible content can change across successive
Linux DECD submissions; the first result was not merely a one-time static
buffer coincidence.  It is a bounded cadence test, not yet a production-rate
or long-duration playback claim.

The guarded target-side reproduction is
[`../../tools/video/decd-visible-sequence.sh`](../../tools/video/decd-visible-sequence.sh).
It requires `ARMED=yes`, verifies the DECD-exclusive DT ownership and live MIPS,
snapshots every register it changes, and restores on all shell exit paths.

The temporary saved U-Boot `bootdelay=10` used to intercept cold boots also
still needs to be returned to `-1` during a planned U-Boot stop.
