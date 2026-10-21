# AudioTop stage design: AudioTop, DSP status and lock sampling — October 21, 2026

**Status: run live ([cold-at-01](hdmi-evidence/2026-10-21-dsp-access-at-live/README.md)): steps 1–93 passed (AudioTop readable and initialized, DSP status readable); step 94, the lock-window read at `0x05001530`, hard-locked the SoC.** See the [preparation evidence](hdmi-evidence/2026-10-21-dsp-access-at/README.md). The kernel parameter named `complete` below became `stage_complete`.
This continues the [extension](hdmi-dsp-access-extension-design-2026-10-21.md),
which [passed live](hdmi-evidence/2026-10-21-dsp-access-ext-live/README.md) to a
hardware-verified state: both TV domains on, TVCAP and demod resets released,
receiver/audio/display clocks running, stock TVFE words written, and MIPS/SCP
stopped. This stage performs the remaining operations of the old monolithic
setup, one per step, up to the point where it was "ready". That point is
AudioTop read and initialization, then plain samples of the DSP status and
both lock words. **It sends no DSP request and writes no lock word.** The
one-shot logical `0x80ff` version pair stays a later, separately reviewed stage.

Goals, in order:

1. Test the leading explanation for the October 21 stall. Repeat the read
   that the old bench most likely hung on (AudioTop `+0x0`), this time in the
   verified state.
2. Reach the old bench's `ready` state with every precondition read back, so
   the version-request stage starts from a known state.

## Evidence that shapes the design

**A1. The old bench's remaining sequence** (`h713-hdmi-dsp-observe.c`, after
its audio clocks):
1. Map AudioTop `0x0614a000`, the DSP port `0x06144000` and the lock window
   `0x05001530`.
2. Read AudioTop `ctl` (`+0x0`) and `cfg` (`+0xc`); refuse if
   `ctl & 0x700` or `cfg & 0x00ffffff` is already set.
3. Write `ctl | 0x700`, then `cfg` as `(cfg & 0xff000000) | 0x001a5e00`,
   then the same with bit 24, and verify.
4. Recheck MIPS/SCP stopped.
5. Read DSP status, lock peer and lock own; refuse if status bit 4 or 7 is
   set, or either lock word is `0x55`.

**A2. Production uses the same order and values.**
`modules/hdmi-audio/h713-hdmi-pcm.c` applies the IHB clock word
(`0x02001d50 = 0x81000002`), then AudioTop with identical values, and only
then touches AudIf. Its comment records that an earlier build put an AudIf
ownership read *before* AudioTop setup, and warns not to assume enabled CCF
gates permit that access. The Android baseline reads AudioTop `0x700` /
`0x011a5e00` (2026-10-08 handoff). The extension already wrote the IHB word,
as raw word `d50`, step 65.

**A3. Domain membership is unknown and stock never separates the domains.**
The stock DT gives none of the `0x0614xxxx` audio blocks (DSP port, AudIf
`0x06146000`, bridge `0x06148000`, AudioTop) or the `0x05000000` region a
power domain of its own. One `tvtop_pm` node holds `pd_tvcap` and `pd_tvfe`
together. Production does the same through the receiver owner.

**A4. The TVFE control word at `0x06e00000`** (a tvtop window) is written
`0x003003ff` by the stock cold driver. Production preserves the MIPS-set live
value (`0x00111111`), because overwriting it broke receiver state 5. The old
bench never touched it. Whether DSP access needs it is unknown.

**A5. The DSP protocol is stateful.** A logical read writes a request and
takes ARM ownership (`0x55`), and release sets `0xaa`. The *plain* status and
lock-word reads in A1 change no protocol state, and the old bench treated
them as samples. They are still new accesses in a logo-free context.

## Design decisions

**B1. Same module, continuous table, new schema.** Steps 1–82 stay as they
are. Step 82 becomes a stage boundary (`extension`) instead of the end. New
steps 83–96 follow, and the helper schema becomes `h713-dsp-access-at-v1`.
The other rules are unchanged: boot-v4 only, the console/panic preflight,
one acknowledged call per step, a snapshot plus `--stage-ack` at
boundaries, no release after step 40, and orderly poweroff as the only end.

**B2. Separate reads for the suspected stall point.** Mapping, reading
`ctl`, and reading `cfg` are three steps, so a hang at step 84 is
unambiguous. The "inherited AudioTop" refusal from A1 is evaluated after
both reads (step 85), and the raw values are recorded either way.

**B3. TVFE control word: read-only.** Sample `0x06e00000` once, after
AudioTop is read, and do not write it. Writing `0x003003ff` is stock cold
behaviour but untested here and not needed to reach the old bench's
`ready`. Adding it is a decision for the version stage, informed by this
sample.

**B4. No discriminating "hang" runs by default.** A deliberate
reproduction would boot without TVCAP powered or with its reset held, then
read AudioTop. A hang there would prove the October 21 cause. But it costs a
cold cycle and a deliberate hard-lock, and it would not change production,
which, like stock, always holds both domains. **I recommend against it**
unless the warm-recovery design later needs to know whether power or reset
is the critical part. If it does, the cheaper first variant is "TVCAP powered,
reset still asserted" (skip step 46).

