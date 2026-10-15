# Managed HDMI EDID/HPD lifetime

This owner uses the exact SCP payload and audio EDID from the endurance test.
It replaces the trial's timed hold with an explicit cooperative stop. Startup
claims a receiver client and the SCP SRAM/reset resources, saves all vectors
and SRAM, validates every installed instruction pair, then pins the module
before releasing SCP. A setup failure after release retains every hold and
requires a cold cycle. No peripheral receiver MMIO is accessed by ARM.

`stop=1` requests peripheral restoration and requires the completion marker,
zero mismatch/exception, stopped SCP reset readback and byte-exact SRAM/vector
restoration before releasing its receiver client and self-reference. Failure
is terminal and retains ownership. DDC pins are managed by the accompanying
service and released only after this module restores and unloads. The backend
refuses shutdown while a signal owner/helper remains. Consumers must require
and order after `h713-hdmi-signal.service` to close before signal teardown.

Build the generated payload with:

```
python3 tools/hdmi/make-edid-trial-code.py --edid tools/hdmi/fixtures/hdmi-audio-edid.hex modules/hdmi-signal/edid-trial-code.h
make -C <validated-kernel-build> M=$PWD/modules/hdmi-signal KBUILD_EXTRA_SYMBOLS=$PWD/modules/hdmi-receiver/Module.symvers ARCH=arm64 LLVM=1 W=1 modules
```

The generated payload is byte-identical to the tested endurance header.
The module builds cleanly with W=1; hardware lifetime validation is pending.
