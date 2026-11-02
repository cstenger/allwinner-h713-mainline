#!/usr/bin/env python3
"""Each deliberately broken copy must fail the test named beside it. Entirely offline."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
TEST = HERE / 'test_warm_reboot.py'
B, R = 'board_script.py', 'run.py'
MUTATIONS = [
    ('poweroff-ignores-boot', B, "require(r['boot_id'] == CONFIG['expected_boot'], 'boot changed since preflight')", 'pass', 'test_every_gate'),
    ('poweroff-skips-live-gates', B, "    live_gates(r)\n    snapshot", '    snapshot', 'test_every_gate'),
    ('poweroff-skips-sram-gates', B, "    sram_gates(snapshot)\n    require(snapshot['bank", "    require(snapshot['bank", 'test_every_gate'),
    ('poweroff-ignores-banks', B, "require(snapshot['bank_backup_sha256'] == CONFIG['s0_bank_sha256'], 'bank backups changed since preflight')", 'pass', 'test_every_gate'),
    ('receipt-not-exclusive', B, 'os.O_CREAT | os.O_EXCL |', 'os.O_CREAT |', 'test_poweroff_runs_once'),
    ('sram-window-widened', B, 'address + size <= SRAM_BASE + SRAM_SIZE', 'address + size <= 0x08000000', 'test_forbidden_addresses'),
    ('collect-gates-on-signal', B, "    r['model'] = text(", "    live_gates(r)\n    r['model'] = text(", 'test_collect_reports'),
    ('collect-accepts-old-boot', B, "require(r['boot_id'] != CONFIG['previous_boot'], 'board did not boot again')", 'pass', 'test_collect_refuses'),
    ('host-reboot-not-checked', R, "need(now_boot != off['host_boot_id'], 'the host has not rebooted since the poweroff')", 'pass', 'test_arm_post_needs_a_real'),
    ('extra-reboots-allowed', R, "need(listed[-2:] == [off['host_boot_id'].replace('-', ''), now_boot.replace('-', '')],\n         'expected exactly one host reboot since the poweroff')", 'pass', 'test_arm_post_needs_exactly_one'),
    ('host-poweroff-allowed', R, "need('reboot requested from' in ended and 'poweroff requested from' not in ended,", "need(True,", 'test_arm_post_refuses_a_host_poweroff'),
    ('poweroff-before-reboot-allowed', R, "'reboot requested from' in ended and 'poweroff requested from' not in ended,", "'reboot requested from' in ended,", 'test_arm_post_refuses_a_reboot_after'),
    ('unrequested-restart-allowed', R, "'reboot requested from' in ended and 'poweroff requested from' not in ended,", "'poweroff requested from' not in ended,", 'test_arm_post_refuses_an_unrequested'),
    ('previous-boot-by-offset', B, "CONFIG['previous_boot'].replace('-', ''), '-u',", "'-1', '-u',", 'test_collect_reports'),
    ('first-advert-not-checked', R, "need('s-monitors: HDMI connected' not in journal, 'this host boot already saw a connect; not a first advert')", 'pass', 'test_arm_post_refuses_an_earlier'),
    ('off-floor-removed', R, "need(elapsed >= MIN_OFF_SECONDS,", 'need(True,', 'test_ready_enforces'),
    ('off-ceiling-removed', R, "need(elapsed <= MAX_OFF_SECONDS,", 'need(True,', 'test_ready_enforces'),
    ('observe-contacts-board', R, "    time.sleep(3)\n    host = cached_hdmi()\n    run.finish('observe'", "    on_board('x')\n    host = cached_hdmi()\n    run.finish('observe'", 'test_observe_never'),
    ('invalid-run-still-concludes', R, "    if not control_ok:\n        return 'INVALID: a matched condition did not hold; this run decides nothing'\n", '', 'test_each_outcome'),
    ('spl-count-not-checked', R, "'one_spl': len(summary['spl']) == 1,", "'one_spl': True,", 'test_failed_match'),
    ('bank-thresholds-swapped', R, "'LOST' if fraction >= .01 else 'PARTIAL'", "'PARTIAL' if fraction >= .01 else 'LOST'", 'test_known_power_loss'),
    ('ready-off-by-a-line', R, "    ready = kernel_time(kernel_log, r'h713-hdmi-signal: EDID and HPD ready')", "    ready = kernel_time(kernel_log, r'h713-hdmi-v4l2: initial signal none')", 'test_timing_reproduces'),
    ('stale-preflight-allowed', R, "need(time.monotonic() - pre['monotonic_s'] < PREFLIGHT_MAX_AGE_SECONDS, 'preflight is stale')", 'pass', 'test_poweroff_stale'),
]


def run_copy(directory):
    env = {**os.environ, 'H713_HRT_DIR': str(directory)}
    return subprocess.run([sys.executable, '-B', str(TEST)], capture_output=True, text=True, env=env, timeout=300)


def main():
    # Inside the repo: run.py finds the sealed evidence relative to its own location.
    directory = Path(tempfile.mkdtemp(prefix='.hrt-mutation-', dir=HERE.parent))
    survived = []
    try:
        originals = {name: (HERE / name).read_text() for name in (B, R)}
        def write(mapping):
            for name, text in mapping.items():
                (directory / name).write_text(text)
        write(originals)
        baseline = run_copy(directory)
        if baseline.returncode:
            sys.exit('baseline copy fails:\n' + baseline.stderr[-1500:])
        for name, target, before, after, expected in MUTATIONS:
            if originals[target].count(before) != 1:
                sys.exit('mutation anchor changed: ' + name)
            write({**originals, target: originals[target].replace(before, after)})
            out = run_copy(directory)
            caught = out.returncode != 0 and any(
                line.startswith(('FAIL: ', 'ERROR: ')) and expected in line for line in out.stderr.splitlines())
            print('%-30s %s' % (name, 'caught by ' + expected if caught else 'SURVIVED'))
            if not caught:
                survived.append(name)
    finally:
        shutil.rmtree(directory)
    print('%d mutations, %d survived' % (len(MUTATIONS), len(survived)))
    sys.exit(1 if survived else 0)


if __name__ == '__main__':
    main()
