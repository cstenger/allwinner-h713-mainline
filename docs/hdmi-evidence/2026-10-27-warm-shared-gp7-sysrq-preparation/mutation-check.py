#!/usr/bin/env python3
"""Deliberate source mutations in memory; tests use only a fake sysfs/proc tree."""
import importlib.util,io,json,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
s=importlib.util.spec_from_file_location('tests',ROOT/'tools/hdmi/test-warm-shared.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
r=t.r;source=pathlib.Path(r.__file__).read_text()
cases=[
 ('write targets GP6',"os.pwrite(fd,bytes.fromhex('dec007b0'),0x1c)","os.pwrite(fd,bytes.fromhex('dec007b0'),0x18)",'test_single_aligned_gp7_write_preserves_gp6_and_resets_without_teardown'),
 ('short write accepted',"if os.pwrite(fd,bytes.fromhex('dec007b0'),0x1c)!=4:","if os.pwrite(fd,bytes.fromhex('dec007b0'),0x1c)<0:",'test_failed_write_readback_or_post_arm_guard_never_retries_or_resets'),
 ('readback skipped',"if os.pread(fd,8,0x18)!=before[:4]+bytes.fromhex('dec007b0'):",'if False:','test_failed_write_readback_or_post_arm_guard_never_retries_or_resets'),
 ('ambiguous provider accepted','if len(providers)!=1:','if len(providers)<1:','test_bad_provider_cell_or_magic_refused_before_any_write'),
 ('RTC address check removed',"if (rtc/'reg').read_bytes()!=bytes.fromhex('0709000000000400'):",'if False:','test_bad_provider_cell_or_magic_refused_before_any_write'),
 ('cell range check removed',"if (cell/'reg').read_bytes()!=bytes.fromhex('0000001c00000004'):",'if False:','test_bad_provider_cell_or_magic_refused_before_any_write'),
 ('initial GP6 GP7 check skipped',"if len(before)!=8 or before[:4]!=bytes.fromhex('494d4448') or before[4:]!=bytes(4):",'if False:','test_wrong_initial_gp6_gp7_or_unhealthy_session_cannot_arm'),
 ('readback UART acknowledgement ignored',"marker=ABRUPT_GP7_MARKER if boot_stop=='gp7' else ABRUPT_MARKER",'marker=ABRUPT_MARKER','test_gp7_abrupt_stream_requires_readback_ack_and_no_keypress'),
 ('runner fails to select GP7 arming',"script=abrupt_script(rec['boot_id'],self.boot_stop)","script=abrupt_script(rec['boot_id'])",'test_sysrq_gp7_runner_selects_armed_script_once'),
 ('sync omitted','os.sync()','pass # sync omitted','test_single_aligned_gp7_write_preserves_gp6_and_resets_without_teardown'),
 ('post-arm guard omitted',"GP7_ARM_CODE+'\\nguard()' if boot_stop=='gp7' else ''","GP7_ARM_CODE if boot_stop=='gp7' else ''",'test_failed_write_readback_or_post_arm_guard_never_retries_or_resets'),
 ('timed interrupt enabled',"interrupt=boot_stop=='interrupt'",'interrupt=True','test_gp7_abrupt_stream_requires_readback_ack_and_no_keypress'),
]
results=[]
for name,old,new,test in cases:
 assert source.count(old)==1,(name,source.count(old))
 try:
  exec(compile(source.replace(old,new),r.__file__,'exec'),r.__dict__)
  log=io.StringIO();res=unittest.TextTestRunner(stream=log).run(unittest.TestSuite([t.GP7Abrupt(test)]))
  results.append({'mutation':name,'test':test,'caught':not res.wasSuccessful(),'output':log.getvalue()})
 finally:exec(compile(source,r.__file__,'exec'),r.__dict__)
print(json.dumps(results,indent=2));assert all(x['caught'] for x in results),'mutation survived'
