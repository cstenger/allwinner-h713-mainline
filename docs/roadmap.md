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
- **The UART is flaky.** Getting a faster console (WiFi/SSH, Phase 2) early pays
  for itself many times over — most bring-up iteration is bottlenecked on it.

## Phase 1 — Build & OS polish (bench, near-term)

- **Kernel modules into the rootfs — the biggest current gap.** Only built-in
  (`=y`) drivers run today; `=m` modules aren't installed (`/lib/modules/6.18.38`
  is absent), so any loadable-module subsystem silently can't load. Add
  `make modules_install INSTALL_MOD_PATH=<rootfs>` to the build/rootfs flow.
- **DTS split** — the current `qz713df-a1` DTS still carries well0nez's
  projector-only nodes. Split into a shared `sun50i-h713.dtsi` + a clean bench
  DTS (no projector nodes) + a real `qz713-v2` projector DTS (Phase 3).
- **Rootfs**: `x-systemd.growfs` ✅; fold the manual `mmdebstrap` steps into a
  `tools/rootfs/build.sh`; ssh-key + disable password auth; rebuild the
  bootstrap **signed** (Debian keyring) for a trustworthy image.
- **Dev workflow**: a persistent, hackable kernel worktree (separate from the
  ephemeral `build/linux-*`) + a fast "rebuild module → load on target" path.

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
- Land the projector DTS; validate boot to Debian (rootfs auto-grows).

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
