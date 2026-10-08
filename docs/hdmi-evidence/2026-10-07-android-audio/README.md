# Android HDMI audio comparison: audible stock baseline captured

Historical October 7 session: current boot state and capture conclusions are
superseded by [the October 8 handoff](../../handoff-2026-10-08-hdmi-audio-capture.md).

The user authorized the Android register/code comparison. Both OS stacks are
resident: Debian is ext4 partition 26, Android userdata is separate f2fs
partition 27. Android boot and super partitions remain intact. No repartition,
reclaim, factory reset, kernel replacement or vendor firmware patch was done.

Before switching, the exact current Linux first stage was backed up as
`linux-spl-before.bin` (32768 bytes), SHA256
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
It is byte-for-byte present in `build/out/h713-restore-spl.bin`, validating the
existing FEL return path. Do not regenerate from a different build.
The vendor boot0 at LBA256 matched the saved board-B image, had a valid eGON
checksum, and has SHA256
`b769a41514fe784ead77ff59738a88c97588784a5d425f879c84cfd84a39a817`.
The first 4096 bytes of misc are backed up without changes.

`tools/stock/vendor-elog-cfg.sh on` changed only the two known guarded config
bytes on bootloader_a to mode 2/level 5, verified by the complete-file hash.
This can prolong stock initialization by about three minutes, as observed in
the previous stock session. Restore with `off` after returning to Debian.
The MIPS binary remains original; identity must be verified from live DRAM.

The verified vendor 64-sector first stage was copied from LBA256 to LBA16,
fsynced, and fully read back. `vendor-switch.log` records verification.
Linux U-Boot proper and both OS partitions remain untouched. The current
running Linux/MIPS state is unchanged until physical power cycle.

The user has been asked to unplug OTG (prevents back-power), physically
power-cycle, wait for the Android launcher, and reconnect USB. HDMI stays
connected. If recovery appears, choose Try again, never Factory data reset.
No adb device was present at the last check.

Next steps after Android is ready:

1. `adb devices -l`, fingerprint, /dev/hidtvreg permissions.
2. Push existing read-only hidtvreg-read/raw, stock-capture.sh, and new
   tools/stock/hdmi-audio-snapshot.sh into /data/local/tmp/cap.
3. Verify live firmware text and loaded cfg using stock-capture.sh fw.
4. Capture idle log/DRAM/clock state. Select Android HDMI1 using its normal UI
   or verified activity and capture lock, then host stereo 48-kHz playback.
5. Correlate buffered firmware SetAPLL/power-up records with the known
   AudioTop/SPDI/bridge register offsets and /proc/interrupts deltas.

The new sampler fails closed on TVFE/TVCAP power, demod reset/bus gate and
audio clock gates. It reads only the exact audio status/control offsets
already sampled by the Linux audio probe; no FIFO reads, IRQ clears or writes.
No ARM reads of receiver, wrapper, 069xxxxx or 0709xxxx are permitted.
MIPS DRAM cache fields are explicitly marked potentially stale. Firmware
logs supply positive code-execution evidence; missing records are inconclusive.
Initial comparison uses the unmodified stock firmware and buffered logs;
direct PLL reads need a separately verified firmware-side output path.

Return: physical FEL entry, external/sunxi-tools/sunxi-fel version, then
external/sunxi-tools/sunxi-fel -p spl build/out/h713-restore-spl.bin; verify
RESTORED-OK on UART, cold boot Debian, verify exact LBA16 and U-Boot hashes,
and turn vendor elog off. The board is currently configured to boot Android.

## Live result, October 7

The user cold-booted Android. UART showed continuous CPU_COMM APPready waits
until about 182 seconds; Android recovered to the launcher. Serial reported
sys.boot_completed=1 and adbd running. USB adb then connected normally.
No recovery reset or register intervention was needed.

The loaded firmware text matched board-B display.bin[0x10000:0x20000], and
loaded config confirmed mode 2/level 5. Android's normal AwSource UI selected
HDMI1, opening awlivetv and a HW1 TV-input session. The host initially read
disconnected, then connected/enabled; the user confirmed Cosmic showed three
displays and a live cursor on the projector. Firmware positively logged
1920x1080 lock. Stock EDID/ELD is SGD SX8, distinct from the Linux canonical
EDID. The dynamic endpoint finder selected hw:0,8.

A bounded 20-second 48-kHz S16 stereo tone (L=1kHz, R=2kHz) completed with
aplay success. **The user heard the tone from the projector speaker.**
The attempted follow-up 60-second file was refused by the tone generator's
30-second limit, so no follow-up playback occurred.

