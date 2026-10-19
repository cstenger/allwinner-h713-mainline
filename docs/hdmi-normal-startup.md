# HDMI audio at normal startup

For automatic playback through the internal speaker, install the separate
[persistent speaker consumer](hdmi-speaker.md). It applies the codec mixer on
each start and stops before signal restoration and capture backend teardown.
The capture backend alone exposes an ALSA input; it does not play that input.

The opt-in startup bundle uses the installed September 24 U-Boot and the
validated October 16 6.18.38 FIT (7,795,668 bytes; board FDT 34,666 bytes).
It prepares HDMI1/source 3 in U-Boot,
then enables the managed ALSA capture device through a persistent systemd unit.
It does not continuously record to disk. Consumers can open `hw:H713HDMI,0`
at 48 kHz, stereo, S16_LE and should declare `Requires=` and `After=` on
`h713-hdmi-signal.service` (which requires the capture backend) so they close
before signal restoration and backend shutdown.

## Boot sequence and guards

The saved `preboot` retains USB and GP7 reboot-mode handling. Its previous
unconditional display/MIPS launch moves inside `h713-hdmi.scr`, behind a
once-per-power-cycle latch in **RTC GP6, physical 0x07090118**. This is the
RTC general-purpose nvmem bank documented and retention-tested by kernel
patch 0029; GP7 remains exclusively the existing reboot-mode handoff.
No other code in our boot chain writes GP6. Do not clear GP6 in software.

A nonzero GP6 skips every display/MIPS launch and boots the original FIT
without a capture handoff. Thus warm reboots still reach Linux, with HDMI
capture disabled until a physical cold cycle. An unexpected GP6 value also
fails closed. Removing power must include serial and USB to avoid backpower.

On a zero latch, the script validates the FIT/FDT sizes and copies its FDT to
RAM. It corrects the Audio Bridge IRQ and adds the same CCU parking consumer
used in the shutdown tests. It requires MIPS status exactly zero, writes and
checks the GP6 latch **before any firmware launch**, runs the existing logo
sequence, and performs the proven trace-enabled MIPS launch. It refreshes
firmware channel records through `commdev`, validates the reader and pointer,
and discovers exactly one live channel-0 PID instead of hardcoding one.
Source 3 must complete its CALL/RETURN protocol and transition trace, with
both trace canaries intact, before the script publishes the three-cell
`/chosen/h713,hdmi-boot-v1` handoff and boots Linux with the RAM FDT.
A preparation/launch failure stops at U-Boot; it never falls through to a
second firmware attempt. A missing script also leaves the recovery prompt.

The persistent service requires that current-kernel handoff. It uses the
existing live MIPS, source trace, firmware hash, ABI, receiver ownership and
same-boot initialization guards. It never launches firmware from Linux.
No `/tmp` bundle or host-generated cold-proof JSON is needed on this path.

The second persistent service owns DDC pins and `h713_hdmi_signal`. Its SCP
payload and audio EDID are byte-identical to the endurance trial. It holds
HPD continuously until explicit stop, without a timer. It takes a receiver
client, pins itself before SCP release, and retains all holds on setup or
restoration failure. Stop verifies peripheral restoration, stops SCP, restores
and verifies SRAM/vectors, then releases the receiver client and DDC pins.
The backend refuses terminal shutdown while any signal owner/helper remains.
Shutdown retains recorder-before-backend ordering, verified DSP/TVFE restore,
terminal MIPS parking and receiver release. Standby and the final lamp/fan
poweroff hook are unchanged.

## Build and install

Build the receiver, audio, DDC pin and managed signal modules against the
validated kernel first (see `modules/hdmi-signal/README.md`), and
provide the pinned 2,896-byte stock DSP firmware at the location used by the
managed boot coordinator. Then:

```
python3 tools/hdmi/build-startup.py build/hdmi-startup
```

Copy the complete output directory to the target and run `sh install-startup.sh`
from it as root. The installer verifies all bundle hashes and module ABI,
installs `/usr/lib/h713-hdmi` and the enabled persistent unit, and writes only
`h713-hdmi.scr` on the boot FAT after comparison. It verifies the original FIT
checksum is unchanged. It refuses an existing installation rather than
replacing a live generation. Installation does not launch capture.

At a confirmed cold U-Boot prompt, first preserve the original `preboot` and
`bootcmd` in `h713_hdmi_previous_preboot` and `h713_hdmi_previous_bootcmd`.
Set the new values from the generated `boot-environment.json` and `saveenv`.
Keep the existing five-second autoboot recovery window. Validate GP6 warm
retention and the skip path before allowing the next physical cold boot to
run the capture startup automatically.

