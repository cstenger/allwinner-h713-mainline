#!/usr/bin/env python3
"""Offline checks for the warm-retention U-Boot runner and Linux census gates."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/serial'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ub = load('ub', ROOT / 'tools/serial/warm-retention-uboot.py')
cen = load('cen', ROOT / 'tools/hdmi/warm-retention-census.py')


class FakeConsole:
    def __init__(self, values, bootcmd='run distro_bootcmd'):
        self.values, self.bootcmd, self.lines = values, bootcmd, []

    def run(self, line, quiet=1.0):
        if not ub.command_allowed(line):
            raise RuntimeError('not allowed')
        self.lines.append(line)
        if line == 'printenv bootcmd':
            return ('printenv bootcmd\r\nbootcmd=%s\r\n=> ' % self.bootcmd).encode()
        addr = int(line.split()[1], 16)
        return ('%s\r\n%08x: %08x    ....\r\n=> ' % (line, addr, self.values[addr])).encode()


class UBoot(unittest.TestCase):
    def test_allowlist(self):
        for ok in ('printenv bootcmd', 'boot', 'md.l 0x070101ac 1', 'md.l 0x070010a4 1',
                   'md.l 0x07001124 1'):
            self.assertTrue(ub.command_allowed(ok), ok)
        for bad in ('md.l 0x07091014 1', 'md.l 0x05001530 1', 'mw.l 0x070101ac 1',
                    'reset', 'setenv bootcmd x', 'saveenv', 'md.l 0x070101ac 2',
                    'md.l 0x070101ac 1; reset', 'run bootcmd', 'boot; reset'):
            self.assertFalse(ub.command_allowed(bad), bad)

    def test_gate_closed_skips_ppu(self):
        con = FakeConsole({ub.R_CCU_PPU: 0x00000000})
        r = ub.census(con)
        self.assertFalse(r['ppu_bus_open'])
        self.assertEqual(con.lines, ['printenv bootcmd', 'md.l 0x070101ac 1'])
        self.assertIsNone(r['ppu_tvfe'])

    def test_gate_half_open_skips_ppu(self):
        for gate in (0x00000001, 0x00010000):
            con = FakeConsole({ub.R_CCU_PPU: gate})
            self.assertFalse(ub.census(con)['ppu_bus_open'])
            self.assertEqual(len(con.lines), 2)

    def test_gate_open_reads_both_domains(self):
        con = FakeConsole({ub.R_CCU_PPU: 0x00010001, ub.PPU_TVFE: 0x00020000,
                           ub.PPU_TVCAP: 0x00010000})
        r = ub.census(con)
        self.assertEqual((r['ppu_tvfe_state'], r['ppu_tvcap_state']), ('off', 'on'))
        self.assertEqual(len(con.lines), 4)
        self.assertEqual(r['bootcmd'], 'run distro_bootcmd')

    def test_parse_md_requires_matching_address(self):
        with self.assertRaises(RuntimeError):
            ub.parse_md(b'070010a4: 00010000\r\n', 0x070101ac)


class FakeBoard:
    def __init__(self, values):
        self.values, self.reads = values, []

    def devmem(self, address):
        for lo, hi in cen.FORBIDDEN:
            if lo <= address < hi:
                raise RuntimeError('forbidden')
        self.reads.append(address)
        return self.values.get(address, 0)

    def run(self, argv):
        return 'inactive' if argv[0] == 'systemctl' else ''

    def read(self, path):
        return 'boot-x\n' if path.endswith('boot_id') else None

    def exists(self, path):
        return path.endswith('h713,hdmi-boot-v1')


def tvtop(routed):
    base = {cen.TVTOP + 0x40: 0x00011111 if routed else 0x10,
            cen.TVTOP + 0x44: 0x11111111 if routed else 0x10,
            cen.TVTOP + 0x80: 0x00001111 if routed else 0x10}
    return base


class Census(unittest.TestCase):
    ALWAYS = {cen.MIPS_STATUS, cen.R_CCU_PPU, cen.TVTOP + 0x40, cen.TVTOP + 0x44, cen.TVTOP + 0x80}
    ROUTED_ONLY = {cen.TVTOP + o for o in cen.TVTOP_ROUTED_ONLY}
    PPU = {cen.PPU_TVFE, cen.PPU_TVCAP}
    DOMAIN_ONLY = {cen.AUDIOTOP, cen.AUDIOTOP + 0xc, cen.DSP_STATUS}
    LOCK = {cen.LOCK_PEER, cen.LOCK_OWN}

    def check(self, values, expected):
        b = FakeBoard(values)
        r = cen.census(b, 't')
        self.assertEqual(set(b.reads), expected)
        return r

    def test_gate_closed_spl_only(self):
        self.check({cen.R_CCU_PPU: 0, **tvtop(False)}, self.ALWAYS)

    def test_half_open_gate_skips_ppu(self):
        for gate in (0x00000001, 0x00010000):
            with self.subTest(gate=gate):
                self.check({cen.R_CCU_PPU: gate, cen.PPU_TVFE: 0x10000, cen.PPU_TVCAP: 0x10000,
                            **tvtop(False)}, self.ALWAYS)

    def test_gate_open_domains_off_spl_only(self):
        r = self.check({cen.R_CCU_PPU: 0x10001, cen.PPU_TVFE: 0x20000, cen.PPU_TVCAP: 0x20000,
                        **tvtop(False)}, self.ALWAYS | self.PPU)
        self.assertFalse(r['tv_domains_both_on'])

    def test_one_domain_off_blocks_audiotop(self):
        self.check({cen.R_CCU_PPU: 0x10001, cen.PPU_TVFE: 0x10000, cen.PPU_TVCAP: 0x20000,
                    **tvtop(True)}, self.ALWAYS | self.PPU | self.ROUTED_ONLY | self.LOCK)

    def test_full_production_state_reads_everything(self):
        r = self.check({cen.R_CCU_PPU: 0x10001, cen.PPU_TVFE: 0x10000, cen.PPU_TVCAP: 0x10000,
                        **tvtop(True)},
                       self.ALWAYS | self.PPU | self.ROUTED_ONLY | self.DOMAIN_ONLY | self.LOCK)
        self.assertTrue(r['tv_domains_both_on'] and r['tvtop_routed'])

    def test_partial_routing_value_reads_nothing_extra(self):
        values = {cen.R_CCU_PPU: 0, **tvtop(False)}
        values[cen.TVTOP + 0x40] = 0  # neither SPL-only nor routed
        self.check(values, self.ALWAYS)

    def test_handoff_is_presence_not_decoded(self):
        r = self.check({cen.R_CCU_PPU: 0, **tvtop(False)}, self.ALWAYS)
        self.assertTrue(r['hdmi_handoff'])
        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'\x00\x8b\xff binary')
        try:
            self.assertIsNone(cen.Board().read(f.name))
        finally:
            os.unlink(f.name)

    def test_forbidden_window_and_no_writes(self):
        with self.assertRaises(RuntimeError):
            cen.Board().devmem(0x07091014)
        source = (ROOT / 'tools/hdmi/warm-retention-census.py').read_text()
        # devmem is only ever invoked with an address and width, never a value.
        self.assertIn("['busybox', 'devmem', '0x%08x' % address, '32']", source)
        self.assertNotIn('devmem_write', source)
        self.assertEqual(source.count("'devmem'"), 1)


class PPUProbe(unittest.TestCase):
    def test_bootcmd_mismatch_refuses_before_probe(self):
        from unittest.mock import patch
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / 'expected.txt'
            expected.write_text('expected production command\n')
            output = Path(tmp) / 'output'
            argv = ['warm-retention-uboot.py', '--port', '/dev/not-a-device',
                    '--output', str(output), '--label', 'test', '--open-ppu-bus',
                    '--expected-bootcmd', str(expected)]
            con = FakeConsole({ub.R_CCU_PPU: 0}, bootcmd='unexpected command')
            with patch.object(sys, 'argv', argv), patch.object(ub, 'open_port', return_value=99), \
                 patch.object(ub.os, 'close'), patch.object(ub, 'write_slow'), \
                 patch.object(ub, 'drain', return_value=b'=> '), \
                 patch.object(ub, 'Console', return_value=con), \
                 patch.object(ub, 'observe_warm_ppu') as probe:
                with self.assertRaisesRegex(RuntimeError, 'bootcmd differs'):
                    ub.main()
                probe.assert_not_called()
            self.assertTrue(json.loads((output / 'census.json').read_text())['bootcmd_mismatch'])
            self.assertEqual(con.lines, ['printenv bootcmd', 'md.l 0x070101ac 1'])

    def test_invalid_cli_combinations_refuse_before_opening_uart(self):
        from unittest.mock import patch
        import contextlib
        import io
        base = ['warm-retention-uboot.py', '--port', '/dev/not-a-device',
                '--output', '/tmp/not-created-ppu-probe', '--label', 'test',
                '--open-ppu-bus']
        for extra in (['--record-bootcmd', '/tmp/unused-bootcmd'],
                      ['--expected-bootcmd', '/tmp/unused-bootcmd', '--boot']):
            with patch.object(sys, 'argv', base + extra), patch.object(ub, 'open_port') as opened:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    ub.main()
                self.assertEqual(raised.exception.code, 2)
                opened.assert_not_called()

    class Console(FakeConsole):
        def run(self, line, quiet=1.0):
            if not ub.command_allowed(line, open_ppu_bus=True):
                raise RuntimeError('not allowed')
            if line == ub.OPEN_PPU_COMMAND:
                self.lines.append(line)
                return b'=> '
            # The default read-only fake deliberately rejects probe-only reads.
            self.lines.append(line)
            addr = int(line.split()[1], 16)
            return ('%08x: %08x\r\n=> ' % (addr, self.values[addr])).encode()

    def console(self, **changes):
        values = {ub.GP6: 0x48444d49, ub.MIPS_STATUS: 0,
                  ub.R_CCU_PPU: ub.PPU_OPEN, ub.PPU_TVFE: 0x20000,
                  ub.PPU_TVCAP: 0x10000}
        values.update({getattr(ub, k): v for k, v in changes.items()})
        return self.Console(values)

    def test_write_allowlist_is_exact_and_opt_in(self):
        self.assertFalse(ub.command_allowed(ub.OPEN_PPU_COMMAND))
        self.assertTrue(ub.command_allowed(ub.OPEN_PPU_COMMAND, True))
        for line in ('mw.l 0x070101ac 0x00010001 2', 'mw.l 0x070010a0 1 1',
                     'mw.l 0x07090118 0 1', 'md.l 0x07091014 1',
                     ub.OPEN_PPU_COMMAND + '; reset'):
            self.assertFalse(ub.command_allowed(line, True), line)

    def test_probe_records_intent_and_verifies_gate_before_domain_reads(self):
        con = self.console()
        result = {'r_ccu_ppu': '00000000'}
        snapshots = []
        import copy
        ub.observe_warm_ppu(con, result, lambda: snapshots.append(copy.deepcopy(result)))
        self.assertEqual(con.lines, ['md.l 0x07090118 1', 'md.l 0x0306101c 1',
                                    ub.OPEN_PPU_COMMAND, 'md.l 0x070101ac 1',
                                    'md.l 0x070010a4 1', 'md.l 0x07001124 1'])
        self.assertEqual(snapshots[0]['ppu_probe']['state'], 'write-intent')
        self.assertEqual(result['ppu_probe']['ppu_tvfe_state'], 'off')
        self.assertEqual(result['ppu_probe']['state'], 'complete-stopped-at-prompt')

    def test_failed_readback_never_reads_domains(self):
        for gate in (0, 1, 0x10000, 0xffffffff):
            con = self.console(R_CCU_PPU=gate)
            result = {'r_ccu_ppu': '00000000'}
            with self.assertRaises(RuntimeError):
                ub.observe_warm_ppu(con, result, lambda: None)
            self.assertEqual(con.lines[-1], 'md.l 0x070101ac 1')
            self.assertEqual(result['ppu_probe']['state'], 'gate-readback')

    def test_cold_live_or_unexpected_baseline_never_writes(self):
        for con, baseline in ((self.console(GP6=0), '00000000'),
                              (self.console(GP6=1), '00000000'),
                              (self.console(MIPS_STATUS=1), '00000000'),
                              (self.console(), '00010001')):
            with self.assertRaises(RuntimeError):
                ub.observe_warm_ppu(con, {'r_ccu_ppu': baseline}, lambda: None)
            self.assertNotIn(ub.OPEN_PPU_COMMAND, con.lines)


if __name__ == '__main__':
    unittest.main()
