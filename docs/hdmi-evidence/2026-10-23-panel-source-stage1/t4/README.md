# T4: AFBD source 0 fetches the HDMI capture ring through the identity map (10-23)

T4 from §10.12 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).

## Boot

* Operator cold power-on: serial and USB unplugged, at least 1 minute off,
  HDMI connected. Serial was replugged right after power-on to stop
  autoboot.
* `tools/serial/run-t4-cold.py` ran the cold startup; its log is in
  `../t4-run/`.
  * Census at the prompt: MIPS `0x0306101c = 0`, GP6 `0x07090118 = 0`
    (`census.json`).
  * It sent `t4-cold.scr` by YMODEM, verified the CRC `36328635`, and
    sourced it once.
  * The script loaded `/root/panel-source-t4/h713-kernel-t4.fit` from ext4
    (7795808 bytes), re-latched 720p and printed `H713 HDMI cold startup
    handoff verified`; then Linux booted (`uart-t4-boot.log`).
* Boot `34ee92bd-95ac-46cd-a066-628f389ad507`, kernel 6.18.38. U-Boot proper
  and every installed file are unchanged.

## The DT took effect (read-only)

* `framebuf@4bf41000` has `iommu-addresses`; `iova-reserve-mips-framebuf`
  exists.
* `/sys/kernel/iommu_groups/0/reserved_regions` (av1, video-codec,
  display):

      0x4bf41000 0x4d940fff direct
      0x4bf41000 0x4d940fff reserved
      0x6c100000 0x6c8fffff direct     (the 0080 scanout map, unchanged)
      0x6c100000 0x6c8fffff reserved

* No failed units, no IOMMU fault lines, `/dev/video0` and `/dev/video1`
  present, HDMI-A connected on the host.

## Steps

The commands went through `mips-shell.py --cmd`; the reads used `t4read.py`
(the T3 reader plus the IOMMU `0x100–0x13c` registers, six `+0x320`
samples, and `0x10`), driven by `t4step.sh`.

| Read | Command | AFBD `0x10` | `+0x58 / +0x5c` | IOMMU `0x108` | selector | TCON 20/24 | faults |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pre` | — | `03000010` | `0 / 0` | `0` | `29000000` | `02f80550 02d00500` | 0 |
| `rn2` | `win rn 2` | `03000200` | `0 / 0` | `0` | `29000000` | same | 0 |
| `en4` | `memory_agent en 4` | **`03000203`** | **`48 / 3c`** | `0` | `29000000` | same | 0 |
| `en4-5s` | (5 s) | `03000203` | `69 / 3c` | `0` | `29000000` | same | 0 |
| `dis4` | `memory_agent dis 4` | `03000200` | `47 / 3b` (frozen) | `0` | `29000000` | same | 0 |
| `rn0` | `win rn 0` | `03000200` | `47 / 3b` | `0` | `29000000` | same | 0 |

Notes on the table:

* **Preconditions** were the same as in T3: MemoryAgent `+0xc = 00020003`,
  `+0xb5 = 1` (locked), bypass `58`, no Cedrus user.
* **`win rn 2`** reproduced T3 exactly: format `0x02`, geometry
  `02cf04ff`, strides `0x500`, mux `022`, composition `0x30 = 00400000`.
* **The capture pair `+0x320`** cycled through the ring slots `4c3ef000`,
  `4c5ee000` and `4c7ed000` throughout.
* **`+0x58`/`+0x5c` while enabled:** a 0.5 s series read `56/4b`, `47/3b`,
  `69/3b`, `69/3b`, `47/3b`, `48/3c`.
* **After `dis 4`:** 20 samples over 2 s all read `47 / 3b`
  (`after-dis-58-5c.txt`).
* **Stage-1 snapshot `t4-en4`** was taken with agent 4 enabled (`../t4-en4/`).

## Result

**Source 0 fetches the capture ring cleanly through the identity map.**

* `memory_agent en 4` set source 0's enable bits (`0x10[1:0] = 3`).
* `+0x58`/`+0x5c` read 0 for as long as source 0 was off. They varied
  continuously while it was on, and froze the moment it was turned off, so
  they track source 0's fetch progress. AFBD fetched.
* Master 2 translates (bypass `58` leaves bit 2 clear), so every fetch went
  through the `0x4bf41000–0x4d940fff` direct map.
  * The IOMMU interrupt status stayed 0, as did every error-address
    register `0x10c–0x13c`.
  * No kernel fault lines appeared, and the console was undisturbed.
* NR agents 5/6 weren't needed, so they weren't added.
* The selector stayed `29000000` (the console), and TCON stayed at 720p.

**Operator observation:** the panel wasn't watched during the steps. When
checked after the restore, it showed the Linux console. So a transient
change during `en 4` can't be ruled out by eye. The register record (the
selector constant at `29000000`, TCON unchanged) is the evidence that
nothing visible was routed.

**What's left before T5:** flipping the selector `0x051c006c` to
`0x39000000` with source 0 fetching. Whether a picture appears, and what
it looks like (format `0x02` 4:2:2 vs the decoder's NV12 assumptions, and
range), is T5's question.

**State after T4:** source 0 is disabled, and the AFBD capture
configuration persists, as after T3. The next boot uses the production
FIT, because the T4 FIT was only ever sourced from RAM. The T4 files
remain in `/root/panel-source-t4/` for T5.
