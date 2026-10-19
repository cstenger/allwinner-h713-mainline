#!/usr/bin/env python3
"""Offline fault checks for the bench module and runner; never access hardware."""
import ast
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class Process:
    def __init__(self, timeout=False, rc=0):
        self.returncode = None
        self.timeout = timeout
        self.rc = rc
        self.actions = []

    def poll(self):
        return self.returncode

    def terminate(self):
        self.actions.append('terminate')

    def kill(self):
        self.actions.append('kill')
        self.timeout = False

    def wait(self, timeout):
        self.actions.append(('wait', timeout))
        if self.timeout:
            raise subprocess.TimeoutExpired('fake process', timeout)
        self.returncode = self.rc
        return self.rc


class Cleanup(unittest.TestCase):
    def exercise(self, *, remote_fail=False, trial_timeout=False, body_fail=False,
                 player_timeout=False, started=True):
        # Execute the actual finally block and failure reporting, replacing only
        # the audible/hardware workload with an injected success or exception.
        module = ast.parse((HERE / 'run-split-test.py').read_text())
        trial = next(node for node in module.body if isinstance(node, ast.Try))
        trial.body = ast.parse("raise RuntimeError('trial failed')" if body_fail else 'pass').body
        code = compile(ast.fix_missing_locations(ast.Module(
            body=[trial, module.body[-1]], type_ignores=[])), '<runner-cleanup>', 'exec')
        commands = []

        def remote(command):
            commands.append(command)
            if remote_fail:
                raise OSError('SSH unavailable')

        with tempfile.TemporaryDirectory(prefix='h713-split-cleanup-') as directory:
            output = Path(directory)
            player = Process(timeout=player_timeout) if started else None
            board = Process() if started else None
            hpd = Process(timeout=trial_timeout) if started else None
            log, trial_log = io.StringIO(), io.StringIO()
            env = dict(subprocess=subprocess, json=json, player=player, board_play=board,
                       trial=hpd, trial_log=trial_log, out=output, log=log,
                       rows=[{'phase': 'waiting'}], cleanup_errors=[], dac_switched=started,
                       remote_control='/tmp/h713-split-control-abc.wav' if started else None,
                       PARAM='/fake/parameters', remote=remote, note=lambda msg: None)
            error = None
            try:
                exec(code, env)
            except RuntimeError as exc:
                error = str(exc)
            errors = json.loads((output / 'cleanup.json').read_text())
            self.assertEqual(json.loads((output / 'receiver-cache.json').read_text()), env['rows'])
            self.assertTrue(log.closed and trial_log.closed)
            return commands, errors, error, player, hpd

    def test_success_targets_only_this_board_playback(self):
        commands, errors, error, _, hpd = self.exercise()
        self.assertEqual(commands, [
            'echo 0 > /fake/parameters/dac_i2s',
            "pkill -fx 'pw-play /tmp/h713-split-control-abc[.]wav' || test $? -eq 1",
            'rm -f -- /tmp/h713-split-control-abc.wav'])
        self.assertEqual((errors, error), ([], None))
        self.assertEqual(hpd.actions, [('wait', 120)])

    def test_all_cleanup_runs_after_ssh_failure(self):
        commands, errors, error, player, hpd = self.exercise(remote_fail=True)
        self.assertEqual(len(commands), 3)
        self.assertEqual(len(errors), 3)
        self.assertIn('Cleanup incomplete', error)
        self.assertIn('terminate', player.actions)
        self.assertEqual(hpd.returncode, 0)

    def test_hpd_timeout_is_reported_without_killing_restore(self):
        _, errors, error, _, hpd = self.exercise(trial_timeout=True)
        self.assertIn('HPD trial restore:', errors[0])
        self.assertIn('Cleanup incomplete', error)
        self.assertEqual(hpd.actions, [('wait', 120)])

    def test_host_player_timeout_escalates_to_kill(self):
        _, errors, error, player, _ = self.exercise(player_timeout=True)
        self.assertEqual(player.actions, ['terminate', ('wait', 5), 'kill', ('wait', 5)])
        self.assertEqual((errors, error), ([], None))

    def test_original_failure_preserves_evidence_and_cleanup(self):
        commands, errors, error, _, _ = self.exercise(body_fail=True, remote_fail=True)
        self.assertEqual(error, 'trial failed')
        self.assertEqual(len(commands), 3)
        self.assertEqual(len(errors), 3)

    def test_failure_before_process_start(self):
        commands, errors, error, _, _ = self.exercise(body_fail=True, started=False)
        self.assertEqual((commands, errors, error), ([], [], 'trial failed'))


