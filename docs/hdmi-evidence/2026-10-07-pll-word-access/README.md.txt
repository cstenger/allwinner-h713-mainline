# PLL scalar word-access experiment

The previous cold trial proved stock Init executes but measured scalar PLL
words match a collapsed byte-store model: +0=67,+4=10,+c=0,+10=3.
This candidate changes the store instructions in both stock byte helpers to
short shims. Only BB880000..0007 and BB88000c..0013 use aligned 32-bit
read-modify-write preserving the other lanes. Offset8 and every other
address retain the original byte store. No guessed PLL values are introduced.
The original helper epilogues, return values and callee-saved state are retained.

The 42-record init/retry profile is retained. Nine expendable progress marker
groups are replaced by 54 records: 31 shim instructions, 2 hooks, 18 unreachable
relocation-census padding instructions and 3 unreachable no-ops. CPU_COMM,
source3 return tracing and canaries remain. The global 62-base/84-store census
is unchanged; exact firmware, U-Boot, expected hook instructions, zero cave,
record ownership and both fixed-size table boundaries are checked.

560 Unicorn execution cases cover both real stock epilogues, register/stack
restoration, byte lanes, word-write widths and forbidden-address byte fallback.
4050 existing retry cases and zero-init selection tests pass. In the full stock
calculator simulation, the shim semantics recover exactly the normal byte-lane
configuration even under the collapse fault model (model.json). This validates
software behavior, not physical PLL lock or capture.

Candidate 67d51b81b9e74d343a1b4c4e327dbc820c05a1cc14f5f0ff632c17ed764b5ddb
uses the same 1798-sector U-Boot extent; SPL, kernel and FIT are untouched.
Original c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7
is retained in uboot-before.bin and must be restored after the cold trial.
Hardware trial pending; no live MIPS code patch or warm relaunch is permitted.

## Installed boundary

install.log confirms complete candidate readback and unchanged SPL. The original
U-Boot rollback is saved on both host and board. Verifier/profile were staged
and filesystem synced. Running Linux/MIPS remain on the preceding profile;
no live patch or relaunch occurred. Awaiting physical power-cycle at U-Boot.
After the trial, restore the exact original U-Boot and verify full readback.

## Completed trial and revised interpretation

Source3 completed; all96records/magic/canaries verified. Exact original U-Boot
restored with full readback and SPL identical (restored.log). DSP upload reached
pair724 but final device1 version completion timed out; no retry or bridge route
was attempted afterward. Thus no valid DMA capture outcome exists for this boot.
Two bounded receiver-only windows locked720p, decoded N6144/Fs48000, and cleaned
up HPD/EDID with exit0. Aligned regr words remained unchanged; logged stock full
Init and PowerUp at tick330669 (logged/elog-hdmi.txt). This does not support the
collapsed-byte-store hypothesis. Individual byte reads are required to test
whether aligned LW values represent the expected packed register contents.
Diagnostic modules unloaded, logging off, shell responsive (cleanup.log).
DSP volatile state is partial and requires physical cold boot to reset.

## Correction from scalar byte reads

The later cold PLL byte-read experiment (../2026-10-07-pll-byte-read) shows
aligned MIPS LW/regr does not provide a packed four-byte value for this bank.
With stock PLL byte stores, explicit four-byte LBU reads during playback yield
+0=0d320667,+4=50000010,+c=60180000,+10=3. Thus earlier +c=0/+0=67
word observations do not prove missing upper-byte configuration or collapsed
byte writes. That hypothesis is withdrawn. Stock full Init and PowerUp are
positively logged; physical PLL lock and capture success are still unproven.
