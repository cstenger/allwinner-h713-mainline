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

    def test_forbidden_window_and_no_writes(self):
        with self.assertRaises(RuntimeError):
            cen.Board().devmem(0x07091014)
        source = (ROOT / 'tools/hdmi/warm-retention-census.py').read_text()
        # devmem is only ever invoked with an address and width, never a value.
        self.assertIn("['busybox', 'devmem', '0x%08x' % address, '32']", source)
        self.assertNotIn('devmem_write', source)
        self.assertEqual(source.count("'devmem'"), 1)


if __name__ == '__main__':
    unittest.main()
