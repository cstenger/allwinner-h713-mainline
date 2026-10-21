# TVTOP stage design: routing before the lock window — October 21, 2026

**Status: PASSED live (all 108 steps,
[cold-tvtop-01](hdmi-evidence/2026-10-21-dsp-access-tvtop-live/README.md)): TVTOP
routing confirmed as the lock-window prerequisite; lock words read `fffffffe`.** Based on the
[lock-window prerequisite note](hdmi-dsp-lock-window-prerequisite-2026-10-21.md).
That note concluded that the `0x05xxxxxx` display fabric, which holds the
lock window, needs TVTOP routing at `0x05700000` as well as clocks.
`cold-at-01` hung on the lock read without it.

## Change to the step table

Steps 1–92 are unchanged: prefix, census, extension, AudioTop read/init and
the DSP status sample, all of which passed live. The old steps 93–96 (lock
map/peer/own/final) are replaced by steps 93–111:

| # | Operation | Touches | Pass condition |
| --- | --- | --- | --- |
| 93 | map-tvtop | ioremap `0x05700000`, 0x90 bytes (unclaimed, as the PPU window) | software only |
| 94 | read-tvtop-40 | read `+0x40` | readable; record |
| 95 | read-tvtop-44 | read `+0x44` | readable; record |
| 96 | read-tvtop-80 | read `+0x80` | readable; record |

Boundary `tvtop-census`.

| # | Operation (value) | Pass condition |
| --- | --- | --- |
| 97 | write-tvtop-04 (`00000001`) | exact readback |
| 98 | write-tvtop-44 (`11111111`) | exact readback |
| 99 | write-tvtop-88 (`11111111`) | exact readback |
| 100 | write-tvtop-00 (`fff11111`) | exact readback |
| 101 | write-tvtop-40 (`00011111`) | exact readback |
| 102 | write-tvtop-80 (`00001111`) | exact readback |
| 103 | write-tvtop-84 (`fff000ef`), then 12 ms | exact readback |
| 104 | recheck-stopped-after-tvtop | MIPS 0, SCP b0 clear |

Boundary `tvtop-routing`.

| # | Operation | Pass condition |
| --- | --- | --- |
| 105 | map-lock-window | software only |
| 106 | read-lock-peer `0x05001530` | ≠ `0x55`; record |
| 107 | read-lock-own `+0x4` | ≠ `0x55`; record |
| 108 | final-recheck | MIPS/SCP stopped, both PPU ON, AudioTop cfg `…011a5e00`, TVTOP `+0x00` `fff11111` |

End snapshot `lock-sampled`, then an orderly poweroff. This makes 108 steps.

## Decisions

**T1. Writes and values come from `h713_display_prepare()` verbatim, in its
order.** That is the primitive U-Boot runs cold in every normal boot, so it
is proven safe from SPL-only TVTOP. Every captured MIPS-live value equals the
written value. The exception is `+0x88`, which reads `11111011` in two
MIPS-live captures and is attributed to firmware runtime changes. With no
MIPS here, exact readback is expected, and a mismatch stops the run.

**T2. The cold census reads only proven offsets.** SPL already
read-modify-writes `+0x40`, `+0x44` and `+0x80` at cold, so those reads are
proven. `+0x00`, `+0x04`, `+0x84` and `+0x88` are not read before being
written. Their cold readability is unproven, and a hang there would cost the
run before it reaches the question being asked. Their *post-write*
readability is covered by the readbacks, which match routine reads in
MIPS-live boots. The cold values of those four words remain unmeasured; this
is noted as a gap for the reset-contract work.

**T3. No mixer write.** `prepare` also writes `0x0525c038 = 00000100`. That
word is inside the gated fabric and serves the display MIPS, and the lock
window does not need the mixer. If the lock read still hangs with routing in
place, the mixer write is the next candidate, in a separate run.

**T4. The DSP status sample stays before TVTOP.** Step 92 passed live
without routing, so its position is unchanged. That keeps "audio blocks do
not need TVTOP" as an observed fact rather than one confounded by the new
writes.

**T5. Everything else is unchanged:** boot-v4, the console/panic preflight,
one acknowledged call per step, a snapshot plus `--stage-ack` at
boundaries, no release after step 40, and an orderly poweroff with the module
loaded as the only end. There is no DSP request and no lock write.

## Interpreting the outcome

| Result | Reading |
| --- | --- |
| Hang at 94–96 | Contradicts SPL's own read-modify-write evidence; stop and re-examine the SPL claim. |
| Readback mismatch at 97–103 | Routing is not latching as in U-Boot; stop. A mismatch at `+0x88` alone would need its MIPS-runtime attribution re-checked. |
| Hang at 106 after routing | TVTOP routing is not sufficient; the mixer write (T3) is next, in a new run. |
| 106–107 pass | **TVTOP routing is the lock-window prerequisite, confirmed.** The old bench's complete `ready` state is reproduced with every precondition verified. The version-request stage can be designed. |
| Refusal at 106–107 (`0x55`) | Lock owned at cold; stop before any request design. |

## Implementation

The same module and helper as before. The helper schema becomes
`h713-dsp-access-tvtop-v1`. New boundaries are after 82, 86, 90, 92
(`dsp-status`), 96 (`tvtop-census`) and 104 (`tvtop-routing`), with an
end-of-run snapshot at 108 (`lock-sampled`). Samples are reported as before,
plus `tvtop_cold` (three words) and `tvtop_set` (seven readbacks).
