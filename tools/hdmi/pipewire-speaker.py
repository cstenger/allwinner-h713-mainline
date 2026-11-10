#!/usr/bin/env python3
"""Route HDMI through the existing media-user PipeWire server.

Resolve ALSA cards by identity, refuse fallback endpoints, and close the HDMI
PCM before the capture backend's ordered shutdown. Never relaunch firmware.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

CAPTURE = 'h713-hdmi-loop-capture'
PLAYBACK = 'h713-hdmi-loop-playback'


def command(argv):
    return subprocess.check_output(argv, text=True, timeout=10)


def graph():
    return json.loads(command(['pw-dump']))


def cards(root=Path('/')):
    found = {}
    for p in (root / 'sys/class/sound').glob('card*/id'):
        identity = p.read_text().strip()
        if identity not in ('Codec', 'H713HDMI'):
            continue
        if identity in found:
            raise RuntimeError('ambiguous ALSA card ' + identity)
        found[identity] = p.parent.name[4:]
    if set(found) != {'Codec', 'H713HDMI'}:
        raise RuntimeError('required ALSA cards absent')
    return found


def endpoints(objects, identities):
    result = {}
    for label, identity, media in (('source', 'H713HDMI', 'Audio/Source'),
                                   ('sink', 'Codec', 'Audio/Sink')):
        matches = []
        for obj in objects:
            if obj.get('type') != 'PipeWire:Interface:Node':
                continue
            props = obj.get('info', {}).get('props', {})
            card = str(props.get('api.alsa.pcm.card', props.get('alsa.card', '')))
            if (props.get('media.class') == media and
                    card == identities[identity] and props.get('device.api') == 'alsa'):
                matches.append(obj)
        if len(matches) != 1:
            raise RuntimeError('absent or ambiguous PipeWire ' + label)
        obj = matches[0]
        name = obj['info']['props'].get('node.name', '')
        if not name or not re.fullmatch(r'[\w.:-]+', name):
            raise RuntimeError('invalid endpoint name')
        result[label] = {'id': obj['id'], 'name': name}
    return result


def argv(route, delay):
    if not math.isfinite(delay) or not 0 <= delay <= 0.5:
        raise ValueError('audio delay must be finite, 0..0.5 seconds')
    return ['pw-loopback', '--name=h713-hdmi-speaker', '--channels=2',
            '--channel-map=[ FL, FR ]', '--latency=20', '--delay=' + str(delay),
            '--capture=' + route['source']['name'],
            '--playback=' + route['sink']['name'],
            '--capture-props={ node.name=' + CAPTURE +
            ' node.dont-fallback=true audio.rate=48000 }',
            '--playback-props={ node.name=' + PLAYBACK +
            ' node.dont-fallback=true audio.rate=48000 }']


def verify(objects, route):
    nodes = {}
    for name in (CAPTURE, PLAYBACK):
        hits = [o for o in objects if o.get('type') == 'PipeWire:Interface:Node'
                and o.get('info', {}).get('props', {}).get('node.name') == name]
        if len(hits) != 1:
            raise RuntimeError('missing or duplicate loopback node ' + name)
        node = hits[0]
        props = node['info']['props']
        if props.get('node.dont-fallback') not in (True, 'true'):
            raise RuntimeError('loopback permits fallback')
        nodes[name] = node['id']
    expected = {(route['source']['id'], nodes[CAPTURE]),
                (nodes[PLAYBACK], route['sink']['id'])}
    links = {pair: set() for pair in expected}
    for obj in objects:
        if obj.get('type') != 'PipeWire:Interface:Link':
            continue
        info = obj.get('info', {})
        pair = (info.get('output-node-id'), info.get('input-node-id'))
        if pair in expected:
            if info.get('state') != 'active' or info.get('error'):
                raise RuntimeError('audio link not active')
            links[pair].add((info.get('output-port-id'), info.get('input-port-id')))
        elif pair[0] == nodes[PLAYBACK] or pair[1] == nodes[CAPTURE]:
            raise RuntimeError('loopback linked to a foreign endpoint')
    if any(len(ports) != 2 for ports in links.values()):
        raise RuntimeError('missing stereo channel links')
    return nodes


def resolve():
    objects = graph()
    return objects, endpoints(objects, cards())


def pcm_pid(path):
    text = Path(path).read_text()
    match = re.search(r'owner_pid\s*:\s*(\d+)', text)
    if not text.startswith('state: RUNNING') or not match:
        raise RuntimeError('PCM not running')
    return int(match[1])


def check():
    objects, route = resolve()
    nodes = verify(objects, route)
    core = [o for o in objects if o.get('type') == 'PipeWire:Interface:Core']
    if len(core) != 1 or core[0]['info'].get('user-name') != 'media':
        raise RuntimeError('wrong PipeWire server')
    pid = int(core[0]['info']['props']['application.process.id'])
    if Path('/proc/' + str(pid) + '/comm').read_text().strip() != 'pipewire':
        raise RuntimeError('server PID is not PipeWire')
    for path in ('/proc/asound/H713HDMI/pcm0c/sub0/status',
                 '/proc/asound/Codec/pcm0p/sub0/status'):
        if pcm_pid(path) != pid:
            raise RuntimeError('PCM owned by a foreign process')
    return {'verified': True, 'version': 1,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'server_pid': pid, 'route': route, 'nodes': nodes}


def release():
    """Called after loopback termination, before ordered backend teardown."""
    pcm = Path('/proc/asound/H713HDMI/pcm0c/sub0/status')
    if not pcm.exists() or pcm.read_text().strip() == 'closed':
        return
    objects, route = resolve()
    source = route['source']['id']
    if any(o.get('type') == 'PipeWire:Interface:Link' and
           o.get('info', {}).get('output-node-id') == source for o in objects):
        raise RuntimeError('another client retains HDMI capture; refusing forced release')
    command(['pw-cli', 'send-command', str(source), 'Suspend'])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not pcm.exists() or pcm.read_text().strip() == 'closed':
            return
        time.sleep(0.1)
    raise RuntimeError('PipeWire did not close HDMI capture; backend must retain holds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'check', 'release'))
    args = parser.parse_args()
    os.environ['PIPEWIRE_RUNTIME_DIR'] = '/run/user/1000'
    if args.action == 'check':
        print(json.dumps(check()))
    elif args.action == 'release':
        release()
    else:
        deadline = time.monotonic() + 45
        while True:
            try:
                _, route = resolve()
                break
            except (RuntimeError, subprocess.SubprocessError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)
        delay = float(os.environ.get('H713_HDMI_AUDIO_DELAY_SEC', '0'))
        cmd = argv(route, delay)
        print(json.dumps({'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                          'route': route, 'delay_sec': delay}), flush=True)
        os.execvp(cmd[0], cmd)


if __name__ == '__main__':
    main()
