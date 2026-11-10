# Claude handoff: HDMI audio normal startup

## Request and immediate state

The user asked to integrate HDMI audio capture into normal startup. Work is
installed but **not yet validated end to end**. The latest cold autoboot
successfully launched MIPS, selected source 3, and verified its transition.
It then stopped at U-Boot because the generated device-tree handoff command
could not parse the PID. The user requested this handoff because their usage
limit is nearly exhausted. Do not launch more work in another chat or send
messages to Claude automatically; this document is for the user to provide.

Workspace: `/home/chris/Projects/h713`, branch `h713-letterbox`.
Current board state is inferred from the user's UART report: at U-Boot,
MIPS live on source 3, RTC GP6 launch latch set, Linux not booted from this
attempt, and managed Linux DSP initialization not attempted on this boot.
No hardware commands were issued after that report. No serial listener runs.

## Exact failure and cause

User's latest output:

```
H713 source 3: callback-event0=1 worker-event0=1 transition-complete=1 worker-old=00000000 worker-new=00000003
Working FDT set to 4f000000
Sorry, I could not convert "b8f275c>"
H713 HDMI source/boot failed - cold cycle required
```

The generated command in `tools/hdmi/build-startup.py`, currently line 71, is:

```
fdt set /chosen h713,hdmi-boot-v1 <0x48444d49 0 ${hdmi_pid}>
```

`setexpr` emits a bare hexadecimal string, here `8b8f275c`. U-Boot's
`external/u-boot/cmd/fdt.c:fdt_parse_prop()` (around lines 810–845) uses
`simple_strtoul(cp, &newp, 0)`: auto-base parsing reads the initial decimal
`8`, then cannot parse the remaining `b8f275c>`. This is a numeric-base error,
not evidence of a source-3, firmware, DSP, or receiver failure.

Suggested fix:

```
fdt set /chosen h713,hdmi-boot-v1 <0x48444d49 0 0x${hdmi_pid}>
```

Audit other environment-derived **FDT cells**, especially `${hdmi_ccu}` in
the resets/clocks properties, and prefix those with `0x` too. Current CCU
phandle happened to be a decimal-compatible value, so those stages passed.
Do not indiscriminately change `itest`/`setexpr`: they use hexadecimal inputs.
Add a regression for PID values containing a–f, ideally against the actual
U-Boot FDT parser or an equivalent focused parser test. Existing host boot
fixtures did not execute this new startup script and missed this bug.

### Safe immediate recovery option

A full cold cycle is the conservative default. There is also a narrowly
scoped pre-Linux resume option, since the failed command occurred **after**
all launch/source/trace guards and **before** Linux/DSP setup:

1. Read `printenv hdmi_pid hdmi_count hdmi_bad`, MIPS status at `0x0306101c`,
   and `h713_disp commtrace`. Require exactly one valid channel-0 PID,
   count 1/bad 0, status exactly 1, and the same completed source-3 trace.
   Confirm current FIT/FDT state and the shutdown consumer/IRQ properties.
2. Run only the corrected `fdt set /chosen ... 0x${hdmi_pid}` command and
   read back its three cells. They must be magic `48444d49`, initial status
   zero, and the current nonzero PID, encoded as three big-endian u32 cells.
3. Boot the already prepared image: `bootm 0x50000000 - 0x4f000000`.

**Do not rerun `hdmi_source`, `hdmi_launch`, the full script, or MIPS launch.**
`hdmi_source` repeats the source CALL. Running the full saved bootcmd on this
latched boot takes the warm skip path and boots without capture. Do not clear
GP6 to force another launch. This resume has not been performed or validated.

## What is installed persistently

Original U-Boot and kernel binaries are unchanged. The boot FAT has a new
`h713-hdmi.scr`. Saved environment now has:

- `preboot`: original GP7 reboot-mode dispatch and USB startup; the old
  unconditional `h713_disp auto 0x34 logo` moved into the guarded script.
- `bootcmd`: FAT-load `h713-hdmi.scr` at `0x52000000`, then `source` it.
- Five-second autoboot delay unchanged.
- `h713_hdmi_previous_preboot` and `h713_hdmi_previous_bootcmd`: rollback.

The script uses RTC **GP6 at 0x07090118** as a once-per-power-cycle latch,
written `0x48444d49` before either display/MIPS launch. GP7 at 0x0709011c
remains the reboot-mode word. GP6 retention across a real warm reset was
verified: the script skipped all MIPS launches, Linux booted the original FIT,
and the capture service skipped with `ConditionResult=no`. A physical cold
cycle showed all RTC GP words zero. Never clear GP6 in software to retry.
Battery/backpower/other-firmware behavior still warrants broader validation.

Persistent files are under `/usr/lib/h713-hdmi`; units are in
`/etc/systemd/system`, both enabled for multi-user.target:

- `h713-hdmi-capture.service`: verifies current-kernel DT handoff, starts
  existing managed receiver/audio lifecycle, terminal shutdown on stop.
