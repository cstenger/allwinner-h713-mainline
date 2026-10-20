# Staged HDMI reset instrumentation — 2026-10-20

Prepared after investigation commit `0d920c8`. This is bench instrumentation,
not a recovery implementation. No board connection, installation, reboot,
GP6 clearing, or firmware retry was performed. Production patch series,
boot script, firmware, and shutdown guards are unchanged.

## Prepared probes

The patches live under [tools/hdmi/reset-trace](../tools/hdmi/reset-trace/).
They are deliberately outside `patches/u-boot/series`.

| Stage | Hook | What has already happened |
| --- | --- | --- |
| `spl_pre_dram` (optional) | Immediately after `preloader_console_init()` in SPL `board_init_f()` | BootROM, SRAM/access setup, timer, clock setup, UART pinmux and console initialization. Not pristine reset entry. |
| `spl_post_dram` (optional) | Immediately after `sunxi_board_init()` | DRAM controller/PHY initialization, board power setup and CPU clock adjustment. Before SPL loads BL31/proper. |
| `proper_preboot` | First statement of proper `board_late_init()` | SPL, BL31, proper relocation and earlier init, including environment loading. Before the main loop executes saved `preboot`, including GP7 consumption and USB startup. |
| `pre_workspace` | In `h713_disp_load()`, immediately before workspace clearing | Proper initialization and any preceding command/script actions. Captures before each display artifact load, including the separate capture launch load on cold startup. |
| `post_logo` | After the auto-logo frame commit | Logo firmware has run and, on the normal boot path, been quiesced; panel timing and framebuffer state have been established. |
| `manual` | Explicit `h713_disp reset-state` command | Whatever the operator already ran; the command itself only snapshots. It does not launch, stop, or prepare firmware. |

The proper probes read five words: GP6 `0x07090118`, GP7 `0x0709011c`,
MIPS clock `0x02001600`, MIPS reset `0x0200160c`, and MIPS status
`0x0306101c`. RTC/control-block reads are already used by the boot and parking
paths. The optional SPL probes read only the first four and explicitly print
`mips_status=unread`; early CPUCFG access has not been established as necessary
or validated on the board. All added accesses are reads; UART output adds
timing overhead and therefore still needs a bench control run.

Example wire format (illustrative values, not a new hardware result):

```text
H713 RESET v1 stage=proper_preboot gp6=48444d49 gp7=00000000 mips_clk=00000000 mips_reset=00000000 mips_status=00000000
```

The words are read sequentially before printing, not atomically. There is no
DSP command, receiver MMIO, SCP reset/SRAM access, memory clearing, or policy
change in the probes. In particular, `pre_workspace` does not dump retained
firmware RAM: its availability and coherency are a separate future question.
This first instrumentation can locate changes in the latch and MIPS controls;
it cannot prove DSP freshness, HPD/DDC restoration, or a usable audio path.

## Earlier boot effects reviewed

Use the normal pinned U-Boot source plus the panel patch series, not the
submodule's later capture-tracing HEAD. The configured DDR3 build has
`CONFIG_BOARD_LATE_INIT=y`, `CONFIG_H713_MIPS_BOOT=y`, and `CONFIG_VIDEO` off.
This makes the late-init probe precede the script-driven logo sequence.

The SPL sequence is `sunxi_sram_init` → `tzpc_init` → timer/clock/GPIO setup →
SPL/console initialization → `sunxi_board_init` → image loading. The reviewed
weak SRAM hook is empty; earlier assembly and BootROM are outside this probe.
The H713 DRAM implementation changes analog/pad controls in the RTC region,
bus/MBUS state, and DRAM clocks/resets; it must not be treated as passive RAM
retention. Its RTC writes at offsets `0x160` and `0x1f4` are distinct from
GP6/GP7 at `0x118/0x11c`. No direct write to the sampled MIPS clock/reset words
was found in the reviewed clock/DRAM paths. This is source evidence, not a
complete proof of silicon reset-domain behavior.

TF-A H713 uses the native PSCI platform and includes the H616 power code.
Its platform setup configures console, timer, interrupt/security state and
device-tree/PMIC handling. The common setup's explicit A64/H5 bus-clock
adjustments do not target H713. The existing BL31 is not instrumented or
rebuilt here. A difference between `spl_post_dram` and `proper_preboot` spans
SPL image loading, BL31 and earlier proper initialization; it must not be
attributed to BL31 alone.

## Build preparation and offline validation

[prepare-reset-trace.py](../tools/hdmi/prepare-reset-trace.py) accepts a normal
prepared source tree, verifies its source-pin metadata, fingerprints its
contents, copies it to a new directory and applies the bench patches with
zero fuzz. It refuses existing output and output inside the base tree.
The source submodule and normal prepared tree are not edited. The output
manifest records the complete base-tree digest, normal input metadata, patch
hashes and instrumented-tree digest; it does not independently authenticate
an arbitrarily modified base tree as a clean export. Use the normal preparer.

To prepare a new proper-only bench tree:

```sh
base_tree=$(tools/build/build.sh uboot-tree)
python3 tools/hdmi/prepare-reset-trace.py "$base_tree" build/hdmi-reset-trace-proper
```

