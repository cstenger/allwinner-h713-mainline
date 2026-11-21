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

## November 14 follow-ups from well0nez

Patches **0191–0197** integrate focused fixes reviewed from
[`well0nez/allwinner-h713-linux` at `149f51d0`](https://github.com/well0nez/allwinner-h713-linux/tree/149f51d0df24c45b12674c81aab128b1fc8f5d4b).
Each patch retains its author and records the exact source in `Link:`.
0195 is Pengpeng Hou's upstream V4L2 fix, backported through well0nez's
0330 with its original upstream attribution and trailers retained.

| Patch | Change |
| --- | --- |
| 0191 | Save only VP9 tx/skip probabilities, reducing the temporary to 15 bytes |
| 0192 | Clear HCI SIDDQ in Linux rather than relying on U-Boot USB initialization |
| 0193–0194 | Index PIO parent interrupts by IRQ-bank order, then list the seven actual bank IRQs |
| 0195 | Validate HEVC L0/L1 active counts in the V4L2 core; retain its missing-reference sentinel policy |
| 0196–0197 | Reject Cedrus HEVC references with invalid indices, missing buffers/MV allocations, or out-of-range collocated references before enabling the engine |

The core accepts missing-reference sentinels for other decoders' concealment
policies; Cedrus refuses a job it cannot safely execute. Buffer allocation is
not proof of a successful earlier decode. These guards prevent invalid
indexing and missing MV-buffer access; they do not add decoded-picture
provenance tracking or general damaged-stream recovery.

The pinctrl patch omits well0nez 0143's separate comment change because our
0171 already corrected that comment and the IRQ mux. The V4L2 core diff was
regenerated for 6.18.38, without the newer HEVC extended-SPS context.

Run the source-bound host checks after building the selected kernel and DTBs:

```sh
python3 tools/video/test-kernel-followups.py \
  --kernel "$(tools/build/build.sh kernel-tree)" -v
```

Use the same `H713_BUILD_DIR` and `KERNEL_CONFIG` as the build. The tests use
ASan/UBSan for extracted real HEVC/VP9 helpers, exercise boundary and invalid
inputs, check four deliberate regressions are caught, and inspect both
compiled DTBs. They do not validate hardware decode or interrupt/PHY delivery.

See [the integration results](../../docs/reviews/well0nez-2026-11-14/integration.md)
for build provenance, checks, and remaining board tests.

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
PL10 for 10-bit AV1 sequences. Consumers: libva-v4l2-request 0017 (and,
until it was deleted on 2026-10-05 under the stock-GStreamer-only rule,
`patches/gstreamer/0003`). 0149 also lets the plane take a framebuffer larger
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

## CPU_COMM interrupt follow-ups (November 14, 2026)

**0198** adapts well0nez's stock-DT correction: CPU_COMM interrupt banks are
SPI 46/109/108 in ARM/ARISC/MIPS order; watchdog is SPI 53. The register
window remains 0x1000. Only DT index 0 belongs to this driver's RX endpoint;
registering remote inbox lines can cause storms and steal ownership.

**0199** retains our sleepable, ONESHOT threaded handler. It masks only the
MIPS-to-ARM RX bit, drains in the thread, acknowledges that endpoint, and
re-enables it without clearing other endpoints or TX status. IRQ reception
remains opt-in with `rx_irq=true`; successful registration starts no polling timer. Explicit
`rx_irq=false`, missing IRQ or registration failure selects polling.
The attempted IRQ qualification failed concurrent/repeat testing, so the
known polling path remains the default. Read-only module parameters `rx_irq_active`, `rx_poll_active`,
`rx_messages_irq` and `rx_messages_poll` make fallback use observable.

This pair requires deploying both the corrected FIT/DTB and matching
`hy310-cpu-comm.ko`; a FIT-only change leaves the old polling driver active.
The guarded bundle builder/installer support the exact DT change and
baseline-reproduced CPU_COMM module in one backup/rollback transaction.
[Validation and bench results](../../docs/reviews/well0nez-2026-11-14/cpu-comm-irqs.md).

**0200** fixes shared-memory ownership and bounds defects uncovered before
retrying IRQ reception: packed counters are claimed under a spinlock,
peer references cannot escape the reserved mapping, slot index 20 is
rejected, ACKs bind to the pending ARM session, and RETURN acknowledges
before waking/recycling. The active-wait list lock excludes timeout cleanup
while completion is in progress; opaque sender metadata retains all 64 bits.
See [handoff regressions and board qualification](../../docs/reviews/well0nez-2026-11-14/cpu-comm-handoff.md).

**0201** preserves a peer-owned send publication after CALL_ACK timeout and
quarantines further sends with `-EPIPE` until clean firmware/driver startup.
Queued callers and a pre-existing SENT publication are checked under the
send semaphore. `tx_desynced` exposes the MIPS quarantine read-only.
The matched polling/IRQ stall is associated with synchronous firmware
UART log flushing; a timeout must not be treated as peer cancellation.

**0202** corrects the firmware's shared spinlock ABI: byte 0 gates entry,
byte 1 holds software ownership and byte 2 controls recursion policy.
Hardware timeout never permits forced entry. Per-thread ownership and
release ordering prevent ARM from corrupting a MIPS-held lock record.
Source-derived peer-contention tests reproduce the old firmware assertion
condition and validate the corrected arbitration.

**0203** adds raw PC/LR/SP/ESR and initial argument registers to the first
fatal arm64 fault record. The DDR3 IRQ fault repeatedly stopped reporting
before the normal Oops register dump. This is diagnostic reporting only;
IRQ corruption remains unresolved and IRQ reception remains default-off.

**0204** adds an opt-in `arena_witness=1` diagnostic for the DDR3 bench.
References the peer sees for the two driver-private arenas name a
poison-filled window in the grown `hdmi-trace@4d980000` no-map
reservation (256 KiB, first 4 KiB trace page kept). ARM still decodes them
to the real local objects, and `arena_witness_status` reports any changed
word. A build-time check requires both real arenas (9984-byte socket pair,
119648-byte device state) plus guard pages to fit. A first 128 KiB version
with a 64 KiB per-arena cap could not hold the device state and failed probe
with -ENOSPC on hardware; its host test had used toy-sized arenas. This is
a diagnostic, not a fix; IRQ reception remains default-off.

**0205** makes ARM-inbox RX by IRQ the default (`rx_irq=1`; `rx_irq=0`
still polls). The IRQ-mode corruption that kept 0199 opt-in came from U-Boot's
k0/k1 comm-trace markers (fixed by U-Boot 0006), not from this driver. With
0006, IRQ-only reception passed 6003 calls per boot on a warm and a cold boot
(12006 IRQ RX, no polling, no fault). The driver refuses IRQ mode and polls
whenever the firmware patch cave (0x4b100300..0x4b100c1f) still holds a
pre-0006 `lui k0` marker or cannot be mapped, so a mismatched bootloader
cannot reintroduce the corruption.

**0206** adapts well0nez's 0313 eMMC read-block threshold. Only the H713
eMMC configuration opts in: HS200/HS400 reads of 1–512 bytes enable the
threshold, while writes and other timings clear it, preserving unrelated
register bits. Other sunxi eMMC controllers and the H713 v5p3x SDIO path
retain their existing behavior. This does not add 0312's controller-reset
recovery. `tools/storage/test-emmc-threshold.py` exercises the actual
prepared helpers under ASan/UBSan, including transitions and device scope.

**0207** adapts well0nez's 0312 reset-before-CMD12 approach only for H713
eMMC CMD18 read errors. Reset, host initialization, IDMA reset completion
and clock restoration must all succeed before CMD12. Restore/stop failure
latches a terminal error independent of `set_ios`; later requests fail
before DMA mapping or MMIO until reprobe/reboot. The original request is
completed once after clearing its pending-stop ownership. CMD17, writes,
CMD53 and other controllers retain their prior recovery paths. The stop
helper now returns its result without changing the legacy callers' behavior;
its CMD53 argument uses an unsigned high-bit shift. See the
[recovery verification](../../docs/reviews/well0nez-2026-11-14/emmc-recovery.md)
for host failure tests, mutation checks and natural full-FIFO hardware errors.

**0208** reserves ARM → MIPS msgbox FIFO room before a CPU_COMM message is
published. The doorbell runs under one lock: the driver is the FIFO's only
writer, so a count below eight under the lock reserves the word, and the
shared header and its SENT flag are written only after that. With no room
within 100 ms the send returns `-EBUSY` with shared memory untouched
(`tx_fifo_full` counts refusals). The lock also keeps concurrent senders'
data writes and TX_IRQ_EN pulses from interleaving; the pulse itself is
unchanged. `SendComm2CPUEx` now propagates the send result, clearing the
pending ACK, releasing the unpublished wait object and keeping the
unpublished slot cached; a failed `copy_to_user` no longer leaks its wait.
`SendAckLow` returns an error and quarantines instead of `BUG()` on a
still-published ACK, and a late RETURN is recycled only after its ACK is
published. The FIFO depth check follows well0nez's 0014f.
`tools/mips/test-cpu-comm-tx.py` tests the actual prepared functions
(`--mutations`, `--baseline`); see the
[TX record](../../docs/reviews/well0nez-2026-11-14/cpu-comm-tx.md).

**0209** stops pulsing TX_IRQ_EN after each ARM → MIPS doorbell word. The
firmware arms its own RX interrupt for our FIFO (`0x03003820` BIT(2)) when
it registers its channel and never handles the TX-room interrupt the pulse
enabled. A protocol-free probe drained 20/20 no-pulse words (median 36 µs);
see the [doorbell record](../../docs/reviews/well0nez-2026-11-14/cpu-comm-doorbell.md).
The data write is now the whole doorbell, which also removes a 10 µs
busy-wait under `msgbox_tx_lock`. It also narrows `known_regs[]` to the two
share registers its callers use: well0nez's 0014e found the transcription
error, but the hwspinlock words belong to the sun6i hwspinlock driver and are
not carried. `tools/mips/test-cpu-comm-tx.py` now fails any TX_IRQ_EN write
and cross-checks the whitelist against every accessor caller.

**0210** resets the cedrus decode engine when a job's codec differs from the
previous job's. VP9 leaves state in the H.265 engine, so concurrent
VP9+H.265 decoding failed every H.265 job's setup (well0nez's 0298 finding).
Their fix pulses `RST_BUS_VE`, which on the H713 also gates the AV1 core's
bus. This patch pulses only `RST_BUS_VE3`, the decode engine's own reset,
which AV1 does not use, and only where that reset exists. A diagnostic build
made all VP9+H.265 pairs bit-exact, and AV1 decoded 40/40 bit-exact beside
5064 such pulses. See the
[decoder-reset record](../../docs/reviews/well0nez-2026-11-14/decoder-reset.md);
`tools/video/test-cedrus-codec-switch-reset.py --mutations` checks the
helper and its placement.

