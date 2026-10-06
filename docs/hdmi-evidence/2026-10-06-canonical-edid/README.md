# Canonical HDMI-input EDID

The HDMI input now has one canonical 256-byte EDID instead of separate 640x480
and 1280x720 test profiles.  It describes the complete capability currently
intended for production:

- preferred 1280x720p60 RGB;
- safe 640x480p59.94 fallback;
- HDMI identity and physical address 1.0.0.0;
- underscan and selectable RGB quantization;
- two-channel LPCM at 32, 44.1, and 48 kHz, 16-bit;
- front-left/front-right speaker allocation.

The generator is `tools/hdmi/make-test-edid.py`.  Its output SHA-256 is:

```text
edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34
```

`edid-decode 1.32.0 --check` reported `EDID conformity: PASS` with no warning
or failure.  Both 128-byte blocks have valid checksums.  The mode selector was
removed from `make-test-edid.py`, `make-edid-trial-code.py`, and
`build-scp-probe.py`, so normal builds cannot silently produce a specialty
EDID.

## Probe build

The canonical payload was regenerated into
`modules/scp-probe/edid-trial-code.h` and built against the installed
6.18.38 kernel.  The module identity was:

```text
SHA-256  198c441f5d8c850749b21996ae26ec4fc61619af13752e74a2547541b2681875
vermagic 6.18.38 SMP mod_unload aarch64
```

The panel harness's exact-EDID guard now requires the canonical hash.

## Source-side validation

The board's MIPS core was parked, so the test did not warm-reboot it or access
receiver/audio MMIO.  The removable TVFE/TVCAP hold was loaded with zero
receiver clocks, and the EDID clock/reset hold was loaded only for each
bounded SCP EDID/HPD window.

In two trials the GPU read all 256 bytes with the exact expected SHA-256 and
identified the display as `H713 HDMI IN`.  It enabled the preferred 1280x720
mode and exposed the 640x480 fallback.  The source output remained independent
of the two desktop monitors.

The GPU audio driver's ELD proved that the audio data belongs to this exact
sink rather than another attached monitor:

```text
monitor_name       H713 HDMI IN
connection_type    HDMI
speakers           FL/FR
sad_count          1
sad0_coding_type   LPCM
sad0_channels      2
sad0_rates         32000 44100 48000
sad0_bits          16
```

Each trial reported `peripheral_restored=Y`, `restored=Y`, and
`edid_mismatch=0`.  Afterward the DDC and SCP modules were absent, the temporary
EDID and power holds were removed, HDMI-A-1 returned to disconnected/disabled,
and the board was back in its original parked state.

This establishes a single valid video-and-audio EDID and source acceptance.
It does not yet prove that the H713 extracts or captures HDMI audio samples;
that is the next hardware gate.
