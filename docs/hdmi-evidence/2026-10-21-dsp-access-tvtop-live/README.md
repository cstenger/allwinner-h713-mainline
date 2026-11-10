# DSP access TVTOP stage — live run, October 21, 2026

**Result: all 108 steps passed on a fresh cold logo-free boot
(`cold-tvtop-01`), ending in an orderly poweroff.** With U-Boot
`h713_display_prepare()`'s TVTOP routing applied first, the lock-window reads
that hard-locked `cold-at-01` complete. The old monolithic bench's complete
`ready` state is reproduced, and every precondition was read back from
hardware. No DSP request, lock write or mixer write was sent.

Context: [TVTOP stage design](../../hdmi-dsp-tvtop-stage-design-2026-10-21.md),
[prerequisite note](../../hdmi-dsp-lock-window-prerequisite-2026-10-21.md),
[offline preparation](../2026-10-21-dsp-access-tvtop/README.md),
[the hard-locked run](../2026-10-21-dsp-access-at-live/README.md).

## Run record (`cold-tvtop-01/`)

Boot `046a1262-cc72-4d5e-b505-f174b90eccb6`, boot-v4. Bundle: module
`ba785734…`, helper `326740fb…`, guard `96f37655…` (already live).

1. **Cold catch and RAM boot** (`cold-uboot.log`, `ram-boot.log`): one SPL
   banner, GP6/GP7/MIPS zero, `tvcap_bus=00000000`; 22/22 guarded steps OK,
   bootm sha256 OK.
2. **Health** (`linux-preflight.txt`): boot IDs match. ext4 replayed its
   journal, because the previous run ended in a hard lock and power cut, and
   logged no errors. boot-v4 DT checks passed; genpd TVCAP/TVFE `off-0`.
3. **Staging and console** as in earlier runs (`stage-bundle.txt`,
   `console-calibration.txt`).
4. **Steps 1–92:** identical to `cold-at-01`. The full clock summary at the
   53 and 69 boundaries matches it apart from CPU frequency. AudioTop
   `0`/`0` → `00000700`/`011a5e00`, TVFE control `00000010`, DSP status `0`.
   Every boundary snapshot (`snapshot-after-NN*`) was reviewed before
   `--stage-ack`.

| Step | Operation | Result |
| --- | --- | --- |
| 93 | map-tvtop `0x05700000` | done |
| 94–96 | cold TVTOP `+0x40` / `+0x44` / `+0x80` | `00000010` each (SPL's bit 4 only; production: `00011111` / `11111111` / `00001111`) |
| 97–103 | routing writes, exact readback | `+04 00000001`, `+44 11111111`, `+88 11111111`, `+00 fff11111`, `+40 00011111`, `+80 00001111`, `+84 fff000ef` (12 ms after `+84`) |
| 104 | recheck MIPS/SCP | stopped |
| 105 | map-lock-window | done |
| 106 | read-lock-peer `0x05001530` | **`fffffffe`: completes** (hard-locked in `cold-at-01` without routing) |
| 107 | read-lock-own `0x05001534` | `fffffffe` |
| 108 | final recheck | MIPS/SCP stopped, both PPU ON, AudioTop cfg `011a5e00`, TVTOP `+00` `fff11111` |

5. **End** (`status-final.txt`): completed = attempted = 108,
   `stage_complete=Y`, failed N; 108 BEGIN/DONE pairs, 41 OP-DONE, 4 genpd
   events, no warning, error or RCU line after boot.
6. **Poweroff** (`poweroff-request.txt`, end of `bench-uart.log`): orderly,
   module loaded; root remounted read-only; guard "poweroff with HDMI holds
   retained"; `reboot: Power down`.

## What this establishes

- **TVTOP routing is the lock-window prerequisite, confirmed.** The same
  read hard-locked without routing in an otherwise identical state.
  Logo-free cold TVTOP is SPL-only (`0x10` at the three sampled offsets).
- **`+0x88` reads back `11111111` with no MIPS.** That supports attributing
  the `11111011` seen in MIPS-live captures to firmware runtime changes.
- **The complete pre-request state is reproducible from cold without the
  logo/MIPS path.** Both TV domains are on; TVCAP and demod resets released;
  receiver/audio/display clocks and stock TVFE words in place; AudioTop
  initialized; TVTOP routed; DSP status not busy; neither lock word `0x55`.
  The October 21 bench lacked TVCAP power/reset before AudioTop and TVTOP
  routing before the lock window.
- **Cold lock words read `fffffffe`.** That is neither `0x55` (ARM-owned) nor
  `0xaa` (released). Their meaning before any DSP contact is open and matters
  to the version-request design.

Not established: any DSP response, version or patch state; warm-reset retention.

`sha256.json` covers every file in `cold-tvtop-01/` and this README.
