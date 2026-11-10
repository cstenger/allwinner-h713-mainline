# Parallel capture startup installation

**Subsequent result:** the first cold measurement passed. Preparation overlaps
the user session, HDMI readiness improves by 3.15 seconds and renderer startup
by 3.19 seconds versus stage 1. See the [cold result](stage2-cold-result.md).
The installation checkpoint below is retained.

November 4, 2026 (America/Los_Angeles). Chris authorized installing the
parallel capture change and measuring another physical cold boot, following
the successful stage-1 measurement. The stage-1 scripts remain unchanged.

Changes are limited to runtime and backend copies of the capture and prepare
units plus the backend manifest. No firmware, kernel, boot environment,
PipeWire configuration or script payload changed.

| Payload | SHA-256 |
| --- | --- |
| h713-hdmi-prepare.service, both copies | `64d4ecd6f4ec570a89d7cd87bb98820e99b05f8ae358d3ef89522a0ee3993b28` |
| h713-hdmi-capture.service, both copies | `41c45dee2ca8b14cf32f409f31743081a64b9b7566a3076860ca39124820eea5` |
| Backend SHA256SUMS | `cb180caaf08a51995571a23a6196dd65bedbe0e4f79079dad42b6b790972e350` |

Before installation, boot ID remained
`5110ffb9-3fd4-4ee5-9bb5-131fd2d9e828`; all stage-1 identities, both original
capture units, all four HDMI manifests and startup health passed. Original
unit/manifest bytes and root:root 0644 metadata were archived and verified on
the host. The new units passed native systemd verification on the actual
board before installation and again after installation.

The guarded installer (`tools/hdmi/install-parallel-capture.py`) validates
stage-1 scripts, original unit/manifest hashes, exact payloads, absence of
unreviewed capture/prepare drop-ins and lack of independent prepare enablement.
It records original absence of the prepare units and preserves original files
in a private rollback transaction. Four offline tests cover preview, complete
rollback, every partial-write boundary, identity/payload/drop-in/symlink drift
and refusal to overwrite foreign rollback targets. All pass.

Installation and readback completed once. `systemctl daemon-reload` reloaded
definitions without restarting services. Prepare remained **inactive, static,
ExecMainStartTimestampMonotonic=0**; its first startup is deliberately deferred
until boot. Capture retains `After=user@1000.service` and gains the required
prepare dependency. All four manifests and startup health passed afterward;
the five sampled existing HDMI service start timestamps and zero restart
counts were unchanged. No preparation unit was independently enabled.

The committed rollback directory is
`/var/lib/h713-hdmi-startup/parallel-capture-91be7ec632744eab80083052ad956dae`.
Its read-only rollback preview passed and all original backup bytes were
copied and hash-verified on the host. Stage-1 rollback records remain intact.
Private package, receipts, backups and logs are under
`local/recovery/2026-11-04-startup-parallel-install/`.

After UART capture was armed, the verified boot received one clean poweroff
request. UART confirms `[865.851358] reboot: Power down` at host UTC
`2026-11-05T02:06:08.369355Z`. A Bluetooth opcode timeout during shutdown is
retained in the raw log; no recovery/reset was forced. The passive recorder
remains armed for the physical cold startup. No startup improvement is yet
claimed for stage 2.

Next measurement: compare against stage-1 boot's 11.729 s capture start,
17.559 s capture ready, 17.902 s EDID ready and 19.310 s renderer activation
(all Linux monotonic). Record prepare start/finish, user-session readiness,
capture adoption duration and all five MIPS completions. Confirm the prepare
interval actually overlaps user startup; preserve shutdown ordering. Separate
source-detection/retry behavior from backend timing and verify unchanged
stage-1 script hashes, all manifests and picture/audio health. Cold power
requires supply and board-side UART/USB disconnected for at least one minute.
