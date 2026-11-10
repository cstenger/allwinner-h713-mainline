"""Read-only preflight and monotonic wait for an explicit boot-only experiment.

No MMIO, ioctl, subprocess, sysfs writes, or ownership changes belong here.
The unchanged signal wrapper takes its original holds only after this returns.
"""
import hashlib
import json
from pathlib import Path
import stat
import time
import uuid

EXCLUDED_BOOT = 'afe48e93-6604-44de-a220-acb9416e8363'
BOOT = '/proc/sys/kernel/random/boot_id'
STATE = '/run/h713-hdmi-session/state.json'
ABSENT = tuple('/sys/module/' + name for name in (
    'h713_hdmi_signal', 'h713_ddc_pins', 'h713_scp_probe',
    'h713_scp_sampler_v2', 'h713_hdmi_dsp_probe', 'h713_hdmi_power',
    'h713_edid_clock', 'h713_hdmi_tvfe_hold')) + (
    '/run/h713-hdmi-signal/owned', '/run/h713-hdmi-signal/attempted')
PARAMS = {
    'h713_hdmi_receiver': {'clock_count': '4', 'init_error': '0',
        'edid_ready': 'Y', 'firmware_pin': 'Y', 'clients': '1',
        'park_failed': 'N', 'parked': 'N'},
    'h713_hdmi_audio': {'graph_ready': 'Y', 'dsp_failed': 'N',
        'manage_dsp': 'Y', 'manage_tvfe': 'Y', 'require_receiver_owner': 'Y'},
}


def require(ok, message):
    if not ok:
        raise RuntimeError('delay bench: ' + message)


class Bench:
    def __init__(self, manifest, digest, delay_ms, *, root=Path('/'),
                 clock=time.monotonic_ns, sleep=time.sleep, emit=None):
        require(type(delay_ms) is int and delay_ms in (0, 2000), 'invalid delay')
        raw = Path(manifest).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'manifest hash mismatch')
        self.manifest = json.loads(raw)
        require(self.manifest['schema'] == 'h713-start-delay-v1', 'manifest schema')
        require(self.manifest['excluded_boot_id'] == EXCLUDED_BOOT, 'excluded boot mismatch')
        require(self.manifest['bundle'] == '/usr/lib/h713-hdmi', 'bundle mismatch')
        require(bool(self.manifest['file_pins']), 'empty file pins')
        self.root, self.clock, self.sleep = Path(root), clock, sleep
        self.emit = emit or (lambda value: print(json.dumps(value, sort_keys=True), flush=True))
        self.delay_ms = delay_ms
        self.boot = self.read(BOOT)
        require(str(uuid.UUID(self.boot)) == self.boot, 'invalid boot ID')
        require(self.boot != EXCLUDED_BOOT, 'current failed boot is excluded')

    def path(self, name):
        path = Path(name)
        require(path.is_absolute() and '..' not in path.parts, 'unsafe manifest path')
        return self.root / str(path).lstrip('/')

    def read(self, name):
        return self.path(name).read_text().strip()

    def preflight(self):
        require(self.read(BOOT) == self.boot, 'boot changed')
        for name in ABSENT:
            require(not self.path(name).exists(), 'owner or diagnostic present: ' + name)
        state = json.loads(self.read(STATE))
        require(state.get('boot_id') == self.boot and state.get('phase') == 'ready',
                'capture session not ready on this boot')
        for module, params in PARAMS.items():
            for name, value in params.items():
                require(self.read(f'/sys/module/{module}/parameters/{name}') == value,
                        'readiness: ' + module + '.' + name)
        for domain in ('tvfe', 'tvcap'):
            require(self.read(f'/sys/devices/h713-hdmi-{domain}/power/runtime_status') == 'active',
                    'receiver domain inactive: ' + domain)
        for name, pin in self.manifest['file_pins'].items():
            path = self.path(name)
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode), 'pin is not regular: ' + name)
            require((info.st_size, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) ==
                    (pin['bytes'], pin['mode'], pin['uid'], pin['gid']), 'pin metadata: ' + name)
            require(hashlib.sha256(path.read_bytes()).hexdigest() == pin['sha256'],
                    'pin content: ' + name)

    def wait(self):
        self.preflight()
        start = previous = self.clock()
        deadline = start + self.delay_ms * 1_000_000
        self.emit({'experiment': 'h713-start-delay-v1', 'phase': 'delay-start',
                   'boot_id': self.boot, 'delay_ms': self.delay_ms, 'monotonic_ns': start})
        while True:
            now = self.clock()
            require(now >= previous, 'monotonic clock moved backwards')
            previous = now
            if now >= deadline:
                break
            # An exception aborts; short sleeps cannot shorten the deadline.
            self.sleep((deadline - now) / 1_000_000_000)
        self.preflight()
        end = self.clock()
        require(end >= now and end >= deadline, 'invalid completion clock')
        self.emit({'experiment': 'h713-start-delay-v1', 'phase': 'delay-complete',
                   'boot_id': self.boot, 'delay_ms': self.delay_ms,
                   'monotonic_ns': end, 'elapsed_ns': end - start})


def prepare(args, digest):
    """Called before the wrapper's already-loaded/idempotent path."""
    enabled = args.bench_delay_ms is not None
    require(enabled == (args.bench_manifest is not None), 'both bench options required')
    if not enabled:
        return None
    require(args.action == 'start', 'bench options only allowed on start')
    require(not args.signal_arg, 'fault/extra signal arguments forbidden')
    require(args.bundle == Path('/usr/lib/h713-hdmi'), 'alternate bundle forbidden')
    bench = Bench(args.bench_manifest, digest, args.bench_delay_ms)
    bench.preflight()
    return bench
