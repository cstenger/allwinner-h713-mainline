# Stock-order TVFE hold

This diagnostic module exists to cross the TVFE clock/reset boundary required
before accessing the H713 HDMI-input audio registers at `0x0614xxxx`.

It is intentionally separate from `h713-hdmi-audio-probe`. The first isolated
experiment enabled `CLK_BUS_DEMOD` before releasing `RST_BUS_DEMOD`; that order
hard-hung the board. The stock `sunxi_tvtop.ko` sequence does the reverse and
also configures fifteen functional clocks before enabling the bus.

The module therefore requires all three acknowledgements:

```sh
insmod h713-hdmi-tvfe-hold.ko \
  armed=1 live_source3=1 receiver_powered=1
```

It refuses an inherited active demod bus/reset state and also refuses a zero
live TVFE control word. On an accepted guarded boot it:

1. saves every affected CCU word and the TVFE initialization word;
2. deasserts the named shared reset while the demod bus remains gated;
3. waits 10--15 ms, matching stock;
4. holds the video0 and ADC parent PLLs;
5. applies the fifteen exact functional-clock words common to four independent
   stock captures;
6. enables the demod bus last and waits again;
7. preserves and verifies the nonzero TVFE control word established by the
   live MIPS receiver firmware.

The first stock-order version wrote the cold stock initialization constant
`0x003003ff` over the live firmware value `0x00111111`. That left MIPS alive
but prevented the HDMI receiver from advancing beyond state 3. Preserving the
live value restores stable state-5 1280x720 lock, so the cold constant must not
be used during a guarded live-source experiment.

Failure and module removal restore all CCU words, parent clock references, and
the reset state. The module touches no HDMI audio registers, IRQs, DMA, or
FIFOs. It must never be autoloaded.
