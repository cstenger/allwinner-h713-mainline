# arm64 Debian rootfs

`tools/rootfs/build.sh` creates a signed Debian 13 (trixie) arm64 root
filesystem for the eMMC `UDISK` partition (`/dev/mmcblk0p26`). The build is
rootless, installs the modules from the exact pinned Linux 6.18.38 build tree,
and emits both raw ext4 and Android-sparse images.

## Security and trust model

- A public key is a mandatory argument; no personal key is stored in Git.
- Root has no usable password. SSH allows public-key authentication only.
- The physical `ttyS0` console autologins as root for board recovery and
  bring-up. Physical serial access is therefore privileged access.
- SSH host keys, the machine ID, and the systemd random seed are removed from
  the image and generated independently on first boot. An idempotent service
  runs `ssh-keygen -A` before SSH so a missing key can never race sshd startup.
- Debian `InRelease` and packages are verified with the Debian archive
  keyring. The final deb822 source uses
  `Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg`; there is no
  `[trusted=yes]` escape hatch.

If the host does not have `debian-archive-keyring` installed, the builder
downloads its Arch package, verifies the detached package signature using the
host pacman keyring, and extracts a temporary bootstrap keyring into the ignored
build cache.

## Prerequisites

On Arch/CachyOS:

- `mmdebstrap`, `apt`, `qemu-user-static-binfmt`
- `e2fsprogs`, `kmod`, `util-linux`
- `android-tools` (`img2simg` and `simg2img`)
- `curl`, `libarchive`, `openssh`

The global `systemd-binfmt` service does **not** need to be enabled. The builder
creates a private user/mount namespace and registers `qemu-aarch64-static` only
inside it. Host sudo/root access is not used.

The kernel must have been built first:

```
build/build.sh kernel
```

## Build

Pass the public key that should be authorized for root:

```
tools/rootfs/build.sh --ssh-key ~/.ssh/id_ed25519.pub
```

Optional arguments:

```
--kernel-tree DIR   use an explicit built kernel tree
--output-dir DIR    output directory (default: build/out)
--image-size SIZE   initial ext4 size (default: 2G)
```

The default kernel-tree discovery intentionally requires exactly one complete
content-addressed `build/linux-6.18.38-*` tree. This prevents modules from a
stale kernel build being installed accidentally.

## Outputs and validation

The builder publishes these ignored artifacts only after all staging-tree and
filesystem checks pass:

| Artifact | Purpose |
|----------|---------|
| `build/out/rootfs.tar` | Final customized filesystem tree, including modules |
| `build/out/rootfs.ext4` | 2 GiB raw ext4 image labelled `UDISK` |
| `build/out/rootfs.simg` | Android-sparse image for fastboot |
| `build/out/rootfs.manifest` | Suite, kernel, module count, size, and SSH-key fingerprint |
| `build/out/ROOTFS-SHA256SUMS` | SHA-256 checksums for all four files |

Verify the published set with:

```
(cd build/out && sha256sum -c ROOTFS-SHA256SUMS)
```

The build checks key permissions and identity, locked password state, SSH
policy, signed APT sources, first-boot identity handling, service enablement,
growfs configuration, and the installed module dependency database. It then
runs read-only `e2fsck`. The first completed build contained all 24 modules for
kernel `6.18.38`; sparse-to-raw conversion was byte-exact in offline testing.

**Hardware-verified on the HY200 bench board (2026-07-19):** the sparse image
flashed through U-Boot Fastboot, booted twice, and expanded from 2 GiB to the
full 4.5 GiB filesystem. `ttyS0` root autologin, udev, dbus, growfs, SSH host-key
generation, and sshd all completed successfully with zero failed systemd units.
The machine ID and all three generated SSH host keys persisted unchanged across
the second boot. All 24 modules were present; Cedrus and Panfrost loaded and
bound to their devices.

## Flash

Enter fastboot from the U-Boot ACM console:

```
run fastboot_mode
```

Then flash the sparse image from the host:

```
fastboot flash UDISK build/out/rootfs.simg
fastboot reboot
```

`rootfs.simg` is required instead of the 2 GiB raw image because U-Boot's
fastboot download buffer is 32 MiB; the host fastboot tool chunks sparse input.

## First-boot checks

The `x-systemd.growfs` root mount option expands the deliberately small ext4
filesystem to fill `UDISK` during first boot. On the serial console, verify:

```
uname -r
findmnt /
test -d /lib/modules/$(uname -r)
modprobe sunxi-cedrus
systemctl --no-pager status systemd-growfs-root.service ssh.service
```

Expected kernel release is `6.18.38`. The bench currently exposes only loopback,
so sshd was verified listening with the configured public-key-only policy but a
remote login cannot be tested until a supported network interface is brought
up. Networking hardware/firmware remains a separate roadmap item.

The artifacts under `local/h713-arm64/rootfs-build/` are historical. They
predate signed bootstrapping, module installation, growfs, and key-only SSH.
