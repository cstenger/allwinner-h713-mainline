#!/usr/bin/env python3
"""Exercise boot/ownership/failure refusal at the userspace MMIO boundary."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('observe', Path(__file__).with_name('dsp-observe.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Fake:
    def __init__(self):
        self.files = {'/proc/sys/kernel/random/boot_id': b'boot-a\n',
                      '/proc/device-tree/chosen/h713,dsp-observation-v1': bytes.fromhex('44535031'),
                      '/bundle/h713-hdmi-dsp-observe.ko': b'module', m.GUARD: b'guard'}
        for node in ('display@5600000', 'cpu-comm@3003000'):
            self.files['/proc/device-tree/soc/' + node + '/status'] = b'disabled\0'
        self.files['/bundle/manifest.json'] = json.dumps({
            'kernel_release': '6.18.38', 'module_sha256': hashlib.sha256(b'module').hexdigest(),
            'guard_sha256': hashlib.sha256(b'guard').hexdigest()}).encode()
        self.calls, self.writes, self.fail_read = [], [], False
    def read(self, path):return self.files[path]
    def exists(self, path):return path in self.files
    def save(self, value):self.files[m.STATE] = json.dumps(value).encode()
    def run(self, argv):
        self.calls.append(argv)
        if argv[0] == 'systemctl':return 'inactive\n'
        if argv[0] == 'uname':return '6.18.38\n'
        if argv[0] == 'modinfo':return '6.18.38 SMP\n'
        if argv[0] == 'insmod':
            for k,v in {'ready':'Y', 'failed':'N', 'attempted':'N', 'released':'N'}.items():
                self.files[m.PARAM+k] = (v+'\n').encode()
            self.files['/sys/module/'+m.MODULE] = b''
        return ''
    def write(self, path, value):
        self.writes.append((path, value))
        if path == m.PARAM+'probe_versions':
            self.files[m.PARAM+'attempted'] = b'Y\n'
            if self.fail_read:self.files[m.PARAM+'failed'] = b'Y\n'
            else:
                self.files[m.PARAM+'version0'] = b'65537\n'
                self.files[m.PARAM+'version1'] = b'1\n'
        elif path == m.PARAM+'restore':self.files[m.PARAM+'released'] = b'Y\n'
        else:raise AssertionError('unexpected hardware operation')


class Boundary(unittest.TestCase):
    def setUp(self):self.b = Fake(); self.s = m.Observation(self.b, '/bundle', 'boot-a')
    def test_prepare_never_issues_dsp_request(self):
        self.assertEqual(self.s.prepare()['DSP_commands_issued'], 0)
        self.assertEqual(self.b.writes, [])
    def test_cross_boot_handoff_missing_marker_competitor_and_bad_guard_refuse_before_load(self):
        for kind in ('boot', 'handoff', 'marker', 'owner', 'guard', 'module', 'display', 'cpucomm', 'auditowner', 'auditstate'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind=='boot':self.b.files['/proc/sys/kernel/random/boot_id']=b'other'
                elif kind=='handoff':self.b.files['/proc/device-tree/chosen/h713,hdmi-boot-v1']=b'old'
                elif kind=='marker':self.b.files['/proc/device-tree/chosen/h713,dsp-observation-v1']=b'bad'
                elif kind=='owner':self.b.files['/sys/module/h713_hdmi_signal']=b''
                elif kind=='guard':self.b.files[m.GUARD]=b'old guard'
                elif kind=='display':self.b.files['/proc/device-tree/soc/display@5600000/status']=b'okay\0'
                elif kind=='auditowner':self.b.files['/sys/module/h713_hdmi_dsp_access_audit']=b''
                elif kind=='auditstate':self.b.files['/run/h713-dsp-access-audit/state.json']=b'{}'
                elif kind=='cpucomm':self.b.files['/dev/cpu_comm_fd']=b''
                else:self.b.files['/bundle/h713-hdmi-dsp-observe.ko']=b'other module'
                with self.assertRaises(RuntimeError):self.s.prepare()
                self.assertFalse(any(c[0]=='insmod' for c in self.b.calls))
                self.assertEqual(self.b.writes, [])
    def test_success_preserves_full_raw_words_and_is_one_shot(self):
        self.s.prepare(); result=self.s.versions()
        self.assertEqual(result['version0_raw'], 65537)
        self.assertEqual(len(self.b.writes), 1)
        with self.assertRaises(RuntimeError):self.s.versions()
        self.s.restore()
        with self.assertRaises(RuntimeError):self.s.prepare()
        self.assertEqual(len(self.b.writes), 2)
    def test_failure_blocks_retry_restore_and_reload(self):
        self.s.prepare();self.b.fail_read=True
        with self.assertRaises(RuntimeError):self.s.versions()
        for action in (self.s.versions,self.s.restore,self.s.prepare):
            with self.assertRaises(RuntimeError):action()
        self.assertEqual(len(self.b.writes), 1)
    def test_prepare_only_cleanup_does_not_issue_dsp_command(self):
        self.s.prepare();self.s.restore()
        self.assertEqual(self.b.writes, [(m.PARAM+'restore', b'1\n')])


if __name__ == '__main__':unittest.main()
