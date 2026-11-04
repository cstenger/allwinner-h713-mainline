# Non-writing recovery-entry rehearsal — November 3, 2026

The pinned FEL rescue entry, recovery access gates and cold return to the
installed production candidate passed. This rehearsed entry/access only;
no rollback payload was flashed and no full restoration trial is claimed.

The operator performed a clean shutdown and physical cold entry into FEL.
Boot ROM identified H713 (0x1860). The sealed tool and rescue SPL hashes matched,
and the required shared libraries resolved. RAM SPL loaded the preserved
older rescue proper, whose expected banner was captured and autoboot caught
before Linux. Fan GPIO PB5 was enabled/read back. Board serial, eMMC card
metadata and all 27 GPT extents/names/unique GUIDs matched the baseline.
The older CLI lacks mmc-reg support, as already noted in packet preflight;
full CID was verified from Linux before shutdown rather than re-read there.

The probe configured only the packet's four exact rollback raw aliases in RAM.
All 20 USB getvar identity/size/slot gates passed. Fastboot continue returned to
the held rescue prompt, all RAM aliases were removed, and fan high was verified.
No flash, erase, environment save, partitioning or logical reset was performed.
Bounded MMC reads and CRC32 checks then matched the installed SPL/proper,
saved environment and preserved two-MiB rescue region to their pinned inputs.
CRC is a transfer checkpoint, not a substitute for the earlier full preboot SHA.

A further physical cold boot identified the rebuilt November 3 SPL, TF-A,
U-Boot and kernel. The complete 71-file/package/kernel/raw-boot/environment/
bundle/startup audit passed on boot `446e81f5-4f1a-479d-bd92-d363b39d4ad2`.
Chris confirmed normal desktop return without reseat or service recovery.
The completed passive UART recorder is closed; the board remains on normal HDMI.

The rehearsal exposed a host-command behavior: sunxi-fel spl expects SPL to
return to ROM so it can read an eGON.FEL signature. This rescue SPL instead
hands off to U-Boot, so the host tool remained waiting after UART success.
Only that host wait was terminated after the expected rescue prompt was proven.
The packet generator's future recovery instructions now bound that wait to
30 seconds and require independent fresh UART evidence; neither a timeout nor
host exit status alone establishes success. The already sealed installation
packet and installed binary artifacts were not edited.

The local probe plan passed its canonical check and rejected three unsafe
mutations (flash, MMC write and wrong role); Python syntax checks passed.
Private raw UART/USB transcripts, source hashes and receipts are retained in
local recovery storage. The one safely discarded unstable frame in the extended
HDMI run remains an open qualification finding. No full rollback write trial
has been run, and this rehearsal does not waive that finding.
