# Handoff — WiFi / SDIO, 2026-08-17

Branch: **`h713-aic8800-vendor-rebase`** (4 commits, **not pushed**).
Full evidence log: [wifi-failure-2026-08-17.md](wifi-failure-2026-08-17.md) (~930 lines).
This file is the orientation; that file is the detail.

---

## The goal

Make WiFi dependable. Concretely: **the board cannot receive a file over WiFi.**
An 8 MB `scp` to it stalls and, before this session's fix, wedged the board hard
enough to need a power cycle.

That is still true. What changed is that we now know *what* is broken, *which
direction*, and *why the board wedged* — and the wedge is fixed.

---

## Bottom line

| | status |
|---|---|
| Vendor driver rebase 2024_0109 → 2026_0123 | **done, committed, runs on hardware** |
| Board wedging on every failed transfer | **fixed and verified** (`ksdioirqd` deadlock) |
| Station churn (16 → 0 reassociations/min) | **fixed** by the rebase |
| **Receiving a file over WiFi** | **still broken** — root cause narrowed, not solved |

---

## The single most useful fact

**The failure is direction-specific.** Same link, same session, same signal:

| direction | size | result |
|---|---|---|
| board **TX** (client pulls *from* board) | 8 MB | 6 s, md5 exact |
| board **TX** | 64 MB | 67 s (0.96 MB/s), md5 exact, **zero faults after 72 MB** |
| board **RX** (client pushes *to* board) | 8 MB | fails, wedges |
| board **RX** | **256 KB** | **also fails** |

Every failing run has exactly **one** `cmd53 fifo error`; every passing run has
none. No exceptions across two driver versions, two SDIO clocks, 40 dB of RF, and
several instrumented builds.

Two framings that were wrong and are now dead:

