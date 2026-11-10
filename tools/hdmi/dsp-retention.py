#!/usr/bin/env python3
"""One explicit warm DSP observation step per call. No stage loops or retries."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

SYS = Path('/sys/kernel/h713_dsp_retention')
RUN = Path('/run/h713-dsp-retention')
GUARD = Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard')
COMPETITORS = ('h713_hdmi_audio', 'h713_hdmi_receiver', 'h713_hdmi_signal', 'h713_ddc_pins',
               'h713_scp_probe', 'h713_hdmi_dsp_probe', 'h713_hdmi_dsp_observe',
               'h713_hdmi_dsp_access_audit', 'h713_tvfe_bench', 'h713_hdmi_power',
               'h713_hdmi_tvfe_hold', 'h713_edid_clock')
STEPS = ['resources', 'census',
    *['enable-clock-' + name for name in ('pll-video0', 'pll-adc', 'bus-tvcap', 'bus-cap-300m', 'vincap-dma', 'tvfe-1296m')],
    'release-demod-reset-if-asserted',
    *['stock-ccu-' + off for off in ('d10', 'd20', 'd24', 'd28', 'd2c', 'd30', 'd34', 'd38', 'd40', 'd48', 'd4c', 'd50', 'd58', 'd5c', 'd60')],
    'open-demod-bus-gate',
    *['enable-clock-' + name for name in ('bus-hdmi-audio', 'hdmi-audio', 'audio-cpu', 'audio-umac', 'audio-ihb',
                                        'pll-video2', 'deint', 'panel', 'svp-dtl', 'afbd', 'bus-disp')],
    'audiotop-census', 'audiotop-control-if-needed', 'audiotop-config-if-needed', 'audiotop-latch-if-needed',
    'dsp-status-and-lock-census', 'claim-stock-lock', 'device0-version', 'device1-version', 'release-stock-lock', 'final-check']
STAGES = {2: 'census', 8: 'receiver-clocks', 9: 'reset-release', 25: 'tvfe-clocks',
          36: 'interface-clocks', 37: 'audiotop-read', 40: 'audiotop-ready',
          41: 'lock-sampled', 42: 'lock-claimed', 43: 'device0', 44: 'device1', 46: 'complete'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_analyzer(bundle):
    import importlib.util
    spec = importlib.util.spec_from_file_location('retention_analysis', bundle / 'analyze-dsp-retention.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight(bundle, baseline, read_only=False):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('purpose') != 'bench DSP warm retention; not installed' or \
            not manifest.get('built') or not manifest.get('symvers_unchanged') or \
            os.uname().release != manifest.get('kernel_release') or \
            os.uname().version != manifest.get('kernel_uts_version'):
        raise RuntimeError('exact ABI-checked retention kernel required')
    for name, digest in manifest['bundle'].items():
        if sha(bundle / name) != digest:
            raise RuntimeError('bundle file changed: ' + name)
    if sha(GUARD) != manifest['bundle']['h713-hdmi-hold-guard']:
        raise RuntimeError('bench shutdown guard is not installed/verified')
    cmdline = Path('/proc/cmdline').read_text().split()
    for token in manifest['requires']:
        if token not in cmdline:
            raise RuntimeError('missing boot argument: ' + token)
    if Path('/proc/sys/kernel/panic').read_text().strip() != '0':
        raise RuntimeError('kernel.panic must remain 0')
    if int(Path('/proc/sys/kernel/printk').read_text().split()[0]) < 6:
        raise RuntimeError('console threshold must be at least 6 (dmesg -n 7)')
    if Path('/proc/device-tree/chosen/h713,hdmi-boot-v1').exists():
        raise RuntimeError('production handoff present')
    for module in COMPETITORS:
        if Path('/sys/module', module).exists():
            raise RuntimeError('competing owner: ' + module)
    for unit in ('capture', 'signal', 'speaker'):
        result = subprocess.run(['systemctl', 'is-active', 'h713-hdmi-' + unit + '.service'],
                                capture_output=True, text=True)
        if result.stdout.strip() != 'inactive':
            raise RuntimeError('HDMI owner is not inactive: ' + unit)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if not load_analyzer(bundle).baseline_valid(baseline) or baseline['boot_id'] == boot:
        raise RuntimeError('verified different-boot cold patched baseline required')
    journal = subprocess.check_output(['journalctl', '_BOOT_ID=' + boot.replace('-', ''),
        '_TRANSPORT=kernel', '--no-pager', '-o', 'cat'], text=True)
    proof = 'H713 RETENTION eligible=1' in journal and 'H713 RETENTION applied=1' in journal and \
            'H713 RETENTION violated:' not in journal and 'H713 TVFE command domain=TVFE' not in journal
    state = json.loads((SYS / 'state').read_text())
    valid = proof and state['schema'] == 'h713-dsp-retention-v1' and \
        bool(state['hold']) and not state['violated'] and not state['failed']
    if not valid and not read_only:
        raise RuntimeError('invalid/failed retained state; poweroff only')
    return boot, state, journal, valid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', required=True, type=Path)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('action', choices=['snapshot', 'step'])
    p.add_argument('--number', type=int)
    p.add_argument('--stage-ack')
    args = p.parse_args()
    bundle = args.bundle.resolve()
    baseline = json.loads(args.baseline.read_text())
    RUN.mkdir(exist_ok=True)
    with (RUN / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        boot, state, journal, valid = preflight(bundle, baseline, read_only=args.action == 'snapshot')
        ledger_path = RUN / 'ledger.json'
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'boot': boot}
        if ledger['boot'] != boot or (ledger.get('uncertain') and args.action != 'snapshot'):
            raise RuntimeError('stale/uncertain ledger; no retry')
        record = {'warm_boot_id': boot, 'state': state, 'baseline': baseline, 'preflight_valid': valid,
                  'monotonic_ns': time.monotonic_ns()}
        if args.action == 'snapshot':
            record['journal'] = journal
            record['debug'] = {name: Path(path).read_text() for name, path in {
                'clocks': '/sys/kernel/debug/clk/clk_summary',
                'domains': '/sys/kernel/debug/pm_genpd/pm_genpd_summary'}.items()}
            (RUN / ('snapshot-%02d.json' % state['step'])).write_text(json.dumps(record, indent=2) + '\n')
            ledger.update(snapshot=state['step'], snapshot_hash=hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest())
            ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
        else:
            if args.number != state['step'] + 1 or not 1 <= args.number <= len(STEPS):
                raise RuntimeError('exact next step required')
            if state['step'] in STAGES:
                if args.stage_ack != STAGES[state['step']] or ledger.get('snapshot') != state['step'] or \
                    ledger.get('snapshot_hash') != hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest():
                    raise RuntimeError('reviewed current snapshot and exact stage acknowledgment required')
            print(json.dumps({'event': 'before-step', 'boot': boot, 'number': args.number,
                              'operation': STEPS[args.number - 1]}), flush=True)
            ledger['uncertain'] = True
            ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
            (SYS / 'step').write_text(str(args.number) + '\n')
            after = json.loads((SYS / 'state').read_text())
            if after['step'] != args.number or after['failed'] or not after['hold'] or after['violated']:
                raise RuntimeError('step incomplete or invalid; retain state, poweroff only')
            ledger['uncertain'] = False
            ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
            record['state'] = after
        record['analysis'] = load_analyzer(bundle).analyze(record)
        print(json.dumps(record, indent=2), flush=True)


if __name__ == '__main__':
    main()
