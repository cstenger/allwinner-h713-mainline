# Handoff — WiFi / SDIO

Updated: **2026-08-18**

Branch: **`h713-aic8800-vendor-rebase`**

Full chronological evidence: [wifi-failure-2026-08-17.md](wifi-failure-2026-08-17.md)

This is the orientation document. The evidence log is intentionally long and
contains the commands, register values, failed hypotheses, and raw outcomes.

## Bottom line

The original acceptance test now passes in both directions on a RAM-loaded
kernel:

| direction | result |
|---|---|
| workstation → board (board RX), 8 MiB | **PASS**, SHA-256 exact |
| board → workstation (board TX), 8 MiB | **PASS**, SHA-256 exact |
| SDIO errors/retries during boot and both copies | **zero** |
| `ksdioirqd/mmc1` afterward | healthy, `S` in `sdio_irq_thread` |

Test payload SHA-256:
`4896f3533e373a1f4b8e898750461c9f837d303178fa6b03bf3dc3b31fec4269`.

The root cause was the v5p3x IDMA descriptor encoding for an exact maximum-size
segment. Linux splits a large SDIO transfer into 4096-byte SG entries because
the v5p3x host advertises `max_seg_size = 4096`. Our descriptor builder encoded
an exact 4096-byte entry as zero, inherited from older sunxi controllers. The
Allwinner v5p3x driver writes **4096 explicitly**. Making that distinction for
`host->cfg->v5p3x` eliminates the board-RX FIFO/hardware-lock failure.

## What is committed

Four hardware-tested changes were committed during this session:

- `df1738e mmc: sunxi: add H713 v5p3x UHS negotiation`
  - per-speed v5p3x delay programming
  - v5p3x CMD11/update-clock semantics
  - v5p3x card-read threshold support
  - stock FIFO trigger value
  - UHS capability declarations
  - AIC V3 clock override changed to `0`, preserving the MMC core's negotiated
    clock
- `977244c mmc: sunxi: restore bus state before CMD53 retry`
  - restores `CLKCR` and `WIDTH` after the controller reset
  - keeps retry bounded and mechanically functional
  - also carries the one-character hunk-count repair found by applying the
    complete patch series from scratch
- `9d7054c mmc: sunxi: use validated SDR25 timing for H713 WiFi`
  - selects UHS-SDR25 at 25 MHz and programs the cold-start phase state that
    avoids the first two CRC errors
- `7ac0845 mmc: sunxi: encode v5p3x max IDMA segment explicitly`
  - applies the Allwinner v5p3x 4096-byte descriptor contract
  - makes the original inbound WiFi acceptance test pass

The important boundary on `df1738e`: our code successfully negotiates and
enumerates 4-bit UHS-SDR104 at 50 MHz, but the first 512-byte CMD53 at that rate
still fails with data CRC/end-bit errors. The commit is a UHS-negotiation
milestone, not a claim that 50 MHz payload transfer works.

## Working configuration

The successful 25 MHz configuration is the final pair in the committed series:

- `patches/kernel/0045-mmc-sunxi-use-validated-sdr25-for-h713-wifi.patch`
  - limits the SDIO node to UHS-SDR25 at 25 MHz
  - programs the validated cold-start state before the first CMD53:
    `DRV=00030000`, `NTSR=81710010`
  - avoids the two initial data-CRC errors rather than relying on recovery
- `patches/kernel/0046-mmc-sunxi-use-v5p3x-max-idma-descriptor-size.patch`
  - encodes an exact 4096-byte v5p3x IDMA buffer as `4096`, not `0`
  - this is the change that made the original inbound copy pass

`patches/kernel/series` includes both 0045 and 0046 in the tested order.

Still untracked:

- `patches/kernel/board/sysrq.config` — debug/test configuration only
- `.backup/` — user-owned; **do not touch or add it**

## Decisive evidence

### Clean cold initialization

With 0045 and 0046 applied, the board logged:

```text
v5p3x delay: rate=400000 timing=4 width=4 DRV=00030000 NTSR=81710010
v5p3x delay: rate=25000000 timing=4 width=4 DRV=00030000 NTSR=81710010
mmc1: new UHS-I speed SDR25 SDIO card at address 85e2
```

The firmware loaded and `wlan0`/the hotspot came up with no `cmd53`, CRC,
FIFO, hardware-lock, phase-retry, or timeout messages.

### Failure immediately before the descriptor fix

At the same SDR25 rate and phase state, but with the old zero encoding, startup
was clean and the 8 MiB inbound copy later failed under load. Its first fault
was:

```text
RINT=0x00000800 IDST=0x0000a000
```

