# DSP access AudioTop stage — live run, October 21, 2026

**Result: steps 1–93 passed; step 94, a plain read of the DSP lock word at
`0x05001530`, hard-locked the SoC.** AudioTop and the DSP port are readable
and AudioTop initializes to the Android baseline in the verified state. The
`0x05000000` region holding the lock window is not reachable even with both
TV domains powered, the TVCAP and demod resets released, and the receiver,
audio and display clock trees running. Recovery was a physical power-off. No
DSP request or lock write was ever sent.

Context: [AudioTop stage design](../../hdmi-dsp-audiotop-stage-design-2026-10-21.md),
[offline preparation](../2026-10-21-dsp-access-at/README.md),
[extension run](../2026-10-21-dsp-access-ext-live/README.md),
[stalled monolithic attempt](../2026-10-21-dsp-cold-access/README.md).
Times are host time; correlation is by boot ID and kernel monotonic time.

## Run record (`cold-at-01/`)

Boot `e49a6b15-5824-47a0-bffc-8b7fa78b76a8`, boot-v4. Bundle: module
`26faf61f…`, helper `3e14a860…`, guard `96f37655…` (already live).

1. **Cold catch** (`cold-uboot.log`, `cold-catcher-events.log`): one SPL
   banner; GP6/GP7 and MIPS zero; `tvcap_bus=00000000` (TVCAP reset asserted)
   as in `cold-ext-01`.
2. **boot-v4 RAM boot** (`ram-boot.log`): 22/22 guarded steps OK, bootm
   sha256 OK. **Health** (`uart-identity.txt`, `linux-preflight.txt`): boot
   IDs match, ext4 mounted cleanly, v1 and v2 markers present, retention flag
   absent, genpd TVCAP and TVFE `off-0`, no h713 modules.
3. **Staging and console** (`stage-bundle.txt`, `console-calibration.txt`):
   bundle verified in `/root/hdmi-dsp-access-at-2026-10-21`; printk 5→7,
   `kernel.panic` 5→0, notice marker seen on the UART.
4. **Steps 1–82**: identical to `cold-ext-01` (both PPU domains `00020000` →
   `00010000`, TVCAP reset 1 → released, clock mask `00010000`, TVFE words as
   U-Boot then the 15 stock words, demod gate `00010001`, audio and display
   clocks, final recheck). The full clock summary at the step-69 boundary
   matches `cold-ext-01` apart from CPU frequency. Every boundary snapshot
   (`snapshot-after-NN*`) was reviewed before `--stage-ack`; no warning lines
   after boot through step 90.

| Step | Operation | Result |
| --- | --- | --- |
| 83 | map-audiotop | done |
| 84 | read-audiotop-ctl `0x0614a000` | `00000000`. The read the old bench most likely hung on **completes** here |
| 85 | read-audiotop-cfg `+0xc` | `00000000` (cold default; no inherited setup) |
| 86 | read-tvfe-ctl `0x06e00000` | `00000010` (neither stock-cold `003003ff` nor MIPS-live `00111111`) |
| 87–89 | AudioTop `ctl \| 0x700`, cfg `001a5e00`, latch | `00000700`, `001a5e00`, `011a5e00`: Android baseline, exact readback |
| 90 | recheck MIPS/SCP | stopped |
| 91 | map-dsp-port | done |
| 92 | read-dsp-status `0x06144000` | `00000000` (not busy) |
| 93 | map-lock-window | done |
| 94 | read-lock-peer `0x05001530` | **BEGIN at 810.146 s, no DONE: SoC hard lock** |

Step 94 detail (`step-94.txt`, `bench-uart.log`, `SUMMARY.txt`):
- **What was sent:** the helper saved `executing`/94 and its last event is
  `before-write advance=94`.
- **What came back:** nothing. The SSH call timed out after 120 s. The UART
  recorded nothing after BEGIN for more than 2.5 minutes, including no RCU
  stall report even though `CONFIG_RCU_CPU_STALL_TIMEOUT=21`. That indicates
  a SoC-wide wedge rather than one stuck CPU.
- **Afterwards:** the board's access point disappeared and ping/SSH had no
  route. With `kernel.panic=0` there was no automatic reboot. The operator
  then powered the board off.

## What this establishes

- **AudioTop and the DSP status port need no more than the extension's
  state.** `0x0614a000` and `0x06144000` are readable with both TV domains on
  and TVCAP released, and AudioTop initializes exactly. The extension run
  showed both TV domains off and TVCAP in reset at cold. The October 21
  bench therefore very likely hung at its AudioTop read.
- **The lock window at `0x05001530` needs something more.** It sits in the
  `0x05000000` (tvdisp / composition) region. It wedges the SoC even with
  both TV domains on, all 17 clocks (including the display tree) enabled, and
  the display reset deasserted. Production touches it only after the logo
  firmware and MIPS have brought up the display side. **The October 21 bench
  would have hung here at the latest.** So the TVCAP state alone does not
  fully explain that stall: the lock read is a confirmed hard lock in a state
  at least as well prepared as the old bench's.
- The one-operation-per-step protocol localized the hang to a single
  register read with no ambiguity.

Not established: what the `0x05000000` region needs; anything about DSP
state, versions or warm-reset retention.

`sha256.json` covers every file in `cold-at-01/` and this README.