**B5. Lock window and display tree.** `0x05001530` lies in the `0x05000000`
region, which the old bench said needs the display clock tree. Stage D of
the extension provided that tree (with the display reset already released),
so no new clock work is needed. The window is still read last, after the
`0x0614xxxx` accesses, because it is the region with the least evidence.

## Step table (continues the extension)

Stage **AT-R — AudioTop read** (boundary `extension` before step 83):

| # | Operation | Touches | Pass condition |
| --- | --- | --- | --- |
| 83 | map-audiotop | ioremap `0x0614a000` (claimed at step 3) | software only |
| 84 | read-audiotop-ctl | read `+0x0` | readable; record |
| 85 | read-audiotop-cfg | read `+0xc` | readable; record; refuse if `ctl & 0x700` or `cfg & 0x00ffffff` |
| 86 | read-tvfe-ctl | ioremap and read `0x06e00000` | readable; record |

Boundary `audiotop-read`. Decision: if steps 84 and 85 return, the October
21 read is shown to work in the verified state.

Stage **AT-I — AudioTop init:**

| # | Operation | Pass condition |
| --- | --- | --- |
| 87 | write-audiotop-ctl `ctl \| 0x700` | exact readback |
| 88 | write-audiotop-cfg `(cfg & 0xff000000) \| 0x001a5e00` | exact readback |
| 89 | write-audiotop-cfg-latch, same with bit 24 | exact readback (`…011a5e00`) |
| 90 | recheck-stopped | MIPS 0, SCP b0 clear |

Boundary `audiotop-init`.

Stage **AT-S — DSP status and lock samples** (no protocol state change):

| # | Operation | Touches | Pass condition |
| --- | --- | --- | --- |
| 91 | map-dsp-port | ioremap `0x06144000` (claimed at step 1) | software only |
| 92 | read-dsp-status | read port `+0x0` | bits 4 and 7 clear; record |
| 93 | map-lock-window | ioremap `0x05001530` (claimed at step 2) | software only |
| 94 | read-lock-peer | read `+0x0` | ≠ `0x55`; record |
| 95 | read-lock-own | read `+0x4` | ≠ `0x55`; record |
| 96 | final-recheck | MIPS/SCP stopped; both PPU ON; AudioTop still `…011a5e00` | pass |

Boundary `dsp-sampled`, then `stage-end` and an orderly poweroff with the
module loaded.

## Interpreting the outcome

| Result | Reading |
| --- | --- |
| Hang at 84 (BEGIN, no DONE) | AudioTop needs something beyond the extension's state. The explanation that TVCAP alone caused the stall would be incomplete. Compare with stock cold init (A4's TVFE word, other resets). |
| 84–85 pass | The read that most likely stalled the old bench works once TVCAP is powered and released. This strongly supports the explanation; proof would need B4. |
| Refusal at 85 | AudioTop is not at its cold default in a cold boot. Record and stop; stock init assumptions need revisiting. |
| Hang or mismatch at 87–89 | The AudioTop init itself. |
| Hang at 92 | The DSP port needs more than AudioTop init. |
| Hang at 94–95 | The `0x05000000` region needs something the display tree did not provide. |
| Refusal at 92–95 | DSP busy or a lock already owned at cold: the cold-state assumption is wrong. Stop before any request design. |
| All pass | The old bench's complete `ready` state is reproduced and verified. The version-request stage can be designed from it. |

## What this will not establish

- The DSP version words, DSP patch state, or anything about retention across
  warm reset. Those need the request stage and then a retained-patch comparison.
- Which domain or reset AudioTop needs (B4).
- Safety with MIPS running.

## Toward the reset contract

Once this passes, the read-only census (steps 34–40, plus AudioTop/DSP
samples) becomes a probe of retained state. Running it after a warm reset
from a known prepared state would show what a warm reboot keeps or clears:
PPU domains, CCU resets, TVFE words, AudioTop and DSP status. That is the
reset-contract question in the handoff. The bench guard deliberately turns
reboot into poweroff, so that comparison needs its own design. It must not
come from relaxing the guard.

## Implementation work (after this design is approved)

1. Module: steps 83–96 and their actions; step 82 no longer terminal;
   `complete` replaces `extension_complete`; `audiotop_ctl`, `audiotop_cfg`,
   `tvfe_ctl`, `dsp_status`, `lock_peer` and `lock_own` exposed read-only.
2. Helper: schema `h713-dsp-access-at-v1`, the 96-step table, new
   boundaries after 82, 86 and 90; the run ends at 96, followed by a final
   snapshot before poweroff. Record the new samples in step results.
3. Tests: parity, boundary gates, the step-85 refusal path, end at 96 with no
   request action, and mutation checks as before.
4. Build W=1, check imports (expected unchanged: no new kernel API), and
   regenerate the bundle with a new manifest. Guard unchanged.
5. Live run: one cold boot with boot-v4, same protocol as `cold-ext-01`.