- `h713-hdmi-signal.service`: Requires/After capture backend; owns DDC pins
  and the new persistent SCP EDID/HPD owner. It restores signal ownership
  before backend DSP restoration, MIPS parking and receiver release.

This makes an ALSA capture device available; it does not record to disk by
default. Consumers should Requires/After **h713-hdmi-signal.service** so they
close before signal restoration and backend teardown.

The latest installed script still has the bare-PID bug. The installed bundle
was built before the latest additional native test edits, which affect tests
only. Both target units and every installed bundle hash were verified.

## Source changes, all UNCOMMITTED

- `tools/hdmi/build-startup.py`: creates reproducible legacy U-Boot script,
  bundle, environment JSON and SHA256 manifest. No mkimage dependency.
- `tools/hdmi/install-startup.sh`: target installer, refuses replacing an
  existing installation, checks ABI/hashes, preserves FIT, installs/enables
  services. Current installation was augmented safely on the warm skip boot,
  with all capture/MIPS modules absent; do not rerun installer blindly.
- `tools/hdmi/h713-hdmi-capture-startup.service`: persistent backend unit.
- `tools/hdmi/h713-hdmi-session.py`: `--boot-handoff` validates DT proof
  instead of host JSON; allows two receiver clients while signal owner is
  loaded; refuses backend shutdown while any signal owner/helper remains.
- `modules/hdmi-signal/h713-hdmi-signal.c`, Makefile, README, .gitignore:
  new continuous SCP owner. **Built, not hardware validated yet.**
- `tools/hdmi/h713-hdmi-signal.py` and `.service`: signal lifecycle wrapper.
- `tools/hdmi/test-hdmi-session.py`: now 19 tests.
- `tools/hdmi/test-hdmi-signal.py`: 4 ownership/failure/order tests.
- `docs/hdmi-normal-startup.md`: design, installation and rollback.
- `docs/hdmi-evidence/2026-10-14-normal-startup/`: installation, warm guard,
  native results and saved environment. Its status.json/README predate the
  latest failed cold autoboot; update them with the user's report.

Build output: `build/hdmi-startup/` (ignored). The SCP payload header is
regenerated from `tools/hdmi/fixtures/hdmi-audio-edid.hex`:

```
python3 tools/hdmi/make-edid-trial-code.py --edid tools/hdmi/fixtures/hdmi-audio-edid.hex modules/hdmi-signal/edid-trial-code.h
```

Its SHA256 is `89627ae0dc603d8909a02daff92b1ddfce63febca43457b6e509c97db70f0109`,
byte-identical to `build/scp-audio-endurance/edid-trial-code.h` used in the
passing endurance tests. The generated header and build products are ignored.

### New SCP owner design and review needs

The old capture tests depended on a **bounded diagnostic signal helper**.
Enabling just the capture backend would not assert HPD continuously. The new
owner uses the same proven payload, which already waits for a cooperative
restore flag; it replaces the probe's timed sleep with a persistent lifetime.

It acquires a receiver client, claims SRAM/reset resources, saves SRAM and
vectors, validates installed instruction pairs, pins itself before SCP release,
and reports ready. Failures after release retain every hold and require a cold
cycle. Explicit `stop=1` requires peripheral completion, zero mismatch/exception,
SCP stopped reset readback, and exact SRAM/vector restoration before releasing
its receiver client/self-reference. Wrapper retains DDC pins on failure.

Review this new code carefully before calling it production ready: init failure
retention, module reference accounting, concurrent stop/state access, complete
peripheral restoration proof, pinctrl restoration error propagation, and
failure during system shutdown. Existing DDC helper logs a pinctrl idle restore
error but has a void module exit; stronger propagation may be needed. The
backend's new guard prevents parking while signal modules remain, but systemd
continues overall OS shutdown even when an ExecStop fails; define/test that
failure policy rather than assuming systemd stops poweroff.

## Validated base and constraints

Last committed base: `1b5a423` corrected UART relay and active-recording poweroff.
Earlier commits: `a5d02f2` endurance/HPD, `29952f4` shutdown integration,
`71dca46` stream recovery, `8244151` managed audio/receiver.

Passing prior hardware results: three input rates (48/32/44.1 kHz), physical
reconnect, one-hour capture without XRUN, ten HPD cycles, verified 22-word DSP
and 15-word TVFE restoration, MIPS terminal parking/receiver release, and full
poweroff with active recording. Last strict poweroff test captured ordered
recorder → diagnostic signal cleanup → backend stop → powerdown; lamp/fan off
and no reboot for 90 seconds confirmed. These tests used the earlier managed
bench boot and bounded signal helper, not the new automatic/persistent path.

Keep unrelated dirty work untouched:
`docs/reference/vp9-scaler-2026-10-06.md` and the three tracked dirty files in
`modules/hdmi-speaker-split/`. There are many older untracked Oct 7 probes,
evidence directories and WAV/build outputs. Do not stage everything or clean.

Never warm-relaunch MIPS or bypass a DSP timeout latch. DSP patch versions must
start 0/0 and become 1/1; patch remains volatile after normal stop/parking and
requires physical power removal to clear. No undocumented reset/receiver MMIO
writes, no forced module unload, no disabling guards. No persistent UART
listener: use bounded command/response or bounded test capture. Do not change
standby, hotspot, suspend or the existing final lamp/fan poweroff hook.

