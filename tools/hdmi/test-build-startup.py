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


if __name__=='__main__':
    unittest.main()