Adding `--include-spl` prepares the optional earlier probes too. It does not
authorize or perform an SPL update. A full DDR3 build with both patches was
completed locally in `build/hdmi-reset-trace-2026-10-20/` using the existing
`build/out/bl31.bin`. It contains source/patch provenance in `manifest.json`,
binary/config/log hashes and compiler identity in `artifacts.json`, and full
configuration/build logs. Both proper and SPL contain their expected marker
strings. The build succeeded with warnings in existing code; no warning was
reported for the new probe header or hooks. No LPDDR3 build or hardware test
is claimed.

| Local bench artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `obj/u-boot-dtb.bin` | 908512 | `76a2bc545a3fdc245c945e77b13d0a2b2cf0375ba73a6ee34252d0dc70fbdc4b` |
| `obj/spl/sunxi-spl.bin` | 32768 | `f83f554b3dee3eb474e8643c8634cef12aacd795e33b963bb626b7f6a3f9463f` |
| `obj/u-boot-sunxi-with-spl.bin` | 988433 | `92d1abcebb3edead88c01fe1149112e0c3206c4d0195c7770b234dda97ddbd13` |

These hashes identify this local build, not the installed October 18 trial.
The combined image is not a write recipe for the split boot layout. Start
with proper-only instrumentation if the next board trial proceeds; keep SPL,
BL31, environment and boot script unchanged for that comparison. Optional SPL
instrumentation requires a separate artifact/layout/recovery review and its
own paired baseline because it changes an earlier component.

For rebuilding, use a new output directory and the same make settings as the
normal U-Boot build, pointing `-C` at the generated `src` and `O` at a separate
absolute object directory. The exact settings for this build were:

```bash
trace_root="$PWD/build/hdmi-reset-trace-2026-10-20"
trace_make=(make -C "$trace_root/src" O="$trace_root/obj"
  ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu'
  LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump
  READELF=llvm-readelf STRIP=llvm-strip KAFLAGS=-fintegrated-as
  KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector'
  BL31="$PWD/build/out/bl31.bin")
"${trace_make[@]}" hy200_qz713df_a1_defconfig
"${trace_make[@]}" -j8
```

## Paired trial procedure, prepared but not executed

1. Inventory installed boot artifacts, saved environment, guarded script and
   kernel/modules. Verify exact backups and rescue access against the
   [split-layout recovery record](uboot-panel-initial-state.md). Validate the
   new proper's extent and installation/readback plan before any write; do
   not substitute these hashes into the old trial's install recipe.
2. Keep a passive UART recording from before the initial cold baseline through
   the reset and subsequent Linux boot. Use the existing
   [passive recorder](../tools/serial/capture-panel-validation.py), with one
   reader for the UART. Retain raw bytes; timestamped chunk representations
   are not analyzer input. Record trial ID, reset method, artifact hashes,
   source connection/rate, starting boot ID and capture byte offsets.
3. Establish each trial from its own physical cold baseline with the same
   instrumented artifacts. Require healthy autonomous capture/signal/speaker
   startup and collect [Linux state](../tools/hdmi/collect-reset-state.py)
   before resetting. Do not compare a fresh cold start against a session that
   already had a firmware failure or manual priming.
4. For the clean trial, request one ordinary systemd reboot. Preserve the
   signal restore, 22 DSP/15 TVFE restore, park and receiver-release logs. If
   the hold guard converts it to poweroff, record a failed clean-reboot trial;
   do not force another reboot around the guard.
5. For the abrupt trial, use one boot-ID-guarded, synced SysRq-b operation
   following the previously documented emergency-reset method. Sync is for
   filesystem writes, not HDMI teardown. Do not reuse the historical trigger's
   old boot ID. Confirm the absence of normal teardown in the UART interval.
   Actual watchdog expiry is a later separate trial, not implied by SysRq-b.
6. Let the existing warm script run once. Expect a retained latch, temporary
   logo launch/quiescence, no sustained capture handoff, and inactive HDMI
   services. Do not manually start the service, clear GP6, invoke source3,
   run a DSP probe, or rerun logo commands to improve the result. Preserve
   source loss and failed/missing markers as observations.
7. Collect Linux state after each boot. Keep complete captures and extract one
   post-reset boot interval per method into `clean-reset.serial.log` and
   `abrupt-reset.serial.log`. Include optional SPL markers from that same
   boot, not the initial cold boot. Use recorded byte offsets and preserve
   original hashes rather than editing logs in place.

Compare the two extracted raw logs:

```sh
python3 tools/hdmi/analyze-reset-trace.py \
  --clean clean-reset.serial.log --abrupt abrupt-reset.serial.log \
  > reset-comparison.json
```

The analyzer requires exactly one `proper_preboot` marker per input and
rejects malformed, repeated-SPL and mixed-boot markers. It preserves stage
occurrences because cold startup may load firmware more than once. It reports
missing stages and field differences, with recovery explicitly `unproven`.
The method labels are supplied by the operator; it does not authenticate a
reset mechanism from those labels. Six offline tests cover ambiguity,
missing data, unread status and source/output isolation.

Stop at the first unexplained failure, state change, or lost serial interval;
retain evidence rather than retrying. A successful collection ends with a
stage-by-stage comparison and a decision about the next measurement. It does
not end with an automatic warm-capture launch. DSP versions, locks, receiver
and SCP state still need separately justified observation before recovery
policy can change.
