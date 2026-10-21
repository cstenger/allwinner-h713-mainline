# Staged DSP preparation prefix audit

This is a new, limited experiment following the
[October 21 preparation stall](../../docs/hdmi-evidence/2026-10-21-dsp-cold-access/README.md).
It is **built/tested offline only**. No board installation or live step has
been performed. See the [access audit and next live gate](../../docs/hdmi-dsp-access-audit-2026-10-21.md).

Module initialization validates software/DT predicates and pins the module;
it performs no audit MMIO, resource mapping or clock/reset/provider lookup.
Each later write to `advance` executes exactly one numbered operation. There
is no runtime continuation into power domains, clock enables, reset changes,
AudioTop setup or DSP requests. There is no `versions` action.

The 33 steps reproduce the original module's initial resource/lookup prefix,
splitting compound reads into separately acknowledged boundaries:

| Steps | Operation |
| --- | --- |
| 1–4 | Claim DSP-port, lock, AudioTop and SCP-reset resource ranges; no access to those registers. |
| 5–8 | Map MIPS status, SCP reset and two CCU windows; no register read. |
| 9–12 | Read MIPS status, SCP reset, demod bus and display bus, individually. |
| 13–16 | Get display reset, read status, get demod reset, read status. No reset change. |
| 17–33 | Get each of the 17 clock handles individually. No clock state read/enable, rate or parent change. |

Only successful READ steps provide a hardware sample in `last_value`;
non-read operations set it to zero as a placeholder. API reset status is
normalized: 1 means asserted. MIPS must be zero, SCP run bit clear, demod bus
bits 16/0 clear, and demod reset asserted. Display reset may be asserted or
released, matching the old prefix predicate. Successful prefix completion
proves neither later access safety nor DSP state.

Use `tools/hdmi/dsp-access-audit.py` from a pinned staged bundle. `load` must
acknowledge cursor zero before any `step`. Every step requires BOTH its exact
next number and operation name. The helper checks current boot ID, marker,
disabled nodes, no handoff/CPU_COMM/competing owners, inactive HDMI services,
module/helper/extended-guard hashes and ABI before each modifying action.
It flushes userspace milestones and durably records the attempt before load,
advance or release. Missing acknowledgment leaves the boot consumed; do not
retry, advance, release, reload or use the legacy bench after uncertainty.
The read-only `status` action is diagnostic, not permission to proceed.

Kernel BEGIN/DONE messages bracket each operation. Printk can be buffered;
missing text is not proof that a preceding operation never ran. Before each
next step, retain both the helper result and passive UART evidence; do not
wrap the CLI in an unattended loop. A subprocess timeout cannot terminate a
wedged kernel MMIO transaction, and sysfs writes are not hardware deadlines.

Successful healthy partial or full prefixes may explicitly `release` software
handles/maps and unload. No hardware restoration occurs because none was
programmed. Release failure/uncertainty forbids retry. Persistent attempt state
blocks reloading even after success; use a fresh disconnected cold boot before
another experiment. Failed kernel operations retain the module pin and acquired
resources until physical cold recovery. Do not force-unload.

The new hold guard includes `h713_hdmi_dsp_access_audit`; the already-installed
board guard covers the legacy bench only. Install/verify the revised guard
with an exact backup before this module can be loaded. The helper refuses the
old guard. The guard cannot rescue a hung kernel.

Build an isolated copy against the installed kernel, without installing it:

```sh
task_build=$(mktemp -d "$PWD/build/hdmi-dsp-access-audit.XXXXXX")
cp modules/hdmi-dsp-access-audit/Makefile modules/hdmi-dsp-access-audit/h713-hdmi-dsp-access-audit.c "$task_build/"
make -C build/linux-6.18.38-da2bc49e45e531a23632a1063266bd439454e31dd383f49c502ddb793277d731 M="$task_build" ARCH=arm64 LLVM=1 W=1 modules
```

The prepared local bundle is in
`build/hdmi-dsp-access-audit-2026-10-21/bundle/`; its manifest pins module,
helper and guard. `preparation.json` records source/kernel inputs and checks.
If any input changes, rebuild and regenerate identities instead of reusing
these pins. No generated `.ko` is tracked or packaged for normal startup.
