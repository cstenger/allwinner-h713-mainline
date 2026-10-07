# HDMI input audio bring-up

Date: 2026-10-06

## Established source side

The canonical 256-byte EDID advertises preferred 1280x720p60, 640x480
fallback, an HDMI VSDB, and stereo LPCM at 32/44.1/48 kHz, 16-bit. Its SHA-256
is `edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`.
During bounded HPD trials the host dynamically resolves the GPU HDMI PCM as
`hw:0,8` and successfully plays a deterministic stereo 48-kHz S16_LE signal
(left 1 kHz, right 2 kHz). MIPS remains responsive after playback.

## Read-only receiver result

The first status probe enables or inherits the five already-described HDMI
audio clocks, but never requests an IRQ, acknowledges status, configures DMA,
or reads a FIFO. Silence, active LPCM, and post-playback snapshots all read
zero in AudIf and AudBrg. Applying the recovered audio-top sequence and the
stock audio-IHB word (`0x02001d50 = 0x81000002`) did not change that result.

The stock `snd_alsa_trid.ko` disassembly shows that 48-kHz LPCM capture device
0 activates SPDI1 by writing `0x00003000` to `0x06146038`, then `0x90000000`
to `0x06146034`. Those writes also read back as zero. This established that the
whole `0x0614xxxx` audio block was inaccessible, rather than merely idle.

## Missing TVFE prerequisite and failed ordering

Four independent stock CCU captures (two idle and two live HDMI) have
`0x02001d64 = 0x00010001`: demod bus reset released and bus gate enabled. The
guarded Linux HDMI boot instead had `0x00000000`. The first diagnostic attempt
enabled `CLK_BUS_DEMOD` and then deasserted `RST_BUS_DEMOD`. It hard-hung the
board during module insertion; SSH and serial both stopped responding. A cold
power cycle was required. That bus-first ordering is withdrawn and must not be
repeated.

The reconstructed stock `sunxi_tvtop.ko` order is materially different:

1. deassert demod reset while its bus remains gated;
2. wait 10--15 ms;
3. configure and enable all fifteen TVFE functional clocks;
4. enable the demod bus;
5. wait 10--15 ms;
6. hold the already-powered TVFE domain;
7. write `0x003003ff` to the TVFE initialization register at `0x06e00000`.

The fifteen exact CCU words are invariant across the four stock captures and
are now encoded in the separately armed `h713-hdmi-tvfe-hold` diagnostic
module. It saves all affected state, follows the stock order, verifies every
write, and restores on failure or unload. It touches no audio register, IRQ,
DMA, or FIFO. SHA-256 of the first exact-kernel build is
`666c782190f173e0d44f489adbeda5ef7e1ef99dbfb137c76dff696653973175`.

On an ordinary Wi-Fi boot with MIPS parked, loading that module without its
three acknowledgements correctly fails with `EPERM`; the module remains absent
and TVFE/audio clocks remain off. The stock-order active path has not yet been
run.

## Next bounded trial

The next hardware run requires a physical cold boot, the guarded U-Boot
source-3 transition, `run bootcmd`, and `prepare-source3.py --postboot-only`.
With MIPS and both receiver power domains verified live:

1. load `h713-hdmi-tvfe-hold.ko` with all acknowledgements;
2. prove MIPS shell liveness before continuing;
3. load `h713-hdmi-audio-probe.ko` and verify audio-top/SPDI1 writes latch;
4. present the canonical EDID and play the deterministic GPU LPCM;
5. compare silence, active, and post-playback status snapshots;
6. keep IRQ, W1C, DMA, and FIFO operations disabled until status proves the
   receiver path is clocked.

`run-audio-status-trial.py` enforces the TVFE-hold prerequisite for every
audio-register-writing option and performs the intermediate MIPS liveness
check automatically.
