# Native U-Boot save-path validation — preparation, October 31, 2026

**Completed November 2: PASS.** Two native saves and two ordinary warm boots
proved save at the corrected slot, reload of the temporary marker, and its
removal. Both Linux storage/startup verifications pass; all nine protected
regions, 59 installed file checks and captured bytes outside the slot are
unchanged. Board left running with HDMI locked at 1280×720; UART released.
The first countdown parser stop attempted no save; an explicitly approved
held-prompt continuation completed the probe without another reboot.
[Final evidence, accepted environment hash and qualifications](hdmi-evidence/2026-11-02-uboot-savepath/README.md).
The remaining preparation and earlier board-state entries below are history.

**Latest board boot, November 1:** boot `afe48e93-6604-44de-a220-acb9416e8363`
loads the migrated environment OK and passes normal startup plus all 56 file
pins. HDMI no-detection has reproduced: board signal none, zero transitions/
frames, host disconnected with no EDID. No recovery, save or extra reboot.
Save-path readiness remains on hold. [Fresh UART and read-only board evidence](hdmi-evidence/2026-11-01-board-boot/README.md).
The powered-off and host-investigation endpoints below are historical.

**Latest operator state:** the board was powered off, ending the captured HDMI
failure/SCP session. Host NVIDIA reader v2 is prepared/tested; no live GPU ioctl
or board action ran. [Reader and qualification](nvidia-cache-reader-2026-10-31.md).
Any later save-path work requires a new normal boot and fresh read-only board
preflight; the old boot-bound SCP packet is historical.

**Latest: one guarded SCP capture PASS.** All 14 reads and fresh return proof
passed, followed by read-only SRAM/identity/56-pin verification. The HDMI bad
state remains unchanged. The companion is now resident and holds the owner's
parameter mutex: do not read original owner parameters, run ordinary startup
checks, repeat capture or unload/reset as cleanup. No preservation release or
reboot occurred. [Evidence and retained endpoint](hdmi-evidence/2026-10-31-scp-capture-live/README.md).
The preparation-only entries below are historical.

**SCP sampler v2:** a replacement is built against the exact running kernel,
tested offline, and packaged for a separately authorized guarded capture. It
uses owner-stop serialization, pre-entry synchronization and fresh return
challenges, retaining scratch and the owner lock on success or ambiguity. No
probe was loaded. Final read-only checks confirm the same boot, identical SRAM,
all 56 file pins and unchanged no-signal state. [Package, tests and lifecycle
constraints](hdmi-evidence/2026-10-31-scp-capture-v2/README.md).

**Earlier SCP safety review:** the first sampling prototype is **NO-GO for live
insertion**. Adversarial tests show its completion marker precedes context
restore/return, and expose unresolved instruction-fetch and owner-stop
coordination requirements. That prototype remains blocked; no injection occurred.
The current bad state and SCP SRAM remain unchanged. [Review, tests and closed
execution gate](hdmi-evidence/2026-10-31-scp-capture-safety/README.md).

**HDMI investigation:** keep the current no-signal state intact. The GPU
reports HDMI-A-1 disconnected with no EDID; the SCP program/payload and DDC
mux validate, but initialization-ready flags do not prove live HPD/DDC state.
The operator explicitly rejected reseating as it erases the bad state and
requested software-only diagnosis. No reseat, HPD pulse, service restart,
SCP/board reset or live instrumentation occurred. [Evidence and remaining
measurement](hdmi-evidence/2026-10-31-hdmi-discovery/README.md).

**Latest fresh preflight:** the operator powered on into Linux boot
`2d8c3970-4164-4a38-8e86-375bb440c971`. Identity, both environments, nine
protected ranges, GPTs, all 56 file pins and automatic startup pass. Live
readiness is **HOLD**: HDMI signal is `none` and the video service has not
started; the prepared controller's six-active-service gate rejects this
capture. No service was started and no gate was waived. No UART arming,
environment save or reboot occurred. [Fresh evidence and next condition](hdmi-evidence/2026-10-31-uboot-savepath-preflight-01/README.md).
Power-off/preparation statements below describe the preceding checkpoint.

