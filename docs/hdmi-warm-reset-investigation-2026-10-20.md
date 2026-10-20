# HDMI warm-reset investigation — 2026-10-20

Automatic warm-reboot HDMI recovery is a release requirement. This first pass
is a source/evidence investigation, with no board access, reset, installation,
or firmware retry. The completion plan was committed as `cc5421d` before this
investigation. A safe automatic recovery implementation is not established.

## Findings that change the recovery design

**The current warm path already executes temporary MIPS firmware.**
[build-startup.py](../tools/hdmi/build-startup.py) skips the sustained capture
launch on nonzero GP6, but if MIPS status is zero it invokes
`h713_disp auto 0x34 logo`. That runs firmware to application readiness and
then quiesces the core for ARM logo presentation. The
[October 18 emergency-reset serial trace](hdmi-evidence/2026-10-18-panel-initial-state-trial/abnormal-reset-01/serial.log)
records the latch branch, workspace clearing, firmware release, application
readiness, and explicit quiescence to reset/status zero. The
[Linux snapshot](hdmi-evidence/2026-10-18-panel-initial-state-trial/abnormal-reset-01/linux-after.txt)
then reports parked MIPS, no capture handoff, and three inactive HDMI units.

Consequently, Linux's parked observation cannot identify the state immediately
after watchdog reset. The warm branch's status-zero condition indicates a
parked core before logo initialization as well, but we still lack a register
census before SPL/BL31/U-Boot initialization. The older
[October 14 warm-reset trace](hdmi-evidence/2026-10-14-normal-startup/activation/09-warm-reset.log)
belongs to an earlier script and must not describe the current logo path.
Temporary logo success does not prove that source3, DSP patch initialization,
or retained SCP/receiver state can be restarted safely.

**Terminal parking is not a reset of every HDMI subsystem.**
[h713-receiver-park.c](../modules/hdmi-receiver/h713-receiver-park.c)
asserts CCU MIPS/DBG/CFG reset IDs 1/2/3, verifies them, polls MIPS status zero
for up to 20 ms, and releases its two MIPS clock holds. These are the MIPS
resets at CCU offset `0x60c`, bits 16/17/18. It does not establish a DSP,
receiver, or whole-TVCAP reset. The
[parked-handoff evidence](hdmi-evidence/2026-10-14-parked-handoff/README.md)
records TVFE off but TVCAP still on under its boot-retention policy. Releasing
domain references therefore cannot be equated with removing all HDMI power.

**Audio restoration deliberately leaves the volatile DSP patch in place.**
[h713-hdmi-dsp.c](../modules/hdmi-audio/h713-hdmi-dsp.c) requires logical
version words `0x80ff` on both devices to be `0/0` before loading the pinned
patch, and verifies `1/1` afterward. Release restores 22 graph words; it does
not undo the patch. Historical
[October 8 teardown](hdmi-evidence/2026-10-08-audio-rate-test/attempt2/README.md)
explicitly records that distinction. Whether an orderly or abrupt system
reset restores DSP `0/0` is unmeasured in the evidence reviewed here.

There are additional preconditions:
[TVFE setup](../modules/hdmi-audio/h713-hdmi-tvfe.c) rejects inherited demod
reset/bus bits, while the
[DSP lock](../modules/hdmi-dsp-probe/h713-dsp-lock.h) refuses an existing ARM
claim and never steals a peer claim. A new Linux process or module lifetime
does not prove that either hardware condition has become fresh.

**Shutdown failure is intentionally not followed by warm reboot.**
The persistent capture unit calls session `shutdown`, which requires signal
restoration, audio restoration, parking, and receiver release. The final
[hold guard](../tools/hdmi/h713-hdmi-hold-guard) converts reboot/kexec into
poweroff if HDMI owners remain loaded. This must remain intact until a proven
recovery path can handle those states. A retained “clean shutdown” marker alone
would not handle abrupt reset or establish fresh hardware state.

## Reset path and provenance

The normal U-Boot build uses source pin
`320a17f71d41ed0d4be7aab25947ce015c98c48e` plus the curated patch series.
The local submodule checkout is `9d35a4e`, which has extra capture tracing;
do not confuse it with the installed trial or the normal source pin. The
MIPS stop/release and auto-logo sequences discussed above were cross-checked
against the pinned source. U-Boot's stop primitive asserts MIPS reset and
gates its clock; release uses staged reset writes and shared-memory setup.
Neither primitive alone is a full receiver/audio reset contract.

The U-Boot defconfig selects PSCI system reset. TF-A checkout
`47ee829f745f7c87273192b26c92dbd8f78b4ab1` implements native system reset
through the key-protected H713 watchdog: configuration at `0x02051010`, mode
at `0x02051014`, key `0x16aa0000`, shortest timeout. Its source comment says
“whole system”; that does not prove which peripheral state or rails are
actually reset. Establish the installed BL31 identity before relying on this
source description. Kernel patch 0186 corrects the Linux watchdog layout,
but actual autonomous watchdog-expiry recovery remains a separate test.

