# HDMI source-power and callback investigation

The exact board-B display firmware (SHA256
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`)
contains an independently traceable source-power path. The running RC matched
four exact code-region hashes before observation. No receiver MMIO, firmware
RPC, callback registration, driver replacement or retry-policy change occurred.

## Static path

The firmware port poller at `0x8b13942c` invokes the function pointer at
`0x8b22f098` (`0x8b13eff0`) and stores its boolean result at port object
`+0x532`. That reader extracts a per-port bit from physical `0x0684037a` via
the firmware's MIPS byte accessor. These are disassembly results, not addresses
to access from ARM. The poller passes port+8 to the event processing routine,
where offset+0x52a therefore names the same byte. The event routine compares
the raw bit with context+0xe, logs "5V detect", and dispatches state and port.
This is a firmware-polled hardware-status path; no dedicated interrupt route
has been established. [Exact disassembly](static-callback-and-power-trace.txt).

The two-argument callback marshaller at `0x8b10a09c` sends state first and
port second using `MipsHalCallback_HdmiHotPlugByPortHandler` (`0x38d780e2`).
The HAL translator is `0x8b148d5c`. Both BSP and HAL callback slots are zero
on this RC. The registration RPC is not a read-only subscription: it installs
callbacks, and both its adapter and the receiver setter ignore zero/null.
Passing zero is therefore not an established rollback. No callback was enabled.
A separate open/read/poll listener only receives copies of already incoming
CPU_COMM calls; opening it cannot by itself cause firmware notifications.

## Baseline and next physical check

In the running locked 720p baseline, port1 raw power candidate=1; ports2/3=0.
The processed event byte is zero on all ports, consistent with the callback
path being disabled; it must not be used as the current source-power state.
Physical disconnect/reconnect validation and the connected/output-disabled control are recorded below. The earlier status=0x2
with and without video was not a sufficient negative control for source power:
a powered source can remain present when no video is transmitted. It also
remains necessary to check power-off/output-disabled and cold-start conditions
and stale-cache behavior before shipping a power-present API.

`tools/hdmi/observe-source-power.py` maps only bounded reserved MIPS DRAM
read-only, validates exact firmware code and receiver/port identities, and
records raw power candidates, signal state, retry count and copied callbacks.
No ioctl or RPC is issued. Three offline guard tests pass. The observer was intentionally stopped after the completed physical tests. Its recording is under
`local/recovery/2026-11-05-hdmi-hardware-events/passive-01.jsonl`.
The existing retry script/unit hashes and running service identity are recorded
in [retry-policy-before.log](retry-policy-before.log).

## Driver feasibility

If the field follows physical source power with acceptable freshness, the
existing guarded MIPS DRAM mapping can supply a read-only
`V4L2_CID_DV_RX_POWER_PRESENT` control, with a control-change notification on
verified transitions. The single exposed input uses bit0 even though firmware
port1 uses bit1 in its internal register. Invalid identity, disabled polling or
stale/unknown data must not be silently promoted to a validated absent/present
state. Coldplug sampling is needed as well as edges. This is a proposed design,
not an installed change.

Linux API references: [receiver power-present semantics](https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-dv.html),
[V4L2 control framework](https://docs.kernel.org/driver-api/media/v4l2-controls.html).
These APIs do not independently validate the H713 sensor. The retry service
will remain unchanged during validation; reporting source power does not by
itself determine whether a powered source intends to send video.

## Two observed physical loss/recovery intervals

Port1 candidate fell and rose in each observed interval; ports2/3 remained zero,
and no callback copies arrived. The user's initial two physical actions produced
one continuous recorded outage; the additional isolated action produced the
second interval. Video recovered both times. The first interval used one
additional existing automatic retry; the second recovered before any additional
retry. In both intervals the candidate remained zero at an observed video-lock
sample and became one about 0.4s afterward. This is evidence of cable-state
correlation, not a qualified earlier-than-video reconnect event. No electrical
+5V edge timestamp was measured. The connected/output-disabled control is completed below.
[Physical-cycle evidence](physical-cycles-result.json).

After both intervals, all services remain active with zero restarts; rejected
frames, audio xruns, bad-guard and invalid-pair counters are zero. Retry script
and unit hashes and service start identity match the pre-test baseline.

## Connected powered source with video disabled: passed

Chris disabled and re-enabled only the board output through PC monitor settings,
leaving the cable connected. Video went holding -> none -> acquiring -> locked;
port1 power candidate remained1 throughout. No additional retry occurred.
This independently distinguishes the observed firmware field from video lock.
It is not an independent electrical voltage measurement or latency benchmark.

The existing retry script/unit hashes and running service start identity are
unchanged. All final stream error counters are zero, and video is locked720p.
Both passive observers are closed; the DRAM/callback observer was intentionally
stopped by exact-command SIGTERM after testing (host SSH exit255 recorded as
expected), and the UART recorder closed normally. No callback activation or
driver installation took place. [Final result](RESULT.json),
[complete passive recording](passive-01.jsonl),
[final health and policy](final-health-and-policy.json).

The source-power field is a viable input for a read-only driver control and
change notifications. Coldplug, first-advertisement/no-lock behavior and
freshness still require qualification before using it to drive retry. There is
no validated dedicated IRQ or universal failed-handshake event. A powered source
with disabled output has the same power/no-video condition as a stalled
handshake, and rising cache transitions trailed video lock on both reconnects.
The timeout fallback therefore remains unchanged.
