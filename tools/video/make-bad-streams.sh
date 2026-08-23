#!/usr/bin/env bash
# Generate deliberately malformed streams from the good vectors. RUNS ON THE HOST.
#
# Every stream this project has ever fed the decoder is well-formed, which means
# the whole bit-exactness gate answers only "is the output right for good
# input". A production decoder is fed truncated files, streams that start
# mid-GOP, and payloads corrupted in transit, and the property that matters
# there is not output at all -- it is:
#
#   the decoder fails, and the VIDEO ENGINE IS STILL USABLE AFTERWARDS.
#
# That second half is why these exist. A cedrus `frame processing timed out!`
# is known to wedge the VE for every client on this board until reboot, and
# nothing in the test suite could provoke one on purpose.
#
# CORRUPTION IS DETERMINISTIC. Seed 713, fixed offsets, no wall-clock input --
# a robustness failure has to be reproducible or it cannot be bisected, and
# "it failed once with random data" is not a bug report.
#
# WHAT REACHES THE HARDWARE, and why the cases differ. ffmpeg parses headers in
# software and hands only slice payload to the accelerator, so a corrupted SPS
# is usually rejected before the VE is ever opened -- a legitimate outcome that
# tests ffmpeg, not us. The cases that actually exercise the engine are the ones
# that keep headers valid and damage the payload (b03, b06, b08). The gate
# reports the VE interrupt delta per case so this is visible rather than assumed.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SRC_DIR=${1:-$PROJECT_ROOT/local/video-test}
OUT_DIR=${2:-$SRC_DIR/bad}

mkdir -p "$OUT_DIR"

python3 - "$SRC_DIR" "$OUT_DIR" <<'PY'
import os, random, sys

src_dir, out_dir = sys.argv[1], sys.argv[2]
SEED = 713

# (vector, extension) -- one HEVC and one H.264 source, so a failure can be
# attributed to a codec path rather than to the corruption itself.
SOURCES = [("h01-640x480-main", "h265"), ("v03-1280x720-main", "h264")]


def nal_units(data):
    """Offsets of each Annex-B start code, in order."""
    out, i = [], 0
    while True:
        j = data.find(b"\x00\x00\x01", i)
        if j < 0:
            break
        out.append(j - 1 if j > 0 and data[j - 1] == 0 else j)
        i = j + 3
    return out


def write(name, blob):
    path = os.path.join(out_dir, name)
    with open(path, "wb") as f:
        f.write(blob)
    print(f"    {name:34s} {len(blob):9d} bytes")


for vec, ext in SOURCES:
    path = os.path.join(src_dir, f"{vec}.{ext}")
    if not os.path.exists(path):
        print(f"!!  {path} missing, skipped")
        continue

    data = bytearray(open(path, "rb").read())
    nals = nal_units(bytes(data))
    tag = "h" if ext == "h265" else "v"
    print(f"==> {vec} ({len(data)} bytes, {len(nals)} NAL units)")

    rng = random.Random(SEED)

    # b01 -- the commonest real failure: the file simply stops. Half of it.
    write(f"b01-{tag}-truncated-half.{ext}", data[: len(data) // 2])

    # b02 -- stops inside the last NAL rather than between two, so the decoder
    # is mid-slice when the data runs out.
    write(f"b02-{tag}-truncated-mid-nal.{ext}", data[: int(len(data) * 0.93)])

    # b03 -- headers intact, payload damaged. THIS is the case that reaches the
    # video engine: 64 flipped bits spread through everything after the first
    # slice header, which is what a bad link or a bad sector looks like.
    payload_start = nals[3] if len(nals) > 3 else len(data) // 4
    b03 = bytearray(data)
    for _ in range(64):
        pos = rng.randrange(payload_start, len(b03))
        b03[pos] ^= 1 << rng.randrange(8)
    write(f"b03-{tag}-bitflip-payload.{ext}", b03)

    # b04 -- damage the parameter sets instead. Expected to be refused in
    # software; included so that "refused cleanly" is on the record as the
    # correct behaviour rather than an untested assumption.
    b04 = bytearray(data)
    for _ in range(8):
        pos = rng.randrange(nals[0] + 4, nals[2] if len(nals) > 2 else 64)
        b04[pos] ^= 1 << rng.randrange(8)
    write(f"b04-{tag}-bitflip-headers.{ext}", b04)

    # b05 -- nothing at all. A decoder that hangs on an empty file is a
    # decoder that hangs on a closed socket.
    write(f"b05-{tag}-empty.{ext}", b"")

    # b06 -- valid parameter sets followed by noise wearing a start code, so
    # the stream stays parseable long enough to hand garbage to the hardware.
    head = bytes(data[: nals[3]]) if len(nals) > 3 else bytes(data[:512])
    noise = bytearray()
    for _ in range(24):
        noise += b"\x00\x00\x01"
        noise += bytes(rng.randrange(256) for _ in range(rng.randrange(64, 512)))
    write(f"b06-{tag}-garbage-after-headers.{ext}", head + bytes(noise))

    # b07 -- start mid-GOP: drop everything before the second slice, so every
    # frame references a picture that was never decoded.
    if len(nals) > 5:
        write(f"b07-{tag}-no-first-slice.{ext}", data[nals[5]:])

    # b08 -- every NAL truncated to half its length. Maximally hostile while
    # remaining a sequence of start codes: the decoder keeps being handed a new
    # unit that ends too early.
    b08 = bytearray()
    for i, off in enumerate(nals):
        end = nals[i + 1] if i + 1 < len(nals) else len(data)
        unit = data[off:end]
        keep = max(6, len(unit) // 2)
        b08 += unit[:keep]
    write(f"b08-{tag}-every-nal-halved.{ext}", bytes(b08))
PY

echo
echo "Bad streams in $OUT_DIR:"
ls -1 "$OUT_DIR" | sed 's/^/  /'