class DSP(unittest.TestCase):
    def test_commands_and_restore_faults(self):
        source = (HERE / 'h713-hdmi-speaker-split.c').read_text()
        wrappers = source[source.index('static int dsp_read(u16'):source.index('/* Route 0x89')]
        words = source[source.index('static const u16 dsp_words'):source.index('/* Internal I2S')]
        restore = source[source.index('static void restore_all(void)'):source.index('static int __init')]
        preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
typedef uint16_t u16;
typedef uint32_t u32;
#define BIT(n) (1U << (n))
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
static bool failed, applied;
static int dsp_lock, claim_error, release_error, write_error, claims, releases;
static u32 response;
static u16 writes[20];
static unsigned int count;
static int h713_dsp_claim(int *p) { (void)p; ++claims; return claim_error; }
static int h713_dsp_release(int *p) { (void)p; ++releases; return release_error; }
static int dsp_read_unlocked(u16 a, u32 *v) { (void)a; *v=response; return 0; }
static int dsp_read1_unlocked(u16 a, u32 *v) { return dsp_read_unlocked(a,v); }
static int dsp_write_unlocked(u16 a, u16 v) {
    writes[count++]=a; response=v; return write_error;
}
static u32 codec_data, i2s_data[4];
static void *codec=&codec_data, *i2s=i2s_data;
static u32 dpc_saved=BIT(29), i2s_saved[]={4,5};
static const u16 i2s_regs[]={0,4};
static u32 readl(void *p) { return *(u32 *)p; }
static void writel(u32 v, void *p) { *(u32 *)p=v; }
static void dump_i2s(const char *s) { (void)s; }
'''
        checks = r'''
int main(void) {
    u32 value;
    assert(!dsp_read(1,&value) && !dsp_read1(1,&value));
    assert(claims==2 && releases==2);
    claim_error=-ETIMEDOUT;
    assert(dsp_read(1,&value)==-ETIMEDOUT && failed && releases==2);
    assert(dsp_write(1,0)==-EIO && claims==3);
    failed=false; claim_error=0; release_error=-EIO;
    assert(dsp_read1(1,&value)==-EIO && failed && releases==3);
    failed=false; release_error=0; write_error=-ETIMEDOUT;
    assert(dsp_set(1,2)==-ETIMEDOUT && failed && releases==4);
    /* A failed command blocks DSP restoration but restores codec source bits. */
    count=0; codec_data=BIT(30)|7; restore_all();
    assert(count==0 && codec_data==(BIT(30)|7) && i2s_data[0]==0);
    applied=true; restore_all();
    assert(count==0 && codec_data==(BIT(29)|7));
    assert(i2s_data[0]==4 && i2s_data[1]==5);
    failed=false; write_error=0;
    for (unsigned int i=0;i<ARRAY_SIZE(dsp_words);++i) dsp_saved[i]=i;
    restore_all();
    assert(count==ARRAY_SIZE(dsp_words));
    for (unsigned int i=0;i<count;++i)
        assert(writes[i]==dsp_words[count-1-i]);
    /* First restore failure must stop all remaining DSP commands. */
    count=0; write_error=-ETIMEDOUT; restore_all();
    assert(count==1 && failed);
    /* Stock format updates preserve fields outside their documented masks. */
    dsp_saved[3]=0xffff; assert(dsp_target(3)==((0xffff & ~0xf93f)|0x3000));
    dsp_saved[5]=0xffff; assert(dsp_target(5)==((0xffff & ~0x23ff)|0x8180));
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='h713-split-dsp-') as directory:
            path = Path(directory)
            (path / 'test.c').write_text(preamble + wrappers + words + restore + checks)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
