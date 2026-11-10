#!/usr/bin/env python3
"""Offline adversarial review of the first SCP sampling prototype.

This is a safety review, not a live injector. It intentionally demonstrates
why the prototype's successful instruction model is insufficient to arm it.
It has no device, network, module-loading, or hardware-write operations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import unittest

ENTRY = 0x4404
SCRATCH = 0x4dc0
OUT = 0x4f80
SAVED = 0x4fe0
ORIGINAL = 0x84830010
MAGIC = 0x48504431
REGISTERS = [0x07091014, 0x07091b00, 0x07091b04, 0x07091b08,
             0x07091020, 0x07091030, 0x07091034, 0x07091038,
             0x07091c00, 0x07091c04, 0x07091d00, 0x07091d04,
             0x07091e00, 0x07091e04]


class Machine:
    def __init__(self, snapshot, code, hook, seed=0, phase=0, stale_fetch=False, stop=0):
        self.original = snapshot
        self.ram = bytearray(snapshot)
        self.ram[SCRATCH:SCRATCH+len(code)] = code
        struct.pack_into('<I', self.ram, ENTRY, hook)
        self.hook = hook
        rng = random.Random(seed)
        self.regs = [rng.getrandbits(32) for _ in range(32)]
        self.regs[0], self.regs[3], self.regs[4] = 0, 0x4f00, 0
        self.regs[10], self.regs[11] = 0x48444d49, 0x07090000
        self.context = list(self.regs)
        self.flag = False
        self.pc = ENTRY+phase*4
        # A hook may become visible in any of the original four loop phases.
        self.delay = ENTRY if phase == 3 else None
        self.stale_fetch = stale_fetch
        self.peripheral = {addr: rng.getrandbits(32) for addr in REGISTERS}
        struct.pack_into('<I', self.ram, 0x4f10, stop)
        self.reads, self.stores, self.trace = [], [], []
        self.entries = 0
        self.returned = False
        self.done_seen_at = None
        self.code_bytes = len(code)

    def word(self, address):
        if not (0 <= address <= len(self.ram)-4 and address % 4 == 0):
            raise ValueError('unbounded SRAM access')
        return struct.unpack_from('<I', self.ram, address)[0]

    def done(self):
        return self.word(OUT) == self.word(OUT+4) == MAGIC

    def step(self, stall_read=None):
        pc = self.pc
        if pc == SCRATCH:
            self.entries += 1
        if self.entries and pc == ENTRY and self.word(ENTRY) == ORIGINAL and not self.stale_fetch:
            self.returned = True
        if not (pc in range(ENTRY, ENTRY+16, 4) or SCRATCH <= pc < SCRATCH+self.code_bytes):
            raise ValueError('execution left reviewed code: '+hex(pc))
        insn = self.hook if pc == ENTRY and self.stale_fetch else self.word(pc)
        op = insn >> 26
        d, a, imm = (insn >> 21) & 31, (insn >> 16) & 31, insn & 65535
        pending = self.delay
        self.delay = None
        following = pc+4
        event = dict(pc=hex(pc), instruction=f'{insn:08x}')
        if op in [0, 3]:
            n = insn & 0x3ffffff
            if n & (1 << 25):
                n -= 1 << 26
            if op == 0 or not self.flag:
                self.delay = pc+4*n
        elif insn == 0x15000000:
            pass
        elif op == 6:
            self.regs[d] = imm << 16
        elif op == 0x2a:
            self.regs[d] = self.regs[a] | imm
        elif insn == 0xbc240000:
            self.flag = self.regs[4] != 0
        elif op == 0x21:
            address = self.regs[a]+(imm-65536 if imm & 0x8000 else imm)
            event['load'] = hex(address)
            if address in self.peripheral:
                if stall_read == len(self.reads):
                    return False  # no further SCP progress; no fabricated bus completion
                self.regs[d] = self.peripheral[address]
                self.reads.append(address)
            elif address == 0x4f10 or SAVED <= address < SAVED+20:
                self.regs[d] = self.word(address)
            else:
                raise ValueError('unreviewed read: '+hex(address))
        elif op == 0x35:
            n = ((insn >> 21) & 31) << 11 | (insn & 2047)
            address = self.regs[a]+(n-65536 if n & 0x8000 else n)
            if not (address == ENTRY or OUT <= address <= 0x4ffc):
                raise ValueError('peripheral/out-of-bounds store: '+hex(address))
            self.stores.append(address)
            event['store'] = hex(address)
            struct.pack_into('<I', self.ram, address, self.regs[(insn >> 11) & 31])
        else:
            raise ValueError('unreviewed instruction: '+hex(insn))
        self.pc = pending if pending is not None else following
        self.trace.append(event)
        if self.done() and self.done_seen_at is None:
            self.done_seen_at = len(self.trace)
        return True

    def run(self, budget=220, stop_on_done=False, stall_read=None):
        for _ in range(budget):
            if not self.step(stall_read):
                return 'stalled'
            if self.returned:
                return 'returned'
            if stop_on_done and self.done():
                return 'done-marker'
        return 'budget'


def review(snapshot, code, hook):
    before = Machine(snapshot, code, hook)
    assert before.run(stop_on_done=True) == 'done-marker'
    early = dict(done=True, original_wait_word=before.word(ENTRY) == ORIGINAL,
                 returned=before.returned, context_restored=before.regs == before.context,
                 next_pc=hex(before.pc), instruction_count=len(before.trace))
    stale = Machine(snapshot, code, hook, stale_fetch=True)
    for _ in range(220):
        stale.step()
        if stale.entries >= 2 and stale.done():
            break
    assert stale.entries >= 2 and stale.done()
    cached = dict(done=stale.done(), original_wait_word=stale.word(ENTRY) == ORIGINAL,
                  probe_entries=stale.entries, returned=stale.returned)
    stalled = []
    for index in range(len(REGISTERS)):
        m = Machine(snapshot, code, hook)
        assert m.run(stall_read=index) == 'stalled'
        stalled.append(dict(register=hex(REGISTERS[index]), done=m.done(),
                            pc=hex(m.pc), hook_restored=m.word(ENTRY) == ORIGINAL))
    return dict(early_completion_counterexample=early,
                noncoherent_fetch_counterexample=cached, stalled_reads=stalled)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--prototype', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    snapshot = bytes.fromhex(json.loads(a.snapshot.read_text())['sram_hex'])
    code = (a.prototype/'scratch-code.bin').read_bytes()
    hook, = struct.unpack('<I', (a.prototype/'hook.bin').read_bytes())
    if len(snapshot) != 0x5000 or len(code) != 260 or SCRATCH+len(code) > 0x4f00:
        raise ValueError('prototype geometry mismatch')
    expected_loop = [0x84830010, 0xbc240000, 0x0ffffffe, 0x15000000]
    if list(struct.unpack_from('<4I', snapshot, ENTRY)) != expected_loop:
        raise ValueError('captured wait loop differs from reviewed source')
    manifest = json.loads((a.prototype/'MANIFEST.json').read_text())
    if hashlib.sha256(snapshot).hexdigest() != manifest['baseline_sram_sha256']:
        raise ValueError('snapshot generation differs from prototype')

    class Tests(unittest.TestCase):
        def test_nominal_all_loop_phases(self):
            for phase in range(4):
                for seed in range(100):
                    m = Machine(snapshot, code, hook, seed, phase)
                    self.assertEqual(m.run(), 'returned')
                    self.assertEqual(m.regs, m.context)
                    self.assertFalse(m.flag)
                    self.assertEqual(m.reads, REGISTERS)
                    self.assertEqual(m.entries, 1)
                    self.assertEqual(m.word(ENTRY), ORIGINAL)

        def test_every_capture_word(self):
            m = Machine(snapshot, code, hook)
            self.assertEqual(m.run(), 'returned')
            for i, addr in enumerate(REGISTERS):
                self.assertEqual(m.word(OUT+8+4*i), m.peripheral[addr])

        def test_no_unapproved_store(self):
            m = Machine(snapshot, code, hook)
            m.run()
            self.assertTrue(all(address == ENTRY or OUT <= address <= 0x4ffc for address in m.stores))

        def test_canaries_outside_mutable_ranges(self):
            m = Machine(snapshot, code, hook)
            m.run()
            allowed = set(range(ENTRY, ENTRY+4)) | set(range(SCRATCH, SCRATCH+len(code))) | set(range(OUT, 0x5000))
            self.assertTrue(all(i in allowed for i, (x, y) in enumerate(zip(snapshot, m.ram)) if x != y))

        def test_done_is_not_return_or_context_proof(self):
            m = Machine(snapshot, code, hook)
            self.assertEqual(m.run(stop_on_done=True), 'done-marker')
            self.assertFalse(m.returned)
            self.assertNotEqual(m.regs, m.context)
            self.assertEqual(m.word(ENTRY), ORIGINAL)

        def test_erase_on_done_breaks_execution(self):
            m = Machine(snapshot, code, hook)
            m.run(stop_on_done=True)
            m.ram[SCRATCH:SCRATCH+len(code)] = snapshot[SCRATCH:SCRATCH+len(code)]
            with self.assertRaises(ValueError):
                m.run()

        def test_stale_fetch_can_repeat_after_success_marker(self):
            m = Machine(snapshot, code, hook, stale_fetch=True)
            for _ in range(220):
                m.step()
                if m.entries >= 2 and m.done():
                    break
            self.assertTrue(m.done())
            self.assertGreater(m.entries, 1)
            self.assertEqual(m.word(ENTRY), ORIGINAL)
            self.assertFalse(m.returned)

        def test_every_peripheral_read_can_stall(self):
            for index in range(len(REGISTERS)):
                m = Machine(snapshot, code, hook)
                self.assertEqual(m.run(stall_read=index), 'stalled')
                self.assertFalse(m.done())
                self.assertNotEqual(m.word(ENTRY), ORIGINAL)

        def test_stop_request_is_not_interlocked(self):
            m = Machine(snapshot, code, hook, stop=1)
            # Even with a stop pending the prototype still performs its reads.
            self.assertEqual(m.run(stop_on_done=True), 'done-marker')
            self.assertEqual(m.reads, REGISTERS)

        def test_corrupt_return_rejected(self):
            changed = bytearray(code)
            struct.pack_into('<I', changed, len(changed)-8, 0)
            m = Machine(snapshot, changed, hook)
            self.assertEqual(m.run(), 'budget')
            self.assertFalse(m.returned)

        def test_peripheral_write_mutation_rejected(self):
            changed = bytearray(code)
            # Change the first peripheral lwz into sw r4,0(r5).
            target = next(i for i in range(0, len(changed), 4) if struct.unpack_from('<I', changed, i)[0] == 0x84850000)
            struct.pack_into('<I', changed, target, 0xd4052000)
            with self.assertRaisesRegex(ValueError, 'store'):
                Machine(snapshot, changed, hook).run()

        def test_bad_branch_target_rejected(self):
            with self.assertRaises(ValueError):
                Machine(snapshot, code, 0x1234).run()

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    findings = review(snapshot, code, hook)
    report = dict(status='SAFETY REVIEW COMPLETE: NO-GO for live insertion of the original prototype',
                  tests=12, nominal_register_phase_cases=400, stalled_read_cases=14,
                  hardware_access=False, hardware_write=False, live_capture_ready=False,
                  prototype_sha256=hashlib.sha256(code).hexdigest(),
                  blockers=['Completion is observable before register restore and return.',
                            'SRAM hook readback does not prove the instruction-fetch view is coherent.',
                            'No supported synchronization with the installed private signal-owner lock.',
                            'A bus-stalled SCP has no proven non-reset recovery/cleanup path.'],
                  findings=findings)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'])


if __name__ == '__main__':
    main()
