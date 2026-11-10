# Save-path UART controller — offline preparation, October 31, 2026

**Prepared and tested; not armed or run against the board.** The operator
reports the board powered off. No board connection, UART transmission,
GPIO/latch operation, environment save, installation or reboot was performed
while preparing this controller. Historical Linux backups predate power-off.

The controller is [uboot-savepath.py](../../../../tools/serial/uboot-savepath.py),
with [offline tests](../../../../tools/serial/test-uboot-savepath.py).
The [complete validation protocol](../../../uboot-savepath-validation-2026-10-31.md)
defines the later two-phase test, protected storage and environment-only recovery.

## Offline coverage

46 tests pass, including five real Linux pseudo-terminal sessions: probe,
cleanup, corrupted command echo, disconnect at the save boundary, and refusal
of an existing reader. No actual serial adapter is used. Tests check paced
transmission, exclusive access, exact framing across arbitrary/one-byte chunks,
single-use output directories, durable save-attempt checkpoints and refusal
without sending a retry. Twelve deliberately faulty controller variants are
caught by behavioral tests. Import/CLI failures do not count as caught faults.

The protocol tests also reject wrong SPL/proper/load address, failed load,
repeated boot, missed countdown, an unexpected prompt, fan/device/card faults,
short reads, preimage/protected-slot CRC changes, changed startup variables,
unexpected runtime variables, duplicate RAM entries, wrong/missing/preexisting
nonce, changes after editing, failed native save, a second save attempt,
corrupted bootcmd echo, panic/reset, stale boot evidence, altered file pins,
protected bytes and unhealthy latches. Cleanup cannot open UART without a
completed probe result and verified post-probe Linux capture.

`uart-tests.txt`, `uart-mutations.txt` and `RESULT.json` record final results.
The original preparation's 8 native C cases, 17 semantic cases, 25 mutations
and sparse storage rehearsal remain separate evidence in the parent folder.
Simulation does not qualify a hardware environment save, power-loss behavior,
or hardware recovery. Linux storage/startup checks remain required after each
live phase even if the UART phase reaches login successfully.

## Sealed private package

`local/recovery/2026-10-31-uboot-savepath/uart-controller-package/` and
`uart-controller-package.tar.gz` contain the controller, tests, checker,
exact baseline packet, historical read-only capture, runbook, result/logs,
manifest and recursive SHA256SUMS. The baseline environment/firmware/CID
remain private and ignored. The original `final-packet/` is preserved and is
also archived as `final-packet.tar.gz`; no old migration package was modified.

Offline reproduction from the extracted controller package:

```sh
sha256sum -c SHA256SUMS
python3 uboot-savepath.py --packet baseline-packet
python3 test-uboot-savepath.py --packet baseline-packet \
  --capture offline-baseline-capture.tar
python3 test-uboot-savepath.py --packet baseline-packet \
  --capture offline-baseline-capture.tar --mutations
```

Run the pseudo-terminal tests on the full host. The sandbox's socket/PID
restrictions cause `fuser` audit warnings, which the controller refuses.
The final full test was run with host visibility, exclusively against PTYs.
Mutations and pure state tests require no board, network or installed packages.

## Later execution procedure — not authorized by preparation

The board is off. First agree on ordinary power-on into Linux and collect a
fresh read-only identity/storage/health capture plus the full startup/56-pin
check. Do not use the historical pre-power-off capture as live preflight.
Review the two native saves, two ordinary warm reboots, shared PB5 lamp/fan
action and no-retry failure policy with the operator. Follow the existing
timed-operation ready sequence before any live invocation or reboot.

Stop all recorder/console services and verify sole ownership in the full host
namespace. The controller opens only an explicitly supplied port at 115200
8N1, with `flock`, `TIOCEXCL`, `fuser` and duplicate-descriptor checks. It never
toggles modem-control lines, flushes buffered input or reconnects. Its default
is an offline plan; only `--execute-approved` selects live TX. That flag is a
mechanical guard and does not substitute for operator authorization.

After that separate authorization, phase A uses a new private output path:

```sh
python3 uboot-savepath.py --packet baseline-packet --phase probe \
  --preflight /path/to/fresh-preflight.tar --port /dev/serial/by-id/VERIFIED-UART \
  --output /path/to/new-probe-run --execute-approved
```

Wait for `ARMED`, then issue the separately authorized ordinary synced warm
reboot externally. The controller itself issues no reboot/power command. It
recognizes the pinned boot, sends one countdown-interrupt space, requires the
prompt, immediately sets PB5 high, validates identity/readbacks/RAM, adds the
nonce, checks the edited RAM, performs one native `env save`, reads/checks
both slots and continues with `run bootcmd`. It waits for shared handoff,
kernel start and Linux login. It uses neither GP7 stop nor `env export`.

Private run evidence includes actual RX/TX bytes, monotonic RX offsets and TX
intent events, durable `CHECKPOINT.json` before each transmit, and final
`RESULT.json`. A crash/disconnect at save is an ambiguous attempted write,
never permission to repeat it. The controller stops on failure; it does not
automatically boot, reset, clean up or restore. Preserve logs and follow the
reviewed continuation/recovery procedure; PB5 is shared lamp/fan, not a separate
fan line. Do not leave an unsafe PB5-low prompt hold.

Collect post-probe Linux storage and run the full startup/56-pin checks, then:

```sh
python3 uboot-savepath.py --packet baseline-packet \
  --verify-result /path/to/new-probe-run/RESULT.json \
  --preflight /path/to/post-probe-capture.tar
```

That offline verifier checks exact RAM-derived saved semantics, full image
CRC, UART CRC agreement, changed boot ID, all nine protected ranges and captured
health/file pins. Preserve this verified generation. Phase B uses the same
packet/nonce, `--phase cleanup`, `--probe-result` pointing to that completed
probe result, and `--preflight` pointing to its post-probe capture. Recheck
current boot identity immediately before arming; collect again if it changed.
Use a new cleanup output directory and another separately authorized warm
entry. The controller must observe the already-loaded nonce before deletion
and exactly one cleanup save. Verify cleanup with `--verify-result` and a new
post-cleanup capture plus full startup checks. No additional reset is included.

The current build lacks `hash`, `env info`, `env load` and `mmc reg read`.
The prompt uses supported MMC info/reads, `crc32` and full RAM snapshots;
Linux supplies full CID/capacity and SHA-256 verification. Only the source-
established control-FDT pointer initialization may differ from baseline.
