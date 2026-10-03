# H713 kernel patches

The H713 has no mainline kernel support yet, so the kernel is carried as a
**patch series applied to a pinned mainline tarball** (see
`config/versions.env` → `KERNEL_VERSION`), rather than a fork. `tools/build/build.sh
kernel` fetches `linux-$KERNEL_VERSION`, applies these in `series` order with
`patch -p1`, then builds with `board/hy200_qz713df_a1_defconfig`.

## Provenance

Patches **0001–0022** are the H713 driver series by **well0nez**
(`github`/ `local/allwinner-h713-linux`), **GPL-2.0**, carried here **with
attribution**. They are architecture-neutral (only `drivers/` and
`include/dt-bindings/`, no `arch/`), which is why the same series that backed
the 32-bit port also builds on arm64. Six were adapted from their original
6.16 form to apply/build against the pinned kernel — see the table in
[../../docs/kernel-bump.md](../../docs/kernel-bump.md); the rest are unchanged.

| # | Area |
|---|------|
| 0001 | clk: sunxi-ng H713 CCU driver |
| 0002–0004, 0018 | pinctrl: H713 PIO / R-PIO / irq-mux / PB bank |
| 0005 | phy: sun4i-usb H713 PMU bit0 quirk |
| 0006 | mmc: sunxi H713 (v5p3x) |
| 0007 | pwm: sun8i 8-channel |
| 0008–0009 | misc: HY310 board-mgr / keystone-motor |
| 0011–0014 | misc/soc: nsi, tvtop, decd, cpu-comm IPC |
| 0015–0016 | H713 driver Kconfig + clock/reset dt-binding IDs |
| 0017 | iommu: sun50i decouple ARM_DMA_USE_IOMMU |
| 0019 | iio-adc: H713 LRADC |
| 0020 | pmdomain: H713 PPU |
| 0021 | media: sunxi-cir H713 vendor init |
| 0022 | staging: cedrus H713 VE3 clock/reset |

## Our arm64 additions

- **`board/hy200_qz713df_a1_defconfig`** — the bench arm64 defconfig (base
  arm64 defconfig slimmed, plus the SoC-general H713 drivers + PPU/LRADC/R-CCU).
  Projector-only vendor drivers (`board-mgr`, keystone motor, `tvtop`, `decd`)
  are deliberately disabled here; they need a separate, hardware-tested
  projector configuration. **`cpu-comm` was enabled 2026-08-30** (`=m`, plus
  `&cpu_comm { status = "okay" }` in the board DTS) so the display firmware's
  RPC surface is reachable from Linux — the runtime source/composition/resume
  calls that exist only over this transport. (It is *not* needed for the
  suppression routines; those were cleared at the U-Boot prompt and carried
  across the handoff on 2026-08-30, and the panel did not change.) Its
  msgbox transport now matches what U-Boot has round-tripped on hardware, and
  the vendor 32-bit shared-pointer ABI above it is ported to arm64 (see the
  `cc_ref` block in `cpu_comm.h`). **It probes on hardware** (2026-08-30): clean
  bind, both chardevs, 18/18 VP routes, no WARN across ~120 `cc_ref()` calls,
  and the shared encoding reproduces ring addresses U-Boot recorded
  independently from the firmware's side. **No message has been exchanged
  yet** — the MIPS is parked, so the doorbell and the tagged-local half of the
  encoding are still unexercised. Console evidence in
  [../../docs/reference/cpu-comm-linux-probe-2026-08-30.txt](../../docs/reference/cpu-comm-linux-probe-2026-08-30.txt);
  background in [../../docs/handoff-2026-08-30.md](../../docs/handoff-2026-08-30.md).
  Copied into
  `arch/arm64/configs/` by the build. It also **disables the Crypto Engine**
  (`# CONFIG_CRYPTO_DEV_SUN8I_CE is not set`, `HW_RANDOM` off): mainline
  `sun8i-ce` cannot drive the H713 CE — see the crypto note below and the
  roadmap. *(ours)*
