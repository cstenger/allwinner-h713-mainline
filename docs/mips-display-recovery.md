# MIPS display recovery plan

This plan recovers the H713 bench kernel first, then brings up the display
coprocessor one dependency at a time. It deliberately separates "the kernel
boots" from "the MIPS firmware starts" and from "ARM/MIPS RPC works." A build
that merely links is not evidence that the shared-memory protocol is safe.

The DDR3 `HY200_QZ713DF_A1` bench board is the only target in scope. Do not
flash these experiments to the untested LPDDR3 projector board.

## Current status (2026-07-27)

The reviewed end state deliberately moves MIPS boot ownership out of Linux:

- the active Linux 6.18.38 series contains 31 patches; Gemini's 910-line
  `sunxi-mipsloader` patch and the later read-only MMIO observer are removed;
- the kernel, modules, both board DTBs, and bench FIT build from a fresh
  extraction;
- NSI, CPU_COMM, TVTOP, DECD, and GE2D remain disabled;
- the compiled bench DTB contains one MIPS object: a no-map reserved-memory
  pool at `0x4b100000+0x0e41000`. It has no MIPS platform device, boot-vector
  property, clock/reset handle, or control-register address;
- the linked kernel has no loader/observer symbols and Linux creates no
  `/dev/mips*` device;
- no display firmware is embedded in the kernel or root filesystem.

The current RAM-only kernel artifact is `build/out/h713-kernel.fit`
(7,701,060 bytes), SHA-256:

```
2791e08e4bc18f5b032829bb98ad869711e22ccbd9b1870b38cd0695cd66b067
```

Its embedded kernel and bench DTB hashes are, respectively:

```
3a5c27c37eabaef514a4a4b43e87d87cd4bca40ee5320aa60f7a74c35fe028e1
23d37712e9822d44152dcb93ef0923f6b382288bdfea85a3cae6ae7397df3ac7
```

U-Boot verified both hashes before the 2026-07-27 bench boot. Linux reached
the Debian root shell and `systemctl is-system-running` reported `running`.
The UART log showed four CPUs, the ext4 root, eMMC, RTC, Panfrost, Cedrus,
AIC8800, serial getty, hotspot, Bluetooth attach, and SSH coming up. The only
MIPS lines in `dmesg` were reserved-memory initialization; `/dev/mips*` did not
exist. This passed the point where the observer-equipped kernel had stopped
responding.

The observer-equipped FIT, SHA-256
`3ee4e49beef8671e3727df319b7f2f1e7c79b0f04b4d16fd417664f2f7a361ce`,
is rejected evidence and must not be reused. Although its driver performed only
a register read, the board stopped responding after Linux clock takeover. The
safety boundary is therefore stronger than "read-only": Linux does not map or
touch the MIPS control registers during this phase.

The factory cold-start sequence is substantially narrower. Reverse engineering
the stock U-Boot
`0a44d54b3683453765fdbda93744eb5510b8d68ce829d1b0481c2cf2844e28f0`
shows that it loads `display.bin` at ARM physical `0x4b100000` and writes that
physical address, not its MIPS KSEG0 alias, to boot-address register
`0x03061030`. It then drives the MIPS clock/reset registers as follows, with
12 ms between reset stages and 300 ms after release:

```
0x02001600 <- 0x80000002
0x0200160c <- 0x00000000
0x0200160c <- 0x00010000
0x0200160c <- 0x00030000
0x0200160c <- 0x00030001
0x03061030 <- 0x4b100000
0x0200160c <- 0x00070001
```

UART-controlled tests established the hardware boundary:

- Writing stock register `0x051c0010 <- 0x01800045` by itself stalled both
  ARM UART and USB ACM. This register belongs to the factory fast-logo/LVDS
  sequence, not the standalone MIPS reset primitive. A power cycle recovered
  the board, and the known-good kernel subsequently booted cleanly.
- Replaying only the MIPS clock/reset sequence remained stable and changed CPU
  status register `0x0306101c` from zero to one. Status one therefore proves
  reset release, not firmware readiness.

