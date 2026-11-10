# U-Boot proper without the reset-time lamp — execution log

Plan: [uboot-lamp-flash-plan.md](../../uboot-lamp-flash-plan.md).

## Step 1 — rescue copy written (2026-10-16) — PASS

`rescue-copy.log`. Staged `proper-installed-1798.bin` on the board; it, the
live LBA `0x49ac00` and the recorded baseline all hash
`c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7`. The spare
slot was all zeros. Wrote 1,798 sectors at LBA `0x4a0c00` (`conv=fsync`), then
with caches dropped and `iflag=direct`: slot reads back `c882461d…`; the 250
sectors after it are zero; `0x49ac00` (`c882461d…`), SPL at `0x10`
(`cb9da874…`) and env (`de2f2560…`) unchanged. `0x49ac00` was not written.

## Step 2 — FEL rescue rehearsal (2026-10-16) — FAIL at U-Boot proper

Attempt 1 (`attempt1/`). FEL enumerated (`fel-version.log`: `soc=00001860(H713)`); `sunxi-fel -p spl
build/out/h713-rescue-spl.bin` (`bcaf5dfa…`). `fel-rescue-serial.log`:

```
U-Boot SPL 2026.07-rc5-g320a17f71d41-dirty (Oct 16 2026 - 01:31:56 -0700)
DRAM: 1024 MiB
Trying to boot from MMC2
NOTICE:  BL31: v2.15.0(release):47ee829f7
NOTICE:  BL31: Built : 03:25:48, Jul 27 2026
NOTICE:  BL31: Detected Allwinner H713 SoC (1860)
NOTICE:  BL31: Found U-Boot DTB at 0x4a0d2900, model: HY200 QZ713DF_A1 (Allwinner H713)
```

Then nothing for the rest of the 40 s capture, no response to input, and
the board still enumerates `1f3a:efe8`. On an eMMC boot the U-Boot banner
follows that BL31 line directly. So FORCE_MMC + the rescue sector work (the
SPL loaded the FIT from `0x4a0c00` and BL31 found its DTB), but **U-Boot
proper does not start when the chain began in FEL**, even when loaded from
eMMC. This is the "U-Boot proper also lands in DRAM" gap in
`docs/flash.md`, not a transfer problem. `fel-spl.log`'s
`usb_bulk_send() ERROR -7` is sunxi-fel waiting for an SPL that by design
never returns to FEL.

No eMMC writes occurred (the rescue SPL writes nothing). **The rescue path is
not proven; step 3 is not executed.** Recover by a full power-off (USB,
serial, power ≥ 1 min); `0x49ac00` is intact.

### Was it USB back-power? No (attempts 2 and 3)

The board does not power down while the FEL USB cable is attached, so attempt
1 started half-powered. **Attempt 2 is invalid** (`attempt2-invalid/`): the
runner fired on the stale FEL device still enumerated from attempt 1;
`sunxi-fel` then failed (`No such device`) and the capture recorded the
operator's *normal* eMMC power-up (SPL `g7b178056c329`, Aug 25), stopped at
the prompt by the runner's keystrokes. The runner now waits for any FEL device
to disappear, then for a fresh one, and requires `sunxi-fel version` to
answer before loading.

**Attempt 3** (`attempt3/`), back-power excluded: USB, serial and power all
unplugged ≥ 1 min; FEL held while applying board power only; USB then serial
plugged afterwards. Fresh device `Device 010`, `soc=00001860(H713)`. The
rescue SPL ran (`g320a17f71d41-dirty`, Oct 16), `Trying to boot from MMC2`,
BL31 found the U-Boot DTB at `0x4a0d2900`, then **no U-Boot banner for 60 s**:
identical to attempt 1. Back-power is ruled out; the FEL-started chain itself
prevents U-Boot proper from running even when proper comes from eMMC. Rescue
path still unproven; `0x49ac00` untouched.

### Prior art in the docs (checked 2026-10-16)

No earlier record of a FEL-started chain reaching BL31 and then stalling
before the U-Boot banner. The closest entries are all earlier stages:

- `docs/flash.md`, `sunxi-fel uboot` (2026-08-25): the SPL stops at
  `Trying to boot from FEL` waiting for the `fel_stash` continuation — it never
  loads U-Boot proper, so it never reaches BL31.
- `docs/reference/h713-fel-notes.md` (July): full-image `sunxi-fel spl`
  wedged before DRAM init in the return-to-FEL/RMR path — since fixed; our run
  is past DRAM and BL31.
- `docs/flash.md`'s "U-Boot proper also lands in DRAM, which is its own
  unresolved issue" is a one-line aside from the 2026-07-29 transport
  correction with no experiment behind it.

