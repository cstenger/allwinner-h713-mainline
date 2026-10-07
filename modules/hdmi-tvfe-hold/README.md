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

It refuses an inherited active demod bus/reset state. On an accepted guarded
boot it:

1. saves every affected CCU word and the TVFE initialization word;
2. deasserts the named shared reset while the demod bus remains gated;
3. waits 10--15 ms, matching stock;
4. holds the video0 and ADC parent PLLs;
5. applies the fifteen exact functional-clock words common to four independent
   stock captures;
6. enables the demod bus last and waits again;
7. writes and verifies the stock `0x003003ff` TVFE initialization word.

Failure and module removal restore the TVFE word, all CCU words, parent clock
references, and the reset state. The module touches no HDMI audio registers,
IRQs, DMA, or FIFOs. It must never be autoloaded.
