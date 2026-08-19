# "WiFi cannot carry a file" -- reproduced, characterised, and A/B'd

> ## READ THIS FIRST: every measurement below was taken with NO ANTENNA ATTACHED
>
> Established after the fact (2026-08-17). The WiFi chip's antenna was not
> connected for any run in this document. Everything here was measured at
> -63...-71 dBm, which is **not** a property of the board, the driver or the
> firmware -- it is a disconnected antenna.
>
> This is not a footnote, it is the leading candidate explanation. The chain is
> the one `roadmap.md` already describes: weak RF -> low MCS -> retransmits ->
> more SDIO traffic per useful byte -> FIFO pressure -> `cmd53 fifo error`. Link
> rates observed were 18-54 Mbit/s on WiFi-6-capable silicon, which should have
> been a tell.
>
> **What this costs each finding:**
> - the transfer failure -- may be substantially or entirely RF, not driver/firmware
> - the -71 dBm "marginal window" from `roadmap.md` -- may itself describe an
>   antenna-less board rather than placement
> - the A/B throughput row -- already discounted, now worthless
> - the station-churn row (16 -> 0) -- **also confounded**, contrary to how it is
>   framed further down. A was measured near -71 dBm and B near -64. A client
>   reassociating at marginal signal is an ordinary explanation for 16/min. The
>   "less RF-sensitive, therefore solid" reasoning in the Comparison section does
>   not survive this.
>
> **Nothing here is retracted** -- the observations are real and the fault chain
> was genuinely captured. But no conclusion about *cause* should be drawn until
> all of it is repeated with the antenna connected. Treat this document as a
> record of what a no-antenna board does.
>
> ### RESOLVED: the antenna was NOT the cause (2026-08-17, later same day)
>
> Antenna reattached, signal went **-63/-71 dBm -> -31 dBm** (~10,000x more
> received power). The 8 MB `scp` **still fails**, on the 2026 driver, with the
> identical fault chain (one `cmd53 fifo error`, recovered, then `cmd timed-out`,
> then the data path dies while the AP keeps beaconing).
>
> And the decisive detail: it stalled at **1,827,840 bytes at -31 dBm -- the
> exact same byte count as the -63 dBm run**. Two runs 32 dB apart landing on the
> same number is not a marginal-link failure. **The stall is deterministic.**
>
> So the antenna caveat above is discharged, and it discharges *upward*: RF is
> ruled out as the cause, which makes the driver/firmware/SDIO path the live
> suspect after all. The confounder warnings on the A/B numbers still stand
> (those runs really were taken at weak signal), but the underlying failure is
> real and reproducible at excellent signal.

> **Result of the vendor rebase (added after the A/B, see "Comparison" below):**
> the 2026_0123 driver **eliminates the station churn** (16 -> 0 events/min) but
> **does not fix the file-transfer failure**. Same stall, same fault signature,
> same terminal wedge. Both halves of that sentence are now subject to the
> antenna caveat above.


2026-08-17, on the 2024_0109 driver + Mar 07 2024 firmware, kernel 6.18.38.
This is the Phase 0 baseline the vendor rebase (2026_0123) gets measured
against. **No fixes were attempted** -- the point here is only to say precisely
what happens. Raw capture: `reference/wifi-baseline-2024-driver.txt`.

## What was run

The board runs the baked-in hotspot: `hostapd` AP `spirits` on channel 6,
`192.168.4.1/24`, no uplink, `wpa_supplicant` masked. So the failing path is a
client pushing a file **to the board over the board's own AP** -- not STA mode.
A workstation joined that AP (`192.168.4.78`) and ran:

```
scp 8mb.bin root@192.168.4.1:/var/tmp/
```

## Result

