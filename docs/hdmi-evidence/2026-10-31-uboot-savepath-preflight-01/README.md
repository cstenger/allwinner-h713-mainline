# Fresh save-path read-only preflight — October 31, 2026

**Storage, identity and automatic startup PASS. Live save-path readiness HOLD.**
The powered-on board is in Linux boot `2d8c3970-4164-4a38-8e86-375bb440c971`,
kernel `6.18.38`, with its session ready. This supersedes the earlier operator
power-off status. No UART recorder/controller was armed, no UART command,
GPIO/latch change, environment save, installation or reboot was performed.

The fresh read-only capture is 38,236,160 bytes and stable across collection.
Identity/CID hash, eMMC user area, 512-byte sectors and 7,818,182,656-byte
capacity match the sealed package. Both environment copies remain identical:
SHA-256 `6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc`,
valid CRC, 72 entries, bootdelay 5, no test probe. All nine protected regions
match, including the installed proper, old environment in super, GPT/SPL,
rescue, boot FAT and intended-slot margins. Both GPTs and entry-array CRCs
validate; 28 entries/27 populated and kernel partition geometry agree.
Reserved partition 18 remains unmounted with no holders.

All four bundle manifests and all 56 installed hash/metadata pins pass.
The installed read-only startup script passes, DSP starts 0/0 and becomes
1/1, GP6 is HDOK, GP7 zero, audio/video error counters zero, and the root
filesystem reports clean with no recorded ext4 errors. The installed script
is non-executable by its pinned mode: an initial direct invocation failed
before execution, then it was run successfully through `sh`. No permission
or board-file change was made; both invocation records are retained privately.

The service gate is **not satisfied**: `h713-hdmi-video.service` is inactive
and has never started in this boot. It reports Result=success, no restarts,
and no journal entries. The receiver reports signal `none`. Its unit is
started by udev when the bridge is ready with a locked/holding signal and
stopped when not-ready. This fits the no-signal state; no video service crash
was observed. Five other monitored services are active, all with zero restarts.
The sealed controller requires six active services, so its unchanged
`read_capture` verifier rejects this capture with `service health gate failed`.
We did not start the video service, change input/source settings or weaken that
requirement. This capture is **not an accepted live controller preflight**.

Before a later authorized live run, restore the intended HDMI source so video
starts normally and repeat the fresh service/storage/health preflight. Preserve
the new boot binding and recheck if the boot or environment generation changes.
No timed operation or environment-save authorization is inferred here.

[Result](RESULT.json), [startup and 56 pins](HEALTH-RESULT.json),
[read-only video diagnostics](VIDEO-DIAGNOSTIC.json).
[Save-path protocol](../../uboot-savepath-validation-2026-10-31.md).

Private fresh capture, collector, 56-pin health script, offline validator and
all stderr/invocation records are preserved in
`local/recovery/2026-10-31-uboot-savepath-preflight-01/`. SHA256SUMS and
`preflight-backups-and-evidence.tar.gz` seal this new capture independently;
the previously sealed controller/baseline packages are unchanged. No commit/push.
