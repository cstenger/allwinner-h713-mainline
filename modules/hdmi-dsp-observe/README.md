# Logo-free DSP access bench

This module is experimental and excluded from normal startup. It does not
implement warm HDMI recovery. See
[the protocol and access audit](../../docs/hdmi-dsp-observation-2026-10-20.md)
for the required cold-only RAM boot, capture and recovery boundaries.

Build against the exact installed kernel, for example:

```sh
make -C "$kernel_build" M="$PWD/modules/hdmi-dsp-observe" ARCH=arm64 LLVM=1 modules
```

The shared ownership/completion headers are the production headers in
`../hdmi-dsp-probe/`. No proprietary DSP patch is bundled. The prepared
experiment uses a copied source tree under the ignored build directory;
its manifest records source/header, module, compiler and kernel identities.

`armed=1` is necessary but insufficient. A dedicated DT marker, no HDMI
handoff, disabled AFBD/CPU_COMM nodes, stopped MIPS/SCP, exclusive register
regions, power-domain holds, reset ownership and clock setup are required.
The userspace helper also pins the boot ID, verifies the module and extended
shutdown guard hashes, rejects competing owners and active HDMI services,
and serializes actions. It records an attempt before loading the module.

Loading acquires the access resources and prepares display/TVFE/audio
controls. It then reads status/lock words, refusing busy or inherited-owned
state. It sends **no DSP request**. The default first cold control refuses
inherited AudioTop enable/configuration state before changing AudioTop.
Preparation is an intervention: it does not preserve pristine DSP reset
state or prove the setup cannot erase a retained patch.

After successful setup, a separate `probe_versions=1` sysfs write requests
logical `0x80ff` on device 0 then device 1. Both busy-clear and done-set waits
are bounded at 50 ms using the stock protocol. The entire pair uses the stock
shared ownership handshake; the peer word is never written. There is no DSP
patch load, graph write, DMA/IRQ registration, firmware launch or SCP payload.
Raw 32-bit responses are retained; nonzero words do not authorize adoption.
Completion history is changed and ARM ownership is released to 0xaa; those
protocol words are not restored to their original reset values.
Any refusal or transaction failure consumes the one-shot request and latches
failure. Stop and physically cold power off; do not reload or retry.

Successful setup-only or successful version observation can use explicit
`restore=1`. It checks stopped processors, restores saved AudioTop and TVFE
words, reasserts only resets that this module released, relinquishes its
clock/domain holds, then drops its module pin. Failed setup/read/restore keeps
the module pinned. The extended shutdown hook converts reboot/kexec to
poweroff while this module is loaded. Do not force unloading.

The supported wrapper is `tools/hdmi/dsp-observe.py` with `prepare`,
`versions`, and `restore`, each requiring the current expected boot ID and
pinned bundle. Do not substitute the production capture/DSP helper: that
helper requires live source3 and different ownership prerequisites.