The firmware positively logged N=6144, Fs=48000, CTS=185625. The guarded
live object walker found Android's HDMI1 object at 8b831460, eight bytes
below the Linux allocation. Its gate was active and cached PLL history was
zero; cached history remains inconclusive because of MIPS D-cache. The
snapshot shell's earlier hardcoded DRAM samples are invalid for Android
allocation and must not be interpreted. They were removed from the script;
only live-audio-cache.json uses the guarded pointer walk.

The initial register guard used the superseded bit-0 bus model and skipped
peripheral reads. It was corrected using the vendor descriptor evidence in
docs/hdmi-tvcap-clock-validation.md: HDMI-audio bit31, cap-300m bit30.
No clock register was changed. Both domains, reset and all required clock
gates passed before the subsequent audio interface reads.

During the audible trial, AudioTop CTL=700/CFG=011a5e00, while SPDI1 controls
and status were zero. Audio Bridge output stream 0 was also all zero; bridge
global IRQ enable=1, mask=0, status=3cf. All six Android ALSA capture streams
were closed. This establishes that audible stock speaker output does not
require the SPDI1/output-stream-0 configuration tried by the Linux probe.
It does not prove that no other bridge stream or input interface is active.

Stock audio HAL positively logs hdmi_input=on, create_audio_patch(source=1,
sink=1), connect_hdmiin_path, and Sound_Connect changing route 71->89.
The exact running audio.primary.ares.so differs from the older extracted
copy, so use the saved running binary (110844 bytes). Thumb disassembly at
9818 confirms route 89 for this HDMI PCM speaker branch; Sound_Connect at
11364 reaches Thal_Sound_Connect. The exact libhalsound, libmspsound,
libmsp_util and libmspdriver are saved for continued offline tracing.

Candidate DSP operations recovered from libmspdriver: HDMI RX enable uses
logical DSP word 8034 with mask90/value10, and HDMI I2S mute uses word8017
mask1. These are library code evidence only; execution/argument timing has
not yet been established. Do not write these values on Linux without tracing
the kernel/DSP address translation and ownership. No direct stock PLL MMIO
read has been made. The Linux PLL state is therefore not yet a confirmed
unique blocker; prioritize the successful stock DSP/input route.

All captures, logs and exact binaries are on the host. Android remains live
on HDMI1, original vendor display.bin unchanged, verbose logging enabled.
The vendor boot entry is still at LBA16. Return to Debian still requires the
verified FEL restore and physical cold boot described above, then elog off.
No Linux boot entry restoration has yet occurred.


## FEL return attempt

The user placed the board in FEL. `sunxi-fel version` positively identified
soc 00001860/H713, scratchpad 00121500. The existing, previously proven
65536-byte restore payload (SHA256
02147d8e5edb6a2810e67066d1986f5663cdb73e35d51dd30c4ebe550e349276)
contains the exact backed-up 32768-byte Linux SPL. The `spl` transfer stalled
without UART output or RESTORED-OK. Its host client was terminated after the
stall; a subsequent bounded FEL version query also timed out. Empty logs are
retained as fel-restore.log and fel-restore-uart.log. This does not establish
whether any eMMC write occurred. The restore remains unconfirmed; a fresh
physical power-on into FEL was requested before a bounded, traced retry.


## Return verified

The user powered on normally and stopped at our U-Boot. Booting from that
prompt reached Debian/Linux 6.18.38 with SSH available. Full eMMC readback
SHA256 verified the restored 64-sector SPL at LBA16 as
cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec,
and all 1798 U-Boot proper sectors at LBA4828160 as
c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7.
Both match the pre-trial originals. Thus the restore completed despite the
host stall and missing UART marker; the earlier uncertainty is resolved.
Vendor elog was then disabled with the guarded helper, which verified the
complete display_cfg.xml hash returned to its exact stock state. Evidence:
linux-restored-verification.txt and elog-disable.log. Board is now in Linux;
this boot reports MIPS parked. Further capture diagnostics require the
established cold-start procedure rather than a live MIPS relaunch.


## DSP route recovery after the standby work

On resumption the checkout was at 63e88e2, with the IR, s2idle and poweroff
commits present. SSH showed Linux 6.18.38 built Oct 7 18:57:16 PDT, systemd
running, MIPS parked, no HDMI audio probe loaded. No hardware audio accesses,
MIPS launch, suspend, or power changes were made in this analysis.

The live board's super LP header and table checksums were validated. Its
vendor_a extent is 223408 sectors starting at sector1921024 of mmcblk0p9
(byte offset983564288, length114384896). A temporary read-only loop setup
failed because Linux has no loop device support; no loop was attached.
The extent was copied to a host /tmp image and read with debugfs, with no
filesystem mount or board storage writes. Exact sound_preset.bin and
libUtility.so are saved here. Preset SHA256 is
babda009400d6c4e7e3e7981e9fe398ffcfc5222fbc25f98b08c5ec525e59604.
It matches the older extracted preset. The freshly extracted libmspdriver
and libmspsound match the previously adb-pulled binaries exactly, independently
confirming this library/preset pairing.

