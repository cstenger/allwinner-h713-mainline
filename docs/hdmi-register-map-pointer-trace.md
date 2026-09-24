# Receiver-map correction and bounded MIPS pointer trace

The board-B MIPS display firmware census identifies `0x050c0000` as DETN
display noise reduction, `0x05000000` as display composition, and
`0x05040000` as a picture-quality measurement tap. The earlier HDMI notes
misidentified these windows as HDMI RX, PHY, and THDMIRX. The experimental
`h713-thdmirx-init` module's prior writes and its constant read-only samples
therefore say nothing about receiver enable or TMDS lock. Historical raw
measurements remain in place, with correction notices in the related notes.

The module now returns `-EOPNOTSUPP` for `apply=1` before requesting or mapping
the DETN region. It compiled against the installed merged Linux 6.18.38 tree.
The verified no-write module (SHA256
`8643031ae6dd4707d810dd3596f1c98dad99a1a9518c030f7f85a52c2e8878c8`)
replaced the staged `/root/hdmi-diagnostic-merged/h713-thdmirx-init.ko` on the
projector; the former staged binary was renamed `.retired-detn`. On the
running kernel, `insmod ... apply=1` returned “Operation not supported”, the
module remained unloaded, and the kernel logged `refusing writes`. The board
remained reachable. `check-power.sh` labels those historical safe reads DETN.

For source selection, the existing U-Boot trace shows that the SetSource
adapter received request 3 and returned while the source callback/worker
markers stayed at startup source 1. The firmware's dispatcher loads its
callback object from cached MIPS address `0x8b253578` and returns success
even if that pointer is null. The live pointer has not yet been observed.
The guarded trace now takes one snapshot of that exact pointer at adapter
entry into trace slot `+0x60` before tail-calling the original SetSource
implementation. Existing requested-source, return, callback, and worker
markers are unchanged. The 407 guarded patch words have unique addresses;
the offline relocation audit found the expected 60 trace bases and 73 stores.
`read-comm-trace.py` verifies the new trampolines before reading the slot.

The board's normal `hy200_qz713df_a1_defconfig` produced a FIT image at
`build/uboot-pointer-trace/u-boot-sunxi-with-spl.fit.fit`, 920,169 bytes,
requiring 1,798 sectors. SHA256 of the image is
`87071df67e2a927e3229790a0b3e862968091011690fc5f991392105966ec2d9`;
SHA256 after zero-padding to the sector boundary is
`ce3192fe2f10ad882b69f413038d4c632b9cc3f25450095288034e04e8129920`.
`mkimage -l` recognizes its AArch64 U-Boot, ATF, and board FDT. The first
attempt used the FEL recovery defconfig and was discarded; it lacked the
recovery payload header and is not a boot candidate.

**Pending device test:** With separate approval, back up the 1,798 sectors
at the established U-Boot-proper LBA `0x49ac00`, write only the prepared
image there, and verify all sectors by read-back. SPL at LBA `0x10`, U-Boot
environment, and the installed merged kernel are outside that range. After
a physical power cycle, run `h713_disp mips-comm-trace 0x34` once and issue
one early `THal_Vp_SetSource(3)` CPU_COMM call. Record callback-object
`+0x60`, adapter, callback, worker, and RETURN markers. Do not make a second
traced MIPS startup on the same power cycle. A failed boot could require FEL
recovery; a MIPS lock could require another physical power cycle. Receiver
MMIO remains untouched until its address and bus owner are established.
