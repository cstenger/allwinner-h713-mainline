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
EXT, ACK, HOLD, DDC_ON, RELEASE = 0x4ac0, 116, 2, 3, 4
REGS = [0x1014, 0x1b00, 0x1b04, 0x1b08, 0x1020, 0x1030, 0x1034, 0x1038]
# Pre-trial values seen on hardware; 1b00/1b08 bits 31:24 read back as zero.
ORIGINAL = {0x1014: 7, 0x1b00: 0x00a0a0a0, 0x1b04: 0x07000000, 0x1b08: 0x00606060}


def sign(value, bits):
    return value - (1 << bits) if value >> (bits - 1) & 1 else value


class Scp:
    """Just enough big-endian-decoded OR1K for the generated payload. SRAM
    words are the ARM's little-endian u32 view, as on hardware."""
    def __init__(self, header, drop=()):
        main, _, rest = header.partition('edid_readvertise_code')
        code = [int(x, 16) for x in re.findall(r'0x([0-9a-f]{8}),', main.split('edid_trial_data')[0])]
        ext = [int(x, 16) for x in re.findall(r'0x([0-9a-f]{8}),', rest.split('edid_trial_data')[0])]
        data = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', header.split('edid_trial_data[] = {', 1)[1]))
        self.sram = {0x4000 + 4 * i: w for i, w in enumerate(code)}
        self.sram.update({EXT + 4 * i: w for i, w in enumerate(ext)})
        self.sram.update({0x4680 + i: int.from_bytes(data[i:i + 4], 'little') for i in range(0, 256, 4)})
        self.sram.update({CHECK + 4 * i: 0xffffffff for i in range(8)})
        self.sram[BASE + 32] = self.sram[BASE + 64] = 1
        self.io = dict(ORIGINAL)
        self.io.update({0x1c00 + 0x100 * b + i: 0x01020304 * (b + 1) + i for b in range(3) for i in range(0, 256, 4)})
        self.edid = {a: v for a, v in self.io.items() if a >= 0x1c00}
        self.drop, self.restoring = drop, False
        self.io_writes = []
        self.wrap, self.byte_reads = {}, []
        self.r, self.pc, self.flag = [0] * 32, 0x4000, False

    def load(self, address):
        if address >> 16 == 0x0709:
            return self.io.get(address & 0xffff, 0)
        return self.sram.get(address, 0)

    def load8(self, address):
        """l.lbz: the byte-wide wrapper answers 0x0684xxxx; anything else is SRAM."""
        self.byte_reads.append(address)
        if address >> 16 == 0x0684:
            return self.wrap.get(address, 0) & 0xff
        if address >> 16 == 0x0709:
            raise AssertionError(f'byte read of 32-bit receiver register {address:#x}')
        return self.sram.get(address & ~3, 0) >> 8 * (address & 3) & 0xff

    def store(self, address, value):
        if address >> 16 != 0x0709:
            self.sram[address] = value
        elif not (self.restoring and address & 0xffff in self.drop):
            offset = address & 0xffff
            self.io[offset] = value & 0x00ffffff if offset in (0x1b00, 0x1b08) else value
            self.io_writes.append((offset, self.io[offset]))

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
        elif op == 0x23:
            r[d] = self.load8((r[a] + sign(imm, 16)) & 0xffffffff)
        elif op == 0x35:
            self.store((r[a] + sign(d << 11 | word & 0x7ff, 16)) & 0xffffffff, r[b])
        elif op == 0x38 and word & 0x30f == 3:
            r[d] = r[a] & r[b]
        elif op == 0x38 and word & 0x30f == 0:
            r[d] = (r[a] + r[b]) & 0xffffffff
        elif op == 0x38 and word & 0x30f == 4:
            r[d] = r[a] | r[b]
        elif op == 0x38 and word & 0x30f == 5:
            r[d] = r[a] ^ r[b]
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


class Readvertise(unittest.TestCase):
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--edid', str(EDID), str(output)],
                           check=True, capture_output=True)
            scp = Scp(output.read_text())
        scp.run_until(8)
        return scp

    def request(self, scp, command):
        scp.sram[BASE + ACK] = 0
        scp.sram[BASE + 16] = command
        for _ in range(1000):
            if scp.sram[BASE + 16] == 0:
                return scp.sram[BASE + ACK]
            scp.step()
        raise AssertionError(f'request {command} never acknowledged')

    def test_hold_ddc_on_release_cycle(self):
        scp = self.ready()
        edid = {a: scp.io[a] for a in scp.io if a >= 0x1c00}
        self.assertEqual(self.request(scp, HOLD), HOLD)
        self.assertEqual(scp.io[0x1014] & 7, 7)       # HPD forced low
        self.assertEqual(scp.io[0x1b04] & 7, 0)       # DDC disabled
        self.assertEqual(self.request(scp, DDC_ON), DDC_ON)
        self.assertEqual(scp.io[0x1b04] & 7, 7)
        self.assertEqual(scp.io[0x1014] & 7, 7)       # still held until release
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.assertEqual(scp.io[0x1014], ORIGINAL[0x1014] & ~7)
        self.assertEqual({a: scp.io[a] for a in edid}, edid)  # EDID banks untouched
        self.assertEqual(scp.sram.get(BASE + 24, 0), 0)

    def test_unknown_request_writes_nothing(self):
        scp = self.ready()
        before = dict(scp.io)
        self.assertEqual(self.request(scp, 9), 0xff)
        self.assertEqual(scp.io, before)

    def test_stop_still_restores_every_original_after_a_cycle(self):
        scp = self.ready()
        for command in (HOLD, DDC_ON, RELEASE, HOLD):  # ends held: stop must still restore
            self.request(scp, command)
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual(scp.sram.get(BASE + 24, 0), 0)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)], [scp.sram[META + 4 * i] for i in range(8)])
        self.assertEqual({a: scp.io.get(a, 0) for a in REGS}, {a: ORIGINAL.get(a, 0) for a in REGS})

    def test_handler_fits_before_the_trap_area(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--edid', str(EDID), str(output)],
                           check=True, capture_output=True)
            header = output.read_text()
        ext = re.findall(r'0x([0-9a-f]{8}),', header.split('edid_readvertise_code')[1].split('edid_trial_data')[0])
        self.assertEqual(len(ext) % 2, 0)
        self.assertLessEqual(EXT + 4 * len(ext), 0x4c00)


