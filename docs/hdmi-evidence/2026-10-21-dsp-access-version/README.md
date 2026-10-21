# DSP access version-request stage — offline preparation, October 21, 2026

**Offline only. No board staging, module load or live step.** Implements the
[version-request stage design](../../hdmi-dsp-version-request-stage-design-2026-10-21.md)
on top of the [TVTOP stage that passed live](../2026-10-21-dsp-access-tvtop-live/README.md).

- **Module** `393117e5…`: steps 1–108 are unchanged in operation and order.
  New steps 109–119, using the protocol from `modules/hdmi-dsp-probe/h713-dsp-lock.h`
  and `h713-dsp-completion.h`:
  1. Check the lock is free (own ≠ `0x55`; peer ≠ `0x55` within 10 ms).
  2. Claim it: own = `0x55` with readback; recheck the peer.
  3. For each device: wait for busy clear (bit 4 / 7, 50 ms); write
     `0x80ff << 16` to `+0x10` / `+0x18`; poll for done (bit 5 / 8, 50 ms);
     read the response.
  4. Release: own = `0xaa` with readback.
  5. Final recheck: stopped, both PPU ON, TVTOP routed, own `0xaa`,
     peer ≠ `0x55`.

  A done timeout is recorded (outcome 2, status kept) and latches
  `dsp_timeout`. Later requests become recorded no-ops (outcome 3), and the
  release still runs. Busy never clearing, an existing owner, or a readback
  mismatch is a hard stop. **The peer word is never written.** There is no
  patch, graph or selector write. W=1 build; only the known compiler-version
  warning. The only new import is `ktime_get` (from `readl_poll_timeout`).
- **Helper** `533bb60f…`, schema `h713-dsp-access-version-v1`: 119 steps; new
  boundaries after 108 (`lock-sampled`), 111 (`lock-claimed`), 114 (`dev0`),
  117 (`dev1`), and the end snapshot at 119 (`versions`). It reports lock
  values, outcomes, status words, versions and the timeout latch.
- **Guard** `96f37655…` and **boot-v4** reused unchanged (boot-v4 hashes rechecked).

Checks: `version-tests.txt` (21 pass). Coverage includes the timeout path
continuing to release and end, a source check that no `writel` targets the
peer word, and the production protocol constants (address, ports, busy/done
bits, `0x55`/`0xaa`). Request steps are checked to sit strictly between claim
and release, the boundary set is pinned, and no step name mentions
patch/graph/selector. Guard (3), legacy observe (5) and boot-prep (3) still
pass. Mutation checks, each failing the suite:
- writing the peer word;
- a wrong version address;
- swapped device ports. This one was initially missed because the substring
  test matched the unchanged response read; every port expression is now
  checked;
- swapped done bits;
- a request before the claim;
- dropping the `lock-claimed` boundary;
- parsing the timeout flag as an integer;
- not reporting the outcome.

Offline consistency only.
