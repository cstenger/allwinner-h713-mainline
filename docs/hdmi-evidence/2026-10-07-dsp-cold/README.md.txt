# Cold Linux receiver and bounded DSP read, October 7

Booted the user's installed Linux 6.18.38 build dated October 7 18:57:16 PDT,
after a physical power cycle, guarded `mips-comm-trace 0x34` first launch and
verified source-3 transition at U-Boot. U-Boot, SPL, FIT and persistent
boot environment were not changed. The recent IR/standby/poweroff work remains.

Exact module build tree:
`build/linux-6.18.38-2a2ced73e505c450215680f0427646c1e7d6432ee82a314344022264b082af23`.
Staged newly built receiver power, EDID clock and DDC modules. The first EDID
probe built from this checkout generated a video-only 128-byte EDID; receiver
lock passed, but the tone was correctly refused by the canonical-hash guard.
`video-only-128-byte-edid.log` retains that failed audio precondition.

Rebuilt the canonical probe from the read-only HDMI checkout without editing
it, against the current kernel. SHA256
`0c41c7071c4606fc328fbc0d8ef2b52783af3dded199d1aad698ebedc5a3c0e0`.
The second 30-second stock-IO trial advertised the full 256-byte EDID, SHA256
`edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`.
The receiver locked 1280x720 with no pixel repeat; the active ELD selected
hw:0,8. An eight-second stereo 48-kHz S16_LE tone (L 1 kHz/R 2 kHz) completed.
Six tone samples cached N=6144 and CTS=74250, giving 48000 Hz at 74.25 MHz.
Other audio cache fields stayed zero; MIPS cache coherence limits remain.
DDC/SCP peripherals and SRAM restored with zero EDID mismatches.

Loaded exact-kernel stock-order TVFE hold and the established audio status
probe with init_audio_top and stock_audio_ihb. No SPDI, DMA or IRQ activation.
AudioTop control 0->700, config 0->011a5e00; IHB already 81000002.
The new DSP probe read status=0, user-owner=50 and kernel-owner=0.
Vendor libmspdriver's function at 1f0a4 accepts kernel ownership other than55,
claims user55 and rechecks kernel. libUtility at21400/21426 delegates to211c8;
02031078/02032078 take its literal /dev/mem fallback path, not a remapped
0614 window. Neither handshake address appeared as claimed in /proc/iomem;
current codec owns only02030000–0203032b and ALSA playback was closed.

First bounded raw DSP1 read of logical fff7 returned0000, status20. MIPS and
Linux remained responsive. This establishes command-port response only;
fff7=0 does not establish full DSP initialization or patch readiness.

Completion stays set after consuming the response. The first implementation
refused later commands on that sticky bit without issuing requests. The
revised probe requires a new request to show clear then set, each bounded.
It read selector0077=0000 with a fresh transition and restored user-owner50.
The next request0130 failed to observe clear within1ms, status20, and blocked
all subsequent requests. No0130 response was accepted. A fast completion
can evade that observation; this is inconclusive, not proof of DSP failure.
Ownership restored50, kernel-owner remained0. Final MIPS help win passed.

Tested revised DSP module SHA256:
`458a47bce5b615c1bf437c07a70fd22cc83668190bbade7d1f6b7cdc8029bed7`.
Host tested binary retained at /tmp/h713-dsp-current-modules/
h713-hdmi-dsp-probe-tested.ko; subsequent source formatting is cosmetic.
Kernel build and git diff --check passed. No PCM capture samples recovered.

At end of trial Linux is responsive with receiver/audio holds and the failed
DSP probe left loaded. DDC/SCP modules are gone and HPD is withdrawn. Physical
cold boot is required before another DSP command trial. Next boundary is a
completion check that handles sticky/fast completion without accepting stale
response, followed by stock DSP0/DSP1 version checks at logical80ff. Do not
infer patch readiness from fff7 alone or blindly replay the724-pair patch.
