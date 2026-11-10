# DSP observation without logo firmware — October 20, 2026

**October 21 live result:** the logo-free maintenance boot passed, but the
single access-preparation attempt became unresponsive before any result. No
version request was sent. [Evidence and next-stage gate](hdmi-evidence/2026-10-21-dsp-cold-access/README.md).
Do not repeat the current bundle unchanged; localize prerequisite setup with
staged acknowledgments and serial markers before further DSP access.
The [new initial-prefix audit](hdmi-dsp-access-audit-2026-10-21.md) is prepared
offline and stops before domain/clock/reset changes; no live prefix result
exists yet. It is separate from the failed module described below.

The [expanded reset trials](hdmi-evidence/2026-10-20-reset-controls/README.md)
found identical SCP/CCU controls after clean and abrupt resets. Before logo,
demod reset is asserted, the demod bus is gated and audio functional clocks
are gated. The current DSP helper requires a live source3 session and its
managed power/clock setup; it cannot safely be used at this earlier point.
This experiment prepares a **logo-free Linux maintenance boot**, followed by
controlled access setup and a separate one-shot DSP version request. It is
not a recovery implementation or a claim of pristine reset-entry state.

## Why a direct U-Boot version probe is excluded

`h713_dsp_stock_response()` writes a logical address request to the DSP
command port. `h713_dsp_claim()` writes ARM ownership 0x55 and release 0xaa.
Even a logical read changes protocol state. Poll deadlines cannot rescue a
bus transaction to an inaccessible peripheral.

Production initialization holds TVFE/TVCAP power and receiver clocks,
releases demod reset, establishes parent/functional clocks, enables the demod
bus last, enables audio clocks, and initializes IHB/AudioTop before DSP
commands. The lock at `0x05001530/34` is also in the display register range;
logo firmware normally provides the complete display clock/reset tree.
AudioTop writes (`CTL|0x700`, configuration `0x001a5e00` then `0x011a5e00`)
precede production version reads. Their DSP-retention effects are not proven.
A version sampled afterward therefore cannot distinguish hardware reset from
an effect of access preparation alone.

The stock library's `sound_lowlevel_init` is unsuitable as a passive
observer: it configures AudioTop and calls DSP clock-speed/HDMI-input setup.
Existing source and the historical offline decoder describe those effects;
no new stock-library hardware execution is performed here. Static firmware
inspection did not identify a verified existing pre-logo DSP version-read
hook. A negative scan is not proof that no indirect access exists.

## Cold-only RAM boot

[prepare-dsp-observe-boot.py](../tools/hdmi/prepare-dsp-observe-boot.py) accepts
only the installed 7795668-byte kernel FIT SHA-256
`0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70`
and the embedded 34666-byte DTB SHA-256
`4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940`.
It prepares individual guarded console commands and a reference DT, without
writing boot media. The RAM DT disables AFBD and CPU_COMM so they cannot
probe hardware normally prepared by logo firmware. It adds the dedicated
`h713,dsp-observation-v1` marker and has no HDMI handoff. Persistent HDMI units
therefore skip. Serial/network/rootfs remain available; no projected logo or
console is expected in this boot.

The command sequence requires GP6, MIPS status and SCP run/reset to be zero.
It loads the pinned FIT, verifies length and RAM CRC32, copies the embedded
FDT, applies only the reviewed RAM edits, sets GP6 to the existing HDMI latch
value, and boots Linux. GP6 is never cleared; setting it reserves the launch
budget even though no MIPS firmware is launched. The installed U-Boot lacks
its hash command. SHA-256 identity is checked offline against a fresh raw FAT
read; CRC32 checks RAM transport and bootm retains its embedded subimage
SHA-256 checks. CRC32 is not cryptographic authentication.

The cold-boot catcher records a fresh SPL boot and sends exactly one space
at the autoboot countdown. It never sends a command or resets the board.
Repeated boots, missed logo boundaries or lost UART after SPL cause refusal.
The boot runner checks each console step's separate acknowledgment and stops
at the first failure. There is no saveenv, startup-script replacement, SPL/
BL31/U-Boot installation, source3 invocation, GPIO/panel programming or SCP
payload. Keep FEL/OTG rescue available throughout the bench experiment.

## Access setup and request boundary

The isolated [bench module](../modules/hdmi-dsp-observe/README.md) requires the
marker, disabled display/CPU_COMM nodes, no handoff, stopped MIPS/SCP and
exclusive DSP-port/lock/AudioTop/SCP-reset resources. It holds the same two
power domains as the receiver owner and prepares the complete display tree
used by `h713_display_clocks_on()`. It preserves inherited clock gates and
the initial display reset state. It follows the production TVFE/audio order,
excluding the live-TVFE control check/write because no source3 exists.

Preparation includes these interventions: domain resume, clock enables,
release of asserted display/demod resets, stock functional-clock words and
AudioTop setup. It records pre-setup AudioTop, then samples DSP status and
lock words. Inherited AudioTop enables/configuration, busy bits or either
ownership word at 0x55 cause a latched refusal. No DSP command is sent during
module load. These reads and this combination without logo are new bench
accesses: a successful build/mock check does not establish hardware safety.
The first cold run must validate setup before requesting any version.

Only an explicit later request reads device-0/device-1 logical 0x80ff. Both
busy-clear and done-set waits are bounded at 50 ms. The whole pair holds the
stock lock, preserves raw responses, never writes the peer word, and never
loads a patch or changes the graph. Any failure prevents further commands;
retain evidence and cold power off. Successful explicit restoration checks
control readbacks and relinquishes holds. A completed read still changes DSP
completion history and releases ARM ownership to 0xaa; cleanup does not claim
to restore those protocol words to their reset values. The extended shutdown guard
prevents a loaded bench module from entering a normal reboot/kexec.

The wrapper pins boot ID, module/guard hashes and ABI, rejects other owners
and active HDMI units, serializes actions, and persists the attempt before
load. A restored session still cannot be repeated in the same Linux boot.
Production guards and DSP 0/0→1/1 initialization policy remain intact.

## Validation and interpretation

The module builds against the installed 6.18.38 kernel tree. Clang 23.1.3
emits the known compiler-version warning against the kernel's 23.1.1 build;
vermagic matches. Native tests exercise the actual shared DSP lock and
response helpers. Fake-backend tests cover boot/marker/DT/owner/guard/module
refusals, no DSP request during setup, preserved raw words, one-shot failure
and successful setup-only restoration. Serial-parser tests cover split
markers, exactly one interrupt and missed/repeated-boot refusal. Offline DT
checks confirm disabled nodes and the dedicated marker. These are not live
DSP or physical reset-domain passes.

The original first-run protocol called for a fully disconnected cold control:
no firmware launch, access setup, status/ownership snapshot, then one version
pair only after healthy setup. It required correlated UART/SSH boot IDs and
the complete sequence, with no retry after a failure.
That first attempt stalled during preparation, so this protocol is now gated
by the October 21 investigation above. A future successful version pair would
establish access **after its recorded setup**. It would not prove that a warm reset erases the DSP patch. That requires a later
controlled retained-patch trial with the same setup and explicit intervention
limits. Automatic warm HDMI recovery remains unimplemented.
