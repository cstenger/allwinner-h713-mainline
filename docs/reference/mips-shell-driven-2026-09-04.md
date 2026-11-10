# The MIPS debug shell, driven — and the coexistence lock solved

2026-09-04. Two firsts for this project in one boot, plus one self-inflicted lock.

## 1. Linux boots with the MIPS alive. The lock was never coexistence.

Four attempts failed before this, and the fix came from the peer tree's note that
an un-initialised MIPS performs a wild memcpy into DRAM
([mips-coexistence-lead-2026-09-04.md](mips-coexistence-lead-2026-09-04.md)).

**The working sequence, all on the flashed bootloader, no code change:**

```
cold power cycle -> interrupt autoboot
h713_disp init 0x34        # FULL bring-up, handshake, core LEFT RUNNING
md.l 0x0306101c 1          # -> 00000001
setenv bootargs <production> initcall_blacklist=h713_afbd_platform_driver_init
run bootcmd
```

Result: **a full Linux boot to the login prompt with `0x0306101c == 1`**, zero
oops, zero warnings, zero BUGs, WiFi up, ssh up.

**What was actually wrong.** Every earlier attempt re-released an *already
quiesced* core with `mw.l`, which cold-restarts the firmware into a state where
the ARM-side CPU_COMM handshake has never happened. `h713_disp init` performs
the whole bring-up and simply does not quiesce at the end:

```
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
H713 MIPS: firmware readiness proven by MIPS READY
H713 MIPS: application readiness proven
H713 disp: display initialised with the firmware running
```

Note there is no "MIPS core quiesced" line, which every other path emits.

**So "a live MIPS window layer and Linux cannot coexist" is refuted outright.**
They coexist fine; what does not survive is a *cold-restarted, un-handshaken*
core. `h713_disp logo-live` is **not** in the flashed bootloader (checked — the
usage text has no such verb), and it was not needed: `init` has the property we
wanted, and its "renders nothing" behaviour is irrelevant here.

## 2. The monitor shell answers

First time driven, via [`tools/mips/mips-shell.py`](../../tools/mips/mips-shell.py)
over the DRAM ring. `--cmd cmds` returned **917 bytes** and a prompt:

```
Command List:
app  bs  crtc  tcd3  dtv  hal  elog  memory_agent  pq
regw  regr  clear  keys  vars  cmds  users  help  setVar  win
VS:/$
```

`help <cmd>` works (`help regr` -> "read register"). `vars` returns an empty
"Var List:". The ring protocol, the pump and the address window are all
confirmed end to end against a live firmware.

### `win wi` and `win wm` return nothing, and it is an output-routing problem

Both echo the command and produce no body. **The window manager exists** — its
singleton pointer at MIPS `0x8bac4bf0` (system `0x4bac4bf0`) reads `0x8B89B9B0`,
non-NULL — so this is not a missing object.

The reason is that both handlers tail-call manager vtable slots whose bodies
emit through the firmware's trace function `0x8b150948`, and the production
`display_cfg.xml` selects **elog mode 0, "no log"** (peer tree,
`docs/subsystems/mips.md`). The shell's own `printf` output arrives; anything
that goes through the logger does not.

**The fix is configuration, not code:** set elog mode 1 or 2 in the
`display_cfg.xml` on the FAT, re-run the bring-up, and read the buffer. Mode 1
is a ~120 KB ring at `0x4B272D9C`, mode 2 a 2 MB linear buffer — both plain DRAM
and therefore readable from Linux exactly the way the shell ring is. The peer
tree has `tools/dump_mips_elog.py` for the format.

## 3. `regr` with a MIPS VA hard-locks the SoC — use ARM-physical addresses

`regr 0xba600140` (AFBD ch1 control expressed as a MIPS virtual address) killed
the board: network and serial both dead, power cycle required.

**The address convention was the mistake, and it is documented.** The peer tree
records the firmware's MMIO helper at `0x8B17FC70` as doing

```
phys = (addr + 0xB5000000) | 0x20000000
```

i.e. **callers pass ARM-physical addresses and the firmware applies the offset
itself**. Passing `0xba600140` double-applies it and lands in unmapped space,
which hangs the bus.

**So the correct form is `regr 0x05600140`, not `regr 0xba600140`.** Untested —
whoever tries it next should start from a register whose value is already known
so the reply is self-checking, and should expect that a bad address is fatal
rather than an error.

## Where this leaves things

The window layer is now *reachable*: Linux runs with the core alive, the shell
answers, and `win os` / `win wi` are one config change away from being usable.
That was the precondition every route in
[mips-window-layer-plan.md](../mips-window-layer-plan.md) was blocked on.

Next, cheapest first:

1. **Enable elog** in `display_cfg.xml`, re-run, and read `win wi` — the live
   window geometry the plan has been trying to reconstruct by disassembly.
2. **`regr 0x05600140`** with the corrected convention.
3. **`win os <0..100>`** for a visible scaling test — but note the panel shows
   nothing under `h713_disp init` (it renders no image), so a content path has
   to be arranged before "visible" means anything.
