# First advertisement: settle DDC before the first HPD release

The initial signal payload enables DDC and immediately releases HPD. The
validated retry instead enables DDC, waits100ms and then releases HPD. This
candidate tests whether that asymmetry causes the missed first handshake.
It is a hypothesis, not yet a bench-proven fix.

The generated candidate keeps HPD held low through EDID installation and DDC
enable. The owner checks copied startup state, waits100ms and requests exactly
one HPD release through the existing SCP mailbox. The SCP reads HPD and DDC
back into SRAM; the owner verifies full values before exposing ready. No ARM
receiver MMIO is added. Poisoned/missing/wrong readback, exception or failed
acknowledgement is terminal and retains ownership. The retry count and retry
policy are unchanged, so any fallback remains a first-advertisement failure.
The default payload is byte-identical; deferred release is opt-in until tested.

The candidate built withW=1 against the accepted6.18.38RC kernel.14OR1K
payload model tests, the actual C function harness (settling/order plus injected
failures),16retry tests and both disk-installer suites passed. The two-target
installer also passed rollback after each post-write failure boundary.

Disk package scope is only the signal module and its bundle SHA256SUMS. Exact
predecessor files were read from the board, checked against the approved75-file
audit pins, and retained locally. The existing guarded transaction installer
provides durable original backups, atomic replacements and exact readback,
without restarting services or unloading the live signal owner. Standby soft
start, receiver/video modules, EDID, retry script and original global radio
startup are retained.

Automatic approval review rejected transfer of this exact module/installer/audit
package without explicit approval. Approval has been requested; no package was
transferred and no board files changed by this preparation.

After approval: preview/install/readback/audit, then orderly board poweroff.
The operator manually reboots the HDMI source PC with the board supply removed,
returns to chat, and capture is rearmed before board power-on. UART may remain
connected per operator preference. Source boot ID and age, initial first-release
log, source lock, video service readiness, all retry outcomes and five-minute
health are recorded. A boot on a primed source is a different control. Repeat
fresh-source successes before claiming the first-detection fault resolved.

[Preparation](PREPARATION.json), [package pins](package-manifest.json).

## Approved disk installation

The operator explicitly approved this exact package transfer, guarded preview,
disk install and audit. The preview passed. Only the signal module and bundle
manifest were changed, with durable backup
`/var/lib/h713-hdmi-startup/initial-advert-9e4c05aa9d2a48138f095f6515521f1c`.
All75file checks, package/kernel/raw bootloader/environment/startup checks
passed. No live module reload or service restart occurred; the candidate takes
effect at the next boot. Fresh-source validation remains pending.
[Install receipt](install-result.json), [audit](after-install-audit.json).

## Fresh-source cold01 result: initial miss persists

New source boot269d6edc and board boote5350845 loaded the exact V1 signal
module. The first HPD release with verified100ms DDC-enabled settling occurred
at15.180075s. It missed; one automatic retry was requested25.585898s and
completed27.720061s. Lock followed28.944138s; video service active29.001007s.
The five-minute window completed at329.18s:59.70858fps, zero stream errors,
no further retries or service restarts. All75file/runtime identity checks
passed. Strict first-advertisement qualification is INVALID for the retry;
V1 is not a fix. The100ms settling hypothesis alone failed in this run.
[Result](cold-01-feature-result.json), [journal](cold-01-early-journal.log).
