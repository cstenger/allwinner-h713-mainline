# Host-reboot test of the HDMI first-advert hypothesis

Repeats the 0 ms cold run (boot `275f5bce`) with one change: one warm host reboot while
the board is off. Why: [the review of the first-detection handoff](../../../docs/handoff-2026-11-01-hdmi-detection-for-claude.md)
found every failure was the board's first HDMI advert in a host boot, aliased with the
production wrapper and long board-off.

**Prepared offline only. Nothing here has run against the board or the host's recorders.**
Each live stage needs `--live` and the owner's go-ahead. The board config is not changed;
the 0 ms override stays installed. The only board change is one orderly poweroff and its receipt.

The host reboot ends every Claude session on this machine. The board is off by then, so
nothing is lost, and receipts in `local/recovery/2026-11-01-hdmi-host-reboot-test/` let a
new session continue from `arm-post`.

## Conditions

Keep the HDMI cable and UART adapter connected throughout. No reseat, display setting change,
forced detection, U-Boot prompt or extra board power cycle. Board off 8 to 20 minutes from
`Power down` to the first SPL line; `ready` refuses outside that.

## Stages

Before the reboot, in order:

```bash
python3 -B tools/hdmi/host-reboot-test/run.py arm-pre --live
```

```bash
python3 -B tools/hdmi/host-reboot-test/run.py preflight --live
```

```bash
python3 -B tools/hdmi/host-reboot-test/run.py poweroff --live
```

Preflight is read-only: identity, 56 file pins, 5 bench files, 10 storage regions, loaded 0 ms
ExecStart, ext4 health, HDMI locked, and SRAM snapshot S0. If the last, unrecorded abrupt cycle
left anything wrong, it refuses here. Poweroff repeats every gate, then issues one
`systemctl poweroff`, and waits for `Power down` on the UART and a host disconnect.

Operator, after `poweroff` passes:

1. Remove the board's supply. Leave every cable in place.
2. On the host, run `systemctl reboot` once and log in to the desktop. Do not power the board yet.

After login, in the repository:

```bash
python3 -B tools/hdmi/host-reboot-test/run.py arm-post --live --supply-removed
```

```bash
python3 -B tools/hdmi/host-reboot-test/run.py ready --live
```

`arm-post` refuses unless there was exactly one host reboot, this host boot has no HDMI connect
yet, and the host shows disconnected with an empty EDID. `ready` tells you if it is too early.

Operator, after `ready` passes: power the board on once and touch nothing else. Then:

```bash
python3 -B tools/hdmi/host-reboot-test/run.py observe --live
```

```bash
python3 -B tools/hdmi/host-reboot-test/run.py collect --live
```

```bash
python3 -B tools/hdmi/host-reboot-test/run.py analyze
```

```bash
python3 -B tools/hdmi/host-reboot-test/run.py close --live
```

`observe` decides detection from host data only: a connect, or none by 120 s after login.
`collect` is read-only and takes snapshot S1 whatever the outcome. `analyze` writes the
conclusion to `STAGE-analyze.json`. `close` stops recorders and seals the run.

If a stage refuses, stop and read why. Do not delete receipts to retry; stages are single-use.

## Deviation in the 2026-11-01 run

The owner deliberately powered the host off after the reboot and login (boot `57af4476`), so
`arm-post` ran with `--declared-host-poweroff-boot`. The receipt and `analyze` limits record it.
This run is not a matched repeat of `275f5bce`: read host-reboot results below as "the host restart path".

## Reading the result

| Result | What it means | Next |
| --- | --- | --- |
| Not detected | 0 ms bench, about the same off time and an orderly shutdown are not enough to explain the failure. The cause lies in what a host reboot changes. | Preserve the state; decide before any recovery |
| Detected at about ready + 0.86 s, lock at ready + 1.31 s | A strict first-advert rule is refuted; a failure rate is not | Same test with a 7 h board-off and no host reboot |
| Any `INVALID` | A matched condition did not hold; the run decides nothing | Fix the condition, new run directory |

EDID RAM, from the SCP's bank backups in S0 and S1 (`0x4780..0x4a7f`). The orderly stop writes
S0's backups back to the banks, and the next boot's SCP backs them up again:

* Identical: the RAM kept power through the off period. With "not detected", this points away
  from rail discharge and toward host state.
* About 9% of bits differ: the same as the known power loss between `2d8c3970` and `afe48e93`.
  Host state and rail discharge stay unseparated. A reset clearing the RAM would look similar.

`udevadm monitor --kernel` runs in both phases. The poweroff disconnect is its positive control:
if no DRM uevent appears there, a missing uevent on the first advert means nothing.

## What this cannot show

One run gives no failure rate. The UART stays wired, so this is not a fully cold start by the
project's own definition. A warm host reboot may or may not drop GPU +5 V and USB power. HPD
voltage and DDC traffic on the wire stay unobserved.

## Offline checks

No hardware; the evidence tests need the ignored `local/recovery/` data and fail without it.

```bash
python3 -B tools/hdmi/host-reboot-test/run.py check
```

```bash
python3 -B tools/hdmi/host-reboot-test/test_host_reboot.py
```

```bash
python3 -B tools/hdmi/host-reboot-test/test_mutations.py
```

Not provable offline, and fail-closed if wrong: `/sys/fs/ext4/*/errors_count` exists on the board,
and the `systemd-run`, `fuser` and `udevadm` recorder start-up behaves as in the earlier runs
(`udevadm monitor --kernel` itself was started once on this host as an ordinary user).
