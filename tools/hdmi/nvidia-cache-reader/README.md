# NVIDIA cache-only hotplug reader — preparation

**Offline reader core and passive cached-file mode prepared. Live RM queries
are NOT qualified and are not implemented as a device transport.** This is a
safety-test result, not a claim that NVIDIA's documented cached API is known to
probe the connector. Do not turn the gate into an execution flag or replace the
absent transport with a general-purpose ioctl wrapper.

The current board retains its SCP sampler, owner parameter mutex, guard and
scratch. This tool has no board transport, SSH, owner-parameter reader, service
operation, I2C operation or reset path. Preparation must preserve that endpoint.

## Available modes

```sh
python3 -B reader.py
python3 -B test.py
python3 -B test.py --mutations
python3 -B reader.py --cached-files
python3 -B reader.py --replay example-replies.json
```

Default is an offline plan with no hardware file reads. `--cached-files` opens
exactly four existing sysfs attributes read-only: NVIDIA version and HDMI-A-1
status/enabled/EDID. It bounds each read, requires driver 615.78.08 and the
preserved disconnected/disabled/empty-EDID state. It issues no NVIDIA or DRM
ioctl and is a baseline observation, not the missing RM/physical-HPD measurement.
The NVIDIA I2C adapter numbers are not guessed as HDMI port mappings.

`--replay` executes the real request boundary against eight offline responses.
Every result says simulation/offline and hardware_executed=false. A disconnected
cached result is valid data, not an error that may trigger detection. A live
request using `--execute-approved` refuses before any device open; no approval
flag overrides the unqualified implementation boundary.

## Candidate RM sequence tested offline

The core allows only an isolated root client, device instance 0, and a
NV04_DISPLAY_COMMON object, followed in order by:

1. GET_SUPPORTED, with output placeholders zero.
2. GET_CONNECT_STATE with exact flags 0x31: METHOD_CACHED, DDC_DISABLE and
   LOAD_DISABLE; a nonzero subset of the returned supported mask; no retry.
3. GET_HOTPLUG_CONFIG, zero inputs/placeholders.
4. GET_HOTPLUG_STATE, zero inputs/placeholders.
5. Free only the new client root, never an existing desktop client's resource.

The lifecycle is a candidate ABI/protocol, not a tested live initialization or
cleanup implementation. No live ioctl marshalling is linked. Exact classes,
handles, sizes, ordering, flags, supported masks and response shapes are checked
at the boundary. Any error, malformed reply or request ends the session with no
retry, detection fallback or automatic failure cleanup. A failed allocation
response never admits an invalid client handle. Success cannot be replayed in
the same session.

All setters, EDID access, ECONODDC, GPIO/MMIO, event subscription and consuming
GET_HOTPLUG_UNPLUG_STATE are excluded. Recorded RM hotplug masks are history;
the output never interprets them as current electrical HPD. These requests also
do not establish which mask bit is the physical HDMI-A-1 connector.

## Exact-source and ABI audit

`audit.py` consumes the downloaded official 615.78.08 tree and compiles `abi.c`
against its headers with warnings treated as errors. The native recorder only
prints type sizes, member offsets and constants; it never initializes a vendor
library or opens a device. The audit records source SHA-256 values and official
version-tagged URLs, generated dispatch metadata, constructor and RPC paths.

The critical result is that all four candidate query entries carry
RMCTRL_FLAGS_ROUTE_TO_PHYSICAL (0x40). The open driver's firmware-client route
calls NV_RM_RPC_CONTROL. GET_CONNECT_STATE's flags are 0x848, which must not be
confused with the distinct kernel RMCTRL_FLAGS_CACHEABLE bit 0x400. Choosing
METHOD_CACHED inside the request does not make it a host-kernel-cache-only path.
The physical implementations of the three relevant queries are not in the
published tree, and device construction uses NV_RM_RPC_ALLOC_SHARE_DEVICE.
GPU-device open/last-close code also contains initialization/shutdown paths
that a future transport must account for.

The public API contract promises a cached connection method, but the available
implementation does not complete this investigation's requested source proof of
no re-detection/state changes across setup, queries and teardown. Accordingly,
the package's live gate stays closed. More unit tests cannot supply that missing
firmware assurance. Future work requires a qualified supported RM path or an
existing genuinely passive exported cache interface, with port mapping and
lifecycle reviewed; do not substitute default detection or direct register reads.

The public NO-GO/preparation report records the distinction. The original SCP
package and live capture evidence stay sealed and unchanged.
