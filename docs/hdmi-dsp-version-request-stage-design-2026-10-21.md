# Version-request stage design: one-shot `0x80ff` pair — October 21, 2026

**Status: design for review. Nothing here is implemented or tested.**
This continues the [TVTOP stage](hdmi-dsp-tvtop-stage-design-2026-10-21.md),
which [passed live](hdmi-evidence/2026-10-21-dsp-access-tvtop-live/README.md).
That run reproduced the old bench's complete `ready` state from cold with every
precondition verified. This stage performs the old bench's single remaining
action: claim the shared lock, read the logical `0x80ff` version word from DSP
device 0 and device 1, and release the lock. **It is the first stage that
changes DSP protocol state.** It loads no patch and writes no graph or
selector word.

## Why this read matters

Production's DSP startup requires both version words to read `0/0` before it
loads the pinned volatile patch, and `1/1` after
([2026-10-08 handoff](handoff-2026-10-08-hdmi-audio-capture.md): *cold
version 0/0 → 724-pair volatile patch → version 1/1*). The patch has no
inverse, and audio teardown deliberately leaves it in place. **Whether an
orderly or abrupt system reset restores `0/0` is unmeasured**
([warm-reset investigation](hdmi-warm-reset-investigation-2026-10-20.md)).
Production currently fails closed on warm reboot through its GP6 launch
latch, without having measured DSP retention. If the patch survives warm
reset, the `0/0` predicate itself blocks warm recovery. If it does not, the
latch is stricter than the DSP requires. Telling these apart is the
reset-contract question.

This stage provides the **cold, logo-free baseline** for that predicate:
- what the version words read with no MIPS and no patch;
- whether the DSP answers at all without the MIPS/logo path.

The retained-patch comparison that answers the reset-contract question comes
after this, as a separate stage.

## Protocol, from existing code

These are `modules/hdmi-dsp-probe/h713-dsp-lock.h` and `h713-dsp-completion.h`,
as used by production and the old bench:

- **Lock.** ARM's own word is `0x05001534`; the peer (MIPS) word is
  `0x05001530`. To claim: refuse if own is already `0x55`; wait for
  peer ≠ `0x55`; write own = `0x55` and read it back; then recheck
  peer ≠ `0x55`. To release: own = `0xaa`. **Never write the peer word.**
- **Read** (per device). Wait up to 50 ms for the busy bit to clear (dev0
  bit 4, dev1 bit 7). Write `0x80ff << 16` to the command port (dev0 `+0x10`,
  dev1 `+0x18`). Poll up to 50 ms for the done bit (dev0 bit 5, dev1 bit 8).
  Read the response from the command port. Completion may finish before the
  first sample, so no clear edge is required.
- **Production failure rule:** a timeout latches; no further command until a
  physical cold boot.

Every register involved has already been read without incident: the status
port (step 92) and both lock words (106–107). The new operations are
**writes**: the own word, and the two command-port words.

## Step table (continues the TVTOP stage)

Step 108 becomes a boundary (`lock-sampled`) instead of the end.

Stage **V-L — claim the lock:**

