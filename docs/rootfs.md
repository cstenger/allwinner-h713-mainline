# arm64 Debian rootfs

Builds a 64-bit Debian 13 (trixie) root filesystem for the board, **rootless**
on an Arch/CachyOS host, with `mmdebstrap` + `qemu-user` binfmt. Boots from the
eMMC `UDISK` partition (`/dev/mmcblk0p26`) to a serial root login.

## Prerequisites

- `mmdebstrap` (AUR), `qemu-user-static` + binfmt (for the aarch64 chroot hook),
  `e2fsprogs`, `android-tools` (`img2simg`), `util-linux` (`unshare`).
- The customize hook: [../tools/rootfs/customize.sh](../tools/rootfs/customize.sh).

## 1. Bootstrap the tree

```
mmdebstrap --arch=arm64 --skip=check/qemu \
  --include=systemd-sysv,ifupdown,isc-dhcp-client,openssh-server \
  --customize-hook='../tools/rootfs/customize.sh "$1"' \
  trixie rootfs.tar \
  'deb [trusted=yes] https://deb.debian.org/debian trixie main'
```

- `[trusted=yes]` because the Arch host has no Debian archive keyring — the
  bootstrap is therefore **unsigned**. Fine for bring-up; rebuild with a proper
  keyring for anything production.
- The customize hook sets hostname `h713-arm64`, `root:root`, a serial getty on
  `ttyS0`, enables ssh, and writes `/etc/fstab` with root on `mmcblk0p26`.

## 2. Pack a rootless ext4 image

The uid/gid map must be full so `chown` inside the image (e.g. shadow gid 42)
works; `mke2fs -d` writes the tree with correct ownership without root:

```
unshare --map-auto --map-root-user -- sh -c '
  mkdir -p rootfs-extract
  tar -C rootfs-extract --exclude=./dev/* -xf rootfs.tar
  mke2fs -d rootfs-extract -t ext4 -L UDISK rootfs.ext4 2G
'
img2simg rootfs.ext4 rootfs.simg          # Android-sparse for fastboot
```

Exclude `/dev/*` from the tar (devtmpfs populates it at boot); a `mknod` would
need real root.

## 3. Write it to the board

Flash `rootfs.simg` to the `UDISK` (p26) partition — see
[flash.md](flash.md#method-3--fastboot). Sparse is required because the image
exceeds the 32 MiB fastboot buffer.

## After first boot

- **Resize:** the image is 2 GiB on a ~4.6 GiB partition — `resize2fs
  /dev/mmcblk0p26` to fill it.
- **Harden:** drop an SSH key into `/root/.ssh/authorized_keys` and disable
  password auth before any real use (root password is `root`).

The working artifacts of a prior build live in `~/Projects/h713-arm64/rootfs-build/`
(not committed).
