# Read-only HDMI source-power control and event-aware retry

The user authorized adding V4L2 source-power reporting and later extended the
scope to updating retry policy. The module and retry script are installed on
disk with durable four-file backup and exact manifest/readback checks. The
board has cleanly powered down; cold-boot and physical event validation are
pending. Original global radio loading remains selected as control B.

The driver reads only guarded MIPS DRAM. Exact firmware code CRCs, receiver and
port identity, enabled polling and boolean field range gate the source-power
cache. The single exposed input is bit0 of V4L2_CID_DV_RX_POWER_PRESENT.
The framework generates standard V4L2_EVENT_CTRL VALUE and FLAGS notifications.
The control is READ_ONLY and framework-cached. INACTIVE means unknown/unavailable:
the last value is retained and must not be interpreted as a current power state.
No volatile-control flag is used because V4L2 suppresses value-change events for
volatile controls. No firmware callback registration or receiver MMIO was added.

The retry service subscribes to control events and re-reads current state at
most once per second. Known absence suppresses HPD pulses; restored power starts
a full waiting period. Unavailable control/status uses the original bounded
10/20/40/80/160 second schedule and 2-second hold. Existing acquiring/active/
holding/unsupported protection and ready/nonfailed-owner checks remain; signal,
power and owner are rechecked before each request. V4L2 has no universal
failed-handshake event, so powered/no-video still needs a bounded watchdog.

The accepted rejection trace remains, now version reject-trace-power-v1. Exact
copy, pair-worker, pair-validation, video port-reading and signal-publication
function bodies match the prior diagnostic module. Host policy, copy-guard and
transaction rollback checks pass; the module builds against the accepted RC
kernel. The 74-file post-install audit checks the new disk files; it does not
claim the new module was live before poweroff. [Install receipt](install-result.json),
[package pins](package-manifest.json), [guard comparison](guard-preservation.json).

DRM/KMS drives the source's display output and this board's panel. V4L2 is the
receiver-facing interface here; adding a DRM connector would not supply a new
receiver sensor or repair firmware handshake behavior. References:
[V4L2 power control](https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-dv.html),
[V4L2 events](https://docs.kernel.org/userspace-api/media/v4l/vidioc-dqevent.html),
[KMS output pipeline](https://docs.kernel.org/gpu/drm-kms.html).

Cold validation: record initial source-power state and loaded build ID, reject
a control write, verify initial control notification, retain any first-advert
miss, observe five minutes of fixed desktop, audit all RC pins, then check
physical control-change events and absence/reconnect retry behavior. Recorder
and observer sessions are recorded in [resume state](RESUME.json).

## Cold01 result and V2 correction

Cold01 loaded the exact power-v1 build. Video was active at16.191347s with
zero retries and a clean five-minute59.70746fps stream window. Power read1,
READ_ONLY was set, S_CTRL returned EACCES13, and the initial CTRL event arrived.
Combined feature qualification failed: empty DQEVENT returns ENOENT on this
kernel, but the first reader accepted only EAGAIN. That caused the retry
process to fall back to unknown-status timeout behavior. The original reader
failure and corrected same-boot API observation are retained.

The firmware cache also initially returned0 despite the attached source,
then1 after lock. V2 therefore marks negative samples INACTIVE/unknown until
the first positive sample on that boot. This avoids suppressing a cold
first-advertisement retry on an unqualified initial zero. Subsequent tested
power loss remains reportable. Empty-queue ENOENT/EAGAIN handling is covered
for both power values. SOURCE_CHANGE subscription is now included alongside
CTRL events; errors close the stale handle and retain timeout fallback.
An extracted actual-driver sampler test covers cold zero, first positive,
later absence, unknown state, and recovery.

V2 module and retry script installed with exact backup/readback and74pins
passed; no live receiver module or service was restarted. The board then
cleanly powered down (UART434.554494). All observers are closed. Next test
uses a freshly rebooted source PC, board off until capture rearmed, to test
the historically failure-prone first advertisement and its fallback.
[Cold01 feature result](cold-01-feature-result.json),
[V2 installation](v2-install.json), [V2 pins](v2-package-manifest.json).

## Cold03 V2 fresh-source result

After a fresh source-PC reboot, the exact V2 build loaded. Initial source-power
zero was INACTIVE/unknown; the retry log confirms timeout fallback, one automatic
re-advertisement at25.065443s, and video active at28.461496s. The power control
then emitted its present/available change; SOURCE_CHANGE was also received.
The read-only write test returned EACCES13 and the event observer remained healthy.

The five-minute window completed at328.64s:59.70879fps, zero rejected frames,
guard/invalid-pair errors or audio xruns, both PCMs RUNNING, and no service
restarts or further retry. All74file pins and runtime/kernel/bootloader audits
passed. The strict no-retry observation is INVALID solely for the initial
HPD re-advertisement; successful recovery does not waive that failure. Physical
disconnect/reconnect and absent-source retry suppression remain pending.
[Cold03 feature result](cold-03-feature-result.json),
[Cold03 observation](cold-03-result.json), [audit](cold-03-audit.json).

Cold02 was interrupted by an operator power-on/off before UART readiness was
confirmed; no first-advertisement conclusion is drawn from that attempt. Its
interruption receipt is retained locally. Cold03 used another fresh source boot
and confirmed host-access UART OPEN before explicit power-on instruction.

## Physical cable events during panel standby

The accidental power-button press entered panel standby at406.118269s without
rebooting Linux. HDMI unplug produced an available power VALUE0 event
at409.332283s. Reconnect produced SOURCE_CHANGE at493.948301s and available
power VALUE1 at494.324337s. At521.16s the signal was locked1280x720, video and
retry services were active with zero restarts, and the retry count remained1.
Thus absence suppressed additional retries and reconnect recovered receiver
lock in this standby condition. Visible panel recovery requires waking the
panel; awake-state repeat and source-output-disabled controls remain pending.
[Absence](cold-03-physical-absence.json), [reconnect](cold-03-physical-reconnect.json).

## Wake failure followed by reboot

Operator reported that the first wake press flashed the panel on/off, and a
second press rebooted it. UART confirms fresh SPL; new Linux boot is
`7fe95ed5-f486-4f2b-aa9f-a7f14e4b93dc`. Receiver is locked1280x720,
V2 remains loaded, retry count is0, and desktop is visually confirmed.
This is not successful standby wake and is not a fresh-source test. The
retained old journal has no standby-off or orderly shutdown entry in its
final tail, and UART has no captured panic/shutdown trace before SPL. Cause
of reset remains unknown. The old power observer exited255 on the reboot.
[Wake/reboot result](cold-03-wake-reboot-result.json),
[journal](cold-03-wake-reboot-journal.log).