| # | Operation | Pass condition |
| --- | --- | --- |
| 109 | check-lock-free: read own and peer | own ≠ `0x55`, peer ≠ `0x55`; record both |
| 110 | claim-lock: write own = `0x55` | OP-DONE; readback `0x55` |
| 111 | recheck-peer-after-claim | peer ≠ `0x55` (stock's recheck) |

Boundary `lock-claimed`.

Stage **V-0 — device 0:**

| # | Operation | Pass condition |
| --- | --- | --- |
| 112 | wait-dev0-idle | status bit 4 clear within 50 ms |
| 113 | request-dev0-version: write `0x80ff0000` to `+0x10` | OP-DONE; then done bit 5 within 50 ms → `done`; else `timeout` (see V1) |
| 114 | read-dev0-response from `+0x10` | record `version0` (no-op if 113 timed out) |

Boundary `dev0`.

Stage **V-1 — device 1:** same as V-0 for device 1 (bits 7/8, `+0x18`),
steps 115–117. These are recorded no-ops if any earlier request timed out
(V1). Boundary `dev1`.

Stage **V-R — release:**

| # | Operation | Pass condition |
| --- | --- | --- |
| 118 | release-lock: write own = `0xaa` | OP-DONE; readback `0xaa` |
| 119 | final-recheck | MIPS/SCP stopped, both PPU ON, TVTOP `+00` `fff11111`, own `0xaa`, peer ≠ `0x55` |

End snapshot `versions`, then an orderly poweroff with the module loaded.

## Design decisions

**V1. A DSP timeout is a recorded outcome, not a module failure.** If the
done bit never sets, that is a meaningful answer: the DSP does not answer
without the MIPS/logo path. It is not a hazard. The status reads are proven
safe and the poll is a bounded loop of those reads, not one stalled bus
access. On a timeout:
- the step records `timeout` and the last status, and latches `dsp_timeout`
  (matching production's no-further-command rule);
- every later request step becomes a recorded no-op;
- the lock is still released (step 118), so the run can end orderly.

A *readback mismatch* or a refusal (`0x55` owner, busy never clears) is still
a hard failure that stops the run.

**V2. One claim covers both reads.** This is stock and production
behaviour. It is split into explicit steps so a hang identifies the exact
write.

**V3. Values and order are verbatim from production code.** The address is
`0x80ff`, the ports `+0x10`/`+0x18`, the busy/done bits 4/5 and 7/8, and the
timeouts 50 ms (busy/done) and 10 ms (peer).

**V4. Nothing else touches the DSP.** No patch, no graph, no selector, no
masked initialization at `00ee`/`8034`/`8017`. After the release, the state
differs from cold by own = `0xaa` and whatever the DSP did with two version
requests. Power-off clears both.

**V5. Same framework:** boot-v4, the console/panic preflight, one
acknowledged call per step, a snapshot plus `--stage-ack` at boundaries,
no release-of-resources after step 40, and an orderly poweroff only.

## Interpreting the outcome

| Result | Reading |
| --- | --- |
| `0/0` | The DSP answers at cold without MIPS, no patch loaded. This matches production's precondition and gives the cold baseline for the retained-patch comparison. |
| `1/1` | A patch is present at cold. That contradicts "volatile, cleared by cold boot"; stop and re-examine. |
| Other values | Record them. The DSP answers, but its version semantics differ from the MIPS-live path. |
| Timeout on dev0 (or dev1) | The DSP does not answer without the MIPS/logo path. Version reads then need MIPS-provided DSP start-up, which constrains what warm recovery must re-establish. The lock is still released. |
| Readback mismatch on own (110/118) | The lock word is not ARM-writable in this state. Stop before reasoning about the protocol. |
| Hang on a write (110, 113, 116, 118) | The first write to that region is unsafe in this state. Localized by OP-DONE. |

The cold lock words read `fffffffe`. After the claim/release they should read
`0x55`/`0xaa`. Whether `fffffffe` is a power-on value or something the DSP
side writes is recorded, not assumed.

## What this will not establish

- Retention of DSP state across warm reset. That is the **retained-patch
  comparison**, the next stage after this one, which this stage feeds. It
  needs a patch load and a warm reset under the guard's poweroff-only rule,
  so it has its own design.
- Anything about MIPS-live behaviour, graph state, or audio.
- That `0/0` here equals `0/0` in production's cold path. The setup here is
  controlled and logo-free; production's follows MIPS. Same-value results
  would be consistent, not identical by construction.

## Implementation outline

1. Module: steps 109–119 (lock check, claim, peer recheck, two device
   triplets, release, final). A `dsp_timeout` latch with no-op semantics.
   Parameters `lock_own_before`, `lock_peer_before`, `version0`, `version1`,
   `dev0_outcome`, `dev1_outcome`, `dev0_status` and `dev1_status`. Reuse the
   completion header's timing.
2. Helper: schema `h713-dsp-access-version-v1`, the 119-step table,
   boundaries after 108, 111, 114 and 117, and the end at 119. Report
   versions and outcomes.
3. Tests: parity with the C table, the boundary set pinned, the
   timeout-then-no-op path, the release still reached after a timeout, the
   readback-mismatch stop, and no write to the peer word anywhere (a source
   check). Mutation checks as before.
4. Build W=1; imports should be unchanged except for possible `ktime`/delay
   helpers. Bundle, manifest, preparation evidence. Guard and boot-v4 are
   reused.
5. Live: one cold boot, same protocol as `cold-tvtop-01`.
