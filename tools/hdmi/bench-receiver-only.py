#!/usr/bin/env python3
"""BENCH ONLY: the HDMI capture session without the audio module.

Bisects the lit-but-black panel after a warm reboot (trial 10: capture alone
triggers it). Uses the installed session's receiver load, clock staging and IPC checks,
with additional bench ownership guards. The default receiver-only mode never loads
h713-hdmi-audio, so its 724-pair DSP patch is never applied. `park` then runs
the production terminal shutdown's park step unchanged (MIPS reset, receiver
clocks released, receiver removed).

Runs on the prepared target with normal HDMI services inactive. All mutating
actions require --armed and --expected-boot BOOT_ID:
  bench-receiver-only.py start --armed --expected-boot BOOT_ID [--audio-no-dsp | --tvfe-only [--audio-top]]
  bench-receiver-only.py stop-audio        (only after --audio-no-dsp)
  bench-receiver-only.py stop-tvfe         (only after --tvfe-only)
  bench-receiver-only.py park

--audio-no-dsp also loads h713-hdmi-audio with manage_dsp=0: TVFE clocks,
audio-IHB, audio-top, the Audio Bridge and SPDI1 are set up exactly as in
production, but the DSP is never touched (no 724-pair patch, no graph).

--tvfe-only loads modules/hdmi-tvfe-bench (/root/h713-tvfe-bench.ko): the
production TVFE hold (its source is h713-hdmi-tvfe.c, unchanged) with no
audio blocks touched. --audio-top adds the audio module's audio-IHB word
and AudioTop setup (bench module parameter audio_top=1), with its restore;
--keep-audio-top is historical only and now refused; every current run restores AudioTop.
--top-ctl HEX / --no-top-cfg apply only part of AudioTop's setup (the control
bits to OR in, and whether to write the config word) to split it.
"""
import argparse
import fcntl
import importlib.util
import json
import struct
from pathlib import Path

BUNDLE = Path('/usr/lib/h713-hdmi')


