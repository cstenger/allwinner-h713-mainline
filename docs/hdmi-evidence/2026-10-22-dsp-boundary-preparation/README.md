# DSP boundary diagnostic preparation — October 22, 2026

**Offline preparation complete. No board access, installation, capture or
power transition occurred. Board remains shut down after the previous run.**
[Design and live runbook](../../hdmi-dsp-boundary-design-2026-10-22.md).

The candidate compares separate fresh patched cold → warm paths with and
without the warm logo. It attempts a version pair before AudioTop writes,
then after each of control/config/latch, preserving all four pairs. The
one-logo arm runs first to qualify exploratory pre-AudioTop access in a
previously functional lock context. The no-logo arm stops before DSP access
if its lock is not writable. These outcomes can narrow the loss bracket;
unavailable/unqualified access cannot establish reset-induced RAM erasure.

## Built artifact

`build/hdmi-dsp-boundary-2026-10-22/candidate/`, independently copied from
previously tested retention `candidate-v2`. [Manifest](candidate-manifest.json).

| Item | Identity |
| --- | --- |
| FIT | 7,754,288 bytes; SHA-256 `bbadfaaa28b299ee6d4d4e514e9d38c2f11e180b7f8171aaeaca1d289e171a83` |
| Kernel | `6.18.38 #4 SMP Thu Oct 22 01:01:15 PDT 2026` |
| DTB | 34,711 bytes; SHA-256 `b789b4c9119dd7710c6e45a15e10d9e3098d47a0fbfd91d19170eabed1c0ec6a` |
| Bench guard | Existing `5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`, unchanged |

Both arms share identical FIT bytes. The DTB differs from production only
by disabling display and CPU_COMM nodes and adding the boundary marker;
this prevents early unprepared display accesses in the no-logo arm. The
existing TVFE hold policy and original PPU source are unchanged. The new
observer requires `h713_dsp_boundary=1` in addition to the hold/trace flags.
Full exported symbol versions match production.

The self-contained board bundle has the FIT, stepped helper, analyzer,
existing bench guard and manifest. Separate host tools validate captured
arm history, RAM image/hook integrity and bind the loader intent once to an
idle exact-kernel Linux boot before any step. Every helper preflight checks
arm/FIT/baseline/boot identity, DT, owner inactivity, console/panic controls,
guard and unviolated hold. Run scope stays root-only, one operation per call.

73 operations preserve the proven clock prefix, add conditional display/
TVCAP reset release and seven routing readbacks, then perform four separately
claimed/released version pairs around AudioTop writes. No DSP request occurs
before an actual writable lock claim. No reset assertion, domain power-on,
patch/graph initialization, firmware launch or GP6/GP7 write is added. A
request timeout permits only skip/release/final of its current pair and
blocks the next setup operation/pair. An uncertain ledger forbids retries.

## Verification

* [Real kernel/modules build](build.log): success, no warnings/errors.
* [Artifact verification](artifact-verification.json), with
  [reproducible checker](verify-artifacts.py): FIT-extracted Image/DTB match,
  decompressed Image matches build output, DTB exactly reproduces the three
  intended edits, complete `Module.symvers` unchanged, bundle hashes valid,
  compiled observer matches current source.
* [59 passing offline tests](tests.log): 11 new boundary tests plus 48
  retention/trace/warm/guard regressions. Native tests execute the actual new
  observer with fake MMIO, including immediate completion, loss after each
  AudioTop write, inherited no-op setup, absent lock backing, initial and
  later request timeouts, power loss, denied resources and invalid gate/
  hold. They verify no setup or new pair after timeout, no pre-setup writes,
  bounded request counts and no peer/PPU/RTC writes. Evidence tests reject
  incomplete pairs, missing response metadata, invalid arm/cold history,
  duplicate logo/reset, wrong acknowledgment and reused cold-cycle comparison.
* [Source hashes](source-hashes.json) pin the tested tools/assets.

Tests qualify control flow, not hardware access before AudioTop. A bounded
poll cannot recover a stalled MMIO transaction; the runbook requires passive
UART BEGIN/DONE coverage and a stop/poweroff outcome, not retry or setup as
recovery. A completed zero before setup is reported as an observation with
an unqualified-interface caveat, never direct DSP RAM erasure.

The board's previous bench guard/original backup remain as documented in
[the previous live result](../2026-10-22-dsp-retention-live/README.md). No new
files were staged to the board. The disabled display driver will not execute
its normal panel shutdown callback: both arms keep the lamp off and require
physical power disconnection after orderly poweroff. No live result exists
for this candidate, and automatic HDMI recovery remains unproven.