`tools/stock/decode-sound-route.py` decodes the PHDR/GRAF mux tables and
resolves selected virtual muxes to terminal module/port pairs. The four
routes in decoded-sound-routes.json were independently checked by executing
the actual libmsp_util BP_AUD_Init and BP_AUD_GetMuxDirector functions in
Unicorn, with a real bounded strncmp stub. All 8/8/2/2 selections matched.
The MSP emulator initializes its module descriptors and intercepts all DSP
writes and the hardware ownership handshake. Every routing call returns
success and reaches the return trampoline; no instruction-limit result is
accepted as completion. This is code evidence, not a runtime MMIO trace or
full graph/device initialization.

MAPI_AUD_SetSourceSelectPort takes DESTINATION module/port first, then SOURCE
module/port, plus an optional error-output pointer. Earlier exploratory calls
reversed these and returned -1; they are not evidence against the route.

| route | preset input | terminal connection | DSP logical selector |
| --- | --- | --- | --- |
| 0x71, previous DTV game speaker route | decoder 0x9400 ports0/1 | surround decoder0x8400 ports0/1 | 0x0077 -> 0x3a3b |
| 0x89, observed audible HDMI speaker route | I2SIN1 0x9600 ports0/1 (preset calls this HDMI2 PCM) | surround decoder0x8400 ports0/1 | 0x0077 -> 0x1617 |
| 0x80, CAPTURE_HDMI_PCM | I2SIN3 0x9602 ports0/1 | DTVOUT1 0x9500 ports0/1 | 0x0130 -> 0x2627 |
| 0xbd, PATH_CAPTURE_HDMI2 | I2SIN1 0x9600 ports0/1 | DTVOUT1 0x9500 ports0/1 | 0x0130 -> 0x1617 |

Each stereo word is set by two masked calls, high byte ff00 then low byte ff.
The 0x71 and0x89 routes share downstream selector0x0118 ->7c7d and
0x0020 ->2e2f (I2S output). The library's internal DSP input index/name is
not the physical connector label: Android selected HDMI1 while using0x89.
Capture0xbd is a matching candidate; it has not been executed on the board.
Only the selectors above are recovered, not the complete processing graph.

`tools/stock/decode-audio-dsp-init.py` executes the exact captured
sound_lowlevel_init and the first patch-download stage entirely offline.
With zero initial MMIO it produces AudioTop CTL0700, CFG001a5e00 then
011a5e00; actual hardware top bits are retained by read-modify-write.
It calls DSP clock speed3, Enable_HDMI_Rx(NULL), and HDMI I2S mute1.
The first Enable_HDMI_Rx parameter is an error-output pointer, NOT enable:
the function unconditionally sets logical8034 mask90/value10.

The patch path writes logical fff7=0 and0000=0, then streams all724 big-endian
(address,value) pairs embedded in patch_msp. The independently decoded blob
and emulated calls match pair-for-pair. audio-dsp-patch.bin SHA256:
8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5.
The saved trace stops before hardware version checks; no readiness result
was fabricated. Stock logcat positively shows downloadpatch start/finish,
but does not provide a runtime patch-write capture.

DSP logical words are NOT physical MMIO offsets. aud_dsp1_write_reg atced8
polls AudioTop06144000 bit4 and writes packed address/value at0614400c.
aud_dsp1_read_reg atd18c writes address<<16 at06144010, then waits for
06144000 bit5 and reads the low16 bits from06144010. Its completion wait has
no timeout. A Linux diagnostic must bound both waits. The outer MSP access
layer also coordinates a 55/aa ownership protocol at02031078 (user) and
02032078 (kernel); this must be understood and preserved before porting.
Do not blindly replay patch data or send selectors to the running board.

Next live work should establish audio DSP readiness and bounded logical
register readback, then the DTVOUT-to-memory path. The prior SPDI1 probe
cannot validate this route. Display MIPS remains parked; start the next
receiver trial using the established physical cold boot at U-Boot, rather
than relaunching it from the live Linux prompt. Preserve the newer standby
kernel and rootfs work.

Correction, 2026-10-08: the Linux probe must not use the 02031078/02032078
addresses mentioned above as an ownership handshake. Those are internal I2S
and daudio registers. Stock kernel REG_Init maps 05001530/34 for the real
WaitDSPFree/ReleaseDSP lock. The corrected bounded probe was tested successfully;
see ../2026-10-08-audio-safety/. This Android session established a working
speaker path, with every ALSA capture stream closed, not a capture baseline.
