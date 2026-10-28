#!/usr/bin/env python3
"""Offline HDMI priority checks against the real player and launcher.

Uses a compile-time fake root, dummy media and commands that record access.
Never runs a decoder or touches the board. --mutations proves every test
detects a faulty implementation, without changing repository sources.
"""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OWNERS = (
    'proc/device-tree/chosen/h713,hdmi-boot-v1',
    'sys/firmware/devicetree/base/chosen/h713,hdmi-boot-v1',
    'sys/module/h713_hdmi_receiver',
    'sys/module/h713_hdmi_audio',
    'sys/module/h713_hdmi_signal',
    'sys/module/h713_hdmi_v4l2',
    'run/h713-hdmi-session/state.json',
)


class Fixture:
    def __init__(self, work, c_source, launcher, ring, stage):
        self.root = work / 'root'
        self.bin = work / 'bin'
        self.bin.mkdir(parents=True)
        self.calls = work / 'calls'
        self.file = work / 'dummy.mp4'
        self.file.touch()
        source = work / 'player.c'
        source.write_text(c_source)
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'gstreamer-1.0', 'gstreamer-video-1.0'], text=True))
        subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror',
                        f'-DH713_POLICY_ROOT="{self.root}"', '-o', str(self.bin / 'gst-plane-play'),
                        str(source), *flags], check=True)
        self.launcher = work / 'h713-play'
        self.launcher.write_text(launcher)
        # Probing must never reach hardware during these tests. The stub
        # produces an ordinary file decode failure if the barrier is bypassed.
        for name in ('ffprobe', 'mpv'):
            stub = self.bin / name
            stub.write_text('#!/bin/sh\necho "$0 $*" >> "$POLICY_CALLS"\nexit 1\n')
            stub.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'POLICY_CALLS': str(self.calls)}
        self.ring, self.stage = ring, stage
        self.reset()

    def reset(self):
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir()
        self.calls.unlink(missing_ok=True)

    def marker(self, path):
        marker = self.root / path
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    def run(self, *args):
        return subprocess.run(args, env=self.env, text=True, capture_output=True, timeout=10)

    def player(self, *args):
        return self.run(str(self.bin / 'gst-plane-play'), *args)


def local_boot(f):
    """A non-HDMI boot may proceed to playback's normal argument handling."""
    f.reset()
    assert f.player('--check-playback-policy').returncode == 0
    result = f.player('dummy', 'bad-codec', 'dummy')
    assert result.returncode == 2 and 'usage:' in result.stderr, result


def hdmi_owners(f):
    """Each independently present ownership marker blocks direct playback."""
    for marker in OWNERS:
        f.reset()
        f.marker(marker)
        result = f.player(str(f.file), 'h264', 'v4l2slh264dec')
        assert result.returncode == 1 and 'HDMI has priority' in result.stderr, (marker, result)


def signal_loss(f):
    """No cable, unsupported 480p, stopped and failed owners never release MIPS."""
    for signal in ('no_signal', 'unsupported 640x480', 'holding', 'locked 1280x720'):
        for phase in ('ready', 'stopped', 'failed', 'parking_failed'):
            f.reset()
            f.marker(OWNERS[0])
            signal_path = f.root / 'sys/devices/platform/h713-hdmi-ring/signal'
            signal_path.parent.mkdir(parents=True)
            signal_path.write_text(signal)
            state = f.root / OWNERS[-1]
            state.parent.mkdir(parents=True)
            state.write_text('{"phase": "%s"}' % phase)
            result = f.player('--check-playback-policy')
            assert result.returncode == 1 and 'HDMI has priority' in result.stderr, result


def unknown_ownership(f):
    """An unreadable ownership namespace is a refusal, not permission."""
    f.reset()
    (f.root / 'sys').mkdir()
    (f.root / 'sys/firmware').touch()  # ENOTDIR, independent of running as root
    result = f.player('--check-playback-policy')
    assert result.returncode == 1 and 'Cannot establish HDMI ownership' in result.stderr, result