Static analysis supplied a separate execution witness. The reset path enters
at the firmware's MIPS BFC vector, executes `eret` to `0x8b1b0868`, and then
clears BSS from MIPS address `0x8b232c00` through `0x8bac7c28`. The firmware's
observed address translation maps these to ARM physical
`0x4b232c00..0x4bac7c28`. Witness address `0x4b600000` is inside that loop but
is the first word beyond the five-megabyte window cleared by U-Boot. The
command writes `0x4d495053` there, flushes that ARM cache line, releases the
MIPS, then invalidates the line before reading it. Only a firmware-owned store
is expected to turn the seed into zero.

The ownership boundary is now explicit: U-Boot proper loads, verifies, and
releases `display.bin` before Linux. SPL remains responsible only for DRAM and
normal boot prerequisites unless a specific clock/interconnect dependency is
later proven to require earlier setup. Linux must not reload or restart the
coprocessor; its eventual role is reserved-memory protection and post-boot IPC
or display management.

A manual U-Boot command implements this boundary without changing autoboot.
`h713_mips load` reads the exact 1,256,216-byte image from a filesystem, clears
the five-megabyte firmware window, and accepts only SHA-256
`16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9`.
Separate `verify`, `start`, `stop`, and `status` operations keep each bench
transition observable. Before reset release, `start` applies only the
bench-proven display PLL/module-clock, TVTOP-routing, and mixer prerequisites.
It deliberately excludes LVDS, PH pinmux, TVCAP, HDMI, and INCAP. `start`
requires both CPU status one and the independent BSS-clear witness; it returns
the core to reset if either check fails.

The first installed and hardware-tested DDR3 bench artifact containing the
execution-witness command was 844,537 bytes, SHA-256:

```
493c45149a84e528f04b4b5861853cbbff43543bbd7048602966aca7d920d1ce
```

The current installed DDR3 build incorporates the proven display prerequisites
and deletes the unsafe experimental `factory-start` path. It also disables the
MIPS clock in `stop` after asserting reset. It is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (844,537 bytes), SHA-256:

```
956a03a61693add8c281f6f2678609e8d427a972b0797a3bd09b22fd8428fef2
```

The command is compiled into U-Boot proper and is absent from SPL as designed.
It is enabled only in the DDR3 bench defconfig, not the projector defconfig,
and it is manual: the normal autoboot path remains unchanged.

Bench execution validated the negative and transition paths:

- uninitialized firmware was rejected and left reset/status zero;
- the known image transferred by YMODEM produced the pinned SHA-256;
- deliberately dirtied bytes beyond the image were cleared before start;
- `start` reproduced the stock staged reset transition and reported status one
  with physical boot address `0x4b100000`;
- on three fresh firmware loads, the BSS witness changed from `0x4d495053` to
  zero while status remained one, independently proving that the MIPS fetched
  and executed its firmware startup code;
- the running firmware modifies bytes in its loaded image. A second `start`
  without restoring a pristine image produced SHA-256
  `6a7a86d23be26a712c6af9671acfd06ed4bcdb1d7216fa89949f6fca3d2bccde`;
  the pinned-image check rejected it and kept the MIPS in reset. Every new run
  must therefore use `load`/`boot` or otherwise restore the pristine image;
- UART and USB ACM remained responsive during all three runs, and `stop`
  returned reset, status, and boot address to zero.

The first post-test Linux handoff stopped producing UART output during driver
bring-up. At that point `stop` had asserted reset but left MIPS clock register
`0x02001600` at `0x80000002`, unlike its cold-boot value of zero. A follow-up
build disabled that clock after asserting reset and was hardware-verified to
return clock, reset, status, and boot address to zero. Linux nevertheless
stopped at the same point after the start/stop cycle. The lingering clock was
therefore not the sole cause. Abruptly resetting active firmware may leave an
outstanding transaction or another display/interconnect register in a state
that reset does not unwind.

Do not treat `stop` after successful execution as a clean Linux handoff. The
intended ownership-model test instead loaded and started the MIPS in U-Boot,
left it running, and booted the protected-memory Linux image. A power cycle
remains the known recovery for a failed post-execution handoff.

The initial live-MIPS handoff reached Linux but stopped deterministically in
the Panfrost probe. Panfrost printed its 864 MHz core and 100 MHz bus clock
rates, then the machine stopped before the next, normally immediate GPU-ID
line. The same boundary occurred after an execute/stop cycle and with the MIPS
left running, so the stop implementation was not the root cause. MIPS startup
needed an earlier display-fabric prerequisite before Linux's first GPU MMIO
access.

