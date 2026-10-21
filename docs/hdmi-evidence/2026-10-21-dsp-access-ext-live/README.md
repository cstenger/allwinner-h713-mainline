# Staged DSP access extension — live run, October 21, 2026

**Result: all 82 steps passed on a fresh cold logo-free boot (`cold-ext-01`),
ending in an orderly poweroff.** Every power-domain, clock, reset and TVFE
CCU operation of the old monolithic setup that precedes AudioTop completes
once TVCAP is actually powered and its bus reset released. **AudioTop, the
DSP port and the lock window were not accessed.** Automatic warm HDMI
recovery remains unimplemented.

Context: [extension design](../../hdmi-dsp-access-extension-design-2026-10-21.md),
[offline preparation](../2026-10-21-dsp-access-ext/README.md),
[prefix runs](../2026-10-21-dsp-access-prefix/README.md),
[stalled monolithic attempt](../2026-10-21-dsp-cold-access/README.md).
Times are host time; correlation is by boot ID and kernel monotonic time.

## The finding

At a cold logo-free start **TVCAP is physically off and its bus reset is
asserted**:

| Evidence | Value |
| --- | --- |
| U-Boot preboot trace (`cold-uboot.log`), CCU `0xd88` | `tvcap_bus=00000000`: gate off, reset bit 16 asserted |
| `pm_genpd_summary` with boot-v4, before the module (`linux-preflight.txt`) | `TVCAP off-0`, `TVFE off-0` |
| Step 35, PPU TVFE status `0x070010a4` | `00020000` (off) |
| Step 36, PPU TVCAP status `0x07001124` | `00020000` (off) |
| Step 38, `reset_bus_tvcap` status | `1` (asserted) |

The old bench booted the boot-v3 DT, which keeps `allwinner,keep-tvcap-on`.
That makes genpd report TVCAP on without reading hardware, so its TVCAP
resume did nothing. Nothing in it releases `reset_bus_tvcap`. It therefore
reached its AudioTop read with TVCAP unpowered and in reset. Accessing a
block behind an unpowered TV domain hard-locked the board in 2026-09 (patch
0087) with the same symptoms as October 21. This is now the leading
explanation for the stall. It is **not yet proven**: whether AudioTop sits
behind TVCAP (or needs its reset) is the AudioTop stage's first question.

## Run record (`cold-ext-01/`)

Boot `0c26fed5-c211-4dbd-8c68-7aa45b942bd9`. Extension bundle: module
`39d2a2e9…`, helper `7ca50c19…`, guard `96f37655…` (already live).

1. **Cold catch** (`cold-catcher-events.log`, `cold-uboot.log`): one SPL
   banner; GP6/GP7 and MIPS clock/reset/status zero; one autoboot interrupt.
2. **boot-v4 RAM boot** (`ram-boot.log`): 22/22 guarded steps OK, including
   `fdt rm … allwinner,keep-tvcap-on` (step 17) and the v2 marker; bootm
   sha256 OK. The kernel no longer prints "TVCAP domain retained from boot".
3. **Health** (`uart-identity.txt`, `linux-preflight.txt`): UART and SSH boot
   IDs match; ext4 mounted cleanly (no journal replay; the previous poweroff
   was orderly); growfs finished. v1 and v2 markers present, retention flag
   absent, display and CPU_COMM disabled, no handoff, HDMI units skipped, no
   h713 modules. Only `bus-disp` (and its `pll-periph0` parent) hardware-on
   among the 17 clocks.
4. **Staging** (`stage-bundle.txt`) into `/root/hdmi-dsp-access-ext-2026-10-21`;
   **console** (`console-calibration.txt`): printk 5→7, `kernel.panic` 5→0,
   notice marker seen on the UART.
5. **Load** (`load.txt`): INIT DONE `extension=1`.
6. **Steps 1–82** (`step-NN.txt`), one helper call each. Each required its
   acknowledgment and exactly one UART BEGIN and DONE; the step 1–8 pairs were
   checked before step 9. At every stage boundary (33, 40, 45, 53, 69, 74,
   81) a read-only snapshot (`snapshot-after-NN*.txt`: clock and genpd
   summaries) was reviewed before `--stage-ack`.
7. **End** (`status-final.txt`): completed = attempted = 82,
   `extension_complete=Y`, failed N. 82 BEGIN/DONE pairs, 31 OP-DONE markers,
   4 genpd events; no warning, error or RCU line after boot.
8. **Poweroff** (`poweroff-request.txt`, end of `bench-uart.log`): orderly
   `systemctl poweroff` with the module loaded; root remounted read-only;
   guard logged "poweroff with HDMI holds retained"; `reboot: Power down`.

| Steps | Result |
| --- | --- |
| 1–33 | As `cold-prefix-02`: MIPS 0, SCP 0, demod bus 0, display bus `00010001`, display reset 0, demod reset 1 |
| 39 | Clock mask `00010000`: only `bus-disp` enabled |
| 40 | TVFE CCU words `01000005 0 7 2 5 4 4 b 20a 2 2 7 2 20b 20b`, identical to the U-Boot trace |
| 41–44 | TVFE then TVCAP: genpd PRE_ON/ON events inside each transition; PPU status `00010000` each |
| 45 | MIPS/SCP still stopped |
| 46 | TVCAP reset **released** (deassert performed), reads deasserted |
| 47–50 | bus-tvcap, bus-cap-300m, vincap-dma (pulled pll-video2), tvfe-1296m at 1296 MHz (pulled pll-video0) |
| 51 | Demod reset released |
| 52–53 | pll-video0 already on; pll-adc enabled |
| 54–68 | All 15 stock TVFE words read back exactly |
| 69 | Demod bus `00010001` (gate and reset set) |
| 70–74 | bus-hdmi-audio, hdmi-audio (pulled pll-video3, 996 MHz); audio-cpu/umac/ihb already on via the raw words |
| 75–80 | pll-video2 already on; deint, panel, svp-dtl, afbd enabled; bus-disp already on |
| 81 | Display reset already released: recorded no-op |
| 82 | MIPS/SCP stopped, both PPU domains ON |

The raw TVFE words enable gates behind the clock framework (snapshot after
69 shows `hw=Y` with enable count 0 for i2h, cip-*, audio-*, tsa432, mpg0/1).
This is expected and harmless here because no restore follows.

## What this does and does not establish

Positive: in a cold logo-free boot, with boot-v4, the complete pre-AudioTop
setup reaches a hardware-verified state. Both TV domains are on, the TVCAP
and demod resets are released, the receiver, audio and display clocks run,
and the stock TVFE words are in place. MIPS and SCP stay stopped throughout.

Not established: anything about AudioTop or later, including whether
AudioTop needs TVCAP, TVFE or both. Also not shown here: DSP state, warm-reset
retention, or behaviour with MIPS running. The display tree ran last here, not
first as in the old bench; the old order specifically is not separately
excluded.

`sha256.json` covers every file in `cold-ext-01/` and this README.
