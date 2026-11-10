#!/usr/bin/env python3
"""Negative controls against actual implementation; never edit source or hardware."""
import contextlib
import importlib.util
import io
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def mutant(module, before, after):
    source = Path(module.__file__).read_text()
    if source.count(before) != 1: raise ValueError('mutation anchor not unique: '+before)
    changed = types.ModuleType(module.__name__);changed.__file__ = module.__file__
    exec(compile(source.replace(before, after), module.__file__, 'exec'), changed.__dict__)
    return changed


def passes(module, name):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        return unittest.TextTestRunner(stream=output).run(
            unittest.defaultTestLoader.loadTestsFromName(name, module)).wasSuccessful()


def main():
    shell = load('ipc_tests', HERE.parent/'mips/test-ipc-completion.py')
    session = load('session_tests', HERE/'test-hdmi-session.py')
    ordering = load('ordering_tests', HERE/'test-parallel-capture.py')
    release = load('release_tests', HERE.parent/'release/test-release.py')
    cases = [
        (shell, 'Completion.test_prompt_echo_partial_and_wrong_body_do_not_pass', 'm',
         'if (ipc_reply_complete(reply) and down.wroff == down.rdoff',
         'if (True and down.wroff == down.rdoff'),
        (shell, 'Completion.test_stale_reply_is_discarded_and_cannot_supply_completion', 'm',
         '    reply = b""\n', '    reply = stale\n'),
        (shell, 'Completion.test_full_reply_requires_command_consumption', 'm',
         'and down.wroff == down.rdoff', 'and True'),
        (shell, 'Completion.test_parked_busy_and_invalid_deadline_never_send', 'm',
         '    if not alive:\n        raise RuntimeError("MIPS is parked; refusing IPC request")',
         '    if False:\n        raise RuntimeError("MIPS is parked; refusing IPC request")'),
        (shell, 'Completion.test_flood_and_short_publication_fail', 'm',
         'if len(reply) > 4096:', 'if False:'),
        (session, 'Lifecycle.test_completion_result_cannot_be_replaced_by_prompt_or_wrong_schema', 'm',
         "result.get('complete') is not True", 'False'),
        (release, 'ReleaseTests.test_overlay_has_runtime_units_and_no_bench_consumer', 'b',
         "if name not in ('h713-hdmi-video.service', 'h713-hdmi-prepare.service'):",
         "if name != 'h713-hdmi-video.service':"),
    ]
    failures = []
    for module, name, attr, before, after in cases:
        if not passes(module, name): raise RuntimeError('baseline fails: '+name)
        with patch.object(module, attr, mutant(getattr(module, attr), before, after)):
            survived = passes(module, name)
        print(('SURVIVED ' if survived else 'CAUGHT ')+name)
        if survived: failures.append(name)
    read = Path.read_text
    for source, before, after in (
        ('h713-hdmi-capture-startup.service', 'user@1000.service ', ''),
        ('h713-hdmi-prepare.service', 'After=systemd-modules-load.service',
         'After=systemd-modules-load.service user@1000.service'),
    ):
        def changed(path, *args, **kwargs):
            text = read(path, *args, **kwargs)
            return text.replace(before, after) if path == HERE/source else text
        name = 'Ordering.test_parallel_start_preserves_lifecycle_and_signal_gates'
        if not passes(ordering, name): raise RuntimeError('ordering baseline fails')
        with patch.object(Path, 'read_text', changed): survived = passes(ordering, name)
        print(('SURVIVED ' if survived else 'CAUGHT ')+source)
        if survived: failures.append(source)
    print(f'{len(cases)+2} mutations; {len(failures)} survived')
    return bool(failures)


if __name__ == '__main__': raise SystemExit(main())
