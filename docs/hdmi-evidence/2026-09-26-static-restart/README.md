# Static-source restart evidence, 2026-09-26

This directory records bounded board-B tests of the follow-on completion-phase
logic against Linux 6.18.38 `#1 SMP Thu Sep 24 01:45:24 PDT 2026`. The temporary
U-Boot proper candidate was the previously verified trace image, SHA-256
`c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7`.
The tested module SHA-256 was
`fbea78fd1cdfac212c61bac3fdea75b506caaf7c5e7bbeea9efeadf1a8537db9`.

## Phase correction

The first static-source attempt tested the stronger but incorrect assumption
`completed_pair = cap_vde % 3`. It observed 359 completion events and rejected
all 359 because the changed pair did not match that absolute phase. This proves
that the zero offset observed in the September 25 corpus was specific to that
boot, not a permanent ABI. The bounded signal cleanup still completed. Its log
is under `initial-failure/`.

The corrected bridge runs a phase monitor from module load. On the first
unambiguous completed-pair change it learns
`completed_pair = (cap_vde + boot_phase_offset) % 3`, retains that offset across
stream close/open, and invalidates it after a three-second completion timeout or
a mode change. On this boot it learned offset 2. A later disconnect/reconnect
timed out the old phase and independently learned offset 2 again.

## Visually static source and stream reopen

`static-pass/` contains a 30-second trial presenting one fullscreen PNG. Five
sparse-verification and three full-verification captures repeatedly opened and
closed `/dev/video1`; every file contained eight complete frames. All eight
driver stream summaries had zero unstable copies and zero rejected frames:

- each sparse stream delivered 9 of 9 produced events with zero overwrites;
- each full stream delivered 9 frames from 11 produced events, with 2 expected
  diagnostic-copy overwrites;
- HPD, EDID state, and DDC ownership restored at the end of the bounded window.

The source picture was visually static, but all captured full-frame hashes were
distinct. The receiver or source path therefore changes low-level bytes even
for this fixed picture. This run proves repeated stream reopen using a retained
phase; it is not proof of cold module loading after a byte-identical source has
already settled. That case still needs a firmware producer index or equivalent
permanent completion ABI.

## Moving integrity regression

`motion-regression/` contains a new 120-frame buffered-read run after another
disconnect/reconnect. All 120 frames contained the deterministic pattern, with
zero band mismatches, zero stripe mismatches, zero skipped IDs, one duplicate
source ID, and zero driver rejections or unstable copies. The uncommitted raw
capture stayed in `/tmp`; its SHA-256 was
`d5380392607ea8ef42b85debd3cd030fd229d0c8ebde078345395676ae5490d5`.

## Final restoration

After the tests, U-Boot proper was restored and read back as the known original
SHA-256
`47ebcfa6dbfd646b2eab83fc1e5206086a2a1226cb5d840512051cbbf6e9e95d`.
The untouched SPL remained
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
The board was rebooted, the established source-3 sequence restored the display
MIPS to ALIVE with trace canaries and transition-complete state verified, and
the prior V4L2 module
`e7e80d1511e8999f01d75211b3722592d4644d2b0228b4bac9cdfef88dc25a39`
was reloaded with full verification. The SCP probe was absent and the source
GPU connector was disconnected and disabled.