A one-boot `modprobe.blacklist=panfrost` isolation test confirmed the boundary:

- the pinned firmware passed its hash and BSS execution witness and remained
  running across the Linux handoff;
- the kernel command line contained the temporary Panfrost blacklist;
- Cedrus, AIC8800, networking, SSH, serial getty, and the Debian root filesystem
  came up;
- `systemctl is-system-running` reported `running` with no failed units;
- Panfrost and DRM scheduler modules were absent, and Linux still created no
  `/dev/mips` device.

The blacklist was transient and was not saved to the U-Boot environment or
kernel image. A normal reboot after the isolation test removed the blacklist,
left the MIPS off, loaded Panfrost, reached `systemd` state `running`, and
reported no failed units.

Register isolation then recovered the missing prerequisite. SPL already leaves
the display bus clock/reset enabled, but the video2 PLL parent and the deint,
panel, SVP-DTL, and AFBD module clocks are gated. The safe pre-start sequence:

```
0x02001050 |= BIT(31)       # video2 PLL parent
0x02001db0 |= BIT(31)       # deint, cold divider preserved
0x02001db4 |= BIT(31)       # panel, cold divider preserved
0x02001db8 |= BIT(31)       # SVP-DTL, cold divider preserved
0x02001dc0 |= BIT(31)       # AFBD, cold divider preserved
0x02001dd8 |= BIT(16)|BIT(0)

0x05700004 <- 0x00000001
0x05700044 <- 0x11111111
0x05700088 <- 0x11111111
0x05700000 <- 0xfff11111
0x05700040 <- 0x00011111
0x05700080 <- 0x00001111
0x05700084 <- 0xfff000ef
0x0525c038 <- 0x00000100
```

With only those writes, the mixer remained readable, the MIPS passed its BSS
execution witness, and Linux booted with Panfrost enabled. Panfrost read GPU ID
`0x7093`, reported one shader and one L2, registered DRM minor zero, and created
`/dev/dri/card0` plus `/dev/dri/renderD128`. Debian reached `running` with zero
failed units. The same handoff passed first as a manual register experiment and
again from the installed cleaned U-Boot implementation.

The broader factory sequence is not safe to carry forward. A diagnostic
`factory-start` path containing PH, TVCAP, HDMI, and LVDS phases wedged after
MIPS release and has been deleted. Direct INCAP access at `0x06940000` wedges
independently even after reconstructing the display and TVCAP clocks and was
also excluded. LVDS registers become ARM-accessible once the display clock tree
is prepared, but no LVDS write is required for the proven Linux handoff, so
they remain out of `h713_mips`.

The specific claim that stock register `0x051c0010 <- 0x01800045` stalls ARM
UART and USB ACM is **withdrawn**. That observation predates
`h713_display_prepare()` and was a clocking artifact, not a property of the
register. Retested on the bench on 2026-07-28 with the MIPS held in reset and
only the prepared clock tree applied by hand:

- the whole LVDS window `0x051c0000..0x051c0057` reads back zero, so the block
  is idle rather than absent;
- `0x051c0010` is readable, and the stock write lands and persists — a
  subsequent read returns `0x01800045`;
- the write is repeatable: two back-to-back writes both completed, and no other
  register in the window changed, so it behaves as a standalone enable rather
  than the entry point of a state machine;
- UART stayed responsive throughout. An observed reset during the first attempt
  was the 16 s watchdog expiring (`wdt start` does not self-service), not a
  stall; re-running the whole sequence inside a single `;`-separated line
  reproduced the writes with no reset.

The cold module-clock dividers were captured in the same session and
independently corroborate the recovered frequencies: `0x02001050` is
`0x08003101` (N=49, 1200 MHz), and deint/panel `0x00000007` (÷8 = 150 MHz) and
SVP-DTL `0x00000005` (÷6 = 200 MHz) match the documented rates. AFBD
`0x00000000` (÷1) implies 1200 MHz, not the 600 MHz recorded earlier; treat the
AFBD figure as unverified. `0x02001dd8` already reads `0x00010001` cold, so
that line of `h713_display_prepare()` is a no-op against the current SPL.

