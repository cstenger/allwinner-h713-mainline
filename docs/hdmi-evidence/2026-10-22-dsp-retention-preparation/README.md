# DSP warm-retention preparation — October 22, 2026

**Offline only; no board installation, power-on or DSP observation.**
Board remains shut down and no capture is armed.

[Design and live runbook](../../hdmi-dsp-retention-design-2026-10-22.md).
Final output: `build/hdmi-dsp-retention-2026-10-21/candidate-v2/`.
The older `candidate/` is a superseded local prototype, not the live bundle.

The new kernel verifies a warm, already-ON/idle TVFE and applies a bench-only
always-on domain flag. It does not power a domain ON or change global genpd
policy. Any attempted TVFE power command invalidates the retention proof.
The built-in observer stays idle until explicit sysfs steps, then prepares
the access clocks/interface, claims the stock lock and issues only the two
logical `0x80ff` reads. No firmware/patch/graph/selector write or reset assertion
is added. Existing original PPU hardware-write statements are unchanged.

The board bundle contains the FIT, stepped helper, analyzer, shutdown hook
and manifest. The hook blocks reboot/kexec on the retain cmdline even without
a loaded module. The host RAM loader validates the installed hook's bytes
before loading/booting the kernel. Hook backup/install and all live staging
remain future work. Normal production boot files and boot firmware are unchanged.

Recorded evidence:

- `manifest.json`: base identity, asset/bundle hashes, compiler/build command,
  exact build version, FIT/DTB sizes and hashes, unchanged exported symbols.
- `bench-ppu.patch`: generated changes to the traced PPU driver; the included
  policy/observer sources are committed under `tools/hdmi/dsp-retention/`.
- `build.log`: successful real arm64 kernel/modules build, no warnings.
- `tests.txt`: 11 retention tests plus 37 trace/warm-census/guard regressions.
- `validation.json`: source/tool hashes and additional packaging/source checks.
- `sha256.json`: hashes of this preparation evidence.

Independent FIT extraction matches its Image and production DTB; decompression
matches the built kernel. `Module.symvers` remains byte-identical to production.
Native fault controls execute the actual observer and stock protocol headers,
including busy/done timeouts, unwritable locks, missing resources and lost power.
Timeout/partial/invalid observations cannot be classified as `0/0`.

Forty-eight offline tests passed. Hardware hold/access safety, actual version
results and warm HDMI recovery remain unqualified. Any completed result must
include a fresh cold `1/1` baseline and document clock/reset-release/AudioTop
interventions; a zero pair is not direct evidence of DSP RAM erasure by reset.
