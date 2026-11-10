# Completion-aware IPC installation

**Subsequent result:** the first measured cold startup passed, with capture
initialization reduced by 5.21 seconds. See the
[cold result](stage1-cold-result.md). The installation checkpoint below is
retained, including its then-pending measurement status.

November 4, 2026 (America/Los_Angeles). Chris authorized installing stage 1
and measuring a cold boot before proceeding with parallel capture startup.

Only `/usr/lib/h713-hdmi/mips-shell.py`, `h713-hdmi-session.py` and their two
entries in the backend `SHA256SUMS` changed. Modes remain 0644, root:root.
No service units, firmware, kernel, boot environment or parallel-start payloads
were installed. The accepted original RC artifacts remain immutable.

| File | Installed SHA-256 |
| --- | --- |
| mips-shell.py | `53320e85a66d48c7f9eb93b070770205f9012eb278f959992be4782b6ecfb6c7` |
| h713-hdmi-session.py | `e8b0a1c327778d25eb7e1fcdcf5465aa04985bfd8ea20c47c2dd5048ebcb5739` |
| Backend SHA256SUMS | `37bb3c51c925ce2a119f74d040c1fd9952481df0d83eb0486cf574b04bb1f231` |

The running boot remained `60f461e3-b6a5-461c-af32-9d9bcfceb1fe` throughout
installation. Old hashes matched the saved baseline, all four HDMI manifests
and startup health passed before and afterward, and the five sampled HDMI
service process-start timestamps and zero restart counts stayed unchanged.
The original files/metadata/manifest were copied and verified on the host
before any replacement. A committed board rollback copy was then archived
and hash-verified on the host; its read-only rollback preview passes.

The narrow installer (`tools/hdmi/install-ipc-completion.py`) uses existing
checked path/atomic-write/fsync helpers. Four additional offline tests cover
read-only preview, exact install/rollback, corrupt/foreign identities and
payloads, metadata/symlinks, and injected partial-write recovery. It only
accepts the exact two script generations, original manifest and measured
capture unit; it refuses parallel-start presence and incomplete transactions.
The new preparation unit remains absent.

An initial installation preview stopped because this fresh RC had no
`/var/lib/h713-hdmi-startup` directory. No script was written. The authorized
installation created that private rollback directory (0700); the subsequent
preview and installation passed. Archive timestamp warnings reflect the
already-known stale board RTC, not changed host timestamps or corrupt bytes.

The passive UART recorder was armed before clean poweroff. Poweroff was
requested once after identity/backup/health verification. UART confirms
`[1608.063934] reboot: Power down` at host `2026-11-05T01:32:32.389903Z`.
The recorder remains armed for the next physical cold startup. No cold-boot
speedup or first-start acceptance is claimed yet.

Private logs, original archive, committed rollback archive, installer receipt
and recording are under `local/recovery/2026-11-04-startup-ipc-install/`.
Board rollback directory:
`/var/lib/h713-hdmi-startup/ipc-completion-2922e7f9799247a1b65f54bc73f100dc`.

Next: power fully disconnected with board-side UART/USB removed for at least
one minute, then reconnect UART and power on with the same HDMI source/cable
conditions. Collect per-check completion durations, capture initialization,
EDID readiness, source lock/retry and renderer timing. Read the preceding
boot's persistent journal for clean teardown results. Verify stage-1 hashes,
all four manifests, original capture unit, absent prepare unit and picture/
audio health. Compare backend timing separately from host detection/retry.
Parallel capture remains deferred until these results have been reviewed.
