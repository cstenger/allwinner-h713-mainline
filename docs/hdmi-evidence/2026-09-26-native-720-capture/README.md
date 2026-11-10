# Native 1280×720 receiver and read-only capture

This is the first native-resolution capture milestone. It proves the trial
EDID, receiver timing, ring geometry, and complete 1280×720 NV16 raster without
routing the result to the projector panel. It does **not** yet prove the V4L2
path, panel presentation, sustained 60 fps, or latency at this mode.

## EDID and receiver lock

`make-test-edid.py --mode 1280x720` produced the 128-byte EDID retained as
`edid.bin`, SHA256
`1bf44b2172fb4e512d8a575c58f2abbcfd96d2f2902bea5b8a7a323248fb9013`.
`edid-decode` reported a preferred 1280×720 progressive mode at 60.000 Hz,
45.000 kHz, and 74.25 MHz with positive sync and a valid checksum. The source
read that exact hash, exposed `1280x720` and `640x480`, and enabled output; see
`detection-source.json`.

During the signal window, every retained guarded MIPS port-cache sample
reported state 5, `hactive=1280`, `vactive=720`, and `pixel_repeat=0`. Before
and after the window it returned to the idle state. The complete samples are
in `detection-port-cache.json` and `capture-port-cache.json`.

## Ring layout and bounds

The safe AFBD current-address window continued to rotate through the existing
three Y and three UV addresses at 720p:

```text
Y:  0x4c3ef000  0x4c5ee000  0x4c7ed000
UV: 0x4c9ec000  0x4cbeb000  0x4cdea000
step: 0x1ff000
```

As at 640p, isolated reads sometimes crossed the Y/UV latch update and showed
a mixed pair; no single read is treated as authoritative. `pointer-trial.json`
and `capture-afbd-pairs.json` retain those observations.

A 1280×720 NV16 plane is `0xe1000` bytes. Each plane therefore ends
`0x11e000` bytes before the next slot. The last plane ends at `0x4cecb000`,
inside the established 26 MiB read-only carveout
`0x4bf41000..0x4d941000`, leaving `0xa76000` bytes to the carveout end. Thus
the six observed 720p planes neither overlap one another nor extend outside
the mapped firmware allocation.

## Full-raster marker capture

The bounded command was:

```text
python3 tools/hdmi/run-native-720-layout.py --frames 3
```

It generated a lossless 1280×720, 60 Hz marker source, temporarily installed
the checksum-verified 720p EDID probe, and read three predecessor ring pairs.
Each read copied one 1,843,200-byte NV16 frame bracketed by sparse plane hashes;
copy times were 21.7–23.0 ms. The marker analysis is the stronger integrity
check here: all three frames carried agreeing IDs in the visible upper,
middle, and lower bands, and every moving stripe matched its ID. There were
zero band or stripe mismatches. Frame IDs were 127, 137, and 141; skips are
expected from this diagnostic sampler and are not a delivery-rate result.

`frame-01.png` shows all 720 rows, a red marker at the first four columns, and
a cyan marker at the last four columns with no wrap, crop, or shifted stride.
The desktop top bar covers the deliberately unused first ID band; the other
three bands span the raster. Per-frame read metadata is in `coherent.json` and
the machine result is in `analysis.json`.

The retained source pattern SHA256 was
`14090043f827550d9c49926afd9104a6264f5b326f8c07f301fd4f86ad9062c2`.
The representative NV16 frame stayed outside Git; its SHA256 was
`4d48812164a45e0d841fb2689aa0d60d2ed9e1bdca72f3234c6f663d5e8f633f`.
The retained PNG SHA256 is
`1f539467cd5fa83f00768a1086a4e0e8750d70c54102eff910ec9a3b0e10acb7`.

Cleanup released HPD/DDC, returned the source connector to
disconnected/disabled, and restored the standard 640p probe module in `/tmp`.
No captured content was displayed on the projector during these tests.
