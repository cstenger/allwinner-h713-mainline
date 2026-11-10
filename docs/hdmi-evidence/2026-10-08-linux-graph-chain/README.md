# 22-word graph-chain trial, attempt 1: DSP read timeout, 2026-10-08

Attempt 2 succeeded: see [attempt2/README.md](attempt2/README.md).

Result: **aborted before the chain was applied.** No capture result. The
board was cold booted by the operator and stopped at U-Boot. The startup
recipe was the same as [the stock-graph trial](../2026-10-08-linux-stock-graph/README.md):

- `cold-start.log`: guarded first MIPS launch, firmware and application
  readiness proven, channel 0 live with pid 8b8f275c (re-read on this boot).
- `source3.log`: source 3 worker transition complete (old 0, new 3).
- `fit-check.log`, `ram-dt.log`: preserved FIT, embedded DT size 8319. IRQ order
  corrected to 115/113 in the RAM copy only. The live
  `/proc/device-tree` confirms it (`staged.log`).
- `linux-boot.log`: same 6.18.38 #1 kernel. `linux-preparation.log`: source 3 and
  canaries verified, holds on.
- Host `/tmp` was lost in an unrelated host shutdown. TVFE-hold and
  bridge-trial modules were rebuilt from the same sources against the same
  kernel build and are **bit-identical** to the recorded builds (8f32cf93...,
  1e137200...). The DSP probe is the `graph_chain` build, SHA256 0bcee8b8...
  (`dsp-build.json`). Its compiled table was checked to hold 22 entries.
- `audio-setup.log`: same bridge/AudioTop/SPDI1 setup, private DMA
  0x76c60000, CONFIG 2207, IRQ 336 = SPI 147 (bridge). Cold DSP versions 0/0.
  `graph_chain=Y`.
- `dsp-patch.log`: fixed 724-pair patch, versions 1/1, no timeout.

## What failed

`dsp-graph-dmesg.log`: all 22 words were read and saved without error. Then
0003 (0000->0300), 800c (0000->0080), 800d and 00ac were written and verified.
The write of 0077 (target 1617) was issued. Its **readback** timed out in
phase `completion-clear`, status 00000120: the done bit did not drop within
the probe's 100 us window. The probe latched `failed` and released the stock
lock. No further DSP command was sent. 0077 is probably 1617 now; the other
18 words were never written. The saved cold values were not logged; they are
printed only per write.

Cause, from stock `snd_alsa_trid.ko`: `aud_dsp1_read_reg` waits busy-clear,
writes the command and polls done-set for up to 49999 us. It never requires
done to clear, and has no 100 us limit. The probe's 100 us clear check is
probe-invented. The 0077 write reconnects module 8400's input, which
plausibly delays the DSP's next command service. The previous 13-word run got
through the same write by luck of timing.

## Probe fix (built, not yet run)

`dsp_read` keeps the stale-response guard (done must clear before it is
trusted as set). If done has not cleared after the 100 us atomic window, it
keeps polling for the clear in sleepable mode, within stock's 50 ms budget.
All other DSP waits are also raised from 10 ms to stock's 50 ms. Each
slow clear is logged with its duration. A clear-then-set that falls between
two sleepable polls gives a timeout, never stale data. New build SHA256
8b5c8e643421837b6216ee37ec62fb7c0b9c79aeed9593f7497c97cc63e9acdc.

## Side observation

With only 0003/800c (and probably 0077) applied and DTVOUT1's selector 0130
still cold, the bridge still ran: 7,572 IRQs, the whole 64 KiB buffer
overwritten (`cleanup.log`). In the direct-bd trial (0130=1617, without 0003/800c)
there were no IRQs. So bridge activity follows 0003/800c, not the route.
That means "no IRQs with 0130=1617" can't be used to infer that I2SIN1 is
dead.

## Restoration

DSP words could not be restored, because the failure latch blocks further
commands. As required, the probe was not reloaded. The DSP, bridge and TVFE
modules were unloaded. SPDI1, output stream 0, AudioTop, the IHB clock and
TVFE state were restored. MIPS `help win` responds. Only the base
receiver-power and EDID holds remain. A physical cold boot is required before
the next DSP trial. It clears the patch and the partial graph.
