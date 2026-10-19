# Stock interface settings added to speaker split trial

Historical October 8 run. The later [bench cleanup](../../../modules/hdmi-speaker-split/README.md)
adds offline failure checks and runner fixes; those changes have no new acoustic
result. The raw offline `speaker-init-code.json` trace referenced below remains
local research material.

Operator was ready before the run and reported **control beep only** afterward.
Host played the 48 kHz stereo 1/2 kHz tone successfully (exit 0), with canonical
EDID and receiver state 5 at 1280x720. All six tone snapshots reported RXCNT=0,
ISTA=0, FSTA=0x100, CTL=0x13. No codec I2S reception was observed. These counters
have not been independently calibrated; this is not proof of absent BCLK or
absent HDMI input to the DSP.

The corrected stock cross-processor lock was used for every DSP command.
Route words 0077=1617, 0118=7c7d, 0020=2e2f, output 001e=a440/001f=3000,
input 0012=8180, and HDMI mute 8017=0 all read back successfully. The previous
trial's output words were zero and input format bits were missing. The stock
initialization trace is in ../2026-10-08-audio-safety/speaker-init-code.json.
This trial did not reproduce every stock processing-graph/gain/effect setting.

The runner finished with empty cleanup.json. Module unload restored all seven
DSP words with verified readback, and all nine codec I2S configuration registers
plus DAC-source bits. restore.log records the original codec CTL 0x60010 and
DAC_DPC 0. ARM lock is released at 0xaa, peer is 0, clock words match stock.
MIPS help win responds after restoration (mips-after.log). The first attempted
post-run MIPS check used a nonexistent executable; it did not access hardware.
The correct existing shell script was then used successfully.

No bridge/DMA trial, bootloader write, kernel installation, power-domain change,
DSP firmware upload, or MIPS relaunch was performed. The next discriminator is
stock Android capture plus known-working internal I2S configuration snapshots.