**Prepared and checked offline; no hardware save, UART command, latch change
or reboot performed.** Fresh read-only backups match warm boot
`b6849123-0398-4736-b06f-cfe25b19e593`. That capture predates the operator's
subsequent power-off. **The board is now off, per the operator; the UART
controller is prepared and tested offline, not armed.** A fresh normal Linux
boot and read-only preflight are required before the proposed warm sequence.
Actual execution requires the separately requested operator-ready sequence;
preparation does not authorize either environment save.

## Goal and boundaries

Prove native U-Boot `env save` writes exactly 128 sectors/65536 bytes at LBA
`0x49ec00` (byte `0x93d80000`) on eMMC user device 1, then demonstrate reload
and remove the test key. Linux `fw_setenv`, raw `mmc write` or a memory-only
`env set` cannot substitute for native-save qualification.

The proposed hardware sequence has **two controlled warm entries and two
native saves**: temporary probe, then cleanup. Each entry ends with `run
bootcmd`, allowing the same boot to continue into Linux; do not add a `reset`
at the prompt. A failure stops the sequence without automatic retry, cleanup
or recovery. Old environment in `super` at LBA `0x32ec00` remains untouched.
New proper is now protected in addition to the original eight protected
ranges: **nine protected ranges, one mutable environment slot**.

## Backups and offline results

Private durable directory: `local/recovery/2026-10-31-uboot-savepath/`.
`read-only-backup.tar` contains fresh raw ranges, GPTs, SPL, proper, rescue,
both environments, intended-slot margins, full boot FAT and private identity.
Current environment has 72 entries, valid CRC, no `h713_savepath_probe` and
the accepted guard values. Both copies still have SHA-256
`6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc`.

`final-packet/` contains exact `environment-before.bin`, nine protected-region
backups/hashes, copied source/config/provenance, a unique nonce, an offline
semantic checker, host source tests and corrected **environment-only** recovery
instructions. `model-*-NOT-FOR-INSTALL.bin` files are synthetic test fixtures,
not payloads to flash. `final-packet.tar.gz` preserves the final packet.

Eight cases compile and exercise the actual `mmc_offset`, `mmc_get_env_addr`,
sunxi `mmc_get_env_dev`, `write_env`, `env_mmc_save` and `env_export` routines
against fake MMC callbacks and regular host sparse images. Device selection,
high absolute fallback with missing DT property, exact extent, body CRC,
initialization/export/offset failures, short/zero writes and final partition
restoration callbacks pass. Ten native-save mutations are caught, and every
case fails under a relevant fault. Environment hash-table serialization and
MMC initialization/partition switching use stubs; no real block driver or
hardware save is exercised by those tests.

Seventeen offline semantic checks pass; 15 faulty validators are caught.
They reject invalid size/CRC/termination/duplicate keys, changed boot guards
or `bootdelay`, a preexisting/wrong nonce, unapproved RAM drift, failed cleanup
and invalid control-FDT metadata. A sparse full-geometry rehearsal applies
probe/cleanup models, compares all potentially nonzero bytes outside the slot
and verifies nine protected regions. Writes into the old environment and
adjacent margin are deliberately caught on host fixtures only.

[Preparation evidence](hdmi-evidence/2026-10-31-uboot-savepath/README.md).

## Installed command and RAM-state constraints

The pinned installed configuration enables `env save`, `env print`, `env
exists`, GPIO, MMC, memory compare and `crc32`. It **does not enable** `hash`,
`env info` or `env load`; do not use those as validation/recovery gates.
`CONFIG_ENV_REDUNDANT` is off and `CONFIG_ENV_SIZE=0x10000`.

Do not use the GP7 boot-stop for this test. Its saved `preboot` sets RAM
`bootdelay=-1` after consuming that stop request, and a subsequent save could
persist the prompt hold. Interrupt the ordinary five-second autoboot countdown
through the sole UART controller instead. Verify `bootdelay=5` before saving;
any unplanned variable change is a refusal, not something to normalize blindly.