The general lesson is that "this register wedges the interconnect" has meant
"this block was unclocked" every time it has been run down. Apply the same
suspicion to the remaining exclusions — INCAP at `0x06940000` in particular —
before treating them as hardware limits.

## Firmware startup trace (2026-07-28)

`h713_mips probe-trace` instruments the authenticated image with 671 volatile
word patches — code caves plus `j`/`jal` redirection — that store marker ids to
the firmware's uncached `0xae340000` alias, visible to the ARM at
`H713_MIPS_SHMEM_ADDR + H713_MIPS_TRACE_OFF`. Markers are streamed to UART as
they change rather than dumped after the poll loop, because the failure being
chased stalls the interconnect and kills the ARM console; a post-hoc dump
returns nothing in exactly the case that matters.

A marker fires when its call is **entered**, so the last marker reported names
a call that never returned. Relevant sites:

| Marker | Site | Enters |
| --- | --- | --- |
| 17 | `0x4b152cf0` | `0x4b10e770` (config parser, passed `0xabe01000`) |
| 20 | `0x4b152d10` | `0x4b159a60` (`memset`) |
| 24 | `0x4b152d30` | `0x4b152b2c` (early system init) |
| 30 | `0x4b10d598` | `0x4b115cec` |
| 44 | `0x4b152c24` | `0x4b152a5c` (nine `0x3003xxxx` resource loads) |
| 45 | `0x4b152c2c` | `0x4b1895c4` |

### The firmware needs three artifacts, not one

The startup hang was **missing vendor artifacts**, not a hardware gate. Stock
U-Boot loads a firmware image, a config blob, and a set of TSE databases; every
earlier run staged only the firmware.

Marker 20 is `memset(cfg["sys:dbg_buf"], 0, cfg["sys:dbg_buf_size"])`. Both
arguments come from config lookups (`0x4b10d40c` and `0x4b10d444`, each fetching
a singleton at `0x8b2536bc` and calling its `vtable[0x14]` with a string key).
With no config staged the parser at marker 17 reads uninitialized DRAM at
`0xabe01000`, the keys resolve to garbage, and `memset` walks a bad pointer
until the bus stalls.

`display_cfg.xml` documents the layout, and the parser's `0xabe01000` argument
is exactly the uncached alias of its `cfg_file` LMA:

| Region | LMA | Size | Staged from |
| --- | --- | --- | --- |
| boot code + C code | `0x4b100000` | `0xc01000` | `display.bin` |
| debug buffer | `0x4bd01000` | `0x100000` | — (cleared) |
| cfg file | `0x4be01000` | `0x40000` | `display_cfg.xml` |
| TSE data | `0x4be41000` | `0x100000` | concatenated `*.TSE` |
| frame buffer | `0x4bf41000` | `0x1a00000` | — (cleared) |

The TSE window takes `database.TSE`, `projecttable.TSE`,
`ProjectID_0x0012.TSE`, and `pq_custom.TSE` **simply concatenated** in that
order (347,816 bytes; kept as `local/mips-display/tse_blob.bin`). Each file is
magic-tagged `TSE` plus a type byte, so the firmware evidently scans for the
magic rather than indexing fixed offsets. Stock U-Boot selects the ProjectID
file via a `mips_projectID` value; `0x0012` is the literal in its binary.

Stage each window with its own fastboot pass and exit with `fastboot continue`
— a warm reset destroys staged DRAM (see [flash.md](flash.md)). `probe-trace`
clears everything above the image except the config and TSE windows, so those
two survive; the firmware image must be re-staged for every run because both
the trace patches and the running firmware modify it.

### Run protocol: one probe per boot

**A `probe-trace` or `probe-ready` run leaves hardware state that breaks the
next run**, and `h713_mips_stop()` does not clean it. The symptom is a stall at
marker 12, the firmware's interrupt init. After a run, even U-Boot's `reset`
command hangs, so recovery is a physical power cycle.

This single rule accounts for every irreproducible result recorded earlier in
this document. Runs that looked like they proved TVCAP ordering, TSE damage, or
non-determinism were second-or-later runs on one boot. Bench procedure:

