# Capturing stock's VideoInfo — located, method proven, boot pending

The VideoInfo dma-buf is the last input to the display firmware that we
construct blind. We know one field we send is wrong (we ask for format 6, the
firmware programs 4, stock plays at 0), and forcing fmt 4 onto stock produced a
tiled half-height picture — so it is demonstrably wrong for NV12 rather than
merely different. Everything else in the 0x104-byte structure is unverified.

Two things that used to make this a vague task are now settled, both without
touching the board.

## 1. The page is already located, from captures we had

DECD writes the VideoInfo physical address into a per-slot register. From
`dec_reg_set_address()`, `info_off[] = {56, 60, 64, 68}` relative to
`regs->workaround`, and that base is `0x05600060`:

    slot 0   0x05600098
    slot 1   0x0560009c
    slot 2   0x056000a0
    slot 3   0x056000a4

The same table gives Y at `+16` = `0x05600070` and C at `+36` = `0x05600084`,
which are the known Y/C bases — so the offsets are anchored, not guessed.

Those registers are inside the AFBD window the 2026-08-28 stock captures already
dump, and they were sitting there unread:

    state       0x05600098..a4
    playback    all four = 0x4D945000
    idle        all four = 0x4D95A000

Page-aligned, and identical across all four slots while Y/C cycle a ring —
consistent with per-stream metadata rather than per-frame. So the capture does
not need a hunt; it needs a read of one known page.

**Read the register live rather than reusing `0x4D945000`** — it is an
allocation and will differ per boot.

## 2. /dev/hidtvreg will map it — it is a general physical-memory window

The open question was whether `/dev/hidtvreg` can map DRAM or only MMIO. It maps
anything. `hidtvreg_dev.ko` was carved out of the board-B eMMC capture
(`bench_emmc_full.img` at offset 1375608832, 7940 bytes, ELF32 ARM, not
stripped; the vendor init script loads it from
`/vendor/lib/modules/hidtvreg_dev.ko`). Its entire mmap handler is 44 bytes:

    ldr r2, [r0, #0x4c]     ; vma->vm_pgoff -- caller-supplied
    bl  remap_pfn_range

No whitelist, no bounds check, no pfn_valid. It forces VM_IO and a noncached
prot and passes the caller's page frame straight through. Noncached is what we
want anyway for a page the firmware writes.

So the existing `tools/display/hidtvreg-read.c` works unmodified — it already
takes an arbitrary address and mmaps `page >> 12`.

## Procedure, once the board is on stock

Build the reader (static, no libc, runs on the 32-bit Android userspace):

    arm-linux-gnueabi-gcc -Wall -Wextra -Os -nostdlib -static -fno-builtin \
        -fno-stack-protector -Wl,-e,_start \
        -o hidtvreg-read tools/display/hidtvreg-read.c

Then, with a clip actually playing and confirmed on the panel:

    ./hidtvreg-read 05600098 4        # live VideoInfo page address
    ./hidtvreg-read <that addr> 41    # 0x104 bytes = 65 words

`0x104` bytes is the structure HWC copies to offset 4096 of its 32 KiB metadata
allocation; magic is `0x61770000`, which is the first thing to check in the
dump. Capture the idle case too — the idle slot holds a different page, and the
diff between idle and playback is itself informative.

Operational notes that cost time before: the vendor player silently refuses a
video-only file ("Video Problem: Do not support this video"); mux a silent AAC
track. Files pushed to `/sdcard` land `-rw-------` under a FUSE uid that
`chmod` cannot change, so scan with `MEDIA_SCANNER_SCAN_FILE` and launch the
resulting `content://` URI. `pidof`/`ps` will not find the player on this build
even while it runs — trust logcat.

## What is still blocking

Only the boot. Switching to the vendor stack is `run switch_vendor` at our
U-Boot prompt plus a power cycle, and coming back needs the FEL button — both
physical. The 2026-08-26 attempt did not boot (red→blue LED, zero UART),
recovered cleanly via FEL, and cost about an hour for no data; check the restore
SPL is current before switching. Stock did boot successfully for the 08-28
captures, so it is achievable, but it is not a cheap operation and it needs an
operator.