Do not use `env export` to manufacture an expected image before saving:
`cmd/nvedit.c` changes `filesize` after export, which would itself change the
saved environment. Capture `env print -a` privately instead. All current values
are newline-free. Convert the delimited RAM transcript to a private map and
require every backup key/value to remain exact except the source-established
`fdtcontroladdr` initialization in `common/board_r.c`. A changed control address
must be an eight-digit DRAM address in `[0x40000000,0x80000000)`, observed in the
current prompt snapshot, not guessed or set by the controller. The installed
`CONFIG_VERSION_VARIABLE` is off: do not blanket-allow `ver`, `filesize`,
`fileaddr`, boot commands, bootdelay or other runtime differences.

Semantic comparison is independent of serialization order/padding. The saved
image still must be exactly 64 KiB with valid little-endian CRC32 over the
remaining 65532 bytes. Require native `env save` success too: a reported short
write is a failure even if unchanged padding makes the resulting bytes look
valid. No automatic second save on error.

## Proposed later hardware sequence

Before each warm entry, recheck current identity, exact before-generation,
source build and storage hashes, clean filesystem/health, HDOK/GP7 zero, no
cold-only diagnostics, operator readiness and recovery availability. Use one
controller owning both UART receive and paced transmit; never run it beside
a competing passive reader. It must capture complete command echoes/replies
and gate every state; never type U-Boot commands into an unrecognized prompt.
The controller and its transcript/state handling are now tested offline;
see [controller usage and test evidence](hdmi-evidence/2026-10-31-uboot-savepath/uart-controller/README.md).
It is not deployed or armed. It never issues a reboot or power command.

### A. Save a unique harmless probe and verify its storage

1. One normal, synced warm reboot; interrupt only the installed autoboot
   countdown. Verify expected proper banner and environment-load address/OK
   before accepting `=>`. No GP6/GP7 arming, RAM boot script or forced reset.
2. Apply the established manual-prompt lamp/fan policy immediately: `gpio set
   PB5` enables the **shared lamp and fan** line. This is an explicit panel/
   GPIO action to include in later authorization, not a separate fan control.
   Do not dwell with PB5 low. Budget the prevalidated prompt interaction and
   do not leave the operator waiting at an unsafe held prompt.
3. `version`, `mmc dev 1 0`, `mmc info`, then a delimited private `env print -a`.
   Confirm eMMC/user-area identity, marker absent, exact saved boot guards,
   `bootdelay=5`, and only the permitted control-FDT initialization delta.
   Stop before saving if snapshot conversion or validation is incomplete.
4. `env set h713_savepath_probe <packet nonce>` followed by **one** `env save`.
   Require native success/`Writing to MMC(1)... OK` and a proper prompt return.
   Do not change any startup-policy key or save an unknown RAM generation.
5. Supported raw read/checks at the prompt:

   ```text
   mmc read 0x42000000 0x49ec00 0x80
   crc32 0x42000000 0x10000
   mmc read 0x43000000 0x32ec00 0x80
   crc32 0x43000000 0x10000
   ```

   Record intended-slot whole-image CRC; the old slot's whole-image CRC must
   match the private backup. CRC32 is transport/readback evidence, not a
   cryptographic substitution for subsequent host SHA-256 comparisons.
6. Continue with `run bootcmd`, not another reset. From Linux, collect the
   new raw environment and protected storage read-only. Validate CRC, unique
   nonce and exact saved map against the captured RAM snapshot plus probe.
   All nine protected ranges, every other variable, startup guards, storage/
   runtime/calibration checks must pass before proceeding to cleanup.

### B. Prove reload, remove the probe and verify cleanup

1. A second normal, synced warm entry; capture corrected-address environment
   load/OK and interrupt countdown as above. Establish the same fan/prompt and
   identity gates. Before setting or deleting anything, capture the RAM map
   and **observe the exact nonce already loaded from storage**.