1. power cycle;
2. `mw.l 0x4be01000 0 0x50000`;
3. stage `display_cfg.xml`, the TSE blob, then `display.bin`;
4. `h713_mips verify` — must print `16c74a28...`;
5. exactly one `h713_mips probe-trace` (or `probe-ready`).

Treat any result from a second run on the same boot as void.

### TVCAP: the ARM does enable it, with specific values

This section previously said the ARM must leave TVCAP alone. That was drawn
from `probe-trace` A/B runs which set the gates with `|= BIT(31)` and released
them mid-run from the poll loop; both harmed firmware startup.

Stock U-Boot's fastlogo disproves the general claim. It enables TVCAP with
explicit values as part of bringing up the display:

```
0x02001d88 <- 0x00010001    bus gate + reset
0x02001d6c <- 0x80000305    TCD3
0x02001d74 <- 0x81000001    VINCAP DMA
0x02001d84 <- 0x80000000    HDMI audio
0x02001d80 <- 0xc0000000    TVCAP bus
```

So the rule is about *values and ordering*, not about ownership. Do not set
these gates by OR-ing an enable bit onto whatever the cold state happens to be.

### Current state: the MIPS never receives a timer interrupt

With all three artifacts staged and one run per boot, the firmware executes
every instrumented point: markers 10-14, 16-24, 26-53, 62-66, 68-78, 84-89,
93-96, 101-104, 111, and 130-132. The HDMI-RX byte load at physical
`0x06840093` succeeds, and the four-registration group at `0x8b128020`
completes. `status` is 1, the BSS witness is clear, both CPU_COMM magics read
`deadbeef`, and the ARM flag reads back `0x5`. An uninstrumented `probe-ready`
with a ten-second budget behaves the same.

`MIPS READY` is never set, and the trace explains why. Markers 1-9 — the entire
CPU_COMM path — never fire:

```
0x4b15257c   ThreadX thread entry           (markers 6, 7)
  0x4b12423c   CPU_COMM init                (markers 8, 9)
    0x4b123828   share-register reader      (markers 1, 2, 3)
    0x4b11abbc   spinlock + slave init      (markers 4, 5)
```

`0x4b15257c` has no direct callers; its address is materialised into `$a3` at
`0x4b152d38`/`0x4b152d44` and handed to a thread-creation call. That call sits
between marker 24's site (`0x4b152d30`) and marker 25's (`0x4b152d54`). Marker
24 fires and marker 25 does not, so the early-system-init call never returns
and the thread is never created.

The innermost stall is marker 53's call into `0x4b1839dc` (marker 54 does not
fire). Inside it, trace slots 104 and 105 — which capture the polling loop's
current and initial tick rather than marker ids — both read **zero**. The loop
is `while ((now - start) < 0x33)`, so a tick that never advances never expires.

The tick source is a software counter at `0x4b252cc0` (BSS), read under an
interrupt-disable/restore pair at `0x4b104b04` and incremented by a timer ISR.
It reads zero, so **the MIPS is receiving no timer interrupt**. The complete
chain is:

> no MIPS timer IRQ -> tick counter stays 0 -> the wait loop never expires ->
> `0x4b1839dc` never returns -> thread creation never runs -> the CPU_COMM
> thread never starts -> `MIPS READY` is never set.

The firmware does program an interrupt block: marker 12's function
`0x4b147950` clears CP0 Cause IP bits and writes `0x03061300..0x03061320` in
the MIPS control window. What is not yet established is where the timer source
lives, whether its clock or reset needs releasing from the ARM the way the
display tree did, and whether the CP0 `Status` interrupt enable is being set.
That is the next thing to recover.

The `0x4b22cf68` flag consulted before each tick read is initialised data whose
image value is `1`, so the stub path is not the issue; the real read is taken
and returns zero.

**Framing correction.** Calling "no timer interrupt" the root cause is too
strong. The tick is a ThreadX software counter incremented by the CP0 Compare
ISR, and interrupts are legitimately masked this early in startup, so a
stopped tick is expected at that point rather than a fault. The real defect is
that `Rx_HDCP14_LoadKey` polls HDMI-RX `0x06840093` for an acknowledgement
that never arrives, and its timeout — which stock relies on to recover — cannot
expire while the tick is stopped. The timer needs no CCU gate either: it is the
MIPS core's own CP0 Count/Compare, and the coprocessor cannot reach the CCU at
all, so every clock it depends on must come from the ARM.

