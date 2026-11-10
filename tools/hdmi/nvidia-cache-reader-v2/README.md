# NVIDIA cached snapshot v2

**Live qualification failed on November 1.** The control-only lifecycle was
denied Device allocation because it lacks the GPU FD required in the caller.
The one attempt stopped and freed its own client; no display query ran. Do not
repeat this packet. See the [live analysis](../../../docs/hdmi-evidence/2026-11-01-nvidia-cache-live/README.md).
Preparation statements below are historical. The sealed packet is unchanged.

Prepared for one explicitly authorized live snapshot using NVIDIA 615.78.08's
supported query API. **No live GPU control call was run during preparation.**
The default command is an offline plan. The board has been powered off by the
operator; the former preserved HDMI failure/SCP session is over. The old SCP
package is historical and must not be reused on another boot.

## Why this replaces the first candidate

The first candidate stopped at the fact that display queries and device
allocation route into GSP. That fact remains true: this tool does not eliminate
firmware execution or prove the firmware implementation. The qualification
basis is now the supported, version-matched cached/query API contract plus an
open-source audit of the host setup and teardown paths. It is suitable for an
ordinary read-only diagnostic snapshot, not a proof of zero internal firmware
state changes or preservation of the original failure across power loss.

The redesign addresses specific host-side risks:

* Opens only `/dev/nvidiactl`. Its exact-version `nvidia_open` path goes to
  `nvidia_ctl_open` before the GPU-device adapter-open path. It does not open
  `/dev/nvidia0`, initialize an adapter, register GPU descriptors, attach GPUs,
  acquire modeset ownership or create a display-engine/channel class.
* Uses root metadata queries implemented in host KRM to require exactly one
  already-attached GPU, match PCI `0000:0c:00.0`, and require existing in-use,
  non-SLI state before creating its own device reference. No attachment fallback.
* Creates only its own client/device/DisplayCommon objects. Public constructor
  code initializes per-client bookkeeping and disabled notifier actions. Cleanup
  frees only this client tree and closes this control FD; it never targets a
  desktop client, display engine, service or board resource.
* Uses fixed METHOD_CACHED/DDC_DISABLE/LOAD_DISABLE flags (`0x31`), static
  connector metadata and recorded hotplug state. An error never falls back to
  default detection, ECONODDC, fresh EDID, direct I2C, force-connect or modesets.
* Omits GET_HOTPLUG_CONFIG: it is administrator-only and its subscription mask
  describes the new reader client, not the desktop's subscriptions. All selected
  query dispatch entries allow unprivileged callers.
* Excludes GET_HOTPLUG_UNPLUG_STATE, which consumes reports; it neither creates
  event subscriptions nor clears/acknowledges pending display events explicitly.

GSP still performs its normal handling of the documented requests and owned
resource lifecycle. No public firmware implementation is available to prove
stronger behavior. The package records that boundary rather than declaring it
firmware-free. Normal driver fault handling is outside this helper's control;
the helper contains no reset, reload, restart, recovery or retry command.

## Implementation and evidence

`protocol.py` is the strict one-snapshot protocol. `transport.py` validates the
same immutable request again immediately before its sole ioctl site and
marshals exact NVOS21/NVOS54/NVOS00 envelopes with private live parameter buffers.
Only allocation, allowed controls and freeing this root are encodable. Root
creation and explicit cleanup are each attempted at most once. A failed query
runs only own-client cleanup; no query is retried. Closing the FD also invokes
normal driver cleanup of resources owned by that FD.

`prepare.py` archives version-tagged primary-source references, checks generated
routing/privilege metadata and the host control-open path, and compiles `abi.c`
against NVIDIA's exact headers with `-Wall -Wextra -Werror`. The native ABI
recorder only prints sizes, offsets, ioctl encodings and constants. The package
contains no vendor userspace library initialization.

The syscall adapter calls libc directly and raises on `EINTR`; it deliberately
avoids Python `fcntl.ioctl`'s automatic retry behavior. The test suite exercises
the actual protocol and ioctl codec with a fake kernel
peer that decodes the mutable ioctl buffers and accesses their real parameter
pointers. It verifies request order, all failure positions before/after a
simulated kernel application, RM status failures, client cleanup, bounded
connector metadata, zero cached connection results, malformed replies,
unsafe commands/flags, device-node identity checks, host baseline gates,
durable logging and packet corruption. The suite's results are offline model
and ABI evidence, not a live GPU qualification claim.

## Later execution

From the sealed private package:

```sh
python3 -B PACKAGE/reader.py
python3 -B PACKAGE/test.py
python3 -B PACKAGE/test.py --mutations
```

A later authorized live action requires `--execute-approved --output NEW_DIR`.
The package checks its entire checksum ledger, ABI and gate; reads only cached
sysfs baselines; requires the pinned host boot, PCI/driver identity and an
active DP desktop; and durably saves baseline and intent before opening the
control node. There is no requirement for the board to be on and no board
transport exists. Do not power it on merely to run this reader.

Use the full host context. This task's sandbox cannot see `/dev/nvidiactl`;
a stat-only full-host check confirmed a root-owned character node, major 195,
minor 255, mode 0666. Do not create a node or load a driver to compensate for a
missing node. No administrator-only query is selected, although leaving the
sandbox requires the normal execution approval mechanism.

Every ioctl intent and returned payload is flushed/fsynced. A 30-second alarm
raises an exception rather than returning to an interrupted call. The libc
adapter does not retry any syscall error, including `EINTR`. This is an
observation deadline, not a guarantee that a blocked kernel call/cleanup can be
preempted. On any error retain FAILURE.json/events and do not automatically
repeat or reset. A client-cleanup failure prevents a success result.

After success, cached DRM attributes and host identity are read again. Changes
are reported, not undone. The RM and DRM observations are sequential rather
than atomic. Static connector metadata labels HDMI-A IDs without guessing I2C
adapters; shared/ambiguous IDs remain visible in the raw mapping. Recorded
hotplug masks are history, not an electrical HPD measurement. No result proves
current cable-side DDC communication. With the board powered off, a disconnected
snapshot is a baseline, not reproduction or diagnosis of the old bad state.