### Updating only the boot script

`install-startup.sh` refuses an existing installation. To replace just the
U-Boot script, copy a freshly built bundle to the target and run
`sh update-startup-script.sh` from it as root. It refuses unless every other
installed file is byte-identical to the bundle and the FAT script is the
installed generation; it keeps the previous script under
`/var/lib/h713-hdmi-startup/`, writes `h713-hdmi.scr.new`, compares, renames,
compares again and re-verifies the FIT checksum. It never touches modules or
units, so it is safe while the services own hardware.

### FDT cell formatting

`fdt set ... <cells>` parses each cell with `simple_strtoul(..., 0)`. A value
stored by `setexpr` (or `fdt get addr/size`) is bare `%lx` and must be
written as `0x${var}`; a value from `fdt get value` is already `0x%08X` and
must not be prefixed again. `tools/hdmi/test-build-startup.py` checks every
environment-derived cell in the generated script against these rules. The
first cold autoboot (2026-10-14) stopped at U-Boot on the bare PID `8b8f275c`;
an all-decimal-digit PID would have been accepted with the wrong value.

## Recovery

A cold autoboot that stops after the source-3 guards and only at the FDT
handoff command can be resumed without rerunning any launch:
`tools/hdmi/resume-startup-handoff.py LOG` checks census, MIPS status, GP6,
the completed source-3 trace and guards, the live channel PID, the patched FDT
and the absent handoff, all read-only; with `--boot` it then writes only the
handoff, reads back its three cells and runs `bootm 0x50000000 - 0x4f000000`.
Never rerun `hdmi_source`, `hdmi_launch` or `bootcmd`, and never clear GP6.

Interrupt autoboot and restore the saved environment:

```
setenv preboot ${h713_hdmi_previous_preboot}
setenv bootcmd ${h713_hdmi_previous_bootcmd}
saveenv
```

In Linux, disable the persistent service with
`systemctl disable h713-hdmi-capture.service`. Also disable `h713-hdmi-signal.service`. Stop any consumers first; stopping
the service is terminal for this power cycle. The original kernel FIT and
bootloader binaries remain in place. A cold cycle is required before using
the old display/MIPS boot path again.

## Validation status

The bundle installation, unchanged FIT checksum, and managed terminal stop
passed on 2026-10-14. Native lifecycle tests include rejection of absent,
malformed, nonzero-status and zero-PID kernel handoffs. The saved startup environment retains rollback commands and the five-second
recovery window. A warm-reset test passed: GP6 persisted, no MIPS launch ran,
Linux booted, the kernel handoff was absent, and capture was skipped by its
condition. The complete SCP lifetime owner builds cleanly with W=1, and both
persistent units pass target systemd verification. Autonomous cold boot and
continuous HPD/capture validation are pending a physical cold cycle.

On 2026-10-14 the first autonomous cold boot reached the completed source-3
transition and then stopped at the bare-PID handoff (see above). With the fix
(evidence `docs/hdmi-evidence/2026-10-14-normal-startup/`):

- the corrected script, sourced from a confirmed cold prompt, booted Linux;
  capture and signal services started unattended (`resume-1/`);
- `update-startup-script.sh` installed it on the target FAT;
- active-recording poweroff passed the strict ordered check with the
  persistent signal owner, lamp/fan confirmed off (`poweroff-1/`);
- a fully autonomous cold autoboot (serial and USB unplugged) passed
  `tools/hdmi/check-startup.sh` and 48/32/44.1 kHz capture (`autonomous-1/`).

Tested scope is one board, two cold boots with the fixed script, one poweroff.
Not yet tested: HPD beyond long durations with the persistent owner, unplug /
replug, no-input boot, delayed source, source reboot; failure and ownership
cases (busy PCM, signal init/restore failure, partial update, missing or
corrupt script, rollback); warm reboot / fastboot / watchdog with the new
script; repeated cold boots. Open design items: review of the new
`h713-hdmi-signal` module (init-failure retention, refcounts, concurrent stop,
pinctrl error propagation), the policy when an ExecStop fails during poweroff
(systemd continues shutting down), pinned image size/ABI, firmware provenance
and rootfs/release integration. Only fixed 48 kHz stereo S16_LE capture with
32/44.1/48 kHz HDMI input is supported.