**0211** marks the `nsi@2020000` node disabled. well0nez noticed it cannot
bind: its compatible matches neither string in 0011's sunxi-nsi driver, which
is also off in our defconfig. The compatible is deliberately not fixed, because
that driver's probe resets the live bus QoS controller and programs
unverified registers. Both compiled board DTBs differ only in that node's
`status`; there is no runtime change.

**0212** makes the H713 speaker one power state instead of per-stream. Every
close of the playback PCM popped: `sun4i_codec_shutdown()` stopped the module
clock microseconds after trigger STOP dropped PA, while the amplifier was still
winding down. A microphone measurement found close-only pops at 0–10 ms between
the two, faint at 30 ms with the fan off, and silence from 100 ms
([evidence](../../docs/speaker-pop-evidence/2026-11-17/README.md)).
Power-up: clock on, the DAC → headphone-amp → line-out path forced on in DAPM,
700 ms, then PA. Power-down: PA off, 300 ms, then path and clock. Streams no
longer touch PA or stop the clock, and a rate-family change takes PA down
around `clk_set_rate()`. The "Speaker Power" card control (default on) is
how `h713-standby` takes it down and up; suspend, shutdown and removal take it
down. It replaces the per-stream PA gate of 0180/0181. Host test:
`tools/audio/test-speaker-power.py <tree>/sound/soc/sunxi/sun4i-codec.c --mutations`;
see [the speaker power plan](../../docs/speaker-power-plan.md).

