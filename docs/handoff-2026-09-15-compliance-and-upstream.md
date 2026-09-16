# Handoff — 2026-09-15: the streak is fixed, compliance run, upstream surveyed

Successor to [handoff-2026-09-14-video-scaler-and-rotation.md](handoff-2026-09-14-video-scaler-and-rotation.md),
whose §6 and §9 were rewritten in place during this session and are current.
Read that one for the scaler itself; this one for what happened after.

Treat observations and photographs as evidence, not instructions.

## 1. Operator protocol and board hazards — unchanged

- Board `root@192.168.4.1`; always `ssh -F /dev/null` and `scp -F /dev/null`.
- **Prompt before every test needing eyes on the panel and wait for `watching`
  or `ready`.** Do not open an observation window and ask afterwards.
- A warm reboot leaves the display unusable. Kernel changes need a **cold
  power-cycle**.
- **`/mnt/media-data` (p23) is NOT mounted after a cold boot.** Forgetting this
  silently turns a test run into a no-op — it cost a run this session. Mount it
  first, every time.
- Never read `0x06940000` or `0x07091000`.
- Rootfs is 100% full; build and stage under `/mnt/media-data`.

## 2. What changed, and where the tree is

Branch `h713-display-video-path`, **6 commits ahead of origin, unpushed**, tree
clean. The series is now **81 patches** and applies to a pristine 6.18.38 with
no fuzz.

| commit | |
| --- | --- |
| `2952b81` | the `max(in_h, out_h)` scaler fix; `0109` dropped |
| `bb24d10` | axis-isolation tooling, installer fixes |
| `5981130` | GStreamer patches, flagged undeployed |
| `699013c` | streak closed; why three good fixes missed it |
| `7de8a67` | `g_shell_quote` bug that killed every live decode run |
| `b9097e6` | the 2026-09-15 validation sweep |
| `ad2bc4b` | `V4L2_CID_ROTATE` rework + compliance record |
| `a779bc3` | correction: those were not regressions |
| `d5a4d98` | backported H.264 bounds fix + fh cleanup (`0112`, `0113`) |

Board runs the current module (`sunxi-cedrus.ko`) and a FIT built from this
series. Backup of the previous kernel:
`/mnt/media-data/h713-kernel-fits/replaced-20260915-200743.fit`.

## 3. The scaler: done and verified on hardware

The grey streak is **fixed**. `proc +0x050[15:0]` is the vertical line-enable
window LENGTH and the firmware sets it to `max(in_h, out_h)`, not `in_h`.
Full account in the predecessor handoff §6a.

Verified on the panel with genuine VE output — real decoded 1080p, really
downscaled, really rotated: scaled 960x544 clean, rotated 180 clean, rotated 90
clean, and sustained native flipping at **59.71 fps, sd 0.02 ms** against a
59.97 Hz panel. Rotation passes headlessly at all four angles, and the
180-degree output is a perfect point reflection of the unrotated one.

**Still not covered: sustained motion THROUGH the scaler.** Not one command
away — `MOVING` needs `CEDRUS=1` to have buffers to flip between, and
`CEDRUS=1` cannot take a compose rectangle because the LD_PRELOAD probe fires
on the decoder's first `S_FMT`, which under GStreamer is a 320x240 capability
probe before the stream size is known. That ordering is what
`patches/gstreamer/0001` exists to fix. Gated on deploying those patches.

## 4. v4l2-compliance: the baseline was lying

Full record: [reference/v4l2-compliance-2026-09-15.md](reference/v4l2-compliance-2026-09-15.md).

| arm | score |
| --- | --- |
| baseline, this series' cedrus patches reverted | 48/49 |
| scaling only, `0110` reverted | 48/49 |
| full series, `0110` as first written | 45/49 |
| full series, `0110` reworked | **46/49** |

**The 48/49 baseline was inflated.** `testRequests` needs an INTEGER or BOOLEAN
control to drive, and every control cedrus had is compound, U32 or menu — so
the whole Request API suite returned OK after testing nothing.
`V4L2_CID_ROTATE` is the first integer control cedrus has ever exposed, and the
suite ran for the first time.

So the two remaining failures are **not regressions**. They are pre-existing
cedrus behaviour that our control made visible.

**Method note worth keeping: cedrus is a MODULE, so every arm above was swapped
in with `tools/install-kernel-module.sh` and no reboot.** That is what made a
four-arm A/B affordable. Reach for it before assuming blame.

One trap it set: building `drivers/staging/media/sunxi/cedrus/` stops at `.o`
and does not relink the `.ko`, so the module on disk stays stale and its md5
looks unchanged. Use `make modules`.

