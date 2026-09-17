# Bounded SCP execution probe

This bench-only module briefly starts an idle H713 SCP, receives an SRAM
marker, holds reset again, and verifies restoration. It does not load stock
firmware or implement power management. The optional HPD payload performs
one fixed SCP-side read and copies its result to SRAM; it never writes HPD.

Use only in the established native-PSCI, BL31-in-DRAM test boot, with no other
SCP owner or concurrent hardware test. The module rejects an already running
core and claims its MMIO regions before modifying them. Those checks cannot
establish ownership by secure firmware, so the boot configuration matters.
Do not configure autoload.

## Memory and cleanup

The first region at ARM 0x00100000 exposes sparse vector stubs: their first
words are writable, their delay slots read as NOP, and tested non-vector
addresses read zero after writes. Code therefore runs in SRAM A2:
ARM 0x00104100 / SCP 0x4100. Marker storage is ARM 0x00104f00 / SCP 0x4f00.
The first A2 page and fourteen changed vector words are saved before use.
All generated code and vector jumps must read back before reset is released.
Exception stubs report their vector number into SRAM, then spin locally.

The probe polls 100 times with 1–1.5 ms sleeps. On completion or timeout it
asserts R_CPUCFG bit-0 reset, restores the page and vectors, compares them,
and releases its mappings/claims before returning. A hardware bus stall can
outlive core reset; the bound applies while ARM remains able to service the
polling/cleanup. A failed insertion leaves no loaded module.

## Build and run

Build against the private tree matching the test Image:

```sh
mkdir -p build/scp-probe
cp modules/scp-probe/Makefile modules/scp-probe/h713-scp-probe.c build/scp-probe/
make -C "$PWD/build/kernel-runtime" M="$PWD/build/scp-probe" ARCH=arm64 LLVM=1 modules
scp -F /dev/null build/scp-probe/h713-scp-probe.ko root@192.168.4.1:/tmp/h713-scp-probe.ko
```

On the target, the default approved execution test is:

```sh
insmod /tmp/h713-scp-probe.ko run=1
cat /sys/module/h713_scp_probe/parameters/marker
cat /sys/module/h713_scp_probe/parameters/restored
rmmod h713_scp_probe
```

The optional test, separately authorized by the owner in this session, is:

```sh
insmod /tmp/h713-scp-probe.ko run=1 hpd_read=1
dmesg | tail
```

A zero value in the logged HPD field is valid only when completed=1; on
timeout it is merely the variable's initial value. See
[the hardware record](../../docs/hdmi-scp-probe-validation.md).