The out-of-series PL6 poweroff patch 0177 records a negative result: dropping
PL6 rebooted the board as the line returned to its reset default. It is not
a demonstrated automatic cold-cycle substitute. Do not revive it as a reset
fix without a separate power-control design.

## State census needed before changing policy

| State | What is known | Missing measurement |
| --- | --- | --- |
| GP6 at `0x07090118`; GP7 reboot mode at `0x0709011c` | GP6 retains the launch latch across warm reset; GP7 has its own established purpose. | Capture exact values at every phase; never clear GP6 or repurpose GP7 to make a trial proceed. |
| MIPS clock/reset/status: `0x02001600`, `0x0200160c`, `0x0306101c` | Kernel parking verifies reset and status zero. Warm logo releases and quiesces firmware again. | Earliest safe post-reset snapshot before logo/workspace changes; distinguish reset hardware effects from bootloader effects. |
| DSP versions, graph, lock, busy/done state | Patch initialization is one-shot from `0/0`; graph restore is narrower than patch removal. | Determine whether reset returns versions/locks to baseline, and which domain owns that reset. No speculative DSP command on a skipped warm boot. |
| TVFE/TVCAP and demod clocks/reset | Managed ownership and restoration exist; TVCAP stayed powered in terminal-parking evidence. | Compare domain and bus/reset state before shutdown, after shutdown, and before/after bootloader initialization. |
| SCP reset/SRAM, HPD/DDC ownership | Signal stop verifies peripheral restore, stops SCP, then restores SRAM and vectors. | Abrupt-reset behavior before old payload memory is overwritten. Determine when reset stops SCP and whether HPD/DDC state survives. |
| Firmware workspace/CPU_COMM/trace | Boot initialization clears and republishes workspace/shared state; PIDs are discovered per launch. | Fresh-generation evidence after warm recovery; old canaries, PIDs, and runtime JSON cannot authorize adoption. |

These addresses identify reviewed code paths, not a raw-memory probing script.
Receiver MMIO can wedge the interconnect without the complete powered clock
tree. Even DSP version reads issue protocol traffic. Use existing safe owner
interfaces and passive firmware trace where possible; justify each additional
register read against its domain/clock state before adding instrumentation.

The new [Linux state collector](../tools/hdmi/collect-reset-state.py) captures
boot ID, handoff bytes, session state, selected module parameters, ALSA status,
domain runtime status, unit properties, current/previous unit journals, and
kernel logs. It performs no MMIO, RPC, module/service mutation, or reset.
It emits missing/error fields and always labels hardware reset state unknown.
It is a non-atomic snapshot; compare its start/end times and boot ID. It cannot
recover pre-logo state or prove DSP freshness.

For a later board session, stream it over the existing connection and save
stdout on the host, for example:

```sh
ssh -F /dev/null -o BatchMode=yes -o ConnectTimeout=5 root@192.168.4.1 \
  'python3 -' < tools/hdmi/collect-reset-state.py > /tmp/hdmi-reset-state.json
```

No board collection was run in this investigation. The collector tolerates
absent services and journals, unlike the production startup checker which
correctly fails immediately when a warm boot has no capture handoff.

## Next experiment and implementation decision

1. Inventory the board's installed boot script/environment, SPL, BL31, proper,
   FIT, and modules; correlate hashes with the recorded trial and rescue
   layout. Collect a Linux snapshot and passive UART without modifying state.
2. Prepare boot instrumentation at a precisely identified stage before logo
   and workspace initialization. First audit SPL/BL31 and any earlier clock,
   reset, or DRAM changes; an interrupted U-Boot prompt is not necessarily
   reset-entry state. Preserve the normal boot path, recovery window, latch,
   and previous artifacts. Add only reviewed, powered-window readbacks.
3. From a known cold baseline, compare one clean-teardown reboot and one
   abrupt reset using the same artifacts and source conditions. Preserve the
   pre-reset logs and the earliest post-reset trace. Do not add an extra MIPS
   launch or DSP probe merely to fill a missing observation. Observe actual
   watchdog expiry separately after the emergency-reset path is understood.
4. Select a mechanism from measured results: a verified fresh reset and new
   launch, or an explicitly validated retained-state adoption protocol. Start
   with orderly reboot, but require recovery independent of successful
   shutdown for the abrupt-reset gate. If reset domains cannot restore a
   usable baseline, escalate to firmware/power-control design rather than
   relaxing version/lock guards.

The preferred first hypothesis is a fresh-reset path, because the current
software already authenticates and initializes a fresh session. That is a
design preference, not evidence that the watchdog resets every required
domain. Retained adoption would need patch identity, graph/lock consistency,
IPC generation and DMA ownership checks that the current version `1/1` test
does not supply. Simply accepting `1/1` is insufficient.

Only after proving that contract should a new boot protocol permit the warm
source-3 handoff. It needs bounded readiness, fresh PID/trace checks, verified
DSP policy, and failure behavior that preserves protective holds. Do not clear
GP6, retry latched operations, remove the hold guard, or change production
boot policy as part of this evidence-gathering pass.
