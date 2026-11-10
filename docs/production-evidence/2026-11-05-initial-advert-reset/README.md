# Second first-advertisement candidate: initial DDC-disabled dwell

V1's100ms DDC-enabled settle did not prevent the first-advertisement miss.
V2 tests the other timing difference against the proven fallback: keep DDC
disabled for2000ms before enabling it. HPD stays held throughout this setup.
The owner then requests DDC-on, verifies its SCP readback, waits100ms, and
requests exactly one HPD release with full SCP HPD/DDC readback. Failed
requests/readbacks are terminal and retain ownership. No ARM receiver MMIO,
EDID change, extra preliminary advertisement or retry-count reset is added.

19OR1K model tests cover initial-disabled state, DDC-on, exactly one HPD
rise, fallback commands and exact restoration. Actual owner C-function tests
cover stage order/timings and injected request/readback/exception errors for
both versions. The module builds against the accepted RC kernel withW=1.
Only the signal module and checksum manifest would change on disk; the tested
guarded transaction supplies backup/rollback/readback. Standby soft-start,
radio/capture/receiver modules and retry policy remain unchanged.

Automatic approval review rejected this changed module/installer/audit package
because the previous explicit approval covered V1 only. V2 approval is pending;
no V2 files have been transferred and the board remains running V1 after its
completed five-minute observation. Fresh-source validation is still required.
[Preparation](PREPARATION.json), [package pins](package-manifest.json).

## Approved V2 disk install

The operator explicitly approved V2 transfer/preview/install/audit. The
two-target preview and transaction passed;75file/package/kernel/raw
bootloader/environment checks passed. Backup:
`/var/lib/h713-hdmi-startup/initial-advert-326b7bd6f3d44e12b29c5bec265c4e51`.
No live owner reload occurred. Fresh-source cold validation is pending.
[Install](install-result.json), [audit](after-install-audit.json).

## Fresh-source V2 result and disposition

Boothostb0b8c71b, board4d06d466 loaded V2 correctly. DDC-on readback
verified17.028031s, first HPD release17.132066s. The source still needed
a retry requested27.516572s, completed29.641024s; lock31.132107s and
video active31.186461s. The five-minute window completed331.4s at
59.70773fps with zero errors, no further retries or service restarts;
75pins passed. No-retry qualification is INVALID; V2 is not a demonstrated fix.

Both timing candidates were rolled back on disk through their exact original
transactions. The baseline75-file audit passed after rollback. The live owner
was not restarted. No measurement equipment is available, so the next step
is a separately approved DDC-only versus HPD isolation diagnostic.
[Result](cold-01-feature-result.json), [baseline audit](baseline-restored-audit.json).
