# HDMI first-advert failure: analysis and plan to fix

November 2, 2026. Built from existing evidence only: the three host-reboot runs, twelve SCP SRAM
snapshots, host kernel and journal logs, and the October 14 HPD bench. No new board or host action
was taken for this analysis.

## What the evidence establishes

**1. The failure reproduces on demand.** Every recorded first advert after a host boot failed:
`2d8c3970`, `afe48e93`, `b3cf2171`, `cf42f5ba`, `1239d8ee` (a timing-invalid run) and `0d907a30`.
Every later advert in the same host boot passed: `7e9e206d`, `e6ccc77a`, `275f5bce`, `3605d346`,
`8177b0d2`, plus operator-reported ones. None of these made a difference:

| Variable | Range covered | Effect |
| --- | --- | --- |
| Board cold or warm | Cold passes (`275f5bce`, `e6ccc77a`) and cold fails | None |
| Board off time | 8 min to about 19 h | None |
| Host reboot or poweroff | Both failed | None |
| Startup timing | Production, 0 ms and 2,000 ms | None |

**2. The board does the same thing every time.** The SCP saves the receiver words it finds at entry.
All twelve snapshots, pass or fail, hold the same values: HPD control `0x07091014 = 7` (held low),
DDC `00a0a0a0 / 07000000 / 00606060`, IO words zero. After release they are again identical:
HPD control `0`, DDC enabled `07000007`. The EDID payload is valid, and the owner is ready at about
23 s every time.

**3. EDID RAM contents don't discriminate pass from fail.** The bank backups are SRAM power-up noise
in every boot. The warm reboot that passed (`8177b0d2`) began with banks byte-identical to those of
the cold boot that failed just before it (`1239d8ee`). Stop using the S0/S1 bank comparison.

**4. The host's display driver never acts on the first advert.** The host is an RTX 3090 on NVIDIA
open driver 615.78.08. During a failed first advert it emits zero DRM uevents and logs nothing,
while the poweroff controls emitted 2 to 4 uevents each. The `RLD advertized maximum pixel clock`
warning appears at every NVIDIA load, including host boots that later connect, and the board's
payload is `HCP`, so it is not this failure.

**5. Re-advertising is already proven on this board.** On October 14, a 12 s HPD hold and release
gave 10 out of 10 host reconnections within one session
([evidence](hdmi-evidence/2026-10-14-hpd-cycles/README.md)).

## What remains open

The board's sequence is identical, so the difference is on the host side of the cable. Two
mechanisms remain:

* **H, host logic:** the GPU driver misses or ignores the first HPD rise after it boots.
* **E, electrical:** a host reboot drops HDMI +5 V, which resets whatever on the board is powered
  from it. The first advert then differs physically, for example an HPD glitch at power-on before
  the hold is applied. Within one host boot, that state survives a board power-off.

Software alone can't separate these. One host command (step 1) or one multimeter reading can.
Both point to the same product remedy: the projector must re-advertise when no source arrives,
because it can't depend on how a particular source behaves.

## Plan

### 1. Classify the failure: one command, now

The current boot is in the failed state (board boot `0d907a30`, host boot `e1026e16`). Force the
host to probe the connector:

```bash
echo detect | sudo tee /sys/class/drm/card1-HDMI-A-1/status
```

```bash
cat /sys/class/drm/card1-HDMI-A-1/status; wc -c < /sys/class/drm/card1-HDMI-A-1/edid
```

* **Connected with a 256-byte EDID (`HCP` / `H713 HDMI IN`):** the board is advertising correctly
  and the host never processed the edge. Go to step 2.
* **Still disconnected:** the GPU sees no HPD or can't read DDC, even on request. Measure HDMI
  pin 19 (HPD) and pin 18 (+5 V) at a breakout: in this state, with the board off, and through
  one host reboot. Re-advertising may still help, but measure first.

This uses up the failed state, which is fine because the failure reproduces on demand.

### Result of step 1 (November 2, 00:50): still disconnected

