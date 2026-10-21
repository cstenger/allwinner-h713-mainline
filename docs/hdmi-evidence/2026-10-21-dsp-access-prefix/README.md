# Staged DSP access prefix — live runs, October 21, 2026

**Result: the 33-step read-only prefix passed on a fresh cold logo-free boot
(`cold-prefix-02`).** An earlier partial run (`cold-prefix-01`) passed steps
1–9 with a bundle predating the console/panic preflight. No domain resume,
clock enable, reset change, TVFE/AudioTop programming or DSP access occurred
in either run. Automatic warm HDMI recovery remains unimplemented.

Context: the [audit and live gate](../../hdmi-dsp-access-audit-2026-10-21.md),
the [preparation evidence](../2026-10-21-dsp-access-audit/README.md) and the
[stalled monolithic attempt](../2026-10-21-dsp-cold-access/README.md) it
replaces. Board wall time is wrong (April 13); times below are host time and
correlation is by boot ID and kernel monotonic time.

## cold-prefix-02 — complete prefix, clean release and poweroff

Boot `36c40861-5bd6-4d21-875a-fce2fc1811b9`. Bundle v2
([manifest](../2026-10-21-dsp-access-audit/bundle-v2-manifest.json)): helper
`432dd643…`, module `c57229a4…`, guard `96f37655…`.

1. **Cold catch** (`cold-catcher-events.log`, `cold-uboot.log`): the operator
   disconnected everything, reconnected UART, then applied power with the
   HDMI source connected. Exactly one SPL banner; proper preboot trace
   GP6/GP7/MIPS clock/reset/status all zero; one autoboot interrupt, no
   command typed by the catcher.
2. **RAM boot** (`ram-boot.log`): pinned `boot-v3` commands, 20/20 guarded
   steps OK, bootm subimage sha256 OK. No environment save or media write.
3. **Identity and health** (`uart-identity.txt`, `linux-preflight.txt`): UART
   and SSH boot IDs match. ext4 replayed its journal (`recovery complete`):
   the previous power-down (end of `cold-prefix-01`) was not orderly. No ext4
   or I/O errors; growfs finished. DT marker `44535031`, display and CPU_COMM
   disabled, no HDMI handoff, no `/dev/cpu_comm_fd`, all three HDMI units
   `ConditionResult=no`, no h713 modules. Live guard already `96f37655…`.
4. **Staging** (`stage-bundle.txt`): bundle v2 to the new board directory
   `/root/hdmi-dsp-access-audit-2026-10-21-v2`; module, helper and live guard
   match the manifest.
5. **New preflight, live** (`preflight-refusal-check.txt`): at the default
   `kernel.printk = 5 4 1 7` the helper refused `load` before saving any
   state; the module stayed unloaded.
6. **Console calibration** (`console-calibration.txt`): printk 5→7,
   `kernel.panic` 5→0; a `<5>` marker written to `/dev/kmsg` appeared on the
   passive UART capture (`bench-uart.log`) within a second.
7. **Load** (`load.txt`, `status-after-load.txt`): INIT and INIT DONE on the
   UART; helper and kernel at cursor 0, phase paused. The host runner
   misparsed this one acknowledgment (it sliced past the JSON into its own
   trailer line); the acknowledgment in `load.txt` and the read-only status
   were checked before step 1 and the parser fixed (`load-check.txt`,
   `host-step-runner.py`).
8. **Steps 1–33** (`step-NN.txt`): one helper call each; every step required
   the helper acknowledgment and exactly one UART BEGIN and DONE before the
   next. All eight pairs for steps 1–8 were confirmed before step 9.
9. **End** (`status-final.txt`): phase paused, completed = attempted = 33,
   `prefix_complete=Y`, failed N. No warning, error or RCU stall line after
   boot; 66 step markers on the UART.
10. **Release and poweroff** (`release.txt`, `poweroff-request.txt`): helper
    release acknowledged, UART BEGIN/DONE software resource release, module
    unloaded. Orderly `systemctl poweroff`: root remounted read-only,
    `reboot: Power down` at 546.3 s. Guard silent, as no h713 module was loaded.

| Step | Operation | Value | Meaning |
| --- | --- | --- | --- |
| 9 | read-mips-stopped `0x0306101c` | `00000000` | MIPS stopped (required 0) |
| 10 | read-scp-stopped `0x07000400` | `00000000` | SCP reset bit clear (required) |
| 11 | read-demod-bus `0x02001d64` | `00000000` | demod gate off, reset asserted (required) |
| 12 | read-display-bus `0x02001dd8` | `00010001` | sample only: gate on, reset deasserted |
| 14 | read-display-reset | `0` | deasserted (sample; 0 or 1 accepted) |
| 16 | read-demod-reset | `1` | asserted (required) |

All other steps are resource claims, mappings or handle lookups (value 0).
Step 12 is notable: with `/soc/display@5600000` disabled, the display bus is
still open. Something before Linux opened it, and `clk_ignore_unused`
leaves it so. The next-stage design must account for this.

## cold-prefix-01 — partial run, steps 1–9

Boot `460adf1a-ac3d-4c8e-b6bb-b86b2154fd0b`, bundle v1 (helper `5fbfd4a8…`,
without the console/panic preflight), board directory
`/root/hdmi-dsp-access-audit-2026-10-21`.

- Cold catch with one SPL banner and zero preboot trace; RAM boot 20/20 OK,
  bootm sha256 OK; boot IDs matched; ext4 replayed its journal after the
  stalled attempt's power cut.
- `guard-install.txt` (`install-prefix-guard.py`): live guard replaced
  `365fe6c9…` → `96f37655…`; exact previous guard backed up on the board as
  `/root/hdmi-dsp-access-audit-2026-10-21/previous-hold-guard`.
- `load` ran at console level 5 (`load-logging-check.txt`): INIT lines are in
  dmesg only, not on the UART. The threshold was then raised to 7 and a
  notice marker confirmed (`console-calibration.txt`, `bench-uart.log` line
  "console threshold corrected before any advance") before step 1.
- Steps 1–9 each acknowledged, and `bench-uart.log` holds exactly one
  BEGIN and one DONE per step (the run's host checker,
  `check-prefix-ack.py`, tests for this); step 9 read MIPS status `00000000`. Nothing was
  sent after step 9. The recorder ran to its 60-minute deadline with no
  further output. `kernel.panic` was not changed in this run.
- **The end of this run was not recorded.** The module was still loaded and
  pinned at cursor 9. The board was later found off; the next boot's journal
  replay is consistent with power removal rather than an orderly shutdown.

## What this does and does not establish

Positive: in a cold, logo-free maintenance boot, the old setup's opening
operations, run one at a time, complete. These are the resource claims,
control mappings, the MIPS/SCP/demod/display control reads, the reset-handle
lookups and status reads, and all 17 clock-handle lookups. Results are
consistent across both runs where they overlap. The stalled monolithic
attempt is therefore most likely in what this prefix omits: domain
registration/resume, clock prepare/enable, reset release, TVFE programming,
AudioTop or later.

Not established: this was not a byte-identical replay of the old init path,
so a timing-dependent failure in that sequence is not excluded. The samples
follow PPU probe and other Linux startup effects, not pristine reset entry.
Nothing here bears on DSP state retention across warm reset, the inherited
TVCAP always-on assumption, or the safety of any power/clock transition.

`sha256.json` covers every file in both run directories and this README.
