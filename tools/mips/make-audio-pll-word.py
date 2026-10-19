#!/usr/bin/env python3
"""Build a cold-only scalar PLL word-write experiment retaining init/retry.

Host artifacts only. Word read/modify/write was a historical byte-lane
hypothesis, later withdrawn after scalar-byte readback. Not a production fix.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('init', Path(__file__).with_name('make-audio-pll-init.py'))
init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init)
monitor, cap = init.monitor, init.monitor.cap
CAVE = 0x8B100C50
START = 0x93554
MARKERS = [0xD001, 0xD005, 0xD002, 0xD003, 0xD103, 0xD004, 0xC010, 0xC011, 0xC111]
SHIM_SHA = '43a7507a417f900aa3104fea7ad44d81e9b9642277b335a988e094524f9fe1a6'
SHIM_SIZE = 124
TABLE_LO, TABLE_HI = 600500, 607636


def check_shim(shim, size=SHIM_SIZE, sha=SHIM_SHA):
    if len(shim) != size or hashlib.sha256(shim).hexdigest() != sha:
        raise ValueError('shim length/SHA256 differs from reviewed instructions')


def build_shim(source='audio-pll-word-write.S', size=SHIM_SIZE, sha=SHIM_SHA,
               clang='clang', linker='ld.lld'):
    # Unique build paths prevent concurrent runs from sharing stale objects.
    from elftools.elf.elffile import ELFFile
    with tempfile.TemporaryDirectory(prefix='h713-pll-shim-') as temporary:
        directory = Path(temporary)
        obj, elf = directory/'shim.o', directory/'shim.elf'
        subprocess.run([clang, '--target=mipsel-none-elf', '-march=mips32r2',
                        '-mno-abicalls', '-fno-pic', '-c',
                        str(Path(__file__).with_name(source)), '-o', str(obj)], check=True)
        subprocess.run([linker, '-m', 'elf32ltsmip', '-Ttext', hex(CAVE),
                        '-e', '_start', str(obj), '-o', str(elf)], check=True)
        with elf.open('rb') as stream:
            image = ELFFile(stream)
            text = image.get_section_by_name('.text')
            if (not image.little_endian or image.elfclass != 32 or
                    image['e_machine'] != 'EM_MIPS' or text is None or
                    text['sh_addr'] != CAVE or image['e_entry'] != CAVE or
                    any(section['sh_type'] in ('SHT_REL', 'SHT_RELA') and section.num_relocations()
                        for section in image.iter_sections())):
                raise ValueError('unexpected shim ELF layout or unresolved relocations')
            shim = text.data()
    check_shim(shim, size, sha)
    return shim


def records(shim):
    check_shim(shim)
    words = list(struct.unpack('<31I', shim))
    words += [0x3C1AAE34]*9 + [0xAF400000]*9 + [0]*3
    return [(CAVE-0x40000000+i*4, 0, word) for i, word in enumerate(words)] + [
        (0x4B1803C4, 0xA0910000, monitor.jump(CAVE)),
        (0x4B18042C, 0xA0910000, monitor.jump(CAVE+16))]


def prepare(original, firmware, shim):
    table, profile = monitor.prepare(original, firmware)
    original = original[:monitor.UBOOT_PADDED_SIZE]
    candidate = bytearray(original)
    offset = profile['fit_table_offset']
    candidate[offset:offset+len(table)] = table
    dataoff, datasize = monitor.fit_uboot_region(original)
    if not (dataoff <= TABLE_LO <= START and START+864 <= TABLE_HI <= dataoff+datasize):
        raise ValueError('second table or ownership window outside U-Boot data')
    if not (offset+len(table) <= START or START+864 <= offset):
        raise ValueError('replacement tables overlap')
    old = [cap.RECORD.unpack_from(original, START+i*16) for i in range(54)]
    for index, marker in enumerate(MARKERS):
        group = old[index*6:index*6+6]
        if ([r[2] for r in group[:3]] != [0x3C1AAE34, 0x341B0000 | marker, 0xAF5B0000]
                or group[4][2] != 0):
            raise ValueError('progress-marker table preimage mismatch')
        site = group[5][0]-0x4B100000
        if not 0 <= site <= len(firmware)-4 or group[5][1] != struct.unpack_from('<I', firmware, site)[0]:
            raise ValueError('progress-marker hook preimage mismatch')
    before = [cap.RECORD.unpack_from(original, p) for p in range(TABLE_LO, TABLE_HI, 16)]
    occupied = {cap.RECORD.unpack_from(candidate, p)[0]
                for p in range(TABLE_LO, TABLE_HI, 16) if not START <= p < START+864}
    extra = records(shim)
    if (len(extra) != 54 or len({r[0] for r in extra}) != 54 or
            cap.census(old) != cap.census(extra)):
        raise ValueError('second table size, uniqueness or relocation census changed')
    for address, expected, _ in extra:
        if address in occupied:
            raise ValueError(f'shim address already owned: {address:#x}')
        site = address-0x4B100000
        if (address & 3 or not 0 <= site <= len(firmware)-4 or
                struct.unpack_from('<I', firmware, site)[0] != expected):
            raise ValueError(f'shim firmware site mismatch: {address:#x}')
    candidate[START:START+864] = cap.encode(extra)
    after = [cap.RECORD.unpack_from(candidate, p) for p in range(TABLE_LO, TABLE_HI, 16)]
    if cap.census(before) != cap.census(after):
        raise ValueError('global relocation census changed')
    if len(candidate) != len(original) or any(
            not (offset <= i < offset+672 or START <= i < START+864)
            for i, (a, b) in enumerate(zip(original, candidate)) if a != b):
        raise ValueError('candidate changes escape the two fixed tables')
    profile['records'] += extra
    profile.update(shim_address=CAVE, shim_bytes=len(shim), second_table_offset=START,
                   removed_markers=MARKERS, fields={})
    return bytes(candidate), profile


def validated_records(profile, size=SHIM_SIZE, sha=SHIM_SHA):
    """Authenticate record addresses/words before a verifier opens /dev/mem.

    Rebuild the entire expected record list from a hash-pinned shim and trusted
    generators; arbitrary profile addresses never become a device allowlist.
    """
    supplied = profile.get('records')
    if (not isinstance(supplied, list) or len(supplied) != 96 or
            any(not isinstance(r, list) or len(r) != 3 or
                any(type(v) is not int for v in r) or
                not 0 <= r[0] < 2**64 or any(not 0 <= v < 2**32 for v in r[1:])
                for r in supplied)):
        raise ValueError('expected 96 well-formed instruction records')
    words = {r[0]: r[2] for r in supplied}
    try:
        shim = b''.join(struct.pack('<I', words[CAVE-0x40000000+i*4]) for i in range(size//4))
    except KeyError as error:
        raise ValueError('profile missing shim instructions') from error
    check_shim(shim, size, sha)
    expected = init.records() + records(shim)
    if (supplied != [list(r) for r in expected] or profile.get('fields') != {} or
            profile.get('firmware_sha256') != monitor.FW_SHA or
            profile.get('installed_uboot_padded_sha256') != monitor.UBOOT_SHA):
        raise ValueError('profile does not match the reviewed experiment')
    return expected


def main(source='audio-pll-word-write.S', size=SHIM_SIZE, sha=SHIM_SHA,
         scope='historical scalar PLL word-write experiment; init/retry retained'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('uboot', type=Path)
    parser.add_argument('firmware', type=Path)
    parser.add_argument('output', type=Path, help='new output directory (must not exist)')
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--linker', default='ld.lld')
    args = parser.parse_args()
    original, firmware = args.uboot.read_bytes(), args.firmware.read_bytes()
    shim = build_shim(source, size, sha, args.clang, args.linker)
    candidate, profile = prepare(original, firmware, shim)
    original = original[:monitor.UBOOT_PADDED_SIZE]
    manifest = dict(candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                    input_sha256=monitor.UBOOT_SHA, bytes=len(candidate), sectors=len(candidate)//512,
                    records=len(profile['records']), shim_sha256=hashlib.sha256(shim).hexdigest(),
                    changed_bytes=sum(a != b for a, b in zip(original, candidate)),
                    table_ranges=[[profile['fit_table_offset'], profile['fit_table_offset']+672],
                                  [START, START+864]], storage_modified=False, scope=scope)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in [('shim.bin', shim), ('uboot-audio-monitor.bin', candidate), ('uboot-before.bin', original)]:
        (args.output/name).write_bytes(data)
    (args.output/'audio-monitor-profile.json').write_text(json.dumps(profile, indent=2)+'\n')
    (args.output/'candidate-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