A forced probe left the connector disconnected with zero EDID bytes. In NVIDIA 615.78.08,
`nv_drm_connector_detect` ignores its cache and issues a fresh NVKMS dynamic-display query on
every detect. So even when asked directly, the GPU does not see this board. That disfavours H, a
missed edge, and favours E: in the first advert after a host boot, the board's HPD or DDC isn't
reaching the GPU, although the receiver registers say HPD is released and DDC is enabled.

The board is unchanged after the probe (boot `0d907a30`, signal `none`, owner ready). Its per-boot
`attempted` latch refuses any re-initialization without a cold cycle, so a service restart can't
be used as a quick re-advertise.

Two checks, each a few minutes, split E into its parts. Both are passive reads.

1. **DDC, no hardware needed.** Read address `0x50` on the five NVIDIA I2C buses (`i2c-0` to
   `i2c-4`). The board's EDID starts `00 ff ff ff ff ff ff 00 20 70`, where `20 70` is `HCP`.
2. **HPD and +5 V.** With an HDMI breakout and a multimeter, measure pin 19 (HPD) and pin 18
   (+5 V) against pin 17. Measure in this failed state, and again after a board warm reboot once
   connected, as the known-good reference.

| DDC returns HCP | HPD | +5 V | Meaning | Next |
| --- | --- | --- | --- | --- |
| Yes | Low | Present | DDC works, but the board does not drive HPD high | Find the HPD gate the warm path sets |
| No | High | Present | HPD reaches the GPU, but EDID is not served | Find the DDC/EDID state the warm path sets |
| No | Low | Present | The receiver output side is not up at all | Diff the receiver window, failed vs. passing |
| — | — | Absent | The host is not supplying +5 V after its reboot | Host-side; the board can't fix it directly |

**DDC result (00:58):** `i2c-3` returned the Acer T232HL EDID (`04 72` = `ACR`, model `0x013a`),
which is the monitor on DP-2. `i2c-0`, `1`, `2` and `4` did not acknowledge `0x50`. The HDMI port's
bus is one of those four, so in the failed state **the board does not answer EDID reads at all**.
HPD is still unmeasured. Positive control still needed: the same read after a board warm reboot
should return the `HCP` EDID on one bus, which also identifies the HDMI bus.

**Bad vs. good snapshot (01:04 / 01:07):** `tools/hdmi/snapshot-rx-state.py` captured the failed
boot `0d907a30`, then a board warm reboot gave `e35674bb`, which connected at 01:07:14. Everything
the ARM side can read is identical, apart from the idle GPU clock (`CCU 0x670`, 150 vs. 600 MHz):

* Both clock controllers, both pin controllers and the TV power-domain words.
* All 20 KB of SCP SRAM, including handoff readbacks and EDID-bank backups (0 words differ).
* Clocks, power domains, regulators, pin mux and pin configuration.
* Receiver, audio and signal-owner parameters.

So the difference lives inside the receiver block at `0x07091000`, which only the SCP may read, or
in the electrical path. Data in `local/recovery/2026-11-02-rx-state-diff/`.

**Positive control (01:09):** with the board connected, `i2c-1` returns `00 ff ff ff ff ff ff 00
20 70 13 07`, the `HCP` EDID. `i2c-1` is the HDMI port. The same bus did not acknowledge in the
failed state, so **DDC is the element that flips.**

**Lead test, no host reboot needed.** Power the board off in an orderly way and remove the supply.
Then read `i2c-1` from the host:

* If it acknowledges, the EDID side runs on cable +5 V, and the data may be the `RLD` EDID.
* Then power the board on without rebooting the host. If detection fails, a host DDC read while
  the board was unpowered is the trigger, and the failure reproduces without a host reboot.

**Result (01:12–01:17):**

* With the supply removed, `i2c-1` does not acknowledge at all, so the board's EDID side is not
  powered from the cable.
* After 256 DDC reads against the unpowered board, a power-on without a host reboot **connected**
  at 01:16:25. Host DDC traffic is not the trigger.
* EDID RAM across that cold cycle: 493 of 6,144 bits differ, so it **lost power and still passed**.
  The board starts from the same fully reset state whether the advert passes or fails. Nothing on
  the board can carry "the host rebooted".