class InitialAdvert(Readvertise):
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise',
                            '--defer-initial-hpd', '--edid', str(EDID), str(output)],
                           check=True, capture_output=True)
            header = output.read_text()
            self.assertIn('#define EDID_INITIAL_HPD_DEFERRED 1', header)
            scp = Scp(header)
        scp.run_until(8)
        return scp

    def test_initial_ddc_ready_without_any_hpd_rise(self):
        scp = self.ready()
        self.assertFalse(any(a == 0x1014 and v & 7 == 0 for a, v in scp.io_writes))
        self.assertEqual(scp.io[0x1014] & 7, 7)
        self.assertEqual(scp.io[0x1b04] & 7, 7)
        self.assertEqual(scp.sram[BASE + 36] & 7, 7)
        self.assertEqual(scp.sram[BASE + 44], scp.io[0x1b04])
        banks = {a: v for a, v in scp.io.items() if a >= 0x1c00}
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.assertEqual(scp.io[0x1014] & 7, 0)
        self.assertEqual(scp.sram[BASE + 120], scp.io[0x1014])
        self.assertEqual(scp.sram[BASE + 124], scp.io[0x1b04])
        self.assertEqual(sum(a == 0x1014 and v & 7 == 0 for a, v in scp.io_writes), 1)
        self.assertEqual({a: scp.io[a] for a in banks}, banks)
        for command in (HOLD, DDC_ON, RELEASE):
            self.request(scp, command)
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)],
                         [scp.sram[META + 4 * i] for i in range(8)])

    def test_deferred_requires_owned_request_and_restore_protocol(self):
        for flags in ([], ['--verify-restore'], ['--readvertise']):
            with tempfile.TemporaryDirectory() as directory:
                p = subprocess.run([sys.executable, str(GENERATOR), '--defer-initial-hpd',
                                    *flags, str(Path(directory) / 'payload.h')], capture_output=True)
                self.assertNotEqual(p.returncode, 0)


