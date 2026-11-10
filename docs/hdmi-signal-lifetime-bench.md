# Bench: one lifetime cycle of the candidate h713-hdmi-signal module

This run validates the H1 change from [hdmi-signal-review.md](hdmi-signal-review.md).
In H1, the SCP payload reads back the HPD/DDC/IO registers after restoring
them, and `stop` refuses to release anything unless every readback equals the
saved original. It is one load → stop → rmmod cycle of the candidate module on
a normal cold boot. The installed configuration is never modified: the
candidate runs through a **runtime-only** systemd drop-in in `/run`, which is
gone after the next boot.

**What a pass proves**
- On this board, the stop readback of all 8 registers equals the originals.
  This is the open risk from H1: a volatile status bit would cause a false
  terminal failure.
- The candidate loads, reaches ready with the readback area intact, and then
  stops, releasing its receiver client and the DDC pins.
- The candidate DDC helper logs a successful idle restore.

**What it does not cover**
- The H2 ExecStop-failure policy.
- An unparked poweroff.
- Any second cycle in the same boot.

## What is staged

`build/signal-lifetime/` was built from base commit `7fba9fc` plus the
review changes, which were uncommitted at the time; `manifest.json` lists them.

| File | Purpose |
|---|---|
| `h713-hdmi-signal.ko` | Candidate. Build-id `166a2ca81c43bf56392d6c96a30180391b26a9d9`; payload from `--verify-restore`. |
| `h713-ddc-pins.ko` | DDC helper. Same behaviour as before; only the exit message is now honest. |
| `h713-hdmi-signal.py` | Wrapper with `--bundle`, so the unit can point at this directory. |
| `run-signal-lifetime.sh` | The self-checking target script. It has two phases, `swap` and `stop`. |
| `check-startup.sh` | Gate: a production-clean cold boot. |
| `candidate.build-id`, `SHA256SUMS`, `manifest.json` | Identity and integrity checks. |

The script stops at the first failed check. It **never** runs `rmmod`,
retries, or undoes a hold.

## Procedure

`T` below is the SSH command from the startup handoff. It relies on word
splitting, so run it in bash (zsh does not split `$T`; there, type the full
`ssh` command each time):

```bash
T="ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 root@192.168.4.1"
```

### 1. Cold boot (operator)

1. Unplug the serial adapter **and** USB.
2. Power off for at least 1 minute.
3. Power on and do not interact. Do not replug serial: that interrupts
   autoboot.

### 2. Connect and stage

Wait until about 30 s after power-on; the services need about 20 s after the
kernel starts. Then run the following.

Join the board's WiFi access point:

```bash
nmcli connection up spirits
```

Confirm the boot came up through the installed units:

```bash
$T 'systemctl is-active h713-hdmi-capture h713-hdmi-signal'
```

Both must print `active`. If either does not, stop here. The boot is not a
clean automatic boot, and nothing below applies.

Copy the bundle to the board:

```bash
scp -F /dev/null -o StrictHostKeyChecking=yes -r build/signal-lifetime root@192.168.4.1:/tmp/h713-signal-lifetime
```

### 3. Swap in the candidate (`swap`)

```bash
$T 'sh /tmp/h713-signal-lifetime/run-signal-lifetime.sh swap'
```

The phase does the following, in order:
- Runs `check-startup.sh`, which needs a clean cold boot.
- Verifies the checksums and vermagic.
- Checks that the installed module's build-id differs from the candidate's.
- Checks that the PCM is closed.
- Stops the **installed** owner through its unit. This is the validated path.
- Proves that stop was clean: the unit is `inactive success`, neither module is
  loaded, the receiver has `clients=1`, and the installed module logged its
  restoration.
- Writes the runtime drop-in and starts the candidate through the same unit.
- Requires all of: `ready=Y`, `failed=N`, `restored=N`, `clients=2`, DDC held,
  the loaded build-id equal to the candidate's, and all 8 readback words still
  `ffffffff` at ready.

It also prints the `ready original` values. A `NOTE` line means they differ
from the known-good probe values (`1014=7 b00=00a0a0a0 b04=07000000
b08=00606060`). That is not a failure, but report it.

