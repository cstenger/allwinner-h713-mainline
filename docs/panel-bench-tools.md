# Panel bench tooling

These opt-in diagnostics supported the earlier black-panel investigation.
The current build, observed result and rollback procedure are in the
[panel initial-state runbook](uboot-panel-initial-state.md). The bench tools
below are separate from normal startup and are not installed or enabled by
this cleanup. Their revised guards and cleanup paths have offline validation;
no new hardware result is claimed.

## Shared TVFE source and build

The `.c` and `.h` entries under `modules/hdmi-tvfe-bench/` are tracked relative
symlinks to `../hdmi-audio/h713-hdmi-tvfe.c` and `.h`. They were already symlinks
in the workspace; the earlier inventory followed them when comparing hashes.
Kbuild therefore compiles the actual production TVFE hold into the bench
module. The production source files are unchanged.

Build both modules against a prepared matching kernel tree:

```sh
make -C /absolute/path/to/kernel ARCH=arm64 LLVM=1 W=1 \
  M="$PWD/modules/hdmi-tvfe-bench" modules
make -C /absolute/path/to/kernel ARCH=arm64 LLVM=1 W=1 \
  M="$PWD/modules/r-wdog-reboot-bench" modules
```

The TVFE bench requires `armed=1`, a live receiver owner, and exclusive ARM
bench access. It pins the receiver through its exported acquire/release API
and claims the AudioTop resource range before taking the shared TVFE hold.
The production audio driver reserves the same range, excluding their
coexistence even in TVFE-only mode. Other raw-MMIO diagnostic clients must
still be excluded by the operator.

`audio_top=1` additionally applies the production-order IHB/AudioTop setup;
`top_ctl` may contain only bits from `0x700`, and `top_cfg=0` skips the config
word. Invalid masks and the historical `keep_audio_top=1` mode are refused
before resource acquisition or MMIO. Normal removal restores AudioTop and IHB
with readback checks before releasing TVFE and receiver ownership. A failed
readback is logged as failure, not restoration success; it requires inspection
and a physical cold cycle before another attempt.

## Target-side receiver bench wrapper

[bench-receiver-only.py](../tools/hdmi/bench-receiver-only.py) runs on the
prepared board with a matching installed `/usr/lib/h713-hdmi` bundle. It uses
the bundle's session state, lock, handoff validation and terminal parking.
It does not prepare a cold boot or disable production services automatically.
Prepare an exclusive bench cold session with capture/signal/speaker units
inactive and no earlier session initialization on that boot. Each mutating
action requires `--armed` and the exact current `--expected-boot` ID.

Example action shapes (replace `BOOT_ID` with the positively checked boot ID):

```sh
python3 bench-receiver-only.py start --armed --expected-boot BOOT_ID --tvfe-only
python3 bench-receiver-only.py stop-tvfe --armed --expected-boot BOOT_ID
python3 bench-receiver-only.py park --armed --expected-boot BOOT_ID
```

Stage the matching bench module at `/root/h713-tvfe-bench.ko` for TVFE mode.
The default start loads the receiver only. `--audio-no-dsp` loads the normal
audio module with `manage_dsp=0`; use `stop-audio` afterward. `--tvfe-only
--audio-top` exercises AudioTop separately. `status` is read-only and does not
require the two mutation acknowledgments. `--bundle` selects an explicit
matching session bundle; it is not a compatibility shim for older APIs.

The once-per-boot state latch prevents setup retry, including after a partial
failure. Clock stages must be in range 0–4. The wrapper refuses competing
owners, checks receiver readiness/IPC, and accepts stop operations only for its
own recorded mode. Audio stop retains an open PCM and restores WirePlumber's
prior active state. TVFE stop checks the loaded module's current `audio_top`
parameter, rather than unrelated older kernel messages. Restore messages must
come from a fresh, prefix-preserving kernel-log tail; missing evidence or log
wrap prevents a verified stop. Terminal parking remains blocked until the
bench module is unloaded and the recorded stop is verified.

Do not bypass a failed stop by editing the shared state file or clearing the
RTC launch latch. The retained-state experiments are historical only.

## R-domain watchdog experiment

The R_WDOG module is a separate intervention, not required by receiver/TVFE
bench modes. Loading with `armed=1` reserves/maps `0x07020400..0x0702041f` and
registers a priority-200 restart handler above PSCI's priority 129. It writes
nothing until the next restart callback. On a normal restart this callback
runs after device shutdown, unlike the earlier immediate SysRq-b test.

The callback replays the recorded stock write order and returns `NOTIFY_DONE`
after two seconds if reset did not occur, allowing lower-priority handlers to
run. Registration/map failures release acquired resources; unload unregisters
the handler and releases the mapping/reservation. It changes the next restart
while loaded: this is bench-only, requires explicit operator preparation, and
is not evidence that the black-panel issue was fixed. The historical repeat
outcomes remain in the separate local October 16/17 investigation records.

## Historical scripts

The old rail-cut/reboot/source-switch/register-scan/U-Boot-latch scripts are
retained as [exact text snapshots](panel-bench-tooling-history/README.md), with
checksums and concrete review findings. They are not active reusable entry
points. Those historical script bodies have only been parsed during cleanup.

The newer [passive UART recorder](../tools/serial/capture-panel-validation.py)
can record an independently authorized trial without sending UART commands.
The broad historical R-domain scan is not an endorsed current read allowlist.

## Offline checks

```sh
python3 tools/hdmi/test-panel-bench.py
python3 tools/hdmi/test-panel-bench-native.py
```

Ten Python cases exercise the actual bench subclass with simulated board IO.
Native harnesses compile the actual TVFE lifecycle/AudioTop functions and
watchdog functions against fake resources/MMIO; they check guard ordering,
ownership, partial mapping failure, setup/restoration, readback failures,
watchdog registration/write order and fallback cleanup. They cannot establish
physical clock, rail or reset behavior. Symlink target checks also pass.
Both ARM64 module builds pass on Linux 6.18.38 with `W=1`; clang reports only
its patch-version difference (23.1.3 versus the tree's original 23.1.1).
No board access, reboot, source switch, latch write or rail cut was performed.
