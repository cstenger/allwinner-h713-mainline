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

python3 - "$SRC_DIR" "$OUT_DIR" "$PROJECT_ROOT/tools/video/vectors" <<'PY'
import os, random, sys

src_dir, out_dir, vec_dir = sys.argv[1], sys.argv[2], sys.argv[3]
SEED = 713

# One source per codec path, so a failure can be attributed to a codec rather
# than to the corruption itself. MPEG-2 uses the same start-code structure as
# Annex-B, so the corruptions below apply unchanged; for it, "NAL unit" reads as
# "start-code-delimited element" (sequence header, GOP header, picture, slice).
#
# (vector, extension, TAG). The tag is explicit rather than derived from the
# extension, and that is not tidiness -- it is a bug that already happened.
# While it was `{"h265": "h", ...}[ext]`, adding a second .h265 source gave both
# the tag "h" and the second one SILENTLY OVERWROTE the first: every
# b0N-h-*.h265 became Main10 while its name, and the suite dispatching on that
# name, still said 8-bit HEVC. Coverage would have moved rather than grown, and
# nothing would have reported it. Keep these unique.
SOURCES = [
    ("h01-640x480-main", "h265", "h"),
    ("v03-1280x720-main", "h264", "v"),
    ("m01-352x288-progressive", "m2v", "m"),
    # Main10 earns its own source rather than riding on h01. The 10-bit path
    # allocates and programs a second plane -- cedrus_h265_2bit_size(), the
    # extra capture space and the 10BIT_CONFIGURE registers -- none of which
    # the 8-bit cases touch. Error handling there is exactly the code a
    # truncated or corrupted payload reaches, and it was completely uncovered:
    # every malformed stream in this suite was 8-bit.
    ("h07-640x480-main10", "h265", "t"),
]


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


seen_tags = set()
for vec, ext, tag in SOURCES:
    if tag in seen_tags:
        raise SystemExit(f"duplicate tag {tag!r} for {vec}: outputs would "
                         f"overwrite another source's, silently")
    seen_tags.add(tag)
    path = os.path.join(src_dir, f"{vec}.{ext}")
    if not os.path.exists(path):
        print(f"!!  {path} missing, skipped")
        continue

    data = bytearray(open(path, "rb").read())
    nals = nal_units(bytes(data))
    # The tag drives the codec dispatch in decode-robustness-test.sh, which
    # matches on *-h-*, *-t-*, *-m-* and falls through to H.264.
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

# b09/b10 -- real damage, not synthetic. These two field-coded MPEG-2 streams
# came off the board rather than out of this script, and neither is a simple
# truncation of the good stream: one has 3,860 bytes removed mid-stream, the
# other 395 bytes altered in place. Whatever produced them understood the
# picture layout, and that tool is not in this repo, so they are committed under
# tools/video/vectors/ and copied in here.
#
# They are worth keeping distinct from b01-b08 because they are FIELD-coded, and
# field pictures are the case kernel patch 0123 exists for. A malformed-stream
# suite made only of corrupted frame-picture streams cannot reach that path.
REAL_DAMAGE = [
    ("m05-720x576-field-shortfirst.m2v", "b09-m-field-shortfirst.m2v"),
    ("m05-720x576-field-damaged.m2v", "b10-m-field-damaged.m2v"),
]
print("==> committed real-damage vectors")
for srcname, dstname in REAL_DAMAGE:
    p = os.path.join(vec_dir, srcname)
    if not os.path.exists(p):
        print(f"!!  {p} missing, skipped -- field-coded damage is UNCOVERED")
        continue
    write(dstname, open(p, "rb").read())
PY

echo
echo "Bad streams in $OUT_DIR:"
ls -1 "$OUT_DIR" | sed 's/^/  /'
