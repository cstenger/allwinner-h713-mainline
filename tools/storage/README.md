# DDR3 eMMC threshold verification

These tools are bench-specific: HY200 QZ713DF_A1, the pinned eMMC CID and
unmounted 2 GiB vendor partition `mmcblk0p9`. They do not inject timing faults
or write the block device. A controller fault can still wedge ordinary root
filesystem I/O; arrange physical power-cycle recovery before running load.

`emmc-read-baseline.py` hashes each direct-I/O read and requires the pinned
partition digest. It samples STAS and THLD with aligned, read-only MMIO loads,
records temperatures and hardware interrupt deltas, and restores the temporary
runtime-PM/profiling settings. A 15-second read-progress watchdog stops its
load children and records the registers; a read stuck inside the kernel may
still require a cold cycle. JSON output should be streamed to the host.

The mixed workload runs 3840×2160 H.264 through `v4l2slh264dec` alongside
`gpu-memory-load.py`: 3840×2160 offscreen rendering at up to 30 fps, explicitly
on the Panfrost render node. Pixel readback rejects a broken renderer; the
reader requires both decoder and GPU interrupt deltas. The normal HDMI
capture/display services stay active. This is a controlled bus-load test,
not a Kodi playback test or a measurement of storage's maximum throughput:
SHA-256 and Python sampling also consume CPU and memory bandwidth.

Stage the GPU script as `/tmp/emmc-gpu-load.py` and the project's
`local/h713-lab/stock-capture-20261001/media/52-h264-2160.mp4` as
`/tmp/emmc-load-2160.mp4`, both in tmpfs. Then run on the board:

```sh
python3 emmc-read-baseline.py --mode idle --rounds 1
python3 emmc-read-baseline.py --mode mixed --rounds 3
```

Host regression against a tree prepared with kernel patch 0206:

```sh
python3 tools/storage/test-emmc-threshold.py --kernel /absolute/prepared/tree
```

This compiles the actual eMMC and SDIO threshold helpers under ASan/UBSan.
It checks device scope, timing/direction/block-size boundaries, preservation
of unrelated THLD bits and clearing after read-to-write/timing transitions.
It does not establish real FIFO semantics without the hardware observations.

## Checked CMD18 recovery (0207)

`test-emmc-recovery.py --kernel /absolute/prepared/tree` compiles the actual
restore, CMD12, completion and terminal-refusal helpers under ASan/UBSan.
It injects reset/init/IDMA/clock/stop failures, checks that failed restoration
skips CMD12, and verifies exact-once completion and refusal before DMA/MMIO.
The separate recovery error cannot be cleared by an unrelated `set_ios` call.

`make-emmc-recovery-diagnostic.py` generates an **opt-in bench-only patch**;
do not put its output in the production series. It adds a bounded threshold
bypass for plain CMD18 reads wholly within this board's vendor partition.
It changes no timing registers and never selects write/rootfs-sector
requests. The default count is zero; counts above 2048 do nothing. Its
read-only counters distinguish selected requests from successful recoveries.
`test-emmc-recovery-diagnostic.py` checks the generated patch and target
bounds, including absent data, other boards/controllers, directions and
commands, overflow candidates and requests crossing the partition boundary.

Restore the normal image on disk before arming a diagnostic boot and keep
root read-only during fault trials. A synthetic error after a completed
transfer is not a valid test of recovery from an active full-FIFO read: it
can make CMD12 fail and correctly latch terminal I/O failure. Use the bounded
read-threshold bypass under the verified load to seek a natural in-flight
error instead. Read success alone does not exercise recovery; require the
recovery counter/log and a matching full-partition hash.