## The ARM display path, and why it is not independent

`LogoRegData.bin` is a fourth vendor artifact, loaded by stock U-Boot from
`mips/LogoRegData.bin`. The ARM consumes it: stock parses and applies it
itself, as its own strings show — `Invalid logo regbin:%s`,
`Get logo table:%d fail!`, `create_fastlogo_inst fail!`,
`Display fastlogo finish!`.

It is a masked register write-table: 16-byte `{address, value, mask, type}`
records where type 1/2/4 is the access width, plus control records with a zero
address and type `0xff` carrying a delay. Roughly 700 register writes across
the CCU, TVTOP, DE, mixer and LVDS. Records are 16 bytes but only 4-byte
aligned, and the stream changes phase between runs, so a walker must
resynchronise rather than step a fixed lattice.

The container holds **alternatives, not one sequence**: a CCU/TVTOP prologue,
eleven timing variants, and seven DE/mixer blocks. Applying a whole range
leaves the *last* variant in force. The block matching this panel is
`0x15d4..0x180c` — `0x05880020 = 0x02f80550` (1360x760 total),
`0x05880024 = 0x02d00500` (1280x720 active), `0x05880028 = 0x00140028`
(bp 40/20), `0x0588002c = 0x00000014` (hs 20), which reproduces
`display_cfg.xml` field for field.

**An earlier revision claimed the ARM path and the MIPS pipeline were
independent, and that a boot console needed only the ARM side. That is wrong.**
Stock's own fastlogo releases the coprocessor as an integral step of putting
its logo on screen. The display requires the MIPS to be running; the two are
one path.

### Stock fastlogo, transcribed

The stock U-Boot is **Thumb**, not ARM — its first word is only the exception
vector. Load base is `0x4a000000`, verified by every string address appearing
as a literal. `"Display fastlogo finish!"` is printed at `0x4a022bc6`.

The tail, from `0x4a022a3c`, with 12 ms between steps:

```
0x02000150 <- 0x22ffff22    PH pin mux (PH0/1 stay UART0)
0x02001d88 <- 0x00010001    TVCAP gate/reset
0x02001040 <- 0xb8003501    PLL enable (same rate, cold state is off)
0x02001d6c <- 0x80000305
0x02001020 <- 0xb8006301    PLL_PERIPH0  -- SEE HAZARD BELOW
0x02001d74 <- 0x81000001
0x02001068 <- 0xb8002f01    PLL enable (cold state is off)
0x02001d84 <- 0x80000000
0x02001d80 <- 0xc0000000
0x06e00004 <- 0x01111117 ; 0x06e00008 <- 0x404 ; 0x06e00000 <- 0x00111111
   ... same three <- 0 ... then the same three restored   (reset pulse)
0x06940000 <- 1             INCAP
0x051c0010 <- 0x01800045    LVDS enable
<MIPS clock/reset/bootaddr/release, identical to h713_mips>
delay 300 ms
0x051c0010 <- 0x45          LVDS finalise
```

**INCAP does not wedge.** `0x06940000 <- 1` is recorded elsewhere in this
document as wedging independently. With the vendor fabric configured it is
fine, on stock and on ours. Another "unclocked, not forbidden" case.

**Hazard: do not write `0x02001020`.** That is PLL_PERIPH0, which clocks MMC
and the AHB/APB buses. Our U-Boot runs it at `0xb8003100`; stock's fastlogo
writes `0xb8006301`. Replaying that write from a U-Boot prompt powered the
bench board off. Stock is writing a value that is already in force in its own
boot context; ours is not. `0x02001040` and `0x02001068` are safe because both
are *disabled* in our cold state, so nothing depends on them.

### Where this stops

Replaying the above, with all four artifacts staged and the MIPS executing
(BSS witness clear), leaves the panel dark. The LVDS FIFO status at
`0x05880FE0` does respond — `0x2` cold, `0x0` after a FIFO reset via
`0x05700088` bit 8, `0x3` after the full sequence — but never changes between
consecutive reads, so nothing is scanning.

