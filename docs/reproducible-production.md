# Rebuilding the HY200 DDR3 production system

This workflow rebuilds the board-specific open-source software, rather than
importing accepted kernel/module binaries or an old installed HDMI bundle.
Debian packages come from an explicitly dated signed archive snapshot.
Only proprietary vendor firmware/data and private device configuration are
external inputs. New outputs are **unqualified candidates** until hardware
acceptance; the builder never connects to or installs anything on a board.

## Inputs

- The complete proposed source checkout and pinned git submodules.
- Host tools matching `config/production-toolchain.json` (including LLVM 23).
  The target GCC/libva/GStreamer versions come from the Debian snapshot.
- Exactly the files in `config/production-vendor.json`: display firmware and
  tables, the stock boot logo, Wi-Fi/BT firmware, and the HDMI audio DSP patch.
- An explicit calibration JSON, SSH public key, and optional private hotspot
  configuration. The supplied DDR3 calibration records the accepted 40 ms
  HDMI speaker delay plus measured accelerometer offsets and lens geometry;
  they are not silently inferred from an old installation.
- An explicit source timestamp and immutable Debian snapshot URL.

Vendor assets may be exported from an authorized firmware archive or offline
boot-filesystem copy. The exporter reads only the named pinned assets, checks
every hash before writing, and refuses an existing output directory:

```sh
python3 tools/release/export-vendor.py \
  --boot-directory /private/vendor-boot-files \
  --wifi-directory /private/aic8800D80 \
  --dsp /private/hdmi-audio-dsp.bin \
  --output /private/hy200-vendor-inputs
```

Keep firmware, hotspot credentials, SSH keys and produced rootfs images out of
Git. The public vendor hash lock contains no firmware payload. No raw saved
U-Boot environment, factory identifiers or host keys are imported.

## Build

After `git submodule update --init --recursive`, use a new empty work path:

```sh
python3 tools/release/build.py \
  --work /scratch/h713-production-candidate \
  --vendor /private/hy200-vendor-inputs \
  --calibration config/hy200-ddr3-calibration.json \
  --ssh-key /private/authorized-key.pub \
  --hotspot /private/hotspot.conf \
  --mirror https://snapshot.debian.org/archive/debian/20261102T000000Z \
  --epoch 1793693083

python3 tools/release/boot-image.py \
  --release /scratch/h713-production-candidate \
  --output /scratch/h713-production-candidate/boot.img
```

Omit `--hotspot` for no hotspot; there is no fallback to `local/hotspot.conf`.
An optional `--source-cache` reuses downloaded Linux tarballs only; their
configured SHA-256 is still checked. No prepared kernel tree or old bundle is
required. The work directory is never overwritten or silently resumed.
`--debian-cache DIR` optionally reuses checksummed package downloads; signed
metadata from the immutable snapshot is still fetched and checked.

The orchestrator builds kernel/DTB/modules, TF-A, U-Boot/SPL, AIC8800, five HDMI
modules, and the VA driver/player/runtime image. The shared DSP protocol
headers are declared build inputs; diagnostic modules are not built. HDMI
runtime scripts and units are assembled from source. The startup script pins
the selected FIT/FDT sizes. The existing delta installers are not used.

Rootfs construction runs target compilation in a disposable arm64 Debian
environment under QEMU. The production image omits the compiler/development
headers, benchmark services, diagnostic probe modules (including the inherited
AV1 probe), kernel runtime-testing menu, Python regression suite, SPA test
plugin, Wi-Fi baseline bench helper, test media, `v4l2-ctl`
and the retired GStreamer HDMI speaker consumer. The PipeWire consumer,
operational health/IPC helpers, logs, serial/SysRq recovery and SSH remain.
Tests and investigation history stay in the source repository.
The second command verifies the release boot archive and creates a new regular
32 MiB FAT image plus a checksum sidecar, without mounting anything or touching
a device. This avoids depending on free space for an in-place FIT replacement.

The builder records source hashes, tool versions, vendor pins, calibration,
target package versions and output hashes. Build dates and gzip headers are
fixed. Rootfs tar ordering/times and ext4 UUID/hash seed are controlled.
Module inputs are enumerated from tracked source files; leftover Kbuild
`*.mod.c` files and generated EDID headers are excluded. The EDID header is
regenerated in the isolated build directory from its tracked generator/fixture.
Two complete builds in separate work directories have produced identical boot,
firmware, rootfs tar/ext4/sparse and release metadata bytes on the recorded
host/toolchain; see the [offline result](production-evidence/2026-11-03-reproducible-build/README.md).
This does not establish hardware acceptance or cross-host reproducibility.
TF-A, U-Boot
and AIC8800 submodules must match their checkout gitlinks without tracked
modifications; their commits are included in the release metadata.

On hosts where a Perl upgrade invalidated generated `syscall.ph`/`ioctl.ph`,
the workflow regenerates those bindings inside its own work directory and
requires mmdebstrap to load them. It never modifies host Perl installation.

## Qualification and deployment

The offline builder marks `release.json` UNQUALIFIED. Keep that sealed manifest
unchanged; hardware acceptance is recorded in a separate attestation bound to
the exact tested artifact hashes. The [November 3 candidate attestation](production-evidence/2026-11-03-candidate-installation/QUALIFICATION.json)
records completed hardware checks and the reviewed GF1 protective-drop
disposition. It does not automatically qualify different source revisions,
inputs or output hashes. A rootfs image is not an in-place update bundle. Before any
installation, review the completed package, exact storage extents, a fresh
board identity/preflight and verified rollback copies. Keep the accepted
system intact while preparing this review. Do not flash the combined U-Boot
image at a guessed offset or reuse historical environment pins.

Hardware acceptance must cover the new boot chain, four CPUs/network/SSH,
kernel config/module identity, HDMI picture/audio/startup and repeated warm
boots, file playback/decoder gates, shutdown, and recovery. Use host-side test
tools without permanently shipping the bench framework. New decoder or
compiler failures require investigation; never mark the candidate accepted
merely because it has the same `6.18.38` release string.
Follow the [candidate qualification plan](production-qualification-plan.md)
before any maintenance window; consistent rollback backups and the actual
device-bound installation packet are still required.