`RINT=0x800` is `HARD_WARE_LOCKED`; `IDST=0xa000` is the IDMA
`WRITE_REQUEST_WAIT` state. Retries then showed response timeouts
(`RINT=0x200`) interleaved with IDMA receive completion (`IDST=0x2`). The
kernel remained responsive and `ksdioirqd` returned to `S`, proving the earlier
deadlock fix still held, but the AIC command channel was dead.

### Success with explicit 4096-byte descriptor lengths

FIT boot and both subimage hashes were verified by U-Boot. The board mounted
the normal Debian root and negotiated:

```text
clock:          25000000 Hz
actual clock:   25000000 Hz
bus width:      4 bits
timing spec:    sd uhs SDR25
signal voltage: 3.30 V
```

Then:

1. workstation `192.168.4.78` copied 8 MiB to board `192.168.4.1`
2. board file size was 8,388,608 bytes and SHA-256 matched
3. the same file was copied back to the workstation
4. workstation size and SHA-256 matched
5. final `dmesg` contained no SDIO error/retry messages

This isolates the bulk-RX fix from the earlier phase work: 0045 removed the two
startup CRC errors; 0046 removed the later inbound-load failure.

## What was learned about the controller

- The SD/MMC command path, four-bit setup, UHS negotiation, firmware transfers,
  and bidirectional bulk transfer all work with the correct v5p3x contracts.
- The eMMC on the separate controller continues to enumerate at HS400.
- The CRC/end-bit checks are performed by the MMC controller/card protocol.
  The cryptography engine (CE) is not involved.
- A generic “controller is broken” explanation is now refuted. The remaining
  50 MHz error is a high-speed timing/signal-integrity problem, separate from
  the fixed 4096-byte IDMA descriptor bug.
- Recovery remains valuable containment, but the passing run generated no
  errors for recovery to handle.

## Current hardware state

The board is currently running the successful image from RAM, with the hotspot
up and both 8 MiB directions verified. Nothing from this session was flashed.

A power cycle returns to the previously flashed kernel, which does **not**
contain 0045/0046 and therefore should still be treated as broken for board RX.
The extra board USB/OTG cable is not required; the UART cable is the only cable
used for the test.

Test artifact:

```text
build/out/h713-kernel-sysrq.fit
size   7745528 bytes
sha256 b057085e8f61d079806d0f9fb31b41e1dffcebbdef9948da6f48eb72351d06fe
kernel 1ff4ccbd087a04e588bec929186b4024bc2d37fdf224c362d18b5f57c2500516
DTB    04b36cda64e51dbbe87ee9c398dcb7e2c8b5ac26a80122a12dcad5ee97ddb80c
```

Prepared kernel tree:
`build/linux-6.18.38-7fe9c8012b420d50f3c780e37beb11572244602694ea9576cd633d7e33501105`.

## Recommended next steps

1. Build the normal production FIT without the `sysrq` fragment.
2. From a true cold boot, repeat:
   - 8 MiB workstation → board with hash verification
   - 8 MiB board → workstation with hash verification
   - a longer/repeated transfer (for example 64 MiB or an 8 MiB loop) to turn
     this from a minimal acceptance pass into a soak result
3. Only after those pass, ask before flashing the kernel persistently.
4. Treat 50 MHz SDR104 data tuning as optional follow-up. The reliable target
   currently demonstrated is UHS-SDR25 at 25 MHz.

Do **not** begin with stock Android/vendor boot anymore; the original failure
now has a locally verified cause and fix. Do not spend time on CE, TCP ACK
filtering, RF strength, skb allocation, or generic retry-count increases; those
paths were tested or rendered irrelevant by the zero-error passing run.

## Boot-test gotcha

`tools/serial/boot_kernel.py` currently installs initramfs-only bootargs
(`rdinit=/init`) and must not be used unchanged for this Debian-root FIT. That
mistake caused one harmless RAM boot to panic before WiFi and overwrote the
uploaded image when U-Boot restarted, requiring a second UART upload.

For this board, set the normal root arguments before `bootm`:

```text
setenv fdt_high 0x4f000000
setenv initrd_high 0x4f000000
setenv bootargs 'console=ttyS0,115200 earlycon loglevel=8 root=/dev/mmcblk0p26 rootwait rootfstype=ext4 rw net.ifnames=0 panic=10 clk_ignore_unused pd_ignore_unused cma=128M'
iminfo 0x50000000
bootm 0x50000000
```

The workstation also prints a changed-host-key warning for `192.168.4.1`
(offending entry currently reported at `~/.ssh/known_hosts:16`), although the
key-based copies completed. Do not modify the user's known-hosts file silently.