class InitialDdcReset(Readvertise):
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise',
                            '--defer-initial-hpd', '--defer-initial-ddc', '--edid', str(EDID), str(output)],
                           check=True, capture_output=True)
            header = output.read_text()
            self.assertIn('#define EDID_INITIAL_DDC_HOLD_MS 2000', header)
            scp = Scp(header)
        scp.run_until(8)
        return scp

    def test_initial_ddc_off_then_enabled_then_one_first_hpd_rise(self):
        scp = self.ready()
        self.assertEqual(scp.io[0x1b04] & 7, 0)
        self.assertEqual(scp.io[0x1014] & 7, 7)
        self.assertFalse(any(a == 0x1014 and v & 7 == 0 for a, v in scp.io_writes))
        self.assertEqual(self.request(scp, DDC_ON), DDC_ON)
        self.assertEqual(scp.io[0x1b04] & 7, 7)
        self.assertEqual(scp.sram[BASE + 124], scp.io[0x1b04])
        self.assertEqual(scp.io[0x1014] & 7, 7)
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.assertEqual(sum(a == 0x1014 and v & 7 == 0 for a, v in scp.io_writes), 1)
        self.assertEqual(scp.sram[BASE + 120], scp.io[0x1014])
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)],
                         [scp.sram[META + 4 * i] for i in range(8)])


class DdcIsolation(Readvertise):
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise',
                            '--isolate-ddc', '--edid', str(EDID), str(output)],
                           check=True, capture_output=True)
            scp = Scp(output.read_text())
        scp.run_until(8)
        return scp

    def test_ddc_only_commands_never_write_hpd(self):
        scp = self.ready()
        hpd = scp.io[0x1014]
        scp.io_writes.clear()
        self.assertEqual(self.request(scp, 5), 5)
        self.assertEqual(scp.io[0x1b04] & 7, 0)
        self.assertEqual(scp.sram[BASE + 120], hpd)
        self.assertEqual(scp.sram[BASE + 124], scp.io[0x1b04])
        self.assertEqual(self.request(scp, DDC_ON), DDC_ON)
        self.assertEqual(scp.io[0x1b04] & 7, 7)
        self.assertFalse(any(a == 0x1014 for a, v in scp.io_writes))
        self.assertEqual(scp.io[0x1014], hpd)
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)],
                         [scp.sram[META + 4 * i] for i in range(8)])


class HpdIsolation(Readvertise):
    flag = '--isolate-hpd'
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise',
                            self.flag, '--edid', str(EDID), str(output)],
                           check=True, capture_output=True)
            scp = Scp(output.read_text())
        scp.run_until(8)
        return scp

    def test_hpd_only_pulse_never_writes_ddc(self):
        scp = self.ready()
        ddc = scp.io[0x1b04]
        self.assertEqual(ddc & 7, 7)                   # DDC enabled by the initial advert
        scp.io_writes.clear()
        self.assertEqual(self.request(scp, 6), 6)
        self.assertEqual(scp.io[0x1014] & 7, 7)        # HPD forced low
        self.assertEqual(scp.sram[BASE + 120], scp.io[0x1014])
        self.assertEqual(scp.sram[BASE + 124], ddc)    # DDC readback unchanged
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.assertEqual(scp.io[0x1014], ORIGINAL[0x1014] & ~7)
        self.assertEqual(scp.sram[BASE + 120], scp.io[0x1014])
        self.assertEqual(scp.sram[BASE + 124], ddc)
        self.assertFalse(any(a == 0x1b04 for a, v in scp.io_writes))
        self.assertEqual(scp.io[0x1b04], ddc)
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)],
                         [scp.sram[META + 4 * i] for i in range(8)])

    def test_hpd_isolation_refuses_combinations(self):
        for extra in (['--isolate-ddc'], ['--defer-initial-hpd']):
            with tempfile.TemporaryDirectory() as directory:
                r = subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--isolate-hpd',
                                    *extra, '--edid', str(EDID), str(Path(directory) / 'p.h')], capture_output=True)
                self.assertNotEqual(r.returncode, 0)


SAMP, FIRST, SEQ, CLR, PAIRS = 0x4da0, 0x4e80, 0x4f80, 0x4f84, 0x4f88
SAMPLED = [0x1000, 0x1008, 0x1014, 0x1018, 0x101c, 0x1020, 0x1030, 0x1034, 0x1038, 0x1b00, 0x1b04, 0x1b08]