def load_session(bundle):
    spec = importlib.util.spec_from_file_location('bench_session', bundle / 'h713-hdmi-session.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receiver_class(session):
    class ReceiverOnly(session.Session):
        audio_no_dsp = False
        tvfe_only = False
        audio_top = False
        top_ctl = None
        top_cfg = True
        TVFE_BENCH = '/root/h713-tvfe-bench.ko'

        def start(self):
            for unit in ('h713-hdmi-capture', 'h713-hdmi-signal', 'h713-hdmi-speaker'):
                if self.b.run(['systemctl', 'show', unit, '-p', 'ActiveState', '--value']).stdout.strip() != 'inactive':
                    raise RuntimeError('normal HDMI services must be inactive for a bench start')
            for owner in (session.OWNER, 'h713_tvfe_bench', 'h713_hdmi_dsp_probe',
                          'h713_hdmi_power', 'h713_edid_clock', 'h713_hdmi_tvfe_hold',
                          'h713_scp_probe', 'h713_ddc_pins', 'h713_hdmi_signal'):
                if self.loaded(owner):
                    raise RuntimeError('competing owner: ' + owner)
            if self.loaded(session.AUDIO):
                raise RuntimeError('audio is loaded: disable h713-hdmi-capture for this bench run')
            if self.prior():
                raise RuntimeError('a session already ran on this boot; cold boot required')
            handoff = self.b.binary(session.HANDOFF)
            if len(handoff) != 12:
                raise RuntimeError('invalid U-Boot HDMI handoff length')
            magic, initial, pid = struct.unpack('>III', handoff)
            if magic != 0x48444d49 or initial != 0 or pid == 0:
                raise RuntimeError('invalid U-Boot HDMI handoff')
            status = self.b.run(['python3', self.bundle + '/mips-shell.py', '--status']).stdout
            if 'MIPS core      ALIVE' not in status:
                raise RuntimeError('MIPS is not proven live')
            trace = json.loads(self.b.run(['python3', self.bundle + '/read-comm-trace.py', '--source-only']).stdout)
            if (trace.get('guards') != '43414e31/43414e31' or trace.get('source3_transition_complete') != 1
                    or trace.get('source3_worker_new') != '00000003'):
                raise RuntimeError('source3 trace guard failed')
            self.save('attempted', bench='receiver-only')
            self.b.run(['insmod', self.bundle + '/h713-hdmi-receiver.ko', 'armed=1', 'live_source3=1'])
            if self.param(session.OWNER, 'init_error') != '0':
                raise RuntimeError('receiver partial setup failed; holds retained')
            current = int(self.param(session.OWNER, 'clock_count'))
            if not 0 <= current <= 4:
                raise RuntimeError('invalid receiver clock stage')
            for stage in range(current + 1, 5):
                self.b.write(session.BASE + session.OWNER + '/parameters/clock_count', f'{stage}\n')
                self.ipc()
            self.owner_ready(0)
            self.ipc()
            if self.tvfe_only:
                before = self.b.run(['dmesg', '--color=never']).stdout
                self.b.run(['insmod', self.TVFE_BENCH, 'armed=1'] + (['audio_top=1'] if self.audio_top else [])
                           + ([f'top_ctl={self.top_ctl}'] if self.top_ctl is not None else [])
                           + ([] if self.top_cfg else ['top_cfg=0']), timeout=20)
                tail = self.fresh_log(before)
                if 'production TVFE hold applied' not in tail:
                    raise RuntimeError('TVFE hold not confirmed')
                if self.audio_top and 'audio-top (top_ctl=' not in tail:
                    raise RuntimeError('AudioTop setup not confirmed')
                self.owner_ready(1)
                self.ipc()
                bench = 'tvfe+audio-top' if self.audio_top else 'tvfe-only'
                self.save('ready', bench=bench, cold_boot_required=True)
                return {'phase': bench, 'audio_loaded': False}
            if not self.audio_no_dsp:
                # Nothing to restore: audio never ran. This is the state park() needs.
                self.save('stopped', bench='receiver-only', cold_boot_required=True, restore_verified=True)
                return {'phase': 'receiver-only', 'audio_loaded': False}
            self.b.run(['insmod', self.bundle + '/h713-hdmi-audio.ko', 'armed=1', 'live_source3=1',
                        'receiver_powered=1', 'manage_dsp=0'], timeout=20)
            if self.param(session.AUDIO, 'manage_dsp') != 'N' or self.param(session.AUDIO, 'graph_ready') != 'N':
                raise RuntimeError('audio did not load with the DSP unmanaged')
            self.owner_ready(1)
            self.ipc()
            self.save('ready', bench='audio-no-dsp', cold_boot_required=True)
            return {'phase': 'audio-no-dsp', 'audio_loaded': True, 'manage_dsp': False}

        def stop_tvfe(self):
            prior = self.prior() or {}
            if prior.get('phase') != 'ready' or prior.get('bench') not in ('tvfe-only', 'tvfe+audio-top'):
                raise RuntimeError('TVFE is not owned by this bench session')
            if not self.loaded('h713_tvfe_bench'):
                raise RuntimeError('the TVFE bench module is not loaded')
            with_top = self.param('h713_tvfe_bench', 'audio_top') == 'Y'
            before = self.b.run(['dmesg', '--color=never']).stdout
            self.b.run(['rmmod', 'h713_tvfe_bench'])
            tail = self.fresh_log(before)
            if '15 clock words and bus verified' not in tail:
                raise RuntimeError('TVFE restore not verified')
            if with_top:
                for line in ('restored audio-top', 'restored audio-IHB clock'):
                    if line not in tail:
                        raise RuntimeError('restore line missing: ' + line)
            if self.loaded('h713_tvfe_bench'):
                raise RuntimeError('TVFE removal incomplete')
            self.owner_ready(0)
            self.ipc()
            self.save('stopped', bench='tvfe-only', cold_boot_required=True, restore_verified=True)
            return {'phase': 'stopped', 'tvfe_restored': True}

        def stop_audio(self):
            """The production stop's audio removal, without the DSP checks."""
            prior = self.prior() or {}
            if prior.get('phase') != 'ready' or prior.get('bench') != 'audio-no-dsp':
                raise RuntimeError('audio is not owned by this bench session')
            if not self.loaded(session.AUDIO):
                raise RuntimeError('audio is not loaded')
            if self.param(session.AUDIO, 'manage_dsp') != 'N':
                raise RuntimeError('this bench stop is only for manage_dsp=0')
            wp = ['runuser', '-u', 'media', '--', 'env', 'XDG_RUNTIME_DIR=/run/user/1000', 'systemctl', '--user']
            active = self.b.run(wp + ['is-active', 'wireplumber.service'], check=False)
            if active.returncode not in (0, 3):
                raise RuntimeError('cannot establish WirePlumber state')
            restore = active.returncode == 0
            try:
                if restore:
                    self.b.run(wp + ['stop', 'wireplumber.service'])
                if self.b.read(session.PCM).strip() != 'closed':
                    raise RuntimeError('capture is open; audio retained')
                before = self.b.run(['dmesg', '--color=never']).stdout
                self.b.run(['rmmod', session.AUDIO])
                tail = self.fresh_log(before)
                for line in ('restored SPDI1', 'restored Audio Bridge output stream 0', 'restored audio-top',
                             'restored audio-IHB clock', '15 clock words and bus verified'):
                    if line not in tail:
                        raise RuntimeError('audio restore line missing: ' + line)
                if self.loaded(session.AUDIO):
                    raise RuntimeError('audio removal incomplete')
                self.owner_ready(0)
                self.ipc()
                self.save('stopped', bench='audio-no-dsp', cold_boot_required=True, restore_verified=True)
                return {'phase': 'stopped', 'restore_lines': 5}
            finally:
                if restore:
                    self.b.run(wp + ['start', 'wireplumber.service'])

        def fresh_log(self, before):
            after = self.b.run(['dmesg', '--color=never']).stdout
            if not after.startswith(before):
                raise RuntimeError('kernel log changed; restoration cannot be verified')
            return after[len(before):]

        def park(self):
            if self.loaded('h713_tvfe_bench'):
                raise RuntimeError('TVFE bench must restore and unload before parking')
            if (self.prior() or {}).get('bench') not in ('receiver-only', 'tvfe-only', 'audio-no-dsp'):
                raise RuntimeError('no verified bench stop available')
            return super().park()
    return ReceiverOnly


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop-audio', 'stop-tvfe', 'park', 'status'))
    parser.add_argument('--bundle', type=Path, default=BUNDLE)
    parser.add_argument('--armed', action='store_true', help='acknowledge a prepared, exclusive bench run')
    parser.add_argument('--expected-boot', help='required current boot ID for every mutating action')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--audio-no-dsp', action='store_true')
    mode.add_argument('--tvfe-only', action='store_true')
    parser.add_argument('--audio-top', action='store_true')
    parser.add_argument('--keep-audio-top', action='store_true', help='historical option; refused')
    parser.add_argument('--top-ctl', type=lambda v: int(v, 0))
    parser.add_argument('--no-top-cfg', action='store_true')
    args = parser.parse_args(argv)
    if args.action != 'status' and (not args.armed or not args.expected_boot):
        parser.error('mutating actions require --armed and --expected-boot')
    if args.keep_audio_top:
        parser.error('retained AudioTop mode is historical only; restoration is required')
    if args.top_ctl is not None and (args.top_ctl < 0 or args.top_ctl & ~0x700):
        parser.error('--top-ctl must be a subset of 0x700')
    if (args.top_ctl is not None or args.no_top_cfg) and not args.audio_top:
        parser.error('--top-ctl/--no-top-cfg need --audio-top')
    if args.audio_top and not args.tvfe_only:
        parser.error('--audio-top needs --tvfe-only')
    if args.action != 'start' and any((args.audio_no_dsp, args.tvfe_only, args.audio_top,
                                     args.top_ctl is not None, args.no_top_cfg)):
        parser.error('mode flags apply only to start')
    try:
        session = load_session(args.bundle)
        board = session.Board()
        s = receiver_class(session)(board, args.bundle, True)
        if args.action != 'status' and s.boot != args.expected_boot:
            raise RuntimeError('boot ID differs from --expected-boot; no action taken')
        s.audio_no_dsp, s.tvfe_only, s.audio_top = args.audio_no_dsp, args.tvfe_only, args.audio_top
        s.top_ctl, s.top_cfg = args.top_ctl, not args.no_top_cfg
        if args.action == 'status':
            print(json.dumps(s.status()), flush=True)
            return
        Path('/run/h713-hdmi-session').mkdir(exist_ok=True)
        with open('/run/h713-hdmi-session/lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps(getattr(s, args.action.replace('-', '_'))()), flush=True)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'Bench action failed: {error}\n')


if __name__ == '__main__':
    main()
