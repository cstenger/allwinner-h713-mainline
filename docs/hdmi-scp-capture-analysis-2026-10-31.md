# Live SCP sample analysis and next preserved-state diagnostic

**Later checkpoint:** the operator powered off the board, ending the preserved
failure/SCP session. A [redesigned NVIDIA cached reader](nvidia-cache-reader-2026-10-31.md)
is prepared and tested under a supported API-contract qualification; no live
GPU call has run. Retention statements below describe the earlier session.

The [guarded capture](hdmi-evidence/2026-10-31-scp-capture-live/README.md)
provides a valid current SCP read, with completion, fresh return proof and
subsequent byte-identical SRAM verification. It narrows the investigation but
does not identify a root cause. No further board access or control operation
was performed for this analysis. The sampler/owner lock/guard/scratch remain
retained.

## What changed in our understanding

All 11 receiver words also recorded at this boot's original handoff still
match. This argues against persistent drift in these sampled controls between
handoff and capture. It cannot exclude a transient, an unsampled control or
electrical behavior.

| Observation | Interpretation and limit |
| --- | --- |
| HPD control `0x07091014 = 0` | Matches this boot's handoff and a successful historical detection trial. Zero is not evidence that the connector's physical HPD voltage is low. |
| DDC `B00=00a0a0a0`, `B04=07000007`, `B08=00c0c0c0` | Matches handoff and the historical successful active configuration. The three low DDC-enable bits remain set. |
| EDID bank first two words all zero | First words were already zero at handoff. More decisively, a successful historical trial also read active-window zeros while the host read the correct EDID. These reads are not proof of an erased EDID. |
| Retained payload has valid header/checksums | Confirms the staged SRAM payload. It does not independently prove current cable-side DDC communication. |
| Host disconnected, disabled, zero cached EDID | Detection has not supplied a usable sink to DRM. The capture does not distinguish absent HPD at the GPU, HPD event handling, or DDC/detection failure. |

The direct historical evidence is the [September source-detection validation](hdmi-source-detection-validation.md),
its [target log](hdmi-evidence/2026-09-18-detection/target.log), and
[host transitions](hdmi-evidence/2026-09-18-detection/source.json). The target log
records the same four active HPD/DDC values and zero bank headers; the host
then reports a connected sink and the exact expected EDID. That was board A
with a different test image, so it establishes a counterexample to interpreting
zeros as failure, not electrical equivalence with the present board.

The four optional IO words match this boot's handoff. They are not identical
to every old experiment (the successful no-stock-IO trial left all four zero),
so the entire 14-word current frame should not be called a universal known-good
signature.

Passive host file reads during this analysis confirm NVIDIA `615.78.08`, the
same disconnected/disabled/zero-EDID cached state, five NVIDIA I2C adapter
names, and no `ddc` symlink on the HDMI connector. Adapter names alone do not
map the HDMI port to a safe bus. Existing kernel logs contain no record that
resolves physical HPD or DDC failure; lack of such a log is not absence of an
event. The old RLD clock warning still does not identify this HCP payload.
Private host evidence is in
`local/recovery/2026-10-31-scp-capture-analysis/`.

## Next safe software-only step

Prepare and source-audit a minimal **host-side, cache-only NVIDIA hotplug
snapshot reader**, leaving the board and retained sampler untouched. The
immediate purpose is to compare the NVIDIA resource manager's recorded
connection/event state with DRM, rather than repeat the same receiver sample.

The version-matched NVIDIA [system-control header](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073system.h)
distinguishes cached connection queries from detection that can use DDC or
load detection. It also documents recorded hotplug configuration and state.
Candidate requests to audit are static display/connector identity,
`GET_CONNECT_STATE` using explicit `METHOD_CACHED`, `GET_HOTPLUG_CONFIG`, and
`GET_HOTPLUG_STATE`. The helper must fail closed without falling back to the
default detection method, and its client/object initialization and exact
implementation paths must also be checked before live execution.

Do not treat every `GET` as passive: `GET_HOTPLUG_UNPLUG_STATE` explicitly
consumes per-client event reports, so exclude it. Exclude ECONODDC, fresh EDID
reads, connector-force operations, generic bus scans, GPIO/MMIO pokes and
hotplug/modeset setters. NVIDIA's [EDID-control header](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073specific.h)
also distinguishes a cached copy from a new DDC transaction; do not substitute
one for the other. The missing DRM DDC link is not a reason to guess an I2C bus.

Recorded hotplug masks are history, **not the current physical HPD input**.
If RM says connected while DRM says disconnected, that supports a discrepancy
between software layers. If both say disconnected, missing physical HPD versus
failed/stale detection remains unresolved. A separate raw-HPD observation is
useful only if a version-matched supported input-only path can be proven safe;
none has yet been qualified. Do not assume that disabling DDC in a detection
request automatically makes the remaining operation a pure HPD read.

This is a concrete next preparation step, not authorization to force a probe
or change the retained state. No new NVIDIA ioctl, I2C transfer, board SRAM
patch, owner release, service restart, HPD pulse or reboot ran during analysis.
