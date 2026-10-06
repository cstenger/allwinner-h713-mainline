# WP5: the hardware mirror (installation mode): plan (2026-10-05)

> **Status 2026-10-06: Phase 1 DONE. Every prediction held on the glass**
> ([reference/mirror-phase1-2026-10-06.md](reference/mirror-phase1-2026-10-06.md)).
> - Video plane: h, v, hv, an asymmetric placement and a non-16 height all behaved as predicted. The bars follow the mirror, and no padding showed.
> - Console route: V = OSD control bit 3 (pixel-exact); H = the shared panel bit, but it **loses one row** (panel histogram, `panel-signature.sh`), fixed by **program window `lvds+0x0c0` y 22 → 23** (histogram bit-identical). OSD bit 2 is dead.
> - **Next: Phase 2 (kernel, 0166+).**
>
> **Phase 0 DONE (2026-10-06).**
> - The model in `letterbox-recipe.py` reproduces all four stock installation modes register for register. Four mutations are each caught.
> - The vblender overlay y follows vde (firmware), and proc instances 1–3 follow instance 0 in hardware (board, read-only).
> - The H mirror's `−1` was mislabelled "interlaced" in the letterbox reference; corrected.
> - Record: [reference/mirror-recipe-2026-10-06.md](reference/mirror-recipe-2026-10-06.md). **Next: Phase 1**, one operator session.
>
> Since this plan was written, letterbox Phases 2–5 have landed (kernel 0161–0165, all hardware-verified), so Phase 2 below builds on 0165 and its patches number from 0166.

## Context

A projector mounted on the ceiling, or behind a rear-projection screen, needs its whole picture mirrored horizontally, vertically or both.
- **Stock does this in display hardware.** `com.htc.magcubicos` → Installation mode → `PANEL_CONFIG_MIRROR` → the MIPS window layer. Everything else in stock (scaling, letterbox, rotation, keystone) is on the GPU.
- **Our stack:**
  - parks the MIPS, so the kernel driver must write the registers itself;
  - has no mirror anywhere: there is no DRM `rotation` property;
  - the only earlier rotation work was decoder-side. Kernel 0110 added the H.264 `V4L2_CID_ROTATE` and 0120 removed it again.
- `gpu-fallback-plan.md:410` lists **WP5** as "REFLECT_X/REFLECT_Y on the DRM planes, from the recipe in the stock reference". `letterbox-plan.md:309` asks letterbox to keep placement in panel coordinates so the mirror can map it.

**Intended outcome:**
- One installation setting (mode 0–3) mirrors everything: the console, the GPU path and the kmssink plane routes, with no client changes and no GPU cost.
- The standard DRM `rotation` property sits on both planes, on top of the setting.

**Decisions (user, 2026-10-05):**
- **API:** an installation setting **plus** a plane `rotation` property (REFLECT_X, REFLECT_Y, ROTATE_180), combined by XOR.
- **Setting:** a runtime sysfs attribute that re-commits immediately, with no reboot (warm reboots kill this display). A module parameter gives the boot default, and the rootfs persists it through tmpfiles.d, like the schedutil setting (`tools/rootfs/customize.sh:592`).

## The recipe: established facts (do not re-derive)

These come from three read-only surveys (confirmed and extended by Phase 0) of the stock capture (`local/h713-lab/stock-capture-20261001/out/orient-*`, video playing at native 720p), `display.bin` disassembly and our driver.