- **0023 — R-CCU on arm64** — upstream gates `SUN20I_D1_R_CCU` to
  `MACH_SUN8I || RISCV || COMPILE_TEST`; the H713 reuses the D1 R-CCU, so this
  adds `|| ARM64` to that `depends` (without it R-PIO / PPU power domains never
  probe). A proper patch, anchored to the `SUN20I_D1_R_CCU` block so it does not
  also touch `SUN20I_D1_CCU`. *(ours)*

- **0024 — arm64 SoC + board devicetrees.** The reconstructed vendor tree is
  split into shared `sun50i-h713.dtsi`, a clean
  `sun50i-h713-hy200-qz713df-a1.dts` bench overlay that disables projector-only
  hardware, and `sun50i-h713-hy200-qz713-v2.dts` for the projector. Both DTBs
  have Makefile entries. Arm64 changes include `arm,armv8-timer` and a
  `secure-bl31@40000000` reservation so Linux leaves TF-A BL31 alone. The
  projector definition is structural only and remains untested on hardware.
  *(ours, reconstructed from well0nez's GPL-2.0 DTS with attribution)*

- **0025 — safe CPU clock transitions.** Registers the CPUX mux and PLL
  notifiers used by cpufreq. CPUX temporarily switches to the 24 MHz oscillator
  while PLL_CPUX is reprogrammed, and the notifier enables the H713 PLL lock
  detector with `LOCK_ENABLE` (BIT 29). *(ours, hardware verified)*

- **0026 — CPU cpufreq foundation.** Adds the shared initial OPP table from 480
  to 1008 MHz and binds it to all four Cortex-A53s, providing the cooling device
  required by the 75/85 C passive trips. Patch 0028 upgrades this table to full
  voltage scaling. *(ours, hardware verified)*

- **0027 — H713 R-PWM clocks.** Exports the recovered R-PWM functional mux/gate
  at R-CCU offset `0x130`, plus its bus gate and reset at `0x13c`. Both clocks
  are required for the PL7 VDD-CPU PWM output. *(ours, hardware verified)*

- **0028 — voltage-scaling CPU DVFS.** Models VDD-CPU as the stock R-PWM
  channel 1 / PL7 regulator and extends the default-bin OPP table from 480 MHz
  at 0.90 V through 1416 MHz at 1.10 V. DMM measurements validate the complete
  PWM transfer direction and representative low/mid/high voltage points; all
  transitions, the thermal bindings, and a two-minute four-core peak load are
  hardware verified. *(ours, hardware verified)*

- **0030 — fix fan-power gpio-hog cell count.** The bench cooling fan is a
  3-wire (VCC/GND/tach) on/off fan, not a PWM-speed part, and it never spun
  because its +V rail was never enabled: the `fan_power_hog` for PB5 (the shared
  backlight/fan power enable) used `gpios = <37 ...>` — a linear GPIO number on a
  `#gpio-cells = <3>` sunxi controller, which gpiolib can't parse, so the hog was
  silently skipped (`/sys/kernel/debug/gpio` showed zero claimed lines on
  gpiochip0). Corrects it to the 3-cell `<1 5 GPIO_ACTIVE_HIGH>` (bank B, pin 5),
  which also restores the projector's shared backlight-enable rail. Supersedes an
  earlier `pwm-fan`-on-PWM0 attempt: PWM0/PH17 was verified emitting on real
  silicon (debugfs register read-back + pinmux), which *did* validate the
  corrected main-PWM map (0007), but PH17 is the fan's tachometer, not a control
  line, so PWM drive does nothing to a 3-wire motor. `pwm-fan`, its `&pwm` mux,
  and `CONFIG_HWMON`/`CONFIG_SENSORS_PWM_FAN` are dropped. **Bench-confirmed: the
  fan spins**, and it (plus the LED backlight) now comes up at power-on from
  U-Boot — `board_init` drives the shared PB5 enable, so the panel is lit and
  cooled from reset with the fan a hard interlock. Backlight *brightness* is
  handled separately by 0032. *(ours, hardware-confirmed)*

- **0032 — pwm-backlight on PWM2/PB4.** Wires the panel dimmer the mainline way
  so brightness is controllable from `/sys/class/backlight`. An earlier note
  said "PB4/PWM2 changed nothing, don't re-attempt," but the captured stock DTB
  (`panel_pwm_ch = 2`, 25 kHz, `panel_backlight = 75` on 0..100), stock fastlogo
  (`pwm_request(2, "fastlogo")`), and the vendor Linux backlight driver all agree
  PB4/PWM2 **is** the dimmer. The likely reason the bench poke did nothing: this
  is a serially-programmed LED panel whose PWM-dim path is enabled by fastlogo's
  panel SPI init, which never runs on mainline — so the un-initialized panel
  ignores PB4. The node uses `<&pwm 2 40000 0>` (25 kHz, normal polarity per
  stock), a linear 0..100 brightness scale (default 75), and `&pwm2_pins`; it
  carries **no** `enable-gpios`, because PB5 (`panel_bl_en`) is shared with fan
  power and stays held high by `fan_power_hog` — this node varies PWM duty only.
  Bench-tested 2026-07-24: `/sys/kernel/debug/pwm` shows ch2 driving the correct
  duty (0/20000/40000 ns for brightness 0/50/100, `actual` == `requested`) with
  PB4 muxed to `pwm2`, but the panel's light does not change — so brightness is
  gated on the panel-side init that fastlogo runs before Linux (Phase-4 MIPS
  display work), not on this node. Kept as the correct foundation; dimming will
  work through it unchanged once the panel init lands.
  *(ours, hardware-tested — PWM correct, panel-init gate confirmed)*

The Crypto Engine device (`ce@3040000`) stays in 0024's device tree as an
H6-compatible node (`allwinner,sun50i-h6-crypto`, three clocks) but is **not
driven**: mainline `sun8i-ce` cannot run it, proven on the bench (2026-07-23).
Enabling the driver registers every algorithm, then each fails its boot-time
known-answer self-test. Wiring the stock CE's second interrupt (SPI 74) *does*
fix task completion, but the engine then rejects the task descriptors mainline
builds — ciphers report `address invalid`, hashes `algorithm not supported` for
standard AES/SHA, which only happens when the CE reads bogus algorithm IDs and
addresses out of the descriptor. So the H713 uses a different descriptor
**format** (the stock two-register-bank / two-IRQ block), not a different IRQ or
byte-vs-word addressing, and there is no CE TRNG. Re-enabling would require
descriptor-level RE of the vendor `allwinner,sunxi-ce` driver (source
unavailable) for no benefit — the A53's ARMv8 AES/SHA already outrun it. See the
roadmap and `docs/status.md`.

With these patches in place `tools/build/build.sh kernel` emits both DTBs and a bench-only
bootable FIT (`build/out/h713-kernel.fit`: gzip Image + bench DTB, load/entry
`0x48000000`).

## Debug kernels (`board/*.config`)

`KERNEL_CONFIG=name[,name…] tools/build/build.sh kernel` merges
`board/<name>.config` over the board defconfig. This is for **diagnostics
only** — the shipping kernel is the defconfig alone.

| fragment | for |
|---|---|
| `kasan.config` | generic KASAN + `MAGIC_SYSRQ`, hunting the kernel memory corruption behind the mpv-on-panel crash (`docs/vaapi-scope.md`) |

Two properties are deliberate and worth not breaking. Fragments are part of the
**input digest**, so a debug build gets its own source tree rather than quietly
reusing the production tree's objects; and outputs are **suffixed**
(`h713-kernel-kasan.fit`), so a debug build cannot overwrite the FIT the board
boots from. The build also verifies the config that was *built* rather than the
one that was requested — `merge_config` warns about a request it cannot honour,
but `olddefconfig` can drop a symbol afterwards for an unmet dependency and say
nothing, and a KASAN kernel that silently did not enable KASAN is worse than no
kernel, because every clean run after it reads as evidence.

## H713 decoder scaling (0120)

H.264 and HEVC use the shared VE+0xf00 polyphase scaler, with arbitrary even
NV12 dimensions from 1× to 4× downscale per axis through CAPTURE S_FMT or
COMPOSE. Rotation is no longer exposed. Patch 0116a repairs prerequisites
missing from the previous series; 0118 has a corrected blank context line.
See [the shared-scaler handoff](../../docs/handoff-2026-09-17-shared-scaler.md)
for the H.264 route, HEVC alignment requirement, and board validation.

`cedrus_can_scale()` admits H.264 and HEVC only, and **MPEG-2 is left out on
purpose**. Not because the hardware cannot — `libawmpeg2.so` exports
`Mpeg2ComputeScaleRatio` and `Mpeg2SetRotateScaleBuf`, so the vendor does scale
it — but because that is the fixratio path. `Mpeg2ComputeScaleRatio` is
byte-identical to `H264ComputeScaleRatio` (all 40 bytes), which returns
half or quarter and nothing else, so it cannot produce the 1.5× this 1280x720
panel needs; and the polyphase route has no MPEG-2 vendor precedent to port.
Reasoning and reopen conditions in
[the inherited-codecs record](../../docs/reference/inherited-codecs-2026-09-17.md).

**0121** supplies a supported HEVC SPS default and moves bit-depth/format
changes from TRY to the control commit callback. Cedrus compliance is now
**49/49, zero warnings**. See [the control validation record](../../docs/reference/cedrus-controls-2026-09-17/README.md).

## 10-bit AV1 to the video plane (0150, 0149, 0147; EXPERIMENT)

**0150** (local, not upstreamed; placed before 0145 in `series`) names the
H713 AV1 core's 10-bit output, which is P010's layout with the samples in bits
9:0: `DRM_FORMAT_MOD_ALLWINNER_LSB10` (`fourcc_mod_code(ALLWINNER, 2)`, valid
with P010/P210) and `V4L2_PIX_FMT_P010_LSB` (`'PL10'`), with the V4L2
format-info entry, the ENUM_FMT description and a hantro bit depth of 10.
**0149** makes the AFBD video plane pick its format byte from the framebuffer
(NV12 0, P010 6, P010 + LSB10 7) and advertise `IN_FORMATS`; **0147** offers
PL10 for 10-bit AV1 sequences. Consumers: libva-v4l2-request 0017 and
`patches/gstreamer/0003`. 0149 also lets the plane take a framebuffer larger
than the 1280x720 picture (hantro's 768-line padding, as GStreamer describes
it), which kmssink needs for any hantro stream. Hardware-verified 2026-10-01.

## DMA-BUF capture (0151 + defconfig, 2026-10-01)

The VA driver allocates decoder capture memory from `/dev/dma_heap/system`
(libva-v4l2-request 0018/0019), so the defconfig now builds
`CONFIG_DMABUF_HEAPS`, `_SYSTEM` and `_CMA` (the CMA heap for diagnostics
only). The system heap is the right one: the VE, the AV1 core and the display
are all IOMMU masters, so scattered pages are contiguous in each device's
address space, and heap buffers were shown on the panel in NV12, P010 and
P010 + LSB10 before the VA driver used them
(`ALLOC=heap tools/display/kms-p010-plane-test.c`).

**0151** sets `bidirectional` on cedrus's capture queue. vb2 maps an imported
dma-buf in the queue's direction, `DMA_FROM_DEVICE` for CAPTURE, and the H713
IOMMU enforces it: the page is write-only, and the first inter frame faults
reading its reference (`Page fault ... master 1, dir rd`, then a timeout).
MMAP buffers never showed it because `dma_alloc` maps read-write. hantro and
rkvdec already set the flag for the same reason, which is why AV1 passed with
DMABUF capture while VP9 on cedrus failed at frame 1.

## GPU clock and DVFS (0152, 0153 + defconfig, 2026-10-02)

WP1 of [the GPU fallback plan](../../docs/gpu-fallback-plan.md).

**0152** fixes the GPU's clock model. PLL_GPU's bit 0 is an output divide-by-two
(the H616 models it as `.p`), and it is set at reset. So the GPU ran at
**432 MHz** while `clk_summary` said 864. The GPU module clock's 2-bit M
divider at `0x670[1:0]` is now modelled; it was measured real at /1, /2 and /4.

**0153** pins PLL_GPU at 600 MHz, stock's value in every CCU capture, and adds
the OPPs stock lists for this die: 150/200/300/600 MHz, which are 600 / M.
Every point is 960 mV, the fixed vdd_sys. A DVFS step changes only M, so the
PLL never relocks. It also gives `gpu-thermal` trips at 85 C (passive, onto
the GPU's devfreq cooling device) and 105 C (critical).

The defconfig adds `CONFIG_DEVFREQ_THERMAL`. That changes `panfrost.ko`, so
deploying needs the module as well as the FIT.

## Stock mpv on the GPU path (0092 in series, 0154, 2026-10-02)

WP2 of [the GPU fallback plan](../../docs/gpu-fallback-plan.md).

**0092 is now in `series`.** Stock mpv's DRM context looks for VA-API's render
node on the *display* device. Without one it logs "Could not create a VA
display" and decodes in software, with no error at the default log level. Every
stock-mpv zero-copy result since 2026-09-03 was measured on a kernel carrying
0092 out of series. On the 0153 kernel, which lacked it, stock
`--vo=gpu --hwdec=vaapi` ran with `hwdec=no` and zero VE interrupts.

With 0092 the GL renderer is still Mali-G31 (Panfrost), so Mesa's kmsro pairing
survives. The nodes renumber: the display gets `renderD128` and Panfrost moves
to `renderD129`. The patch still advertises a capability the display hardware
does not have; the alternatives are an mpv patch or a Wayland compositor.

**0154** derives the VP9 reference-pitch field (`LAST_SCALE1 [30:28]`, log2 of
alignment / 8) from the capture pitch instead of hard-coding the vendor's 16.
- It is needed by libva-v4l2-request 0020, which asks for 64-aligned pitches so
  Panfrost can import the frames.
- It also fixes a bug that predates 0020: stock GStreamer `v4l2slvp9dec` at
  330 wide was 1/30 frames bit-exact, and is 30/30 with 0154.

## VA driver switch to megi's libva-v4l2_request (0155, 2026-10-03)

WP3 of [the GPU fallback plan](../../docs/gpu-fallback-plan.md); the VA driver
itself is [`../libva-v4l2_request/`](../libva-v4l2_request/README.md).

**0155** makes cedrus refuse VP9 profiles other than 0 in `try_ctrl`. Before
it, the VP9 frame control had no `cedrus_ctrl_ops`, so a 10-bit Profile 2 frame
was accepted and failed only at job setup (`-22`, every frame). megi's driver
probes exactly that refusal to decide whether to advertise
`VAProfileVP9Profile2`. Without 0155, ffmpeg picks VA-API for a Profile 2
stream and decodes nothing instead of falling back to software. cedrus is a
module, so deploy with `tools/install-kernel-module.sh`.

## Retired: display-side scaling (2026-09-23)

Six patches left `series` — **0098, 0103, 0105, 0106, 0108, 0111** — and the
series is 85 entries. They gave the video plane the proc upscaler at
`0x05180000`, so a decoded picture smaller than the panel could be magnified
onto it. That was stage 2 of the composite route (VE power-of-two down to
960x544, proc back up to 1280x720) and **0120 superseded it**: the VE's
polyphase scaler produces arbitrary even sizes, so the decoder lands on
1280x720 exactly and there is nothing left for the display to scale.

The retirement is not merely tidying. Nothing in the shipping stack could still
reach that path — mpv's `vo_drm` refuses any source size that differs from the
mode, `vd_lavc` only ever asks the decoder to shrink, and 0106 required a
panel-sized framebuffer, which a sub-panel decode does not produce. The plane
is back to one framebuffer geometry and one source rectangle.

What it costs is the *latent* ability to upscale with no GPU — 480p on this
720p panel — because the VE scales down only. That is the reopen condition;
the six are a chain and come back together. Each carries a header saying so,
and the full argument is in
[the retirement handoff](../../docs/handoff-2026-09-23-retire-display-scaling.md).

The afbd DT node drops back to three `reg` ranges, and the driver is built in
(`CONFIG_DRM_SUN50I_H713_AFBD=y`), so deploying this needs a FIT flash and a
cold boot — a module swap cannot carry it.