class DdcSampler(Readvertise):
    """The read-only sampler keeps first/last/sticky words and never writes the receiver."""
    extra = ()
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--sample-ddc',
                            *self.extra, '--edid', str(EDID), str(output)], check=True, capture_output=True)
            header = output.read_text()
        block, rest = header.split('static const u32 edid_sampler_code[] = {', 1)
        words, rest = rest.split('};', 1)
        scp = Scp(rest)  # main program, handler and data only
        for i, w in enumerate(int(x, 16) for x in re.findall(r'0x([0-9a-f]{8}),', words)):
            scp.sram[SAMP + 4 * i] = w
        self.header = header
        scp.io.update({0x1000: 0, 0x1008: 0, 0x1018: 0x8, 0x101c: 3})
        scp.run_until(8)
        return scp

    def spin(self, scp, n=3000):
        for _ in range(n):
            scp.step()

    def pair(self, scp, reg):
        i = SAMPLED.index(reg)
        return scp.sram.get(PAIRS + 8 * i, 0), scp.sram.get(PAIRS + 8 * i + 4, 0)

    def test_first_last_and_sticky_capture_a_transient_without_receiver_writes(self):
        scp = self.ready()
        scp.io_writes.clear()
        self.spin(scp)
        seq = scp.sram[SEQ]
        self.assertGreater(seq, 0)
        first = [scp.sram[FIRST + 4 * i] for i in range(len(SAMPLED))]
        self.assertEqual(first[SAMPLED.index(0x1b04)] & 7, 7)   # DDC enabled at owner ready
        self.assertEqual(self.pair(scp, 0x1008), (0, 0))
        scp.io[0x1008] = 2                                     # transient event bit
        self.spin(scp)
        scp.io[0x1008] = 0
        self.spin(scp)
        self.assertEqual(self.pair(scp, 0x1008), (0, 2))        # last back to 0, sticky kept
        self.assertGreater(scp.sram[SEQ], seq)
        self.assertEqual([scp.sram[FIRST + 4 * i] for i in range(len(SAMPLED))], first)
        self.assertEqual(scp.io_writes, [])                     # sampler is read-only
        scp.sram[CLR] = 1
        self.spin(scp)
        self.assertEqual(scp.sram[CLR], 0)
        self.assertEqual(self.pair(scp, 0x1008), (0, 0))

    def test_sampled_registers_are_only_stock_accessed_ones(self):
        regs = re.search(r'edid_sample_regs\[\] = \{([^}]*)\}', self.ready() and self.header).group(1)
        self.assertEqual([int(x, 16) & 0xffff for x in regs.split(',')], SAMPLED)


class HpdPulseWithSampler(DdcSampler):
    """The deployed combination: HPD-only pulse handler plus the idle-loop sampler."""
    extra = ('--isolate-hpd',)

    def test_pulse_is_seen_by_the_sampler_and_ddc_is_never_written(self):
        scp = self.ready()
        self.spin(scp)
        scp.sram[CLR] = 1
        self.spin(scp)
        scp.io_writes.clear()
        self.assertEqual(self.request(scp, 6), 6)
        self.spin(scp)
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.spin(scp)
        self.assertEqual(self.pair(scp, 0x1014)[1] & 7, 7)     # HPD low/high toggled
        self.assertEqual(self.pair(scp, 0x1b04)[1], 0)         # DDC never moved
        self.assertFalse(any(a == 0x1b04 for a, v in scp.io_writes))
        self.assertEqual({a for a, v in scp.io_writes}, {0x1014})
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)],
                         [scp.sram[META + 4 * i] for i in range(8)])


class HpdPulseProduction(HpdIsolation):
    """The production --hpd-pulse build runs the identical, proven SCP branch."""
    flag = '--hpd-pulse'

    def test_production_and_diagnostic_scp_code_are_identical(self):
        def body(flag):
            with tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / 'p.h'
                subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', flag,
                                '--edid', str(EDID), str(out)], check=True, capture_output=True)
                return [l for l in out.read_text().splitlines() if not l.startswith('#define')]
        self.assertEqual(body('--hpd-pulse'), body('--isolate-hpd'))


SCAN_TABLE, SCAN_LAST, SCAN_MASK, SCAN_FIRST, SCAN_N, SCAN_IDLE = 0x4ba8, 0x4e80, 0x4ec0, 0x4f88, 16, 0x1b04


