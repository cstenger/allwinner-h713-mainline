# DDC versus HPD isolation diagnostic

Both first-advertisement timing candidates failed their fresh-source runs, and
were reverted on disk to the checked baseline. No HDMI breakout, scope or logic
analyzer is available. This diagnostic separates DDC enable-state reset from
the HPD pulse, which the proven fallback changes together.

The original initial advertisement is retained. The diagnostic version of the
startup policy requires signal none, no known absent power, healthy owner and
zero prior DDC/HPD counts. It observes3seconds of continued no-source state,
requests one DDC-only2000ms reset and100ms settle, then waits up to5seconds
for lock before starting the unchanged bounded HPD fallback. Active/acquiring/
holding/unsupported streams are skipped. A state/count gate is checked again
immediately before the request. The module permits this diagnostic only once
before any HPD retry, checks full SCP-copied HPD/DDC values after both steps,
and marks a failed transaction terminal while retaining every owner resource.
Neither DDC-off-only nor DDC-on command writes HPD in the generated program.
No ARM receiver MMIO, callback installation, firmware RPC or driver reload is added.

The counters and JSON journal distinguish DDC repair from HPD re-advertisement.
DDC-only lock with readvertised0 would show no programmed HPD pulse was needed
for that recovery; it would not prove an untouched initial DDC handshake or an
electrically glitch-free HPD waveform. DDC-only failure followed by HPD recovery
is also a useful negative result. The diagnostic can add about10seconds before
the old fallback starts if it does not recover video. It is not a product fix.

Offline checks:24OR1K model tests (including no HPD write in DDC-only branches),
6policy tests (including candidate main/cleanup),16unchanged fallback tests,
actual kernel-setter success/gates/stage-error tests,3installer tests with all
3post-write rollback boundaries, accepted RC kernelW=1 build, and byte-identical
legacy payload. The generated header is opt-in; production policy default
DIAGNOSTIC_DDC_ONLY remains false in repository source.

The operator explicitly approved this exact module/script/installer/audit
package. Three disk files were atomically replaced with durable original backup:
signal module, startup policy and their checksum manifest. No live module or
service was restarted. All75file pins and package/kernel/bootloader/startup
checks passed. Standby soft-start and other RC components remain retained.
Fresh-source hardware validation is complete: the DDC-only reset did not recover video. One subsequent HPD fallback recovered the stream. The diagnostic was rolled back on disk to the original three files; all75baseline file pins pass. No live service or module was restarted.

[Preparation](PREPARATION.json), [package pins](package-manifest.json),
[install](install-result.json), [audit](after-install-audit.json).

## Fresh-source result

Source boot `9df6717c-ea4b-4585-b53f-270178c13431`, board boot `d50d994e-b1f6-4afc-8b84-dccf6483c1b5`. Initial owner ready14.877s; DDC-only cycle completed20.424s with SCP full register readbacks and no programmed HPD change. Still no lock at25.458s. HPD fallback completed37.608s, lock38.880s and video service38.927s. Counts: one DDC cycle and one HPD retry. Operator confirmed desktop visible. Five-minute recovered stream59.706788fps with all four error counters zero; no-retry qualification fails solely because HPD re-advertisement occurred. This is a negative isolation result, not an initial-detection fix. Electrical HPD waveform remains unmeasured.

[Feature result](cold-01/feature-result.json), [observation](cold-01/result.json), [rollback](cold-01/rollback.log), [baseline audit](cold-01/baseline-restored-audit.json).
