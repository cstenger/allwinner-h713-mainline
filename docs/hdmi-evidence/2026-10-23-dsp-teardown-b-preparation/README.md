# Phase B teardown bench — preparation (Claude, October 23)

**Offline only. No board access, staging, capture or power request.**
Implements Phase B of the
[remaining teardown design](../../hdmi-dsp-remaining-teardown-design-2026-10-22.md)
after the Phase A matched result
([arm 2](../2026-10-22-dsp-teardown-a-teardown-live/README.md): all register
teardown preserved `1/1`). Candidate:
`build/hdmi-dsp-teardown-b-2026-10-23/candidate/` (Phase A candidate untouched).
[Manifest](manifest.json), [verification](verification.json),
[build log](build.log), [tests](tests-summary.json),
[cold script](cold-teardown-b.cmd), patches for
[PCM](h713-hdmi-pcm.c.patch), [DSP](h713-hdmi-dsp.c.patch),
[TVFE](h713-hdmi-tvfe.c.patch).

## What the live journal says the clock edge is

From the Phase A boots: all five audio clocks were **inherited on**
(`enabled_by_driver=0`), so normal teardown drops none through CCF; the
IHB retime is a no-op (`81000002→81000002`). `pll-video0` was inherited,
`pll-adc` was enabled by the TVFE probe (and the receiver also holds
`tvfe-1296m`). So the real clock-off edge of normal teardown is
`h713_hdmi_tvfe_release()`: demod bus gate off with reset still released
(`0x02001d64 = 00010000`), the 15 TVFE/audio CCU words restored in reverse
to their pre-prepare values, `pll-adc` dropped, then the shared
`reset_bus_demod` (bit 16 of the same register) asserted and the saved bus
word restored. The cold U-Boot census shows those saved words have their
gates **off** (e.g. TVFE-1296 `0`, audio CPU/UMAC `2`, IHB `7`), so this edge
stops the DSP core and audio clocks. The bench records the actual saved
words; if none clears a gate the analyzer refuses to attribute
(`inconclusive_null_clock_edge`).

## Plan (39 one-shot steps, 4 version pairs, at most 8 requests)

| Steps | Operation | Sham (arm 1) | Arm 2 |
| --- | --- | --- | --- |
| 1 | Census: Phase A words + 15 TV words, bus, reset, parents, audio clocks | same | same |
| 2–6 | Pair 0 (positive control) | | |
| 7–10 | Phase A prefix: graph, SPDI, bridge, AudioTop config (qualified) | writes | writes |
| 11–15 | Pair 1 (prefix check; must be `1/1`) | | |
| 16 | **Close gate:** AudioTop control → saved 0 | write | write |
| 17 | Saved IHB word; release driver-enabled audio clocks via CCF | IHB only | IHB + CCF |
| 18 | TVFE off edge: bus gate off (reset released), 15 words reverse, drop `pll-adc` | reads only | writes |
| 19 | Hold 1 s, closed | same | same |
| 20 | Reacquire in prepare order: parents, 15 stock words forward, bus last | identical writes | writes + CCF |
| 21 | Audio clocks back, stock IHB word | IHB only | IHB + CCF |
| 22 | **Open gate:** TVTOP+0x40 routed, AudioTop control 700 | write | write |
| 23–27 | Pair 2: **clock round trip** | | |
| 28–34 | Same as 16–22, plus `reset_control_assert` + saved bus after the off edge, and `reset_control_deassert` + 10–15 ms settle before reacquire | no reset | **demod reset** |
| 35–39 | Pair 3: **clock + demod reset round trip** | | |

A changed, echoed or timed-out pair is terminal; no later operation runs.
The sham performs every common access-restoration transaction (gate
close/open, IHB writes, identical stock-word and bus rewrites, the same
dwell and settles) but never changes a clock, parent or reset.

## Access gate and safety

* While the gate is closed: no AudioTop, AudIf, bridge, DSP-port or lock
  access; health reads only R_CCU PPU, PPU status, MIPS status, TVTOP+0x40
  (SPL-safe) and CCU words, and reports the verified control write instead
  of reading AudioTop. Version, claim and checkpoint refuse unless open.
* Every step verifies all 15 TV words and the bus word against the phase
  the bench put them in. TVTOP+0x40 is recorded every step and must be
  routed (`00011111`) before the gate reopens; a routing change during the
  off window is recorded, then the reopen is a hard failure (no lock read).
* Shared reset balance: one assert/deassert on the existing shared handle;
  the assert must actually reach hardware (status 1, bit 16 clear) or the
  step fails — another deasserted user would otherwise fake the boundary.
* CCF balance: `pll-adc` and any driver-enabled audio clock are released
  and re-enabled through the clk API; references are never put. A parent
  still running after its drop (receiver child hold) is recorded.
* Mappings, IRQ objects, DMA, receiver reference and domains stay held; no
  MIPS park, domain release, unmap, rmmod, firmware relaunch or repatch.
* Board helper skips the debug clk/genpd summaries whenever the gate is
  closed or the TV phase is not ON; requires arm-2 census (Phase A words,
  TV census and TV saved words) to equal the sham's before step 2, and a
  patched prefix pair before step 16. Phase A and older shams are rejected.

## Verification

* W=1 build against the unchanged production kernel/config/Image/Symvers:
  zero C diagnostics (only the clang 23.1.1/23.1.3 Kbuild notice). Vermagic
  matches; the only new undefined symbol versus Phase A is `msleep`
  (kernel-exported). Module `50a63980…`; cold script `7d489809…` differs from
  Phase A's only in marker `h713,dsp-teardown-b-v1`, bootarg and echo.
* 30 new tests. 17 native modes run all three real includes on a fake CCU,
  shared reset and CCF model whose audio windows abort unless control is on
  and the TVFE-1296/audio gates and demod bus run. 22 mutations caught
  (one survivor led to the added `sham-driver-clock` case, one to a
  self-consistent compare fixture). 69 regressions pass (Phase A 26, owner
  14, startup 11, managed boot 7, minimum 11).

**Limits.** The fake cannot predict real stall behaviour or whether MIPS
firmware tolerates the off window; the closed-gate access rule is the
safety argument. A clock-round-trip change localizes to the round trip,
not to the off edge alone. No CPU/MIPS reset, domain release or warm logo
is tested here (Phase C).

## Runbook

Same as Phase A with `tools/hdmi/dsp-teardown-b-host.py`,
`tools/serial/run-dsp-teardown-b-cold.py`, run directories
`docs/hdmi-evidence/<date>-dsp-teardown-b-{sham,arm}-live` and stage names
from `tools/hdmi/dsp-teardown-b.py`. Sham first; arm 2 only after
`sham_positive_control_passed`; separate fully unplugged cold cycles.