The untranscribed half of the function is the likely gap: **`0x4a022860`**
is the function prologue, and `0x4a022860..0x4a022a04` covers panel power
sequencing, the table-application path (parser around `0x4a0248xx`,
write helper `0x4a024878`), and the bitmap blit. Transcribe and replay that
before drawing further conclusions.

### Hardware note

The bench board's display is an **LCD panel** — `HY200-1-3-W` on a 30-pin
`Z20HD720M-V03` flex, 1280x720, driven directly over LVDS. It is not a DLP
system. `local/allwinner-h713-linux/` documents **HY310** hardware
(1920x1080, `LVDS -> DLPC3435 -> DLP imager`) and must not be treated as
authoritative for this board; doing so sent an entire investigation after a
DLP controller that does not exist here.

## Safety rules

- Keep a known-good FIT available and preserve UART as the recovery path.
- Do not enable `cpu-comm`, `tvtop`, `decd`, or GE2D in the recovery image.
- Do not map or access the MIPS control registers from Linux until their clock
  and power-domain behavior is independently understood.
- Do not mix unrelated GPU, filesystem, WiFi, or DVFS changes into display
  experiments.
- Treat `display.bin` and vendor image extracts as local-only research inputs.
  Record their hashes, but do not embed workstation-specific paths in defconfig.
- Every patch-series edit must pass a fresh `build/build.sh kernel`; cached or
  previously published artifacts are not proof of the current tree.
- A driver must return an error when its hardware does not become ready. Probe
  success and log messages must not conceal a failed reset/clock/firmware step.

## Milestone 0 — preserve evidence and restore a buildable series

Actions:

1. Keep the experimental GE2D patch and reverse-engineering inputs out of the
   active series while they are reviewed.
2. Repair all malformed or stale new-file hunk counts.
3. Remove the absolute `CONFIG_EXTRA_FIRMWARE_DIR` and rootfs dependency on
   `tmp/`.
4. Restore the bench overlay to its known boot-safe state: reserve the firmware
   DRAM, but expose no MIPS control device to Linux.
5. Revert unrelated GPU IRQ and ext4 `norecovery` changes.

Acceptance:

- `build/build.sh kernel` applies every patch from a clean extraction.
- `Image`, both board DTBs, modules, and the bench FIT are published.
- The bench DTB has no enabled MIPS/display device and contains only the
  no-map firmware DRAM reservation.
- No MIPS/display firmware is compiled into the recovery kernel.

## Milestone 1 — verify the recovery kernel on the bench

Boot the Milestone 0 FIT over the existing safe path before writing it to eMMC.

Acceptance on UART:

- U-Boot hands off to Linux and Debian reaches the normal login target.
- Root ext4 mounts normally, without `norecovery`.
- Fan, UART, eMMC, RTC/reboot-mode, and the existing WiFi fixes show no
  regression.
- Save the complete UART log and FIT SHA-256 as the new display-recovery
  baseline.

## Milestone 2 — U-Boot firmware loader

Keep the operation in U-Boot proper while it needs filesystem access and
SHA-256. Do not place the proprietary firmware in SPL or the U-Boot image.
Keep the command manual until firmware readiness has a bounded independent
witness.

Required behavior:

- hold MIPS reset before modifying its DRAM window;
- accept only the known size and SHA-256 of `display.bin`;
- clear the complete factory five-megabyte load window before copying;
- flush ARM caches before releasing the external processor;
- use the recovered physical boot address and staged reset sequence;
- prepare only the proven display clocks, TVTOP routing, and mixer register;
- exclude LVDS, PH pinmux, TVCAP, HDMI, and INCAP;
- return to reset after a bad hash, short read, or unexpected CPU status;
- print reset status separately from firmware readiness.

Acceptance:

- The command is present only in the DDR3 bench U-Boot proper image and absent
  from SPL and the projector defconfig. **Passed on 2026-07-27.**
- A rejected or missing firmware image leaves CPU status zero. **Passed on
  2026-07-27.**
- The known image produces the expected hash and reset transition without
  disrupting UART, USB ACM, or eMMC. **Passed on 2026-07-27.**
