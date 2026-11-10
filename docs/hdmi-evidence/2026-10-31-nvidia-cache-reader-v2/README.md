# NVIDIA reader v2 preparation evidence

Prepared and sealed for one explicitly authorized snapshot; no live GPU ioctl
was run. The operator reports the board powered off. The previous preserved
HDMI failure and SCP session have ended.

[Qualification report](../../nvidia-cache-reader-2026-10-31.md),
[result](RESULT.json), [live gate](LIVE-GATE.json), [37 tests](tests.txt),
[11 safety mutations](mutations.txt), and [exact vendor ABI](abi.json).

The live path uses only the control node, an already-attached/in-use GPU,
owned query objects, non-privileged fixed cached/static/history requests and
own-client cleanup. No GPU node open, attach, modeset, consuming notification,
fresh EDID, DDC, reset or board action is selected. Libc ioctl errors, including
EINTR, are not retried by the application.

Qualification relies on NVIDIA's supported version-matched API contract and
audited host lifecycle. Firmware execution remains; its physical implementation
is not proven. This is not a firmware-free preservation guarantee, electrical
HPD measurement or reproduction of the power-cycled failure.

Private packet and adjacent archive:
`local/recovery/2026-10-31-nvidia-cache-reader-v2/`.
Cached host baseline, source references, source copies, full ABI build and
checksums remain there. All live execution evidence fields are false/zero.