The existing restore SPL halts by design, and the 2026-09-29 vendor round
trip returned by restore SPL + power cycle, so neither ever handed a
FEL-started chain to U-Boot proper. Code read: proper's FEL-dependent logic
(`sunxi_get_boot_device()` → `BOOT_DEVICE_BOARD` → `fel_booted`, env
location, `parse_spl_header()`) runs after the banner and cannot explain a
pre-banner stall. Next diagnostic: a debug-UART build of proper in the spare
slot to locate the stall.

### Attempt 4 — debug-UART proper locates the stall (`attempt4-debug/`)

Spare slot temporarily held a debug build of proper (`DEBUG_UART` on UART0
`0x02500000` + announce, every `INITCALL` named on the debug UART;
`03b1e065…`, `debug-slot-write.log`). FEL run, back-power excluded:

```
<debug_uart>
[setup_mon_len] … [initf_dm] [timer_init]
[env_init]
initcall_run_f(): initcall env_init() failed
### ERROR ### Please RESET the board ###
```

Cause: after a FEL load the SPL header in SRAM carries `eGON.FEL`, so proper's
`sunxi_get_boot_device()` returns `BOOT_DEVICE_BOARD`; `env_get_location()`
(board/sunxi/board.c) then has no driver for FEL with `ENV_IS_IN_MMC` only and
returns `ENVL_UNKNOWN` — upstream's own comment says this "will silently hang".
The error prints before the console exists, so a normal build shows nothing.

### Attempt 5 — rescue path PROVEN (`attempt5-rescue-pass/`)

Fix in the rescue SPL only (`CONFIG_H713_SPL_RESCUE`,
`spl_board_prepare_for_boot()`): restore `eGON.BT0`, set `boot_media` =
`SUNXI_BOOTED_FROM_MMC2`, clear `fel_script_address`. Rescue SPL
`dab3b1585a8d05d30d87a57795fa505409304ce7287cfa58d5c8deed1bcf75f0`.
The spare slot was restored to the exact installed proper `c882461d…`
(`rescue-slot-restore.log`; debug tail zeroed). FEL, back-power excluded:

```
U-Boot SPL 2026.07-rc5-g320a17f71d41-dirty (Oct 16 2026 - 03:00:07 -0700)
Trying to boot from MMC2
H713 rescue: SPL header marked eMMC boot for U-Boot proper
NOTICE:  BL31: … Found U-Boot DTB at 0x4a0d2900 …
U-Boot 2026.07-rc5-ga1358432003c-dirty (Sep 24 2026 - 10:58:54 -0700)
Loading Environment from MMC... Reading from MMC(1)... OK
=>
```

At that prompt (`rescue-prompt-check.log`): `mmc read` of the rescue slot
(`0x4a0c00`, 0x706 blocks) and of the live slot (`0x49ac00`) both OK, and
`cmp.b` "Total of 920576 byte(s) were the same". The recovery's write half
(`mmc write 0x42000000 0x49ac00 0x706`) was deliberately not run.
**This is the first FEL-started chain to reach U-Boot proper on H713.**
`0x49ac00` and the SPL were never written during steps 1–2.

## Step 3 — lamp-off U-Boot proper installed (2026-10-16)

`step3-precheck.log`: B staged (`41b1e1bd…`, 1,798 sectors, FIT 920,169 B);
live `0x49ac00`, rescue slot and on-board rollback copy all `c882461d…`; SPL
`cb9da874…`. `step3-write.log`: B written to `0x49ac00` (`conv=fsync`),
`iflag=direct` readback `41b1e1bd…`; rescue slot, SPL and env unchanged.

Warm reboot (`step3-warm-boot-serial.log`, host-timestamped): SPL (unchanged)
→ `U-Boot 2026.07-rc5-g320a17f71d41 (Oct 16 2026 - 01:29:12 -0700)` at 9.68 s;
warm path; `PB5 … value is 0` 14.88 s; logo committed and `PB5 … value is 1`
16.92 s; kernel 17.95 s; fbcon 19.77 s; autologin 30.8 s. Linux: lamp hog high,
TCON 720p, `systemctl is-system-running` = running.
Serial cannot show PB5 between reset and 14.88 s (U-Boot no longer drives
it). **Operator (visual, warm boot): the lamp started off and stayed off until
the logo was shown**, then the console — the on → off → on residual is gone.

## Step 4 — cold cycle on the new U-Boot (2026-10-16) — PASS

Operator (visual, unfilmed): lamp dark from power-on until the logo, then the
console; audio works. Board (`step4-cold-check.log`), boot
`449b9fe3-a426-4c9d-b8ec-21bd5aa07d9a`: `h713,hdmi-boot-v1` present; capture,
signal and speaker active; TCON 720p; lamp hog high; system running;
`0x49ac00` = `41b1e1bd…`. Review L2 closed. The rescue slot keeps the previous
known-good proper (`c882461d…`, lamp on at reset) — a valid FEL rescue target.
