#!/usr/bin/env python3
"""Prove each synchronization/guard test rejects a fault, in host temp files."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


t=load('sync_tests',HERE/'test-guard-sync.py')
g=load('guard_tests',HERE/'test-hdmi-hold-guard.py')


def run(module,name):
    output=io.StringIO()
    with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
        result=unittest.TextTestRunner(stream=output).run(unittest.defaultTestLoader.loadTestsFromName(name,module))
    return result.wasSuccessful()


def changed(module,before,after,count=-1):
    source=Path(module.__file__).read_text()
    if before not in source:raise RuntimeError('missing mutation anchor: '+before)
    result=types.ModuleType(module.__name__)
    result.__file__=module.__file__
    exec(compile(source.replace(before,after,count),result.__file__,'exec'),result.__dict__)
    return result


cases=[
 ('test_preview_is_read_only_and_scope_exact','u',"if dry_run or phase == 'already-current':","if phase == 'already-current':"),
 ('test_install_changes_only_scope_preserves_modes_and_backup','u',"atomic(path(root, relative), after[i], attrs[i], record['before'][i])","None"),
 ('test_repeat_install_is_noop','u',"if dry_run or phase == 'already-current':","if dry_run:"),
 ('test_bad_inputs_refused_without_target_writes','u','verify_generation(root, current[2])','None'),
 ('test_incomplete_update_recoverable_at_each_cut','u',"save(backup / 'INCOMPLETE', b'Guard transaction; finish or rollback before shutdown.\\n')","None"),
 ('test_committed_rollback_and_idempotence','u','for i in (1, 0, 2):','for i in (1, 0):'),
 ('test_rollback_refuses_corrupt_backup_foreign_target_or_other_file','u',"if [digest(b) for b in before] != r['before'] or r['before'][:2] != [OLD, OLD] or r['after'][:2] != [NEW, NEW]:",'if False:'),
 ('test_paths_and_manifest_table_fail_closed','u',"if not name or name in entries or Path(name).is_absolute() or '..' in Path(name).parts:",'if not name or name in entries:'),
 ('test_mutation_during_write_is_refused','u','if digest(p.read_bytes()) != expected:','if False:'),
 ('test_builder_pins_audit_and_candidate_without_mutating_sources','b','if sha(guard) != NEW:','if False:'),
 ('test_directory_lock_refuses_overlapping_update','u','fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)','None'),
]
failures=[]
for name,attr,before,after in cases:
    original=getattr(t,attr)
    with mock.patch.object(t,attr,changed(original,before,after)):
        survived=run(t,'Sync.'+name)
    print(('SURVIVED' if survived else 'CAUGHT'),name)
    if survived:failures.append(name)

# The CLI runs a separate interpreter: substitute a temporary script path.
with tempfile.TemporaryDirectory() as tmp:
    directory=Path(tmp)
    original=(HERE/'sync-shutdown-guard.py').read_text()
    (directory/'sync-shutdown-guard.py').write_text(original.replace('not a.install or a.dry_run','a.dry_run'))
    # Fixture copies use HERE too; preserve their normal source bytes.
    (directory/'h713-hdmi-hold-guard').write_bytes((HERE/'h713-hdmi-hold-guard').read_bytes())
    with mock.patch.object(t,'HERE',directory):
        survived=run(t,'Sync.test_cli_defaults_to_read_only_preview')
    print(('SURVIVED' if survived else 'CAUGHT'),'test_cli_defaults_to_read_only_preview')
    if survived:failures.append('CLI preview')

# Actual guard cases: sanitize real log device paths in the shared harness;
# lamp/poweroff commands are always harmless call-recording test stubs.
guard=(HERE/'h713-hdmi-hold-guard').read_text()
guard_cases=[('test_clean_teardown_leaves_every_verb_alone','[ -n "$held" ] || exit 0',':')]
guard_cases += [('test_retained_holds_turn_reboot_and_kexec_into_lamp_off_poweroff',' '+module,'') for module in g.HOLDS]
guard_cases += [('test_retained_holds_never_alter_poweroff_or_halt','*)\n','*)\n  "$OFF" poweroff\n')]
with tempfile.TemporaryDirectory() as tmp:
    script=Path(tmp)/'guard'
    for name,before,after in guard_cases:
        assert before in guard
        script.write_text(guard.replace(before,after))
        with mock.patch.object(g,'GUARD',script):survived=run(g,'Guard.'+name)
        print(('SURVIVED' if survived else 'CAUGHT'),name,before)
        if survived:failures.append(name)

rehearsal=load('audited_rehearsal',HERE/'rehearse-guard-sync.py')
with tempfile.TemporaryDirectory() as tmp:
    bundle=Path(tmp)/'bundle'
    t.b.build(bundle)
    faulty=changed(rehearsal.u,"atomic(path(root, relative), after[i], attrs[i], record['before'][i])",'None')
    with mock.patch.object(rehearsal,'u',faulty):
        try:rehearsal.rehearse(bundle)
        except (AssertionError,RuntimeError):survived=False
        else:survived=True
    print(('SURVIVED' if survived else 'CAUGHT'),'exact audited-generation rehearsal: omitted writes')
    if survived:failures.append('audited rehearsal')
print(f'{len(cases)+2+len(guard_cases)} mutations; {len(failures)} survived')
raise SystemExit(bool(failures))