class DdcScan(Readvertise):
    """Read-only DDC-block scan on top of the production HPD pulse."""
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--hpd-pulse',
                            '--scan-ddc', '--edid', str(EDID), str(output)], check=True, capture_output=True)
            header = output.read_text()
        block, rest = header.split('static const u32 edid_scan_code[] = {', 1)
        words, rest = rest.split('};', 1)
        self.header, self.words = header, [int(x, 16) for x in re.findall(r'0x([0-9a-f]{8}),', words)]
        scp = Scp(rest)
        for i, w in enumerate(self.words):
            scp.sram[SAMP + 4 * i] = w
        for i in range(SCAN_N):                       # module init: parked, clear 1
            scp.sram[SCAN_TABLE + 4 * i] = SCAN_IDLE
        scp.sram[SEQ], scp.sram[CLR] = 0, 1
        # Unknown block words with recognisable values; 0x1b0c..0x1bfc are not stock-accessed.
        scp.io.update({0x1b00 + o: 0x5a000000 | o for o in range(0x0c, 0x100, 4)})
        scp.run_until(8)
        return scp

    def spin(self, scp, n=3000):
        for _ in range(n):
            scp.step()

    def window(self, scp, start, count=SCAN_N):
        for i in range(SCAN_N):
            scp.sram[SCAN_TABLE + 4 * i] = (start + 4 * i) & 0xffff if i < count else SCAN_IDLE
        scp.sram[CLR] = 1

    def report(self, scp):
        return [(0x07090000 | scp.sram[SCAN_TABLE + 4 * i], scp.sram.get(SCAN_FIRST + 4 * i, 0),
                 scp.sram.get(SCAN_LAST + 4 * i, 0), scp.sram.get(SCAN_MASK + 4 * i, 0)) for i in range(SCAN_N)]

    def test_parked_scan_reads_only_the_stock_ddc_enable(self):
        scp = self.ready()
        reads = []
        load = scp.load
        scp.load = lambda a: (reads.append(a & 0xffff) if a >> 16 == 0x0709 else None) or load(a)
        scp.io_writes.clear()
        self.spin(scp)
        self.assertEqual(set(reads), {SCAN_IDLE})
        self.assertEqual(scp.io_writes, [])
        self.assertEqual(scp.sram[CLR], 0)
        self.assertGreater(scp.sram[SEQ], 0)
        self.assertTrue(all(f & 7 == 7 and l == f and m == 0 for _, f, l, m in self.report(scp)))

    def test_moved_window_records_first_last_and_a_transient(self):
        scp = self.ready()
        self.spin(scp)
        scp.io_writes.clear()
        self.window(scp, 0x07091b40)
        self.spin(scp)
        self.assertEqual(scp.sram[CLR], 0)
        rows = self.report(scp)
        self.assertEqual([a for a, *_ in rows], [0x07091b40 + 4 * i for i in range(SCAN_N)])
        self.assertEqual([f for _, f, _, _ in rows], [0x5a000000 | (0x40 + 4 * i) for i in range(SCAN_N)])
        self.assertTrue(all(m == 0 for *_, m in rows))
        scp.io[0x1b48] ^= 0x100                      # a bit that pulses during a read
        self.spin(scp)
        scp.io[0x1b48] ^= 0x100
        self.spin(scp)
        a, f, l, m = self.report(scp)[2]
        self.assertEqual((a, l, m), (0x07091b48, f, 0x100))
        self.assertEqual(scp.io_writes, [])

    def test_partial_window_parks_the_rest_and_end_of_block_is_reachable(self):
        scp = self.ready()
        self.window(scp, 0x07091bf8, 2)
        self.spin(scp)
        rows = self.report(scp)
        self.assertEqual([a for a, *_ in rows[:3]], [0x07091bf8, 0x07091bfc, 0x07091b04])
        self.assertEqual(rows[1][1], 0x5a0000fc)

    def test_pulse_still_works_and_restore_is_clean_while_scanning(self):
        scp = self.ready()
        self.window(scp, 0x07091b00)
        self.spin(scp)
        scp.io_writes.clear()
        self.assertEqual(self.request(scp, 6), 6)
        self.spin(scp)
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.assertEqual({a for a, v in scp.io_writes}, {0x1014})
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)],
                         [scp.sram[META + 4 * i] for i in range(8)])

    def test_layout_stays_inside_free_sram(self):
        self.ready()
        ext = re.search(r'edid_readvertise_code\[\] = \{(.*?)\};', self.header, re.S).group(1)
        self.assertLessEqual(EXT + 4 * len(re.findall(r'0x[0-9a-f]{8},', ext)), SCAN_TABLE)
        self.assertLessEqual(SCAN_TABLE + 4 * SCAN_N, 0x4c00)               # trap stubs
        self.assertGreaterEqual(SAMP, 0x4c00 + 0x20 * 13)
        self.assertLessEqual(SAMP + 4 * len(self.words), SCAN_LAST)
        self.assertLessEqual(SCAN_MASK + 4 * SCAN_N, BASE)                   # marker area
        self.assertGreaterEqual(SCAN_FIRST, CLR + 4)
        self.assertLessEqual(SCAN_FIRST + 4 * SCAN_N, 0x5000)

    def test_scan_refuses_the_sampler_and_needs_the_request_protocol(self):
        for flags in (['--verify-restore', '--readvertise', '--sample-ddc', '--scan-ddc'], ['--scan-ddc']):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                r = subprocess.run([sys.executable, str(GENERATOR), *flags, str(Path(d) / 'p.h')], capture_output=True)
                self.assertNotEqual(r.returncode, 0)

    def test_scan_and_production_share_main_program_except_the_idle_branch(self):
        scan = Scp(self.ready() and self.header.split('};', 1)[1])
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'p.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--hpd-pulse',
                            '--edid', str(EDID), str(out)], check=True, capture_output=True)
            prod = Scp(out.read_text())
        diff = [a for a in prod.sram if prod.sram[a] != scan.sram.get(a)]
        self.assertEqual(len(diff), 1)                                       # bnf wait -> bnf 0x4da0


