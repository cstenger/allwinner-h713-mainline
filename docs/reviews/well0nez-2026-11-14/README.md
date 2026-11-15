# Useful changes from well0nez — November 14, 2026

There is useful work to bring back, especially decoder error handling,
mixed-codec isolation, eMMC recovery, and Linux USB cold-start independence.
Their projector application, installer, and board profiles are useful longer
term, but depend on a different integration model. This review makes no
production code changes and installs nothing on hardware.

**Subsequent integration:** the user selected the initial fixes, now carried
as kernel patches 0191–0197. See [the integration record](integration.md)
for attribution, adaptations and verification. The analysis below records
the pre-integration review; its candidate inventory is not a claim that the
selected fixes are still absent locally.

## Sources and overlap

Reviewed [well0nez/main at
149f51d0](https://github.com/well0nez/allwinner-h713-linux/tree/149f51d0df24c45b12674c81aab128b1fc8f5d4b),
whose tip is November 13. Cloned without submodules into the ignored
`local/well0nez-review-20261114` directory, separate from our original source
snapshot. Retained that checkout so individual candidates can be inspected
and adapted against this exact revision. Our comparison base is
`10af96af825dfef18b51f22b949f2f204ca9047f`; pre-existing local edits were not
changed. Their `hy300-pro-ab` branch last changed September 22, is 1,133
commits behind main with two branch-only commits, and is not newer work.

Their current series contains **373 active kernel entries**, versus our
**152**. Their PROVENANCE table still says 351, so the count here is from
the actual series file, excluding blank lines and comments. Of those 373:

- **31** patch files are byte-identical to an entry in our active series.
- **81** have the same ordered target paths and added/removed lines as an
  entry in our active series, ignoring patch preambles, hunk positions and
  unchanged context. The 31 are included in this comparison where applicable.
- A nonmatch does not establish new authorship or new behavior: adaptations,
  combined patches, retired entries, and equivalent implementations also
  produce nonmatches. Patch numbering is independent between the trees.

[Full overlap table](kernel-overlap.tsv). This checks active entries, not
every file that happens to remain on disk.

They explicitly credit the subtree import of our tree at `8860991`, our
display branch, Cedrus/VP9 work, AV1 work, GPU fixes, and subsequent decoder
hardening in [their provenance
record](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/PROVENANCE.md).
For example, their 0271–0296 largely correspond to our scaler/Cedrus/VP9
series; 0300–0304 include our AV1 work; 0322–0324 contain our bounded H.264
wait, capture-buffer limit, and HEVC DPB clearing. Those are not new fixes to
import a second time. Some earlier shared patches originated with well0nez
and came through our tree; equality alone cannot assign their authorship to
us.

Their provenance record also explains that they removed our unlicensed
scripts/docs from their working tree and rewrote needed tools. Their LICENSE
sets GPL-2.0 as the default for their code, with per-file/component exceptions;
their docs use CC BY-SA 4.0. Preserve each patch's actual author and origin,
including upstream authors, when adapting it. Our own top-level licensing
remains a separate maintainer decision.

## Candidates to bring back first

Links below are pinned to the reviewed revision. Patch application was checked
only on isolated source copies, not our active series or cached build trees.

| Priority | Their change | Benefit and fit in our tree | Required validation |
| --- | --- | --- | --- |
| First | [0330: HEVC active-reference count validation](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0330-media-v4l2-ctrls-validate-hevc-active-reference-counts.patch) | Our pinned V4L2 core leaves the HEVC slice-control validation case empty. This is Pengpeng Hou's upstream change, not an original well0nez patch; independently checked [upstream afbe4bc](https://github.com/torvalds/linux/commit/afbe4bc252d90a6f8fad869b06d5430f615f22f9). Their patch has newer HEVC-extension context absent in 6.18.38, so adapt the small change rather than applying it unchanged. | Boundary counts on P/B slices, valid-stream regression, and driver error propagation. Preserve upstream treatment of missing-reference sentinel values. |
| First | [0309: HEVC reference validation](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0309-media-cedrus-an-h265-reference-must-be-a-picture-decoded-here.patch) and [0316: collocated-reference bounds](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0316-media-cedrus-h265-the-collocated-picture-must-be-in-the-active-reference-list.patch) | Our driver indexes `dpb[ref_idx_l0[i]]` without these checks and sends `collocated_ref_idx` directly to hardware. 0309 applies with zero fuzz; 0316 applies with zero fuzz after 0309. Their approach refuses the whole job for a missing reference; the patch itself notes upstream prefers skipping invalid references, so choose that policy explicitly during adaptation. | Malformed/missing references, MV-buffer lifetime, P/B and temporal-MVP cases, damaged streams and subsequent valid decode. |
| First | [0317: VP9 small saved-probability struct](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0317-media-cedrus-vp9-keep-only-the-tx-and-skip-probabilities-across-load-probs.patch) | Our VP9 finish path still saves a full `v4l2_vp9_frame_context` to retain only tx/skip fields. Replace it with the 15-byte subset. Applies with zero fuzz and is the smallest independent candidate. | Build/frame-size diagnostics and bit-exact intra/inter VP9 adaptation tests. |
| First | [0005a: Linux HCI SIDDQ clearing](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0005a-phy-sun4i-usb-h713-clear-siddq-on-the-hci-phys.patch) | Our kernel H713 PHY config lacks `hci_phy_ctl_clear`; this removes dependence on U-Boot having initialized USB host. Applies with zero fuzz. Their report measured missing devices when bootloader `usb start` was omitted. | Cold boot without bootloader USB initialization; enumerate each wired host port and check gadget routing. |
| First | [0143: PIO parent IRQ lookup](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0143-pinctrl-sunxi-index-the-bank-interrupts-by-irq-bank-not-by-hardware-bank.patch) and [0144: seven DT IRQs](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0144-arm64-dts-h713-the-pio-has-seven-bank-interrupts-not-nine.patch) | Source-derived mismatch reproduced in the earlier issue investigation. The actual lookup hunk applies with zero fuzz; 0143's separate comment hunk needs adaptation because our pin-mux work differs. 0144 applies with zero fuzz. Fix lookup before trimming the list. | Main-PIO interrupts beyond PE, especially PH17; regression of R_PIO consumers. |
| Next | [0313: eMMC read threshold](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0313-mmc-sunxi-the-emmc-host-starts-a-read-block-only-when-the-fifo-has-room-for-it.patch) and [0312: CMD18 recovery](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0312-mmc-sunxi-a-failed-multi-block-read-re-initialises-the-controller-before-the-stop.patch) | Both apply individually with zero fuzz. Our SDIO CMD53 recovery is not CMD18 recovery, and our threshold helper is v5p3x/SDIO-specific. They report FIFO saturation and read CRC errors under combined video/GPU/storage load, with threshold improvement and recovery after induced errors. | HY200 HS400 reads under combined load, timing/reset restoration, runtime PM and ordinary I/O. Review SoC scope and recovery error returns before adoption: 0312's helper ignores reset/init/clock errors, and 0313 selects all non-v5p3x hosts advertising HS400 rather than an H713-only compatible. |
| Next, coupled work | [0298: reset on Cedrus codec switch](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0298-media-cedrus-a-job-of-another-codec-starts-from-a-reset-engine.patch), plus 0305–0308 reset/IOMMU coordination | 0298 applies with zero fuzz and addresses VP9 leaving HEVC registers dirty; their documented paired-stream results make this worth reproducing here. **Do not land it alone:** resetting the shared VE bus can interrupt AV1. Their guard covers first register writes through IRQ/done/timeout, and recovery resets faulted IOMMU client ports only with the engine stopped. | Mixed VP9/HEVC first, then AV1 concurrently, timeouts, late IRQs and malformed streams. Their own 0310 disables AV1: their recovery/guard is not proof that all workloads coexist. Audit the guard's forced pulse after a three-second wait and whether reset APIs can sleep under its spinlock. |

The sensible small first implementation is VP9 stack reduction plus the Linux
USB/PIO fixes, alongside an upstream-based HEVC validation series. Storage
and shared-reset recovery deserve separate changes and evidence.

## CPU_COMM and firmware integration worth studying

Their 0014b/0014c and 0024d describe all msgbox banks while requesting only the
ARM-owned inbox line. Their 0014e corrects two register-whitelist entries
from msgbox addresses to hardware-spinlock status addresses. Their 0014f
checks the eight-word TX FIFO before writing and returns `-EBUSY` rather than
silently losing a word. Our sender currently has no equivalent depth check.

These are useful focused adaptations, not a reason to replace our whole
CPU_COMM patch with theirs. In particular, carry send errors through CALL and
ACK/RETURN_ACK paths and reconcile queue publication/wait cleanup; a count
check alone does not define recovery from an already-published message.

Their latest 0014f also explicitly retracts certainty about the TX_IRQ_EN
pulse: vendor code uses TX enable as a level managed by an ISR, and their
older pulse experiment was confounded by a parked MIPS. They retain the pulse
pending a device test. Our emulator experiment establishes the **message
encoding**, not the electrical interrupt trigger mechanism. Retain our tested
transport while designing a controlled pulse/no-pulse test; do not repeat the
edge-trigger claim as settled fact.

Their 0326 checks firmware allocator break position before using fixed shared
scratch pages. That is a useful ownership principle for our firmware tooling,
but their exact offsets and driver lifecycle do not map automatically to our
reserved buffers. Our HDMI path uses standalone modules and host-assisted
MIPS tooling; theirs integrates a different in-kernel HDMI/ARISC driver stack.

The EDID fragment-completion fixes (0091e/0091f), timing-table parsing and
colour metadata (0136h onward), and DDC port-table byte-order fix (0336) are
valuable references for additional sources and boards. Our present EDID/DDC
owner has a different implementation; use their tests and firmware findings
as inputs rather than running both owners on the same hardware. Port 1 on
the HY320 exposed defects a port-0-only test can miss.

## Features for a later projector product

| Area | Useful code to examine | Integration boundary |
| --- | --- | --- |
| Board/firmware identification | `boards/`, `installer/h713/profiles/`, `installer/h713/identify.py`, board checks | Per-board DRAM, firmware hashes, panel parameters and variants; explicit verified/test/profile status. Reuse facts and schema ideas for our board manifest. A same-size eMMC is not the same board. Our existing install packet already pins exact device/storage identity; this complements future multi-board support. |
| Install/update preservation | `installer/h713/install.py`, `installer/tests/test_release_board.py`, settings/env preservation tests | They refuse known cross-board images and preserve settings, SSH host identity and Bluetooth state. Their image/GPT/environment layout differs from our split-layout migration: do not substitute their installer or sector addresses for ours. |
| Keystone/display ownership | `userspace/h713-warp/`, `userspace/libh713geom/`, `userspace/h713-tv/` | More complete than our shader/player keystone path: GPU warp, dmabuf clients, source handoff, remote-driven controls. It assumes h713-tv owns DRM and can replace the capture ring with a Wayland client. Adapt as a feature project, not a daemon to drop into our current desktop/DRM ownership. |
| Autofocus and motor limits | `userspace/h713-autofocus/`, `userspace/h713-focus/`, kernel motor patches | Camera sharpness metric, dry-run frame replay, bounded search, end-switch handling, per-board motor range. Useful when working on a board with camera and motor; our bench does not establish those peripherals. Their known issues still include a lower-stop recovery problem. |
| Launcher/settings/remote | `userspace/h713-keys/`, `userspace/h713-osd/`, `userspace/h713-settings/` | A substantial remote-first projector UI with HDMI/Kodi/desktop switching. Worth a separate user-experience decision; dependent on their controller/warp protocols and services. |
| Thermal/fan and lamp control | 0332/0333, per-board lamp and volume tables | Separate board configuration from driver policy, orderly thermal shutdown and fan-aware lamp modes. Do not use another board's thresholds or GPIOs as HY200 defaults. |

## What to leave behind for now

- Disabling AV1 (0310), their conditional VE clock policy (0315), and display
  IOMMU differences are tradeoffs in their integration, not improvements to
  apply wholesale to our validated decoder/display stack.
- Their RTC crystal fix 0320 addresses the same class of issue as our 0176;
  importing a second RTC implementation would duplicate existing work.
- New board DTs, IR mappings and panel mix-control words need matching
  hardware/firmware. Their LPDDR3 board remains profile-only; it supplies no
  hardware validation of our projector SPL.
- Their release does not offer standby, and their known issues include
  unvalidated paths, overlay phase problems and partial newer-board Wi-Fi.
  Do not infer reliability from the presence of a release image or a larger
  patch count.
- Retained old/withdrawn files are not necessarily active fixes. Their NSI
  driver is withdrawn; ours is already disabled and absent from the active
  series.

## Validation performed in this review

Reconstructed the selected kernel files from our pinned
`build/cache/linux-6.18.38.tar.xz` and current active series into
`build/well0nez-review-20261114/patch-fit`, using the project's normal patch
context-fuzz behavior for our own series. Existing patch 0118 needs context
fuzz in this reconstruction; this was not a new upstream candidate failure.
Then checked candidate application with `patch --dry-run --batch --fuzz=0`.
The [raw results](patch-fit.json) include the independent checks and the
0316-after-0309 dependency check. Offsets are allowed; context fuzz is not.

Seven independent candidate patches apply with zero fuzz: 0005a, 0144, 0298,
0309, 0312, 0313, 0317. 0316 also passes with its 0309 prerequisite. 0143's
functional hunk passes; its separate pinctrl comment differs. 0330 requires
adapting newer-kernel surrounding context. These checks establish mechanical
fit only: no kernel builds, third-party test suites, device operations or
performance measurements were run. Candidate behavior and reported board
results were reviewed in patch bodies, code, and their known-issues records.

The prior [issue investigation](../../github-issue-investigation-2026-11-14.md)
and [draft replies](../../github-replies-2026-11-14.md) have been corrected for
the newly identified U-Boot PMU-bit-0 equivalent and the unresolved pulse
mechanism. The response archive records publication separately.