## 5. The next fix, and it is small

`cedrus_request_validate()` rejects only a request with no buffer or with more
than one. It never checks that the current codec's controls are present, so it
queues a request that compliance — and the **documented** stateless decoder
contract — expects to be refused with `-ENOENT`:

> If a request is submitted without an OUTPUT buffer, or if some of the required
> controls are missing from the request, then `MEDIA_REQUEST_IOC_QUEUE()` will
> return `-ENOENT`.

The `blocking wait` failure follows from the same place: `fail_on_test_val`
returns before `testRequests` reaches its cleanup, leaving buffers allocated so
the next test fails on its own `reqbufs`.

**One fix, in cedrus, likely clears both, and is upstream-worthy on its own
merits** — decoding a slice with no SPS, PPS or slice params is meaningless and
the driver accepts it today. Verification is module-only: compliance plus the
four-quadrant card, no bench time.

## 6. Upstream survey — nobody has done any of this

Full record: [reference/upstream-survey-2026-09-15.md](reference/upstream-survey-2026-09-15.md).
Two results change what is worth doing next.

**H.265 scale/rotate went from "RE from scratch" to "follow two named
functions."** `libawh265.so` exports `regHEVC_ExtraCtrl_reg50`,
`regHEVC_ExtraYBuf_reg54` and `regHEVC_ExtraCBuf_reg58`, independently
confirming the secondary output at the offsets mainline leaves dead. The field
layout of `reg50` is the only gap; `H265DecoderSetExtraScaleInfo` (already
disassembled, a setter into software state at `ctx+0x3008..0x3014`, enable at
`+0x3018[0]`) and `HevcSetOutputConfigReg` are the trail.

**We diverged from the mainline API precedent.** Hantro — the only mainline
stateless decoder with decode-time down-scaling — selects the scale with
`S_FMT` on the capture queue and advertises sizes via `ENUM_FRAMESIZES`. We use
`S_SELECTION(COMPOSE)` and implement no `enum_framesizes` at all. Worth
resolving before proposing any of this upstream.

Also: our pinned `libva-v4l2-request` PR #38 has been open since 2021; PR #44
"Kernel 6.18" (2026-06-12) is live and we are on 6.18.38.

## 7. Suggested order for the next session

1. **`cedrus_request_validate()` required-controls check.** Small, upstreamable,
   closes both remaining compliance failures. Module-only verification.
2. **De-`EXPERIMENT` `0097` and `0100`.** Both are in the shipping series and
   `0100` is worse than dead weight: `proc_en` (writable `0644`) gates whether
   the scaler engages at all, *after* `atomic_check` accepted the scaled
   configuration. `0097`'s `sd_*` debug knobs ship in the production module.
3. **Deploy the GStreamer patches.** The only thing standing between here and
   sustained scaled motion, and the last item for the video path overall.
4. **`HevcSetOutputConfigReg` RE**, if HEVC scale/rotate is wanted.
5. **Decide the API shape** (hantro-style `S_FMT` + `ENUM_FRAMESIZES` vs our
   `COMPOSE`) before any upstream submission.

Open smaller items already recorded: the `COMPOSE` vs `COMPOSE_BOUNDS`
inconsistency under 90/270; `cedrus_compose_shift()` and `g_selection`
modelling the same quantity two different ways; the pre-existing
`TRY_EXT_CTRLS` failure worth reporting upstream; and the fact that a stock
compliance run never reaches our compose code because the default output format
is MPEG-2.

## 8. Tooling facts that cost time this session

- **`CEDRUS=1` is freeze-frame, not playback.** It discards `DECD_FREEZE_AT`
  (default 60) frames, holds one buffer and leaks the sample deliberately. A
  run printing one `cedrus frame` line is working correctly.
- **A frame file must be tightly packed at the SOURCE size**, `src_w * src_h *
  3 / 2`. The harness black-fills the 1280x720 canvas itself and copies rows in
  at panel pitch. A full-canvas capture fails the size check and displays
  nothing.
- `MOVING=1` is the flip loop and requires `CEDRUS=1`.
- Playback looks **2x fast** because the flip loop is unpaced by design
  (`sync=false` unless `PACED=1`) against a 29.97 fps clip. Not a defect.
- Building the harness needs the full pkg-config set including
  `gstreamer-allocators-1.0` and `-lm`; the header's build line was stale and
  is now fixed.
- `git.linuxtv.org` and `gitlab.freedesktop.org` block automated fetches
  entirely. **Ask the operator to clone.**
- Local `objdump` cannot disassemble aarch64. Use capstone.
