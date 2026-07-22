# Roadmap

Where the project goes after the foundation (open boot chain + Debian 6.18.38 +
standalone boot, all hardware-verified on the bench). Ordered by dependency, not
just priority. See [status.md](status.md) for what already works.

## Guiding constraints

- **Bench (`HY200_QZ713DF_A1`, DDR3) is the safe dev board.** The projector
  (`HY200_QZ713_V2`, LPDDR3) lives inside a projector and is untested — bring it
  up carefully, FEL-first, brick-avoidance paramount.
- **The kernel is a patch series, and that's its home by design.**
  `patches/kernel/` applied to a pinned mainline tarball is deliberate (the tree
  is too big to fork, and this keeps our delta reviewable + rebasable). Driver
  work = edit the series + `build/build.sh kernel`. No "kernel fork" is needed;
  what *is* worth adding is a hackable persistent tree for iteration (Phase 1).
- **UART is the recovery anchor.** It is now the reliable U-Boot default, while
  ACM is an explicit faster mode. Networking/SSH still removes the throughput
  bottleneck for Linux-side iteration.

## Phase 1 — Build & OS polish (bench, near-term)

- **Rootfs workflow — complete and hardware-verified.** The rootless
  `tools/rootfs/build.sh` verifies signed Debian metadata, requires an SSH key,
  disables password SSH, installs all 24 Linux 6.18.38 modules, builds
  raw+sparse ext4 images, and validates growfs plus filesystem integrity. On
  the bench it boots repeatedly with a 4.5 GiB root filesystem, serial
  autologin, stable per-device identity, Cedrus/Panfrost modules, and active
  public-key-only sshd. A remote SSH login remains gated on networking.
- **Boot cleanup — complete and hardware-verified:** removed the CCU
  `MIPS_DIAG` residue, enabled autofs, modeled the Mali supply, installed clean
  U-Boot `g8a601c1`, and verified UART, ACM, fastboot, and normal Debian boot.
- **Dev workflow**: a persistent, hackable kernel worktree (separate from the
  ephemeral `build/linux-*`) + a fast "rebuild module → load on target" path.
- **WiFi SDIO stability — fixed for load; bench-validated (no regression).**
  The AIC8800 `mmc1` link wedged under sustained load: `FIFO_RUN_ERROR` on CMD53
  that the phase-rotation retry can't recover (phase fixes CRC, not underruns) →
  CMD53 timeout → `aic8800_fdrv` `cmdqueue drain timeout` leaks an atomic context
  → `scheduling while atomic`. Patch 0006 now **classifies the CMD53 error**: FIFO
  underruns (`FIFO_RUN_ERROR`/`HARD_WARE_LOCKED`) get FIFO/DMA-reset recovery with
  a short AHB back-off and *no* phase rotation (which would only knock a good link
  off its stock sampling phase); CRC/timing errors keep the phase-rotation path.
  Independent retry budgets (7 phase / 15 FIFO) keep a burst of load-induced
  underruns from exhausting the CRC budget and surfacing as a hard `-ETIMEDOUT`.
  **Bench (2026-07-22):** 384 MB of sustained WiFi transfer completed with zero
  SDIO errors and no wedge (previously ~12 MB wedged it); the old failure is gone.
  The FIFO recovery path itself was **not provoked** — the SDIO data path never
  underran this session (the marginal weak-RF placement that produced the original
  `FIFO_RUN_ERROR` didn't reproduce), so it stands as defense-in-depth; to observe
  it firing, retest from the −71…−80 dBm spot. DVFS was ruled out (wedged even
  pinned at 1416 MHz).

## Phase 2 — Bench subsystem bring-up (SoC-general)

Independent of the projector; ordered to unblock the dev loop first.

1. **Networking (WiFi + BT) — highest value.** Unlocks SSH and ends the UART
   pain. First verify *what's populated and on which bus* (the well0nez
   reference points at an **AIC8800** combo, SDIO or USB); then driver +
   firmware + DT node. Everything downstream gets easier once this lands.
2. **Thermal / cpufreq / DVFS** — safety + real performance.
3. **Crypto (sun8i-ce) + RNG.**
4. **Video decode (Cedrus / VE3)** — headless-testable (patch 0022 in series).
5. **GPU (Mali-G31 / Panfrost)** — driver is mainline; needs a working display
   output (HDMI?) to be useful, so partly gated on the display path.
6. **Audio** (I2S / codec / HDMI audio) — depends on what's populated.
7. **IR receiver (sunxi-cir)** — patch 0021; needs the receiver populated.

## Phase 3 — Projector board bring-up (`HY200_QZ713_V2`, LPDDR3)

- Build U-Boot with `hy200_qz713_v2_defconfig` — the **LPDDR3 params are
  replay-verified only, never run on hardware**.
- **FEL-boot first**, verify DRAM + console, *before* writing anything to its
  eMMC. Confirm the recovery vector exists on this board.
- Audit the existing projector DTS against the physical board, enable its
  vendor-only drivers in a separate config, and port `cpu-comm` away from its
  inherited 32-bit virtual-pointer ABI before enabling it on arm64. Then
  validate boot to Debian (rootfs auto-grows).

## Phase 4 — Projector subsystems (needs Phase 3)

- **LCD panel + backlight** (PWM).
- **MIPS display coprocessor pipeline** — `mipsloader` + `nsi` + `cpu-comm` +
  `tvtop` + `decd`: the projector's display path (RE'd by well0nez; the hardest
  and least-understood piece).
- **Keystone motor** (GPIO stepper, patch 0009).
- **Fans + NTC** (board-mgr, patch 0008).

## Phase 5 — Upstreaming (long-term)

Clean the H713 driver series (CCU, pinctrl, PPU, LRADC, USB-PHY, MMC, …) + DT
bindings for mainline submission; upstream the board DTS once stable. The forks
were curated with this in mind (see [../PROVENANCE.md](../PROVENANCE.md)).

## Open questions — verify before committing effort

- **Board population**: what's actually fitted on each board — WiFi/BT chip +
  bus, HDMI, audio codec, IR receiver, fans, panel connector?
- **Projector safety**: can `HY200_QZ713_V2` be FEL-recovered (button / BROM
  fallback) if a flash goes wrong?
- **Display output on the bench** — is there HDMI (or only the projector's LCD
  path)? Determines how far GPU/display bring-up can go on the bench alone.
