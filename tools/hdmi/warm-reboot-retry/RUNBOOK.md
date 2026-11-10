# Warm-reboot retry of the HDMI first-advert test

Same test as the [warm-reboot repeat](../warm-reboot-test/RUNBOOK.md): one warm host reboot and no
host poweroff. That run (board boot `1239d8ee`) was `INVALID` only because the board was powered
on 139 s after the off-time limit. It also did not detect. This retry changes no condition; it
only makes the deadline harder to miss.

**Prepared offline only. Nothing here has run against the board or the host's recorders.**
Each live stage needs `--live` and the owner's go-ahead. The board config is not changed; the
0 ms override stays installed. `../host-reboot-test/` and `../warm-reboot-test/` are the frozen packets of the earlier runs.

The host reboot ends every Claude session on this machine. The board is off by then, and
receipts in `local/recovery/2026-11-02-hdmi-warm-reboot-retry/` let a new session continue from `arm-post`.

## Conditions

Keep the HDMI cable and UART adapter connected throughout. No reseat, display setting change,
forced detection, U-Boot prompt or extra board power cycle once `arm-pre` has run. Board off 8 to
20 minutes from `Power down` to the first SPL line; `ready` refuses outside that.

**Restart the host with `systemctl reboot` in a terminal, once. Do not use the desktop's power
dialog, and do not power the host off at any point between `poweroff` and `close`.** `arm-post`
refuses unless the previous host boot ended in a requested reboot with no poweroff request. That
is a single-use refusal for this run directory: a host poweroff ends the run.

## Setup: reach a locked board

`arm-pre` needs the host connected, and `preflight` needs HDMI locked. The repeat left the board
up in its failed state (signal `none`), and the host has not connected in its current boot.

1. A board warm reboot over ssh restores detection: it did on 2026-11-01, connecting 52 s
   after the command, with no reseat. It is a recovery step and needs its own go-ahead.
2. If it does not connect, stop and decide. Do not reseat without a decision.
3. Connected with the expected EDID and the board `locked`: continue to the stages.

## Timing

The board must reach its first SPL line 480 to 1200 s after `Power down`. A host reboot and login
took about 6 minutes last time, so `ready` passes soon after login. **Power the board on as soon
as `ready` passes.** `ready` prints the deadline as `power_on_by_local`; past it, the run is `INVALID`.

## Stages

Before the reboot, in order:

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py arm-pre --live
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py preflight --live
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py poweroff --live
```

Operator, after `poweroff` passes:

1. Remove the board's supply. Leave every cable in place.
2. In a terminal on the host, run `systemctl reboot` once and log in to the desktop. Do not power the board yet.

After login, in the repository:

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py arm-post --live --supply-removed
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py ready --live
```

Operator, after `ready` passes: power the board on once, right away, and touch nothing else. Then:

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py observe --live
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py collect --live
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py analyze
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py close --live
```

If a stage refuses, stop and read why. Do not delete receipts to retry; stages are single-use.

## Reading the result

| Result | What it means | Next |
| --- | --- | --- |
| Not detected | A full host poweroff is not needed to reproduce the failure; one warm reboot is enough | Preserve the state; decide before any recovery |
| Detected | A strict first-advert rule is refuted, and the poweroff stays a candidate | Same test with a full host poweroff alone |
| Any `INVALID` | A matched condition did not hold; the run decides nothing | Fix the condition, new run directory |

The EDID RAM reading is the same as in the earlier runbook. Identical backups with "not detected"
point away from rail discharge and toward host state; about 9% of bits differing leaves them unseparated.

## Changes from the repeat's packet

* Run directory, recorder unit names and the board's poweroff receipt are named after this run.
  The repeat's receipt is still on the board and is exclusive, so a shared name would have made
  `poweroff` fail after its gates. One `TAG` constant in `run.py` now sets all three.
* `ready` records and prints the latest power-on time.
* No condition, gate or conclusion changed.

## What this cannot show

One run gives no failure rate, and comparing two single runs gives a candidate, not a cause. The
UART stays wired, so this is not a fully cold start. A warm host reboot may or may not drop GPU
+5 V and USB power. HPD voltage and DDC traffic stay unobserved. The earlier host had been up for
hours before its reboot, and this one may not have been, because uptime is not controlled.

## Offline checks

No hardware; the evidence tests need the ignored `local/recovery/` data and fail without it.

```bash
python3 -B tools/hdmi/warm-reboot-retry/run.py check
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/test_warm_reboot.py
```

```bash
python3 -B tools/hdmi/warm-reboot-retry/test_mutations.py
```