Expected last line: `PASS swap: …`

### 4. Optional: capture through the candidate

Use the host HDMI source, as in `2026-10-14-normal-startup/resume-1/`. The
test's own guard requires `h713-hdmi-signal.service` to be active, which the
drop-in keeps true.

Stage the recorder (`/tmp` was cleared by the cold boot):

```bash
scp -F /dev/null -o StrictHostKeyChecking=yes build/hdmi-alsa-utils/usr/bin/aplay root@192.168.4.1:/tmp/arecord
```

Run the capture test:

```bash
python3 tools/hdmi/run-alsa-capture-test.py --persistent-signal --recorder /tmp/arecord docs/hdmi-evidence/2026-10-14-signal-lifetime/capture
```

This proves that the candidate serves EDID/ELD and HPD to a real source. The
lifetime pass does not depend on it.

### 5. Stop the candidate (`stop`)

Every capture consumer must be closed first.

```bash
$T 'sh /tmp/h713-signal-lifetime/run-signal-lifetime.sh stop'
```

The phase checks that the PCM is closed, then stops the unit. Its `ExecStop` is
the candidate wrapper: `stop=1`, then `rmmod h713_hdmi_signal`, then
`rmmod h713_ddc_pins`. It then requires all of the following:
- The unit is `inactive success`, both modules are gone, the ownership record
  is gone, and the receiver has `clients=1`.
- The `stop marker=` line ends `marker=48444d49 ready=48444d49 exception=0
  error=0 done=48444d49`.
- The **`stop readback` values equal the `stop original` values**, compared as
  whole strings.
- `peripheral readback, SRAM and vectors restored` and `DDC pins returned to
  inputs` are both logged.
- No `WARNING:`, `BUG:`, `Oops` or `input-state restore failed` appears.

Expected last line: `PASS stop: readback equals originals; …`

### 6. Collect the evidence

```bash
scp -F /dev/null -o StrictHostKeyChecking=yes -r root@192.168.4.1:/var/tmp/h713-signal-lifetime docs/hdmi-evidence/2026-10-14-signal-lifetime/target
```

This directory holds, per boot ID, `swap.log`, `stop.log`,
`check-startup.log`, and the dmesg excerpts since each phase marker.

### 7. Finish

The signal unit is now stopped and the capture backend is still running. This
is the state the validated poweroff already handles: with no signal module
present, the backend restores the DSP/TVFE words, parks MIPS and releases the
receiver.

```bash
$T 'systemctl poweroff'
```

Confirm that the lamp and fan are off. The drop-in and the staged `/tmp` files
are gone on the next boot. Do **not** restart the signal unit on this boot;
that path is untested.

## Pass criteria

Both phases must print `PASS`. Above all, the `stop readback` line must equal
the `stop original` line. That pair is the result this run exists to get; copy
it into the review doc, next to H1.

## If a check fails

Do **not** retry, rerun a phase, `rmmod`, or warm reboot. Save the evidence
first (step 6), then read the case:

| Where it failed | State | Next |
|---|---|---|
| `swap`, before "stopping the installed signal owner" | Nothing was touched. | Fix the cause (bundle, boot, consumer). A rerun on this boot is fine. |
| `swap`, the installed stop | The installed owner failed to restore, and its holds are retained. This is a finding about the **installed** module, not the candidate. | Power off (see below). |
| `swap`, the candidate start or the ready checks | The candidate holds are retained, or after an early clean refusal the DDC helper is held (review M1). | Power off (see below). |
| `stop` | The candidate is `failed` and holds every resource. A readback mismatch means a register restore did not land, or the register has a volatile bit: the logged `readback` and `original` lines show which. | Power off (see below). |

In each "power off" case, the backend will refuse to park because a signal
module is still loaded. `systemctl poweroff` will then halt **without parking
MIPS**. That path is untested (review H2). Watch for these and report them:
- `reboot: Power down` on the console, if you can capture it without
  replugging serial before poweroff;
- the lamp and fan going off;
- no reboot within 90 s.

That outcome is the first data point for the H2 policy. Then cold-cycle as in
step 1.