- **"sustained load"** — 256 KB fails. It is not throughput or contention.
- **"STA mode"** — the failing path is AP mode (client → board's own hotspot).

Why it hid for months: the 2026-07-22 bench that recorded "384 MB clean" was a
client scp-**pull**, i.e. board TX — the direction that works. Sustained board RX
had apparently never been benchmarked.

---

## Root cause of the *wedge* (fixed)

`CONFIG_OOB=n` and the driver uses `sdio_claim_irq()`, so it depends on the
in-band SDIO card interrupt. Linux masks that interrupt, wakes `ksdioirqd`, runs
the driver's handler, and re-enables it **only when the handler returns**.

1. Card IRQ → core masks it → wakes `ksdioirqd`
2. handler issues the inbound CMD53 **read**
3. read hits the FIFO error; patch 0006's retry runs
4. **the re-issued request never completes** — `mmc_wait_for_req_done()` has no
   timeout, so the thread blocks in **D state forever**
5. handler never returns → card interrupt never re-enabled → link deaf
6. `cmd timed-out` follows 84–250 s later (same thread)

Captured directly:

```
ksdioirqd/mmc1  D  mmc_wait_for_req_done
  mmc_io_rw_extended / sdio_readsb
  aicwf_sdio_readframes [aic8800_fdrv]
  aicwf_sdio_hal_irqhandler / process_sdio_pending_irqs / sdio_irq_thread
```

with `IMASK` bit 16 clear and the SDIO IRQ counter frozen, against a healthy idle
value of `IMASK = 0x00010000`.

**Fixed in `patches/kernel/0006`** (commit `7f3d70c`), verified on the flashed
kernel: a 2 s watchdog fails the request and calls `mmc_request_done()`;
`ksdioirqd` returns to `S`, `IMASK` comes back as `0x0001BBC6`. Also restores
`GCTRL`/`DLBA`/`IMASK` etc. after `reset_control_reset()`, which the retry
previously destroyed and never put back.

**Both reference trees (`local/linux-6.16.7`, `local/h713-arm64/linux-6.16.7`)
carry the identical retry code, so the same latent deadlock is in them.**

⚠ **The fix does NOT make shutdown graceful.** I predicted the
`systemd-shutdown ... Waiting for process: hostapd` hang would clear; **it does
not**. `hostapd` blocks separately — most likely in nl80211 on the aic8800
command queue, which is dead after `cmd timed-out`. Board recovers on its own,
but reboot after a failed transfer is still slow.

---

## Hypotheses tested on hardware and REFUTED

Do not repeat these.

| hypothesis | how it died |
|---|---|
| RX skb allocation failure | instrumented both failure branches; **never fired** |
| Driver TCP-ACK filtering (`CONFIG_FILTER_TCP_ACK`) | rebuilt with it `=n`; **identical failure** |
| `FTRGL` misconfiguration | stock programs the **same** `0x20070008` |
| Card read threshold as an independent factor | stock disables it below SDR50 too |
| SDIO clock | 25 MHz → stalls; 150 MHz (vendor default) → **worse**. Not the axis |
| Weak RF / antenna | fails identically at **−31 dBm** after the antenna was fitted |
| Client WiFi power-save (for the churn) | disabling it left the rate unchanged at 16/min |

---

## Two real differences vs stock that remain unexamined

Stock has five `v5p3x`-specific routines; we have none of them. Three matter:

1. **`sunxi_mmc_thld_ctl_for_sdmmc_v5p3x`** — card read threshold.
   **Register contract fully recovered by disassembly:** THLD (`0x100`)
   bits `[27:16]` = threshold size (`data->blksz`), bit 0 = enable; applied only
   when `data->flags & MMC_DATA_READ`; gated on `ios->timing` ∈ {5 SDR50,
   6 SDR104, 9 HS200}.
2. **`sunxi_mmc_clk_set_rate_for_sdmmc_v5p3x` / `set_clk_dly`** — per-speed
   sampling-delay tuning, fed by DT properties we do not have:
   ```
   sunxi-dly-52M-ddr4 = <1 0 0 0 2>;
   sunxi-dly-104M     = <1 1 0 0 1>;
   sunxi-dly-208M     = <1 0 0 0 1>;
   ```
   (full ordered set in stock: `400k, 26M, 52M, 52M-ddr4, 52M-ddr8, 104M, 208M,
   104M-ddr, 208M-ddr`). We hardcode one `NTSR = 0x81710110` for 25 MHz.
3. **`sunxi_mmc_judge_retry_v5p3x`** — version-aware retry decision. Ours is the
   hand-rolled phase/FIFO split in patch 0006.

Plus the DT gap that connects them:

| property | stock | ours |
|---|---|---|
| `max-frequency` | 50 MHz | 25 MHz |
| `sd-uhs-sdr25/sdr50/ddr50/sdr104` | all four | **none** |
| `vqmmc-supply` | none | none (so 1.8 V is *not* the blocker) |

Our link therefore runs `timing 2 (sd high-speed)`, where the read threshold can
never engage.

**Tested and it fails:** adding the `sd-uhs-*` properties alone **hangs SDIO init
outright** (`systemd-modules-load` timed out twice, no `wlan0`, console dead).
The delay tuning is a **prerequisite, not an optional companion**. That also
retro-explains the DTS comment left during the original bring-up — *"CMD53 DMA
errors on large transfers at 50 MHz"*.

---

## Ordered next steps

Each gates the next. Do not skip.

0. **(cheap, do first) Verify stock can actually receive bulk data.**
   Everything below assumes it can — inferred from "it's a casting projector", never
   measured. Android did not boot this session. Costs one `switch_vendor` +
   FEL recovery, both now proven procedures. If stock's RX *also* fails, steps
   1–4 are wasted effort.
1. **Recover the BSP `sunxi_mmc_host` struct layout** from the stripped ARM32
   stock kernel. Both remaining routines are gated on this — every offset
   (`0x288`, `0x488`, `0x290`, …) is meaningless without it. This is the real
   project; budget hours, start deliberately.
2. **Implement per-speed delay tuning** using the `sunxi-dly-*` values above.
3. **Then** declare the `sd-uhs-*` capabilities and check
   `/sys/kernel/debug/mmc1/ios` reports `timing spec: 5`.
4. **Then** implement `thld_ctl` (contract already known, see above).

Independent of all that: **the aic8800 driver does not recover from a failed
read.** Even with the watchdog returning a clean `-ETIMEDOUT`, its command
channel dies and the interface stays down until reboot. Making the driver
survive an I/O error would be valuable on its own.

---

## Practical notes (things that cost time to learn)

- **Serial is the only reliable channel.** `tools/serial/console.py` (paced
  writes), `send_file.py` (~11 KB/s, md5-verified), `load_fit.py` (YMODEM a FIT
  into RAM at `0x50000000`, ~12 min for 7.7 MB, then `bootm` — no flash write,
  power cycle reverts).
- **`sudo` needs a password**; `/proc/interrupts` and `busybox devmem` are the
  cheapest diagnostics on the board. mmc1 = SDIO = `0x04021000`; mmc0 = eMMC =
  `0x04022000`. Identify which IRQ is which by driving eMMC I/O and seeing which
  counter moves — both are named `sunxi-mmc`.
- **Healthy vs stuck registers** (mmc1): healthy idle `GCTRL=0x20000010
  IMASK=0x00010000`; stuck mid-request `GCTRL=0x20000330 IMASK=0x0000BBCA`.
- **Stock kernel**: `local/stock-boot/boot_a-board-b.img` is an Android boot
  header **v3** (offset 12 is `ramdisk_size`, *not* `kernel_addr` — parsing it as
  v0/v2 gives garbage). Kernel at offset 4096, uncompressed, Linux 5.4.99 ARM32.
  **Virtual base = `0xC0008000`**, so `vaddr = 0xC0008000 + file_offset` — that is
  what makes reference-finding possible.
- **`boot_vendor` is a no-op** while our boot0 is installed. **`switch_vendor`**
  writes the vendor boot0 over sector `0x10` (persistent; needs FEL to undo).
  Vendor U-Boot 2018.05 then comes up, but with a generic default env
  (`bootcmd=run distro_bootcmd`, undefined) and `BOOTMODE=standby`, so Android
  does not auto-boot; `sunxi_flash read 0x48000000 boot_a` produced no valid
  header.
- **FEL recovery works** (`docs/flash.md` Method 4) — but **regenerate the SPL
  payload header first**. The committed one was stale (built against an older
  U-Boot, 648 bytes differed) and nothing warns you.
- **Kernel deploy**: `load_fit.py` then
  `fatwrite mmc 1:2 0x50000000 h713-kernel.fit ${filesize}`.
- **`tools/wifi/wifi-baseline.sh`** ships in the image at
  `/usr/local/sbin/wifi-baseline`; it refuses to run off-target (a baseline of
  the wrong machine is worse than none). Fault counters are split into a
  kernel-side **control** group and the AIC8800 group under test — if the control
  moves after a driver swap, the experiment is wrong, not the driver.

---

## Things that were nearly missed

- **The board runs a mismatched firmware variant.** The chip reports
  `is_chip_id_h` (register `0x40500000`); only the 2026 driver has a D80 `_h_`
  list, so it loads `fmacfw_8800d80_h_u02.bin`. The 2024 driver had no such list
  and silently used the non-`_h_` file — for the board's whole life. Impact
  unquantified.
- **Driver and firmware are NOT independently swappable** despite a byte-identical
  `lmac_msg.h`. The wire protocol is unchanged; the *file-selection logic* is not.
- **`kernel_inputs_digest` hashed all of `versions.env`**, so any unrelated pin
  bump invalidated every cached kernel tree — which is why `build/` had 28 of
  them. Fixed to hash only `KERNEL_*`.
- **`fault.fifo_run_error` read 0 through runs that had errors.** `FIFO_RUN_ERROR`
  is a register-bit macro, never log text; the real string is `cmd53 fifo error`.

---

## Housekeeping

- `sudo rm baseline-2024-driver.txt` (root-owned workstation capture, repo root)
- `build/linux-debug-mmcinstr` — 2.1 GB debug tree, deletable
- Board currently: flashed kernel **with** the watchdog, healthy, hotspot up.
