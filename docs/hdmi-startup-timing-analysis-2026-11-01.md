# HDMI first-detection timing: comparison with successful startup tests

Startup was tested successfully, including autonomous cold boots and installed
warm boots. The fresh failure is not evidence that those tests never exercised
startup, nor that every historical acceptance case passed without qualification.
The next useful experiment is a board startup-timing comparison, not another
host GPU reader. **This analysis performed no board or host control operation.**

## Closest known-good comparison

The [October 31 migrated warm boot](hdmi-evidence/2026-10-31-uboot-warm-validation/README.md)
returned the host desktop without a host setting change or board recovery.
Its saved full kernel log can be compared directly with the
[November 1 failed fresh boot](hdmi-evidence/2026-11-01-board-boot/README.md).
The signal module, wrapper, unit, DDC helper, receiver and session script hashes
and metadata match the checked current generation.

Times below are seconds after Linux kernel start, not after mains power-on:

| Event | Successful warm boot | Failed fresh boot |
| --- | ---: | ---: |
| Fourth receiver clock enabled | 17.907 | 18.184 |
| DSP graph verified | 22.441 | 22.718 |
| EDID/HPD ready log | 22.871 | 23.143 |
| First 1280×720 lock | 24.195 | None observed; transitions stay zero |
| Graph-verified → EDID/HPD-ready interval | 0.431 s | 0.425 s |

The failed run advertises readiness slightly later in Linux uptime, with nearly
the same relative sequencing. This argues against a simple missing dependency
or blanket "we start too early" explanation. Cold versus warm electrical/source
history still differs; this is not a controlled timing A/B experiment. The
ready log follows the SCP's operations and is not a physical HPD-edge timestamp.

## What readiness actually gates

The signal unit runs after the capture service, and its wrapper requires the
DSP graph ready. Receiver ownership requires clocks and EDID lifetime readiness;
the EDID consumer enables its clock and releases reset before marking ready.
The signal wrapper then claims DDC pins and launches the owned SCP program.

In [the SCP generator](../tools/hdmi/make-edid-trial-code.py), the activation
sequence is: validate staged payload → force HPD low → disable DDC → configure
controls → write all three EDID banks → verify all three banks → enable DDC →
release HPD force-low → record active state and ready. Thus the implemented
order does not intentionally advertise the sink before EDID programming and
verification. Video-service activation is downstream of source detection.

What is missing is a timed guarantee: no explicit settling delay separates DDC
enable and HPD release, and no explicit minimum HPD-low duration is enforced.
The original HPD control was already `7` (the validated force-low state) at SCP
entry in both compared boots. That limits the inference: absence of an explicit
delay does not demonstrate that the actual low interval was short. A ready flag
also does not establish the external pin voltage or that the first DDC request
was serviced successfully.

## Earlier tests and what they qualify

* [October 14 autonomous cold startup](hdmi-evidence/2026-10-14-normal-startup/README.md)
  passed startup around 23 seconds and subsequent real multi-rate HDMI capture.
  This includes a genuinely autonomous cold run, separate from the earlier
  manually resumed test.
* [October 27 installed cold/warm acceptance](hdmi-evidence/2026-10-27-audio-lifecycle-fix/acceptance/README.md)
  includes picture/audio passes without board service recovery. Some host player
  outputs were reopened after endpoint return; uninterrupted-client acceptance
  was explicitly not claimed. Its no-source reconnect needed a PC-end reseat
  after the first connection remained undetected. First detection was already
  an unresolved coverage gap.
* [September 18 detection trials](hdmi-source-detection-validation.md) ran after
  receiver/EDID-clock setup in a fully booted bench environment. A first trial
  failed before later revisions/repeats succeeded; payload transfer and code
  layout also changed, so it was not a delay-only experiment. Active HPD/DDC
  values and zero active EDID-window reads matched successful source detection.
* The [software HPD-cycle runner](../tools/hdmi/run-alsa-hpd-cycle-test.py) waits
  three seconds between restored trials. That is materially different from a
  first advertisement during boot. Its 12-second signal window is an active
  capture window, not a 12-second HPD-low settling delay.

These records support investigating first-advertisement/HPD/DDC settling, but
do not diagnose a specific delay defect or justify a production timing change.

## Next safe board-side step

Prepare and test offline a temporary **delay-only initial signal startup**
variant. Keep the same EDID, SCP binary, register order, clocks, source selection,
receiver/DSP gates, once-per-boot ownership markers and failure-retention rules.
After all current readiness gates pass, wait an additional **2,000 ms before
initializing the signal owner**. This is an experimental interval, not a claimed
HDMI specification requirement. Do not restart the currently running owner.

On a later explicitly authorized boot, record passive UART/kernel-relative
milestones and cached host connection/EDID transitions from before power-on.
Keep host/cable conditions fixed, with no reseat, forced detection, source-mode
change or hidden recovery. Compare the normal baseline with delayed starts;
repeat matched conditions before calling an intermittent result fixed.

If delay helps reproducibly, it supports a startup/first-detection timing issue,
but does not alone distinguish board settling, a longer inherited HPD-low period
or host readiness. If it does not help, the unmeasured DDC-enable-to-HPD interval
and electrical path remain unresolved. A later separate experiment could isolate
that interval; it would require a new reviewed SCP layout/readback/timing design.
Neither variant is installed or live-ready from this analysis.

Current boot `afe48e93-6604-44de-a220-acb9416e8363` stays untouched in the fresh
failure state. No HPD pulse, reseat, service restart, new probe or reboot ran.
Private reproducible timestamps, matching pin checks and the proposed-test JSON
are in `local/recovery/2026-11-01-hdmi-startup-comparison/`.
