#!/usr/bin/env python3
"""Mutate GP7 runner source in memory; all subprocess/UART operations mocked."""
import importlib.util,io,json,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('warm_tests',ROOT/'tools/hdmi/test-warm-shared.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
r=t.r;source=pathlib.Path(r.__file__).read_text()
cases=[
 ('interrupt re-enabled',"interrupt=boot_stop=='interrupt'",'interrupt=True','test_gp7_prompt_requires_markers_but_never_sends_an_interrupt'),
 ('preboot magic checked as zero',"'gp7':GP7_STOP if boot_stop=='gp7' else '00000000'","'gp7':'00000000'",'test_gp7_prompt_requires_markers_but_never_sends_an_interrupt'),
 ('automatic kernel boot accepted',"BEFORE_INTERRUPT+(b'Starting kernel',b'## Executing script',b'boot logo published')",'BEFORE_INTERRUPT','test_gp7_missing_markers_extra_reset_or_automatic_boot_never_launches'),
 ('prompt environment checks skipped',"check_bootstop_env(env['preboot'],env['bootdelay'])",'pass','test_prompt_env_and_consumed_gp7_are_verified_before_fit_load'),
 ('consumed GP7 not checked',"if got!=want:raise RuntimeError('warm prompt census differs from expected; no launch')","if False:raise RuntimeError('warm prompt census differs from expected; no launch')",'test_prompt_env_and_consumed_gp7_are_verified_before_fit_load'),
 ('wrong reboot argument',"'--reboot-argument=bootloader'","'--reboot-argument=normal'",'test_orderly_trigger_uses_kernel_bootloader_argument_only_after_guards'),
 ('boot-ID guard disabled',"if P('/proc/sys/kernel/random/boot_id').read_text().strip()!=%r:",'if False:','test_orderly_trigger_uses_kernel_bootloader_argument_only_after_guards'),
 ('driver binding ignored',"if not P('/sys/bus/platform/drivers/nvmem-reboot-mode/reboot-mode').is_dir():",'if False:','test_orderly_trigger_uses_kernel_bootloader_argument_only_after_guards'),
 ('request no longer detached'," > /run/h713-warm-shared-bootstop.log 2>&1 < /dev/null &"," > /run/h713-warm-shared-bootstop.log",'test_gp7_request_is_detached_once_and_intent_precedes_submission'),
 ('GP7 allowed with SysRq-b',"if boot_stop=='gp7' and reset!='orderly':",'if False:','test_gp7_sysrq_and_resume_mode_changes_refused_before_uart'),
 ('resume ignores mode changes',"if old_options!=self.options():raise RuntimeError('resume options differ')","if False:raise RuntimeError('resume options differ')",'test_gp7_sysrq_and_resume_mode_changes_refused_before_uart'),
]
results=[]
for name,old,new,test in cases:
 assert source.count(old)==1,(name,source.count(old))
 try:
  exec(compile(source.replace(old,new),r.__file__,'exec'),r.__dict__)
  log=io.StringIO();res=unittest.TextTestRunner(stream=log).run(unittest.TestSuite([t.GP7Stop(test)]))
  results.append({'mutation':name,'test':test,'caught':not res.wasSuccessful(),'output':log.getvalue()})
 finally:exec(compile(source,r.__file__,'exec'),r.__dict__)
print(json.dumps(results,indent=2))
assert all(x['caught'] for x in results),'mutation survived'