**Revised reading:** the state that decides pass or fail is outside the board: in the host's HDMI
port after its boot, or electrically on the cable. A board warm reboot repairs it by what the host
sees, namely HPD released in the failed boot, then held low through the reboot (~25 s), then
released. The first advert after a host boot never had an HPD-high period before its release.
Re-advertising (an HPD low pulse) is back as the leading product fix, and the re-activation test
below exercises exactly that.

**Different source (01:38–01:45): the Mac connected on its first advert.** The board was shut down
and its supply removed, with HDMI moved to a Mac laptop. The Mac was restarted and logged in, then
the board was powered on. In board boot `112c31f5`, EDID/HPD was ready at 23.26 s and the signal
locked at 1280x720 at 25.56 s, 2.3 s later. The Mac desktop appeared after the normal console
period. With NVIDIA, the same sequence failed 6 out of 6 times. So the board's first advert works
with another source, and the fault is specific to the NVIDIA host. One Mac run so far; a repeat
would firm it up.

**Superseded lead:** the host reads EDID over DDC at boot (~2 s), while the board is off and the receiver's
EDID side may be running on cable +5 V. The `RLD … 170000 KHz` warning at every NVIDIA load would
then be that read, of garbage. A DDC slave left stuck by that read would explain the timing
pattern exactly. Only a host boot with the board off does this; every passing advert followed a
host boot where the board's DDC was already serving our EDID.

**Next experiment, on the next reproduction:** in the failed state, stop the signal service, clear
its `attempted` latch, and start it again. This re-runs the SCP restore and activation, with DDC
disabled and re-enabled, without rebooting.

* **Host connects:** a second activation is the fix, done automatically after a no-signal timeout.
* **No connect:** the reboot path (U-Boot, MIPS or SCP firmware) does the missing initialization.
  Next is an SCP read of the full receiver window, failed vs. good.

For the board-side rows, the next step is a single SCP read of the receiver window, once in this
failed state and once after a warm reboot. The difference is the missing initialization, and
adding it to startup is the root-cause fix. Re-advertising (step 2) helps only if HPD is the gap.

### Fix as built (November 2), not yet on the board

**Prior art.** No report matches this exact NVIDIA case. Linux's HDMI receiver drivers settle what
a sink should do: hold HPD low at least 100 ms before a source re-reads the EDID, longer for some
sources, and only raise HPD once the EDID is readable. Sources: the `adv7604` and `tc358743`
drivers, and the RK3588 `snps_hdmirx` HPD-toggle patches. Closest NVIDIA reports:
open-gpu-kernel-modules issues #811 and #1238.

**SCP payload** (`make-edid-trial-code.py --readvertise`):

* Requests share the stop word at `0x4f10`: 2 holds HPD low and disables DDC, 3 enables DDC,
  4 releases HPD to its original value. The SCP acknowledges at `0x4f74` and clears the word.
* The code page is full (414 of 416 instructions), so the 52-instruction handler sits in free
  SRAM at `0x4ac0`. The wait loop gains a 3-instruction hook.
* Without the flag, the output is byte-identical to the installed header.

**Module:** writing `readvertise=<ms>` (100 to 15000) sends hold, sleeps, sends DDC on, waits
100 ms, then sends release. A request that isn't acknowledged makes the owner terminal and retains
its holds, as a failed stop does. The `readvertised` parameter counts completed cycles.

**Service** (`h713-hdmi-readvertise.py`): while the signal is `none`, it requests a 2,000 ms
cycle after 10, 20, 40, 80 and 160 s. Any lock resets the schedule, and a lost source starts it
again. `acquiring`, `locked`, `hold` and `unsupported` are never pulsed.

**Offline checks:**

* `test-edid-trial-payload.py`: 8 tests, including 4 on the OR1K model. 4 of 4 handler breaks caught.
* `test-hdmi-readvertise.py`: 9 tests. 4 of 4 service breaks caught.
* The existing wrapper tests pass. The module builds with `W=1` against the board kernel.

