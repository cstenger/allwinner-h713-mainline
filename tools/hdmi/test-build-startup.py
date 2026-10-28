#!/usr/bin/env python3
"""Check every environment-derived FDT cell in the generated startup script.

Models U-Boot exactly where it matters: setexpr and fdt get addr/size store
bare %lx, fdt get value stores 0x%08X for one cell, and fdt set <...> parses
each cell with simple_strtoul(cp, &newp, 0). The 2026-10-14 cold boot failed
on a bare PID 8b8f275c: base 0 read decimal 8 and stopped at 'b'.
"""
import importlib.util
from pathlib import Path
import re
import unittest

spec=importlib.util.spec_from_file_location('build_startup',Path(__file__).with_name('build-startup.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

# PIDs with a-f digits, decimal-looking digits (wrong value in base 0), and
# the reported failure.
SAMPLES=[0x8b8f275c,0xabcdef01,0x10,0x89,0x7,0x1,0xffffffff]


def producers(text):
    """Map each variable to the U-Boot formatter that last writes it."""
    out={}
    for var in re.findall(r'setexpr(?:\.[lwb])? (\w+) ',text):out[var]=lambda v:'%x'%v
    for var in re.findall(r'fdt get (?:addr|size) (\w+) ',text):out[var]=lambda v:'%x'%v
    for var in re.findall(r'fdt get value (\w+) ',text):out[var]=lambda v:'0x%08X'%v
    for var,src in re.findall(r'setenv (\w+) \$\{(\w+)\}',text):out[var]=out[src]
    return out


def strtoul0(s):
    """lib/strto.c simple_strtoul with base 0; returns (value, consumed)."""
    i=0;base=10
    if s[:1]=='0':
        if s[1:2].lower()=='x':base=16;i=2
        else:base=8
    start=i;value=0
    while i<len(s) and s[i].lower() in '0123456789abcdef'[:base]:
        value=value*base+int(s[i],16);i+=1
    return value,i if i>start or base==8 else 0


def parse_cells(arg):
    """cmd/fdt.c fdt_parse_prop for a '<...>' cell array."""
    assert arg[0]=='<' and arg[-1]=='>',arg
    cells=[]
    for token in arg[1:-1].split():
        value,used=strtoul0(token)
        if used!=len(token):raise ValueError('Sorry, I could not convert "%s"'%token)
        cells.append(value&0xffffffff)
    return cells


class StartupScript(unittest.TestCase):
    def setUp(self):
        self.text=m.script();self.formats=producers(self.text)
        self.sets=re.findall(r"fdt set (\S+) (\S+) (<[^>]*>)",self.text)
    def test_every_cell_variable_has_a_known_producer(self):
        used={v for _,_,cells in self.sets for v in re.findall(r'\$\{(\w+)\}',cells)}
        self.assertEqual(used,{'hdmi_pid','hdmi_ccu'})
        self.assertLessEqual(used,set(self.formats))
    def test_env_derived_cells_round_trip_for_all_samples(self):
        for node,prop,cells in self.sets:
            names=re.findall(r'\$?\{?(\w+)\}?',cells[1:-1])
            for value in SAMPLES:
                with self.subTest(prop=prop,value=hex(value)):
                    text=re.sub(r'\$\{(\w+)\}',lambda x:self.formats[x.group(1)](value),cells)
                    expect=[value if re.search(r'\$\{\w+\}',tok) else parse_cells('<'+tok+'>')[0]
                            for tok in cells[1:-1].split()]
                    self.assertEqual(parse_cells(text),expect)
    def test_handoff_is_magic_zero_pid(self):
        (cells,)=[c for _,p,c in self.sets if p=='h713,hdmi-boot-v1']
        self.assertEqual(parse_cells(cells.replace('${hdmi_pid}','8b8f275c')),[0x48444d49,0,0x8b8f275c])
    def test_reported_bare_pid_failure_is_reproduced(self):
        with self.assertRaisesRegex(ValueError,'b8f275c'):parse_cells('<0x48444d49 0 8b8f275c>')
        with self.assertRaises(ValueError):parse_cells('<0x0x00000003 1>') # double prefix
    def test_ccu_is_not_double_prefixed(self):
        self.assertNotIn('0x${hdmi_ccu}',self.text)
    def test_panel_timing_relatched_after_last_firmware_call(self):
        line = next(l for l in self.text.splitlines() if l.startswith("setenv hdmi_source '"))
        source = line[len("setenv hdmi_source '"):-1].split(' && ')
        relatch = source.index('mw.l 0x05880024 02d00500')
        self.assertLess(source.index('h713_disp commcall eaf13de5 chan=0 pid=${hdmi_pid} 3'), relatch)
        self.assertLess(relatch, source.index('bootm 0x50000000 - 0x4f000000'))
        self.assertIn('itest.l *0x05880024 == 02d00500', source)
        self.assertFalse(any(' & ' in c or ' | ' in c for c in source))

    def stage(self, name):
        line = next(l for l in self.text.splitlines() if l.startswith(f"setenv hdmi_{name} '"))
        return line[len(f"setenv hdmi_{name} '"):-1].split(' && ')

    def test_lamp_dark_during_cold_bring_up_and_lit_before_boot(self):
        launch, source = self.stage('launch'), self.stage('source')
        self.assertLess(launch.index('gpio clear PB5'), launch.index('h713_disp auto 0x34 logo'))
        self.assertLess(source.index('echo H713 panel 720p timing re-latched after source 3'),
                        source.index('gpio set PB5'))
        self.assertLess(source.index('gpio set PB5'), source.index('bootm 0x50000000 - 0x4f000000'))

    def test_every_failure_branch_relights_the_lamp_and_fan(self):
        failures = [l for l in self.text.splitlines() if 'failed - ' in l]
        self.assertEqual(len(failures), 2)
        for l in failures:
            self.assertLess(l.index('gpio set PB5'), l.index('echo'))

    def test_warm_path_draws_the_logo_and_relights_before_boot(self):
        body = self.text.split('else\n  if run hdmi_image')[0].split('logo-only fallback')[1]
        order = ['itest.l *0x0306101c == 0', 'gpio clear PB5', 'h713_disp auto 0x34 logo',
                 'gpio set PB5', 'bootm 0x50000000']
        self.assertEqual([body.index(c) for c in order], sorted(body.index(c) for c in order))
        self.assertNotIn('mips-comm-trace', body)
        self.assertNotIn('hdmi-boot-v1', body)

    def test_image_guards_come_from_the_pinned_kernel_sizes(self):
        self.assertIn(f'itest ${{filesize}} == {m.FIT_SIZE:x} ',self.text)
        self.assertIn(f'itest ${{hdmi_fdt_size}} == {m.FDT_SIZE:x} ',self.text)
        self.assertIn(f'itest ${{hdmi_fdt_end}} -le {0x50000000+m.FIT_SIZE:x} ',self.text)
    def test_build_refuses_a_kernel_the_script_does_not_pin(self):
        # 2026-10-15: a new FIT reached the board with the old sizes pinned
        # here, and U-Boot (correctly) refused to boot it.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fit,dtb=Path(d)/'k.fit',Path(d)/'b.dtb'
            fit.write_bytes(bytes(m.FIT_SIZE));dtb.write_bytes(bytes(m.FDT_SIZE))
            m.check_kernel(fit,dtb)
            for path,size in ((fit,m.FIT_SIZE+4),(dtb,m.FDT_SIZE-4)):
                with self.subTest(path=path.name):
                    path.write_bytes(bytes(size))
                    with self.assertRaises(SystemExit):m.check_kernel(fit,dtb)
                    fit.write_bytes(bytes(m.FIT_SIZE));dtb.write_bytes(bytes(m.FDT_SIZE))


if __name__=='__main__':
    unittest.main()