2. Validate that map against backup/probe and permitted FDT initialization.
   `env delete h713_savepath_probe`, then **one** `env save`. Require success;
   read/check both slots as above and continue with `run bootcmd`.
3. Read-only Linux verification must show marker absent, valid CRC and original
   semantics except permitted control-FDT metadata, old `super` copy unchanged,
   nine protected ranges unchanged, and healthy startup. Preserve cleanup
   bytes as the newly accepted generation; do not claim byte-identical cleanup
   if legitimate serialization/FDT metadata differs. No extra reboot is part
   of the proposed sequence. A subsequent independent cleanup reload test can
   be separately planned if needed.

## Failure and environment-only recovery

On CRC/status/address/identity/protected-data mismatch, unexpected console
input, guard poweroff, non-return, altered policy or missing reload proof,
stop and preserve logs. Never force through a guard, repeat `env save`, edit
boot policy, reset again or restore the old diagnostic proper automatically.
A test nonce left after a stopped phase is harmless to boot policy but must
be reported and cleaned up only under the reviewed continuation/recovery.

`ENV-ONLY-RECOVERY.txt` pins the **current filled environment** backup, not the
zero-filled pre-migration slot. It bounds a potential restore to 128 sectors
at `0x49ec00`, with eMMC identity, host SHA-256, UART transfer size/CRC32 and
exact RAM/disk compare before continuation. New proper, GPT/SPL, rescue, boot
FAT and old environment stay protected. Current proper lacks the `hash`
command; older sealed recovery notes using it are not executable instructions
for this prompt without checking that recovery image's command capabilities.
The new packet uses supported `crc32`/`cmp.b` and independent host SHA-256.
Hardware restoration and FEL entry remain separately authorized, unexecuted
fallbacks; none is required or attempted for preparation.

## Prepared UART controller

`tools/serial/uboot-savepath.py` defaults to an offline plan. Its live mode
performs exactly one phase and at most one native save, then continues the
same boot and records Linux login. This is UART completion, not a storage or
startup verdict; the separate offline `--verify-result` consumes a fresh Linux
read-only capture and checks saved CRC/semantics, UART readback CRC, a changed
boot ID, all nine protected ranges, 50 captured installed file/metadata pins,
four bundle manifests, six active services, error counters and filesystem.
The broader 56-pin and full `check-startup.sh` checks remain required externally.

Every command has a unique status token inside a Hush `if` statement, complete
echo validation and an exact prompt boundary. The controller checks PB5 high,
version, MMC user device/card details, preimage and old-slot CRCs, full RAM map,
the edited RAM map, native save status, readback extent and CRC. Cleanup requires
the completed probe UART result and its verified Linux capture before opening
UART, and then observes the nonce loaded into RAM before deleting anything.
`mmc reg read` is also disabled in this build; full CID/capacity identity comes
from Linux preflight, while supported `mmc info` and slot CRCs gate the prompt.
Backslashes doubled by native `env print` are decoded; multiline values are
unsupported and refused rather than guessed.

Live acquisition requires an explicit UART path, execution flag and a new
private output directory. It uses `flock`, `TIOCEXCL`, an existing-owner audit
with host `fuser`, and rejects duplicate descriptors. Run on the full host:
a restricted PID namespace cannot prove that another reader is absent. Stop
all existing recorder/console services first. It paces TX at 2 ms per byte,
records private RX/TX plus a durable checkpoint before transmission, uses
180-second boot/Linux, 5-second interrupt, 15-second command and 120-second
total prompt limits, and refuses reconnect/retry/recovery after a failure.
No MMIO command, raw storage write, GP6/GP7 operation or automatic second save
exists in its command path. PB5 high is an intentional later live action.

Do not arm from the present powered-off state under this warm-test plan.
First obtain operator readiness for ordinary power-on into Linux, collect a
fresh current-boot backup/preflight and full startup check, and review the
separate timed run authorization. The previous powered-on capture is useful
offline evidence but cannot establish current hardware state after power-off.
