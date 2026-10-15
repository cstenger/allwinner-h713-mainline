#!/usr/bin/env python3
"""Check exact audio EDID preservation and malformed-payload rejection."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / 'tools/hdmi/make-edid-trial-code.py'
EDID = ROOT / 'tools/hdmi/fixtures/hdmi-audio-edid.hex'


class Payload(unittest.TestCase):
    def test_audio_extension_is_preserved_and_invalid_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = (Path(directory) / name for name in ('input.bin', 'payload.h'))
            data = bytes.fromhex(EDID.read_text())
            fixture_result = subprocess.run([sys.executable, str(GENERATOR), '--edid', str(EDID), str(output)], capture_output=True)
            self.assertEqual(fixture_result.returncode, 0, fixture_result.stderr)
            fixture_header = output.read_bytes()
            source.write_bytes(data)
            command = [sys.executable, str(GENERATOR), '--edid', str(source), str(output)]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), fixture_header)
            payload = output.read_text().split('static const u8 edid_trial_data[] = {', 1)[1]
            self.assertEqual(bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', payload)), data)
            corrupt = bytearray(data)
            corrupt[140] ^= 1
            for invalid in (data[:-1], bytes(corrupt), data[:128] + bytes(128)):
                output.unlink(missing_ok=True)
                source.write_bytes(invalid)
                result = subprocess.run(command, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())


MARKER, BASE, CHECK, META = 0x48444d49, 0x4f00, 0x4aa0, 0x4a80
REGS = [0x1014, 0x1b00, 0x1b04, 0x1b08, 0x1020, 0x1030, 0x1034, 0x1038]
# Pre-trial values seen on hardware; 1b00/1b08 bits 31:24 read back as zero.
ORIGINAL = {0x1014: 7, 0x1b00: 0x00a0a0a0, 0x1b04: 0x07000000, 0x1b08: 0x00606060}


def sign(value, bits):
    return value - (1 << bits) if value >> (bits - 1) & 1 else value


class Scp:
    """Just enough big-endian-decoded OR1K for the generated payload. SRAM
    words are the ARM's little-endian u32 view, as on hardware."""
    def __init__(self, header, drop=()):
        code = [int(x, 16) for x in re.findall(r'0x([0-9a-f]{8}),', header.split('edid_trial_data')[0])]
        data = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', header.split('edid_trial_data[] = {', 1)[1]))
        self.sram = {0x4000 + 4 * i: w for i, w in enumerate(code)}
        self.sram.update({0x4680 + i: int.from_bytes(data[i:i + 4], 'little') for i in range(0, 256, 4)})
        self.sram.update({CHECK + 4 * i: 0xffffffff for i in range(8)})
        self.sram[BASE + 32] = self.sram[BASE + 64] = 1
        self.io = dict(ORIGINAL)
        self.io.update({0x1c00 + 0x100 * b + i: 0x01020304 * (b + 1) + i for b in range(3) for i in range(0, 256, 4)})
        self.edid = {a: v for a, v in self.io.items() if a >= 0x1c00}
        self.drop, self.restoring = drop, False
        self.r, self.pc, self.flag = [0] * 32, 0x4000, False

    def load(self, address):
        if address >> 16 == 0x0709:
            return self.io.get(address & 0xffff, 0)
        return self.sram.get(address, 0)

    def store(self, address, value):
        if address >> 16 != 0x0709:
            self.sram[address] = value
        elif not (self.restoring and address & 0xffff in self.drop):
            offset = address & 0xffff
            self.io[offset] = value & 0x00ffffff if offset in (0x1b00, 0x1b08) else value

    def step(self):
        word, r = self.sram[self.pc], self.r
        op, d, a, b = word >> 26, word >> 21 & 31, word >> 16 & 31, word >> 11 & 31
        imm, target = word & 0xffff, None
        if op in (0, 3, 4):
            if op == 0 or self.flag == (op == 4):
                target = self.pc + 4 * sign(word & 0x3ffffff, 26)
        elif op == 5:
            pass
        elif op == 6:
            r[d] = imm << 16
        elif op == 0x27:
            r[d] = (r[a] + sign(imm, 16)) & 0xffffffff
        elif op == 0x2a:
            r[d] = r[a] | imm
        elif op == 0x21:
            r[d] = self.load((r[a] + sign(imm, 16)) & 0xffffffff)
        elif op == 0x35:
            self.store((r[a] + sign(d << 11 | word & 0x7ff, 16)) & 0xffffffff, r[b])
        elif op == 0x38 and word & 0x30f == 3:
            r[d] = r[a] & r[b]
        elif op == 0x39 and d == 1:
            self.flag = r[a] != r[b]
        elif op == 0x2f and d == 1:
            self.flag = r[a] != sign(imm, 16) & 0xffffffff
        else:
            raise AssertionError(f'unmodelled instruction {word:08x} at {self.pc:x}')
        r[0] = 0
        if target is None:
            self.pc += 4
        else:
            self.pc += 4
            self.step()  # delay slot
            self.pc = target

    def run_until(self, offset):
        for _ in range(100000):
            if self.sram.get(BASE + offset) == MARKER:
                return
            self.step()
        raise AssertionError(f'payload never wrote +{offset}')


class Readback(unittest.TestCase):
    def payload(self, *flags):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), *flags, '--edid', str(EDID), str(output)], check=True, capture_output=True)
            return output.read_text()

    def lifetime(self, drop=()):
        scp = Scp(self.payload('--verify-restore'), drop)
        scp.run_until(8)  # ready: HPD asserted, EDID served
        self.assertEqual(scp.io[0x1014], 0)
        self.assertEqual(scp.io[0x1020], 3)
        self.assertNotEqual(scp.io[0x1c00], scp.edid[0x1c00])
        scp.restoring = True
        scp.sram[BASE + 16] = 1  # module stop request
        scp.run_until(28)
        self.assertEqual(scp.sram.get(BASE + 24, 0), 0)
        self.assertEqual(scp.sram.get(BASE + 12, 0), 0)
        meta = [scp.sram[META + 4 * i] for i in range(8)]
        check = [scp.sram[CHECK + 4 * i] for i in range(8)]
        return scp, meta, check

    def test_clean_restore_reads_back_every_original(self):
        scp, meta, check = self.lifetime()
        self.assertEqual(meta, [ORIGINAL.get(a, 0) for a in REGS])
        self.assertEqual(check, meta)  # the module's stop comparison passes
        self.assertEqual({a: scp.io.get(a, 0) for a in REGS}, {a: ORIGINAL.get(a, 0) for a in REGS})
        self.assertEqual({a: scp.io[a] for a in scp.edid}, scp.edid)

    def test_a_restore_write_that_does_not_land_is_caught(self):
        # 1014 is restored last among DDC/HPD, 1038 is the very last write.
        for register in (0x1014, 0x1b04, 0x1038):
            with self.subTest(register=hex(register)):
                _, meta, check = self.lifetime(drop=(register,))
                self.assertEqual([i for i in range(8) if check[i] != meta[i]], [REGS.index(register)])

    def test_default_payload_has_no_readback(self):
        header = self.payload()
        self.assertNotIn('EDID_CHECK_OFFSET', header)
        scp = Scp(header)
        scp.run_until(8)
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)], [0xffffffff] * 8)


if __name__ == '__main__':
    unittest.main()
