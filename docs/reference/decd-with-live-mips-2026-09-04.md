# DECD frame submit with a live MIPS still locks the SoC — 2026-09-04

The coexistence fix ([mips-shell-driven-2026-09-04.md](mips-shell-driven-2026-09-04.md))
got Linux booting with a properly handshaken MIPS. **Handing that MIPS a frame
through DECD still hard-locks the board.**

## The configuration, which was the right one

This is stock's own division of labour, and every precondition checked out:

```
h713_disp init 0x34                       # full bring-up, core left running
boot h713-kernel-decd-iommu-0076v3.fit    # dec@5600000 okay, display@5600000 disabled
```

On the booted system, before touching anything:

```
core           0x0306101c = 0x00000001    ALIVE
dec@5600000    okay          display@5600000  disabled
/dev/decd      present       /dev/dri      card0 (panfrost only)
oops 0         WARNING 0
```

So: DECD owns the frame handover, no ARM KMS driver is on the display, and the
MIPS owns composition — exactly the arrangement `decd.ko`'s register map implies
stock uses.

## What locked it

```
decd-client show /root/decd-test-frame.nv12 6000
```

A **single static 720p NV12 frame**, not a stream. Network and serial both dead,
power cycle required.

That is worth being precise about, because the standing note said *"real Cedrus
traffic + live display MIPS hard-locks the SoC; static frames with MIPS alive are
fine."* **The static-frame exemption does not survive.** It was recorded when the
MIPS had been cold-restarted with no handshake — in that state the window layer
was not really running, so nothing contended. Now that the core is genuinely
live and driving the WCE, a static submit is enough.

## The likely mechanism, labelled as inference

Both sides program **AFBD source 0**. The MIPS's `NRWinNode` slot 4 writes the
source geometry and commits through `0x05600014`/`0x0560006c`, and our DECD
driver writes the same registers plus the IOMMU master-2 flip. On stock the two
are coordinated — HWC submits through `/dev/decd` *and* the firmware is told
about the frame through the VideoInfo descriptor and CPU_COMM. Ours submits
blind.

So this looks like genuine two-owner contention on `0x05600000`, which is a
different thing from the boot-time lock that turned out to be an un-handshaken
core. Not established.

## Method failure worth fixing before the next attempt

**The elog of the fatal moment was lost.** A baseline was captured
(`/root/elog.before.txt`, 2191 lines) but the "after" never was, and the buffer
lives at `0x4b272000` inside the firmware window that U-Boot reloads on the next
boot — so a power cycle destroys exactly the evidence that mattered.

**Fix: stream the elog to the serial console rather than reading it afterwards.**
A background loop on the board doing `python3 /root/elog-dump.py > /dev/console`
every second puts each dump on the UART as it happens, where the host's serial
capture keeps it through the lock. That is the same trick that made the
`/dev/kmsg` narration work for the release sequence, and it should have been
applied here.

## Where this leaves it

The three preconditions are now all individually solved — Linux boots with the
core alive, the shell answers, the firmware log is readable — and the fourth,
getting a frame to the live window layer, is not. The next attempt should:

1. stream the elog to the console first, so a lock still yields the WCE's last
   words;
2. try `decd-client blue` (DECD's internal generator) before a real frame, which
   removes the buffer and the IOMMU from the picture entirely;
3. consider that the missing coordination is the **VideoInfo descriptor plus a
   CPU_COMM notification**, which is what stock pairs with every submit and what
   we have never sent.
