# HDMI discovery failure preserved — October 31, 2026

The operator confirmed that HDMI connects the board directly to the host GPU,
and that reseating is an established workaround. **Do not reseat, toggle the
source, pulse HPD, restart HDMI services or reboot to investigate this instance.**
The bad state remains available in Linux boot
`2d8c3970-4164-4a38-8e86-375bb440c971`. The proposed reseat recorder was prepared
but never started; the operator rejected that recovery experiment.

## Observed boundary

* NVIDIA RTX 3090 / driver 615.78.08 reports HDMI-A-1 disconnected, disabled,
  no modes and zero EDID bytes. COSMIC lists only the two DP monitors. This
  is below an ordinary compositor setting that disables a detected display.
* A DRM connector query through `modetest -M nvidia-drm -c` still reports the
  HDMI connector disconnected with no EDID. It did not restore discovery.
  No modeset or output-setting command was issued. The initial modetest form
  with only `-D` failed to open a device; the driver-selected query succeeded.
* Board receiver holds four clocks, firmware and EDID resources, two clients;
  init_error=0, signal owner ready=Y/failed=N. The bridge remains none with
  zero transitions/frames. Video service has not started. Its inactivity is
  downstream of missing signal, rather than an observed player crash.
* Read-only bounded SRAM/DRAM snapshots show SCP reset control bit 0 released
  (`0x1`), exact expected 1,648-byte SCP code, marker/backup/ready magic,
  exception/error/stop/done zero, and DDC mux PL10–PL15 `0x222222`.
* The 256-byte SCP payload is checksum-valid HCP / H713 HDMI IN EDID,
  preferred 1280×720@60; SHA-256 edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34.
  This is payload SRAM, **not a new live read of peripheral EDID RAM**.
* MIPS port 1 is selected/no-video (state 3), zero dimensions and cached count;
  other ports are state 1. Two snapshots show unchanged port cache and SCP
  SRAM. These fields provide no independent proof of firmware liveness.

The host kernel has an earlier boot warning about RLD maximum pixel clock;
RLD is not this payload's HCP identity, so that warning is not established as
causal evidence for this failure. Do not blame the driver version from that
warning alone.

## Why the health PASS did not settle this

The current signal program configures/read-checks EDID and HPD once, writes
ready and then waits for a stop request. It does not continuously read or
reassert those controls. Thus the production ready flags can remain true if
a later writer or electrical/host detection issue prevents discovery.
The current interface has no live HPD/DDC readback request. A valid SRAM
payload does not establish the physical HPD level or successful host DDC reads.
The startup health PASS is narrower than live HDMI detection.

Source audit also finds no explicit time-based HPD-low dwell in the SCP's
EDID setup before releasing its force-low. That is a **hypothesis to measure**,
not a diagnosed timing bug or justification to insert a recovery pulse now.
Remaining candidates include peripheral state drift after setup and a
source-side hotplug/discovery latch. The observations do not distinguish them.

## Software-only next measurement

The decisive next sample is current HPD/DDC/IO controls and peripheral EDID
headers, read by the SCP while the bad state is preserved. ARM must never
read 0x07091000–0x07091fff or 0x06940000. Existing read-only interfaces cannot
produce that sample.

An **offline prototype only**, `capture-probe-offline/` under the private
recovery directory, models a one-shot sampler inserted into the existing SCP
wait loop. It reads 14 peripheral words, writes only SCP SRAM, self-restores
the wait instruction and restores the registers it uses before returning.
100 deterministic randomized register/data cases pass the restricted OR1K
instruction model. It proposes no HPD/DDC writes, SCP reset, service stop or
HDMI reinitialization. The prototype and exact before-bytes are preserved.

**This prototype is not a live-ready tool and has no live executor.** The
model does not prove live instruction-fetch coherency, atomic insertion,
coordination with the running kernel owner or recovery from a stalled SCP bus
read. Its done marker alone does not prove the final return executed. Those
points must be resolved in a reviewed live protocol before any SRAM patch;
preparation is not permission to instrument the running owner. Do not flash
or manually write these generated binaries. No live instrumentation ran here.

## Evidence and boundaries

Private data: `local/recovery/2026-10-31-hdmi-discovery/`, including both exact
SCP SRAM snapshots, bounded read source, port caches, source/host baselines,
offline prototype, model result and checksums. The pread method was unsupported
(EFAULT); the established read-only mmap method succeeded. All mappings were
PROT_READ on an O_RDONLY descriptor. Reads were limited to known SCP SRAM,
validated MIPS DRAM, driver-established DDC mux and SCP reset-control words;
no forbidden ARM receiver MMIO, IPC calls, memory stores or settings changes.

[Result](RESULT.json), [host connectors](host-connectors-before.json),
[DRM query](host-drm-query.txt), [board state](board-before.json),
[offline prototype result and limitations](probe-offline-result.json).
No cable movement, HPD toggle, source-mode change, service restart, installation,
SCP/board reset, environment save or UART arming occurred. Root cause remains
unresolved; preserve the bad state for the live readback measurement.