- A second observable witness, such as a firmware-owned memory word or bounded
  IPC acknowledgement, proves instruction execution before autoboot is added.
  **Passed on 2026-07-27:** the cache-coherent BSS-clear witness passed on three
  pristine firmware loads.
- The complete recovery kernel reaches userspace with the MIPS running.
  **Passed on 2026-07-27:** the installed minimal display preparation makes the
  live-MIPS handoff safe with Panfrost enabled; DRM and the render node register
  and Debian reports `running` with zero failed units.
- A bounded firmware mailbox/IPC acknowledgement proves higher-level readiness
  before autoboot or Linux clients are added. **Pending.**

## Milestone 2b — Linux post-boot ownership

Enable only the no-map MIPS firmware reservation. Do not instantiate a Linux
MIPS loader, observer, or management driver. Keep CPU_COMM, TVTOP, DECD, GE2D,
and their extra framebuffers disabled.

Acceptance:

- Linux reaches userspace when U-Boot has not started the MIPS. **Passed on
  2026-07-27.**
- Linux reaches userspace with MIPS running and Panfrost transiently
  blacklisted. **Passed on 2026-07-27; diagnostic configuration only.**
- Linux reaches userspace with MIPS running and Panfrost enabled after U-Boot
  applies the minimal display prerequisites. **Passed on 2026-07-27; installed
  U-Boot and unmodified kernel command line.**
- Linux never loads `display.bin`, rewrites the boot vector, or toggles the
  MIPS reset sequence.
- The compiled DT contains no MIPS control-register address and Linux creates
  no MIPS platform or character device. **Passed on 2026-07-27.**
- `dmesg` reports only the no-map firmware reservation, not a MIPS probe.
  **Passed on 2026-07-27.**

## Milestone 3 — CPU_COMM address model

Do not enable CPU_COMM until its address domains are explicit:

- native kernel virtual addresses use `uintptr_t`/pointers and are never stored
  in protocol `u32` fields;
- shared-memory protocol fields contain 32-bit MIPS-visible physical addresses
  or offsets, converted through checked helpers;
- no helper reconstructs a pointer by OR-ing a fixed arm64 VA prefix;
- kernel-only lists use native `struct list_head` or native-width storage;
- shared structures retain the vendor ABI with compile-time layout assertions.

Add host-side KUnit or equivalent tests for FIFO wrap/full/empty behavior,
physical↔virtual conversion bounds, list insertion/removal, and malformed
shared-memory values.

Acceptance:

- The CPU_COMM objects build without pointer-to-int or int-to-pointer warnings.
- The platform driver is present in the linked image and probes exactly once.
- Invalid shared pointers return errors rather than reaching `BUG()`.
- With MIPS running, ARM and MIPS exchange a bounded ping/ack before any
  synchronous display RPC is attempted.

## Milestone 4 — TVTOP and DECD

Enable TVTOP first, then DECD. Keep GE2D disabled. Define resource ownership so
shared display clocks, resets, IRQs, and overlapping register windows have one
clear owner. Child population must propagate errors and be paired with
depopulation.

Acceptance:

- Both drivers can defer and reprobe without leaked PM, IRQ, clock, reset, or
  character-device state.
- No IRQ is requested non-shared by two active devices.
- CPU_COMM ping/ack remains reliable while TVTOP and DECD probe.

## Milestone 5 — GE2D and visible panel path

Review the GE2D patch as a separate feature series. Probe must not issue
synchronous MIPS RPC until CPU_COMM reports ready, and every RPC result must be
checked. Start with framebuffer/IRQ/backlight side effects disabled, then enable
one at a time.

Acceptance:

- GE2D can probe without changing fan/backlight GPIO state unexpectedly.
- Panel initialization, PWM configuration, and framebuffer scanout are separate
  observable steps.
- The LVDS path produces a stable test pattern before compositor or GPU
  integration begins.

## Artifact organization

After Milestone 0 builds:

- discard one-off top-level `fix_*.py`, `patch_editor.py`, `wait.sh`, and saved
  build stdout/stderr;
- move useful vendor extracts, firmware, disassembly, and analysis scripts under
  ignored `local/mips-display/`;
- keep the inactive GE2D patch in a clearly named local research location until
  it passes review and has reproducible provenance.

Nothing under `local/` is published or force-added to Git.
