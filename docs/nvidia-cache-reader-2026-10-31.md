# NVIDIA cached snapshot reader v2 — October 31, 2026

**Superseded by live result, November 1:** the single attempt stopped at Device
allocation with `NV_ERR_INSUFFICIENT_PERMISSIONS`. The lifecycle audit missed
the caller's required GPU-device FD. Own root cleanup succeeded; no display
queries ran. A later host boot differs, so same-boot post-verification is
unavailable. [Failure analysis and next offline work](hdmi-evidence/2026-11-01-nvidia-cache-live/README.md).
Do not rerun this packet; preparation-only conclusions below are historical.

Preparation finalized November 1, 2026.

**Prepared and tested for one separately authorized live snapshot. No live GPU
ioctl ran.** All 37 offline tests pass and all 11 deliberate safety mutations
are detected. Exact NVIDIA 615.78.08 ABI checks compile with warnings treated
as errors. [Protocol, implementation and operating notes](../tools/hdmi/nvidia-cache-reader-v2/README.md).
[Machine-readable result and test evidence](hdmi-evidence/2026-10-31-nvidia-cache-reader-v2/README.md).

The operator reports the board powered off. Its former HDMI failure and resident
SCP session are no longer preserved. The previous live capture remains useful
historical evidence; its boot-bound packet must not be reused after power-on.
This reader never accesses or powers the board. A snapshot with the board off
would establish a host baseline, not reproduce the old failure.

## Resolution of the GSP blockers

The first candidate's stronger firmware-free/source-proof requirement could
not be met: the physical implementations are absent from the published tree.
Version 2 does not pretend otherwise. Its qualification basis is the supported,
version-matched query contract plus an audited and tightly bounded host path.
GSP execution remains, including owned resource allocation/free; the reader
does not promise zero internal firmware state changes or immunity to driver bugs.

| Concern | V2 design and evidence |
| --- | --- |
| GPU-device open could initialize an adapter | Opens only the verified control character node, `/dev/nvidiactl`. `nvidia_open` dispatches this to `nvidia_ctl_open` before the GPU adapter-open path. |
| Unknown GPU/device identity or implicit attach | Three host-KRM metadata queries require exactly one already-attached, already-in-use non-SLI GPU at PCI `0000:0c:00.0`. No attach API, guessed minor or fallback exists. |
| Setup/teardown could take over desktop display state | Only a new root client, Device and DisplayCommon objects are allowed. No display-engine/channel, ownership, event registration or modeset class. Free targets only this client's tree; close targets only this control FD. |
| METHOD_CACHED confused with a host-only cache | The connection request uses exact flags `0x31`, while the report explicitly identifies the GSP/API-contract boundary. No default/ECONODDC/fresh-EDID fallback. |
| Hotplug getter might consume notifications | Consuming GET_HOTPLUG_UNPLUG_STATE is forbidden. Only recorded GET_HOTPLUG_STATE is selected. |
| GET_HOTPLUG_CONFIG is privileged and client-specific | Removed. Generated flags `0x44` require admin, and its subscription mask describes the new reader client rather than desktop subscriptions. Every selected query is non-privileged. |
| HDMI mask bit guessed from an I2C adapter | Bounded static GET_CONNECTOR_DATA queries associate supported display IDs with connector type/index/location. Ambiguous/shared mappings are reported, not forced. |
| Interrupted ioctl could be silently retried | Uses libc directly instead of Python fcntl.ioctl; errors including EINTR raise after one call. No application retry. |
| Partial result or cleanup failure mistaken for success | Durable baseline/intent precede driver access, every request/response is logged, failures retain evidence, and cleanup failure prevents a success result. |

The primary references are NVIDIA's exact-version
[control open/close implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/kernel-open/nvidia/nv.c),
[ioctl dispatch](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/nvidia/arch/nvalloc/unix/src/escape.c),
[device lifecycle](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/nvidia/src/kernel/gpu/device.c),
[display-object constructors](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/nvidia/src/kernel/gpu/disp/disp_objs.c),
[query contracts](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073system.h),
and [static connector contract](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073specific.h).
The private package archives relevant source files and their hashes.

## Validation and package

Tests run the actual Python protocol and ctypes ioctl codec against a fake kernel
peer that decodes the real outer buffers and parameter pointers. They cover all
13 request boundaries in a three-display example, syscall failure before/after
simulated application, RM status failures, unsafe flags/commands, wrong GPU,
malformed replies, client cleanup and cleanup failures, actual ABI data,
node identity/race checks, cached baseline checks, package corruption, durable
orchestration, interrupted calls and byte-buffer copyback. No test contacts a
GPU, board, display server or I2C adapter.

Passive sysfs reads confirm NVIDIA 615.78.08 and two enabled DP monitors; HDMI
is disconnected with no cached EDID, as expected with the board powered off.
A full-host stat-only check confirms `/dev/nvidiactl` is root-owned character
195:255, mode 0666. The sandbox hides that node, so later execution must use the
full host context. No node is created, driver loaded or permission changed.

Private packet: `local/recovery/2026-10-31-nvidia-cache-reader-v2/package/`.
The adjacent archive/checksum preserve the packet, source audit, exact ABI,
tests, mutation evidence, host baseline and explicit live gate. Default mode
prints an offline plan. Actual snapshot requires an explicit execution flag
and a new private output directory and is still unexecuted.

The output comprises sequential RM/DRM caches and static connector metadata.
It is not atomic, does not measure electrical HPD and does not perform a fresh
cable-side EDID read. No reseat, source-output setting, HPD pulse, service/driver
restart, SCP operation, storage write, UART command or board reboot occurred.
