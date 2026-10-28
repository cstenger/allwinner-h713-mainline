#!/usr/bin/env python3
"""Exercise endpoint identity, graph validation and ordered capture release.
Each mutation runs the same tests against the changed implementation.
"""
import copy
import importlib.util
import math
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / 'pipewire-speaker.py').read_text()

def load(source=SOURCE):
    m = types.ModuleType('speaker')
    m.__file__ = str(HERE / 'pipewire-speaker.py')
    exec(compile(source, m.__file__, 'exec'), m.__dict__)
    return m

M = load()

def node(i, name, **props):
    return {'id': i, 'type': 'PipeWire:Interface:Node',
            'info': {'props': {'node.name': name, **props}}}

def fixture():
    g = [node(1, 'hdmi', **{'media.class': 'Audio/Source', 'api.alsa.pcm.card': '7', 'device.api': 'alsa'}),
         node(2, 'codec', **{'media.class': 'Audio/Sink', 'api.alsa.pcm.card': '4', 'device.api': 'alsa'}),
         node(3, M.CAPTURE, **{'node.dont-fallback': True}),
         node(4, M.PLAYBACK, **{'node.dont-fallback': True})]
    for a, b in ((1, 3), (4, 2)):
        for channel in range(2):
            g.append({'type': 'PipeWire:Interface:Link', 'info': {
                'output-node-id': a, 'input-node-id': b,
                'output-port-id': a*10+channel, 'input-port-id': b*10+channel,
                'state': 'active', 'error': None}})
    return g

class Tests(unittest.TestCase):
    def setUp(self):
        self.g = fixture()
        self.route = M.endpoints(self.g, {'Codec': '4', 'H713HDMI': '7'})

    def test_card_identity_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for n, identity in ((4, 'Codec'), (7, 'H713HDMI')):
                p = root / f'sys/class/sound/card{n}'; p.mkdir(parents=True)
                (p/'id').write_text(identity)
            self.assertEqual(M.cards(root), {'Codec': '4', 'H713HDMI': '7'})
            p = root/'sys/class/sound/card8'; p.mkdir(); (p/'id').write_text('Codec')
            with self.assertRaises(RuntimeError): M.cards(root)

    def test_reordered_cards_and_duplicates(self):
        self.assertEqual(self.route['source']['name'], 'hdmi')
        self.assertEqual(self.route['sink']['name'], 'codec')
        self.g.append(copy.deepcopy(self.g[0]))
        with self.assertRaises(RuntimeError): M.endpoints(self.g, {'Codec': '4', 'H713HDMI': '7'})

    def test_wrong_card_and_foreign_api(self):
        with self.assertRaises(RuntimeError): M.endpoints(self.g, {'Codec': '0', 'H713HDMI': '1'})
        self.g[0]['info']['props']['device.api'] = 'foreign'
        with self.assertRaises(RuntimeError): M.endpoints(self.g, {'Codec': '4', 'H713HDMI': '7'})

    def test_argv_explicit_targets_delay_and_no_fallback(self):
        a = M.argv(self.route, .03)
        self.assertIn('--capture=hdmi', a); self.assertIn('--playback=codec', a)
        self.assertIn('--delay=0.03', a)
        self.assertEqual(sum('node.dont-fallback=true' in x for x in a), 2)
        for v in (-1, .51, math.inf, math.nan):
            with self.assertRaises(ValueError): M.argv(self.route, v)

    def test_graph_requires_all_stereo_links(self):
        self.assertEqual(M.verify(self.g, self.route), {M.CAPTURE: 3, M.PLAYBACK: 4})
        self.g.pop()
        with self.assertRaises(RuntimeError): M.verify(self.g, self.route)

    def test_graph_refuses_foreign_link(self):
        self.g.append({'type': 'PipeWire:Interface:Link', 'info': {
            'output-node-id': 4, 'input-node-id': 99, 'state': 'active'}})
        with self.assertRaises(RuntimeError): M.verify(self.g, self.route)

    def test_graph_refuses_inactive_or_fallback(self):
        self.g[-1]['info']['state'] = 'paused'
        with self.assertRaises(RuntimeError): M.verify(self.g, self.route)
        self.g[-1]['info']['state'] = 'active'
        self.g[2]['info']['props']['node.dont-fallback'] = False
        with self.assertRaises(RuntimeError): M.verify(self.g, self.route)

    def test_release_suspends_exact_source_and_waits_for_closed(self):
        pcm = Mock(); pcm.exists.return_value = True
        pcm.read_text.side_effect = ['state: RUNNING', 'state: RUNNING', 'closed']
        with patch.object(M, 'Path', return_value=pcm), patch.object(M, 'resolve', return_value=([], self.route)), patch.object(M, 'command') as cmd, patch.object(M.time, 'sleep'):
            M.release()
            cmd.assert_called_once_with(['pw-cli', 'send-command', '1', 'Suspend'])

    def test_release_refuses_other_capture_clients(self):
        pcm = Mock(); pcm.exists.return_value = True; pcm.read_text.return_value = 'state: RUNNING'
        with patch.object(M, 'Path', return_value=pcm), patch.object(M, 'resolve', return_value=(self.g, self.route)), patch.object(M, 'command') as cmd:
            with self.assertRaises(RuntimeError): M.release()
            cmd.assert_not_called()

    def test_release_timeout_fails_closed(self):
        pcm = Mock(); pcm.exists.return_value = True; pcm.read_text.return_value = 'state: RUNNING'
        with patch.object(M, 'Path', return_value=pcm), patch.object(M, 'resolve', return_value=([], self.route)), patch.object(M, 'command'), patch.object(M.time, 'monotonic', side_effect=[0, 6]):
            with self.assertRaises(RuntimeError): M.release()

    def test_check_rejects_foreign_pcm_owner(self):
        self.g.append({'type': 'PipeWire:Interface:Core', 'info': {
            'user-name': 'media', 'props': {'application.process.id': '100'}}})
        p = Mock(); p.read_text.return_value = 'pipewire'
        with patch.object(M, 'resolve', return_value=(self.g, self.route)), patch.object(M, 'Path', return_value=p), patch.object(M, 'pcm_pid', return_value=999):
            with self.assertRaises(RuntimeError): M.check()