class ByteScan(DdcScan):
    """--scan-bytes: same scanner, l.lbz of full addresses in the 0x0684 wrapper."""
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--hpd-pulse',
                            '--scan-bytes', '--edid', str(EDID), str(output)], check=True, capture_output=True)
            header = output.read_text()
        block, rest = header.split('static const u32 edid_scan_code[] = {', 1)
        words, rest = rest.split('};', 1)
        self.header, self.words = header, [int(x, 16) for x in re.findall(r'0x([0-9a-f]{8}),', words)]
        self.assertIn('#define EDID_SCAN_BYTES 1', header)
        self.assertIn('#define EDID_SCAN_IDLE 0x4f00', header)
        self.assertIn('#define EDID_SCAN_ARM 0x06840094', header)
        self.assertIn('#define EDID_SCAN_ARM_COUNT 4', header)
        scp = Scp(rest)
        for i, w in enumerate(self.words):
            scp.sram[SAMP + 4 * i] = w
        for i in range(SCAN_N):                      # module init: armed on the DDC line byte
            scp.sram[SCAN_TABLE + 4 * i] = 0x06840094 + i if i < 4 else BYTE_IDLE
        scp.sram[ACT] = scp.sram[LASTACT] = scp.sram[BUSY] = 0
        scp.sram[SEQ], scp.sram[CLR] = 0, 1
        scp.wrap.update({0x06840000 + o: (o * 7 + 3) & 0xff for o in range(0x1000)})
        scp.run_until(8)
        return scp

    def window(self, scp, start, count=SCAN_N):
        for i in range(SCAN_N):
            scp.sram[SCAN_TABLE + 4 * i] = start + i if i < count else BYTE_IDLE
        scp.sram[CLR] = 1

    def report(self, scp):
        return [(scp.sram[SCAN_TABLE + 4 * i], scp.sram.get(SCAN_FIRST + 4 * i, 0),
                 scp.sram.get(SCAN_LAST + 4 * i, 0), scp.sram.get(SCAN_MASK + 4 * i, 0)) for i in range(SCAN_N)]

    def test_armed_scan_reads_only_the_ddc_line_bytes_and_sram(self):
        scp = self.ready()
        scp.byte_reads.clear()
        reads = []
        load = scp.load
        scp.load = lambda a: (reads.append(a) if a >> 16 == 0x0709 else None) or load(a)
        scp.io_writes.clear()
        self.spin(scp)
        self.assertEqual(set(scp.byte_reads), {BYTE_IDLE, 0x06840094, 0x06840095, 0x06840096, 0x06840097})
        self.assertEqual(reads, [])
        self.assertEqual(scp.sram[ACT], 0)                # nothing toggled yet
        self.assertEqual(scp.io_writes, [])
        self.assertGreater(scp.sram[SEQ], 0)

    # The word-scan tests below do not apply to byte addressing.
    test_parked_scan_reads_only_the_stock_ddc_enable = None
    test_moved_window_records_first_last_and_a_transient = None
    test_partial_window_parks_the_rest_and_end_of_block_is_reachable = None

    def test_byte_window_reads_exact_bytes_and_catches_the_busy_bit(self):
        scp = self.ready()
        self.spin(scp)
        scp.io_writes.clear()
        self.window(scp, 0x06840090)
        self.spin(scp)
        rows = self.report(scp)
        self.assertEqual([a for a, *_ in rows], [0x06840090 + i for i in range(SCAN_N)])
        self.assertEqual([f for _, f, _, _ in rows], [(o * 7 + 3) & 0xff for o in range(0x90, 0xa0)])
        scp.wrap[0x06840095] ^= 0x20                    # busy while a transfer is in flight
        self.spin(scp)
        scp.wrap[0x06840095] ^= 0x20
        self.spin(scp)
        a, f, l, m = rows[5][0], *self.report(scp)[5][1:]
        self.assertEqual((a, l, m), (0x06840095, f, 0x20))
        self.assertEqual(scp.io_writes, [])
        self.assertTrue(all(b == BYTE_IDLE or 0x06840090 <= b < 0x068400a0 for b in scp.byte_reads))

    def test_scan_and_production_share_main_program_except_the_idle_branch(self):
        super().test_scan_and_production_share_main_program_except_the_idle_branch()

    def test_pulse_still_works_and_restore_is_clean_while_scanning(self):
        scp = self.ready()
        self.window(scp, 0x06840090)
        self.spin(scp)
        scp.io_writes.clear()
        self.assertEqual(self.request(scp, 6), 6)
        self.spin(scp)
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.assertEqual({a for a, v in scp.io_writes}, {0x1014})
        scp.sram[BASE + 16] = 1
        scp.run_until(28)
        self.assertEqual([scp.sram[CHECK + 4 * i] for i in range(8)],
                         [scp.sram[META + 4 * i] for i in range(8)])

    def test_activity_timestamp_marks_the_first_toggling_pass_and_clear_rearms_it(self):
        scp = self.ready()
        scp.io_writes.clear()
        scp.wrap[0x06840096] = 0x33
        self.spin(scp)
        scp.sram[CLR] = 1
        self.spin(scp)
        self.assertEqual(scp.sram[ACT], 0)
        seq = scp.sram[SEQ]
        scp.wrap[0x06840096] = 0x13                       # SDA/SCL low: a transfer
        self.spin(scp, 600)                               # about two passes
        act = scp.sram[ACT]
        self.assertTrue(seq < act <= scp.sram[SEQ] + 1, (seq, act, scp.sram[SEQ]))
        scp.wrap[0x06840096] = 0x33
        self.spin(scp)
        self.assertEqual(scp.sram[ACT], act)              # first activity only
        self.assertEqual(self.report(scp)[2][3], 0x20)
        scp.sram[CLR] = 1
        self.spin(scp)
        self.assertEqual((scp.sram[ACT], scp.sram[CLR]), (0, 0))
        self.assertEqual(scp.io_writes, [])

    def test_busy_and_last_measure_how_long_the_lines_kept_toggling(self):
        scp = self.ready()
        scp.io_writes.clear()
        scp.wrap[0x06840096] = 0x33
        self.spin(scp)
        scp.sram[CLR] = 1
        self.spin(scp)
        self.assertEqual((scp.sram[ACT], scp.sram[LASTACT], scp.sram[BUSY]), (0, 0, 0))
        def burst(passes):                               # one line flip seen by each of `passes` passes
            for _ in range(passes):
                seq = scp.sram[SEQ]
                scp.wrap[0x06840096] ^= 0x20
                while scp.sram[SEQ] < seq + 2:           # a whole pass has read the new level
                    scp.step()
            scp.wrap[0x06840096] = 0x33
            self.spin(scp, 700)
        burst(2)                                         # a NAKed address probe: short
        short = scp.sram[BUSY]
        self.assertTrue(2 <= short <= 4, short)
        first = scp.sram[ACT]
        burst(40)                                        # a real read: long
        self.assertEqual(scp.sram[ACT], first)           # first activity unchanged
        self.assertGreaterEqual(scp.sram[BUSY] - short, 40)
        self.assertGreater(scp.sram[LASTACT] - first, 40)
        self.assertLessEqual(scp.sram[LASTACT], scp.sram[SEQ] + 1)
        scp.sram[CLR] = 1
        self.spin(scp)
        self.assertEqual((scp.sram[ACT], scp.sram[LASTACT], scp.sram[BUSY], scp.sram[CLR]), (0, 0, 0, 0))
        self.assertEqual(scp.io_writes, [])

    def test_scan_bytes_refuses_other_scanners(self):
        for flags in (['--verify-restore', '--readvertise', '--scan-ddc', '--scan-bytes'],
                      ['--verify-restore', '--readvertise', '--sample-ddc', '--scan-bytes'], ['--scan-bytes']):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                r = subprocess.run([sys.executable, str(GENERATOR), *flags, str(Path(d) / 'p.h')], capture_output=True)
                self.assertNotEqual(r.returncode, 0)


