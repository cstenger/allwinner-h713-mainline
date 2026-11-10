# One NVIDIA cached snapshot attempt — November 1, 2026

**INCOMPLETE: Device allocation was denied; no display snapshot was collected.**
Exactly one authorized attempt ran. No retry, privilege change, GPU-device
open, display query, DDC probe, modeset, restart, reset or board access followed.
The board remained powered off as reported by the operator.

[Result](RESULT.json), [consumed-attempt record](LIVE-ATTEMPT-CONSUMED.json),
[sanitized event trace](events.jsonl), and [offline denial replay](offline-denial-replay.txt).
The sealed preparation packet remains unchanged as a historical checkpoint;
its live-readiness conclusion is superseded by this result. Do not rerun it.

## What the attempt actually did

The archive and working packet matched before execution. Host version, boot,
PCI identity and cached DP desktop checks passed; baseline and intent were
saved durably. The control node opened, and six RM ioctls returned:

| Request | Result |
| --- | --- |
| Allocate own root client (`0x41`) | Success |
| Attached GPU IDs (`0x201`) | One GPU, `0x00000c00` |
| GPU PCI metadata (`0x21b`) | `0000:0c:00` |
| GPU instance metadata (`0x205`) | Flags `9`: already in use, boot master, non-SLI; device/subdevice `0/0` |
| Allocate own Device (`0x80`) | `0x0000001b`, `NV_ERR_INSUFFICIENT_PERMISSIONS` |
| Free own root client | Success |

The reader closed its control FD without a reported cleanup error and exited
with failure. It never allocated DisplayCommon or requested supported displays,
connector mapping, cached connection or recorded hotplug state. This is a
successful refusal/cleanup observation, not a successful HDMI measurement.

## Cause and correction to the preparation audit

The lifecycle audit missed an explicit Device constructor access requirement.
In [deviceConstruct_IMPL](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/nvidia/src/kernel/gpu/device.c),
user contexts call `osIsGpuAccessible` and return this permission error when it
fails. Its exact-version [host implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/kernel-open/nvidia/nv.c)
iterates the calling process's file descriptors and requires a matching GPU
device file. Holding only `/dev/nvidiactl` cannot meet that requirement.

This source path explains the observed denial. It does not mean that the GPU
was off, the cached queries were privileged, or HDMI detection failed. Merely
running the unchanged reader as administrator does not remove the file-descriptor
check: it applies to every privilege level below kernel mode. No such retry ran.

The fake kernel used for preparation admitted Device allocation without this
access prerequisite. The offline protocol/ABI tests therefore did not establish
the proposed control-only lifecycle's live feasibility. An additional regression
replays the actual denied sequence and verifies immediate own-client cleanup,
absence of display queries and refusal to repeat the session. It does not repair
the missing prerequisite or qualify a replacement live path.

## Later host observation and limits

Attempt files place the denied request and cleanup at approximately **00:04:42
PDT**. The old-boot kernel journal later records an `xdg-desktop-por` process
segfault in `libnvidia-glcore.so.615.78.08` around **00:05:56**, followed by
shutdown around **00:06:02**. A new boot starts around **00:06:22**. These times
come from retained file metadata and journals, rather than a continuous recorder.
The ordering does not establish causality. No host restart/reset command was
issued by the reader or during follow-up analysis.

The later full-host passive check has a different boot ID. Thus a same-boot
post-attempt verification is unavailable. Its connector states, enabled flags,
cached EDID lengths and hashes match the saved baseline: two DP displays enabled,
HDMI disconnected/disabled with empty cached EDID. This is a later-boot cache
comparison, not proof of uninterrupted display operation. The retained old-boot
kernel log contains no NVIDIA Xid or kernel panic establishing a GPU fault;
that absence does not exclude one.

Private raw journals, events, authorization, stderr, baseline and later passive
check are in `local/recovery/2026-10-31-nvidia-cache-reader-v2/live-01/`, with an
adjacent evidence archive. Root/client handles and unrelated host details stay
private.

## Next safe work

Remain offline/read-only: investigate the later graphics-library failure and
redesign/test the Device-access prerequisite before another GPU experiment.
Any required GPU descriptor must have its creation, lifetime and cleanup
audited; do not add a plain GPU open or silently escalate privileges. In
particular, the source's nonblocking-open path can queue a deferred open, so
`O_NONBLOCK` alone is not a proven no-initialization guarantee. No replacement
descriptor strategy is qualified here.

The original board HDMI bad state was lost at power-off. This failed off-board
baseline attempt adds no evidence distinguishing physical HPD, DDC or cached
HDMI detection. The one-attempt authorization is consumed.