def run(module):
    global M
    M = module
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(Tests).run(result)
    return result

if __name__ == '__main__':
    r = run(load())
    for test, detail in r.errors + r.failures: print(test, detail)
    assert r.wasSuccessful(), 'baseline failed'
    print(f'PASS: {r.testsRun} lifecycle tests')
    mutations = [
        ("if identity in found:", "if False:"),
        ("if len(matches) != 1:", "if not matches:"),
        ("card == identities[identity] and props.get('device.api') == 'alsa'", "card == identities[identity]"),
        ("if not math.isfinite(delay) or not 0 <= delay <= 0.5:", "if False:"),
        ("' node.dont-fallback=true audio.rate=48000 }'", "' node.dont-fallback=false audio.rate=48000 }'"),
        ("if any(len(ports) != 2 for ports in links.values()):", "if any(len(ports) < 1 for ports in links.values()):"),
        ("elif pair[0] == nodes[PLAYBACK] or pair[1] == nodes[CAPTURE]:", "elif False:"),
        ("if info.get('state') != 'active' or info.get('error'):", "if False:"),
        ("if props.get('node.dont-fallback') not in (True, 'true'):", "if False:"),
        ("str(source), 'Suspend'", "str(route['sink']['id']), 'Suspend'"),
        ("if any(o.get('type') == 'PipeWire:Interface:Link' and", "if any(False and o.get('type') == 'PipeWire:Interface:Link' and"),
        ("raise RuntimeError('PipeWire did not close HDMI capture; backend must retain holds')", "return"),
        ("if pcm_pid(path) != pid:", "if False:"),
    ]
    for old, new in mutations:
        assert old in SOURCE, old
        r = run(load(SOURCE.replace(old, new)))
        assert not r.wasSuccessful(), 'SURVIVED: ' + old
        print('CAUGHT:', old)
    print(f'PASS: all {len(mutations)} implementation mutations caught')

    # Existing warm checker must accept the new verified route and reject a
    # stale/failed graph proof or a direct consumer under the PipeWire unit.
    checker_source = (HERE/'check-warm-shared.py').read_text()
    def checker_module(source):
        module = types.ModuleType('checker')
        module.__file__ = str(HERE/'check-warm-shared.py')
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
        return module
    def checker_cases(module):
        rec = {'label': 'warm', 'boot_id': 'b2', 'route_kind': 'pipewire',
               'speaker': 'active', 'check_startup': {'rc': 0, 'output': 'PASS'},
               'dsp_lines': ['DSP versions 0000/0000', 'patch verified versions 1/1'],
               'pipewire_check': {'rc': 0},
               'pipewire_route': {'verified': True, 'version': 1, 'boot_id': 'b2'},
               'flow': []}
        for t, ptr in ((0, 0), (3, 144000)):
            rec['flow'].append({'t': t, 'periods': ptr//256, 'xruns': 0,
                'capture_state': 'state: RUNNING', 'play_state': 'state: RUNNING',
                'capture_owner': 'pipewire', 'play_owner': 'pipewire',
                'capture_ptr': ptr, 'play_ptr': ptr})
        assert module.evaluate(rec)['passed']
        for key, value in (('verified', False), ('version', 9), ('boot_id', 'old-boot')):
            bad = copy.deepcopy(rec); bad['pipewire_route'][key] = value
            assert not module.evaluate(bad)['passed'], key
        bad = copy.deepcopy(rec); bad['pipewire_check']['rc'] = 1
        assert not module.evaluate(bad)['passed'], 'failed route command'
        bad = copy.deepcopy(rec)
        for s in bad['flow']: s['capture_owner'] = s['play_owner'] = 'hdmi-speaker'
        assert not module.evaluate(bad)['passed'], 'foreign owner'
    checker_cases(checker_module(checker_source))
    for old in ("route.get('verified') is not True", "route.get('version')!=1",
                "route.get('boot_id')!=rec.get('boot_id')", "rec.get('pipewire_check',{}).get('rc')!=0"):
        assert old in checker_source
        try: checker_cases(checker_module(checker_source.replace(old, 'False')))
        except AssertionError: print('CAUGHT checker:', old)
        else: raise AssertionError('checker mutation survived: ' + old)
    print('PASS: PipeWire warm-checker acceptance/refusal cases and 4 mutations')
