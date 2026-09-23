# THDMIRX controller initialization and mistimed source trial

Private kernel #5 retained TVCAP from U-Boot. The 34-word MIPS witness passed
its 60-second U-Boot gate, then continued advancing in Linux with no recorded
exception. TVFE, TVCAP, the four receiver clocks, the EDID clock, and the
callback-capable CPU_COMM module were loaded before this test.

The opt-in `h713-thdmirx-init` module applied the controller sequence recovered
from the independently working peer driver. It changed the key state as
follows:

```
before timer=00000000 cmu=00000300 phy=00000000 descrand=00000000
       deframer=264d8960 scdc=ffff1000 ced=00000401 mask=00000000
       enable=00000000
after  timer=198b7b25 cmu=00020300 phy=00018000 descrand=00000000
       deframer=264d8963 scdc=ffff1000 ced=0b000010 mask=00000000
       enable=00203901 scdc-status1=00000033
```

The MIPS heartbeat advanced for another five seconds without exception, and
the firmware `cmds` shell command returned. The complete stock-equivalent
daemon initialization then succeeded without source selection; every RPC
returned, the hot-plug callback reached userspace, and a subsequent three-second
witness plus shell command also passed. This validates the controller sequence
as a stable prerequisite.

The following live attempt is inconclusive because host-side orchestration used
almost the whole 30-second HPD window. Target timestamps show the SCP helper
asserting HPD at 301.182 seconds, the daemon opening its callback channel at
331.760 seconds, and the SCP helper restoring HPD at 332.910 seconds. The daemon
had not reached `SetSource(3)` before that restoration boundary. The source log
confirms exact EDID detection and output enable, followed by disconnect at the
end of the bounded trial.

`SetSource(3)` subsequently did not return. CPU_COMM reported session `0x2b`
interrupted while waiting for its return, systemd reported a segmentation
fault, and SSH, ping, and the serial shell stopped responding. SCP still
reported SRAM/peripheral restoration and zero EDID mismatches. Because HPD was
already being restored, this does not test source selection with a sustained
live input and does not reject the THDMIRX prerequisite.

`tools/hdmi/run-detection-trial.py --run-hdmird --seconds 30` now starts the
fixed callback-aware daemon command from inside the source monitor as soon as
the GPU connector becomes enabled. That removes the host orchestration delay
for the next cold-boot trial.

Files:

- `source.json`: source DRM transitions and exact EDID hash.
- `edid.bin`: 128-byte EDID returned to the GPU.
- `target.log`: SCP completion/restoration output recovered before SSH loss.
- `live-daemon.log`: daemon output through the `SetSource(3)` boundary.
- `serial-boundary.log`: final serial messages before the board stopped.
- `receiver.log`: failed auxiliary read caused by staging the helper under the
  wrong filename; no receiver conclusion is drawn from it.
- `cleanup.log`: expected SSH timeout after the board stopped.
