# AFBD completion-phase evidence, 2026-09-26

This directory records bounded board-B tests of the AFBD current-pair window
at `0x05600320/0x05600324`. The temporary U-Boot proper image supplied the
guarded `cap-vde` completion trace and had SHA-256
`c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7`.
The tested V4L2 module had SHA-256
`d91a6705379b9bab05838b4d7ea155de719ce414863b24f4b240ef627ceb343b`.

## Read-only telemetry

The first static run left AFBD as telemetry only. Its sparse-verification
snapshot recorded 418 samples, zero invalid pairs, and phase bins 12/3/404;
the full-verification snapshot recorded 160 samples, zero invalid pairs, and
bins 2/2/157. Module-parameter snapshots are not atomic, so a sample total can
differ from the sum of the three bins by one.

A 120-frame moving-pattern run then recorded 1,843 samples, zero invalid
pairs, and bins 23/8/1,812: phase 2 held 98.3% of observations. All 120 frames
had valid band and stripe markers. The full-verification driver produced 162,
delivered 121 to the V4L2 queue, overwrote 41 while its diagnostic double-read
ran, and rejected none. These results establish a strong phase signal, but the
minor bins show why one AFBD read must not select a buffer.

## AFBD-only cold static startup

The bridge was changed to require at least 10 matching samples in a window of
12 consecutive valid, single-step completion events. An invalid pair, event
gap, mode change, or completion timeout clears the vote window. A fixed or
stale pair produces a rotating 4/4/4 distribution and therefore cannot pass.

For the decisive trial, the static source was allowed to settle before the
module loaded and ring-content phase learning was disabled with
`phase_from_hash=0`. Both the sparse and full module loads independently
learned offset 2 from unanimous AFBD votes:

```text
learned completion phase offset=2 from AFBD votes 0/0/12
```

Five sparse and three full-verification stream opens each delivered complete
frames with zero unstable copies and zero rejections. Every eight-frame output
contained eight distinct full-frame hashes. The sparse snapshot recorded 217
samples, zero invalid pairs, and bins 4/3/211; the full snapshot recorded 161
samples, zero invalid pairs, and bins 2/2/158. The bounded EDID/HPD operation
returned the source connector to disconnected and disabled.

The default configuration, with AFBD bootstrap and hash fallback both enabled,
then captured another 120-frame moving pattern. It had zero band or stripe
mismatches, 116 sequential steps, two duplicates, and one skipped step.

## Three disconnect/reconnect cycles

`run-reconnect-trial.py` kept one sparse-verification module instance loaded
with `phase_from_hash=0` across three bounded EDID/HPD cycles. After each
disconnect it waited four seconds, longer than the three-second no-frame
timeout, so the next connection had to establish a fresh AFBD phase. The three
offset-2 votes were 1/1/10, 0/0/12, and 0/1/11.

Each cycle captured 30 deterministic motion frames. All 90 frames had valid
band and stripe markers, all 87 transitions were sequential, and there were no
duplicates or skips. Each driver stream produced and copied 31 completion
events, delivered 31 buffers, and reported zero overwrites, unstable copies,
or rejections. The source connector returned to disconnected and disabled
after every cycle. This passes a short repeated reconnect test; it is not a
long-duration endurance result.

## Final restoration

Only the established 1,798 U-Boot-proper sectors were modified for the test.
Afterward their complete readback matched the original SHA-256
`47ebcfa6dbfd646b2eab83fc1e5206086a2a1226cb5d840512051cbbf6e9e95d`.
The untouched 64-sector SPL readback remained
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
The normal image booted, the established source-3 sequence returned the MIPS
to ALIVE with trace canaries verified, and the pre-completion V4L2 module
rebuilt from commit `9cfef0e` was restored with full verification. Its SHA-256
is `428870353d83dd2380b0b96616bf5e6bada218458236651ac8a8483737717a66`.
The SCP probe is absent and the source connector is disconnected and disabled.

Raw 73 MiB NV16 captures remain outside Git. The retained JSON files contain
the frame-integrity analyses, static restart hashes, and reconnect summaries.