**261,120 of 8,388,608 bytes (3.1%) in 300 s**, then killed by timeout. That is
~870 B/s effective. It matches the earlier field report ("10.8 MB scp moved 0
bytes in 6 min") closely enough to call it the same failure.

The kernel log gives a clean chain, with nothing else in between:

```
t=6306.619  sunxi-mmc 4021000.mmc: cmd53 fifo error (RINT=0x00000800 IDST=0x0000a000), retry 1/15
t=6306.619  sunxi-mmc 4021000.mmc: cmd53 fifo retry 1/15 (RINT=0x00000800 IDST=0x00000000)
t=6390.634  cmd timed-out
```

## What that chain says

1. **The FIFO recovery in kernel patch 0006 fired, and worked.** `IDST` goes
   `0x0000a000 -> 0x00000000` on retry 1 of 15. `docs/roadmap.md` recorded that
   this path had never been provoked and predicted it would need the
   -71...-80 dBm spot to fire. Signal here was **-71 dBm**. That prediction was
   exactly right.
2. **`cmd timed-out` followed 84 s later.** Not immediate, and only one FIFO
   error occurred -- so this is not a storm of SDIO errors dragging the command
   channel down. Either the single recovery left the transport in a state that
   only showed up later, or the two are independent and merely co-triggered by
   the same marginal RF.
3. **No `DHDISDOWN`, no `wlan error reset flow`.** The firmware did *not* enter
   its documented crash path. This is a quieter failure than the one the rootfs
   crash notifier was built for -- that notifier would not have fired here.

## End state -- the interesting part

After the stall:

- serial console: **wedged** (echoes characters, no prompt; Ctrl-C recovered it
  once earlier, then stopped working)
- SysRq: silent, but **inconclusive** -- `MAGIC_SYSRQ` is only in the
  `kasan`/`builtin-drivers` configs, not the shipping defconfig this board runs
- the AP is **still beaconing**, and the workstation is still associated at
  -65 dBm
- ping and TCP to `192.168.4.1`: **100% loss**

So the firmware is alive enough to beacon and hold an association autonomously,
while the SDIO data path between host and firmware is dead and the host side is
blocked. Recovery is a power cycle.

## What this does and does not establish

**Established.** The failure is reproducible on demand with an 8 MB scp. It is
in the AP-mode datapath. It involves the SDIO transport (`cmd53 fifo error`),
not just the firmware command channel. The board does not panic -- it wedges.

**Not established.** Whether the marginal RF is *causal* or merely a trigger.
-71 dBm is inside the window `roadmap.md` flagged as marginal, so RF placement
is a live confounder: a run at strong signal might not reproduce this at all.
Any A/B against the rebase must hold placement constant or it measures furniture.

**Also worth noting.** The 2026-07-22 bench recorded 384 MB clean with zero SDIO
errors, which is wildly better than 261 KB. `roadmap.md` does not say whether
that bench was AP or STA mode. If it was STA, then AP-mode bulk transfer has
never actually been benchmarked, and this is a previously unmeasured path rather
than a regression.

## Second, separate observation: station churn

Independently of the transfer, the client re-associates constantly --
**16 `del_station` events per minute**, measured over a clean 60 s window.
Each cycle completes fully (`associated` -> WPA 4-way -> `DHCPACK`) and then
repeats ~10 s later. `hostapd` logs no deauth reason. The driver leaks a station
slot each time: index climbed 15 -> 27, with `debugfs: '<mac>' already exists in
'rc'` and `Error while (un)registering debug entry for sta N` on every re-add.

Client-side WiFi power-save was **ruled out** -- disabling it left the rate
unchanged at 16/min.

Whether this churn causes the transfer failure or is a second bug sharing a root
cause is open. It is a strong candidate to check first after the rebase, because
a station torn down mid-transfer would produce exactly the observed stall.

## Measurement bug found along the way -- fixed

`tools/wifi/wifi-baseline.sh` counted SDIO faults by grepping `FIFO_RUN_ERROR`,
the name used throughout `roadmap.md`. That name is a **register-bit macro**
(`SDXC_FIFO_RUN_ERROR`) in the C source of `patches/kernel/0006` and never
reaches the kernel log. So `fault.fifo_run_error` read `0` through a run that
demonstrably had one -- it under-reported precisely the fault class that matters
most here.

Corrected against the literal format strings in patch 0006:

| field | matches |
|-------|---------|
| `fault.cmd53_fifo_error` | `cmd53 fifo error` -- FIFO/data-path stall |
| `fault.cmd53_phase_error` | `cmd53 phase error` -- CRC/timing class, separate retry budget |
| `fault.cmd53_retry_limit` | `retry limit reached` -- recovery exhausted, request failed |
| `fault.mmc_reset_timeout` | `DMA` / `FIFO` / `IDMA soft` `reset timeout` -- recovery itself failed |

**Counts are a lower bound.** The error line is `dev_warn_ratelimited`, so under
a storm the kernel drops repeats. Treat a jump from 0 as significant and the
absolute magnitude as approximate.

The `load.rx.*` per-phase counters were fixed the same way. The board still runs
the old copy at `/usr/local/sbin/wifi-baseline` -- it needs re-transferring
after the power cycle, or picking up from a rootfs rebuild.

---

# Comparison: 2024_0109 vs 2026_0123 (A/B, same board, same session)

Both arms: same kernel 6.18.38, same rootfs, same AP config, same 8 MB `scp`
from the same workstation, board unmoved.

| metric | A: 2024_0109 + Mar-2024 fw | B: 2026_0123 + `_h_` fw |
|--------|---------------------------|-------------------------|
| station churn (`del_station`/60 s) | **16** | **0** |
| 8 MB scp, best run | 0 B in 300 s | 1,827,840 B in 300 s |
| RF during that run | -71 dBm | -63 dBm |
| `cmd53 fifo error` | 1 | 1 |
| `cmd timed-out` | 1 | 1 |
| `DHDISDOWN` | 0 | 0 |
| terminal state | wedged; AP still beaconing | wedged; AP still beaconing |

## What is solid

**The station churn is fixed.** 16 events/min -> 0 over a clean 60 s window,
with `NetworkManager` logging 0 disconnects in 10 minutes where the old driver
produced 23 in 3. This is the strongest result in the A/B because it is a count
of discrete events rather than a throughput number, so it is far less sensitive
to the RF variation that contaminates everything else here. The station-slot
leak (index climbing, `debugfs: already exists`) is gone with it.

## What is not fixed

**Bulk transfer still fails.** Neither driver moved 8 MB in 300 s. The fault
signature is byte-for-byte the same shape -- one `cmd53 fifo error`, one
`cmd timed-out`, no `DHDISDOWN` -- and the terminal state is identical: the
firmware keeps beaconing and holding the association autonomously while the SDIO
data path is dead and userspace is blocked. Power cycle required either way.

## Limits of this comparison -- read before trusting the numbers

- **Two variables, not one.** The 2026 driver *cannot* run on the 2024 firmware
  set (see the `_h_` finding above), so "driver only" was not achievable. B is
  driver **and** `fmacfw` together.
- **RF was not held constant.** -71 dBm in A vs -63 dBm in B. `roadmap.md`
  identifies -71...-80 dBm as the marginal window, so A ran in it and B did not.
  The throughput difference (0 -> 1.8 MB) is therefore **not attributable to the
  driver** on this evidence.
- **One usable throughput sample per arm.** Later B runs failed at connect time
  ("No route to host", "Connection closed") rather than stalling mid-transfer,
  which is a different failure and not comparable.
- The churn result does **not** share these problems and stands on its own.

## What would sharpen it

Repeat both arms at matched RF, several runs each, with the board unmoved --
old modules are backed up on the board at `/root/oldmods/`, so swapping back is
a copy plus a reboot. Until then: churn fixed, transfer not fixed, cause of the
transfer failure still open.

---

# ROOT-CAUSE NARROWING: the failure is direction-specific (2026-08-17)

The clock experiments were a dead end (below). This was the test that mattered:
**run the same transfer in the opposite direction.**

| direction | what | size | result |
|-----------|------|------|--------|
| board **RX** (`scp` push *to* board) | WiFi -> SDIO -> host | 8 MB | **0-1,827,840 B in 300 s**, 1 `cmd53 fifo error`, 1 `cmd timed-out`, data path dies |
| board **TX** (`scp` pull *from* board) | host -> SDIO -> WiFi | 8 MB | **complete in 6 s**, md5 exact |
| board **TX** | same | 64 MB | **complete in 67 s (0.96 MB/s)**, md5 exact |

Same link, same session, same -32 dBm, same 25 MHz SDIO clock, minutes apart.
After **72 MB** of board TX: `cmd53 fifo error` **0**, `cmd53 phase error` **0**,
`cmd timed-out` **0**, `DHDISDOWN` **0**. A clean run in one direction and a
wedge in the other, at a 35x size ratio.

**So this is not the radio, not the link, not RF, and not the SDIO clock.** It is
the SDIO **receive** path -- card -> host -- under sustained load.

## Why this was missed for so long

The 2026-07-22 bench in `roadmap.md` that "proved" 384 MB clean was a **client
scp-pull over the AP** -- board TX. Sustained board **RX** appears never to have
been benchmarked. The bench was real; it just exercised the working direction.

## Why "buffer/descriptor exhaustion" is the leading hypothesis

- **The stall point is deterministic**: 1,827,840 bytes at -63 dBm and again at
  -31 dBm. A marginal link does not fail at a repeatable byte count; a finite
  resource does.
- **Exactly one `cmd53 fifo error`**, never a storm, and the retry *succeeds*
  (`IDST 0xa000 -> 0`). One hiccup, then the pipe never recovers -- that is a
  leak, not damage.
- **`cmd timed-out` arrives 84-160 s later**, not immediately: the command
  channel starves behind a dead RX path rather than failing with it.
- **Low-rate RX keeps working throughout** -- ssh, ping, DHCP, hostapd are all
  fine. Only *sustained* RX dies.
- The 2026 firmware carries RX exhaustion diagnostics the 2024 one does not:
  `rep: no rxmsg buffer, %d`, `rep: rxmsg no desc`, `rep: no buffer, %d`,
  `rep: no desc`. The vendor was chasing this class of bug.
- The driver preallocates RX buffers (`aic8800_fdrv/aicwf_rx_prealloc.c`), which
  is where a finite pool would live.

## Dead end, recorded so it is not repeated: the SDIO clock

`FEATURE_SDIO_CLOCK_V3`, board TX unaffected throughout:

| clock | inbound 8 MB result |
|-------|--------------------|
| 25 MHz (shipped) | 1,827,840 B, twice, identical |
| 150 MHz (vendor default) | 0 B |

Raising it did not help and plausibly hurt. **25 MHz stays.** No lower value was
tested: 12.5 MHz is not a value the vendor ever shipped, and testing invented
speeds is fishing rather than hypothesis-driven.

## Next test

Instrument the RX path rather than the link. Concretely: watch
`aicwf_rx_prealloc` pool occupancy and the firmware's `rep: no *` messages
(raise `aicwf_dbg_level` from `0x1` to include firmware logs, `0x403`) across an
inbound transfer, and see whether the pool is empty at the moment the stall
begins. If it is, this is a leak in RX buffer recycling and the byte count will
be a function of pool size.

---

# Two hypotheses tested and REFUTED (2026-08-17)

Both were tested on hardware, single-variable, and both were wrong. Recorded so
nobody spends the time again.

## 1. RX skb allocation failure -- REFUTED

**Hypothesis.** `aicwf_sdio_readframes()` (the `#else`, non-prealloc branch, which
is the one built: `CONFIG_PREALLOC_RX_SKB ?= n`) does:

```c
skb = __dev_alloc_skb(size, GFP_KERNEL);
if (!skb) return NULL;              /* silent -- no log, no counter */
ret = aicwf_sdio_recv_pkt(sdiodev, skb, size);
```

On alloc failure it returns **before** `recv_pkt`, so the card's pending data is
never drained and its FIFO would stay full -- which would produce
`FIFO_RUN_ERROR` on the next CMD53. The path is completely silent upstream.

**Test.** Rebuilt `aic8800_fdrv` with `pr_err_ratelimited` on both the alloc
failure and the `recv_pkt` failure branches; ran the 8 MB inbound transfer.

**Result.** **Zero** `aicwf-instr` hits, while `cmd53 fifo error` = 1 and
`cmd timed-out` = 1 as usual. Allocation is not failing and `recv_pkt` is not
returning an error. In hindsight this is consistent: patch 0006 *recovers* the
FIFO error, so `recv_pkt` returns success -- the data is read.

Note the `aicwf_rx_prealloc.c` pool (30 buffers x 32 KB) is **not compiled in**
at all, so it was never a suspect either.

## 2. Driver TCP-ACK filtering -- REFUTED

**Hypothesis.** The driver ships `CONFIG_FILTER_TCP_ACK = y` (both 2024 and 2026)
and implements `is_drop_tcp_ack()` / `intf_tcp_drop_msg()` -- it deliberately
drops TCP ACKs. That logic engages **only when the board is receiving**, which is
exactly the failing direction, and over-dropping would close the sender's window
and stall the stream with no SDIO error at all. Being identical in both drivers
would also explain why the rebase did not fix it.

**Test.** Rebuilt with `CONFIG_FILTER_TCP_ACK=n`, confirmed `is_drop_tcp_ack` was
absent from the module, retested.

**Result.** Identical failure -- 0 bytes, 1 `cmd53 fifo error`, 1 `cmd timed-out`.

Incidental finding while doing it: disabling that flag **breaks the build**.
`aic_priv_cmd.c` reaches `vmalloc` only via
`rwnx_defs.h -> #ifdef CONFIG_FILTER_TCP_ACK -> aicwf_tcp_ack.h -> net/tcp.h`.
Latent fragility in the vendor tree; worth an explicit include if that flag is
ever turned off for real.

## What survives: a perfect correlation

| run | direction | `cmd53 fifo error` | outcome |
|-----|-----------|--------------------|---------|
| A, B, C, E, H, I | RX inbound | **1** | fails |
| F (8 MB), G (64 MB) | TX outbound | **0** | completes, md5 exact |

Every failing run has exactly one FIFO error; every successful run has none.
Never any other combination, across driver versions, SDIO clocks, RF levels and
two instrumented builds.

## Refined hypothesis (untested): patch 0006's recovery is incomplete

The FIFO error is on the SDIO **read** path (card -> host), which only carries
load in the RX direction. `patches/kernel/0006` retries it and the *MMC layer*
reports success (`IDST 0xa000 -> 0`), so the aic8800 driver sees no error -- both
refutations above are consistent with that.

But the aic8800 SDIO protocol is framed: read `intstatus` to get a block count,
then read exactly that many blocks. If the retried CMD53 does not restore the
card's read pointer to precisely where the host thinks it is, host and card
desynchronise. From then on every read is misframed, RX is dead, and the command
channel eventually times out -- which is the 84-160 s gap we keep seeing.

That would mean **the trigger is a sunxi-mmc/SoC FIFO underrun and the fatal part
is our own recovery**, not the vendor driver at all. It also fits TX being clean:
writes do not use that path.

Next step if pursued: log around the patch-0006 retry (`error_rint`,
`idma_int_sum`, block count, and the aic8800's `intstatus` before/after) and
check whether the post-retry read length matches what the card advertised.

---

# ROOT CAUSE FOUND: patch 0006's FIFO recovery disables the SDIO interrupt

**The bug is ours, in `patches/kernel/0006`, not in the vendor driver.**

## The evidence that ended it

After a failed inbound transfer, with the board still alive and `wlan0` UP:

```
256:  3168 -> 3168    GICv2 73  sunxi-mmc
257:  8663 -> 8663    GICv2 72  sunxi-mmc     (30 seconds apart)
```

**Zero SDIO interrupts in 30 s.** The controller has stopped interrupting
entirely. That single fact explains every earlier negative result: no RX frames
arrive because the interrupt that would fetch them never fires -- so there are no
skb allocation failures, no `recv_pkt` errors, and no framing desync. Nothing is
read at all.

## The mechanism

`sunxi_mmc_init_host()` arms the controller:

```c
rval = mmc_readl(host, REG_GCTRL);
rval |= SDXC_INTERRUPT_ENABLE_BIT;      /* BIT(4) -- global interrupt enable */
rval &= ~SDXC_ACCESS_DONE_DIRECT;
mmc_writel(host, REG_GCTRL, rval);
```

and also programs `REG_DLBA` (the IDMA descriptor list base), `REG_FUNS`,
`REG_DBGC`, `REG_RINTR`.

Patch 0006's CMD53 recovery does a **full controller reset**:

```c
clk_disable_unprepare(host->clk_mmc);
if (!IS_ERR(host->reset))
        reset_control_reset(host->reset);     /* clears GCTRL, DLBA, ... */
ret = clk_prepare_enable(host->clk_mmc);
...
mmc_writel(host, REG_SD_NTSR, ntsr_saved);            /* restored */
writel(drv_dl_saved, host->reg_base + SDXC_REG_DRV_DL); /* restored */
```

It restores **only** the two timing registers. It never restores `REG_GCTRL`
(grep for `REG_GCTRL` inside the retry block: **0 hits**), never restores
`REG_DLBA`, and never re-runs the init sequence.

So `SDXC_INTERRUPT_ENABLE_BIT` is cleared and never set again. The retried CMD53
itself still completes -- which is why the MMC layer reports success
(`IDST 0xa000 -> 0`) and why every driver-level hypothesis came back clean -- but
from that moment the host is deaf.

## Why this fits every observation

| observation | explanation |
|---|---|
| direction-specific (RX fails, TX fine) | the FIFO error only occurs on CMD53 **reads**, which only carry load inbound. TX never triggers the recovery, so TX never disarms the interrupt. 72 MB of TX ran with **0** FIFO errors. |
| exactly one `cmd53 fifo error`, never a storm | after the first one the controller is deaf, so no further transfers happen to fail |
| the retry "succeeds" | it does -- the data transfer completes; only the interrupt enable is lost |
| `cmd timed-out` 84-250 s later | the aic8800 command channel also waits on completion interrupts |
| RX dies but the AP keeps beaconing | the firmware runs autonomously; it is the host link that is deaf |
| survives 32 dB of RF improvement | nothing to do with the radio |
| unaffected by SDIO clock (25 vs 150 MHz) | nothing to do with bus speed |
| identical on 2024 and 2026 drivers | the bug is in the kernel patch both share |

## Status

**Mechanism confirmed by structure and by the frozen interrupt counters;
causality not yet proven by experiment.** The proof is to restore `GCTRL` (and
`DLBA`) after the reset -- or simply re-run the init sequence -- and check
whether inbound transfers then complete. That is a small change to patch 0006
and it is the next thing to do.

Historical note: `roadmap.md` records that this recovery path had **never been
provoked** when patch 0006 was benchmarked -- the 2026-07-22 bench was a
scp-*pull* (TX), which never triggers it. So the recovery code shipped having
never once executed. The first time it ran was this session.

---

# ACTUAL ROOT CAUSE: the CMD53 retry never completes the request,
# deadlocking the SDIO IRQ thread

**Supersedes the GCTRL section above.** That section identified a real defect but
was wrong about it being the cause -- see "correction" below.

## The evidence

With the board wedged after a failed inbound transfer:

```
PID  STAT  WCHAN                   COMMAND
152  D     mmc_wait_for_req_done   ksdioirqd/mmc1

[<0>] mmc_wait_for_req_done+0x2c/0x10c
[<0>] mmc_wait_for_req+0xb8/0xcc
[<0>] mmc_io_rw_extended+0x198/0x2e8
[<0>] sdio_io_rw_ext_helper+0xf4/0x1c8
[<0>] sdio_readsb+0x20/0x2c
[<0>] aicwf_sdio_readframes+0x68/0xc0 [aic8800_fdrv]
[<0>] aicwf_sdio_hal_irqhandler+0x268/0x34c [aic8800_fdrv]
[<0>] process_sdio_pending_irqs+0x5c/0x1e0
[<0>] sdio_irq_thread+0x78/0x1a0
```

and the controller registers:

```
GCTRL = 0x20000330   BIT(4) interrupt-enable SET
IMASK = 0x0000BBCA   BIT(16) SDXC_SDIO_INTERRUPT *not* set
RINTR = 0x00000000   nothing pending
```

## The chain

`CONFIG_OOB = n`, and the driver calls `sdio_claim_irq()` -- so it depends
entirely on the **in-band SDIO card interrupt**. The Linux SDIO core handles that
by masking the card IRQ, waking `ksdioirqd`, running the card's handler, and
re-enabling the IRQ *after the handler returns*.

1. Card raises its IRQ. Core masks `SDXC_SDIO_INTERRUPT`, wakes `ksdioirqd`.
2. `ksdioirqd` -> `aicwf_sdio_hal_irqhandler` -> `readframes` -> `sdio_readsb`
   issues the CMD53 **read**.
3. That CMD53 hits the FIFO underrun. Patch 0006's retry runs.
4. **The re-issued request never completes.** `mmc_wait_for_req_done()` has no
   timeout, so `ksdioirqd` blocks in D state forever.
5. Because the handler never returns, the core **never re-enables**
   `SDXC_SDIO_INTERRUPT` -- hence `IMASK` bit 16 = 0.
6. No further card interrupts -> inbound data is never fetched -> RX is dead.
7. `cmd timed-out` follows minutes later: the aic8800 command channel needs the
   same thread.
8. Everything else keeps running -- board alive, AP beaconing, TX fine.

## Why this explains every observation

- **Direction-specific**: only inbound traffic drives the card-interrupt path
  through `ksdioirqd`. TX never touches it -- 72 MB of outbound ran with zero
  faults.
- **Deterministic**: the first FIFO error on a read deadlocks the thread. There
  is no second one because nothing else is ever issued.
- **Survives RF and clock changes**: neither affects whether the request is
  completed.
- **Identical on 2024 and 2026 drivers**: the defect is in the kernel patch both
  share.
- **Silent**: no driver-level error, because from the driver's point of view the
  read simply never returns.

## Correction: GCTRL was a real defect, but not the cause

The earlier section is right that `reset_control_reset()` clears
`SDXC_INTERRUPT_ENABLE_BIT` and the retry never restored it -- with interrupts
globally off, the re-issued CMD53 could never complete, which would produce this
same deadlock. That fix was applied and verified in-register
(`GCTRL = 0x20000330`, BIT(4) set).

**But the deadlock persists with GCTRL restored.** So the reset clears more state
than GCTRL alone (or the manual-stop leaves the card unable to answer), and the
re-issued request still never completes. The GCTRL restore is necessary but not
sufficient, and should be kept.

## Two fixes, and the second matters more

1. **Make the retry actually work** -- restore the full controller state after
   `reset_control_reset()`. Started (GCTRL/DLBA/IMASK/FTRGL/TMOUT/RINTR/DBGC/
   FUNS); evidently still incomplete. Calling `sunxi_mmc_init_host()` and then
   re-applying the saved timing may be the more reliable route than enumerating
   registers by hand.

2. **Guarantee the request is always completed.** Whatever else happens, the
   retry path must never leave an mrq outstanding -- on any failure it must call
   `mmc_request_done()` with an error. That converts a permanent, power-cycle-only
   wedge into a recoverable I/O error that the aic8800 driver can report. This is
   the more important of the two: it removes the *class* of failure rather than
   one instance of it, and it is what makes the difference between "WiFi drops a
   frame" and "the board needs unplugging".

Note the reference trees `local/linux-6.16.7` and `local/h713-arm64/linux-6.16.7`
carry the identical retry code, so both have this latent deadlock too.

---

# Bottom-up verification: healthy baseline, and what the watchdog fixed

Run bottom-up as suggested: establish what "working" looks like *before*
provoking anything, instead of reasoning about register values from source.

## Healthy vs stuck, observed

Sampled six times on an idle, working link (mmc1 = SDIO, base 0x04021000):

```
HEALTHY (idle):   GCTRL=0x20000010   IMASK=0x00010000   RINTR=0   IDIE=0
STUCK (old bug):  GCTRL=0x20000330   IMASK=0x0000BBCA   RINTR=0
```

`IMASK=0x00010000` is exactly `SDXC_SDIO_INTERRUPT` (BIT 16) and it is **stable**
-- it does not oscillate between the core masking and re-enabling it, so
`bit16 = 0` in the stuck state really is anomalous, not a sampling artifact.
The stuck value `0xBBCA` is the per-request mask (error + data-over bits) with
the card IRQ masked: the controller sitting mid-transfer, waiting for a
completion that never arrives.

## Phase 2 result: inbound fails at 256 KB

**A 256 KB inbound transfer fails**, with the same `cmd53 fifo error` signature.

This kills the "sustained load" framing that has been carried through this whole
document. It is not a throughput or contention problem: the SDIO **read** path
hits `FIFO_RUN_ERROR` almost immediately on any inbound bulk transfer, while
72 MB of outbound produced zero errors. Earlier runs that moved 1.8 MB before
stalling were the lucky end of the distribution, not the typical case.

## The retry watchdog works, and fixes a real bug

Added `retry_timer` to the host: armed when the retried CMD53 is handed to
hardware, and on expiry it fails the request with `-ETIMEDOUT` and calls
`mmc_request_done()`.

Verified on hardware:

| | before watchdog | after watchdog |
|---|---|---|
| `ksdioirqd/mmc1` | **D** at `mmc_wait_for_req_done` (forever) | **S** at `sdio_irq_thread` |
| `IMASK` bit 16 | 0 -- card IRQ never re-enabled | **set** (0x0001BBC6) |
| watchdog log | -- | `cmd53 retry did not complete within 2000 ms - failing the request` |

So the **kernel-side deadlock is fixed**: the SDIO IRQ thread is no longer
wedged in uninterruptible sleep, and the core re-arms the card interrupt.

## But WiFi still does not survive

After the watchdog fires, the link is still unusable -- no ssh, outbound pull
fails, and the SDIO IRQ counter freezes again. `cmd timed-out` follows ~56 s
later. So the aic8800 driver does not recover from the failed read: its firmware
command channel dies and the interface stays down until reboot.

**Net position.** Two separable problems:

1. **Kernel thread deadlock** -- real, serious (an uninterruptible kernel thread
   is worse than an I/O error), and now **fixed and verified**. Worth keeping on
   its own merits regardless of the rest.
2. **SDIO reads fail on this board** -- unfixed. `FIFO_RUN_ERROR` on inbound
   CMD53 at sizes as small as 256 KB, the controller cannot recover the
   transfer, and the aic8800 driver cannot recover from the resulting error.

The second is the actual "WiFi cannot carry a file" bug and it remains open.

---

# Ground truth from the stock kernel: what its MMC driver does that ours does not

Rather than keep guessing at register values, the stock Android kernel was
extracted and inspected.

## Extraction

`local/stock-boot/boot_a-board-b.img` is an **Android boot image header v3**
(the version field is at offset 40; offset 12 is `ramdisk_size`, *not*
`kernel_addr` -- parsing it as v0/v2 yields garbage). Kernel payload starts at
4096, uncompressed:

```
Linux version 5.4.99-00049-g34f0974adef4-dirty
  (arm-linux-gnueabi-gcc ... Linaro GCC 5.3)  #1006 SMP  Mon Sep 22 09:29:12 CST 2025
```

Note stock runs a **32-bit ARM** kernel; our port is arm64. Extracted copy:
`scratchpad/stock-kernel.bin` (not committed).

## FTRGL is NOT the difference -- speculation closed

The literal `0x20070008` appears **exactly once** in the stock kernel, in a
literal pool immediately after a function that accesses register offset `0x40`
(`ldr r3, [r2, #64]` -- FTRGL). **Stock programs the same FTRGL value we do.**

So the earlier "RX trigger 7 vs burst 8" idea is dead, and it deserved to be:
mainline uses this value too, and on the usual Allwinner convention `RX_TL=7`
means "trigger at >7", which matches burst 8 correctly. Changing it would have
been the same unfounded move as testing an invented SDIO clock.

Corroborating: the **eMMC** controller (mmc0) runs with `FTRGL = 0x00000000` and
works fine, while the SDIO controller (mmc1) has `0x20070008` and fails reads.
FTRGL is not what separates them.

## What stock actually has that we lack

Stock supports six controller revisions and carries **five v5p3x-specific
routines** -- v5p3x is our controller:

```
sunxi_mmc_clk_set_rate_for_sdmmc_v5p3x
sunxi_mmc_init_priv_v5p3x
sunxi_mmc_judge_retry_v5p3x
sunxi_mmc_restore_spec_reg_v5p3x
sunxi_mmc_thld_ctl_for_sdmmc_v5p3x
```

Our mainline-derived driver has **no equivalent of any of them**. Three matter
directly to what we have been chasing:

| stock routine | what we do instead | relevance |
|---|---|---|
| `thld_ctl_for_sdmmc_v5p3x` | **nothing** -- we only *read* THLD (0x100) for error dumps, never program it. Live on the board: `THLD = 0x00000000`. | The card **read** threshold. It gates when the controller will start a read against available FIFO space -- i.e. exactly the read-side overflow protection whose absence produces `FIFO_RUN_ERROR` on inbound CMD53 while writes stay clean. |
| `restore_spec_reg_v5p3x` | hand-rolled: restore `NTSR` + `DRV_DL` only | Stock has a dedicated "restore special registers" step for this controller. We found empirically that our reset loses `GCTRL`/`DLBA`/`IMASK`; stock treats register restoration as a first-class, version-specific operation. |
| `judge_retry_v5p3x` | hand-rolled CMD53 retry with fixed budgets | Stock makes the retry decision version-aware. Ours is a generic phase/FIFO split invented for patch 0006. |

Also present and absent from ours: `sunxi_mmc_set_rdtmout_reg_v4p6x` (read
timeout register), `sunxi_mmc_reg_ex_res_inter`.

## Assessment

The read-threshold gap is the strongest lead yet, and unlike every previous
hypothesis it is **not speculative**: stock has a dedicated routine for it on
this exact controller revision, ours has none, and the register reads zero on
the running board. It is also read-specific, which matches the one hard fact
that has survived every test -- inbound fails, outbound is clean.

Next step would be to implement a `thld_ctl` equivalent for v5p3x. That needs
the values stock writes, which means disassembling
`sunxi_mmc_thld_ctl_for_sdmmc_v5p3x` from the extracted kernel, or recovering
the Allwinner BSP source for it -- not inventing them.

## Disassembly of `sunxi_mmc_thld_ctl_for_sdmmc_v5p3x` -- and why the lead died

Located by scanning for ARM32 `STR Rd,[Rn,#0x100]` near the MMC code (anchored on
the FTRGL literal). File offset 7773612 in `stock-kernel.bin`. Recovered
semantics:

```asm
ldr   r3, [r2, #8]          ; data->blksz          (mmc_data offset 8, Linux 5.4)
ldr   ip, [r2, #24]         ; data->flags
cmp   r3, #4096             ; blksz < 4096
ands  r0, r0, ip, lsr #9    ; AND (flags >> 9) = MMC_DATA_READ    <-- read-only
ldrb  ip, [r5, #70]
add   r3, r3, ip, lsl #2
cmp   r3, #1024             ; blksz + (x<<2) <= 1024
ldrb  r3, [r1, #16]         ; ios->timing
cmp   r3, #9                ; timing == 9  (HS200)
cmpne r1, #1                ;   or timing-5 <= 1  -> 5 (SDR50) / 6 (SDR104)
bhi   <disable>
; enable:
ldr   r3, [r0, #0x100]
bic   r3, r3, #0x0FF00000   ; \ clear bits [27:16] = threshold size
bic   r3, r3, #0x000F0000   ; /
orr   r3, r3, r4, lsl #16   ; size = blksz << 16
orr   r4, r3, #1            ; bit 0 = read-threshold enable
; disable:
bic   r4, r4, #1
str   r4, [r3, #0x100]
```

So the register contract is now known exactly: **THLD bits [27:16] = read
threshold size, bit 0 = enable**, applied only to reads.

**But it does not apply to us.** Our SDIO link runs at
`timing spec: 2 (sd high-speed)` (`/sys/kernel/debug/mmc1/ios`), and stock only
enables the threshold for timing 5/6/9. **Stock would leave `THLD = 0` on this
link too** -- exactly what we observe. It is not a difference, and implementing
it would change nothing at this bus speed.

## Score so far on stock-vs-ours

| candidate difference | verdict |
|---|---|
| `FTRGL` value | **same as stock** (`0x20070008`, one literal, beside FTRGL-offset code) |
| card read threshold (`THLD`) | **same as stock** at our timing -- stock disables it below SDR50 |
| `GCTRL` BIT(4) semantics | confirmed from stock's own code (`orr r5,#16`), and our restore is correct |
| `restore_spec_reg_v5p3x` | **stock has it, we do not** -- still an unexamined difference |
| `judge_retry_v5p3x` | **stock has it, we do not** -- still an unexamined difference |

Two speculative register leads are now closed with evidence rather than opinion.

## The obvious next move

We have been comparing our *driver* against stock's *source*, but never against
stock's *running configuration*. Per `memory: vendor-stack-is-bootable`,
`run switch_vendor` boots the full vendor Android stack on this board. Booting it
and reading `/sys/kernel/debug/mmc1/ios` plus the live `GCTRL/FTRGL/THLD/TMOUT`
registers would answer, with no inference at all:

- what **timing and clock** stock actually runs the AIC8800 SDIO link at (if it
  uses SDR50, the read threshold *is* live for stock and dead for us -- a real,
  concrete difference)
- what the controller registers hold during healthy sustained RX
- whether stock can do a large inbound transfer over the same link

That converts the entire remaining question from code archaeology into a direct
A/B against a known-good system.

---

# THE CONFIGURATION DIFFERENCE: our DT never enables the UHS modes

Found by comparing the stock device tree against ours, after booting the vendor
U-Boot proved awkward (see below). This is the first difference between stock and
our stack that is **unambiguous and not speculative**.

## Stock's SDIO node vs ours

Stock (`local/h713-lab/analysis/board-a-stock-20260622/vendor_boot_a-unpack/dtb.dts`,
the `sunxi-mmc-v5p3x` node carrying `cap-sdio-irq`):

```dts
compatible = "allwinner,sunxi-mmc-v5p3x";
max-frequency = <0x2faf080>;   /* 50 MHz */
cap-sd-highspeed;
keep-power-in-suspend;
sd-uhs-sdr25;
sd-uhs-sdr50;                  /* timing 5 */
sd-uhs-ddr50;
sd-uhs-sdr104;                 /* timing 6 */
cap-sdio-irq;
```

Ours (`patches/kernel/0024`, `mmc@4021000`):

```dts
compatible = "allwinner,sun50i-h713-mmc";
bus-width = <4>;
cap-sd-highspeed;
cap-sdio-irq;
no-mmc;
no-sd;
/* no max-frequency, no sd-uhs-* of any kind */
```

| property | stock | ours |
|---|---|---|
| `max-frequency` | 50 MHz | **absent** |
| `sd-uhs-sdr25` / `sdr50` / `ddr50` / `sdr104` | **all four** | **none** |
| `keep-power-in-suspend` | yes | absent |

Consequence, measured on the running board: `/sys/kernel/debug/mmc1/ios` reports
`timing spec: 2 (sd high-speed)` at 25 MHz. Without the `sd-uhs-*` properties the
core cannot negotiate anything faster, so the link is capped at SD-HS.

## Why this reconnects to the read threshold

`sunxi_mmc_thld_ctl_for_sdmmc_v5p3x` enables the card read threshold **only** for
timing 5 / 6 / 9. Stock declares SDR50 and SDR104, so on stock the link runs at
timing 5 and the read threshold **is active**. On ours the link is stuck at
timing 2, where the threshold is never enabled -- and our driver has no threshold
support at all.

So the earlier conclusion ("the threshold is a no-op for us, therefore not a
difference") was correct as far as it went, but it had the causality backwards:
**the threshold is inert for us because our DT keeps the link in a mode where it
does not apply.** The DT omission is upstream of it.

**Stated carefully:** this is a confirmed configuration divergence with a
plausible mechanism, not a proven cause. It is odd on its face that the *slower*
mode is the one that overflows the read FIFO, and that wrinkle is unexplained --
at SD-HS stock would not enable the threshold either. What can be said without
overreach is that stock runs a mode we have never run, with a read-path
protection we have never had, and that this is the only unambiguous
configuration difference found in the whole investigation.

## Next test (non-speculative)

Add stock's declared capabilities to our `mmc@4021000` node -- `max-frequency`,
`sd-uhs-sdr25/sdr50/ddr50/sdr104`, `keep-power-in-suspend` -- rebuild, and check:

1. does `/sys/kernel/debug/mmc1/ios` then report `timing spec: 5` (SDR50)?
2. does an inbound transfer work?

We are not inventing values here: they are copied from the vendor's own device
tree for this exact board and controller.

If the link comes up at SDR50 but reads still fail, the next step is implementing
`thld_ctl` -- whose register contract is now fully recovered (THLD bits [27:16] =
`blksz`, bit 0 = enable, reads only).

## Note on the vendor-boot detour

`boot_vendor` (magic to an RTC scratch register + reset) is a **no-op** while our
boot0 is installed -- it simply reboots into our stack.

`switch_vendor` works and installs the vendor first stage (verified: it writes
64 blocks from sector 0x100 to sector 0x10). After a cold boot the board comes up
in the **vendor U-Boot 2018.05** (Allwinner, arm-linux-gnueabi-gcc) rather than
ours. But its environment is the generic default (`bootcmd=run distro_bootcmd`,
which is undefined) and `BOOTMODE=standby`, so Android does not auto-boot;
`sunxi_flash read 0x48000000 boot_a` also returned no valid Android header. Full
vendor Android boot was not achieved this session.

**The board is currently left in vendor-boot mode.** Restoring our stack means
putting our boot0 back at sector 0x10 (FEL, per `memory: vendor-stack-is-bootable`).

## Test: enabling stock's UHS modes -- FAILS, and says why

Added stock's declared capabilities to `mmc@4021000` (`sd-uhs-sdr25/sdr50/ddr50/
sdr104`, `max-frequency` 25 -> 50 MHz), rebuilt, RAM-booted.

**Result: SDIO init hangs.** `systemd-modules-load.service` ran to its 6-minute
timeout, retried, timed out again at 3 minutes, and **FAILED**. The board reached
`multi-user.target` but with no aic8800 modules, no `wlan0`, no hotspot, no ssh --
and the serial console went silent (getty never became usable).

This is not outcome 1, 2 or 3 from the plan; it is a fourth: the link does not
merely stay at timing 2, it **cannot initialise at all**.

## Why -- the missing piece is the per-speed delay tuning

Stock's SDIO node carries delay tables our DT and driver have no equivalent of:

```dts
sunxi-dly-52M-ddr4 = <0x01 0x00 0x00 0x00 0x02>;
sunxi-dly-104M     = <0x01 0x01 0x00 0x00 0x01>;
sunxi-dly-208M     = <0x01 0x00 0x00 0x00 0x01>;
ctl-spec-caps      = <0x08>;
```

These feed `sunxi_mmc_clk_set_rate_for_sdmmc_v5p3x` / `sunxi_mmc_set_clk_dly` --
stock **retunes the sampling delays for every speed mode**. Our driver hardcodes
a single `NTSR = 0x81710110` chosen for 25 MHz and never changes it.

So declaring SDR50 asks the controller to sample at a rate its delay
configuration was never tuned for. That also retro-explains the DT comment
recorded during the original bring-up -- *"the AIC8800 port hits CMD53 DMA errors
on large transfers at 50 MHz"* -- as the same problem, hit from the other side.

Also confirmed from the stock DT: it has **no `vqmmc-supply`** (and no
`vmmc-supply` either), so the 1.8 V-signalling concern was not the blocker.

## Ordering for whoever picks this up

The UHS modes cannot be enabled on their own. The dependency chain is:

1. implement per-speed delay tuning (`set_clk_dly` equivalent) using the values
   in the stock DT above -- **not invented**, read from the vendor's own tree
2. *then* declare the `sd-uhs-*` capabilities
3. *then* the link can reach timing 5, where `thld_ctl` becomes applicable
4. *then* implement `thld_ctl` (register contract already recovered: THLD
   bits [27:16] = `blksz`, bit 0 = enable, reads only)

Each step is a prerequisite for the next. Attempting step 2 alone -- which is
what this test did -- breaks SDIO init outright.

**Board state:** the change was RAM-loaded only. A power cycle returns the board
to the flashed 25 MHz kernel, which works. `patches/kernel/0024` was never
modified; the edit lives only in `build/linux-debug-mmcinstr`.

---

# 2026-08-18 continuation — UHS works, startup CRCs removed, board RX fixed

This section supersedes the old “ordered next steps” above. The investigation
continued from repeated cold boots at the U-Boot prompt and ended with the
original acceptance test passing in both directions. No image was flashed.

## 1. Recovered and implemented the v5p3x controller contracts

The mainline host was extended with the pieces recovered from Allwinner's
v5p3x driver:

- separate per-speed command/data drive and sample phases
- the v5p3x CMD11 and update-clock voltage-switch bits
- v5p3x `WAIT_PRE_OVER` behavior
- v5p3x read-threshold register programming
- the stock v5p3x FIFO trigger value (`FTRGL=0x200700f8`)
- UHS declarations in the H713 SDIO node
- AIC `FEATURE_SDIO_CLOCK_V3=0`, so the vendor module no longer overwrites the
  rate negotiated by the MMC core

This became `patches/kernel/0043-mmc-sunxi-v5p3x-delays-threshold-and-uhs.patch`
and was committed as:

```text
df1738e mmc: sunxi: add H713 v5p3x UHS negotiation
```

### Hardware result at 50 MHz

The board successfully negotiated and enumerated:

```text
4-bit UHS-SDR104
clock/actual: 50000000 Hz
DRV=00030000
NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card
```

Therefore the UHS transition and controller command path work. The boundary is
equally important: the first 512-byte CMD53 failed at 50 MHz. A bounded sweep
of seven command/data sample and data-drive combinations produced data-CRC or
end-bit errors (`RINT=0x80` or `0x8000`), always with `IDST=0`. UHS negotiation
works; 50 MHz UHS payload transfer is not yet reliable.

## 2. Repaired the retry mechanism without treating it as the solution

`reset_control_reset()` erases the SDIO bus clock and width. The old retry path
restored timing registers but then reissued CMD53 with no card clock and in
one-bit mode, so it could never complete. The repair saves/restores `CLKCR` and
`WIDTH`, turns the output clock back on, cancels a retry watchdog when a retried
request reaches IRQ, and makes the phase sweep match the v5p3x fields.

This became:

```text
patches/kernel/0044-mmc-sunxi-restore-bus-state-for-cmd53-phase-retry.patch
977244c mmc: sunxi: restore bus state before CMD53 retry
```

The seven-state 50 MHz run completed every attempt and then failed cleanly;
`ksdioirqd/mmc1` did not wedge. This proved that recovery mechanics were fixed,
not that recovery could make an invalid sampling state reliable.

## 3. CRC is MMC/SDIO, not the cryptography engine

The CRC and end-bit status comes from the SD/MMC controller/card protocol. The
CE is not on the CMD53 data path and does not generate or validate these CRCs.
Nothing in this session enabled or depended on the CE. The errors at 50 MHz
were genuine MMC sampling/data-integrity errors, not malformed output from a
disabled crypto engine.

## 4. SDR25 isolated and removed the first two errors

For the next diagnostic, the DT advertised only `sd-uhs-sdr25` and capped the
host at 25 MHz. The first run negotiated 4-bit SDR25 at 25 MHz but began at the
v5p3x 26 MHz default:

```text
DRV=00010000 NTSR=81710000
```

The first CMD53 produced two data-CRC errors. The retry sweep reached:

```text
DRV=00030000 NTSR=81710010
```

and firmware loading then succeeded. This was an empirical, reproducible
known-good SDR25 state, not a reason to accept two startup failures.

`patches/kernel/0045-mmc-sunxi-use-validated-sdr25-for-h713-wifi.patch`
programs that state before the first CMD53 by separating command and data
sample phases:

- command drive = 1
- data drive = 1
- command sample phase = 1
- data sample phase = 0

On the next cold initialization, the same state was present before enumeration,
firmware loaded, the hotspot started, and there were **zero startup CRCs or
retries**. This directly satisfies the requirement to avoid the errors rather
than rely on recovery.

## 5. SDR25 still failed under board-RX load before the IDMA fix

With clean startup and the known-good SDR25 phase, the original 8 MiB
workstation-to-board copy still failed later under load. This was a different
failure from the immediate 50 MHz sampling errors.

The first fault was:

```text
cmd53 fifo error (RINT=0x00000800 IDST=0x0000a000)
```

- `RINT=0x800` = `HARD_WARE_LOCKED`
- `IDST=0xa000` = IDMA state `WRITE_REQUEST_WAIT`

Retries then alternated FIFO/hardware-lock errors with response timeouts:

```text
RINT=0x00000200 IDST=0x00000002
```

where `IDST=0x2` is the IDMA receive-interrupt bit. After the bounded retries,
the AIC command queue died, but the console remained responsive and
`ksdioirqd/mmc1` was `S` in `sdio_irq_thread`. The deadlock fix still held.

This changed the diagnosis: UHS-SDR25 and phase selection solved initialization
but did not solve the original receive-path failure. The first under-load state
pointed at the controller's IDMA destination path.

## 6. Root cause: v5p3x maximum descriptor size is explicit, not zero

The decisive comparison was between:

- our `sunxi_mmc_init_idma_des()` in `drivers/mmc/host/sunxi-mmc.c`
- Allwinner's `/tmp/linux-orangepi-v5p3x/drivers/mmc/host/sunxi-mmc.c`
- v5p3x limits in `sunxi-mmc-v5p3x.c`
- Linux SDIO request construction in `drivers/mmc/core/sdio_ops.c`

The v5p3x host advertises `max_seg_size = 1 << 12 = 4096`. Linux therefore
splits a large CMD53 buffer into exact 4096-byte SG entries. Our descriptor
builder inherited this rule from older sunxi controllers:

```c
if (chunk_len == max_len)
        pdes[n].buf_size = 0;
```

Allwinner's v5p3x driver does not use the zero shorthand. It writes the actual
length, including `4096`, into every descriptor. This aligns exactly with the
observed receive failure: IDMA had no valid destination progress while the card
continued filling the receive FIFO, ending in `HARD_WARE_LOCKED`.

The diagnostic fix is intentionally variant-specific:

```c
if (chunk_len == max_len && !host->cfg->v5p3x)
        pdes[n].buf_size = 0;
else
        pdes[n].buf_size = cpu_to_le32(chunk_len);
```

It is stored as:

```text
patches/kernel/0046-mmc-sunxi-use-v5p3x-max-idma-descriptor-size.patch
```

## 7. Decisive passing run

The complete 45-patch series (through 0046) applied cleanly to a fresh
Linux 6.18.38 tree and built with the `sysrq` debug fragment:

```text
tree: build/linux-6.18.38-7fe9c8012b420d50f3c780e37beb11572244602694ea9576cd633d7e33501105
FIT:  build/out/h713-kernel-sysrq.fit
size: 7745528 bytes
FIT sha256: b057085e8f61d079806d0f9fb31b41e1dffcebbdef9948da6f48eb72351d06fe
kernel sha256: 1ff4ccbd087a04e588bec929186b4024bc2d37fdf224c362d18b5f57c2500516
DTB sha256:    04b36cda64e51dbbe87ee9c398dcb7e2c8b5ac26a80122a12dcad5ee97ddb80c
```

U-Boot `iminfo` verified both FIT subimage hashes before execution.

### Boot result

Cold SDIO initialization selected the validated state directly:

```text
v5p3x delay: rate=400000 timing=4 width=4 DRV=00030000 NTSR=81710010
v5p3x delay: rate=25000000 timing=4 width=4 DRV=00030000 NTSR=81710010
mmc1: new UHS-I speed SDR25 SDIO card at address 85e2
```

The AIC firmware loaded and the AP started without any CMD53 error or retry.
The workstation associated as `192.168.4.78`; the board was `192.168.4.1`.

### Board RX: workstation → board

Source:

```text
/tmp/h713-sdr25-8m.bin
8388608 bytes
sha256 4896f3533e373a1f4b8e898750461c9f837d303178fa6b03bf3dc3b31fec4269
```

Destination `/tmp/h713-idma-8m.bin` on the board was 8,388,608 bytes and had
the identical SHA-256. This is the direction that had failed in every prior
acceptance run.

### Board TX: board → workstation

The board file was copied back to `/tmp/h713-idma-back.bin`. It was 8,388,608
bytes and had the identical SHA-256.

### Final controller state

```text
clock:          25000000 Hz
actual clock:   25000000 Hz
bus width:      4 bits
timing spec:    4 (sd uhs SDR25)
signal voltage: 0 (3.30 V)
ksdioirqd/mmc1: S in sdio_irq_thread
```

Final `dmesg` grep for `cmd53|fifo error|phase error|CRC|HARD|timed-out`
contained only the CPU's “CRC32 instructions” feature line: **zero SDIO faults
or retries across boot and both transfers**.

## 8. Harness mistake during the passing build (do not repeat)

`tools/serial/boot_kernel.py` sets:

```text
rdinit=/init
```

but this FIT has no initramfs and must mount Debian from eMMC. The first launch
therefore panicked at `VFS: Unable to mount root fs`, rebooted, and U-Boot
overwrote the RAM address while attempting its default boot. The FIT itself had
already passed hash verification; no SDIO conclusion was drawn from this run.

After a second UART upload, the successful boot used:

```text
setenv fdt_high 0x4f000000
setenv initrd_high 0x4f000000
setenv bootargs 'console=ttyS0,115200 earlycon loglevel=8 root=/dev/mmcblk0p26 rootwait rootfstype=ext4 rw net.ifnames=0 panic=10 clk_ignore_unused pd_ignore_unused cma=128M'
iminfo 0x50000000
bootm 0x50000000
```

Update the helper before using it for this Debian-root workflow.

## 9. Repository and board handoff state

Committed:

```text
df1738e mmc: sunxi: add H713 v5p3x UHS negotiation
977244c mmc: sunxi: restore bus state before CMD53 retry
9d7054c mmc: sunxi: use validated SDR25 timing for H713 WiFi
7ac0845 mmc: sunxi: encode v5p3x max IDMA segment explicitly
```

The two hardware-passing patches and their `series` entries are committed.
Remaining intentionally untracked state at handoff:

```text
?? patches/kernel/board/sysrq.config     # debug only
?? .backup/                              # user-owned; do not touch
```

The board is left running the successful kernel from RAM, hotspot up, after
both passing transfers. Nothing was flashed. A power cycle returns to the
previously flashed kernel, which lacks 0045/0046 and must still be considered
broken for board RX.

Next: build a normal non-sysrq FIT, repeat a cold-boot two-direction 8 MiB test
plus a longer soak, then ask before flashing. The extra board USB/OTG cable is
not used; UART is the only required cable.

## 10. Quick 25 MHz vs 50 MHz comparison recipe

The committed `patches/kernel/series` is the known-good 25 MHz control. Leave
it unchanged for baseline tests: 0045 selects SDR25 at 25 MHz and initializes
the validated delay state, while 0046 fixes exact-4096-byte v5p3x IDMA
descriptors.

To make a temporary **RAM-only** 50 MHz comparison build, remove only the 0045
line from `patches/kernel/series`; keep 0043, 0044, and 0046. This re-exposes
0043's all-UHS, 50 MHz configuration without losing the bidirectional IDMA
fix. Keep AIC `FEATURE_SDIO_CLOCK_V3=0`, record the resulting FIT hash, and do
not flash the experiment.

Confirm the selected rate and mode in `/sys/kernel/debug/mmc1/ios`, then repeat
the two-direction 8 MiB hash test and the final SDIO error grep. The expected
control is 25,000,000 Hz/SDR25. A previous 50,000,000 Hz/SDR104 build
enumerated successfully but failed its first 512-byte CMD53 data transfer with
CRC/end-bit errors, so enumeration alone is not acceptance. Restore the 0045
line after the A/B run; any later 50 MHz tuning should change only timing/delay
variables while retaining 0046 and comparing against the unchanged 25 MHz
control.
