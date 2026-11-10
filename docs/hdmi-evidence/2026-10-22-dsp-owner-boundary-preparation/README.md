# Owner-based positive control and shutdown-boundary preparation

**Offline preparation only; no board access, staging, install or capture.**
[Design and live runbook](../../hdmi-dsp-owner-boundary-design-2026-10-22.md).
Board remains powered down after the completed control-only replication.

The next two cold cycles use one module/script/kernel/firmware: first a
no-write sham requiring four completed patched `1/1` pairs, then a matched
boundary arm with fresh patched baseline. Its first intervention is the
existing 22 saved graph-word restorations, followed by AudioTop config clear,
then control off/on only while prior pairs remain patched. The first changed
or timed-out pair ends the sequence after skip/release/checkpoint. There is
no reset or warm logo after patching in either arm.

This ordering addresses normal audio teardown before CPU reset. Normal
SPDI/bridge restoration between graph and AudioTop is omitted in both arms;
this is a controlled prefix experiment, not a complete replay of every
normal shutdown write. Later clock restoration/demod reset, CPU reset,
early boot and warm-logo tests depend on this batch's result.

Candidate: `build/hdmi-dsp-owner-boundary-2026-10-22/candidate/`.
[Manifest](manifest.json), [verification](verification.json),
[build log](build.log), [test results](tests-summary.json),
[generated cold script](cold-owner.cmd).

* Production FIT unchanged, SHA-256
  `0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70`.
  Exact kernel `6.18.38 #1 SMP Fri Oct 16 15:44:49 PDT 2026`.
* New isolated audio module SHA-256
  `6cbc305cfcd14b20d9c72c25c293402cc2c7490d1cf3e977ba60654c5bf62001`.
  It is built from pinned production sources in a separate build directory;
  normal source/module files are unchanged. Module `vermagic` matches the
  installed module: `6.18.38 SMP mod_unload aarch64`. Production kernel
  `Module.symvers` unchanged. Loaded build-ID note is pinned in the manifest.
* RAM cold script: 4,360 bytes, SHA-256
  `0f3245113d33501761e51aa87c59980e63e03c2569d6b05e3276b47d18e6e1d1`.
  Legacy header/data CRC and exact payload verified. Retains the pinned
  installed cold source3 flow, removes warm fallback, holds lamp off,
  masks normal HDMI services for this boot, sets `panic=0 loglevel=7` and
  a bench DT marker. No saved-environment/media update.
* Pinned patch firmware: 2,896 bytes, SHA-256
  `8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5`.
  Loaded once during each normal-style owner initialization, before the
  positive measurement. No patch application after the positive control.
* Sole owner retains register resources/receiver/clocks, omits PCM and
  disables audio IRQ handlers in both arms. Lifetime pin prevents unload
  and automatic graph/AudioTop/clock teardown between observations.
  [PCM-side changes](h713-hdmi-pcm.c.patch),
  [DSP include change](h713-hdmi-dsp.c.patch).
* Kernel checks exact cursor, immutable arm, expected AudioTop state,
  powered/idle domains, live MIPS, stock ARM lock and patched predecessor.
  Four maximum version pairs; graph restore additionally uses only the
  existing saved-word normal teardown. State includes raw responses and
  graph saved values so the second arm can reject unmatched context.
* Host helper binds fresh cold proof/kernel/module build ID/manifest/boot,
  requires a successful exact sham for arm 2, enforces snapshot-stage
  acknowledgments and an uncertain ledger, and exports before checked
  poweroff. Uncertain snapshots cannot be reported as successful.

**43 tests pass:** 14 new test methods, including actual-C fake-MMIO
execution of both bench includes, plus 29 relevant existing startup,
managed-boot and minimum-observer regressions. Cases cover sham preservation,
graph/config/control version changes, graph restore failure, missing arm,
health/lock failure, busy/done/late timeout, unpatched positive control,
context drift, cursor refusal, generated JSON parsing, proof/arm/cold-latch
checks, command echoes, matched-record gating and uncertain-ledger analysis.
The actual isolated module builds with `W=1` and no C diagnostics. Kbuild
prints a compiler-version notice: the production kernel used clang 23.1.1,
while the upgraded host now uses 23.1.3. Exact production kernel headers,
Symvers and vermagic are verified; no replacement kernel was built.

No live claim is made yet: the sham must qualify this new owner-based
measurement before the boundary arm can be run. Existing bench guard and
original backup remain untouched; no recovery policy is relaxed.
