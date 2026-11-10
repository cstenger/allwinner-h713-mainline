# DSP access version-request stage — live run, October 21, 2026

**Result: steps 1–109 passed; step 110 stopped on a readback mismatch.** In the
verified logo-free state, a write of `0x55` to the ARM lock word `0x05001534`
completed without a hang but read back `ffffffff`. The lock could not be
claimed, so **no DSP version request was sent**. The peer word was never
written, the board stayed responsive, and the run ended with an orderly
poweroff.

Context: [version-request stage design](../../hdmi-dsp-version-request-stage-design-2026-10-21.md),
[offline preparation](../2026-10-21-dsp-access-version/README.md),
[TVTOP stage run](../2026-10-21-dsp-access-tvtop-live/README.md).

## Run record (`cold-version-01/`)

Boot `55a8aced-dc37-4c16-8d0d-70216e952ecf`, boot-v4. Bundle: module
`393117e5…`, helper `533bb60f…`, guard `96f37655…` (already live).

1. **Cold catch, RAM boot and health** (`cold-uboot.log`, `ram-boot.log`,
   `linux-preflight.txt`): one SPL banner, cold predicates zero, 22/22 boot
   steps OK, bootm sha256 OK, boot IDs match, ext4 mounted cleanly, boot-v4
   DT checks passed, genpd TVCAP/TVFE `off-0`.
2. **Staging and console** (`stage-bundle.txt`, `console-calibration.txt`)
   as in earlier runs.
3. **Steps 1–108** are identical to `cold-tvtop-01`: census, both domains on,
   resets released, clocks, 15 TVFE words, AudioTop `0`/`0` →
   `00000700`/`011a5e00`, TVFE control `00000010`, DSP status `0`, cold TVTOP
   `0x10` ×3, all seven routing words exact. The only clock-summary
   difference from `cold-tvtop-01` is the idle GPU clock's configured rate
   (600 vs 150 MHz; `en=0`, `hw=N`, domain off). Every boundary snapshot was
   reviewed before `--stage-ack`.

| Step | Operation | Result |
| --- | --- | --- |
| 106 | read-lock-peer | `ffffffff` (`cold-tvtop-01`: `fffffffe`) |
| 107 | read-lock-own | `ffffffff` (`cold-tvtop-01`: `fffffffe`) |
| 108 | final recheck | pass (TVTOP `+00` `fff11111`) |
| 109 | check-lock-free | own and peer `ffffffff`, neither `0x55`: pass |
| 110 | claim-lock: `writel(0x55, 0x05001534)` | OP-DONE (the write completed); **readback `ffffffff` ≠ `0x55` → FAIL −5** |

After the failure (`status-after-fail.txt`), read-only: `failed=Y`,
completed 109, attempted 110; `dev0_outcome=0`, `dsp_timeout=N` (no request
ever issued); board responsive; the only warning since boot is the FAIL
line. Then an orderly poweroff with the module loaded: root read-only, the
guard logged "poweroff with HDMI holds retained", `reboot: Power down`
(`poweroff-request.txt`, `bench-uart.log`).

## What this establishes

- **The lock window does not hold written values in a logo-free boot.** With
  routing in place it is readable, but a `0x55` write reads back
  `ffffffff`.
- **Its cold contents vary between boots** (`fffffffe` in `cold-tvtop-01`,
  `ffffffff` here), unlike a defined register reset value.
- The stock claim/request/release protocol therefore cannot run in this
  state. Production only uses the lock with MIPS running.

Not established: what backs the lock words in production; whether a DSP
would answer a request without the lock; anything about DSP version or
retention.

`sha256.json` covers every file in `cold-version-01/` and this README.