**Bench validation 1 (02:11–02:13): PASS.** The fix was staged as a bench: candidate module and
service under `/usr/lib/h713-hdmi-readvertise-bench/`, the unit enabled, and drop-in
`95-readvertise-bench.conf`. The board shut down, its supply was removed and the host rebooted
(fresh boot `29ce315c`), then the board was powered on. In board boot `959c77ed`:

| Uptime | Event |
| --- | --- |
| 23.7 s | EDID/HPD ready, with no source |
| 34.0 s | Re-advertise requested |
| 36.1 s | Cycle done |
| 37.4 s | Locked at 1280x720 |

The host connected at 02:13:28. The same sequence failed 6 out of 6 times without the fix.

The new module's shutdown after a cycle (boot `d679b09d`) read back every original register. The
re-advertise service stopped before the signal service.

**Repeats 2 and 3: PASS.** Each was a board poweroff, supply removed, a fresh host boot, then the
board powered on.

| Run | Host boot | Board boot | Ready | Re-advertise | Locked | Host connected |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `29ce315c` | `959c77ed` | 23.7 s | 34.0 → 36.1 s | 37.4 s | 02:13:28 |
| 2 | `5e7d1120` | `ea911275` | 23.1 s | 33.4 → 35.5 s | 36.8 s | 02:20:34 |
| 3 | `014f2eaf` | `bcd192e3` | 23.1 s | 33.5 → 35.6 s | 36.9 s | 02:24:13 |

3 out of 3 with the fix, against 6 out of 6 failures without it. Each time a single cycle was
enough, and the lock followed the release by 1.1 to 1.3 s.

**Installed in production (November 2).** `tools/hdmi/build-readvertise.py` rebuilt the module
byte-identical to the validated one (`fb3bdcf0…`). `install-readvertise.sh` then:

* Replaced `h713-hdmi-signal.ko` (pinned predecessor `0a6987ce…`) and added
  `h713-hdmi-readvertise.py` and its unit in `/usr/lib/h713-hdmi`, rewriting only those three
  `SHA256SUMS` entries. The full generation verifies.
* Installed and enabled `/etc/systemd/system/h713-hdmi-readvertise.service`.
* Retired the `90-start-delay.conf` (0 ms bench) and `95-readvertise-bench.conf` drop-ins. The
  signal service is back to the plain production command.
* Kept the previous files under `/var/lib/h713-hdmi-startup/readvertise.*`. The bench directory
  was removed.

Offline tests: 6 installer tests on a fake root, with 4 of 4 guard breaks caught.

### 2. Build the product fix: re-advertise when no source arrives

In the production signal owner, after EDID/HPD ready: if no TMDS signal locks within *T*, hold HPD
low for *D*, then release. Repeat with bounded retries, and stop once a lock arrives.

* **Mechanism:** add a re-advertise request to the SCP program's wait loop in
  `make-edid-trial-code.py` (`hold_hpd`, dwell, release to `META & ~7`). Keep the owner's existing
  ownership and restore guarantees. Reuse the October 14 bench's saved/restored HPD hold.
* **Starting values:** *T* = 10 s, *D* = 2 s (the bench used 12 s, which is known to work),
  3 retries, then one every 60 s. These are tunable.
* **Offline qualification:** unit tests plus mutation checks, as with the existing owner.

### 3. Validate it with the reproducer

The cycle is: host reboot with the board off, log in, power the board on, and pass if the host
connects within *T* + *D* + 10 s. Run it 3 times. Before the fix this failed 6 out of 6, so 3 passes
is strong evidence. Also run one advert later in the same host boot, and one board warm reboot, as
regression checks.

Keep the identity and pin guards. Drop what has stopped earning its cost here: the single-use stage
receipts, the 8 to 20 minute off-time window, the EDID RAM comparison and the preservation rules.

### 4. Close out

Remove the 0 ms bench override, install the fixed production owner, record the result, and move on.

## Optional, if a second source is at hand

A laptop or other HDMI source that is powered on, then connected to a freshly booted board, shows
whether the failure is NVIDIA-specific. It doesn't change the plan.
