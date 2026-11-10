# Two-second startup-delay variant: offline preparation

**PASS offline; not installed or run on the board.** The temporary package adds
at least 2,000 ms after capture/receiver/DSP readiness and before the original
signal ownership markers, DDC claim and SCP initialization. A matched 0 ms
control uses the same checks and logging. The sample service overrides differ
only in that delay argument.

This follows the [startup timing comparison](../../hdmi-startup-timing-analysis-2026-11-01.md).
It tests a later initial advertisement. It does not change the SCP sequence or
add a delay between DDC enable and HPD release, and is not a production fix.

| Offline check | Result |
| --- | --- |
| Delay-specific tests, including real workstation two-second wait | 24 pass |
| Existing wrapper ownership, failure-retention and shutdown regressions against generated candidate | 31 pass |
| Broken variants detected by safety/order/timing oracles | 6/6 |
| Isolated systemd verification, generators disabled | Both overrides pass |
| Original AST after removing explicit bench hooks | Exact match, including stop branch |
| Independent runtime rebuild | Byte-identical |
| Production wrapper/unit source hashes | Still match installed baseline pins |

The checks reject the current failed boot, existing owners/diagnostics/attempt
markers, extra signal arguments, alternate bundles, manifest tampering, changes
to any of the 56 baseline file pins, unavailable readiness, and drift during the
wait. Logging, clock and sleep errors abort before the original markers/holds.
Explicit bench tests also cover DDC claim failure, verified pre-SCP rejection
cleanup and ambiguous loaded-owner retention. Original shutdown and later
initialization recovery behavior are preserved, rather than reimplemented.

Mutations detected: one-second wait, skipped wait, wait after DDC claim, skipped
post-wait checks, allowing the excluded boot, and allowing fault arguments.

The package and complete source snapshot are under
`local/recovery/2026-11-01-hdmi-start-delay/`, with internal SHA256SUMS and a sibling
archive/checksum file. The [runbook](../../../tools/hdmi/startup-delay-bench/RUNBOOK.md)
describes the later staging/backup/reversion boundary. No installer is included.
Runtime files would live separately from the production bundle; original
ExecStop, unit ordering, restart policy, timeouts and all module binaries remain
the production versions. The manifest's hash is embedded in the private wrapper.

Both variants add common read-only preflight/logging overhead. Their readiness
checks assume the existing single systemd invocation and no competing manual
operations. A successful production stop still clears the original attempt
latch; the experiment must not be reused in that boot. Unit parsing uses
placeholder dependencies and cannot qualify the eventual installed merged unit.

Live installation and any boot remain separate work requiring authorization,
fresh board preflight and merged-unit review. Compare repeated matched boot
conditions with passive UART and cached host observation, with no reseating or
recovery during measurement. One successful boot would not establish a fix.

Preparation did not connect to the board, install files, restart services,
change HPD, reseat cables or reboot. Boot
`afe48e93-6604-44de-a220-acb9416e8363` remains excluded from the bench path.

Evidence: [result](RESULT.json), [delay tests](offline-tests.log),
[existing regression suite](production-regression.log), [mutations](MUTATIONS.json),
[unit checks](UNIT-CHECKS.json), [AST proof](AST-PROOF.json).
