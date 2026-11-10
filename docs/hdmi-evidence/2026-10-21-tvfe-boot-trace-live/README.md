# TVFE OFF localized to genpd sync-state — October 21, 2026

**Result: Linux explicitly powers TVFE OFF through the genpd provider's
sync-state callback.** TVFE remains ON through early Linux, PPU probe, bus
reset/clock preparation and all 15 original domain-init writes. At about
7.35 seconds the callback stack reaches `h713_ppu_power_off`; the instrumented
TVFE OFF command is bracketed by ON and OFF status reads.

**Board ended in orderly poweroff** (`reboot: Power down`, 153.56 seconds).
No optional U-Boot proper was installed. No DSP request was sent, and DSP
retention remains unmeasured. This is a localized power-policy finding,
not automatic HDMI recovery.

Design/preparation: [runbook](../../hdmi-tvfe-boot-trace-design-2026-10-21.md),
[offline preparation](../2026-10-21-tvfe-boot-trace-preparation/README.md).
Raw workspace: `build/hdmi-tvfe-boot-trace-2026-10-21/live-01/`.

## Evidence sequence

| Point | TVFE | TVCAP | Evidence |
| --- | --- | --- | --- |
| Cold production, boot `d7017dce` | ON | ON | `cold-census.json`; DSP `0/0` → patch verified `1/1`, normal owners active |
| Warm pre-logo, after bus-only open | ON | ON | `warm-prelogo/`; bootcmd matched this cycle's cold record |
| Final U-Boot sample after one successful logo and RAM preparation | ON | ON | `kernel-trace/preboot.json`; MIPS parked and production GP6 latch checked |
| Linux early initcall, 0.026955 s | ON | ON | `kernel-trace/serial.log` |
| PPU probe complete, 0.138101 s | ON | ON | every reset/clock/init boundary also ON |
| Immediately before OFF command, 7.516185 s | `00010000` | `00010000` | `power_cmd_before` |
| TVFE command, 7.526458 s | `domain=TVFE hw=1 on=0` | — | original PPU power command, unchanged by instrumentation |
| Immediately after command, 7.539832 s | **`00020002`** | `00010000` | `power_cmd_after`; OFF plus transition-done bit |
| Warm Linux census, boot `73c7ebcb` | **`00020000`** | `00010000` | no handoff, no h713 modules, HDMI services inactive; DSP reads skipped |

UART monotonic timestamps above are used directly. The journal's monotonic
format rebases buffered early messages; do not substitute it for UART timing.
The exact diagnostic `_BOOT_ID` journal is preserved separately.

Cold boot was captured from one SPL with GP6 zero. Both cold and warm UART
catchers were verified OPEN on the host before startup/reset. Orderly reboot
was guarded by boot `d7017dce-174d-4795-bf23-0049f73f04b4` and active production
owners. UART records `reboot: Restarting system`, one warm SPL and GP6 latch.
Watchdog-stop warnings do not turn this into a watchdog-expiry trial.

The single warm-logo invocation has its complete `H713_TVFE_LOGO_OK` marker,
post-logo instrumentation and returned prompt in `warm-logo.log`. Its
20-second silence tolerance retained the intentional three-second panel hold.
There was no second firmware launch or source3 relaunch.

The staged rootfs FIT matched SHA-256
`54a691f727e3b405540ea806f11afe5da6178109adb3747094b55ea4f12fbf7e` and 7,747,368
bytes. The RAM runner verified filesize/CRC and warm state, set volatile
`h713_tvfe_trace=1 loglevel=7 panic=0`, then recorded a fixed 60 seconds.
Linux boot `73c7ebcb-8f9a-4251-ab71-079a265ef7b4` reports the expected clang
23.1.3 diagnostic build. Wi-Fi/SSH worked with the existing rootfs modules.
Production boot files, saved environment, SPL, BL31 and proper were unchanged.
The separate file `/root/hdmi-tvfe-boot-trace-2026-10-21/kernel.fit` remains
staged; it is not selected by normal startup.

## The writer and why ignore-unused did not prevent it

The recorded stack is:

```text
Workqueue: events_unbound deferred_probe_work_func
h713_ppu_power_off
_genpd_power_off
genpd_power_off
genpd_sync_state
device_links_flush_sync_list
device_links_driver_bound
driver_bound
really_probe
...
```

`genpd-source-excerpts.txt` records the exact diagnostic kernel's source and
line numbers; its full-file SHA-256 is in `manifest.json`.

- `pd_ignore_unused` makes `genpd_power_off_unused()` skip the late sweep;
  the log confirms that sweep was skipped at 2.526665 seconds.
- `genpd_sync_state()` calls `of_genpd_sync_state()`. That routine iterates
  the provider's domains, clears `stay_on`, then calls `genpd_power_off()`.
  It does **not** test `pd_ignore_unused`.
- `genpd_power_off()` respects always-on flags and active consumers. TVFE
  has no attached consumer in this warm boot, so its callback runs. TVCAP
  has the existing keep-on policy and stays ON.

The stack plus explicit TVFE OFF command and immediate status change identify
this software power-off path in this diagnostic cycle. Reset, U-Boot cleanup
and the PPU's init writes are not required to explain the observed transition.
The previous uninstrumented cycles were not themselves traced; do not claim
that they independently recorded this callback.

## Coverage, tooling and limits

`analysis.json` reports complete **kernel** coverage: all seven boundaries,
five samples at each of the four domain-init phases, no missing/unfinished
markers, and one observed ON-to-OFF interval around the power command.
The optional U-Boot probe stages were not installed or required for this
first run. The generic analyzer leaves writer identification conservative;
the stack/command/source review above provides the attribution.

The actual serial log replays an identical initial Linux banner during
console handover. The analyzer initially treated any second banner as a
second boot. It was corrected to permit identical banner replay while
rejecting distinct banners or repeated early-init samples. **15 offline
tests pass**, including the new replay/mixed-boot regressions. Raw UART is
preserved; it was not edited to make analysis pass.

This run still includes the deliberate pre-logo bus-opening intervention,
additional logging/timing, and a diagnostic compiler build. It is not a
release qualification. The callback stack dump is instrumentation, not an
oops. No DSP versions were queried after reset, no audio/video acceptance
was claimed, and no power-policy fix was deployed.

## Next experiment

The warm version-read experiment must avoid this known Linux-induced OFF
transition or observe the DSP before it. Otherwise a later `0/0` could be
confounded by power loss during observation rather than reset itself.

Prepare a narrowly scoped bench retention policy with hardware-verified
TVFE initially ON, explicit diagnostics and bounded ownership, then design
the warm clock/lock/version sequence. Preserve production guards and GP6;
do not globally disable genpd or turn this diagnostic hold into release
policy without separate validation. The optional bootm-trace proper is not
needed to answer the power-off-writer question now localized here.
