# Initial well0nez follow-ups integrated — November 14, 2026

The active kernel series now includes **0191–0197**: VP9 stack reduction,
Linux USB HCI SIDDQ clearing, main-PIO interrupt indexing and DT correction,
and HEVC core/reference/collocated-reference validation. Authorship and pinned source links are retained in each patch.

**Hardware update:** the candidate has now been installed on the DDR3 bench
and tested. See [hardware results](hardware.md) for the seven bit-exact decode
vectors, malformed-control recovery, PH17 edges, cold USB enumeration and
verified restoration of the temporary boot setting. The initial offline
verification record below is retained as build provenance.

## Changes and attribution

| Our patch | Origin in well0nez's pinned tree | Adaptation |
| --- | --- | --- |
| 0191 | 0317, well0nez | Preserve the original 15-byte tx/skip save/restore implementation |
| 0192 | 0005a, well0nez | Add author metadata to the original plain unified patch |
| 0193 | 0143, well0nez | Keep the parent-IRQ fix; omit the separate comment hunk already corrected by our 0171 |
| 0194 | 0144, well0nez | Preserve the seven-parent-IRQ DT change, after 0193 |
| 0195 | 0330; upstream author Pengpeng Hou | Regenerate contexts for our pinned 6.18.38; retain upstream semantics and authorship/trailers |
| 0196 | 0309, well0nez | Preserve reference-index, capture-buffer and MV-allocation checks |
| 0197 | 0316, well0nez | Preserve temporal-MVP collocated-reference validation, after 0196 |

Each patch has a `From:` author and a `Link:` to the exact file in
[`149f51d0df24c45b12674c81aab128b1fc8f5d4b`](https://github.com/well0nez/allwinner-h713-linux/tree/149f51d0df24c45b12674c81aab128b1fc8f5d4b).
0195 also identifies upstream
[`afbe4bc252d9`](https://github.com/torvalds/linux/commit/afbe4bc252d90a6f8fad869b06d5430f615f22f9).
Mail-format metadata was normalized; code changes remain attributable to
their original authors. No new sign-off was invented.

The V4L2 core still accepts missing-reference sentinels such as `0xff` when
active counts are valid. Cedrus itself refuses a job whose active references
are unsafe, before enabling the HEVC engine. This deliberately prevents an
out-of-bounds access or missing MV allocation instead of attempting hardware
concealment with an invalid slot. Allocated MV storage does not prove an
earlier decode succeeded; this change does not add decoded-picture tracking.

## Verification

- All seven patches apply sequentially with **zero context fuzz** to the
  reconstructed pre-integration source files. All seven resulting files
  match the final production prepared tree byte for byte.
- The default DDR3 configuration built **Image, modules, both board DTBs and
  FIT** successfully. Its source behavior is the same as the final patches;
  subsequent changes normalized patch mail headers only.
- The **final production-profile build also passed**: Image, modules, both
  board DTBs and `h713-kernel-production.fit`. The FIT is 7,613,576 bytes.
- Source-bound host tests compile the actual HEVC/VP9 helpers against the
  kernel's own UAPI types with **AddressSanitizer and UndefinedBehaviorSanitizer**.
  The five test groups cover all 65,536 B-slice active-count pairs, P-slice
  count boundaries, sentinel policy, invalid indices, absent buffers and MV
  allocations, I/P/B collocated-reference boundaries, and VP9 preservation
  across 512 probability contexts. Both GPIO DTBs and USB configuration are
  checked. Four intentionally broken variants must fail; all four are caught.
- Checkpatch reports **zero errors** across the seven patches. Its three
  remaining warnings are commit-ID lookups for a contributor U-Boot commit
  and the two upstream Linux references, unavailable in this workspace's
  superproject history. Original attribution references were retained.
- The default build's only warning is the existing host
  `scripts/sorttable.c` unused `long_size`; no VP9 stack-size warning remains.

Final patch/source/config/artifact hashes are recorded in the
[validation manifest](integration-validation.json); the
[host-test output](integration-host-tests.txt) records the successful run
against the final production tree.

The build uses the recorded production host compiler, clang/LLD **23.1.4**,
and the project's Rust-free kernel probe setting. Outputs live under
`build/well0nez-integration-20261114`, isolated from the usual `build/out`.

Reproduce the production build and checks:

```sh
H713_BUILD_DIR="$PWD/build/well0nez-integration-20261114" \
  KERNEL_CONFIG=production JOBS=24 tools/build/build.sh kernel

H713_BUILD_DIR="$PWD/build/well0nez-integration-20261114" \
  KERNEL_CONFIG=production tools/build/build.sh kernel-tree

python3 tools/video/test-kernel-followups.py --kernel <printed-kernel-tree> -v
```

## Remaining hardware qualification

The original offline-stage qualification list was:

1. Bit-exact valid VP9 and HEVC regression vectors on the candidate kernel;
   damaged HEVC requests followed by a valid decode, checking errors are
   returned without hangs or unexpected IOMMU accesses.
2. USB host enumeration from a cold boot without U-Boot `usb start`, then
   verify the wired host ports and OTG/gadget routing separately.
3. Main-PIO IRQ delivery beyond the missing PE bank, especially PH17, plus
   R_PIO power-key and SDIO-host-wake regression checks on the intended board.

The projector DTB compiling is not LPDDR3 hardware validation. eMMC recovery,
mixed-codec resets, AV1 coordination, mailbox IRQs and the unresolved doorbell
pulse experiment are outside this integration.

The [subsequent hardware record](hardware.md) identifies the tests completed
and the remaining limits; it supersedes the original not-installed state.
