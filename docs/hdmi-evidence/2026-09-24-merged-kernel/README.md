# HDMI diagnostics on the newer video-decode kernel

The isolated `codex/hdmi-capture` branch merged the committed
`h713-display-video-path` tip `ad3ffac` without editing its working tree. The
kernel patch series applies the three newer Cedrus/scanout-memory patches
before the existing HDMI clock, TVCAP, CPU_COMM, trace-page, and EDID-consumer
patches. Their filenames retain the original numbers from the two parallel
branches; the explicit `series` order is authoritative.

`JOBS=8 tools/build/build.sh kernel` applied the complete series and built
Linux 6.18.38. The resulting `build/out/h713-kernel.fit` has SHA256
`dee568ab30d33566b228e94f126c686afa9eafc83f6eb355a8dfca392777af80`.
Its kernel `.config` is byte-for-byte identical to the newer branch's latest
normal build. The bench DTB contains the newer VE scanout IOVA reservation
alongside the HDMI trace-page reservation, `allwinner,keep-tvcap-on`, and
the EDID clock consumer. HDMI power, EDID clock, DDC pins, SCP probe, and
THDMIRX initializer modules all rebuilt against this exact tree with
`6.18.38 SMP mod_unload aarch64` vermagic.

The FIT was staged at `/root/fits/h713-merged-video-hdmi-20260924.fit` and
verified there against the same SHA256. A one-time boot of that file reached
Linux 6.18.38 #1 built September 24 01:45:24 PDT. SSH returned; AFBD adopted
the panel, Cedrus registered `/dev/video0`, TVCAP remained on, and the checked
boot log had no Oops or panic. The board's installed `sunxi-cedrus.ko` had
exactly the same SHA256 as the module built from the merged tree:
`a731825e78e1b15a526c7dad9657e2c4a84b3a666af79de4828b9fc681eb000f`.
The rebuilt HDMI power and EDID clock modules loaded together, held both
domains active and the EDID clock at 24 MHz, and unloaded cleanly.

`tools/check-repo.sh` passed after refreshing the generated register index.
The board currently runs this merged image from the one-time boot. Its boot
FAT still contains the preceding default FIT (SHA256
`af3493288c4f0543be588e5fee7be968fd91150204c4e6c20246c1b3e1a06c2d`),
confirmed by a read-only mount. A normal reboot would return to that image
until the backed-up and read-back-verified default update is authorized and
performed.
