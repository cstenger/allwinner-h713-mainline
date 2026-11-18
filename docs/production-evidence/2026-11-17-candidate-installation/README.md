# Candidate installation — November 17, 2026

**The `cb939748` final build is installed on the DDR3 board and boots through
its new SPL and proper.** Every packet gate passed; the whole-disk readback
before first boot matched the prediction. Hardware qualification of the
image (HDMI picture/audio by eye, cold boot, lifecycle, endurance) is still
pending; nothing here marks the release qualified.

## Sequence

1. **Entry:** `systemctl reboot --reboot-argument=bootloader` with a passive
   UART listener; preboot set `bootdelay=-1` and the prompt held with no
   keypress; `gpio set PB5`. This replaces INSTALL.md's older cold-catch entry
   step, which predates `bootdelay=0`. Identity: `serial#`
   `034000428c2136eb`, saved bootcmd/preboot match the packet, mmc 1 part 0
   is the 7.3 GiB `8GTF4R`.
2. **Fresh backup:** Linux had run since the
   [first backup](../2026-11-17-installation-packet/README.md), so a second
   two-read backup was taken in the same hold: **`1033f877…`** (only Linux p26
   changed; FAT, SPL, proper and environment identical to the first). Host-copy
   verification clean. The packet was rebuilt on it and verifies offline;
   predicted pre-boot install hash **`60d13236…`**.
3. **Preflight (read-only):** PASS, device = baseline `1033f877…`. Two earlier
   attempts stopped before reading the disk: once on a packet self-check
   (`expected readback changed: install`) that two recomputations could not
   reproduce, once because a diagnostic import left a bytecode cache in the
   sealed packet folder (removed). All gates fail closed.
4. **Writes,** one phase at a time from the packet transcript, each with five
   exact `getvar` gates and the transcript's `mmc read`/`crc32` checkpoints:

   | Phase | Extent | Checkpoints |
   | --- | --- | --- |
   | root | LBA `0x54c400`, 2 GiB (262.8 s) | 128 pairs PASS |
   | fat | LBA `0x22000`, 32 MiB | 2 pairs PASS |
   | proper | LBA `0x49ac00`, 1867 sectors | PASS (`d9c83b9d`) |
   | spl (last) | LBA `0x10`, 64 sectors | PASS (`51a7e1eb`) |

   The first root attempt stopped at the first `getvar` (fastboot USB I/O is
   blocked inside the agent's command sandbox) before any write; after the
   root write, the runner missed the prompt behind buffered flash output, so
   the 128 checkpoints were run separately. No write was repeated.
5. **Final readback (read-only):** PASS, whole device **`60d13236…`** =
   prediction, including every byte outside the four writes. RAM-only fastboot
   aliases cleared; environment never saved.
6. **First boot** (`run bootcmd`, old U-Boot still in RAM): booted in ~20 s.
   New ED25519 host key `SHA256:ztv0mbmpe9oNrNT3kR/VznBPNiqu7+BaGmbGtgUADpo`
   read over UART, pinned, and matched by the network key. Four CPUs, system
   running, no failed units, ext4 errors 0, rootfs grown to 2.83 GB, startup
   check PASS, CPU_COMM IRQ, all three HDMI manifests verified, Wi-Fi AP and
   Bluetooth up. Of 17,352 candidate rootfs files only `/etc/machine-id`
   differs. Installed SPL `a03a06c4…`, FIT `966eba3c…`.
7. **New boot chain:** an ordinary reboot ran SPL and proper
   `2026.07-rc5-g320a17f71d41-h713-32671ea3` (the 0007 build), loaded the
   environment from `0x93d80000` and booted Linux; the same health checks pass.
8. **HDMI:** Chris confirmed HDMI picture and sound on the projector on that
   boot (`24bb4c30`), with no intervention or service restart.
9. **Cold boot:** clean `systemctl poweroff` from `24bb4c30` (previous-boot
   journal ends in an ordinary systemd shutdown), serial and USB unplugged,
   power off at least one minute. Boot `6a4a8b2f`: Chris saw the picture; system
   running, no failed units, ext4 errors 0, startup check PASS, CPU_COMM IRQ,
   Bluetooth up. All eight HDMI units active/success with 0 restarts; video
   active at 9.67 s monotonic (11.6 s on 2026-11-09). `systemd-analyze`:
   2.258 s kernel + 9.101 s userspace = 11.360 s. One kernel error not seen on
   the earlier boots: AIC8800 `sdio_err ... bus err` during Wi-Fi bring-up;
   Wi-Fi came up and carried SSH.

## Rollback

The packet's `ROLLBACK.md` restores baseline `1033f877…` exactly (the
four extents, including Linux p26's full 2.75 GiB). It has not been run;
a full rollback write has still never been rehearsed.

## Not yet covered

Speaker delay measurement;
the lifecycle regression, standby thermal and two-hour endurance from the
completion checklist; decoder/playback, keys, mirror/keystone. Private
receipts, transcripts and the packet:
`local/recovery/2026-11-17-deployment-packet/` and
`local/releases/h713-ddr3-installation-packet-20261117b/`.