| Fact | Source |
| --- | --- |
| **H mirror is one panel bit, `0x051c00a0[0]`**, written by `PanelWinNode::WriteReg` (fw `0x8b1a5c38`–`5c44`). Stock never sets an H bit on either AFBD channel. | orient-rear vs mode 0 (`1b-h264-1280x720-*`, `keystone-*`) |
| **H also moves the vertical timing one line earlier (vde 22 → 21).** The H flag feeds vde at fw `0x8b1a8928`. It moves exactly the four dy-REL fields 0161 already models by −1: comp `0x80c[31:16]` 0x14→0x13, `0x840[15:0]` 0x15→0x14, `0x858[15:0]` 0x15→0x14, and proc `+0x050[31:16]` 27→26. The proc change is the shift, not a flag. The elog's `m_border_overlay_win` y goes 22 → 21, so vblend `0x010/0x024[15:0]` (baseline `0x02D00016`) should follow; that was not captured. | dumps, elog, fw |
| **H changes nothing horizontally** (`0x804/808/844/85c`, proc `+044`), and the panel program window stays at (49, 22) (`PanelWinNode::CalcWindow` adds 1 back). | dumps, fw `0x8b1a546c` |
| **V flip is two bits, written by fw `0x8b1a43f0` inside the NR geometry group (0x800, inside the hold/release bracket):** AFBD `0x05600010[3:2]` = 2 (`0x03000013 → 0x0300001B`), and for source mode 2, comp `0x05000040[3]` = 0 (`0x02090208 → 0x02090200`). No address, stride or fetch-window change: AFBD flips internally. **Our native state is source mode 2 too** (`comp+030 = 0xC00`, `+040 = 0x02090208`). | dumps, fw |
| **V does not move the picture's position.** The NR output y is not mirrored. | fw |
| **H+V is the union of the two.** | orient-front-ceiling |
| **Don't write these.** They change but the firmware never writes them (status or readback): comp `0xa0c/aa8/aac`, DETN `0x050c0940/950/970`, route `0xe04/e08/e18`, panel `0x154/164/184/198/1a0/1b4`. `0x05040014` is noise. Proc instances 1–3 (`+0x150/250/350`) change too, but the firmware writes instance 0 only. | `block-map.py`, dumps |
| **Our planes take different routes.** The primary (console, GPU path) is the AFBD OSD channel `0x05600140` with selector `lvds+0x06c = 0x29000000`, and bypasses NR/proc. The video plane is source 0 → NR → proc → panel, selector `0x39000000`. The mux is exclusive. Stock runs everything through source 0, so **the RGB route's mirror is untested.** | `kms-display.md`, driver |
| **RGB-route V:** OSD control bit 3. Stock's `ge2d_dev.ko` `tgd_put_plane_info` clears [3:2] and sets bit 3 for V. U-Boot writes `mirror_mode` into `0x05600140[3:2]` (`external/u-boot/arch/arm/mach-sunxi/h713_mips.c:5052`). | |
| **RGB-route H: two candidates.** The panel bit (if it sits after the selector), or OSD bit 2 (U-Boot's field, never used by stock). | |
| **The letterbox driver's extension points** (0161, since extended by 0163–0165; re-read the 0165 tree before Phase 2): `struct h713_geom {w,h,dx,dy}`; `h713_lb_fields[]` with ABS/REL fields; `h713_lb_words()`; `h713_lb_snapshot()` (probe self-check); `h713_lb_program()` (bracket); `h713_geom_eq()`; video `atomic_check`/`atomic_update`; `h713_afbd_video_stop()`; `h713_afbd_set_source()` (writes `rgb_ctrl_active` every flip). The DT maps lvds `+0x100`, proc `+0x200` and vblend `+0x100`, so `0x0a0`, `0x050` and `0x010/0x024` are all reachable. | agent survey |

## How the setting and the plane property combine

Inputs: `inst` (mode 0–3: H = modes 1 and 3, V = modes 2 and 3), the plane rotation normalised by `drm_rotation_simplify()` (ROTATE_180 becomes REFLECT_X|REFLECT_Y), and the client's dst (x, y, w, h).

- The visible picture must be the whole-screen mirror (`inst`) of the client's composition, with the plane's own reflection applied inside its rect.
- **H** (the panel flips content *and* position): `hflip = inst_H ^ REFLECT_X`; `dx_hw = REFLECT_X ? 1280 − x − w : x`. Installation H needs no x compensation.
- **V** (AFBD flips content only): `vflip = inst_V ^ REFLECT_Y`; `dy_hw = inst_V ? 720 − y − h : y`.
- The bars (vblend borders) come from `dx_hw/dy_hw` and follow automatically. This assumes the vblender sits before the panel mirror; Phase 1 tests it.
- **The primary plane is always full-screen**, so only `hflip/vflip` apply to it.
- **Panel bit ownership:** whichever source owns the mux. The video plane writes it in its geometry program. `video_stop` hands it back to the primary's value after restoring RGB.

## Phase 0: desk work and read-only checks (no writes)

1. **Confirm two firmware details by disassembly** (`tools/mips/disasm.py`, `block-map.py`; MIPS address = ARM + `0xB5000000`):
   - the writer of vblend `0x010/0x024` and whether its y comes from vde (`WriteBorderOverlay` near `0x8b1a55d8`);
   - that proc instances 1–3 are never written (so we write instance 0 only).
2. **Extend `tools/display/letterbox-recipe.py`** with `hflip/vflip`:
   - dy-REL fields become `dy − hflip`;
   - add vblend `0x010/0x024[15:0]` as REL `−hflip`;
   - add panel `0x0a0[0] = hflip`, AFBD `0x010[3:2] = vflip ? 2 : 0`, comp `0x040[3] = !vflip` (asserting source mode 2 from comp `0x030[11:10] == 3`).

   Add `--mirror 0..3` and `--reflect x|y` so the tool computes the hardware geometry from client coordinates by the formulas above.
3. **Self-test against stock.**
   - Our baseline (`docs/reference/letterbox-baseline-2026-10-04/native-720p.txt`) must equal stock mode 0 on every word the mirror touches. Diff first.
   - The tool must then reproduce the firmware-written words of `orient-rear`, `orient-rear-ceiling` and `orient-front-ceiling` exactly.
   - Mutations must each fail: no −1, wrong polarity of `040[3]`, H on proc only.
   - A formula that fails this does not drive a write.
4. **Extend the read set of `letterbox-baseline.py`** (read-only, known-safe ranges only): panel `0x0a0`, `0x164`; proc `0x150/250/350`; AFBD `0x05600140`; comp `0x030`. Then retake the baseline.
5. **Fix the docs:**
   - `docs/reference/stock-capture-2026-10-01.md:69-84` and `FINDINGS.md:74-76`: H = `0x051c00a0[0]`; proc `+0x50` is the line shift; "y 22→21" belongs to H, not H+V; drop `0x05040014` and the status words.
   - `docs/reference/letterbox-recipe-2026-10-04.md:51`: "−1 if H mirror", not "if interlaced".
6. **Deliverables:** `docs/reference/mirror-recipe-<date>.md`, and this plan copied to `docs/mirror-plan.md`.

**Exit gate:** the recipe reproduces stock's three orientation states and our native state.

**Outcome (2026-10-06): met.** See [reference/mirror-recipe-2026-10-06.md](reference/mirror-recipe-2026-10-06.md).

| Item | Result |
| --- | --- |
| 1 Firmware | vblend `0x010/0x024[15:0]` are the overlay rectangle's y, stored before the program window's +1, so they follow vde. The firmware addresses proc instance 0 only. |
| 2 Recipe | `hflip/vflip` in `P`, a `vde` property, control bits under `"ctl"` (read-modify-write), `--mirror` and `--reflect`, and `hw_place()`. |
| 3 Self-test | Stock mode 0 equals ours on all 9 mirror words. Modes 1–3: 48 registers × 10 captures, all match. Mutations caught: 8, 6, 3 and 2 mismatches. |
| 4 Baseline | Adds proc `0x250/0x350` and lvds `0x164`. Re-taken on 0165: 50/50 match. **Proc instances 1–3 read identical to instance 0 at a placed dy=92**, so they are followers. `lvds+0x164` read `0x29C` in ordinary playback, so it is status. |
| 5 Docs | The letterbox reference vde line, the stock-capture reference, and the capture's FINDINGS.md. |

## Phase 1: register-poke panel test (one operator session)

> **Tooling built 2026-10-06:**
> - `letterbox-test.sh mirror` (and `plan mirror`, `card-primary`): one "ready" runs the video steps `z h v hv ch abv`, switches the holder to `letterbox-card --primary`, then runs `pv php pho`.
> - `letterbox-apply.py` applies the recipe's `"ctl"` bits read-modify-write. It also has a new `"kind": "osd"` step for the primary route, and stamps each window with wall-clock time.
> - `letterbox-measure.py --mirror --log` reads orientation from the corner-patch colours, treats a frame as control only if it is upright, and matches windows to steps by time. So a step with no visible effect is reported as NO VISIBLE CHANGE instead of shifting every later step.

Extend the letterbox Phase 1 tooling rather than writing new tools:
- `letterbox-apply.py`: mirror steps, with source 0 stopped, writes inside the NR bracket, read-modify-write on comp `0x040` (bit 25 shares the word) and proc, and timed exact restores.
- `letterbox-test.sh all`: one "ready", `LEAD_S` = 30 s, steps back to back, the console returning means stop recording.
- `letterbox-card.c`: add a `--primary` mode, an ARGB card on the primary plane with the same quadrant colours (TL red, TR green, BL blue, BR yellow) plus a 1-px white frame on all four edges.
- `letterbox-measure.py`: add an orientation classifier from the quadrant colours (identity, mirror-x, mirror-y, rot180), self-tested on synthetic renders of all four, alongside the existing rect measurement and magenta detection.

Steps, written in hardware coordinates:

| Step | Holder | Writes | Expect |
| --- | --- | --- | --- |
| z | video card | no-op rewrite | identical card |
| h | video card | panel bit + dy−1 (4 fields) + vblend y−1 | L/R swapped, nothing shifted |
| v | video card | AFBD `[3:2]=2` + comp `040[3]=0` | T/B swapped |
| hv | video card | both | rot180 |
| c-h | video card | 852x480 at hw (0,120) + H | picture at visible x=428, bars 428/0 (vblender is upstream) |
| ab-v | video card | 1280x536 at hw (0,0) + V | flipped, top-aligned, **no magenta** (padding rows not flipped into view) |
| p-v | primary card | `0x05600140[3]=1` + READY | T/B swapped |
| p-hp | primary card | panel `0x0a0[0]=1` only | L/R swapped? all four white edges present (no lost row)? |
| p-ho | primary card | `0x05600140[2]=1` + READY | L/R swapped? (ranks the two RGB H mechanisms) |
| (opt) p010-v/h | kms-p010-plane-test | v, h on native P010 | format coverage |

**Operator question per step:** which corner is red, is anything magenta, are all four white edges there?

**Decisions this produces:**
- The RGB H mechanism: the panel bit is preferred, as stock's. If only OSD bit 2 works, use it. If neither works, stop and ask before going on, because the installation mode would be partial.
- Whether V needs `h % 16 == 0`: if ab-v shows magenta, `check` refuses non-16 heights under V, and the fit rounding in `h713-play` honours it.
- Whether P010 can V-flip. If not, `check` refuses V for P010, and the client falls back to the GPU path.

**Safety:**
- logo first, then the native card as positive control;
- stop at the first refusal or wedge;
- budget one power cycle (serial and USB unplugged, ≥1 min off);
- never read `0x07091000` or `0x06940000`.

## Phase 2: kernel (on top of 0165)

**Patch A (small), debugfs `geometry`**, which letterbox Phase 2 planned but never shipped. Check 0163–0165 first. It prints:
- the committed src/dst;
- the hardware geom (dx, dy, hflip, vflip);
- `mirror_mode`;
- each recipe register, live vs model.

This is what every register diff below uses.

**Patch B, the mirror**, in `drivers/gpu/drm/tiny/sun50i-h713-afbd.c`:

- **State:**
  - `struct h713_geom` gains `hflip, vflip`, and `h713_geom_eq()` compares them, so a flip change takes the existing stop → bracket → start path.
  - Field functions return signed values (`dy − hflip` is −1 at dy=0).
  - New table entries: vblend `0x010/0x024[15:0]` REL `−hflip`, and panel `0x0a0[0]` ABS `hflip`.
- **`h713_lb_program()`:**
  - read-modify-write comp `0x040[3] = !vflip` after hold and before release;
  - not through the word table, whose `0x040` word would carry bit 25 and release NR early.
- **Video `atomic_update`:** the ctrl word ORs `vflip ? BIT(3) : 0`.
  - **Native size with flips** goes through `h713_lb_program()` but **not** `h713_lb_check()`, so NV12 and P010 at native size can both mirror.
  - Split the "native?" test into size/placement versus flips.
- **Probe:** mirror support (`mirror_ok`) requires `lb_ok`, comp `030[11:10]==3`, comp `040[3]==1`, panel `0x0a0[0]==0`, and both AFBD ctrl `[3:2]==0` (an unmirrored boot).
  - Otherwise no rotation property is created, and setting the mode returns `-EOPNOTSUPP`.
- **Rotation property:** `drm_plane_create_rotation_property()` on `h->pipe.plane` and `h->video_plane`, with supported = ROTATE_0 | ROTATE_180 | REFLECT_X | REFLECT_Y.
  - Both checks normalise with `drm_rotation_simplify()` and compute the hardware geometry by the formulas above.
- **Primary plane:**
  - Keep a current OSD ctrl (`rgb_ctrl_active | vflip<<3 [| hflip<<2 if OSD-bit H won]`), used by `h713_afbd_set_source()` and `video_stop()`.
  - Write the panel bit for the primary's hflip while the primary owns the mux.
  - Add a vertical compensation only if Phase 1 showed a lost row.
- **Installation setting:**
  - A `drm_private_obj` holds `mirror_mode`. Both plane checks pull it in, so check and commit see one value.
  - Device attribute `mirror_mode` (RW, 0–3) on the display device. Its store builds an atomic state with the new private state plus both planes, and commits it blocking with `-EDEADLK` backoff.
  - On a check failure it returns the error and leaves the mode unchanged.
  - The video plane re-commits with one ~30 ms green flash, which is the existing geometry-change behaviour.
  - Module parameter `mirror_mode` (0444) is the probe-time default (cmdline `sun50i_h713_afbd.mirror_mode=N`).
- **Don't** set the connector `panel orientation` property: fbcon and other clients would compensate in software and double-flip.

## Phase 3: userspace, rootfs, docs

- **`tools/display/h713-mirror [front|rear|rear-ceiling|ceiling|0-3] [--persist]`**:
  - the names map to stock: front=0, rear=1 (H), rear-ceiling=2 (V), ceiling=3 (H+V);
  - it writes sysfs and prints the resulting mode;
  - `--persist` rewrites `/etc/tmpfiles.d/h713-mirror.conf`.
- **`tools/rootfs/customize.sh`:** add the default line (mode 0) next to the schedutil one at `:592`.
- **`h713-play` and kmssink:** no change; the mirror is invisible to them. Rotated files still go to the GPU.
- **Docs:**
  - `gpu-fallback-plan.md` WP5 line;
  - `letterbox-plan.md` Phase 4 mirror bullet (now points to WP5);
  - `kms-display.md` (rotation property, `mirror_mode`);
  - `register-index.md` (`0x051c00a0[0]`, `0x05600010[3:2]`, `0x05600140[3:2]`, comp `0x040[3]`);
  - `status.md`;
  - the memory notes `vendor-capture-plan` and `window-layer-placement`.

## Verification

- **Phase 0:** `letterbox-recipe.py --self-test` passes the stock orientation points and the mutations fail.
- **Build and boot:** `tools/build/build.sh kernel` → `tools/install-kernel-fit.sh build/out/h713-kernel.fit` → cold power cycle. dmesg reports mirror support.
- **Mode 0 regression:** debugfs `geometry` equals the baseline on every recipe register. The native NV12 and P010 scanout gate is unchanged (changing fb id, `0x05600010`).
- **Register diff:** for each mode, debugfs `geometry` minus `letterbox-recipe.py --mirror N` gives 0 mismatches.
- **Panel matrix (one "ready", handheld video, orientation classifier):**
  - console, with modes 0→1→2→3→0 set from sysfs and no client running;
  - video card in modes 1–3;
  - an asymmetric 852x480 at (0,0) in modes 1–3, expecting visible (428,0), (0,240), (428,240);
  - REFLECT_X in mode 0 (mirrored in place);
  - REFLECT_X in mode 1 (cancels, at (428,0));
  - ROTATE_180 in mode 0;
  - REFLECT_Y on the primary;
  - native P010 in mode 3.
- **Every step:** zero refused commits, zero IOMMU faults, a changing fb id.
- **Playback:**
  - `h713-play` plane-ve on a scope clip in mode 3, 10 min (`plane-soak.sh`), with three mid-play 0↔3 switches (one flash each, A/V in sync);
  - stock mpv GPU path in mode 3, mirrored.
  - **Print the route and decoder/GPU IRQs for every run**: plane routes must have 0 GPU IRQs.
- **Persistence:** `h713-mirror ceiling --persist`, cold boot, mode 3 is active after tmpfiles. Then restore 0.

## Sequencing and cost

| Phase | Work | Operator looks | Power cycles |
| --- | --- | --- | --- |
| 0 | desk, recipe tool, docs | 0 | 0 |
| 1 | tooling and one session | 1 | 1 |
| 2 | kernel A and B (0166+) | 1–2 | 1 (FIT) |
| 3 | tool, rootfs, docs | 0–1 | — |


## Risks and standing rules

- **The RGB route's H mechanism is unknown until Phase 1.** No working mechanism means no installation H for the console or the GPU path; escalate rather than ship a partial mode.
- **Proc has live upper bits, and comp `0x040` shares the word with hold/release:** read-modify-write only. Values come from the recipe tool, never by hand.
- **Never enable source 0 with no frame behind it.** The fetch budget must never exceed the buffer.
- **The panel bit's latch timing (vsync or immediate) is unknown.** A one-frame tear on a mode change is acceptable.
- **The stock elog releases NR one frame later than our bracket does.** Our immediate release was clean for letterbox; revisit only if a mirror step shows a one-frame glitch.
