# HDMI audio monitor and correlated bridge trial

Date: 2026-10-07. Continued from the cold source-3 resume. No persistent
bootloader, environment, or firmware changes were made.

## Positive firmware evidence corrects the cache inference

The port-1 active byte at port-object+0x531 is already 1. HDMI+0xe8 identifies
port 1 as active. Neither needed modification. The port poll tail-calls
AudioMonitor at 0x8b13a2a8 after checking this byte.

ARM's read-only snapshots of MIPS DRAM can be stale behind MIPS D-cache.
Unchanging PLL history fields must not be interpreted as evidence that
SetAPLL never ran. The firmware elog also has dirty-cache holes and damaged
records: positive messages are useful, missing messages are not conclusive.

The normal tone stop/start window (`cache-trial.log`, `audio-cache-trial.json`)
completed twice with CTS 74250 / N 6144. Its later firmware dump (`elog-hdmi.txt`)
contains positive records:

- tick 1583298: audio parameters 74250, 6144, 48000, 48, 16;
- tick 1614140: SetAPLL detects last N/Fs 0 -> 6144/48000 and calls Update;
- same tick: PLL calculation reaches xDiv 1, pDiv 8, mDiv 48, mInt 48,
  remainder 0, programs the update, and logs `Updated!`;
- tick 1614150: source loss resets audio and changes receiver state 5 -> 3.

This establishes firmware PLL update execution just before source-loss handling
in that window. It does not prove PLL lock or audio output during playback.

## Correlated bridge trial

`bridge-trial-command.py` is an evidence copy of the latest checkout's
run-audio-status-trial.py adapted in /tmp to use its original sibling helpers,
add the cold-session-required `--stock-io`, and read firmware elog/cache at
snapshots 2–5. The other chat's checkout was not edited.

Exact kernel 6.18.38 modules were rebuilt in /tmp; their hashes match the
previously validated builds:

| Module | SHA256 |
|---|---|
| Corrected stock-order TVFE hold | 8f32cf93d04650082aacc825bcc6d7350a3e9bff40cdc8e4a6d0912e9047f816 |
| Deferred/threaded IRQ audio probe | d08ff41b12967deef9b40ddb5c521da8c77feb758bae816f2040eadb01112bb7 |
| Complete canonical EDID SCP probe | 0c41c7071c4606fc328fbc0d8ef2b52783af3dded199d1aad698ebedc5a3c0e0 |

The bounded 30-second HPD window read the canonical EDID, locked port 1 state 5
at 1280x720 with pixel repeat 0, resolved PCM hw:0,8 through ELD, and completed
12 seconds of stereo S16_LE 48-kHz tone (left 1 kHz/right 2 kHz). The probe
applied validated audio-top/IHB, SPDI1 open/run, and stage-4 bridge stream 0.

Snapshots 1–6 (including after HPD teardown) all showed:

- SPDI1 and bridge status zero; both interrupt counts zero;
- coherent 64-KiB DMA sentinel unchanged, FNV-1a 62519dc5;
- bridge stream config 0x3207, start/end 0x006c6000/0x006c6fff,
  DMA address 0x76c60000, block threshold 0x40;
- SPDI1 controls 0x90000000/0x3000 and IHB word 0x81000002 latched.

The firmware log captured during playback positively records audio parameters
74250/6144/48000/48/16 at tick 2058626. No new SetAPLL message was visible in
these snapshots, including the final dump after source teardown; missing
messages remain inconclusive because this log is not cache-coherent. No PCM
samples were captured. This trial correlates known audio metadata with absent
SPDI1/bridge activity, without establishing the reason upstream audio is absent.

## Monitor control-flow boundary

Disassembly (`audio-worker.asm`, `audio-pll-route.asm`, `audio-init.asm`) shows:

1. AudioMonitor reads receiver+0x40 & 0xf0 through 0x8b13cc9c.
2. Branch 0x8b13a2f4 skips SetAPLL when this status equals audio+0x10.
3. On a change it saves the status and dispatches SetAPLL through 0x8b22f0c4.
4. SetAPLL at 0x8b13c524 independently compares N/Fs against history+0x30/34.
5. Event 0x3000 populates audio timing fields and clears that history.
6. The fallback when the infoframe rate is absent updates the receiver's rate
   code via 0x8b13cad0, rather than directly calling SetAPLL.

A metadata event after a stable audio-status transition could therefore leave
PLL history cleared without triggering another SetAPLL until status changes.
This is a concrete hypothesis, not a confirmed diagnosis: DRAM snapshots do
not establish what the MIPS monitor sees. The next useful firmware experiment
is a counted monitor/SetAPLL trace during playback with a guarded cold-start
profile. Avoid live code patching or inferring PLL state from ARM cache zeros.
No speculative firmware patch was applied.

## Cleanup and reproducibility

The HPD helper restored peripherals/SRAM and disabled the host HDMI output.
Both audio and TVFE hold probes unloaded cleanly; MIPS answered `help win`.
Only h713_hdmi_power and h713_edid_clock remain loaded for receiver bring-up.
`bridge-cleanup.log` retains snapshot 6 and the liveness check. Canonical
capture evidence remains separate from user changes to the VP9 reference.

Parsed firmware logs are retained here; raw 2-MiB dumps remain in /tmp and
`raw-elog-manifest.json` records their sizes and hashes. Log snapshots read
only the MIPS DRAM log window at physical 0x4b270000, never receiver MMIO.
The audio sampler's corrected labels include last N, last sample rate,
infoframe rate code, monitor counter, and active-port gate. Python syntax
compilation and git diff --check pass.