**0213** corrects the `motor_ctr` description: the stepper is the HY310's
focus motor, not a keystone motor (well0nez's 0024b finding). Only the
comment changes; the driver and compatible keep the `hy310-keystone-motor`
name, and both board DTBs are byte-identical.

**0214** disables `motor_ctr` in the SoC dtsi. Not every H713 projector has
the focus motor (the HY200_QZ713_V2 projector here does not), but only the
bench board overrode the node, so the projector DTB described a motor. A board
with the motor enables it in its own .dts. The bench DTB is unchanged; the
driver is not built in our configs, so this corrects the description only.

**0215** makes the projector's one USB-A port (port 0) dual-role: musb is
enabled with `dr_mode = "otg"` on V2 only. The port has no ID pin or VBUS
sense, so the PHY polls nothing and the role changes only through musb's
`mode` attribute, which `h713-usb` writes (`tools/usb/h713-usb`). It also adds
the `usbdev` reboot-mode magic (`0x05bdb007`), which boot.scr turns into
`h713.usb=device` for one boot. The defconfig gains the configfs NCM and ACM
gadget functions. The bench DTB is unchanged.

**0216** fixes sunxi's musb glue dropping a mode change written while the
controller is disabled (no gadget bound). `echo host > mode` returned success,
but the PHY stayed in peripheral and the port stayed routed to musb. The work
now applies a pending `phy_set_mode()` in that case too. Found on the
projector.

`series` files may carry `#` comments and blank lines; `tools/build/build.sh`
reads every series through `series_entries`, so hashing and applying see the
same list.
