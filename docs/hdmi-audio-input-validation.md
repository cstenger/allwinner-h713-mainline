# HDMI input audio bring-up

Date: 2026-10-07

## Established source and receiver path

The canonical 256-byte EDID advertises preferred 1280x720p60, 640x480
fallback, an HDMI VSDB, and stereo LPCM at 32/44.1/48 kHz, 16-bit. Its SHA-256
is `edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`.
During bounded HPD trials the host dynamically resolves the GPU HDMI PCM as
`hw:0,8` and plays a deterministic 48-kHz S16_LE signal (left 1 kHz, right
2 kHz). Never hard-code that PCM number; resolve it from the active ELD.

Every audio trial now gates playback on the MIPS receiver cache reporting port
1 state 5, 1280x720, and pixel repeat 0. The state is saved in
`receiver-lock.json`. This removed an earlier false negative in which the GPU
was connected but the receiver remained in state 3.

## TVFE prerequisite and corrected hold

Four stock CCU captures have `0x02001d64 = 0x00010001`: demod reset released
and bus gate enabled. A first Linux experiment enabled the bus before releasing
reset and hard-hung the board. That ordering is withdrawn. The safe order
recovered from `sunxi_tvtop.ko` is reset first, fifteen functional clocks next,
and the demod bus last, with the stock delays.

The first stock-order hold then exposed another important distinction: writing
the cold stock TVFE constant `0x003003ff` over the live MIPS value `0x00111111`
left MIPS responsive but prevented receiver lock. The corrected module refuses
a zero live word and preserves the existing nonzero firmware state. It has
held stable state-5 1280x720 lock across a 20-second canonical-EDID window.
The exact-kernel corrected build used for those trials has SHA-256
`8f32cf93d04650082aacc825bcc6d7350a3e9bff40cdc8e4a6d0912e9047f816`.

Do not repeat either the bus-first sequence or the live `0x003003ff` overwrite.

## AudIf result with a valid video lock

With the corrected TVFE hold, audio-top setup, stock audio-IHB word
(`0x02001d50 = 0x81000002`), and SPDI1 run words all latch. The stock
`AudIf_spdi_Open` sequence has also been reproduced with an owned DT interrupt:

- clear controls and W1C only `0x00300052`;
- write route `0x400`;
- enable mask bits `0x00300052`;
- write `0x00003000` to `0x06146038`, then `0x90000000` to `0x06146034`.

In the lock-gated trial at
`/tmp/h713-hdmi-audio-status-20261007T091825Z`, the exact EDID was active,
the receiver remained state 5 at 1280x720, and the GPU completed deterministic
PCM playback. AudIf status stayed zero before, during, and after playback;
the owned handler received zero interrupts. MIPS remained alive. This is a
valid negative result: clocks plus SPDI1 open/run are insufficient without the
Audio Bridge stream or another upstream HDMI-audio route.

The owned-SPDI exact-kernel build in that trial has SHA-256
`4088c5ff50c1eb1309d30213e6390d63e730f18e5df249ee36149a3fff458f15`.

## Stock Audio Bridge output stream 0

The stock `snd_alsa_trid.ko` call chain is:

`Thal_Alsa_Audio_Capture_Start` -> `Trid_Audio_Output_SPDIF_Input` ->
`audbrg_ostream_config` / `audbrg_ostream_start` -> `AudIf_spdi_Open` ->
`AudIf_spdi_Run`.

For capture device 0 the caller passes `(0, 0, 2, 2)`. The resulting output
stream 0 configuration is:

- private 64-KiB coherent DMA buffer;
- stream register block `0x06148100`;
- start/end addresses in 16-byte units and the upper nibble at `0x06142044`;
- 1024-byte block threshold (`0x40` in 16-byte units);
- config word `0x00003207` (not `0x2207`; `r2=2` contributes bit 12);
- stream IRQ bit `0x10`, global bridge IRQ bit 0, and DT interrupt index 0;
- stream-sync zero followed by a 1 -> 0 flush/start toggle.

A first combined stage-4 load on 2026-10-07 hard-hung the board during module
insertion: SSH disappeared and a later serial listen produced no output. The
receiver and MIPS had passed their checks immediately before insertion, but no
new stage log was captured, so the precise failing write is not yet known. Do
not repeat that combined load.

The Audio Bridge DT node is present but disabled. Consequently Linux creates
no platform device for it, and the first revised stage-1 attempt correctly
returned `-ENODEV`. The probe now registers a private 32-bit direct-DMA root
device solely for the coherent allocation and splits bridge setup into phases
selected by `audbrg_stage=1..4`:

1. create the private DMA device and allocate/fill DMA while leaving bridge DT
   interrupt 0 unmapped and performing no bridge-register writes;
2. add address and inert stream register programming;
3. log and clear all pending bridge status before mapping DT interrupt 0,
   request the stock-style one-shot threaded handler, and enable the owned
   interrupt bits;
4. add the flush/start toggle.

Each phase logs before its first new hardware action and restores only the
state that phase touched. On the first serial-instrumented stage-1 retry, all
five audio clocks logged and the machine then stopped before audio-IHB setup or
DMA allocation. The initial suspect was the eager hard-handler request for DT
interrupt 0. A second cold boot deferred the request but stopped at the same
boundary before the post-`irq_of_parse_and_map(..., 0)` message. Creating the
mapping for this already-asserted level source is therefore itself unsafe on
the current kernel. Stock `AudBrg_Init` uses
`request_threaded_irq(NULL, handler, IRQF_ONESHOT, ...)`, and its handler
acknowledges all 14 Audio Bridge status bits. Revised stages 1 and 2 leave the
bridge interrupt entirely unmapped; stage 3 isolates mapping plus the stock
threaded shape after status logging and clearing.

The current ordering has passed all four phases under continuous serial
capture. Phase 1 allocated DMA at `0x76c60000` without changing the sentinel;
phase 2 latched start `0x006c6000`, end `0x006c6fff`, block `0x40`, config
`0x3207`, and upper-address word `0x70`; phase 3 cleared zero pending status,
mapped Linux IRQ 336/GICv2 145, and enabled the threaded handler without an
interrupt; phase 4 survived the flush/start toggle. MIPS remained responsive
and every phase unloaded cleanly. The exact-kernel module has SHA-256
`d08ff41b12967deef9b40ddb5c521da8c77feb758bae816f2040eadb01112bb7`.

## Full bridge/SPDI trial

The canonical trial log is
`/tmp/h713-hdmi-audio-status-20261007T095104Z`. It used the exact complete
EDID, dynamically resolved `hw:0,8`, held receiver state 5 at 1280x720, and
ran the deterministic 48-kHz stereo LPCM signal with the stage-4 bridge and
SPDI1 path active. Across snapshots 2 through 5:

- AudIf status remained zero and its handler received zero interrupts;
- Audio Bridge status remained zero and its handler received zero interrupts;
- the 64-KiB sentinel buffer had zero changed bytes (FNV `62519dc5`);
- MIPS remained responsive after playback.

This moves the missing boundary upstream of both the DMA engine and SPDI1.
Stock ALSA capture open/config does not add another HDMI receiver write:
`Thal_Alsa_Audio_Open` allocates the capture handle, enables the bridge
interrupt, and opens output stream 0; config only records format fields; start
calls the bridge/SPDI sequence already reproduced here. The next bounded work
is therefore to identify the receiver/MIPS route that feeds recovered HDMI
audio into SPDI1, not to repeat bridge DMA trials.
