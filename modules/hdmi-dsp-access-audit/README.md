# Staged DSP access audit

A limited experiment following the
[October 21 preparation stall](../../docs/hdmi-evidence/2026-10-21-dsp-cold-access/README.md).
Design: [extension design](../../docs/hdmi-dsp-access-extension-design-2026-10-21.md).
Prefix live result: [prefix runs](../../docs/hdmi-evidence/2026-10-21-dsp-access-prefix/README.md).

Module initialization validates software/DT predicates and pins the module;
it performs no audit MMIO, resource mapping or clock/reset/provider lookup.
Each later write to `advance` executes exactly one numbered operation. There
is no `versions` action, and nothing maps or reads AudioTop, the DSP port or
the lock window.

| Steps | Operation | Boot |
| --- | --- | --- |
| 1–4 | Claim DSP-port, lock, AudioTop and SCP-reset ranges; no access to those registers. | v3 or v4 |
| 5–8 | Map MIPS status, SCP reset and two CCU windows. | v3 or v4 |
| 9–12 | Read MIPS status, SCP reset, demod bus and display bus, individually. | v3 or v4 |
| 13–16 | Get/read display and demod reset. No reset change. | v3 or v4 |
| 17–33 | Get each of the 17 clock handles. No enable. | v3 or v4 |
| 34–40 | Census: map and read TVFE/TVCAP PPU status, TVCAP reset handle/status, clock-enabled mask, 15 TVFE CCU words. Read-only. | v4 only |
| 41–45 | Attach and resume the TVFE then TVCAP genpd domains, each verified by PPU status `00010000`; recheck MIPS/SCP stopped. | v4 only |
| 46–53 | Release TVCAP reset only if asserted; enable receiver clocks; release demod reset; PLLs. | v4 only |
| 54–69 | Write the 15 stock TVFE CCU words one per step with readback; set demod bus gate. | v4 only |
| 70–74 | Enable audio clocks. | v4 only |
| 75–82 | Display tree, display reset only if asserted, final recheck. | v4 only |

Steps 34 onward run only when the booted DT carries
`h713,dsp-observation-v2` and the PPU node lacks `allwinner,keep-tvcap-on`
(boot-v4); `extension_available` reports this. On a boot-v3 DT the module
stops at `prefix-end` as before. State-changing steps log `OP-DONE` between
the operation and its read-back, so a hang shows which half stuck. Clock
steps skip clocks already enabled (`last_value` 1) and take no reference on
them, matching the old bench.

`release_prefix` frees software handles only, and only through step 40.
From step 41 there is no software restore: the only supported end is an
orderly poweroff with the module loaded, which the hold guard permits
(it converts reboot/kexec to poweroff). Failed operations retain the module
pin and everything acquired until physical cold recovery. Do not force-unload.

Use `tools/hdmi/dsp-access-audit.py` from a pinned staged bundle. `load` must
acknowledge cursor zero before any `step`; every step needs both its exact
number and operation name. At each stage boundary (after steps 33, 40, 45,
53, 69, 74, 81) the helper requires a read-only `snapshot` (clock and genpd
summaries) and then `--stage-ack <stage>`. Before every modifying action it
checks boot ID, boot-v4 markers, the absent TVCAP flag, disabled nodes, no
competing owners or HDMI services, console threshold ≥ 6, `kernel.panic` 0,
module/helper/guard hashes and ABI. It flushes milestones and records the
attempt before load, advance or release. A missing acknowledgment consumes
the boot; do not retry, advance, release or reload after uncertainty.

BEGIN/OP-DONE/DONE messages are `pr_notice`; raise the console with
`dmesg -n 7` first or the UART shows none of them. Printk can be buffered;
missing text is not proof an operation never ran. A subprocess timeout
cannot end a wedged MMIO transaction.

Build an isolated copy against the installed kernel, without installing it:

```sh
task_build=$(mktemp -d "$PWD/build/hdmi-dsp-access-audit.XXXXXX")
cp modules/hdmi-dsp-access-audit/Makefile modules/hdmi-dsp-access-audit/h713-hdmi-dsp-access-audit.c "$task_build/"
make -C build/linux-6.18.38-da2bc49e45e531a23632a1063266bd439454e31dd383f49c502ddb793277d731 M="$task_build" ARCH=arm64 LLVM=1 W=1 modules
```

The prepared extension bundle is `build/hdmi-dsp-access-ext-2026-10-21/bundle/`
with `boot-v4/` beside it. The earlier prefix bundles (`bundle/`,
`bundle-v2/` under `build/hdmi-dsp-access-audit-2026-10-21/`) pin the
prefix-only helper. No generated `.ko` is tracked or packaged for normal startup.
