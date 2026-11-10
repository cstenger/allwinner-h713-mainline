# What backs the DSP lock words — offline investigation, October 21, 2026

**Status: offline analysis; no hardware access.** Follows the
[version-stage run](hdmi-evidence/2026-10-21-dsp-access-version-live/README.md).
In that run, in the fully routed logo-free state, the ARM lock word
`0x05001534` accepted a `0x55` write without a hang but read back
`ffffffff`.

## Observations to explain

| State | Lock words before claim | Claim (own ← `0x55`) |
| --- | --- | --- |
| MIPS-live production path, 2026-10-08 ([audio safety](hdmi-evidence/2026-10-08-audio-safety/README.md)) | both `0` | sticks; release reads `0xaa`; versions read `1/1` |
| Logo-free, TVTOP routed (`cold-tvtop-01`) | both `fffffffe` | not attempted |
| Logo-free, TVTOP routed (`cold-version-01`) | both `ffffffff` | write completes, reads back `ffffffff` |

Cold logo-free values vary between boots and ignore writes. That is the
signature of storage that is not yet functional (unclocked, held in reset,
or not mapped behind the routed port), not of a register with a defined
reset value.

## What the code says

1. **Only ARM-side audio code references the lock.** Stock `snd_alsa_trid.ko`
   maps `0x05001530`, 8 bytes (2026-10-08 audio-safety evidence). Our probes
   copy it.
2. **The display MIPS firmware never addresses it.** `display.bin` (board B,
   little-endian, base `0x8b100000`) has 45 `lui 0xba00` sites. None is
   followed by `0x1530`/`0x1534`. Across all loads/stores/address arithmetic
   in the image, the only `0x1530` immediate is a log-string pointer at
   `0x8b12b430`. The one `+0x534` site is composition geometry at
   `0xba000534` = ARM `0x05000534`, not the lock.
   - **The scan could have seen it:** the same method finds 30
     `lui 0xba60` + `0x0010` AFBD sites.
   - **So the DSP-probe header's "MIPS peer is `05001530`" is an inherited
     assumption.** No firmware code backs it. The peer may be the audio DSP
     or another agent, or nothing that runs in a logo-free boot.
3. **The vendor display tables never write the `0x0500xxxx` page.** Parsing
   `LogoRegData.bin` with `h713_logo_walk`'s exact record and resync rules,
   the board's prologue 3, timing 6 and DE 5 make 32 + 32 + 55 writes. None
   is in `0x0500xxxx`, and neither does any table anywhere in the container.
   - **The parser is verified:** it reproduces prologue 3's 17 TVTOP writes.
   - **The composition block is programmed only by the running MIPS
     firmware.** It writes the global words `0x05000004`, `0x05000018`,
     `0x05000030` and `0x05000040` (15–22 sites each) and the geometry pages.
4. **The vendor prologue applies TVTOP differently from `prepare`.** It
   writes `+0x00`/`+0x04` as `ffffffff`. It cycles the port words `+0x40`,
   `+0x44`, `+0x80`, `+0x84` and `+0x88` to `0` and back. It uses
   `+0x84 = 00f00000` where `h713_display_prepare` uses `fff000ef`. This is a
   recorded difference, not yet a candidate.
5. **No MIPS-live capture of the composition global words or of the
   `0x050015xx` page exists.** The 2026-08-31 capture stops at `0x0500087c`.
   Its `0x03540030`/`0x05000030` pairs are *values held* in `0x05000844`/`0x0500085c`.

## Ranked candidates

1. **The composition block is not running.** The lock words may sit in a
   register file or SRAM of the composition block (or a block behind the same
   port) that reads as ones and ignores writes until the block is enabled or
   out of soft reset. In production the running MIPS does that through its
   global words. *Supported by:* the varying all-ones reads; the firmware
   being the only writer of the page; production working only MIPS-live.
2. **The mixer control word `0x0525c038 = 00000100`.** `prepare` writes it
   and the TVTOP stage omitted it. *Weaker:* it is a mixer register, not the
   composition page.
3. **The vendor prologue's routing cycle and `+0x84` value** differ from
   `prepare`. *Weaker:* routing already made the page readable.
4. **The lock is a mailbox owned by another agent** (the audio DSP or SCP),
   functional only once that agent runs. *Not excluded* by any code read here.

## What would discriminate cheaply

A **read-only census of the composition global words** (`0x05000000`–`0x05000044`)
and of `0x05001500`–`0x0500153c`, taken in two states:
- the routed logo-free state (the TVTOP stage's end, which is proven safe to
  read the `0x050015xx` page);
- a normal MIPS-live production boot, where reads of this page are routine.

A logo-free global word that differs from MIPS-live (for example a
zero enable or a reset bit) ranks candidate 1. Equal global words with
differing lock behaviour push towards candidate 4. Neither state changes
DSP protocol state.

## Strategic note

Each logo-free stage has had to reconstruct something the MIPS/logo path
provides: TVCAP power and reset, TVTOP routing, and now a functional lock.
The user's goal is warm-reboot recovery of the *production* path, where the
lock works. The question that matters is the reset contract: does the DSP
patch (versions `1/1`) survive an orderly or abrupt warm reset? That can be
asked more directly on the MIPS-live path, by reading versions with the
stock lock after a warm reset from a patched state. That needs its own design
under the guard and GP6 rules (warm branches park MIPS). The logo-free bench
remains valuable for cold-state census and as a hang-safe method, but may
not be the right vehicle for the version question.
