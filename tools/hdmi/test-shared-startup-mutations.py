#!/usr/bin/env python3
"""Confirm every production test detects a fault in the implementation (offline)."""
import contextlib,importlib.util,io,pathlib,types,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('production_tests',HERE/'test-shared-startup.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
# Mutate loaded implementation source, never production files or hardware.
def mutated(module,old,new):
    source=pathlib.Path(module.__file__).read_text()
    if source.count(old)!=1:raise RuntimeError('mutation anchor is not unique: '+old)
    result=types.ModuleType(module.__name__);result.__file__=module.__file__
    exec(compile(source.replace(old,new),module.__file__,'exec'),result.__dict__)
    return result
cases=[
 ('Startup.test_both_builders_include_the_health_integration','b','return package.build(output)','return None'),
 ('Startup.test_four_states_and_unacknowledged_second_boot','b','!= 48444f4b; then','== 48444f4b; then'),
 ('Startup.test_each_census_failure_stops_before_lamp_or_firmware','b',"        'itest.l *0x02001600 == 0',\n",''),
 ('Startup.test_proven_source_and_image_stages_unchanged_except_echo','b','chan=0 pid=${hdmi_pid} 3','chan=0 pid=${hdmi_pid} 4'),
 ('Ack.test_single_gp6_write_idempotence_and_dry_run','h',"struct.pack('<I',HDOK),0x18","struct.pack('<I',HDOK),0x1c"),
 ('Ack.test_health_handoff_and_session_fail_closed','h',"if state.get('boot_id')!=boot or state.get('phase')!='ready':","if False:"),
 ('Ack.test_wrong_latches_pending_gp7_and_provider_rejected_without_write','h','if gp7!=0:','if False:'),
 ('Ack.test_boot_or_latch_change_and_short_write_readback_failure_no_retry','h','if board.healthy()!=boot:','if False:'),
 ('Installer.test_dry_run_then_install_and_verified_rollback','i',"if dry_run:return {'dry_run':True,'would_install':", "if False:return {'dry_run':True,'would_install':"),
 ('Installer.test_foreign_script_kernel_or_modified_backend_refused_in_dry_run','i',"if sha(fat/'h713-kernel.fit')!=m['fit_sha256']:", 'if False:'),
 ('Installer.test_failed_enable_leaves_old_boot_and_recoverable_backup','i',"control(['daemon-reload']);control(['enable','h713-hdmi-health-ack.service'])", "control(['daemon-reload'])"),
 ('Installer.test_failed_partial_backend_update_can_rollback_without_module_change','i',"        for name in ('h713-hdmi.scr','h713-hdmi.cmd'):\n", "        atomic(root/FAT/'h713-hdmi.scr',(bundle/'h713-hdmi.scr').read_bytes())\n        for name in ('h713-hdmi.scr','h713-hdmi.cmd'):\n"),
 # Additional independent guard/readback faults in the same tests.
 ('Ack.test_boot_or_latch_change_and_short_write_readback_failure_no_retry','h','if os.pread(fd,8,0x18)!=before:', 'if False:'),
 ('Ack.test_wrong_latches_pending_gp7_and_provider_rejected_without_write','h','if gp6 not in (HDMI,HDOK):','if False:'),
 ('Ack.test_wrong_latches_pending_gp7_and_provider_rejected_without_write','h','if len(providers)!=1:','if len(providers)==0:'),
 ('Ack.test_boot_or_latch_change_and_short_write_readback_failure_no_retry','h',"if os.pread(fd,8,0x18)!=struct.pack('<II',HDOK,gp7):", 'if False:'),
]
failed=[]
def run(name):
    suite=unittest.defaultTestLoader.loadTestsFromName(name,t)
    output=io.StringIO()
    with contextlib.redirect_stdout(output):result=unittest.TextTestRunner(stream=output).run(suite)
    return result.wasSuccessful()
for name,attr,old,new in cases:
    original=getattr(t,attr)
    with mock.patch.object(t,attr,mutated(original,old,new)):
        survived=run(name)
    print(('SURVIVED' if survived else 'CAUGHT')+' '+name+' :: '+old.strip())
    if survived:failed.append(name)
# Service dependency mutation exercises the actual unit text consumed by the test.
read=pathlib.Path.read_text
unit=HERE/'h713-hdmi-health-ack.service'
def broken_read(p,*args,**kwargs):
    text=read(p,*args,**kwargs)
    return text.replace('After=h713-hdmi-capture.service h713-hdmi-signal.service','After=network.target') if p==unit else text
name='Ack.test_unit_does_not_require_signal_lock_or_start_consumers'
with mock.patch.object(pathlib.Path,'read_text',broken_read):survived=run(name)
print(('SURVIVED' if survived else 'CAUGHT')+' '+name+' :: broken unit ordering')
if survived:failed.append(name)
print('%d mutations; %d survived'%(len(cases)+1,len(failed)))
raise SystemExit(bool(failed))
