# PLL byte-read diagnostic

The word-write trial verified all 96 records and logged stock full Init and
PowerUp, but aligned regr values stayed +0=67,+4=10,+c=0,+10=3. That did not
confirm the collapsed-byte-write hypothesis. The final DSP version1 handshake
also timed out, preventing a valid bridge capture trial. Original U-Boot was
restored before trials; no DSP retry or live MIPS patch occurred.

This candidate retains stock PLL byte writes exactly. It changes only regr's
read at 8b180114: for four exact scalar PLL addresses BB880000/4/c/10, read
four consecutive bytes using stock's byte width and pack them for the existing
RTT print. Every other address retains its original LW. The hook's delay-slot
LW a1 and original epilogue remain. The shim performs no stores. Offset8 and
all wrapper/receiver ranges remain outside its byte-read allowlist.

The init/retry profile and 96-record/global relocation-census checks remain.
264 Unicorn cases verify access widths, exact addresses, fallback, packed
value and delay-slot argument restoration with no stores. This is a diagnostic
of read-width semantics, not a capture fix. First test without DSP upload so
its prior version-check timeout cannot affect interpretation.

Candidate SHA324543e16e3ef56e97011a5cdba563b08211ad4ba56fce05d4ce05f06568c37e.
Exact original c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7
must be restored after cold launch verification. Same1798sector extent, SPL
hash guarded and untouched. Kernel/FIT and user IR/suspend/poweroff untouched.
