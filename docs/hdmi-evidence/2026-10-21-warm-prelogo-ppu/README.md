# Warm pre-logo PPU diagnostic — October 21, 2026

**Result:** TVFE and TVCAP were ON at warm U-Boot before the logo, and
still ON at the sample after one logo invocation. Warm Linux subsequently
reported TVFE OFF, TVCAP ON. **Board ended in orderly poweroff. DSP retention
was not measured.**

Design/source review: [pre-logo PPU review](../../hdmi-warm-prelogo-ppu-review-2026-10-21.md).
This cycle deliberately opened bus-r-ppu at preboot. It is separate from
Claude's [unmodified A–C controls](../2026-10-21-warm-retention/README.md).

| Observation | R_CCU PPU | TVFE | TVCAP | MIPS |
| --- | --- | --- | --- | --- |
| Production cold-live, boot `fe51947d` | `00010001` | ON | ON | running |
| Warm prompt, before probe | `00000000` | not read | not read | parked |
| Warm pre-logo, after bus open | `00010001` | **ON** | ON | parked |
| After single logo invocation, before Linux | `00010001` | **ON** | ON | parked |
| Warm Linux, boot `1889c531` | `00010001` | **OFF** | ON | parked |

## Sequence and evidence

1. Operator reported making the board unpowered and then powering it. The
   first catcher ran inside the sandbox, where the host UART was invisible;
   it captured nothing. The cold preboot baseline is missing. Host UART access
   was then verified with escalation, and the ineffective catcher was stopped.
   Do not count this as a fully captured cold-control trial.
2. `cold-live-health.txt` and `cold-live-census.json`: boot
   `fe51947d-10f3-405b-9b6f-0d56fb04a824`; all production units active, handoff
   present, DSP `0/0` then verified patch `1/1`, both domains ON, stock
   AudioTop and lock peer/own `0`/`aa`. These are software/ register results;
   moving video and audible output were not independently observed here.
3. `warm-catch/`: confirmed UART OPEN before the guarded orderly reboot.
   Request matched the current boot and active production units. UART records
   `reboot: Restarting system`, one SPL, matching proper version, GP6
   `48444d49`, MIPS zero and the captured U-Boot prompt. Watchdog-stop warnings
   precede the orderly restart; this is not a watchdog-expiry test.
4. `warm-prelogo/`: bootcmd matched Claude's saved production value (no cold
   bootcmd was captured this cycle). Bus initially zero; GP6 and parked MIPS
   checked. One write `mw.l 0x070101ac 0x00010001 1`, exact readback, then
   both PPU status words `00010000`. **No domain power command was sent.**
5. `warm-logo-lamp-off.log`, `warm-logo.log`: PB5 off, then one invocation
   of the production `h713_disp auto 0x34 logo` command. The command recorder
   used a three-second silence timeout and closed during the deliberate
   three-second panel hold. A subsequent passive read did not recover its
   completion output. `after-logo-prompt-check.log` proves return to the
   prompt, but **the explicit success/failure marker is missing**. Do not
   count the logo itself as a fully recorded successful qualification. No
   initialization retry was performed. Future recording must use a silence
   timeout greater than the longest intentional hold, e.g. 20 seconds.
6. `post-logo/`: both domains still ON at the prompt. `post-logo-mips.log`
   separately confirms MIPS zero. PB5 restored; the normal warm-branch
   FIT load and boot were executed directly, guarded by parked MIPS,
   **without executing the startup script again** (which would run a second
   logo). `warm-linux-uart.log` records the FIT boot and Linux startup.
7. `warm-linux-census.json`: boot
   `1889c531-069d-4a9b-8499-fa74326f186e`; TVFE OFF, TVCAP ON, no handoff,
   all HDMI units inactive, no h713 modules, routed TVTOP and lock `0/0`.
   AudioTop/DSP reads were correctly skipped. The domain summary and current
   boot journal are in `warm-linux-domain-and-journal.txt`; TVFE has no
   attached devices at collection, and the unused-domain sweep was skipped.
8. Guarded poweroff checked that same boot ID, absent handoff and inactive
   HDMI units. `end-poweroff-uart.log` records **`reboot: Power down`** at
   121.98 seconds. SSH timed out during shutdown and its redirected request
   output is empty; UART is the completion evidence.

## Interpretation and next gate

- In this diagnostic cycle, the PPU reports TVFE ON after reset/early boot
  and after the single logo invocation. A reset-induced OFF state cannot
  simply be inferred from Claude's later Linux census.
- The observed change is between the final U-Boot PPU sample and the Linux
  census. This includes `bootm` cleanup, firmware handoff, early kernel code,
  PPU probe and later runtime-PM activity. **It does not yet identify the
  writer or prove that a Linux callback caused it.**
- Opening/reset-releasing bus-r-ppu before the logo is an intervention.
  This result does not retroactively measure the untouched A–C trials.
- Neither domain status nor lock clearing measures DSP RAM retention.
  Phase D remains pending; do not clear GP6, relax DSP predicates or relaunch
  source3 on this evidence.

Next prepare instrumentation offline: sample PPU just before Linux handoff
and at the PPU driver's earliest safe access, before/after domain init;
log every TVFE power callback with its caller. Keep reads behind a verified
open bus and preserve existing startup/ownership guards. Such a trace should
separate boot handoff from PPU probe/runtime transitions before designing
the warm version read. No further cold cycle is armed by this record.