def launcher_barrier(f):
    """Every route, even dry-run, checks before ffprobe/DRM/decoder access."""
    f.reset()
    f.marker(OWNERS[0])
    for route in ('auto', 'plane', 'gpu'):
        for dry in ([], ['--dry-run']):
            result = f.run('bash', str(f.launcher), *dry, '--route=' + route, str(f.file))
            assert result.returncode == 1 and 'HDMI has priority' in result.stderr, result
            assert not f.calls.exists(), f.calls.read_text()
    # The barrier is not a blanket refusal: a local boot reaches ffprobe.
    f.reset()
    result = f.run('bash', str(f.launcher), '--dry-run', str(f.file))
    assert result.returncode == 1 and 'no video stream' in result.stderr, result
    assert 'ffprobe' in f.calls.read_text()
    # Exercise normal command selection without opening host DRM devices.
    (f.bin / 'ffprobe').write_text('#!/bin/sh\nprintf "%s\\n" codec_name=h264 width=1280 height=720 '
                                 'coded_width=1280 coded_height=720 sample_aspect_ratio=1:1 pix_fmt=yuv420p\n')
    python = f.bin / 'python3'
    python.write_text('#!/bin/sh\nexit 1\n')
    python.chmod(0o755)
    for route in ('auto', 'plane', 'gpu'):
        result = f.run('bash', str(f.launcher), '--dry-run', '--route=' + route, str(f.file))
        expected = 'mpv' if route == 'gpu' else 'v4l2slh264dec'
        assert result.returncode == 0 and 'would run:' in result.stdout and expected in result.stdout, result


def unsupported_480p(f):
    """Both production and observation paths explicitly disable 480p."""
    for text in (f.ring, f.stage):
        load = [line for line in text.splitlines() if 'insmod ' in line]
        assert load and all('allow_480p=0' in line for line in load), load


TESTS = (local_boot, hdmi_owners, signal_loss, unknown_ownership, launcher_barrier, unsupported_480p)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutations', action='store_true')
    args = parser.parse_args()
    originals = [(ROOT / path).read_text() for path in (
        'tools/video/gst-plane-play.c', 'tools/video/h713-play',
        'tools/hdmi/h713-hdmi-ring.service', 'tools/hdmi/stage-hdmi-video.sh')]
    with tempfile.TemporaryDirectory(prefix='h713-policy-') as tmp:
        tmp = Path(tmp)
        f = Fixture(tmp / 'baseline', *originals)
        for test in TESTS:
            test(f)
            print('PASS', test.__name__)
        if not args.mutations:
            return
        # One fault per test; additionally prove every individual marker
        # and both 480p deployment paths are necessary.
        mutations = [
            (local_boot, 0, 'return 0;\n}\n\nstatic gint', 'return 1;\n}\n\nstatic gint'),
            (signal_loss, 0, 'if (check_playback_policy())', 'if (0 && check_playback_policy())'),
            (unknown_ownership, 0, 'if (errno != ENOENT)', 'if (0 && errno != ENOENT)'),
            (launcher_barrier, 1, '"$player" --check-playback-policy', ':'),
        ]
        for marker in OWNERS:
            mutations.append((hdmi_owners, 0, '"/' + marker + '"', '"/removed-marker"'))
        for index in (2, 3):
            mutations.append((unsupported_480p, index, 'allow_480p=0', 'allow_480p=1'))
        for index, (test, source_index, before, after) in enumerate(mutations):
            sources = originals.copy()
            assert before in sources[source_index], before
            sources[source_index] = sources[source_index].replace(before, after)
            f = Fixture(tmp / str(index), *sources)
            try:
                test(f)
            except AssertionError:
                print('CAUGHT', test.__name__, before)
            else:
                raise AssertionError('mutation survived: ' + test.__name__ + ' ' + before)
        print(f'{len(TESTS)} tests passed; {len(mutations)} mutations caught')


if __name__ == '__main__':
    main()