## Build / connection details

Validated kernel build:
`build/linux-6.18.38-2a2ced73e505c450215680f0427646c1e7d6432ee82a314344022264b082af23`.
Kernel 6.18.38 #1, Oct 7 18:57:16 PDT 2026, HY200 QZ713DF_A1.
FIT: FAT mmc 1:2 `/h713-kernel.fit`, 7,789,216 bytes (0x76daa0).
Embedded FDT: **0x8319** bytes (U-Boot prints hexadecimal 8319).
FIT address 0x50000000; copied RAM FDT 0x4f000000.
IRQ fix: `/soc/audio-bridge@203042c interrupts <0 115 4 0 113 4>`.
Parking node supplies CCU reset IDs 1/2/3 and clock IDs 19/20.

Pinned DSP firmware: local ignored
`docs/hdmi-evidence/2026-10-07-android-audio/audio-dsp-patch.bin`, 2,896 bytes,
SHA256 `8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5`.
ALSA capture: `hw:H713HDMI,0`, 48k stereo S16_LE, 256-frame periods.

```
make -C <kernel-build> M=$PWD/modules/hdmi-signal KBUILD_EXTRA_SYMBOLS=$PWD/modules/hdmi-receiver/Module.symvers ARCH=arm64 LLVM=1 W=1 modules
python3 tools/hdmi/build-startup.py build/hdmi-startup
python3 tools/hdmi/test-hdmi-session.py
python3 tools/hdmi/test-managed-boot.py
python3 tools/hdmi/test-hdmi-signal.py
python3 tools/hdmi/test-edid-trial-payload.py
```

SSH: `ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 root@192.168.4.1`.
Host WiFi: `nmcli connection up spirits` after board AP is up.
UART: `python3 tools/serial/console.py --port auto --wait 1 '<command>'`.
In Codex, SSH/serial/nmcli and Git mutations have needed sandbox escalation.

## Remaining steps to production readiness

1. Preserve user's failed cold-boot report as evidence; fix FDT numeric base
   formatting, add regression, and safely resume or cold boot into Linux.
2. Rebuild and install corrected script/bundle with checksum comparison,
   retaining original FIT and saved rollback environment. Existing installer
   deliberately refuses replacements; implement a guarded update path or use
   a narrowly verified update while stopped. Do not remove live owner holds.
3. Validate a completely autonomous cold boot: correct DT handoff, DSP 0/0 →
   1/1, healthy graph, receiver clocks/domains/EDID, signal ready/failed=N,
   owner clients=2 and no bench /tmp bundle or host proof dependency.
4. Verify actual host EDID/ELD and sustained real stereo tone capture through
   the automatic path. Do **not** use existing capture runner unchanged: it
   starts a competing bounded SCP helper and expects a disconnected connector.
   Adapt a test to use the already-running persistent signal service instead.
   Stage arecord if absent (old build has `build/hdmi-alsa-utils/usr/bin/aplay`).
5. Test persistent HPD beyond the former timeout, HDMI unplug/replug, input
   rate changes, no-input boot, delayed source connection and source reboot.
   Reuse existing signal analysis and capture counters; verify no XRUN/stall.
6. Validate consumer → persistent signal restore/DDC release → backend DSP/TVFE
   restore → MIPS park → receiver unload ordering. Test full poweroff with active
   recording and the already corrected bounded UART journal relay. Check lamp/
   fan off and no reboot, then repeat across more cold boots.
7. Exercise failure/ownership cases: foreign helpers, busy PCM, signal init or
   restore failure, backend failure, service stop/start, partial install/update,
   missing/corrupt script, and safe rollback. Never bypass hardware latches.
   Re-test warm reboot, reboot bootloader/fastboot, watchdog/WiFi recovery;
   confirm GP6 remains latched and capture stays disabled without hanging Linux.
8. Review/reduce bench-specific assumptions: pinned image sizes/ABI, firmware
   provenance/installation, proper immutable release manifest, generated DT
   consumer naming, DDC ownership/error reporting, failure policy, rootfs build
   integration and reliable upgrade/rollback. Broaden cold-reset provenance
   validation before treating RTC GP6 as universally sufficient.
9. Document supported formats/rates honestly. Current production candidate is
   fixed 48k stereo S16_LE capture and tested HDMI input rates 32/44.1/48k; do not
   claim compressed, multichannel, higher precision or other rates without tests.
10. Update evidence/status/docs, review the complete diff, and commit only this
    startup integration once validated (user has not requested a new commit yet).

Rollback at U-Boot (use after appropriate cold-cycle preparation):

```
setenv preboot ${h713_hdmi_previous_preboot}
setenv bootcmd ${h713_hdmi_previous_bootcmd}
saveenv
```

Disable both persistent HDMI units in Linux for rollback. Restoring the old
preboot reintroduces its display/MIPS launch, so do not warm-reset into it
while the old volatile firmware/DSP state remains.
