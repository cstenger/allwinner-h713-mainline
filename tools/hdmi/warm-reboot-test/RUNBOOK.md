# Warm-reboot repeat of the HDMI first-advert test

The [host-reboot run](../host-reboot-test/RUNBOOK.md) failed to detect (board boot `b3cf2171`),
but its host went through a warm reboot and then a full poweroff (boot `57af4476`). This run
keeps everything else and has **one warm reboot and no host poweroff**, to separate the two.

**Prepared offline only. Nothing here has run against the board or the host's recorders.**
Each live stage needs `--live` and the owner's go-ahead. The board config is not changed; the
0 ms override stays installed. `../host-reboot-test/` is the frozen packet of the earlier run.

The host reboot ends every Claude session on this machine. The board is off by then, and
receipts in `local/recovery/2026-11-01-hdmi-warm-reboot-test/` let a new session continue from `arm-post`.

## Conditions

Keep the HDMI cable and UART adapter connected throughout. No reseat, display setting change,
forced detection, U-Boot prompt or extra board power cycle once `arm-pre` has run. Board off 8 to
20 minutes from `Power down` to the first SPL line; `ready` refuses outside that.

**Restart the host with `systemctl reboot` in a terminal, once. Do not use the desktop's power
dialog, and do not power the host off at any point between `poweroff` and `close`.** `arm-post`
refuses unless the previous host boot ended in a requested reboot with no poweroff request. That
is a single-use refusal for this run directory: a host poweroff ends the run.

## Setup: reach a locked board

`arm-pre` needs the host connected, and `preflight` needs HDMI locked. Both host and board have
been off for hours, so the first step is a board power-on in a fresh host boot. That is the
condition that has failed before, so it may fail here. It is outside the matched part of the run.

1. Operator: power the board on once and touch nothing else.
2. Read the outcome. The journal line is the only record of this advert, so note it either way:

```bash
journalctl -b 0 --no-pager -o short-iso | grep 's-monitors: HDMI'
```

3. Connected: continue to the stages. Not connected: stop and decide. A board warm reboot has
   brought detection back without a reseat before, but it is a recovery step and needs its own
   go-ahead. It is preferred over a reseat, which is the known workaround and changes the cable state.

## Stages

Before the reboot, in order:

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py arm-pre --live
```

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py preflight --live
```

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py poweroff --live
```

Operator, after `poweroff` passes:

1. Remove the board's supply. Leave every cable in place.
2. In a terminal on the host, run `systemctl reboot` once and log in to the desktop. Do not power the board yet.

After login, in the repository:

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py arm-post --live --supply-removed
```

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py ready --live
```

Operator, after `ready` passes: power the board on once and touch nothing else. Then:

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py observe --live
```

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py collect --live
```

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py analyze
```

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py close --live
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

## Changes from the earlier packet

* `arm-post` reads the previous host boot's journal and refuses a poweroff request or an unrequested restart.
* The board poweroff receipt has a new name. The earlier receipt is still on the board and is
  created exclusively, so reusing the name would have made `poweroff` fail after its gates.
* `collect` asks for the previous board boot by id. `-b -1` returned the current boot's lines in
  the earlier run, which is why `prior_stop_restored` was false there. The fix is not proven until
  this run, and the check stays outside the validity gate.
* The default run directory, recorder unit names and conclusions are this run's.

## What this cannot show

One run gives no failure rate, and comparing two single runs gives a candidate, not a cause. The
UART stays wired, so this is not a fully cold start. A warm host reboot may or may not drop GPU
+5 V and USB power. HPD voltage and DDC traffic stay unobserved. The earlier host had been up for
hours before its reboot, and this one may not have been, because uptime is not controlled.

## Offline checks

No hardware; the evidence tests need the ignored `local/recovery/` data and fail without it.

```bash
python3 -B tools/hdmi/warm-reboot-test/run.py check
```

```bash
python3 -B tools/hdmi/warm-reboot-test/test_warm_reboot.py
```

```bash
python3 -B tools/hdmi/warm-reboot-test/test_mutations.py
```