BYTE_IDLE = 0x4f00
ACT = 0x4fc8
LASTACT, BUSY = 0x4fcc, 0x4fd0


class WordScan(Readvertise):
    """--scan-words: l.lwz of full addresses inside the SCP-owned receiver block."""
    def ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'payload.h'
            subprocess.run([sys.executable, str(GENERATOR), '--verify-restore', '--readvertise', '--hpd-pulse',
                            '--scan-words', '--edid', str(EDID), str(output)], check=True, capture_output=True)
            header = output.read_text()
        self.assertIn('#define EDID_SCAN_WORDS 1', header)
        self.assertNotIn('EDID_SCAN_ARM', header)
        self.assertNotIn('EDID_SCAN_BYTES', header)
        block, rest = header.split('static const u32 edid_scan_code[] = {', 1)
        words, rest = rest.split('};', 1)
        self.header, self.words = header, [int(x, 16) for x in re.findall(r'0x([0-9a-f]{8}),', words)]
        scp = Scp(rest)
        for i, w in enumerate(self.words):
            scp.sram[SAMP + 4 * i] = w
        for i in range(SCAN_N):                      # module init: parked on SCP SRAM
            scp.sram[SCAN_TABLE + 4 * i] = BYTE_IDLE
        scp.sram[SEQ], scp.sram[CLR] = 0, 1
        scp.sram[ACT] = scp.sram[LASTACT] = scp.sram[BUSY] = 0
        scp.io.update({0x1040 + 4 * i: 0xa5000000 | i for i in range(0x2b0)})   # unknown words
        scp.run_until(8)
        return scp

    def spin(self, scp, n=3000):
        for _ in range(n):
            scp.step()

    def window(self, scp, start):
        for i in range(SCAN_N):
            scp.sram[SCAN_TABLE + 4 * i] = start + 4 * i
        scp.sram[CLR] = 1

    def test_parked_scan_reads_no_receiver_register(self):
        scp = self.ready()
        reads = []
        load = scp.load
        scp.load = lambda a: (reads.append(a) if a >> 16 == 0x0709 else None) or load(a)
        scp.io_writes.clear()
        self.spin(scp)
        self.assertEqual(reads, [])
        self.assertEqual(scp.io_writes, [])
        self.assertGreater(scp.sram[SEQ], 0)

    def test_window_reads_exact_words_including_the_unknown_range(self):
        scp = self.ready()
        scp.io_writes.clear()
        for start, expect in ((0x07091000, [scp.io.get(0x1000 + 4 * i, 0) for i in range(SCAN_N)]),
                              (0x07091800, [0xa5000000 | ((0x1800 - 0x1040) // 4 + i) for i in range(SCAN_N)])):
            self.window(scp, start)
            self.spin(scp)
            self.assertEqual([scp.sram[SCAN_LAST + 4 * i] for i in range(SCAN_N)], expect)
            self.assertEqual([scp.sram[SCAN_FIRST + 4 * i] for i in range(SCAN_N)], expect)
        self.assertEqual(scp.io_writes, [])

    def test_pulse_still_works_while_a_window_is_set(self):
        scp = self.ready()
        self.window(scp, 0x07091040)
        self.spin(scp)
        scp.io_writes.clear()
        self.assertEqual(self.request(scp, 6), 6)
        self.spin(scp)
        self.assertEqual(self.request(scp, RELEASE), RELEASE)
        self.assertEqual({a for a, v in scp.io_writes}, {0x1014})

    def test_scan_words_refuses_other_scanners(self):
        for flags in (['--verify-restore', '--readvertise', '--scan-bytes', '--scan-words'],
                      ['--verify-restore', '--readvertise', '--scan-ddc', '--scan-words'], ['--scan-words']):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                r = subprocess.run([sys.executable, str(GENERATOR), *flags, str(Path(d) / 'p.h')], capture_output=True)
                self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
