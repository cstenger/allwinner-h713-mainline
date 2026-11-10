# First warm shared-startup test — preparation (October 23)

**Offline only. No board access, staging or power request.**
Implements the first direct warm test of the
[shared startup plan](../../hdmi-shared-startup-plan-2026-10-23.md): after an
orderly reboot from a healthy cold HDMI session, the warm boot runs the
**installed cold startup sequence**, from RAM, once. The production FIT,
bootargs, modules and services are unchanged. Nothing is installed.

## Pieces

| File | Role |
| --- | --- |
| `tools/hdmi/build-warm-shared.py` → `build/hdmi-warm-shared-2026-10-23/warm-shared.scr` | The installed `h713-hdmi.scr` cold branch with four reviewed changes ([diff](warm-shared-vs-installed.diff)): runs only when GP6 = `48444d49` (the latch a cold-path boot leaves); never writes GP6; a census before the logo (MIPS status 0, GP7 0, R_CCU PPU bus 0); the handoff echo reads `WARM-SHARED`. Script SHA-256 `4c1ee8c0…`, 4,062 bytes. |
| `tools/serial/run-warm-shared.py` | One unattended sequence; sole UART reader throughout. |
| `tools/hdmi/check-warm-shared.py` | Session health: `check-startup.sh` unchanged, plus 5 s of the source through the user's PipeWire. Records level and PCM state, then compares cold with warm. |
| `tools/hdmi/test-warm-shared.py` | 23 tests, run against real October 22 UART logs; 12 mutations caught. |

## What `run-warm-shared.py run` does

1. **Opens the UART** before power is applied and writes `OPEN` to events.
2. **Cold boot, watched and never interrupted.** It requires exactly one SPL,
   a preboot line of all zeros (GP6/GP7/MIPS), the installed cold path's
   720p re-latch and `cold startup handoff verified`, then the kernel and
   login. It refuses on the latch-set branch, any script failure text or a
   second reset.
3. **Cold health.** It waits for SSH, then for capture and signal to settle,
   then runs `check-startup.sh`. It records the tone and needs RMS ≥ 0.01
   and the PCM RUNNING. If anything fails, the warm test is not started.
4. **Orderly `systemctl reboot`**, one request with no retry. The guard's
   `reboot refused` (failed teardown) stops the run.
5. **Warm catch.** It requires one new SPL with preboot GP6 = `48444d49`,
   with GP7 and the MIPS clock, reset and status words all 0. It sends **one** autoboot interrupt, so the
   installed warm logo never runs. A logo stage before the interrupt is a
   failure.
6. **Prompt census** (the reader thread is paused, so U-Boot only talks to
   the runner). It checks that `bootcmd` is unchanged and that
   `md.l` reads GP6 `48444d49`, GP7 0, MIPS 0 and R_CCU PPU 0. It then loads
   the FIT from eMMC and checks its size and CRC against the production FIT.
   Any difference means nothing is sent.
7. **YMODEM `warm-shared.scr`** to `0x52000000`; the sender verifies the RAM
   CRC.
8. **One `source 0x52000000`**, after `launch-attempted` is written. It
   requires the re-latch, `WARM-SHARED startup handoff verified`, the kernel
   and login. Any failure text or any reset stops the run.
9. **Warm health**, the same as step 3. Then a **cold/warm comparison**: a
   new boot ID, both sessions passing, and the warm level within 3 dB of
   cold (same source).
10. It prints `OPERATOR CHECK NOW` and leaves the board running.
    `run-warm-shared.py poweroff` performs the orderly production poweroff and
    confirms `reboot: Power down` on UART.

## Safety

* **Nothing installed:** the installed script, U-Boot, saved environment,
  GP6 rule, FIT, modules and services are untouched. If the warm launch
  wedges, the next power cycle autoboots the installed script, which sees
  GP6 set and takes today's logo-only branch. No boot loop is possible.
* **One of everything:** one reboot request, one interrupt, one transfer,
  one `source`. SSH deadlines are logged as uncertain and never retried;
  only read-only reachability is polled.
* **Every guard is kept:** each `itest` of the installed cold branch, plus
  the census, the FIT CRC, the driver's DSP `0/0` gate, the session's
  once-per-boot latch, receiver/owner checks and the hold guard.
* **Never touched:** CPUS/ARISC `0x07091xxx`, `0x06940000`, GP7 writes, the
  DSP or lock outside the production driver. PB5 behaves as on cold boots.
* **Board state to know:** the installed hold guard is the bench variant
  (`5ad26677…`). It differs from production only by also counting
  `h713_tvfe_retain=1` on the command line, which production does not
  set, so it behaves like the production guard here. The installed U-Boot
  proper prints the `H713 RESET v1 … proper_preboot` census line the runner
  checks.

## Expected panel behaviour

The previous boot ran the cold path with the cable connected, so the
**panel may come up black** (the known, separate panel-black problem,
about 80%). That is recorded as an operator observation, not as an HDMI
failure. Recovery: unplug the HDMI cable at the projector, then reboot.

## Runbook (one operator "ready")

1. The board is fully unplugged (serial, USB, power) for at least 1 minute;
   the HDMI source is connected and playing the tone clip continuously.
2. Run (unsandboxed, for SSH and UART):
   `python3 tools/serial/run-warm-shared.py run --output docs/hdmi-evidence/<date>-warm-shared-live`
   Confirm `OPEN` in `events.log`, then ask for power: **serial adapter
   first, then mains.** Plugging serial in after power would interrupt the
   cold autoboot.
3. Unattended: cold boot (~2 min), cold health, reboot, warm launch (~2
   min), warm health. The lamp turns on during each U-Boot re-latch.
4. **Operator:** after the second lamp-on, report the picture (live video /
   logo / black) and whether the tone is audible.
5. `python3 tools/serial/run-warm-shared.py poweroff --output <same dir>`.
