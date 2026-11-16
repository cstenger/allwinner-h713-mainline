#!/usr/bin/env python3
"""Run the production health-check shell against an isolated board fixture."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class StartupHealth(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put('proc/sys/kernel/random/boot_id', 'boot-1\n')
        self.put('proc/uptime', '500 100\n')
        self.put('proc/device-tree/chosen/h713,hdmi-boot-v1',
                 bytes.fromhex('48444d49000000008b8f275c'))
        self.put('run/h713-hdmi-session/state.json', '{"phase": "ready"}\n')
        params = {
            'h713_hdmi_receiver': dict(clock_count='4', init_error='0', firmware_pin='Y',
                                      edid_ready='Y', clients='2'),
            'h713_hdmi_audio': dict(dsp_failed='N', manage_dsp='Y', graph_ready='Y', manage_tvfe='Y'),
            'h713_hdmi_signal': dict(ready='Y', failed='N', restored='N'),
        }
        for module, values in params.items():
            for key, value in values.items():
                self.put(f'sys/module/{module}/parameters/{key}', value+'\n')
        self.put('sys/module/h713_hdmi_audio/initstate', 'live\n')
        (self.root/'sys/module/h713_ddc_pins').mkdir(parents=True)
        for domain in ('tvfe', 'tvcap'):
            self.put(f'sys/devices/h713-hdmi-{domain}/power/runtime_status', 'active\n')
        self.put('usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard', '#!/bin/sh\n', 0o755)
        self.put('proc/asound/cards', 'H713HDMI\n')
        self.put('proc/asound/H713HDMI/pcm0c/sub0/status', 'state: RUNNING\n')
        self.put('bin/systemctl', '''#!/bin/sh
case "$*" in
  *ExecStart*) echo '/usr/bin/python3 --boot-handoff';;
  is-active*) echo active;;
  *) printf 'success\n0\nactive\nyes\n';;
esac
''', 0o755)
        self.put('bin/journalctl', '#!/bin/sh\nexit 0\n', 0o755)
        # No historical DSP messages survive. Any accidental dmesg use is visible.
        self.put('bin/dmesg', '#!/bin/sh\necho dmesg-used >&2\nexit 1\n', 0o755)
        source = (HERE/'check-startup.sh').read_text()
        source = re.sub(r'(?<![\w/])/(?:sys|proc|run|usr/lib/systemd|tmp)\b',
                        lambda match: str(self.root)+match.group(), source)
        self.put('check.sh', source)

    def put(self, path, data, mode=0o644):
        p = self.root/path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
        p.chmod(mode)

    def check(self):
        return subprocess.run(['/bin/sh', str(self.root/'check.sh')], capture_output=True,
                              text=True, env={**os.environ, 'PATH': str(self.root/'bin')+':'+os.environ['PATH']})

    def test_live_verified_managed_graph_passes_without_any_startup_logs(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], 'PASS')
        self.assertIn('DSP patch and graph verified by live managed state', result.stdout)
        self.assertNotIn('dmesg-used', result.stderr)

    def test_stale_good_logs_cannot_hide_failed_or_unmanaged_graph(self):
        self.put('bin/dmesg', "#!/bin/sh\nprintf 'h713-hdmi-audio: DSP versions 0000/0000\\nh713-hdmi-audio: pinned 724-pair DSP patch verified versions 1/1\\n'\n", 0o755)
        for key, bad, good in (('dsp_failed', 'Y', 'N'), ('manage_dsp', 'N', 'Y'), ('graph_ready', 'N', 'Y')):
            with self.subTest(key=key):
                path = f'sys/module/h713_hdmi_audio/parameters/{key}'
                self.put(path, bad+'\n')
                result = self.check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f'h713_hdmi_audio.{key}', result.stdout)
                self.assertNotIn('\nPASS\n', result.stdout)
                self.put(path, good+'\n')

    def test_absent_graph_status_and_incomplete_or_unloaded_module_fail(self):
        path = 'sys/module/h713_hdmi_audio/parameters/graph_ready'
        (self.root/path).unlink()
        self.assertNotEqual(self.check().returncode, 0)
        self.put(path, 'Y\n')
        for state in ('coming\n', 'going\n', ''):
            with self.subTest(state=state):
                self.put('sys/module/h713_hdmi_audio/initstate', state)
                result = self.check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('audio module not live', result.stdout)
        (self.root/'sys/module/h713_hdmi_audio/initstate').unlink()
        self.assertNotEqual(self.check().returncode, 0)

    def test_live_graph_does_not_bypass_other_runtime_health_checks(self):
        self.put('sys/module/h713_hdmi_signal/parameters/failed', 'Y\n')
        self.assertNotEqual(self.check().returncode, 0)
        self.put('sys/module/h713_hdmi_signal/parameters/failed', 'N\n')
        self.put('proc/asound/cards', '')
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no ALSA card', result.stdout)


if __name__ == '__main__':
    unittest.main()
